import os
import sys
import re
import ssl
import json
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
import urllib.request
import urllib.parse
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
    from .question_bank import (
        init_question_bank_db,
        get_unit_bank_stats,
        mark_bank_question_solved,
        fetch_next_bank_question,
        save_question_to_bank,
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
    from question_bank import (
        init_question_bank_db,
        get_unit_bank_stats,
        mark_bank_question_solved,
        fetch_next_bank_question,
        save_question_to_bank,
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


# 팀 가이드라인(gemini-3.5-flash-lite) 및 구글 권장(gemini-3.8-flash) 공식 모델 우선순위 리스트
OFFICIAL_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
MODEL_NAME = OFFICIAL_MODELS[0]


def get_genai_client() -> Optional[genai.Client]:
    """Google GenAI SDK 클라이언트 동적 생성 (표준 및 v1 이중 호환)"""
    key = find_and_load_api_key()
    if not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception:
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
@router.get("", response_class=HTMLResponse)
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
    user_id: Optional[str] = Query(None),
    grade: Optional[int] = Query(4),
    pokemon_type: str = Query("grass"),
):
    """학생의 누적 점수 및 포켓몬 5대 타입 진화 등급(EXP) 실시간 조회"""
    return get_or_create_user(user_name=user_name, grade=grade, pokemon_type=pokemon_type, user_id=user_id)


# 6. 문제 채점 결과 DB 저장 API
class SaveQuizRequest(BaseModel):
    user_id: Optional[str] = None
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
        user_id=req.user_id,
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


# 7. 주관식: 대화 속 빈칸 핵심 어휘 AI 생성 API (문제은행 + AI 무한 생성)
class GenerateShortRequest(BaseModel):
    grade: str = "34"
    category: Optional[str] = "동물"
    user_name: str = "김에듀"


@router.post("/api/generate-short")
async def generate_short_question(req: GenerateShortRequest):
    """
    초등 2022 개정 교육과정 실생활 대화문 기반 주관식 빈칸 퀴즈 실시간 생성
    - AI가 초등학생 눈높이에 맞는 A-B 2줄 대화와 핵심 어휘 빈칸(___)을 생성합니다.
    """
    grade_desc = "초등 3~4학년 (기초 생활 어휘)" if req.grade == "34" else "초등 5~6학년 (실전 응용 어휘)"
    cat = req.category or "생활"

    cli = get_genai_client()
    if cli:
        prompt = f"""
        너는 대한민국 2022 개정 초등영어 교육과정 전문 출제위원이야.
        {grade_desc} 수준에 맞는 [실생활 대화 속 빈칸 어휘 완성] 주관식 문제를 1개 만들어줘.

        [주제/카테고리]: {cat}
        [교육과정 단원 목차 참고]:
        {CURRICULUM_TEXT[:400]}...

        [출제 규칙]:
        1. 초등학생 둘(A와 B)의 2줄 실생활 자연스러운 대화문이어야 함.
        2. B의 답변 속에 핵심 단어 1개를 빈칸("___")으로 비워둘 것.
        3. 정답 단어는 초등 필수 어휘(소문자) 1개로 명확해야 함.
        4. 첫 글자 힌트(hint_char)와 한국어 뜻(meaning), 문맥 힌트(clue)를 친절히 제공할 것.

        반드시 아래 JSON 형식으로만 응답해:
        {{
            "dialogue": [
                {{"speaker": "A", "text": "What animal do you like?"}},
                {{"speaker": "B", "text": "I like the cute ___."}}
            ],
            "target_word": "rabbit",
            "meaning": "토끼",
            "hint_clue": "귀가 길고 깡총깡총 뛰는 동물",
            "explanation": "대화 문맥상 알맞은 단어는 'rabbit(토끼)'입니다."
        }}
        """
        for m in OFFICIAL_MODELS:
            try:
                res = cli.models.generate_content(
                    model=m,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                raw = res.text.strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                data = json.loads(raw)
                return {"success": True, "question": data, "source": "ai"}
            except Exception:
                continue

    # AI 미연결 또는 오류 시 안정적인 교육과정 표준 백업 문제은행 풀백
    fallback_pool = [
        {
            "dialogue": [{"speaker": "A", "text": "What is your favorite pet?"}, {"speaker": "B", "text": "I love my cute ___."}],
            "target_word": "dog",
            "meaning": "개, 강아지",
            "hint_clue": "멍멍 짖으며 꼬리를 흔드는 동물",
            "explanation": "문맥상 반려동물로 알맞은 단어는 'dog(개)'입니다."
        },
        {
            "dialogue": [{"speaker": "A", "text": "Do you want some fruit?"}, {"speaker": "B", "text": "Yes, I like sweet red ___s."}],
            "target_word": "apple",
            "meaning": "사과",
            "hint_clue": "백설공주가 좋아하는 빨간 과일",
            "explanation": "문맥상 빨간 과일로 알맞은 단어는 'apple(사과)'입니다."
        },
        {
            "dialogue": [{"speaker": "A", "text": "Where is the book?"}, {"speaker": "B", "text": "It is on the study ___."}],
            "target_word": "desk",
            "meaning": "책상",
            "hint_clue": "공부하거나 책을 올려놓는 가구",
            "explanation": "문맥상 방 안의 가구로 알맞은 단어는 'desk(책상)'입니다."
        }
    ]
    chosen = random.choice(fallback_pool)
    return {"success": True, "question": chosen, "source": "bank"}


# ---------------------------------------------------------------------------
# [공통 표준] 문제은행 단원 통계 / 풀이 기록 / 출제 / AI 채점 API
# ---------------------------------------------------------------------------
@router.get("/api/question-bank/unit-stats")
async def get_bank_unit_stats(
    subject: str = Query("english"),
    user_id: Optional[str] = Query(None),
    user_name: str = Query("김에듀"),
    grade: Optional[int] = Query(None),
):
    """각 단원별 (맞춘 문제 / 전체 은행 문제) 실시간 통계 반환"""
    user_key = (user_id or user_name or "김에듀").strip() or "김에듀"
    return get_unit_bank_stats(subject=subject, user_key=user_key, grade=grade)


class MarkSolvedRequest(BaseModel):
    bank_id: int
    subject: str = "english"
    user_id: Optional[str] = None
    user_name: str = "김에듀"


@router.post("/api/question-bank/mark-solved")
async def post_mark_bank_solved(req: MarkSolvedRequest):
    """문제은행 문제 정답 풀이 기록"""
    user_key = (req.user_id or req.user_name or "김에듀").strip() or "김에듀"
    ok = mark_bank_question_solved(bank_id=req.bank_id, subject=req.subject, user_key=user_key)
    return {"success": ok}


@router.get("/api/question-bank/next")
async def get_next_question_from_bank(
    subject: str = Query("english"),
    unit_name: Optional[str] = Query(None),
    grade: Optional[int] = Query(4),
    question_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    user_name: str = Query("김에듀"),
    allow_review: bool = Query(False),
):
    """
    문제은행 DB에서 다음 문제 출제
    - allow_review=False: 미풀이 문제 우선 출제
    - allow_review=True: 이미 푼 문제라도 복습용 랜덤 출제 (is_review=True)
    """
    user_key = (user_id or user_name or "김에듀").strip() or "김에듀"
    q_dict, is_rev = fetch_next_bank_question(
        subject=subject,
        unit_name=unit_name,
        grade=grade,
        question_type=question_type,
        user_key=user_key,
        allow_review=allow_review,
    )
    if q_dict:
        return {"success": True, "question": q_dict, "is_review": is_rev, "source": "bank"}
    return {"success": False, "question": None, "is_review": False, "source": "bank"}


class AIGenerateRequest(BaseModel):
    grade: str = "34"
    unit_name: Optional[str] = "동물"
    question_type: str = "객관식"  # "객관식" | "단답형" | "서술형"
    user_name: str = "김에듀"
    user_id: Optional[str] = None


@router.post("/api/question-bank/ai-generate")
async def generate_ai_question(req: AIGenerateRequest):
    """
    단원/유형 맞춤형 Gemini 실시간 AI 문제 출제
    - 실패 시 {"success": False, "error": ...} 반환하여 프론트엔드가 즉시 3단계 폴백으로 전환
    """
    cli = get_genai_client()
    if not cli:
        return {"success": False, "error": "AI_CLIENT_NOT_AVAILABLE"}

    grade_label = "초등 3~4학년" if req.grade == "34" else "초등 5~6학년"
    unit_val = req.unit_name or "생활"

    prompt = f"""
    너는 대한민국 2022 개정 초등영어 교육과정 전문 출제위원이야.
    {grade_label} 수준의 [{unit_val}] 단원에 알맞은 초등 영어 {req.question_type} 문제를 1개 만들어줘.

    [요구 조건]:
    1. 초등 필수 어휘 및 자연스러운 일상 표현을 다룰 것.
    2. 객관식일 경우 4개의 보기(choices) 배열을 만들고, 그중 1개가 정답이어야 함.
    3. 단답형일 경우 영어 단어 철자 문제여야 함.
    4. 서술형일 경우 학생이 1문장을 영작하는 지문과 추천 문장이어야 함.

    반드시 아래 JSON 형식으로만 응답해:
    {{
        "word": "target_word",
        "ipa": "/ipa_sound/",
        "meaning": "한국어 뜻",
        "hint": "초등학생 눈높이 힌트",
        "question_type": "{req.question_type}",
        "question_text": "문제 지문 텍스트",
        "choices": ["보기1", "보기2", "보기3", "보기4"],
        "correct_answer": "정답단어 또는 모범문장",
        "explanation": "친절한 정답 설명",
        "difficulty": "중",
        "points": 3
    }}
    """
    for m in OFFICIAL_MODELS:
        try:
            res = cli.models.generate_content(
                model=m,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            raw = res.text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            data = json.loads(raw)
            return {"success": True, "question": data, "source": "ai"}
        except Exception:
            continue

    return {"success": False, "error": "AI_GENERATION_FAILED"}


class SaveBankQuestionRequest(BaseModel):
    question_text: str
    correct_answer: str
    question_type: str = "객관식"
    grade: int = 4
    grade_group: str = "3~4학년군"
    unit_name: str = "기본 어휘"
    sub_topic: str = ""
    difficulty: str = "중"
    points: int = 3
    choices: Optional[List[str]] = None
    explanation: str = ""
    source_type: str = "manual"
    source_log_id: Optional[int] = None
    created_by: str = "master"
    created_by_name: str = "총 관리자"


@router.post("/api/question-bank/save")
async def api_save_question_to_bank(req: SaveBankQuestionRequest):
    """표준 문제은행 DB(question_bank.db)에 신규 문제 저장 API"""
    b_id = save_question_to_bank(
        question_text=req.question_text,
        correct_answer=req.correct_answer,
        question_type=req.question_type,
        grade=req.grade,
        grade_group=req.grade_group,
        unit_name=req.unit_name,
        sub_topic=req.sub_topic,
        difficulty=req.difficulty,
        points=req.points,
        choices=req.choices,
        explanation=req.explanation,
        source_type=req.source_type,
        source_log_id=req.source_log_id,
        created_by=req.created_by,
        created_by_name=req.created_by_name,
    )
    return {"success": True, "bank_id": b_id}



# 8. 서술형: AI 3단계 문장 정밀 검수(맞는 문장 / 어색한 문장 / 틀린 문장) 및 첨삭 코칭 API
class GradeRequest(BaseModel):
    user_id: Optional[str] = None
    user_name: str = "김에듀"
    grade: str = "34"
    target_word: Optional[str] = None
    user_answer: str
    unit: Optional[str] = "자유 영작"
    topic: Optional[str] = None
    difficulty: Optional[str] = "중"


@router.post("/api/grade")
async def grade_descriptive_answer(req: GradeRequest):
    """
    서술형 AI 3단계 문장 검수 및 다정한 첨삭 코칭:
    - 억지 미션 조건 없이, 학생이 작성한 문장의 본래 의도를 100% 존중!
    - 1단계: 맞는 문장 (perfect) -> 칭찬과 5점 만점
    - 2단계: 어색한 문장 (awkward) -> 의미는 통하나 어순/표현이 어색한 부분 교정 및 부분점수(3~4점)
    - 3단계: 틀린 문장 (incorrect) -> 심한 문법 오류나 비문 교정 및 재도전 유도(1~2점)
    """
    user_ans = req.user_answer.strip()
    grade_int = 4 if req.grade == "34" else 6
    grade_label = "초등 3~4학년" if req.grade == "34" else "초등 5~6학년"

    # 1차 사전 검증: 빈 칸
    if not user_ans:
        verdict = "incorrect"
        verdict_kr = "✏️ 아직 문장이 작성되지 않았어요!"
        score = 1
        feedback = "문장을 적어주시면 AI 선생님이 다정하게 확인해 드릴게요 💕"
        sample = "I like apples."
    else:
        verdict = None
        verdict_kr = None
        score = None
        feedback = None
        sample = user_ans

        cli = get_genai_client()
        target = (req.target_word or "").strip()
        if cli:
            prompt = f"""
            너는 대한민국 2022 개정 초등영어 교육과정 전문 친절한 AI 수석 첨삭 선생님이야.
            초등학생 ({grade_label})이 주어진 [목표 단어]를 활용하여 작성한 영문장을 공정하고 다정하게 검수하고 피드백해줘.

            [문제 정보]:
            - 목표 제시 단어: "{target}" (의미/주제: {req.topic or '영어 문장 표현'})
            - 학생 작성 문장: "{user_ans}"

            [핵심 평가 원칙 - 문제 타당성 및 목표 단어 일치성 최우선]:
            1. [목표 단어 타당성 검사 (가장 중요)]:
               - 이번 문제의 목표는 제시 단어 "{target}"을(를) 활용하여 올바른 영문장을 완성하는 것이다.
               - 학생이 목표 단어 "{target}"(또는 그 오타)을 전혀 쓰지 않고 무관한 외계어/비단어(예: xlck)나 딴소리를 쓴 경우:
                 * 절대로 엉뚱한 다른 사물/단어(예: clock 등)로 제멋대로 넘겨짚어 교정하지 말 것!
                 * 판정: "incorrect" (2점)
                 * verdict_kr: "✏️ 이번 문제의 목표 단어가 빠져 있어요!"
                 * 피드백: "문장의 형태를 시도한 것은 좋지만, 이번 문제의 목표 단어인 '{target}'({req.topic or ''})이(가) 들어있지 않아요! '{target}'을(를) 넣어 다시 문장을 완성해 볼까요?"
                 * 모범 교정(corrected): 반드시 목표 단어 "{target}"이 들어간 자연스러운 초등 수준 영문장 제시. (예: target이 traffic이면 "The traffic is heavy." 또는 "Look at the traffic.")

            2. [목표 단어 철자 오타 검사]:
               - 학생이 목표 단어 "{target}"을 쓰려 했으나 철자 오타(예: traffc 등)를 낸 경우:
                 * 판정: "awkward" (3점)
                 * verdict_kr: "💡 목표 단어의 철자를 확인해 볼까요?"
                 * 피드백: 목표 단어 "{target}"의 철자 교정 이유 다정하게 설명.
                 * 모범 교정(corrected): 오타를 올바른 "{target}"으로 고친 자연스러운 영문장.

            3. [자연스러운 완성 문장 검사]:
               - 목표 단어 "{target}"을 알맞게 포함하고, 주어와 동사를 갖춘 자연스러운 문장:
                 * 판정: "perfect" (5점)
                 * verdict_kr: "🎉 자연스럽고 완벽한 문장이에요!"
                 * 피드백: 따뜻한 칭찬과 격려.
                 * 모범 교정(corrected): 학생이 작성한 훌륭한 문장 그대로 유지.

            4. [사소한 문장부호/대소문자/관사 오류]:
               - 목표 단어는 잘 썼으나 첫 글자 소문자, 마침표 누락, 사소한 관사 실수:
                 * 판정: "awkward" (4점)
                 * verdict_kr: "💡 표현을 조금 다듬어 볼까요?"

            반드시 아래 JSON 포맷으로만 응답해:
            {{
                "verdict": "perfect" | "awkward" | "incorrect",
                "verdict_kr": "한국어 판정 문구",
                "score": 5,
                "feedback": "초등학생 눈높이에 맞춘 다정한 칭찬 및 교정 이유 설명 (1~2문장)",
                "corrected": "{target}을(를) 활용한 바른 모범 영문장"
            }}
            """
            for m in OFFICIAL_MODELS:
                try:
                    res = cli.models.generate_content(
                        model=m,
                        contents=prompt,
                        config={"response_mime_type": "application/json"},
                    )
                    raw = res.text.strip()
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0].strip()
                    data = json.loads(raw)
                    verdict = data.get("verdict", "awkward")
                    verdict_kr = data.get("verdict_kr", "💡 철자나 표현을 확인해 볼까요?")
                    score = int(data.get("score", 3))
                    feedback = data.get("feedback", "문장을 멋지게 잘 작성했어요!")
                    sample = data.get("corrected", user_ans)
                    break
                except Exception:
                    continue

        if score is None:
            # 로컬 안전 폴백
            words = user_ans.split()
            clean_words = [w.strip(".,!?\"'").lower() for w in words]
            target_lower = target.lower()

            import difflib
            is_target_present = target_lower and any(target_lower in w for w in clean_words)
            close_matches = difflib.get_close_matches(target_lower, clean_words, n=1, cutoff=0.6) if target_lower else []
            is_target_typo = bool(close_matches) and not is_target_present

            if len(words) <= 1:
                verdict = "incorrect"
                verdict_kr = "✏️ 아직 완전한 문장이 아니에요!"
                score = 2
                feedback = f"주어와 동사를 넣어 'This is {target or user_ans}.'처럼 완전한 문장으로 만들어 보세요!"
                sample = f"Look at the {target}." if target else "I like apples."
            elif not is_target_present and not is_target_typo:
                verdict = "incorrect"
                verdict_kr = "✏️ 이번 문제의 목표 단어가 빠져 있어요!"
                score = 2
                feedback = f"문장 형태를 시도한 것은 좋지만, 이번 문제의 목표 단어인 '{target}'({req.topic or ''})이(가) 들어있지 않아요! '{target}'을(를) 활용해서 문장을 완성해 볼까요?"
                sample = f"The {target} is heavy." if target == "traffic" else (f"I like the {target}." if target else "I like apples.")
            elif is_target_typo:
                typo_word = close_matches[0]
                verdict = "awkward"
                verdict_kr = "💡 목표 단어의 철자를 확인해 볼까요?"
                score = 3
                sample = user_ans
                for w in words:
                    if w.strip(".,!?\"'").lower() == typo_word:
                        sample = sample.replace(w, target)
                feedback = f"목표 단어 '{target}'의 철자에 작은 오타('{typo_word}')가 있어요! '{target}'(으)로 바르게 고쳐 보세요 ✨"
            elif any(p in user_ans.lower() for p in ["i like", "this is", "that is", "it is", "i have", "i see", "i want", "i go", "the traffic", "there is"]):
                verdict = "perfect"
                verdict_kr = "🎉 자연스럽고 멋진 문장이에요!"
                score = 5
                feedback = f"목표 단어 '{target}'을(를) 활용하여 문맥과 구조를 완벽하게 갖춘 멋진 영어 문장이에요! 참 잘했어요 👏"
                sample = user_ans
            else:
                verdict = "awkward"
                verdict_kr = "💡 의미는 통하지만 표현을 조금 다듬어 볼까요?"
                score = 4
                feedback = "좋은 표현 시도예요! 첫 글자를 대문자로 쓰고 끝에 마침표를 찍어 완성해 보세요 ✨"
                sample = user_ans.capitalize() + ("." if not user_ans.endswith((".", "!", "?")) else "")

    # 상/중/하 난이도별 배점 환산 (가이드라인 표준: 상: 5점 / 중: 3점 / 하: 1점)
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
    is_corr = (verdict in ["perfect", "awkward"])  # 맞는 문장 및 부분정답 인정

    import time
    saved = save_quiz_log(
        user_id=req.user_id,
        user_name=req.user_name,
        quiz_id=f"english_desc_{user_ans[:10]}_{int(time.time())}",
        grade=grade_int,
        unit=req.unit or "자유 영작",
        topic=req.topic or "문장 표현",
        difficulty=diff_val,
        question_type="서술형",
        question="나만의 영어 문장 표현 만들기",
        user_answer=user_ans,
        correct_answer=sample,
        solution=feedback,
        earned_score=earned_points,
        is_correct=is_corr,
    )

    return {
        "verdict": verdict,
        "verdict_kr": verdict_kr,
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


class BankGradeRequest(BaseModel):
    bank_id: Optional[int] = None
    question_type: str = "서술형"  # "단답형" | "서술형"
    question_text: str = ""
    correct_answer: str = ""
    user_answer: str = ""
    unit_name: Optional[str] = None
    grade: str = "34"
    user_name: str = "김에듀"
    user_id: Optional[str] = None


@router.post("/api/question-bank/grade")
async def grade_bank_question(req: BankGradeRequest):
    """문제은행 주관식(단답형) 및 서술형 AI 채점 및 피드백 API"""
    q_type = req.question_type
    user_ans = req.user_answer.strip()
    corr_ans = req.correct_answer.strip()

    if q_type in ["단답형", "주관식"]:
        is_exact = (user_ans.lower() == corr_ans.lower())
        if is_exact:
            return {
                "is_correct": True,
                "score": 5,
                "earned_score": 3,
                "feedback": f"정확한 철자입니다! '{corr_ans}'을(를) 완벽하게 맞혔어요! 👏",
                "sample": corr_ans,
            }

        # AI 단답형 오타/동의어 판정
        cli = get_genai_client()
        if cli:
            try:
                prompt = f"""
                초등 영어 단답형 문제 채점:
                - 문제: {req.question_text}
                - 모범 정답: {corr_ans}
                - 학생 답안: {user_ans}

                JSON 응답:
                {{"is_correct": true|false, "feedback": "초등학생 눈높이 1문장 피드백", "score": 1~5}}
                """
                res = cli.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                data = json.loads(res.text.strip())
                corr = bool(data.get("is_correct", False))
                return {
                    "is_correct": corr,
                    "score": int(data.get("score", 3 if corr else 1)),
                    "earned_score": 3 if corr else 0,
                    "feedback": data.get("feedback", f"바른 철자는 '{corr_ans}'입니다."),
                    "sample": corr_ans,
                }
            except Exception:
                pass

        return {
            "is_correct": False,
            "score": 1,
            "earned_score": 0,
            "feedback": f"아쉬워요! 바른 철자는 '{corr_ans}'입니다.",
            "sample": corr_ans,
        }

    # 서술형: AI 3단계 정밀 검수 호출
    desc_req = GradeRequest(
        user_id=req.user_id,
        user_name=req.user_name,
        grade=req.grade,
        target_word=corr_ans,
        user_answer=user_ans,
        unit=req.unit_name or "단원 학습",
        topic="문장 표현",
    )
    return await grade_descriptive_answer(desc_req)


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
        for m in OFFICIAL_MODELS:
            try:
                res = cli.models.generate_content(
                    model=m,
                    contents=prompt
                )
                if res and res.text and res.text.strip():
                    ai_reply = res.text.strip()
                    break
            except Exception:
                continue

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
async def get_weakest(user_name: str = Query("김에듀"), user_id: Optional[str] = Query(None)):
    """학생의 오답 내역을 분석하여 가장 취약한 단원 반환"""
    return get_weakest_unit_and_topic(user_name=user_name, user_id=user_id)


# ---------------------------------------------------------------------------
# 11. [네이버 영어사전 공식 음원] 미국식(Naver Studio) / 영국식(Oxford) & 호주 표준 발음 스트리밍 API
# ---------------------------------------------------------------------------
_AUDIO_CACHE: Dict[str, bytes] = {}


def fetch_naver_dict_audio(word: str, accent: str = "us") -> Optional[bytes]:
    """
    네이버 어학사전(en.dict.naver.com)의 공식 원어민 스튜디오 녹음 음원(MP3)을 실시간 파싱하여 스트리밍
    - US: 네이버 사전 공식 미국 원어민 스튜디오 녹음 음원 (1순위)
    - UK/GB: 네이버 사전 공식 옥스퍼드 영국 원어민 녹음 음원
    """
    clean_word = word.strip().lower()
    if not clean_word:
        return None

    # 공백이 있는 긴 문장은 사전 표제어 검색 대신 실시간 음성 스트림으로 처리
    if " " in clean_word:
        return None

    ssl_ctx = ssl._create_unverified_context()
    target_accent = "us" if accent.lower() in ["us", "en-us"] else "uk"

    # 네이버 영한사전 웹 및 모바일 API 검색 엔드포인트
    search_queries = [
        f"https://en.dict.naver.com/api3/enko/search?query={urllib.parse.quote(clean_word)}&m=pc&range=word",
        f"https://dict.naver.com/api3/enko/search?query={urllib.parse.quote(clean_word)}&m=pc&range=word",
        f"https://m.dict.naver.com/api3/enko/search?query={urllib.parse.quote(clean_word)}&range=word",
        f"https://en.dict.naver.com/api3/eko/search?query={urllib.parse.quote(clean_word)}&range=word",
    ]

    for search_url in search_queries:
        try:
            req = urllib.request.Request(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://en.dict.naver.com/",
                    "Accept": "application/json, text/plain, */*",
                }
            )
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = (
                data.get("searchResultMap", {})
                .get("searchResultListMap", {})
                .get("WORD", {})
                .get("items", [])
            )
            if not items:
                continue

            candidates = []

            # 1. 표제어 순회하며 발음 기호/음원 후보 수집 및 정밀 스코어링
            for item in items:
                raw_entry = item.get("expEntry", "") or item.get("handleEntry", "") or item.get("entryName", "")
                clean_entry = re.sub(r'<[^>]+>', '', raw_entry).strip().lower()
                clean_entry = re.sub(r'[\d\s\-_()]+$', '', clean_entry).strip()

                is_exact = (clean_entry == clean_word)

                symbol_list = item.get("searchPhoneticSymbolList", []) or []
                for sym in symbol_list:
                    s_type = (sym.get("symbolType") or "").upper()
                    s_name = (sym.get("symbol") or "").upper()
                    s_url = sym.get("phoneticSymbolPath") or sym.get("soundUrl") or sym.get("audioUrl") or sym.get("url") or sym.get("mp3Url") or ""
                    if not s_url:
                        continue

                    u_lower = s_url.lower()
                    score = 0

                    if target_accent == "us":
                        # [미국식 판별] 네이버 사전 공식 미국 원어민 스튜디오 MP3 링크 최우선 매칭
                        if "/us/" in u_lower or "pron/new/us" in u_lower or "_us_" in u_lower or "us.mp3" in u_lower:
                            score += 120
                        elif "US" in s_type or "USA" in s_type or "미국" in s_name or s_type == "A":
                            score += 90
                        elif not ("/uk/" in u_lower or "pron/new/uk" in u_lower or "_uk_" in u_lower or "uk.mp3" in u_lower or "UK" in s_type or "GB" in s_type or "영국" in s_name):
                            score += 30  # 중립
                        else:
                            score -= 80  # 영국식 음원은 미국식 요청 시 배제
                    else:
                        # [영국식 판별] 옥스퍼드 공식 영국 원어민 음원 매칭
                        if "/uk/" in u_lower or "pron/new/uk" in u_lower or "_uk_" in u_lower or "uk.mp3" in u_lower:
                            score += 120
                        elif "UK" in s_type or "GB" in s_type or "영국" in s_name or s_type == "B":
                            score += 90
                        elif not ("/us/" in u_lower or "pron/new/us" in u_lower or "_us_" in u_lower or "us.mp3" in u_lower or "US" in s_type or "미국" in s_name):
                            score += 30
                        else:
                            score -= 80

                    if is_exact:
                        score += 50

                    candidates.append((score, s_url))

            # 점수 높은 순으로 정렬
            candidates.sort(key=lambda x: x[0], reverse=True)

            for score, audio_url in candidates:
                if score < 0:
                    continue
                if audio_url.startswith("//"):
                    audio_url = "https:" + audio_url
                elif audio_url.startswith("/"):
                    audio_url = "https://dict-dn.pstatic.net" + audio_url
                elif audio_url.startswith("http://"):
                    audio_url = "https://" + audio_url[7:]

                for ref in ["https://en.dict.naver.com/", ""]:
                    try:
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        }
                        if ref:
                            headers["Referer"] = ref
                        audio_req = urllib.request.Request(audio_url, headers=headers)
                        with urllib.request.urlopen(audio_req, context=ssl_ctx, timeout=3.5) as a_resp:
                            content = a_resp.read()
                            if len(content) > 300:
                                return content
                    except Exception:
                        pass
        except Exception:
            continue

    return None


def fetch_external_audio(text: str, accent: str = "us") -> Optional[bytes]:
    """
    네이버 어학사전 공식 원어민 스튜디오 음원 기준 실시간 스트리밍
    - 미국식: 네이버 어학사전 공식 미국 원어민 스튜디오 녹음 음원 (1순위)
    - 영국식: 네이버 어학사전 공식 옥스퍼드 원어민 녹음 음원
    - 호주식: 호주 고유 억양 남성(Male) 원어민 음원
    """
    clean_text = text.strip()
    if not clean_text:
        return None
    cache_key = f"{accent.lower()}_{clean_text.lower()}"
    if cache_key in _AUDIO_CACHE:
        return _AUDIO_CACHE[cache_key]

    encoded = urllib.parse.quote(clean_text)
    ssl_ctx = ssl._create_unverified_context()

    # 1. 미국식: [네이버 어학사전 공식 미국 원어민 스튜디오 음원] 1순위 파싱 스트리밍
    if accent.lower() in ["us", "en-us"]:
        naver_us_data = fetch_naver_dict_audio(clean_text, "us")
        if naver_us_data:
            _AUDIO_CACHE[cache_key] = naver_us_data
            return naver_us_data

        # 미국식 2순위 고품질 표준 원어민 발음 (된소리/이상한 기계음 nvoice 완전 영구 퇴출)
        backup_us_urls = [
            f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en-US&q={encoded}",
            f"https://translate.googleapis.com/translate_tts?client=gtx&ie=UTF-8&tl=en-US&q={encoded}",
            f"https://translate.google.com/translate_tts?ie=UTF-8&client=gtx&tl=en-US&q={encoded}",
        ]
        for u in backup_us_urls:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://translate.google.com/"
                }
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, context=ssl_ctx, timeout=3.5) as resp:
                    data = resp.read()
                    if len(data) > 300:
                        _AUDIO_CACHE[cache_key] = data
                        return data
            except Exception:
                pass

    # 2. 영국식: [네이버 어학사전 옥스퍼드 공식 음원]
    elif accent.lower() in ["gb", "uk", "en-gb"]:
        naver_uk_data = fetch_naver_dict_audio(clean_text, "gb")
        if naver_uk_data:
            _AUDIO_CACHE[cache_key] = naver_uk_data
            return naver_uk_data

        url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en-GB&q={encoded}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=3.5) as resp:
                data = resp.read()
                if len(data) > 300:
                    _AUDIO_CACHE[cache_key] = data
                    return data
        except Exception:
            pass

    # 3. 호주식: [호주 남성(Male) 원어민 전용 음원]
    elif accent.lower() in ["au", "en-au"]:
        urls = [
            f"https://code.responsivevoice.org/getvoice.php?t={encoded}&tl=en-AU&pitch=0.46&rate=0.48&vol=1&gender=male",
            f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en-AU&q={encoded}"
        ]
        for u in urls:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": "https://responsivevoice.org/" if "responsivevoice" in u else "https://translate.google.com/"
                }
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, context=ssl_ctx, timeout=3.5) as resp:
                    data = resp.read()
                    if len(data) > 300:
                        _AUDIO_CACHE[cache_key] = data
                        return data
            except Exception:
                pass

    return None


@router.get("/api/audio")
async def get_audio_stream(word: str = Query(...), accent: str = Query("us")):
    """
    네이버 영어사전 공식 음원(미국식 clara / 영국식 richard) 및 호주 표준 음원 실시간 스트리밍 API
    """
    audio_bytes = fetch_external_audio(word, accent)
    if audio_bytes:
        return Response(content=audio_bytes, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="오디오를 불러올 수 없습니다.")


# 단독 실행용 FastAPI 인스턴스 (변수명을 반드시 app으로 지정)
app = FastAPI(title="EduMate AI - 초등영어 단독 테스트 서버")
app.include_router(router)

@app.get("/")
async def root_page():
    return FileResponse(str(HTML_PATH))


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    PORT = 8000
    print(f"\n🚀 [초등영어] 로컬 테스트 서버 구동: http://localhost:{PORT}/english/\n")
    webbrowser.open(f"http://localhost:{PORT}/english/")
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    except OSError:
        PORT = 8001
        print(f"\n⚠️ 8000번 포트 사용 중으로 8001번으로 전환: http://localhost:{PORT}/english/\n")
        webbrowser.open(f"http://localhost:{PORT}/english/")
        uvicorn.run(app, host="0.0.0.0", port=PORT)

