import { Alert, Linking } from 'react-native';

// 카카오내비 딥링크에는 카카오 '네이티브 앱 키'가 필요하다.
// Kakao Developers > 내 애플리케이션 > 앱 키 > 네이티브 앱 키
//   로컬 개발 : frontend/.env 의 EXPO_PUBLIC_KAKAO_NATIVE_KEY
//   APK 빌드  : frontend/eas.json 의 preview/production env
// 키가 없으면 카카오맵 길찾기로 자동으로 떨어지므로 앱이 멈추지는 않는다.
const KAKAO_NATIVE_KEY = process.env.EXPO_PUBLIC_KAKAO_NATIVE_KEY || '';

/**
 * 목적지까지의 길안내 링크 후보를 순서대로 만든다.
 *
 * 1순위 카카오내비: 출발지를 현재 위치로 잡고 바로 안내를 시작한다.
 *   kakaonavi://navigate?name=&x=경도&y=위도&coord_type=wgs84&key=네이티브앱키
 *   key 가 없으면 "필수 파라미터가 존재하지 않습니다" 오류가 나므로,
 *   키가 없을 때는 아예 후보에서 뺀다.
 *
 * 2순위 카카오맵 길찾기: 키가 필요 없다. 카카오내비가 없는 폰의 대비책.
 * 3순위 웹: 앱이 하나도 없을 때.
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

  const targets = [];

  if (KAKAO_NATIVE_KEY) {
    const params = [
      `name=${encodeURIComponent(name)}`,
      `x=${lng}`,
      `y=${lat}`,
      'coord_type=wgs84',
      `key=${encodeURIComponent(KAKAO_NATIVE_KEY)}`,
      // 1 = 자동차. 지정하지 않으면 카카오내비가 되묻는다.
      'vehicle_type=1',
      // 100 = 추천 경로.
      'rpoption=100',
      'returnuri=',
    ].join('&');
    targets.push(`kakaonavi://navigate?${params}`);
  }

  targets.push(`kakaomap://route?ep=${lat},${lng}&by=CAR`);
  targets.push(
    `https://map.kakao.com/link/to/${encodeURIComponent(name)},${lat},${lng}`,
  );
  return targets;
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
    '카카오내비 또는 카카오맵 앱이 설치되어 있는지 확인해 주세요.',
  );
  return false;
}

/** 설정 화면 등에서 키가 들어갔는지 확인할 때 쓴다. */
export const hasKakaoNaviKey = Boolean(KAKAO_NATIVE_KEY);
