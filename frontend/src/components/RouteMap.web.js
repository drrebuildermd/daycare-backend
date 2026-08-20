import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

// 지도 SDK는 지오코딩용 REST 키가 아니라 '자바스크립트 앱 키'를 쓴다. (별개의 키)
const KAKAO_JS_KEY = process.env.EXPO_PUBLIC_KAKAO_JS_KEY || '';

// 차량별 동선 색상. 차량이 더 많으면 순환한다.
const ROUTE_COLORS = ['#0F766E', '#1D4ED8', '#B91C1C', '#B45309', '#7E22CE', '#0369A1'];

const MAP_CANVAS_CLASS = 'songyoung-map-canvas';

// 지도 높이는 실제 미디어 쿼리로 정한다. RN StyleSheet에는 미디어 쿼리가 없고,
// JS로 창 크기를 재는 방식은 이 환경에서 리사이즈 시 갱신되지 않았다.
const injectMapCss = () => {
  const id = 'songyoung-map-css';
  if (document.getElementById(id)) return;
  const style = document.createElement('style');
  style.id = id;
  style.textContent = `
    .${MAP_CANVAS_CLASS} { width: 100%; height: 340px; background: #E2E8F0; }
    @media (min-width: 1024px) { .${MAP_CANVAS_CLASS} { height: 620px; } }
  `;
  document.head.appendChild(style);
};

let sdkPromise = null;

const loadKakaoSdk = () => {
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise((resolve, reject) => {
    if (window.kakao && window.kakao.maps && window.kakao.maps.LatLng) {
      resolve(window.kakao);
      return;
    }
    const script = document.createElement('script');
    // autoload=false로 받아 kakao.maps.load()가 끝난 뒤에만 API를 만진다.
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_JS_KEY}&autoload=false`;
    script.async = true;
    script.onload = () => window.kakao.maps.load(() => resolve(window.kakao));
    script.onerror = () => reject(new Error(
      '카카오맵 SDK를 불러오지 못했습니다. 자바스크립트 키와 등록된 사이트 도메인을 확인해 주세요.',
    ));
    document.head.appendChild(script);
  });
  return sdkPromise;
};

const numberedMarkerHtml = (label, color) => `
  <div style="
    transform: translate(-50%, -50%);
    width: 30px; height: 30px; border-radius: 15px;
    background: ${color}; border: 2.5px solid #FFFFFF;
    box-shadow: 0 2px 6px rgba(15,23,42,0.35);
    color: #FFFFFF; font-weight: 800; font-size: 13px;
    display: flex; align-items: center; justify-content: center;
  ">${label}</div>`;

const centerMarkerHtml = `
  <div style="
    transform: translate(-50%, -50%);
    padding: 5px 11px; border-radius: 8px;
    background: #0F172A; border: 2.5px solid #FFFFFF;
    box-shadow: 0 2px 8px rgba(15,23,42,0.4);
    color: #FFFFFF; font-weight: 800; font-size: 12px; white-space: nowrap;
  ">🏫 센터</div>`;

export default function RouteMap({ center, vehicles, focusVehicleId }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const drawnRef = useRef([]);
  const [error, setError] = useState('');
  const [hiddenVehicles, setHiddenVehicles] = useState({});

  useEffect(injectMapCss, []);

  // 차량 -> 색상 매핑. 범례와 동선이 같은 색을 쓰도록 한 곳에서 만든다.
  const legend = useMemo(
    () => (vehicles || []).map((vehicle, index) => ({
      vehicleId: vehicle.vehicle_id,
      label: `${vehicle.vehicle_type} ${vehicle.plate_number}`,
      color: ROUTE_COLORS[index % ROUTE_COLORS.length],
      stopCount: (vehicle.trips || []).reduce((sum, trip) => sum + (trip.stops || []).length, 0),
    })),
    [vehicles],
  );

  useEffect(() => {
    if (!KAKAO_JS_KEY || !center) return undefined;
    let cancelled = false;

    loadKakaoSdk()
      .then((kakao) => {
        if (cancelled || !containerRef.current) return;

        const centerPoint = new kakao.maps.LatLng(center.latitude, center.longitude);
        if (!mapRef.current) {
          mapRef.current = new kakao.maps.Map(containerRef.current, {
            center: centerPoint,
            level: 6,
          });
          mapRef.current.addControl(
            new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT,
          );
        }
        const map = mapRef.current;

        // 이전에 그린 것들을 먼저 지운다. 남겨두면 재계산 때마다 겹쳐 쌓인다.
        drawnRef.current.forEach((item) => item.setMap(null));
        drawnRef.current = [];

        const bounds = new kakao.maps.LatLngBounds();
        bounds.extend(centerPoint);

        (vehicles || []).forEach((vehicle, vehicleIndex) => {
          if (hiddenVehicles[vehicle.vehicle_id]) return;
          if (focusVehicleId && vehicle.vehicle_id !== focusVehicleId) return;
          const color = ROUTE_COLORS[vehicleIndex % ROUTE_COLORS.length];

          (vehicle.trips || []).forEach((trip) => {
            const stops = trip.stops || [];
            if (!trip.used || !stops.length) return;

            const stopPoints = stops.map(
              (stop) => new kakao.maps.LatLng(stop.latitude, stop.longitude),
            );
            // 센터에서 출발해 순서대로 방문하고 센터로 복귀하는 폐곡선.
            const path = [centerPoint, ...stopPoints, centerPoint];
            const polyline = new kakao.maps.Polyline({
              path,
              strokeWeight: 4,
              strokeColor: color,
              strokeOpacity: 0.85,
              // 2차 운행은 점선으로 구분한다.
              strokeStyle: trip.round === 2 ? 'shortdash' : 'solid',
            });
            polyline.setMap(map);
            drawnRef.current.push(polyline);

            stops.forEach((stop, stopIndex) => {
              const point = stopPoints[stopIndex];
              bounds.extend(point);
              const overlay = new kakao.maps.CustomOverlay({
                position: point,
                content: numberedMarkerHtml(stop.sequence, color),
                zIndex: 3,
              });
              overlay.setMap(map);
              drawnRef.current.push(overlay);
            });
          });
        });

        const centerOverlay = new kakao.maps.CustomOverlay({
          position: centerPoint,
          content: centerMarkerHtml,
          zIndex: 5,
        });
        centerOverlay.setMap(map);
        drawnRef.current.push(centerOverlay);

        map.setBounds(bounds, 48, 48, 48, 48);
        setError('');
      })
      .catch((sdkError) => {
        if (!cancelled) setError(sdkError.message);
      });

    return () => { cancelled = true; };
  }, [center, vehicles, hiddenVehicles, focusVehicleId]);

  if (!center) return null;

  if (!KAKAO_JS_KEY) {
    return (
      <View style={[styles.card, styles.fallback]}>
        <Text style={styles.fallbackTitle}>🗺️ 지도를 표시하려면 카카오맵 자바스크립트 키가 필요합니다</Text>
        <Text style={styles.fallbackBody}>
          지오코딩에 쓰는 REST API 키와는 별개의 키입니다.{'\n\n'}
          1. Kakao Developers → 내 애플리케이션 → 앱 키 → <Text style={styles.mono}>JavaScript 키</Text> 복사{'\n'}
          2. 같은 앱의 [플랫폼] → [Web]에 <Text style={styles.mono}>http://localhost:8081</Text> 등록{'\n'}
          3. <Text style={styles.mono}>frontend/.env</Text>에 아래 한 줄 추가 후 Expo 재시작{'\n'}
          {'   '}<Text style={styles.mono}>EXPO_PUBLIC_KAKAO_JS_KEY=발급받은_자바스크립트_키</Text>
        </Text>
        <Text style={styles.fallbackNote}>키가 없어도 아래 배차 리스트와 내비 연동은 정상 동작합니다.</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <View style={styles.mapHeader}>
        <Text style={styles.mapTitle}>전체 동선</Text>
        <Text style={styles.mapCaption}>번호는 방문 순서 · 점선은 2차 운행</Text>
      </View>

      <View style={styles.mapBody}>
        <div ref={containerRef} className={MAP_CANVAS_CLASS} />
        {!!error && (
          <View style={styles.errorOverlay}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
      </View>

      {legend.length > 1 && (
        <View style={styles.legend}>
          {legend.map((item) => {
            const isHidden = Boolean(hiddenVehicles[item.vehicleId]);
            return (
              <Pressable
                key={item.vehicleId}
                style={[styles.legendItem, isHidden && styles.legendItemOff]}
                onPress={() => setHiddenVehicles((current) => ({
                  ...current, [item.vehicleId]: !current[item.vehicleId],
                }))}
              >
                <View style={[styles.legendSwatch, { backgroundColor: isHidden ? '#CBD5E1' : item.color }]} />
                <Text style={[styles.legendText, isHidden && styles.legendTextOff]}>
                  {item.label} · {item.stopCount}명
                </Text>
              </Pressable>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, borderWidth: 1, borderColor: '#E2E8F0', overflow: 'hidden', marginBottom: 16 },
  mapHeader: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', paddingHorizontal: 16, paddingTop: 14, paddingBottom: 10 },
  mapTitle: { color: '#0F172A', fontSize: 16, fontWeight: '900' },
  mapCaption: { color: '#64748B', fontSize: 11, flexShrink: 1, textAlign: 'right' },
  mapBody: { width: '100%' },
  errorOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: '#FEF2F2', alignItems: 'center', justifyContent: 'center', padding: 20 },
  errorText: { color: '#B91C1C', fontWeight: '700', fontSize: 13, textAlign: 'center' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: 16, paddingVertical: 12, borderTopWidth: 1, borderColor: '#E2E8F0' },
  legendItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#F8FAFC', borderRadius: 999, borderWidth: 1, borderColor: '#E2E8F0', paddingHorizontal: 10, paddingVertical: 6 },
  legendItemOff: { opacity: 0.55 },
  legendSwatch: { width: 11, height: 11, borderRadius: 6, marginRight: 7 },
  legendText: { color: '#334155', fontSize: 12, fontWeight: '700' },
  legendTextOff: { textDecorationLine: 'line-through', color: '#94A3B8' },
  fallback: { padding: 20, justifyContent: 'center' },
  fallbackTitle: { color: '#0F172A', fontSize: 14, fontWeight: '900', marginBottom: 10 },
  fallbackBody: { color: '#475569', fontSize: 12.5, lineHeight: 20 },
  fallbackNote: { color: '#0F766E', fontSize: 12, fontWeight: '700', marginTop: 12 },
  mono: { fontFamily: 'monospace', color: '#0F172A', backgroundColor: '#F1F5F9' },
});
