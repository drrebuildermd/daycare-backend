"""v4.2 검증: 어르신을 길에 두지 않는다.

현장에서 40명 명단으로 5명이 배차 누락됐다. 원장님 말씀은 분명했다.
"이렇게 정해진 시간에 얽매여서 어르신을 길에 버려두는 일은 절대 없어."

그래서 엔진이 제약에 막히면 포기하지 않고 스스로 조금씩 양보하며 다시 푼다.
다만 세 가지를 반드시 지켜야 한다.

  · 원안으로 되면 아무것도 양보하지 않는다 (멀쩡한 배차를 흔들지 않는다)
  · 양보는 싼 것부터 한다 (이용시간 단축은 수가 손실이라 맨 뒤다)
  · 무엇을 얼마나 양보했는지 반드시 보고한다 (조용히 바꾸면 오통보가 된다)

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_soft_constraint.py
"""
from app.config import get_settings
from app.escalate import LADDER, Step, solve_until_everyone_rides
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, format_hhmm, parse_hhmm

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()
# 다시 풀기를 여러 번 하므로 검증에서는 솔버 시간을 줄인다.
S = S.model_copy(update={"solver_time_limit_seconds": 3})

CENTER = ResolvedLocation(name="행복센터", address="센터", latitude=37.500, longitude=127.000)

# 센터에서 사방으로 2km 남짓 흩어진 다섯 분. 한 바퀴 도는 데 시간이 걸린다.
SPOTS = [
    ("김마중", 37.518, 127.000),
    ("이케어", 37.482, 127.000),
    ("박삼수", 37.500, 127.023),
    ("최복순", 37.500, 126.977),
    ("정영자", 37.514, 127.018),
]


def build(window=None, hours=None, capacity=9, people=None):
    picked = people or SPOTS
    passengers = []
    for index, (name, lat, lon) in enumerate(picked, start=1):
        row = {"id": f"pa{index}", "name": name, "address": f"{name} 자택",
               "latitude": lat, "longitude": lon}
        if window:
            row["pickup_start"], row["pickup_end"] = window
        if hours:
            row["planned_service_hours"] = hours
        passengers.append(row)
    return OptimizeRequest.model_validate({
        "trip_type": "inbound",
        "center": {"name": "행복센터", "address": "센터",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [{"id": "v1", "vehicle_type": "스타리아",
                      "plate_number": "00검0001", "capacity": capacity}],
        "passengers": passengers,
    })


def resolved_for(request):
    return [CENTER] + [
        ResolvedLocation(name=p.name, address=p.address,
                         latitude=p.latitude, longitude=p.longitude)
        for p in request.passengers
    ]


def solve(request):
    return solve_until_everyone_rides(request, resolved_for(request), S)


# ---------------------------------------------------------------------------
print("=== 1. 사다리 자체가 올바른 순서인가 ===")
print("   싼 것부터 양보해야 한다. 이용시간 단축은 수가 손실이라 맨 뒤다.")

check("첫 칸은 원안이다 (아무것도 양보하지 않는다)", LADDER[0].is_original, LADDER[0].describe())
check("여섯 칸이다", len(LADDER) == 6, len(LADDER))

slacks = [s.window_slack for s in LADDER]
cuts = [s.service_cut for s in LADDER]
check("희망 시각 여유는 줄지 않는다", slacks == sorted(slacks), slacks)
check("이용시간 단축도 줄지 않는다", cuts == sorted(cuts), cuts)
check("희망 시각은 최대 ±60분", max(slacks) == 60, max(slacks))
check("이용시간 단축은 최대 60분 (8시간 -> 7시간)", max(cuts) == 60, max(cuts))

first_cut = next(i for i, s in enumerate(LADDER) if s.service_cut)
first_slack = next(i for i, s in enumerate(LADDER) if s.window_slack)
check("시각을 먼저 넓히고 이용시간은 나중에 줄인다", first_slack < first_cut,
      f"창 {first_slack}번째 · 이용시간 {first_cut}번째")
for step in LADDER[first_cut:]:
    check(f"이용시간을 줄이는 칸은 시각을 이미 최대로 열어 뒀다 ({step.describe()})",
          step.window_slack == 60, step.window_slack)


print()
print("=== 2. 원안으로 되면 아무것도 건드리지 않는다 (가장 중요) ===")
print("   멀쩡히 돌아가던 배차가 v4.2 때문에 달라지면 안 된다.")

plain = solve(build())
result, relax = plain
check("전원 배차된다", not result.unassigned_passengers, len(result.unassigned_passengers))
check("양보하지 않았다", not relax.applied, relax.label)
check("첫 칸에서 끝났다 (다시 풀지 않았다)", relax.steps_tried == 1, relax.steps_tried)
check("조정된 어르신이 없다", not relax.adjusted, len(relax.adjusted))
check("이용시간을 줄이지 않았다", relax.service_cut_minutes == 0, relax.service_cut_minutes)

baseline_km = result.total_distance_km
print(f"   → {result.total_distance_km}km · {len(result.vehicles[0].trips)}회차 배정")


print()
print("=== 3. 시간이 빡빡하면 스스로 넓혀서 전원을 태운다 ===")
print("   다섯 분이 08:00~08:05 5분 안에 다 타실 수는 없다. 정차만 15분이다.")

tight = build(window=("08:00", "08:05"))

# 먼저 원안으로만 풀어 보면 실제로 누락이 나는가 (전제 확인)
from app.optimizer import optimize_routes  # noqa: E402
bare = optimize_routes(tight, resolved_for(tight), S)
check("전제 — 원안대로면 실제로 누락이 난다", bool(bare.unassigned_passengers),
      f"{len(bare.unassigned_passengers)}명 누락")

result, relax = solve(tight)
check("자동 완화로 전원 배차됐다", not result.unassigned_passengers,
      [i.name for i in result.unassigned_passengers])
check("양보했다고 보고한다", relax.applied, relax.label)
check("다시 풀었다", relax.steps_tried > 1, f"{relax.steps_tried}칸")
check("희망 시각을 넓혔다", relax.window_slack_minutes > 0, relax.window_slack_minutes)
check("이용시간까지는 안 줄였다 (싼 것으로 해결됐다)",
      relax.service_cut_minutes == 0, relax.service_cut_minutes)
print(f"   → 양보: {relax.label} · {relax.elapsed_seconds}초")


print()
print("=== 4. 누가 얼마나 밀렸는지 실명으로 보고한다 ===")
print("   조용히 시각만 바꿔 놓으면 원장님이 보호자에게 잘못 통보하시게 된다.")

check("조정된 분 목록이 비어 있지 않다", bool(relax.adjusted), len(relax.adjusted))
names = {item.name for item in relax.adjusted}
check("모두 실제 명단에 있는 분이다", names <= {n for n, _, _ in SPOTS}, names)

for item in relax.adjusted:
    print(f"     {item.name} — 당초 {item.planned_window} → 실제 {item.actual_time} "
          f"({item.shift_minutes}분)")
    low, high = (parse_hhmm(t) for t in item.planned_window.split("~"))
    actual = parse_hhmm(item.actual_time)
    check(f"{item.name} 은 정말로 당초 창을 벗어났다", not (low <= actual <= high),
          f"{item.planned_window} vs {item.actual_time}")
    check(f"{item.name} 의 밀린 분이 실제 차이와 맞는다",
          item.shift_minutes == (low - actual if actual < low else actual - high),
          item.shift_minutes)
    check(f"{item.name} 은 양보 한도({relax.window_slack_minutes}분) 안에서 밀렸다",
          item.shift_minutes <= relax.window_slack_minutes, item.shift_minutes)

if relax.adjusted:
    shifts = [i.shift_minutes for i in relax.adjusted]
    check("많이 밀린 분부터 보여 준다", shifts == sorted(shifts, reverse=True), shifts)

# 넓힌 것과 실제로 밀린 것은 다르다. 전원을 넓혔다고 전원이 밀린 것은 아니다.
check("실제로 밀린 분만 골라냈다 (전원이 아니다)",
      len(relax.adjusted) <= len(SPOTS), len(relax.adjusted))


print()
print("=== 5. 마지막 칸 — 이용시간을 줄이면 마지노선이 뒤로 밀린다 ===")
print("   8시간을 7시간으로 줄이면 '몇 시까지 도착' 선이 한 시간 늦춰진다.")
print("   그래서 아침에 늦게 출발해도 태울 수 있게 된다. 대신 수가가 준다.")

from app.optimizer import resolve_window  # noqa: E402
from app.models import PassengerInput  # noqa: E402

one = PassengerInput.model_validate({"name": "어르신", "address": "주소",
                                     "latitude": 37.5, "longitude": 127.0,
                                     "planned_service_hours": 8})
deadline = parse_hhmm("17:00")
_, base_high, _, _ = resolve_window(one, "inbound", 480, S, deadline)
check("안 줄이면 08:45 까지", format_hhmm(base_high) == "08:45", format_hhmm(base_high))

for cut, expected in ((30, "09:15"), (60, "09:45")):
    _, high, _, _ = resolve_window(one, "inbound", 480, S, deadline, cut)
    check(f"{cut}분 줄이면 {expected} 까지 (정확히 {cut}분 늦춰진다)",
          format_hhmm(high) == expected and high - base_high == cut, format_hhmm(high))

# 아무리 줄여도 최소 1시간은 남긴다. 30분 이용은 수가가 나오지 않는다.
_, floor_high, _, _ = resolve_window(
    PassengerInput.model_validate({"name": "짧게", "address": "주소",
                                   "latitude": 37.5, "longitude": 127.0,
                                   "planned_service_hours": 1}),
    "inbound", 480, S, deadline, 60)
check("이용시간 1시간 밑으로는 안 내려간다",
      floor_high == deadline - 60 - S.deadline_safety_margin_minutes,
      format_hhmm(floor_high))


print()
print("=== 6. 물리적으로 불가능하면 지어내지 않는다 ===")
print("   정원 2명 차 한 대(2회차)면 네 자리뿐이다. 다섯 분은 못 태운다.")
print("   이때는 솔직하게 배차 불가로 남겨야 한다. 없는 답을 만들면 현장이 무너진다.")

impossible = build(capacity=2)
result, relax = solve(impossible)
check("누락을 감추지 않는다", bool(result.unassigned_passengers),
      len(result.unassigned_passengers))
check("사다리를 끝까지 다 해 봤다", relax.steps_tried == len(LADDER), relax.steps_tried)
check("결과는 여전히 유효한 배차표다", result.status == "optimal_or_feasible", result.status)
print(f"   → {len(result.unassigned_passengers)}명 배차 불가 "
      f"(사유: {sorted({i.reason for i in result.unassigned_passengers})})")


print()
print("=== 7. 회차 수를 넘겨도 동작한다 (추천 엔진과 함께 쓴다) ===")
passed_through = solve_until_everyone_rides(
    build(), resolved_for(build()), S, trips_per_vehicle=3)
check("3회차로도 풀린다", not passed_through[0].unassigned_passengers)
check("원안이면 여전히 양보하지 않는다", not passed_through[1].applied)


print()
print("=== 8. 한 번 계산에 원장님을 오래 기다리게 하지 않는다 ===")
print("   여섯 칸을 모두 15초로 돌면 90초다. 다시 풀 때는 시간을 줄인다.")
from app.escalate import RETRY_TIME_LIMIT_SECONDS  # noqa: E402
check("다시 풀기 제한 시간이 원안보다 짧다",
      RETRY_TIME_LIMIT_SECONDS < get_settings().solver_time_limit_seconds,
      f"{RETRY_TIME_LIMIT_SECONDS}초 vs {get_settings().solver_time_limit_seconds}초")
worst = get_settings().solver_time_limit_seconds + RETRY_TIME_LIMIT_SECONDS * (len(LADDER) - 1)
check("최악의 경우도 60초를 넘지 않는다", worst <= 60, f"{worst}초")


print()
print("=== 9. 응답 모델에 그대로 실린다 ===")
from app.main import _relaxation_headline  # noqa: E402
from app.models import OptimizeResponse  # noqa: E402

check("응답에 relaxation 자리가 있다", "relaxation" in OptimizeResponse.model_fields)

result, relax = solve(build(window=("08:00", "08:05")))
line = _relaxation_headline(relax)
check("안내 문구가 만들어진다", bool(line), line)
check("전원 배차라고 먼저 말한다", line.startswith("전원 배차를 완료했습니다"), line[:20])
check("붉은 '누락' 표현이 없다", "누락" not in line and "실패" not in line, line)
check("실명이 들어 있다", any(i.name in line for i in relax.adjusted))
print()
print("   실제 문구:")
print("     " + line)

quiet = _relaxation_headline(solve(build())[1])
check("양보한 게 없으면 문구도 없다 (괜한 팝업을 띄우지 않는다)", quiet == "", quiet)


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
