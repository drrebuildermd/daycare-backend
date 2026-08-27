import { Alert, Linking } from 'react-native';

/**
 * 목적지까지 길안내를 시작한다.
 *
 * 예전에는 백엔드가 만든 kakaonavi://navigate?params={JSON} 을 그대로 열었는데
 * 두 가지 문제가 있었다.
 *
 *   1) 그 형식은 카카오내비 SDK 가 쓰는 것으로, 딥링크로 직접 부르면
 *      네이티브 앱 키가 필요하다. 키가 없어 "필수 파라미터가 존재하지 않습니다"
 *      오류가 떴다.
 *   2) app.json 의 intentFilters 에 kakaonavi 스킴이 등록돼 있어서 우리 앱도
 *      그 링크의 수신자로 잡혔고, 안드로이드가 앱 선택 팝업을 띄웠다.
 *
 * 그래서 키가 필요 없는 카카오맵 길찾기 스킴을 쓴다.
 *   kakaomap://route?ep={위도},{경도}&by=CAR
 * 출발지(sp)를 비우면 현재 위치에서 자동차 길안내가 바로 시작된다.
 *
 * 앱이 없으면 웹 링크로 떨어진다. 브라우저에서 열리므로 항상 무언가는 뜬다.
 */
export function buildNavigationTargets(stop) {
  const lat = Number(stop?.latitude);
  const lng = Number(stop?.longitude);
  const name = (stop?.name || '목적지').trim();

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    // 좌표가 없으면 주소로 검색이라도 걸어준다.
    const query = encodeURIComponent(stop?.address || name);
    return [`https://map.kakao.com/?q=${query}`];
  }

  return [
    // 1순위: 설치돼 있으면 카카오맵이 바로 자동차 길안내를 시작한다.
    `kakaomap://route?ep=${lat},${lng}&by=CAR`,
    // 2순위: 앱이 없을 때. 카카오맵 웹이 열리고 앱 설치/실행을 안내한다.
    `https://map.kakao.com/link/to/${encodeURIComponent(name)},${lat},${lng}`,
  ];
}

/**
 * 후보 링크를 순서대로 시도한다.
 *
 * canOpenURL 은 안드로이드 11 이상에서 <queries> 선언이 없으면 설치돼 있어도
 * false 를 돌려준다. 그래서 쓰지 않고, openURL 을 직접 시도해 실패하면 다음으로
 * 넘어간다. (openURL 은 암시적 인텐트라 <queries> 없이도 동작한다)
 */
export async function startNavigation(stop) {
  const targets = buildNavigationTargets(stop);

  for (const url of targets) {
    try {
      await Linking.openURL(url);
      return true;
    } catch (_) {
      // 이 스킴을 처리할 앱이 없다. 다음 후보로.
    }
  }

  Alert.alert(
    '길안내를 시작하지 못했습니다',
    '카카오맵 앱이 설치되어 있는지 확인해 주세요.',
  );
  return false;
}
