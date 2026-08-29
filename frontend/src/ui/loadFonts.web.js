import { useFonts } from 'expo-font';

/**
 * 웹 관제 화면용 폰트 준비.
 *
 * app.json 의 expo-font 플러그인은 네이티브 빌드에만 적용된다. 웹에서는
 * 브라우저가 직접 내려받아야 하므로 여기서 부른다.
 *
 * 이 파일이 .web.js 인 덕분에 앱 번들에는 아래 require 가 들어가지 않는다.
 * 같이 들어가면 TTF 가 네이티브 리소스와 번들에 두 벌 실려 10MB 가 더 붙는다.
 */
export default function useAppFonts() {
  const [loaded] = useFonts({
    'Pretendard-Regular': require('../../assets/fonts/Pretendard-Regular.ttf'),
    'Pretendard-Medium': require('../../assets/fonts/Pretendard-Medium.ttf'),
    'Pretendard-SemiBold': require('../../assets/fonts/Pretendard-SemiBold.ttf'),
    'Pretendard-Bold': require('../../assets/fonts/Pretendard-Bold.ttf'),
  });
  return loaded;
}
