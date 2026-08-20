from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from .config import Settings
from .models import LocationInput


@dataclass(frozen=True)
class ResolvedLocation:
    name: str
    address: str
    latitude: float
    longitude: float


async def resolve_locations(
    locations: list[LocationInput], settings: Settings
) -> list[ResolvedLocation]:
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
    async with httpx.AsyncClient(timeout=8.0) as client:
        for item in locations:
            if item.latitude is not None and item.longitude is not None:
                resolved.append(
                    ResolvedLocation(
                        name=item.name,
                        address=item.address,
                        latitude=item.latitude,
                        longitude=item.longitude,
                    )
                )
                continue

            response = await client.get(
                "https://dapi.kakao.com/v2/local/search/address.json",
                params={"query": item.address},
                headers=headers,
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"카카오 주소 검색 실패({item.name}): HTTP {response.status_code}",
                )
            documents = response.json().get("documents", [])
            if not documents:
                raise HTTPException(
                    status_code=422,
                    detail=f"주소를 찾을 수 없습니다: {item.name} / {item.address}",
                )
            document = documents[0]
            resolved.append(
                ResolvedLocation(
                    name=item.name,
                    address=item.address,
                    latitude=float(document["y"]),
                    longitude=float(document["x"]),
                )
            )
    return resolved

