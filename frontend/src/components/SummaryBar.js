import React from 'react';
import Text from '../ui/Text';
import { TRIP_OUTBOUND, tripLabel } from '../api';
import { StyleSheet, View } from 'react-native';

/**
 * 관리자 화면 상단 현황판.
 *
 * 어느 탭에 있든 같은 자리에 떠서, 지금 몇 대/몇 명을 다루고 있는지
 * 눈을 옮기지 않고 확인할 수 있게 한다.
 */
export default function SummaryBar({ vehicles, passengers, tripType }) {
  const vehicleCount = vehicles.length;
  // 이름이나 주소가 하나도 없는 줄은 아직 입력 중인 빈 칸이므로 세지 않는다.
  const entered = passengers.filter((item) => item.name || item.address);
  // 등원과 하원은 타는 분이 다르다. 지금 보고 있는 쪽을 센다.
  // 예전에는 늘 등원 기준으로 세어, 하원 탑승을 꺼도 숫자가 그대로였다.
  const outbound = tripType === TRIP_OUTBOUND;
  const attending = entered.filter((item) => (
    outbound ? item.attendingOutbound !== false : item.attending !== false
  ));

  const items = [
    { label: `오늘 ${tripLabel(tripType)} 대상`, value: attending.length, unit: '명', tone: 'teal' },
    { label: '운행 차량', value: vehicleCount, unit: '대', tone: 'navy' },
    { label: '전체 명단', value: entered.length, unit: '명', tone: 'slate' },
  ];

  return (
    <View style={styles.row}>
      {items.map((item) => (
        <View key={item.label} style={[styles.cell, styles[`cell_${item.tone}`]]}>
          <Text style={styles.label}>{item.label}</Text>
          <Text style={[styles.value, styles[`value_${item.tone}`]]}>
            {item.value}
            <Text style={styles.unit}> {item.unit}</Text>
          </Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, marginHorizontal: 18, marginBottom: 12 },
  cell: { flex: 1, borderRadius: 12, paddingVertical: 11, paddingHorizontal: 12, borderWidth: 1 },
  cell_teal: { backgroundColor: '#E6F7F4', borderColor: '#6ED6C1' },
  cell_navy: { backgroundColor: '#F8F9FB', borderColor: '#E4E7EC' },
  cell_slate: { backgroundColor: '#F8F9FB', borderColor: '#E4E7EC' },
  label: { color: '#667085', fontSize: 11, fontWeight: '600' },
  value: { fontSize: 20, fontWeight: '700', marginTop: 3 },
  value_teal: { color: '#0BA38E' },
  value_navy: { color: '#0D2540' },
  value_slate: { color: '#667085' },
  unit: { fontSize: 12, fontWeight: '600' },
});
