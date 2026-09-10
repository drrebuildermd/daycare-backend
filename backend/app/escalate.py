"""어르신을 길에 두지 않는다.

현장에서는 '시간이 안 맞아서 못 태웠습니다' 라는 배차표를 쓸 수 없다.
그런 표를 받아 든 원장님은 결국 손으로 다시 짜야 하고, 그럴 거면 엔진이
있을 이유가 없다.

그래서 제약에 막히면 포기하지 않고 스스로 조금씩 풀어 가며 다시 푼다.
싼 것부터 푼다. 덜 아픈 것부터 양보한다는 뜻이다.

  1. 원안 그대로                       아무것도 양보하지 않는다
  2. 희망 시각 ±30분                   어르신이 조금 일찍/늦게 타신다
  3. 희망 시각 ±60분                   더 많이 움직인다
  4. ±60분 + 탑승 시간 +20분            차에 조금 더 오래 계신다
  5. ±60분 + 탑승 +40분 + 이용시간 -30분  센터에 머무는 시간이 준다
  6. ±60분 + 탑승 +40분 + 이용시간 -60분  8시간이 7시간이 된다

이용시간을 줄이는 것을 맨 뒤에 두는 이유는 그것이 수가로 직결되기 때문이다.
구간이 내려가면 그날 매출이 준다. 다른 모든 방법을 써 본 뒤에 손대야 한다.

무엇을 양보했는지는 반드시 남긴다. 조용히 시간을 바꿔 놓고 성공했다고만
하면, 원장님이 보호자에게 잘못된 시각을 통보하시게 된다.
"""
import time
from dataclasses import dataclass, field

from .config import Settings
from .geocoding import ResolvedLocation
from .models import OptimizeRequest, OptimizeResponse, format_hhmm, parse_hhmm
from .optimizer import optimize_routes, resolve_window


@dataclass(frozen=True)
class Step:
    """완화 한 단계."""

    window_slack: int = 0
    transit_extra: int = 0
    service_cut: int = 0

    @property
    def is_original(self) -> bool:
        return not (self.window_slack or self.transit_extra or self.service_cut)

    def describe(self) -> str:
        parts = []
        if self.window_slack:
            parts.append(f"희망 시각 ±{self.window_slack}분")
        if self.transit_extra:
            parts.append(f"탑승 시간 +{self.transit_extra}분")
        if self.service_cut:
            parts.append(f"이용시간 -{self.service_cut}분")
        return " · ".join(parts) if parts else "원안"


LADDER: tuple[Step, ...] = (
    Step(),
    Step(window_slack=30),
    Step(window_slack=60),
    Step(window_slack=60, transit_extra=20),
    Step(window_slack=60, transit_extra=40, service_cut=30),
    Step(window_slack=60, transit_extra=40, service_cut=60),
)

# 다시 풀 때는 '되는가' 만 알면 된다. 최적해까지 필요하지 않아 시간을 줄인다.
# 여섯 단계를 모두 15초로 돌면 90초가 걸려 원장님이 화면 앞에서 기다리신다.
RETRY_TIME_LIMIT_SECONDS = 8


@dataclass
class Adjustment:
    """당초 계획보다 시각이 밀린 어르신 한 분."""

    passenger_id: str
    name: str
    planned_window: str
    actual_time: str
    shift_minutes: int
    # 늦어진 것인가. 등원이 늦어지면 그만큼 그날 이용시간이 줄어든다.
    # 구간이 내려가면 수가가 준다. 빨라진 것과 무게가 다르다.
    late: bool = False


@dataclass
class Relaxation:
    """무엇을 얼마나 양보해서 전원 배차를 만들었는가."""

    applied: bool = False
    steps_tried: int = 1
    window_slack_minutes: int = 0
    transit_extra_minutes: int = 0
    service_cut_minutes: int = 0
    adjusted: list[Adjustment] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def label(self) -> str:
        parts = []
        if self.window_slack_minutes:
            parts.append(f"희망 시각 ±{self.window_slack_minutes}분")
        if self.transit_extra_minutes:
            parts.append(f"탑승 시간 +{self.transit_extra_minutes}분")
        if self.service_cut_minutes:
            parts.append(f"이용시간 -{self.service_cut_minutes}분")
        return " · ".join(parts)


def _original_windows(
    request: OptimizeRequest, settings: Settings, stay_minutes: int, deadline: int | None
) -> dict[str, tuple[int, int]]:
    """양보하기 전의 창. 나중에 '얼마나 밀렸나' 를 재는 기준이다."""
    windows: dict[str, tuple[int, int]] = {}
    for index, passenger in enumerate(request.passengers, start=1):
        key = passenger.id or f"P{index:03d}"
        low, high, _source, _conflict = resolve_window(
            passenger, request.trip_type, stay_minutes, settings, deadline
        )
        windows[key] = (low, high)
    return windows


def _measure(result: OptimizeResponse, original: dict[str, tuple[int, int]]) -> list[Adjustment]:
    """당초 창을 벗어난 분만 골라낸다.

    전원의 시각을 넓혀서 풀었더라도, 실제로 창을 벗어난 분은 대개 몇 분뿐이다.
    넓힌 것과 실제로 밀린 것은 다르다. 원장님께는 실제로 밀린 분만 알려야 한다.
    """
    adjusted: list[Adjustment] = []
    for vehicle in result.vehicles:
        for trip in vehicle.trips:
            if not trip.used:
                continue
            for stop in trip.stops:
                bounds = original.get(stop.passenger_id)
                if not bounds or not stop.estimated_pickup:
                    continue
                low, high = bounds
                actual = parse_hhmm(stop.estimated_pickup)
                if low <= actual <= high:
                    continue
                shift = (low - actual) if actual < low else (actual - high)
                adjusted.append(Adjustment(
                    passenger_id=stop.passenger_id,
                    name=stop.name,
                    planned_window=f"{format_hhmm(low)}~{format_hhmm(high)}",
                    actual_time=stop.estimated_pickup,
                    shift_minutes=shift,
                    late=actual > high,
                ))
    adjusted.sort(key=lambda item: -item.shift_minutes)
    return adjusted


def solve_until_everyone_rides(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    trips_per_vehicle: int | None = None,
) -> tuple[OptimizeResponse, Relaxation]:
    """전원이 탈 때까지 조금씩 양보하며 다시 푼다.

    원안으로 전원이 타면 아무것도 양보하지 않고 그대로 돌려준다.
    끝까지 안 되면 가장 많이 태운 결과를 돌려준다. 그때도 못 탄 분은
    배차 불가로 남는다. 없는 답을 지어내지는 않는다.
    """
    started = time.perf_counter()
    stay_minutes = round(settings.stay_hours * 60)
    deadlines = [
        parse_hhmm(vehicle.outbound_deadline)
        for vehicle in request.vehicles
        if vehicle.outbound_deadline
    ]
    if not deadlines and settings.outbound_deadline:
        deadlines = [parse_hhmm(settings.outbound_deadline)]
    tightest = min(deadlines) if deadlines else None
    original = _original_windows(request, settings, stay_minutes, tightest)

    kwargs = {} if trips_per_vehicle is None else {"trips_per_vehicle": trips_per_vehicle}
    best: OptimizeResponse | None = None
    best_step = LADDER[0]

    for attempt, step in enumerate(LADDER, start=1):
        tuned = settings
        if step.transit_extra:
            tuned = settings.model_copy(update={
                "max_transit_minutes": settings.max_transit_minutes + step.transit_extra
            })
        # 원안은 제대로 풀고, 다시 푸는 것은 빠르게 본다.
        if attempt > 1:
            tuned = tuned.model_copy(
                update={"solver_time_limit_seconds": RETRY_TIME_LIMIT_SECONDS}
            )

        try:
            result = optimize_routes(
                request, resolved, tuned,
                window_slack_minutes=step.window_slack,
                service_cut_minutes=step.service_cut,
                **kwargs,
            )
        except Exception:  # noqa: BLE001
            # 원안이 터진 것은 요청 자체가 잘못됐다는 뜻이다. 그건 그대로 알린다.
            # 삼켜 버리면 '왜 안 되는지' 를 원장님이 영영 못 보시게 된다.
            if attempt == 1:
                raise
            # 다시 푸는 도중의 실패는 그 칸만 건너뛴다.
            continue

        if best is None or len(result.unassigned_passengers) < len(best.unassigned_passengers):
            best, best_step = result, step

        if not result.unassigned_passengers:
            relaxation = Relaxation(
                applied=not step.is_original,
                steps_tried=attempt,
                window_slack_minutes=step.window_slack,
                transit_extra_minutes=step.transit_extra,
                service_cut_minutes=step.service_cut,
                adjusted=_measure(result, original) if not step.is_original else [],
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            return result, relaxation

    # 여기까지 왔다면 끝까지 못 태운 분이 있다. 가장 많이 태운 것을 준다.
    relaxation = Relaxation(
        applied=not best_step.is_original,
        steps_tried=len(LADDER),
        window_slack_minutes=best_step.window_slack,
        transit_extra_minutes=best_step.transit_extra,
        service_cut_minutes=best_step.service_cut,
        adjusted=_measure(best, original) if best and not best_step.is_original else [],
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )
    return best, relaxation
