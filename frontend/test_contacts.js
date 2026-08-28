/**
 * 기사님 📞 버튼이 누구에게 거는지 검증.
 * 실행: frontend 폴더에서  node test_contacts.js
 */
const babel = require('@babel/core');
const fs = require('fs');

const code = babel.transformSync(fs.readFileSync('src/contacts.js', 'utf8'), {
  filename: 'contacts.js',
  presets: ['babel-preset-expo'],
  plugins: ['@babel/plugin-transform-modules-commonjs'],
  babelrc: false, configFile: false,
}).code;
const mod = { exports: {} };
new Function('require', 'module', 'exports', code)(require, mod, mod.exports);
const { callTargetFor } = mod.exports;

const failures = [];
const check = (label, ok, detail) => {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}${detail ? ' -> ' + detail : ''}`);
  if (!ok) failures.push(label);
};

const G = '010-1111-2222';
const S = '010-3333-4444';
const show = (t) => (t ? `${t.label} ${t.digits}` : '없음');

console.log('=== 지정한 대로 건다 ===');
let t = callTargetFor({ guardian_phone: G, passenger_phone: S, primary_contact: 'guardian' });
check('보호자 지정 -> 보호자', t.label === '보호자' && t.digits === '01011112222', show(t));

t = callTargetFor({ guardian_phone: G, passenger_phone: S, primary_contact: 'self' });
check('본인 지정 -> 본인', t.label === '본인' && t.digits === '01033334444', show(t));

console.log();
console.log('=== 지정한 쪽 번호가 없으면 남은 번호로 ===');
t = callTargetFor({ guardian_phone: G, passenger_phone: '', primary_contact: 'self' });
check('본인 지정인데 본인 번호 없음 -> 보호자', t.label === '보호자', show(t));

t = callTargetFor({ guardian_phone: '', passenger_phone: S, primary_contact: 'guardian' });
check('보호자 지정인데 보호자 번호 없음 -> 본인', t.label === '본인', show(t));

console.log();
console.log('=== 이름표와 번호가 반드시 같은 사람을 가리켜야 한다 ===');
for (const [g, s, pc] of [[G, S, 'self'], [G, S, 'guardian'], ['', S, 'self'], [G, '', 'guardian'],
                          [G, '', 'self'], ['', S, 'guardian']]) {
  const r = callTargetFor({ guardian_phone: g, passenger_phone: s, primary_contact: pc });
  const expected = r && (r.label === '본인' ? s : g).replace(/[^0-9]/g, '');
  check(`(보호자:${g || '없음'} 본인:${s || '없음'} 지정:${pc})`, !!r && r.digits === expected, show(r));
}

console.log();
console.log('=== 번호가 아예 없으면 걸지 않는다 ===');
check('둘 다 없음 -> null', callTargetFor({ primary_contact: 'guardian' }) === null);
check('빈 문자열 -> null', callTargetFor({ guardian_phone: '', passenger_phone: '' }) === null);
check('자리수 부족(9자리) -> null', callTargetFor({ guardian_phone: '012345678' }) === null);
check('stop 자체가 없음 -> null', callTargetFor(undefined) === null);

console.log();
console.log('=== 기존 명단(새 필드 없음)도 동작해야 한다 ===');
t = callTargetFor({ guardian_phone: G });
check('primary_contact 없으면 보호자', t && t.label === '보호자', show(t));

console.log();
if (failures.length) {
  console.log(`실패 ${failures.length}건: ${failures.join(', ')}`);
  process.exit(1);
}
console.log('전체 통과 — 버튼 글자와 실제 걸리는 번호가 항상 일치합니다.');
