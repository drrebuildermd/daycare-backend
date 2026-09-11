"""v4.3 검증: 무엇을 양보할지는 센터가 정한다.

v4.2 의 완화 사다리는 '이용시간(수가) 을 마지막에 양보한다' 를 코드에 박아
두었다. 하지만 그건 엔진의 철학이지 모든 센터의 철학이 아니다.

  · 어떤 센터는 수익보다 어르신이 차에 오래 계시는 것을 더 걱정한다
  · 어떤 센터는 보호자께 통보한 시각을 바꾸는 것을 가장 꺼린다

그래서 센터가 '마지막까지 지킬 것' 하나를 고르면, 엔진이 사다리를 다시
쌓는다. 고른 것은 다른 방법이 모두 바닥난 뒤에야 손댄다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_priority.py
"""
from app.config import get_settings
from app.escalate import (
    GRADES, LEVER_NOUN, PRIORITIES, PRIORITY_LABEL, SERVICE, TRANSIT, WINDOW,
    Adjustment, Relaxation, build_ladder, normalize_priority,
    solve_until_everyone_rides,
)
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


import app.escalate as escalate  # noqa: E402

S = get_settings().model_copy(update={"solver_time_limit_seconds": 3})
# 여기서 재는 것은 '어느 칸에서 멈추는가' 이지 솔버의 최적해가 아니다.
# 일곱 칸을 7초씩 돌면 한 번에 45초라 철학 셋 × 시나리오 둘이 5분을 넘는다.
escalate.RETRY_TIME_LIMIT_SECONDS = 2
CENTER = ResolvedLocation(name="행복센터", address="센터", latitude=37.500, longitude=127.000)
SPOTS = [
    ("김마중", 37.518, 127.000),
    ("이케어", 37.482, 127.000),
    ("박삼수", 37.500, 127.023),
    ("최복순", 37.500, 126.977),
    ("정영자", 37.514, 127.018),
]
# 센터에서 사방으로 5km 남짓. 한 바퀴 도는 데 50분으로는 모자란다.
SPREAD = [
    ("김마중", 37.545, 127.000),
    ("이케어", 37.455, 127.000),
    ("박삼수", 37.500, 127.057),
    ("최복순", 37.500, 126.943),
    ("정영자", 37.538, 127.045),
    ("한일만", 37.462, 126.955),
]


def _request(priority, people, window=None, transit=None):
    payload = {
        "trip_type": "inbound",
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": [{"id": "v1", "vehicle_type": "스타리아",
                      "plate_number": "00검0001", "capacity": 9}],
        "passengers": [
            {"id": f"pa{i}", "name": n, "address": "주소", "latitude": la, "longitude": lo,
             **({"pickup_start": window[0], "pickup_end": window[1]} if window else {})}
            for i, (n, la, lo) in enumerate(people, start=1)
        ],
    }
    if transit:
        payload["max_transit_minutes"] = transit
    if priority:
        payload["dispatch_priority"] = priority
    return OptimizeRequest.model_validate(payload)


def spread(priority=None):
    """흩어진 여섯 분 · 탑승 상한 50분. 세 방법 중 아무거나로 풀린다."""
    return _request(priority, SPREAD, transit=50)


def tight(priority=None):
    """다섯 분이 5분 창 안에. 시각을 넓히는 것 말고는 길이 없다."""
    return _request(priority, SPOTS, window=("08:00", "08:05"))


def build(priority=None, window=("08:00", "08:05")):
    return _request(priority, SPOTS, window=window)


def resolved_for(request):
    return [CENTER] + [
        ResolvedLocation(name=p.name, address=p.address,
                         latitude=p.latitude, longitude=p.longitude)
        for p in request.passengers
    ]


# ---------------------------------------------------------------------------
print("=== 1. 세 철학이 각자 지키겠다고 한 것을 정말로 맨 뒤에 두는가 ===")
print("   이게 무너지면 드롭다운은 있으나 마나다.")

for key, order in PRIORITIES.items():
    protected = order[-1]
    ladder = build_ladder(key)
    print()
    print(f"   [{PRIORITY_LABEL[key]}] — 지키는 것: {LEVER_NOUN[protected]}")

    check(f"{key}: 첫 칸은 원안", ladder[0].is_original, ladder[0].describe())
    check(f"{key}: 일곱 칸", len(ladder) == 7, len(ladder))

    # 지키기로 한 것에 처음 손대는 칸
    first_touch = next(i for i, s in enumerate(ladder) if s.value_of(protected))
    # 나머지 둘에 손대는 마지막 칸
    others = [lever for lever in order[:-1]]
    last_other = max(
        max(i for i, s in enumerate(ladder) if s.value_of(lever)) for lever in others
    )
    first_other = min(
        next(i for i, s in enumerate(ladder) if s.value_of(lever)) for lever in others
    )
    check(f"{key}: 다른 둘을 먼저 건드린다", first_other < first_touch,
          f"다른 것 {first_other}번째 · 지킬 것 {first_touch}번째")

    # 지키기로 한 것에 손대는 순간, 나머지 둘은 이미 한계까지 가 있어야 한다.
    at_touch = ladder[first_touch]
    for lever in others:
        check(f"{key}: {LEVER_NOUN[lever]} 은(는) 그 전에 한계까지 썼다",
              at_touch.value_of(lever) == GRADES[lever][-1],
              f"{at_touch.value_of(lever)} / 한계 {GRADES[lever][-1]}")

    # 모든 칸에서 값은 줄지 않는다. 줄면 이미 시도한 조합으로 되돌아가는 셈이다.
    for lever in (WINDOW, TRANSIT, SERVICE):
        series = [s.value_of(lever) for s in ladder]
        check(f"{key}: {LEVER_NOUN[lever]} 값이 되돌아가지 않는다",
              series == sorted(series), series)

    for i, step in enumerate(ladder, 1):
        print(f"     {i}. {step.describe()}")


print()
print("=== 2. 같은 상황을 철학에 따라 다르게 푼다 (핵심) ===")
print("   여섯 분이 흩어져 있고 한 회차 탑승 시간 상한이 50분이라 원안으로는")
print("   태울 수 없다. 이 상황은 시각을 넓혀도, 탑승을 늘려도, 이용시간을")
print("   줄여도 풀린다. 그래서 무엇을 내주는지가 철학에 따라 갈린다.")

outcomes = {}
for key in PRIORITIES:
    request = spread(key)
    result, relax = solve_until_everyone_rides(request, resolved_for(request), S)
    outcomes[key] = relax
    print()
    print(f"   [{PRIORITY_LABEL[key]}] — 지키려던 것: {LEVER_NOUN[relax.protected]}")
    print(f"     누락 {len(result.unassigned_passengers)}명 · {relax.steps_tried}칸")
    print(f"     양보: {relax.label or '없음'}")
    check(f"{key}: 전원 배차됐다", not result.unassigned_passengers,
          [i.name for i in result.unassigned_passengers])
    check(f"{key}: 고른 철학이 그대로 기록된다", relax.priority == key, relax.priority)
    check(f"{key}: 지킨 것이 기록된다",
          relax.protected == PRIORITIES[key][-1], relax.protected)

revenue, comfort, promise = (outcomes[k] for k in ("revenue", "comfort", "promise"))

print()
check("수익 최우선은 이용시간을 지켜 냈다 (수가 손실 0)",
      revenue.service_cut_minutes == 0, revenue.service_cut_minutes)
check("보호자 약속 최우선은 픽업 시각을 지켜 냈다",
      promise.window_slack_minutes == 0, promise.window_slack_minutes)
# 창을 안 넓혔어도 이용시간을 줄이면 도착 마지노선이 밀려 픽업 시각이
# 따라 움직인다. 그런 경우는 '지켰다' 가 아니라 '못 지켰다' 로 잡혀야 한다.
check("실제로 밀린 분이 있으면 약속을 지켰다고 하지 않는다",
      promise.protected_conceded == bool(promise.adjusted),
      f"conceded={promise.protected_conceded} · 밀린 분 {len(promise.adjusted)}명")
check("수익 최우선과 보호자 약속 최우선의 결과가 실제로 다르다",
      revenue.label != promise.label, f"{revenue.label}  vs  {promise.label}")
check("보호자 약속 최우선은 대신 다른 것을 내줬다",
      promise.transit_extra_minutes > 0 or promise.service_cut_minutes > 0,
      promise.label)
check("수익 최우선은 대신 시각을 내줬다",
      revenue.window_slack_minutes > 0, revenue.window_slack_minutes)


print()
print("=== 3. 지킨 것을 지켰다고만 말하는가 (거짓말 방지) ===")
print("   끝내 손댔으면서 '지켰습니다' 라고 하면 원장님을 속이는 것이다.")

for key, relax in outcomes.items():
    actual = {
        WINDOW: relax.window_slack_minutes,
        TRANSIT: relax.transit_extra_minutes,
        SERVICE: relax.service_cut_minutes,
    }[relax.protected]
    # 픽업 시각만은 '지렛대를 썼는가' 가 아니라 '실제로 밀렸는가' 로 본다.
    expected = (actual > 0) or (relax.protected == WINDOW and bool(relax.adjusted))
    check(f"{key}: protected_conceded 가 실제와 맞는다",
          relax.protected_conceded == expected,
          f"{relax.protected_conceded} / 지렛대 {actual}분 · 밀린 분 {len(relax.adjusted)}명")

check("수익 최우선은 계획 이용시간을 지켜 냈다고 기록된다",
      not revenue.protected_conceded)
# 어르신 편의 최우선은 이 판에서 탑승 시간까지 내줘야 풀렸다.
# 그걸 지켰다고 우기지 않는 것이 이 필드의 존재 이유다.
check("어르신 편의 최우선은 끝내 탑승 시간을 내줬다고 솔직히 기록된다",
      comfort.protected_conceded, comfort.label)


print()
print("=== 4. 안내 문구가 철학을 설명하는가 ===")

print()
print("   [수익 최우선] — 지켜 낸 경우")
line = revenue.headline
print("     " + line)
check("전원 배차라고 먼저 말한다", line.startswith("전원 배차를 완료했습니다"), line[:20])
check("고른 목표 이름이 들어 있다", PRIORITY_LABEL["revenue"] in line)
check("무엇을 지켰는지 말한다", "계획 이용시간을 줄이지 않는 대신" in line, line)
check("붉은 '누락/실패' 표현이 없다", "누락" not in line and "실패" not in line)

print()
print("   [보호자 약속 최우선] — 아무도 안 밀렸어도 무엇을 내줬는지는 말해야 한다")
line = promise.headline
print("     " + line)
check("양보한 게 있으면 문구가 나온다", bool(line), line)
check("대신 무엇을 내줬는지 말한다",
      "탑승 시간 한도를" in line or "계획 이용시간을" in line, line)
if promise.adjusted:
    check("밀린 분이 있으면 지켰다고 하지 않는다",
          "건드리지 않는 대신" not in line, line)
    check("밀린 분 실명을 밝힌다", any(i.name in line for i in promise.adjusted))
else:
    check("픽업 시각을 지켰다고 말한다", "픽업 시각을 건드리지 않는 대신" in line, line)
    check("아무도 안 밀렸으므로 실명을 지어내지 않는다", "어르신의" not in line, line)

print()
print("   [어르신 편의 최우선] — 끝내 내준 경우")
line = comfort.headline
print("     " + line)
check("지켰다고 말하지 않는다", "늘리지 않는 대신" not in line, line)
check("아꼈지만 안 됐다고 말한다", "끝까지 아꼈지만" in line, line)


print()
print("=== 4-1. 지킬 것이 유일한 해법이면 그것도 내주고 솔직히 말한다 ===")
print("   다섯 분이 08:00~08:05 5분 안에 다 타실 수는 없다. 정차만 15분이다.")
print("   이 판은 시각을 넓히는 것 말고는 길이 없다. 약속을 지킬 수가 없다.")

request = tight("promise")
result, relax = solve_until_everyone_rides(request, resolved_for(request), S)
check("그래도 전원 배차한다 (어르신을 길에 두지 않는다)",
      not result.unassigned_passengers, len(result.unassigned_passengers))
check("다른 방법을 모두 써 본 뒤였다", relax.steps_tried >= 6, relax.steps_tried)
check("끝내 시각을 내줬다고 기록된다", relax.protected_conceded, relax.label)
line = relax.headline
print("     " + line)
check("'지켰습니다' 라고 하지 않는다", "건드리지 않는 대신" not in line, line)
check("끝까지 아꼈다고 말한다", "픽업 시각을 끝까지 아꼈지만" in line, line)
check("밀린 분 실명을 밝힌다", any(i.name in line for i in relax.adjusted))


print("=== 5. 끝까지 손댄 경우의 문구 ===")
print("   '아꼈지만 그것만으로는 안 됐다' 고 솔직하게 말해야 한다.")

honest = Relaxation(
    applied=True, steps_tried=7,
    window_slack_minutes=60, transit_extra_minutes=40, service_cut_minutes=60,
    priority="comfort", protected=TRANSIT, protected_conceded=True,
    adjusted=[Adjustment("pa1", "김마중", "07:30~08:45", "09:20", 35, True)],
)
line = honest.headline
print("     " + line)
check("지켰다고 말하지 않는다", "늘리지 않는 대신" not in line, line)
check("아꼈지만 안 됐다고 말한다", "끝까지 아꼈지만" in line, line)
check("탑승 시간 연장을 숨기지 않는다", "탑승 시간 한도를 40분 연장" in line, line)
check("이용시간 단축도 숨기지 않는다", "계획 이용시간을 60분 단축" in line, line)


print()
print("=== 6. 구형 앱과 잘못된 값이 배차를 막지 않는다 ===")
print("   드롭다운이 없던 버전의 앱도 계속 써야 한다.")

check("아무것도 안 보내면 수익 최우선", normalize_priority(None) == "revenue")
check("빈 문자열도 수익 최우선", normalize_priority("") == "revenue")
check("모르는 값도 수익 최우선", normalize_priority("김밥") == "revenue")
check("아는 값은 그대로", normalize_priority("comfort") == "comfort")

old_app = spread(priority=None)
check("구형 요청에는 dispatch_priority 가 없다", old_app.dispatch_priority is None,
      old_app.dispatch_priority)
result, relax = solve_until_everyone_rides(old_app, resolved_for(old_app), S)
check("구형 요청도 전원 배차된다", not result.unassigned_passengers)
check("구형 요청은 v4.2 와 같은 철학으로 푼다", relax.priority == "revenue", relax.priority)
# 같은 판을 수익 최우선으로 푼 것과 글자 하나까지 같아야 한다.
check("결과도 수익 최우선과 똑같다", relax.label == revenue.label,
      f"{relax.label} vs {revenue.label}")


print()
print("=== 7. 원안으로 풀리면 철학과 무관하게 아무것도 안 건드린다 ===")
print("   멀쩡한 배차는 어떤 철학을 골라도 달라지면 안 된다.")

labels = set()
for key in PRIORITIES:
    request = build(key, window=None)
    result, relax = solve_until_everyone_rides(request, resolved_for(request), S)
    check(f"{key}: 양보하지 않았다", not relax.applied, relax.label)
    check(f"{key}: 첫 칸에서 끝났다", relax.steps_tried == 1, relax.steps_tried)
    check(f"{key}: 안내 문구가 없다 (괜한 팝업을 띄우지 않는다)", relax.headline == "")
    labels.add(result.total_distance_km)
check("세 철학의 결과가 똑같다", len(labels) == 1, labels)


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
