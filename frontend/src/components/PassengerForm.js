import React, { useState } from 'react';
import TextInput from '../ui/TextInput';
import Text from '../ui/Text';
import Icon from '../ui/Icon';
import { STAY_HOURS, shiftTime } from '../api';
import { color } from '../theme';
import { Pressable, StyleSheet, Switch, View, TouchableOpacity } from 'react-native';

import AddressSearch from './AddressSearch';
import Accordion from './Accordion';

const Field = ({ label, ...props }) => (
  <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <TextInput
      style={styles.input}
      placeholderTextColor="#98A2B3"
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
  // 아침엔 보호자가 모셔오고 오후엔 센터 차를 타는 분이 있다.
  // 기존 명단에는 이 값이 없으므로 둘 다 탑승으로 본다.
  const attendingOutbound = value.attendingOutbound !== false;

  // 하차 시각을 비워두면 서버가 등원 시각 + 8시간으로 정한다.
  // 그 값을 미리 보여줘야 원장님이 '비워도 되는구나' 를 안다.
  const autoStart = shiftTime(value.pickupStart);
  const autoEnd = shiftTime(value.pickupEnd);
  const dropoffBlank = !(value.dropoffStart || '').trim() && !(value.dropoffEnd || '').trim();
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
          ? { label: '등원', icon: 'inbound', tone: 'success' }
          : { label: '등원 안 함', icon: 'inbound', tone: 'default' },
        attendingOutbound
          ? { label: '하원', icon: 'outbound', tone: 'success' }
          : { label: '하원 안 함', icon: 'outbound', tone: 'default' },
        ...((attending || attendingOutbound) && !hasGuardianPhone
          ? [{ label: '연락처 없음', icon: 'warning', tone: 'warning' }]
          : []),
        ...(smsOptIn ? [] : [{ label: '알림 끔', icon: 'bellOff', tone: 'warning' }]),
      ]}
      tone={(attending || attendingOutbound) ? 'default' : 'muted'}
      onRemove={onRemove}
    >
      {/* 등원과 하원을 따로 켜고 끈다. 명단에서 지우는 것이 아니라
          그날 그 운행의 배차 대상에서만 빠진다. */}
      <View style={styles.attendanceRow}>
        <View style={styles.attendanceText}>
          <View style={styles.labelRow}>
            <Icon name="inbound" size={15} tint={attending ? color.teal : color.textSecondary} />
            <Text style={[styles.attendanceLabel, !attending && styles.absentLabel]}>
              등원 탑승
            </Text>
          </View>
          <Text style={styles.switchCaption}>
            {attending ? '아침에 센터로 모셔옵니다.' : '등원 배차에서 빠집니다.'}
          </Text>
        </View>
        <Switch
          value={attending}
          onValueChange={(enabled) => set('attending', enabled)}
          trackColor={{ false: '#E4E7EC', true: '#6ED6C1' }}
          thumbColor={attending ? '#3BB273' : '#F8F9FB'}
        />
      </View>

      {/* 켠 스위치 바로 밑에 그 시간칸을 둔다. 상단 토글과 무관하게
          여기서 등원·하원 시각을 모두 고칠 수 있다. */}
      {attending && (
        <View style={styles.timeBlock}>
          <View style={styles.timeRow}>
            <View style={styles.timeField}>
              <Field
                label="픽업 하한"
                value={value.pickupStart}
                onChangeText={(text) => set('pickupStart', text)}
                placeholder="08:00"
                keyboardType="numbers-and-punctuation"
                maxLength={5}
              />
            </View>
            <Text style={styles.tilde}>~</Text>
            <View style={styles.timeField}>
              <Field
                label="픽업 상한"
                value={value.pickupEnd}
                onChangeText={(text) => set('pickupEnd', text)}
                placeholder="08:30"
                keyboardType="numbers-and-punctuation"
                maxLength={5}
              />
            </View>
          </View>
        </View>
      )}

      <View style={styles.attendanceRow}>
        <View style={styles.attendanceText}>
          <View style={styles.labelRow}>
            <Icon
              name="outbound"
              size={15}
              tint={attendingOutbound ? color.teal : color.textSecondary}
            />
            <Text style={[styles.attendanceLabel, !attendingOutbound && styles.absentLabel]}>
              하원 탑승
            </Text>
          </View>
          <Text style={styles.switchCaption}>
            {attendingOutbound ? '오후에 댁으로 모셔다드립니다.' : '하원 배차에서 빠집니다.'}
          </Text>
        </View>
        <Switch
          value={attendingOutbound}
          onValueChange={(enabled) => set('attendingOutbound', enabled)}
          trackColor={{ false: '#E4E7EC', true: '#6ED6C1' }}
          thumbColor={attendingOutbound ? '#3BB273' : '#F8F9FB'}
        />
      </View>

      {attendingOutbound && (
        <View style={styles.timeBlock}>
          <View style={styles.timeRow}>
            <View style={styles.timeField}>
              <Field
                label="하차 하한"
                value={value.dropoffStart}
                onChangeText={(text) => set('dropoffStart', text)}
                placeholder={autoStart || '15:30'}
                keyboardType="numbers-and-punctuation"
                maxLength={5}
              />
            </View>
            <Text style={styles.tilde}>~</Text>
            <View style={styles.timeField}>
              <Field
                label="하차 상한"
                value={value.dropoffEnd}
                onChangeText={(text) => set('dropoffEnd', text)}
                placeholder={autoEnd || '17:00'}
                keyboardType="numbers-and-punctuation"
                maxLength={5}
              />
            </View>
          </View>
          {dropoffBlank && (
            <Text style={styles.autoHint}>
              {autoStart
                ? `비워두면 등원 ${value.pickupStart}~${value.pickupEnd} 에 ${STAY_HOURS}시간을 더해 `
                  + `${autoStart}~${autoEnd} 로 자동 계산됩니다.`
                : `비워두면 등원 시각에 ${STAY_HOURS}시간을 더해 자동 계산됩니다.`}
            </Text>
          )}
        </View>
      )}
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
        <View style={styles.warnRow}>
          <Icon name="warning" size={14} tint="#8A6100" />
          <Text style={styles.phoneWarning}>
            번호가 없으면 탑승 완료 문자가 발송되지 않습니다.
          </Text>
        </View>
      )}

      <Field
        label="어르신 본인 연락처"
        value={value.passengerPhone}
        onChangeText={(text) => set('passengerPhone', text)}
        placeholder="010-9876-5432 (없으면 비워두세요)"
        keyboardType="phone-pad"
      />

      {/* 기사님이 📞 를 눌렀을 때 누구에게 걸지. 어르신마다 다르다. */}
      <Text style={styles.label}>대표 연락처 (기사님 전화 버튼)</Text>
      <View style={styles.toggleRow}>
        <Pressable
          style={[styles.toggle, !callsSelf && styles.toggleOn]}
          onPress={() => set('primaryContact', 'guardian')}
        >
          <Text style={[styles.toggleText, !callsSelf && styles.toggleTextOn]}>
            보호자
          </Text>
        </Pressable>
        <Pressable
          style={[styles.toggle, callsSelf && styles.toggleOn]}
          onPress={() => set('primaryContact', 'self')}
        >
          <Text style={[styles.toggleText, callsSelf && styles.toggleTextOn]}>
            어르신 본인
          </Text>
        </Pressable>
      </View>
      {callsSelf && !hasOwnPhone && (
        <View style={styles.warnRow}>
          <Icon name="warning" size={14} tint="#8A6100" />
          <Text style={styles.phoneWarning}>
            본인 연락처가 없어 전화는 보호자에게 연결됩니다.
          </Text>
        </View>
      )}

      {/* 알림을 원치 않는 보호자가 있다. 명단에서 지우는 대신 여기서 끈다. */}
      <View style={styles.attendanceRow}>
        <View style={{ flex: 1 }}>
          <View style={styles.labelRow}>
            <Icon
              name={smsOptIn ? 'bellOn' : 'bellOff'}
              size={15}
              tint={smsOptIn ? color.teal : color.textSecondary}
            />
            <Text style={styles.attendanceLabel}>
              {smsOptIn ? '탑승 완료 알림 보내기' : '탑승 완료 알림 끔'}
            </Text>
          </View>
          <Text style={styles.switchCaption}>
            {smsOptIn
              ? '탑승하시면 보호자에게 문자를 보냅니다.'
              : '문자를 보내지 않습니다. 탑승 기록은 그대로 남습니다.'}
          </Text>
        </View>
        <Switch
          value={smsOptIn}
          onValueChange={(enabled) => set('smsOptIn', enabled)}
          trackColor={{ false: '#E4E7EC', true: '#6ED6C1' }}
          thumbColor={smsOptIn ? '#3BB273' : '#F8F9FB'}
        />
      </View>

      {/* 개조된 주소 검색 영역 */}
      <View style={{ marginBottom: 15 }}>
        <Text style={styles.label}>주소</Text>
        <TouchableOpacity
          style={styles.addressButton}
          onPress={() => setIsAddressModalOpen(true)}
        >
          <Icon name="search" size={15} tint="#FFFFFF" />
          <Text style={styles.addressButtonText}>
            {value.address ? '주소 다시 검색하기' : '정확한 주소 찾기'}
          </Text>
        </TouchableOpacity>
        
        {/* 검색 완료된 주소가 표시되는 곳 */}
        {value.address ? (
          <View>
            <Text style={{ marginTop: 8, marginBottom: 8, color: '#667085', fontSize: 15, padding: 5, backgroundColor: '#F2F4F7' }}>
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
      
      <View style={styles.switchRow}>
        <View>
          <Text style={styles.switchTitle}>휠체어 이용</Text>
          <Text style={styles.switchCaption}>관제 목록에 별도 표시합니다.</Text>
        </View>
        <Switch
          value={value.wheelchair}
          onValueChange={(enabled) => set('wheelchair', enabled)}
          trackColor={{ false: '#E4E7EC', true: '#6ED6C1' }}
          thumbColor={value.wheelchair ? '#3BB273' : '#F8F9FB'}
        />
      </View>
    </Accordion>
  );
}

const styles = StyleSheet.create({
  attendanceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#F8F9FB', borderRadius: 12, padding: 12, marginBottom: 14 },
  attendanceLabel: { color: '#237B4B', fontWeight: '800', fontSize: 14 },
  absentLabel: { color: '#667085' },
  field: { marginBottom: 12 },
  label: { color: '#667085', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  attendanceText: { flex: 1, minWidth: 0, paddingRight: 12 },
  warnRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  addressButton: { flexDirection: 'row', gap: 6, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0D2540', paddingVertical: 12, borderRadius: 10, marginTop: 5 },
  addressButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  toggleRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  toggle: { flex: 1, borderRadius: 12, borderWidth: 1.5, borderColor: '#E4E7EC', backgroundColor: '#F8F9FB', paddingVertical: 11, alignItems: 'center' },
  toggleOn: { borderColor: '#0BA38E', backgroundColor: '#E9F7EF' },
  toggleText: { color: '#667085', fontSize: 12.5, fontWeight: '800' },
  toggleTextOn: { color: '#0BA38E' },
  phoneWarning: { color: '#8A6100', fontSize: 12, fontWeight: '700', marginTop: -6, marginBottom: 12, lineHeight: 17 },
  input: { backgroundColor: '#F8F9FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 16, color: '#0D2540' },
  timeRow: { flexDirection: 'row', alignItems: 'center' },
  // 스위치와 그 시간칸을 한 덩어리로 묶어 어디에 딸린 값인지 보이게 한다.
  timeBlock: { backgroundColor: '#F8F9FB', borderRadius: 12, padding: 12, marginBottom: 12 },
  timeField: { flex: 1 },
  autoHint: { color: '#07705F', backgroundColor: '#E6F7F4', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, fontSize: 12, lineHeight: 18, marginBottom: 12 },
  tilde: { color: '#667085', fontWeight: '800', marginHorizontal: 9, marginTop: 6 },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 2 },
  switchTitle: { color: '#0D2540', fontWeight: '700' },
  switchCaption: { color: '#98A2B3', fontSize: 12, marginTop: 2 },
});