import csv
import io
import time
import uuid
import hmac
import hashlib

import httpx
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

from app.config import Settings, get_settings
from app.database import (
    KST,
    init_database,
    list_completions,
    mark_dispatch_sms_sent,
    today_kst,
    upsert_completion,
    was_dispatch_sms_sent,
)
from app.geocoding import resolve_locations
from app.dispatch import (
    acknowledge_dispatch,
    list_acknowledgements,
    load_dispatch,
    notify_drivers,
    save_dispatch,
)
from app.drivers import deactivate_device, list_devices, register_device
from app.models import (
    DispatchAckCreate,
    DispatchAckList,
    DispatchAckRecord,
    DispatchNotifyResult,
    DispatchToday,
    DriverDeviceCreate,
    DriverDeviceList,
    DriverDeviceRecord,
    OptimizeRequest,
    OptimizeResponse,
    RideCompletionCreate,
    TripType,
    RideCompletionList,
    RideCompletionRecord,
)
from app.optimizer import optimize_routes
from app.runs import record_optimization_run
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
# 솔라피 문자 발송
#
# 보내는 곳이 둘이다. 탑승 완료(보호자에게)와 배차 확정(기사님에게).
# 인증 로직은 하나만 두고 문구만 갈아끼운다.
# ==========================================
def _digits(value: str | None) -> str:
    """전화번호에서 숫자만 남긴다. 10자리 미만이면 쓸 수 없는 번호로 본다."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _solapi_send(target_number: str | None, text: str) -> tuple[bool, str]:
    """번호 하나에 문자 한 통. 실패해도 예외를 던지지 않고 이유를 돌려준다."""
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
    digits = _digits(target_number)
    if len(digits) < 10:
        return (False, "연락처가 없어 발송하지 않았습니다.")

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
            "text": text,
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


def send_test_sms(
    passenger_name: str,
    target_number: str,
    center_name: str,
    sms_opt_in: bool = True,
    trip_type: str = "inbound",
):
    """탑승(등원) 또는 하차(하원)를 보호자에게 알린다."""
    # 알림을 원치 않는 보호자가 있다. 명단에서 지우는 대신 이 스위치로 끈다.
    if not sms_opt_in:
        print(f"[문자 건너뜀] {passenger_name} 어르신은 알림 수신이 꺼져 있습니다.")
        return (False, "보호자가 알림 수신을 꺼두어 발송하지 않았습니다.")

    # 번호가 없으면 아예 부르지 않는다. 예전에는 발신번호(센터 번호)로 대체했는데,
    # 보호자에게 전달된 것처럼 보이면서 실제로는 센터 자기 폰으로만 가는 상태였다.
    if len(_digits(target_number)) < 10:
        print(f"[문자 건너뜀] {passenger_name} 어르신의 보호자 번호가 없습니다.")
        return (False, "보호자 연락처가 없어 발송하지 않았습니다.")

    # 하원은 '탑승'이 아니라 '댁에 도착'이다. 문구가 같으면 보호자가 혼란스럽다.
    body = (
        f"{passenger_name} 어르신이 댁에 안전하게 도착하셨습니다."
        if trip_type == "outbound"
        else f"{passenger_name} 어르신이 무사히 차량에 탑승하셨습니다."
    )
    return _solapi_send(
        target_number,
        f"[{center_name or '주야간보호센터'}] {body}",
    )
def _dispatch_sms_signature(vehicle) -> str:
    """기사님 한 분의 오늘 동선을 한 줄로 요약한다.

    다시 계산해도 이 값이 같으면 그 기사님에게는 달라진 게 없다는 뜻이다.
    조건을 바꿔가며 계산할 때마다 문자가 나가면 요금이 새고 기사님도 지친다.
    """
    parts = []
    for trip in vehicle.trips:
        if not trip.used:
            continue
        stops = ">".join(f"{stop.passenger_id}@{stop.estimated_pickup}" for stop in trip.stops)
        parts.append(f"{trip.round}:{stops}")
    return "|".join(parts)


def _notify_drivers_by_sms(response: OptimizeResponse) -> list[str]:
    """배차가 확정되면 기사님들께 문자로 알린다.

    동선이 지난번과 같은 기사님은 건너뛴다. 실패해도 배차 결과는 그대로 돌려준다.
    """
    center_name = response.center.name or "주야간보호센터"
    service_date = today_kst()
    trip_type = response.trip_type
    trip_label = "하원" if trip_type == "outbound" else "등원"
    notices: list[str] = []
    sent_count = 0

    for vehicle in response.vehicles:
        signature = _dispatch_sms_signature(vehicle)
        if not signature:
            continue  # 배정된 어르신이 없는 차량은 알릴 것이 없다

        digits = _digits(vehicle.driver_phone)
        if len(digits) < 10:
            notices.append(
                f"{vehicle.plate_number} 기사님 연락처가 없어 {trip_label} 문자를 보내지 못했습니다."
            )
            continue

        try:
            if was_dispatch_sms_sent(
                service_date, vehicle.vehicle_id, signature, trip_type
            ):
                continue
        except Exception as error:  # noqa: BLE001 - 중복 확인 실패가 배차를 막으면 안 된다
            print(f"[배차 문자] 중복 확인 실패, 그냥 보냅니다: {error}")

        driver = (vehicle.driver_name or "").strip()
        try:
            sent, message = _solapi_send(
                digits,
                f"[{center_name}] {driver + ' ' if driver else ''}기사님, "
                f"오늘 {trip_label} 배차표가 확정되었습니다. 앱에서 확인해 주세요.",
            )
        except Exception as error:  # noqa: BLE001 - 문자 실패가 배차를 무효화하면 안 된다
            print(f"[배차 문자 실패] {vehicle.plate_number}: {error}")
            continue

        if sent:
            sent_count += 1
            try:
                mark_dispatch_sms_sent(
                    service_date, vehicle.vehicle_id, signature, trip_type
                )
            except Exception as error:  # noqa: BLE001
                # 기록에 실패하면 다음 계산 때 한 번 더 갈 수 있다. 안 가는 것보다 낫다.
                print(f"[배차 문자] 발송 기록 실패: {error}")
        else:
            notices.append(f"{vehicle.plate_number} 기사님 배차 문자 실패: {message}")

    if sent_count:
        notices.insert(0, f"{trip_label} 배차표 확정 문자를 기사님 {sent_count}분께 보냈습니다.")
    return notices


def _archive_passengers(request: OptimizeRequest, resolved) -> None:
    """어르신 명단을 Supabase에 백업한다. 실패해도 배차 결과는 그대로 반환한다.

    이 표는 날짜별 기록이 아니라 '지금 명단'의 거울이다. 원장님 폰이 고장났을 때
    되살리기 위한 것이므로 한 어르신당 한 줄이면 된다.

    예전에는 insert 만 해서 배차를 계산할 때마다 명단 전체가 새 줄로 쌓였다.
    7일 쓰는 동안 36명이 251줄이 됐다. passenger_id 를 키로 덮어쓴다.
    """
    now = datetime.now(KST).replace(microsecond=0).isoformat()
    rows = [
        {
            "passenger_id": passenger.id or passenger.name,
            "updated_at": now,
            "name": passenger.name,
            "address": passenger.address,
            "detail_address": passenger.detail_address,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "pickup_start": passenger.pickup_start,
            "pickup_end": passenger.pickup_end,
            "is_wheelchair": passenger.wheelchair,
            "guardian_phone": passenger.guardian_phone,
            "passenger_phone": passenger.passenger_phone,
            "primary_contact": passenger.primary_contact,
            "is_sms_opt_in": passenger.sms_opt_in,
            "dropoff_start": passenger.dropoff_start,
            "dropoff_end": passenger.dropoff_end,
            "is_attending_inbound": passenger.attending,
            "is_attending_outbound": passenger.attending_outbound,
        }
        for passenger, location in zip(request.passengers, resolved[1:])
    ]
    if not rows:
        return
    try:
        get_supabase().table("passengers").upsert(
            rows, on_conflict="passenger_id"
        ).execute()
    except Exception as error:  # noqa: BLE001 - 백업 실패가 배차를 막으면 안 된다
        print(f"[Supabase 백업 실패] {error}")


def _archive_vehicles(request: OptimizeRequest, resolved) -> None:
    """차량 설정을 Supabase에 백업한다. 실패해도 배차 결과는 그대로 반환한다.

    자차 송영 출발지까지 남겨야 나중에 "그날 어디서 출발했는지" 확인할 수 있다.
    """
    rows = []
    for vehicle in request.vehicles:
        row = {
            "vehicle_id": vehicle.id or vehicle.plate_number,
            "vehicle_type": vehicle.vehicle_type,
            "plate_number": vehicle.plate_number,
            "driver_name": vehicle.driver_name,
            "driver_phone": vehicle.driver_phone,
            "capacity": vehicle.capacity,
            "wheelchair_capacity": vehicle.wheelchair_capacity,
            "start_type": vehicle.start_type,
            "start_address": vehicle.start_address,
            "updated_at": datetime.now(KST).replace(microsecond=0).isoformat(),
        }
        rows.append(row)

    # 지오코딩된 자차 출발지 좌표를 채워 넣는다.
    # 노드 순서는 [센터, *어르신, *커스텀출발지] 이므로 뒤에서부터 순서대로 대응된다.
    node = 1 + len(request.passengers)
    for row, vehicle in zip(rows, request.vehicles):
        if vehicle.start_type == "custom" and node < len(resolved):
            row["start_latitude"] = resolved[node].latitude
            row["start_longitude"] = resolved[node].longitude
            node += 1

    if not rows:
        return
    try:
        get_supabase().table("vehicles").upsert(
            rows, on_conflict="vehicle_id"
        ).execute()
    except Exception as error:  # noqa: BLE001 - 백업 실패가 배차를 막으면 안 된다
        print(f"[Supabase 차량 백업 실패] {error}")


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
async def send_dispatch(
    result: OptimizeResponse, settings: Settings = Depends(get_settings)
) -> DispatchNotifyResult:
    """배차를 확정한다. 저장하고, 기사님 폰으로 푸시와 문자를 보낸다.

    원장님이 계산 결과를 눈으로 확인하고 [배차 전송]을 누른 시점이 확정이다.
    계산할 때마다 나가면 아직 정하지도 않은 배차가 기사님께 통보된다.
    """
    service_date = today_kst()
    save_dispatch(result, service_date, settings.center_id)
    outcome = await notify_drivers(result, service_date)

    # 앱을 안 깔았거나 푸시를 못 받는 기사님도 있다. 문자는 따로 나간다.
    # 문자가 실패해도 배차 저장과 푸시 결과는 그대로 돌려준다.
    try:
        sms_notices = _notify_drivers_by_sms(result)
    except Exception as error:  # noqa: BLE001
        print(f"[배차 문자] 전체 실패: {error}")
        sms_notices = [f"배차 문자 발송 중 오류가 났습니다: {error}"]

    outcome.sms_notices = sms_notices
    return outcome


@app.get("/api/dispatch/today", response_model=DispatchToday)
def read_today_dispatch(
    trip_type: TripType = Query("inbound"),
) -> DispatchToday:
    """기사님 폰이 본인 동선을 그리려고 받아가는 오늘의 배차.

    trip_type 을 안 보내면 등원을 준다. 구형 앱이 그대로 동작하게 하려는 것이다.
    """
    service_date = today_kst()
    return DispatchToday(
        service_date=service_date.isoformat(),
        trip_type=trip_type,
        result=load_dispatch(service_date, trip_type),
    )


@app.post("/api/dispatch/ack", response_model=DispatchAckRecord)
def acknowledge_today_dispatch(payload: DispatchAckCreate) -> DispatchAckRecord:
    """기사님이 오늘 배차표를 확인했다고 표시한다."""
    return acknowledge_dispatch(payload, today_kst())


@app.get("/api/dispatch/acks/today", response_model=DispatchAckList)
def read_today_acknowledgements(
    trip_type: TripType = Query("inbound"),
) -> DispatchAckList:
    """관리자 관제 화면이 어느 차량이 확인했는지 보려고 받아간다."""
    service_date = today_kst()
    return DispatchAckList(
        service_date=service_date.isoformat(),
        trip_type=trip_type,
        records=list_acknowledgements(service_date, trip_type),
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
    #
    # 등원과 하원은 타는 사람이 다르다. 아침엔 보호자가 모셔오고 오후엔
    # 센터 차를 타는 분이 있어 각각 따로 본다.
    label = "하원" if request.trip_type == "outbound" else "등원"
    attending = [
        passenger
        for passenger in request.passengers
        if passenger.is_attending(request.trip_type)
    ]
    absent_count = len(request.passengers) - len(attending)
    if not attending:
        raise HTTPException(
            status_code=422,
            detail=f"{label} 대상 어르신이 없습니다. 탑승 여부를 확인해 주세요.",
        )
    request = request.model_copy(update={"passengers": attending})

    # 노드 순서: 0=센터, 1..n=어르신, n+1..=자차 출발지.
    # optimize_routes 가 이 순서를 그대로 전제한다.
    custom_starts = [
        location
        for location in (vehicle.as_start_location() for vehicle in request.vehicles)
        if location is not None
    ]
    resolved = await resolve_locations(
        [request.center, *request.passengers, *custom_starts], settings
    )
    response = optimize_routes(request, resolved, settings)
    if absent_count:
        response.notices.append(f"{label} 미탑승 {absent_count}명은 배차에서 제외했습니다.")
    _archive_passengers(request, resolved)
    _archive_vehicles(request, resolved)

    # 이 계산을 했다는 사실을 남긴다. 실패해도 None 이 올 뿐 배차는 그대로 나간다.
    # 같은 날 두 번째 줄이 쌓이면 그 자체가 '앞 결과를 다시 짰다' 는 신호다.
    response.optimization_run_id = record_optimization_run(
        request, response, today_kst(), settings
    )
    # 여기서는 문자를 보내지 않는다. 계산은 원장님이 결과를 보려고 여러 번
    # 누르는 단계다. 확정 전에 기사님께 통보되면 안 된다.
    # 문자는 [배차 전송]을 눌렀을 때(/api/dispatch/notify) 나간다.
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
            sms_opt_in=payload.sms_opt_in,
            trip_type=payload.trip_type,
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
    trip_type: TripType | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> RideCompletionList:
    """오늘의 탑승·하차 기록.

    trip_type 을 주면 그쪽만, 안 주면 등원·하원을 모두 준다.
    구형 앱은 안 보내므로 지금까지처럼 전부 받는다.
    """
    service_date: date = today_kst()
    return RideCompletionList(
        service_date=service_date.isoformat(),
        trip_type=trip_type,
        records=list_completions(service_date, settings, trip_type),
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
