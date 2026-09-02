"""Phase 2 검증: 최적화 이력 / 목적함수 항목별 재계산 / 배차안 비교.

DB 에 쓰지 않는다. 저장 함수는 가짜 Supabase 로 바꿔서 무엇을 보내려 했는지만 본다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_run_history.py
"""
import datetime as dt
import json

from app.config import get_settings
from app.geocoding import ResolvedLocation
from app.models import OptimizeRequest, OptimizeResponse
from app.optimizer import (
    DROP_PENALTY,
    SECOND_RUN_PENALTY,
    TIME_SPAN_COEFFICIENT,
    optimize_routes,
)
from app.plan_diff import compare_plans
import app.runs as runs

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


CENTER = ResolvedLocation(name="행복센터", address="센터주소",
                          latitude=37.500, longitude=127.000)


def build(count, capacity=9, window=("08:00", "10:00"), vehicles=1):
    people = [
        {"id": f"p{i}", "name": f"어르신{i}", "address": f"어르신주소{i}",
         "detail_address": "101동 1502호", "guardian_phone": "010-1234-5678",
         "latitude": 37.500 + i * 0.004, "longitude": 127.000 + i * 0.004,
         "pickup_start": window[0], "pickup_end": window[1]}
        for i in range(1, count + 1)
    ]
    fleet = [
        {"id": f"veh{v}", "vehicle_type": "스타리아",
         "plate_number": f"{v + 1}{v + 1}가{v + 1}{v + 1}{v + 1}{v + 1}",
         "driver_name": f"기사{v + 1}", "driver_phone": "010-1111-2222",
         "capacity": capacity}
        for v in range(vehicles)
    ]
    request = OptimizeRequest.model_validate({
        "trip_type": "inbound",
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.500, "longitude": 127.000},
        "vehicles": fleet, "passengers": people,
    })
    resolved = [CENTER] + [
        ResolvedLocation(name=p["name"], address=p["address"],
                         latitude=p["latitude"], longitude=p["longitude"])
        for p in people
    ]
    return request, optimize_routes(request, resolved, get_settings())


# ---------------------------------------------------------------------------
print("=== 1. 목적함수 항목별 재계산 ===")
print("   솔버는 총합만 준다. 같은 계수로 다시 계산한 값이 맞는지 본다.")

request, result = build(5)
bd = result.objective_breakdown
check("objective_breakdown 이 채워진다", bd is not None)
# km 필드는 소수점 한 자리로 반올림된 값이다. breakdown 이 정확한 미터를 갖는다.
check("거리가 결과의 총거리와 맞는다",
      abs(bd.distance_m / 1000 - result.total_distance_km) < 0.05,
      f"{bd.distance_m}m vs {result.total_distance_km}km")
check("2회차 벌점 = 2회차 수 x 상수",
      bd.second_run_penalty == bd.second_run_count * SECOND_RUN_PENALTY,
      f"{bd.second_run_count}회 -> {bd.second_run_penalty}")
check("소요시간 벌점 = 분 x 상수",
      bd.time_span_penalty == bd.time_span_minutes * TIME_SPAN_COEFFICIENT,
      f"{bd.time_span_minutes}분 -> {bd.time_span_penalty}")
check("합계가 항목의 합과 같다",
      bd.total == (bd.distance_m + bd.second_run_penalty
                   + bd.time_span_penalty + bd.unassigned_penalty),
      bd.total)
check("전원 배차된 판에서는 제외 벌점이 0", bd.unassigned_penalty == 0)

print()
print("=== 2. 배차 불가가 있으면 그만큼 벌점이 잡힌다 ===")
print("   9명을 4석 한 대로. 창이 좁아 못 태우는 분이 생긴다.")
_, tight = build(9, capacity=4, window=("08:00", "08:40"))
tb = tight.objective_breakdown
check("제외된 분 수가 unassigned_passengers 와 같다",
      tb.unassigned_count == len(tight.unassigned_passengers),
      f"{tb.unassigned_count}명")
check("제외 벌점 = 인원 x 상수",
      tb.unassigned_penalty == tb.unassigned_count * DROP_PENALTY,
      tb.unassigned_penalty)

print()
print("=== 3. 스냅샷에 개인정보가 남지 않는다 ===")
print("   이름·연락처·상세주소는 빼고 좌표는 남긴다.")

snap_in = runs.build_input_snapshot(request)
snap_out = runs.build_result_snapshot(result)
blob = json.dumps([snap_in, snap_out], ensure_ascii=False)

check("어르신 이름이 없다", "어르신1" not in blob)
check("보호자 번호가 없다", "010-1234-5678" not in blob)
check("기사 이름이 없다", "기사1" not in blob)
check("기사 번호가 없다", "010-1111-2222" not in blob)
check("상세주소가 없다", "101동 1502호" not in blob)
check("도로명 주소가 없다", "어르신주소1" not in blob)

check("어르신 id 는 남는다", snap_in["passengers"][0]["id"] == "p1")
check("좌표는 남는다", snap_in["passengers"][0]["latitude"] == 37.504,
      snap_in["passengers"][0]["latitude"])
check("시간창은 남는다", snap_in["passengers"][0]["pickup_start"] == "08:00")
check("센터 좌표는 남는다", snap_in["center"]["latitude"] == 37.500)
check("경로 정류장 좌표는 남는다",
      snap_out["vehicles"][0]["trips"][0]["stops"][0].get("latitude") is not None)

print()
print("=== 4. 저장이 실패해도 배차는 그대로 나간다 ===")
print("   표가 없거나 Supabase 가 죽어도 None 만 돌아와야 한다.")


class Boom:
    def table(self, *_args, **_kwargs):
        raise RuntimeError('relation "public.optimization_runs" does not exist')


original_client = runs.get_supabase
runs.get_supabase = lambda: Boom()
try:
    run_id = runs.record_optimization_run(
        request, result, dt.date(2026, 9, 2), get_settings()
    )
    check("예외를 삼키고 None 을 준다", run_id is None, run_id)
finally:
    runs.get_supabase = original_client


print()
print("=== 5. 무엇을 저장하려 했는지 ===")

captured = {}


class Fake:
    def table(self, name):
        captured["table"] = name
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def insert(self, row):
        captured["row"] = row
        return self

    def execute(self):
        # 앞선 select 는 빈 결과(=첫 계산), insert 는 id 를 돌려준다.
        if "row" in captured:
            return type("R", (), {"data": [{"id": "run-uuid-0001"}]})()
        return type("R", (), {"data": []})()


runs.get_supabase = lambda: Fake()
try:
    run_id = runs.record_optimization_run(
        request, result, dt.date(2026, 9, 2), get_settings()
    )
finally:
    runs.get_supabase = original_client

row = captured.get("row", {})
check("optimization_runs 에 넣는다", captured.get("table") == "optimization_runs")
check("id 를 돌려준다", run_id == "run-uuid-0001", run_id)
check("center_id 가 들어간다", row.get("center_id") == get_settings().center_id)
check("첫 계산은 run_sequence 1", row.get("run_sequence") == 1)
check("엔진 버전이 들어간다", str(row.get("engine_version", "")).startswith("CARE_ENGINE"),
      row.get("engine_version"))
check("어떤 계수로 풀었는지 남는다",
      row.get("config", {}).get("second_run_penalty") == SECOND_RUN_PENALTY)
check("배차된 인원 = 전체 - 제외",
      row.get("assigned_count") == result.total_passengers - len(result.unassigned_passengers))
check("총거리는 미터로 남는다", row.get("total_distance_m") == bd.distance_m)


print()
print("=== 6. 원안과 최종안 비교 ===")
print("   아직 손으로 고치는 화면은 없다. 계산하는 쪽만 먼저 확인한다.")

same = compare_plans(result, result)
check("고친 것이 없으면 is_human_modified 가 False", same.is_human_modified is False)
check("바뀐 차량 0", same.vehicle_reassignment_count == 0)
check("바뀐 순서 0", same.stop_reorder_count == 0)

# 두 대짜리 판에서 한 분을 다른 차로 옮겨 본다.
_, two_car = build(6, capacity=3, vehicles=2)
edited = OptimizeResponse.model_validate(two_car.model_dump())
# 한 분을 뽑아 '다른 차량' 으로 옮긴다. 같은 차에 도로 넣으면 변경이 아니다.
moved = None
source_vehicle_id = None
for vehicle in edited.vehicles:
    for trip in vehicle.trips:
        if trip.used and len(trip.stops) > 1:
            moved = trip.stops.pop()
            source_vehicle_id = vehicle.vehicle_id
            break
    if moved:
        break

target_trip = None
if moved:
    for vehicle in edited.vehicles:
        if vehicle.vehicle_id == source_vehicle_id:
            continue
        for trip in vehicle.trips:
            if trip.used:
                target_trip = trip
                break
        if target_trip:
            break

if moved and target_trip:
    target_trip.stops.append(moved)

    diff = compare_plans(two_car, edited)
    check("옮기면 is_human_modified 가 True", diff.is_human_modified is True)
    check("옮긴 인원이 1명으로 잡힌다", diff.vehicle_reassignment_count == 1,
          diff.vehicle_reassignment_count)
    check("누가 옮겨졌는지 id 로 남는다",
          diff.reassigned_passenger_ids == [moved.passenger_id],
          diff.reassigned_passenger_ids)
else:
    check("옮길 어르신과 받을 차량을 찾았다", False,
          f"moved={moved is not None} target={target_trip is not None}")

# 같은 차 안에서 순서만 바꾼다.
reordered = OptimizeResponse.model_validate(two_car.model_dump())
for vehicle in reordered.vehicles:
    for trip in vehicle.trips:
        if trip.used and len(trip.stops) > 1:
            trip.stops[0], trip.stops[1] = trip.stops[1], trip.stops[0]
            break
    else:
        continue
    break
order_diff = compare_plans(two_car, reordered)
check("순서만 바꾸면 차량 변경은 0", order_diff.vehicle_reassignment_count == 0)
check("순서 변경이 2건으로 잡힌다", order_diff.stop_reorder_count == 2,
      order_diff.stop_reorder_count)


print()
print("=== 7. 하위 호환 ===")
print("   구형 프론트가 보내던 모양이 그대로 통해야 한다.")

legacy = result.model_dump(mode="json")
legacy.pop("optimization_run_id", None)
legacy.pop("objective_breakdown", None)
try:
    restored = OptimizeResponse.model_validate(legacy)
    check("새 필드가 없는 응답도 읽힌다", True)
    check("없으면 None 이다", restored.optimization_run_id is None)
    check("breakdown 도 None 이다", restored.objective_breakdown is None)
except Exception as error:  # noqa: BLE001
    check("새 필드가 없는 응답도 읽힌다", False, error)

check("응답에 optimization_run_id 칸이 생겼다",
      "optimization_run_id" in result.model_dump(mode="json"))
check("v2.1 필드는 그대로 있다",
      all(key in legacy for key in
          ("trip_type", "total_passengers", "total_distance_km",
           "vehicles", "notices", "unassigned_passengers")))


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
