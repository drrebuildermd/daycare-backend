"""v4.1 검증: 센터 주도형 배차.

보호자 희망 시간을 맞추기보다, 센터가 수가를 지키는 선에서 효율적인 동선을
짜고 그 시각을 통보하는 것이 실제 운영 방식이다.

다만 시간을 무한정 열면 두 가지가 무너진다.
  · 수가 — 마지노선을 넘겨 도착하면 이용시간이 줄어 구간이 내려간다
  · 탑승 시간 — 차 한 대로 온 동네를 도는 답이 싸 보인다

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_center_driven.py
"""
from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, PassengerInput, format_hhmm, parse_hhmm
from app.optimizer import optimize_routes, resolve_window

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()
CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)


def person(**kw):
    return PassengerInput.model_validate({
        "name": kw.pop("name", "어르신"), "address": "주소",
        "latitude": 37.5, "longitude": 127.0, **kw,
    })


# ---------------------------------------------------------------------------
print("=== 1. 역산 — 수가를 지키는 마지노선 ===")
print("   마감 17:00 · 계획 8시간 · 안전 여유 15분 -> 08:45 까지 도착해야 한다.")

deadline = parse_hhmm("17:00")
low, high, source, conflict = resolve_window(person(), "inbound", 480, S, deadline)
check("엔진이 정한 것으로 표시된다", source == "derived", source)
check("모순 아님", not conflict)
check(f"하한이 가장 이른 픽업({S.earliest_pickup})", low == parse_hhmm(S.earliest_pickup),
      format_hhmm(low))
check("상한 = 마감 − 8시간 − 15분 = 08:45",
      high == deadline - 480 - S.deadline_safety_margin_minutes,
      format_hhmm(high))
print(f"   → {format_hhmm(low)}~{format_hhmm(high)}")


print()
print("=== 2. 계획 이용시간이 길면 마지노선이 당겨진다 ===")
for hours, expected in ((6, "10:45"), (8, "08:45"), (9, "07:45")):
    _, hi, _, _ = resolve_window(
        person(planned_service_hours=hours), "inbound", 480, S, deadline)
    check(f"{hours}시간 이용 -> {expected} 까지", format_hhmm(hi) == expected, format_hhmm(hi))


print()
print("=== 3. 원장님이 적은 시각이 언제나 이긴다 ===")
told = person(pickup_start="09:30", pickup_end="10:30")
low, high, source, _ = resolve_window(told, "inbound", 480, S, deadline)
check("적어 둔 값이 그대로 쓰인다",
      (format_hhmm(low), format_hhmm(high)) == ("09:30", "10:30"),
      f"{format_hhmm(low)}~{format_hhmm(high)}")
check("역산 마지노선(08:45)을 넘겨도 존중한다", high > parse_hhmm("08:45"))
check("declared 로 표시된다", source == "declared", source)

half = person(pickup_start="08:20")
low, high, source, _ = resolve_window(half, "inbound", 480, S, deadline)
check("하한만 적으면 그쪽만 존중하고 상한은 역산",
      (format_hhmm(low), format_hhmm(high)) == ("08:20", "08:45"),
      f"{format_hhmm(low)}~{format_hhmm(high)}")


print()
print("=== 4. 설정이 모순이면 조용히 뭉개지 않고 알린다 ===")
print("   07:30 부터 17:00 까지는 9시간 30분. 11시간 이용은 불가능하다.")
low, high, _, conflict = resolve_window(
    person(planned_service_hours=11), "inbound", 480, S, deadline)
check("모순으로 표시된다", conflict is True)
check("창이 한 점으로 붙는다", low == high, f"{format_hhmm(low)}~{format_hhmm(high)}")


print()
print("=== 5. 하원은 계획 이용시간을 채운 뒤에 나간다 ===")
low, high, source, _ = resolve_window(person(), "outbound", 480, S, deadline)
check("하한 = 가장 이른 픽업 + 8시간 = 15:30",
      format_hhmm(low) == "15:30", format_hhmm(low))
check("상한 = 하원 마감", high == deadline, format_hhmm(high))
check("derived 로 표시된다", source == "derived")


print()
print("=== 6. 실제로 풀어 본다 — 시각을 비운 명단 ===")


def solve(count, capacity=9, blank=True, vehicles=1, spread=0.008):
    people = []
    for i in range(1, count + 1):
        row = {"id": f"p{i}", "name": f"어르신{i}", "address": f"주소{i}",
               "latitude": 37.500 + i * spread, "longitude": 127.000 + i * spread}
        if not blank:
            row.update({"pickup_start": "08:00", "pickup_end": "09:00"})
        people.append(row)
    request = OptimizeRequest.model_validate({
        "trip_type": "inbound",
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [{"id": f"v{v}", "vehicle_type": "스타리아",
                      "plate_number": f"{v+1}{v+1}가{v+1}{v+1}{v+1}{v+1}",
                      "capacity": capacity} for v in range(vehicles)],
        "passengers": people,
    })
    resolved = [CENTER] + [
        ResolvedLocation(name=p["name"], address=p["address"],
                         latitude=p["latitude"], longitude=p["longitude"])
        for p in people
    ]
    return optimize_routes(request, resolved, S)


result = solve(6)
check("시각을 비워도 배차된다", not result.unassigned_passengers,
      [i.passenger_id for i in result.unassigned_passengers])

stops = [s for v in result.vehicles for t in v.trips if t.used for s in t.stops]
check("모든 정류장이 derived 로 표시된다",
      all(s.time_source == "derived" for s in stops),
      {s.time_source for s in stops})

limit = parse_hhmm(S.earliest_pickup)
check("가장 이른 픽업보다 이르게 가지 않는다",
      all(parse_hhmm(s.estimated_pickup) >= limit for s in stops),
      min(s.estimated_pickup for s in stops))

for vehicle in result.vehicles:
    for trip in vehicle.trips:
        if trip.used:
            check(f"{trip.round}회차 센터 도착 {trip.return_time} <= 08:45",
                  parse_hhmm(trip.return_time) <= parse_hhmm("08:45"),
                  trip.return_time)
print(f"   픽업 시각: {[s.estimated_pickup for s in stops]}")


print()
print("=== 7. 회차 소요 시간 상한 ===")
print(f"   설정값 {S.max_transit_minutes}분. 한 회차가 이보다 길 수 없다.")
wide = solve(8, capacity=9, spread=0.020)
for vehicle in wide.vehicles:
    for trip in vehicle.trips:
        if not trip.used:
            continue
        span = parse_hhmm(trip.return_time) - parse_hhmm(trip.departure_time)
        check(f"{trip.round}회차 소요 {span}분 <= {S.max_transit_minutes}분",
              span <= S.max_transit_minutes, f"{span}분")


print()
print("=== 8. 적어 둔 시각은 예전과 똑같이 동작한다 (하위 호환) ===")
told_result = solve(5, blank=False)
check("전원 배차", not told_result.unassigned_passengers)
told_stops = [s for v in told_result.vehicles for t in v.trips if t.used for s in t.stops]
check("declared 로 표시된다",
      all(s.time_source == "declared" for s in told_stops),
      {s.time_source for s in told_stops})
check("적어 둔 창 안에서 픽업한다",
      all(parse_hhmm("08:00") <= parse_hhmm(s.estimated_pickup) <= parse_hhmm("09:00")
          for s in told_stops),
      [s.estimated_pickup for s in told_stops])


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
