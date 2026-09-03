"""3회차를 무리해서 도는 것과 차를 한 대 늘리는 것 중 어느 쪽이 싼가.

왜 이 계산이 필요한가
    "3회차를 돌면 전원 수용됩니다" 까지만 말하면 원장님은 그게 이득인지 손해인지
    모른다. 3회차는 공짜가 아니다. 다만 그 비용이 어디서 나오는지가 현장의
    상식과 다르다.

    인건비는 0원이다. 운전은 이미 급여가 나가는 요양보호사가 맡으므로 연장수당도
    신규 고용도 없다. 여기서는 아예 세지 않는다.

    진짜 비용은 수가 삭감이다. 기사님 퇴근 시간을 맞추면서 3회차를 돌리려면
    1회차 어르신을 계획보다 일찍 보내야 한다. 이용시간이 줄면 청구 구간이
    내려가고 그만큼 매출이 준다.

수가는 계단이다
    이 파일에서 가장 중요한 사실이다. 장기요양 주야간보호 수가는 이용시간
    '구간' 별 정액이다. 시간에 비례하지 않는다.

      11시간 50분인 분을 40분 당기면 11시간 10분  -> 같은 구간, 손실 0원
      10시간 10분인 분을 40분 당기면  9시간 30분  -> 구간 강등, 손실 발생

    비례식으로 짜면 앞의 분에게도 손실을 매겨 3회차를 실제보다 훨씬 비싸게
    본다. 그러면 엔진이 늘 "증차하세요" 라고 답하는데 그건 틀린 조언이다.

이 파일은 순수 계산만 한다
    솔버도 DB 도 부르지 않는다. 그래야 금액 하나하나를 테스트로 묶어 둘 수 있다.
"""
from dataclasses import dataclass, field

from .config import Settings

# ── 수가 구간 ────────────────────────────────────────────────
#
# (하한 시간, 상한 시간). 상한은 포함하지 않는다.
# 고시의 구간을 그대로 옮긴 것이라 임의로 바꾸면 안 된다.
SERVICE_BANDS: tuple[tuple[float, float], ...] = (
    (3.0, 6.0),
    (6.0, 8.0),
    (8.0, 10.0),
    (10.0, 12.0),
    (12.0, 13.0),
)


def band_of(hours: float) -> tuple[float, float] | None:
    """이용시간이 어느 구간에 드는가. 3시간 미만이면 None."""
    for low, high in SERVICE_BANDS:
        if low <= hours < high:
            return (low, high)
    # 13시간을 넘으면 마지막 구간으로 본다. 그 위는 별도 고시라 여기서 다루지 않는다.
    if hours >= SERVICE_BANDS[-1][1]:
        return SERVICE_BANDS[-1]
    return None


def band_label(band: tuple[float, float] | None) -> str:
    if band is None:
        return "3시간 미만"
    low, high = band
    return f"{low:g}~{high:g}시간"


@dataclass
class RevenueLossItem:
    """수가가 깎인 어르신 한 분."""

    passenger_id: str
    name: str
    care_grade: int
    planned_hours: float
    actual_hours: float
    planned_band: str
    actual_band: str
    lost_won: int


@dataclass
class ScenarioCost:
    """한 가지 운영 방식의 하루 비용."""

    label: str
    distance_km: float
    fuel_won: int = 0
    fixed_won: int = 0
    revenue_loss_won: int = 0
    # 누구에게서 수가가 깎였는지. 원장님이 "그럼 그 분만 옮기면?" 을 판단하는 근거다.
    revenue_loss_items: list[RevenueLossItem] = field(default_factory=list)

    @property
    def total_won(self) -> int:
        return self.fuel_won + self.fixed_won + self.revenue_loss_won


def rate_for(settings: Settings, grade: int, band: tuple[float, float] | None) -> int | None:
    """그 등급, 그 구간의 하루 수가. 표에 없으면 None.

    None 은 0원이 아니라 '모른다' 는 뜻이다. 모르는 것을 0으로 두면 손실이
    없는 것처럼 보여서 잘못된 권고가 나간다. 부르는 쪽이 판단을 보류해야 한다.
    """
    if band is None:
        return None
    return settings.care_rate_table.get(f"{grade}:{band[0]:g}-{band[1]:g}")


def fuel_cost_won(distance_km: float, settings: Settings) -> int:
    """이 거리를 달리는 데 드는 기름값.

    차량마다 연비가 다르지만 시뮬레이션 단계에서는 어느 차가 얼마를 더 달릴지
    확정할 수 없다. 센터 평균 연비 하나로 계산하고, 그 값을 설정으로 열어 둔다.
    """
    if settings.fleet_fuel_efficiency_kmpl <= 0:
        return 0
    liters = distance_km / settings.fleet_fuel_efficiency_kmpl
    return int(round(liters * settings.fuel_price_per_liter))


def revenue_loss(
    departures: dict[str, float],
    passengers: list,
    settings: Settings,
) -> tuple[int, list[RevenueLossItem], list[str]]:
    """일찍 하원하게 되어 깎인 수가를 더한다.

    departures 는 어르신 id -> 계획보다 몇 시간 일찍 나가는지(양수).
    돌려주는 것은 (총 삭감액, 항목별 내역, 계산하지 못한 사유).
    """
    total = 0
    items: list[RevenueLossItem] = []
    unknown: list[str] = []

    for passenger in passengers:
        shortfall = departures.get(passenger.id or "", 0.0)
        if shortfall <= 0:
            continue

        planned = passenger.planned_service_hours or settings.stay_hours
        actual = max(0.0, planned - shortfall)
        planned_band = band_of(planned)
        actual_band = band_of(actual)

        # 구간이 그대로면 한 푼도 깎이지 않는다. 이 파일이 존재하는 이유다.
        if planned_band == actual_band:
            continue

        grade = passenger.care_grade or settings.default_care_grade
        before = rate_for(settings, grade, planned_band)
        after = rate_for(settings, grade, actual_band)

        if before is None or after is None:
            unknown.append(
                f"{passenger.name} 어르신({grade}등급 "
                f"{band_label(planned_band)}→{band_label(actual_band)})의 수가가 표에 없습니다."
            )
            continue

        lost = max(0, before - after)
        if not lost:
            continue

        total += lost
        items.append(RevenueLossItem(
            passenger_id=passenger.id or "",
            name=passenger.name,
            care_grade=grade,
            planned_hours=round(planned, 2),
            actual_hours=round(actual, 2),
            planned_band=band_label(planned_band),
            actual_band=band_label(actual_band),
            lost_won=lost,
        ))

    return total, items, unknown


def build_scenarios(
    label_a: str,
    distance_a_km: float,
    early_departures: dict[str, float],
    passengers: list,
    label_b: str,
    distance_b_km: float,
    settings: Settings,
    consider_revenue_loss: bool,
) -> tuple[ScenarioCost, ScenarioCost, list[str]]:
    """A안(3회차)과 B안(증차)의 하루 비용을 각각 매긴다."""
    notes: list[str] = []

    scenario_a = ScenarioCost(
        label=label_a,
        distance_km=round(distance_a_km, 1),
        fuel_won=fuel_cost_won(distance_a_km, settings),
    )
    if consider_revenue_loss:
        lost, items, unknown = revenue_loss(early_departures, passengers, settings)
        scenario_a.revenue_loss_won = lost
        scenario_a.revenue_loss_items = items
        notes.extend(unknown)
    else:
        notes.append(
            "조기 하원에 따른 수가 감소를 비용에 넣지 않고 계산했습니다. "
            "실제 청구는 실제 제공한 이용시간을 반영해야 합니다."
        )

    scenario_b = ScenarioCost(
        label=label_b,
        distance_km=round(distance_b_km, 1),
        fuel_won=fuel_cost_won(distance_b_km, settings),
        fixed_won=int(round(settings.spare_vehicle_daily_cost)),
    )

    return scenario_a, scenario_b, notes
