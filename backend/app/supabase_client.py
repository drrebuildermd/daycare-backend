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


def key_kind(token: str | None) -> str:
    """백엔드가 어떤 종류의 키를 쓰는지 판별한다.

    RLS 를 켜기 전에 반드시 확인해야 한다. 공개용 키(publishable/anon)는
    RLS 의 적용을 받으므로, 정책 없이 RLS 를 켜면 백엔드가 즉시
    테이블에 접근하지 못하고 서버가 기동조차 못 한다.
    """
    if not token:
        return "none"
    if token.startswith("sb_secret_"):
        return "secret"
    if token.startswith("sb_publishable_"):
        return "publishable"
    # 구형 JWT 키. payload 의 role 클레임으로 구분한다.
    if token.count(".") == 2:
        import base64
        import json

        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            role = json.loads(base64.urlsafe_b64decode(payload)).get("role")
            return "secret" if role == "service_role" else "publishable"
        except Exception:  # noqa: BLE001
            return "unknown"
    return "unknown"


PUBLISHABLE_WARNING = (
    "[보안 경고] 백엔드가 공개용 Supabase 키를 쓰고 있습니다.\n"
    "  - 지금은 RLS 가 꺼져 있어 동작하지만, 같은 등급의 키가 앱에도 들어 있어\n"
    "    앱 번들만 뜯으면 어르신 개인정보를 전부 조회할 수 있습니다.\n"
    "  - SUPABASE_KEY 를 secret 키(sb_secret_...)로 교체한 뒤 RLS 를 켜세요.\n"
    "  - 순서를 바꾸면(먼저 RLS) 서버가 기동하지 못합니다."
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
