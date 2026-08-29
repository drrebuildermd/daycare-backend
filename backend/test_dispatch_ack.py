"""배차표 확인(기사 -> 관리자) 저장소 계층 검증.

실제 Supabase 테이블 없이 가짜 클라이언트로 돌린다.
어떤 테이블에 어떤 컬럼으로 쓰는지가 supabase_schema.sql 과 맞는지 본다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_dispatch_ack.py
"""
import re
import sys
from datetime import date

import app.dispatch as dispatch
from app.models import DispatchAckCreate

SCHEMA = open("supabase_schema.sql", encoding="utf-8").read()


def schema_unique(table: str) -> str:
    """스키마에 적힌 그 표의 유일키를 'a,b,c' 꼴로 돌려준다.

    upsert 의 on_conflict 는 이 값과 정확히 같아야 한다. 다르면 Postgres 가
    충돌을 못 알아보고 새 줄을 만든다.
    """
    body = re.search(
        rf"create table if not exists public\.{table} \((.*?)\n\);", SCHEMA, re.S
    ).group(1)
    columns = re.search(r"unique \(([^)]*)\)", body, re.S).group(1)
    return ",".join(part.strip() for part in columns.split(","))


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
ROW = {
    "id": 1, "service_date": date(2026, 8, 27), "vehicle_id": "v1",
    "vehicle_label": "스타렉스 12가3456", "driver_name": "홍길동",
    "acknowledged_at": "2026-08-27T08:10:00+09:00",
}


class FakeQuery:
    def __init__(self, table):
        self.table = table

    def _log(self, op, **kw):
        calls.append({"table": self.table, "op": op, **kw})
        return self

    def upsert(self, row, on_conflict=None):
        return self._log("upsert", row=row, on_conflict=on_conflict)

    def select(self, *a):
        return self._log("select")

    def eq(self, column, value):
        return self._log("eq", column=column, value=value)

    def order(self, column, desc=False):
        return self._log("order", column=column)

    def execute(self):
        return type("R", (), {"data": [ROW]})()


class FakeSupabase:
    def table(self, name):
        return FakeQuery(name)


dispatch.get_supabase = lambda: FakeSupabase()

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


print("--- 1. 확인 저장 ---")
calls.clear()
record = dispatch.acknowledge_dispatch(
    DispatchAckCreate(vehicle_id="v1", vehicle_label="스타렉스 12가3456",
                      driver_name="홍길동"),
    date(2026, 8, 27),
)
upsert = next(c for c in calls if c["op"] == "upsert")
check("dispatch_acks 테이블 사용", upsert["table"] == "dispatch_acks", upsert["table"])
check("on_conflict 가 유니크 제약과 일치",
      upsert["on_conflict"] == schema_unique("dispatch_acks"),
      f'코드 {upsert["on_conflict"]} / 스키마 {schema_unique("dispatch_acks")}')
unknown = set(upsert["row"]) - schema_columns("dispatch_acks")
check("보내는 컬럼이 전부 스키마에 존재", not unknown, unknown or "전부 일치")
check("반환 레코드 매핑", record.vehicle_label == "스타렉스 12가3456" and record.driver_name == "홍길동")
check("service_date 를 문자열로 변환", isinstance(record.service_date, str), record.service_date)

print("--- 2. 오늘 확인 목록 조회 ---")
calls.clear()
rows = dispatch.list_acknowledgements(date(2026, 8, 27))
eq = next(c for c in calls if c["op"] == "eq")
check("service_date 로 필터", eq["column"] == "service_date", eq["value"])
check("확인 시각 순 정렬",
      any(c["op"] == "order" and c["column"] == "acknowledged_at" for c in calls))
check("레코드 1건 반환", len(rows) == 1, len(rows))

print("--- 3. 기사 이름 없이도 저장되는가 ---")
calls.clear()
dispatch.acknowledge_dispatch(
    DispatchAckCreate(vehicle_id="v2", vehicle_label="카니발 34나7890"),
    date(2026, 8, 27),
)
upsert = next(c for c in calls if c["op"] == "upsert")
check("driver_name 이 None 이어도 전송됨", upsert["row"]["driver_name"] is None)

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과")
