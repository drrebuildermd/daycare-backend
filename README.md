# 주야간보호센터 송영 최적화 MVP

FastAPI + Google OR-Tools 백엔드와 React Native(Expo) 모바일 앱으로 구성된 로컬 실행용 MVP입니다.

## 구현 범위

- 차량 관리 화면에서 차종, 차량번호, 정원을 제한 없이 추가·수정·삭제
- API 요청의 동적 차량 배열에 맞춰 OR-Tools 차량 수와 정원을 구성
- 차량별 1차/2차까지만 생성하며 3차 운행은 모델 구조상 존재하지 않음
- 같은 차량은 1차 운행 후 센터에 복귀하고 회차 준비시간이 지난 뒤에만 2차 출발
- 픽업 하한~상한을 OR-Tools의 하드 타임윈도로 적용(지각/조기 도착 허용 없음)
- 모바일 개별 입력과 XLS/XLSX/CSV 일괄 입력
- 차량/회차별 순서, 예상 픽업 시각, 복귀 시각, 거리 표시
- 탑승자 카드마다 해당 주소 한 곳만 목적지로 담은 `kakaonavi://` 단건 딥링크
- 탑승 완료 버튼을 누르면 카드를 비활성화하고 완료 시각을 초 단위로 기록
- SQLite에 서버 한국시간으로 탑승 완료 기록을 영구 저장하고 앱 재실행 시 복원
- 당일 송영 기록을 엑셀 호환 UTF-8 CSV로 다운로드
- 개발 편의를 위한 CORS 설정

카카오내비 경유지 제한을 피하기 위해 운행 전체를 한 번에 넘기지 않고, 기사가 다음 탑승자 카드의 `내비` 버튼을 누르는 순차 단건 안내 방식으로 동작합니다.

## 1. 백엔드 실행

PowerShell 터미널에서:

```powershell
cd C:\Users\HOME\Documents\Daycare_App\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

주소만으로 좌표를 찾으려면 `backend/.env`의 `KAKAO_REST_API_KEY`에 Kakao Developers REST API 키를 입력합니다. 위도/경도가 들어 있는 요청은 키가 없어도 됩니다.

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

SQLite는 Python 표준 라이브러리를 사용하므로 별도 DB 패키지나 서버 설치가 필요하지 않습니다. 첫 실행 시 `backend/data/daycare_routing.db`와 테이블이 자동 생성됩니다.

- API 문서: [http://localhost:8000/docs](http://localhost:8000/docs)
- 상태 확인: [http://localhost:8000/api/health](http://localhost:8000/api/health)

샘플 요청은 `backend/sample_request.json`에 있습니다.

## 2. 프론트엔드 실행

새 PowerShell 터미널에서:

```powershell
cd C:\Users\HOME\Documents\Daycare_App\frontend
npm install
Copy-Item .env.example .env
npm start
```

앱 재실행 후 마지막 배차 화면을 복원하기 위해 `@react-native-async-storage/async-storage`를 사용합니다. 기존 설치 환경에서는 `npm install` 한 번으로 추가됩니다.

실행 환경별 `frontend/.env` 설정:

- Android 에뮬레이터: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`
- iOS 시뮬레이터: `EXPO_PUBLIC_API_URL=http://localhost:8000`
- 실제 휴대폰: PC와 같은 Wi-Fi에 연결하고 `http://PC의_LAN_IP:8000` 사용

`.env` 변경 후에는 Expo 서버를 `Ctrl+C`로 종료하고 `npx expo start -c`로 다시 시작합니다. 화면의 QR 코드를 Expo Go로 스캔하면 됩니다.

## 엑셀 형식

첫 번째 시트의 다음 열을 인식합니다. 한글 또는 영문 열 이름을 사용할 수 있습니다.

| 필수 | 한글 열 | 영문 열 | 예시 |
|---|---|---|---|
| 예 | 이름 | `name` | 김행복 |
| 예 | 주소 | `address` | 서울특별시 종로구 종로 1 |
| 예 | 픽업 하한 | `pickup_start` | 08:10 |
| 예 | 픽업 상한 | `pickup_end` | 08:35 |
| 아니오 | 휠체어 | `wheelchair` | 예 / 아니오 |
| 아니오 | 위도 | `latitude` | 37.5704 |
| 아니오 | 경도 | `longitude` | 126.9810 |
| 아니오 | ID | `id` | P001 |

바로 시험할 파일은 `frontend/sample_passengers.csv`입니다. 센터 주소는 앱에서 별도로 입력합니다.

## 최적화 방식과 운영 전 교체 지점

MVP는 주소를 WGS84 좌표로 변환한 뒤 직선거리 × 도로계수와 평균속도로 시간행렬을 만듭니다. 픽업 시간창 자체는 이 행렬에 대해 1분 오차도 허용하지 않는 하드 제약입니다. 실제 운영에서는 교통상황을 반영하는 Kakao Mobility Directions API 등의 도로 시간행렬로 `backend/app/optimizer.py`의 `_matrices()`만 교체하는 것을 권장합니다.

휠체어 여부는 현재 관제 표시 정보입니다. 휠체어 리프트 장착 차량이나 휠체어당 좌석 환산 규칙이 정해지면 차량 호환성/수요량 제약으로 확장할 수 있습니다.
