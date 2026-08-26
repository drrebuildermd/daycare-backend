import * as DocumentPicker from 'expo-document-picker';
import * as XLSX from 'xlsx';

// 웹/네이티브에서 파일 읽는 방식이 달라 Metro가 플랫폼별 파일을 자동 선택한다.
import { readWorkbookInput } from './readWorkbook';

const COLUMN_ALIASES = {
  id: ['id', 'ID', '아이디', '번호'],
  name: ['name', '이름', '어르신 이름', '성명'],
  address: ['address', '주소'],
  detailAddress: ['detail_address', '상세주소', '상세 주소', '동호수'],
  pickupStart: ['pickup_start', '픽업 하한', '픽업시간 하한', '시작시간', '하한'],
  pickupEnd: ['pickup_end', '픽업 상한', '픽업시간 상한', '종료시간', '상한'],
  wheelchair: ['wheelchair', '휠체어', '휠체어 여부'],
  guardianPhone: ['guardian_phone', '보호자 연락처', '보호자연락처', '연락처', '전화번호', '휴대폰'], // 🚨 [신규 장착] 엑셀에서 연락처 열 추출
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

const asBoolean = (value) => ['true', 'y', 'yes', '1', '예', '유', 'o'].includes(
  String(value ?? '').trim().toLowerCase(),
);

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
  const { data, type } = await readWorkbookInput(asset);
  const workbook = XLSX.read(data, { type, cellDates: false });
  const worksheet = workbook.Sheets[workbook.SheetNames[0]];
  const rows = XLSX.utils.sheet_to_json(worksheet, { defval: '' });

  const passengers = rows
    .map((row, index) => ({
      localId: `${Date.now()}-${index}`,
      id: String(getValue(row, COLUMN_ALIASES.id) || `P${String(index + 1).padStart(3, '0')}`),
      name: String(getValue(row, COLUMN_ALIASES.name) ?? '').trim(),
      address: String(getValue(row, COLUMN_ALIASES.address) ?? '').trim(),
      detailAddress: String(getValue(row, COLUMN_ALIASES.detailAddress) ?? '').trim(),
      pickupStart: excelTime(getValue(row, COLUMN_ALIASES.pickupStart)),
      pickupEnd: excelTime(getValue(row, COLUMN_ALIASES.pickupEnd)),
      wheelchair: asBoolean(getValue(row, COLUMN_ALIASES.wheelchair)),
      guardianPhone: String(getValue(row, COLUMN_ALIASES.guardianPhone) ?? '').trim(), // 🚨 [신규 장착] 연락처 데이터 연결
      latitude: String(getValue(row, COLUMN_ALIASES.latitude) ?? '').trim(),
      longitude: String(getValue(row, COLUMN_ALIASES.longitude) ?? '').trim(),
    }))
    .filter((item) => item.name || item.address);

  if (!passengers.length) {
    throw new Error('첫 시트에서 어르신 데이터를 찾지 못했습니다. 열 이름을 확인해 주세요.');
  }
  return { passengers, fileName: asset.name };
}