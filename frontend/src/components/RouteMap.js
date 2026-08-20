import React, { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { API_URL } from '../api';

// 네이티브(iOS/Android) 동선 지도.
//
// 카카오맵 자바스크립트 SDK는 DOM 기반이라 React Native에서 직접 못 쓴다.
// 그래서 백엔드가 서빙하는 /map 페이지를 WebView로 연다.
// HTML 문자열을 앱에 넣지 않고 실제 URL을 여는 이유는, 카카오 JS 키가 요청 도메인을
// 검사하기 때문이다. 백엔드 주소를 Kakao Developers에 등록하면 그대로 동작한다.
export default function RouteMap({ center, vehicles, focusVehicleId }) {
  const webViewRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const payload = JSON.stringify({ center, vehicles: vehicles || [], focusVehicleId });

  // 지도 페이지가 "SDK 준비됐다"고 알려오면 그때 경로를 넘긴다.
  // 로드 완료(onLoadEnd)만 믿고 보내면 SDK가 아직이라 그려지지 않는다.
  const handleMessage = useCallback((event) => {
    try {
      const message = JSON.parse(event.nativeEvent.data);
      if (message.type === 'map-ready') {
        setLoading(false);
        webViewRef.current?.injectJavaScript(
          `window.renderRoute(${payload}); true;`,
        );
      }
    } catch (_) {
      // 지도 페이지가 보내는 다른 메시지는 무시한다.
    }
  }, [payload]);

  if (!center) return null;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{focusVehicleId ? '내 동선' : '전체 동선'}</Text>
        <Text style={styles.caption}>번호는 방문 순서 · 점선은 2회차</Text>
      </View>

      <View style={styles.body}>
        <WebView
          ref={webViewRef}
          source={{ uri: `${API_URL}/map` }}
          originWhitelist={['*']}
          onMessage={handleMessage}
          javaScriptEnabled
          domStorageEnabled
          // 지도를 손가락으로 확대/축소할 수 있어야 한다.
          scalesPageToFit={false}
          onError={() => setError('지도 페이지를 열지 못했습니다. 네트워크를 확인해 주세요.')}
          onHttpError={(event) => setError(
            `지도 페이지 오류 (HTTP ${event.nativeEvent.statusCode})`,
          )}
          style={styles.webview}
        />
        {loading && !error && (
          <View style={styles.overlay}>
            <ActivityIndicator color="#0F766E" />
            <Text style={styles.overlayText}>지도를 불러오는 중…</Text>
          </View>
        )}
        {!!error && (
          <View style={[styles.overlay, styles.errorOverlay]}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden', marginBottom: 16 },
  header: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 14, paddingBottom: 10 },
  title: { color: '#0F172A', fontSize: 16, fontWeight: '900' },
  caption: { color: '#64748B', fontSize: 11, flexShrink: 1, textAlign: 'right' },
  body: { width: '100%', height: 380, backgroundColor: '#E2E8F0' },
  webview: { flex: 1, backgroundColor: '#E2E8F0' },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F1F5F9', gap: 10 },
  overlayText: { color: '#475569', fontSize: 13, fontWeight: '700' },
  errorOverlay: { backgroundColor: '#FEF2F2' },
  errorText: { color: '#B91C1C', fontSize: 13, fontWeight: '700', textAlign: 'center', paddingHorizontal: 20 },
});
