// 프론트엔드 -> 백엔드로 데이터를 쏘아 올리는 통신망 (api.js)
export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

const request = async (path, options = {}) => {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (error) {
    throw new Error(`백엔드(${API_URL})에 연결하지 못했습니다. 서버 실행 여부와 주소를 확인해 주세요.`);
  }

  if (!response.ok) {
    let detail = `요청 실패 (HTTP ${response.status})`;
    try {
      const body = await response.json();
      if (Array.isArray(body.detail)) {
        detail = body.detail.map((item) => item.msg).join('\n');
      } else if (body.detail) {
        detail = body.detail;
      }
    } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
};

export const optimizeRoutes = (payload) => request('/api/optimize', { method: 'POST', body: JSON.stringify(payload) });
export const saveRideCompletion = (payload) => request('/api/ride-completions', { method: 'POST', body: JSON.stringify(payload) });
export const fetchTodayCompletions = () => request('/api/ride-completions/today');
export const getTodayCompletionExportUrl = () => `${API_URL}/api/ride-completions/today/export`;
export const registerDriverDevice = (payload) => request('/api/driver-devices', { method: 'POST', body: JSON.stringify(payload) });
export const notifyDispatch = (result) => request('/api/dispatch/notify', { method: 'POST', body: JSON.stringify(result) });
export const fetchTodayDispatch = () => request('/api/dispatch/today');

// --- 실시간 갱신 ---
//
// 예전에는 여기서 수파베이스를 직접 구독했다. 그러려면 anon 키를 앱에 넣어야 하는데,
// 그 키는 APK 를 뜯으면 누구나 꺼낼 수 있고 RLS 를 켜면 구독도 함께 막힌다.
// 로그인이 없는 앱이라 "우리 앱만 허용"하는 정책을 만들 방법도 없다.
//
// 그래서 백엔드 경유 폴링으로 바꿨다. 앱에는 수파베이스 키가 아예 들어가지 않는다.

// 관제 화면을 보고 있는 동안만 이 간격으로 새로고침한다.
export const COMPLETION_POLL_MS = 20000;

/** 오늘의 탑승 완료를 { 어르신id: 완료시각 } 형태로 받아온다. */
export const fetchCompletedStopMap = async () => {
  const today = await fetchTodayCompletions();
  return Object.fromEntries(
    today.records.map((record) => [record.passenger_id, record.completed_at]),
  );
};
