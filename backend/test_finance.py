"""v4.0 검증: 재무 비교.

가장 중요한 것 하나. 수가는 시간에 비례하지 않고 구간별 정액이다.
같은 40분을 당겨도 구간이 그대로면 손실이 0원이다. 비례식으로 짜면
3회차를 실제보다 훨씬 비싸게 봐서 늘 "증차하세요" 라고 답하게 된다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_finance.py
"""
from app.config import get_settings
from app.finance import (
    SERVICE_BANDS,
    band_label,
    band_of,
    build_scenarios,
    fuel_cost_won,
    rate_for,
    revenue_loss,
)
from app.models import PassengerInput

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()


def person(pid, name, grade=4, planned=None):
    return PassengerInput.model_validate({
        "id": pid, "name": name, "address": f"주소{pid}",
        "latitude": 37.5, "longitude": 127.0,
        "pickup_start": "08:00", "pickup_end": "10:00",
        "care_grade": grade, "planned_service_hours": planned,
    })


# ---------------------------------------------------------------------------
print("=== 1. 수가는 계단이다 (이 파일의 존재 이유) ===")
print("   같은 40분을 당겨도 구간이 그대로면 한 푼도 안 깎인다.")

check("11.83시간과 11.17시간은 같은 구간",
      band_of(11.83) == band_of(11.17) == (10.0, 12.0),
      f"{band_label(band_of(11.83))} / {band_label(band_of(11.17))}")
check("10.17시간과 9.5시간은 다른 구간",
      band_of(10.17) != band_of(9.5),
      f"{band_label(band_of(10.17))} -> {band_label(band_of(9.5))}")

# 40분(0.667시간)씩 당겨 본다.
safe = revenue_loss({"p1": 0.667}, [person("p1", "여유있는분", planned=11.83)], S)
tight = revenue_loss({"p1": 0.667}, [person("p1", "빠듯한분", planned=10.17)], S)
check("여유 있는 분은 손실 0원", safe[0] == 0, f"{safe[0]}원")
check("빠듯한 분은 손실 발생", tight[0] > 0, f"{tight[0]}원")
check("손실액이 구간 차액과 같다 (63000-57000)", tight[0] == 6000, tight[0])
print(f"   같은 40분: 여유 있는 분 {safe[0]:,}원 / 빠듯한 분 {tight[0]:,}원")


print()
print("=== 2. 구간 강등 금액이 표와 맞는가 ===")
for grade, before, after, expected in (
    (3, 11.0, 9.0, 67000 - 60000),
    (4, 11.0, 9.0, 63000 - 57000),
    (5, 11.0, 9.0, 60000 - 54000),
    (4, 9.0, 7.0, 57000 - 45000),
    (4, 7.0, 5.0, 45000 - 34000),
):
    got = revenue_loss({"p": before - after},
                       [person("p", "테스트", grade=grade, planned=before)], S)
    check(f"{grade}등급 {before:g}h→{after:g}h = {expected:,}원",
          got[0] == expected, f"{got[0]:,}원")


print()
print("=== 3. 수가표에 없으면 0원이 아니라 '모름' ===")
print("   모르는 것을 0으로 두면 손실이 없는 것처럼 보여 잘못된 권고가 나간다.")
check("1등급은 표에 없다", rate_for(S, 1, (10.0, 12.0)) is None)
unknown = revenue_loss({"p": 2.0}, [person("p", "일등급", grade=1, planned=11.0)], S)
check("금액에 더해지지 않는다", unknown[0] == 0, unknown[0])
check("항목으로도 잡히지 않는다", len(unknown[1]) == 0)
check("모른다고 알려 준다", len(unknown[2]) == 1, unknown[2])
print("   사유:", unknown[2][0] if unknown[2] else "(없음)")


print()
print("=== 4. 유류비 ===")
print(f"   연비 {S.fleet_fuel_efficiency_kmpl}km/L · 경유 {S.fuel_price_per_liter:,.0f}원/L")
check("90km = 10L = 16,000원", fuel_cost_won(90, S) == 16000, f"{fuel_cost_won(90, S):,}원")
check("0km 는 0원", fuel_cost_won(0, S) == 0)
check("거리가 늘면 유류비도 는다", fuel_cost_won(120, S) > fuel_cost_won(90, S))


print()
print("=== 5. 두 시나리오 저울질 ===")
people = [
    person("p1", "김빠듯", planned=10.17),
    person("p2", "이빠듯", planned=10.17),
    person("p3", "박여유", planned=11.83),
    person("p4", "최여유", planned=11.83),
]
# A안: 3회차. p1·p2 는 40분 일찍, p3·p4 도 40분 일찍 (하지만 구간 여유 있음)
early = {"p1": 0.667, "p2": 0.667, "p3": 0.667, "p4": 0.667}

a, b, notes = build_scenarios(
    "기존 차량 3회차", 95.0, early, people,
    "1대 증차 · 2회차 여유", 88.0, S, consider_revenue_loss=True,
)
check("A안 수가 삭감 = 빠듯한 두 분만", a.revenue_loss_won == 12000, f"{a.revenue_loss_won:,}원")
check("여유 있는 두 분은 항목에 없다", len(a.revenue_loss_items) == 2,
      [i.name for i in a.revenue_loss_items])
check("B안은 수가 삭감 없음", b.revenue_loss_won == 0)
check("B안에 증차 고정비가 들어간다", b.fixed_won == 40000, f"{b.fixed_won:,}원")
check("A안 합계 = 유류비 + 수가삭감",
      a.total_won == a.fuel_won + a.revenue_loss_won, a.total_won)
check("B안 합계 = 유류비 + 고정비",
      b.total_won == b.fuel_won + b.fixed_won, b.total_won)
print(f"   A안 {a.total_won:,}원 (유류 {a.fuel_won:,} + 수가 {a.revenue_loss_won:,})")
print(f"   B안 {b.total_won:,}원 (유류 {b.fuel_won:,} + 렌트 {b.fixed_won:,})")
# 두 분이 6,000원씩 깎인다고 40,000원짜리 차를 빌리는 건 손해다.
# 엔진이 그렇게 답해야 맞다.
check("두 명뿐이면 3회차가 싸다", a.total_won < b.total_won,
      f"A {a.total_won:,} vs B {b.total_won:,}")

print()
print("   ── 손익분기: 몇 명이 깎여야 증차가 유리해지는가")
crossover = None
for count in range(1, 15):
    many = [person(f"q{i}", f"빠듯{i}", planned=10.17) for i in range(count)]
    many_early = {f"q{i}": 0.667 for i in range(count)}
    ca, cb, _ = build_scenarios(
        "3회차", 95.0, many_early, many, "증차", 88.0, S, consider_revenue_loss=True,
    )
    if cb.total_won < ca.total_won:
        crossover = count
        break
check("어느 지점에서는 증차가 유리해진다", crossover is not None, crossover)
if crossover:
    print(f"   구간이 내려가는 분이 {crossover}명 이상이면 증차가 유리합니다.")
    check("손익분기가 상식적인 범위(3~12명)", 3 <= crossover <= 12, crossover)


print()
print("=== 6. 투트랙 — 수가를 빼면 판정이 뒤집힌다 ===")
print("   3회차의 비용이 유류비뿐이 되므로 대개 3회차가 싸진다.")
a_off, b_off, notes_off = build_scenarios(
    "기존 차량 3회차", 95.0, early, people,
    "1대 증차 · 2회차 여유", 88.0, S, consider_revenue_loss=False,
)
check("수가 삭감이 0원", a_off.revenue_loss_won == 0)
check("항목도 비어 있다", len(a_off.revenue_loss_items) == 0)
check("3회차가 싸진다", a_off.total_won < b_off.total_won,
      f"A {a_off.total_won:,} vs B {b_off.total_won:,}")
check("무엇을 뺐는지 알려 준다",
      any("수가 감소를 비용에 넣지 않고" in n for n in notes_off), notes_off)
print(f"   A안 {a_off.total_won:,}원 / B안 {b_off.total_won:,}원")
print("   안내:", notes_off[0] if notes_off else "(없음)")


print()
print("=== 7. 일찍 안 가면 손실도 없다 ===")
none_early, items, _ = revenue_loss({}, people, S)
check("조기 하원이 없으면 0원", none_early == 0)
check("항목도 없다", len(items) == 0)


print()
print("=== 8. 등급이 안 적힌 어르신은 센터 기본 등급 ===")
no_grade = PassengerInput.model_validate({
    "id": "x", "name": "무등급", "address": "주소x",
    "latitude": 37.5, "longitude": 127.0,
    "pickup_start": "08:00", "pickup_end": "10:00",
    "planned_service_hours": 11.0,
})
got, items, _ = revenue_loss({"x": 2.0}, [no_grade], S)
check(f"기본 {S.default_care_grade}등급으로 계산된다",
      got == 63000 - 57000, f"{got:,}원")
check("항목에 등급이 적힌다",
      items and items[0].care_grade == S.default_care_grade,
      items[0].care_grade if items else None)


print()
print("=== 9. 계획 이용시간을 안 적으면 센터 공통값 ===")
plain = PassengerInput.model_validate({
    "id": "y", "name": "무시간", "address": "주소y",
    "latitude": 37.5, "longitude": 127.0,
    "pickup_start": "08:00", "pickup_end": "10:00",
})
check(f"센터 공통값은 {S.stay_hours}시간", S.stay_hours == 8.0)
got2, items2, _ = revenue_loss({"y": 0.5}, [plain], S)
# 8.0시간에서 30분 당기면 7.5시간 -> 6~8 구간으로 강등
check("8시간에서 30분 당기면 구간이 내려간다", got2 == 57000 - 45000, f"{got2:,}원")


print()
print("=== 10. 구간 경계 ===")
check("정확히 8.0시간은 8~10 구간", band_of(8.0) == (8.0, 10.0))
check("7.99시간은 6~8 구간", band_of(7.99) == (6.0, 8.0))
check("3시간 미만은 구간 없음", band_of(2.5) is None)
check("13시간 이상은 마지막 구간", band_of(14.0) == SERVICE_BANDS[-1])


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
