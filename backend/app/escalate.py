"""어르신을 길에 두지 않는다 — 다만 무엇을 양보할지는 센터가 정한다.

현장에서는 '시간이 안 맞아서 못 태웠습니다' 라는 배차표를 쓸 수 없다.
그래서 제약에 막히면 포기하지 않고 스스로 조금씩 풀어 가며 다시 푼다.

그런데 '무엇부터 양보할 것인가' 에는 정답이 없다. 센터마다 지키려는 것이
다르기 때문이다. 엔진이 그 순서를 정해 버리면, 엔진의 철학을 전국 센터에
강요하는 셈이 된다.

양보할 수 있는 것은 셋뿐이다.

  픽업·하차 시각   보호자와 약속한 시각이 틀어진다
  탑승 시간        어르신이 차에 더 오래 계신다
  이용 시간        센터에 머무는 시간이 줄어 수가 구간이 내려간다

센터는 이 중 '마지막까지 지킬 것' 하나를 고른다. 나머지 둘은 싼 것부터
양보한다. 고른 것은 다른 방법이 모두 바닥난 뒤에야 손댄다.

  수익 최우선    이용 시간을 끝까지 지킨다   (시각 → 탑승 → 이용)
  어르신 편의    탑승 시간을 끝까지 지킨다   (시각 → 이용 → 탑승)
  보호자 약속    픽업 시각을 끝까지 지킨다   (탑승 → 이용 → 시각)

무엇을 양보했는지는 반드시 남긴다. 조용히 시간을 바꿔 놓고 성공했다고만
하면, 원장님이 보호자에게 잘못된 시각을 통보하시게 된다.
"""
import time
from dataclasses import dataclass, field

from .config import Settings
from .geocoding import ResolvedLocation
from .models import OptimizeRequest, OptimizeResponse, format_hhmm, parse_hhmm
from .optimizer import optimize_routes, resolve_window

# ── 양보할 수 있는 세 가지 ────────────────────────────────────
WINDOW = "window"
TRANSIT = "transit"
SERVICE = "service"

# 각 지렛대를 어디까지 어떤 단계로 푸는가.
GRADES: dict[str, tuple[int, ...]] = {
    WINDOW: (30, 60),    # 희망 시각 ±분
    TRANSIT: (20, 40),   # 한 회차 탑승 시간 상한 +분
    SERVICE: (30, 60),   # 계획 이용시간 -분
}

# 사후 보고에 쓰는 이름.
LEVER_NOUN = {
    WINDOW: "픽업·하차 시각",
    TRANSIT: "탑승 시간",
    SERVICE: "이용 시간",
}
# '이것만은 지켰습니다' 라고 말할 때의 문구.
LEVER_KEPT = {
    WINDOW: "픽업 시각을 건드리지 않는 대신",
    TRANSIT: "탑승 시간을 늘리지 않는 대신",
    SERVICE: "계획 이용시간을 줄이지 않는 대신",
}
# 끝내 그것까지 손댄 경우의 문구.
LEVER_YIELDED = {
    WINDOW: "픽업 시각을 끝까지 아꼈지만",
    TRANSIT: "탑승 시간을 끝까지 아꼈지만",
    SERVICE: "계획 이용시간을 끝까지 아꼈지만",
}

# ── 센터의 운영 철학 ──────────────────────────────────────────
# 값은 '양보하는 순서'. 맨 뒤가 끝까지 지키는 것이다.
PRIORITIES: dict[str, tuple[str, str, str]] = {
    # 수가를 지킨다. 이용시간 단축만이 그날 매출을 직접 깎는다.
    "revenue": (WINDOW, TRANSIT, SERVICE),
    # 어르신 피로도를 지킨다. 차에 오래 태우느니 수가를 깎는다.
    "comfort": (WINDOW, SERVICE, TRANSIT),
    # 보호자와의 약속을 지킨다. 통보한 시각을 바꾸느니 다른 걸 내준다.
    "promise": (TRANSIT, SERVICE, WINDOW),
}
PRIORITY_LABEL = {
    "revenue": "수익·이용시간 최우선",
    "comfort": "어르신 편의 최우선",
    "promise": "보호자 약속 최우선",
}
DEFAULT_PRIORITY = "revenue"


@dataclass(frozen=True)
class Step:
    """완화 한 단계."""

    window_slack: int = 0
    transit_extra: int = 0
    service_cut: int = 0

    @property
    def is_original(self) -> bool:
        return not (self.window_slack or self.transit_extra or self.service_cut)

    def value_of(self, lever: str) -> int:
        return {
            WINDOW: self.window_slack,
            TRANSIT: self.transit_extra,
            SERVICE: self.service_cut,
        }[lever]

    def describe(self) -> str:
        parts = []
        if self.window_slack:
            parts.append(f"희망 시각 ±{self.window_slack}분")
        if self.transit_extra:
            parts.append(f"탑승 시간 +{self.transit_extra}분")
        if self.service_cut:
            parts.append(f"이용시간 -{self.service_cut}분")
        return " · ".join(parts) if parts else "원안"


_FIELD = {WINDOW: "window_slack", TRANSIT: "transit_extra", SERVICE: "service_cut"}


def normalize_priority(priority: str | None) -> str:
    """모르는 값이 와도 배차는 되어야 한다. 구형 앱은 아예 안 보낸다."""
    return priority if priority in PRIORITIES else DEFAULT_PRIORITY


def build_ladder(priority: str | None = None) -> tuple[Step, ...]:
    """센터가 고른 철학대로 완화 사다리를 새로 쌓는다.

    앞의 지렛대를 끝까지 다 쓴 뒤에야 다음 것을 건드린다. 그래야 '마지막까지
    지킨다' 는 약속이 말뿐이 아니게 된다. 첫 칸은 언제나 원안이다.
    """
    order = PRIORITIES[normalize_priority(priority)]
    steps = [Step()]
    held = {WINDOW: 0, TRANSIT: 0, SERVICE: 0}
    for lever in order:
        for grade in GRADES[lever]:
            held[lever] = grade
            steps.append(Step(**{_FIELD[key]: value for key, value in held.items()}))
    return tuple(steps)


# 기본 철학의 사다리. 예전 코드가 LADDER 를 그대로 쓰던 자리를 위해 남긴다.
LADDER: tuple[Step, ...] = build_ladder(DEFAULT_PRIORITY)

# 다시 풀 때는 '되는가' 만 알면 된다. 최적해까지 필요하지 않아 시간을 줄인다.
# 일곱 칸을 모두 15초로 돌면 105초가 걸려 원장님이 화면 앞에서 기다리신다.
RETRY_TIME_LIMIT_SECONDS = 7


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
    """무엇을 얼마나, 어떤 철학으로 양보해서 전원 배차를 만들었는가."""

    applied: bool = False
    steps_tried: int = 1
    window_slack_minutes: int = 0
    transit_extra_minutes: int = 0
    service_cut_minutes: int = 0
    adjusted: list[Adjustment] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    # 센터가 고른 철학과, 그 철학이 끝까지 지키려던 것.
    priority: str = DEFAULT_PRIORITY
    protected: str = SERVICE
    # 끝내 그것까지 손댔는가. 지켰다고 거짓말하지 않기 위한 값이다.
    protected_conceded: bool = False

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABEL[normalize_priority(self.priority)]

    @property
    def protected_label(self) -> str:
        return LEVER_NOUN[self.protected]

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

    @property
    def headline(self) -> str:
        """원장님께 그대로 보여 줄 한 문단.

        '전원 태웠습니다' 로만 끝내지 않는다. 어떤 철학으로 무엇을 지키고
        무엇을 내줬는지까지 말해야, 원장님이 그 판단에 동의할지 결정하실 수 있다.
        """
        if not self.applied:
            return ""

        clauses: list[str] = []
        # 창을 넓혔느냐가 아니라 '실제로 밀렸느냐' 로 말한다.
        # 이용시간을 줄여도 도착 마지노선이 뒤로 밀려 픽업 시각이 따라 움직인다.
        # 창을 안 건드렸다는 이유로 그걸 빼먹으면 원장님이 모르고 통보하신다.
        if self.adjusted:
            names = [item.name for item in self.adjusted]
            shown = ", ".join(names[:5])
            more = f" 외 {len(names) - 5}분" if len(names) > 5 else ""
            biggest = max(item.shift_minutes for item in self.adjusted)
            clauses.append(
                f"[{shown}{more}] 어르신의 픽업·하차 시각을 최대 {biggest}분 조정"
            )
        elif self.window_slack_minutes:
            # 창은 넓혔으나 결과적으로 아무도 당초 시각을 벗어나지 않았다.
            clauses.append(f"픽업·하차 시각 범위를 ±{self.window_slack_minutes}분 확대")
        if self.transit_extra_minutes:
            clauses.append(f"한 회차 탑승 시간 한도를 {self.transit_extra_minutes}분 연장")
        if self.service_cut_minutes:
            clauses.append(f"계획 이용시간을 {self.service_cut_minutes}분 단축")
        if not clauses:
            return ""

        body = "하고, ".join(clauses) + "했습니다."
        stance = (
            f"{LEVER_YIELDED[self.protected]}, 그것만으로는 전원을 태울 수 없어"
            if self.protected_conceded
            else LEVER_KEPT[self.protected]
        )
        return (
            "전원 배차를 완료했습니다. "
            f"센터가 선택한 [{self.priority_label}] 목표에 따라, {stance} "
            f"부득이하게 {body}"
        )


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


def _report(
    step: Step, attempt: int, priority: str, order: tuple[str, str, str],
    adjusted: list[Adjustment], started: float,
) -> Relaxation:
    protected = order[-1]
    conceded = step.value_of(protected) > 0
    # 창을 안 넓혔어도 이용시간을 줄이면 '몇 시까지 도착' 선이 뒤로 밀리고
    # 픽업 시각이 따라 움직인다. 실제로 밀린 분이 있으면 약속을 지킨 것이
    # 아니다. 지렛대를 안 썼다는 이유로 지켰다고 하면 거짓말이 된다.
    if protected == WINDOW and adjusted:
        conceded = True
    return Relaxation(
        applied=not step.is_original,
        steps_tried=attempt,
        window_slack_minutes=step.window_slack,
        transit_extra_minutes=step.transit_extra,
        service_cut_minutes=step.service_cut,
        adjusted=adjusted,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        priority=priority,
        protected=protected,
        protected_conceded=conceded,
    )


def solve_until_everyone_rides(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    trips_per_vehicle: int | None = None,
    priority: str | None = None,
) -> tuple[OptimizeResponse, Relaxation]:
    """전원이 탈 때까지, 센터가 고른 순서대로 조금씩 양보하며 다시 푼다.

    원안으로 전원이 타면 아무것도 양보하지 않고 그대로 돌려준다.
    끝까지 안 되면 가장 많이 태운 결과를 돌려준다. 그때도 못 탄 분은
    배차 불가로 남는다. 없는 답을 지어내지는 않는다.
    """
    started = time.perf_counter()
    # 화면에서 고른 값이 서버 기본값을 이긴다. 둘 다 없으면 수익 최우선이다.
    chosen = normalize_priority(
        priority
        or request.dispatch_priority
        or getattr(settings, "dispatch_priority", None)
    )
    order = PRIORITIES[chosen]
    ladder = build_ladder(chosen)

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
    best_step = ladder[0]

    for attempt, step in enumerate(ladder, start=1):
        # 원안은 제대로 풀고, 다시 푸는 것은 빠르게 본다.
        tuned = settings if attempt == 1 else settings.model_copy(
            update={"solver_time_limit_seconds": RETRY_TIME_LIMIT_SECONDS}
        )
        try:
            result = optimize_routes(
                request, resolved, tuned,
                window_slack_minutes=step.window_slack,
                service_cut_minutes=step.service_cut,
                transit_extra_minutes=step.transit_extra,
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
            return result, _report(
                step, attempt, chosen, order,
                _measure(result, original) if not step.is_original else [],
                started,
            )

    # 여기까지 왔다면 끝까지 못 태운 분이 있다. 가장 많이 태운 것을 준다.
    return best, _report(
        best_step, len(ladder), chosen, order,
        _measure(best, original) if best and not best_step.is_original else [],
        started,
    )
