"""라이브 Render 서버 대상 솔라피 문자 발송 E2E 검증.

프론트엔드를 거치지 않고 서버만 단독으로 검증한다.

  A. 솔라피 자격증명/서명 검증  : 잔액 조회 (읽기 전용, 무과금)
  B. 라이브 서버로 탑승완료 POST : 응답의 sms_sent 가 권위 있는 신호
  C. 솔라피 발송 이력 교차 확인  : 이번 실행 고유 표식으로 정확 일치 검사

주의사항 두 가지:
  - curl 로 보내면 안 된다. Git Bash 가 한글을 cp949 로 인코딩해
    FastAPI 가 본문 파싱에 실패(400)한다. httpx 로 보내야 UTF-8 로 간다.
  - 이력 검사는 부분 문자열이 아니라 실행마다 새로 만드는 표식으로 해야 한다.
    "발송점검" 같은 고정 문자열은 과거 테스트 문자에 걸려 오탐이 난다.

실제 문자 1건이 발송된다. 수신번호는 등록된 발신번호(센터 번호)로 자가발송한다.
실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_live_sms.py
"""
import hashlib
import hmac
import sys
import time
import uuid

import httpx

from app.config import get_settings
from app.supabase_client import get_supabase, key_kind

LIVE = "https://daycare-routing-api.onrender.com"
SOLAPI = "https://api.solapi.com"

settings = get_settings()
API_KEY = settings.solapi_api_key
API_SECRET = settings.solapi_api_secret
SENDER = settings.solapi_sender

# 이번 실행을 유일하게 식별하는 표식. 과거 문자와 섞이지 않게 한다.
MARK = "SRVCHK" + uuid.uuid4().hex[:6].upper()
TEST_ID = "ZZ-" + MARK

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


def mask(number):
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return digits[:3] + "*" * max(0, len(digits) - 6) + digits[-3:] if len(digits) >= 6 else "???"


def auth_header():
    date = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    salt = uuid.uuid1().hex
    signature = hmac.new(
        API_SECRET.encode("utf-8"), (date + salt).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"HMAC-SHA256 apiKey={API_KEY}, date={date}, salt={salt}, signature={signature}"


print("=== 사전 확인 ===")
check("로컬에 솔라피 자격증명 존재", bool(API_KEY and API_SECRET and SENDER))
if failures:
    print("\n자격증명이 없어 중단합니다. backend/.env 를 확인하세요.")
    sys.exit(1)
print(f"  발신번호  : {mask(SENDER)}")
print(f"  식별 표식 : {MARK}")

# ---------------------------------------------------------------------------
print("\n=== A. 솔라피 자격증명 / 서명 검증 (읽기 전용, 무과금) ===")
try:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(f"{SOLAPI}/cash/v1/balance", headers={"Authorization": auth_header()})
    check("잔액 조회 HTTP 200 (= 서명 유효)", r.status_code == 200,
          f"HTTP {r.status_code} {'' if r.status_code == 200 else r.text[:120]}")
    if r.status_code == 200:
        b = r.json()
        check("발송 가능한 잔액 보유", (b.get("point") or 0) + (b.get("balance") or 0) > 0,
              f"balance={b.get('balance')} point={b.get('point')}")
except httpx.HTTPError as error:
    check("솔라피 접속", False, str(error))

# ---------------------------------------------------------------------------
print("\n=== B. 라이브 서버로 탑승완료 POST ===")
payload = {
    "passenger_id": TEST_ID,
    "passenger_name": MARK,
    "vehicle_id": "selftest",
    "vehicle_type": "점검용",
    "vehicle_plate_number": "00가0000",
    "trip_round": 1,
    "scheduled_pickup": "08:00",
    "center_name": "서버발송점검",
    "guardian_phone": SENDER,
}
sms_sent = None
try:
    with httpx.Client(timeout=150.0) as client:
        r = client.post(f"{LIVE}/api/ride-completions", json=payload)
    check("HTTP 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        record = r.json()
        check("DB 저장 확인", bool(record.get("completed_at")), record.get("completed_at"))
        sms_sent = record.get("sms_sent")
        check("서버가 문자 결과를 보고함 (구버전이면 null)", sms_sent is not None, sms_sent)
        print(f"     sms_sent    : {sms_sent}")
        print(f"     sms_message : {record.get('sms_message')}")
        check("서버가 문자 발송에 성공", sms_sent is True, record.get("sms_message"))
except httpx.HTTPError as error:
    check("라이브 서버 접속", False, str(error))

# ---------------------------------------------------------------------------
print("\n=== C. 솔라피 발송 이력 교차 확인 ===")
if sms_sent is not True:
    print("  B에서 발송되지 않아 건너뜁니다.")
else:
    time.sleep(6)
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(f"{SOLAPI}/messages/v4/list", params={"limit": 20},
                           headers={"Authorization": auth_header()})
        check("발송 이력 조회 HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            msgs = list(r.json().get("messageList", {}).values())
            hit = [m for m in msgs if MARK in (m.get("text") or "")]
            check("이번 실행의 문자를 이력에서 발견", bool(hit),
                  f"최근 {len(msgs)}건 중 {len(hit)}건")
            if hit:
                m = hit[0]
                print(f"     상태코드 : {m.get('statusCode')} ({m.get('statusMessage')})")
                print(f"     수신     : {mask(m.get('to'))}")
    except httpx.HTTPError as error:
        check("솔라피 이력 조회", False, str(error))

# ---------------------------------------------------------------------------
print("\n=== 정리: 테스트로 남은 일지 행 삭제 ===")
# RLS 를 켠 뒤로 공개용 키로는 삭제도 조회도 막힌다.
# 그런데 조회가 빈 배열을 돌려주므로 '잔여 0건'이 되어 정리에 성공한 것처럼 보인다.
# 키 등급을 먼저 확인해 그 거짓 통과를 막는다.
local_key = key_kind(get_settings().supabase_key)
if local_key != "secret":
    print(f"  SKIP  로컬 SUPABASE_KEY 가 {local_key} 라 정리할 수 없습니다.")
    print(f"        Supabase SQL Editor 에서 지워 주세요:")
    print(f"          delete from public.ride_completions where passenger_id = '{TEST_ID}';")
else:
    try:
        get_supabase().table("ride_completions").delete().eq("passenger_id", TEST_ID).execute()
        left = get_supabase().table("ride_completions").select("passenger_id") \
            .like("passenger_id", "ZZ-%").execute().data
        check("테스트 행 정리됨", len(left) == 0, f"잔여 {len(left)}건")
    except Exception as error:  # noqa: BLE001
        check("테스트 행 정리", False, str(error))

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전체 통과 — 라이브 서버에서 솔라피 문자 발송이 정상 동작합니다.")
