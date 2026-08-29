import React from 'react';
import { StyleSheet, Text as RNText } from 'react-native';

/**
 * Pretendard 를 입힌 Text.
 *
 * 안드로이드는 굵기별로 폰트 패밀리가 따로다. fontWeight: '700' 만 줘서는
 * 굵어지지 않고 Regular 그대로 나온다. 그래서 넘어온 스타일의 fontWeight 를
 * 읽어 알맞은 패밀리로 바꿔준다.
 *
 * 화면 코드는 지금처럼 fontWeight 만 쓰면 된다. 폰트 이름을 아는 곳은 여기뿐이다.
 *
 * React 19 에서 Text.defaultProps 가 사라져 전역으로 폰트를 씌우는 예전 방법은
 * 쓸 수 없다. 그래서 각 화면이 이 컴포넌트를 import 한다.
 */

const FAMILY = {
  400: 'Pretendard-Regular',
  500: 'Pretendard-Medium',
  600: 'Pretendard-SemiBold',
  700: 'Pretendard-Bold',
};

// 넣은 굵기는 4종뿐이다. 800/900 을 쓰는 화면이 많아 가장 굵은 것으로 모은다.
function familyFor(weight) {
  const n = Number(weight);
  if (weight === 'bold' || !Number.isFinite(n)) return FAMILY[weight === 'bold' ? 700 : 400];
  if (n >= 700) return FAMILY[700];
  if (n >= 600) return FAMILY[600];
  if (n >= 500) return FAMILY[500];
  return FAMILY[400];
}

export default function Text({ style, ...props }) {
  // 스타일을 한 덩어리로 편 뒤 fontWeight 를 아예 뺀다.
  // 배열 뒤에 fontWeight: undefined 를 얹는 방법으로는 앞의 값이 지워지지 않는다.
  // 굵기를 패밀리로 표현하는데 fontWeight 가 남아 있으면 안드로이드가 그 위에
  // 가짜 볼드를 한 번 더 씌워 글자가 뭉개진다.
  const { fontWeight, ...rest } = StyleSheet.flatten(style) || {};
  return <RNText {...props} style={[rest, { fontFamily: familyFor(fontWeight) }]} />;
}

export { familyFor };
