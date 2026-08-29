import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import React from 'react';

import { color } from '../theme';

/**
 * 앱 전체가 쓰는 아이콘.
 *
 * 세트를 하나(MaterialCommunityIcons)로 묶는다. 세트를 섞으면 굵기와 모서리가
 * 달라 화면마다 다른 앱처럼 보이고, 세트마다 폰트가 따로 실려 용량도 는다.
 *
 * 이모지를 대신하는 것이므로 이름은 '무엇을 뜻하는지'로 짓는다.
 * 아이콘 이름이 바뀌어도 화면 코드는 그대로 두기 위해서다.
 */
const NAME = {
  // 운행
  navigate: 'navigation-variant',
  phone: 'phone',
  vehicle: 'van-passenger',
  boarded: 'account-check',
  route: 'map-marker-path',
  map: 'map-outline',

  // 등원은 센터로 모셔오는 것, 하원은 댁으로 모셔다드리는 것.
  inbound: 'login-variant',
  outbound: 'logout-variant',

  // 출발지
  center: 'office-building',
  home: 'home-outline',

  // 상태
  done: 'check-circle',
  waiting: 'clock-outline',
  warning: 'alert-circle-outline',
  locked: 'lock-outline',
  refresh: 'refresh',

  // 알림
  bellOn: 'bell-ring-outline',
  bellOff: 'bell-off-outline',

  // 관리
  admin: 'view-dashboard-outline',
  passenger: 'account-group-outline',
  wheelchair: 'wheelchair-accessibility',
  send: 'send',
  report: 'file-document-outline',
  excel: 'table-arrow-down',
  add: 'plus',
  search: 'map-marker-radius-outline',
  chevronDown: 'chevron-down',
  chevronRight: 'chevron-right',
  chevronUp: 'chevron-up',
  back: 'arrow-left',
};

export default function Icon({ name, size = 18, tint = color.textSecondary, style }) {
  return (
    <MaterialCommunityIcons
      name={NAME[name] || name}
      size={size}
      color={tint}
      style={style}
    />
  );
}

export { NAME };
