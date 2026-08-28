import math
import time
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import HTTPException
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .config import Settings
from .geocoding import ResolvedLocation
from .models import (
    CenterResult,
    OptimizeRequest,
    OptimizeResponse,
    StopResult,
    TripResult,
    VehicleResult,
    format_hhmm,
    parse_hhmm,
)


@dataclass(frozen=True)
class VehicleSpec:
    vehicle_id: str
    vehicle_type: str
    plate_number: str
    driver_name: str | None
    driver_phone: str | None
    capacity: int
    # 1회차 출발 노드. 0 이면 센터, 그 외는 자차 출발지 노드.
    start_node: int = 0


def _required_groups(
    passenger_ids: list[str], required_pairs: list[tuple[str, str]]
) -> dict[str, set[str]]:
    """필수 동승 규칙을 묶어 그룹으로 만든다.

    A-B, B-C가 모두 짝꿍이면 A/B/C는 한 덩어리로 같은 차에 타야 한다.
    유니온-파인드로 이 전이 관계를 미리 펼쳐 둔다.
    """
    parent = {pid: pid for pid in passenger_ids}

    def find(pid: str) -> str:
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    for left, right in required_pairs:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    groups: dict[str, set[str]] = {}
    for pid in passenger_ids:
        groups.setdefault(find(pid), set()).add(pid)
    return groups


def _validate_pair_rules(
    passenger_ids: list[str],
    forbidden_pairs: list[tuple[str, str]],
    required_pairs: list[tuple[str, str]],
    names: dict[str, str],
    max_vehicle_capacity: int,
) -> None:
    """솔버에 넘기기 전에 명백한 모순을 잡아 알아들을 수 있는 메시지로 돌려준다.

    이걸 안 하면 OR-Tools는 그냥 '해 없음'만 뱉어서 원인을 알 수 없다.
    """
    groups = _required_groups(passenger_ids, required_pairs)

    for members in groups.values():
        if len(members) > max_vehicle_capacity:
            who = ", ".join(sorted(names.get(pid, pid) for pid in members))
            raise HTTPException(
                status_code=422,
                detail=(
                    f"필수 동승으로 묶인 {len(members)}명({who})은 함께 타야 하는데, "
                    f"가장 큰 차량의 정원이 {max_vehicle_capacity}명입니다."
                ),
            )

    member_of = {pid: root for root, members in groups.items() for pid in members}
    for left, right in forbidden_pairs:
        if member_of.get(left) == member_of.get(right):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{names.get(left, left)}님과 {names.get(right, right)}님은 "
                    "동승 불가인 동시에 필수 동승으로 묶여 있어 배차할 수 없습니다."
                ),
            )


def _haversine_km(a: ResolvedLocation, b: ResolvedLocation) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat = lat2 - lat1
    dlng = math.radians(b.longitude - a.longitude)
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _matrices(
    locations: list[ResolvedLocation], settings: Settings
) -> tuple[list[list[int]], list[list[int]]]:
    distance_m: list[list[int]] = []
    travel_minutes: list[list[int]] = []
    for origin in locations:
        distance_row: list[int] = []
        time_row: list[int] = []
        for destination in locations:
            if origin is destination:
                distance_row.append(0)
                time_row.append(0)
                continue
            km = _haversine_km(origin, destination) * settings.road_distance_factor
            distance_row.append(max(1, round(km * 1000)))
            time_row.append(max(1, math.ceil(km / settings.average_speed_kph * 60)))
        distance_m.append(distance_row)
        travel_minutes.append(time_row)
    return distance_m, travel_minutes


def _kakao_navi_url(destination: ResolvedLocation) -> str:
    """길안내 딥링크.

    예전에는 kakaonavi://navigate?params={JSON} 을 만들었는데, 그 형식은
    카카오내비 SDK 용이라 딥링크로 직접 부르면 네이티브 앱 키를 요구한다.
    키가 없어 기기에서 "필수 파라미터가 존재하지 않습니다" 오류가 났다.

    키가 필요 없는 카카오맵 길찾기 스킴으로 바꿨다. 출발지를 비우면
    현재 위치에서 자동차 길안내가 시작된다.

    앱은 이 값을 쓰지 않고 좌표로 직접 링크를 만든다(navigation.js).
    이미 저장된 배차에도 즉시 적용되게 하기 위해서다. 이 필드는 호환용이다.
    """
    return (
        f"kakaomap://route?ep={destination.latitude},{destination.longitude}&by=CAR"
    )


def optimize_routes(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
) -> OptimizeResponse:
    started = time.perf_counter()
    passenger_count = len(request.passengers)
    # 자차 출발지는 어르신 노드 뒤에 순서대로 붙어 있다.
    # main.py 가 [센터, *어르신, *커스텀출발지] 순으로 지오코딩해 넘긴다.
    next_start_node = 1 + passenger_count
    vehicles = []
    for index, vehicle in enumerate(request.vehicles):
        if vehicle.start_type == "custom":
            start_node = next_start_node
            next_start_node += 1
        else:
            start_node = 0
        vehicles.append(
            VehicleSpec(
                vehicle_id=vehicle.id or f"vehicle-{index + 1}",
                vehicle_type=vehicle.vehicle_type,
                plate_number=vehicle.plate_number,
                driver_name=vehicle.driver_name,
                driver_phone=vehicle.driver_phone,
                capacity=vehicle.capacity,
                start_node=start_node,
            )
        )
    # 규칙을 노드 번호로 옮기려면 어르신마다 확정된 id가 필요하다.
    # StopResult가 쓰는 것과 같은 규칙으로 만든다.
    passenger_ids = [
        passenger.id or f"P{node:03d}"
        for node, passenger in enumerate(request.passengers, start=1)
    ]
    node_of_passenger = {pid: node for node, pid in enumerate(passenger_ids, start=1)}
    names = dict(zip(passenger_ids, (p.name for p in request.passengers)))

    forbidden_pairs = [rule.pair for rule in request.forbidden_pairs]
    required_pairs = [rule.pair for rule in request.required_pairs]
    _validate_pair_rules(
        passenger_ids,
        forbidden_pairs,
        required_pairs,
        names,
        max(vehicle.capacity for vehicle in vehicles),
    )

    max_capacity = sum(vehicle.capacity for vehicle in vehicles) * 2
    if passenger_count > max_capacity:
        raise HTTPException(
            status_code=422,
            detail=f"탑승 인원 {passenger_count}명은 2회 운행 최대 수용 인원 {max_capacity}명을 초과합니다.",
        )

    # 노드 0은 센터, 1..n은 어르신, 그 뒤는 자차 출발지.
    # 물리 차량 한 대당 두 개의 라우팅 차량(1·2회차)을 만들고,
    # 아래 제약으로 두 회차를 시간 순으로 묶는다.
    distance_m, travel_minutes = _matrices(resolved, settings)
    trip_specs = [(vehicle, round_number) for vehicle in vehicles for round_number in (1, 2)]

    # 자차 출발은 1회차에만 적용한다. 2회차는 이미 센터에 돌아와 있으므로
    # 센터에서 출발하는 것이 현장 동선과 맞다.
    trip_starts = [
        vehicle.start_node if round_number == 1 else 0
        for vehicle, round_number in trip_specs
    ]
    # 도착지는 항상 센터다. 어르신을 센터로 모셔오는 것이 송영이다.
    trip_ends = [0] * len(trip_specs)
    manager = pywrapcp.RoutingIndexManager(
        len(resolved), len(trip_specs), trip_starts, trip_ends
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return distance_m[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    distance_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(distance_index)

    # 배열 길이는 전체 노드 수와 같아야 한다. 콜백이 원본 노드 번호로 색인하는데
    # 자차 출발지 노드가 뒤에 붙으므로, 짧으면 IndexError 가 난다.
    service = [0] + [settings.stop_service_minutes] * passenger_count
    service += [0] * (len(resolved) - len(service))

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return service[from_node] + travel_minutes[from_node][to_node]

    time_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(time_index, 24 * 60, 24 * 60, False, "Time")
    time_dimension = routing.GetDimensionOrDie("Time")
    time_dimension.SetGlobalSpanCostCoefficient(2)

    for node, passenger in enumerate(request.passengers, start=1):
        index = manager.NodeToIndex(node)
        time_dimension.CumulVar(index).SetRange(
            parse_hhmm(passenger.pickup_start), parse_hhmm(passenger.pickup_end)
        )

    for trip_index in range(len(trip_specs)):
        start_index = routing.Start(trip_index)
        end_index = routing.End(trip_index)
        time_dimension.CumulVar(start_index).SetRange(0, 24 * 60)
        time_dimension.CumulVar(end_index).SetRange(0, 24 * 60)
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(end_index))
        # A second run costs extra, helping the solver avoid unnecessary runs.
        routing.SetFixedCostOfVehicle(0 if trip_index % 2 == 0 else 20_000, trip_index)

    demands = [0] + [1] * passenger_count
    demands += [0] * (len(resolved) - len(demands))

    def demand_callback(index: int) -> int:
        return demands[manager.IndexToNode(index)]

    demand_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        0,
        [spec.capacity for spec, _ in trip_specs],
        True,
        "Capacity",
    )

    solver = routing.solver()
    for vehicle_index in range(len(vehicles)):
        first_trip = vehicle_index * 2
        second_trip = first_trip + 1
        # Never label a run as round 2 unless round 1 is actually used.
        solver.Add(
            routing.ActiveVehicleVar(second_trip)
            <= routing.ActiveVehicleVar(first_trip)
        )
        # The physical vehicle must return before its second departure.
        solver.Add(
            time_dimension.CumulVar(routing.Start(second_trip))
            >= time_dimension.CumulVar(routing.End(first_trip))
            + settings.turnaround_minutes
        )

    # 동승 규칙. VehicleVar는 '어느 운행(차량×회차)에 실렸는가'를 가리키므로,
    # 같으면 같은 차에 같은 회차로 함께 탄다는 뜻이다.
    # 회차가 다르면 차 안에서 마주치지 않으므로 '동승'으로 보지 않는다.
    for left, right in forbidden_pairs:
        solver.Add(
            routing.VehicleVar(manager.NodeToIndex(node_of_passenger[left]))
            != routing.VehicleVar(manager.NodeToIndex(node_of_passenger[right]))
        )
    for left, right in required_pairs:
        solver.Add(
            routing.VehicleVar(manager.NodeToIndex(node_of_passenger[left]))
            == routing.VehicleVar(manager.NodeToIndex(node_of_passenger[right]))
        )

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromSeconds(settings.solver_time_limit_seconds)
    search.log_search = False
    solution = routing.SolveWithParameters(search)
    if solution is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "주어진 탑승 시간, 차량 정원, 차량별 2회 운행 제한"
                + (", 동승 규칙" if (forbidden_pairs or required_pairs) else "")
                + "을 동시에 만족하는 경로가 없습니다. "
                "시간창을 넓히거나 동승 규칙을 줄여 보세요."
            ),
        )

    vehicle_results: list[VehicleResult] = []
    total_distance = 0
    for physical_index, vehicle in enumerate(vehicles):
        trips: list[TripResult] = []
        for offset, round_number in enumerate((1, 2)):
            trip_index = physical_index * 2 + offset
            route_nodes: list[int] = []
            route_distance = 0
            index = routing.Start(trip_index)
            departure = solution.Value(time_dimension.CumulVar(index))
            while not routing.IsEnd(index):
                next_index = solution.Value(routing.NextVar(index))
                route_distance += distance_callback(index, next_index)
                node = manager.IndexToNode(next_index)
                if node != 0:
                    route_nodes.append(node)
                index = next_index
            return_time = solution.Value(time_dimension.CumulVar(index))
            used = bool(route_nodes)
            stops: list[StopResult] = []
            if used:
                index = routing.Start(trip_index)
                sequence = 0
                while not routing.IsEnd(index):
                    index = solution.Value(routing.NextVar(index))
                    node = manager.IndexToNode(index)
                    if node == 0:
                        continue
                    sequence += 1
                    passenger = request.passengers[node - 1]
                    location = resolved[node]
                    pickup_minute = solution.Value(time_dimension.CumulVar(index))
                    stops.append(
                        StopResult(
                            sequence=sequence,
                            passenger_id=passenger_ids[node - 1],
                            name=passenger.name,
                            address=passenger.address,
                            detail_address=passenger.detail_address,
                            guardian_phone=passenger.guardian_phone,
                            passenger_phone=passenger.passenger_phone,
                            primary_contact=passenger.primary_contact,
                            sms_opt_in=passenger.sms_opt_in,
                            latitude=location.latitude,
                            longitude=location.longitude,
                            wheelchair=passenger.wheelchair,
                            requested_window=f"{passenger.pickup_start}~{passenger.pickup_end}",
                            estimated_pickup=format_hhmm(pickup_minute),
                            kakao_navi_url=_kakao_navi_url(location),
                        )
                    )
            total_distance += route_distance
            trips.append(
                TripResult(
                    round=round_number,
                    used=used,
                    passenger_count=len(route_nodes),
                    capacity=vehicle.capacity,
                    departure_time=format_hhmm(departure) if used else None,
                    return_time=format_hhmm(return_time) if used else None,
                    distance_km=round(route_distance / 1000, 1),
                    stops=stops,
                )
            )
        # start_node 0 은 센터다. 이때 start_name 은 센터 등록 시 입력한
        # 센터명(예: 수주간보호센터)이 그대로 들어간다. 기사님 화면에서
        # 긴 주소 대신 센터명을 보여줄 수 있어야 한다.
        start_location = resolved[vehicle.start_node]
        vehicle_results.append(
            VehicleResult(
                vehicle_id=vehicle.vehicle_id,
                vehicle_type=vehicle.vehicle_type,
                plate_number=vehicle.plate_number,
                driver_name=vehicle.driver_name,
                driver_phone=vehicle.driver_phone,
                capacity=vehicle.capacity,
                start_type="custom" if vehicle.start_node != 0 else "center",
                start_name=start_location.name,
                start_address=start_location.address,
                start_latitude=start_location.latitude,
                start_longitude=start_location.longitude,
                trips=trips,
            )
        )

    center_location = resolved[0]
    return OptimizeResponse(
        status="optimal_or_feasible",
        center=CenterResult(
            name=center_location.name,
            address=center_location.address,
            latitude=center_location.latitude,
            longitude=center_location.longitude,
        ),
        total_passengers=passenger_count,
        total_distance_km=round(total_distance / 1000, 1),
        solve_seconds=round(time.perf_counter() - started, 3),
        vehicles=vehicle_results,
        notices=[
            "모든 픽업 예상 시각은 요청 시간창 안에 있으며 차량별 운행은 최대 2회입니다.",
            *(
                [
                    "자차 송영 차량("
                    + ", ".join(
                        v.plate_number for v in vehicles if v.start_node != 0
                    )
                    + ")은 1회차를 지정된 출발지에서 시작하고 센터로 복귀합니다."
                ]
                if any(v.start_node != 0 for v in vehicles)
                else []
            ),
            "MVP의 이동시간은 직선거리×도로계수와 평균속도로 산정됩니다. 운영 전 실시간 도로 시간행렬 연동을 권장합니다.",
        ],
    )
