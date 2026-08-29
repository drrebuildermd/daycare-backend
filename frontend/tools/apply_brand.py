"""마중ON Care 브랜드 토큰을 화면 코드에 입힌다.

하는 일 두 가지.
  1) react-native 의 Text 대신 src/ui/Text.js (Pretendard) 를 쓰게 import 를 바꾼다.
  2) 흩어져 있던 색 리터럴을 브랜딩 패키지 theme_tokens.json 의 값으로 옮긴다.

마크업과 로직은 건드리지 않는다. 색 값과 import 줄만 바꾼다.

실행: frontend 폴더에서  python3 tools/apply_brand.py
"""
import io
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# ── 색 매핑 ───────────────────────────────────────────────────────────────
# 왼쪽은 지금 코드에 박혀 있는 값, 오른쪽은 브랜드 토큰.
COLORS = {
    # 브랜드 주색
    "#0F766E": "#0BA38E",  # Teal — 지금까지의 사실상 primary
    "#0f766e": "#0BA38E",
    "#0D9488": "#0BA38E",
    # 글자
    "#0F172A": "#0D2540",  # Deep Navy
    "#1E293B": "#0D2540",
    "#334155": "#0D2540",
    "#475569": "#667085",
    "#64748B": "#667085",
    "#94A3B8": "#98A2B3",  # placeholder 는 한 단계 더 흐리게 둔다
    "#374151": "#667085",
    # 면·선
    "#E2E8F0": "#E4E7EC",
    "#E5E7EB": "#E4E7EC",
    "#CBD5E1": "#E4E7EC",
    "#F1F5F9": "#F2F4F7",  # Soft Gray
    "#F8FAFC": "#F8F9FB",
    "#FAFAFA": "#F8F9FB",
    "#f3f4f6": "#F2F4F7",
    # 성공/완료
    "#ECFDF5": "#E9F7EF",
    "#CCFBF1": "#E9F7EF",
    "#99F6E4": "#6ED6C1",
    "#A7F3D0": "#6ED6C1",
    "#047857": "#237B4B",
    "#059669": "#3BB273",
    "#10B981": "#3BB273",
    "#166534": "#237B4B",
    # 정보 (파랑 계열을 teal 계열로 모은다)
    "#E0F2FE": "#E6F7F4",
    "#EFF6FF": "#E6F7F4",
    "#BFDBFE": "#6ED6C1",
    "#93C5FD": "#6ED6C1",
    "#0369A1": "#07705F",
    "#0284C7": "#0BA38E",
    "#0EA5E9": "#0BA38E",
    "#1D4ED8": "#0BA38E",
    # 보라 (관제 경로색으로만 쓰이던 것)
    "#EDE9FE": "#E6F7F4",
    "#7C3AED": "#07705F",
    "#7E22CE": "#07705F",
    # 주의
    "#FEF3C7": "#FEF6E7",
    "#FFFBEB": "#FEF6E7",
    "#FFF7ED": "#FEF6E7",
    "#FCD34D": "#F2B84B",
    "#B45309": "#8A6100",
    "#9A3412": "#8A6100",
    # 오류
    "#FEF2F2": "#FCEDED",
    "#fee2e2": "#FCEDED",
    "#DC2626": "#D64545",
    "#B91C1C": "#9B2C2C",
    "#b91c1c": "#9B2C2C",
    # 카카오 노랑 버튼 → 브랜드 규칙상 '길안내'는 Teal 이다.
    "#FEE500": "#0BA38E",
    "#191919": "#FFFFFF",
}

# ── Pretendard Text 로 갈아끼울 파일 ──────────────────────────────────────
TEXT_FILES = {
    "App.js": "./src/ui/Text",
    "src/screens/ModeGate.js": "../ui/Text",
    "src/screens/DriverScreen.js": "../ui/Text",
    "src/components/Accordion.js": "../ui/Text",
    "src/components/AddressSearch.js": "../ui/Text",
    "src/components/AddressSearch.web.js": "../ui/Text",
    "src/components/DriverPushPanel.js": "../ui/Text",
    "src/components/PairRuleEditor.js": "../ui/Text",
    "src/components/PassengerForm.js": "../ui/Text",
    "src/components/RouteMap.js": "../ui/Text",
    "src/components/RouteMap.web.js": "../ui/Text",
    "src/components/SummaryBar.js": "../ui/Text",
    "src/components/VehicleForm.js": "../ui/Text",
    "src/components/VehicleResults.js": "../ui/Text",
}

COLOR_FILES = list(TEXT_FILES) + ["src/theme.js"]


def swap_text_import(src, rel):
    """react-native import 목록에서 Text 를 빼고, ui/Text 를 따로 들여온다."""
    m = re.search(r"import \{([^}]*)\} from 'react-native';", src)
    if not m:
        return src, False
    names = [n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()]
    if "Text" not in names:
        return src, False
    names.remove("Text")

    if names:
        joined = ", ".join(names)
        if len(joined) > 88:  # 길면 여러 줄로 접는다
            body = "\n" + "".join("  %s,\n" % n for n in names)
            replacement = "import {%s} from 'react-native';" % body
        else:
            replacement = "import { %s } from 'react-native';" % joined
    else:
        replacement = ""

    src = src[:m.start()] + replacement + src[m.end():]
    anchor = "import React"
    line_end = src.index("\n", src.index(anchor)) + 1
    return src[:line_end] + "import Text from '%s';\n" % rel + src[line_end:], True


changed = []
color_hits = 0

for rel_path in COLOR_FILES:
    path = os.path.join(ROOT, rel_path)
    src = original = io.open(path, encoding="utf-8").read()

    if rel_path in TEXT_FILES:
        src, swapped = swap_text_import(src, TEXT_FILES[rel_path])
    for old, new in COLORS.items():
        if old in src:
            color_hits += src.count(old)
            src = src.replace(old, new)

    if src != original:
        io.open(path, "w", encoding="utf-8", newline="\n").write(src)
        changed.append(rel_path)

print("색 리터럴 %d곳 교체" % color_hits)
print("파일 %d개 수정:" % len(changed))
for c in changed:
    print("   ", c)
