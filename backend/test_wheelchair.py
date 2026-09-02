"""v3.1 검증: 휠체어 하드 제약.

핵심은 하나다. 휠체어 고정석이 0인 차량에는 휠체어 어르신이 절대 실리지 않는다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_wheelchair.py
"""
from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, VehicleInput
from app.optimizer import CONSTRAINT_VERSION, optimize_routes

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)


def build(people_spec, fleet_spec, trip_type="inbound", window=("08:00", "11:00")):
    """people_spec: [(id, 휠체어여부), ...]  fleet_spec: [(id, 정원, 휠체어석), ...]"""
    people = [
        {"id": pid, "name": f"어르신{pid}", "address": f"주소{pid}",
         "latitude": 37.500 + i * 0.004, "longitude": 127.000 + i * 0.004,
         "pickup_start": window[0], "pickup_end": window[1], "wheelchair": wc}
        for i, (pid, wc) in enumerate(people_spec, start=1)
    ]
    fleet = [
        {"id": vid, "vehicle_type": "스타리아", "plate_number": f"{i}{i}가{i}{i}{i}{i}",
         "driver_name": f"기사{i}", "capacity": cap, "wheelchair_capacity": wcap}
        for i, (vid, cap, wcap) in enumerate(fleet_spec, start=1)
    ]
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
    return optimize_routes(request, resolved, get_settings())


def seated(result):
    """차량 id -> 그 차에 실린 어르신 id 집합."""
    out = {}
    for vehicle in result.vehicles:
        ids = set()
        for trip in vehicle.trips:
            if trip.used:
                ids |= {stop.passenger_id for stop in trip.stops}
        out[vehicle.vehicle_id] = ids
    return out


# ---------------------------------------------------------------------------
print("=== 1. 리프트 없는 차량에는 휠체어 어르신이 실리지 않는다 (핵심) ===")
print("   9석 리프트 없음 1대 + 휠체어 어르신 2명 + 일반 3명.")
print("   정원은 충분하다. 오직 리프트가 없어서 빠져야 한다.")

r1 = build(
    [("w1", True), ("w2", True), ("n1", False), ("n2", False), ("n3", False)],
    [("veh-plain", 9, 0)],
)
placed = seated(r1)
check("리프트 없는 차에 휠체어 어르신이 하나도 없다",
      not ({"w1", "w2"} & placed["veh-plain"]), placed["veh-plain"])
check("일반 어르신 3명은 정상 배차됐다",
      {"n1", "n2", "n3"} <= placed["veh-plain"], placed["veh-plain"])

dropped = {item.passenger_id for item in r1.unassigned_passengers}
check("휠체어 두 분이 배차 불가로 잡힌다", dropped == {"w1", "w2"}, dropped)
check("사유가 wheelchair 로 갈린다",
      all(i.reason == "wheelchair" for i in r1.unassigned_passengers),
      [(i.passenger_id, i.reason) for i in r1.unassigned_passengers])
check("휠체어 표시가 붙는다",
      all(i.wheelchair for i in r1.unassigned_passengers))

lift_notice = [n for n in r1.notices if "휠체어" in n]
check("안내 문구가 리프트 문제라고 말한다", bool(lift_notice))
check("고정석이 없다고 알려 준다",
      any("차량이 없습니다" in n for n in lift_notice), lift_notice)
print("   문구:", lift_notice[0] if lift_notice else "(없음)")


print()
print("=== 2. 리프트 차량이 있으면 정상 배차된다 ===")
print("   같은 사람들, 휠체어석 2자리를 가진 차량 한 대로 바꾼다.")

r2 = build(
    [("w1", True), ("w2", True), ("n1", False), ("n2", False), ("n3", False)],
    [("veh-lift", 9, 2)],
)
check("아무도 빠지지 않는다", not r2.unassigned_passengers,
      [i.passenger_id for i in r2.unassigned_passengers])
check("휠체어 두 분이 리프트 차에 실린다",
      {"w1", "w2"} <= seated(r2)["veh-lift"])
check("다섯 분 전원 배차", len(seated(r2)["veh-lift"]) == 5)


print()
print("=== 3. 휠체어석 수를 넘겨 태우지 않는다 ===")
print("   휠체어석 1자리짜리 차 한 대에 휠체어 어르신 3명.")
print("   총 정원은 9석이라 자리는 남는다. 고정석만 모자란다.")

r3 = build(
    [("w1", True), ("w2", True), ("w3", True), ("n1", False)],
    [("veh-lift1", 9, 1)],
)
on_board = seated(r3)["veh-lift1"]
wheelchair_on_board = on_board & {"w1", "w2", "w3"}
check("한 회차에 휠체어는 고정석 수만큼만 탄다",
      all(
          sum(1 for stop in trip.stops if stop.wheelchair) <= 1
          for vehicle in r3.vehicles for trip in vehicle.trips if trip.used
      ),
      [[s.passenger_id for s in t.stops]
       for v in r3.vehicles for t in v.trips if t.used])
check("일반 어르신은 배차된다", "n1" in on_board)
print(f"   휠체어 {len(wheelchair_on_board)}명 탑승 / "
      f"{len(r3.unassigned_passengers)}명 미배차")


print()
print("=== 4. 회차를 나누면 고정석을 다시 쓸 수 있다 ===")
print("   휠체어석 1자리 차량이 2회차를 돌면 휠체어 2명을 나눠 태울 수 있어야 한다.")
r4 = build(
    [("w1", True), ("w2", True)],
    [("veh-lift1", 9, 1)],
    window=("08:00", "12:00"),
)
used_trips = [t for v in r4.vehicles for t in v.trips if t.used]
both_seated = len(r4.unassigned_passengers) == 0
check("휠체어 두 분 모두 배차됐다", both_seated,
      [i.passenger_id for i in r4.unassigned_passengers])
if both_seated:
    check("회차를 나눠서 태웠다", len(used_trips) == 2, f"{len(used_trips)}회차")
    for trip in used_trips:
        wc = sum(1 for stop in trip.stops if stop.wheelchair)
        check(f"  {trip.round}회차 휠체어 {wc}명 (고정석 1자리 이내)", wc <= 1)


print()
print("=== 5. 두 정원이 서로 독립이다 ===")
print("   일반 정원 2석 / 휠체어석 2자리 차량. 휠체어석이 총정원을 늘리지 않는다.")
r5 = build(
    [("w1", True), ("n1", False), ("n2", False), ("n3", False)],
    [("veh", 2, 2)],
)
for vehicle in r5.vehicles:
    for trip in vehicle.trips:
        if trip.used:
            check(f"{trip.round}회차 탑승 인원이 총정원 2명 이하",
                  len(trip.stops) <= 2, len(trip.stops))


print()
print("=== 6. 사유가 섞여도 갈라서 안내한다 ===")
print("   리프트 없는 1석 차량 1대 + 휠체어 1명 + 일반 5명. 창도 좁다.")
print("   휠체어는 리프트 때문에, 나머지는 정원 때문에 빠진다.")
r6 = build(
    [("w1", True), ("n1", False), ("n2", False),
     ("n3", False), ("n4", False), ("n5", False)],
    [("veh-plain", 1, 0)],
    window=("08:00", "08:30"),
)
reasons = {i.passenger_id: i.reason for i in r6.unassigned_passengers}
check("휠체어 어르신 사유는 wheelchair", reasons.get("w1") == "wheelchair", reasons)
plain_dropped = {k: v for k, v in reasons.items() if k != "w1"}
check("정원 때문에 빠진 분도 실제로 있다", bool(plain_dropped), reasons)
check("일반 어르신 사유는 capacity",
      plain_dropped and all(v == "capacity" for v in plain_dropped.values()), reasons)
check("안내 문구가 두 갈래로 나온다",
      sum(1 for n in r6.notices if "배차하지 못했습니다" in n) == 2,
      [n for n in r6.notices if "배차하지 못했습니다" in n])
for notice in r6.notices:
    if "배차하지 못했습니다" in notice:
        print("   ·", notice)


print()
print("=== 7. 하위 호환 ===")
print("   휠체어석을 안 보내던 구형 요청이 그대로 통해야 한다.")
legacy = VehicleInput.model_validate({
    "vehicle_type": "스타리아", "plate_number": "99가9999", "capacity": 9,
})
check("휠체어석 없이도 차량이 만들어진다", legacy.wheelchair_capacity == 0)

r7 = build(
    [("n1", False), ("n2", False), ("n3", False)],
    [("veh", 9, 0)],
)
check("휠체어 어르신이 없으면 아무 영향 없다", not r7.unassigned_passengers)
check("일반 배차는 그대로 된다", len(seated(r7)["veh"]) == 3)

check("제약 버전이 V3.1 로 올라갔다",
      CONSTRAINT_VERSION == "CARE_CONSTRAINT_V3.1", CONSTRAINT_VERSION)


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
