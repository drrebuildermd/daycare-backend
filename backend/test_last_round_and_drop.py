"""v2.1 검증: 자차 마지막 회차 퇴근 / 배차 불가 어르신 분리.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_last_round_and_drop.py
"""
import sys

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest
from app.optimizer import optimize_routes

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)
GARAGE = ResolvedLocation(name="차고지", address="차고지주소",
                          latitude=37.470, longitude=126.970)


def build(count, capacity=9, self_drive=True, trip_type="outbound",
          window=("08:00", "10:00"), vehicles=1):
    people = [
        {"id": f"p{i}", "name": f"어르신{i}", "address": f"어르신주소{i}",
         "latitude": 37.500 + i * 0.004, "longitude": 127.000 + i * 0.004,
         "pickup_start": window[0], "pickup_end": window[1]}
        for i in range(1, count + 1)
    ]
    fleet = []
    for v in range(vehicles):
        item = {"id": f"veh{v}", "vehicle_type": "스타리아",
                "plate_number": f"{v + 1}{v + 1}가{v + 1}{v + 1}{v + 1}{v + 1}",
                "driver_name": f"기사{v + 1}", "capacity": capacity}
        if self_drive:
            item.update({"start_type": "custom", "start_address": "차고지주소",
                         "start_latitude": 37.470, "start_longitude": 126.970})
        fleet.append(item)
    request = OptimizeRequest.model_validate({
        "trip_type": trip_type,
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": fleet, "passengers": people,
    })
    resolved = [CENTER]
    resolved += [ResolvedLocation(name=p["name"], address=p["address"],
                                  latitude=p["latitude"], longitude=p["longitude"])
                 for p in people]
    resolved += [GARAGE] * (vehicles if self_drive else 0)
    return optimize_routes(request, resolved, get_settings())


print("=== 1. 자차 하원: 한 회차만 돌면 그 회차가 차고지에서 끝난다 ===")
print("   (정원 9석에 3명. 두 회차를 돌 이유가 없다)")

result = build(count=3, capacity=9)
trips = {t.round: t for t in result.vehicles[0].trips}
used_rounds = [r for r, t in trips.items() if t.used]
check("한 회차만 씀", used_rounds == [1], used_rounds)
check("그 회차가 차고지에서 끝남", trips[1].destination_name == "차고지",
      f"{trips[1].origin_name} → {trips[1].destination_name}")
check("센터에서 출발함", trips[1].origin_name == "행복센터", trips[1].origin_name)
check("쓰지 않은 2회차는 빈 자리", not trips[2].used and not trips[2].stops)

print()
print("=== 2. 자차 하원: 두 회차를 돌면 2회차가 차고지에서 끝난다 ===")
print("   (정원 3석에 6명. 두 회차가 필요하다)")

result = build(count=6, capacity=3)
trips = {t.round: t for t in result.vehicles[0].trips}
check("두 회차 모두 씀", trips[1].used and trips[2].used,
      [r for r, t in trips.items() if t.used])
check("1회차는 센터 → 센터",
      trips[1].origin_name == "행복센터" and trips[1].destination_name == "행복센터",
      f"{trips[1].origin_name} → {trips[1].destination_name}")
check("2회차는 센터 → 차고지",
      trips[2].origin_name == "행복센터" and trips[2].destination_name == "차고지",
      f"{trips[2].origin_name} → {trips[2].destination_name}")
check("1회차 복귀 후 2회차 출발", trips[1].return_time <= trips[2].departure_time,
      f"{trips[1].return_time} -> {trips[2].departure_time}")

print()
print("=== 3. 등원은 예전 그대로 (자택 출발 → 센터 도착) ===")

result = build(count=3, capacity=9, trip_type="inbound")
trips = {t.round: t for t in result.vehicles[0].trips}
check("1회차는 차고지 → 센터",
      trips[1].origin_name == "차고지" and trips[1].destination_name == "행복센터",
      f"{trips[1].origin_name} → {trips[1].destination_name}")

print()
print("=== 4. 센터 차량은 하원에서도 늘 센터로 복귀 ===")

result = build(count=3, capacity=9, self_drive=False)
for trip in result.vehicles[0].trips:
    check(f"{trip.round}회차 센터 → 센터",
          trip.origin_name == "행복센터" and trip.destination_name == "행복센터",
          f"{trip.origin_name} → {trip.destination_name}")

print()
print("=== 5. 태울 방법이 없으면 전체를 실패로 돌리지 않고 그분만 뺀다 ===")
print("   (정원 2석 차량 1대 · 2회 운행 = 4명인데 10명)")

result = build(count=10, capacity=2, self_drive=False)
placed = [s.passenger_id for v in result.vehicles for t in v.trips for s in t.stops]
check("일부는 배차됨", len(placed) > 0, f"{len(placed)}명")
check("나머지는 제외 목록에", len(result.unassigned_passengers) == 10 - len(placed),
      f"배차 {len(placed)}명 / 제외 {len(result.unassigned_passengers)}명")
check("배차와 제외가 겹치지 않음",
      not (set(placed) & {u.passenger_id for u in result.unassigned_passengers}))
check("제외 목록에 이름이 담김",
      all(u.name and u.requested_window for u in result.unassigned_passengers),
      [u.name for u in result.unassigned_passengers][:3])
check("안내문에 무엇을 고쳐야 하는지 적힘",
      any("배차하지 못했습니다" in n and "다시 계산" in n for n in result.notices),
      [n for n in result.notices if "배차하지" in n])
check("정원을 넘긴 회차 없음",
      all(len(t.stops) <= v.capacity for v in result.vehicles for t in v.trips))

print()
print("=== 6. 태울 수 있으면 아무도 빠지지 않는다 ===")

result = build(count=6, capacity=9, self_drive=False)
check("제외 목록이 비어 있음", not result.unassigned_passengers,
      [u.name for u in result.unassigned_passengers])
check("안내문에 실패 문구 없음",
      not any("배차하지 못했습니다" in n for n in result.notices))

print()
print("=== 7. 하원 안내문이 '센터 복귀' 라고 거짓말하지 않는다 ===")

result = build(count=3, capacity=9)
notice = next((n for n in result.notices if "자차 송영 차량" in n), "")
check("하원 안내문은 차고지 퇴근이라고 적음", "차고지" in notice and "퇴근" in notice, notice)

result = build(count=3, capacity=9, trip_type="inbound")
notice = next((n for n in result.notices if "자차 송영 차량" in n), "")
check("등원 안내문은 센터 복귀라고 적음", "센터로 복귀" in notice, notice)

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 마지막 회차 퇴근과 배차 제외가 의도대로 동작합니다.")
