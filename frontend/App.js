import AsyncStorage from '@react-native-async-storage/async-storage';
import { useFonts } from 'expo-font';
import * as SplashScreen from 'expo-splash-screen';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Text from './src/ui/Text';
import { brand, color } from './src/theme';
import Icon from './src/ui/Icon';
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import {
  API_URL,
  COMPLETION_POLL_MS,
  fetchCompletedStopMap,
  fetchTodayAcks,
  fetchTodayCompletions,
  fetchTodayDispatch,
  getTodayCompletionExportUrl,
  notifyDispatch,
  optimizeRoutes,
  saveRideCompletion,
} from './src/api';
import PassengerForm from './src/components/PassengerForm';
import VehicleForm from './src/components/VehicleForm';
import VehicleResults from './src/components/VehicleResults';
import { pickPassengerExcel } from './src/excel';
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
  pickupStart: '08:00',
  pickupEnd: '08:30',
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
  // 자차 송영. 기본은 센터 출발.
  driverPhone: '',
  startType: 'center',
  startAddress: '',
  startLatitude: '',
  startLongitude: '',
});

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
function formatClock(value) {
  return value.toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
}

const STORAGE_KEY = 'daycare-routing:last-session:v1';
// 기사님 폰은 한 번 고르면 계속 기사 화면으로 열려야 한다.
const MODE_KEY = 'daycare-routing:mode:v1';

// 준비가 끝날 때까지 스플래시를 내리지 않는다.
SplashScreen.preventAutoHideAsync().catch(() => {});

export default function App() {
  const [fontsLoaded] = useFonts({
    'Pretendard-Regular': require('./assets/fonts/Pretendard-Regular.ttf'),
    'Pretendard-Medium': require('./assets/fonts/Pretendard-Medium.ttf'),
    'Pretendard-SemiBold': require('./assets/fonts/Pretendard-SemiBold.ttf'),
    'Pretendard-Bold': require('./assets/fonts/Pretendard-Bold.ttf'),
  });
  const [screen, setScreen] = useState('vehicles');
  const [vehicles, setVehicles] = useState([emptyVehicle()]);
  const [center, setCenter] = useState({
    name: '주야간보호센터', address: '', latitude: '', longitude: '',
  });
  const [passengers, setPassengers] = useState([emptyPassenger()]);
  const [excelName, setExcelName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
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
          if (session.result) {
            setResult(session.result);
            setScreen('results');
          }
        }
      } catch (_) {}
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
      try {
        const savedMode = await AsyncStorage.getItem(MODE_KEY);
        setMode(savedMode === 'admin' || savedMode === 'driver' ? savedMode : 'gate');
      } catch (_) {
        setMode('gate');
      }
      setRestored(true);
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
      JSON.stringify({ vehicles, center, passengers, pairRules, result }),
    ).catch(() => {});
  }, [restored, vehicles, center, passengers, pairRules, result]);

  // 탑승 완료와 배차 확인은 서로를 기다리지 않는다.
  // 예전에는 Promise.all 이라 탑승 완료 조회가 한 번 실패하면 배차 확인까지
  // 통째로 버려졌다. 그러면 주기마다 조용히 같은 실패를 반복하면서 화면은
  // 영원히 '확인 대기'로 남는다.
  const syncLiveState = useCallback(async () => {
    setSyncing(true);
    try {
      const [completions, ackList] = await Promise.allSettled([
        fetchCompletedStopMap(),
        fetchTodayAcks(),
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
  }, []);

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
  }, [screen, syncLiveState]);

  useEffect(() => {
    if (fontsLoaded && mode !== null) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded, mode]);

  const passengerCount = useMemo(
    () => passengers.filter(
      (passenger) => (passenger.name || passenger.address) && passenger.attending !== false,
    ).length,
    [passengers],
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

  const importExcel = async () => {
    try {
      const imported = await pickPassengerExcel();
      if (!imported) return;
      setPassengers(imported.passengers);
      setExcelName(imported.fileName);
      Alert.alert('불러오기 완료', `${imported.passengers.length}명의 정보를 불러왔습니다.`);
    } catch (error) {
      Alert.alert('엑셀 읽기 실패', error.message);
    }
  };

  const validate = () => {
    if (!vehicles.length) return '차량을 한 대 이상 등록해 주세요.';
    const plateNumbers = new Set();
    for (const [index, vehicle] of vehicles.entries()) {
      const capacity = Number(vehicle.capacity);
      if (!vehicle.vehicleType.trim() || !vehicle.plateNumber.trim()) return `${index + 1}번 차량의 차종과 차량번호를 입력해 주세요.`;
      if (!Number.isInteger(capacity) || capacity < 1 || capacity > 100) return `${vehicle.plateNumber} 차량의 정원은 1~100 사이의 정수여야 합니다.`;
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
    const active = entered.filter((item) => item.attending !== false);
    if (!active.length) return '출석한 어르신이 없습니다. 출석 토글을 확인해 주세요.';
    if (active.length > maxPassengerCapacity) return `등록 차량의 2회 운행 최대 수용 인원은 ${maxPassengerCapacity}명입니다.`;
    for (const [index, passenger] of active.entries()) {
      if (!passenger.name.trim() || !passenger.address.trim()) return `${index + 1}번 어르신의 이름과 주소를 입력해 주세요.`;
      if (!HHMM.test(passenger.pickupStart) || !HHMM.test(passenger.pickupEnd)) return `${passenger.name}님의 시간을 HH:MM 형식으로 입력해 주세요.`;
      if (passenger.pickupStart > passenger.pickupEnd) return `${passenger.name}님의 픽업 하한이 상한보다 늦습니다.`;
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

  const submit = async () => {
    const message = validate();
    if (message) return Alert.alert('입력 확인', message);
    setLoading(true);
    try {
      const active = passengers
        .filter((item) => item.name || item.address)
        .filter((item) => item.attending !== false);
      const activeIds = new Set(active.map((item) => item.id));
      const liveRules = pairRules.filter(
        (rule) => rule.passengerIds.every((id) => activeIds.has(id)),
      );
      const asRule = (rule) => ({ passenger_ids: rule.passengerIds });

      const response = await optimizeRoutes({
        center: asLocation(center),
        vehicles: vehicles.map((vehicle) => ({
          id: vehicle.id,
          vehicle_type: vehicle.vehicleType.trim(),
          plate_number: vehicle.plateNumber.trim(),
          driver_name: (vehicle.driverName || '').trim() || null,
          driver_phone: (vehicle.driverPhone || '').trim() || null,
          capacity: Number(vehicle.capacity),
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
          attending: true,
          pickup_start: item.pickupStart,
          pickup_end: item.pickupEnd,
          wheelchair: item.wheelchair,
          guardian_phone: (item.guardianPhone || '').trim(),
          passenger_phone: (item.passengerPhone || '').trim() || null,
          // 기존 명단에는 없던 값이다. 없으면 보호자에게 걸고, 알림은 켠 것으로 본다.
          primary_contact: item.primaryContact === 'self' ? 'self' : 'guardian',
          sms_opt_in: item.smsOptIn !== false,
        })),
        forbidden_pairs: liveRules.filter((rule) => rule.kind === 'forbidden').map(asRule),
        required_pairs: liveRules.filter((rule) => rule.kind === 'required').map(asRule),
      });
      setResult(response);
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
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="dark-content" backgroundColor="#F2F4F7" />
        <ModeGate onSelect={chooseMode} />
      </SafeAreaView>
    );
  }

  if (mode === 'driver') {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" backgroundColor="#0BA38E" />
        <DriverScreen onExit={leaveMode} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" backgroundColor="#F2F4F7" />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.topBar}>
          <View>
            <Text style={styles.eyebrow}>{brand.descriptor}</Text>
            <Text style={styles.appTitle}>{brand.productName}</Text>
          </View>
          <Pressable style={styles.statusPill} onPress={leaveMode}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>관리자 모드 · 탭하여 변경</Text>
          </Pressable>
        </View>

        <SummaryBar vehicles={vehicles} passengers={passengers} />

        <View style={styles.tabs}>
          <Pressable style={[styles.tab, screen === 'vehicles' && styles.activeTab]} onPress={() => setScreen('vehicles')}>
            <Text style={[styles.tabText, screen === 'vehicles' && styles.activeTabText]}>1. 차량 관리</Text>
          </Pressable>
          <Pressable style={[styles.tab, screen === 'input' && styles.activeTab]} onPress={() => setScreen('input')}>
            <Text style={[styles.tabText, screen === 'input' && styles.activeTabText]}>2. 대상자</Text>
          </Pressable>
          <Pressable style={[styles.tab, screen === 'results' && styles.activeTab]} onPress={() => result && setScreen('results')}>
            <Text style={[styles.tabText, screen === 'results' && styles.activeTabText, !result && styles.disabledText]}>3. 배차 관제</Text>
          </Pressable>
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
              <Text style={styles.sectionCaption}>모든 차량은 센터에서 출발하고 센터로 복귀합니다.</Text>
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
                <View>
                  <Text style={styles.sectionTitle}>어르신 정보</Text>
                  <Text style={styles.sectionCaption}>출석 {passengerCount}명 · 등록 차량 2회 최대 {maxPassengerCapacity}명</Text>
                </View>
                <Pressable style={styles.excelButton} onPress={importExcel}>
                  <Icon name="excel" size={15} tint={color.teal} />
                  <Text style={styles.excelButtonText}>엑셀 불러오기</Text>
                </Pressable>
              </View>
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
              <View style={styles.fabSpacer} />
            </>
          ) : (
            <>
              <View style={styles.resultsHeading}>
                <View>
                  <Text style={styles.sectionTitle}>오늘의 배차 관제</Text>
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
                  <Icon name="report" size={15} tint="#FFFFFF" />
                  <Text style={styles.exportButtonText}>송영 일지</Text>
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
              />
            </>
          )}
        </ScrollView>

        {/* 어르신이 스무 명쯤 되면 계산 버튼까지 스크롤을 한참 내려야 했다.
            스크롤 위에 띄워 어디서든 바로 누를 수 있게 한다.
            대상자 탭에서만 보인다. 관제 화면에는 이미 자기 버튼들이 있다. */}
        {screen === 'input' && (
          <View style={styles.fabWrap} pointerEvents="box-none">
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  safeArea: { flex: 1, backgroundColor: '#F2F4F7' },
  bootScreen: { flex: 1, backgroundColor: color.deepNavy },
  topBar: { paddingHorizontal: 18, paddingTop: 14, paddingBottom: 11, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  eyebrow: { color: '#0BA38E', fontSize: 10, fontWeight: '900', letterSpacing: 1.4 },
  appTitle: { color: '#0D2540', fontSize: 24, fontWeight: '900', marginTop: 1 },
  statusPill: { maxWidth: 160, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 9, paddingVertical: 6, borderRadius: 20, backgroundColor: '#FFFFFF' },
  statusDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#3BB273', marginRight: 5 },
  statusText: { color: '#667085', fontSize: 9, flexShrink: 1 },
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
  excelButton: { backgroundColor: '#E6F7F4', borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9 },
  excelButtonText: { color: '#07705F', fontWeight: '800', fontSize: 12 },
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
    paddingBottom: Platform.select({ android: 96, ios: 34, default: 24 }),
  },
  fab: { flexDirection: 'row', gap: 8, width: '100%', maxWidth: 520, backgroundColor: '#0BA38E', borderRadius: 999, height: 58, alignItems: 'center', justifyContent: 'center', shadowColor: '#0D2540', shadowOpacity: 0.28, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 8 },
  fabText: { color: '#FFFFFF', fontSize: 17, fontWeight: '900' },
  // 버튼이 가리는 만큼 스크롤 끝에 자리를 비운다. 안 그러면 마지막 항목이 가린다.
  fabSpacer: { height: Platform.select({ android: 168, ios: 106, default: 96 }) },
  optimizeButton: { backgroundColor: '#0BA38E', borderRadius: 15, height: 56, alignItems: 'center', justifyContent: 'center', shadowColor: '#0BA38E', shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 4 },
  nextButton: { flexDirection: 'row', gap: 6, backgroundColor: '#07705F', borderRadius: 15, height: 54, alignItems: 'center', justifyContent: 'center' },
  optimizeButtonText: { color: '#FFFFFF', fontSize: 17, fontWeight: '900' },
  disabledButton: { opacity: 0.6 },
  hint: { color: '#98A2B3', fontSize: 11, textAlign: 'center', marginTop: 10 },
  resultsHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  editLink: { color: '#0BA38E', fontWeight: '800', fontSize: 13 },
  capacitySummary: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#E9F7EF', borderRadius: 14, padding: 14, marginBottom: 14 },
  capacityLabel: { color: '#237B4B', fontWeight: '800' },
  capacityValue: { color: '#237B4B', fontSize: 16, fontWeight: '900' },
  actionRow: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  exportButton: { flex: 1, backgroundColor: '#0BA38E', borderRadius: 13, paddingVertical: 13, alignItems: 'center' },
  dispatchButton: { flex: 1, backgroundColor: '#0BA38E', borderRadius: 13, paddingVertical: 13, alignItems: 'center', justifyContent: 'center' },
  driverPanelSpacing: { marginTop: 18 },
  syncBar: { alignSelf: 'flex-start', backgroundColor: '#E6F7F4', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7, marginBottom: 12 },
  syncText: { color: '#07705F', fontSize: 12, fontWeight: '700' },
  focusBanner: { backgroundColor: '#E9F7EF', borderWidth: 1, borderColor: '#6ED6C1', borderRadius: 12, paddingVertical: 10, alignItems: 'center', marginBottom: 12 },
  focusBannerText: { color: '#237B4B', fontWeight: '800', fontSize: 12.5 },
  exportButtonText: { color: '#FFFFFF', fontWeight: '900', fontSize: 14 },
});