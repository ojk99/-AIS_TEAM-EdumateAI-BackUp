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


# 8. 서술형: AI 3단계 문장 정밀 검수(맞는 문장 / 어색한 문장 / 틀린 문장) 및 첨삭 코칭 API
class GradeRequest(BaseModel):
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

