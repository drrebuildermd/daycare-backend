import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import Accordion from './Accordion';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput style={styles.input} placeholderTextColor="#94A3B8" {...props} />
  </View>
);

export default function VehicleForm({ value, index, onChange, onRemove }) {
  const set = (field, nextValue) => onChange({ ...value, [field]: nextValue });

  const plate = (value.plateNumber || '').trim();
  const driver = (value.driverName || '').trim();
  // 접혔을 때 보이는 한 줄. 여기만 봐도 무엇이 저장돼 있는지 알 수 있어야 한다.
  const summary = [
    plate || '차량번호 미입력',
    driver ? `(담당: ${driver})` : '(담당 미지정)',
  ].join(' ');

  return (
    <Accordion
      index={index}
      title={`[${(value.vehicleType || '').trim() || '차종 미입력'}]`}
      summary={summary}
      badge={value.capacity ? `${value.capacity}인승` : null}
      onRemove={onRemove}
    >
      <Field
        label="차종"
        value={value.vehicleType}
        onChangeText={(text) => set('vehicleType', text)}
        placeholder="예: 스타리아, 레이, 카니발"
      />
      <Field
        label="차량번호"
        value={value.plateNumber}
        onChangeText={(text) => set('plateNumber', text)}
        placeholder="예: 12가 3456"
      />
      <Field
        label="담당 기사 이름"
        value={value.driverName}
        onChangeText={(text) => set('driverName', text)}
        placeholder="예: 명민승"
        maxLength={30}
      />
      <Field
        label="최대 탑승 인원"
        value={value.capacity}
        onChangeText={(text) => set('capacity', text.replace(/[^0-9]/g, ''))}
        placeholder="예: 7"
        keyboardType="number-pad"
        maxLength={3}
      />
    </Accordion>
  );
}

const styles = StyleSheet.create({
  driverTag: { color: '#0F766E', fontSize: 13, fontWeight: '700' },
  field: { marginBottom: 12 },
  label: { color: '#475569', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0F172A' },
});
