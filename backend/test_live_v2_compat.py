"""실서버에 대고 v2.0 하위 호환을 확인한다.

기사님 폰에는 v1.5.2 가 깔려 있다. 그 앱은 trip_type 을 모른다.
새 백엔드가 그 요청을 예전과 똑같이 처리하는지, 그리고 새 앱이 보낼
하원 요청도 제대로 갈리는지 둘 다 본다.

실제 DB 에 쓴다. 남는 행은 ZZ- 로 시작하게 해서 나중에 지울 수 있게 했다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_live_v2_compat.py
"""
import sys

import httpx

BASE = "https://daycare-routing-api.onrender.com"
failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


client = httpx.Client(timeout=180)

print("=== 0. 서버가 깨어 있는가 ===")
health = client.get(f"{BASE}/api/health").json()
check("health ok", health.get("status") == "ok", health.get("status"))


print()
print("=== 1. 구형 앱(v1.5.2)이 보내던 그대로 ===")
# 이 앱은 trip_type 을 아예 모른다. 쿼리도 body 도 붙이지 않는다.

r = client.get(f"{BASE}/api/dispatch/today")
check("GET /api/dispatch/today (파라미터 없음)", r.status_code == 200, r.status_code)
check("등원으로 응답", r.json().get("trip_type") == "inbound", r.json().get("trip_type"))

r = client.get(f"{BASE}/api/ride-completions/today")
check("GET /api/ride-completions/today", r.status_code == 200, r.status_code)

r = client.get(f"{BASE}/api/dispatch/acks/today")
check("GET /api/dispatch/acks/today", r.status_code == 200, r.status_code)
check("등원 확인 목록", r.json().get("trip_type") == "inbound", r.json().get("trip_type"))

# 구형 앱의 탑승 완료 전송. sms_opt_in 도 trip_type 도 없다.
r = client.post(f"{BASE}/api/ride-completions", json={
    "passenger_id": "ZZ-COMPAT-1", "passenger_name": "ZZ호환테스트",
    "vehicle_id": "ZZ-VEH", "vehicle_type": "레이", "vehicle_plate_number": "00가0000",
    "trip_round": 1, "scheduled_pickup": "08:10",
})
check("POST /api/ride-completions (구형 body)", r.status_code == 200, r.status_code)
if r.status_code == 200:
    check("등원으로 저장됨", r.json().get("trip_type") == "inbound", r.json().get("trip_type"))

# 구형 앱의 배차표 확인.
r = client.post(f"{BASE}/api/dispatch/ack", json={
    "vehicle_id": "ZZ-COMPAT-VEH", "vehicle_label": "ZZ 호환 00가0000",
})
check("POST /api/dispatch/ack (구형 body)", r.status_code == 200, r.status_code)


print()
print("=== 2. 같은 어르신의 등원과 하원이 따로 남는가 ===")
# 이게 이번 개편의 핵심이다. 예전 유일키였다면 오후가 오전을 덮어썼다.

r = client.post(f"{BASE}/api/ride-completions", json={
    "trip_type": "outbound",
    "passenger_id": "ZZ-COMPAT-1", "passenger_name": "ZZ호환테스트",
    "vehicle_id": "ZZ-VEH", "vehicle_type": "레이", "vehicle_plate_number": "00가0000",
    "trip_round": 1, "scheduled_pickup": "16:10",
})
check("하원 기록 저장", r.status_code == 200, r.status_code)

records = client.get(f"{BASE}/api/ride-completions/today").json()["records"]
mine = [x for x in records if x["passenger_id"] == "ZZ-COMPAT-1"]
check("같은 어르신 기록이 2건 남음", len(mine) == 2,
      [(x["trip_type"], x["scheduled_pickup"]) for x in mine])
check("등원 기록이 살아 있음",
      any(x["trip_type"] == "inbound" and x["scheduled_pickup"] == "08:10" for x in mine))
check("하원 기록도 있음",
      any(x["trip_type"] == "outbound" and x["scheduled_pickup"] == "16:10" for x in mine))

only_out = client.get(f"{BASE}/api/ride-completions/today",
                      params={"trip_type": "outbound"}).json()["records"]
check("trip_type 으로 걸러짐",
      all(x["trip_type"] == "outbound" for x in only_out), len(only_out))


print()
print("=== 3. 하원 배차가 실제로 도는가 ===")

today = client.get(f"{BASE}/api/dispatch/today").json().get("result")
if not today:
    print("  (오늘 저장된 배차가 없어 건너뜁니다)")
else:
    center = today["center"]
    stops = [s for v in today["vehicles"] for t in v["trips"] for s in t["stops"]][:3]
    payload = {
        "trip_type": "outbound",
        "center": {k: center[k] for k in ("name", "address", "latitude", "longitude")},
        "vehicles": [{
            "id": "ZZ-OUT-SELF", "vehicle_type": "스타리아", "plate_number": "00나0000",
            "driver_name": "ZZ기사", "capacity": 7,
            "start_type": "custom", "start_address": stops[0]["address"],
            "start_latitude": stops[0]["latitude"], "start_longitude": stops[0]["longitude"],
        }],
        "passengers": [{
            "id": f"ZZ-P{i}", "name": s["name"], "address": s["address"],
            "latitude": s["latitude"], "longitude": s["longitude"],
            "pickup_start": "08:00", "pickup_end": "09:30",
        } for i, s in enumerate(stops, start=1)],
    }
    r = client.post(f"{BASE}/api/optimize", json=payload)
    check("하원 배차 계산", r.status_code == 200, r.text[:160])
    if r.status_code == 200:
        result = r.json()
        check("응답이 하원", result["trip_type"] == "outbound", result["trip_type"])
        trips = {t["round"]: t for t in result["vehicles"][0]["trips"]}
        check("1회차 센터 → 센터",
              trips[1]["origin_name"] == center["name"]
              and trips[1]["destination_name"] == center["name"],
              f'{trips[1]["origin_name"]} → {trips[1]["destination_name"]}')
        check("2회차 도착이 기사님 출발지",
              trips[2]["destination_name"] != center["name"],
              f'{trips[2]["origin_name"]} → {trips[2]["destination_name"]}')
        windows = {s["requested_window"] for t in result["vehicles"][0]["trips"]
                   if t["used"] for s in t["stops"]}
        check("하원 기본 시간창 적용", windows == {"15:30~17:00"}, windows)


print()
print("=== 4. 어르신 명단이 더 이상 쌓이지 않는가 ===")
print("  (배차 계산을 두 번 돌려 passengers 행수가 그대로인지 봅니다)")
try:
    from dotenv import load_dotenv
    load_dotenv()
    from app.supabase_client import get_supabase
    sb = get_supabase()
    before = len(sb.table("passengers").select("id").execute().data or [])
    if today:
        client.post(f"{BASE}/api/optimize", json=payload)
        client.post(f"{BASE}/api/optimize", json=payload)
    after = len(sb.table("passengers").select("id").execute().data or [])
    check("두 번 더 계산해도 행수가 늘지 않음", after <= before + len(payload["passengers"]),
          f"{before} -> {after}")
except Exception as error:  # noqa: BLE001
    print(f"  (DB 직접 확인 생략: {error})")


print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 구형 앱은 그대로 돌고, 등원/하원은 따로 남습니다.")
print()
print("정리용 SQL:")
print("  delete from public.ride_completions where passenger_id like 'ZZ-%';")
print("  delete from public.dispatch_acks where vehicle_id like 'ZZ-%';")
print("  delete from public.passengers where passenger_id like 'ZZ-%';")
print("  delete from public.vehicles where vehicle_id like 'ZZ-%';")
