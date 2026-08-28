"""v1.4.0 문자 발송 규칙 검증.

솔라피를 실제로 부르지 않는다. 부르는 시늉만 하고 무엇이 나갔는지 들여다본다.
실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_sms_rules.py
"""
import sys
from datetime import date

import app.main as main
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest
from app.optimizer import optimize_routes
from app.config import get_settings

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


# ── 솔라피 대역 ──
sent_box = []


def fake_solapi(target_number, text):
    sent_box.append((target_number, text))
    return (True, "발송 접수됨 (대역)")


main._solapi_send = fake_solapi


print("=== 1. 탑승 완료 문자: 수신 거부하면 보내지 않는다 ===")

sent_box.clear()
ok, message = main.send_test_sms("김어르신", "01012345678", "행복센터", sms_opt_in=True)
check("수신 동의 시 발송됨", ok and len(sent_box) == 1, message)
check("문구에 어르신 성함이 들어감", "김어르신" in sent_box[0][1], sent_box[0][1])

sent_box.clear()
ok, message = main.send_test_sms("박어르신", "01012345678", "행복센터", sms_opt_in=False)
check("수신 거부 시 발송 안 함", (not ok) and len(sent_box) == 0, message)
check("이유를 알려줌", "꺼두어" in message, message)

sent_box.clear()
ok, message = main.send_test_sms("최어르신", "", "행복센터", sms_opt_in=True)
check("번호가 없으면 발송 안 함", (not ok) and len(sent_box) == 0, message)
check("보호자 연락처 없음이라고 알려줌", "보호자 연락처" in message, message)


print()
print("=== 2. 배차 확정 문자: 기사님께 간다 ===")

CENTER = ResolvedLocation(name="행복센터", address="센터주소", latitude=37.50, longitude=127.00)
P1 = ResolvedLocation(name="김어르신", address="주소1", latitude=37.51, longitude=127.01)
P2 = ResolvedLocation(name="박어르신", address="주소2", latitude=37.52, longitude=127.02)


def build(driver_phone_a="01011112222", driver_phone_b="01033334444"):
    request = OptimizeRequest.model_validate({
        "center": {"name": "행복센터", "address": "센터주소", "latitude": 37.50, "longitude": 127.00},
        "vehicles": [
            {"id": "veh-a", "vehicle_type": "스타리아", "plate_number": "11가1111",
             "driver_name": "김기사", "driver_phone": driver_phone_a, "capacity": 7},
            {"id": "veh-b", "vehicle_type": "레이", "plate_number": "22나2222",
             "driver_name": "박기사", "driver_phone": driver_phone_b, "capacity": 7},
        ],
        "passengers": [
            {"id": "p1", "name": "김어르신", "address": "주소1", "latitude": 37.51, "longitude": 127.01,
             "pickup_start": "08:00", "pickup_end": "09:30"},
            {"id": "p2", "name": "박어르신", "address": "주소2", "latitude": 37.52, "longitude": 127.02,
             "pickup_start": "08:00", "pickup_end": "09:30"},
        ],
    })
    return optimize_routes(request, [CENTER, P1, P2], get_settings())


# 중복 방지 대역: 메모리에 기록한다.
memory = {}


def fake_was_sent(service_date, vehicle_id, signature):
    return memory.get((service_date, vehicle_id)) == signature


def fake_mark_sent(service_date, vehicle_id, signature):
    memory[(service_date, vehicle_id)] = signature


main.was_dispatch_sms_sent = fake_was_sent
main.mark_dispatch_sms_sent = fake_mark_sent

response = build()
sent_box.clear()
memory.clear()
notices = main._notify_drivers_by_sms(response)
assigned = [v for v in response.vehicles if any(t.used for t in v.trips)]
check("배정된 기사님께 문자 발송", len(sent_box) == len(assigned), f"{len(sent_box)}통 / 배정 {len(assigned)}대")
if sent_box:
    check("문구에 확인 요청이 들어감", "앱에서 확인" in sent_box[0][1], sent_box[0][1])
    check("문구에 센터명이 들어감", "행복센터" in sent_box[0][1], sent_box[0][1])
check("보낸 건수를 안내문으로 알림", any("기사님" in n and "보냈습니다" in n for n in notices), notices)


print()
print("=== 3. 같은 배차를 다시 계산하면 문자를 또 보내지 않는다 ===")

sent_box.clear()
again = build()
notices = main._notify_drivers_by_sms(again)
check("두 번째 계산에서는 발송 없음", len(sent_box) == 0, f"{len(sent_box)}통")


print()
print("=== 4. 동선이 바뀌면 다시 보낸다 ===")

sent_box.clear()
changed = build()
# 한 대의 동선을 손으로 바꿔 지문을 다르게 만든다.
for vehicle in changed.vehicles:
    for trip in vehicle.trips:
        if trip.used and trip.stops:
            trip.stops[0].estimated_pickup = "09:15"
            break
    else:
        continue
    break
main._notify_drivers_by_sms(changed)
check("동선이 바뀐 기사님께는 다시 발송", len(sent_box) == 1, f"{len(sent_box)}통")


print()
print("=== 5. 기사님 번호가 없으면 알려준다 ===")

sent_box.clear()
memory.clear()
no_phone = build(driver_phone_a="", driver_phone_b="")
notices = main._notify_drivers_by_sms(no_phone)
check("번호 없으면 발송 안 함", len(sent_box) == 0, f"{len(sent_box)}통")
check("연락처 없다고 안내문에 남김", any("연락처가 없어" in n for n in notices), notices)


print()
print("=== 6. 배정 안 된 차량에는 보내지 않는다 ===")

sent_box.clear()
memory.clear()
idle = build()
empty = [v for v in idle.vehicles if not any(t.used for t in v.trips)]
main._notify_drivers_by_sms(idle)
check(
    "빈 차량 수만큼 발송이 줄어듦",
    len(sent_box) == len(idle.vehicles) - len(empty),
    f"차량 {len(idle.vehicles)}대 중 빈 차 {len(empty)}대, 발송 {len(sent_box)}통",
)


print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 문자 발송 규칙이 의도대로 동작합니다.")
