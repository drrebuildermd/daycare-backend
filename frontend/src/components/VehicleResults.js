import React, { useMemo } from 'react';
import Text from '../ui/Text';
import Icon from '../ui/Icon';
import { color } from '../theme';
import { Pressable, StyleSheet, View } from 'react-native';

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
            {stop.wheelchair && <Icon name="wheelchair" size={15} tint={color.textSecondary} />}
            <Text style={[styles.eta, completedAt && styles.completedText]}>{stop.estimated_pickup}</Text>
          </View>
          <Text style={[styles.address, completedAt && styles.completedText]}>{stop.address}</Text>
          {!!stop.detail_address && (
            <Text style={[styles.detailAddress, completedAt && styles.completedText]}>{stop.detail_address}</Text>
          )}
          <Text style={styles.window}>요청 {stop.requested_window}</Text>
          {completedAt && <Text style={styles.completedAt}>탑승 완료 · {formatCompletionTime(completedAt)}</Text>}
        </View>
        <View style={styles.actionColumn}>
          <Pressable
            style={[styles.singleNaviButton, completedAt && styles.disabledAction]}
            onPress={() => startNavigation(
              stop, originForStop({ vehicle, trip, stopIndex, center }),
            )}
            disabled={Boolean(completedAt)}
          >
            <Icon name="navigate" size={14} tint="#FFFFFF" />
            <Text style={styles.singleNaviText}>내비</Text>
          </Pressable>
          <Pressable
            style={[styles.completeButton, (completedAt || isSaving) && styles.completedButton]}
            onPress={() => onComplete({ stop, tripRound: trip.round, vehicle })}
            disabled={Boolean(completedAt) || isSaving}
          >
            <Text style={[styles.completeButtonText, completedAt && styles.completedButtonText]}>
              {completedAt ? '완료됨' : isSaving ? '저장 중…' : '탑승 완료'}
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
                ? { label: '자차 송영', icon: 'home', tone: 'warning' }
                : { label: '센터 차량', icon: 'center', tone: 'success' },
              ack
                ? { label: `${formatAckTime(ack.acknowledged_at)} 확인`, icon: 'done', tone: 'success' }
                : { label: '확인 대기', icon: 'waiting', tone: 'default' },
            ]}
          >
            {/* 어디서 떠나 어디서 끝나는지는 회차마다 다르다.
                등원 자차는 자택에서 떠나고, 하원 자차는 자택에서 끝난다.
                차량 등록 정보로 짐작하지 말고 회차가 말하는 것을 그대로 적는다. */}
            {(vehicle.trips || []).filter((trip) => trip.used).map((trip) => (
              <Text key={trip.round} style={styles.originAddress}>
                {trip.round}회차 · {trip.origin_name || '센터'} 출발 →{' '}
                {trip.destination_name || '센터'} 도착
              </Text>
            ))}
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
  summary: { backgroundColor: '#FFFFFF', borderRadius: 12, borderWidth: 1, borderColor: '#E4E7EC',
    borderLeftWidth: 4, borderLeftColor: '#0BA38E', padding: 18, marginBottom: 16 },
  // flexWrap이 분할/적층을 자동으로 결정한다. 폭이 flexBasis 합보다 좁으면 줄바꿈된다.
  splitRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: 16 },
  // 지도는 스크롤에 따라붙어 리스트를 훑는 동안에도 계속 보이게 한다.
  mapPane: { flexGrow: 1.15, flexShrink: 1, flexBasis: 520, minWidth: 300, position: 'sticky', top: 16 },
  listPane: { flexGrow: 1, flexShrink: 1, flexBasis: 440, minWidth: 300 },
  summaryEyebrow: { color: '#07705F', fontWeight: '700', fontSize: 12, marginBottom: 5 },
  summaryTitle: { color: '#0D2540', fontWeight: '700', fontSize: 22 },
  summaryCaption: { color: '#667085', fontSize: 13, marginTop: 6 },
  vehicleCapacity: { color: '#667085', marginTop: 3, fontSize: 12 },
  originAddress: { color: '#8A6100', fontSize: 12, fontWeight: '700', marginTop: 4, lineHeight: 18 },
  trip: { borderTopWidth: 1, borderColor: '#E4E7EC', padding: 15 },
  tripLabel: { color: '#0BA38E', fontSize: 14, fontWeight: '900', marginBottom: 10 },
  unusedTrip: { paddingVertical: 12, backgroundColor: '#F8F9FB' },
  tripHeading: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 13 },
  roundBadge: { backgroundColor: '#E9F7EF', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8 },
  mutedBadge: { backgroundColor: '#E4E7EC' },
  roundText: { color: '#0BA38E', fontWeight: '900', fontSize: 12 },
  mutedText: { color: '#667085' },
  tripMeta: { color: '#667085', fontSize: 12, fontWeight: '600' },
  emptyText: { color: '#98A2B3', fontSize: 13 },
  stopCard: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 14, padding: 11, marginBottom: 10, backgroundColor: '#FFFFFF' },
  completedCard: { backgroundColor: '#E4E7EC', borderColor: '#E4E7EC', opacity: 0.78 },
  sequence: { width: 25, height: 25, borderRadius: 13, backgroundColor: '#0BA38E', alignItems: 'center', justifyContent: 'center', zIndex: 1 },
  completedSequence: { backgroundColor: '#667085' },
  sequenceText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  stopBody: { flex: 1, paddingHorizontal: 9 },
  nameRow: { flexDirection: 'row', alignItems: 'center' },
  stopName: { color: '#0D2540', fontWeight: '800', fontSize: 15 },
  wheelchair: { color: '#07705F', fontSize: 10, fontWeight: '800', marginLeft: 6, backgroundColor: '#E6F7F4', paddingHorizontal: 5, paddingVertical: 2, borderRadius: 5 },
  eta: { marginLeft: 'auto', color: '#0BA38E', fontWeight: '900', fontSize: 16 },
  address: { color: '#667085', fontSize: 12, marginTop: 4 },
  detailAddress: { color: '#0BA38E', fontSize: 13, fontWeight: '700', marginTop: 2 },
  window: { color: '#98A2B3', fontSize: 11, marginTop: 3 },
  completedText: { color: '#667085', textDecorationLine: 'line-through' },
  completedAt: { color: '#237B4B', fontSize: 11, fontWeight: '800', marginTop: 5 },
  actionColumn: { width: 89, gap: 7 },
  singleNaviButton: { flexDirection: 'row', gap: 5, backgroundColor: '#0BA38E', borderRadius: 8, paddingVertical: 9, alignItems: 'center', justifyContent: 'center' },
  singleNaviText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  completeButton: { backgroundColor: '#0BA38E', borderRadius: 9, paddingVertical: 9, alignItems: 'center' },
  completeButtonText: { color: '#FFFFFF', fontSize: 10, fontWeight: '900' },
  completedButton: { backgroundColor: '#E4E7EC' },
  completedButtonText: { color: '#667085' },
  disabledAction: { opacity: 0.4 },
  tripFooter: { alignItems: 'flex-end', marginBottom: 9 },
  distance: { color: '#667085', fontSize: 12, fontWeight: '700' },
  noticeBox: { backgroundColor: '#FEF6E7', borderRadius: 14, padding: 14, marginBottom: 24 },
  notice: { color: '#8A6100', fontSize: 12, lineHeight: 18, marginBottom: 4 },
});
