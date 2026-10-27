# 프로젝트 개요
- 프로젝트 이름: 매일 해야할 일을 기록하고 관리하는 AI 기반 웹 서비스
- 목적: 
  - Google Gemini API 및 Hugging Face 모델 파이프라인을 LangChain으로 결합
  - FastAPI와 Jinja2 템플릿을 통해 웹 서비스를 제공하는 풀스택 서비스
  - 매일의 일상을 LLM API를 연동하여 분석하고 관리하여 개선 사항을 찾아내는 서비스

# 프로젝트 아키텍처
- 기술 스택
  - 언어: Python 3.13.14
  - 웹 프레임워크: FastAPI
  - 템플릿 엔진: Jinja2
  - 데이터베이스 & ORM: MySQL 8.4.x, SQLAlchemy 2.x
  - AI LLM 프레임워크: LangChain, langchain-google-genai(Google Gemini)
  - 환경 관리: 아나콘다 가상환경(ais)
  
# 디렉터리 구조
- .git/                  # Git 저장소
- app
    - auth/              # 패스워드 암호화 및 JWT 인증
    - config/            # 설정(config.py), 환경 설정 모듈
    - database/          # 데이터베이스 접속 및 ORM
    - routers/           # API 라우트 엔드포인트
    - schemas/           # Pydantic 요청/응답 DTO
    - models/            # SQLAlchemy DB 엔티티 모델
    - main.py            # 최초 시작 모듈
- web
    - templates/         # Jinja2 HTML 템플릿 파일
    - static/            # CSS, JS, 이미지 정적 파일
- sql/                   # 데이터베이스 생성 및 사용자 생성 sql 파일들
- tests/                 # pytest 단위 및 통합 테스트
- ANTIGRAVITY.md         # 에이전트 컨텍스트 가이드
- requirements.txt       # 의존성 패키지 목록
- .env                   # 환경 변수
- .gitattributes         # Git 속성 파일
- .gitignore             # Git 제외 정보 파일

# 프로젝트 기능 목록  
- 로그인
  - 로그인
  - 회원가입
- 할일 목록
  - 추가
  - 변경
  - 삭제
