import * as DocumentPicker from 'expo-document-picker';
import * as XLSX from 'xlsx';

// 웹/네이티브에서 파일 읽는 방식이 달라 Metro가 플랫폼별 파일을 자동 선택한다.
import { readWorkbookInput } from './readWorkbook';
import { saveWorkbookFile } from './saveTemplate';
import { checkRow } from './excelValidate';

const COLUMN_ALIASES = {
  id: ['id', 'ID', '아이디', '번호'],
  name: ['name', '이름', '어르신 이름', '성명'],
  address: ['address', '주소'],
  detailAddress: ['detail_address', '상세주소', '상세 주소', '동호수'],
  pickupStart: ['pickup_start', '픽업 하한', '픽업시간 하한', '시작시간', '하한'],
  pickupEnd: ['pickup_end', '픽업 상한', '픽업시간 상한', '종료시간', '상한'],
  dropoffStart: ['dropoff_start', '하차 하한', '하원 하한', '하차시간 하한'],
  dropoffEnd: ['dropoff_end', '하차 상한', '하원 상한', '하차시간 상한'],
  wheelchair: ['wheelchair', '휠체어', '휠체어 여부'],
  careGrade: ['care_grade', '장기요양등급', '등급', '요양등급'],
  plannedServiceHours: ['planned_service_hours', '계획 이용시간', '이용시간', '계획이용시간'],
  guardianPhone: ['guardian_phone', '보호자 연락처', '보호자연락처', '연락처', '전화번호', '휴대폰'],
  // 어르신 본인 휴대폰. 대표 연락처를 '본인' 으로 두면 기사님이 여기로 건다.
  passengerPhone: ['passenger_phone', '어르신 전화번호', '어르신 연락처',
    '본인 연락처', '본인연락처', '어르신휴대폰'],
  latitude: ['latitude', 'lat', '위도'],
  longitude: ['longitude', 'lng', 'lon', '경도'],
};

const getValue = (row, aliases) => {
  const key = aliases.find((candidate) => row[candidate] !== undefined);
  return key ? row[key] : undefined;
};

const excelTime = (value) => {
  if (typeof value === 'number') {
    const minutes = Math.round((value % 1) * 24 * 60);
    return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  }
  const text = String(value ?? '').trim();
  const match = text.match(/^(\d{1,2}):(\d{2})/);
  return match ? `${match[1].padStart(2, '0')}:${match[2]}` : text;
};

// 등급 칸. 원장님이 '4', '4등급', '인지지원', '등급외' 처럼 여러 모양으로 적는다.
// 못 알아보면 빈 값으로 두고 서버가 센터 기본값(4등급)으로 본다.
const asGrade = (value) => {
  const text = String(value ?? '').trim();
  if (!text) return '';
  if (/인지/.test(text)) return 'cognitive';
  if (/등급\s*외|등급외|해당\s*없음/.test(text)) return 'none';
  const digit = text.match(/[1-5]/);
  return digit ? digit[0] : '';
};

// 계획 이용시간. '8', '8시간', '8.5' 를 받는다. 숫자가 아니면 빈 값.
const asHours = (value) => {
  const text = String(value ?? '').trim();
  if (!text) return '';
  const found = text.match(/[0-9]+(\.[0-9]+)?/);
  if (!found) return '';
  const hours = Number(found[0]);
  return hours > 0 && hours <= 24 ? String(hours) : '';
};

const asBoolean = (value) => ['true', 'y', 'yes', '1', '예', '유', 'o'].includes(
  String(value ?? '').trim().toLowerCase(),
);

// ---------------------------------------------------------------------------
// 표준 양식
// ---------------------------------------------------------------------------
//
// 원장님이 빈 엑셀을 놓고 '무슨 열을 만들어야 하나' 를 고민하지 않도록
// 채워진 예시 한 줄과 함께 내려준다. 그 줄을 지우고 쓰시면 된다.

const TEMPLATE_HEADERS = [
  '이름', '주소', '상세주소', '보호자 연락처', '어르신 전화번호',
  '픽업 하한', '픽업 상한', '하차 하한', '하차 상한', '휠체어',
  '장기요양등급', '계획 이용시간',
];

const TEMPLATE_SAMPLE = [
  {
    이름: '김마중',
    주소: '창원시 의창구 중앙대로 100',
    상세주소: '101동 1502호',
    '보호자 연락처': '010-1234-5678',
    '어르신 전화번호': '010-9876-5432',
    '픽업 하한': '08:00',
    '픽업 상한': '08:30',
    '하차 하한': '',
    '하차 상한': '',
    휠체어: 'N',
    장기요양등급: '4',
    '계획 이용시간': '8',
  },
  {
    이름: '박온케어',
    주소: '창원시 성산구 원이대로 200',
    상세주소: '',
    '보호자 연락처': '010-2345-6789',
    '어르신 전화번호': '',
    '픽업 하한': '08:20',
    '픽업 상한': '09:00',
    '하차 하한': '16:00',
    '하차 상한': '16:40',
    휠체어: 'Y',
    장기요양등급: '인지지원',
    '계획 이용시간': '10',
  },
];

export async function downloadPassengerTemplate() {
  const sheet = XLSX.utils.json_to_sheet(TEMPLATE_SAMPLE, { header: TEMPLATE_HEADERS });

  // 열 너비를 미리 잡아 준다. 기본값이면 주소가 다 가려서 뭘 넣는 칸인지 모른다.
  sheet['!cols'] = [
    { wch: 10 }, { wch: 32 }, { wch: 14 }, { wch: 16 }, { wch: 16 },
    { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 8 },
    { wch: 14 }, { wch: 14 },
  ];

  const book = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(book, sheet, '어르신 명단');

  const base64 = XLSX.write(book, { bookType: 'xlsx', type: 'base64' });
  const fileName = '마중ON_어르신명단_양식.xlsx';
  const outcome = await saveWorkbookFile(base64, fileName);
  return { fileName, ...outcome };
}


// ---------------------------------------------------------------------------
// 검사
// ---------------------------------------------------------------------------
//
// 값이 빠진 채로 넘어가면 배차 계산 단계에서야 터진다. 그때는 어느 줄이
// 문제인지 알 수 없어서 원장님이 34줄을 눈으로 훑어야 한다.
// 읽는 그 자리에서 줄 번호와 이름을 붙여 알려 준다.

export async function pickPassengerExcel() {
  const picked = await DocumentPicker.getDocumentAsync({
    type: [
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/csv',
    ],
    copyToCacheDirectory: true,
  });
  if (picked.canceled) return null;

  const asset = picked.assets[0];
  let rows;
  try {
    const { data, type } = await readWorkbookInput(asset);
    const workbook = XLSX.read(data, { type, cellDates: false });
    const worksheet = workbook.Sheets[workbook.SheetNames[0]];
    if (!worksheet) {
      throw new Error('시트를 찾지 못했습니다.');
    }
    rows = XLSX.utils.sheet_to_json(worksheet, { defval: '' });
  } catch (error) {
    throw new Error(
      '엑셀 파일을 열지 못했습니다. 파일이 손상되었거나 지원하지 않는 형식입니다.\n'
      + '[표준 엑셀 양식 받기] 로 받은 파일에 채워서 올려 주세요.',
    );
  }

  if (!rows.length) {
    throw new Error(
      '첫 시트에 데이터가 없습니다.\n'
      + '[표준 엑셀 양식 받기] 로 받은 파일에 채워서 올려 주세요.',
    );
  }

  // 이름도 주소도 없는 줄은 사람이 아니라 빈 줄이다. 조용히 건너뛴다.
  const parsed = rows
    .map((row, index) => ({
      // 엑셀에서 원장님이 보시는 행 번호. 1행은 열 이름이라 2부터다.
      rowNumber: index + 2,
      localId: `${Date.now()}-${index}`,
      id: String(getValue(row, COLUMN_ALIASES.id) || `P${String(index + 1).padStart(3, '0')}`),
      name: String(getValue(row, COLUMN_ALIASES.name) ?? '').trim(),
      address: String(getValue(row, COLUMN_ALIASES.address) ?? '').trim(),
      detailAddress: String(getValue(row, COLUMN_ALIASES.detailAddress) ?? '').trim(),
      pickupStart: excelTime(getValue(row, COLUMN_ALIASES.pickupStart)),
      pickupEnd: excelTime(getValue(row, COLUMN_ALIASES.pickupEnd)),
      dropoffStart: excelTime(getValue(row, COLUMN_ALIASES.dropoffStart)),
      dropoffEnd: excelTime(getValue(row, COLUMN_ALIASES.dropoffEnd)),
      wheelchair: asBoolean(getValue(row, COLUMN_ALIASES.wheelchair)),
      careGrade: asGrade(getValue(row, COLUMN_ALIASES.careGrade)),
      plannedServiceHours: asHours(getValue(row, COLUMN_ALIASES.plannedServiceHours)),
      guardianPhone: String(getValue(row, COLUMN_ALIASES.guardianPhone) ?? '').trim(),
      passengerPhone: String(getValue(row, COLUMN_ALIASES.passengerPhone) ?? '').trim(),
      latitude: String(getValue(row, COLUMN_ALIASES.latitude) ?? '').trim(),
      longitude: String(getValue(row, COLUMN_ALIASES.longitude) ?? '').trim(),
    }))
    .filter((item) => item.name || item.address);

  if (!parsed.length) {
    throw new Error(
      '어르신 데이터를 찾지 못했습니다.\n'
      + `첫 줄의 열 이름이 '이름', '주소' 인지 확인해 주세요.\n`
      + '[표준 엑셀 양식 받기] 로 받은 파일을 쓰시면 확실합니다.',
    );
  }

  const problems = parsed.flatMap((item) => checkRow(item, item.rowNumber));
  if (problems.length) {
    // 스무 줄이 전부 잘못됐을 때 스무 줄을 다 띄우면 읽히지 않는다.
    const shown = problems.slice(0, 5);
    const rest = problems.length - shown.length;
    throw new Error(
      shown.join('\n')
      + (rest > 0 ? `\n... 그 밖에 ${rest}건이 더 있습니다.` : '')
      + '\n\n엑셀에서 고친 뒤 다시 올려 주세요. 아무것도 반영하지 않았습니다.',
    );
  }

  // 검사에 쓴 줄 번호는 앱 안에서 쓰지 않으므로 뺀다.
  const passengers = parsed.map(({ rowNumber, ...rest }) => rest);
  return { passengers, fileName: asset.name };
}
