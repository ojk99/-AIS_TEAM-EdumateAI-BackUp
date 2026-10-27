import os
import json
import re
import time
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai

# ==============================================================================
# 0. 공통 DB 모듈(quiz_logs.py) 표준 함수 안전 임포트
# ==============================================================================
try:
    from .quiz_logs import (
        save_quiz_log,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_or_create_user,
        get_user_status,
        grant_full_score_by_tutor,
    )
except ImportError:
    from quiz_logs import (
        save_quiz_log,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_or_create_user,
        get_user_status,
        grant_full_score_by_tutor,
    )

# ==============================================================================
# 1. 파일 경로 및 API 키 계단식 로드 (가이드라인 261008 표준)
# ==============================================================================
CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
ROOT_DIR = CURRENT_DIR.parents[2]  # d:\팀프로젝트

def find_and_load_api_key() -> str:
    """현재 과목 폴더 -> 상위 폴더 -> 프로젝트 루트 -> 시스템 환경변수 순서로 안전 로드"""
    # 1. 시스템 환경변수 우선 확인
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    # 2. 계단식 .env 탐색 (과목 폴더 -> 상위 폴더 -> 루트 폴더)
    for target_env in [CURRENT_DIR / ".env", PARENT_DIR / ".env", ROOT_DIR / ".env"]:
        if target_env.exists():
            load_dotenv(dotenv_path=target_env, override=True)
            loaded = os.getenv("GEMINI_API_KEY")
            if loaded and loaded.strip():
                return loaded.strip()

    load_dotenv(override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()

def get_genai_client():
    key = find_and_load_api_key()
    if not key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY가 설정되지 않았습니다. app/subjects/korean/.env 파일이나 시스템 환경변수를 확인하세요."
        )
    return genai.Client(api_key=key, http_options={"api_version": "v1"})


# ==============================================================================
# 2. curriculum.txt (초등국어 단원 목차) 로더
# ==============================================================================
def load_curriculum_text() -> str:
    # 1. 현재 과목 폴더 내 curriculum.txt
    file_path = CURRENT_DIR / "curriculum.txt"
    if not file_path.exists():
        # 2. 루트 경로 탐색
        file_path = ROOT_DIR / "curriculum.txt"

    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return "초등학교 1~6학년 국어 교육과정 (기초 문해력, 맞춤법, 띄어쓰기, 문단 구조, 비유 표현)"


# ==============================================================================
# 3. Pydantic DTO (가이드라인 Schema 표준 & 팀 통합 규격)
# ==============================================================================
class QuizRequest(BaseModel):
    grade: str = Field(..., description="학년 (예: '1학년 1학기', '3학년 1학기', '5학년 1학기')")
    unit: Optional[str] = Field(None, description="단원명 또는 주제 (생략 가능)")
    question_type: str = Field("객관식", description="문제 유형: 'OX', '객관식', '단답형', '서술형'")
    user_name: Optional[str] = Field("김에듀", description="학생 이름")
    use_weakest: Optional[bool] = Field(False, description="취약 단원 맞춤 출제 여부")

class QuizItem(BaseModel):
    id: int = Field(..., description="문제 번호 (1~5)")
    quiz_id: Optional[str] = Field(None, description="문제 고유 식별자")
    unit: str = Field("핵심 단원", description="출제 단원명")
    question_type: str = Field("객관식", description="문제 유형")
    difficulty: str = Field("중", description="난이도: 상, 중, 하")
    base_score: int = Field(3, description="난이도별 배점 (하: 1점, 중: 3점, 상: 5점)")
    question: str = Field(..., description="문제 내용 (지문 포함)")
    options: List[str] = Field(default=[], description="객관식/OX 보기 목록")
    answer: str = Field(..., description="정답")
    explanation: str = Field(..., description="친절한 해설")

class QuizSetResponse(BaseModel):
    grade: str
    total_count: int = 5
    questions: List[QuizItem]

class GradeItemRequest(BaseModel):
    id: int
    quiz_id: Optional[str] = None
    unit: Optional[str] = None
    difficulty: Optional[str] = "중"
    question_type: str
    question: str
    model_answer: str
    user_answer: str
    base_score: int = 3
    explanation: Optional[str] = None

class GradeSetRequest(BaseModel):
    user_id: Optional[str] = None
    user_name: str = "김에듀"
    grade: Optional[str] = "4학년 1학기"
    pokemon_type: str = "grass"
    items: List[GradeItemRequest]

class GradeItemResult(BaseModel):
    id: int
    log_id: Optional[int] = None
    score: int
    max_score: int
    is_correct: bool
    feedback: str
    model_answer: str
    user_answer: str

class GradeSetResponse(BaseModel):
    total_score: int
    max_total_score: int
    correct_count: int
    total_count: int
    user_status: Optional[dict] = None
    results: List[GradeItemResult]

class UserStatusRequest(BaseModel):
    user_id: Optional[str] = None
    user_name: str = "김에듀"
    grade: Optional[int] = 4
    pokemon_type: str = "grass"

class AskMoreRequest(BaseModel):
    log_id: int
    student_question: str
    context_question: Optional[str] = None
    model_answer: Optional[str] = None
    user_answer: Optional[str] = None
    user_name: Optional[str] = "김에듀"
    user_id: Optional[str] = None


# ==============================================================================
# 4. FastAPI APIRouter 정의 (조장 통합 서버 Step B 필수 규격)
# ==============================================================================
router = APIRouter(prefix="/korean", tags=["초등국어"])

@router.get("/", response_class=HTMLResponse)
async def serve_subject_index():
    """메인 로비에서 초등국어관 입장 시 index.html 서빙 (조장 Step B 필수 규격)"""
    return FileResponse(CURRENT_DIR / "index.html")

@router.get("/logo.svg")
async def serve_logo():
    """EduMate 공식 공통 로고 SVG 서빙 (조장 표준 규격)"""
    logo_path = CURRENT_DIR / "edumate_logo.svg"
    if not logo_path.exists():
        logo_path = CURRENT_DIR.parent.parent.parent / "sample" / "edumate_logo.svg"
    if logo_path.exists():
        return FileResponse(str(logo_path), media_type="image/svg+xml")
    return Response(
        content='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="50">EduMate</text></svg>',
        media_type="image/svg+xml"
    )

@router.post("/user-status")
async def api_get_user_status(req: UserStatusRequest):
    """학생 계정 조회 및 포켓몬 진화 등급 정보 / 누적 총점 반환"""
    return get_or_create_user(user_name=req.user_name, grade=req.grade, pokemon_type=req.pokemon_type, user_id=req.user_id)

@router.get("/user-status")
async def api_get_user_status_get(user_name: str = "김에듀", grade: int = 4, pokemon_type: str = "grass", user_id: Optional[str] = None):
    """학생 계정 조회 GET 엔드포인트"""
    return get_or_create_user(user_name=user_name, grade=grade, pokemon_type=pokemon_type, user_id=user_id)

@router.get("/weakest-unit")
async def api_get_weakest_unit(user_name: str = "김에듀", user_id: Optional[str] = None):
    """학생의 과거 오답 데이터 기반 취약 단원 조회"""
    return get_weakest_unit_and_topic(user_name=user_name, user_id=user_id)

@router.post("/favorite/{log_id}")
async def api_toggle_favorite(log_id: int):
    """문제 즐겨찾기 토글 (0 <-> 1)"""
    res = toggle_favorite(log_id)
    if not res.get("success", False):
        raise HTTPException(status_code=404, detail=res.get("error", "로그를 찾을 수 없습니다."))
    return res

@router.post("/ask-more")
async def api_ask_more(req: AskMoreRequest):
    """채점된 문제에 대해 AI 선생님께 이어서 질문하기 (대화 내역 DB 누적 저장 및 출제/채점 오류 시 점수 정정)"""
    client = get_genai_client()
    prompt = f"""
당신은 친절하고 공정하며 다정한 2022 개정 초등학교 국어 전문 교사입니다.
초등학생이 자신이 푼 국어 문제에 대해 다음과 같이 질문하거나 이의를 제기하였습니다.

[문제 내용]: {req.context_question or "초등국어 문제"}
[학생이 제출한 답안]: {req.user_answer or "미제출"}
[기존 모범 정답/해설]: {req.model_answer or "핵심 개념"}
[학생 질문]: {req.student_question}

[독립 검증 및 출제·채점 오류 정직 인정 원칙]:
만약 학생이 '보기에 정답이 없어요', '문제가 이상해요', '제 답도 맞지 않나요?'라고 이의를 제기하면, 기존 [정답]이나 [해설]을 무조건 맹신하여 억지로 끼워 맞추지 마세요!
반드시 [문제 지문]의 조건과 사실을 직접 다시 검증해 보고,
(A) 문제나 보기에 실제 출제 오류가 있었던 경우, 또는
(B) 학생이 제출했던 답안이 실제로 정답으로 인정될 수 있는 타당한 답안인 경우에는,
학생에게 정직하게 오류를 인정하고 정답으로 정정해 주겠다고 칭찬한 뒤, 답변 맨 마지막에 `[SCORE_UPGRADE_APPROVED]` 태그를 붙이세요.
(단, 단순 질문이거나 학생이 틀렸는데 근거 없이 점수만 달라고 떼쓰는 경우에는 절대 태그를 붙이지 마세요!)

초등학생 눈높이에 맞추어 이해하기 쉽고 따뜻하게 2~3문장으로 명쾌하게 설명해주세요.
"""
    try:
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config={"temperature": 0.4}
        )
        ai_reply = resp.text.strip()
    except Exception:
        ai_reply = f"선생님이 질문을 잘 읽어보았어요! 이 문제는 '{req.model_answer or '핵심 개념'}'와(과) 연관되어 있단다. 지문이나 문맥의 뜻을 차근차근 살펴보면 더 쉽게 이해할 수 있을 거야!"

    # 점수 정정 승인 태그 감지 및 정제
    grant_full_score = "[SCORE_UPGRADE_APPROVED]" in ai_reply
    if grant_full_score:
        ai_reply = ai_reply.replace("[SCORE_UPGRADE_APPROVED]", "").strip()

    # 대화 기록 저장
    db_res = append_chat_message(log_id=req.log_id, student_question=req.student_question, ai_reply=ai_reply)

    # 출제 오류나 정당 답안 인정 시 DB 정답(만점) 처리 및 최신 점수 반영
    score_info = {}
    if grant_full_score:
        score_info = grant_full_score_by_tutor(
            log_id=req.log_id,
            user_name=req.user_name,
            user_id=req.user_id,
        )

    return {
        "success": True,
        "log_id": req.log_id,
        "ai_reply": ai_reply,
        "chat_history": db_res.get("chat_history", []),
        "score_corrected": grant_full_score,
        "added_score": score_info.get("added_score", 0) if grant_full_score else 0,
        "best_score": score_info.get("best_score", 0) if grant_full_score else 0,
        "total_score": score_info.get("total_score") if grant_full_score else None,
        "user_status": score_info.get("user_status") if grant_full_score else None,
    }


@router.get("/curriculum-summary")
async def get_curriculum_summary():
    """단원 선택 UI를 위한 텍스트 요약 제공"""
    return {"curriculum": load_curriculum_text()}

@router.post("/quiz", response_model=QuizSetResponse)
async def generate_korean_quiz_set(req: QuizRequest):
    """
    지정된 학년/학기 교육과정 내에서 무작위 단원을 선정하여 5문항의 퀴즈 세트를 동적 출제합니다.
    """
    client = get_genai_client()
    curriculum_context = load_curriculum_text()

    target_unit_instruction = ""
    if req.unit and req.unit.strip() and req.unit.strip() != "전체":
        target_unit_instruction = f"\n[★ 지정 단원 집중 출제]: 학생이 선택한 단원은 '{req.unit}'입니다. 5개 문항 모두 반드시 이 '{req.unit}' 단원의 교육과정 학습 목표와 핵심 개념에 집중하여 출제해 주세요."
        unit_rule = f"1. 단원 선정: 학생이 지정한 '{req.unit}' 단원의 핵심 내용에서 5문항 모두 집중 출제하세요."
    elif req.use_weakest:
        weak = get_weakest_unit_and_topic(req.user_name or "김에듀")
        if weak and weak.get("unit"):
            target_unit_instruction = f"\n[★ 취약 단원 맞춤 출제]: 학생의 최근 오답 분석 결과 가장 취약한 단원은 '{weak['unit']}'입니다. 이 취약 단원의 핵심 역량을 강화할 수 있는 문제를 우선적으로 포함해 주세요."
        unit_rule = f"1. 단원 선정: 학생의 취약 단원을 우선 고려하여 {req.grade} 목차에서 알맞게 선정하세요."
    else:
        unit_rule = f"1. 단원 무작위 선정: {req.grade} 교육과정 목차 중에서 어떤 단원에서 몇 문제를 출제할지는 자유롭고 무작위(Random)로 결정하세요."

    # 4대 문제 유형별 강력한 출제 공식 정의
    type_rules = """
[★ 4대 문제 유형별 절대 출제 공식 - 위반 시 무효 ★]
1. OX 퀴즈:
   - question은 반드시 "하나의 완결된 설명문(진술)"을 제시하고, 마지막에 "(이 설명이 맞으면 O, 틀리면 X를 선택하세요.)"로 끝나야 합니다.
   - ⚠️ 절대 "다음 중 옳은 것은?" 같은 객관식 질문을 던지지 마세요!
   - options는 반드시 정확히 ["O", "X"] 2개만 넣으세요.
   - answer는 오직 "O" 또는 "X" 한 글자만 넣으세요. (절대 '맞다', '참', 'O (정답)' 등을 넣지 마세요!)
   - 올바른 예시:
     "『비유하는 표현』은 어떤 현상이나 사물을 다른 현상이나 사물에 빗대어 나타내는 것이다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)"

2. 객관식 (4지선다):
   - question은 "다음 글을 읽고 ... 가장 알맞은 것을 고르시오." 형태로 질문만 작성하세요.
   - ⚠️ 절대 question 지문 안에 ①, ②, ③, ④ 선택지 내용을 적지 마세요! 지문 안에는 지문과 질문만 넣으세요.
   - options 배열에 반드시 4개의 실질적인 보기 텍스트를 넣으세요. (예: ["직유법", "은유법", "의인법", "풍유법"])
   - ⚠️ 절대 options에 ["1번", "2번", "3번", "4번"]이나 ["1", "2", "3", "4"] 같은 무의미한 번호만 넣지 마세요!
   - answer는 options 중 정답 보기 텍스트와 100% 토씨 하나 안 틀리고 동일하게 작성하세요. (예: "직유법")

3. 단답형 (주관식):
   - 학생이 낱말 하나를 직접 자판으로 입력하는 문제입니다.
   - ⚠️ 절대 question에 "고르시오", "선택하시오", "보기 중"이라는 단어를 사용하지 마세요!
   - 반드시 "~은 무엇인지 쓰시오.", "빈칸에 들어갈 알맞은 낱말을 쓰시오." 형태로 직접 쓰도록 요구하세요.
   - options는 반드시 빈 배열 [] 이어야 합니다.
   - answer는 핵심 정답 낱말 1개만 명확히 제시하세요. (예: "비유")

4. 서술형 (주관식):
   - 학생이 한두 문장으로 생각이나 까닭을 직접 서술하는 주관식 문제입니다.
   - ⚠️ 절대 question에 "고르시오", "선택하시오"를 사용하지 마세요!
   - 반드시 "~의 까닭을 한 문장으로 서술하시오.", "~한 이유를 설명하시오." 형태로 출제하세요.
   - options는 반드시 빈 배열 [] 이어야 합니다.
   - answer는 1~2문장의 친절한 모범 서술 답안을 제시하세요.
"""

    if req.question_type in ["단답형", "서술형"]:
        sample_options = "[]"
    elif req.question_type == "OX":
        sample_options = '["O", "X"]'
    else:
        sample_options = '["선택지 1", "선택지 2", "선택지 3", "선택지 4"]'

    prompt = f"""
당신은 2022 개정 초등학교 국어 교육과정 전문 AI 교사입니다.
아래 [교육과정 단원 목록]에서 {req.grade}의 목차를 참고하여, 총 5개의 국어 평가 문제를 출제해주세요.{target_unit_instruction}

[교육과정 단원 목록]
{curriculum_context}

{type_rules}

[★ 출제 원칙 ★]
{unit_rule}
2. 대상 학년: {req.grade}
3. 문제 수: 정확히 5문항 (id: 1, 2, 3, 4, 5)
4. 출제 문제 유형: {req.question_type} (5문항 모두 반드시 지정된 '{req.question_type}' 유형의 공식에 맞게 출제)
5. 국어과 역량 중심: 질문은 반드시 국어적 역량(중심 내용, 관점, 사실과 의견, 어휘 의미, 맞춤법 등)을 평가할 것.
6. 난이도 및 차등 배점 원칙 (필수 준수):
   - 5문항의 난이도를 다양하게 분배하세요: '하' (기초 확인 1~2문항), '중' (표준 적용 2~3문항), '상' (심화 추론 1문항).
   - difficulty 값은 반드시 '하', '중', '상' 중 하나만 입력하세요.
   - 난이도별 배점(base_score): '하'는 1점, '중'은 3점, '상'은 5점을 정확히 부여하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "grade": "{req.grade}",
  "total_count": 5,
  "questions": [
    {{
      "id": 1,
      "unit": "출제 단원명1",
      "question_type": "{req.question_type}",
      "difficulty": "하",
      "base_score": 1,
      "question": "문제 내용",
      "options": {sample_options},
      "answer": "정답",
      "explanation": "해설"
    }},
    {{
      "id": 2,
      "unit": "출제 단원명2",
      "question_type": "{req.question_type}",
      "difficulty": "중",
      "base_score": 3,
      "question": "문제 내용",
      "options": {sample_options},
      "answer": "정답",
      "explanation": "해설"
    }},
    {{
      "id": 3,
      "unit": "출제 단원명3",
      "question_type": "{req.question_type}",
      "difficulty": "중",
      "base_score": 3,
      "question": "문제 내용",
      "options": {sample_options},
      "answer": "정답",
      "explanation": "해설"
    }},
    {{
      "id": 4,
      "unit": "출제 단원명4",
      "question_type": "{req.question_type}",
      "difficulty": "상",
      "base_score": 5,
      "question": "문제 내용",
      "options": {sample_options},
      "answer": "정답",
      "explanation": "해설"
    }},
    {{
      "id": 5,
      "unit": "출제 단원명5",
      "question_type": "{req.question_type}",
      "difficulty": "중",
      "base_score": 3,
      "question": "문제 내용",
      "options": {sample_options},
      "answer": "정답",
      "explanation": "해설"
    }}
  ]
}}
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "temperature": 0.5
            }
        )
        raw_text = response.text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
        data = json.loads(cleaned, strict=False)

        raw_questions = data.get("questions", [])
        clean_questions: List[QuizItem] = []

        import time
        t_stamp = int(time.time() * 1000)

        for idx, q in enumerate(raw_questions[:5], start=1):
            q_type = req.question_type
            q_text = str(q.get("question", "")).strip()
            q_ans = str(q.get("answer", "")).strip()
            q_exp = str(q.get("explanation", "")).strip()

            if q_type == "OX":
                opts = ["O", "X"]
                # OX 정답 정규화: '참', '맞', 'o' 등은 'O', '거짓', '틀', 'x' 등은 'X'
                if any(k in q_ans.lower() for k in ["o", "참", "맞", "옳", "true"]):
                    q_ans = "O"
                elif any(k in q_ans.lower() for k in ["x", "거짓", "틀", "아닙", "false"]):
                    q_ans = "X"
                else:
                    q_ans = "O" if "O" in q_ans else "X"

                # OX 발문 보정: 객관식 문구("고르시오" 등)가 남아있으면 설명문형으로 정제
                if not ("(이 설명이 맞으면" in q_text or "O/X" in q_text or "O인지 X인지" in q_text):
                    q_text = q_text.rstrip(".") + "\n(이 설명이 맞으면 O, 틀리면 X를 선택하세요.)"

            elif q_type in ["단답형", "서술형"]:
                opts = []
                # 주관식인데 "고르시오"라는 객관식 발문이 섞였을 경우 정제
                q_text = re.sub(r"다음\s*중\s*알맞은\s*것을\s*고르시오\.?", "알맞은 답을 쓰시오.", q_text)
                q_text = re.sub(r"알맞은\s*것을\s*고르시오\.?", "알맞은 답을 쓰시오.", q_text)
                q_text = re.sub(r"가장\s*적절한\s*것을\s*고르시오\.?", "알맞은 답을 쓰시오.", q_text)

            else:  # 객관식
                opts = q.get("options", [])
                # 만약 options가 비었거나 '1번, 2번' 형태인 경우, 지문 본문에서 보기를 파출 시도
                is_invalid_opts = (not isinstance(opts, list)) or (len(opts) < 2) or all(re.match(r"^(\d+번|\d+)$", str(o).strip()) for o in opts)
                if is_invalid_opts:
                    # 지문에서 ① ② ③ ④ 또는 1) 2) 3) 4) 추출 시도
                    extracted = re.findall(r"(?:[①-④]|\d\))\s*([^\n①-④\d\)]+)", q_text)
                    if len(extracted) >= 4:
                        opts = [e.strip() for e in extracted[:4]]
                        # 지문에서 보기 목록 제거
                        q_text = re.sub(r"(?:[①-④]|\d\))\s*[^\n①-④\d\)]+", "", q_text).strip()
                    else:
                        opts = ["1번 보기", "2번 보기", "3번 보기", "4번 보기"]

                # 각 보기 앞의 불필요한 번호 접두어(예: "1. ", "① ", "1) ") 제거
                clean_opts = []
                for o in opts[:4]:
                    clean_opt = re.sub(r"^([①-④]|\d+[\.\)]|\[\d+\])\s*", "", str(o).strip())
                    clean_opts.append(clean_opt or str(o).strip())
                opts = clean_opts

                # answer가 '1번' 또는 숫자 형태면 실제 텍스트로 보정 시도
                num_m = re.match(r"^(\d+)번?$", q_ans)
                if num_m:
                    n_idx = int(num_m.group(1)) - 1
                    if 0 <= n_idx < len(opts):
                        q_ans = opts[n_idx]

            q_uid = f"korean_{req.grade}_q{idx}_{t_stamp}"
            raw_diff = str(q.get("difficulty", "중")).strip()
            if "하" in raw_diff:
                clean_diff = "하"
            elif "상" in raw_diff:
                clean_diff = "상"
            else:
                clean_diff = "중"
            calc_score = {"하": 1, "중": 3, "상": 5}.get(clean_diff, 3)

            clean_questions.append(
                QuizItem(
                    id=idx,
                    quiz_id=q_uid,
                    unit=str(q.get("unit", f"단원 {idx}")),
                    question_type=q_type,
                    difficulty=clean_diff,
                    base_score=calc_score,
                    question=q_text,
                    options=opts,
                    answer=q_ans,
                    explanation=q_exp
                )
            )

        # 만약 5개 미만으로 생성되었을 경우 안전 보정
        while len(clean_questions) < 5:
            n = len(clean_questions) + 1
            fb_diff = "하" if n == 1 else ("상" if n >= 4 else "중")
            fb_score = {"하": 1, "중": 3, "상": 5}.get(fb_diff, 3)
            def_opts = ["O", "X"] if req.question_type == "OX" else (["첫째", "둘째", "셋째", "넷째"] if req.question_type == "객관식" else [])
            def_q = f"{req.grade} 국어 확인 진술입니다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)" if req.question_type == "OX" else f"{req.grade} 국어 확인 문제입니다."
            clean_questions.append(
                QuizItem(
                    id=n,
                    quiz_id=f"korean_{req.grade}_q{n}_{t_stamp}",
                    unit=f"핵심 국어 단원 {n}",
                    question_type=req.question_type,
                    difficulty=fb_diff,
                    base_score=fb_score,
                    question=def_q,
                    options=def_opts,
                    answer="O" if req.question_type == "OX" else "첫째",
                    explanation="2022 개정 교육과정 성취기준에 따른 기본 해설입니다."
                )
            )

        return QuizSetResponse(
            grade=req.grade,
            total_count=5,
            questions=clean_questions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"5문항 퀴즈 출제 오류: {str(e)}")


@router.post("/grade-set", response_model=GradeSetResponse)
async def grade_korean_quiz_set(req: GradeSetRequest):
    """
    사용자가 푼 5문항의 답안을 일괄 채점하고 총점과 문항별 피드백을 산출합니다.
    """
    client = get_genai_client()
    results: List[GradeItemResult] = []
    total_score = 0
    correct_count = 0

    # 서술형/단답형 중 문맥 평가가 필요한 문항 수집
    ai_eval_items = []
    for item in req.items:
        user_clean = item.user_answer.strip().lower()
        model_clean = item.model_answer.strip().lower()

        if item.question_type == "OX":
            # OX 전용 정밀 판정 로직
            u_ox = "O" if any(k in user_clean for k in ["o", "참", "맞", "옳", "true"]) else ("X" if any(k in user_clean for k in ["x", "거짓", "틀", "아닙", "false"]) else user_clean.upper())
            m_ox = "O" if any(k in model_clean for k in ["o", "참", "맞", "옳", "true"]) else ("X" if any(k in model_clean for k in ["x", "거짓", "틀", "아닙", "false"]) else model_clean.upper())
            is_correct = (u_ox == m_ox)
            score = item.base_score if is_correct else 0
            if is_correct:
                fb = f"정답입니다! 진술의 참/거짓을 바르게 판별했어요 ({m_ox}). 🎉"
                correct_count += 1
            else:
                fb = f"아쉬워요! 올바른 답은 '{m_ox}'입니다. 💡"
            total_score += score
            results.append(GradeItemResult(
                id=item.id,
                score=score,
                max_score=item.base_score,
                is_correct=is_correct,
                feedback=fb,
                model_answer=item.model_answer,
                user_answer=item.user_answer
            ))
        elif item.question_type == "객관식":
            # 보기 앞뒤 공백 및 번호 제거 후 정밀 일치 비교
            u_norm = re.sub(r"^([①-④]|\d+[\.\)]|\[\d+\])\s*", "", user_clean)
            m_norm = re.sub(r"^([①-④]|\d+[\.\)]|\[\d+\])\s*", "", model_clean)
            is_correct = (u_norm == m_norm) or (u_norm in m_norm) or (m_norm in u_norm)
            score = item.base_score if is_correct else 0
            if is_correct:
                fb = "정답입니다! 알맞은 보기를 정확히 골랐습니다. 🎉"
                correct_count += 1
            else:
                fb = f"아쉬워요! 정답은 '{item.model_answer}'입니다. 💡"
            total_score += score
            results.append(GradeItemResult(
                id=item.id,
                score=score,
                max_score=item.base_score,
                is_correct=is_correct,
                feedback=fb,
                model_answer=item.model_answer,
                user_answer=item.user_answer
            ))
        elif item.question_type == "단답형":
            # 단답형 단순 일치 여부 먼저 확인
            if user_clean == model_clean or user_clean in model_clean or model_clean in user_clean:
                score = item.base_score
                is_correct = True
                fb = "정답입니다! 핵심 낱말을 바르게 적었습니다. 🎉"
                correct_count += 1
                total_score += score
                results.append(GradeItemResult(
                    id=item.id,
                    score=score,
                    max_score=item.base_score,
                    is_correct=is_correct,
                    feedback=fb,
                    model_answer=item.model_answer,
                    user_answer=item.user_answer
                ))
            else:
                ai_eval_items.append(item)
        else:  # 서술형
            ai_eval_items.append(item)

    # AI 채점이 필요한 문항 일괄 평가
    if ai_eval_items:
        prompt_data = [
            {
                "id": it.id,
                "question": it.question,
                "model_answer": it.model_answer,
                "user_answer": it.user_answer,
                "base_score": it.base_score
            }
            for it in ai_eval_items
        ]

        prompt = f"""
당신은 2022 개정 초등국어 공정 채점관입니다.
아래 학생의 주관식/서술형 답안 목록을 채점하여 각 문항별 점수(0점 ~ 해당 문항의 base_score 만점), 정답 여부, 친절한 조언 피드백을 JSON으로 작성하세요.
각 문항의 score는 0점 이상 base_score 이하의 정수여야 합니다. (예: base_score가 1점이면 0~1점, 3점이면 0~3점, 5점이면 0~5점)

[채점 대상 목록]
{json.dumps(prompt_data, ensure_ascii=False, indent=2)}

반드시 아래 형식의 JSON 배열로만 응답하세요:
[
  {{
    "id": 1,
    "score": 3,
    "is_correct": true,
    "feedback": "초등학생 눈높이의 친절한 1문장 피드백"
  }}
]
"""
        try:
            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.3}
            )
            raw_text = resp.text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
            graded_list = json.loads(cleaned, strict=False)
            graded_map = {g.get("id"): g for g in graded_list if isinstance(g, dict)}

            for it in ai_eval_items:
                g_info = graded_map.get(it.id, {})
                sc = min(it.base_score, max(0, int(g_info.get("score", 0))))
                threshold = max(1, it.base_score / 2)
                corr = bool(g_info.get("is_correct", sc >= threshold))
                fb = str(g_info.get("feedback", "문맥 검토가 완료되었습니다."))
                if corr:
                    correct_count += 1
                total_score += sc
                results.append(GradeItemResult(
                    id=it.id,
                    score=sc,
                    max_score=it.base_score,
                    is_correct=corr,
                    feedback=fb,
                    model_answer=it.model_answer,
                    user_answer=it.user_answer
                ))
        except Exception:
            for it in ai_eval_items:
                part_score = 1 if it.base_score >= 3 else 0
                results.append(GradeItemResult(
                    id=it.id,
                    score=part_score,
                    max_score=it.base_score,
                    is_correct=False,
                    feedback=f"정답: '{it.model_answer}'.",
                    model_answer=it.model_answer,
                    user_answer=it.user_answer
                ))
                total_score += part_score

    # id 순서대로 정렬
    results.sort(key=lambda x: x.id)
    max_total = sum(it.base_score for it in req.items)

    # 학년 숫자 파싱 (예: '4학년 1학기' -> 4)
    grade_num = 4
    if req.grade:
        m = re.search(r"(\d+)", req.grade)
        if m:
            grade_num = int(m.group(1))

    # req.items를 id 기준 딕셔너리로 매핑
    req_item_map = {item.id: item for item in req.items}

    # 각 채점 문항마다 save_quiz_log 호출하여 중앙 DB에 풀이 로그 기록 & log_id 바인딩
    import time
    t_now = int(time.time() * 1000)
    for res_item in results:
        req_item = req_item_map.get(res_item.id)
        if req_item:
            q_id = req_item.quiz_id or f"korean_{grade_num}_{req_item.id}_{t_now}"
            log_res = save_quiz_log(
                user_id=req.user_id,
                user_name=req.user_name,
                quiz_id=q_id,
                grade=grade_num,
                unit=req_item.unit or None,
                topic=None,  # 국어에서 미사용 시 None (DB에서는 NULL로 안전하게 기록됨)
                difficulty=req_item.difficulty or "중",
                question_type=req_item.question_type,
                question=req_item.question,
                user_answer=res_item.user_answer,
                correct_answer=res_item.model_answer,
                solution=req_item.explanation or None,
                earned_score=res_item.score,
                is_correct=res_item.is_correct,
            )
            res_item.log_id = log_res.get("log_id")

    # 학생의 최신 상태(포켓몬 진화 등급 정보 및 전과목 누적 총점) 실시간 산출
    user_status = get_or_create_user(
        user_id=req.user_id,
        user_name=req.user_name,
        grade=grade_num,
        pokemon_type=req.pokemon_type
    )

    return GradeSetResponse(
        total_score=total_score,
        max_total_score=max_total,
        correct_count=correct_count,
        total_count=len(req.items),
        user_status=user_status,
        results=results
    )


# ==============================================================================
# 5. 과목 단독 테스트 실행 블록 (가이드라인 [261008 추가지시사항] 표준)
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    import webbrowser

    app = FastAPI(title="EduMate AI - [초등국어] 단독 테스트 서버")
    app.include_router(router)

    @app.get("/")
    async def root_page():
        html_file = CURRENT_DIR / "index.html"
        if html_file.exists():
            return FileResponse(str(html_file))
        return {
            "message": "EduMate AI 초등국어 단독 테스트 API 서버 가동 중",
            "docs": "http://localhost:8000/docs",
            "curriculum": "/korean/curriculum-summary"
        }

    PORT = 8000
    print(f"🚀 EduMate AI 초등국어 단독 테스트 서버 시작: http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")

    # 스파이더(IPython) 및 주피터 환경의 이벤트 루프 중복 충돌 방지 처리
    import asyncio
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        config = uvicorn.Config(app, host="0.0.0.0", port=PORT)
        server = uvicorn.Server(config)
        loop.create_task(server.serve())
    else:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
