import csv
import io
import time
import uuid
import hmac
import hashlib

import httpx
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from app.config import Settings, get_settings
from app.database import init_database, list_completions, today_kst, upsert_completion
from app.geocoding import resolve_locations
from app.dispatch import load_dispatch, notify_drivers, save_dispatch
from app.drivers import deactivate_device, list_devices, register_device
from app.models import (
    DispatchNotifyResult,
    DispatchToday,
    DriverDeviceCreate,
    DriverDeviceList,
    DriverDeviceRecord,
    OptimizeRequest,
    OptimizeResponse,
    RideCompletionCreate,
    RideCompletionList,
    RideCompletionRecord,
)
from app.optimizer import optimize_routes
from app.supabase_client import (
    MISSING_MESSAGE,
    PUBLISHABLE_WARNING,
    get_supabase,
    is_configured,
    key_kind,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 송영 일지가 Supabase에 저장되므로 더 이상 선택 사항이 아니다.
    # 설정이 없는 채로 뜨면 '탑승 완료'를 누르는 순간에야 실패하므로 여기서 막는다.
    if not is_configured():
        raise RuntimeError(MISSING_MESSAGE)
    # 공개용 키로 돌고 있으면 배포 로그에 크게 남긴다. 죽이지는 않는다 —
    # 지금 죽이면 운영이 멈추고, 교체는 사람이 해야 하는 일이다.
    if key_kind(get_settings().supabase_key) == "publishable":
        print(PUBLISHABLE_WARNING)
    init_database(get_settings())
    yield


app = FastAPI(title="Daycare Routing API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🚨 [최종 장착] 1급 기밀(.env) 연동 진짜 보호자 번호 발사 헬퍼 함수
# ==========================================
def send_test_sms(passenger_name: str, target_number: str, center_name: str):
    settings = get_settings()
    api_key = settings.solapi_api_key
    api_secret = settings.solapi_api_secret
    sender_number = settings.solapi_sender

    # 키가 없으면 건너뛴다. 문자 설정이 없다고 배차/일지가 멈추면 안 된다.
    if not (api_key and api_secret and sender_number):
        print("[문자 건너뜀] 솔라피 자격증명(SOLAPI_API_KEY/SECRET/SENDER)이 없습니다.")
        return (False, "서버에 솔라피 설정이 없어 발송하지 않았습니다.")

    # 번호가 없거나 형식이 아니면 발송하지 않는다.
    # 예전에는 발신번호(센터 번호)로 대체했는데, 보호자에게 전달된 것처럼
    # 보이면서 실제로는 센터 자기 폰으로만 가는 상태였다.
    digits = "".join(ch for ch in (target_number or "") if ch.isdigit())
    if len(digits) < 10:
        print(f"[문자 건너뜀] {passenger_name} 어르신의 보호자 번호가 없습니다.")
        return (False, "보호자 연락처가 없어 발송하지 않았습니다.")

    url = "https://api.solapi.com/messages/v4/send"
    
    date = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    salt = str(uuid.uuid1().hex)
    data = date + salt
    
    signature = hmac.new(
        api_secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    auth_header = f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}"
    
    payload = {
        "message": {
            "to": digits,
            "from": sender_number.replace("-", "").strip(),
            "text": f"[{center_name or '주야간보호센터'}] {passenger_name} 어르신이 무사히 차량에 탑승하셨습니다.",
            "type": "SMS"
        }
    }
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload, headers=headers)
    result = response.json()
    print(f"✉️ 문자 발송 리포트: {result}")

    # 솔라피는 접수 성공 시 messageId 와 statusCode 2000/3000 을 준다.
    # 인증 실패 등은 200이 아닌 상태코드와 errorCode 로 온다.
    if response.status_code == 200 and result.get("messageId"):
        return (True, f"발송 접수됨 ({result.get('statusMessage', '').strip()})")
    reason = result.get("errorMessage") or result.get("statusMessage") or response.text[:80]
    return (False, f"솔라피 거절: {result.get('errorCode') or response.status_code} {reason}")

def _archive_passengers(request: OptimizeRequest, resolved) -> None:
    """어르신 명단을 Supabase에 백업한다. 실패해도 배차 결과는 그대로 반환한다."""
    rows = [
        {
            "name": passenger.name,
            "address": passenger.address,
            "detail_address": passenger.detail_address,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "pickup_start": passenger.pickup_start,
            "pickup_end": passenger.pickup_end,
            "is_wheelchair": passenger.wheelchair,
        }
        for passenger, location in zip(request.passengers, resolved[1:])
    ]
    if not rows:
        return
    try:
        get_supabase().table("passengers").insert(rows).execute()
    except Exception as error:  # noqa: BLE001 - 백업 실패가 배차를 막으면 안 된다
        print(f"[Supabase 백업 실패] {error}")


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Render의 헬스 체크와 폰에서의 연결 확인용.

    문자 설정 여부를 함께 알려준다. 값은 노출하지 않고 '있다/없다'와 길이만 준다.
    배포 환경변수가 실제로 반영됐는지 밖에서 확인할 방법이 이것뿐이다.
    """
    return {
        "status": "ok",
        "storage": "supabase",
        "sms": {
            "api_key": bool(settings.solapi_api_key),
            "api_secret": bool(settings.solapi_api_secret),
            "secret_length": len(settings.solapi_api_secret or ""),
            "sender": bool(settings.solapi_sender),
        },
        # RLS 를 켜기 전/후에 키 교체가 실제로 반영됐는지 밖에서 확인하는 용도.
        # 'secret' 이어야 RLS 를 켜도 백엔드가 살아남는다.
        "supabase_key_kind": key_kind(settings.supabase_key),
    }


@app.post("/api/driver-devices", response_model=DriverDeviceRecord)
def create_driver_device(payload: DriverDeviceCreate) -> DriverDeviceRecord:
    """기사님 폰의 Expo 푸시 토큰을 등록한다. (3번 과제에서 발송에 사용)"""
    return register_device(payload)


@app.get("/api/driver-devices", response_model=DriverDeviceList)
def read_driver_devices(driver_name: str | None = None) -> DriverDeviceList:
    return DriverDeviceList(devices=list_devices(driver_name))


@app.delete("/api/driver-devices/{expo_push_token}", status_code=204)
def delete_driver_device(expo_push_token: str) -> None:
    deactivate_device(expo_push_token)


@app.post("/api/dispatch/notify", response_model=DispatchNotifyResult)
async def send_dispatch(result: OptimizeResponse) -> DispatchNotifyResult:
    """배차 결과를 저장하고 담당 기사님 폰으로 푸시를 보낸다."""
    service_date = today_kst()
    save_dispatch(result, service_date)
    return await notify_drivers(result, service_date)


@app.get("/api/dispatch/today", response_model=DispatchToday)
def read_today_dispatch() -> DispatchToday:
    """기사님 폰이 본인 동선을 그리려고 받아가는 오늘의 배차."""
    service_date = today_kst()
    return DispatchToday(
        service_date=service_date.isoformat(), result=load_dispatch(service_date)
    )


@app.get("/map", response_class=HTMLResponse)
def map_page(settings: Settings = Depends(get_settings)) -> HTMLResponse:
    """네이티브 앱의 WebView가 여는 지도 페이지.

    HTML 문자열을 앱에 넣지 않고 서버가 실제 URL로 서빙하는 이유는,
    카카오맵 자바스크립트 키가 요청 도메인을 검사하기 때문이다.
    이 서버 주소를 Kakao Developers > 플랫폼 > Web 에 등록하면 된다.
    """
    static_dir = Path(__file__).resolve().parents[1] / "static"
    html = (static_dir / "map.html").read_text(encoding="utf-8")
    html = html.replace("__KAKAO_JS_KEY__", settings.kakao_js_key or "")
    return HTMLResponse(content=html)


@app.post("/api/optimize", response_model=OptimizeResponse)
async def run_optimization(
    request: OptimizeRequest, settings: Settings = Depends(get_settings)
) -> OptimizeResponse:
    # 결석자는 지오코딩 전에 걷어낸다. 뒤에 두면 카카오 호출을 헛되이 쓰고,
    # optimize_routes가 전제하는 '노드 번호 = 어르신 순번'도 어긋난다.
    attending = [passenger for passenger in request.passengers if passenger.attending]
    absent_count = len(request.passengers) - len(attending)
    if not attending:
        raise HTTPException(
            status_code=422, detail="출석한 어르신이 없습니다. 출석 여부를 확인해 주세요."
        )
    request = request.model_copy(update={"passengers": attending})

    # 노드 0은 센터, 1번부터가 어르신. optimize_routes가 이 순서를 전제한다.
    resolved = await resolve_locations([request.center, *request.passengers], settings)
    response = optimize_routes(request, resolved, settings)
    if absent_count:
        response.notices.append(f"결석 처리된 {absent_count}명은 배차에서 제외했습니다.")
    _archive_passengers(request, resolved)
    return response


@app.post("/api/ride-completions", response_model=RideCompletionRecord)
def create_ride_completion(
    payload: RideCompletionCreate, settings: Settings = Depends(get_settings)
) -> RideCompletionRecord:
    # 1. 수파베이스(DB)에 탑승 기록을 먼저 저장합니다.
    record = upsert_completion(payload, settings)

    # 2. 보호자에게 탑승 완료 문자를 보냅니다.
    #    저장은 이미 끝났으므로 문자 실패로 500을 돌려주면 안 된다.
    #    그러면 기사님 화면에는 '저장 실패'가 뜨는데 실제로는 저장된 상태가 된다.
    try:
        sms_sent, sms_message = send_test_sms(
            passenger_name=payload.passenger_name,
            target_number=payload.guardian_phone,
            center_name=payload.center_name,
        )
    except Exception as error:  # noqa: BLE001 - 문자 실패가 탑승 기록을 무효화하면 안 된다
        print(f"[문자 발송 실패] {payload.passenger_name}: {error}")
        sms_sent, sms_message = False, f"발송 중 오류: {error}"

    # 3. 저장 결과와 문자 발송 결과를 함께 돌려준다.
    #    문자 실패는 200을 유지하되 화면에서 알 수 있어야 한다.
    record.sms_sent = sms_sent
    record.sms_message = sms_message
    return record


@app.get("/api/ride-completions/today", response_model=RideCompletionList)
def read_today_completions(
    settings: Settings = Depends(get_settings),
) -> RideCompletionList:
    service_date: date = today_kst()
    return RideCompletionList(
        service_date=service_date.isoformat(),
        records=list_completions(service_date, settings),
    )


@app.get("/api/ride-completions/today/export")
def export_today_completions(settings: Settings = Depends(get_settings)):
    service_date = today_kst()
    records = list_completions(service_date, settings)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["운행일", "어르신", "차종", "차량번호", "운행회차", "예정시각", "완료시각"]
    )
    for record in records:
        writer.writerow(
            [
                record.service_date,
                record.passenger_name,
                record.vehicle_type,
                record.vehicle_plate_number,
                f"{record.trip_round}차",
                record.scheduled_pickup,
                record.completed_at,
            ]
        )

    # Excel이 한글을 깨뜨리지 않도록 UTF-8 BOM을 붙인다.
    payload = buffer.getvalue().encode("utf-8-sig")
    filename = f"songyoung-log-{service_date.isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
