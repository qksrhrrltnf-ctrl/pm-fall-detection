# PM 넘어짐 탐지 시스템 (MVP)

버스 카메라 기반 넘어짐 PM(Personal Mobility) 탐지 + GPS 연동 + 실시간 알림 대시보드

## 📋 개요

이 프로젝트는 **1단계 MVP** 버전으로, 실제 컴퓨터 비전(YOLO) 탐지 없이 Mock 이벤트를 사용하여 전체 end-to-end 파이프라인을 완성합니다.

### 주요 기능

1. **Simulator**: 가짜 PM 넘어짐 탐지 이벤트 생성
   - 경로(route.json)를 따라 GPS 좌표 선형 보간
   - 프레임 구간별 확률로 이벤트 발생

2. **Backend (FastAPI)**: 이벤트 수신 및 처리
   - 중복 제거(Deduplication) 로직
   - SQLite 데이터베이스 저장
   - SSE(Server-Sent Events) 실시간 스트리밍

3. **Dashboard**: 실시간 지도 기반 대시보드
   - Leaflet 지도에 이벤트 마커 표시
   - 좌측 이벤트 목록
   - SSE 구독으로 실시간 업데이트

## 🚀 빠른 시작

### Docker Compose로 실행 (권장)

```bash
# 프로젝트 루트 디렉토리에서
docker-compose up --build
```

### 확인 방법

1. **대시보드**: 브라우저에서 http://localhost:8000 접속
   - 지도에 이벤트 마커가 실시간으로 표시됩니다
   - 좌측 패널에서 이벤트 목록을 확인합니다

2. **API 확인**:
   ```bash
   # 최근 24시간 이벤트 목록
   curl http://localhost:8000/events?hours=24
   
   # 헬스 체크
   curl http://localhost:8000/health
   ```

3. **중복 제거 확인**:
   - 동일 위치(grid_key)에서 10분 내 재발생 시 `occurrence_count`가 증가합니다
   - 대시보드에서 이벤트 카드의 "N회" 뱃지로 확인

## 📁 프로젝트 구조

```
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI 앱 진입점
│   │   ├── db.py           # 데이터베이스 설정
│   │   ├── models.py       # SQLAlchemy 모델
│   │   ├── dedup.py        # 중복 제거 로직
│   │   ├── realtime.py     # SSE 브로드캐스터
│   │   └── static/
│   │       └── index.html  # 대시보드 HTML
│   ├── requirements.txt
│   └── Dockerfile
├── simulator/
│   ├── simulate.py         # 시뮬레이터 메인
│   ├── sample_data/
│   │   └── route.json      # 샘플 버스 경로
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🛠️ 로컬 개발 실행

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Simulator

```bash
cd simulator
pip install -r requirements.txt

# 기본 실행 (3분, 1x 속도)
python simulate.py

# 옵션 사용
python simulate.py --speed 5 --minutes 3 --bus-id bus-2

# 환경 변수로 백엔드 URL 지정
BACKEND_URL=http://localhost:8000 python simulate.py
```

### Simulator 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--speed` | 1.0 | 시뮬레이션 속도 배율 |
| `--minutes` | 3.0 | 시뮬레이션 시간 (분) |
| `--bus-id` | bus-1 | 버스 ID |
| `--route` | sample_data/route.json | 경로 JSON 파일 |

## 📡 API 명세

### POST /events
이벤트 수신 및 저장 (중복 제거 적용)

**Request Body:**
```json
{
  "type": "fallen_pm",
  "bus_id": "bus-1",
  "lat": 37.5665,
  "lon": 126.9780,
  "confidence": 0.85,
  "timestamp": "2024-01-08T10:30:00Z"
}
```

**Response:**
```json
{
  "kind": "new",  // or "update"
  "event": {
    "id": "uuid",
    "type": "fallen_pm",
    "bus_id": "bus-1",
    "first_seen_at": "2024-01-08T10:30:00",
    "last_seen_at": "2024-01-08T10:30:00",
    "lat": 37.5665,
    "lon": 126.9780,
    "confidence": 0.85,
    "grid_key": "37.5665:126.978",
    "occurrence_count": 1,
    "dedup_group_id": "..."
  }
}
```

### GET /events
최근 N시간 이벤트 목록 조회

**Query Parameters:**
- `hours`: 조회할 시간 범위 (기본: 24, 최대: 168)

### GET /stream
SSE 실시간 이벤트 스트림

**Event Format:**
```
data: {"kind": "new", "event": {...}}

data: {"kind": "update", "event": {...}}
```

### GET /health
헬스 체크

## 🔧 중복 제거 규칙

1. **Grid Key**: 위도/경도를 소수점 4자리로 반올림
   - `grid_key = f"{round(lat,4)}:{round(lon,4)}"`
   
2. **Time Window**: 10분 (600초)

3. **동작**:
   - 같은 `grid_key` + 같은 `type`이 time_window 내 재발생:
     - `last_seen_at` 갱신
     - `occurrence_count` +1
     - 더 높은 confidence면 갱신
   - 처음 발생: 새 이벤트 생성

## 🎨 대시보드 기능

- **실시간 지도**: 서울 시청 주변 다크 테마 지도
- **이벤트 마커**: 신뢰도에 따른 크기/색상
- **이벤트 목록**: 시간순 정렬, 클릭 시 지도 포커스
- **통계**: 총 이벤트 수, 오늘 발생 수
- **연결 상태**: 실시간 SSE 연결 상태 표시

## 🐛 트러블슈팅

### Docker 관련

```bash
# 컨테이너 로그 확인
docker-compose logs -f

# 컨테이너 재시작
docker-compose restart

# 완전히 새로 빌드
docker-compose down
docker-compose up --build
```

### 데이터베이스 초기화

```bash
# data 디렉토리 삭제 후 재시작
rm -rf data/
docker-compose up --build
```

## 📝 다음 단계 (2단계 계획)

- [ ] 실제 YOLO 모델 연동
- [ ] 다중 버스 지원
- [ ] 알림 시스템 (웹훅/이메일)
- [ ] PostgreSQL 마이그레이션
- [ ] Kubernetes 배포
