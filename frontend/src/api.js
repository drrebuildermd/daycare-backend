import { createClient } from '@supabase/supabase-js';

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

// ==========================================
// 📡 [신규 장착] 수파베이스 실시간 수신 안테나
// ==========================================
const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

export const supabase = (supabaseUrl && supabaseAnonKey)
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;

// 탑승 완료 실시간 방송 수신 레이더 함수
export const listenForRideCompletions = (onRecordAdded) => {
  if (!supabase) {
    console.warn('⚠️ 수파베이스 안테나가 없습니다. (.env 파일 확인 필요)');
    return null;
  }

  const channel = supabase
    .channel('public:ride_completions')
    .on(
      'postgres_changes',
      { event: '*', schema: 'public', table: 'ride_completions' },
      (payload) => {
        // 기사님이 현장에서 탑승 완료를 누르는 순간 이 부분이 즉시 발동됩니다!
        onRecordAdded(payload.new);
      }
    )
    .subscribe();

  return channel; // 앱이 꺼질 때 안테나를 접기 위해 반환
};