import math
import time
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import HTTPException
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .config import Settings
from .geocoding import ResolvedLocation
from .models import (
    ObjectiveBreakdown,
    UnassignedPassenger,
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
    # 휠체어 고정석 수. 0 이면 리프트 없는 차량이다.
    wheelchair_capacity: int = 0
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


# ── 목적함수를 이루는 값 ──────────────────────────────────────
#
# 비용의 단위는 미터다. 거리 1m 가 1이다.
# 그래서 아래 값들은 '몇 km 를 더 달리는 것과 같은가' 로 읽으면 된다.
#
# 이 값을 바꾸면 배차 성향이 바뀐다. 어떤 판으로 풀었는지 남겨야
# 나중에 'V1.2 가 V1.1 보다 나았나' 를 물을 수 있어서 버전을 함께 둔다.

# 두 번째 회차를 쓰는 값. 20km 를 더 달리는 것과 같다.
SECOND_RUN_PENALTY = 20_000
# 어르신 한 분을 배차에서 빼는 값. 10,000km 라 사실상 마지막 수단이다.
DROP_PENALTY = 10_000_000
# 전체 운행이 걸리는 시간(분)에 붙는 값. 1분을 2m 로 친다.
TIME_SPAN_COEFFICIENT = 2

# 차량 한 대가 도는 회차 수. 늘리면 더 많은 분을 태울 수 있지만 기사님이
# 그만큼 더 운행하신다. 그래서 기본값은 2 이고, 대안 분석기가 '3회차까지
# 돌면 되는가' 를 물을 때만 올려서 풀어 본다.
DEFAULT_TRIPS_PER_VEHICLE = 2

ENGINE_VERSION = "CARE_ENGINE_V2.1"
# v3.1 에서 휠체어 고정석 제약이 추가됐다. 제약이 바뀌면 결과도 바뀌므로
# 이 값을 올려야 예전 기록과 나란히 놓고 비교할 수 있다.
CONSTRAINT_VERSION = "CARE_CONSTRAINT_V3.1"
OBJECTIVE_VERSION = "CARE_OBJECTIVE_V2.1"


def trip_endpoints(
    home_node: int,
    round_number: int,
    trip_type: str,
    last_round: int = DEFAULT_TRIPS_PER_VEHICLE,
) -> tuple[int, int]:
    """이 회차가 어느 노드에서 떠나 어느 노드에서 끝나는지.

    home_node 는 자차 출발지 노드다. 센터 차량이면 0(센터)이라 아래 규칙이
    자동으로 '센터 → 센터'로 접힌다. 차량 종류로 분기하지 않는 이유다.

    등원 — 어르신을 센터로 모셔온다. 그래서 늘 센터에서 끝난다.
      자차 1회차   자택 → 센터      (기사님이 집에서 바로 출근길에 태운다)
      자차 2회차   센터 → 센터      (1회차를 마치고 센터에 있다)
      센터차량     센터 → 센터

    하원 — 어르신을 댁에 모셔다드린다. 그래서 늘 센터에서 떠난다.
      자차 1회차   센터 → 센터      (뒤 회차를 더 돌아야 하니 복귀한다)
      자차 마지막   센터 → 자택      (마지막 어르신을 내려드리고 퇴근한다)
      센터차량     센터 → 센터

    자차 하원에서 2회차를 돌지 않아도 기사님은 결국 집으로 간다. 그 빈 이동도
    거리 비용에 넣어 두면(ConsiderEmptyRouteCostsForVehicle) 솔버가 2회차를
    쓸지 말지를 그 비용까지 견줘서 정한다.
    """
    # '마지막 회차' 는 회차 수에 따라 달라진다. 3회차까지 도는 판에서는
    # 2회차가 아니라 3회차가 퇴근길이다.
    if trip_type == "outbound":
        return 0, (home_node if round_number == last_round else 0)
    return (home_node if round_number == 1 else 0), 0


def _reroute_to_end(
    stops: list[StopResult],
    node_of: dict[str, int],
    start_node: int,
    end_node: int,
    distance_m,
    travel_minutes,
    service: list[int],
    windows: dict[str, tuple[int, int]],
    settings: Settings,
) -> tuple[list[StopResult], int, int, int] | None:
    """같은 어르신들을 같은 차로, 다른 곳에서 끝나도록 다시 순서를 짠다.

    하원 자차가 한 회차만 돌 때 쓴다. 본 계산은 그 회차가 센터로 돌아온다고 보고
    순서를 정했는데, 실제로는 기사님이 마지막 어르신을 내려드리고 차고지로 퇴근한다.
    끝나는 곳이 달라지면 좋은 순서도 달라진다.

    어르신 몇 분짜리 작은 문제라 금방 풀린다. 풀리지 않으면 None 을 돌려주고
    부르는 쪽이 원래 순서를 그대로 쓴다.

    돌려주는 것: (다시 짠 정류장, 이동거리m, 출발시각분, 도착시각분)
    """
    if not stops:
        return None

    nodes = [start_node] + [node_of[s.passenger_id] for s in stops] + [end_node]
    local = {original: position for position, original in enumerate(nodes)}
    size = len(nodes)

    manager = pywrapcp.RoutingIndexManager(size, 1, [0], [size - 1])
    routing = pywrapcp.RoutingModel(manager)

    def distance(from_index, to_index):
        return distance_m[nodes[manager.IndexToNode(from_index)]][
            nodes[manager.IndexToNode(to_index)]
        ]

    routing.SetArcCostEvaluatorOfAllVehicles(
        routing.RegisterTransitCallback(distance)
    )

    def elapsed(from_index, to_index):
        a = nodes[manager.IndexToNode(from_index)]
        b = nodes[manager.IndexToNode(to_index)]
        return service[a] + travel_minutes[a][b]

    routing.AddDimension(
        routing.RegisterTransitCallback(elapsed), 24 * 60, 24 * 60, False, "Time"
    )
    time_dimension = routing.GetDimensionOrDie("Time")
    for stop in stops:
        low, high = windows[stop.passenger_id]
        time_dimension.CumulVar(
            manager.NodeToIndex(local[node_of[stop.passenger_id]])
        ).SetRange(low, high)
    time_dimension.CumulVar(routing.Start(0)).SetRange(0, 24 * 60)
    time_dimension.CumulVar(routing.End(0)).SetRange(0, 24 * 60)
    routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(0)))

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search.time_limit.FromSeconds(2)
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return None

    by_node = {node_of[s.passenger_id]: s for s in stops}
    ordered: list[StopResult] = []
    travelled = 0
    index = routing.Start(0)
    departure = solution.Value(time_dimension.CumulVar(index))
    while not routing.IsEnd(index):
        next_index = solution.Value(routing.NextVar(index))
        travelled += distance(index, next_index)
        node = nodes[manager.IndexToNode(next_index)]
        if node in by_node:
            stop = by_node[node]
            ordered.append(stop.model_copy(update={
                "sequence": len(ordered) + 1,
                "estimated_pickup": format_hhmm(
                    solution.Value(time_dimension.CumulVar(next_index))
                ),
            }))
        index = next_index
    arrival = solution.Value(time_dimension.CumulVar(index))
    return ordered, travelled, departure, arrival


def optimize_routes(
    request: OptimizeRequest,
    resolved: list[ResolvedLocation],
    settings: Settings,
    trips_per_vehicle: int = DEFAULT_TRIPS_PER_VEHICLE,
) -> OptimizeResponse:
    started = time.perf_counter()
    trip_type = request.trip_type
    # 하원 시각을 안 적은 어르신은 등원 시각 + 머무는 시간으로 계산한다.
    stay_minutes = round(settings.stay_hours * 60)
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
                wheelchair_capacity=vehicle.wheelchair_capacity,
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


    # 노드 0은 센터, 1..n은 어르신, 그 뒤는 자차 출발지.
    # 물리 차량 한 대당 두 개의 라우팅 차량(1·2회차)을 만들고,
    # 아래 제약으로 두 회차를 시간 순으로 묶는다.
    def is_passenger_node(node: int) -> bool:
        return 1 <= node <= passenger_count

    distance_m, travel_minutes = _matrices(resolved, settings)

    # 물리 차량 한 대당 라우팅 차량 두 개(1·2회차)를 만든다.
    rounds = tuple(range(1, trips_per_vehicle + 1))
    trip_specs = [(vehicle, round_number) for vehicle in vehicles for round_number in rounds]

    endpoints = [
        trip_endpoints(vehicle.start_node, round_number, trip_type, trips_per_vehicle)
        for vehicle, round_number in trip_specs
    ]
    trip_starts = [start for start, _ in endpoints]
    trip_ends = [end for _, end in endpoints]
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
    time_dimension.SetGlobalSpanCostCoefficient(TIME_SPAN_COEFFICIENT)

    passenger_windows: dict[str, tuple[int, int]] = {}
    for node, passenger in enumerate(request.passengers, start=1):
        index = manager.NodeToIndex(node)
        window_start, window_end = passenger.window(trip_type, stay_minutes)
        low, high = parse_hhmm(window_start), parse_hhmm(window_end)
        passenger_windows[passenger_ids[node - 1]] = (low, high)
        time_dimension.CumulVar(index).SetRange(low, high)

    for trip_index in range(len(trip_specs)):
        start_index = routing.Start(trip_index)
        end_index = routing.End(trip_index)
        time_dimension.CumulVar(start_index).SetRange(0, 24 * 60)
        time_dimension.CumulVar(end_index).SetRange(0, 24 * 60)
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(end_index))
        # 두 번째 회차는 값을 더 매겨 꼭 필요할 때만 쓰게 한다.
        # 회차를 더 쓸수록 비싸다. 1회차는 공짜, 2회차부터 한 번에 하나씩
        # 더 붙는다. 회차 수가 2일 때는 예전과 같은 값(0, 20000)이 된다.
        round_number = trip_specs[trip_index][1]
        routing.SetFixedCostOfVehicle(
            (round_number - 1) * SECOND_RUN_PENALTY, trip_index
        )
        # 출발지와 도착지가 다른 회차는, 어르신을 태우지 않아도 그 거리를 실제로 달린다.
        # 자차 하원 2회차가 그렇다. 이 비용을 세지 않으면 솔버는 그 이동을 공짜로 보고
        # 2회차를 쓸지 말지를 잘못 저울질한다.
        if trip_starts[trip_index] != trip_ends[trip_index]:
            routing.SetVehicleUsedWhenEmpty(True, trip_index)

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

    # 휠체어 고정석은 일반 좌석과 따로 센다.
    #
    # 어르신이 휠체어에서 내려 일반 좌석에 앉기도 하고 휠체어째 리프트석에
    # 고정하기도 한다. 두 가지를 한 숫자로 뭉뚱그리면 어느 쪽도 맞지 않아서
    # 차원을 하나 더 둔다.
    #
    # 리프트 없는 차량은 이 정원이 0 이다. 휠체어 어르신의 수요가 1 이므로
    # 0 을 넘게 되어 그 차에는 원천적으로 실리지 못한다. 적합성 제약을
    # 따로 걸 필요가 없다.
    wheelchair_demands = [0] + [
        1 if passenger.wheelchair else 0 for passenger in request.passengers
    ]
    wheelchair_demands += [0] * (len(resolved) - len(wheelchair_demands))

    def wheelchair_demand_callback(index: int) -> int:
        return wheelchair_demands[manager.IndexToNode(index)]

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(wheelchair_demand_callback),
        0,
        [spec.wheelchair_capacity for spec, _ in trip_specs],
        True,
        "Wheelchair",
    )

    solver = routing.solver()

    # 한 물리 차량의 회차들을 시간 순으로 묶는다.
    # 회차가 몇 개든 이웃한 두 개씩 이으면 전체가 한 줄로 이어진다.
    for vehicle_index in range(len(vehicles)):
        base = vehicle_index * trips_per_vehicle
        for offset in range(1, trips_per_vehicle):
            previous_trip = base + offset - 1
            this_trip = base + offset
            # 앞 회차를 쓰지 않으면서 뒤 회차만 쓰는 일은 없다.
            solver.Add(
                routing.ActiveVehicleVar(this_trip)
                <= routing.ActiveVehicleVar(previous_trip)
            )
            # 물리 차량은 한 대뿐이다. 앞 회차가 돌아와야 다음 회차가 나간다.
            solver.Add(
                time_dimension.CumulVar(routing.Start(this_trip))
                >= time_dimension.CumulVar(routing.End(previous_trip))
                + settings.turnaround_minutes
            )

    # 동승 규칙. VehicleVar는 '어느 운행(차량×회차)에 실렸는가'를 가리키므로,
    # 같으면 같은 차에 같은 회차로 함께 탄다는 뜻이다.
    # 회차가 다르면 차 안에서 마주치지 않으므로 '동승'으로 보지 않는다.
    for left, right in forbidden_pairs:
        left_index = manager.NodeToIndex(node_of_passenger[left])
        right_index = manager.NodeToIndex(node_of_passenger[right])
        different = solver.IsDifferentVar(
            routing.VehicleVar(left_index), routing.VehicleVar(right_index)
        )
        # 두 분이 모두 배차된 경우에만 '다른 차' 를 따진다.
        # 한 분이라도 빠졌으면 마주칠 일이 없다.
        solver.Add(
            routing.ActiveVar(left_index) * routing.ActiveVar(right_index) <= different
        )
    for left, right in required_pairs:
        solver.Add(
            routing.VehicleVar(manager.NodeToIndex(node_of_passenger[left]))
            == routing.VehicleVar(manager.NodeToIndex(node_of_passenger[right]))
        )

    # 정원이나 시간이 도저히 안 맞으면 전체를 포기하는 대신 그 어르신만 빼고 푼다.
    # 예전에는 422 를 던져서 원장님이 무엇을 고쳐야 할지 알 수 없었다.
    # 벌점은 어떤 경로 비용보다도 크게 둔다. 뺄 수 있으면 빼는 쪽이 싸 보이면 안 된다.
    for node in range(1, passenger_count + 1):
        routing.AddDisjunction([manager.NodeToIndex(node)], DROP_PENALTY)

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
    assigned_nodes: set[int] = set()

    def route_of(trip_index: int) -> list[int]:
        """그 운행이 실제로 들른 어르신 노드."""
        nodes = []
        index = routing.Start(trip_index)
        while not routing.IsEnd(index):
            index = solution.Value(routing.NextVar(index))
            node = manager.IndexToNode(index)
            if is_passenger_node(node):
                nodes.append(node)
        return nodes

    for physical_index, vehicle in enumerate(vehicles):
        trips: list[TripResult] = []
        for offset, round_number in enumerate(rounds):
            trip_index = physical_index * trips_per_vehicle + offset
            route_nodes: list[int] = []
            route_distance = 0
            index = routing.Start(trip_index)
            departure = solution.Value(time_dimension.CumulVar(index))
            while not routing.IsEnd(index):
                next_index = solution.Value(routing.NextVar(index))
                route_distance += distance_callback(index, next_index)
                node = manager.IndexToNode(next_index)
                # 어르신 노드는 1..n 뿐이다. 0(센터)과 그 뒤(자차 출발지·도착지)는 아니다.
                if is_passenger_node(node):
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
                    if not is_passenger_node(node):
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
                            requested_window="{}~{}".format(
                                *passenger.window(trip_type, stay_minutes)
                            ),
                            estimated_pickup=format_hhmm(pickup_minute),
                            kakao_navi_url=_kakao_navi_url(location),
                        )
                    )
            assigned_nodes.update(route_nodes)
            total_distance += route_distance
            start_node, end_node = endpoints[trip_index]
            origin, destination = resolved[start_node], resolved[end_node]
            trips.append(
                TripResult(
                    round=round_number,
                    used=used,
                    origin_name=origin.name,
                    origin_latitude=origin.latitude,
                    origin_longitude=origin.longitude,
                    destination_name=destination.name,
                    destination_latitude=destination.latitude,
                    destination_longitude=destination.longitude,
                    passenger_count=len(route_nodes),
                    capacity=vehicle.capacity,
                    departure_time=format_hhmm(departure) if used else None,
                    return_time=format_hhmm(return_time) if used else None,
                    distance_km=round(route_distance / 1000, 1),
                    stops=stops,
                )
            )
        # 하원 자차가 한 회차만 돌았다면, 그 회차가 마지막 회차다.
        # 기사님은 센터로 돌아가는 것이 아니라 차고지로 퇴근한다.
        #
        # 본 계산에서 도착지를 미리 못 박을 수 없어서(몇 회차가 마지막인지는
        # 풀어봐야 안다) 2회차를 차고지로 두고 풀었다. 여기서 실제 결과를 보고
        # 옮긴다. 끝나는 곳이 달라지면 좋은 순서도 달라지므로 순서도 다시 짠다.
        # 마지막으로 실제 운행한 회차가 퇴근길이다. 몇 번째가 될지는
        # 풀어봐야 알기에 마지막 회차를 차고지로 두고 풀었고, 여기서 옮긴다.
        used_indexes = [i for i, trip in enumerate(trips) if trip.used]
        last_used = used_indexes[-1] if used_indexes else None
        needs_repair = (
            trip_type == "outbound"
            and vehicle.start_node != 0
            and last_used is not None
            and last_used != len(trips) - 1
        )
        if needs_repair:
            repaired = _reroute_to_end(
                trips[last_used].stops, node_of_passenger, 0, vehicle.start_node,
                distance_m, travel_minutes, service, passenger_windows, settings,
            )
            garage = resolved[vehicle.start_node]
            if repaired:
                ordered, travelled, departure, arrival = repaired
                total_distance += travelled - round(trips[last_used].distance_km * 1000)
                trips[last_used] = trips[last_used].model_copy(update={
                    "stops": ordered,
                    "distance_km": round(travelled / 1000, 1),
                    "departure_time": format_hhmm(departure),
                    "return_time": format_hhmm(arrival),
                    "destination_name": garage.name,
                    "destination_latitude": garage.latitude,
                    "destination_longitude": garage.longitude,
                })
            else:
                # 다시 짜는 데 실패해도 도착지는 사실대로 적는다.
                trips[last_used] = trips[last_used].model_copy(update={
                    "destination_name": garage.name,
                    "destination_latitude": garage.latitude,
                    "destination_longitude": garage.longitude,
                })
            # 쓰지 않은 뒤 회차가 '센터 → 차고지' 로 남으면 여러 번 퇴근하는
            # 것처럼 보인다. 안 쓴 회차는 전부 센터에서 끝나는 것으로 적는다.
            for idx in range(last_used + 1, len(trips)):
                trips[idx] = trips[idx].model_copy(update={
                    "destination_name": resolved[0].name,
                    "destination_latitude": resolved[0].latitude,
                    "destination_longitude": resolved[0].longitude,
                })

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

    notices = [
        "모든 예상 시각은 요청 시간창 안에 있으며 차량별 운행은 최대 "
        f"{trips_per_vehicle}회입니다.",
    ]
    self_drive = [v.plate_number for v in vehicles if v.start_node != 0]
    if self_drive:
        plates = ", ".join(self_drive)
        if trip_type == "outbound":
            notices.append(
                f"자차 송영 차량({plates})은 센터에서 출발하고 마지막 회차를 마치면"
                " 기사님 자택(차고지)으로 퇴근합니다."
            )
        else:
            notices.append(
                f"자차 송영 차량({plates})은 1회차를 지정된 출발지에서 시작하고"
                " 센터로 복귀합니다."
            )
    notices.append(
        "MVP의 이동시간은 직선거리×도로계수와 평균속도로 산정됩니다."
        " 운영 전 실시간 도로 시간행렬 연동을 권장합니다."
    )

    # 배차에 못 넣은 어르신을 모은다.
    # 전체를 실패로 돌리는 대신 여기에 담아 보내면, 원장님이 무엇을 고쳐야
    # 하는지 알 수 있고 나머지 배차는 그대로 쓸 수 있다.
    # 휠체어 고정석이 모자라서 빠진 것인지, 정원·시간이 안 맞아서 빠진 것인지
    # 갈라 준다. 원장님이 리프트 차량을 불러야 하는지 시간을 넓혀야 하는지
    # 알 수 없으면 안내가 없는 것과 같다.
    wheelchair_seats = sum(spec.wheelchair_capacity for spec in vehicles)
    wheelchair_riders = sum(1 for p in request.passengers if p.wheelchair)
    unassigned = []
    for node in range(1, passenger_count + 1):
        if node in assigned_nodes:
            continue
        passenger = request.passengers[node - 1]
        # 휠체어를 쓰는 분인데 고정석 총량이 이미 다 찼거나 아예 없으면
        # 시간을 넓혀도 해결되지 않는다. 차량 문제다.
        blocked_by_lift = (
            passenger.wheelchair and wheelchair_seats < wheelchair_riders
        )
        unassigned.append(
            UnassignedPassenger(
                passenger_id=passenger_ids[node - 1],
                name=passenger.name,
                requested_window="{}~{}".format(
                    *passenger.window(trip_type, stay_minutes)
                ),
                reason="wheelchair" if blocked_by_lift else "capacity",
                wheelchair=passenger.wheelchair,
            )
        )

    if unassigned:
        lift_short = [i for i in unassigned if i.reason == "wheelchair"]
        plain = [i for i in unassigned if i.reason == "capacity"]
        # 사유가 다르면 고칠 방법도 다르므로 문구를 나눠 넣는다.
        if plain:
            names = ", ".join(item.name for item in plain)
            notices.insert(
                0,
                f"{len(plain)}명을 배차하지 못했습니다: {names}."
                " 시간 범위를 넓히거나 차량(또는 회차)을 늘린 뒤 다시 계산해 주세요.",
            )
        if lift_short:
            names = ", ".join(item.name for item in lift_short)
            detail = (
                "휠체어 고정석이 있는 차량이 없습니다"
                if wheelchair_seats == 0
                else f"휠체어 고정석이 {wheelchair_seats}자리뿐입니다"
            )
            notices.insert(
                0,
                f"휠체어 이용 {len(lift_short)}명을 배차하지 못했습니다: {names}."
                f" {detail}. 차량 관리에서 휠체어 전용 좌석 수를 확인해 주세요.",
            )

    # 솔버가 무엇을 얼마나 비싸게 봤는지 같은 계수로 다시 계산한다.
    # OR-Tools 는 총합만 주고 항목별로는 나눠주지 않는다.
    used_trips = [t for v in vehicle_results for t in v.trips if t.used]
    # 2회차 이상은 모두 추가 회차다. 3회차를 도는 판에서는 두 번 세어야 한다.
    second_runs = sum(t.round - 1 for t in used_trips if t.round > 1)
    minutes = [
        parse_hhmm(value)
        for t in used_trips
        for value in (t.departure_time, t.return_time)
        if value
    ]
    span = (max(minutes) - min(minutes)) if minutes else 0
    breakdown = ObjectiveBreakdown(
        distance_m=total_distance,
        second_run_count=second_runs,
        second_run_penalty=second_runs * SECOND_RUN_PENALTY,
        time_span_minutes=span,
        time_span_penalty=span * TIME_SPAN_COEFFICIENT,
        unassigned_count=len(unassigned),
        unassigned_penalty=len(unassigned) * DROP_PENALTY,
    )
    breakdown.total = (
        breakdown.distance_m
        + breakdown.second_run_penalty
        + breakdown.time_span_penalty
        + breakdown.unassigned_penalty
    )

    return OptimizeResponse(
        trip_type=trip_type,
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
        notices=notices,
        unassigned_passengers=unassigned,
        objective_breakdown=breakdown,
    )
