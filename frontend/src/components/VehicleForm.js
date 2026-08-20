import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput style={styles.input} placeholderTextColor="#94A3B8" {...props} />
  </View>
);

export default function VehicleForm({ value, index, onChange, onRemove }) {
  const set = (field, nextValue) => onChange({ ...value, [field]: nextValue });

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.numberBadge}><Text style={styles.number}>{index + 1}</Text></View>
        <Text style={styles.title}>
          {value.vehicleType || `차량 ${index + 1}`}
          {!!value.driverName && <Text style={styles.driverTag}> · {value.driverName} 선생님</Text>}
        </Text>
        <Pressable onPress={onRemove} hitSlop={10}><Text style={styles.remove}>삭제</Text></Pressable>
      </View>
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
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: '#E2E8F0' },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  numberBadge: { width: 28, height: 28, borderRadius: 9, backgroundColor: '#DCFCE7', alignItems: 'center', justifyContent: 'center', marginRight: 9 },
  number: { color: '#15803D', fontWeight: '900' },
  title: { flex: 1, color: '#0F172A', fontSize: 16, fontWeight: '900' },
  remove: { color: '#DC2626', fontWeight: '700', fontSize: 13 },
  driverTag: { color: '#0F766E', fontSize: 13, fontWeight: '700' },
  field: { marginBottom: 12 },
  label: { color: '#475569', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0F172A' },
});
