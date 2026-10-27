# 🔬 EduMate AI - 초등 과학 전담 학습관

> 2022 개정 교육과정 기반 초등학교 1~6학년 과학 AI 실시간 온디맨드 퀴즈 모듈  
> **프로젝트 표준 구조 및 과목 격리 원칙(내 방 원칙)**을 100% 준수한 독립 패키지입니다.

---

## 📁 1. 폴더 및 파일 구성 (`science/`)

| 파일/폴더명 | 역할 및 설명 |
| :--- | :--- |
| **`curriculum.txt`** | 초등 1~6학년 과학 단원 목차 데이터 (도메인: 생명, 지구, 물질, 화학, 천문, 융합) |
| **`service.py`** | Google GenAI SDK (`gemini-3.5-flash-lite`, `api_version: "v1"`) 기반 AI 3대 모드 출제 및 CoT 문맥 채점 엔진 |
| **`database.py`** | MySQL 연결 우선 시도 -> 연결 실패 시 로컬 SQLite(`data/quiz_logs.db`) 무중단 안전 계단식 폴백 DB 모듈 |
| **`router.py`** | FastAPI 표준 `APIRouter` (팀 중앙 서버 결합용) + 단독 테스트(Standalone) 서버 내장 |
| **`index.html`** | 초등 과학 전용 웹 프론트엔드 (3대 모드 + 📖 스마트 오답노트 + 🚨 실시간 문제 오류 신고 모달) |
| **`data/`** | 로컬 SQLite 데이터베이스 파일(`quiz_logs.db`) 저장 폴더 |
| **`reported_issues/`** | 사용자가 실시간 접수한 문제 오류 신고 백업 JSON 저장 폴더 |
| **`saved_results/`** | 서술형 문맥 채점 결과 자동 아카이빙 폴더 (JSON 리포트 저장소) |
| **`error_analysis/`** | 17대 핵심 오류 분석 리포트 및 실제 케이스 JSON 데이터 |
| **`requirements.txt`** | 실행에 필요한 필수 파이썬 라이브러리 목록 (SQLAlchemy, PyMySQL 포함) |
| **`README.md`** | 과목 소개, 명세서 및 실행 가이드 (본 문서) |

---

## 🎯 2. 주요 기능 (3대 퀴즈 모드 + 스마트 오답노트 + 오류 신고)
1. **⭕❌ OX 퀴즈**: 한 문제씩 풀고 바로 정오답 소리와 해설을 확인하는 스피드 퀴즈 모드 (틀린 문제 오답노트 자동 등록)
2. **📝 5지선다 객관식**: 초등 교과 핵심 개념 중심 5지선다형 정밀 퀴즈 모드 (음성 TTS 지원, 오답 자동 등록)
3. **✍️ 서술형 문맥 채점**: 
   - 10문제 연속 풀이 및 생각 힌트 토글 서랍 제공
   - Gemini AI의 Chain-of-Thought(사고 과정) 기반 0~5점 정밀 문맥 채점
   - 1~2문장의 초등 눈높이 다정한 원포인트 피드백 및 모범 답안 제시
   - 채점 결과 자동 파일 저장(`saved_results/`) 및 5점 미만 감점 문제 오답노트 자동 연동
4. **📖 스마트 오답노트 (Wrong Answer Notebook)**:
   - MySQL / SQLite 무중단 연동으로 틀린 문제만 모아보기
   - 학년별 / 문제유형별 필터링, 정답/해설 확인, [다시 풀어보기] 및 [개념 마스터 완료] 관리
5. **🚨 실시간 문제 오류 신고 시스템**:
   - 각 문제 카드마다 원클릭 `[🚨 오류 신고]` 버튼 제공
   - 지문 오류, 정답 오류, 채점 오류, 난이도 부적절 등 유형별 접수 및 DB/JSON 동시 안전 보관

---

## 🚀 3. 실행 방법

### 방법 A. 조원 단독 로컬 테스트 (Standalone)
팀 서버 없이 본인 컴퓨터에서 단독으로 테스트할 수 있습니다.

1. **사전 준비**: 루트 또는 본 폴더에 `.env` 파일이 있는지 확인합니다:
   ```env
   GEMINI_API_KEY=본인의_구글_API_키
   ```
2. **실행 방법 (택1)**:
   - **방식 1 (가장 쉬움 - 마우스 더블 클릭 ⭐)**:
     - 폴더 안의 **`run.bat`** 파일을 **더블 클릭**하면 끝! (서버 실행 및 브라우저 창 자동 오픈)
   - **방식 2 (파이썬 직접 실행)**:
     ```bash
     cd D:\AIS26L\Project\science
     python router.py
     ```
   - **방식 3 (수업 표준)**: 코드 수정 실시간 반영(Reload) Uvicorn 실행
     ```bash
     cd D:\AIS26L\Project\science
     uvicorn router:app --port 8000 --reload
     ```
3. 브라우저에서 `http://localhost:8000` 으로 접속하여 문제 풀이 및 탭 전환을 테스트합니다.

---

### 방법 B. 팀 중앙 서버 결합 (조장 / 테크 리더용)
팀 메인 서버(`core/app.py` 또는 `main.py`)에 단 2줄로 플러그인처럼 장착됩니다:

```python
from science.router import router as science_router

# FastAPI 메인 앱에 장착
app.include_router(science_router)
```
- 장착 후 접속 주소: `http://localhost:8000/science`

---

## 📡 4. API 엔드포인트 명세

| Method | Endpoint | 설명 | 요청 Body 예시 |
| :--- | :--- | :--- | :--- |
| **GET** | `/science` | 과학 퀴즈 웹 화면 서빙 | - |
| **GET** | `/science/api/curriculum` | 1~6학년 과학 단원 목차 데이터 조회 | - |
| **POST** | `/science/api/quiz` | 실시간 10문제 출제 (OX 또는 5지선다) | `{"grade": 3, "unit": "자석의 이용", "mode": "ox"}` |
| **POST** | `/science/api/quiz/mcq` | 5지선다 객관식 전용 출제 | `{"grade": 3, "unit": "자석의 이용", "mode": "mcq"}` |
| **POST** | `/science/api/quiz/subjective` | 서술형 10문제 실시간 출제 | `{"grade": 4, "unit": "화산과 지진"}` |
| **POST** | `/science/api/quiz/evaluate_batch` | 서술형 10문제 일괄 AI 문맥 채점 및 자동 저장 | `{"grade": 4, "unit": "...", "answers": [...]}` |
| **GET** | `/science/api/history` | 과거 서술형 채점 리포트 목록 조회 | - |
| **GET** | `/science/api/history/{filename}` | 특정 채점 리포트 상세 데이터 조회 | - |

---

## 🔒 5. 보안 및 Git 협업 원칙 (필수)
- `.env` 파일은 절대 Git에 커밋하지 않습니다.
- Git 커밋 시 반드시 본인 작업 폴더만 콕 집어서 추가합니다:
  ```bash
  git add science/
  git commit -m "feat(science): 초등 과학 실시간 AI 출제 및 서술형 채점 통합 모듈 완성"
  git push origin feature/science
  ```
