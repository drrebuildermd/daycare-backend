import { Platform } from 'react-native';

/**
 * 표준 양식 파일을 원장님께 넘긴다.
 *
 * 플랫폼을 파일 이름(.web.js)이 아니라 코드에서 직접 가른다.
 * 번들러의 확장자 해석에 기대면 설정이 바뀌었을 때 조용히 반대쪽 코드가
 * 실려도 알아채기 어렵다. PC에서 공유 시트가 뜨는 것이 그런 종류의 사고다.
 */
export async function saveWorkbookFile(base64, fileName) {
  if (Platform.OS === 'web') return saveOnWeb(base64, fileName);
  return saveOnDevice(base64, fileName);
}

// PC(브라우저) — 누르는 즉시 다운로드 폴더로 들어간다.
// 공유 시트를 거칠 이유가 없다.
function saveOnWeb(base64, fileName) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);

  const blob = new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // 브라우저가 다 읽을 시간을 준 뒤 회수한다.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { shared: true, path: fileName, via: 'download' };
}

// 폰 — 앱 안에 파일을 만든 뒤 공유 시트를 연다. 거기서 카카오톡으로 보내거나
// 내 파일에 저장하면 PC에서 열어 채울 수 있다.
// 앱이 직접 다운로드 폴더에 쓰려면 저장소 권한을 받아야 해서 이 방식을 쓴다.
async function saveOnDevice(base64, fileName) {
  const FileSystem = require('expo-file-system/legacy');
  const Sharing = require('expo-sharing');

  const target = `${FileSystem.cacheDirectory}${fileName}`;
  await FileSystem.writeAsStringAsync(target, base64, { encoding: 'base64' });

  if (!(await Sharing.isAvailableAsync())) {
    return { shared: false, path: target, via: 'file' };
  }
  await Sharing.shareAsync(target, {
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    dialogTitle: '표준 엑셀 양식 저장',
    UTI: 'org.openxmlformats.spreadsheetml.sheet',
  });
  return { shared: true, path: target, via: 'share' };
}
