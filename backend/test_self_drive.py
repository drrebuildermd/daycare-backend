"""자차 송영(차량별 출발지) 검증.

좌표를 직접 넣어 카카오 지오코딩을 타지 않는다.
실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_self_drive.py
"""
import sys

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest
from app.optimizer import optimize_routes

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


# 센터는 원점. 어르신은 동쪽 일렬. 자차 출발지는 훨씬 더 동쪽에 둔다.
# 자차 차량이 정말 자기 출발지에서 시작하면 '가장 먼 어르신부터' 태우게 된다.
CENTER = {"name": "센터", "address": "센터", "latitude": 35.30, "longitude": 129.00}
PEOPLE = [
    ("P001", "가까운어르신", 35.30, 129.02),
    ("P002", "중간어르신", 35.30, 129.04),
    ("P003", "먼어르신", 35.30, 129.06),
]
HOME = (35.30, 129.10)  # 기사님 자택. 모든 어르신보다 동쪽.


def passenger(pid, name, lat, lng):
    return {
        "id": pid, "name": name, "address": f"{name} 자택",
        "latitude": lat, "longitude": lng,
        "pickup_start": "07:00", "pickup_end": "10:00", "wheelchair": False,
    }


def build(vehicle_extra):
    base = {
        "id": "v1", "vehicle_type": "스타렉스", "plate_number": "12가3456",
        "driver_name": "홍길동", "capacity": 5,
    }
    base.update(vehicle_extra)
    return OptimizeRequest.model_validate({
        "center": CENTER,
        "vehicles": [base],
        "passengers": [passenger(*p) for p in PEOPLE],
    })


def resolve_for(request):
    """main.py 와 같은 순서로 노드를 만든다: 센터, 어르신들, 자차 출발지."""
    nodes = [ResolvedLocation("센터", "센터", CENTER["latitude"], CENTER["longitude"])]
    nodes += [ResolvedLocation(n, f"{n} 자택", lat, lng) for _, n, lat, lng in PEOPLE]
    for vehicle in request.vehicles:
        location = vehicle.as_start_location()
        if location is not None:
            nodes.append(ResolvedLocation(
                location.name, location.address, HOME[0], HOME[1]))
    return nodes


settings = get_settings()

print("=== 1. 기준: 센터 출발 (기존 동작) ===")
req = build({})
result = optimize_routes(req, resolve_for(req), settings)
trip1 = result.vehicles[0].trips[0]
order_center = [s.name for s in trip1.stops]
check("배차 성공", bool(order_center), order_center)
check("출발지가 센터로 보고됨", result.vehicles[0].start_name == "센터",
      result.vehicles[0].start_name)
print(f"     1회차 순서: {' -> '.join(order_center)}")
dist_center = trip1.distance_km

print("\n=== 2. 자차 송영: 기사님 자택에서 출발 ===")
req = build({
    "start_type": "custom",
    "start_address": "경남 양산시 기사님댁",
})
resolved = resolve_for(req)
check("출발지 노드가 어르신 뒤에 붙음", len(resolved) == 1 + len(PEOPLE) + 1, len(resolved))
result = optimize_routes(req, resolved, settings)
vehicle = result.vehicles[0]
trip1 = vehicle.trips[0]
order_home = [s.name for s in trip1.stops]
print(f"     1회차 순서: {' -> '.join(order_home)}")

check("배차 성공", bool(order_home))
check("전원 배차됨", len(order_home) == 3, len(order_home))
check("출발지가 자택으로 보고됨", vehicle.start_name == "12가3456 출발지",
      vehicle.start_name)
check("출발지 좌표가 자택", (vehicle.start_latitude, vehicle.start_longitude) == HOME,
      (vehicle.start_latitude, vehicle.start_longitude))
# 자택이 가장 동쪽이므로, 거기서 출발하면 먼 어르신부터 태우고 센터로 와야 한다.
check("자택에서 출발해 먼 어르신부터 태움", order_home[0] == "먼어르신", order_home[0])
check("센터 출발과 순서가 달라짐", order_home != order_center,
      f"센터출발 {order_center} vs 자차 {order_home}")

print("\n=== 3. 출발지 노드가 방문지로 잡히지 않는지 ===")
all_stops = [s.name for v in result.vehicles for t in v.trips for s in t.stops]
check("출발지가 어르신 명단에 섞이지 않음",
      not any("출발지" in n for n in all_stops), all_stops)
check("어르신 3명만 방문", len(all_stops) == 3, len(all_stops))

print("\n=== 4. 2회차는 센터에서 출발 ===")
# 정원을 줄여 2회차가 생기게 한다.
req = build({"start_type": "custom", "start_address": "경남 양산시 기사님댁", "capacity": 2})
result = optimize_routes(req, resolve_for(req), settings)
used = [t for t in result.vehicles[0].trips if t.used]
check("2회차가 생성됨", len(used) == 2, [t.round for t in used])
check("안내문에 자차 송영 설명 포함",
      any("자차 송영" in n for n in result.notices),
      [n[:40] for n in result.notices])

print("\n=== 5. 자차 설정인데 주소가 없으면 거절 ===")
try:
    build({"start_type": "custom"})
    check("주소 없는 자차 설정 거절", False, "예외가 발생하지 않음")
except Exception as error:  # noqa: BLE001
    check("주소 없는 자차 설정 거절", True, str(error).split("\n")[-2].strip()[:60])

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 자차 송영이 배차 동선에 정확히 반영됩니다.")
