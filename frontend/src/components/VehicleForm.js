import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import Accordion from './Accordion';
import AddressSearch from './AddressSearch';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput style={styles.input} placeholderTextColor="#94A3B8" {...props} />
  </View>
);

export default function VehicleForm({ value, index, onChange, onRemove }) {
  const set = (field, nextValue) => onChange({ ...value, [field]: nextValue });
  const [isAddressOpen, setIsAddressOpen] = useState(false);

  const plate = (value.plateNumber || '').trim();
  const driver = (value.driverName || '').trim();
  const hasDriverPhone = (value.driverPhone || '').replace(/[^0-9]/g, '').length >= 10;
  // 기존 차량 데이터에는 이 값이 없으므로 센터 출발을 기본으로 본다.
  const isCustomStart = value.startType === 'custom';
  const startAddress = (value.startAddress || '').trim();

  // 접혔을 때 보이는 한 줄. 여기만 봐도 무엇이 저장돼 있는지 알 수 있어야 한다.
  const summary = [
    plate || '차량번호 미입력',
    driver ? `(담당: ${driver})` : '(담당 미지정)',
    value.capacity ? `· ${value.capacity}인승` : '',
  ].filter(Boolean).join(' ');

  return (
    <Accordion
      index={index}
      title={`[${(value.vehicleType || '').trim() || '차종 미입력'}]`}
      summary={summary}
      badges={[
        isCustomStart
          ? { label: '🏠 자차 송영', tone: 'warning' }
          : { label: '🏫 센터 차량', tone: 'success' },
        ...(hasDriverPhone ? [] : [{ label: '📵 번호 없음', tone: 'warning' }]),
      ]}
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
        label="기사님 연락처"
        value={value.driverPhone}
        onChangeText={(text) => set('driverPhone', text)}
        placeholder="010-1234-5678"
        keyboardType="phone-pad"
      />
      <Text style={styles.startHint}>
        배차를 계산하면 이 번호로 "배차표가 확정되었습니다" 문자가 갑니다.{'\n'}
        비워두면 문자를 보내지 않습니다.
      </Text>

      <Field
        label="최대 탑승 인원"
        value={value.capacity}
        onChangeText={(text) => set('capacity', text.replace(/[^0-9]/g, ''))}
        placeholder="예: 7"
        keyboardType="number-pad"
        maxLength={3}
      />

      {/* --- 자차 송영 --- */}
      <Text style={styles.label}>1회차 출발지</Text>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggle, !isCustomStart && styles.toggleOn]}
          onPress={() => set('startType', 'center')}
        >
          <Text style={[styles.toggleText, !isCustomStart && styles.toggleTextOn]}>
            🏫 센터에서 출발
          </Text>
        </Pressable>
        <Pressable
          style={[styles.toggle, isCustomStart && styles.toggleOn]}
          onPress={() => set('startType', 'custom')}
        >
          <Text style={[styles.toggleText, isCustomStart && styles.toggleTextOn]}>
            🏠 다른 주소지 (자차)
          </Text>
        </Pressable>
      </View>

      {isCustomStart ? (
        <View style={styles.startBox}>
          <Pressable style={styles.searchButton} onPress={() => setIsAddressOpen(true)}>
            <Text style={styles.searchButtonText}>
              📍 {startAddress ? '출발지 다시 검색하기' : '출발지 주소 찾기'}
            </Text>
          </Pressable>

          {startAddress ? (
            <Text style={styles.startAddress}>{startAddress}</Text>
          ) : (
            <Text style={styles.startWarning}>
              ⚠️ 주소를 넣지 않으면 배차 계산이 거절됩니다.
            </Text>
          )}

          <Text style={styles.startHint}>
            기사님이 이 주소에서 출발해 어르신을 태우고 센터로 복귀합니다.{'\n'}
            2회차는 센터에서 출발합니다.
          </Text>
        </View>
      ) : (
        <Text style={styles.startHint}>센터에서 출발해 센터로 복귀합니다.</Text>
      )}

      <AddressSearch
        visible={isAddressOpen}
        onSelected={(address) => {
          // 좌표는 배차할 때 백엔드가 카카오로 변환한다.
          // 주소가 바뀌면 예전 좌표는 버려야 엉뚱한 곳에서 출발하지 않는다.
          onChange({
            ...value,
            startType: 'custom',
            startAddress: address,
            startLatitude: '',
            startLongitude: '',
          });
          setIsAddressOpen(false);
        }}
        onClose={() => setIsAddressOpen(false)}
      />
    </Accordion>
  );
}

const styles = StyleSheet.create({
  field: { marginBottom: 12 },
  label: { color: '#475569', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0F172A' },
  toggleRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  toggle: { flex: 1, borderRadius: 12, borderWidth: 1.5, borderColor: '#CBD5E1', backgroundColor: '#F8FAFC', paddingVertical: 11, alignItems: 'center' },
  toggleOn: { borderColor: '#0F766E', backgroundColor: '#ECFDF5' },
  toggleText: { color: '#64748B', fontSize: 12.5, fontWeight: '800' },
  toggleTextOn: { color: '#0F766E' },
  startBox: { backgroundColor: '#FFFBEB', borderWidth: 1, borderColor: '#FCD34D', borderRadius: 12, padding: 12, gap: 8 },
  searchButton: { backgroundColor: '#0F766E', borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  searchButtonText: { color: '#FFFFFF', fontWeight: '800', fontSize: 13 },
  startAddress: { color: '#0F172A', fontSize: 14, fontWeight: '700', backgroundColor: '#FFFFFF', borderRadius: 8, padding: 10 },
  startWarning: { color: '#B45309', fontSize: 12.5, fontWeight: '700' },
  startHint: { color: '#64748B', fontSize: 12, lineHeight: 18 },
});
