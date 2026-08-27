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
//
// --- 콜드 스타트 대응 ---
// Render 무료 티어는 15분 무활동이면 잠든다. 실측해 보니 깨어나는 동안 503을
// 돌려주는 게 아니라 응답을 그대로 붙잡고 있었다. (측정값 82.5초)
// 그래서 onError / onHttpError 가 전혀 발동하지 않고 WebView 만 하얗게 멈춘다.
//
// 두 단계로 나눠 처리한다.
//   1단계: 가벼운 /api/health 로 서버를 먼저 깨운다. 경과 시간을 보여줘서
//          기사님이 "멈췄나?" 하고 앱을 끄지 않도록 한다.
//   2단계: 깨어난 뒤에 WebView 를 띄운다. 그래도 지도가 안 그려지면
//          3초 간격 최대 3회 재시도한다.

const WAKING_STATUS = [408, 425, 429, 500, 502, 503, 504];
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 3000;
// 서버 기동에 80초 넘게 걸리는 것을 실측했다. 넉넉히 잡는다.
const WAKE_TIMEOUT_MS = 100000;
// 서버가 깨어난 뒤라면 지도는 금방 떠야 한다. 이 안에 map-ready 가
// 안 오면 붙잡힌 것으로 보고 재시도한다.
const LOAD_TIMEOUT_MS = 20000;

export default function RouteMap({ center, vehicles, focusVehicleId }) {
  const webViewRef = useRef(null);
  const retryTimerRef = useRef(null);
  const loadTimerRef = useRef(null);
  const tickerRef = useRef(null);

  const [phase, setPhase] = useState('waking'); // waking | loading | ready | error
  const [attempt, setAttempt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [message, setMessage] = useState('');
  const [round, setRound] = useState(0); // '다시 시도' 를 누르면 올라간다

  const payload = JSON.stringify({ center, vehicles: vehicles || [], focusVehicleId });

  const clearTimers = useCallback(() => {
    clearTimeout(retryTimerRef.current);
    clearTimeout(loadTimerRef.current);
    clearInterval(tickerRef.current);
    retryTimerRef.current = null;
    loadTimerRef.current = null;
    tickerRef.current = null;
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  // --- 1단계: 서버 깨우기 ---
  // 지도 페이지(무거움)로 서버를 깨우면 붙잡힌 채 아무 신호도 못 받는다.
  // 가벼운 health 로 먼저 깨우면 그동안 경과 시간을 보여줄 수 있다.
  useEffect(() => {
    if (!center) return undefined;
    let cancelled = false;

    setPhase('waking');
    setElapsed(0);
    setAttempt(0);

    const startedAt = Date.now();
    tickerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), WAKE_TIMEOUT_MS);

    fetch(`${API_URL}/api/health`, { signal: controller.signal })
      .catch(() => null)
      .finally(() => {
        clearTimeout(abortTimer);
        if (cancelled) return;
        clearInterval(tickerRef.current);
        tickerRef.current = null;
        // 깨우기에 실패했더라도 지도는 시도해 본다.
        // health 만 막히고 페이지는 열리는 경우가 있다.
        setPhase('loading');
      });

    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(abortTimer);
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    };
  }, [center, round]);

  const failOrRetry = useCallback((reason) => {
    clearTimeout(loadTimerRef.current);
    loadTimerRef.current = null;

    if (attempt < MAX_RETRIES) {
      setMessage(`지도를 다시 불러오는 중입니다… (${attempt + 1}/${MAX_RETRIES})`);
      retryTimerRef.current = setTimeout(() => {
        setAttempt((current) => current + 1);
      }, RETRY_DELAY_MS);
      return;
    }
    setPhase('error');
    setMessage(reason);
  }, [attempt]);

  // --- 2단계: 지도 로드 감시 ---
  // 응답이 붙잡히면 onError 가 안 뜬다. 시간으로 판정해야 한다.
  useEffect(() => {
    if (phase !== 'loading') return undefined;
    setMessage('');
    loadTimerRef.current = setTimeout(() => {
      failOrRetry('지도가 응답하지 않습니다. 네트워크를 확인하고 다시 시도해 주세요.');
    }, LOAD_TIMEOUT_MS);
    return () => clearTimeout(loadTimerRef.current);
  }, [phase, attempt, failOrRetry]);

  // 지도 페이지가 "SDK 준비됐다"고 알려오면 그때 경로를 넘긴다.
  // 로드 완료(onLoadEnd)만 믿고 보내면 SDK가 아직이라 그려지지 않는다.
  const handleMessage = useCallback((event) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === 'map-ready') {
        clearTimeout(loadTimerRef.current);
        loadTimerRef.current = null;
        setPhase('ready');
        setMessage('');
        webViewRef.current?.injectJavaScript(`window.renderRoute(${payload}); true;`);
      }
    } catch (_) {
      // 지도 페이지가 보내는 다른 메시지는 무시한다.
    }
  }, [payload]);

  const handleHttpError = useCallback((event) => {
    const code = event.nativeEvent.statusCode;
    failOrRetry(
      WAKING_STATUS.includes(code)
        ? '서버가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.'
        : `지도 페이지 오류 (HTTP ${code})`,
    );
  }, [failOrRetry]);

  const handleError = useCallback(() => {
    failOrRetry('지도 페이지를 열지 못했습니다. 네트워크를 확인해 주세요.');
  }, [failOrRetry]);

  const retryNow = useCallback(() => {
    clearTimers();
    setMessage('');
    setRound((current) => current + 1); // 서버 깨우기부터 다시
  }, [clearTimers]);

  if (!center) return null;

  const showOverlay = phase !== 'ready';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{focusVehicleId ? '내 동선' : '전체 동선'}</Text>
        <Text style={styles.caption}>번호는 방문 순서 · 점선은 2회차</Text>
      </View>

      <View style={styles.body}>
        {phase !== 'waking' && (
          <WebView
            // key 를 바꾸면 WebView 가 새로 마운트되어 확실히 다시 요청한다.
            key={`map-${round}-${attempt}`}
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
        )}

        {showOverlay && phase !== 'error' && (
          <View style={styles.overlay}>
            <ActivityIndicator size="large" color="#0F766E" />
            <Text style={styles.overlayTitle}>
              {phase === 'waking'
                ? '서버를 깨우고 지도를 불러오는 중입니다…'
                : (message || '지도를 불러오는 중입니다…')}
            </Text>
            {phase === 'waking' && (
              <>
                <Text style={styles.overlayHint}>
                  절전 상태였던 서버를 깨우는 중입니다.{'\n'}
                  처음 열 때는 1분 이상 걸릴 수 있습니다. 앱을 끄지 말고 기다려 주세요.
                </Text>
                <Text style={styles.elapsed}>{elapsed}초 경과</Text>
              </>
            )}
          </View>
        )}

        {phase === 'error' && (
          <View style={[styles.overlay, styles.errorOverlay]}>
            <Text style={styles.errorText}>{message}</Text>
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
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F1F5F9', gap: 12, paddingHorizontal: 28 },
  overlayTitle: { color: '#0F172A', fontSize: 15, fontWeight: '800', textAlign: 'center' },
  overlayHint: { color: '#64748B', fontSize: 12.5, textAlign: 'center', lineHeight: 19 },
  elapsed: { color: '#0F766E', fontSize: 13, fontWeight: '800' },
  errorOverlay: { backgroundColor: '#FEF2F2' },
  errorText: { color: '#B91C1C', fontSize: 13.5, fontWeight: '700', textAlign: 'center', lineHeight: 20 },
  retryButton: { backgroundColor: '#B91C1C', borderRadius: 10, paddingHorizontal: 20, paddingVertical: 10 },
  retryText: { color: '#FFFFFF', fontWeight: '800', fontSize: 13 },
});
