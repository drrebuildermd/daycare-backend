"""최적화를 한 번 돌릴 때마다 그 사실을 남긴다.

왜 필요한가
    지금까지는 배차를 계산해도 그 원안이 어디에도 남지 않았다. [배차 전송] 을
    눌러야만 마지막 하나가 dispatches 에 들어가고, 같은 날 다시 전송하면
    그것마저 덮어썼다. 그래서 '원장님이 조건을 바꿔가며 세 번 다시 짰다' 는
    사실도, 첫 번째 안이 어땠는지도 남지 않았다.

    여기서 남기는 것은 매 실행마다 한 줄이고, 절대 덮어쓰지 않는다.

지켜야 할 것
    이 파일의 어떤 실패도 배차 결과 반환을 막아서는 안 된다. 기록은 곁다리고
    배차가 본체다. 그래서 모든 함수가 예외를 삼키고 None 을 돌려준다.
    표가 아직 없어도, Supabase 가 잠깐 죽어도, 원장님 화면에는 배차가 그대로 뜬다.

개인정보
    스냅샷에는 이름·연락처·상세주소를 담지 않는다. 좌표와 시간창은 남긴다.
    좌표가 없으면 '왜 이 순서로 돌았나' 를 나중에 되짚을 수 없기 때문이다.
"""
import logging
from datetime import date

from .config import Settings
from .models import OptimizeRequest, OptimizeResponse
from .optimizer import (
    CONSTRAINT_VERSION,
    DROP_PENALTY,
    ENGINE_VERSION,
    OBJECTIVE_VERSION,
    SECOND_RUN_PENALTY,
    TIME_SPAN_COEFFICIENT,
)
from .supabase_client import get_supabase

logger = logging.getLogger(__name__)

TABLE = "optimization_runs"

# 스냅샷에서 지우는 칸. 사람을 특정할 수 있는 것들이다.
PASSENGER_PII = (
    "name",
    "address",
    "detail_address",
    "guardian_phone",
    "passenger_phone",
    "guardian_name",
)
VEHICLE_PII = ("driver_name", "driver_phone", "start_address")


def _strip_passenger(passenger: dict) -> dict:
    """어르신 한 분의 입력에서 사람을 특정할 만한 것을 뺀다.

    id 는 남긴다. 그래야 같은 분이 어제와 오늘 어떻게 다르게 배차됐는지 볼 수 있다.
    id 자체로는 이름도 연락처도 알 수 없다.
    """
    return {key: value for key, value in passenger.items() if key not in PASSENGER_PII}


def _strip_vehicle(vehicle: dict) -> dict:
    return {key: value for key, value in vehicle.items() if key not in VEHICLE_PII}


def build_input_snapshot(request: OptimizeRequest) -> dict:
    """계산에 들어간 입력. 개인정보는 뺀다."""
    data = request.model_dump(mode="json")
    return {
        "trip_type": data.get("trip_type"),
        "center": {
            "latitude": data.get("center", {}).get("latitude"),
            "longitude": data.get("center", {}).get("longitude"),
        },
        "passengers": [_strip_passenger(p) for p in data.get("passengers", [])],
        "vehicles": [_strip_vehicle(v) for v in data.get("vehicles", [])],
        "forbidden_pairs": data.get("forbidden_pairs", []),
    }


def build_result_snapshot(result: OptimizeResponse) -> dict:
    """나온 경로. 정류장의 이름·주소는 빼고 좌표와 시각만 남긴다."""
    data = result.model_dump(mode="json")
    for vehicle in data.get("vehicles", []):
        for key in VEHICLE_PII:
            vehicle.pop(key, None)
        for trip in vehicle.get("trips", []):
            for stop in trip.get("stops", []):
                for key in ("name", "address", "detail_address", "guardian_phone",
                            "passenger_phone", "phone"):
                    stop.pop(key, None)
    for passenger in data.get("unassigned_passengers", []):
        passenger.pop("name", None)
    return data


def _next_sequence(service_date: date, trip_type: str, center_id: str) -> int:
    """같은 날 같은 구분으로 몇 번째 계산인지.

    2 이상이면 앞선 결과를 원장님이 받아들이지 않고 다시 짰다는 뜻이다.
    이것이 '재계산 신호' 다. 편집 이벤트를 따로 남기지 않고도 얻을 수 있다.
    """
    result = (
        get_supabase()
        .table(TABLE)
        .select("run_sequence")
        .eq("center_id", center_id)
        .eq("service_date", service_date.isoformat())
        .eq("trip_type", trip_type)
        .order("run_sequence", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return 1
    return int(result.data[0]["run_sequence"]) + 1


def record_optimization_run(
    request: OptimizeRequest,
    result: OptimizeResponse,
    service_date: date,
    settings: Settings,
) -> str | None:
    """실행 하나를 남기고 그 id 를 돌려준다.

    실패하면 로그만 남기고 None 을 돌려준다. 부르는 쪽은 이 값이 None 이어도
    아무 일 없었다는 듯 배차 결과를 그대로 반환해야 한다.
    """
    try:
        center_id = settings.center_id
        breakdown = result.objective_breakdown
        row = {
            "center_id": center_id,
            "service_date": service_date.isoformat(),
            "trip_type": result.trip_type,
            "run_sequence": _next_sequence(service_date, result.trip_type, center_id),
            "engine_version": ENGINE_VERSION,
            "constraint_version": CONSTRAINT_VERSION,
            "objective_version": OBJECTIVE_VERSION,
            # 어떤 판으로 풀었는지. 이 값이 바뀌면 결과도 바뀌므로 함께 남긴다.
            "config": {
                "average_speed_kph": settings.average_speed_kph,
                "road_distance_factor": settings.road_distance_factor,
                "stop_service_minutes": settings.stop_service_minutes,
                "turnaround_minutes": settings.turnaround_minutes,
                "stay_hours": settings.stay_hours,
                "solver_time_limit_seconds": settings.solver_time_limit_seconds,
                "second_run_penalty": SECOND_RUN_PENALTY,
                "drop_penalty": DROP_PENALTY,
                "time_span_coefficient": TIME_SPAN_COEFFICIENT,
            },
            "solver_status": result.status,
            "solve_seconds": result.solve_seconds,
            "passenger_count": result.total_passengers,
            "vehicle_count": len(result.vehicles),
            "assigned_count": result.total_passengers - len(result.unassigned_passengers),
            "unassigned_count": len(result.unassigned_passengers),
            # km 필드는 소수점 한 자리로 반올림된 값이라 여기 쓰면 미터가 어긋난다.
            "total_distance_m": (
                breakdown.distance_m if breakdown
                else int(round(result.total_distance_km * 1000))
            ),
            "objective_breakdown": breakdown.model_dump() if breakdown else None,
            "input_snapshot": build_input_snapshot(request),
            "result_snapshot": build_result_snapshot(result),
        }
        response = get_supabase().table(TABLE).insert(row).execute()
        if not response.data:
            return None
        return str(response.data[0]["id"])
    except Exception as error:  # noqa: BLE001 - 기록 실패가 배차를 막으면 안 된다
        logger.warning("최적화 이력 저장 실패 (배차는 정상 진행): %s", error)
        return None


def save_recommendation(run_id: str, report) -> bool:
    """어떤 대안을 제안했는지 그 계산 이력에 붙인다.

    나중에 '원장님이 이 제안을 받아들였나' 를 보려면 제안 자체가 남아 있어야
    한다. 같은 날 다음 계산에서 그 어르신의 시각이 실제로 바뀌었는지 보면
    수용 여부를 알 수 있고, 그게 다음 개선의 근거가 된다.

    여기서도 실패는 삼킨다. 이력이 안 남는 것보다 분석 결과를 못 보는 것이
    더 나쁘다.
    """
    try:
        get_supabase().table(TABLE).update(
            {"recommendation": report.model_dump(mode="json")}
        ).eq("id", run_id).execute()
        return True
    except Exception as error:  # noqa: BLE001 - 기록 실패가 분석을 막으면 안 된다
        logger.warning("대안 분석 결과 저장 실패 (분석 결과는 정상 반환): %s", error)
        return False
