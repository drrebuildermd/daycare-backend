import csv
import io
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
from app.supabase_client import MISSING_MESSAGE, get_supabase, is_configured

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 송영 일지가 Supabase에 저장되므로 더 이상 선택 사항이 아니다.
    # 설정이 없는 채로 뜨면 '탑승 완료'를 누르는 순간에야 실패하므로 여기서 막는다.
    if not is_configured():
        raise RuntimeError(MISSING_MESSAGE)
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
def health() -> dict:
    """Render의 헬스 체크와 폰에서의 연결 확인용."""
    return {"status": "ok", "storage": "supabase"}


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
    html = (Path(__file__).parent / "static" / "map.html").read_text(encoding="utf-8")
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
    return upsert_completion(payload, settings)


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
