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
    for table in (TABLE, "driver_devices"):
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
