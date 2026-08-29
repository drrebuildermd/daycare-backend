/**
 * 네이티브(안드로이드/iOS)용 폰트 준비.
 *
 * 앱에서는 Pretendard 를 app.json 의 expo-font 플러그인이 네이티브 리소스로
 * 직접 심는다. 그래서 앱이 켜진 뒤 따로 등록할 것이 없고, 기다릴 것도 없다.
 *
 * 예전에는 useFonts 로 실행 중에 등록했는데, 삼성 실기기에서 일부 화면만
 * 시스템 글꼴로 나오는 일이 있었다. 브라우저에서는 재현되지 않아 원인을 좁히지
 * 못했고, 등록 시점이라는 변수를 아예 없애는 쪽을 골랐다.
 *
 * 웹에는 이 플러그인이 적용되지 않으므로 loadFonts.web.js 가 따로 불러온다.
 */
export default function useAppFonts() {
  return true;
}
