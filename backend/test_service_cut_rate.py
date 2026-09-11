"""v4.3.2 검증: 수가 경고는 진짜 깎일 때만 뜬다.

앞 버전에서 '등원이 늦어지면 그날 이용시간이 줄어 수가 구간이 내려간다' 는
경고를 띄웠다. 현장 로직을 잘못 이해한 것이었다.

등원이 10분 늦어져도 하원 배차가 실제 센터 도착 시각에 맞춰 픽업을 뒤로
미뤄 체류 시간을 보장한다. 그래서 그날 수가는 그대로다. 그걸 붉게 띄우면
멀쩡한 배차를 두고 원장님이 불안해하신다.

수가가 실제로 깎이는 것은 엔진이 최후수단으로 '계획 이용시간 자체를'
줄였을 때뿐이다. 그리고 줄였다고 다 깎이는 것도 아니다. 9시간을
8시간으로 줄여도 둘 다 8~10 구간이라 한 푼도 안 깎인다.

실행: backend 폴더에서  .venv\\Scripts\\python.exe -X utf8 test_service_cut_rate.py
"""
from app.config import get_settings
from app.escalate import _service_cut_losses
from app.finance import band_label, band_of
from app.models import OptimizeRequest

failures = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' -> ' + str(detail)) if detail else ''}")
    if not ok:
        failures.append(label)


S = get_settings()


def request_with(people):
    """people: (이름, 계획 이용시간, 등급)"""
    return OptimizeRequest.model_validate({
        "trip_type": "inbound",
        "center": {"name": "행복센터", "address": "센터주소",
                   "latitude": 37.5, "longitude": 127.0},
        "vehicles": [{"id": "v1", "vehicle_type": "스타리아",
                      "plate_number": "00검0001", "capacity": 9}],
        "passengers": [
            {"id": f"pa{i}", "name": n, "address": "주소",
             "latitude": 37.5, "longitude": 127.0,
             "planned_service_hours": h, "care_grade": g}
            for i, (n, h, g) in enumerate(people, start=1)
        ],
    })


# ---------------------------------------------------------------------------
print("=== 1. 안 줄였으면 아무 경고도 없다 ===")
print("   등원이 아무리 밀려도 이 계산에는 들어오지 않는다.")

req = request_with([("김마중", 8, "4"), ("이케어", 8, "3")])
won, items, unknown = _service_cut_losses(req, S, 0)
check("단축 0분 -> 손실 0원", won == 0, won)
check("단축 0분 -> 명단 비어 있음", not items, len(items))
check("단축 0분 -> 모르는 것도 없음", not unknown, unknown)


print()
print("=== 2. 줄였어도 구간이 그대로면 한 푼도 안 깎인다 (핵심) ===")
print("   9시간을 8시간으로 줄여도 둘 다 8~10 구간 안이다.")
print("   구간은 low <= h < high 라 10시간은 8~10 이 아니라 10~12 이다.")
print("   여기를 헷짚으면 없는 손실을 보고하거나 있는 손실을 놓친다.")

check("전제 — 9시간과 8시간은 같은 구간",
      band_of(9) == band_of(8), f"{band_label(band_of(9))} / {band_label(band_of(8))}")
check("전제 — 10시간은 한 구간 위다",
      band_of(10) != band_of(9), f"{band_label(band_of(10))} / {band_label(band_of(9))}")
req = request_with([("장수한", 9, "4")])
won, items, unknown = _service_cut_losses(req, S, 60)
check("60분 줄여도 손실 0원", won == 0, won)
check("경고 명단에 안 오른다", not items, [i.name for i in items])
print("   → 9시간 어르신은 1시간 줄여도 8~10 구간 그대로라 수가 변동 없음")


print()
print("=== 3. 구간이 내려가면 그분만 특정해서 잡는다 ===")
print("   8시간 -> 7시간이면 8~10 구간에서 6~8 구간으로 내려간다.")

check("전제 — 8시간과 7시간은 다른 구간",
      band_of(8) != band_of(7), f"{band_label(band_of(8))} / {band_label(band_of(7))}")

req = request_with([
    ("김마중", 8, "4"),     # 8 -> 7  8~10 에서 6~8 로 내려감
    ("장수한", 9, "4"),     # 9 -> 8  둘 다 8~10 이라 그대로
    ("이케어", 8, "3"),     # 8 -> 7  8~10 에서 6~8 로 내려감
])
won, items, unknown = _service_cut_losses(req, S, 60)
names = [i.name for i in items]
check("구간이 내려간 두 분만 잡힌다", sorted(names) == ["김마중", "이케어"], names)
check("구간 그대로인 분은 안 잡힌다", "장수한" not in names, names)
check("손실 금액이 0보다 크다", won > 0, f"{won:,}원")
check("합계가 항목의 합과 맞는다", won == sum(i.lost_won for i in items), won)

for item in items:
    print(f"     {item.name}({item.care_grade}등급) "
          f"{item.planned_hours}h→{item.actual_hours}h · "
          f"{item.planned_band}→{item.actual_band} · -{item.lost_won:,}원")
    check(f"{item.name}: 계획 시간이 줄어든 것으로 기록",
          item.actual_hours < item.planned_hours,
          f"{item.planned_hours} -> {item.actual_hours}")
    check(f"{item.name}: 구간이 실제로 달라졌다",
          item.planned_band != item.actual_band,
          f"{item.planned_band} / {item.actual_band}")
    check(f"{item.name}: 깎인 금액이 0보다 크다", item.lost_won > 0, item.lost_won)


print()
print("=== 4. 등급외 어르신은 깎일 수가가 없다 ===")
print("   급여 대상이 아니라 조기 하원해도 매출이 줄지 않는다. 0원이지 '모름' 이 아니다.")

req = request_with([("무등급", 8, "none")])
won, items, unknown = _service_cut_losses(req, S, 60)
check("손실 0원", won == 0, won)
check("경고에 안 뜬다", not items, [i.name for i in items])
check("모르는 것으로도 안 샌다", not unknown, unknown)


print()
print("=== 5. 표에 없는 등급은 0원으로 둔갑시키지 않는다 ===")
print("   1·2등급과 인지지원등급 수가는 아직 표에 없다. 모르면 모른다고 해야 한다.")

req = request_with([("일등급", 8, "1")])
won, items, unknown = _service_cut_losses(req, S, 60)
check("금액을 지어내지 않는다", won == 0, won)
check("경고 명단에도 안 올린다", not items, [i.name for i in items])
check("대신 모른다고 알린다", bool(unknown), unknown)
if unknown:
    print("     " + unknown[0])


print()
print("=== 6. 계획이 짧은 분은 바닥(1시간)에 걸려 덜 줄어든다 ===")
print("   optimizer 의 바닥과 여기 계산이 어긋나면 없는 손실을 보고하게 된다.")

req = request_with([("짧게", 1.5, "4")])
won, items, unknown = _service_cut_losses(req, S, 60)
# 90분에서 60분을 빼면 30분이지만 바닥이 60분이라 실제로는 30분만 줄어든다.
# 게다가 1.5시간도 1시간도 3시간 미만이라 구간 자체가 없다 -> 깎일 것이 없다.
check("3시간 미만은 구간이 없어 손실로 잡지 않는다", not items, [i.name for i in items])
check("금액도 0원", won == 0, won)


print()
print("=== 7. 문구가 등원 지연을 수가와 엮지 않는다 ===")
from app.escalate import Relaxation, Adjustment, TRANSIT  # noqa: E402

# 시각만 밀린 경우 — 수가 이야기가 나오면 안 된다.
only_late = Relaxation(
    applied=True, steps_tried=2, window_slack_minutes=30,
    priority="revenue", protected="service",
    adjusted=[Adjustment("pa1", "김마중", "07:30~08:45", "09:05", 20, True)],
)
line = only_late.headline
print("   [시각만 밀린 경우]")
print("     " + line)
check("수가 이야기가 없다", "수가" not in line, line)
check("구간 이야기도 없다", "구간" not in line, line)
check("그래도 밀린 분은 알린다", "김마중" in line, line)

# 실제로 구간이 내려간 경우 — 그때는 분명히 말해야 한다.
req = request_with([("김마중", 8, "4")])
won, items, unknown = _service_cut_losses(req, S, 60)
real_cut = Relaxation(
    applied=True, steps_tried=6, window_slack_minutes=60,
    transit_extra_minutes=40, service_cut_minutes=60,
    priority="comfort", protected=TRANSIT, protected_conceded=True,
    service_cut_losses=items, service_cut_loss_won=won,
)
line = real_cut.headline
print()
print("   [계획 이용시간을 줄인 경우]")
print("     " + line)
check("수가 구간이 내려간다고 말한다", "수가 구간" in line, line)
check("누구인지 밝힌다", "김마중" in line, line)
check("얼마인지 밝힌다", f"{won:,}" in line, line)
check("어느 구간에서 어디로인지 밝힌다",
      items[0].planned_band in line and items[0].actual_band in line, line)


print()
if failures:
    print(f"실패 {len(failures)}건: " + ", ".join(failures))
    raise SystemExit(1)
print("전부 통과했습니다.")
