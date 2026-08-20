"""배차 전송(푸시) 로직 검증.

Expo 푸시 서버와 Supabase는 가짜로 갈아끼운다. 실제 알림을 쏘지 않고도
- 어떤 기사에게 몇 건을 보내는지
- 알림 data 에 딥링크용 vehicle_id 가 들어가는지
- DeviceNotRegistered 기기를 자동 해제하는지
를 확인한다.

실행: .venv\\Scripts\\python.exe -X utf8 test_dispatch_push.py
"""
import asyncio
import sys
from datetime import date

import app.dispatch as dispatch
from app.models import DriverDeviceRecord, OptimizeResponse

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


def device(name, token):
    return DriverDeviceRecord(
        id=1, driver_name=name, expo_push_token=token, device_label="테스트폰",
        is_active=True, created_at="2026-08-19T12:00:00+09:00",
        updated_at="2026-08-19T12:00:00+09:00",
    )


def stop(seq, pid, name):
    return {
        "sequence": seq, "passenger_id": pid, "name": name, "address": "주소",
        "detail_address": None, "latitude": 35.34, "longitude": 129.04,
        "wheelchair": False, "requested_window": "08:00~09:00",
        "estimated_pickup": f"08:{10 + seq * 5}", "kakao_navi_url": "kakaonavi://x",
    }


RESULT = OptimizeResponse.model_validate({
    "status": "optimal_or_feasible",
    "center": {"name": "센터", "address": "양산시청", "latitude": 35.335, "longitude": 129.037},
    "total_passengers": 3, "total_distance_km": 12.0, "solve_seconds": 1.0,
    "vehicles": [
        {"vehicle_id": "v1", "vehicle_type": "스타리아", "plate_number": "12가3456",
         "driver_name": "명민승", "capacity": 3, "trips": [
             {"round": 1, "used": True, "passenger_count": 2, "capacity": 3,
              "departure_time": "08:05", "return_time": "08:40", "distance_km": 7.0,
              "stops": [stop(1, "P001", "김어르신"), stop(2, "P002", "이어르신")]},
             {"round": 2, "used": True, "passenger_count": 1, "capacity": 3,
              "departure_time": "09:00", "return_time": "09:20", "distance_km": 5.0,
              "stops": [stop(1, "P003", "박어르신")]}]},
        # 담당 기사 이름이 없는 차량
        {"vehicle_id": "v2", "vehicle_type": "카니발", "plate_number": "34나7890",
         "driver_name": None, "capacity": 2, "trips": [
             {"round": 1, "used": True, "passenger_count": 1, "capacity": 2,
              "departure_time": "08:10", "return_time": "08:30", "distance_km": 4.0,
              "stops": [stop(1, "P004", "최어르신")]},
             {"round": 2, "used": False, "passenger_count": 0, "capacity": 2,
              "departure_time": None, "return_time": None, "distance_km": 0, "stops": []}]},
        # 기사 이름은 있으나 등록된 기기가 없는 차량
        {"vehicle_id": "v3", "vehicle_type": "레이", "plate_number": "56다1234",
         "driver_name": "박기사", "capacity": 1, "trips": [
             {"round": 1, "used": False, "passenger_count": 0, "capacity": 1,
              "departure_time": None, "return_time": None, "distance_km": 0, "stops": []},
             {"round": 2, "used": False, "passenger_count": 0, "capacity": 1,
              "departure_time": None, "return_time": None, "distance_km": 0, "stops": []}]},
    ],
    "notices": [],
})

# --- 가짜 의존성 ------------------------------------------------------------
DEVICES = {"명민승": [device("명민승", "ExponentPushToken[AAA]"),
                     device("명민승", "ExponentPushToken[BBB]")]}
deactivated = []
sent_payloads = {}


class FakeResponse:
    status_code = 200

    def json(self):
        # 두 번째 토큰은 기기 미등록으로 실패시킨다.
        return {"data": [
            {"status": "ok"},
            {"status": "error", "details": {"error": "DeviceNotRegistered"}},
        ]}


class FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        sent_payloads["url"] = url
        sent_payloads["messages"] = json
        return FakeResponse()


dispatch.list_devices = lambda name: DEVICES.get(name, [])
dispatch.deactivate_device = lambda token: deactivated.append(token)
dispatch.httpx.AsyncClient = FakeClient

print("--- 배차 전송 ---")
outcome = asyncio.run(dispatch.notify_drivers(RESULT, date(2026, 8, 19)))

check("Expo 푸시 엔드포인트 호출", sent_payloads.get("url") == dispatch.EXPO_PUSH_URL,
      sent_payloads.get("url"))
messages = sent_payloads.get("messages", [])
check("등록 기기 2대에만 발송 (기사없음·기기없음 차량은 제외)", len(messages) == 2, len(messages))

first = messages[0] if messages else {}
check("알림 제목에 차량 표기", "스타리아 12가3456" in first.get("title", ""), first.get("title"))
check("본문에 기사님·인원·출발시각",
      all(k in first.get("body", "") for k in ["명민승", "3명", "08:05"]), first.get("body"))
check("딥링크용 vehicle_id 포함", first.get("data", {}).get("vehicle_id") == "v1",
      first.get("data"))
check("딥링크용 screen=route", first.get("data", {}).get("screen") == "route")

print("--- 발송 결과 집계 ---")
check("성공 1건 / 실패 1건", outcome.sent == 1 and outcome.failed == 1,
      f"sent={outcome.sent} failed={outcome.failed}")
check("DeviceNotRegistered 기기 자동 해제", deactivated == ["ExponentPushToken[BBB]"],
      deactivated)

by_label = {o.vehicle_label: o for o in outcome.outcomes}
check("차량 3대 모두 결과 보고", len(outcome.outcomes) == 3, len(outcome.outcomes))
check("기사 이름 없는 차량 안내",
      "담당 기사 이름이 없어" in by_label["카니발 34나7890"].message,
      by_label["카니발 34나7890"].message)
check("등록 기기 없는 기사 안내",
      "등록된 기기가 없습니다" in by_label["레이 56다1234"].message,
      by_label["레이 56다1234"].message)

print("--- 발송 대상이 아예 없을 때 ---")
dispatch.list_devices = lambda name: []
empty = asyncio.run(dispatch.notify_drivers(RESULT, date(2026, 8, 19)))
check("Expo 호출 없이 0건 반환", empty.sent == 0 and len(empty.outcomes) == 3,
      f"sent={empty.sent}")

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과")
