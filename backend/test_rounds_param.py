"""v3.2 회귀: 회차 파라미터화가 기존 동작을 건드리지 않는가.

대안 분석기를 만들려면 '3회차까지 돌면 되는가' 를 물어야 하고, 그러려면
2로 못 박혀 있던 회차 수를 풀어야 한다. 핵심 엔진을 건드리는 유일한 곳이라
여기서 두껍게 막는다.

지켜야 할 것은 하나다. 기본값(2)으로 부른 결과가 예전과 똑같아야 한다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_rounds_param.py
"""
import json

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest
from app.optimizer import DEFAULT_TRIPS_PER_VEHICLE, optimize_routes, trip_endpoints

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)
GARAGE = ResolvedLocation(name="차고지", address="차고지주소",
                          latitude=37.470, longitude=126.970)


def build(count, capacity=4, vehicles=1, trip_type="inbound",
          window=("08:00", "11:00"), self_drive=False, wheelchair_every=0,
          wheelchair_seats=0):
    people = []
    for i in range(1, count + 1):
        people.append({
            "id": f"p{i}", "name": f"어르신{i}", "address": f"주소{i}",
            "latitude": 37.500 + i * 0.004, "longitude": 127.000 + i * 0.004,
            "pickup_start": window[0], "pickup_end": window[1],
            "wheelchair": bool(wheelchair_every and i % wheelchair_every == 0),
        })
    fleet = []
    for v in range(vehicles):
        item = {"id": f"veh{v}", "vehicle_type": "스타리아",
                "plate_number": f"{v + 1}{v + 1}가{v + 1}{v + 1}{v + 1}{v + 1}",
                "driver_name": f"기사{v + 1}", "capacity": capacity,
                "wheelchair_capacity": wheelchair_seats}
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
    resolved = [CENTER] + [
        ResolvedLocation(name=p["name"], address=p["address"],
                         latitude=p["latitude"], longitude=p["longitude"])
        for p in people
    ]
    resolved += [GARAGE] * (vehicles if self_drive else 0)
    return request, resolved


def solve(request, resolved, trips=None):
    settings = get_settings()
    if trips is None:
        return optimize_routes(request, resolved, settings)
    return optimize_routes(request, resolved, settings, trips_per_vehicle=trips)


def shape(result):
    """비교할 알맹이만 남긴다. 연산 시간처럼 매번 달라지는 값은 뺀다."""
    data = result.model_dump(mode="json")
    data.pop("solve_seconds", None)
    data.pop("optimization_run_id", None)
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
print("=== 1. 기본값을 안 넘긴 것과 2를 넘긴 것이 완전히 같다 (핵심) ===")
print("   같은 판을 두 방식으로 풀어 결과 전체를 통째로 비교한다.")

CASES = [
    ("등원 1대 6명", dict(count=6, capacity=4)),
    ("등원 2대 10명", dict(count=10, capacity=4, vehicles=2)),
    ("하원 1대 6명", dict(count=6, capacity=4, trip_type="outbound")),
    ("자차 하원 5명", dict(count=5, capacity=9, trip_type="outbound", self_drive=True)),
    ("자차 하원 10명 2회차", dict(count=10, capacity=6, trip_type="outbound",
                                 self_drive=True)),
    ("자차 등원 6명", dict(count=6, capacity=4, self_drive=True)),
    ("휠체어 섞임", dict(count=8, capacity=9, wheelchair_every=3, wheelchair_seats=1)),
    ("배차 불가 발생", dict(count=9, capacity=2, window=("08:00", "08:40"))),
]

for label, kwargs in CASES:
    request, resolved = build(**kwargs)
    default_run = shape(solve(request, resolved))
    explicit_run = shape(solve(request, resolved, trips=2))
    check(f"{label}: 결과가 완전히 동일", default_run == explicit_run,
          "다름" if default_run != explicit_run else "")


print()
print("=== 2. 회차 수를 늘려도 2회차 판의 정답이 나빠지지 않는다 ===")
print("   3회차를 허용해도 2회차로 충분하면 2회차만 써야 한다.")

request, resolved = build(count=6, capacity=4)
two = solve(request, resolved, trips=2)
three = solve(request, resolved, trips=3)
check("3회차 허용해도 전원 배차", not three.unassigned_passengers)
check("거리가 나빠지지 않는다",
      three.total_distance_km <= two.total_distance_km + 0.1,
      f"2회차 {two.total_distance_km}km vs 3회차 {three.total_distance_km}km")
used_rounds = {t.round for v in three.vehicles for t in v.trips if t.used}
check("필요 없으면 3회차를 쓰지 않는다", 3 not in used_rounds, used_rounds)


print()
print("=== 3. 2회차로 안 되던 판이 3회차로 풀린다 (분석기의 근거) ===")
print("   정원 2명짜리 한 대에 6명. 2회차면 4명이 한계다.")

request, resolved = build(count=6, capacity=2, window=("08:00", "12:00"))
two = solve(request, resolved, trips=2)
three = solve(request, resolved, trips=3)
check("2회차로는 못 태우는 분이 있다", len(two.unassigned_passengers) > 0,
      f"{len(two.unassigned_passengers)}명 미배차")
check("3회차로는 더 많이 태운다",
      len(three.unassigned_passengers) < len(two.unassigned_passengers),
      f"{len(two.unassigned_passengers)}명 -> {len(three.unassigned_passengers)}명")
three_rounds = {t.round for v in three.vehicles for t in v.trips if t.used}
check("실제로 3회차를 쓴다", 3 in three_rounds, three_rounds)


print()
print("=== 4. 회차가 시간 순으로 이어진다 ===")
print("   차 한 대는 동시에 두 곳에 있을 수 없다. 앞 회차가 돌아와야 다음이 뜬다.")

request, resolved = build(count=6, capacity=2, window=("08:00", "12:00"))
result = solve(request, resolved, trips=3)
turnaround = get_settings().turnaround_minutes
for vehicle in result.vehicles:
    used = [t for t in vehicle.trips if t.used]
    for earlier, later in zip(used, used[1:]):
        gap_ok = later.departure_time >= earlier.return_time
        check(f"{earlier.round}회차 복귀 {earlier.return_time} <= "
              f"{later.round}회차 출발 {later.departure_time}", gap_ok)
    rounds = [t.round for t in used]
    check("앞 회차를 건너뛰지 않는다", rounds == sorted(rounds) and
          (not rounds or rounds[0] == 1), rounds)


print()
print("=== 5. 자차 하원은 '마지막으로 실제 운행한 회차' 가 퇴근길이다 ===")
print("   3회차판에서 2회차까지만 돌았다면 2회차가 차고지에서 끝나야 한다.")

request, resolved = build(count=5, capacity=3, trip_type="outbound",
                          self_drive=True, window=("13:00", "18:00"))
result = solve(request, resolved, trips=3)
for vehicle in result.vehicles:
    used = [t for t in vehicle.trips if t.used]
    if not used:
        continue
    last = used[-1]
    check(f"마지막({last.round}회차)이 차고지에서 끝난다",
          last.destination_name == "차고지", last.destination_name)
    for trip in used[:-1]:
        check(f"{trip.round}회차는 센터로 복귀한다",
              trip.destination_name != "차고지", trip.destination_name)
    unused = [t for t in vehicle.trips if not t.used]
    check("안 쓴 회차가 차고지로 남지 않는다",
          all(t.destination_name != "차고지" for t in unused),
          [t.destination_name for t in unused])


print()
print("=== 6. 목적함수가 추가 회차를 제대로 센다 ===")
request, resolved = build(count=6, capacity=2, window=("08:00", "12:00"))
result = solve(request, resolved, trips=3)
used = [t for v in result.vehicles for t in v.trips if t.used]
expected = sum(t.round - 1 for t in used if t.round > 1)
check("추가 회차 수 = Σ(회차번호 - 1)",
      result.objective_breakdown.second_run_count == expected,
      f"{result.objective_breakdown.second_run_count} vs {expected}")

# 2회차만 쓰는 판에서는 예전 정의(2회차 개수)와 값이 같아야 한다.
request, resolved = build(count=6, capacity=4)
two = solve(request, resolved)
old_style = sum(1 for v in two.vehicles for t in v.trips if t.used and t.round == 2)
check("2회차 판에서는 예전 정의와 같은 값",
      two.objective_breakdown.second_run_count == old_style,
      f"{two.objective_breakdown.second_run_count} vs {old_style}")


print()
print("=== 7. 안내 문구가 실제 회차 수를 말한다 ===")
request, resolved = build(count=4, capacity=9)
check("기본은 최대 2회",
      any("최대 2회" in n for n in solve(request, resolved).notices))
check("3회차판은 최대 3회",
      any("최대 3회" in n for n in solve(request, resolved, trips=3).notices))


print()
print("=== 8. 회차 1개짜리도 성립한다 ===")
print("   분석기가 쓰지는 않지만, 사슬 로직이 이웃 없이도 도는지 본다.")
request, resolved = build(count=3, capacity=9)
one = solve(request, resolved, trips=1)
check("1회차판이 예외 없이 풀린다", one.status == "optimal_or_feasible")
check("회차가 하나뿐이다",
      all(len(v.trips) == 1 for v in one.vehicles),
      [len(v.trips) for v in one.vehicles])
check("전원 배차", not one.unassigned_passengers)


print()
print("=== 9. 기본 상수가 2 그대로다 ===")
check("DEFAULT_TRIPS_PER_VEHICLE == 2", DEFAULT_TRIPS_PER_VEHICLE == 2,
      DEFAULT_TRIPS_PER_VEHICLE)
check("trip_endpoints 기본 인자도 2회차 규칙",
      trip_endpoints(5, 2, "outbound") == (0, 5),
      trip_endpoints(5, 2, "outbound"))


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
