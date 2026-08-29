/**
 * 마중ON Care 디자인 토큰.
 *
 * 값은 브랜딩 패키지의 04_specs/theme_tokens.json 을 그대로 옮긴 것이다.
 * 색을 새로 만들지 말고 여기서 가져다 쓴다.
 */

export const brand = {
  masterName: '마중ON',
  productName: '마중ON Care',
  // OS 홈화면에는 짧게. 앱 안에서는 제품명 전체를 쓴다.
  osDisplayName: '마중ON',
  tagline: '복잡한 송영, 가장 효율적으로.',
  descriptor: '배차 · 경로 · 차량 운영 자동 최적화',
};

export const color = {
  deepNavy: '#0D2540',
  teal: '#0BA38E',
  mint: '#6ED6C1',
  green: '#3BB273',
  softGray: '#F2F4F7',
  white: '#FFFFFF',
  textPrimary: '#0D2540',
  textSecondary: '#667085',
  border: '#E4E7EC',
  warning: '#F2B84B',
  danger: '#D64545',
};

/**
 * 상태를 색으로 말하는 규칙. (UI_IMPLEMENTATION_SPEC 의 '상태 시각 언어')
 *
 * 배경과 글자를 짝으로 둔다. 배지를 만들 때마다 색을 고르면 화면마다 달라진다.
 */
export const tone = {
  // 주 동작. 누르면 일이 벌어지는 버튼.
  primary: { bg: color.deepNavy, fg: color.white },
  // 최적화·경로·내비게이션처럼 '지금 움직이는 것'.
  active: { bg: color.teal, fg: color.white },
  success: { bg: '#E9F7EF', fg: '#237B4B', solid: color.green },
  info: { bg: '#E6F7F4', fg: '#07705F', solid: color.teal },
  neutral: { bg: color.softGray, fg: color.textSecondary },
  warning: { bg: '#FEF6E7', fg: '#8A6100', solid: color.warning },
  danger: { bg: '#FCEDED', fg: '#9B2C2C', solid: color.danger },
};

export const radius = { small: 8, medium: 12, large: 16, pill: 999 };

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

/**
 * 글자 크기와 굵기.
 *
 * fontFamily 는 여기 적지 않는다. src/ui/Text.js 가 fontWeight 를 보고 정한다.
 * 안드로이드는 굵기별로 패밀리가 따로라 한곳에서 처리해야 어긋나지 않는다.
 */
export const type = {
  display: { fontSize: 24, fontWeight: '700', color: color.textPrimary },
  title: { fontSize: 18, fontWeight: '700', color: color.textPrimary },
  section: { fontSize: 16, fontWeight: '600', color: color.textPrimary },
  body: { fontSize: 14, fontWeight: '400', color: color.textPrimary },
  bodyStrong: { fontSize: 14, fontWeight: '600', color: color.textPrimary },
  caption: { fontSize: 12, fontWeight: '400', color: color.textSecondary },
  captionStrong: { fontSize: 12, fontWeight: '600', color: color.textSecondary },
};

/** 카드 한 장의 기본 생김새. 화면마다 테두리 색이 달라지지 않게 한다. */
export const surface = {
  card: {
    backgroundColor: color.white,
    borderRadius: radius.large,
    borderWidth: 1,
    borderColor: color.border,
  },
  screen: { backgroundColor: color.softGray },
};

export default { brand, color, tone, radius, space, type, surface };
