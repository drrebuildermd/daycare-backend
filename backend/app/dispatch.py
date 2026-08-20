"""배차 결과 보관 + 기사님 폰으로 푸시 발송.

관리자가 PC에서 '배차 전송'을 누르면
  1) 오늘의 배차 결과를 Supabase에 저장하고 (기사님 폰이 지도를 그릴 때 받아간다)
  2) 담당 기사님 기기로 Expo 푸시를 보낸다.

푸시 본문에 경로를 통째로 넣지 않는 이유는 Expo 페이로드가 4KB로 제한되기 때문이다.
알림에는 vehicle_id만 싣고, 앱이 그 id로 /api/dispatch/today 를 받아간다.
"""
from datetime import date, datetime

import httpx
from fastapi import HTTPException
from postgrest.exceptions import APIError

from .database import KST
from .drivers import deactivate_device, list_devices
from .models import DispatchNotifyResult, DriverNotifyOutcome, OptimizeResponse
from .supabase_client import get_supabase

TABLE = "dispatches"
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def save_dispatch(result: OptimizeResponse, service_date: date) -> None:
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    row = {
        "service_date": service_date.isoformat(),
        "payload": result.model_dump(mode="json"),
        "updated_at": now,
    }
    try:
        get_supabase().table(TABLE).upsert(row, on_conflict="service_date").execute()
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"배차 결과 저장에 실패했습니다: {error.message}"
        ) from error


def load_dispatch(service_date: date) -> OptimizeResponse | None:
    try:
        result = (
            get_supabase()
            .table(TABLE)
            .select("payload")
            .eq("service_date", service_date.isoformat())
            .limit(1)
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status_code=502, detail=f"배차 결과 조회에 실패했습니다: {error.message}"
        ) from error
    if not result.data:
        return None
    return OptimizeResponse.model_validate(result.data[0]["payload"])


def _summarize(vehicle) -> tuple[int, str]:
    """알림 본문에 쓸 '총 몇 명 / 몇 시 출발' 요약."""
    used = [trip for trip in vehicle.trips if trip.used]
    total = sum(trip.passenger_count for trip in used)
    first_departure = min(
        (trip.departure_time for trip in used if trip.departure_time), default=None
    )
    rounds = ", ".join(f"{trip.round}회차 {trip.passenger_count}명" for trip in used)
    detail = rounds or "배정된 운행 없음"
    if first_departure:
        detail = f"{first_departure} 출발 · {detail}"
    return total, detail


async def notify_drivers(result: OptimizeResponse, service_date: date) -> DispatchNotifyResult:
    messages = []
    outcomes: list[DriverNotifyOutcome] = []

    for vehicle in result.vehicles:
        label = f"{vehicle.vehicle_type} {vehicle.plate_number}"
        if not vehicle.driver_name:
            outcomes.append(DriverNotifyOutcome(
                vehicle_label=label, driver_name=None, sent=0,
                message="담당 기사 이름이 없어 발송하지 않았습니다.",
            ))
            continue

        devices = list_devices(vehicle.driver_name)
        if not devices:
            outcomes.append(DriverNotifyOutcome(
                vehicle_label=label, driver_name=vehicle.driver_name, sent=0,
                message="등록된 기기가 없습니다. 기사님 폰에서 알림 받기를 켜 주세요.",
            ))
            continue

        total, detail = _summarize(vehicle)
        for device in devices:
            messages.append({
                "to": device.expo_push_token,
                "title": f"🚐 오늘 배차 · {label}",
                "body": f"{vehicle.driver_name} 선생님, 총 {total}명 · {detail}",
                "sound": "default",
                "priority": "high",
                # 앱이 알림을 눌렀을 때 이 값으로 해당 차량 지도를 연다.
                "data": {
                    "screen": "route",
                    "vehicle_id": vehicle.vehicle_id,
                    "vehicle_label": label,
                    "service_date": service_date.isoformat(),
                },
            })
        outcomes.append(DriverNotifyOutcome(
            vehicle_label=label, driver_name=vehicle.driver_name,
            sent=len(devices), message=f"기기 {len(devices)}대로 발송했습니다.",
        ))

    if not messages:
        return DispatchNotifyResult(sent=0, outcomes=outcomes)

    tokens = [message["to"] for message in messages]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"accept": "application/json", "content-type": "application/json"},
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502, detail=f"Expo 푸시 서버에 연결하지 못했습니다: {error}"
        ) from error

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Expo 푸시 발송 실패 (HTTP {response.status_code}): {response.text[:200]}",
        )

    # Expo는 티켓 배열을 돌려준다. 실패한 것만 골라 정리한다.
    tickets = response.json().get("data", [])
    failed = 0
    for token, ticket in zip(tokens, tickets):
        if ticket.get("status") == "ok":
            continue
        failed += 1
        # 앱이 지워졌거나 토큰이 만료된 기기는 발송 대상에서 뺀다.
        if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
            try:
                deactivate_device(token)
            except HTTPException:
                pass

    return DispatchNotifyResult(sent=len(messages) - failed, failed=failed, outcomes=outcomes)
