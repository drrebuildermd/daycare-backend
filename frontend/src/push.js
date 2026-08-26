import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

import { registerDriverDevice } from './api';

// expo-notifications 는 여기서 import 하지 않는다.
//
// 이유:
//  1) Expo Go(SDK 53+)는 안드로이드 원격 푸시를 아예 들어냈다. 이 모듈의 일부 API는
//     그 상황에서 console.error 를 호출하는데, 개발 모드의 Expo Go에서는 그것만으로도
//     레드박스가 떠서 앱 화면(지도 포함)이 통째로 가려진다.
//  2) 모듈 최상단에서 setNotificationHandler 를 부르면 네이티브 모듈이 없는 환경에서
//     import 시점에 터진다. App.js가 이 파일을 최상단에서 import 하므로 앱 전체가 죽는다.
//
// 그래서 실제로 푸시를 쓸 수 있는 환경에서만 require 한다.

export class PushSetupError extends Error {}

const REASONS = {
  web: '푸시 알림은 휴대폰 앱에서만 동작합니다. (웹 관제 화면에서는 배차 전송만 가능합니다)',
  simulator: '푸시 알림은 실제 기기에서만 동작합니다. (시뮬레이터 불가)',
  expoGo:
    'Expo Go에서는 안드로이드 푸시 알림을 쓸 수 없습니다. (SDK 53에서 제거됨)\n'
    + 'EAS로 빌드한 앱(APK)을 설치하면 정상 동작합니다.',
  noProjectId:
    'EAS projectId가 없습니다. 프로젝트 폴더에서 `npx eas init`을 실행한 뒤 다시 빌드해 주세요.',
  moduleMissing: '알림 모듈을 불러오지 못했습니다. 앱을 다시 설치해 주세요.',
};

const isExpoGo = () =>
  Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

const getProjectId = () =>
  Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? null;

/**
 * 이 환경에서 푸시를 쓸 수 있는지 판단한다. 절대 예외를 던지지 않는다.
 * @returns {{supported: boolean, reason: string|null, message: string|null}}
 */
export function getPushEnvironment() {
  const deny = (reason) => ({ supported: false, reason, message: REASONS[reason] });

  try {
    if (Platform.OS === 'web') return deny('web');
    if (!Device.isDevice) return deny('simulator');
    if (isExpoGo()) return deny('expoGo');
    if (!getProjectId()) return deny('noProjectId');
    return { supported: true, reason: null, message: null };
  } catch (_) {
    // 환경 판단 자체가 실패하면 '지원 안 함'으로 본다. 여기서 앱을 죽이지 않는다.
    return deny('moduleMissing');
  }
}

let notificationsModule = null;
let handlerInstalled = false;

/** expo-notifications 를 지연 로드한다. 실패하면 null 을 돌려주고 예외는 삼킨다. */
function loadNotifications() {
  if (notificationsModule) return notificationsModule;
  try {
    // eslint-disable-next-line global-require
    const notifications = require('expo-notifications');

    if (!handlerInstalled) {
      // 앱이 떠 있는 동안에도 알림 배너를 띄운다.
      // import 시점이 아니라 여기서 부르는 게 핵심이다.
      notifications.setNotificationHandler({
        handleNotification: async () => ({
          shouldShowBanner: true,
          shouldShowList: true,
          shouldPlaySound: true,
          shouldSetBadge: false,
        }),
      });
      handlerInstalled = true;
    }

    notificationsModule = notifications;
    return notifications;
  } catch (error) {
    console.warn('[push] expo-notifications 로드 실패:', error?.message);
    return null;
  }
}

/**
 * 이 폰을 해당 기사님의 알림 수신 기기로 등록한다.
 * 쓸 수 없는 환경이면 PushSetupError 를 던진다. (호출부가 알럿으로 안내)
 */
export async function enablePushForDriver(driverName) {
  const environment = getPushEnvironment();
  if (!environment.supported) throw new PushSetupError(environment.message);

  const Notifications = loadNotifications();
  if (!Notifications) throw new PushSetupError(REASONS.moduleMissing);

  try {
    if (Platform.OS === 'android') {
      // 안드로이드는 채널이 없으면 알림이 조용히 무시된다.
      await Notifications.setNotificationChannelAsync('dispatch', {
        name: '배차 알림',
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#0F766E',
      });
    }

    const existing = await Notifications.getPermissionsAsync();
    let status = existing.status;
    if (status !== 'granted') {
      ({ status } = await Notifications.requestPermissionsAsync());
    }
    if (status !== 'granted') {
      throw new PushSetupError(
        '알림 권한이 거부되었습니다. 설정 > 앱 > 송영 최적화 > 알림에서 켜 주세요.',
      );
    }

    const { data: token } = await Notifications.getExpoPushTokenAsync({
      projectId: getProjectId(),
    });

    await registerDriverDevice({
      driver_name: driverName,
      expo_push_token: token,
      device_label: Device.deviceName || Device.modelName || null,
    });

    return token;
  } catch (error) {
    // 권한 거부/서버 오류 등 우리가 만든 메시지는 그대로 올린다.
    if (error instanceof PushSetupError) throw error;
    throw new PushSetupError(
      `알림 등록 중 문제가 발생했습니다: ${error?.message || '알 수 없는 오류'}`,
    );
  }
}

/**
 * 배차 알림을 눌러 앱이 열렸을 때 onOpenRoute(vehicleId) 를 호출한다.
 *
 * App.js가 useEffect에서 바로 부르므로, 어떤 환경에서도 예외를 던지지 않고
 * 항상 정리 함수를 돌려줘야 한다. 여기서 터지면 앱 전체가 하얗게 죽는다.
 */
export function listenForDispatchTaps(onOpenRoute) {
  const noop = () => {};

  const environment = getPushEnvironment();
  if (!environment.supported) return noop;

  const Notifications = loadNotifications();
  if (!Notifications) return noop;

  try {
    const handle = (response) => {
      try {
        const data = response?.notification?.request?.content?.data;
        if (data?.screen === 'route' && data?.vehicle_id) {
          onOpenRoute(data.vehicle_id);
        }
      } catch (error) {
        console.warn('[push] 알림 처리 실패:', error?.message);
      }
    };

    // 앱이 완전히 꺼진 상태에서 알림으로 실행된 경우도 처리한다.
    Notifications.getLastNotificationResponseAsync()
      .then((response) => { if (response) handle(response); })
      .catch((error) => console.warn('[push] 최근 알림 확인 실패:', error?.message));

    const subscription = Notifications.addNotificationResponseReceivedListener(handle);
    return () => {
      try {
        subscription.remove();
      } catch (_) {
        // 이미 정리된 경우는 무시한다.
      }
    };
  } catch (error) {
    console.warn('[push] 알림 리스너 등록 실패:', error?.message);
    return noop;
  }
}
