"""동승 규칙 / 출석 / 담당기사 동작 확인용 스크립트.

좌표를 직접 넣어 카카오 지오코딩을 타지 않는다.
실행: .venv\\Scripts\\python.exe test_pair_rules.py
"""
import sys

from fastapi.testclient import TestClient

import app.main as main

CENTER = {
    "name": "행복주야간보호센터",
    "address": "양산시청",
    "latitude": 35.3350,
    "longitude": 129.0371,
}

PEOPLE = [
    ("P001", "김어르신", 35.3480, 129.0290),
    ("P002", "이어르신", 35.3390, 129.0510),
    ("P003", "박어르신", 35.3210, 129.0330),
    ("P004", "최어르신", 35.3600, 129.0450),
]


def passenger(pid, name, lat, lng, attending=True):
    return {
        "id": pid, "name": name, "address": f"{name} 자택",
        "latitude": lat, "longitude": lng, "attending": attending,
        "pickup_start": "08:00", "pickup_end": "09:30", "wheelchair": False,
    }


def build(vehicles, people, forbidden=(), required=()):
    return {
        "center": CENTER,
        "vehicles": vehicles,
        "passengers": people,
        "forbidden_pairs": [{"passenger_ids": list(p)} for p in forbidden],
        "required_pairs": [{"passenger_ids": list(p)} for p in required],
    }


def trip_of(result):
    """어르신 id -> (차량번호, 회차) 매핑."""
    placement = {}
    for vehicle in result["vehicles"]:
        for trip in vehicle["trips"]:
            for stop in trip["stops"]:
                placement[stop["passenger_id"]] = (vehicle["plate_number"], trip["round"])
    return placement


VEHICLES_2 = [
    {"id": "v1", "vehicle_type": "스타리아", "plate_number": "12가3456",
     "driver_name": "명민승", "capacity": 2},
    {"id": "v2", "vehicle_type": "카니발", "plate_number": "34나7890",
     "driver_name": "김철수", "capacity": 2},
]

failures = []


def check(label, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{(' -> ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


with TestClient(main.app) as client:
    people = [passenger(*p) for p in PEOPLE]

    print("--- 1. 기준: 규칙 없음 ---")
    r = client.post("/api/optimize", json=build(VEHICLES_2, people))
    check("배차 성공", r.status_code == 200, f"HTTP {r.status_code}")
    base = trip_of(r.json())
    check("4명 전원 배차됨", len(base) == 4, str(len(base)))
    check("담당 기사 이름 전달",
          all(v.get("driver_name") for v in r.json()["vehicles"]),
          str([v.get("driver_name") for v in r.json()["vehicles"]]))

    print("--- 2. 동승 불가: 기준 배차에서 같이 탔던 두 명을 떼어놓기 ---")
    together = [
        (a, b) for a in base for b in base
        if a < b and base[a] == base[b]
    ]
    if not together:
        print("  SKIP  기준 배차에 같은 운행에 탄 조합이 없어 검증 불가")
    else:
        pair = together[0]
        r = client.post("/api/optimize", json=build(VEHICLES_2, people, forbidden=[pair]))
        check("동승 불가 배차 성공", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            placed = trip_of(r.json())
            check(f"{pair[0]}/{pair[1]} 가 서로 다른 운행에 배치됨",
                  placed[pair[0]] != placed[pair[1]],
                  f"{placed[pair[0]]} vs {placed[pair[1]]}")

    print("--- 3. 필수 동승: 기준 배차에서 떨어져 있던 두 명을 붙이기 ---")
    apart = [
        (a, b) for a in base for b in base
        if a < b and base[a] != base[b]
    ]
    if not apart:
        print("  SKIP  기준 배차에 떨어진 조합이 없어 검증 불가")
    else:
        pair = apart[0]
        r = client.post("/api/optimize", json=build(VEHICLES_2, people, required=[pair]))
        check("필수 동승 배차 성공", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            placed = trip_of(r.json())
            check(f"{pair[0]}/{pair[1]} 가 같은 운행에 배치됨",
                  placed[pair[0]] == placed[pair[1]],
                  f"{placed[pair[0]]} vs {placed[pair[1]]}")

    print("--- 4. 전이 규칙: A-B, B-C 짝꿍이면 셋 다 같은 차 (정원 2 초과) ---")
    r = client.post("/api/optimize", json=build(
        VEHICLES_2, people, required=[("P001", "P002"), ("P002", "P003")]))
    check("정원 초과를 422로 거절", r.status_code == 422, f"HTTP {r.status_code}")
    if r.status_code == 422:
        check("메시지에 3명이 묶였다는 설명 포함", "3명" in r.json()["detail"],
              r.json()["detail"][:60])

    print("--- 5. 모순 규칙: 같은 두 명이 짝꿍이면서 기피 ---")
    r = client.post("/api/optimize", json=build(
        VEHICLES_2, people, forbidden=[("P001", "P002")], required=[("P001", "P002")]))
    check("모순을 422로 거절", r.status_code == 422, f"HTTP {r.status_code}")

    print("--- 6. 결석 처리 ---")
    with_absent = [passenger(*PEOPLE[0], attending=False)] + [passenger(*p) for p in PEOPLE[1:]]
    r = client.post("/api/optimize", json=build(VEHICLES_2, with_absent))
    check("배차 성공", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        placed = trip_of(r.json())
        check("결석자가 배차에서 빠짐", "P001" not in placed, str(sorted(placed)))
        check("출석 3명만 배차됨", len(placed) == 3, str(len(placed)))
        check("미탑승 안내문구 추가됨",
              any("미탑승" in n for n in r.json()["notices"]),
              str(r.json()["notices"]))

    print("--- 7. 결석자를 가리키는 규칙은 거절 ---")
    r = client.post("/api/optimize", json=build(
        VEHICLES_2, with_absent, required=[("P001", "P002")]))
    check("422로 거절", r.status_code == 422, f"HTTP {r.status_code}")

    print("--- 8. 전원 결석 ---")
    r = client.post("/api/optimize", json=build(
        VEHICLES_2, [passenger(*p, attending=False) for p in PEOPLE]))
    check("422로 거절", r.status_code == 422, f"HTTP {r.status_code}")

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과")
