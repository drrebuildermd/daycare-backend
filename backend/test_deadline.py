"""v4.0 검증: 하원 마감 시각.

이 제약이 없으면 솔버가 3회차를 저녁까지 늘어뜨린다. 그러면 조기 하원이
일어나지 않고 '3회차의 비용' 이라는 것 자체가 생기지 않는다.
현장에서 3회차가 비싼 이유는 이 마감을 맞추려 앞당기기 때문이다.

센터 차량과 자차는 기준이 다르다.
  센터 차량 — 마지막 어르신을 내려드리고 센터로 돌아오는 시각
  자차     — 마지막 어르신을 내려드리는 시각 (차고지 퇴근은 안 센다)

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_deadline.py
"""
from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, VehicleInput, parse_hhmm
from app.optimizer import deadline_of, optimize_routes

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)
GARAGE = ResolvedLocation(name="차고지", address="차고지주소",
                          latitude=37.470, longitude=126.970)


def build(count, capacity=2, self_drive=False, deadline=None,
          window=("13:00", "17:00"), trips=2):
    people = [
        {"id": f"p{i}", "name": f"어르신{i}", "address": f"주소{i}",
         "latitude": 37.500 + i * 0.008, "longitude": 127.000 + i * 0.008,
         "pickup_start": "08:00", "pickup_end": "10:00",
         "dropoff_start": window[0], "dropoff_end": window[1]}
        for i in range(1, count + 1)
    ]
    vehicle = {"id": "v1", "vehicle_type": "스타리아", "plate_number": "11가1111",
               "driver_name": "기사1", "capacity": capacity}
    if deadline is not None:
        vehicle["outbound_deadline"] = deadline
    if self_drive:
        vehicle.update({"start_type": "custom", "start_address": "차고지주소",
                        "start_latitude": 37.470, "start_longitude": 126.970})
    request = OptimizeRequest.model_validate({
        "trip_type": "outbound",
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [vehicle], "passengers": people,
    })
    resolved = [CENTER] + [
        ResolvedLocation(name=p["name"], address=p["address"],
                         latitude=p["latitude"], longitude=p["longitude"])
        for p in people
    ]
    if self_drive:
        resolved.append(GARAGE)
    return optimize_routes(request, resolved, get_settings(), trips_per_vehicle=trips)


def used(result):
    return [t for v in result.vehicles for t in v.trips if t.used]


# ---------------------------------------------------------------------------
print("=== 1. 센터 차량은 '센터 복귀' 가 마감 안이어야 한다 ===")
result = build(6, capacity=2, deadline="17:00", trips=3)
limit = parse_hhmm("17:00")
for trip in used(result):
    check(f"{trip.round}회차 복귀 {trip.return_time} <= 17:00",
          parse_hhmm(trip.return_time) <= limit, trip.return_time)
check("실제로 여러 회차를 돌았다", len(used(result)) >= 2, len(used(result)))


print()
print("=== 2. 마감이 이르면 1회차가 앞으로 밀린다 (수가 삭감의 원인) ===")
print("   같은 판을 마감만 바꿔 풀어 본다.")
# 창을 마감 뒤까지 열어 둔다. 그래야 마감이 실제로 당기는 힘이 된다.
# 창이 이미 마감 안에 다 들어가 있으면 마감을 바꿔도 아무 일이 없다.
late = build(6, capacity=2, deadline="19:00", window=("16:00", "19:00"), trips=3)
early = build(6, capacity=2, deadline="17:00", window=("16:00", "19:00"), trips=3)
late_first = min(parse_hhmm(t.departure_time) for t in used(late))
early_first = min(parse_hhmm(t.departure_time) for t in used(early))
check("마감이 이르면 첫 출발도 이르다", early_first < late_first,
      f"19시 마감 {used(late)[0].departure_time} vs 17시 마감 {used(early)[0].departure_time}")
print(f"   19:00 마감 → 첫 출발 {min(t.departure_time for t in used(late))}")
print(f"   17:00 마감 → 첫 출발 {min(t.departure_time for t in used(early))}")


print()
print("=== 3. 자차는 '마지막 하차' 가 기준이다 (차고지 퇴근은 안 센다) ===")
print("   차고지 도착이 마감을 넘어도 된다. 그때는 이미 퇴근길이다.")
result = build(5, capacity=2, self_drive=True, deadline="17:00", trips=3)
limit = parse_hhmm("17:00")
for vehicle in result.vehicles:
    for trip in vehicle.trips:
        if not trip.used:
            continue
        stop_times = [parse_hhmm(s.estimated_pickup) for s in trip.stops
                      if s.estimated_pickup]
        if stop_times:
            check(f"{trip.round}회차 마지막 하차 "
                  f"{max(s.estimated_pickup for s in trip.stops)} <= 17:00",
                  max(stop_times) <= limit,
                  max(s.estimated_pickup for s in trip.stops))
garage_trips = [t for t in used(result) if t.destination_name == "차고지"]
check("차고지로 퇴근하는 회차가 있다", len(garage_trips) == 1,
      [t.destination_name for t in used(result)])


print()
print("=== 4. 차량마다 마감을 따로 줄 수 있다 ===")
settings = get_settings()
plain = VehicleInput(vehicle_type="스타리아", plate_number="11가1111", capacity=9)
own = VehicleInput(vehicle_type="스타리아", plate_number="22가2222", capacity=9,
                   outbound_deadline="17:30")
check("안 적으면 센터 공통값", deadline_of(plain, settings) == parse_hhmm(settings.outbound_deadline),
      deadline_of(plain, settings))
check("적으면 그 값이 이긴다", deadline_of(own, settings) == parse_hhmm("17:30"),
      deadline_of(own, settings))
check("잘못 적힌 값은 제약을 걸지 않는다 (배차를 막지 않는다)",
      deadline_of(VehicleInput.model_construct(outbound_deadline="이상한값"), settings) is None)


print()
print("=== 5. 등원에는 마감을 걸지 않는다 ===")
print("   마감은 하원 개념이다. 아침 운행을 묶으면 안 된다.")
people = [
    {"id": f"p{i}", "name": f"어르신{i}", "address": f"주소{i}",
     "latitude": 37.500 + i * 0.008, "longitude": 127.000 + i * 0.008,
     "pickup_start": "18:00", "pickup_end": "20:00"}
    for i in range(1, 4)
]
request = OptimizeRequest.model_validate({
    "trip_type": "inbound",
    "center": {"name": "행복센터", "address": "센터주소",
               "latitude": 37.500, "longitude": 127.000},
    "vehicles": [{"id": "v1", "vehicle_type": "스타리아", "plate_number": "11가1111",
                  "capacity": 9, "outbound_deadline": "17:00"}],
    "passengers": people,
})
resolved = [CENTER] + [
    ResolvedLocation(name=p["name"], address=p["address"],
                     latitude=p["latitude"], longitude=p["longitude"])
    for p in people
]
inbound = optimize_routes(request, resolved, get_settings())
check("마감(17:00)보다 늦은 등원도 정상 배차된다",
      not inbound.unassigned_passengers,
      [i.passenger_id for i in inbound.unassigned_passengers])
check("실제로 마감 이후 시각이다",
      any(parse_hhmm(t.return_time) > parse_hhmm("17:00") for t in used(inbound)),
      [t.return_time for t in used(inbound)])


print()
print("=== 6. 마감을 못 지키면 태우지 못할 뿐, 터지지 않는다 ===")
print("   창이 마감 뒤에 있는 어르신. 배차 불가로 빠져야 한다.")
tight = build(4, capacity=2, deadline="14:00", window=("15:00", "17:00"), trips=2)
check("예외 없이 결과가 나온다", tight.status == "optimal_or_feasible", tight.status)
check("태우지 못한 분이 목록에 잡힌다", len(tight.unassigned_passengers) > 0,
      len(tight.unassigned_passengers))


print()
print("=== 7. 마감이 넉넉하면 예전과 같이 동작한다 ===")
loose = build(4, capacity=9, deadline="23:59", trips=2)
check("전원 배차", not loose.unassigned_passengers)
check("한 회차로 끝난다", len(used(loose)) == 1, len(used(loose)))


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
