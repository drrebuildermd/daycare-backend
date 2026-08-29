"""마중ON Care 브랜드 asset 생성기.

브랜딩 패키지가 준 majungon_mroute_symbol.svg 를 기준으로 앱 아이콘·스플래시를
다시 그린다. 심볼을 새로 디자인하는 것이 아니라, SVG 안의 좌표·색·구조를 그대로
읽어 빌드에 쓸 수 있는 해상도와 여백으로 래스터화하는 것이다.

패키지의 PNG 를 그대로 쓰지 않는 이유는 두 가지다.
  1) app_icon_1024.png 는 흰 획 가장자리에 빗살 모양 아티팩트가 있다.
  2) adaptive_foreground_1024.png 는 내용의 15.5% 가 안드로이드 원형 마스크
     안전영역(가운데 66%) 밖으로 나가 있어 기종에 따라 잘린다.

실행: frontend 폴더에서
      ..\\backend\\.venv\\Scripts\\python.exe -X utf8 tools\\make_brand_assets.py
"""
import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")

# ── SVG(viewBox 0 0 300 220) 에서 그대로 옮긴 좌표 ────────────────────────
ROUTE = [
    ((42, 172), (60, 118), (78, 54), (106, 54)),
    ((106, 54), (134, 54), (143, 151), (166, 151)),
    ((166, 151), (190, 151), (206, 59), (238, 63)),
]
STROKE_W = 18
# 노드는 '색 링 + 흰 중심'이다. stroke 8 이 r13 위에 얹히므로 링은 r9~r17.
NODES = [((42, 172), (13, 92, 120)), ((166, 151), (11, 163, 142))]
NODE_OUTER, NODE_INNER = 17, 9
PIN_AT = (238, 63)
PIN_PATH = [
    ((0, -20), (15, -20), (27, -9), (27, 6)),
    ((27, 6), (27, 24), (0, 49), (0, 49)),
    ((0, 49), (0, 49), (-27, 24), (-27, 6)),
    ((-27, 6), (-27, -9), (-15, -20), (0, -20)),
]
PIN_GREEN = (59, 178, 115)
PIN_DOT_AT, PIN_DOT_R = (0, 5), 8

# 그라디언트 정지점 (SVG routeGradient: 왼쪽아래 → 오른쪽위)
G0, G1, G2 = (13, 92, 120), (11, 163, 142), (59, 178, 115)
DEEP_NAVY = (13, 37, 64)

# 심볼 내용의 viewBox 경계 (획 두께·핀·노드 포함)
BOX = (42 - NODE_OUTER, 63 - 20, 238 + 27, 172 + NODE_OUTER)

SS = 4  # 수퍼샘플링. 4배로 그린 뒤 줄여야 가장자리가 깨끗하다.
HOLE = (0, 0, 0, 0)


def bezier(p0, p1, p2, p3, steps):
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        ))
    return out


def flatten(segments, steps):
    pts = []
    for seg in segments:
        pts.extend(bezier(*seg, steps))
    return pts


def diagonal_gradient(size, a, b, c, to_bottom_right):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x / size + (y / size if to_bottom_right else 1 - y / size)) / 2
            if t < 0.55:
                u, lo, hi = t / 0.55, a, b
            else:
                u, lo, hi = (t - 0.55) / 0.45, b, c
            px[x, y] = tuple(round(lo[i] + (hi[i] - lo[i]) * u) for i in range(3))
    return img


def render(size, margin, on_dark):
    """심볼을 size×size 캔버스 가운데에 그린다.

    on_dark=True  → 어두운 배경 위의 흰 심볼. 흰 중심은 구멍으로 뚫어 배경이 비친다.
    on_dark=False → SVG 원본색 그대로. 그라디언트 획 + 색 링 + 흰 중심.
    """
    S = size * SS
    x0, y0, x1, y1 = BOX
    w, h = x1 - x0, y1 - y0
    scale = size * margin / max(w, h) * SS
    ox = (S - w * scale) / 2 - x0 * scale
    oy = (S - h * scale) / 2 - y0 * scale

    def T(p):
        return (p[0] * scale + ox, p[1] * scale + oy)

    def disc(draw, center, radius, fill):
        cx, cy = T(center)
        r = radius * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    # 1) 획: 경로를 따라 원을 찍는다. 둥근 끝과 이음매가 자연히 생긴다.
    stroke_mask = Image.new("L", (S, S), 0)
    sd = ImageDraw.Draw(stroke_mask)
    r = STROKE_W / 2 * scale
    for p in flatten(ROUTE, 260):
        cx, cy = T(p)
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)

    layer = Image.new("RGBA", (S, S), HOLE)
    if on_dark:
        layer.paste((255, 255, 255, 255), mask=stroke_mask)
    else:
        grad = diagonal_gradient(S, G0, G1, G2, to_bottom_right=False).convert("RGBA")
        layer.paste(grad, mask=stroke_mask)

    draw = ImageDraw.Draw(layer)

    # 2) 노드: 링을 깔고 중심을 얹는다.
    for center, ring in NODES:
        disc(draw, center, NODE_OUTER, (255, 255, 255, 255) if on_dark else ring + (255,))
        disc(draw, center, NODE_INNER, HOLE if on_dark else (255, 255, 255, 255))

    # 3) 핀: 아래를 향하는 물방울 + 흰 점. SVG 순서상 맨 위에 온다.
    px, py = T(PIN_AT)
    poly = [(px + x * scale, py + y * scale) for x, y in flatten(PIN_PATH, 60)]
    draw.polygon(poly, fill=(255, 255, 255, 255) if on_dark else PIN_GREEN + (255,))
    disc(draw, (PIN_AT[0] + PIN_DOT_AT[0], PIN_AT[1] + PIN_DOT_AT[1]), PIN_DOT_R,
         HOLE if on_dark else (255, 255, 255, 255))

    return layer.resize((size, size), Image.LANCZOS)


def content_radius(img):
    a = img.split()[3]
    w, h = img.size
    cx, cy = w / 2, h / 2
    best = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if a.getpixel((x, y)) > 10:
                best = max(best, math.hypot(x - cx, y - cy))
    return best


os.makedirs(OUT, exist_ok=True)

# 1) 앱 아이콘 — 그라디언트 배경 + 흰 경로 (패키지 아이콘과 같은 구성)
icon = diagonal_gradient(1024, G0, G1, G2, to_bottom_right=True).convert("RGBA")
icon.alpha_composite(render(1024, 0.68, on_dark=True))
icon.convert("RGB").save(os.path.join(OUT, "icon.png"))

# 2) 안드로이드 adaptive foreground — 원형 마스크 안전영역(가운데 66%) 안에 넣는다.
fg = render(1024, 0.44, on_dark=True)
fg.save(os.path.join(OUT, "adaptive-icon.png"))

# 3) 스플래시 — 딥네이비 배경 위에 얹을 흰 심볼
render(1024, 0.74, on_dark=True).save(os.path.join(OUT, "splash-icon.png"))

# 4) 웹 파비콘
icon.convert("RGB").resize((48, 48), Image.LANCZOS).save(os.path.join(OUT, "favicon.png"))

# 5) 앱 화면 안에서 쓸 심볼 (SVG 원본색, 투명 배경)
render(512, 0.9, on_dark=False).save(os.path.join(OUT, "mroute-mark.png"))

print("adaptive foreground 내용 반경 %.0fpx / 안전 338px" % content_radius(fg))
for name in ("icon.png", "adaptive-icon.png", "splash-icon.png", "favicon.png", "mroute-mark.png"):
    p = os.path.join(OUT, name)
    print("  %-20s %s  %5.1f KB" % (name, Image.open(p).size, os.path.getsize(p) / 1024))
