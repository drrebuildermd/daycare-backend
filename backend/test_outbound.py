"""v2.0 등원/하원 분리 검증.

좌표를 직접 넣어 카카오 지오코딩을 타지 않는다.
실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_outbound.py
"""
import sys

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, RideCompletionCreate
from app.optimizer import optimize_routes, trip_endpoints

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


# 노드: 0=센터, 1..3=어르신, 4=자차 출발지(기사님 자택)
CENTER = ResolvedLocation(name="행복센터", address="센터", latitude=37.500, longitude=127.000)
P1 = ResolvedLocation(name="김어르신", address="주소1", latitude=37.510, longitude=127.010)
P2 = ResolvedLocation(name="박어르신", address="주소2", latitude=37.520, longitude=127.020)
P3 = ResolvedLocation(name="최어르신", address="주소3", latitude=37.530, longitude=127.030)
HOME = ResolvedLocation(name="기사님 자택", address="자택", latitude=37.470, longitude=126.970)

HOME_NODE = 4


def build(trip_type, self_drive=True, passengers=3, capacity=7, **extra):
    people = [
        {"id": f"p{i}", "name": n, "address": a, "latitude": lat, "longitude": lng,
         "pickup_start": "08:00", "pickup_end": "09:30", **extra}
        for i, (n, a, lat, lng) in enumerate(
            [("김어르신", "주소1", 37.510, 127.010),
             ("박어르신", "주소2", 37.520, 127.020),
             ("최어르신", "주소3", 37.530, 127.030)][:passengers], start=1)
    ]
    vehicle = {
        "id": "veh-1", "vehicle_type": "스타리아", "plate_number": "11가1111",
        "driver_name": "김기사", "capacity": capacity,
    }
    if self_drive:
        vehicle.update({"start_type": "custom", "start_address": "자택",
                        "start_latitude": 37.470, "start_longitude": 126.970})
    request = OptimizeRequest.model_validate({
        "trip_type": trip_type,
        "center": {"name": "행복센터", "address": "센터",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [vehicle],
        "passengers": people,
    })
    resolved = [CENTER, P1, P2, P3][:1 + passengers] + ([HOME] if self_drive else [])
    return optimize_routes(request, resolved, get_settings())


print("=== 1. 회차별 출발/도착 규칙 ===")

RULES = [
    # (설명, 자차인가, 회차, 운행종류, 기대 출발, 기대 도착)
    ("등원 자차 1회차", HOME_NODE, 1, "inbound", HOME_NODE, 0),
    ("등원 자차 2회차", HOME_NODE, 2, "inbound", 0, 0),
    ("등원 센터 1회차", 0, 1, "inbound", 0, 0),
    ("등원 센터 2회차", 0, 2, "inbound", 0, 0),
    ("하원 자차 1회차", HOME_NODE, 1, "outbound", 0, 0),
    ("하원 자차 2회차", HOME_NODE, 2, "outbound", 0, HOME_NODE),
    ("하원 센터 1회차", 0, 1, "outbound", 0, 0),
    ("하원 센터 2회차", 0, 2, "outbound", 0, 0),
]
for label, home, rnd, kind, want_start, want_end in RULES:
    got = trip_endpoints(home, rnd, kind)
    check(label, got == (want_start, want_end), f"{got} (기대 {(want_start, want_end)})")


print()
print("=== 2. 등원은 늘 센터에서 끝난다 ===")

result = build("inbound")
check("trip_type 이 응답에 실림", result.trip_type == "inbound", result.trip_type)
used = [t for t in result.vehicles[0].trips if t.used]
check("모든 회차가 센터 도착", all(t.destination_name == "행복센터" for t in used),
      [t.destination_name for t in used])
first = next(t for t in result.vehicles[0].trips if t.round == 1)
check("자차 1회차는 자택에서 출발", first.origin_name == "기사님 자택", first.origin_name)


print()
print("=== 3. 하원 자차: 1회차는 센터 복귀, 2회차는 자택에서 끝난다 ===")

result = build("outbound")
check("trip_type 이 응답에 실림", result.trip_type == "outbound", result.trip_type)
trips = {t.round: t for t in result.vehicles[0].trips}
check("1회차 출발은 센터", trips[1].origin_name == "행복센터", trips[1].origin_name)
check("1회차 도착은 센터", trips[1].destination_name == "행복센터", trips[1].destination_name)
check("2회차 출발은 센터", trips[2].origin_name == "행복센터", trips[2].origin_name)
check("2회차 도착은 기사님 자택", trips[2].destination_name == "기사님 자택",
      trips[2].destination_name)


print()
print("=== 4. 하원 센터 차량은 양쪽 다 센터 ===")

result = build("outbound", self_drive=False)
for trip in result.vehicles[0].trips:
    check(f"{trip.round}회차 센터→센터",
          trip.origin_name == "행복센터" and trip.destination_name == "행복센터",
          f"{trip.origin_name} → {trip.destination_name}")


print()
print("=== 5. 하원 시간창은 센터 공통 기본값을 쓴다 ===")

settings = get_settings()
result = build("outbound", capacity=7)
stops = [s for t in result.vehicles[0].trips if t.used for s in t.stops]
want = f"{settings.dropoff_window_start}~{settings.dropoff_window_end}"
check("요청 시간창이 하원 기본값", all(s.requested_window == want for s in stops),
      {s.name: s.requested_window for s in stops})
check("도착 예정 시각이 그 창 안에",
      all(settings.dropoff_window_start <= s.estimated_pickup <= settings.dropoff_window_end
          for s in stops),
      {s.name: s.estimated_pickup for s in stops})

# 어르신이 직접 하원 시각을 지정하면 그 값을 쓴다.
result = build("outbound", dropoff_start="16:00", dropoff_end="16:30")
stops = [s for t in result.vehicles[0].trips if t.used for s in t.stops]
check("지정한 하원 시각이 우선", all(s.requested_window == "16:00~16:30" for s in stops),
      {s.name: s.requested_window for s in stops})

# 등원은 여전히 픽업 시간창이다.
result = build("inbound")
stops = [s for t in result.vehicles[0].trips if t.used for s in t.stops]
check("등원은 픽업 시간창 유지", all(s.requested_window == "08:00~09:30" for s in stops),
      {s.name: s.requested_window for s in stops})


print()
print("=== 6. 등원/하원 탑승 여부가 따로 논다 ===")

from app.models import PassengerInput

only_in = PassengerInput.model_validate({
    "name": "김", "address": "주소", "latitude": 37.5, "longitude": 127.0,
    "pickup_start": "08:00", "pickup_end": "09:00",
    "attending": True, "attending_outbound": False,
})
check("등원만 타는 분", only_in.is_attending("inbound") and not only_in.is_attending("outbound"))

only_out = PassengerInput.model_validate({
    "name": "박", "address": "주소", "latitude": 37.5, "longitude": 127.0,
    "pickup_start": "08:00", "pickup_end": "09:00",
    "attending": False, "attending_outbound": True,
})
check("하원만 타는 분", (not only_out.is_attending("inbound")) and only_out.is_attending("outbound"))

legacy = PassengerInput.model_validate({
    "name": "최", "address": "주소", "latitude": 37.5, "longitude": 127.0,
    "pickup_start": "08:00", "pickup_end": "09:00",
})
check("구형 명단은 둘 다 탑승", legacy.is_attending("inbound") and legacy.is_attending("outbound"))


print()
print("=== 7. 구형 앱 호환: trip_type 을 안 보내면 등원 ===")

req = OptimizeRequest.model_validate({
    "center": {"name": "센터", "address": "주소", "latitude": 37.5, "longitude": 127.0},
    "vehicles": [{"vehicle_type": "레이", "plate_number": "22나2222", "capacity": 5}],
    "passengers": [{"name": "김", "address": "주소", "latitude": 37.51, "longitude": 127.01,
                    "pickup_start": "08:00", "pickup_end": "09:00"}],
})
check("배차 요청 기본값", req.trip_type == "inbound", req.trip_type)

done = RideCompletionCreate.model_validate({
    "passenger_id": "p1", "passenger_name": "김", "vehicle_id": "v1",
    "vehicle_type": "레이", "vehicle_plate_number": "22나2222",
    "trip_round": 1, "scheduled_pickup": "08:10",
})
check("탑승 기록 기본값", done.trip_type == "inbound", done.trip_type)


print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 등원/하원이 규칙대로 갈립니다.")
