import * as FileSystem from 'expo-file-system/legacy';

// 네이티브(iOS/Android)에서는 DocumentPicker가 file:// URI를 주는데,
// React Native의 fetch는 file:// 를 지원하지 않아 "Network request failed"가 난다.
// 그래서 파일을 base64로 직접 읽어 xlsx에 넘긴다.
export async function readWorkbookInput(asset) {
  const base64 = await FileSystem.readAsStringAsync(asset.uri, { encoding: 'base64' });
  return { data: base64, type: 'base64' };
}
