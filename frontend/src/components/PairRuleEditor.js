import React, { useMemo, useState } from 'react';
import Text from '../ui/Text';
import { Pressable, StyleSheet, View } from 'react-native';

// 동승 규칙 편집기.
// forbidden = 같은 차·같은 회차에 함께 태우면 안 되는 조합 (기피)
// required  = 반드시 같은 차·같은 회차에 태워야 하는 조합 (짝꿍)
const RULE_KINDS = [
  { key: 'forbidden', label: '동승 불가', hint: '두 분을 서로 다른 운행으로 갈라 배차합니다.' },
  { key: 'required', label: '필수 동승', hint: '두 분을 같은 차 같은 회차에 함께 배차합니다.' },
];

const pairKey = (a, b) => [a, b].sort().join('|');

export default function PairRuleEditor({ passengers, rules, onChange }) {
  const [kind, setKind] = useState('forbidden');
  const [picked, setPicked] = useState([]);

  // 규칙은 출석한, 이름이 있는 어르신끼리만 만들 수 있다.
  // 결석자를 가리키는 규칙은 백엔드가 422로 거절한다.
  const selectable = useMemo(
    () => passengers.filter((item) => item.attending !== false && item.name.trim()),
    [passengers],
  );

  const nameOf = useMemo(() => {
    const map = {};
    passengers.forEach((item) => { map[item.id] = item.name.trim() || '이름 없음'; });
    return map;
  }, [passengers]);

  const toggle = (id) => {
    setPicked((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      // 규칙은 항상 두 명 단위다. 세 번째를 고르면 먼저 고른 쪽을 밀어낸다.
      return current.length < 2 ? [...current, id] : [current[1], id];
    });
  };

  const addRule = () => {
    if (picked.length !== 2) return;
    const next = { kind, passengerIds: picked };
    const exists = rules.some(
      (rule) => rule.kind === kind && pairKey(...rule.passengerIds) === pairKey(...picked),
    );
    if (!exists) onChange([...rules, next]);
    setPicked([]);
  };

  const removeRule = (index) => onChange(rules.filter((_, itemIndex) => itemIndex !== index));

  // 명단에서 빠졌거나 결석 처리된 사람을 가리키는 규칙은 눈에 띄게 표시한다.
  const isStale = (rule) => rule.passengerIds.some(
    (id) => !selectable.some((item) => item.id === id),
  );

  if (selectable.length < 2) {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>동승 규칙</Text>
        <Text style={styles.empty}>
          출석한 어르신이 두 분 이상이면 기피·짝꿍 규칙을 지정할 수 있습니다.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>동승 규칙</Text>
      <Text style={styles.caption}>{RULE_KINDS.find((item) => item.key === kind).hint}</Text>

      <View style={styles.kindRow}>
        {RULE_KINDS.map((item) => (
          <Pressable
            key={item.key}
            style={[styles.kindTab, kind === item.key && styles.kindTabActive]}
            onPress={() => setKind(item.key)}
          >
            <Text style={[styles.kindText, kind === item.key && styles.kindTextActive]}>
              {item.label}
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.pickLabel}>어르신 두 분을 선택하세요 ({picked.length}/2)</Text>
      <View style={styles.chipWrap}>
        {selectable.map((item) => {
          const isPicked = picked.includes(item.id);
          return (
            <Pressable
              key={item.id}
              style={[styles.chip, isPicked && styles.chipPicked]}
              onPress={() => toggle(item.id)}
            >
              <Text style={[styles.chipText, isPicked && styles.chipTextPicked]}>
                {item.name.trim()}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        style={[styles.addButton, picked.length !== 2 && styles.addButtonOff]}
        onPress={addRule}
        disabled={picked.length !== 2}
      >
        <Text style={styles.addButtonText}>＋ 규칙 추가</Text>
      </Pressable>

      {rules.length > 0 && (
        <View style={styles.ruleList}>
          {rules.map((rule, index) => {
            const stale = isStale(rule);
            return (
              <View key={`${rule.kind}-${pairKey(...rule.passengerIds)}`} style={styles.ruleRow}>
                <Text style={[styles.ruleText, stale && styles.ruleTextStale]}>
                  {rule.kind === 'forbidden' ? '갈라서' : '함께'}{' · '}
                  {nameOf[rule.passengerIds[0]] || '삭제된 어르신'}
                  {' · '}
                  {nameOf[rule.passengerIds[1]] || '삭제된 어르신'}
                  {stale ? ' (결석·삭제됨)' : ''}
                </Text>
                <Pressable onPress={() => removeRule(index)} hitSlop={8}>
                  <Text style={styles.ruleRemove}>삭제</Text>
                </Pressable>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: '#E4E7EC' },
  title: { color: '#0D2540', fontSize: 16, fontWeight: '900' },
  caption: { color: '#667085', fontSize: 12, marginTop: 3, marginBottom: 12 },
  empty: { color: '#98A2B3', fontSize: 12.5, marginTop: 8, lineHeight: 19 },
  kindRow: { flexDirection: 'row', backgroundColor: '#F2F4F7', borderRadius: 12, padding: 4, marginBottom: 14 },
  kindTab: { flex: 1, paddingVertical: 9, alignItems: 'center', borderRadius: 9 },
  kindTabActive: { backgroundColor: '#FFFFFF' },
  kindText: { color: '#667085', fontSize: 13, fontWeight: '800' },
  kindTextActive: { color: '#0BA38E' },
  pickLabel: { color: '#667085', fontWeight: '700', fontSize: 13, marginBottom: 8 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginBottom: 12 },
  chip: { backgroundColor: '#F8F9FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 999, paddingHorizontal: 13, paddingVertical: 8 },
  chipPicked: { backgroundColor: '#0BA38E', borderColor: '#0BA38E' },
  chipText: { color: '#0D2540', fontSize: 13, fontWeight: '700' },
  chipTextPicked: { color: '#FFFFFF' },
  addButton: { borderWidth: 1.5, borderStyle: 'dashed', borderColor: '#0BA38E', borderRadius: 12, paddingVertical: 11, alignItems: 'center' },
  addButtonOff: { borderColor: '#E4E7EC', opacity: 0.5 },
  addButtonText: { color: '#0BA38E', fontWeight: '800', fontSize: 13 },
  ruleList: { marginTop: 14, borderTopWidth: 1, borderColor: '#E4E7EC', paddingTop: 12, gap: 8 },
  ruleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#F8F9FB', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  ruleText: { color: '#0D2540', fontSize: 13, fontWeight: '700', flexShrink: 1 },
  ruleTextStale: { color: '#8A6100' },
  ruleRemove: { color: '#D64545', fontWeight: '700', fontSize: 12, marginLeft: 10 },
});
