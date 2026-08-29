import React from 'react';
import { StyleSheet, TextInput as RNTextInput } from 'react-native';

import { familyFor } from './Text';

/**
 * Pretendard 를 입힌 입력칸.
 *
 * Text 래퍼는 <Text> 만 감싼다. 입력칸에 사람이 쳐 넣은 글자는 그대로 시스템
 * 글꼴로 남아, 어르신 성함이나 차량번호만 다른 폰트로 보인다.
 */
export default function TextInput({ style, ...props }) {
  const { fontWeight, ...rest } = StyleSheet.flatten(style) || {};
  return <RNTextInput {...props} style={[rest, { fontFamily: familyFor(fontWeight) }]} />;
}
