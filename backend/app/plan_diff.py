"""두 배차안이 무엇이 다른지 센다.

무엇을 위한 것인가
    엔진이 낸 원안과, 원장님이 실제로 내보낸 최종안을 비교한다. 차이가 크다면
    엔진이 현장을 모르는 것이고, 그 차이가 곧 엔진이 배워야 할 내용이다.

무엇을 남기지 않는가
    편집 이벤트를 하나하나 남기지 않는다. '누가 언제 무엇을 드래그했다' 는
    양만 늘고 쓸모가 적다. 원안과 최종안 두 장만 있으면 필요한 것은 다 나온다.

    그래서 여기서 세는 것은 의미 단위다.
      - 담당 차량이 바뀐 어르신이 몇 분인가
      - 차량은 그대로인데 순서만 바뀐 곳이 몇 군데인가

지금 상태
    아직 배차를 손으로 고치는 화면이 없다. 그 화면이 생겼을 때 바로 쓸 수 있도록
    계산하는 쪽을 먼저 둔다. 지금은 최종안이 항상 원안과 같아
    is_human_modified 가 False 로 나온다.
"""
from dataclasses import dataclass, field

from .models import OptimizeResponse


@dataclass
class PlanDiff:
    """원안과 최종안의 차이."""

    is_human_modified: bool = False
    # 담당 차량이 바뀐 어르신 수
    vehicle_reassignment_count: int = 0
    # 차량은 그대로인데 방문 순서가 바뀐 어르신 수
    stop_reorder_count: int = 0
    # 원안에 없다가 최종안에 들어온 분 / 그 반대
    added_passenger_count: int = 0
    removed_passenger_count: int = 0
    # 어느 분이 어떻게 바뀌었는지. 이름이 아니라 id 다.
    reassigned_passenger_ids: list[str] = field(default_factory=list)


def _placements(plan: OptimizeResponse) -> dict[str, tuple[str, int, int]]:
    """어르신 id -> (차량, 회차, 그 회차 안에서 몇 번째로 방문하는지)."""
    placements: dict[str, tuple[str, int, int]] = {}
    for vehicle in plan.vehicles:
        for trip in vehicle.trips:
            if not trip.used:
                continue
            for order, stop in enumerate(trip.stops):
                if stop.passenger_id:
                    placements[stop.passenger_id] = (vehicle.vehicle_id, trip.round, order)
    return placements


def compare_plans(original: OptimizeResponse, final: OptimizeResponse) -> PlanDiff:
    """엔진이 낸 원안과 실제로 내보낸 최종안을 비교한다."""
    before = _placements(original)
    after = _placements(final)

    diff = PlanDiff()
    diff.added_passenger_count = len(set(after) - set(before))
    diff.removed_passenger_count = len(set(before) - set(after))

    for passenger_id in set(before) & set(after):
        old_vehicle, old_round, old_order = before[passenger_id]
        new_vehicle, new_round, new_order = after[passenger_id]
        if (old_vehicle, old_round) != (new_vehicle, new_round):
            # 차량이나 회차가 바뀐 것은 순서가 바뀐 것보다 무거운 변경이다.
            diff.vehicle_reassignment_count += 1
            diff.reassigned_passenger_ids.append(passenger_id)
        elif old_order != new_order:
            diff.stop_reorder_count += 1

    diff.is_human_modified = bool(
        diff.vehicle_reassignment_count
        or diff.stop_reorder_count
        or diff.added_passenger_count
        or diff.removed_passenger_count
    )
    return diff
