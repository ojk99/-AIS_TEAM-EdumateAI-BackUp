2026-10-14 답안 범위 확대: 한자어 40개 모두 뜻·음 순서 자유 채점. 9급 한자어 9개에도 공통 적용. 女 여자/계집(녀·여), 父 아버지/아비, 日 해/날, 母 어머니/어미, 男 사내/남자 등의 인정 훈 추가. 기존 accepted_huneum 자료는 보존. 학습 카드의 기본 표기는 유지하며 널리 쓰는 별도 훈을 정답으로 허용. 기존 저장 결과는 자동 변경하지 않음.

# 2026-10-13 최신 팀 DB·로고·Step B 연동

방금 전달된 quiz_logs.py가 DB 규격의 기준입니다.
공통 모듈은 SUBJECT_NAME = "hanja" 한 줄만 변경했으며 18개 칼럼의 이름·순서를 그대로 유지합니다.
이 버전의 총점은 users 테이블 대신 quiz_logs의 earned_score 합계로 산출합니다.
학생 상태/진화 등급은 get_user_status()를 사용합니다. 5개 포켓몬 타입의 단계·티어를 그대로 표시합니다.
없는 함수명을 공통 파일에 추가하지 않았습니다. team_db.py에서 기존 is_favorite/chat_history 칼럼을 사용해 즐겨찾기·추가 질문·취약 내용 조회를 제공합니다.
선택 항목이 없는 경우 None으로 넘깁니다. options/rubric은 이 최신 표준 테이블의 칼럼에 없으므로 별도 칼럼을 만들지 않습니다.

## 팀원에게 전달
app/subjects/hanja/ 전체와 의존성 목록을 전달하세요.
조장 app/main.py에서 `from app.subjects.hanja.router import router` 다음 `app.include_router(router)`.
라우터 prefix는 /hanja, tags는 초등한자이며 /hanja/는 index.html을 FileResponse로 직접 반환합니다.
공식 로고는 /hanja/logo.svg, 로고 링크는 메인 로비 / 입니다.
단독 서버의 /는 /hanja/로 돌아가며 팀 통합 서버의 /는 조장이 제공하는 로비를 사용합니다.
다른 팀 공통 파일은 덮어쓰지 마세요.

## 포털 계정
localStorage edumate_current_account(계정 JSON 또는 학생명)와 edumate_pokemon_type을 읽습니다.
계정 JSON의 user_name/username/name/user_id, grade를 지원합니다.
해당 정보는 한자 API 헤더로 전달되고 로그는 이름 기준으로 합산됩니다.
계정이 없으면 브라우저별 게스트 식별자로 저장합니다. 기존 개인 기록은 자동으로 중앙 DB에 이관하거나 합산하지 않습니다.
포털 로그인 인증 자체는 조장의 공통 서버가 맡습니다. localStorage 정보만으로 서버 인증을 구현한 것은 아닙니다.

## DB와 저장
팀 통합 환경의 중앙 DB는 data/edumate.db입니다.
기존 data/hanja.sqlite3는 문제 세션/채점 재시도용 캐시로 남기고, 화면의 풀이 내역·누적 점수는 최신 중앙 DB를 조회합니다.
새 채점 결과에는 log_id가 포함됩니다. 다시 제출해도 같은 문제는 중복 합산하지 않습니다.
중앙 저장 실패 시 재제출할 수 있습니다. 중앙 저장 성공 후 개인 캐시 실패 시 재제출해도 점수가 다시 늘지 않습니다.
기존 score_hook을 추가 연결하여 같은 획득 점수를 두 번 합산하지 않습니다.

## 화면 기능
전 과목 누적 점수와 진화 단계·경험치 표시.
채점 후 오른쪽 기록 영역에서 즐겨찾기 및 AI 선생님 추가 질문 가능.
추가 질문은 실제 Gemini 연결이 필요하며 연결 실패 시 대화 내역에 가짜 답을 저장하지 않습니다.
취약 내용 맞춤 복습은 한자 과목의 오답을 집계해 사자성어/한자/실용 한자어 중 관련 문제를 다시 냅니다.
즐겨찾기·대화는 해당 log_id에 누적됩니다. 즐겨찾기 목록 전용 화면은 아직 없습니다.

## 검증과 되돌리기
pytest 13개 통과, 화면 상태 회귀 검사 통과.
전 과목 합산, 다른 학생 로그 접근 분리, 중복 저장, NULL, 18칼럼 불변, 즐겨찾기 전환, 대화 저장, 취약 문제 출제, 저장 실패 재시도를 검증했습니다.
AI 대화 검사는 모의 응답으로 수행했습니다. 실제 조장의 포털과 계정 JSON 연결은 팀 환경에서 최종 확인하세요.
rollback/Hanja-Team-Rollback-20261013.zip은 이번 통합 전 버전입니다.
서버를 끈 뒤 기존 DB와 .env는 보존하고 소스만 이전 버전으로 되돌리세요.
공개 chatgpt.site는 이번 작업으로 변경하지 않았습니다.

---
이전 설치·실행 안내:

# EduMate 한자 팀 통합 패키지 — 2026-10-12

새 guideline.txt의 폴더 규격·단독 실행·환경변수 탐색·Google GenAI SDK를 적용했습니다.
공개 사이트는 변경하지 않았습니다. 팀 화면은 공개 사이트의 사자성어 30개 기능으로 동기화했습니다.

## 설치와 실행
Python 3.11 이상, 프로젝트 루트에서 `python -m pip install -r requirements.txt`.
- 한자 폴더 `app/subjects/hanja/`에서 `python router.py`
- 같은 폴더에서 `uvicorn router:app --port 8000 --reload`
- 프로젝트 루트에서 `uvicorn app.main:app --port 8000 --reload`
학습 화면: http://localhost:8000/hanja/ (루트 /는 단독 서버에서 이 주소로 이동).

## 팀 병합
`app/subjects/hanja/`만 팀 저장소에 전달합니다. 조장 main.py에서
`from app.subjects.hanja.router import router` 후 `app.include_router(router)`.
`create_router(storage=..., score_hook=...)`로 공통 DB 엔진·총점 함수에 연결할 수도 있습니다.
루트 app/main.py는 실행 예시이므로 팀 공통 파일을 덮어쓰지 마세요.
필수 router.py, index.html, curriculum.txt 및 보조 파일을 갖추었습니다.
ORM 모델/저장은 models.py와 storage.py에 있습니다. quiz_logs.py는 선택 항목으로, 기존 저장 모듈을 사용합니다.

## API 키
한자 폴더 또는 프로젝트 루트에 .env 파일을 만들고 `GEMINI_API_KEY=발급받은키` 또는 `GOOGLE_API_KEY=발급받은키`를 입력합니다.
같은 키의 우선순위: 과목 폴더 > 가까운 상위 폴더 > 프로젝트 루트 > OS 환경변수.
파일이 있어도 키가 없으면 계속 상위 설정을 확인합니다. OS 값은 덮어쓰지 않습니다.
키가 없으면 한글로 안내하고 기본 채점/예문을 사용합니다. 서버 시작을 막지 않습니다.
모델 기본 선호값: gemini-3.5-flash-lite. 실제 키의 모델 목록에 없으면 사용 가능한 Flash 모델을 선택합니다.
`HANJA_GEMINI_MODEL`로 원하는 모델을 설정할 수 있습니다.
API v1을 우선 사용하며, 기능 미지원(400/404)이면 v1beta로 재시도합니다.
가이드 예시는 v1을 명시하지만 모든 모델/구조화 기능을 v1이 지원한다고 가정하지 않습니다.
`HANJA_GEMINI_API_VERSION=v1beta`로 직접 지정할 수 있습니다.
기존 AI REST 호출 대신 공식 google-genai SDK의 비동기 API를 사용합니다.

## 기록과 채점
로그인 없이 브라우저별 식별자로 풀이 상세 로그를 SQLAlchemy/SQLite에 저장합니다.
누적 점수는 중복 없는 풀이 기록의 합입니다. 이전 기록 DB를 삭제하지 마세요.
사자성어는 1/3/5점, 빈 답은 제출 차단, 채점 결과 후 직접 다음 문제로 이동합니다.
실용 한자어는 정답 1점/오답 0점, AI는 예문만 생성합니다.
AI 오류 시 기본 연습 채점/준비된 예문으로 전환하고 결과에 표시합니다.
다른 기기·브라우저는 별도 기록이며 계정 연결은 아직 없습니다.

## 되돌리기
함께 제공되는 Hanja-Team-Rollback-20261012.zip은 수정 전 소스입니다.
서버를 끄고 현재 소스를 백업한 뒤 이전 소스로 교체하세요.
실제 .env와 data/hanja.sqlite3는 교체하지 마세요. 기존 누적 기록은 그대로 보존할 수 있습니다.
이번 변경은 DB 스키마를 변경하지 않습니다.
공개 사이트 소스 ZIP과 이 FastAPI 통합용 패키지는 별개입니다.

## 2026-10-13 환경변수 키 호환
서버 실행자의 OS/호스팅 환경변수에 GEMINI_API_KEY 또는 GOOGLE_API_KEY가 있으면 .env 없이 사용할 수 있습니다. 두 이름에 모두 유효한 값이 있으면 GEMINI_API_KEY가 우선합니다. 각 이름의 설정 탐색은 기존 .env 우선순위를 유지합니다. 키가 없으면 기본 연습 모드로 동작합니다. 일반 학습자의 웹 브라우저가 아니라 서버를 실행하는 환경의 키를 사용합니다. 배포 시 서버 관리자가 환경변수를 등록하세요. 소스 ZIP에 실제 키를 넣지 않습니다.
