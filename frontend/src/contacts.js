/**
 * 기사님이 📞 를 눌렀을 때 누구에게 걸지 정한다.
 *
 * 버튼에 적힌 글자와 실제로 걸리는 번호가 어긋나면, 기사님은 보호자에게 건다고
 * 믿으면서 어르신 본인에게 걸게 된다. 그래서 번호와 이름표를 한 곳에서 함께 정한다.
 */

const digitsOf = (value) => (value || '').replace(/[^0-9]/g, '');

// 백엔드와 같은 기준. 숫자만 뽑아 10자리 미만이면 쓸 수 없는 번호로 본다.
const isDialable = (digits) => digits.length >= 10;

export function callTargetFor(stop) {
  const guardian = digitsOf(stop?.guardian_phone);
  const own = digitsOf(stop?.passenger_phone);
  const wantsSelf = stop?.primary_contact === 'self';

  if (wantsSelf && isDialable(own)) return { digits: own, label: '본인' };
  if (!wantsSelf && isDialable(guardian)) return { digits: guardian, label: '보호자' };

  // 지정한 쪽이 비어 있으면 남은 번호로라도 연결한다.
  // 기사님이 길 위에서 번호가 없다고 멈추는 것보다 낫다.
  if (isDialable(own)) return { digits: own, label: '본인' };
  if (isDialable(guardian)) return { digits: guardian, label: '보호자' };

  return null;
}
