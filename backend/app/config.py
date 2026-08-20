from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    kakao_rest_api_key: str | None = None
    # 백엔드가 서빙하는 지도 페이지(/map)에 심는 키. 주소검색용 REST 키와 다르다.
    kakao_js_key: str | None = None
    # 송영 일지와 기사 기기 토큰이 저장되는 곳. 없으면 서버가 뜨지 않는다.
    supabase_url: str | None = None
    supabase_key: str | None = None
    cors_origins: str = "*"
    average_speed_kph: float = 25.0
    road_distance_factor: float = 1.25
    stop_service_minutes: int = 3
    turnaround_minutes: int = 5
    solver_time_limit_seconds: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        values = [item.strip() for item in self.cors_origins.split(",")]
        return [value for value in values if value] or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
