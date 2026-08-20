// 프론트엔드 -> 백엔드로 데이터를 쏘아 올리는 통신망 (api.js)

// 실기기(Expo Go)에서는 localhost가 휴대폰 자신을 가리키므로,
// .env의 EXPO_PUBLIC_API_URL에 PC의 LAN IP를 넣어야 한다. (.env.example 참고)
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
      // FastAPI 검증 오류는 detail이 배열로 온다.
      if (Array.isArray(body.detail)) {
        detail = body.detail.map((item) => item.msg).join('\n');
      } else if (body.detail) {
        detail = body.detail;
      }
    } catch (_) {
      // 본문이 JSON이 아니면 상태 코드 메시지를 그대로 쓴다.
    }
    throw new Error(detail);
  }

  return response.json();
};

// App.js가 { center, vehicles, passengers } 한 덩어리로 넘기고,
// 백엔드 OptimizeRequest도 같은 모양을 받는다. 변형하지 않고 그대로 전달한다.
export const optimizeRoutes = (payload) =>
  request('/api/optimize', { method: 'POST', body: JSON.stringify(payload) });

export const saveRideCompletion = (payload) =>
  request('/api/ride-completions', { method: 'POST', body: JSON.stringify(payload) });

export const fetchTodayCompletions = () => request('/api/ride-completions/today');

export const getTodayCompletionExportUrl = () =>
  `${API_URL}/api/ride-completions/today/export`;

// --- 기사님 기기 / 배차 전송 ---

export const registerDriverDevice = (payload) =>
  request('/api/driver-devices', { method: 'POST', body: JSON.stringify(payload) });

// 배차 결과를 서버에 저장하고 담당 기사님 폰으로 푸시를 보낸다.
export const notifyDispatch = (result) =>
  request('/api/dispatch/notify', { method: 'POST', body: JSON.stringify(result) });

// 기사님 폰이 본인 동선을 그리려고 받아가는 오늘의 배차.
export const fetchTodayDispatch = () => request('/api/dispatch/today');
