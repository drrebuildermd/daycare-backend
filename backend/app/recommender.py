"""배차가 안 된 이유를 넘어, 어떻게 하면 되는지를 계산한다.

왜 필요한가
    "휠체어석이 부족해서 3명 누락" 까지만 말하면 원장님은 그래서 무엇을 해야
    하는지 알 수 없다. 시간을 조절하면 되는 일인지, 한 회차를 더 돌면 되는
    일인지, 차를 더 사야 하는 일인지는 전혀 다른 결정이다.

어떻게 찾는가
    조건을 하나씩 풀어 주며 다시 풀어 본다. 싼 것부터 시도해서 가장 먼저
    통하는 것을 답으로 삼는다.

      0단계  산수      (0초)   용량이 절대적으로 모자라면 여기서 끝난다
      1단계  시간 완화 (~4초)  빠진 분의 희망 시각만 ±30분, 안 되면 ±60분
      2단계  회차 추가 (~2초)  원래 시간 그대로, 3회차까지 허용
      3단계  구조적 한계       무엇이 얼마나 모자란지 숫자로

    0단계가 중요하다. 휠체어 이용 5명인데 고정석이 총 1자리라면 시간을 아무리
    넓혀도 답이 없다. 이건 산수로 즉시 알 수 있고, 그때 솔버를 세 번 돌리는
    것은 45초를 버리는 일이다.

비용
    완화 패스는 '되는가' 만 알면 되고 최적해까지 필요하지 않다. 그래서 제한
    시간을 2초로 낮춘다. 최악의 경우에도 6초 안에 끝난다.
"""
import time

from .config import Settings
from .geocoding import ResolvedLocation
from .finance import build_scenarios
from .models import (
    FinancialComparison,
    OptimizeRequest,
    RecommendationAction,
    RecommendationOption,
    RecommendationReport,
    RevenueLossEntry,
    ScenarioCostView,

    VehicleInput,
    format_hhmm,
    parse_hhmm,
)
from .optimizer import DEFAULT_TRIPS_PER_VEHICLE, optimize_routes

# 완화 패스의 솔버 제한 시간. 최적해가 아니라 실현 가능성만 보면 된다.
RELAXATION_TIME_LIMIT_SECONDS = 2

# 시간 완화 폭. 싼 것부터 본다.
TIME_RELAXATION_STEPS_MINUTES = (30, 60)

# 회차를 어디까지 늘려 볼 것인가. 기사님 근무를 생각하면 3이 현실적인 한계다.
MAX_TRIPS_PER_VEHICLE = 3

DAY_START = 0
DAY_END = 24 * 60 - 1

def _relaxed_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"solver_time_limit_seconds": RELAXATION_TIME_LIMIT_SECONDS}
    )

def _window_fields(trip_type: str) -> tuple[str, str]:
    """이 방향에서 실제로 쓰는 시각 칸 이름."""
    if trip_type == "outbound":
        return "dropoff_start", "dropoff_end"
    return "pickup_start", "pickup_end"

def _assigned_ids(result) -> set[str]:
    return {
        stop.passenger_id
        for vehicle in result.vehicles
        for trip in vehicle.trips
        if trip.used
        for stop in trip.stops
    }

def _scheduled_times(result) -> dict[str, str]:
    return {
        stop.passenger_id: stop.estimated_pickup
        for vehicle in result.vehicles
        for trip in vehicle.trips
        if trip.used
        for stop in trip.stops
    }

# ---------------------------------------------------------------------------
# 0단계 — 산수
# ---------------------------------------------------------------------------

def _capacity_check(request: OptimizeRequest) -> dict:
    """솔버를 부르기 전에 용량이 애초에 되는지 센다.

    회차를 최대로 돌린다고 쳐도 모자라면 시간을 넓혀 봐야 소용없다.
    """
    riders = len(request.passengers)
    wheelchair_riders = sum(1 for p in request.passengers if p.wheelchair)

    seats = sum(v.capacity for v in request.vehicles)
    wheelchair_seats = sum(v.wheelchair_capacity for v in request.vehicles)

    return {
        "riders": riders,
        "wheelchair_riders": wheelchair_riders,
        "seats": seats,
        "wheelchair_seats": wheelchair_seats,
        # 최대 회차까지 돌렸을 때 실을 수 있는 총량
        "max_seat_slots": seats * MAX_TRIPS_PER_VEHICLE,
        "max_wheelchair_slots": wheelchair_seats * MAX_TRIPS_PER_VEHICLE,
        "seat_shortfall": max(0, riders - seats * MAX_TRIPS_PER_VEHICLE),
        "wheelchair_shortfall": max(
            0, wheelchair_riders - wheelchair_seats * MAX_TRIPS_PER_VEHICLE
        ),
    }

def _structural_option(numbers: dict, priority: int) -> RecommendationOption:
    """무엇이 얼마나 모자란지 숫자로 말한다."""
    lines: list[str] = []
    shortfall = 0

    if numbers["wheelchair_shortfall"]:
        shortfall += numbers["wheelchair_shortfall"]
        if numbers["wheelchair_seats"] == 0:
            lines.append(
                f"휠체어 이용 {numbers['wheelchair_riders']}명인데 고정석이 있는 "
                "차량이 한 대도 없습니다."
            )
        else:
            lines.append(
                f"휠체어 이용 {numbers['wheelchair_riders']}명인데 고정석 "
                f"{numbers['wheelchair_seats']}자리로 {MAX_TRIPS_PER_VEHICLE}회차까지 "
                f"돌아도 {numbers['max_wheelchair_slots']}명이 한계입니다. "
                f"{numbers['wheelchair_shortfall']}명이 남습니다."
            )

    if numbers["seat_shortfall"]:
        shortfall += numbers["seat_shortfall"]
        lines.append(
            f"전체 {numbers['riders']}명인데 좌석 {numbers['seats']}석으로 "
            f"{MAX_TRIPS_PER_VEHICLE}회차까지 돌아도 {numbers['max_seat_slots']}명이 "
            f"한계입니다. {numbers['seat_shortfall']}명이 남습니다."
        )

    if not lines:
        # 산수로는 되는데 실제로 안 풀린 경우. 시간이나 거리 때문이다.
        lines.append(
            "정원은 모자라지 않지만 희망 시각을 지키면서 도는 방법을 찾지 못했습니다."
        )

    detail = " ".join(lines)
    if shortfall:
        detail += (
            f" 리프트 차량 증차나 외부 콜택시 이용을 검토해 주세요."
            if numbers["wheelchair_shortfall"]
            else " 차량 증차나 외부 콜택시 이용을 검토해 주세요."
        )

    return RecommendationOption(
        priority=priority,
        kind="structural",
        feasible=False,
        headline=(
            f"차량이 절대적으로 부족합니다 ({shortfall}명분)"
            if shortfall
            else "시간과 회차를 조절해도 배차되지 않습니다"
        ),
        detail=detail,
        resolves_count=0,
    )

# ---------------------------------------------------------------------------
# 1단계 — 시간 완화
# ---------------------------------------------------------------------------

def _widen(request: OptimizeRequest, target_ids: set[str], minutes: int) -> OptimizeRequest:
    """빠진 분의 희망 시각만 앞뒤로 넓힌다.

    전원을 넓히면 '누구 시간을 조절하면 되는지' 를 말해 줄 수 없다.
    빠진 분만 건드려야 조치가 구체적이 된다.
    """
    start_field, end_field = _window_fields(request.trip_type)
    widened = []
    for passenger in request.passengers:
        if passenger.id not in target_ids:
            widened.append(passenger)
            continue

        start_value = getattr(passenger, start_field, None)
        end_value = getattr(passenger, end_field, None)
        # 하원 시각을 비워 두신 분은 서버가 등원 시각 + 8시간으로 채운다.
        # 그런 분은 픽업 칸을 넓혀도 소용없으므로 건드리지 않는다.
        if not start_value or not end_value:
            widened.append(passenger)
            continue

        low = max(DAY_START, parse_hhmm(start_value) - minutes)
        high = min(DAY_END, parse_hhmm(end_value) + minutes)
        widened.append(passenger.model_copy(update={
            start_field: format_hhmm(low),
            end_field: format_hhmm(high),
        }))

    return request.model_copy(update={"passengers": widened})

def _time_option(
    request: OptimizeRequest,
    relaxed_request: OptimizeRequest,
    result,
    target_ids: set[str],
    minutes: int,
    priority: int,
) -> RecommendationOption:
    start_field, end_field = _window_fields(request.trip_type)
    original = {p.id: p for p in request.passengers}
    scheduled = _scheduled_times(result)
    now_assigned = _assigned_ids(result) & target_ids

    actions = []
    for passenger in relaxed_request.passengers:
        if passenger.id not in now_assigned:
            continue
        before = original[passenger.id]
        before_start = getattr(before, start_field, None)
        before_end = getattr(before, end_field, None)
        if not before_start or not before_end:
            continue
        actions.append(RecommendationAction(
            passenger_id=passenger.id,
            name=before.name,
            current_window=f"{before_start}~{before_end}",
            suggested_window=(
                f"{getattr(passenger, start_field)}~{getattr(passenger, end_field)}"
            ),
            delta_minutes=minutes,
            scheduled_time=scheduled.get(passenger.id),
        ))

    return RecommendationOption(
        priority=priority,
        kind="adjust_time",
        feasible=True,
        headline=(
            f"{len(actions)}분의 희망 시각을 앞뒤로 {minutes}분씩 넓히면 "
            "배차됩니다"
        ),
        detail=(
            "빠진 분의 시각만 넓혀 본 결과입니다. 다른 어르신의 시각은 그대로입니다."
        ),
        actions=actions,
        resolves_count=len(actions),
    )

# ---------------------------------------------------------------------------
# 본체
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 재무 비교 (v4.0)
# ---------------------------------------------------------------------------

def _center_times(result, trip_type: str) -> dict[str, int]:
    """어르신마다 센터에 있는 시간이 언제 끝나는가(분).

    하원이면 그분을 태운 차가 센터를 떠나는 시각이다. 그때 센터를 나선다.
    등원이면 그분을 태운 차가 센터에 도착하는 시각이다. 그때부터 머무신다.
    """
    times: dict[str, int] = {}
    for vehicle in result.vehicles:
        for trip in vehicle.trips:
            if not trip.used:
                continue
            stamp = trip.departure_time if trip_type == "outbound" else trip.return_time
            if not stamp:
                continue
            minutes = parse_hhmm(stamp)
            for stop in trip.stops:
                if stop.passenger_id:
                    times[stop.passenger_id] = minutes
    return times

def _lost_hours(plan_a, plan_b, trip_type: str) -> dict[str, float]:
    """A안을 고르면 어르신마다 이용시간이 몇 시간 줄어드는가.

    ⚠️ 지금은 이 값이 거의 항상 비어 있다. 알고 있는 한계다.

    현장에서 3회차가 비싼 이유는 '기사님 퇴근 시각 안에 세 번을 우겨넣으려면
    1회차를 훨씬 일찍 보내야 하기 때문' 이다. 그런데 이 엔진에는 퇴근 시각이라는
    제약이 없다. 솔버는 거리와 소요시간만 줄이므로 3회차를 허용해도 앞으로
    당기는 대신 저녁까지 늘어뜨린다. 압축이 일어나지 않으니 조기 하원도 없다.

    실제로 6명/2석 판에서 재보면 A안(3회차)은 13:47~14:39 에 내보내는데
    B안(증차)은 12:57 에 전원을 내보낸다. 오히려 B안이 더 이르다.

    이 항이 제대로 돌려면 운행 종료 시각(settings.operation_end_time 같은 것)이
    제약으로 들어가야 한다. 그전까지 재무 비교는 유류비와 렌트비만으로 판정한다.
    그 판정도 틀린 것은 아니지만 수가 항이 늘 0원이라는 점을 알고 봐야 한다.

    두 안을 같은 자로 재야 의미가 있다. '계획보다 얼마나 이른가' 는 계획을
    무엇으로 잡느냐에 따라 답이 달라지지만, 'B안 대신 A안을 고르면 얼마나
    손해인가' 는 두 결과를 직접 비교하면 되므로 흔들리지 않는다.

    하원은 더 일찍 떠나면 손해, 등원은 더 늦게 도착하면 손해다.
    """
    a_times = _center_times(plan_a, trip_type)
    b_times = _center_times(plan_b, trip_type)

    lost: dict[str, float] = {}
    for passenger_id, a_minutes in a_times.items():
        b_minutes = b_times.get(passenger_id)
        if b_minutes is None:
            continue
        gap = (b_minutes - a_minutes) if trip_type == "outbound" else (a_minutes - b_minutes)
        if gap > 0:
            lost[passenger_id] = gap / 60.0
    return lost

def _with_spare_vehicle(request: OptimizeRequest, settings: Settings) -> OptimizeRequest:
    """차를 한 대 빌렸다고 치고 명단에 끼워 넣는다.

    부족한 것이 휠체어석인데 리프트 없는 차를 넣으면 B안이 성립하지 않는다.
    그래서 표준 증차 차량에는 고정석이 최소 한 자리 있다.
    """
    spare = VehicleInput(
        id="__spare__",
        vehicle_type="증차 검토 차량",
        plate_number="증차검토",
        capacity=settings.spare_vehicle_capacity,
        wheelchair_capacity=settings.spare_vehicle_wheelchair_capacity,
    )
    return request.model_copy(update={"vehicles": [*request.vehicles, spare]})

def _as_view(cost) -> ScenarioCostView:
    return ScenarioCostView(
        label=cost.label,
        distance_km=cost.distance_km,
        fuel_won=cost.fuel_won,
        fixed_won=cost.fixed_won,
        revenue_loss_won=cost.revenue_loss_won,
        total_won=cost.total_won,
        revenue_loss_items=[
            RevenueLossEntry(
                passenger_id=item.passenger_id,
                name=item.name,
                care_grade=item.care_grade,
                planned_hours=item.planned_hours,
                actual_hours=item.actual_hours,
                planned_band=item.planned_band,
                actual_band=item.actual_band,
                lost_won=item.lost_won,
            )
            for item in cost.revenue_loss_items
        ],
    )

def _compare_money(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    plan_a,
    targets: set[str],
    consider_revenue_loss: bool,
) -> FinancialComparison | None:
    """3회차로 버티는 것과 차를 한 대 늘리는 것 중 어느 쪽이 싼지 계산한다.

    plan_a 는 이미 풀어 둔 3회차 결과다. 여기서는 증차안만 한 번 더 푼다.
    """
    relaxed = _relaxed_settings(settings)
    try:
        plan_b = optimize_routes(
            _with_spare_vehicle(request, settings), resolved, relaxed
        )
    except Exception:  # noqa: BLE001 - 재무 비교 실패가 대안 제시를 막으면 안 된다
        return None

    # 차를 늘려도 못 태우면 비교 자체가 성립하지 않는다.
    if not targets <= _assigned_ids(plan_b):
        return None

    cost_a, cost_b, notes = build_scenarios(
        label_a=f"기존 차량 {MAX_TRIPS_PER_VEHICLE}회차",
        distance_a_km=plan_a.total_distance_km,
        early_departures=_lost_hours(plan_a, plan_b, request.trip_type),
        passengers=request.passengers,
        label_b="1대 증차 · 2회차 여유",
        distance_b_km=plan_b.total_distance_km,
        settings=settings,
        consider_revenue_loss=consider_revenue_loss,
    )

    view_a, view_b = _as_view(cost_a), _as_view(cost_b)
    difference = abs(view_a.total_won - view_b.total_won)

    # 수가표에 없는 조합이 있었다면 A안 금액을 믿을 수 없다. 판정을 미룬다.
    incomplete = any("표에 없습니다" in note for note in notes)
    if incomplete:
        recommended = None
        headline = (
            "수가표에 없는 등급·구간이 있어 어느 쪽이 이득인지 판정을 보류했습니다. "
            "아래 금액은 확인된 항목만 더한 것입니다."
        )
    elif view_a.total_won <= view_b.total_won:
        recommended = "add_round"
        headline = (
            f"{MAX_TRIPS_PER_VEHICLE}회차 운영이 하루 {difference:,}원 유리합니다"
            f" (월 약 {difference * 22 // 10000}만원)"
            if difference
            else f"두 방식의 하루 비용이 같습니다"
        )
    else:
        recommended = "add_vehicle"
        headline = (
            f"증차가 하루 {difference:,}원 유리합니다"
            f" (월 약 {difference * 22 // 10000}만원)"
        )

    # 손실이 어디서 나는지 짚어 준다. 원장님이 "그럼 그 분만 옮기면?" 을
    # 바로 판단하실 수 있어야 한다.
    hit = len(view_a.revenue_loss_items)
    if consider_revenue_loss and hit:
        safe = len(_center_times(plan_a, request.trip_type)) - hit
        names = ", ".join(item.name for item in view_a.revenue_loss_items[:3])
        more = f" 외 {hit - 3}분" if hit > 3 else ""
        notes.append(
            f"수가 감소는 {hit}분({names}{more})에게서 발생하며, "
            f"나머지 {safe}분은 구간 여유가 있어 손실이 없습니다."
        )

    return FinancialComparison(
        consider_revenue_loss=consider_revenue_loss,
        scenario_a=view_a,
        scenario_b=view_b,
        recommended=recommended,
        difference_won=difference,
        headline=headline,
        notes=notes,
    )

def analyze(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    unassigned_ids: list[str],
    optimization_run_id: str | None = None,
    consider_revenue_loss: bool = True,
) -> RecommendationReport:
    """빠진 분을 어떻게 하면 태울 수 있는지 찾는다.

    싼 것부터 시도하고, 처음으로 통하는 것을 답으로 삼는다.
    """
    started = time.perf_counter()
    targets = {pid for pid in unassigned_ids if pid}

    if not targets:
        return RecommendationReport(
            verdict="all_assigned",
            unassigned_count=0,
            analyzed_seconds=round(time.perf_counter() - started, 3),
            optimization_run_id=optimization_run_id,
        )

    relaxed = _relaxed_settings(settings)
    options: list[RecommendationOption] = []

    # ── 0단계: 산수 ────────────────────────────────────────────
    numbers = _capacity_check(request)
    if numbers["seat_shortfall"] or numbers["wheelchair_shortfall"]:
        # 회차를 최대로 돌려도 모자란다. 풀어 볼 필요가 없다.
        options.append(_structural_option(numbers, priority=1))
        return RecommendationReport(
            verdict="structural",
            unassigned_count=len(targets),
            options=options,
            analyzed_seconds=round(time.perf_counter() - started, 3),
            optimization_run_id=optimization_run_id,
        )

    # ── 1단계: 시간 완화 ───────────────────────────────────────
    for minutes in TIME_RELAXATION_STEPS_MINUTES:
        candidate = _widen(request, targets, minutes)
        try:
            trial = optimize_routes(candidate, resolved, relaxed)
        except Exception:  # noqa: BLE001 - 분석 실패가 배차를 무효화하면 안 된다
            break
        if targets <= _assigned_ids(trial):
            options.append(
                _time_option(request, candidate, trial, targets, minutes, priority=1)
            )
            return RecommendationReport(
                verdict="time_relaxable",
                unassigned_count=len(targets),
                options=options,
                analyzed_seconds=round(time.perf_counter() - started, 3),
                optimization_run_id=optimization_run_id,
            )

    options.append(RecommendationOption(
        priority=1, kind="adjust_time", feasible=False,
        headline=(
            f"희망 시각을 앞뒤로 {TIME_RELAXATION_STEPS_MINUTES[-1]}분까지 "
            "넓혀도 배차되지 않습니다"
        ),
    ))

    # ── 2단계: 회차 추가 ───────────────────────────────────────
    try:
        trial = optimize_routes(
            request, resolved, relaxed, trips_per_vehicle=MAX_TRIPS_PER_VEHICLE
        )
    except Exception:  # noqa: BLE001
        trial = None

    if trial is not None and targets <= _assigned_ids(trial):
        extra = sorted({
            vehicle.plate_number
            for vehicle in trial.vehicles
            for trip in vehicle.trips
            if trip.used and trip.round > DEFAULT_TRIPS_PER_VEHICLE
        })
        plates = ", ".join(extra) if extra else "일부 차량"
        options.append(RecommendationOption(
            priority=2, kind="add_round", feasible=True,
            headline=f"{plates} 차량을 {MAX_TRIPS_PER_VEHICLE}회차까지 운행하면 전원 수용됩니다",
            detail=(
                "희망 시각은 그대로 두고 회차만 늘린 결과입니다. "
                "기사님 근무 시간이 늘어나므로 협의가 필요합니다."
            ),
            resolves_count=len(targets),
        ))
        # 3회차가 가능하다는 것만으로는 부족하다. 그게 이득인지 손해인지
        # 답해야 원장님이 결정하실 수 있다.
        financials = _compare_money(
            request, resolved, settings, trial, targets, consider_revenue_loss
        )
        return RecommendationReport(
            verdict="needs_extra_round",
            unassigned_count=len(targets),
            options=options,
            analyzed_seconds=round(time.perf_counter() - started, 3),
            optimization_run_id=optimization_run_id,
            financials=financials,
        )

    options.append(RecommendationOption(
        priority=2, kind="add_round", feasible=False,
        headline=f"{MAX_TRIPS_PER_VEHICLE}회차까지 늘려도 배차되지 않습니다",
    ))

    # ── 3단계: 구조적 한계 ─────────────────────────────────────
    options.append(_structural_option(numbers, priority=3))
    return RecommendationReport(
        verdict="structural",
        unassigned_count=len(targets),
        options=options,
        analyzed_seconds=round(time.perf_counter() - started, 3),
        optimization_run_id=optimization_run_id,
    )
