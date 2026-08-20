"""기사님 기기(Expo Push Token) 저장소.

3번 과제(푸시 알림)에서 '배차 전송'을 누르면 여기 등록된 토큰으로 발송한다.
이번 단계에서는 등록/조회/해제까지만 만들고 실제 발송은 다음 과제에서 붙인다.
"""
from datetime import datetime

from fastapi import HTTPException
from postgrest.exceptions import APIError

from .database import KST
from .models import DriverDeviceCreate, DriverDeviceRecord
from .supabase_client import get_supabase

TABLE = "driver_devices"


def register_device(payload: DriverDeviceCreate) -> DriverDeviceRecord:
    """기기를 등록하거나, 이미 있는 토큰이면 담당 기사/라벨을 갱신한다.

    같은 폰을 다른 기사님이 쓰게 되는 경우가 있어 토큰 기준으로 덮어쓴다.
    """
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    row = {
        "driver_name": payload.driver_name.strip(),
        "expo_push_token": payload.expo_push_token.strip(),
        "device_label": (payload.device_label or "").strip() or None,
        "is_active": True,
        "updated_at": now,
    }
    try:
        result = (
            get_supabase()
            .table(TABLE)
            .upsert(row, on_conflict="expo_push_token")
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"기기 등록에 실패했습니다: {error.message}"
        ) from error
    if not result.data:
        raise HTTPException(status_code=502, detail="기기 등록 결과가 비어 있습니다.")
    return _to_record(result.data[0])


def list_devices(driver_name: str | None = None) -> list[DriverDeviceRecord]:
    try:
        query = get_supabase().table(TABLE).select("*").eq("is_active", True)
        if driver_name:
            query = query.eq("driver_name", driver_name.strip())
        result = query.order("driver_name", desc=False).execute()
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"기기 목록 조회에 실패했습니다: {error.message}"
        ) from error
    return [_to_record(row) for row in result.data]


def deactivate_device(expo_push_token: str) -> None:
    """기기를 발송 대상에서 뺀다. 이력은 남긴다.

    푸시 발송 시 Expo가 DeviceNotRegistered 를 돌려주면 여기로 정리하면 된다.
    """
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    try:
        result = (
            get_supabase()
            .table(TABLE)
            .update({"is_active": False, "updated_at": now})
            .eq("expo_push_token", expo_push_token.strip())
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"기기 해제에 실패했습니다: {error.message}"
        ) from error
    if not result.data:
        raise HTTPException(status_code=404, detail="등록되지 않은 기기 토큰입니다.")


def _to_record(row: dict) -> DriverDeviceRecord:
    return DriverDeviceRecord(
        id=row["id"],
        driver_name=row["driver_name"],
        expo_push_token=row["expo_push_token"],
        device_label=row.get("device_label"),
        is_active=row["is_active"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
