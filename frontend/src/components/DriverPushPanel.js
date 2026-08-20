import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { enablePushForDriver } from '../push';

/**
 * 기사님이 본인 폰을 알림 수신 기기로 등록하는 패널.
 * 관리자 PC(웹)에서는 등록할 수 없으므로 안내만 띄운다.
 */
export default function DriverPushPanel({ vehicles }) {
  const [busy, setBusy] = useState('');
  const [registered, setRegistered] = useState({});

  // 차량에 입력된 담당 기사 이름이 곧 알림 수신자 목록이다.
  const drivers = useMemo(() => {
    const seen = new Set();
    return vehicles
      .map((vehicle) => (vehicle.driverName || '').trim())
      .filter((name) => {
        if (!name || seen.has(name)) return false;
        seen.add(name);
        return true;
      });
  }, [vehicles]);

  const enable = async (driverName) => {
    setBusy(driverName);
    try {
      await enablePushForDriver(driverName);
      setRegistered((current) => ({ ...current, [driverName]: true }));
      Alert.alert(
        '알림 설정 완료',
        `${driverName} 선생님, 이 폰으로 배차 알림을 받습니다.`,
      );
    } catch (error) {
      Alert.alert('알림 설정 실패', error.message);
    } finally {
      setBusy('');
    }
  };

  if (Platform.OS === 'web') {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>📱 기사님 알림 설정</Text>
        <Text style={styles.body}>
          배차 알림은 기사님 휴대폰의 앱에서 켭니다.{'\n'}
          기사님 폰에 앱을 설치한 뒤 [1. 차량 관리] 화면 아래에서
          본인 이름을 눌러 주세요.
        </Text>
      </View>
    );
  }

  if (!drivers.length) {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>📱 기사님 알림 설정</Text>
        <Text style={styles.body}>
          차량에 담당 기사 이름을 먼저 입력하면 여기에 표시됩니다.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>📱 기사님 알림 설정</Text>
      <Text style={styles.body}>
        이 폰을 쓰시는 분의 이름을 눌러 주세요. 관리자가 배차를 전송하면 알림이 옵니다.
      </Text>
      <View style={styles.chipWrap}>
        {drivers.map((name) => {
          const isBusy = busy === name;
          const isDone = registered[name];
          return (
            <Pressable
              key={name}
              style={[styles.chip, isDone && styles.chipDone]}
              onPress={() => enable(name)}
              disabled={Boolean(busy)}
            >
              {isBusy ? (
                <ActivityIndicator size="small" color="#0F766E" />
              ) : (
                <Text style={[styles.chipText, isDone && styles.chipTextDone]}>
                  {isDone ? `✅ ${name} 선생님` : `${name} 선생님`}
                </Text>
              )}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: '#FFFFFF', borderRadius: 18, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: '#E2E8F0' },
  title: { color: '#0F172A', fontSize: 15, fontWeight: '900' },
  body: { color: '#64748B', fontSize: 12.5, lineHeight: 19, marginTop: 5 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  chip: { backgroundColor: '#F8FAFC', borderWidth: 1.5, borderColor: '#0F766E', borderRadius: 999, paddingHorizontal: 15, paddingVertical: 10, minWidth: 110, alignItems: 'center' },
  chipDone: { backgroundColor: '#ECFDF5', borderColor: '#10B981' },
  chipText: { color: '#0F766E', fontSize: 13, fontWeight: '800' },
  chipTextDone: { color: '#047857' },
});
