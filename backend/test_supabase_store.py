"""Supabase 저장소 계층 검증.

실제 Supabase 테이블 없이도 돌도록 가짜 클라이언트를 끼워 넣고,
'어떤 테이블에 어떤 컬럼으로 무슨 쿼리를 날리는지'가 supabase_schema.sql 과
일치하는지 확인한다. 컬럼명 오타나 on_conflict 실수를 여기서 잡는다.

실행: .venv\\Scripts\\python.exe -X utf8 test_supabase_store.py
"""
import re
import sys
from datetime import date

import app.database as db
import app.drivers as drivers
from app.models import DriverDeviceCreate, RideCompletionCreate

# --- supabase_schema.sql 에서 실제 컬럼 목록을 읽어온다 -----------------------
SCHEMA = open("supabase_schema.sql", encoding="utf-8").read()


def schema_columns(table: str) -> set[str]:
    body = re.search(
        rf"create table if not exists public\.{table} \((.*?)\n\);", SCHEMA, re.S
    ).group(1)
    columns = set()
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--") or line.startswith("constraint"):
            continue
        columns.add(line.split()[0])
    return columns


calls = []


class FakeQuery:
    def __init__(self, table, rows):
        self.table = table
        self.rows = rows

    def _log(self, op, **kwargs):
        calls.append({"table": self.table, "op": op, **kwargs})
        return self

    def upsert(self, row, on_conflict=None):
        return self._log("upsert", row=row, on_conflict=on_conflict)

    def update(self, row):
        return self._log("update", row=row)

    def select(self, *args):
        return self._log("select", columns=args)

    def eq(self, column, value):
        return self._log("eq", column=column, value=value)

    def order(self, column, desc=False):
        return self._log("order", column=column)

    def limit(self, n):
        return self._log("limit", n=n)

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table

    def table(self, name):
        return FakeQuery(name, self.rows_by_table.get(name, []))


COMPLETION_ROW = {
    "id": 1, "service_date": date(2026, 8, 19), "passenger_id": "P001",
    "passenger_name": "김어르신", "vehicle_id": "v1", "vehicle_type": "스타리아",
    "vehicle_plate_number": "12가3456", "trip_round": 1, "scheduled_pickup": "08:26",
    "completed_at": "2026-08-19T11:58:49+09:00",
    "created_at": "2026-08-19T11:58:49+09:00",
    "updated_at": "2026-08-19T11:58:49+09:00",
}

DEVICE_ROW = {
    "id": 7, "driver_name": "명민승",
    "expo_push_token": "ExponentPushToken[abcdefghijklmnopqrstuv]",
    "device_label": "갤럭시 S23", "is_active": True,
    "created_at": "2026-08-19T12:00:00+09:00",
    "updated_at": "2026-08-19T12:00:00+09:00",
}

fake = FakeSupabase({"ride_completions": [COMPLETION_ROW], "driver_devices": [DEVICE_ROW]})
db.get_supabase = lambda: fake
drivers.get_supabase = lambda: fake

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


print("--- 1. 송영 일지 저장 (upsert) ---")
calls.clear()
record = db.upsert_completion(
    RideCompletionCreate(
        passenger_id="P001", passenger_name="김어르신", vehicle_id="v1",
        vehicle_type="스타리아", vehicle_plate_number="12가3456",
        trip_round=1, scheduled_pickup="08:26",
    ),
    None,
)
upsert = next(c for c in calls if c["op"] == "upsert")
check("ride_completions 테이블 사용", upsert["table"] == "ride_completions", upsert["table"])
check("on_conflict 가 유니크 제약과 일치",
      upsert["on_conflict"] == "service_date,passenger_id", upsert["on_conflict"])
unknown = set(upsert["row"]) - schema_columns("ride_completions")
check("보내는 컬럼이 전부 스키마에 존재", not unknown, unknown or "전부 일치")
check("반환 레코드 매핑", record.passenger_name == "김어르신" and record.trip_round == 1)
check("service_date 를 문자열로 변환 (date 객체가 새어나오지 않음)",
      isinstance(record.service_date, str), record.service_date)

print("--- 2. 오늘 일지 조회 ---")
calls.clear()
rows = db.list_completions(date(2026, 8, 19), None)
eq = next(c for c in calls if c["op"] == "eq")
check("service_date 로 필터", eq["column"] == "service_date", eq)
check("완료시각 순 정렬",
      any(c["op"] == "order" and c["column"] == "completed_at" for c in calls))
check("레코드 1건 반환", len(rows) == 1, len(rows))

print("--- 3. 기사 기기 등록 ---")
calls.clear()
device = drivers.register_device(DriverDeviceCreate(
    driver_name="명민승",
    expo_push_token="ExponentPushToken[abcdefghijklmnopqrstuv]",
    device_label="갤럭시 S23",
))
upsert = next(c for c in calls if c["op"] == "upsert")
check("driver_devices 테이블 사용", upsert["table"] == "driver_devices", upsert["table"])
check("토큰 기준 upsert", upsert["on_conflict"] == "expo_push_token", upsert["on_conflict"])
unknown = set(upsert["row"]) - schema_columns("driver_devices")
check("보내는 컬럼이 전부 스키마에 존재", not unknown, unknown or "전부 일치")
check("반환 레코드 매핑", device.driver_name == "명민승" and device.is_active)

print("--- 4. 활성 기기만 조회 ---")
calls.clear()
drivers.list_devices()
check("is_active=True 로 필터",
      any(c["op"] == "eq" and c["column"] == "is_active" and c["value"] is True for c in calls))

print("--- 5. Expo 토큰 형식 검증 ---")
for token, should_pass in [
    ("ExponentPushToken[abc123]", True),
    ("ExpoPushToken[abc123]", True),
    ("그냥문자열", False),
    ("ExponentPushToken[abc123", False),
    ("", False),
]:
    try:
        DriverDeviceCreate(driver_name="명민승", expo_push_token=token)
        passed = True
    except Exception:
        passed = False
    check(f"토큰 {token!r} -> {'허용' if should_pass else '거절'}", passed == should_pass)

print("--- 6. 기동 시 테이블 누락 감지 ---")


class BrokenQuery(FakeQuery):
    def execute(self):
        from postgrest.exceptions import APIError
        raise APIError({"message": "Could not find the table", "code": "PGRST205"})


class BrokenSupabase:
    def table(self, name):
        return BrokenQuery(name, [])


db.get_supabase = lambda: BrokenSupabase()
try:
    db.init_database(None)
    check("테이블 없으면 기동 실패", False, "예외가 발생하지 않음")
except RuntimeError as error:
    check("테이블 없으면 기동 실패", True)
    check("안내에 스키마 파일명 포함", "supabase_schema.sql" in str(error), str(error)[:70])

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과")
