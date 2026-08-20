import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { registerDriverDevice } from './api';

// 앱이 떠 있는 동안에도 알림 배너를 띄운다.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export class PushSetupError extends Error {}

const getProjectId = () => {
  // SDK 49+ 는 푸시 토큰 발급에 EAS projectId 를 요구한다.
  // `npx eas init` 을 돌리면 app.json 의 extra.eas.projectId 에 들어간다.
  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId
    ?? Constants.easConfig?.projectId;
  if (!projectId) {
    throw new PushSetupError(
      'EAS projectId가 없습니다. 프로젝트 폴더에서 `npx eas init`을 한 번 실행한 뒤 앱을 다시 빌드해 주세요.',
    );
  }
  return projectId;
};

/**
 * 이 폰을 해당 기사님의 알림 수신 기기로 등록한다.
 * 성공하면 Expo 푸시 토큰을 돌려준다.
 */
export async function enablePushForDriver(driverName) {
  if (!Device.isDevice) {
    throw new PushSetupError('푸시 알림은 실제 기기에서만 동작합니다. (시뮬레이터/웹 불가)');
  }

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
}

/**
 * 알림을 눌러서 앱이 열렸을 때 호출된다.
 * onOpenRoute(vehicleId) 로 해당 차량 지도를 연다.
 *
 * 앱이 완전히 꺼진 상태에서 알림으로 실행된 경우도 처리해야 해서,
 * 마지막 응답(getLastNotificationResponseAsync)까지 확인한다.
 */
export function listenForDispatchTaps(onOpenRoute) {
  const handle = (response) => {
    const data = response?.notification?.request?.content?.data;
    if (data?.screen === 'route' && data?.vehicle_id) {
      onOpenRoute(data.vehicle_id);
    }
  };

  Notifications.getLastNotificationResponseAsync().then((response) => {
    if (response) handle(response);
  });

  const subscription = Notifications.addNotificationResponseReceivedListener(handle);
  return () => subscription.remove();
}
