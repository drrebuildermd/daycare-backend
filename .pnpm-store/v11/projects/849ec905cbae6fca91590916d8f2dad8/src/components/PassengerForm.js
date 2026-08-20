import React, { useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  TouchableOpacity
} from 'react-native';

import AddressSearch from './AddressSearch';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput
      style={styles.input}
      placeholderTextColor="#94A3B8"
      {...props}
    />
  </View>
);

export default function PassengerForm({ value, index, onChange, onRemove }) {
  const set = (field, nextValue) => onChange({ ...value, [field]: nextValue });
  // 명단에는 남기고 배차에서만 빼기 위한 값. 기존 데이터에는 없으므로 기본을 출석으로 본다.
  const attending = value.attending !== false;

const [isAddressModalOpen, setIsAddressModalOpen] = useState(false);

  return (
    <View style={[styles.card, !attending && styles.absentCard]}>
      <View style={styles.header}>
        <View style={styles.numberBadge}><Text style={styles.number}>{index + 1}</Text></View>
        <Text style={[styles.title, !attending && styles.absentTitle]}>
          {value.name || `어르신 ${index + 1}`}
        </Text>
        <Pressable onPress={onRemove} hitSlop={10}>
          <Text style={styles.remove}>삭제</Text>
        </Pressable>
      </View>

      <View style={styles.attendanceRow}>
        <View>
          <Text style={[styles.attendanceLabel, !attending && styles.absentLabel]}>
            {attending ? '🟢 출석' : '⚪ 결석'}
          </Text>
          <Text style={styles.switchCaption}>
            {attending ? '오늘 배차에 포함됩니다.' : '명단은 유지되고 오늘 배차에서만 빠집니다.'}
          </Text>
        </View>
        <Switch
          value={attending}
          onValueChange={(enabled) => set('attending', enabled)}
          trackColor={{ false: '#CBD5E1', true: '#A7F3D0' }}
          thumbColor={attending ? '#059669' : '#F8FAFC'}
        />
      </View>
      <Field label="어르신 이름" value={value.name} onChangeText={(text) => set('name', text)} placeholder="홍길동" />
      {/* 개조된 주소 검색 영역 */}
          <View style={{ marginBottom: 15 }}>
            <Text style={styles.label}>주소</Text>
            <TouchableOpacity 
              style={{ backgroundColor: '#0f766e', padding: 12, borderRadius: 8, marginTop: 5 }}
              onPress={() => setIsAddressModalOpen(true)}
            >
              <Text style={{ color: 'white', textAlign: 'center', fontWeight: 'bold' }}>
                📍 {value.address ? "주소 다시 검색하기" : "정확한 주소 찾기"}
              </Text>
            </TouchableOpacity>
            
           {/* 검색 완료된 주소가 표시되는 곳 */}
            {value.address ? (
              <View>
                <Text style={{ marginTop: 8, marginBottom: 8, color: '#374151', fontSize: 15, padding: 5, backgroundColor: '#f3f4f6' }}>
                  {value.address}
                </Text>
                {/* 🎯 상세 주소 입력칸 추가 */}
                <Field 
                  label="상세 주소" 
                  value={value.detailAddress} 
                  onChangeText={(text) => set('detailAddress', text)} 
                  placeholder="예: 101동 202호 (선택)" 
                />
              </View>
            ) : null}
          </View>

          {/* 우편번호 검색 팝업창 */}
          <AddressSearch
            visible={isAddressModalOpen}
            onSelected={(address) => {
              set('address', address); // 도로명 주소를 꽂아넣음
              setIsAddressModalOpen(false); // 선택 즉시 팝업 닫기
            }}
            onClose={() => setIsAddressModalOpen(false)}
          />
      
      <View style={styles.timeRow}>
        <View style={styles.timeField}>
          <Field label="픽업 하한" value={value.pickupStart} onChangeText={(text) => set('pickupStart', text)} placeholder="08:00" keyboardType="numbers-and-punctuation" maxLength={5} />
        </View>
        <Text style={styles.tilde}>~</Text>
        <View style={styles.timeField}>
          <Field label="픽업 상한" value={value.pickupEnd} onChangeText={(text) => set('pickupEnd', text)} placeholder="08:30" keyboardType="numbers-and-punctuation" maxLength={5} />
        </View>
      </View>
      <View style={styles.switchRow}>
        <View>
          <Text style={styles.switchTitle}>휠체어 이용</Text>
          <Text style={styles.switchCaption}>관제 목록에 별도 표시합니다.</Text>
        </View>
        <Switch
          value={value.wheelchair}
          onValueChange={(enabled) => set('wheelchair', enabled)}
          trackColor={{ false: '#CBD5E1', true: '#A7F3D0' }}
          thumbColor={value.wheelchair ? '#059669' : '#F8FAFC'}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 16, marginBottom: 14, borderWidth: 1, borderColor: '#E2E8F0' },
  absentCard: { backgroundColor: '#F8FAFC', borderColor: '#CBD5E1', opacity: 0.75 },
  absentTitle: { color: '#94A3B8', textDecorationLine: 'line-through' },
  attendanceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#F8FAFC', borderRadius: 12, padding: 12, marginBottom: 14 },
  attendanceLabel: { color: '#047857', fontWeight: '800', fontSize: 14 },
  absentLabel: { color: '#64748B' },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  numberBadge: { width: 28, height: 28, borderRadius: 9, backgroundColor: '#E0F2FE', alignItems: 'center', justifyContent: 'center', marginRight: 9 },
  number: { color: '#0369A1', fontWeight: '800' },
  title: { flex: 1, color: '#0F172A', fontSize: 16, fontWeight: '800' },
  remove: { color: '#DC2626', fontWeight: '700', fontSize: 13 },
  field: { marginBottom: 12 },
  label: { color: '#475569', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0F172A' },
  timeRow: { flexDirection: 'row', alignItems: 'center' },
  timeField: { flex: 1 },
  tilde: { color: '#64748B', fontWeight: '800', marginHorizontal: 9, marginTop: 6 },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 2 },
  switchTitle: { color: '#1E293B', fontWeight: '700' },
  switchCaption: { color: '#94A3B8', fontSize: 12, marginTop: 2 },
});

