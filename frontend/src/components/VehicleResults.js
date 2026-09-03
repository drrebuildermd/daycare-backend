import React, { useMemo } from 'react';
import Text from '../ui/Text';
import Icon from '../ui/Icon';
import { color } from '../theme';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

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
  // 대안 분석. 원장님이 [대안 보기] 를 눌렀을 때만 채워진다.
  advice, advising, onAskAdvice, onApplyTimeAdvice,
  considerRevenueLoss, onToggleRevenueLoss,
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
  const unassigned = result.unassigned_passengers || [];
  // 빠진 이유가 다르면 원장님이 할 일도 다르다. 리프트가 없어서 빠진 분에게
  // '시간 범위를 넓히세요' 라고 하면 아무리 넓혀도 해결되지 않는다.
  const liftBlocked = unassigned.filter((item) => item.reason === 'wheelchair');
  const capacityBlocked = unassigned.filter((item) => item.reason !== 'wheelchair');

  return (
    <View>
      {/* 물리적으로 태울 방법이 없어 빠진 분이 있으면 가장 먼저 알린다.
          결과를 그대로 전송하면 이분들은 아무 차에도 없다. */}
      {unassigned.length > 0 && (
        <View style={styles.dropCard}>
          <View style={styles.dropHead}>
            <Icon name="warning" size={18} tint="#9B2C2C" />
            <Text style={styles.dropTitle}>
              {unassigned.length}명의 배차가 누락되었습니다
            </Text>
          </View>
          {liftBlocked.length > 0 && (
            <View style={styles.dropGroup}>
              <View style={styles.dropReason}>
                <Icon name="wheelchair" size={15} tint="#9B2C2C" />
                <Text style={styles.dropReasonText}>휠체어 고정석 부족</Text>
              </View>
              <Text style={styles.dropNames}>
                {liftBlocked.map((item) => item.name).join(', ')}
              </Text>
              <Text style={styles.dropHelp}>
                차량 관리에서 휠체어 전용 좌석 수를 확인해 주세요. 리프트 차량이
                없으면 시간 범위를 넓혀도 배차되지 않습니다.
              </Text>
            </View>
          )}
          {capacityBlocked.length > 0 && (
            <View style={styles.dropGroup}>
              {liftBlocked.length > 0 && (
                <View style={styles.dropReason}>
                  <Icon name="warning" size={15} tint="#9B2C2C" />
                  <Text style={styles.dropReasonText}>정원·시간 부족</Text>
                </View>
              )}
              <Text style={styles.dropNames}>
                {capacityBlocked.map((item) => item.name).join(', ')}
              </Text>
              <Text style={styles.dropHelp}>
                해당 어르신의 시간 범위를 넓히거나, 투입 차량(또는 회차)을 추가한 뒤
                다시 계산해 보세요.
              </Text>
            </View>
          )}

          {/* 이유만 말하고 끝내면 원장님은 무엇을 해야 할지 모른다.
              시간을 조절할 일인지, 회차를 늘릴 일인지, 차를 늘릴 일인지까지
              답해 줘야 한다. 계산에 최대 6초가 걸려 눌렀을 때만 부른다. */}
          {!advice && (
            <Pressable
              style={[styles.adviceButton, advising && styles.adviceButtonBusy]}
              onPress={onAskAdvice}
              disabled={advising}
            >
              {advising ? (
                <>
                  <ActivityIndicator size="small" color="#9B2C2C" />
                  <Text style={styles.adviceButtonText}>
                    대안을 찾는 중입니다 (최대 6초)
                  </Text>
                </>
              ) : (
                <>
                  <Icon name="warning" size={15} tint="#9B2C2C" />
                  <Text style={styles.adviceButtonText}>대안 보기 (왜 안 되나요?)</Text>
                </>
              )}
            </Pressable>
          )}

          {advice && (
            <View style={styles.adviceBox}>
              {(advice.options || []).map((option, index) => (
                <View
                  key={`${option.kind}-${index}`}
                  style={[
                    styles.adviceOption,
                    option.feasible ? styles.adviceOk : styles.adviceNo,
                  ]}
                >
                  <View style={styles.adviceHead}>
                    <View
                      style={[
                        styles.adviceRank,
                        option.feasible ? styles.adviceRankOk : styles.adviceRankNo,
                      ]}
                    >
                      <Text
                        style={[
                          styles.adviceRankText,
                          option.feasible
                            ? styles.adviceRankTextOk
                            : styles.adviceRankTextNo,
                        ]}
                      >
                        {option.priority}순위
                      </Text>
                    </View>
                    <Text
                      style={[
                        styles.adviceHeadline,
                        !option.feasible && styles.adviceHeadlineNo,
                      ]}
                    >
                      {option.headline}
                    </Text>
                  </View>

                  {!!option.detail && (
                    <Text style={styles.adviceDetail}>{option.detail}</Text>
                  )}

                  {(option.actions || []).length > 0 && (
                    <View style={styles.adviceActions}>
                      {option.actions.map((action) => (
                        <View key={action.passenger_id} style={styles.adviceRow}>
                          <Text style={styles.adviceName}>{action.name}</Text>
                          <Text style={styles.adviceTime}>
                            {action.current_window} → {action.suggested_window}
                          </Text>
                          {!!action.scheduled_time && (
                            <Text style={styles.adviceEta}>
                              실제 도착 {action.scheduled_time}
                            </Text>
                          )}
                        </View>
                      ))}
                    </View>
                  )}

                  {option.feasible && option.kind === 'adjust_time' && (
                    <Pressable
                      style={styles.applyButton}
                      onPress={() => onApplyTimeAdvice(option.actions)}
                    >
                      <Text style={styles.applyButtonText}>
                        이대로 적용 ({option.actions.length}명)
                      </Text>
                    </Pressable>
                  )}
                </View>
              ))}
            </View>
          )}

              {/* 어느 쪽이 이득인가.
                  3회차가 가능하다는 것만으로는 부족하다. 그게 이득인지
                  손해인지 답해야 원장님이 결정하실 수 있다. */}
              {!!(advice && advice.financials) && (
                <View style={styles.moneyCard}>
                  <View style={styles.moneyHead}>
                    <Icon name="excel" size={16} tint={color.teal} />
                    <Text style={styles.moneyTitle}>어느 쪽이 이득인가</Text>
                  </View>

                  <Pressable style={styles.moneyToggle} onPress={onToggleRevenueLoss}>
                    <View
                      style={[
                        styles.checkbox,
                        considerRevenueLoss && styles.checkboxOn,
                      ]}
                    >
                      {considerRevenueLoss && (
                        <Icon name="done" size={12} tint="#FFFFFF" />
                      )}
                    </View>
                    <Text style={styles.moneyToggleText}>
                      조기 하원에 따른 수가 감소를 비용에 포함
                    </Text>
                  </Pressable>

                  {[advice.financials.scenario_a, advice.financials.scenario_b].map(
                    (scenario, index) => {
                      const kind = index === 0 ? 'add_round' : 'add_vehicle';
                      const picked = advice.financials.recommended === kind;
                      return (
                        <View
                          key={kind}
                          style={[styles.moneyRow, picked && styles.moneyRowPicked]}
                        >
                          <View style={styles.moneyRowHead}>
                            <Text style={styles.moneyLabel}>
                              {index === 0 ? 'A안' : 'B안'} {scenario.label}
                            </Text>
                            {picked && (
                              <View style={styles.pickBadge}>
                                <Text style={styles.pickBadgeText}>권장</Text>
                              </View>
                            )}
                          </View>
                          <Text style={styles.moneyTotal}>
                            하루 {scenario.total_won.toLocaleString()}원
                          </Text>
                          <Text style={styles.moneyBreak}>
                            {[
                              `유류비 ${scenario.fuel_won.toLocaleString()}원`,
                              scenario.fixed_won
                                ? `렌트 ${scenario.fixed_won.toLocaleString()}원`
                                : null,
                              scenario.revenue_loss_won
                                ? `수가 감소 ${scenario.revenue_loss_won.toLocaleString()}원`
                                : null,
                            ].filter(Boolean).join(' · ')}
                          </Text>
                          {scenario.revenue_loss_items.map((item) => (
                            <Text key={item.passenger_id} style={styles.moneyPerson}>
                              {item.name} {item.planned_band}→{item.actual_band}
                              {'  '}−{item.lost_won.toLocaleString()}원
                            </Text>
                          ))}
                        </View>
                      );
                    },
                  )}

                  <Text style={styles.moneyHeadline}>{advice.financials.headline}</Text>
                  {(advice.financials.notes || []).map((note, index) => (
                    <Text key={index} style={styles.moneyNote}>· {note}</Text>
                  ))}
                  <Text style={styles.moneyFootnote}>
                    운전은 이미 급여가 나가는 요양보호사가 맡으므로 인건비는 세지 않았습니다.
                  </Text>
                </View>
              )}
        </View>
      )}

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
  // 놓치면 안 되는 경고다. 결과 카드보다 먼저, 더 눈에 띄게 둔다.
  moneyCard: {
    marginTop: 12, backgroundColor: '#FFFFFF', borderRadius: 12,
    borderWidth: 1, borderColor: '#B7E4DA', padding: 14,
  },
  moneyHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  moneyTitle: { fontSize: 14, fontWeight: '800', color: '#07705F' },
  moneyToggle: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 8, marginBottom: 6,
  },
  checkbox: {
    width: 18, height: 18, borderRadius: 5, borderWidth: 1.5,
    borderColor: '#B7C4C0', alignItems: 'center', justifyContent: 'center',
  },
  checkboxOn: { backgroundColor: '#07705F', borderColor: '#07705F' },
  moneyToggleText: { flex: 1, fontSize: 12, color: '#4A5D57', fontWeight: '600' },
  moneyRow: {
    borderRadius: 10, padding: 11, marginTop: 6,
    backgroundColor: '#F7F9F8', borderWidth: 1, borderColor: '#EDF1EF',
  },
  moneyRowPicked: { backgroundColor: '#E9F7EF', borderColor: '#3BB273' },
  moneyRowHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  moneyLabel: { flex: 1, fontSize: 12, fontWeight: '700', color: '#1B2B26' },
  pickBadge: {
    backgroundColor: '#07705F', borderRadius: 999,
    paddingHorizontal: 7, paddingVertical: 2,
  },
  pickBadgeText: { color: '#FFFFFF', fontSize: 10, fontWeight: '800' },
  moneyTotal: {
    fontSize: 17, fontWeight: '900', color: '#0D2540', marginTop: 3,
    fontVariant: ['tabular-nums'],
  },
  moneyBreak: { fontSize: 11, color: '#7C8D87', marginTop: 2 },
  moneyPerson: { fontSize: 11, color: '#9B2C2C', marginTop: 3 },
  moneyHeadline: {
    marginTop: 12, fontSize: 13, fontWeight: '800',
    color: '#07705F', lineHeight: 19,
  },
  moneyNote: { marginTop: 6, fontSize: 11, color: '#5A6B65', lineHeight: 17 },
  moneyFootnote: { marginTop: 8, fontSize: 10, color: '#98A2B3' },
  adviceButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginTop: 12, paddingVertical: 11, borderRadius: 10,
    borderWidth: 1, borderColor: '#D64545', backgroundColor: '#FFFFFF',
  },
  adviceButtonBusy: { opacity: 0.7 },
  adviceButtonText: { color: '#9B2C2C', fontSize: 13, fontWeight: '800' },

  adviceBox: { marginTop: 12, gap: 8 },
  adviceOption: { borderRadius: 10, padding: 12, borderWidth: 1 },
  adviceOk: { backgroundColor: '#FFFFFF', borderColor: '#3BB273' },
  adviceNo: { backgroundColor: '#FBF7F7', borderColor: '#E5D5D5' },
  adviceHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 7 },
  adviceRank: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5, marginTop: 1 },
  adviceRankOk: { backgroundColor: '#E9F7EF' },
  adviceRankNo: { backgroundColor: '#EFE8E8' },
  adviceRankText: { fontSize: 10, fontWeight: '800' },
  adviceRankTextOk: { color: '#237B4B' },
  adviceRankTextNo: { color: '#8A6A6A' },
  adviceHeadline: { flex: 1, fontSize: 13, fontWeight: '700', color: '#1B2B26', lineHeight: 19 },
  adviceHeadlineNo: { color: '#8A6A6A', fontWeight: '600' },
  adviceDetail: { marginTop: 6, fontSize: 12, color: '#5A6B65', lineHeight: 18 },
  adviceActions: { marginTop: 8, gap: 6 },
  adviceRow: {
    backgroundColor: '#F6FAF8', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7,
  },
  adviceName: { fontSize: 12, fontWeight: '700', color: '#1B2B26' },
  adviceTime: { fontSize: 12, color: '#237B4B', fontWeight: '600', marginTop: 1 },
  adviceEta: { fontSize: 11, color: '#7C8D87', marginTop: 1 },
  applyButton: {
    marginTop: 10, paddingVertical: 10, borderRadius: 9,
    backgroundColor: '#07705F', alignItems: 'center',
  },
  applyButtonText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
  dropGroup: { marginTop: 8 },
  dropReason: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 2 },
  dropReasonText: { color: '#9B2C2C', fontSize: 12, fontWeight: '800' },
  dropCard: { backgroundColor: '#FCEDED', borderWidth: 1, borderColor: '#D64545',
    borderRadius: 12, padding: 16, marginBottom: 16 },
  dropHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dropTitle: { flex: 1, minWidth: 0, color: '#9B2C2C', fontSize: 15, fontWeight: '700' },
  dropNames: { color: '#0D2540', fontSize: 14, fontWeight: '600', marginTop: 10, lineHeight: 21 },
  dropHelp: { color: '#667085', fontSize: 13, lineHeight: 20, marginTop: 8 },
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
