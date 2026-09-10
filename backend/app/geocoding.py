"""주소를 좌표로 바꾼다.

카카오 주소 검색은 엄격하다. 행정구가 하나라도 어긋나면 0건을 낸다.
  "창원시 의창구 중앙대로 151"  -> 0건 (실제로는 성산구다)
  "창원시 성산구 중앙대로 151"  -> 1건

카카오와 네이버는 주소 DB 가 다르다. 네이버에 있는 번지가 카카오에 없는
경우가 실제로 있다. 그래서 세 가지를 한다.

  1) 주소 검색으로 못 찾으면 키워드 검색으로 한 번 더 찾는다.
     어르신 주소를 '○○아파트' 처럼 건물명으로 적어 두시는 경우가 많은데,
     주소 검색은 그걸 못 찾고 키워드 검색은 찾는다.
  2) 첫 번째 실패에서 멈추지 않고 끝까지 훑어 못 찾은 것을 모아 알린다.
     34명 명단에서 한 분씩 고쳐 가며 34번 다시 계산하게 하면 안 된다.
  3) 배차에서는 못 찾은 분만 빼고 나머지를 배차한다.
     한 분의 주소 때문에 마흔 분의 배차를 통째로 막으면 안 된다.
"""
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from .config import Settings
from .models import LocationInput

ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


@dataclass(frozen=True)
class ResolvedLocation:
    name: str
    address: str
    latitude: float
    longitude: float


def _clean(address: str) -> str:
    """앞뒤 공백을 떼고 가운데 공백·개행·탭을 한 칸으로 만든다.

    카카오는 이런 것에 관대하지만, 우리가 정규식으로 주소를 검사하는 곳이
    있고 화면에도 그대로 뜨므로 여기서 한 번 다듬는다.
    엑셀에서 Alt+Enter 로 줄을 나눠 적으시는 경우가 있다.
    """
    return " ".join(str(address or "").split())


async def _lookup(client: httpx.AsyncClient, address: str, headers: dict):
    """좌표 한 쌍을 찾는다. 못 찾으면 None.

    주소 검색을 먼저 하고, 없으면 키워드 검색으로 한 번 더 본다.
    """
    response = await client.get(ADDRESS_URL, params={"query": address}, headers=headers)
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"카카오 주소 검색에 실패했습니다 (HTTP {response.status_code}).",
        )
    documents = response.json().get("documents", [])
    if documents:
        return float(documents[0]["y"]), float(documents[0]["x"])

    # 건물명·아파트명으로 적힌 주소는 여기서 걸린다.
    keyword = await client.get(
        KEYWORD_URL, params={"query": address, "size": 1}, headers=headers
    )
    if keyword.status_code == 200:
        found = keyword.json().get("documents", [])
        if found:
            return float(found[0]["y"]), float(found[0]["x"])
    return None


def address_failure_message(names: list[str]) -> str:
    """못 찾은 주소를 원장님께 알리는 문구."""
    shown = names[:5]
    lines = "\n".join(f"· {name}" for name in shown)
    rest = len(names) - len(shown)
    more = f"\n... 그 밖에 {rest}명" if rest > 0 else ""
    return (
        f"주소 {len(names)}건을 지도에서 찾지 못했습니다.\n{lines}{more}\n\n"
        "시·구 이름과 번지가 실제와 맞는지 확인해 주세요. "
        "카카오 지도에 없는 번지는 네이버에 있어도 찾지 못합니다.\n"
        "아파트나 건물 이름으로 적어 보시면 찾는 경우가 많습니다."
    )


async def resolve_locations_partial(
    locations: list[LocationInput], settings: Settings
) -> tuple[list[ResolvedLocation], list[int]]:
    """찾은 것과 못 찾은 자리를 함께 돌려준다.

    못 찾은 자리에도 항목을 넣는다(좌표 0). 자리를 비우면 노드 번호가
    어긋나기 때문이다. 부르는 쪽이 그 자리를 걷어낸다.
    """
    unresolved = [item for item in locations if item.latitude is None]
    if unresolved and not settings.kakao_rest_api_key:
        names = ", ".join(item.name for item in unresolved[:3])
        suffix = " 외" if len(unresolved) > 3 else ""
        raise HTTPException(
            status_code=422,
            detail=(
                f"좌표가 없는 주소({names}{suffix})를 변환할 KAKAO_REST_API_KEY가 없습니다. "
                "backend/.env에 키를 설정하거나 위도/경도를 함께 전달하세요."
            ),
        )

    headers = {"Authorization": f"KakaoAK {settings.kakao_rest_api_key}"}
    resolved: list[ResolvedLocation] = []
    failed_indexes: list[int] = []

    async with httpx.AsyncClient(timeout=8.0) as client:
        for position, item in enumerate(locations):
            if item.latitude is not None and item.longitude is not None:
                resolved.append(ResolvedLocation(
                    name=item.name, address=item.address,
                    latitude=item.latitude, longitude=item.longitude,
                ))
                continue

            address = _clean(item.address)
            point = await _lookup(client, address, headers)
            if point is None:
                failed_indexes.append(position)
                resolved.append(ResolvedLocation(
                    name=item.name, address=address, latitude=0.0, longitude=0.0,
                ))
                continue

            latitude, longitude = point
            resolved.append(ResolvedLocation(
                name=item.name, address=address,
                latitude=latitude, longitude=longitude,
            ))

    return resolved, failed_indexes


async def resolve_locations(
    locations: list[LocationInput], settings: Settings
) -> list[ResolvedLocation]:
    """하나라도 못 찾으면 거절한다.

    센터 주소처럼 빠지면 배차 자체가 성립하지 않는 곳에 쓴다.
    """
    resolved, failed_indexes = await resolve_locations_partial(locations, settings)
    if failed_indexes:
        raise HTTPException(
            status_code=422,
            detail=address_failure_message([locations[i].name for i in failed_indexes]),
        )
    return resolved
