# 🔬 EduMate AI - 초등 과학 전담 학습관

> 2022 개정 교육과정 기반 초등학교 1~6학년 과학 AI 실시간 온디맨드 퀴즈 모듈  
> **프로젝트 표준 구조 및 과목 격리 원칙(내 방 원칙)**을 100% 준수한 독립 패키지입니다.

---

## 📁 1. 폴더 및 파일 구성 (`science/`)

| 파일/폴더명 | 역할 및 설명 |
| :--- | :--- |
| **`curriculum.txt`** | 초등 1~6학년 과학 단원 목차 데이터 (도메인: 생명, 지구, 물질, 화학, 천문, 융합) |
| **`service.py`** | Google GenAI SDK (`gemini-3.5-flash-lite`, `api_version: "v1"`) 기반 AI 출제 및 문맥 채점 엔진 |
| **`question_bank.py`** | 조장 표준 문제은행 모듈 (`question_bank`, `question_bank_solved` 표준 스키마 및 AI 채점 연동) |
| **`question_bank.db`** | 초등 과학 전용 SQLite 문제은행 로컬 데이터베이스 (1~6학년 대표 17문항 시드 탑재) |
| **`quiz_logs.py`** | EduMate AI 팀 공통 표준 DB (`quiz_logs`, `accounts`) 연동, 누적점수/포켓몬 등급 및 취약단원 집계 |
| **`database.py`** | MySQL 연결 우선 시도 -> 연결 실패 시 로컬 SQLite(`data/quiz_logs.db`) 무중단 안전 계단식 폴백 DB 모듈 |
| **`router.py`** | FastAPI 표준 `APIRouter` (팀 중앙 서버 결합 단일 접점) + 단독 테스트(Standalone) 서버 내장 |
| **`index.html`** | 초등 과학 전용 웹 프론트엔드 (AI 출제 토글, (2/32) 단원 현황, 스마트 오답노트, 복사 가능한 오류 모달) |
| **`data/`** | 로컬 SQLite 데이터베이스 파일(`quiz_logs.db`) 저장 폴더 |
| **`reported_issues/`** | 사용자가 실시간 접수한 문제 오류 신고 백업 JSON 저장 폴더 |
| **`requirements.txt`** | 실행에 필요한 필수 파이썬 라이브러리 목록 |
| **`README.md`** | 과목 소개, 명세서 및 실행 가이드 (본 문서) |

---

## 🎯 2. 주요 기능 및 최신 표준 반영

1. **📚 표준 문제은행 DB 및 양방향 3단계 자동 폴백 시스템**:
   - **토글 ON (AI 출제 모드)**: 실시간 Gemini AI 온디맨드 10문제 생성.
   - **토글 OFF (문제은행 모드)**: `question_bank.db`에서 미풀이 문제를 우선 출제하며, 단원 버튼에 `(맞춘 문제/전체 문제)` 실시간 표기 (정답 시 `mark-solved` 자동 갱신).
   - **정방향 폴백**: 문제은행 문제가 없거나 소진 시 ➡️ 자동으로 AI 실시간 출제로 자동 전환.
   - **역방향 폴백 (3단계 안전망)**: AI 서버 연결 장애 시 ➡️ 1단계: 미풀이 은행문제 출제 ➡️ 2단계: 기풀이 문제 복습 모드 랜덤 출제 (누적 포인트 미반영 배너 안내) ➡️ 3단계: 은행문제 0개 시 명확한 에러 안내 모달 팝업.
2. **✍️ 직접 출제(문제은행) 주관식 · 서술형 AI 문맥 채점**:
   - 문제은행 문제도 단순 문자열 일치에 국한되지 않고, AI 의미 동치 판별 및 부분 점수(1~5점) 채점 지원.
3. **🎯 취약 단원 맞춤 추천 (풀이 방식까지 100% 자동 세팅)**:
   - 과거 오답 분석을 통해 가장 취약한 학년/단원뿐만 아니라 **문제 풀이 방식(OX / 5지선다 / 서술형)**까지 콕 집어 자동 탭 전환 및 맞춤 단원 세팅.
4. **📖 계정별 분리 스마트 오답노트 & 📂 지난 채점 리포트 아카이브**:
   - 계정 고유 ID(`user_id`) 및 이름(`user_name`)을 기준으로 오답노트와 지난 리포트가 안전하게 격리되어 조회.
5. **🚨 복사 가능한 오류 안내 모달 & 실시간 오류 신고 시스템**:
   - 브라우저 기본 경고창 대신 마우스 드래그 및 `[📋 오류 내용 복사하기]` 원클릭 클립보드 복사 모달 제공.

---

## 🚀 3. 실행 방법

### 방법 A. 조원 단독 로컬 테스트 (Standalone)
팀 서버 없이 본인 컴퓨터에서 단독으로 테스트할 수 있습니다.
```bash
cd science
python router.py
# 또는
uvicorn router:app --port 8000 --reload
```
- 브라우저 접속 주소: `http://localhost:8000`

---

### 방법 B. 팀 메인 관제탑 결합 (조장 전용 - 단 2줄 장착)
조장님의 메인 FastAPI 서버(`app/main.py`)에 단 2줄로 플러그인처럼 장착됩니다:

```python
# 조장과의 유일한 결합 접점 (내 방 격리 원칙)
from app.subjects.science.router import router as science_router

app.include_router(science_router)
```
- 메인 통합 후 접속 주소: `http://localhost:8000/science`

---

## 📡 4. API 엔드포인트 명세

| Method | Endpoint | 설명 |
| :--- | :--- | :--- |
| **GET** | `/science` | 초등 과학 퀴즈 웹 화면 서빙 |
| **GET** | `/science/api/curriculum` | 1~6학년 과학 단원 목차 데이터 조회 |
| **POST** | `/science/api/quiz` | OX / 5지선다 퀴즈 출제 (AI ↔ 문제은행 양방향 폴백) |
| **POST** | `/science/api/quiz/subjective` | 서술형 10문제 출제 (양방향 폴백) |
| **POST** | `/science/api/quiz/evaluate_batch` | 10문제 서술형 답안 AI 일괄 문맥 채점 & DB 저장 |
| **GET** | `/science/api/history` | 과거 10문제 채점 리포트 아카이브 목록 조회 |
| **GET** | `/science/api/recommend/weakness` | 학생별 취약 단원 및 문제 풀이 방식 맞춤 추천 |
| **GET** | `/science/api/question-bank/unit-stats` | 단원별 문제은행 (맞춘 문제/전체 문제) 통계 조회 |
| **POST** | `/science/api/question-bank/mark-solved` | 문제은행 정답 풀이 완료 기록 |
| **POST** | `/science/api/question-bank/grade` | 문제은행 주관식/서술형 AI 문맥 채점 |

---

## 🔒 5. 보안 및 Git 협업 원칙 (필수)
- `.env` 파일은 절대 Git에 커밋하지 않습니다.
- Git 커밋 시 반드시 본인 작업 폴더만 콕 집어서 추가합니다:
  ```bash
  git add science/
  git commit -m "feat(science): 초등 과학 실시간 AI 출제 및 서술형 채점 통합 모듈 완성"
  git push origin feature/science
  ```
