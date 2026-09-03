/**
 * 웹에서 표준 양식 파일을 내려준다. 브라우저가 알아서 다운로드 폴더에 넣는다.
 */
export async function saveWorkbookFile(base64, fileName) {
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
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // 브라우저가 다 읽을 시간을 준 뒤 회수한다.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { shared: true, path: fileName };
}
