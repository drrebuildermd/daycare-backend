"""RLS 활성화 후 라이브 서버 기능 검증.

RLS 를 켜면 백엔드가 secret 키로 접근하므로 정상 동작해야 하고,
공개용 키로는 아무것도 읽히지 않아야 한다. 둘 다 확인한다.

  1. 서버 상태와 키 종류
  2. 배차 (읽기 없음 / passengers 쓰기 포함)
  3. 탑승 완료 (ride_completions 쓰기 + 읽기)
  4. 오늘 일지 조회 / CSV 내보내기
  5. 배차 저장·조회 (dispatches)
  6. 기사 기기 목록 (driver_devices)
  7. 공개용 키로 외부에서 읽히는지 (RLS 가 실제로 막는지)

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_live_rls.py
"""
import io
import sys
import uuid

import httpx

LIVE = "https://daycare-routing-api.onrender.com"
MARK = "RLSCHK" + uuid.uuid4().hex[:6].upper()
TEST_ID = "ZZ-" + MARK

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


client = httpx.Client(timeout=180.0)

# ---------------------------------------------------------------------------
print("=== 1. 서버 상태 ===")
r = client.get(f"{LIVE}/api/health")
check("health 200", r.status_code == 200, r.status_code)
health = r.json() if r.status_code == 200 else {}
check("secret 키로 동작 중", health.get("supabase_key_kind") == "secret",
      health.get("supabase_key_kind"))

# ---------------------------------------------------------------------------
print("\n=== 2. 배차 (passengers 쓰기 포함) ===")
req = {
    "center": {"name": "행복주야간보호센터", "address": "양산시청",
               "latitude": 35.3350, "longitude": 129.0371},
    "vehicles": [{"id": "v1", "vehicle_type": "점검용", "plate_number": "00가0000",
                  "driver_name": "점검기사", "capacity": 3}],
    "passengers": [
        {"id": TEST_ID + "-1", "name": MARK + "일", "address": "양산 1로",
         "guardian_phone": "01000000001", "latitude": 35.34, "longitude": 129.04,
         "pickup_start": "08:00", "pickup_end": "09:30"},
        {"id": TEST_ID + "-2", "name": MARK + "이", "address": "양산 2로",
         "latitude": 35.33, "longitude": 129.05,
         "pickup_start": "08:00", "pickup_end": "09:30"},
    ],
}
r = client.post(f"{LIVE}/api/optimize", json=req)
check("배차 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")
result = r.json() if r.status_code == 200 else None
if result:
    stops = [s for v in result["vehicles"] for t in v["trips"] for s in t["stops"]]
    check("2명 전원 배차됨", len(stops) == 2, len(stops))
    phones = {s["name"]: s.get("guardian_phone") for s in stops}
    check("보호자 번호가 결과에 실림", phones.get(MARK + "일") == "01000000001", phones)

# ---------------------------------------------------------------------------
print("\n=== 3. 탑승 완료 (ride_completions 쓰기) ===")
r = client.post(f"{LIVE}/api/ride-completions", json={
    "passenger_id": TEST_ID, "passenger_name": MARK, "vehicle_id": "v1",
    "vehicle_type": "점검용", "vehicle_plate_number": "00가0000",
    "trip_round": 1, "scheduled_pickup": "08:00",
    "center_name": "RLS점검", "guardian_phone": "",
})
check("탑승완료 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")
if r.status_code == 200:
    rec = r.json()
    check("DB 저장됨 (RLS에 막히지 않음)", bool(rec.get("completed_at")), rec.get("completed_at"))
    check("문자 결과 보고됨", rec.get("sms_sent") is not None,
          f"{rec.get('sms_sent')} / {rec.get('sms_message')}")

# ---------------------------------------------------------------------------
print("\n=== 4. 오늘 일지 조회 / 내보내기 (ride_completions 읽기) ===")
r = client.get(f"{LIVE}/api/ride-completions/today")
check("일지 조회 200", r.status_code == 200, r.status_code)
if r.status_code == 200:
    names = [x["passenger_name"] for x in r.json()["records"]]
    check("방금 넣은 기록이 보임 (읽기 정상)", MARK in names, f"{len(names)}건")

r = client.get(f"{LIVE}/api/ride-completions/today/export")
check("CSV 내보내기 200", r.status_code == 200, r.status_code)
if r.status_code == 200:
    check("CSV 본문 생성됨", len(r.content) > 50, f"{len(r.content)} bytes")

# ---------------------------------------------------------------------------
print("\n=== 5. 배차 저장·조회 (dispatches) ===")
if result:
    r = client.post(f"{LIVE}/api/dispatch/notify", json=result)
    check("배차 전송 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    r = client.get(f"{LIVE}/api/dispatch/today")
    check("오늘 배차 조회 200", r.status_code == 200, r.status_code)
    if r.status_code == 200 and r.json().get("result"):
        saved = [s["name"] for v in r.json()["result"]["vehicles"]
                 for t in v["trips"] for s in t["stops"]]
        check("저장된 배차를 되읽음", any(MARK in n for n in saved), saved[:3])

# ---------------------------------------------------------------------------
print("\n=== 6. 기사 기기 목록 (driver_devices) ===")
r = client.get(f"{LIVE}/api/driver-devices")
check("기기 목록 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")

# ---------------------------------------------------------------------------
print("\n=== 7. 공개용 키로 외부 접근이 실제로 막히는가 ===")
front = {}
for line in io.open(r"C:\Users\HOME\Documents\Daycare_App\frontend\.env",
                    encoding="utf-8").read().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        front[k.strip()] = v.strip()
url = front.get("EXPO_PUBLIC_SUPABASE_URL", "")
anon = front.get("EXPO_PUBLIC_SUPABASE_ANON_KEY", "")
if not (url and anon):
    print("  SKIP  프론트 .env 에 수파베이스 값이 없어 확인 불가")
else:
    for table in ("ride_completions", "passengers"):
        rr = client.get(f"{url}/rest/v1/{table}", params={"select": "*", "limit": 1},
                        headers={"apikey": anon, "Authorization": f"Bearer {anon}"})
        blocked = rr.status_code != 200 or rr.json() == []
        check(f"{table}: 공개용 키로 조회 차단됨", blocked,
              f"HTTP {rr.status_code} {rr.text[:80]}")

# ---------------------------------------------------------------------------
print("\n=== 정리 ===")
r = client.get(f"{LIVE}/api/ride-completions/today")
print(f"  오늘 일지 {len(r.json()['records'])}건 (테스트 행 포함)")
print(f"  정리 대상 passenger_id: {TEST_ID}")

client.close()
print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — RLS 활성화 후에도 모든 기능이 정상 동작합니다.")
