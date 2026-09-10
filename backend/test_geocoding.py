"""v4.1.1 검증: 주소 → 좌표 변환.

현장에서 '주소를 찾을 수 없습니다' 로 배차가 통째로 막혔다.

원인은 두 가지였다.
  1) 양식에 넣어 둔 예시 주소가 실존하지 않았다. 원장님이 예시 줄을 지우지
     않고 올리시면 그 두 줄 때문에 전체가 막힌다.
  2) 첫 번째 실패에서 멈춰서, 34명 명단이면 한 분씩 34번 고쳐야 했다.

카카오 주소 검색은 행정구가 하나만 어긋나도 0건을 낸다.
  "창원시 의창구 중앙대로 151" -> 0건 (실제로는 성산구)
  "창원시 성산구 중앙대로 151" -> 1건

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_geocoding.py
  (실제 카카오 API 를 부른다. 네트워크와 키가 필요하다.)
"""
import asyncio

from dotenv import load_dotenv

load_dotenv()

from fastapi import HTTPException  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.geocoding import _clean, resolve_locations  # noqa: E402
from app.models import LocationInput  # noqa: E402

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()


def loc(name, address):
    return LocationInput(name=name, address=address)


def run(locations):
    return asyncio.run(resolve_locations(locations, S))


# ---------------------------------------------------------------------------
print("=== 1. 공백 정리 ===")
print("   엑셀에서 Alt+Enter 로 줄을 나눠 적으시는 경우가 있다.")
cases = [
    ("  앞뒤 공백  ", "앞뒤 공백"),
    ("가운데\n개행", "가운데 개행"),
    ("탭\t포함", "탭 포함"),
    ("두칸  공백", "두칸 공백"),
    ("", ""),
]
for raw, want in cases:
    check(f"{raw!r} -> {want!r}", _clean(raw) == want, repr(_clean(raw)))


print()
print("=== 2. 실존 주소는 찾는다 ===")
real = [
    loc("창원시청", "경남 창원시 성산구 중앙대로 151"),
    loc("서울시청", "서울 중구 세종대로 110"),
    loc("판교", "경기 성남시 분당구 판교역로 235"),
]
resolved = run(real)
check("세 곳 모두 좌표가 나온다", len(resolved) == 3)
for item in resolved:
    check(f"{item.name} 좌표가 0 이 아니다",
          item.latitude != 0.0 and item.longitude != 0.0,
          f"{item.latitude:.4f}, {item.longitude:.4f}")


print()
print("=== 3. 건물명만 적어도 찾는다 (키워드 검색 대체) ===")
print("   어르신 주소를 아파트명으로 적어 두시는 경우가 많다.")
by_name = run([loc("아파트", "창원 용지아이파크"), loc("관공서", "창원시청")])
for item in by_name:
    check(f"{item.name} 좌표를 찾았다",
          item.latitude != 0.0, f"{item.latitude:.4f}, {item.longitude:.4f}")


print()
print("=== 4. 새 양식의 예시 주소가 실제로 찾아진다 (이번 버그의 핵심) ===")
print("   예시 줄을 지우지 않고 올리셔도 배차가 막히지 않아야 한다.")
samples = run([
    loc("예시1", "경남 창원시 성산구 중앙대로 151"),
    loc("예시2", "경남 창원시 성산구 원이대로 579번길 13"),
])
for item in samples:
    check(f"{item.name} 좌표를 찾았다", item.latitude != 0.0,
          f"{item.latitude:.4f}, {item.longitude:.4f}")


print()
print("=== 5. 못 찾은 주소를 한 번에 모아 알린다 ===")
print("   첫 번째에서 멈추면 34명 명단을 34번 고쳐야 한다.")
try:
    run([
        loc("정상", "경남 창원시 성산구 중앙대로 151"),
        loc("가짜1", "창원시 의창구 중앙대로 100"),
        loc("가짜2", "창원시 성산구 원이대로 200"),
        loc("가짜3", "없는시 없는구 없는로 999"),
    ])
    check("실패를 알린다", False, "예외가 나지 않았다")
except HTTPException as error:
    detail = error.detail
    check("422 로 알린다", error.status_code == 422, error.status_code)
    check("건수를 말한다", "3건" in detail, detail[:40])
    check("가짜1 이 목록에 있다", "가짜1" in detail)
    check("가짜2 도 함께 있다 (첫 실패에서 안 멈춘다)", "가짜2" in detail)
    check("가짜3 까지 있다", "가짜3" in detail)
    check("정상인 곳은 목록에 없다", "정상 —" not in detail)
    check("시·구와 번지를 확인하라고 안내한다", "시·구 이름과 번지" in detail)
    # 양식의 예시가 이제 실존 주소라 '예시 줄을 지우세요' 안내는 뺐다.
    # 대신 카카오/네이버 DB 차이와 건물명 대안을 알려 준다.
    check("카카오와 네이버가 다르다는 것을 알려 준다", "네이버" in detail, detail[-80:])
    check("건물명으로 적어 보라고 안내한다", "건물 이름" in detail)
    print()
    print("   실제 문구:")
    for line in detail.split("\n"):
        print("     " + line)


print()
print("=== 6. 좌표가 이미 있으면 API 를 부르지 않는다 ===")
given = run([LocationInput(name="좌표있음", address="아무거나",
                           latitude=35.2, longitude=128.6)])
check("준 좌표를 그대로 쓴다",
      (given[0].latitude, given[0].longitude) == (35.2, 128.6),
      f"{given[0].latitude}, {given[0].longitude}")


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
