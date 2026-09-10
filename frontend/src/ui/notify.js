import { Alert, Platform } from 'react-native';

/**
 * 사람에게 알린다.
 *
 * react-native-web 의 Alert.alert 는 본문이 빈 함수다. 웹에서 부르면
 * 아무 일도 일어나지 않는다. 그래서 엑셀 업로드가 실패해도 화면에는
 * 아무것도 뜨지 않고 조용히 끝났다.
 *
 * 웹에서는 브라우저 기본 창을 쓴다. 예쁘지는 않지만 반드시 보인다.
 * 보이지 않는 예쁜 알림보다 보이는 못난 알림이 낫다.
 */
export default function notify(title, message) {
  if (Platform.OS === 'web') {
    const text = message ? `${title}\n\n${message}` : title;
    if (typeof window !== 'undefined' && window.alert) window.alert(text);
    return;
  }
  Alert.alert(title, message);
}
