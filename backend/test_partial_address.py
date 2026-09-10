"""v4.1.3 검증: 주소 하나 때문에 전체가 막히지 않는다.

현장에서 40명 명단 중 한 분의 번지가 카카오 지도에 없어 배차가 통째로
거절됐다. 카카오와 네이버는 주소 DB 가 달라서, 네이버에 있는 번지가
카카오에 없는 경우가 실제로 있다.

한 분을 못 찾았다고 마흔 분을 못 태우면 안 된다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_partial_address.py
  (실제 카카오 API 를 부른다.)
"""
import asyncio

from dotenv import load_dotenv

load_dotenv()

from fastapi import HTTPException  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import run_optimization  # noqa: E402
from app.models import OptimizeRequest  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()
GOOD = [
    ("정상가", "경남 창원시 성산구 중앙대로 151"),
    ("정상나", "경남 창원시 성산구 원이대로 579번길 13"),
    ("정상다", "창원 용지아이파크"),
]
BAD = ("주소불량", "창원시 성산구 원이대로 682")   # 카카오에 없는 번지


def build(people, center="경남 창원시 성산구 중앙대로 151"):
    return OptimizeRequest.model_validate({
        "trip_type": "inbound",
        "center": {"name": "검증센터", "address": center},
        "vehicles": [{"id": "pv1", "vehicle_type": "스타리아",
                      "plate_number": "00검0001", "capacity": 9}],
        "passengers": [
            {"id": f"pa{i}", "name": n, "address": a}
            for i, (n, a) in enumerate(people, start=1)
        ],
    })


def run(request):
    return asyncio.run(run_optimization(request, S))


# ---------------------------------------------------------------------------
print("=== 1. 전원 정상이면 그대로 배차된다 ===")
result = run(build(GOOD))
check("3명 전원 배차", not result.unassigned_passengers,
      [i.passenger_id for i in result.unassigned_passengers])


print()
print("=== 2. 한 분 주소가 나빠도 나머지는 배차된다 (핵심) ===")
print(f"   {BAD[0]} — {BAD[1]} (카카오에 없는 번지)")
result = run(build([*GOOD, BAD]))

assigned = {
    stop.passenger_id
    for v in result.vehicles for t in v.trips if t.used for stop in t.stops
}
check("정상 3명은 배차됐다", len(assigned) == 3, sorted(assigned))
check("전체가 거절되지 않았다", result.status == "optimal_or_feasible", result.status)

dropped = result.unassigned_passengers
check("주소 불량 한 분이 배차 불가 목록에 있다", len(dropped) == 1, len(dropped))
if dropped:
    item = dropped[0]
    check("이름이 들어 있다", item.name == BAD[0], item.name)
    check("사유가 address 다", item.reason == "address", item.reason)
    check("어떤 주소였는지 보여 준다", BAD[1] in item.requested_window,
          item.requested_window)

notice = [n for n in result.notices if "찾지 못했습니다" in n]
check("안내 문구가 나온다", bool(notice))
if notice:
    print()
    print("   실제 문구:")
    for line in notice[0].split("\n"):
        print("     " + line)


print()
print("=== 3. 여러 명이 나빠도 마찬가지다 ===")
result = run(build([*GOOD, BAD, ("또다른불량", "없는시 없는구 없는로 999")]))
dropped = [i for i in result.unassigned_passengers if i.reason == "address"]
check("두 분 모두 목록에 있다", len(dropped) == 2, len(dropped))
check("나머지 3명은 여전히 배차된다",
      result.total_passengers == 3, result.total_passengers)


print()
print("=== 4. 센터 주소가 나쁘면 이건 거절한다 ===")
print("   센터가 빠지면 배차 자체가 성립하지 않는다.")
try:
    run(build(GOOD, center="없는시 없는구 없는로 999"))
    check("거절한다", False, "예외가 나지 않았다")
except HTTPException as error:
    check("422 로 거절한다", error.status_code == 422, error.status_code)
    check("센터 문제라고 말한다", "센터 주소" in error.detail, error.detail[:40])
    print("   문구:", error.detail.split("\n")[0])


print()
print("=== 5. 동승 규칙이 못 찾은 분을 가리켜도 터지지 않는다 ===")
request = OptimizeRequest.model_validate({
    "trip_type": "inbound",
    "center": {"name": "검증센터", "address": "경남 창원시 성산구 중앙대로 151"},
    "vehicles": [{"id": "pv1", "vehicle_type": "스타리아",
                  "plate_number": "00검0001", "capacity": 9}],
    "passengers": [
        {"id": "pa1", "name": GOOD[0][0], "address": GOOD[0][1]},
        {"id": "pa2", "name": GOOD[1][0], "address": GOOD[1][1]},
        {"id": "pa3", "name": BAD[0], "address": BAD[1]},
    ],
    "required_pairs": [{"passenger_ids": ["pa1", "pa3"]}],
})
try:
    result = run(request)
    check("500 이 나지 않는다", True)
    check("나머지 2명은 배차된다", result.total_passengers == 2, result.total_passengers)
except Exception as error:  # noqa: BLE001
    check("500 이 나지 않는다", False, f"{type(error).__name__}: {error}")


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
