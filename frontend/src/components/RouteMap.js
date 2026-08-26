import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { API_URL } from '../api';

// 네이티브(iOS/Android) 동선 지도.
//
// 카카오맵 자바스크립트 SDK는 DOM 기반이라 React Native에서 직접 못 쓴다.
// 그래서 백엔드가 서빙하는 /map 페이지를 WebView로 연다.
// HTML 문자열을 앱에 넣지 않고 실제 URL을 여는 이유는, 카카오 JS 키가 요청 도메인을
// 검사하기 때문이다. 백엔드 주소를 Kakao Developers에 등록하면 그대로 동작한다.

// Render 무료 티어는 15분 무활동이면 잠들고, 깨어나는 동안 502/503을 돌려준다.
// 한 번 실패했다고 에러 화면에 고정하면 안 되고, 잠깐 기다렸다 다시 열어야 한다.
const WAKING_STATUS = [408, 425, 429, 500, 502, 503, 504];
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 3000;

export default function RouteMap({ center, vehicles, focusVehicleId }) {
  const webViewRef = useRef(null);
  const retryTimerRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState(null); // { kind: 'waking' | 'error', message }

  const payload = JSON.stringify({ center, vehicles: vehicles || [], focusVehicleId });

  // 재시도 대기 중에 화면을 벗어나면 타이머를 정리한다.
  useEffect(() => () => clearTimeout(retryTimerRef.current), []);

  // 지도 페이지가 "SDK 준비됐다"고 알려오면 그때 경로를 넘긴다.
  // 로드 완료(onLoadEnd)만 믿고 보내면 SDK가 아직이라 그려지지 않는다.
  const handleMessage = useCallback((event) => {
    try {
      const message = JSON.parse(event.nativeEvent.data);
      if (message.type === 'map-ready') {
        setLoading(false);
        setStatus(null);
        webViewRef.current?.injectJavaScript(`window.renderRoute(${payload}); true;`);
      }
    } catch (_) {
      // 지도 페이지가 보내는 다른 메시지는 무시한다.
    }
  }, [payload]);

  const scheduleRetry = useCallback((message) => {
    setStatus({ kind: 'waking', message });
    setLoading(true);
    clearTimeout(retryTimerRef.current);
    retryTimerRef.current = setTimeout(() => {
      setAttempt((current) => current + 1);
      webViewRef.current?.reload();
    }, RETRY_DELAY_MS);
  }, []);

  const handleHttpError = useCallback((event) => {
    const code = event.nativeEvent.statusCode;
    if (WAKING_STATUS.includes(code) && attempt < MAX_RETRIES) {
      scheduleRetry(`서버를 깨우는 중입니다… (${attempt + 1}/${MAX_RETRIES})`);
      return;
    }
    setLoading(false);
    setStatus({
      kind: 'error',
      message: WAKING_STATUS.includes(code)
        ? '서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.'
        : `지도 페이지 오류 (HTTP ${code})`,
    });
  }, [attempt, scheduleRetry]);

  const handleError = useCallback(() => {
    if (attempt < MAX_RETRIES) {
      scheduleRetry(`서버를 깨우는 중입니다… (${attempt + 1}/${MAX_RETRIES})`);
      return;
    }
    setLoading(false);
    setStatus({ kind: 'error', message: '지도 페이지를 열지 못했습니다. 네트워크를 확인해 주세요.' });
  }, [attempt, scheduleRetry]);

  const retryNow = useCallback(() => {
    clearTimeout(retryTimerRef.current);
    setAttempt(0);
    setStatus(null);
    setLoading(true);
    webViewRef.current?.reload();
  }, []);

  if (!center) return null;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{focusVehicleId ? '내 동선' : '전체 동선'}</Text>
        <Text style={styles.caption}>번호는 방문 순서 · 점선은 2회차</Text>
      </View>

      <View style={styles.body}>
        <WebView
          // key 를 바꾸면 WebView 가 새로 마운트되어 확실히 다시 요청한다.
          key={`map-${attempt}`}
          ref={webViewRef}
          source={{ uri: `${API_URL}/map` }}
          originWhitelist={['*']}
          onMessage={handleMessage}
          javaScriptEnabled
          domStorageEnabled
          // 지도를 손가락으로 확대/축소할 수 있어야 한다.
          scalesPageToFit={false}
          onError={handleError}
          onHttpError={handleHttpError}
          style={styles.webview}
        />

        {loading && status?.kind !== 'error' && (
          <View style={styles.overlay}>
            <ActivityIndicator color="#0F766E" />
            <Text style={styles.overlayText}>
              {status?.kind === 'waking' ? status.message : '지도를 불러오는 중…'}
            </Text>
            {status?.kind === 'waking' && (
              <Text style={styles.overlayHint}>
                무료 서버가 절전에서 깨어나는 중이라 최대 1분 정도 걸릴 수 있습니다.
              </Text>
            )}
          </View>
        )}

        {status?.kind === 'error' && (
          <View style={[styles.overlay, styles.errorOverlay]}>
            <Text style={styles.errorText}>{status.message}</Text>
            <Pressable style={styles.retryButton} onPress={retryNow}>
              <Text style={styles.retryText}>다시 시도</Text>
            </Pressable>
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
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F1F5F9', gap: 10, paddingHorizontal: 24 },
  overlayText: { color: '#475569', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  overlayHint: { color: '#94A3B8', fontSize: 11.5, textAlign: 'center', lineHeight: 17 },
  errorOverlay: { backgroundColor: '#FEF2F2' },
  errorText: { color: '#B91C1C', fontSize: 13, fontWeight: '700', textAlign: 'center' },
  retryButton: { backgroundColor: '#B91C1C', borderRadius: 10, paddingHorizontal: 18, paddingVertical: 9 },
  retryText: { color: '#FFFFFF', fontWeight: '800', fontSize: 12.5 },
});
