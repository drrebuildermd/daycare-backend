/**
 * 엑셀에서 읽은 한 줄이 쓸 만한지 본다.
 *
 * 값이 빠진 채로 넘어가면 배차 계산 단계에서야 터진다. 그때는 어느 줄이
 * 문제인지 알 수 없어서 원장님이 수십 줄을 눈으로 훑어야 한다.
 * 읽는 그 자리에서 줄 번호와 이름을 붙여 알려 준다.
 *
 * expo 모듈을 쓰지 않는다. 그래야 문구를 테스트로 묶어 둘 수 있다.
 */
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export function describe(rowNumber, name) {
  // 엑셀 첫 줄은 열 이름이므로 데이터 첫 줄이 2행이다. 원장님이 보시는
  // 번호와 같아야 찾아가실 수 있다.
  return name ? `${rowNumber}번째 줄 ${name} 어르신` : `${rowNumber}번째 줄`;
}

export function checkRow(passenger, rowNumber) {
  const problems = [];
  const who = describe(rowNumber, passenger.name);

  if (!passenger.name) problems.push(`${who}의 이름이 비어 있습니다.`);
  if (!passenger.address) problems.push(`${who}의 주소가 비어 있습니다.`);

  const pairs = [
    ['픽업', passenger.pickupStart, passenger.pickupEnd, true],
    ['하차', passenger.dropoffStart, passenger.dropoffEnd, false],
  ];
  for (const [label, low, high, required] of pairs) {
    const hasLow = !!low;
    const hasHigh = !!high;
    if (!hasLow && !hasHigh) {
      // 하차 시각은 비워 두면 서버가 등원 시각 + 8시간으로 채운다.
      if (required) problems.push(`${who}의 ${label} 시간이 비어 있습니다.`);
      continue;
    }
    if (hasLow !== hasHigh) {
      problems.push(`${who}의 ${label} 시간이 한쪽만 채워져 있습니다. 둘 다 넣거나 둘 다 비워 주세요.`);
      continue;
    }
    if (!HHMM.test(low) || !HHMM.test(high)) {
      problems.push(`${who}의 ${label} 시간 형식이 올바르지 않습니다 (${low}~${high}). 08:30 처럼 넣어 주세요.`);
      continue;
    }
    if (low > high) {
      problems.push(`${who}의 ${label} 하한(${low})이 상한(${high})보다 늦습니다.`);
    }
  }

  return problems;
}


