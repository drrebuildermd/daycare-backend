import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

/**
 * 네이티브(안드로이드/iOS)에서 표준 양식 파일을 원장님께 넘긴다.
 *
 * 앱 안에서 파일을 만든 뒤 공유 시트를 연다. 거기서 카카오톡으로 보내거나
 * 내 파일에 저장하면 PC에서 열어 채울 수 있다.
 * 앱이 직접 다운로드 폴더에 쓰려면 저장소 권한을 받아야 해서 이 방식을 쓴다.
 */
export async function saveWorkbookFile(base64, fileName) {
  const target = `${FileSystem.cacheDirectory}${fileName}`;
  await FileSystem.writeAsStringAsync(target, base64, { encoding: 'base64' });

  if (!(await Sharing.isAvailableAsync())) {
    return { shared: false, path: target };
  }
  await Sharing.shareAsync(target, {
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    dialogTitle: '표준 엑셀 양식 저장',
    UTI: 'org.openxmlformats.spreadsheetml.sheet',
  });
  return { shared: true, path: target };
}
