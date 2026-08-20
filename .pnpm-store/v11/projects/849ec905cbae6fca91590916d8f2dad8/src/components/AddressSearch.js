import React from 'react';
import { ActivityIndicator, Modal, Text, TouchableOpacity, View } from 'react-native';
import { WebView } from 'react-native-webview';

// 네이티브(iOS/Android) 전용.
// react-daum-postcode는 DOM 기반이라 여기서는 못 쓴다. 대신 같은 다음 우편번호
// 서비스를 WebView 안에서 띄우고, 선택 결과만 postMessage로 넘겨받는다.
const POSTCODE_HTML = `<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
  </head>
  <body style="margin:0;padding:0;">
    <div id="wrap" style="width:100%;height:100vh;"></div>
    <script src="https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js"></script>
    <script>
      new daum.Postcode({
        oncomplete: function (data) {
          window.ReactNativeWebView.postMessage(JSON.stringify(data));
        },
        width: '100%',
        height: '100%',
      }).embed(document.getElementById('wrap'), { autoClose: false });
    </script>
  </body>
</html>`;

export default function AddressSearch({ visible, onSelected, onClose }) {
  const handleMessage = (event) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      onSelected(data.roadAddress || data.address);
    } catch (_) {
      // 우편번호 스크립트가 보내는 부가 메시지는 무시한다.
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, marginTop: 40, backgroundColor: 'white' }}>
        <WebView
          source={{ html: POSTCODE_HTML, baseUrl: 'https://postcode.map.daum.net' }}
          originWhitelist={['*']}
          onMessage={handleMessage}
          javaScriptEnabled
          startInLoadingState
          renderLoading={() => (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
              <ActivityIndicator color="#0F766E" />
            </View>
          )}
        />
        <TouchableOpacity style={{ padding: 20, backgroundColor: '#fee2e2' }} onPress={onClose}>
          <Text style={{ textAlign: 'center', color: '#b91c1c', fontWeight: 'bold' }}>닫기</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}
