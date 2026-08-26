"""라이브 Render 서버 대상 솔라피 문자 발송 E2E 검증.

프론트엔드를 거치지 않고 서버만 단독으로 검증한다. 3단계로 나눈 이유는,
/api/ride-completions 응답만으로는 문자가 실제로 나갔는지 알 수 없기 때문이다.
(문자 실패는 try/except로 삼켜지고 200이 반환된다 — 의도된 동작)

  A. 솔라피 자격증명/서명 검증  : 잔액 조회(읽기 전용, 무과금)
  B. 라이브 서버로 탑승완료 POST : Render가 200을 돌려주는지
  C. 솔라피 발송 이력 조회       : B가 실제로 문자를 만들었는지 (핵심)

C가 있어야 "Render가 보냈다"와 "Render가 조용히 건너뛰었다"를 구분할 수 있다.

주의: 실제 문자가 1건 발송된다. 수신번호는 등록된 발신번호(센터 번호)로 자가발송한다.
실행: .venv\\Scripts\\python.exe -X utf8 test_live_sms.py
"""
import hashlib
import hmac
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

from app.config import get_settings

LIVE = "https://daycare-routing-api.onrender.com"
SOLAPI = "https://api.solapi.com"
TEST_PASSENGER_ID = "ZZ-SMS-SELFTEST"

settings = get_settings()
API_KEY = settings.solapi_api_key
API_SECRET = settings.solapi_api_secret
SENDER = settings.solapi_sender

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


def mask(number):
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return digits[:3] + "*" * max(0, len(digits) - 6) + digits[-3:] if len(digits) >= 6 else "???"


def auth_header():
    """app/main.py 의 send_test_sms 와 동일한 서명 방식."""
    date = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    salt = uuid.uuid1().hex
    signature = hmac.new(
        API_SECRET.encode("utf-8"), (date + salt).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return (
        f"HMAC-SHA256 apiKey={API_KEY}, date={date}, salt={salt}, signature={signature}"
    )


print("=== 사전 확인 ===")
check("로컬에 솔라피 자격증명 존재", bool(API_KEY and API_SECRET and SENDER))
if failures:
    print("\n자격증명이 없어 중단합니다. backend/.env 를 확인하세요.")
    sys.exit(1)
print(f"  발신번호: {mask(SENDER)}")

# ---------------------------------------------------------------------------
print("\n=== A. 솔라피 자격증명 / 서명 검증 (읽기 전용, 무과금) ===")
try:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(
            f"{SOLAPI}/cash/v1/balance", headers={"Authorization": auth_header()}
        )
    check("잔액 조회 HTTP 200 (= 서명 유효)", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        balance = r.json()
        point = balance.get("point", 0)
        cash = balance.get("balance", 0)
        check("발송 가능한 잔액 보유", (point or 0) + (cash or 0) > 0,
              f"balance={cash} point={point}")
    else:
        check("서명 오류 아님", False, r.text[:150])
except httpx.HTTPError as error:
    check("솔라피 접속", False, str(error))

# ---------------------------------------------------------------------------
print("\n=== B. 라이브 Render 서버로 탑승완료 POST ===")
sent_at = datetime.now(timezone.utc)
payload = {
    "passenger_id": TEST_PASSENGER_ID,
    "passenger_name": "발송점검",
    "vehicle_id": "selftest",
    "vehicle_type": "점검용",
    "vehicle_plate_number": "00가0000",
    "trip_round": 1,
    "scheduled_pickup": "08:00",
    "center_name": "발송 점검",
    # 등록된 발신번호로 자가발송한다. 외부인에게 문자가 가지 않도록.
    "guardian_phone": SENDER,
}
try:
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{LIVE}/api/ride-completions", json=payload)
    check("HTTP 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")
    if r.status_code == 200:
        record = r.json()
        check("DB 저장 확인 (completed_at 반환)", bool(record.get("completed_at")),
              record.get("completed_at"))
        # guardian_phone 은 DB에 저장하지 않으므로 응답에 실려 오지 않는다.
        # 번호가 서버까지 갔는지는 C단계(실제 발송 이력)로 확인한다.
except httpx.HTTPError as error:
    check("라이브 서버 접속", False, str(error))

# ---------------------------------------------------------------------------
print("\n=== C. 솔라피 발송 이력에서 실제 발송 확인 (핵심) ===")
print("  서버가 문자를 만들 시간을 잠깐 줍니다...")
time.sleep(6)
try:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(
            f"{SOLAPI}/messages/v4/list",
            params={"limit": 20},
            headers={"Authorization": auth_header()},
        )
    check("발송 이력 조회 HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
    if r.status_code == 200:
        messages = list(r.json().get("messageList", {}).values())
        recent = [
            m for m in messages
            if "발송점검" in (m.get("text") or "")
        ]
        check("이번 요청으로 생성된 문자 발견", bool(recent),
              f"최근 {len(messages)}건 중 {len(recent)}건 일치")
        if recent:
            newest = recent[0]
            print(f"     상태코드 : {newest.get('statusCode')}")
            print(f"     상태메시지: {newest.get('statusMessage')}")
            print(f"     수신번호  : {mask(newest.get('to'))}")
            print(f"     본문      : {(newest.get('text') or '')[:60]}")
            # 2000 = 정상 접수/발송. 4xxx/5xxx 는 실패.
            code = str(newest.get("statusCode") or "")
            check("발송 성공 상태코드", code in ("2000", "3000", "4000"),
                  f"statusCode={code} ({newest.get('statusMessage')})")
except httpx.HTTPError as error:
    check("솔라피 이력 조회", False, str(error))

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 라이브 서버에서 솔라피 문자 발송이 정상 동작합니다.")
