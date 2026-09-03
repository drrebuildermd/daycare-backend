"""v3.2 검증: 대안 분석기.

'N명 누락' 까지만 말하면 원장님은 무엇을 해야 할지 모른다.
시간을 조절할 일인지, 회차를 늘릴 일인지, 차를 사야 할 일인지 답해야 한다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_recommender.py
"""
import time

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest
from app.optimizer import optimize_routes
from app.recommender import MAX_TRIPS_PER_VEHICLE, RELAXATION_TIME_LIMIT_SECONDS, analyze

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)


def build(people_spec, fleet_spec, trip_type="inbound", window=("08:00", "10:00")):
    """people_spec: [(id, 휠체어), ...]  fleet_spec: [(id, 정원, 휠체어석), ...]"""
    people = [
        {"id": pid, "name": f"어르신{pid}", "address": f"주소{pid}",
         "latitude": 37.500 + i * 0.005, "longitude": 127.000 + i * 0.005,
         "pickup_start": window[0], "pickup_end": window[1], "wheelchair": wc}
        for i, (pid, wc) in enumerate(people_spec, start=1)
    ]
    fleet = [
        {"id": vid, "vehicle_type": "스타리아",
         "plate_number": f"{i}{i}가{i}{i}{i}{i}", "driver_name": f"기사{i}",
         "capacity": cap, "wheelchair_capacity": wcap}
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
    return request, resolved


def run_and_analyze(request, resolved):
    settings = get_settings()
    result = optimize_routes(request, resolved, settings)
    dropped = [i.passenger_id for i in result.unassigned_passengers]
    started = time.perf_counter()
    report = analyze(request, resolved, settings, dropped, "run-test-0001")
    return result, report, time.perf_counter() - started


# ---------------------------------------------------------------------------
print("=== 1. 빠진 분이 없으면 즉시 끝난다 ===")
request, resolved = build([("p1", False), ("p2", False)], [("v1", 9, 0)])
_, report, elapsed = run_and_analyze(request, resolved)
check("verdict = all_assigned", report.verdict == "all_assigned", report.verdict)
check("솔버를 부르지 않는다 (0.1초 미만)", elapsed < 0.1, f"{elapsed:.3f}초")
check("run id 를 들고 있다", report.optimization_run_id == "run-test-0001")


print()
print("=== 2. 0단계 산수 — 휠체어석이 절대 부족하면 즉시 3순위 ===")
print("   휠체어 5명 / 고정석 0자리. 시간을 넓혀도 회차를 늘려도 답이 없다.")
request, resolved = build(
    [("w1", True), ("w2", True), ("w3", True), ("w4", True), ("w5", True)],
    [("v1", 9, 0)],
)
_, report, elapsed = run_and_analyze(request, resolved)
check("verdict = structural", report.verdict == "structural", report.verdict)
check("솔버를 한 번도 안 돌린다 (0.1초 미만)", elapsed < 0.1, f"{elapsed:.3f}초")
check("대안이 구조적 한계 하나뿐", len(report.options) == 1 and
      report.options[0].kind == "structural",
      [(o.kind, o.priority) for o in report.options])
check("고정석이 한 대도 없다고 말한다",
      "한 대도 없습니다" in (report.options[0].detail or ""),
      report.options[0].detail)
check("몇 명분 부족한지 말한다", "5명분" in report.options[0].headline,
      report.options[0].headline)
print("   판정:", report.options[0].headline)
print("   설명:", report.options[0].detail)


print()
print("=== 3. 0단계 산수 — 좌석이 절대 부족한 경우 ===")
print("   20명 / 정원 2석 한 대. 3회차를 돌아도 6명이 한계다.")
request, resolved = build(
    [(f"p{i}", False) for i in range(1, 21)], [("v1", 2, 0)],
)
_, report, elapsed = run_and_analyze(request, resolved)
check("verdict = structural", report.verdict == "structural", report.verdict)
check("솔버를 안 돌린다", elapsed < 0.1, f"{elapsed:.3f}초")
check("부족 인원을 숫자로 말한다", "14명이 남습니다" in (report.options[0].detail or ""),
      report.options[0].detail)
print("   설명:", report.options[0].detail)


print()
print("=== 4. 1단계 — 시간만 넓히면 되는 경우 ===")
print("   정원은 넉넉한데 창이 좁아 못 태운다. 넓히면 풀려야 한다.")
request, resolved = build(
    [(f"p{i}", False) for i in range(1, 9)], [("v1", 9, 0)],
    window=("08:00", "08:20"),
)
result, report, elapsed = run_and_analyze(request, resolved)
print(f"   기준 계산에서 {len(result.unassigned_passengers)}명 미배차")
if result.unassigned_passengers:
    check("verdict = time_relaxable", report.verdict == "time_relaxable", report.verdict)
    check(f"{RELAXATION_TIME_LIMIT_SECONDS*2}초 + 여유 안에 끝난다",
          elapsed < 8, f"{elapsed:.3f}초")
    option = report.options[0]
    check("1순위 대안이다", option.priority == 1 and option.kind == "adjust_time",
          (option.priority, option.kind))
    check("가능하다고 표시된다", option.feasible)
    check("누구를 몇 분 조절할지 알려 준다", len(option.actions) > 0,
          len(option.actions))
    if option.actions:
        action = option.actions[0]
        check("현재 시각과 제안 시각이 모두 있다",
              bool(action.current_window and action.suggested_window),
              f"{action.current_window} -> {action.suggested_window}")
        check("실제 도착 시각까지 알려 준다", bool(action.scheduled_time),
              action.scheduled_time)
        print(f"   제안: {action.name} {action.current_window} -> "
              f"{action.suggested_window} (실제 도착 {action.scheduled_time})")
    check("해결되는 인원 수가 맞다",
          option.resolves_count == len(result.unassigned_passengers),
          f"{option.resolves_count} vs {len(result.unassigned_passengers)}")
else:
    check("이 시나리오가 미배차를 만든다", False, "판을 다시 짜야 함")


print()
print("=== 5. 2단계 — 회차를 늘려야 하는 경우 ===")
print("   시간은 넉넉한데 정원이 모자란다. 넓혀도 안 되고 3회차면 된다.")
request, resolved = build(
    [(f"p{i}", False) for i in range(1, 7)], [("v1", 2, 0)],
    window=("08:00", "12:00"),
)
result, report, elapsed = run_and_analyze(request, resolved)
print(f"   기준 계산에서 {len(result.unassigned_passengers)}명 미배차")
if result.unassigned_passengers:
    check("verdict = needs_extra_round", report.verdict == "needs_extra_round",
          report.verdict)
    check("6초 + 여유 안에 끝난다", elapsed < 10, f"{elapsed:.3f}초")
    check("1순위(시간)는 안 된다고 나온다",
          report.options[0].kind == "adjust_time" and not report.options[0].feasible)
    winner = [o for o in report.options if o.kind == "add_round"][0]
    check("2순위가 회차 추가", winner.priority == 2)
    check("가능하다고 표시된다", winner.feasible)
    check("어느 차량인지 말한다", "가" in winner.headline, winner.headline)
    check(f"{MAX_TRIPS_PER_VEHICLE}회차를 언급한다",
          f"{MAX_TRIPS_PER_VEHICLE}회차" in winner.headline, winner.headline)
    print("   제안:", winner.headline)
else:
    check("이 시나리오가 미배차를 만든다", False, "판을 다시 짜야 함")


print()
print("=== 6. 우선순위 순서가 지켜진다 ===")
print("   시간 -> 회차 -> 구조. 이 순서로만 제시해야 한다.")
for label, kwargs in (
    ("시간 완화 판", dict(people_spec=[(f"p{i}", False) for i in range(1, 9)],
                          fleet_spec=[("v1", 9, 0)], window=("08:00", "08:20"))),
    ("회차 추가 판", dict(people_spec=[(f"p{i}", False) for i in range(1, 7)],
                          fleet_spec=[("v1", 2, 0)], window=("08:00", "12:00"))),
):
    request, resolved = build(**kwargs)
    _, report, _ = run_and_analyze(request, resolved)
    priorities = [o.priority for o in report.options]
    check(f"{label}: 우선순위가 오름차순", priorities == sorted(priorities), priorities)
    kinds = [o.kind for o in report.options]
    order = {"adjust_time": 1, "add_round": 2, "structural": 3}
    check(f"{label}: 종류도 순서대로",
          [order[k] for k in kinds] == sorted(order[k] for k in kinds), kinds)


print()
print("=== 7. 완화 패스가 원본 요청을 건드리지 않는다 ===")
request, resolved = build(
    [(f"p{i}", False) for i in range(1, 9)], [("v1", 9, 0)],
    window=("08:00", "08:20"),
)
before = [(p.id, p.pickup_start, p.pickup_end) for p in request.passengers]
run_and_analyze(request, resolved)
after = [(p.id, p.pickup_start, p.pickup_end) for p in request.passengers]
check("원본 시간창이 그대로다", before == after)


print()
print("=== 8. 비용 통제 ===")
check(f"완화 패스 제한 시간이 {RELAXATION_TIME_LIMIT_SECONDS}초",
      RELAXATION_TIME_LIMIT_SECONDS == 2, RELAXATION_TIME_LIMIT_SECONDS)
check("기본 배차의 15초를 건드리지 않는다",
      get_settings().solver_time_limit_seconds == 15,
      get_settings().solver_time_limit_seconds)

print()
print("   최악의 경우(3단계 모두 실행) 실측:")
request, resolved = build(
    [(f"p{i}", False) for i in range(1, 13)], [("v1", 3, 0), ("v2", 3, 0)],
    window=("08:00", "08:35"),
)
_, report, elapsed = run_and_analyze(request, resolved)
check("6초 + 여유 안에 끝난다", elapsed < 10, f"{elapsed:.3f}초 / {report.verdict}")
check("분석 시간이 보고서에 기록된다", report.analyzed_seconds > 0,
      f"{report.analyzed_seconds}초")


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
