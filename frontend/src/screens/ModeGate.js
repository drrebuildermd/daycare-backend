import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

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
        <Text style={styles.eyebrow}>DAYCARE ROUTING</Text>
        <Text style={styles.heading}>관리자 확인</Text>
        <Text style={styles.sub}>관리자 PIN 을 입력해 주세요.</Text>

        <TextInput
          style={styles.pinInput}
          value={pin}
          onChangeText={(text) => { setPin(text.replace(/[^0-9]/g, '')); setError(''); }}
          placeholder="••••"
          placeholderTextColor="#CBD5E1"
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
          <Text style={styles.linkText}>← 뒤로</Text>
        </Pressable>
      </KeyboardAvoidingView>
    );
  }

  return (
    <View style={styles.screen}>
      <Text style={styles.eyebrow}>DAYCARE ROUTING</Text>
      <Text style={styles.heading}>송영 최적화</Text>
      <Text style={styles.sub}>어떤 화면으로 들어가시겠어요?</Text>

      <Pressable style={[styles.choice, styles.choiceDriver]} onPress={() => onSelect('driver')}>
        <Text style={styles.choiceIcon}>🚐</Text>
        <Text style={styles.choiceTitle}>기사님</Text>
        <Text style={styles.choiceDesc}>오늘 내 차량의 탑승 명단만 크게 봅니다</Text>
      </Pressable>

      <Pressable style={[styles.choice, styles.choiceAdmin]} onPress={() => setAsking(true)}>
        <Text style={styles.choiceIcon}>🗂️</Text>
        <Text style={styles.choiceTitle}>관리자</Text>
        <Text style={styles.choiceDesc}>차량·어르신 등록, 배차 계산, 전체 관제</Text>
        <Text style={styles.lockHint}>🔒 PIN 필요</Text>
      </Pressable>

      <Text style={styles.footnote}>
        한 번 고르면 다음부터 이 화면 없이 바로 열립니다.{'\n'}
        바꾸려면 화면 상단의 모드 표시를 누르세요.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9', paddingHorizontal: 24, paddingTop: 60, alignItems: 'stretch' },
  eyebrow: { color: '#0F766E', fontSize: 11, fontWeight: '900', letterSpacing: 1.4 },
  heading: { color: '#0F172A', fontSize: 28, fontWeight: '900', marginTop: 4 },
  sub: { color: '#64748B', fontSize: 14, marginTop: 8, marginBottom: 28 },

  choice: { borderRadius: 20, padding: 22, marginBottom: 14, borderWidth: 2 },
  choiceDriver: { backgroundColor: '#ECFDF5', borderColor: '#10B981' },
  choiceAdmin: { backgroundColor: '#FFFFFF', borderColor: '#CBD5E1' },
  choiceIcon: { fontSize: 32 },
  choiceTitle: { color: '#0F172A', fontSize: 21, fontWeight: '900', marginTop: 8 },
  choiceDesc: { color: '#475569', fontSize: 13, marginTop: 5, lineHeight: 19 },
  lockHint: { color: '#94A3B8', fontSize: 12, fontWeight: '700', marginTop: 8 },

  pinInput: { backgroundColor: '#FFFFFF', borderWidth: 1.5, borderColor: '#CBD5E1', borderRadius: 14, height: 60, fontSize: 26, letterSpacing: 10, textAlign: 'center', color: '#0F172A', marginBottom: 12 },
  error: { color: '#DC2626', fontSize: 13, fontWeight: '700', marginBottom: 10, textAlign: 'center' },
  primaryButton: { backgroundColor: '#0F766E', borderRadius: 15, height: 54, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: '#FFFFFF', fontSize: 17, fontWeight: '900' },
  linkButton: { alignItems: 'center', paddingVertical: 16 },
  linkText: { color: '#64748B', fontSize: 14, fontWeight: '700' },

  footnote: { color: '#94A3B8', fontSize: 12, textAlign: 'center', lineHeight: 19, marginTop: 8 },
});
