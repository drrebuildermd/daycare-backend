import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

// 네이티브(iOS/Android) 대체 화면.
// 카카오맵 자바스크립트 SDK는 DOM 기반이라 웹에서만 동작한다. Metro가 웹에서는
// RouteMap.web.js를, 네이티브에서는 이 파일을 자동으로 고른다.
export default function RouteMap({ center }) {
  if (!center) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.title}>🗺️ 동선 지도는 웹 관제 화면에서 보실 수 있습니다</Text>
      <Text style={styles.body}>
        네이티브 앱에서는 각 정류장의 [🚀 내비] 버튼으로 카카오내비를 실행해 주세요.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E2E8F0', padding: 18, marginBottom: 16 },
  title: { color: '#0F172A', fontSize: 14, fontWeight: '900', marginBottom: 6 },
  body: { color: '#64748B', fontSize: 12.5, lineHeight: 19 },
});
