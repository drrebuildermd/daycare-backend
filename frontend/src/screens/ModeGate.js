import React, { useState } from 'react';
import Text from '../ui/Text';
import { Image, KeyboardAvoidingView, Platform, Pressable, StyleSheet, TextInput, View } from 'react-native';

import Icon from '../ui/Icon';
import { brand, color } from '../theme';

// 관리자 화면 진입 PIN.
// 이건 보안이 아니라 오조작 방지 장치다. EXPO_PUBLIC_* 값은 앱 번들에 박히므로
// APK 를 뜯으면 볼 수 있다. 기사님이 실수로 배차 화면에 들어가 명단을 건드리는
// 것을 막는 용도이지, 외부인의 침입을 막는 수단이 아니다.
const ADMIN_PIN = process.env.EXPO_PUBLIC_ADMIN_PIN || '0000';

/**
 * 앱 첫 화면. 관리자와 기사 중 무엇으로 들어갈지 고른다.
 * 기사는 바로 들어가고, 관리자만 PIN 을 묻는다.
 */
export default function ModeGate({ onSelect }) {
  const [asking, setAsking] = useState(false);
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');

  const submitPin = () => {
    if (pin.trim() === ADMIN_PIN) {
      onSelect('admin');
      return;
    }
    setError('PIN 이 올바르지 않습니다.');
    setPin('');
  };

  if (asking) {
    return (
      <KeyboardAvoidingView
        style={styles.screen}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Text style={styles.eyebrow}>{brand.productName}</Text>
        <Text style={styles.heading}>관리자 확인</Text>
        <Text style={styles.sub}>관리자 PIN 을 입력해 주세요.</Text>

        <TextInput
          style={styles.pinInput}
          value={pin}
          onChangeText={(text) => { setPin(text.replace(/[^0-9]/g, '')); setError(''); }}
          placeholder="••••"
          placeholderTextColor="#E4E7EC"
          keyboardType="number-pad"
          secureTextEntry
          maxLength={8}
          onSubmitEditing={submitPin}
          autoFocus
        />
        {!!error && <Text style={styles.error}>{error}</Text>}

        <Pressable style={styles.primaryButton} onPress={submitPin}>
          <Text style={styles.primaryText}>확인</Text>
        </Pressable>
        <Pressable style={styles.linkButton} onPress={() => { setAsking(false); setPin(''); setError(''); }}>
          <Icon name="back" size={15} tint={color.textSecondary} />
          <Text style={styles.linkText}>뒤로</Text>
        </Pressable>
      </KeyboardAvoidingView>
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.brandRow}>
        <Image
          source={require('../../assets/mroute-mark.png')}
          style={styles.mark}
          resizeMode="contain"
        />
        <View style={styles.brandText}>
          <Text style={styles.heading}>{brand.productName}</Text>
          <Text style={styles.eyebrow}>{brand.descriptor}</Text>
        </View>
      </View>
      <Text style={styles.sub}>{brand.tagline}</Text>

      <Pressable style={[styles.choice, styles.choiceDriver]} onPress={() => onSelect('driver')}>
        <Icon name="vehicle" size={30} tint={color.green} />
        <Text style={styles.choiceTitle}>기사님 · 운행</Text>
        <Text style={styles.choiceDesc}>오늘 내 차량의 동선과 탑승 명단을 봅니다</Text>
      </Pressable>

      <Pressable style={[styles.choice, styles.choiceAdmin]} onPress={() => setAsking(true)}>
        <Icon name="admin" size={30} tint={color.deepNavy} />
        <Text style={styles.choiceTitle}>관리자 · 배차</Text>
        <Text style={styles.choiceDesc}>배차 계산과 경로·차량 운영, 전체 관제</Text>
        <View style={styles.lockRow}>
          <Icon name="locked" size={13} tint={color.textSecondary} />
          <Text style={styles.lockHint}>PIN 필요</Text>
        </View>
      </Pressable>

      <Text style={styles.footnote}>
        한 번 고르면 다음부터 이 화면 없이 바로 열립니다.{'\n'}
        바꾸려면 화면 상단의 모드 표시를 누르세요.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F2F4F7', paddingHorizontal: 24, paddingTop: 60, alignItems: 'stretch' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  mark: { width: 56, height: 56 },
  brandText: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#0BA38E', fontSize: 12, fontWeight: '600', marginTop: 2 },
  heading: { color: '#0D2540', fontSize: 26, fontWeight: '700' },
  sub: { color: '#667085', fontSize: 14, marginTop: 14, marginBottom: 26 },

  choice: { borderRadius: 16, padding: 20, marginBottom: 12, borderWidth: 1.5 },
  choiceDriver: { backgroundColor: '#E9F7EF', borderColor: '#3BB273' },
  choiceAdmin: { backgroundColor: '#FFFFFF', borderColor: '#E4E7EC' },
  choiceTitle: { color: '#0D2540', fontSize: 20, fontWeight: '700', marginTop: 10 },
  choiceDesc: { color: '#667085', fontSize: 13, marginTop: 4, lineHeight: 19 },
  lockRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 10 },
  lockHint: { color: '#667085', fontSize: 12, fontWeight: '600' },

  pinInput: { backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#E4E7EC', borderRadius: 14, height: 60, fontSize: 26, letterSpacing: 10, textAlign: 'center', color: '#0D2540', marginBottom: 12 },
  error: { color: '#D64545', fontSize: 13, fontWeight: '700', marginBottom: 10, textAlign: 'center' },
  primaryButton: { backgroundColor: '#0D2540', borderRadius: 12, height: 54, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: '#FFFFFF', fontSize: 16, fontWeight: '700' },
  linkButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 16 },
  linkText: { color: '#667085', fontSize: 14, fontWeight: '600' },

  footnote: { color: '#98A2B3', fontSize: 12, textAlign: 'center', lineHeight: 19, marginTop: 8 },
});
