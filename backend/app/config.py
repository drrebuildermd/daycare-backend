from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    kakao_rest_api_key: str | None = None
    # 백엔드가 서빙하는 지도 페이지(/map)에 심는 키. 주소검색용 REST 키와 다르다.
    kakao_js_key: str | None = None
    # 탑승 완료 시 보호자에게 문자를 보내는 솔라피 자격증명.
    # 없으면 발송을 건너뛴다. (배차/일지 기능은 그대로 동작)
    solapi_api_key: str | None = None
    solapi_api_secret: str | None = None
    solapi_sender: str | None = None
    # 송영 일지와 기사 기기 토큰이 저장되는 곳. 없으면 서버가 뜨지 않는다.
    supabase_url: str | None = None
    supabase_key: str | None = None
    cors_origins: str = "*"
    # 센터 식별자. 지금은 한 곳뿐이라 기본값으로 두지만, 이 값을 나중에
    # 넣으면 이미 쌓인 기록에는 소급할 수 없어 지금부터 채운다.
    center_id: str = "default"
    average_speed_kph: float = 25.0
    road_distance_factor: float = 1.25
    stop_service_minutes: int = 3
    turnaround_minutes: int = 5
    # 어르신이 센터에 머무시는 시간. 주야간보호는 보통 8시간이다.
    # 하원 시각을 따로 적지 않으면 등원 시각에 이만큼을 더해 정한다.
    # 일찍 오신 분이 일찍 가시고, 늦게 오신 분이 늦게 가신다.
    stay_hours: float = 8.0
    solver_time_limit_seconds: int = 15

    # ── 재무 비교 (v4.0) ──────────────────────────────────────
    #
    # 3회차를 무리해서 도는 것과 차를 한 대 늘리는 것 중 어느 쪽이 싼지
    # 저울질하는 데 쓴다. 자세한 설명은 app/finance.py 에 있다.

    # 센터 차량 평균 연비. 스타리아급 시내 주행 기준.
    fleet_fuel_efficiency_kmpl: float = 9.0
    # 경유 1리터 값. 유가는 자주 바뀌니 원장님이 갱신하신다.
    fuel_price_per_liter: float = 1600.0

    # 증차 시뮬레이션에 쓸 표준 차량. 15인승 스타리아 월 렌트비 일할 환산.
    spare_vehicle_daily_cost: float = 40000.0
    spare_vehicle_capacity: int = 9
    # 부족한 것이 휠체어석인데 리프트 없는 차를 넣으면 B안이 성립하지 않는다.
    # 그래서 최소 1자리는 있어야 한다.
    spare_vehicle_wheelchair_capacity: int = 1

    # 등급이 적히지 않은 어르신에게 적용할 등급.
    # 현장에서 가장 흔한 것이 3~5등급이라 가운데를 기본으로 둔다.
    default_care_grade: int = 4

    # 장기요양 주야간보호 수가표. "등급:구간하한-구간상한" -> 1일 금액(원).
    #
    # 고시는 해마다 바뀐다. 표에 없는 조합은 0원이 아니라 '모름' 으로 다뤄
    # 재무 판정을 보류한다. 모르는 것을 0으로 두면 손실이 없는 것처럼 보여
    # 잘못된 권고가 나가기 때문이다.
    #
    # 1·2등급은 자료를 받지 못해 비워 두었다. 그 등급 어르신이 계시면
    # 판정이 보류되고 그 사실을 화면에 알린다.
    care_rate_table: dict[str, int] = {
        "3:3-6": 36000, "4:3-6": 34000, "5:3-6": 32000,
        "3:6-8": 48000, "4:6-8": 45000, "5:6-8": 42000,
        "3:8-10": 60000, "4:8-10": 57000, "5:8-10": 54000,
        "3:10-12": 67000, "4:10-12": 63000, "5:10-12": 60000,
    }

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        values = [item.strip() for item in self.cors_origins.split(",")]
        return [value for value in values if value] or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
