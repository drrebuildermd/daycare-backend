// 웹에서는 DocumentPicker가 blob: URI를 주므로 fetch로 그대로 읽을 수 있다.
export async function readWorkbookInput(asset) {
  const response = await fetch(asset.uri);
  return { data: await response.arrayBuffer(), type: 'array' };
}
