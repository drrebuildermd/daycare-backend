/**
 * 엑셀 업로드 검사 문구 검증.
 *
 * 원장님이 34줄짜리 명단을 올렸을 때 "뭔가 잘못됐습니다" 로 끝나면
 * 어디를 고쳐야 할지 알 수 없다. 몇 번째 줄 누구인지 말해야 한다.
 *
 * 실행: frontend 폴더에서  node test_excel_validate.js
 */
const babel = require('@babel/core');
const fs = require('fs');

const code = babel.transformSync(fs.readFileSync('src/excelValidate.js', 'utf8'), {
  filename: 'excelValidate.js',
  presets: ['babel-preset-expo'],
  plugins: ['@babel/plugin-transform-modules-commonjs'],
  babelrc: false, configFile: false,
}).code;
const mod = { exports: {} };
new Function('require', 'module', 'exports', code)(require, mod, mod.exports);
const { checkRow } = mod.exports;

const failures = [];
const check = (label, ok, detail) => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' -> ' + detail : ''}`);
  if (!ok) failures.push(label);
};

const row = (over = {}) => ({
  name: '김마중',
  address: '창원시 의창구 중앙대로 100',
  pickupStart: '08:00',
  pickupEnd: '08:30',
  dropoffStart: '',
  dropoffEnd: '',
  ...over,
});

console.log('=== 1. 멀쩡한 줄은 통과한다 ===');
check('필수값이 다 있으면 문제 없음', checkRow(row(), 2).length === 0,
  JSON.stringify(checkRow(row(), 2)));
check('하차 시각은 비워도 된다 (서버가 등원 +8시간으로 채운다)',
  checkRow(row({ dropoffStart: '', dropoffEnd: '' }), 2).length === 0);
check('하차 시각을 둘 다 넣어도 된다',
  checkRow(row({ dropoffStart: '16:00', dropoffEnd: '16:40' }), 2).length === 0);

console.log('');
console.log('=== 2. 줄 번호와 이름이 문구에 들어간다 (핵심) ===');
const noAddress = checkRow(row({ name: '박온케어', address: '' }), 4);
check('한 건만 잡힌다', noAddress.length === 1, JSON.stringify(noAddress));
check('줄 번호가 들어간다', noAddress[0].includes('4번째 줄'), noAddress[0]);
check('이름이 들어간다', noAddress[0].includes('박온케어'), noAddress[0]);
check('무엇이 문제인지 말한다', noAddress[0].includes('주소'), noAddress[0]);
console.log('   문구:', noAddress[0]);

console.log('');
console.log('=== 3. 이름이 없으면 줄 번호만으로 안내한다 ===');
const noName = checkRow(row({ name: '' }), 7);
check('이름 누락을 잡는다', noName.some((m) => m.includes('이름')), JSON.stringify(noName));
check('줄 번호는 그대로 붙는다', noName[0].includes('7번째 줄'), noName[0]);
check("'undefined 어르신' 같은 문구가 없다",
  !noName.some((m) => m.includes('undefined')), JSON.stringify(noName));
console.log('   문구:', noName[0]);

console.log('');
console.log('=== 4. 시간 문제를 갈라서 잡는다 ===');
const reversed = checkRow(row({ name: '최시간', pickupStart: '09:00', pickupEnd: '08:00' }), 5);
check('하한이 상한보다 늦으면 잡는다', reversed.length === 1, JSON.stringify(reversed));
check('두 값을 모두 보여 준다',
  reversed[0].includes('09:00') && reversed[0].includes('08:00'), reversed[0]);
console.log('   문구:', reversed[0]);

const halfOnly = checkRow(row({ name: '정한쪽', pickupEnd: '' }), 6);
check('한쪽만 채우면 잡는다', halfOnly.length === 1, JSON.stringify(halfOnly));
check('어떻게 고칠지 말해 준다', halfOnly[0].includes('둘 다'), halfOnly[0]);
console.log('   문구:', halfOnly[0]);

const badFormat = checkRow(row({ name: '오형식', pickupStart: '8시', pickupEnd: '9시' }), 8);
check('형식이 틀리면 잡는다', badFormat.length === 1, JSON.stringify(badFormat));
check('예시를 보여 준다', badFormat[0].includes('08:30'), badFormat[0]);
console.log('   문구:', badFormat[0]);

const missingPickup = checkRow(row({ name: '무시간', pickupStart: '', pickupEnd: '' }), 9);
check('픽업 시간이 아예 없으면 잡는다', missingPickup.length === 1,
  JSON.stringify(missingPickup));
console.log('   문구:', missingPickup[0]);

console.log('');
console.log('=== 5. 하차 시각도 같은 규칙으로 본다 ===');
const badDropoff = checkRow(row({ name: '하차역전', dropoffStart: '17:00', dropoffEnd: '16:00' }), 10);
check('하차 하한>상한을 잡는다', badDropoff.length === 1, JSON.stringify(badDropoff));
check("'하차' 라고 말한다", badDropoff[0].includes('하차'), badDropoff[0]);
console.log('   문구:', badDropoff[0]);

const halfDropoff = checkRow(row({ name: '하차한쪽', dropoffStart: '16:00' }), 11);
check('하차 한쪽만 채우면 잡는다', halfDropoff.length === 1, JSON.stringify(halfDropoff));

console.log('');
console.log('=== 6. 한 줄에 여러 문제가 있으면 다 알려 준다 ===');
const messy = checkRow({ name: '', address: '', pickupStart: '', pickupEnd: '' }, 12);
check('이름·주소·시간 세 건을 모두 잡는다', messy.length === 3, JSON.stringify(messy));
check('모두 같은 줄 번호를 가리킨다',
  messy.every((m) => m.includes('12번째 줄')), JSON.stringify(messy));

console.log('');
console.log('=== 7. 실제 명단 시나리오 ===');
console.log('   2·3행 정상 / 4행 주소없음 / 5행 시간역전 / 6행 한쪽만 / 7행 이름없음');
const sheet = [
  [row({ name: '김정상' }), 2],
  [row({ name: '이정상' }), 3],
  [row({ name: '박주소없음', address: '' }), 4],
  [row({ name: '최시간역전', pickupStart: '09:00', pickupEnd: '08:00' }), 5],
  [row({ name: '정한쪽만', pickupEnd: '' }), 6],
  [row({ name: '' }), 7],
];
const all = sheet.flatMap(([data, n]) => checkRow(data, n));
check('문제가 정확히 4건 잡힌다', all.length === 4, JSON.stringify(all, null, 1));
check('정상인 두 줄은 걸리지 않는다',
  !all.some((m) => m.includes('김정상') || m.includes('이정상')), JSON.stringify(all));
for (const message of all) console.log('   ·', message);

console.log('');
if (failures.length) {
  console.log(`실패 ${failures.length}건: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('전부 통과했습니다.');
