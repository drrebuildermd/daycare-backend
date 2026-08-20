"""Supabase 연결을 한 곳에서 만든다.

전에는 main.py가 자체적으로 클라이언트를 들고 있었는데, 송영 일지까지 Supabase로
옮기면서 여러 모듈이 같은 연결을 써야 해 여기로 모았다.
"""
from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


class SupabaseNotConfigured(RuntimeError):
    """SUPABASE_URL / SUPABASE_KEY 가 없을 때."""


MISSING_MESSAGE = (
    "SUPABASE_URL 과 SUPABASE_KEY 가 설정되지 않았습니다.\n"
    "송영 완료 기록이 Supabase에 저장되므로 이 값 없이는 서버를 띄울 수 없습니다.\n"
    "로컬은 backend/.env 에, Render는 대시보드의 Environment 에 넣어 주세요."
)


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_key)


@lru_cache
def get_supabase() -> Client:
    # os.environ을 직접 읽으면 load_dotenv() 호출 순서에 결과가 달라진다.
    # 나머지 설정과 같은 경로(Settings)로 읽어 그 의존성을 없앤다.
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise SupabaseNotConfigured(MISSING_MESSAGE)
    return create_client(settings.supabase_url, settings.supabase_key)
