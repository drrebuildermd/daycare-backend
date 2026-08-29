import React, { useState } from 'react';
import Text from '../ui/Text';
import { Pressable, StyleSheet, View } from 'react-native';

/**
 * 접기/펼치기 카드.
 *
 * 기본은 접힌 상태다. 차량과 어르신이 수십 명이 되면 전부 펼쳐진 화면은
 * 훑어볼 수가 없다. 접힌 줄만 봐도 무엇이 저장돼 있는지 알 수 있어야 한다.
 *
 * summary  : 접혔을 때 보이는 한 줄 (예: "[스타리아] 12가3456 (담당: 홍길동)")
 * badge    : 요약 오른쪽의 짧은 상태 표시 (예: "출석", "연락처 없음")
 * tone     : 'default' | 'muted' | 'warning' — 접힌 줄의 색을 바꾼다
 */
export default function Accordion({
  index,
  title,
  summary,
  badge,
  badgeTone = 'default',
  // 배지를 여러 개 달아야 할 때. [{ label, tone }] 형태.
  badges,
  tone = 'default',
  onRemove,
  children,
  defaultOpen = false,
}) {
  const [open, setOpen] = useState(defaultOpen);

  // 예전에는 badge 하나만 받았다. 둘 다 받아준다.
  const shownBadges = (badges && badges.length)
    ? badges
    : (badge ? [{ label: badge, tone: badgeTone }] : []);

  return (
    <View style={[styles.card, tone === 'muted' && styles.cardMuted]}>
      <Pressable
        style={styles.header}
        onPress={() => setOpen((current) => !current)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
      >
        <View style={styles.headerRow}>
          {typeof index === 'number' && (
            <View style={[styles.numberBadge, tone === 'muted' && styles.numberBadgeMuted]}>
              <Text style={styles.number}>{index + 1}</Text>
            </View>
          )}

          <View style={styles.headerText}>
            <Text
              style={[styles.title, tone === 'muted' && styles.titleMuted]}
              numberOfLines={1}
            >
              {title}
            </Text>
            {!!summary && (
              <Text style={styles.summary} numberOfLines={1}>{summary}</Text>
            )}
          </View>

          {/* 펼침 방향을 화살표로 알린다. 접힌 카드가 눌리는 것인지 모르면 아무도 안 누른다. */}
          <Text style={styles.chevron}>{open ? '▲' : '▼'}</Text>
        </View>

        {/* 배지는 아랫줄에 둔다. 윗줄에 같이 두면 배지가 늘어날 때마다
            차량번호와 기사님 이름이 잘려나간다. */}
        {shownBadges.length > 0 && (
          <View style={styles.badgeRow}>
            {shownBadges.map((item) => (
              <View
                key={item.label}
                style={[styles.badge, styles[`badge_${item.tone || 'default'}`]]}
              >
                <Text style={[styles.badgeText, styles[`badgeText_${item.tone || 'default'}`]]}>
                  {item.label}
                </Text>
              </View>
            ))}
          </View>
        )}
      </Pressable>

      {open && (
        <View style={styles.body}>
          {children}
          {!!onRemove && (
            <Pressable style={styles.removeButton} onPress={onRemove}>
              <Text style={styles.removeText}>삭제</Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 16, marginBottom: 10, borderWidth: 1, borderColor: '#E4E7EC', overflow: 'hidden' },
  cardMuted: { backgroundColor: '#F8F9FB', borderColor: '#E4E7EC' },
  header: { paddingHorizontal: 14, paddingVertical: 13 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 9 },
  numberBadge: { width: 26, height: 26, borderRadius: 9, backgroundColor: '#E6F7F4', alignItems: 'center', justifyContent: 'center' },
  numberBadgeMuted: { backgroundColor: '#E4E7EC' },
  number: { color: '#07705F', fontWeight: '800', fontSize: 12 },
  headerText: { flex: 1, minWidth: 0 },
  title: { color: '#0D2540', fontSize: 15, fontWeight: '800' },
  titleMuted: { color: '#98A2B3', textDecorationLine: 'line-through' },
  summary: { color: '#667085', fontSize: 12, marginTop: 2 },
  badge: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4 },
  badge_default: { backgroundColor: '#F2F4F7' },
  badge_success: { backgroundColor: '#E9F7EF' },
  badge_warning: { backgroundColor: '#FEF6E7' },
  badgeText: { fontSize: 11, fontWeight: '800' },
  badgeText_default: { color: '#667085' },
  badgeText_success: { color: '#237B4B' },
  badgeText_warning: { color: '#8A6100' },
  chevron: { color: '#98A2B3', fontSize: 11, fontWeight: '900' },
  body: { paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderColor: '#F2F4F7', paddingTop: 14 },
  removeButton: { alignSelf: 'flex-end', paddingHorizontal: 12, paddingVertical: 7 },
  removeText: { color: '#D64545', fontWeight: '700', fontSize: 13 },
});
