"""실전 스케일 하원 배차 시뮬레이션.

어르신 40명, 차량 5대(4인승 4대 + 9인승 1대), 그중 2대는 자차(차고지 복귀형).
좌표를 직접 넣어 카카오 지오코딩을 타지 않는다.

무엇을 증명하려는가
  1. 자차 차량의 하원 1회차가 센터에서 출발하는가
  2. 자차 차량의 하원 마지막 회차가 차고지에서 끝나는가
  3. 40명이 정원과 8시간 룰에 맞게 쪼개지는가

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_simulation_40.py
"""
import math
import sys

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, parse_hhmm
from app.optimizer import optimize_routes

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


# ── 가상 센터: 창원 의창구 언저리 ──────────────────────────────
CENTER_LAT, CENTER_LNG = 35.2557, 128.6138

# ── 어르신 40명 ────────────────────────────────────────────────
# 등원 시각을 07:30 부터 10:00 까지 흩어 놓는다. 8시간 룰이 걸리면
# 하원 시각도 15:30 부터 18:00 까지 따라서 흩어져야 한다.
# 창을 3시간으로 잡는다. 실제 센터의 등원도 07:30~10:30 처럼 넓게 잡는다.
# 조건을 바꿔가며 재보니 이 규모(40명 / 25석 5대 / 2회 운행)에서는
# 창이 2시간이면 해가 아예 없고 3시간부터 풀린다.
PICKUP_SLOTS = [
    ("07:30", "10:30"), ("08:00", "11:00"), ("08:30", "11:30"),
    ("09:00", "12:00"), ("09:30", "12:30"),
]

PASSENGERS = []
for i in range(40):
    angle = (i / 40) * 2 * math.pi
    radius = 0.010 + (i % 7) * 0.0035          # 센터에서 1~4km 흩어놓는다
    start, end = PICKUP_SLOTS[i % len(PICKUP_SLOTS)]
    PASSENGERS.append({
        "id": f"sim-{i + 1:02d}",
        "name": f"어르신{i + 1:02d}",
        "address": f"창원시 의창구 가상동 {i + 1}-{(i % 9) + 1}",
        "latitude": CENTER_LAT + radius * math.cos(angle),
        "longitude": CENTER_LNG + radius * math.sin(angle) * 1.2,
        "pickup_start": start,
        "pickup_end": end,
    })

# ── 차량 5대: 4인승 4대 + 9인승 1대, 그중 2대는 자차 ────────────
GARAGES = {
    "차량2": (CENTER_LAT - 0.028, CENTER_LNG + 0.031),
    "차량5": (CENTER_LAT + 0.026, CENTER_LNG - 0.034),
}
VEHICLES = []
for index, (name, capacity) in enumerate(
    [("차량1", 4), ("차량2", 4), ("차량3", 4), ("차량4", 4), ("차량5", 9)], start=1
):
    vehicle = {
        "id": f"sim-veh-{index}",
        "vehicle_type": "스타리아" if capacity == 9 else "레이",
        "plate_number": f"{index}{index}가{index}{index}{index}{index}",
        "driver_name": f"기사{index}",
        "capacity": capacity,
    }
    if name in GARAGES:
        lat, lng = GARAGES[name]
        vehicle.update({
            "start_type": "custom",
            "start_address": f"{name} 기사님 차고지",
            "start_latitude": lat,
            "start_longitude": lng,
        })
    VEHICLES.append(vehicle)

SELF_DRIVE = {v["plate_number"] for v in VEHICLES if v.get("start_type") == "custom"}

# ── 노드 순서: 0=센터, 1..40=어르신, 41..=자차 차고지 ───────────
resolved = [ResolvedLocation(name="가상주간보호센터", address="창원시 의창구 가상로 1",
                             latitude=CENTER_LAT, longitude=CENTER_LNG)]
resolved += [ResolvedLocation(name=p["name"], address=p["address"],
                              latitude=p["latitude"], longitude=p["longitude"])
             for p in PASSENGERS]
resolved += [ResolvedLocation(name=f'{v["plate_number"]} 차고지', address=v["start_address"],
                              latitude=v["start_latitude"], longitude=v["start_longitude"])
             for v in VEHICLES if v.get("start_type") == "custom"]

request = OptimizeRequest.model_validate({
    "trip_type": "outbound",
    "center": {"name": "가상주간보호센터", "address": "창원시 의창구 가상로 1",
               "latitude": CENTER_LAT, "longitude": CENTER_LNG},
    "vehicles": VEHICLES,
    "passengers": PASSENGERS,
})

settings = get_settings().model_copy(update={"solver_time_limit_seconds": 60})
stay = round(settings.stay_hours * 60)

print("=== 시뮬레이션 조건 ===")
print(f"  센터 1곳 · 어르신 {len(PASSENGERS)}명 · 차량 {len(VEHICLES)}대")
print(f"  정원: {' + '.join(str(v['capacity']) for v in VEHICLES)}"
      f" = {sum(v['capacity'] for v in VEHICLES)}석 (2회 운행이면 "
      f"{sum(v['capacity'] for v in VEHICLES) * 2}명)")
print(f"  자차(차고지 복귀형): {', '.join(sorted(SELF_DRIVE))}")
print(f"  머무는 시간: {settings.stay_hours}시간")
print()

result = optimize_routes(request, resolved, settings)

# ══════════════════════════════════════════════════════════════
print("=== 운행 결과 ===")
print()
placed = []
for vehicle in result.vehicles:
    mark = "자차" if vehicle.plate_number in SELF_DRIVE else "센터"
    used = [t for t in vehicle.trips if t.used]
    total = sum(len(t.stops) for t in used)
    print(f"[{mark}] {vehicle.vehicle_type} {vehicle.plate_number}"
          f" · {vehicle.driver_name} · 정원 {vehicle.capacity}석 · 총 {total}명")
    for trip in vehicle.trips:
        if not trip.used:
            print(f"    {trip.round}회차  (운행 없음)"
                  f"   {trip.origin_name} → {trip.destination_name}")
            continue
        print(f"    {trip.round}회차  {trip.departure_time}~{trip.return_time}"
              f"  {len(trip.stops)}/{vehicle.capacity}명  {trip.distance_km}km")
        print(f"           {trip.origin_name} 출발 → {trip.destination_name} 도착")
        for stop in trip.stops:
            placed.append(stop.passenger_id)
            print(f"             {stop.sequence}. {stop.name}"
                  f"  하차 {stop.estimated_pickup}  (희망 {stop.requested_window})")
    print()

print(f"총 이동거리 {result.total_distance_km}km · 연산 {result.solve_seconds}초")
print()

# ══════════════════════════════════════════════════════════════
print("=== 검증 ===")
print()

print("① 자차 차량의 1회차는 센터에서 출발한다")
for vehicle in result.vehicles:
    if vehicle.plate_number not in SELF_DRIVE:
        continue
    first = next(t for t in vehicle.trips if t.round == 1)
    check(f"{vehicle.plate_number} 1회차 출발",
          first.origin_name == "가상주간보호센터", first.origin_name)

print()
print("② 자차 차량의 마지막 회차는 차고지에서 끝난다")
for vehicle in result.vehicles:
    garage = f"{vehicle.plate_number} 차고지"
    last = next(t for t in vehicle.trips if t.round == 2)
    if vehicle.plate_number in SELF_DRIVE:
        check(f"{vehicle.plate_number} 2회차 도착", last.destination_name == garage,
              last.destination_name)
    else:
        check(f"{vehicle.plate_number}(센터차량) 2회차 도착",
              last.destination_name == "가상주간보호센터", last.destination_name)

print()
print("③ 40명이 정원과 8시간 룰에 맞게 쪼개졌다")
check("40명 전원 배차", len(placed) == 40, f"{len(placed)}명")
check("중복 배차 없음", len(set(placed)) == len(placed), f"고유 {len(set(placed))}명")

over = [(v.plate_number, t.round, len(t.stops), v.capacity)
        for v in result.vehicles for t in v.trips if t.used and len(t.stops) > v.capacity]
check("정원을 넘긴 회차 없음", not over, over or "없음")

window_of = {p["id"]: p for p in PASSENGERS}
out_of_window = []
for vehicle in result.vehicles:
    for trip in vehicle.trips:
        for stop in trip.stops:
            person = window_of[stop.passenger_id]
            low, high = person["pickup_start"], person["pickup_end"]
            want_low = parse_hhmm(low) + stay
            want_high = parse_hhmm(high) + stay
            got = parse_hhmm(stop.estimated_pickup)
            if not (want_low <= got <= want_high):
                out_of_window.append((stop.name, low, stop.estimated_pickup))
check("모든 하차가 '등원+8시간' 창 안", not out_of_window, out_of_window[:4] or "없음")

# 일찍 오신 분이 일찍 가시는가
early = [s for v in result.vehicles for t in v.trips for s in t.stops
         if window_of[s.passenger_id]["pickup_start"] == "07:30"]
late = [s for v in result.vehicles for t in v.trips for s in t.stops
        if window_of[s.passenger_id]["pickup_start"] == "09:30"]
early_avg = sum(parse_hhmm(s.estimated_pickup) for s in early) / len(early)
late_avg = sum(parse_hhmm(s.estimated_pickup) for s in late) / len(late)
check("일찍 오신 무리가 늦게 오신 무리보다 먼저 내리심",
      early_avg < late_avg,
      f"07:30조 평균 {early_avg / 60:.1f}시 / 09:30조 평균 {late_avg / 60:.1f}시")

print()
print("④ 회차 순서가 뒤집히지 않았다")
for vehicle in result.vehicles:
    trips = {t.round: t for t in vehicle.trips}
    if not (trips[1].used and trips[2].used):
        continue
    check(f"{vehicle.plate_number} 1회차 복귀 후 2회차 출발",
          trips[1].return_time <= trips[2].departure_time,
          f"{trips[1].return_time} -> {trips[2].departure_time}")

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 실전 스케일에서 하원 배차가 규칙대로 나옵니다.")
