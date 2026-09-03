// 프론트엔드 -> 백엔드로 데이터를 쏘아 올리는 통신망 (api.js)
export const API_URL = (
  process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

// 응답이 아예 오지 않는 경우를 막는다.
//
// try/catch 로는 이걸 못 잡는다. catch 는 요청이 '실패' 해야 도는데,
// 서버가 답을 안 주면 실패도 성공도 아닌 채로 영원히 매달린다.
// 그러면 await 뒤의 코드가 통째로 실행되지 않는다.
//
// Render 무료 요금제는 15분쯤 놀면 잠든다. 다시 깨는 데 30~60초가
// 걸리고 그동안 요청이 매달린다. 앱이 어떤 날은 켜지고 어떤 날은
// 안 켜지던 이유가 이것이었다.
const DEFAULT_TIMEOUT_MS = 30000;

const request = async (path, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) => {
  let response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    });
  } catch (error) {
    if (error && error.name === 'AbortError') {
      throw new Error(
        `서버가 ${Math.round(timeoutMs / 1000)}초 안에 응답하지 않았습니다. `
        + '잠시 후 다시 시도해 주세요.',
      );
    }
    throw new Error(`백엔드(${API_URL})에 연결하지 못했습니다. 서버 실행 여부와 주소를 확인해 주세요.`);
  } finally {
    clearTimeout(timer);
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

// 배차 계산은 솔버가 15초를 쓰고 지오코딩도 붙는다. 서버가 자고 있었다면
// 깨는 시간까지 더해진다. 짧게 끊으면 정상 계산이 실패로 보인다.
export const optimizeRoutes = (payload) =>
  request('/api/optimize', { method: 'POST', body: JSON.stringify(payload) }, 120000);

// 배차가 안 된 분들을 어떻게 하면 태울 수 있는지 묻는다.
// 배차 계산과 일부러 떼어 둔 API 다. 이쪽은 최대 6초까지 걸리므로
// 원장님이 결과를 보고 궁금할 때만 부른다.
export const recommendResolution = (payload, unassignedIds, runId, considerRevenueLoss = true) =>
  request('/api/optimize/recommend', {
    method: 'POST',
    body: JSON.stringify({
      request: payload,
      unassigned_passenger_ids: unassignedIds,
      optimization_run_id: runId || null,
      consider_revenue_loss: considerRevenueLoss,
    }),
  }, 120000);
export const saveRideCompletion = (payload) => request('/api/ride-completions', { method: 'POST', body: JSON.stringify(payload) });
// 등원(inbound)은 어르신을 센터로 모셔오는 운행, 하원(outbound)은 댁으로 모셔다드리는 운행.
export const TRIP_INBOUND = 'inbound';
export const TRIP_OUTBOUND = 'outbound';

/** 지금 시각으로 어느 쪽 운행인지 짐작한다. 기사님이 앱을 열 때 기본값으로 쓴다. */
export const guessTripType = (now = new Date()) =>
  (now.getHours() < 12 ? TRIP_INBOUND : TRIP_OUTBOUND);

export const tripLabel = (tripType) =>
  (tripType === TRIP_OUTBOUND ? '하원' : '등원');

// 어르신이 센터에 머무시는 시간. 백엔드의 stay_hours 와 같은 값이어야 한다.
// 화면은 '이렇게 계산됩니다' 를 미리 보여주기만 하고, 실제 계산은 서버가 한다.
export const STAY_HOURS = 8;

/** 'HH:MM' 에 시간을 더한다. 자정을 넘기면 23:59 에서 멈춘다. */
export const shiftTime = (value, hours = STAY_HOURS) => {
  const match = /^(\d{1,2}):(\d{2})$/.exec((value || '').trim());
  if (!match) return '';
  const total = Number(match[1]) * 60 + Number(match[2]) + hours * 60;
  const capped = Math.min(total, 24 * 60 - 1);
  return `${String(Math.floor(capped / 60)).padStart(2, '0')}:${String(capped % 60).padStart(2, '0')}`;
};

export const fetchTodayCompletions = (tripType) =>
  request(`/api/ride-completions/today${tripType ? `?trip_type=${tripType}` : ''}`);
// 송영 일지는 등원과 하원을 함께 내려받는다. 하루치를 한 장으로 봐야 한다.
export const getTodayCompletionExportUrl = () => `${API_URL}/api/ride-completions/today/export`;
export const registerDriverDevice = (payload) => request('/api/driver-devices', { method: 'POST', body: JSON.stringify(payload) });
export const notifyDispatch = (result) => request('/api/dispatch/notify', { method: 'POST', body: JSON.stringify(result) });
export const fetchTodayDispatch = (tripType = TRIP_INBOUND) =>
  request(`/api/dispatch/today?trip_type=${tripType}`);

// 기사님이 오늘 배차표를 확인했다고 표시한다. (기사 -> 관리자)
export const acknowledgeDispatch = (payload) =>
  request('/api/dispatch/ack', { method: 'POST', body: JSON.stringify(payload) });

// 관제 화면이 어느 차량이 확인했는지 보려고 받아간다.
export const fetchTodayAcks = (tripType = TRIP_INBOUND) =>
  request(`/api/dispatch/acks/today?trip_type=${tripType}`);

// --- 실시간 갱신 ---
//
// 예전에는 여기서 수파베이스를 직접 구독했다. 그러려면 anon 키를 앱에 넣어야 하는데,
// 그 키는 APK 를 뜯으면 누구나 꺼낼 수 있고 RLS 를 켜면 구독도 함께 막힌다.
// 로그인이 없는 앱이라 "우리 앱만 허용"하는 정책을 만들 방법도 없다.
//
// 그래서 백엔드 경유 폴링으로 바꿨다. 앱에는 수파베이스 키가 아예 들어가지 않는다.

// 관제 화면을 보고 있는 동안만 이 간격으로 새로고침한다.
export const COMPLETION_POLL_MS = 20000;

/** 오늘의 탑승·하차 완료를 { 어르신id: 완료시각 } 형태로 받아온다.
 *
 * 등원과 하원은 같은 어르신이 둘 다 있으므로 반드시 한쪽만 받아야 한다.
 * 안 그러면 아침에 태운 기록 때문에 오후 명단이 이미 끝난 것처럼 보인다.
 */
export const fetchCompletedStopMap = async (tripType = TRIP_INBOUND) => {
  const today = await fetchTodayCompletions(tripType);
  return Object.fromEntries(
    today.records.map((record) => [record.passenger_id, record.completed_at]),
  );
};
