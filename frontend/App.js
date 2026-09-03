import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SplashScreen from 'expo-splash-screen';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import TextInput from './src/ui/TextInput';
import Text from './src/ui/Text';
import { brand, color } from './src/theme';
import Icon from './src/ui/Icon';
import useAppFonts from './src/ui/loadFonts';
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  Image,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';

import {
  API_URL,
  COMPLETION_POLL_MS,
  TRIP_INBOUND,
  TRIP_OUTBOUND,
  tripLabel,
  fetchCompletedStopMap,
  fetchTodayAcks,
  fetchTodayCompletions,
  fetchTodayDispatch,
  getTodayCompletionExportUrl,
  notifyDispatch,
  recommendResolution,
  optimizeRoutes,
  saveRideCompletion,
} from './src/api';
import PassengerForm from './src/components/PassengerForm';
import VehicleForm from './src/components/VehicleForm';
import VehicleResults from './src/components/VehicleResults';
import { downloadPassengerTemplate, pickPassengerExcel } from './src/excel';
import AddressSearch from './src/components/AddressSearch';
import PairRuleEditor from './src/components/PairRuleEditor';
import SummaryBar from './src/components/SummaryBar';
import ModeGate from './src/screens/ModeGate';
import DriverScreen from './src/screens/DriverScreen';
import DriverPushPanel from './src/components/DriverPushPanel';
import { listenForDispatchTaps } from './src/push';

const emptyPassenger = () => ({
  localId: `${Date.now()}-${Math.random()}`,
  id: `passenger-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
  name: '',
  address: '',
  detailAddress: '',
  attending: true,
  // 등원과 하원의 탑승 여부는 다를 수 있다.
  attendingOutbound: true,
  pickupStart: '08:00',
  pickupEnd: '08:30',
  // 비워두면 서버가 등원 시각 + 머무는 시간(8시간)으로 정한다.
  dropoffStart: '',
  dropoffEnd: '',
  wheelchair: false,
  guardianPhone: '', // 🚨 [신규 장착] 보호자 연락처 저장 공간 확보
  passengerPhone: '',
  // 기사님 📞 버튼이 누구에게 걸지. 기본은 보호자.
  primaryContact: 'guardian',
  // 탑승 완료 문자 수신 여부. 기본은 받음.
  smsOptIn: true,
  latitude: '',
  longitude: '',
});

const emptyVehicle = () => ({
  localId: `${Date.now()}-${Math.random()}`,
  id: `vehicle-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
  vehicleType: '',
  plateNumber: '',
  driverName: '',
  capacity: '4',
  // 휠체어 고정석. 리프트가 없는 차량이 기본이라 0에서 시작한다.
  wheelchairCapacity: '0',
  // 자차 송영. 기본은 센터 출발.
  driverPhone: '',
  startType: 'center',
  startAddress: '',
  startLatitude: '',
  startLongitude: '',
});

// 등원과 하원은 타는 사람이 다르다. 아침엔 보호자가 모셔다 주고 오후엔
// 센터 차를 타는 분이 있어서, 어느 쪽을 계산하느냐에 따라 대상자가 달라진다.
//
// 이 판단을 화면마다 따로 하면 '대상 34명인데 20명만 배차됨' 같은 일이 생긴다.
// 실제로 그랬다. 요약 막대는 하원 스위치를 보고, 서버로 보낼 명단은 등원
// 스위치를 봐서, 하원만 타시는 14분이 요청에 실리지도 않고 사라졌다.
// 그래서 기준은 여기 하나뿐이다.
const isRiding = (passenger, trip) =>
  (trip === TRIP_OUTBOUND ? passenger.attendingOutbound : passenger.attending) !== false;

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
function formatClock(value) {
  return value.toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

// 화면 아래 고정된 계산 버튼의 크기. 스크롤 끝을 얼마나 비울지 계산하는 데 쓴다.
const FAB_HEIGHT = 58;
const FAB_GAP = 16;

const STORAGE_KEY = 'daycare-routing:last-session:v1';
// 기사님 폰은 한 번 고르면 계속 기사 화면으로 열려야 한다.
const MODE_KEY = 'daycare-routing:mode:v1';

// 준비가 끝날 때까지 스플래시를 내리지 않는다.
SplashScreen.preventAutoHideAsync().catch(() => {});

// 안드로이드는 화면 위아래 끝까지 앱이 그려진다(edge-to-edge).
// 상태바·제스처바가 차지하는 만큼을 직접 비워주지 않으면 글자가 그 밑에 깔린다.
export default function App() {
  return (
    <SafeAreaProvider>
      <AdminApp />
    </SafeAreaProvider>
  );
}

function AdminApp() {
  const insets = useSafeAreaInsets();
  const fontsLoaded = useAppFonts();
  // 화면 아래 떠 있는 계산 버튼이 가리는 높이.
  // onLayout 으로 재보려 했으나 웹에서 0 이 돌아와 스페이서가 비어버렸다.
  // 버튼 높이가 styles.fab 에 고정되어 있으므로 그냥 더한다. 잴 필요가 없다.
  //   버튼(58) + 버튼 아래 여백(기기 제스처바 + 16) + 콘텐츠와의 간격(16)
  const ctaClearance = FAB_HEIGHT + insets.bottom + FAB_GAP + 16;
  const [screen, setScreen] = useState('vehicles');
  // 등원과 하원은 명단도 동선도 다르다. 결과를 따로 들고 있어야
  // 토글을 오갈 때마다 다시 계산하지 않는다.
  const [tripType, setTripType] = useState(TRIP_INBOUND);
  const [results, setResults] = useState({ inbound: null, outbound: null });
  const [vehicles, setVehicles] = useState([emptyVehicle()]);
  const [center, setCenter] = useState({
    name: '주야간보호센터', address: '', latitude: '', longitude: '',
  });
  const [passengers, setPassengers] = useState([emptyPassenger()]);
  const [excelName, setExcelName] = useState('');
  const [loading, setLoading] = useState(false);
  const result = results[tripType];
  const setResult = useCallback(
    (next) => setResults((current) => ({ ...current, [tripType]: next })),
    [tripType],
  );
  const [completedStops, setCompletedStops] = useState({});
  const [savingStops, setSavingStops] = useState({});
  const [isCenterAddressModalOpen, setIsCenterAddressModalOpen] = useState(false);
  const [pairRules, setPairRules] = useState([]);
  const [sending, setSending] = useState(false);
  const [focusVehicleId, setFocusVehicleId] = useState(null);
  // 기사님이 배차표를 확인했는지. 관제 화면에서 대기 중인 차량이 보여야 한다.
  const [acks, setAcks] = useState([]);
  // 폴링이 살아 있는지 원장님이 눈으로 확인할 수 있어야 한다.
  const [syncedAt, setSyncedAt] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [restored, setRestored] = useState(false);
  // null = 아직 모름(로딩), 'gate' = 선택 화면, 'admin' | 'driver'
  const [mode, setMode] = useState(null);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEY);
        if (saved) {
          const session = JSON.parse(saved);
          if (session.vehicles) setVehicles(session.vehicles);
          if (session.center) setCenter(session.center);
          if (session.passengers) setPassengers(session.passengers);
          if (session.pairRules) setPairRules(session.pairRules);
          // v1 은 배차 결과를 result 하나로 들고 있었다. 그때는 등원뿐이었다.
          // 그대로 두면 원장님 폰에서 어제 배차가 사라진 것처럼 보인다.
          const restored = session.results
            || (session.result ? { inbound: session.result, outbound: null } : null);
          if (restored) {
            setResults({ inbound: restored.inbound || null, outbound: restored.outbound || null });
            if (restored.inbound || restored.outbound) setScreen('results');
          }
          if (session.tripType === TRIP_OUTBOUND) setTripType(TRIP_OUTBOUND);
        }
      } catch (_) {}

      // 여기까지는 폰 안에서만 읽는다. 화면을 띄우는 데 필요한 것은
      // 이게 전부다.
      //
      // 예전에는 이 아래 서버 호출 두 개를 먼저 기다린 뒤에 모드를 정했다.
      // 서버가 자고 있으면 그 await 에서 멈췄고, setMode 가 실행되지 않아
      // mode 가 null 로 남았다. 스플래시를 내리는 조건이 mode !== null 이라
      // 앱이 첫 화면에서 영원히 멈췄다. 서버가 깨어 있는 날에는 멀쩡했다.
      try {
        const savedMode = await AsyncStorage.getItem(MODE_KEY);
        setMode(savedMode === 'admin' || savedMode === 'driver' ? savedMode : 'gate');
      } catch (_) {
        setMode('gate');
      }
      setRestored(true);

      // 서버에서 받아오는 것은 화면을 띄운 뒤에 채운다.
      // 늦게 와도, 아예 안 와도 앱은 이미 쓸 수 있는 상태다.
      try {
        const today = await fetchTodayCompletions();
        setCompletedStops(Object.fromEntries(
          today.records.map((record) => [record.passenger_id, record.completed_at]),
        ));
      } catch (_) {}
      try {
        const ackList = await fetchTodayAcks();
        setAcks(ackList.records || []);
      } catch (_) {}
    };
    restoreSession();
  }, []);

  useEffect(() => listenForDispatchTaps(async (vehicleId) => {
    setFocusVehicleId(vehicleId);
    setScreen('results');
    try {
      const today = await fetchTodayDispatch();
      if (today.result) setResult(today.result);
    } catch (error) {
      Alert.alert('배차 정보를 불러오지 못했습니다', error.message);
    }
  }), []);

  useEffect(() => {
    if (!restored) return;
    AsyncStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ vehicles, center, passengers, pairRules, results, tripType }),
    ).catch(() => {});
  }, [restored, vehicles, center, passengers, pairRules, results, tripType]);

  // 탑승 완료와 배차 확인은 서로를 기다리지 않는다.
  // 예전에는 Promise.all 이라 탑승 완료 조회가 한 번 실패하면 배차 확인까지
  // 통째로 버려졌다. 그러면 주기마다 조용히 같은 실패를 반복하면서 화면은
  // 영원히 '확인 대기'로 남는다.
  const syncLiveState = useCallback(async () => {
    setSyncing(true);
    try {
      const [completions, ackList] = await Promise.allSettled([
        fetchCompletedStopMap(tripType),
        fetchTodayAcks(tripType),
      ]);

      if (completions.status === 'fulfilled') setCompletedStops(completions.value);
      if (ackList.status === 'fulfilled') setAcks(ackList.value.records || []);

      // 둘 다 실패하면 지금 보이는 화면이 언제 것인지 알 수 없다.
      // 그때는 시각을 갱신하지 않아 '마지막 갱신'이 멈춘 것으로 보이게 둔다.
      // 조용히 낡아가는 것보다 멈춘 게 보이는 편이 낫다.
      if (completions.status === 'fulfilled' || ackList.status === 'fulfilled') {
        setSyncedAt(new Date());
      }
    } finally {
      setSyncing(false);
    }
  }, [tripType]);

  // 다른 기사님이 탑승 완료나 배차표 확인을 누르면 관제 화면에도 반영되어야 한다.
  // 수파베이스를 직접 구독하는 대신 백엔드를 주기적으로 물어본다.
  // 관제 화면을 보고 있고 앱이 앞에 있을 때만 돈다. 배터리와 서버를 아낀다.
  useEffect(() => {
    if (screen !== 'results') return undefined;

    let timer = null;

    const start = () => {
      if (timer) return;
      syncLiveState();
      timer = setInterval(syncLiveState, COMPLETION_POLL_MS);
    };
    const stop = () => {
      clearInterval(timer);
      timer = null;
    };

    start();
    // 앱이 백그라운드로 가면 멈추고, 돌아오면 즉시 한 번 맞춘 뒤 재개한다.
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') start();
      else stop();
    });

    return () => {
      stop();
      subscription.remove();
    };
  }, [screen, tripType, syncLiveState]);

  useEffect(() => {
    if (fontsLoaded && mode !== null) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded, mode]);

  // 마지막 안전망.
  //
  // 위 조건이 어떤 이유로든 참이 되지 않으면 원장님은 멈춘 앱을 보게 된다.
  // 무엇이 잘못됐든 8초 뒤에는 화면을 넘긴다. 모드를 못 읽었으면 선택
  // 화면으로 보낸다. 잘못된 화면을 보여 주는 편이 아무것도 못 하는 것보다 낫다.
  useEffect(() => {
    const rescue = setTimeout(() => {
      setMode((current) => (current === null ? 'gate' : current));
      SplashScreen.hideAsync().catch(() => {});
    }, 8000);
    return () => clearTimeout(rescue);
  }, []);

  const passengerCount = useMemo(
    () => passengers.filter(
      (passenger) => (passenger.name || passenger.address) && isRiding(passenger, tripType),
    ).length,
    [passengers, tripType],
  );
  const maxPassengerCapacity = useMemo(
    () => vehicles.reduce((sum, vehicle) => sum + (Number(vehicle.capacity) || 0), 0) * 2,
    [vehicles],
  );

  const updatePassenger = (index, next) => {
    setPassengers((current) => current.map((item, itemIndex) => itemIndex === index ? next : item));
  };

  const updateVehicle = (index, next) => {
    setVehicles((current) => current.map((item, itemIndex) => itemIndex === index ? next : item));
  };

  const [excelBusy, setExcelBusy] = useState(false);

  const importExcel = async () => {
    setExcelBusy(true);
    try {
      const imported = await pickPassengerExcel();
      if (!imported) return;
      setPassengers(imported.passengers);
      setExcelName(imported.fileName);
      const wheelchairs = imported.passengers.filter((item) => item.wheelchair).length;
      Alert.alert(
        '불러오기 완료',
        `${imported.passengers.length}명을 불러왔습니다.`
        + (wheelchairs ? `\n휠체어 이용 ${wheelchairs}명이 포함되어 있습니다.` : ''),
      );
    } catch (error) {
      // 어느 줄이 왜 잘못됐는지 그대로 보여 준다. 원장님이 엑셀에서
      // 바로 찾아 고치실 수 있어야 한다.
      Alert.alert('엑셀을 불러오지 못했습니다', error.message);
    } finally {
      setExcelBusy(false);
    }
  };

  const getTemplate = async () => {
    setExcelBusy(true);
    try {
      const saved = await downloadPassengerTemplate();
      if (!saved.shared) {
        Alert.alert('양식을 만들었습니다', `저장 위치: ${saved.path}`);
      }
    } catch (error) {
      Alert.alert('양식을 만들지 못했습니다', error.message);
    } finally {
      setExcelBusy(false);
    }
  };

  const validate = () => {
    if (!vehicles.length) return '차량을 한 대 이상 등록해 주세요.';
    const plateNumbers = new Set();
    for (const [index, vehicle] of vehicles.entries()) {
      const capacity = Number(vehicle.capacity);
      if (!vehicle.vehicleType.trim() || !vehicle.plateNumber.trim()) return `${index + 1}번 차량의 차종과 차량번호를 입력해 주세요.`;
      if (!Number.isInteger(capacity) || capacity < 1 || capacity > 100) return `${vehicle.plateNumber} 차량의 정원은 1~100 사이의 정수여야 합니다.`;
      const wheelchairCapacity = Number(vehicle.wheelchairCapacity || 0);
      if (!Number.isInteger(wheelchairCapacity) || wheelchairCapacity < 0) return `${vehicle.plateNumber} 차량의 휠체어 좌석 수는 0 이상의 정수여야 합니다.`;
      if (wheelchairCapacity > capacity) return `${vehicle.plateNumber} 차량의 휠체어 좌석(${wheelchairCapacity}자리)이 총 정원(${capacity}명)보다 많습니다.`;
      if (plateNumbers.has(vehicle.plateNumber.trim())) return `차량번호 ${vehicle.plateNumber}가 중복되었습니다.`;
      plateNumbers.add(vehicle.plateNumber.trim());
    }
    const missingStart = vehicles.find(
      (vehicle) => vehicle.startType === 'custom' && !(vehicle.startAddress || '').trim(),
    );
    if (missingStart) {
      return `${missingStart.plateNumber || '차량'}은 자차 출발로 설정됐지만 출발지 주소가 없습니다.`;
    }
    if (!center.address.trim()) return '센터 주소를 입력해 주세요.';
    const entered = passengers.filter((item) => item.name || item.address);
    if (!entered.length) return '어르신을 한 명 이상 입력해 주세요.';
    const active = entered.filter((item) => isRiding(item, tripType));
    if (!active.length) return `${tripLabel(tripType)} 대상 어르신이 없습니다. 탑승 토글을 확인해 주세요.`;
    if (active.length > maxPassengerCapacity) return `등록 차량의 2회 운행 최대 수용 인원은 ${maxPassengerCapacity}명입니다.`;
    for (const [index, passenger] of active.entries()) {
      if (!passenger.name.trim() || !passenger.address.trim()) return `${index + 1}번 어르신의 이름과 주소를 입력해 주세요.`;
      if (!HHMM.test(passenger.pickupStart) || !HHMM.test(passenger.pickupEnd)) return `${passenger.name}님의 시간을 HH:MM 형식으로 입력해 주세요.`;
      if (passenger.pickupStart > passenger.pickupEnd) return `${passenger.name}님의 픽업 하한이 상한보다 늦습니다.`;
      // 하원 하차 시각은 비워 두면 서버가 등원 시각 + 8시간으로 채운다.
      // 그래서 넣은 경우에만 본다.
      const hasDropoff = (passenger.dropoffStart || '') && (passenger.dropoffEnd || '');
      if (hasDropoff) {
        if (!HHMM.test(passenger.dropoffStart) || !HHMM.test(passenger.dropoffEnd)) return `${passenger.name}님의 하차 시간을 HH:MM 형식으로 입력해 주세요.`;
        if (passenger.dropoffStart > passenger.dropoffEnd) return `${passenger.name}님의 하차 하한이 상한보다 늦습니다.`;
      }
    }
    return null;
  };

  const asLocation = (item) => {
    const output = { name: item.name.trim(), address: item.address.trim() };
    if (item.latitude !== '' && item.longitude !== '') {
      output.latitude = Number(item.latitude);
      output.longitude = Number(item.longitude);
    }
    return output;
  };

  // 배차 계산과 대안 분석이 같은 입력을 써야 한다. 두 곳에서 따로 만들면
  // 분석이 원장님 화면에 보이는 것과 다른 판을 푸는 일이 생긴다.
  const buildPayload = () => {
    const active = passengers
      .filter((item) => item.name || item.address)
      .filter((item) => isRiding(item, tripType));
    const activeIds = new Set(active.map((item) => item.id));
    const liveRules = pairRules.filter(
      (rule) => rule.passengerIds.every((id) => activeIds.has(id)),
    );
    const asRule = (rule) => ({ passenger_ids: rule.passengerIds });

    return {
      trip_type: tripType,
      center: asLocation(center),
      vehicles: vehicles.map((vehicle) => ({
        id: vehicle.id,
        vehicle_type: vehicle.vehicleType.trim(),
        plate_number: vehicle.plateNumber.trim(),
        driver_name: (vehicle.driverName || '').trim() || null,
        driver_phone: (vehicle.driverPhone || '').trim() || null,
        capacity: Number(vehicle.capacity),
        wheelchair_capacity: Number(vehicle.wheelchairCapacity || 0),
        start_type: vehicle.startType === 'custom' ? 'custom' : 'center',
        start_address: (vehicle.startAddress || '').trim() || null,
        // 좌표는 백엔드가 주소로 변환한다. 비어 있으면 보내지 않는다.
        start_latitude: vehicle.startLatitude === '' || vehicle.startLatitude == null
          ? null : Number(vehicle.startLatitude),
        start_longitude: vehicle.startLongitude === '' || vehicle.startLongitude == null
          ? null : Number(vehicle.startLongitude),
      })),
      passengers: active.map((item) => ({
        ...asLocation(item),
        id: item.id,
        detail_address: (item.detailAddress || '').trim(),
        attending: item.attending !== false,
        attending_outbound: item.attendingOutbound !== false,
        pickup_start: item.pickupStart,
        pickup_end: item.pickupEnd,
        wheelchair: item.wheelchair,
        dropoff_start: (item.dropoffStart || '').trim() || null,
        dropoff_end: (item.dropoffEnd || '').trim() || null,
        guardian_phone: (item.guardianPhone || '').trim(),
        passenger_phone: (item.passengerPhone || '').trim() || null,
        // 기존 명단에는 없던 값이다. 없으면 보호자에게 걸고, 알림은 켠 것으로 본다.
        primary_contact: item.primaryContact === 'self' ? 'self' : 'guardian',
        sms_opt_in: item.smsOptIn !== false,
      })),
      forbidden_pairs: liveRules.filter((rule) => rule.kind === 'forbidden').map(asRule),
      required_pairs: liveRules.filter((rule) => rule.kind === 'required').map(asRule),
    };
  };

  // 대안 분석. 원장님이 [대안 보기] 를 눌렀을 때만 부른다.
  const [advice, setAdvice] = useState(null);
  const [advising, setAdvising] = useState(false);

  const askForAdvice = async () => {
    if (!result) return;
    const dropped = (result.unassigned_passengers || []).map((item) => item.passenger_id);
    if (!dropped.length) return;
    setAdvising(true);
    setAdvice(null);
    try {
      const report = await recommendResolution(
        buildPayload(), dropped, result.optimization_run_id,
      );
      setAdvice(report);
    } catch (error) {
      Alert.alert('대안 분석 실패', error.message || '잠시 후 다시 시도해 주세요.');
    } finally {
      setAdvising(false);
    }
  };

  // 제안한 시간을 그대로 명단에 적용한다. 원장님이 어르신을 한 분씩
  // 찾아 고치게 하면 제안이 있어도 실제로 쓰이지 않는다.
  const applyTimeAdvice = (actions) => {
    if (!actions || !actions.length) return;
    const byId = new Map(actions.map((item) => [item.passenger_id, item]));
    const outbound = tripType === TRIP_OUTBOUND;
    setPassengers((current) => current.map((passenger) => {
      const action = byId.get(passenger.id);
      if (!action) return passenger;
      const [low, high] = action.suggested_window.split('~');
      return outbound
        ? { ...passenger, dropoffStart: low, dropoffEnd: high }
        : { ...passenger, pickupStart: low, pickupEnd: high };
    }));
    setAdvice(null);
    Alert.alert(
      '시간을 수정했습니다',
      `${actions.length}분의 희망 시각을 바꿨습니다.\n`
      + '[최적 배차 계산하기] 를 다시 눌러 주세요.',
    );
    setScreen('input');
  };

  const submit = async () => {
    const message = validate();
    if (message) return Alert.alert('입력 확인', message);
    setLoading(true);
    try {
      const response = await optimizeRoutes(buildPayload());
      setResult(response);
      // 판이 바뀌었으니 지난 분석은 버린다.
      setAdvice(null);
      setScreen('results');
      try {
        const today = await fetchTodayCompletions();
        setCompletedStops(Object.fromEntries(
          today.records.map((record) => [record.passenger_id, record.completed_at]),
        ));
      } catch (_) {}
      try {
        await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({
          vehicles,
          center,
          passengers,
          pairRules,
          result: response,
        }));
      } catch (_) {
        Alert.alert('로컬 복원 저장 실패', '현재 배차는 사용할 수 있지만 앱 재실행 시 자동 복원되지 않을 수 있습니다.');
      }
    } catch (error) {
      Alert.alert('배차 최적화 실패', error.message);
    } finally {
      setLoading(false);
    }
  };

  const completeStop = async ({ stop, tripRound, vehicle }) => {
    const completionKey = stop.passenger_id;
    setSavingStops((current) => ({ ...current, [completionKey]: true }));
    try {
      // 보호자 번호는 배차 결과에 실려 온다.
      // 로컬 명단(passengers)에서 찾으면 기사님 폰에서는 명단이 없어 항상 빈 값이 된다.
      const phone = stop.guardian_phone || '';

      const record = await saveRideCompletion({
        passenger_id: stop.passenger_id,
        passenger_name: stop.name,
        vehicle_id: vehicle.vehicle_id,
        vehicle_type: vehicle.vehicle_type,
        vehicle_plate_number: vehicle.plate_number,
        trip_round: tripRound,
        scheduled_pickup: stop.estimated_pickup,
        trip_type: tripType,
        center_name: center.name,       // 🚨 [신규 장착] 센터명 백엔드로 발사!
        guardian_phone: phone           // 🚨 [신규 장착] 보호자 번호 백엔드로 발사!
      });
      
      setCompletedStops((current) => ({
        ...current,
        [completionKey]: record.completed_at,
      }));

      // 문자 발송 결과를 기사님께 알린다.
      // 전에는 발송이 실패해도 화면상 성공으로 보여, 보호자에게 갔다고 오해할 수 있었다.
      if (record.sms_sent === false) {
        Alert.alert(
          '탑승 완료 (문자 미발송)',
          `${stop.name} 어르신 기록은 저장했습니다.\n\n문자가 발송되지 않았습니다: ${record.sms_message || '사유 불명'}`,
        );
      }
    } catch (error) {
      Alert.alert('탑승 완료 저장 실패', error.message);
    } finally {
      setSavingStops((current) => {
        const next = { ...current };
        delete next[completionKey];
        return next;
      });
    }
  };

  const sendDispatch = async () => {
    if (!result) return;
    setSending(true);
    try {
      const outcome = await notifyDispatch(result);
      const lines = outcome.outcomes.map(
        (item) => `· ${item.vehicle_label}: ${item.message}`,
      );
      // 문자는 푸시와 다른 경로로 나간다. 결과도 따로 보여줘야 원장님이
      // 누가 못 받았는지 알 수 있다.
      const smsLines = outcome.sms_notices || [];
      const body = [
        lines.join('\n') || '전송할 차량이 없습니다.',
        ...(smsLines.length ? ['', '── 문자 ──', ...smsLines.map((line) => `· ${line}`)] : []),
      ].join('\n');
      Alert.alert(
        outcome.sent > 0 ? `${outcome.sent}대에 배차를 전송했습니다` : '전송된 알림이 없습니다',
        body,
      );
    } catch (error) {
      Alert.alert('배차 전송 실패', error.message);
    } finally {
      setSending(false);
    }
  };

  const downloadTodayLog = async () => {
    try {
      await Linking.openURL(getTodayCompletionExportUrl());
    } catch (_) {
      Alert.alert('다운로드 실패', '백엔드 연결 주소와 네트워크를 확인해 주세요.');
    }
  };

  // 갤럭시 하단 뒤로 가기로 앱이 그대로 종료되던 문제.
  // 화면 깊이에 따라 한 단계씩 되돌리고, 최상위에서만 종료를 허용한다.
  useEffect(() => {
    const onBack = () => {
      if (mode === 'admin') {
        // 관제 화면에서 특정 차량만 보고 있으면 먼저 전체 보기로.
        if (screen === 'results' && focusVehicleId) {
          setFocusVehicleId(null);
          return true;
        }
        // 탭을 한 단계씩 되돌린다.
        if (screen === 'results') { setScreen('input'); return true; }
        if (screen === 'input') { setScreen('vehicles'); return true; }
        // 첫 탭에서는 모드 선택으로 빠진다.
        setMode('gate');
        return true;
      }
      if (mode === 'driver') {
        // 기사 화면 내부 처리는 DriverScreen 이 먼저 가져간다.
        // 여기까지 왔다면 차량 선택 화면이므로 모드 선택으로 빠진다.
        setMode('gate');
        return true;
      }
      // 모드 선택 화면에서는 기본 동작(앱 종료)을 허용한다.
      return false;
    };

    const subscription = BackHandler.addEventListener('hardwareBackPress', onBack);
    return () => subscription.remove();
  }, [mode, screen, focusVehicleId]);

  const chooseMode = (next) => {
    setMode(next);
    AsyncStorage.setItem(MODE_KEY, next).catch(() => {});
  };
  const leaveMode = () => {
    setMode('gate');
    AsyncStorage.removeItem(MODE_KEY).catch(() => {});
  };

  // 저장소에서 모드를 읽기 전에는 아무것도 그리지 않는다.
  // 잠깐이라도 관리자 화면이 스쳐 보이면 기사님이 혼란스럽다.
  if (!fontsLoaded || mode === null) {
    // 스플래시가 아직 떠 있다. 그 뒤에서 같은 색 배경을 깔아 두어야
    // 스플래시가 내려가는 순간 흰 화면이 번쩍이지 않는다.
    return <View style={styles.bootScreen} />;
  }

  if (mode === 'gate') {
    return (
      <View style={[styles.safeArea, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
        <StatusBar barStyle="dark-content" backgroundColor="#F2F4F7" />
        <ModeGate onSelect={chooseMode} />
      </View>
    );
  }

  if (mode === 'driver') {
    return (
      <View style={[styles.safeArea, { paddingTop: insets.top }]}>
        <StatusBar barStyle="light-content" backgroundColor="#0D2540" />
        <DriverScreen onExit={leaveMode} bottomInset={insets.bottom} />
      </View>
    );
  }

  return (
    <View style={[styles.safeArea, { paddingTop: insets.top }]}>
      <StatusBar barStyle="dark-content" backgroundColor="#F2F4F7" />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.topBar}>
          <Image
            source={require('./assets/mroute-mark.png')}
            style={styles.topMark}
            resizeMode="contain"
          />
          {/* 제목이 남는 자리를 다 먹어야 오른쪽 버튼이 화면 밖으로 밀리지 않는다. */}
          <Text style={styles.appTitle} numberOfLines={1}>{brand.productName}</Text>
          <Pressable style={styles.statusPill} onPress={leaveMode} hitSlop={8}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText} numberOfLines={1}>관리자</Text>
          </Pressable>
        </View>

        <SummaryBar vehicles={vehicles} passengers={passengers} tripType={tripType} />

        <View style={styles.tabs}>
          <Pressable style={[styles.tab, screen === 'vehicles' && styles.activeTab]} onPress={() => setScreen('vehicles')}>
            <Text style={[styles.tabText, screen === 'vehicles' && styles.activeTabText]}>1. 차량 관리</Text>
          </Pressable>
          <Pressable style={[styles.tab, screen === 'input' && styles.activeTab]} onPress={() => setScreen('input')}>
            <Text style={[styles.tabText, screen === 'input' && styles.activeTabText]}>2. 대상자</Text>
          </Pressable>
          <Pressable style={[styles.tab, screen === 'results' && styles.activeTab]} onPress={() => setScreen('results')}>
            <Text style={[styles.tabText, screen === 'results' && styles.activeTabText]}>3. 배차 관제</Text>
          </Pressable>
        </View>

        {/* 등원과 하원은 명단도 동선도 다르다. 지금 무엇을 짜고 있는지
            어느 탭에 있든 한눈에 보여야 한다. */}
        <View style={styles.tripToggle}>
          {[TRIP_INBOUND, TRIP_OUTBOUND].map((value) => {
            const active = tripType === value;
            return (
              <Pressable
                key={value}
                style={[styles.tripOption, active && styles.tripOptionOn]}
                onPress={() => setTripType(value)}
              >
                <Icon
                  name={value === TRIP_INBOUND ? 'inbound' : 'outbound'}
                  size={16}
                  tint={active ? '#FFFFFF' : color.textSecondary}
                />
                <Text style={[styles.tripOptionText, active && styles.tripOptionTextOn]}>
                  {tripLabel(value)} 배차
                </Text>
              </Pressable>
            );
          })}
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {screen === 'vehicles' ? (
            <>
              <Text style={styles.sectionTitle}>차량 관리</Text>
              <Text style={styles.sectionCaption}>보유 차량을 자유롭게 추가하고 실제 최대 탑승 인원을 설정하세요.</Text>
              <View style={styles.capacitySummary}>
                <Text style={styles.capacityLabel}>등록 차량 {vehicles.length}대</Text>
                <Text style={styles.capacityValue}>2회 최대 {maxPassengerCapacity}명</Text>
              </View>
              {vehicles.map((vehicle, index) => (
                <VehicleForm
                  key={vehicle.localId}
                  value={vehicle}
                  index={index}
                  onChange={(next) => updateVehicle(index, next)}
                  onRemove={() => setVehicles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                />
              ))}
              <Pressable style={styles.addButton} onPress={() => setVehicles((current) => [...current, emptyVehicle()])}>
                <Text style={styles.addButtonText}>＋ 차량 추가</Text>
              </Pressable>
              <Pressable style={styles.nextButton} onPress={() => setScreen('input')}>
                <Text style={styles.optimizeButtonText}>대상자 입력으로</Text>
                <Icon name="chevronRight" size={20} tint="#FFFFFF" />
              </Pressable>

              <View style={styles.driverPanelSpacing}>
                <DriverPushPanel vehicles={vehicles} />
              </View>
            </>
          ) : screen === 'input' ? (
            <>
              <Text style={styles.sectionTitle}>센터 정보</Text>
              {/* v2.0 부터 자차 송영의 마지막 회차는 센터가 아니라 기사님 자택에서 끝난다.
                  '모두 센터로 복귀' 는 이제 틀린 말이다. */}
              <Text style={styles.sectionCaption}>
                자차 송영 차량의 마지막 회차는 기사님 자택(차고지)으로 퇴근하도록 자동 최적화됩니다.
              </Text>
              <View style={styles.centerCard}>
                <Text style={styles.inputLabel}>센터명</Text>
                <TextInput style={styles.input} value={center.name} onChangeText={(text) => setCenter({ ...center, name: text })} placeholder="센터명" />
                <Text style={styles.inputLabel}>센터 주소</Text>
                <TouchableOpacity
                  style={{ backgroundColor: '#0BA38E', padding: 12, borderRadius: 8, marginTop: 5, marginBottom: 8 }}
                  onPress={() => setIsCenterAddressModalOpen(true)}
                >
                  <Text style={{ color: 'white', textAlign: 'center', fontWeight: 'bold' }}>
                    {center.address ? '주소 다시 검색하기' : '정확한 센터 주소 찾기'}
                  </Text>
                </TouchableOpacity>

                <TextInput style={styles.input} value={center.address} onChangeText={(text) => setCenter({ ...center, address: text })} placeholder="도로명 주소" />
              </View>
              <AddressSearch
                visible={isCenterAddressModalOpen}
                onSelected={(address) => {
                  setCenter({ ...center, address, latitude: '', longitude: '' });
                  setIsCenterAddressModalOpen(false);
                }}
                onClose={() => setIsCenterAddressModalOpen(false)}
              />

              <View style={styles.sectionRow}>
                {/* 글자가 길어져도 오른쪽 버튼을 밀지 않도록 이쪽이 줄어든다. */}
                <View style={styles.sectionHeading}>
                  <Text style={styles.sectionTitle}>어르신 정보</Text>
                  <Text style={styles.sectionCaption}>출석 {passengerCount}명 · 등록 차량 2회 최대 {maxPassengerCapacity}명</Text>
                </View>
              </View>

              {/* 엑셀 한 줄. 양식을 먼저 받고 채워서 올리는 순서라 왼쪽에 둔다. */}
              <View style={styles.excelRow}>
                <Pressable
                  style={[styles.excelButton, styles.excelGhost, excelBusy && styles.excelBusy]}
                  onPress={getTemplate}
                  disabled={excelBusy}
                >
                  <Icon name="excel" size={16} tint={color.teal} />
                  <Text style={styles.excelGhostText} numberOfLines={1}>표준 양식 받기</Text>
                </Pressable>
                <Pressable
                  style={[styles.excelButton, styles.excelSolid, excelBusy && styles.excelBusy]}
                  onPress={importExcel}
                  disabled={excelBusy}
                >
                  <Icon name="excel" size={16} tint="#FFFFFF" />
                  <Text style={styles.excelSolidText} numberOfLines={1}>엑셀 불러오기</Text>
                </Pressable>
              </View>
              <Text style={styles.excelHint}>
                양식을 받아 채운 뒤 올리시면 명단이 한 번에 들어갑니다.
                {'\n'}빠진 값이 있으면 몇 번째 줄인지 알려 드립니다.
              </Text>
              {!!excelName && <Text style={styles.fileName}>불러온 파일: {excelName}</Text>}

              {passengers.map((passenger, index) => (
                <PassengerForm
                  key={passenger.localId}
                  value={passenger}
                  index={index}
                  onChange={(next) => updatePassenger(index, next)}
                  onRemove={() => setPassengers((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                />
              ))}

              <Pressable style={styles.addButton} onPress={() => setPassengers((current) => [...current, emptyPassenger()])}>
                <Text style={styles.addButtonText}>＋ 어르신 추가</Text>
              </Pressable>

              <PairRuleEditor
                passengers={passengers}
                rules={pairRules}
                onChange={setPairRules}
              />
              <Text style={styles.hint}>주소 좌표가 없으면 백엔드의 카카오 REST API 키로 자동 변환합니다.</Text>
              {/* 계산 버튼이 화면 아래에 떠 있어 그 밑이 가린다. 그만큼 자리를 비운다. */}
              <View style={{ height: ctaClearance }} />
            </>
          ) : !result ? (
            <View style={styles.emptyResult}>
              <Icon
                name={tripType === TRIP_OUTBOUND ? 'outbound' : 'inbound'}
                size={28}
                tint={color.textSecondary}
              />
              <Text style={styles.emptyResultTitle}>
                {tripLabel(tripType)} 배차를 아직 계산하지 않았습니다
              </Text>
              <Text style={styles.emptyResultBody}>
                [2. 대상자] 에서 {tripLabel(tripType)} 탑승 여부를 확인한 뒤
                {'\n'}아래 [최적 배차 계산하기] 를 눌러 주세요.
              </Text>
              <Pressable style={styles.emptyResultButton} onPress={() => setScreen('input')}>
                <Text style={styles.emptyResultButtonText}>대상자 확인하러 가기</Text>
              </Pressable>
            </View>
          ) : (
            <>
              <View style={styles.resultsHeading}>
                <View>
                  <Text style={styles.sectionTitle}>오늘의 {tripLabel(tripType)} 관제</Text>
                  <Text style={styles.sectionCaption}>차량별 픽업 순서와 도착 예정 시각</Text>
                </View>
                <Pressable onPress={() => setScreen('input')}><Text style={styles.editLink}>입력 수정</Text></Pressable>
              </View>

              {/* 폴링이 살아 있는지 눈으로 확인할 수 있어야 한다.
                  시각이 멈춰 있으면 서버와 끊긴 것이고, 눌러서 즉시 다시 맞출 수 있다. */}
              <Pressable style={styles.syncBar} onPress={syncLiveState} disabled={syncing}>
                <Icon name="refresh" size={13} tint="#07705F" />
                <Text style={styles.syncText}>
                  {syncing
                    ? '갱신 중...'
                    : syncedAt
                      ? `${formatClock(syncedAt)} 기준 · 눌러서 새로고침`
                      : '아직 갱신되지 않았습니다 · 눌러서 새로고침'}
                </Text>
              </Pressable>
              {!!focusVehicleId && (
                <Pressable style={styles.focusBanner} onPress={() => setFocusVehicleId(null)}>
                  <Text style={styles.focusBannerText}>
                    내 차량 동선만 보는 중 · 눌러서 전체 보기
                  </Text>
                </Pressable>
              )}
              <View style={styles.actionRow}>
                <Pressable
                  style={[styles.dispatchButton, sending && styles.disabledButton]}
                  onPress={sendDispatch}
                  disabled={sending}
                >
                  {sending
                    ? <ActivityIndicator color="#FFFFFF" />
                    : (
                      <>
                        <Icon name="send" size={15} tint="#FFFFFF" />
                        <Text style={styles.exportButtonText}>배차 전송</Text>
                      </>
                    )}
                </Pressable>
                <Pressable style={styles.exportButton} onPress={downloadTodayLog}>
                  <Icon name="report" size={15} tint={color.deepNavy} />
                  <Text style={styles.secondaryButtonText}>송영 일지</Text>
                </Pressable>
              </View>
              <VehicleResults
                result={result}
                vehicles={vehicles}
                completedStops={completedStops}
                savingStops={savingStops}
                onComplete={completeStop}
                focusVehicleId={focusVehicleId}
                acks={acks}
                advice={advice}
                advising={advising}
                onAskAdvice={askForAdvice}
                onApplyTimeAdvice={applyTimeAdvice}
              />
            </>
          )}
        </ScrollView>

        {/* 어르신이 스무 명쯤 되면 계산 버튼까지 스크롤을 한참 내려야 했다.
            스크롤 위에 띄워 어디서든 바로 누를 수 있게 한다.
            대상자 탭에서만 보인다. 관제 화면에는 이미 자기 버튼들이 있다. */}
        {screen === 'input' && (
          <View
            style={[styles.fabWrap, { paddingBottom: insets.bottom + FAB_GAP }]}
            pointerEvents="box-none"
          >
            <Pressable
              style={[styles.fab, loading && styles.disabledButton]}
              onPress={submit}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#FFFFFF" />
                : (
                  <>
                    <Icon name="route" size={20} tint="#FFFFFF" />
                    <Text style={styles.fabText}>최적 배차 계산하기</Text>
                  </>
                )}
            </Pressable>
          </View>
        )}
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  safeArea: { flex: 1, backgroundColor: '#F2F4F7' },
  bootScreen: { flex: 1, backgroundColor: color.deepNavy },
  topBar: { paddingHorizontal: 18, paddingTop: 10, paddingBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 8 },
  topMark: { width: 26, height: 26 },
  appTitle: { flex: 1, minWidth: 0, color: '#0D2540', fontSize: 17, fontWeight: '700' },
  // flexShrink: 0 이 없으면 제목이 길 때 이 버튼이 화면 밖으로 밀려 잘린다.
  statusPill: { flexShrink: 0, flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 999, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC' },
  statusDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#3BB273', marginRight: 5 },
  statusText: { color: '#667085', fontSize: 12, fontWeight: '600' },
  // 선택된 쪽은 Deep Navy 로 채우고, 나머지는 흰 배경에 테두리만 둔다.
  tripToggle: { flexDirection: 'row', gap: 8, marginHorizontal: 18, marginBottom: 12 },
  tripOption: { flex: 1, flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', paddingVertical: 11, borderRadius: 12, borderWidth: 1, borderColor: '#E4E7EC', backgroundColor: '#FFFFFF' },
  tripOptionOn: { backgroundColor: '#0D2540', borderColor: '#0D2540' },
  tripOptionText: { color: '#667085', fontSize: 14, fontWeight: '700' },
  tripOptionTextOn: { color: '#FFFFFF' },
  tabs: { marginHorizontal: 18, backgroundColor: '#E4E7EC', borderRadius: 13, padding: 4, flexDirection: 'row' },
  tab: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: 10 },
  activeTab: { backgroundColor: '#FFFFFF' },
  tabText: { color: '#667085', fontSize: 13, fontWeight: '800' },
  activeTabText: { color: '#0BA38E' },
  disabledText: { opacity: 0.35 },
  content: { padding: 18, paddingBottom: 50 },
  sectionTitle: { color: '#0D2540', fontSize: 18, fontWeight: '900' },
  sectionCaption: { color: '#667085', fontSize: 12, marginTop: 3, marginBottom: 12 },
  centerCard: { backgroundColor: '#FFFFFF', padding: 16, borderRadius: 18, borderWidth: 1, borderColor: '#E4E7EC', marginBottom: 24 },
  inputLabel: { color: '#667085', fontWeight: '700', fontSize: 13, marginBottom: 6 },
  input: { backgroundColor: '#F8F9FB', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 12, paddingHorizontal: 13, height: 48, fontSize: 15, color: '#0D2540', marginBottom: 12 },
  sectionRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  // 제목이 길어져도 버튼을 밀지 않도록 이쪽만 줄어들게 한다.
  // minWidth 0 이 없으면 flex 자식이 내용 너비 아래로는 줄지 않아
  // 옆 버튼의 글자가 잘린다. 예전에 '엑셀 불러오기' 가 잘리던 이유다.
  sectionHeading: { flex: 1, minWidth: 0 },
  excelRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  excelButton: {
    flex: 1,
    // 이 값이 없으면 아이콘과 글자가 세로로 쌓인다. RN 의 기본은 column 이다.
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderRadius: 11,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  excelGhost: { backgroundColor: '#E6F7F4', borderWidth: 1, borderColor: '#B7E4DA' },
  excelSolid: { backgroundColor: '#07705F' },
  excelBusy: { opacity: 0.55 },
  excelGhostText: { color: '#07705F', fontWeight: '800', fontSize: 13 },
  excelSolidText: { color: '#FFFFFF', fontWeight: '800', fontSize: 13 },
  excelHint: { color: '#7C8D87', fontSize: 12, lineHeight: 18, marginBottom: 10 },
  fileName: { color: '#0BA38E', fontSize: 11, marginTop: -7, marginBottom: 12 },
  addButton: { borderWidth: 1.5, borderStyle: 'dashed', borderColor: '#98A2B3', borderRadius: 14, paddingVertical: 14, alignItems: 'center', marginBottom: 14 },
  addButtonText: { color: '#667085', fontWeight: '800' },
  // 스크롤 위에 떠 있는 계산 버튼.
  // wrap 은 터치를 통과시키고(box-none) 버튼만 누르게 한다. 안 그러면
  // 버튼 옆 빈 공간이 스크롤을 먹는다.
  // 안드로이드는 화면 맨 아래를 시스템 바(뒤로가기·홈)가 차지한다.
  // 여기 맞춰 띄우지 않으면 버튼이 그 밑에 깔려 눌리지 않는다.
  fabWrap: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: 18, alignItems: 'center',
  },
  fab: { flexDirection: 'row', gap: 8, width: '100%', maxWidth: 520, backgroundColor: '#0BA38E', borderRadius: 999, height: FAB_HEIGHT, alignItems: 'center', justifyContent: 'center', shadowColor: '#0D2540', shadowOpacity: 0.28, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 8 },
  fabText: { color: '#FFFFFF', fontSize: 17, fontWeight: '900' },
  optimizeButton: { backgroundColor: '#0BA38E', borderRadius: 15, height: 56, alignItems: 'center', justifyContent: 'center', shadowColor: '#0BA38E', shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 4 },
  nextButton: { flexDirection: 'row', gap: 6, backgroundColor: '#07705F', borderRadius: 15, height: 54, alignItems: 'center', justifyContent: 'center' },
  optimizeButtonText: { color: '#FFFFFF', fontSize: 17, fontWeight: '900' },
  disabledButton: { opacity: 0.6 },
  hint: { color: '#98A2B3', fontSize: 11, textAlign: 'center', marginTop: 10 },
  emptyResult: { alignItems: 'center', backgroundColor: '#FFFFFF', borderRadius: 12, borderWidth: 1, borderColor: '#E4E7EC', paddingVertical: 32, paddingHorizontal: 24 },
  emptyResultTitle: { color: '#0D2540', fontSize: 16, fontWeight: '700', marginTop: 12, textAlign: 'center' },
  emptyResultBody: { color: '#667085', fontSize: 13, lineHeight: 20, marginTop: 8, textAlign: 'center' },
  emptyResultButton: { backgroundColor: '#0D2540', borderRadius: 12, paddingHorizontal: 20, paddingVertical: 12, marginTop: 18 },
  emptyResultButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  resultsHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  editLink: { color: '#0BA38E', fontWeight: '800', fontSize: 13 },
  capacitySummary: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#E9F7EF', borderRadius: 14, padding: 14, marginBottom: 14 },
  capacityLabel: { color: '#237B4B', fontWeight: '800' },
  capacityValue: { color: '#237B4B', fontSize: 16, fontWeight: '900' },
  actionRow: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  // 보조 동작이다. 채우지 않고 테두리만 둬서 주 동작과 구별되게 한다.
  exportButton: { flex: 1, flexDirection: 'row', gap: 6, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#E4E7EC', borderRadius: 12, paddingVertical: 13, alignItems: 'center', justifyContent: 'center' },
  dispatchButton: { flex: 1, flexDirection: 'row', gap: 6, backgroundColor: '#0D2540', borderRadius: 12, paddingVertical: 13, alignItems: 'center', justifyContent: 'center' },
  driverPanelSpacing: { marginTop: 18 },
  syncBar: { alignSelf: 'flex-start', backgroundColor: '#E6F7F4', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, marginBottom: 12 },
  syncText: { color: '#07705F', fontSize: 12, fontWeight: '700' },
  focusBanner: { backgroundColor: '#E9F7EF', borderWidth: 1, borderColor: '#6ED6C1', borderRadius: 12, paddingVertical: 10, alignItems: 'center', marginBottom: 12 },
  focusBannerText: { color: '#237B4B', fontWeight: '800', fontSize: 12.5 },
  exportButtonText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },
  secondaryButtonText: { color: '#0D2540', fontWeight: '700', fontSize: 14 },
});