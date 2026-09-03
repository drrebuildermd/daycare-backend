"""v3.1.1 검증: 등원/하원 명단이 어긋나 사람이 사라지는 문제.

현장에서 '하원 대상 34명인데 20명만 배차되고 14명이 증발' 이 났다.
원인은 두 갈래였고 둘 다 여기서 막는다.

  1) 프론트가 하원을 계산하면서 등원 스위치로 명단을 걸렀다 (App.js, 별도 수정)
  2) 동승 규칙이 이번에 안 타시는 분을 가리키면 서버가 KeyError 로 터졌다

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_trip_roster.py
"""
import asyncio

from app.config import get_settings
from app.models import OptimizeRequest
from app.main import run_optimization

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


def person(pid, inbound=True, outbound=True, i=1):
    return {
        "id": pid, "name": f"어르신{pid}", "address": f"주소{pid}",
        "latitude": 37.500 + i * 0.004, "longitude": 127.000 + i * 0.004,
        "pickup_start": "08:00", "pickup_end": "11:00",
        "attending": inbound, "attending_outbound": outbound,
    }


def run(people, trip_type, required=None, forbidden=None):
    payload = {
        "trip_type": trip_type,
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [{"id": "v1", "vehicle_type": "스타리아",
                      "plate_number": "11가1111", "capacity": 9}],
        "passengers": people,
    }
    if required:
        payload["required_pairs"] = [{"passenger_ids": list(p)} for p in required]
    if forbidden:
        payload["forbidden_pairs"] = [{"passenger_ids": list(p)} for p in forbidden]
    request = OptimizeRequest.model_validate(payload)
    return asyncio.run(run_optimization(request, get_settings()))


# ---------------------------------------------------------------------------
print("=== 1. 아무도 사라지지 않는다 ===")
print("   대상 = 배차 완료 + 배차 불가. 이 등식이 깨지면 누군가 증발한 것이다.")

# 등원만 2명 / 하원만 3명 / 양쪽 2명
roster = [
    person("both1", True, True, 1),
    person("both2", True, True, 2),
    person("in1", True, False, 3),
    person("in2", True, False, 4),
    person("out1", False, True, 5),
    person("out2", False, True, 6),
    person("out3", False, True, 7),
]

for trip_type, expected, label in (("inbound", 4, "등원"), ("outbound", 5, "하원")):
    result = run(roster, trip_type)
    assigned = {
        stop.passenger_id
        for vehicle in result.vehicles for trip in vehicle.trips if trip.used
        for stop in trip.stops
    }
    unassigned = {item.passenger_id for item in result.unassigned_passengers}

    check(f"{label} 대상 인원이 {expected}명으로 잡힌다",
          result.total_passengers == expected, result.total_passengers)
    check(f"{label} 배차 + 불가 = 대상",
          len(assigned) + len(unassigned) == result.total_passengers,
          f"{len(assigned)} + {len(unassigned)} vs {result.total_passengers}")
    check(f"{label} 반대편 전용 어르신은 명단에 없다",
          not (assigned & ({"out1", "out2", "out3"} if trip_type == "inbound"
                           else {"in1", "in2"})),
          assigned)


print()
print("=== 2. 하원 전용 어르신이 하원 배차에 실제로 실린다 ===")
print("   이분들이 증발했던 것이다.")
result = run(roster, "outbound")
assigned = {
    stop.passenger_id
    for vehicle in result.vehicles for trip in vehicle.trips if trip.used
    for stop in trip.stops
}
check("out1/out2/out3 이 모두 배차됐다",
      {"out1", "out2", "out3"} <= assigned, assigned)
check("both1/both2 도 함께 배차됐다", {"both1", "both2"} <= assigned, assigned)


print()
print("=== 3. 한쪽만 타는 분을 가리키는 동승 규칙이 서버를 죽이지 않는다 ===")
print("   예전에는 KeyError 로 500 이 났다.")

try:
    result = run(roster, "outbound", required=[("both1", "in1")])
    check("500 이 나지 않는다", True)
    check("규칙을 뺐다고 알려 준다",
          any("동승 규칙" in n for n in result.notices),
          [n for n in result.notices if "동승" in n])
    check("나머지 배차는 정상", result.total_passengers == 5, result.total_passengers)
except Exception as error:  # noqa: BLE001
    check("500 이 나지 않는다", False, f"{type(error).__name__}: {error}")

try:
    result = run(roster, "inbound", forbidden=[("both1", "out1")])
    check("같이 타면 안 되는 규칙도 마찬가지", True)
    check("안내가 나온다", any("동승 규칙" in n for n in result.notices))
except Exception as error:  # noqa: BLE001
    check("같이 타면 안 되는 규칙도 마찬가지", False, f"{type(error).__name__}: {error}")


print()
print("=== 4. 양쪽 모두 타는 분끼리의 규칙은 그대로 지켜진다 ===")
result = run(roster, "outbound", required=[("both1", "both2")])
for vehicle in result.vehicles:
    for trip in vehicle.trips:
        if not trip.used:
            continue
        ids = {stop.passenger_id for stop in trip.stops}
        if "both1" in ids or "both2" in ids:
            check("both1 과 both2 가 같은 회차에 함께 탄다",
                  {"both1", "both2"} <= ids, ids)
            break
check("멀쩡한 규칙은 빼지 않는다",
      not any("동승 규칙" in n for n in result.notices),
      [n for n in result.notices if "동승" in n])


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
