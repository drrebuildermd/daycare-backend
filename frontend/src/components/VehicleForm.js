import React, { useState } from 'react';
import TextInput from '../ui/TextInput';
import TimeInput from '../ui/TimeInput';
import Text from '../ui/Text';
import Icon from '../ui/Icon';
import { color } from '../theme';
import { Pressable, StyleSheet, View } from 'react-native';

import Accordion from './Accordion';
import AddressSearch from './AddressSearch';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput style={styles.input} placeholderTextColor="#98A2B3" {...props} />
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
  // 기존 차량 데이터에는 이 값이 없다. 없으면 리프트 없음으로 본다.
  const wheelchairSeats = Number(value.wheelchairCapacity) || 0;

  // 접혔을 때 보이는 한 줄. 여기만 봐도 무엇이 저장돼 있는지 알 수 있어야 한다.
  const summary = [
    plate || '차량번호 미입력',
    driver ? `(담당: ${driver})` : '(담당 미지정)',
    value.capacity ? `· ${value.capacity}인승` : '',
    wheelchairSeats > 0 ? `· 휠체어 ${wheelchairSeats}석` : '',
    (value.outboundDeadline || '').trim() ? `· 마감 ${value.outboundDeadline}` : '',
  ].filter(Boolean).join(' ');

  return (
    <Accordion
      index={index}
      title={`[${(value.vehicleType || '').trim() || '차종 미입력'}]`}
      summary={summary}
      badges={[
        isCustomStart
          ? { label: '자차 송영', icon: 'home', tone: 'warning' }
          : { label: '센터 차량', icon: 'center', tone: 'success' },
        ...(wheelchairSeats > 0
          ? [{ label: `휠체어 ${wheelchairSeats}석`, icon: 'wheelchair', tone: 'success' }]
          : []),
        ...(hasDriverPhone ? [] : [{ label: '연락처 없음', icon: 'warning', tone: 'warning' }]),
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
        label="총 탑승 정원"
        value={value.capacity}
        onChangeText={(text) => set('capacity', text.replace(/[^0-9]/g, ''))}
        placeholder="예: 7"
        keyboardType="number-pad"
        maxLength={3}
      />

      <Field
        label="휠체어 전용 좌석 수"
        value={value.wheelchairCapacity}
        onChangeText={(text) =>
          set('wheelchairCapacity', text.replace(/[^0-9]/g, ''))
        }
        placeholder="예: 1 (리프트가 없으면 0)"
        keyboardType="number-pad"
        maxLength={3}
      />
      <Text style={styles.startHint}>
        휠체어를 탄 채로 고정할 수 있는 자리 수입니다. 총 정원과 따로 셉니다.
        {'\n'}0으로 두면 휠체어 이용 어르신을 이 차량에 배차하지 않습니다.
      </Text>

      {/* 이 차량만의 하원 마감. 자차는 센터로 돌아오지 않아 조금 늦게 잡기도 한다. */}
      <View style={styles.field}>
        <Text style={styles.label}>하원 마감 시각 (이 차량만)</Text>
        <TimeInput
          style={styles.input}
          placeholderTextColor="#98A2B3"
          value={value.outboundDeadline}
          onChangeTime={(text) => set('outboundDeadline', text)}
          placeholder="비우면 센터 공통값"
        />
      </View>
      <Text style={styles.startHint}>
        {isCustomStart
          ? '자차는 마지막 어르신을 내려드리는 시각을 기준으로 봅니다. 차고지 퇴근길은 세지 않습니다.'
          : '센터 차량은 센터로 돌아오는 시각을 기준으로 봅니다.'}
      </Text>

      {/* --- 자차 송영 --- */}
      <Text style={styles.label}>1회차 출발지</Text>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggle, !isCustomStart && styles.toggleOn]}
          onPress={() => set('startType', 'center')}
        >
          <Icon name="center" size={15} tint={!isCustomStart ? color.teal : color.textSecondary} />
          <Text style={[styles.toggleText, !isCustomStart && styles.toggleTextOn]}>
            센터에서 출발
          </Text>
        </Pressable>
        <Pressable
          style={[styles.toggle, isCustomStart && styles.toggleOn]}
          onPress={() => set('startType', 'custom')}
        >
          <Icon name="home" size={15} tint={isCustomStart ? color.teal : color.textSecondary} />
          <Text style={[styles.toggleText, isCustomStart && styles.toggleTextOn]}>
            다른 주소지 (자차)
          </Text>
        </Pressable>
      </View>

      {isCustomStart ? (
        <View style={styles.startBox}>
          <Pressable style={styles.searchButton} onPress={() => setIsAddressOpen(true)}>
            <Icon name="search" size={15} tint="#FFFFFF" />
            <Text style={styles.searchButtonText}>
              {startAddress ? '출발지 다시 검색하기' : '출발지 주소 찾기'}
            </Text>
          </Pressable>

          {startAddress ? (
            <Text style={styles.startAddress}>{startAddress}</Text>
          ) : (
            <View style={styles.warnRow}>
              <Icon name="warning" size={14} tint="#8A6100" />
              <Text style={styles.startWarning}>
                주소를 넣지 않으면 배차 계산이 거절됩니다.
              </Text>
            </View>
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
  label: { color: '#667085', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8F9FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0D2540' },
  toggleRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  warnRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  toggle: { flex: 1, flexDirection: 'row', gap: 5, justifyContent: 'center', borderRadius: 12, borderWidth: 1.5, borderColor: '#E4E7EC', backgroundColor: '#F8F9FB', paddingVertical: 11, alignItems: 'center' },
  toggleOn: { borderColor: '#0BA38E', backgroundColor: '#E9F7EF' },
  toggleText: { color: '#667085', fontSize: 12.5, fontWeight: '800' },
  toggleTextOn: { color: '#0BA38E' },
  startBox: { backgroundColor: '#FEF6E7', borderWidth: 1, borderColor: '#F2B84B', borderRadius: 12, padding: 12, gap: 8 },
  searchButton: { flexDirection: 'row', gap: 6, justifyContent: 'center', backgroundColor: '#0D2540', borderRadius: 10, paddingVertical: 12, alignItems: 'center' },
  searchButtonText: { color: '#FFFFFF', fontWeight: '800', fontSize: 13 },
  startAddress: { color: '#0D2540', fontSize: 14, fontWeight: '700', backgroundColor: '#FFFFFF', borderRadius: 8, padding: 10 },
  startWarning: { color: '#8A6100', fontSize: 12.5, fontWeight: '700' },
  startHint: { color: '#667085', fontSize: 12, lineHeight: 18 },
});
