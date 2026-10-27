import os
import sys
import json
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

# 현재 디렉터리 경로 등록 (단독 실행 및 패키지 임포트 양방향 호환 지원)
_curr_dir = Path(__file__).resolve().parent
if str(_curr_dir) not in sys.path:
    sys.path.insert(0, str(_curr_dir))

# 1. 과목 내부 모듈 임포트
try:
    from .quiz_logs import (
        save_quiz_log,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_or_create_user,
        get_user_status,
    )
except ImportError:
    from quiz_logs import (
        save_quiz_log,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_or_create_user,
        get_user_status,
    )

# 2. [가이드라인 261008 표준] 환경변수 다중 계단식 폴백 로드 (.env -> 상위 .env -> 시스템 환경변수)
_curr_path = Path(__file__).resolve().parent

def find_and_load_api_key() -> str:
    """
    1) 현재 과목 폴더의 .env 확인
    2) 상위 부모 폴더(프로젝트 루트) 순차 탐색
    3) OS 시스템 환경변수(os.environ) 확인
    """
    # 1) 현재 과목 폴더 .env
    if (_curr_path / ".env").exists():
        load_dotenv(dotenv_path=_curr_path / ".env", override=True)
    else:
        # 2) 상위 부모 폴더(루트) .env 탐색
        for folder in _curr_path.parents:
            env_file = folder / ".env"
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=True)
                break
        else:
            load_dotenv(override=True)

    # 3) 환경변수 및 시스템 환경변수(os.environ) 최종 추출
    key = os.getenv("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return key.strip()


# 가이드라인 절대 원칙: 하위 버전 불가, 무조건 gemini-3.5-flash-lite 단일 모델만 사용
MODEL_NAME = "gemini-3.5-flash-lite"


def get_genai_client() -> Optional[genai.Client]:
    """Google GenAI SDK v1 규격 클라이언트 동적 생성"""
    key = find_and_load_api_key()
    if not key:
        return None
    try:
        return genai.Client(api_key=key, http_options={"api_version": "v1"})
    except Exception:
        return None


client = get_genai_client()

# 3. 조장의 통합 서버(app/main.py)에 바로 꽂히는 표준 규격 (Step B)
router = APIRouter(prefix="/english", tags=["초등영어"])

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "index.html"
LOGO_PATH = BASE_DIR / "edumate_logo.svg"
CURRICULUM_PATH = BASE_DIR / "curriculum.txt"


def load_curriculum() -> str:
    if CURRICULUM_PATH.exists():
        try:
            return CURRICULUM_PATH.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


CURRICULUM_TEXT = load_curriculum()


# 4. 메인 화면 및 공통 로고 서빙
@router.get("/", response_class=HTMLResponse)
async def serve_subject_index():
    """초등영어 학습관 메인 퀴즈 웹페이지 반환"""
    if HTML_PATH.exists():
        return FileResponse(HTML_PATH)
    raise HTTPException(status_code=404, detail="index.html 파일을 찾을 수 없습니다.")


@router.get("/logo.svg")
async def serve_logo():
    """공통 에듀메이트 로고 SVG 반환"""
    if LOGO_PATH.exists():
        return FileResponse(LOGO_PATH, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="edumate_logo.svg 파일을 찾을 수 없습니다.")


# 5. 학생 계정 및 포켓몬 진화 등급 조회 API
@router.get("/api/user")
async def get_user_info(
    user_name: str = Query("김에듀"),
    grade: Optional[int] = Query(4),
    pokemon_type: str = Query("grass"),
):
    """학생의 누적 점수 및 포켓몬 5대 타입 진화 등급(EXP) 실시간 조회"""
    return get_or_create_user(user_name=user_name, grade=grade, pokemon_type=pokemon_type)


# 6. 문제 채점 결과 DB 저장 API
class SaveQuizRequest(BaseModel):
    user_name: str = "김에듀"
    quiz_id: Optional[str] = None
    grade: Optional[int] = None
    unit: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    question: str = ""
    user_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    solution: Optional[str] = None
    earned_score: int = 0
    is_correct: bool = False
    is_solution_revealed: bool = False


@router.post("/api/save-quiz")
async def submit_quiz_log(req: SaveQuizRequest):
    """
    객관식/주관식/서술형 풀이 결과를 quiz_logs 테이블에 기록하고 전과목 누적 총점에 자동 합산합니다.
    - 미사용 항목은 파이썬 None(DB NULL)으로 안전하게 기록됩니다.
    """
    res = save_quiz_log(
        user_name=req.user_name,
        quiz_id=req.quiz_id,
        grade=req.grade,
        unit=req.unit,
        topic=req.topic,
        difficulty=req.difficulty,
        question_type=req.question_type,
        question=req.question,
        user_answer=req.user_answer,
        correct_answer=req.correct_answer,
        solution=req.solution,
        earned_score=req.earned_score,
        is_correct=req.is_correct,
        is_solution_revealed=req.is_solution_revealed,
    )
    return res


# 7. 서술형 AI 문맥 정밀 채점 API
class GradeRequest(BaseModel):
    user_name: str = "김에듀"
    grade: str = "34"
    target_word: str
    user_answer: str
    unit: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = "중"


@router.post("/api/grade")
async def grade_descriptive_answer(req: GradeRequest):
    """
    서술형 문맥 정밀 채점:
    - 1차: 빈 칸 및 미션 단어 누락 사전 방어
    - 2차: Gemini 기반 1~5점 부분 점수 및 맞춤 피드백
    - 3차: 채점 결과를 DB에 즉시 자동 저장하여 log_id와 누적 점수 반환
    """
    user_ans = req.user_answer.strip()
    target = req.target_word.strip()
    grade_int = 4 if req.grade == "34" else 6

    # 사전 검증 1: 공백
    if not user_ans:
        score = 1
        feedback = f"문장이 작성되지 않았어요! 단어 '{target}'를 넣어 문장을 만들어 보세요 💕"
        sample = f"I like {target}."
    # 사전 검증 2: 미션 단어 미포함
    elif target.lower() not in user_ans.lower():
        score = 1
        feedback = f"미션 단어인 '{target}'가 문장에 보이지 않아요! 단어를 쏙 넣어서 완성해 볼까요?"
        sample = f"I like {target}."
    # 단어 1개만 단독 작성
    elif len(user_ans.split()) == 1 and user_ans.split()[0].lower() == target.lower():
        score = 2
        feedback = f"단어 철자는 완벽하지만 아직 문장이 아니에요! 'This is a {target}.'처럼 주어와 동사를 넣어보세요."
        sample = f"This is a {target}."
    else:
        score = None
        feedback = None
        sample = f"I like {target}."

        cli = get_genai_client()
        if cli:
            prompt = f"""
            너는 대한민국 2022 개정 초등영어 전문 친절한 AI 채점 선생님이야.
            초등학생 ({'3~4학년' if req.grade == '34' else '5~6학년'})의 답안을 공정하게 평가해줘.

            [단원 목차 참고]:
            {CURRICULUM_TEXT[:400]}...

            [미션 단어]: {target}
            [학생 작성 문장]: "{user_ans}"

            [채점 기준]:
            - 1점: 단어 미포함 또는 의미 없는 글자
            - 2점: 단어 단독 또는 심한 미완성
            - 3점: 문장 시도는 했으나 주어/동사 누락 등 어색함
            - 4점: 의미가 잘 통하고 관사 등 경미한 실수
            - 5점: 초등 수준에 딱 맞는 완벽한 문장

            반드시 아래 JSON 포맷으로만 응답해:
            {{"score": 5, "feedback": "다정한 피드백 한 줄"}}
            """
            try:
                res = cli.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                raw = res.text.strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                data = json.loads(raw)
                score = int(data.get("score", 4))
                feedback = data.get("feedback", "참 잘했어요!")
            except Exception:
                pass

        if score is None:
            words = user_ans.split()
            is_pattern = any(p in user_ans.lower() for p in ["i like", "this is", "that is", "it is", "i have", "i see"])
            score = 5 if is_pattern else (4 if len(words) >= 3 else 3)
            feedback = f"미션 단어 '{target}'를 넣어 문장을 훌륭하게 완성했어요! 참 잘했어요 👏"

    # 상/중/하 난이도 기준 (가이드라인 표준: 상: 5점 / 중: 3점 / 하: 1점)
    diff_val = req.difficulty or ("상" if req.grade == "56" else "중")
    if diff_val in ["고급", "심화"]:
        diff_val = "상"
    elif diff_val in ["중급", "표준"]:
        diff_val = "중"
    elif diff_val in ["초급", "기초"]:
        diff_val = "하"

    if diff_val == "상" or req.grade == "56":
        point_map = {5: 5, 4: 4, 3: 3, 2: 2, 1: 1}
    elif diff_val == "중":
        point_map = {5: 3, 4: 2, 3: 2, 2: 1, 1: 1}
    else:
        point_map = {5: 1, 4: 1, 3: 1, 2: 0, 1: 0}

    earned_points = point_map.get(score, 1)
    is_corr = (score >= 3)  # 3점 이상 부분 정답 인정

    saved = save_quiz_log(
        user_name=req.user_name,
        quiz_id=f"english_desc_{target}_{user_ans[:10]}",
        grade=grade_int,
        unit=req.unit or "문장 표현",
        topic=req.topic or target,
        difficulty=diff_val,
        question_type="서술형",
        question=f"단어 '{target}'를 사용한 문장 표현 만들기",
        user_answer=user_ans,
        correct_answer=sample,
        solution=feedback,
        earned_score=earned_points,
        is_correct=is_corr,
    )

    return {
        "score": score,
        "eval_score": score,
        "earned_score": earned_points,
        "difficulty": diff_val,
        "feedback": feedback,
        "sample": sample,
        "log_id": saved["log_id"],
        "added_score": saved["added_score"],
        "total_score": saved["total_score"],
    }


# 8. AI 선생님께 이어서 질문하기 API
class ChatRequest(BaseModel):
    log_id: int
    user_name: str = "김에듀"
    student_question: str
    quiz_context: Optional[str] = None


@router.post("/api/chat")
async def chat_with_tutor(req: ChatRequest):
    """
    학생이 특정 문제 카드에서 AI 선생님께 추가 질문을 하면,
    Gemini 친절한 AI 튜터가 답변하고 DB의 chat_history에 누적 저장합니다.
    """
    q = req.student_question.strip()
    if not q:
        return {"reply": "질문을 입력해 주세요! 친절하게 설명해 드릴게요 😊"}

    ai_reply = None
    cli = get_genai_client()
    if cli:
        prompt = f"""
당신은 대한민국 2022 개정 초등학교 영어 전문 다정하고 친절한 AI 선생님입니다.
초등학생이 방금 푼 영어 문제에 대해 다음과 같이 추가 질문을 하였습니다.

[문제 상황 / 어휘 / 지문]: {req.quiz_context or '초등영어 어휘 및 문장 학습'}
[학생 질문]: "{q}"

[선생님 답변 절대 규칙 (필수 준수)]:
1. **동문서답 절대 금지 (핵심 답변 우선 제시)**:
   - 학생 질문의 핵심(예: 동의어/다른 표현, 철자 차이, 문맥상 쓰임새)에 대한 정확한 영어 표현과 답변을 첫 문장에 바로 명쾌하게 제시하세요.
   - 예: "window 말고 다른 표현도 있나요?" 질문 시 -> "네, 맞아요! 창문(window) 외에도 창문 유리창은 'pane', 지붕에 달린 채광창은 'skylight', 활짝 여닫는 창문은 'casement'라고도 불러요." 처럼 구체적인 단어를 즉시 알려주세요.
2. **초등학생 눈높이 칭찬과 예시**:
   - 질문한 학생을 칭찬하고, 쉬운 예문 1개를 곁들여 2~3문장 이내로 다정하고 따뜻하게 설명해 주세요.
3. 100% 한국어로 설명하고 문장 부호와 이모티콘을 적절히 활용하세요.
"""
        try:
            res = cli.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )
            if res and res.text and res.text.strip():
                ai_reply = res.text.strip()
        except Exception:
            pass

    if not ai_reply:
        # 지능형 상황별 폴백 응답
        if "다른" in q and ("표현" in q or "단어" in q or "말" in q):
            ai_reply = f"좋은 질문이에요! '{req.quiz_context or '해당 단어'}'와 관련된 표현으로 상황에 따라 다양한 유의어가 있어요. 단어장을 찾아보거나 비슷한 표현을 소리 내어 연습해보면 실력이 쑥쑥 늘어요! ✨"
        else:
            ai_reply = f"훌륭한 질문이에요! '{q}'에 대해 호기심을 갖는 모습이 정말 멋져요. 배운 표현을 소리 내어 말해보고 나만의 문장을 만들어보면 훨씬 쉽게 익힐 수 있답니다! 👏"

    append_chat_message(req.log_id, q, ai_reply)
    return {"reply": ai_reply, "log_id": req.log_id}


# 9. 문제 즐겨찾기 토글 API
class FavoriteRequest(BaseModel):
    log_id: int


@router.post("/api/favorite")
async def toggle_quiz_favorite(req: FavoriteRequest):
    """문제 즐겨찾기(is_favorite) 토글"""
    return toggle_favorite(req.log_id)


# 10. 취약 단원 분석 API
@router.get("/api/weakest")
async def get_weakest(user_name: str = Query("김에듀")):
    """학생의 오답 내역을 분석하여 가장 취약한 단원 반환"""
    return get_weakest_unit_and_topic(user_name)


# ---------------------------------------------------------------------------
# [가이드라인 261008 표준] 과목 담당 조원 단독 테스트 실행 블록
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    import webbrowser

    # 단독 실행용 FastAPI 인스턴스 (변수명을 반드시 app으로 지정)
    app = FastAPI(title="EduMate AI - 초등영어 단독 테스트 서버")
    app.include_router(router)

    @app.get("/")
    async def root_page():
        return FileResponse(str(HTML_PATH))

    PORT = 8000
    print(f"\n🚀 [초등영어] 로컬 테스트 서버 구동: http://localhost:{PORT}/english/\n")
    webbrowser.open(f"http://localhost:{PORT}/english/")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

