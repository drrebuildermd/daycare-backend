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
from .models import (
    OptimizeRequest,
    RecommendationAction,
    RecommendationOption,
    RecommendationReport,
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


def analyze(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    unassigned_ids: list[str],
    optimization_run_id: str | None = None,
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
        return RecommendationReport(
            verdict="needs_extra_round",
            unassigned_count=len(targets),
            options=options,
            analyzed_seconds=round(time.perf_counter() - started, 3),
            optimization_run_id=optimization_run_id,
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
