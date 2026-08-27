import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, BackHandler, Linking, Pressable, ScrollView,
  StyleSheet, Text, View,
} from 'react-native';

import { fetchCompletedStopMap, fetchTodayDispatch, saveRideCompletion } from '../api';
import { startNavigation } from '../navigation';
import Accordion from '../components/Accordion';
import RouteMap from '../components/RouteMap';

// 관제 화면과 같은 주기로 맞춘다. 다른 기사님이 태운 어르신이 내 화면에도 반영된다.
const POLL_MS = 20000;

/**
 * 기사님 전용 화면.
 *
 * 현장에서 운전 중에 쓰는 화면이다. 탭도 설정도 없다.
 * 차량을 한 번 고르면 그 뒤로는 명단 / 내비 / 전화 / 완료 네 가지만 보인다.
 */
export default function DriverScreen({ onExit }) {
  const [dispatch, setDispatch] = useState(null);
  const [vehicleId, setVehicleId] = useState(null);
  const [completed, setCompleted] = useState({});
  const [saving, setSaving] = useState({});
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
      const [today, done] = await Promise.all([
        fetchTodayDispatch(),
        fetchCompletedStopMap().catch(() => ({})),
      ]);
      setDispatch(today.result || null);
      setCompleted(done);
      setPhase('ready');
    } catch (error) {
      setErrorMessage(error.message);
      setPhase('error');
    } finally {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
  }, []);

  useEffect(() => {
    load();
    return () => clearInterval(tickerRef.current);
  }, [load]);

  // 차량을 고른 뒤에만 주기 갱신한다.
  useEffect(() => {
    if (phase !== 'ready' || !vehicleId) return undefined;
    const timer = setInterval(() => {
      fetchCompletedStopMap().then(setCompleted).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [phase, vehicleId]);

  const vehicle = (dispatch?.vehicles || []).find((v) => v.vehicle_id === vehicleId);

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

  const completeStop = async (stop, tripRound) => {
    setSaving((current) => ({ ...current, [stop.passenger_id]: true }));
    try {
      const record = await saveRideCompletion({
        passenger_id: stop.passenger_id,
        passenger_name: stop.name,
        vehicle_id: vehicle.vehicle_id,
        vehicle_type: vehicle.vehicle_type,
        vehicle_plate_number: vehicle.plate_number,
        trip_round: tripRound,
        scheduled_pickup: stop.estimated_pickup,
        center_name: dispatch?.center?.name || '',
        guardian_phone: stop.guardian_phone || '',
      });
      setCompleted((current) => ({ ...current, [stop.passenger_id]: record.completed_at }));
      if (record.sms_sent === false) {
        Alert.alert(
          '탑승 완료 (문자 미발송)',
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

  const openNavigation = (stop) => startNavigation(stop);

  const callGuardian = async (stop) => {
    const digits = (stop.guardian_phone || '').replace(/[^0-9]/g, '');
    if (digits.length < 10) {
      Alert.alert('보호자 연락처 없음', `${stop.name} 어르신의 보호자 번호가 등록되어 있지 않습니다.`);
      return;
    }
    try {
      await Linking.openURL(`tel:${digits}`);
    } catch (_) {
      Alert.alert('전화 연결 실패', '이 기기에서 전화를 걸 수 없습니다.');
    }
  };

  // --- 로딩 / 오류 ---
  if (phase === 'loading') {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#0F766E" />
        <Text style={styles.centerTitle}>오늘 배차를 불러오는 중입니다…</Text>
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
          <Pressable onPress={onExit} hitSlop={12} style={styles.topActionButton}>
            <Text style={styles.topAction}>모드 변경</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.pickBody}>
          <Text style={styles.pickHeading}>운행하실 차량을 선택하세요</Text>
          {vehicles.length === 0 ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>오늘 배차가 아직 없습니다</Text>
              <Text style={styles.emptyBody}>
                관리자가 배차를 전송하면 여기에 차량이 나타납니다.
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
                {!!item.start_address && item.start_name !== '센터' && (
                  <Text style={styles.vehiclePickStart}>
                    🏠 1회차 출발: {item.start_address}
                  </Text>
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
            {doneCount}/{totalStops}명 탑승 완료
            {vehicle.driver_name ? ` · ${vehicle.driver_name} 선생님` : ''}
          </Text>
        </View>
        <Pressable onPress={() => setVehicleId(null)} hitSlop={12} style={styles.topActionButton}>
          <Text style={styles.topAction}>차량 변경</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.listBody}>
        <Accordion
          title="🗺️ 오늘 내 동선 지도"
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

            {trip.stops.map((stop) => {
              const doneAt = completed[stop.passenger_id];
              const isSaving = Boolean(saving[stop.passenger_id]);
              const hasPhone = (stop.guardian_phone || '').replace(/[^0-9]/g, '').length >= 10;

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
                      <Text style={[styles.stopName, doneAt && styles.stopNameDone]}>
                        {stop.name}
                        {stop.wheelchair ? '  ♿' : ''}
                      </Text>
                      <Text style={styles.stopAddress}>{stop.address}</Text>
                      {!!stop.detail_address && (
                        <Text style={styles.stopDetail}>🏠 {stop.detail_address}</Text>
                      )}
                    </View>
                    <Text style={styles.stopTime}>{stop.estimated_pickup}</Text>
                  </View>

                  <View style={styles.actionRow}>
                    <Pressable style={[styles.action, styles.actionNavi]} onPress={() => openNavigation(stop)}>
                      <Text style={styles.actionIcon}>🧭</Text>
                      <Text style={styles.actionLabel}>내비</Text>
                    </Pressable>

                    <Pressable
                      style={[styles.action, styles.actionCall, !hasPhone && styles.actionOff]}
                      onPress={() => callGuardian(stop)}
                    >
                      <Text style={styles.actionIcon}>📞</Text>
                      <Text style={styles.actionLabel}>{hasPhone ? '보호자' : '번호없음'}</Text>
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
                          <Text style={styles.actionIcon}>{doneAt ? '✅' : '🚌'}</Text>
                          <Text style={[styles.actionLabel, styles.actionLabelOnDark]}>
                            {doneAt ? '완료됨' : '탑승 완료'}
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
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, backgroundColor: '#F1F5F9', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 32, gap: 14 },
  centerTitle: { color: '#0F172A', fontSize: 17, fontWeight: '800', textAlign: 'center' },
  centerHint: { color: '#64748B', fontSize: 13.5, textAlign: 'center', lineHeight: 21 },
  elapsed: { color: '#0F766E', fontSize: 15, fontWeight: '900' },
  errorText: { color: '#B91C1C', fontSize: 15, fontWeight: '700', textAlign: 'center', lineHeight: 22 },

  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingHorizontal: 18, paddingTop: 16, paddingBottom: 14, backgroundColor: '#0F766E' },
  topActionButton: { backgroundColor: 'rgba(255,255,255,0.18)', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 },
  topTitle: { color: '#FFFFFF', fontSize: 20, fontWeight: '900' },
  topSub: { color: '#A7F3D0', fontSize: 13, fontWeight: '700', marginTop: 3 },
  topAction: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },

  pickBody: { padding: 18, gap: 12 },
  pickHeading: { color: '#0F172A', fontSize: 18, fontWeight: '900', marginBottom: 4 },
  vehiclePick: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 2, borderColor: '#0F766E', padding: 22 },
  vehiclePickName: { color: '#0F172A', fontSize: 24, fontWeight: '900' },
  vehiclePickPlate: { color: '#0F766E', fontSize: 17, fontWeight: '800', marginTop: 2 },
  vehiclePickMeta: { color: '#64748B', fontSize: 14, marginTop: 8 },
  vehiclePickStart: { color: '#B45309', fontSize: 13, fontWeight: '700', marginTop: 6, lineHeight: 19 },

  listBody: { padding: 14, paddingBottom: 40 },
  roundHeader: { flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 8, marginBottom: 10, paddingHorizontal: 4 },
  roundText: { color: '#0F172A', fontSize: 18, fontWeight: '900' },
  roundMeta: { color: '#64748B', fontSize: 13, fontWeight: '700' },

  stopCard: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E2E8F0', padding: 16, marginBottom: 12 },
  stopCardDone: { backgroundColor: '#F8FAFC', borderColor: '#A7F3D0' },
  stopHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  seq: { width: 40, height: 40, borderRadius: 14, backgroundColor: '#0F766E', alignItems: 'center', justifyContent: 'center' },
  seqDone: { backgroundColor: '#10B981' },
  seqText: { color: '#FFFFFF', fontSize: 19, fontWeight: '900' },
  stopName: { color: '#0F172A', fontSize: 22, fontWeight: '900' },
  stopNameDone: { color: '#64748B' },
  stopAddress: { color: '#475569', fontSize: 14, marginTop: 4, lineHeight: 20 },
  stopDetail: { color: '#0F766E', fontSize: 14, fontWeight: '700', marginTop: 2 },
  stopTime: { color: '#0F766E', fontSize: 18, fontWeight: '900' },

  actionRow: { flexDirection: 'row', gap: 9, marginTop: 14 },
  action: { flex: 1, borderRadius: 14, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', gap: 3, minHeight: 68 },
  actionNavi: { backgroundColor: '#EFF6FF', borderWidth: 1.5, borderColor: '#93C5FD' },
  actionCall: { backgroundColor: '#FEF3C7', borderWidth: 1.5, borderColor: '#FCD34D' },
  actionDone: { backgroundColor: '#0F766E' },
  actionOff: { opacity: 0.45 },
  actionIcon: { fontSize: 22 },
  actionLabel: { color: '#0F172A', fontSize: 13, fontWeight: '800' },
  actionLabelOnDark: { color: '#FFFFFF' },

  emptyCard: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E2E8F0', padding: 24, alignItems: 'center', gap: 12 },
  emptyTitle: { color: '#0F172A', fontSize: 16, fontWeight: '800', textAlign: 'center' },
  emptyBody: { color: '#64748B', fontSize: 13.5, textAlign: 'center', lineHeight: 20 },

  bigButton: { backgroundColor: '#0F766E', borderRadius: 15, paddingHorizontal: 28, paddingVertical: 15 },
  bigButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
  linkButton: { paddingVertical: 12 },
  linkText: { color: '#64748B', fontSize: 14, fontWeight: '700', textDecorationLine: 'underline' },
});
