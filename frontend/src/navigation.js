import { Alert, Linking } from 'react-native';

// 길안내는 카카오맵 길찾기 스킴만 쓴다.
//
// 카카오내비 딥링크는 네이티브 앱 키 인증을 요구하는데, 키 해시를 정확히
// 등록해도 EAS 서명 환경에서 실패하는 경우가 있어 변수가 너무 많았다.
// 카카오맵 길찾기는 키가 전혀 필요 없다.
//
// 카카오맵의 유일한 약점은 출발지를 GPS 로 잡지 못해 빈칸으로 두는 것이었다.
// 그런데 우리는 배차 결과에 모든 좌표를 이미 갖고 있다. 그래서 sp(출발지)를
// 직접 넣어준다. GPS 에 기대지 않으므로 실내·지하에서도 경로가 바로 잡힌다.
//
//   kakaomap://route?sp={출발위도},{출발경도}&ep={도착위도},{도착경도}&by=CAR

const isFiniteCoord = (value) => Number.isFinite(Number(value));

// 정류장/차량은 latitude·longitude 로, 이 파일이 만든 좌표는 lat·lng 로 들고 다닌다.
// 둘 다 받아준다. (originForStop 의 결과를 다시 asPoint 에 넣는 경로가 있다)
const asPoint = (candidate) => {
  if (!candidate) return null;
  const lat = Number(candidate.latitude ?? candidate.lat);
  const lng = Number(candidate.longitude ?? candidate.lng);
  if (!isFiniteCoord(lat) || !isFiniteCoord(lng)) return null;
  return { lat, lng };
};

/**
 * 이 정류장으로 갈 때의 출발지를 정한다.
 *
 * 기사님은 순서대로 도니까, 두 번째 어르신부터는 바로 앞 어르신 댁에 있다.
 * 첫 번째는 그 회차의 출발점이다.
 *   1회차 - 차량 출발지 (자차 송영이면 기사님 자택, 아니면 센터)
 *   2회차 - 센터 (1회차를 마치고 센터로 복귀한 상태)
 */
export function originForStop({ vehicle, trip, stopIndex, center }) {
  if (stopIndex > 0) {
    const previous = trip?.stops?.[stopIndex - 1];
    const point = asPoint(previous);
    if (point) return point;
  }

  if (trip?.round === 1) {
    const start = asPoint({
      latitude: vehicle?.start_latitude,
      longitude: vehicle?.start_longitude,
    });
    if (start) return start;
  }

  return asPoint(center);
}

/**
 * 길안내 링크 후보를 순서대로 만든다.
 * origin 이 있으면 출발지를 강제로 지정하고, 없으면 카카오맵이 알아서 잡게 둔다.
 */
export function buildNavigationTargets(stop, origin) {
  const destination = asPoint(stop);
  const name = (stop?.name || '목적지').trim();

  if (!destination) {
    // 좌표가 없으면 주소로 검색이라도 걸어준다.
    const query = encodeURIComponent(stop?.address || name);
    return [`https://map.kakao.com/?q=${query}`];
  }

  const start = asPoint(origin);
  const ep = `${destination.lat},${destination.lng}`;
  const route = start
    ? `kakaomap://route?sp=${start.lat},${start.lng}&ep=${ep}&by=CAR`
    : `kakaomap://route?ep=${ep}&by=CAR`;

  return [
    route,
    // 앱이 없을 때. 카카오맵 웹이 열리고 앱 설치/실행을 안내한다.
    `https://map.kakao.com/link/to/${encodeURIComponent(name)},${ep}`,
  ];
}

/**
 * 후보 링크를 순서대로 시도한다.
 *
 * canOpenURL 은 안드로이드 11 이상에서 <queries> 선언이 없으면 설치돼 있어도
 * false 를 돌려준다. 그래서 쓰지 않고, openURL 을 직접 시도해 실패하면 다음으로
 * 넘어간다. (openURL 은 암시적 인텐트라 <queries> 없이도 동작한다)
 */
export async function startNavigation(stop, origin) {
  const targets = buildNavigationTargets(stop, origin);

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
