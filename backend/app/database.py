"""송영 완료 기록 저장소 (Supabase).

예전에는 SQLite 파일에 저장했는데, Render 무료 티어는 재배포/슬립마다 디스크가
초기화되어 일지가 통째로 사라진다. 그래서 Supabase(Postgres)로 옮겼다.

바깥에서 보는 함수 이름과 반환 타입은 SQLite 시절과 동일하게 유지했다.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from postgrest.exceptions import APIError

from .config import Settings
from .models import RideCompletionCreate, RideCompletionRecord
from .supabase_client import get_supabase

KST = ZoneInfo("Asia/Seoul")

TABLE = "ride_completions"
# 배차 확정 문자를 누구에게 언제 보냈는지. 같은 동선으로 다시 보내지 않으려고 둔다.
DISPATCH_SMS_TABLE = "driver_dispatch_sms"

_SCHEMA_HINT = (
    "Supabase에 '{table}' 테이블이 없습니다. "
    "backend/supabase_schema.sql 을 Supabase 대시보드 > SQL Editor 에서 실행해 주세요."
)


def today_kst() -> date:
    return datetime.now(KST).date()


def init_database(settings: Settings) -> None:
    """기동 시 테이블 존재 여부를 확인한다.

    스키마 SQL을 깜빡한 채 배포하면 첫 '탑승 완료'를 누를 때까지 아무도 모른다.
    여기서 미리 터뜨려 배포 로그에 남긴다.
    """
    for table in (TABLE, "driver_devices", "dispatches", "dispatch_acks"):
        try:
            get_supabase().table(table).select("id").limit(1).execute()
        except APIError as error:
            raise RuntimeError(_SCHEMA_HINT.format(table=table)) from error


def upsert_completion(
    payload: RideCompletionCreate, settings: Settings
) -> RideCompletionRecord:
    now = datetime.now(KST).replace(microsecond=0)
    row = {
        "service_date": now.date().isoformat(),
        "passenger_id": payload.passenger_id,
        "passenger_name": payload.passenger_name,
        "vehicle_id": payload.vehicle_id,
        "vehicle_type": payload.vehicle_type,
        "vehicle_plate_number": payload.vehicle_plate_number,
        "trip_round": payload.trip_round,
        "scheduled_pickup": payload.scheduled_pickup,
        "completed_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    try:
        # 같은 날 같은 어르신을 다시 찍으면 새 줄을 만들지 않고 갱신한다.
        result = (
            get_supabase()
            .table(TABLE)
            .upsert(row, on_conflict="service_date,passenger_id")
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"송영 일지 저장에 실패했습니다: {error.message}"
        ) from error

    if not result.data:
        raise HTTPException(status_code=502, detail="송영 일지 저장 결과가 비어 있습니다.")
    return _to_record(result.data[0])


def list_completions(
    service_date: date, settings: Settings
) -> list[RideCompletionRecord]:
    try:
        result = (
            get_supabase()
            .table(TABLE)
            .select("*")
            .eq("service_date", service_date.isoformat())
            .order("completed_at", desc=False)
            .order("passenger_name", desc=False)
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"송영 일지 조회에 실패했습니다: {error.message}"
        ) from error
    return [_to_record(row) for row in result.data]


def _to_record(row: dict) -> RideCompletionRecord:
    return RideCompletionRecord(
        service_date=str(row["service_date"]),
        passenger_id=row["passenger_id"],
        passenger_name=row["passenger_name"],
        vehicle_id=row["vehicle_id"],
        vehicle_type=row["vehicle_type"],
        vehicle_plate_number=row["vehicle_plate_number"],
        trip_round=row["trip_round"],
        scheduled_pickup=row["scheduled_pickup"],
        completed_at=str(row["completed_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


# ──────────────────────────────────────────────────────────────
# 배차 확정 문자 중복 방지
#
# 원장님은 조건을 바꿔가며 배차를 여러 번 계산한다. 그때마다 문자가 나가면
# 요금이 새고 기사님도 지친다. 그래서 기사님별 동선을 지문처럼 남겨두고,
# 같으면 건너뛴다.
#
# 이 테이블이 아직 없어도 서버가 죽으면 안 된다. 없으면 중복 방지만 꺼지고
# (= 예전처럼 매번 발송) 나머지는 그대로 돈다. init_database 의 필수 목록에
# 넣지 않은 이유다.
# ──────────────────────────────────────────────────────────────
def was_dispatch_sms_sent(service_date: date, vehicle_id: str, signature: str) -> bool:
    """이미 같은 내용으로 보냈으면 True."""
    result = (
        get_supabase()
        .table(DISPATCH_SMS_TABLE)
        .select("signature")
        .eq("service_date", service_date.isoformat())
        .eq("vehicle_id", vehicle_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return bool(rows) and rows[0].get("signature") == signature


def mark_dispatch_sms_sent(service_date: date, vehicle_id: str, signature: str) -> None:
    """보냈다고 기록한다. 같은 날 같은 차량이면 덮어쓴다."""
    get_supabase().table(DISPATCH_SMS_TABLE).upsert(
        {
            "service_date": service_date.isoformat(),
            "vehicle_id": vehicle_id,
            "signature": signature,
            "sent_at": datetime.now(KST).replace(microsecond=0).isoformat(),
        },
        on_conflict="service_date,vehicle_id",
    ).execute()
