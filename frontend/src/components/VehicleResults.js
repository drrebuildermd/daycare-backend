import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import Accordion from './Accordion';
import RouteMap from './RouteMap';
import { originForStop, startNavigation } from '../navigation';

function formatCompletionTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

const tripLabel = (vehicle, trip) => {
  const base = `${vehicle.vehicle_type} (${trip.round}회차)`;
  return vehicle.driver_name ? `${base} - ${vehicle.driver_name} 선생님` : base;
};

const Trip = ({ trip, vehicle, center, completedStops, savingStops, onComplete }) => (
  <View style={[styles.trip, !trip.used && styles.unusedTrip]}>
    <Text style={[styles.tripLabel, !trip.used && styles.mutedText]}>{tripLabel(vehicle, trip)}</Text>
    <View style={styles.tripHeading}>
      <View style={[styles.roundBadge, !trip.used && styles.mutedBadge]}>
        <Text style={[styles.roundText, !trip.used && styles.mutedText]}>{trip.round}차</Text>
      </View>
      {trip.used ? (
        <>
          <Text style={styles.tripMeta}>{trip.passenger_count}/{trip.capacity}명</Text>
          <Text style={styles.tripMeta}>{trip.departure_time} 출발 · {trip.return_time} 복귀</Text>
        </>
      ) : <Text style={styles.emptyText}>운행 없음</Text>}
    </View>

    {trip.stops.map((stop, stopIndex) => {
      const completionKey = stop.passenger_id;
      const completedAt = completedStops[completionKey];
      const isSaving = Boolean(savingStops[completionKey]);
      return (
      <View key={stop.passenger_id} style={[styles.stopCard, completedAt && styles.completedCard]}>
        <View style={[styles.sequence, completedAt && styles.completedSequence]}><Text style={styles.sequenceText}>{stop.sequence}</Text></View>
        <View style={styles.stopBody}>
          <View style={styles.nameRow}>
            <Text style={[styles.stopName, completedAt && styles.completedText]}>{stop.name}</Text>
            {stop.wheelchair && <Text style={styles.wheelchair}>♿ 휠체어</Text>}
            <Text style={[styles.eta, completedAt && styles.completedText]}>{stop.estimated_pickup}</Text>
          </View>
          <Text style={[styles.address, completedAt && styles.completedText]}>{stop.address}</Text>
          {!!stop.detail_address && (
            <Text style={[styles.detailAddress, completedAt && styles.completedText]}>🏠 {stop.detail_address}</Text>
          )}
          <Text style={styles.window}>요청 {stop.requested_window}</Text>
          {completedAt && <Text style={styles.completedAt}>✅ 탑승 완료 · {formatCompletionTime(completedAt)}</Text>}
        </View>
        <View style={styles.actionColumn}>
          <Pressable
            style={[styles.singleNaviButton, completedAt && styles.disabledAction]}
            onPress={() => startNavigation(
              stop, originForStop({ vehicle, trip, stopIndex, center }),
            )}
            disabled={Boolean(completedAt)}
          >
            <Text style={styles.singleNaviText}>🚀 내비</Text>
          </Pressable>
          <Pressable
            style={[styles.completeButton, (completedAt || isSaving) && styles.completedButton]}
            onPress={() => onComplete({ stop, tripRound: trip.round, vehicle })}
            disabled={Boolean(completedAt) || isSaving}
          >
            <Text style={[styles.completeButtonText, completedAt && styles.completedButtonText]}>
              {completedAt ? '완료됨' : isSaving ? '저장 중…' : '✅ 탑승 완료'}
            </Text>
          </Pressable>
        </View>
      </View>
    );})}

    {trip.used && (
      <>
        <View style={styles.tripFooter}>
          <Text style={styles.distance}>왕복 예상 {(trip.distance_km || 0).toFixed(1)} km</Text>
        </View>
      </>
    )}
  </View>
);

function formatAckTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

export default function VehicleResults({
  result, completedStops, savingStops, onComplete, focusVehicleId, acks = [],
  vehicles = [],
}) {
  // 배차 결과는 계산한 순간에 박제된다. 그 뒤에 차량 정보를 고쳐도 반영되지 않고,
  // start_type 이 없던 시절에 계산된 배차에는 이 값이 아예 들어 있지 않다.
  // 그래서 배지는 살아 있는 차량 등록부를 먼저 본다.
  const registry = useMemo(
    () => new Map((vehicles || []).map((item) => [item.id, item])),
    [vehicles],
  );
  // 기사님이 알림으로 들어온 경우 본인 차량만 보여준다.
  const shownVehicles = (result.vehicles || []).filter(
    (vehicle) => !focusVehicleId || vehicle.vehicle_id === focusVehicleId,
  );
  return (
    <View>
      <View style={styles.summary}>
        <Text style={styles.summaryEyebrow}>배차 완료</Text>
        <Text style={styles.summaryTitle}>{result.total_passengers || 0}명 · 총 {(result.total_distance_km || 0).toFixed(1)} km</Text>
        <Text style={styles.summaryCaption}>연산 {(result.solve_seconds || 0).toFixed(2)}초</Text>
      </View>

      <View style={styles.splitRow}>
        <View style={styles.mapPane}>
          <RouteMap
            center={result.center}
            vehicles={result.vehicles || []}
            focusVehicleId={focusVehicleId}
          />
        </View>

        <View style={styles.listPane}>
      {shownVehicles.map((vehicle) => {
        const ack = acks.find((item) => item.vehicle_id === vehicle.vehicle_id);
        const registered = registry.get(vehicle.vehicle_id);
        const isSelfDrive = registered
          ? registered.startType === 'custom'
          : vehicle.start_type === 'custom';
        const startAddress = registered
          ? (registered.startAddress || '').trim()
          : (vehicle.start_address || '');
        const total = (vehicle.trips || [])
          .filter((trip) => trip.used)
          .reduce((sum, trip) => sum + trip.stops.length, 0);

        // 접힌 줄만 봐도 누가 몇 명을 태우는지, 배차표를 봤는지 알 수 있어야 한다.
        const summary = [
          vehicle.plate_number,
          vehicle.driver_name ? `${vehicle.driver_name} 선생님` : '담당 미지정',
          `${total}명`,
        ].join(' · ');

        return (
          <Accordion
            key={vehicle.vehicle_id}
            title={vehicle.vehicle_type}
            summary={summary}
            badges={[
              isSelfDrive
                ? { label: '🏠 자차 송영', tone: 'warning' }
                : { label: '🏫 센터 차량', tone: 'success' },
              ack
                ? { label: `✅ ${formatAckTime(ack.acknowledged_at)} 확인`, tone: 'success' }
                : { label: '⏳ 확인 대기', tone: 'default' },
            ]}
          >
            {isSelfDrive && !!startAddress && (
              <Text style={styles.originAddress}>🏠 1회차 출발: {startAddress}</Text>
            )}
            <Text style={styles.vehicleCapacity}>
              정원 {vehicle.capacity}명 · 최대 2회
            </Text>

            {vehicle.trips.map((trip) => (
              <Trip
                key={trip.round}
                trip={trip}
                vehicle={vehicle}
                center={result.center}
                completedStops={completedStops}
                savingStops={savingStops}
                onComplete={onComplete}
              />
            ))}
          </Accordion>
        );
      })}
        </View>
      </View>

      <View style={styles.noticeBox}>
        {(result.notices || []).map((notice) => <Text key={notice} style={styles.notice}>• {notice}</Text>)}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { backgroundColor: '#0F766E', borderRadius: 20, padding: 20, marginBottom: 16 },
  // flexWrap이 분할/적층을 자동으로 결정한다. 폭이 flexBasis 합보다 좁으면 줄바꿈된다.
  splitRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: 16 },
  // 지도는 스크롤에 따라붙어 리스트를 훑는 동안에도 계속 보이게 한다.
  mapPane: { flexGrow: 1.15, flexShrink: 1, flexBasis: 520, minWidth: 300, position: 'sticky', top: 16 },
  listPane: { flexGrow: 1, flexShrink: 1, flexBasis: 440, minWidth: 300 },
  summaryEyebrow: { color: '#99F6E4', fontWeight: '800', fontSize: 12, marginBottom: 5 },
  summaryTitle: { color: '#FFFFFF', fontWeight: '900', fontSize: 22 },
  summaryCaption: { color: '#CCFBF1', marginTop: 6 },
  vehicleCapacity: { color: '#64748B', marginTop: 3, fontSize: 12 },
  originAddress: { color: '#B45309', fontSize: 12, fontWeight: '700', marginTop: 4, lineHeight: 18 },
  trip: { borderTopWidth: 1, borderColor: '#E2E8F0', padding: 15 },
  tripLabel: { color: '#0F766E', fontSize: 14, fontWeight: '900', marginBottom: 10 },
  unusedTrip: { paddingVertical: 12, backgroundColor: '#FAFAFA' },
  tripHeading: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 13 },
  roundBadge: { backgroundColor: '#CCFBF1', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8 },
  mutedBadge: { backgroundColor: '#E2E8F0' },
  roundText: { color: '#0F766E', fontWeight: '900', fontSize: 12 },
  mutedText: { color: '#64748B' },
  tripMeta: { color: '#475569', fontSize: 12, fontWeight: '600' },
  emptyText: { color: '#94A3B8', fontSize: 13 },
  stopCard: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: '#E2E8F0', borderRadius: 14, padding: 11, marginBottom: 10, backgroundColor: '#FFFFFF' },
  completedCard: { backgroundColor: '#E5E7EB', borderColor: '#CBD5E1', opacity: 0.78 },
  sequence: { width: 25, height: 25, borderRadius: 13, backgroundColor: '#0EA5E9', alignItems: 'center', justifyContent: 'center', zIndex: 1 },
  completedSequence: { backgroundColor: '#64748B' },
  sequenceText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  stopBody: { flex: 1, paddingHorizontal: 9 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  stopName: { color: '#0F172A', fontWeight: '800', fontSize: 15 },
  wheelchair: { color: '#7C3AED', fontSize: 10, fontWeight: '800', marginLeft: 6, backgroundColor: '#EDE9FE', paddingHorizontal: 5, paddingVertical: 2, borderRadius: 5 },
  eta: { marginLeft: 'auto', color: '#0284C7', fontWeight: '900', fontSize: 16 },
  address: { color: '#64748B', fontSize: 12, marginTop: 4 },
  detailAddress: { color: '#0F766E', fontSize: 13, fontWeight: '700', marginTop: 2 },
  window: { color: '#94A3B8', fontSize: 11, marginTop: 3 },
  completedText: { color: '#64748B', textDecorationLine: 'line-through' },
  completedAt: { color: '#166534', fontSize: 11, fontWeight: '800', marginTop: 5 },
  actionColumn: { width: 89, gap: 7 },
  singleNaviButton: { backgroundColor: '#FEE500', borderRadius: 9, paddingVertical: 9, alignItems: 'center' },
  singleNaviText: { color: '#191919', fontSize: 12, fontWeight: '900' },
  completeButton: { backgroundColor: '#0F766E', borderRadius: 9, paddingVertical: 9, alignItems: 'center' },
  completeButtonText: { color: '#FFFFFF', fontSize: 10, fontWeight: '900' },
  completedButton: { backgroundColor: '#CBD5E1' },
  completedButtonText: { color: '#475569' },
  disabledAction: { opacity: 0.4 },
  tripFooter: { alignItems: 'flex-end', marginBottom: 9 },
  distance: { color: '#64748B', fontSize: 12, fontWeight: '700' },
  noticeBox: { backgroundColor: '#FFF7ED', borderRadius: 14, padding: 14, marginBottom: 24 },
  notice: { color: '#9A3412', fontSize: 12, lineHeight: 18, marginBottom: 4 },
});
