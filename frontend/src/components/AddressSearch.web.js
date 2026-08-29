import React from 'react';
import Text from '../ui/Text';
import { Modal, TouchableOpacity, View } from 'react-native';
import DaumPostcode from 'react-daum-postcode';

// 웹 전용. react-daum-postcode는 내부적으로 document/window를 쓰므로
// 네이티브에서는 Metro가 AddressSearch.js(WebView 버전)를 대신 고른다.
export default function AddressSearch({ visible, onSelected, onClose }) {
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, marginTop: 40, backgroundColor: 'white' }}>
        <DaumPostcode
          onComplete={(data) => onSelected(data.roadAddress || data.address)}
          autoClose={false}
        />
        <TouchableOpacity style={{ padding: 20, backgroundColor: '#FCEDED' }} onPress={onClose}>
          <Text style={{ textAlign: 'center', color: '#9B2C2C', fontWeight: 'bold' }}>닫기</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}
