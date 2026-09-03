import React from 'react';

import TextInput from './TextInput';

/**
 * 시각 입력칸. 숫자만 치면 콜론이 저절로 붙는다.
 *
 * 폰에서 08:30 을 넣으려고 콜론을 찾아 키보드를 바꾸는 것은 최악이다.
 * 0·8·3·0 만 누르면 08:30 이 된다.
 *
 * 두 자리까지는 콜론을 붙이지 않는다. 붙여 두면 지우려 할 때 콜론이 계속
 * 되살아나 뒤로 지우기가 막힌다.
 *   1 -> "1"      17 -> "17"      170 -> "17:0"     1700 -> "17:00"
 */
export function maskTime(text) {
  const digits = String(text ?? '').replace(/[^0-9]/g, '').slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}:${digits.slice(2)}`;
}

export default function TimeInput({ value, onChangeTime, ...props }) {
  return (
    <TextInput
      {...props}
      value={value}
      onChangeText={(text) => onChangeTime(maskTime(text))}
      // 숫자만 받으면 되므로 폰에서 숫자 자판이 바로 뜬다.
      keyboardType="number-pad"
      // 콜론까지 5글자. 마스크가 넘치는 입력을 이미 자르지만,
      // 자판 쪽에서도 막아 두면 커서가 튀지 않는다.
      maxLength={5}
    />
  );
}
