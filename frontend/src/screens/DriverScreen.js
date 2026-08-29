import React, { useCallback, useEffect, useRef, useState } from 'react';
import Text from '../ui/Text';
import Icon from '../ui/Icon';
import { color } from '../theme';
import { ActivityIndicator, Alert, BackHandler, Image, Linking, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import {
  acknowledgeDispatch,
  fetchCompletedStopMap,
  fetchTodayAcks,
  TRIP_INBOUND,
  TRIP_OUTBOUND,
  guessTripType,
  tripLabel,
  fetchTodayDispatch,
  saveRideCompletion,
} from '../api';
import { callTargetFor } from '../contacts';
import { originForStop, startNavigation } from '../navigation';
import Accordion from '../components/Accordion';
import RouteMap from '../components/RouteMap';

// 관제 화면과 같은 주기로 맞춘다. 다른 기사님이 태운 어르신이 내 화면에도 반영된다.
const POLL_MS = 20000;

function formatAckTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

/**
 * 기사님 전용 화면.
 *
 * 현장에서 운전 중에 쓰는 화면이다. 탭도 설정도 없다.
 * 차량을 한 번 고르면 그 뒤로는 명단 / 내비 / 전화 / 완료 네 가지만 보인다.
 */
function TripSwitch({ value, onChange }) {
  return (
    <View style={styles.tripRow}>
      {[TRIP_INBOUND, TRIP_OUTBOUND].map((option) => {
        const active = value === option;
        return (
          <Pressable
            key={option}
            style={[styles.tripChip, active && styles.tripChipOn]}
            onPress={() => onChange(option)}
          >
            <Icon
              name={option === TRIP_INBOUND ? 'inbound' : 'outbound'}
              size={16}
              tint={active ? color.deepNavy : '#C7D0DA'}
            />
            <Text style={[styles.tripChipText, active && styles.tripChipTextOn]}>
              {tripLabel(option)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}


export default function DriverScreen({ onExit, bottomInset = 0 }) {
  // 아침이면 등원, 오후면 하원으로 열어 준다. 기사님이 매번 고르지 않아도 되게.
  // 손으로 바꿀 수 있어야 한다. 늦은 등원이나 이른 하원이 있다.
  const [tripType, setTripType] = useState(guessTripType);
  const [dispatch, setDispatch] = useState(null);
  const [ackList, setAckList] = useState([]);
  const [vehicleId, setVehicleId] = useState(null);
  const [completed, setCompleted] = useState({});
  const [saving, setSaving] = useState({});
  const [ackedAt, setAckedAt] = useState(null);
  const [acking, setAcking] = useState(false);
  const [phase, setPhase] = useState('loading'); // loading | ready | error
  const [elapsed, setElapsed] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const tickerRef = useRef(null);

  const load = useCallback(async () => {
    setPhase('loading');
    setElapsed(0);
    const startedAt = Date.now();
    clearInterval(tickerRef.current);
    tickerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000,
    );
    try {
      const [today, done, acks] = await Promise.all([
        fetchTodayDispatch(tripType),
        fetchCompletedStopMap(tripType).catch(() => ({})),
        fetchTodayAcks(tripType).catch(() => ({ records: [] })),
      ]);
      setDispatch(today.result || null);
      setCompleted(done);
      setAckList(acks.records || []);
      setPhase('ready');
    } catch (error) {
      setErrorMessage(error.message);
      setPhase('error');
    } finally {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
  }, [tripType]);

  useEffect(() => {
    load();
    return () => clearInterval(tickerRef.current);
  }, [load]);

  // 차량을 고른 뒤에만 주기 갱신한다.
  useEffect(() => {
    if (phase !== 'ready' || !vehicleId) return undefined;
    const timer = setInterval(() => {
      fetchCompletedStopMap(tripType).then(setCompleted).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase, vehicleId]);

  const vehicle = (dispatch?.vehicles || []).find((v) => v.vehicle_id === vehicleId);

  useEffect(() => {
    const mine = ackList.find((item) => item.vehicle_id === vehicleId);
    setAckedAt(mine ? mine.acknowledged_at : null);
  }, [ackList, vehicleId]);

  // 차량을 고른 뒤 뒤로 가기를 누르면 차량 선택 화면으로 돌아간다.
  // 여기서 처리하지 않으면 App.js 핸들러가 모드 선택까지 빠져버린다.
  useEffect(() => {
    if (!vehicleId) return undefined;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      setVehicleId(null);
      return true;
    });
    return () => subscription.remove();
  }, [vehicleId]);

  const outbound = tripType === TRIP_OUTBOUND;
  const doneWord = outbound ? '하차 완료' : '탑승 완료';

  const completeStop = async (stop, tripRound) => {
    setSaving((current) => ({ ...current, [stop.passenger_id]: true }));
    try {
      const record = await saveRideCompletion({
        passenger_id: stop.passenger_id,
        passenger_name: stop.name,
        vehicle_id: vehicle.vehicle_id,
        vehicle_type: vehicle.vehicle_type,
        vehicle_plate_number: vehicle.plate_number,
        trip_type: tripType,
        trip_round: tripRound,
        scheduled_pickup: stop.estimated_pickup,
        center_name: dispatch?.center?.name || '',
        sms_opt_in: stop.sms_opt_in !== false,
        guardian_phone: stop.guardian_phone || '',
      });
      setCompleted((current) => ({ ...current, [stop.passenger_id]: record.completed_at }));
      if (record.sms_sent === false) {
        Alert.alert(
          `${doneWord} (문자 미발송)`,
          `${stop.name} 어르신 기록은 저장했습니다.\n\n문자가 발송되지 않았습니다: ${record.sms_message || '사유 불명'}`,
        );
      }
    } catch (error) {
      Alert.alert('탑승 완료 저장 실패', error.message);
    } finally {
      setSaving((current) => {
        const next = { ...current };
        delete next[stop.passenger_id];
        return next;
      });
    }
  };

  const confirmDispatch = async () => {
    setAcking(true);
    try {
      const record = await acknowledgeDispatch({
        vehicle_id: vehicle.vehicle_id,
        trip_type: tripType,
        vehicle_label: `${vehicle.vehicle_type} ${vehicle.plate_number}`,
        driver_name: vehicle.driver_name || null,
      });
      setAckedAt(record.acknowledged_at);
    } catch (error) {
      Alert.alert('확인 처리 실패', error.message);
    } finally {
      setAcking(false);
    }
  };

  // 앞 정류장(또는 회차 출발지)을 출발지로 넘긴다.
  // 카카오맵이 GPS 를 못 잡아 출발지가 빈칸이던 문제를 이걸로 없앤다.
  const openNavigation = (stop, trip, stopIndex) => startNavigation(
    stop,
    originForStop({ vehicle, trip, stopIndex, center: dispatch?.center }),
  );

  const callContact = async (stop) => {
    const target = callTargetFor(stop);
    if (!target) {
      Alert.alert('연락처 없음', `${stop.name} 어르신의 연락처가 등록되어 있지 않습니다.`);
      return;
    }
    try {
      await Linking.openURL(`tel:${target.digits}`);
    } catch (_) {
      Alert.alert('전화 연결 실패', '이 기기에서 전화를 걸 수 없습니다.');
    }
  };

  // --- 로딩 / 오류 ---
  if (phase === 'loading') {
    return (
      <View style={styles.center}>
        {/* 심볼 → 진행 표시 → 제목 → 설명 순으로 간격을 벌려 눈이 차례로 읽게 한다. */}
        <Image
          source={require('../../assets/mroute-mark.png')}
          style={styles.loadingMark}
          resizeMode="contain"
        />
        <ActivityIndicator size="large" color={color.teal} style={styles.loadingSpinner} />
        <Text style={styles.centerTitle}>오늘 배차를 불러오는 중입니다</Text>
        <Text style={styles.centerHint}>
          절전 상태였던 서버를 깨우는 중일 수 있습니다.{'\n'}
          처음 열 때는 1분 이상 걸릴 수 있습니다. 앱을 끄지 말고 기다려 주세요.
        </Text>
        <Text style={styles.elapsed}>{elapsed}초 경과</Text>
      </View>
    );
  }

  if (phase === 'error') {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{errorMessage}</Text>
        <Pressable style={styles.bigButton} onPress={load}>
          <Text style={styles.bigButtonText}>다시 시도</Text>
        </Pressable>
        <Pressable style={styles.linkButton} onPress={onExit}>
          <Text style={styles.linkText}>모드 바꾸기</Text>
        </Pressable>
      </View>
    );
  }

  // --- 차량 선택 ---
  if (!vehicle) {
    const vehicles = dispatch?.vehicles || [];
    return (
      <View style={styles.screen}>
        <View style={styles.topBar}>
          {/* 제목이 남는 공간을 다 먹어야 버튼이 오른쪽 끝으로 밀린다. */}
          <Text style={[styles.topTitle, { flex: 1 }]}>기사님 화면</Text>
          <Pressable onPress={onExit} hitSlop={12} style={[styles.topActionButton, { flexShrink: 0 }]}>
            <Text style={styles.topAction}>모드 변경</Text>
          </Pressable>
        </View>
        <TripSwitch value={tripType} onChange={setTripType} />
        <ScrollView contentContainerStyle={[styles.pickBody, { paddingBottom: 18 + bottomInset }]}>
          <Text style={styles.pickHeading}>
            {tripLabel(tripType)}하실 차량을 선택하세요
          </Text>
          {vehicles.length === 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>
                오늘 {tripLabel(tripType)} 배차가 아직 없습니다
              </Text>
              <Text style={styles.emptyBody}>
                관리자가 {tripLabel(tripType)} 배차를 전송하면 여기에 차량이 나타납니다.
                {'\n'}위에서 {tripLabel(tripType === TRIP_INBOUND ? TRIP_OUTBOUND : TRIP_INBOUND)}으로 바꿔 볼 수도 있습니다.
              </Text>
              <Pressable style={styles.bigButton} onPress={load}>
                <Text style={styles.bigButtonText}>새로고침</Text>
              </Pressable>
            </View>
          ) : vehicles.map((item) => {
            const total = (item.trips || [])
              .filter((trip) => trip.used)
              .reduce((sum, trip) => sum + trip.stops.length, 0);
            return (
              <Pressable
                key={item.vehicle_id}
                style={styles.vehiclePick}
                onPress={() => setVehicleId(item.vehicle_id)}
              >
                <Text style={styles.vehiclePickName}>{item.vehicle_type}</Text>
                <Text style={styles.vehiclePickPlate}>{item.plate_number}</Text>
                <Text style={styles.vehiclePickMeta}>
                  {item.driver_name ? `${item.driver_name} 선생님 · ` : ''}총 {total}명
                </Text>
                {item.start_type === 'custom' ? (
                  <View style={styles.startBlock}>
                    <View style={styles.selfBadge}>
                      <Text style={styles.selfBadgeText}>자차 송영</Text>
                    </View>
                    {/* 출발지는 기사님에게 중요한 운행 정보다. 줄을 통째로 내준다. */}
                    <View style={styles.startRow}>
                      <Icon name="home" size={14} tint={color.textSecondary} />
                      <Text style={styles.vehiclePickStart} numberOfLines={2}>
                        {item.start_address}
                      </Text>
                    </View>
                  </View>
                ) : (
                  // 센터 출발이면 긴 주소 대신 등록된 센터명을 보여준다.
                  <View style={styles.startRow}>
                    <Icon name="center" size={14} tint={color.textSecondary} />
                    <Text style={styles.vehiclePickCenter}>
                      {item.start_name || '센터'}에서 출발
                    </Text>
                  </View>
                )}
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
    );
  }

  // --- 오늘의 탑승 명단 ---
  const trips = (vehicle.trips || []).filter((trip) => trip.used);
  const totalStops = trips.reduce((sum, trip) => sum + trip.stops.length, 0);
  const doneCount = trips.reduce(
    (sum, trip) => sum + trip.stops.filter((s) => completed[s.passenger_id]).length, 0,
  );

  return (
    <View style={styles.screen}>
      <View style={styles.topBar}>
        <View style={{ flex: 1 }}>
          <Text style={styles.topTitle}>{vehicle.vehicle_type} {vehicle.plate_number}</Text>
          <Text style={styles.topSub}>
            {doneCount}/{totalStops}명 {doneWord}
            {vehicle.driver_name ? ` · ${vehicle.driver_name} 선생님` : ''}
          </Text>
        </View>
        <Pressable
          onPress={() => setVehicleId(null)}
          hitSlop={12}
          style={[styles.topActionButton, { flexShrink: 0 }]}
        >
          <Text style={styles.topAction}>차량 변경</Text>
        </Pressable>
      </View>

      <TripSwitch value={tripType} onChange={setTripType} />
      <ScrollView contentContainerStyle={[styles.listBody, { paddingBottom: 40 + bottomInset }]}>
        <View style={[styles.ackBar, ackedAt && styles.ackBarDone]}>
          {!!ackedAt && <Icon name="done" size={16} tint="#237B4B" />}
          <Text style={[styles.ackText, ackedAt && styles.ackTextDone]}>
            {ackedAt
              ? `${tripLabel(tripType)} 배차표를 확인했습니다 (${formatAckTime(ackedAt)})`
              : `오늘 ${tripLabel(tripType)} 배차표를 확인하셨으면 눌러 주세요. 관리자에게 전달됩니다.`}
          </Text>
          {!ackedAt && (
            <Pressable style={styles.ackButton} onPress={confirmDispatch} disabled={acking}>
              {acking
                ? <ActivityIndicator color="#FFFFFF" />
                : <Text style={styles.ackButtonText}>배차표 확인 완료</Text>}
            </Pressable>
          )}
        </View>

        <Accordion
          title="오늘 내 동선"
          summary={`${totalStops}곳 · 눌러서 펼치기`}
        >
          <RouteMap
            center={dispatch?.center}
            vehicles={dispatch?.vehicles || []}
            focusVehicleId={vehicle.vehicle_id}
          />
        </Accordion>

        {trips.map((trip) => (
          <View key={trip.round}>
            <View style={styles.roundHeader}>
              <Text style={styles.roundText}>{trip.round}회차</Text>
              <Text style={styles.roundMeta}>
                {trip.departure_time} 출발 · {trip.stops.length}명
              </Text>
            </View>

            {trip.stops.map((stop, stopIndex) => {
              const doneAt = completed[stop.passenger_id];
              const isSaving = Boolean(saving[stop.passenger_id]);
              const phoneTarget = callTargetFor(stop);

              return (
                <View
                  key={stop.passenger_id}
                  style={[styles.stopCard, doneAt && styles.stopCardDone]}
                >
                  <View style={styles.stopHead}>
                    <View style={[styles.seq, doneAt && styles.seqDone]}>
                      <Text style={styles.seqText}>{stop.sequence}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={styles.stopNameRow}>
                        <Text style={[styles.stopName, doneAt && styles.stopNameDone]}>
                          {stop.name}
                        </Text>
                        {!!stop.wheelchair && (
                          <Icon name="wheelchair" size={15} tint={color.textSecondary} />
                        )}
                      </View>
                      <Text style={styles.stopAddress}>{stop.address}</Text>
                      {!!stop.detail_address && (
                        <Text style={styles.stopDetail}>{stop.detail_address}</Text>
                      )}
                    </View>
                    <Text style={styles.stopTime}>{stop.estimated_pickup}</Text>
                  </View>

                  <View style={styles.actionRow}>
                    <Pressable
                      style={[styles.action, styles.actionNavi]}
                      onPress={() => openNavigation(stop, trip, stopIndex)}
                    >
                      <Icon name="navigate" size={22} tint={color.teal} />
                      <Text style={styles.actionLabel}>내비</Text>
                    </Pressable>

                    <Pressable
                      style={[styles.action, styles.actionCall, !phoneTarget && styles.actionOff]}
                      onPress={() => callContact(stop)}
                    >
                      <Icon
                        name="phone"
                        size={22}
                        tint={phoneTarget ? color.deepNavy : color.textSecondary}
                      />
                      <Text style={styles.actionLabel}>{phoneTarget ? phoneTarget.label : '번호없음'}</Text>
                    </Pressable>

                    <Pressable
                      style={[styles.action, styles.actionDone, doneAt && styles.actionOff]}
                      onPress={() => completeStop(stop, trip.round)}
                      disabled={Boolean(doneAt) || isSaving}
                    >
                      {isSaving ? (
                        <ActivityIndicator color="#FFFFFF" />
                      ) : (
                        <>
                          <Icon name={doneAt ? 'done' : 'boarded'} size={22} tint="#FFFFFF" />
                          <Text style={[styles.actionLabel, styles.actionLabelOnDark]}>
                            {doneAt ? '완료됨' : doneWord}
                          </Text>
                        </>
                      )}
                    </Pressable>
                  </View>
                </View>
              );
            })}
          </View>
        ))}

        {totalStops === 0 && (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>이 차량에 배정된 어르신이 없습니다</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F2F4F7' },
  // gap 을 쓰지 않고 항목마다 간격을 따로 준다. 심볼과 글자는 붙는 정도가 달라야 한다.
  center: { flex: 1, backgroundColor: '#F2F4F7', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32 },
  loadingMark: { width: 72, height: 72 },
  loadingSpinner: { marginTop: 24 },
  centerTitle: { color: '#0D2540', fontSize: 17, fontWeight: '700', textAlign: 'center', marginTop: 20 },
  centerHint: { color: '#667085', fontSize: 13.5, textAlign: 'center', lineHeight: 21, marginTop: 10 },
  elapsed: { color: '#07705F', fontSize: 14, fontWeight: '700', marginTop: 18 },
  errorText: { color: '#9B2C2C', fontSize: 15, fontWeight: '600', textAlign: 'center', lineHeight: 22, marginBottom: 20 },

  topBar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 18, paddingTop: 14, paddingBottom: 14, backgroundColor: '#0D2540' },
  topActionButton: { backgroundColor: 'rgba(255,255,255,0.18)', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 },
  topTitle: { color: '#FFFFFF', fontSize: 18, fontWeight: '700' },
  topSub: { color: '#6ED6C1', fontSize: 13, fontWeight: '700', marginTop: 3 },
  topAction: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },

  // 상단 딥네이비 띠 바로 아래에 붙는다. 선택된 쪽만 흰색으로 채워
  // 지금 무엇을 운행 중인지 운전석에서도 바로 보이게 한다.
  tripRow: { flexDirection: 'row', gap: 8, backgroundColor: '#0D2540', paddingHorizontal: 14, paddingBottom: 12 },
  tripChip: { flex: 1, flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 999, borderWidth: 1, borderColor: '#33506B' },
  tripChipOn: { backgroundColor: '#FFFFFF', borderColor: '#FFFFFF' },
  tripChipText: { color: '#C7D0DA', fontSize: 15, fontWeight: '700' },
  tripChipTextOn: { color: '#0D2540' },
  pickBody: { padding: 18, gap: 12 },
  pickHeading: { color: '#0D2540', fontSize: 18, fontWeight: '700', marginBottom: 4 },
  vehiclePick: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 2, borderColor: '#0BA38E', padding: 22 },
  vehiclePickName: { color: '#0D2540', fontSize: 24, fontWeight: '900' },
  vehiclePickPlate: { color: '#0BA38E', fontSize: 17, fontWeight: '800', marginTop: 2 },
  vehiclePickMeta: { color: '#667085', fontSize: 14, marginTop: 8 },
  vehiclePickStart: { flex: 1, minWidth: 0, color: '#8A6100', fontSize: 13.5, fontWeight: '600', lineHeight: 20 },
  vehiclePickCenter: { flex: 1, minWidth: 0, color: '#07705F', fontSize: 13.5, fontWeight: '600', lineHeight: 20 },
  stopNameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  startBlock: { alignItems: 'flex-start', gap: 6, marginTop: 8 },
  startRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: 6, alignSelf: 'stretch' },
  selfBadge: { backgroundColor: '#FEF6E7', borderWidth: 1, borderColor: '#F2B84B', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  selfBadgeText: { color: '#8A6100', fontSize: 11, fontWeight: '900' },
  ackBar: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#FFFFFF', borderRadius: 14, borderWidth: 1, borderColor: '#E4E7EC', padding: 14, marginBottom: 12 },
  ackBarDone: { backgroundColor: '#E9F7EF', borderColor: '#6ED6C1' },
  ackText: { flex: 1, color: '#667085', fontSize: 13, fontWeight: '700', lineHeight: 19 },
  ackTextDone: { color: '#237B4B' },
  ackButton: { backgroundColor: '#0BA38E', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 12 },
  ackButtonText: { color: '#FFFFFF', fontSize: 13.5, fontWeight: '900' },

  listBody: { padding: 14, paddingBottom: 40 },
  roundHeader: { flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 8, marginBottom: 10, paddingHorizontal: 4 },
  roundText: { color: '#0D2540', fontSize: 18, fontWeight: '900' },
  roundMeta: { color: '#667085', fontSize: 13, fontWeight: '700' },

  stopCard: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E4E7EC', padding: 16, marginBottom: 12 },
  stopCardDone: { backgroundColor: '#F8F9FB', borderColor: '#6ED6C1' },
  stopHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  seq: { width: 40, height: 40, borderRadius: 14, backgroundColor: '#0BA38E', alignItems: 'center', justifyContent: 'center' },
  seqDone: { backgroundColor: '#3BB273' },
  seqText: { color: '#FFFFFF', fontSize: 19, fontWeight: '900' },
  stopName: { color: '#0D2540', fontSize: 22, fontWeight: '900' },
  stopNameDone: { color: '#667085' },
  stopAddress: { color: '#667085', fontSize: 14, marginTop: 4, lineHeight: 20 },
  stopDetail: { color: '#0BA38E', fontSize: 14, fontWeight: '700', marginTop: 2 },
  stopTime: { color: '#0BA38E', fontSize: 18, fontWeight: '900' },

  actionRow: { flexDirection: 'row', gap: 9, marginTop: 14 },
  action: { flex: 1, borderRadius: 14, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', gap: 3, minHeight: 68 },
  actionNavi: { backgroundColor: '#E6F7F4', borderWidth: 1.5, borderColor: '#6ED6C1' },
  actionCall: { backgroundColor: '#FEF6E7', borderWidth: 1.5, borderColor: '#F2B84B' },
  actionDone: { backgroundColor: '#0BA38E' },
  actionOff: { opacity: 0.45 },
  actionLabel: { color: '#0D2540', fontSize: 13, fontWeight: '800' },
  actionLabelOnDark: { color: '#FFFFFF' },

  emptyCard: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E4E7EC', padding: 24, alignItems: 'center', gap: 12 },
  emptyTitle: { color: '#0D2540', fontSize: 16, fontWeight: '700', textAlign: 'center' },
  emptyBody: { color: '#667085', fontSize: 13.5, textAlign: 'center', lineHeight: 20 },

  bigButton: { backgroundColor: '#0D2540', borderRadius: 12, paddingHorizontal: 28, paddingVertical: 15 },
  bigButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
  linkButton: { paddingVertical: 12, marginTop: 6 },
  linkText: { color: '#667085', fontSize: 14, fontWeight: '700', textDecorationLine: 'underline' },
});
