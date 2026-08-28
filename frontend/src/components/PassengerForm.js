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
import Accordion from './Accordion';

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
  // 백엔드와 같은 기준으로 판정한다. (숫자만 뽑아 10자리 미만이면 발송 건너뜀)
  const hasGuardianPhone = (value.guardianPhone || '').replace(/[^0-9]/g, '').length >= 10;
  const hasOwnPhone = (value.passengerPhone || '').replace(/[^0-9]/g, '').length >= 10;
  // 기존 데이터에는 없는 값이다. 알림은 받는 쪽, 전화는 보호자 쪽을 기본으로 본다.
  const smsOptIn = value.smsOptIn !== false;
  const callsSelf = value.primaryContact === 'self';

  const [isAddressModalOpen, setIsAddressModalOpen] = useState(false);

  // 접힌 줄만 보고도 무엇이 저장돼 있는지, 무엇이 빠졌는지 알 수 있어야 한다.
  const displayName = (value.name || '').trim() || `어르신 ${index + 1}`;
  const summary = hasGuardianPhone
    ? `보호자 ${(value.guardianPhone || '').trim()}`
    : '보호자 연락처 없음';

  return (
    <Accordion
      index={index}
      title={displayName}
      summary={summary}
      badges={[
        attending
          ? (hasGuardianPhone ? { label: '출석', tone: 'success' } : { label: '연락처 없음', tone: 'warning' })
          : { label: '결석', tone: 'default' },
        ...(smsOptIn ? [] : [{ label: '🔕 알림 끔', tone: 'warning' }]),
      ]}
      tone={attending ? 'default' : 'muted'}
      onRemove={onRemove}
    >
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
      
      {/* 보호자 연락처. 비어 있으면 탑승 완료 문자가 발송되지 않는다. */}
      <Field
        label="보호자 연락처"
        value={value.guardianPhone}
        onChangeText={(text) => set('guardianPhone', text)}
        placeholder="010-1234-5678"
        keyboardType="phone-pad"
      />
      {attending && !hasGuardianPhone && (
        <Text style={styles.phoneWarning}>
          ⚠️ 번호가 없으면 탑승 완료 문자가 발송되지 않습니다.
        </Text>
      )}

      <Field
        label="어르신 본인 연락처"
        value={value.passengerPhone}
        onChangeText={(text) => set('passengerPhone', text)}
        placeholder="010-9876-5432 (없으면 비워두세요)"
        keyboardType="phone-pad"
      />

      {/* 기사님이 📞 를 눌렀을 때 누구에게 걸지. 어르신마다 다르다. */}
      <Text style={styles.label}>대표 연락처 (기사님 📞 버튼)</Text>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggle, !callsSelf && styles.toggleOn]}
          onPress={() => set('primaryContact', 'guardian')}
        >
          <Text style={[styles.toggleText, !callsSelf && styles.toggleTextOn]}>
            👨‍👩‍👦 보호자
          </Text>
        </Pressable>
        <Pressable
          style={[styles.toggle, callsSelf && styles.toggleOn]}
          onPress={() => set('primaryContact', 'self')}
        >
          <Text style={[styles.toggleText, callsSelf && styles.toggleTextOn]}>
            🧑 어르신 본인
          </Text>
        </Pressable>
      </View>
      {callsSelf && !hasOwnPhone && (
        <Text style={styles.phoneWarning}>
          ⚠️ 본인 연락처가 없어 기사님 📞 는 보호자에게 연결됩니다.
        </Text>
      )}

      {/* 알림을 원치 않는 보호자가 있다. 명단에서 지우는 대신 여기서 끈다. */}
      <View style={styles.attendanceRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.attendanceLabel}>
            {smsOptIn ? '🔔 탑승 완료 알림 보내기' : '🔕 탑승 완료 알림 끔'}
          </Text>
          <Text style={styles.switchCaption}>
            {smsOptIn
              ? '탑승하시면 보호자에게 문자를 보냅니다.'
              : '문자를 보내지 않습니다. 탑승 기록은 그대로 남습니다.'}
          </Text>
        </View>
        <Switch
          value={smsOptIn}
          onValueChange={(enabled) => set('smsOptIn', enabled)}
          trackColor={{ false: '#CBD5E1', true: '#A7F3D0' }}
          thumbColor={smsOptIn ? '#059669' : '#F8FAFC'}
        />
      </View>

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
    </Accordion>
  );
}

const styles = StyleSheet.create({
  attendanceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#F8FAFC', borderRadius: 12, padding: 12, marginBottom: 14 },
  attendanceLabel: { color: '#047857', fontWeight: '800', fontSize: 14 },
  absentLabel: { color: '#64748B' },
  field: { marginBottom: 12 },
  label: { color: '#475569', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  toggleRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  toggle: { flex: 1, borderRadius: 12, borderWidth: 1.5, borderColor: '#CBD5E1', backgroundColor: '#F8FAFC', paddingVertical: 11, alignItems: 'center' },
  toggleOn: { borderColor: '#0F766E', backgroundColor: '#ECFDF5' },
  toggleText: { color: '#64748B', fontSize: 12.5, fontWeight: '800' },
  toggleTextOn: { color: '#0F766E' },
  phoneWarning: { color: '#B45309', fontSize: 12, fontWeight: '700', marginTop: -6, marginBottom: 12, lineHeight: 17 },
  input: { backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0F172A' },
  timeRow: { flexDirection: 'row', alignItems: 'center' },
  timeField: { flex: 1 },
  tilde: { color: '#64748B', fontWeight: '800', marginHorizontal: 9, marginTop: 6 },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 2 },
  switchTitle: { color: '#1E293B', fontWeight: '700' },
  switchCaption: { color: '#94A3B8', fontSize: 12, marginTop: 2 },
});