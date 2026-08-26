/**
 * push.js 안전 가드 검증.
 *
 * expo-constants / expo-device / react-native / expo-notifications 를 가짜로 갈아끼워
 * 웹 · 시뮬레이터 · Expo Go · 개발빌드(APK) 네 환경을 각각 재현한다.
 *
 * 확인 대상:
 *  1) 어느 환경에서도 push.js import 자체가 터지지 않는가
 *  2) listenForDispatchTaps 가 절대 throw 하지 않고 항상 함수를 돌려주는가
 *  3) 지원 불가 환경에서 expo-notifications 를 아예 require 하지 않는가 (레드박스 방지)
 */
const path = require('path');
const babel = require('@babel/core');
const fs = require('fs');
const Module = require('module');

const FRONTEND = 'C:/Users/HOME/Documents/Daycare_App/frontend';

let notificationsRequired = false;
let fakeEnv = {};

const FAKES = {
  'expo-constants': () => ({
    __esModule: true,
    default: {
      executionEnvironment: fakeEnv.executionEnvironment,
      expoConfig: { extra: { eas: { projectId: fakeEnv.projectId } } },
      easConfig: null,
    },
    ExecutionEnvironment: { Bare: 'bare', Standalone: 'standalone', StoreClient: 'storeClient' },
  }),
  'expo-device': () => ({ isDevice: fakeEnv.isDevice, deviceName: '테스트폰', modelName: 'SM-S911N' }),
  'react-native': () => ({ Platform: { OS: fakeEnv.os } }),
  'expo-notifications': () => {
    // Expo Go 안드로이드에서 레드박스를 유발하는 지점을 모사한다.
    notificationsRequired = true;
    if (fakeEnv.executionEnvironment === 'storeClient' && fakeEnv.os === 'android') {
      console.error('expo-notifications: Android Push ... removed from Expo Go');
    }
    return {
      setNotificationHandler: () => {},
      getLastNotificationResponseAsync: async () => null,
      addNotificationResponseReceivedListener: () => ({ remove() {} }),
    };
  },
};

function loadPushModule() {
  const file = path.join(FRONTEND, 'src', 'push.js');
  const code = babel.transformSync(fs.readFileSync(file, 'utf8'), {
    filename: file,
    presets: [['babel-preset-expo', { jsxRuntime: 'automatic' }]],
    plugins: [require.resolve('@babel/plugin-transform-modules-commonjs')],
    babelrc: false, configFile: false,
  }).code;

  const mod = new Module(file, null);
  mod.filename = file;
  mod.paths = Module._nodeModulePaths(path.dirname(file));
  const origRequire = mod.require.bind(mod);
  mod.require = (id) => {
    if (FAKES[id]) return FAKES[id]();
    if (id === './api') return { registerDriverDevice: async () => ({}) };
    return origRequire(id);
  };
  mod._compile(code, file);
  return mod.exports;
}

const SCENARIOS = [
  { label: '웹 (관제 PC)',        os: 'web',     isDevice: true,  executionEnvironment: 'bare',        projectId: 'abc', expectSupported: false, expectReason: 'web' },
  { label: '시뮬레이터',           os: 'android', isDevice: false, executionEnvironment: 'bare',        projectId: 'abc', expectSupported: false, expectReason: 'simulator' },
  { label: 'Expo Go (안드로이드)', os: 'android', isDevice: true,  executionEnvironment: 'storeClient', projectId: 'abc', expectSupported: false, expectReason: 'expoGo' },
  { label: 'projectId 없음',      os: 'android', isDevice: true,  executionEnvironment: 'bare',        projectId: undefined, expectSupported: false, expectReason: 'noProjectId' },
  { label: '개발빌드 APK',         os: 'android', isDevice: true,  executionEnvironment: 'bare',        projectId: 'abc', expectSupported: true,  expectReason: null },
];

let failures = 0;
const check = (label, ok, detail) => {
  if (!ok) failures++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' -> ' + detail : ''}`);
};

for (const scenario of SCENARIOS) {
  console.log(`--- ${scenario.label} ---`);
  fakeEnv = scenario;
  notificationsRequired = false;

  let push;
  try {
    push = loadPushModule();
    check('import 시 예외 없음', true);
  } catch (error) {
    check('import 시 예외 없음', false, error.message.slice(0, 80));
    continue;
  }

  check('import 만으로는 expo-notifications 를 require 하지 않음', !notificationsRequired);

  const env = push.getPushEnvironment();
  check(`환경 판정 = ${scenario.expectReason ?? '지원됨'}`,
    env.supported === scenario.expectSupported && env.reason === scenario.expectReason,
    `supported=${env.supported} reason=${env.reason}`);

  let cleanup;
  try {
    cleanup = push.listenForDispatchTaps(() => {});
    check('listenForDispatchTaps 예외 없음', true);
  } catch (error) {
    check('listenForDispatchTaps 예외 없음', false, error.message.slice(0, 80));
    continue;
  }
  check('정리 함수 반환', typeof cleanup === 'function', typeof cleanup);
  try { cleanup(); check('정리 함수 호출 안전', true); }
  catch (e) { check('정리 함수 호출 안전', false, e.message); }

  if (!scenario.expectSupported) {
    check('지원 불가 환경에서 expo-notifications 미로드 (레드박스 방지)', !notificationsRequired);
  } else {
    check('지원 환경에서는 정상 로드', notificationsRequired);
  }
}

console.log('');
console.log(failures ? `실패 ${failures}건` : '전체 통과');
process.exit(failures ? 1 : 0);
