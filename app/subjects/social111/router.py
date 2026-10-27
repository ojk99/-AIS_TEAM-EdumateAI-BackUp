# -*- coding: utf-8 -*-
"""
[EduMate AI - 초등사회] AI 문제 출제 및 서술형 채점 엔진 (social/router.py)
- 특징:
  1. 가이드라인 [추가지시사항 3] 계단식 .env 다중 탐색 적용
  2. 가이드라인 [추가지시사항 1] 단독 실행용 FastAPI 인스턴스(app) 및 자동 브라우징 내장
  3. API 키가 없어도 '내장 문제은행(QuestionBankService 270문항)'으로 100% 즉시 무설치·무과금 구동
  4. 1~2학년군, 3~4학년군, 5~6학년군 전 학년 지원 및 스마트 중복 출제 방지 알고리즘
  5. 서술형 0~5점 5단계 문맥 정밀 채점 (gemini-3.5-flash-lite 연동)
"""

import os
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# [가이드라인 추가지시사항 3] .env 안전 계단식 탐색 (다중 폴백 메커니즘)
# --------------------------------------------------------------------------
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent

if (current_dir / ".env").exists():
    load_dotenv(dotenv_path=current_dir / ".env")
elif (parent_dir / ".env").exists():
    load_dotenv(dotenv_path=parent_dir / ".env")
elif (parent_dir.parent / ".env").exists():
    load_dotenv(dotenv_path=parent_dir.parent / ".env")
else:
    load_dotenv()

# --------------------------------------------------------------------------
# 모듈 임포트 (통합 패키지 환경 및 조원 단독 실행 환경 100% 양방향 호환)
# --------------------------------------------------------------------------
try:
    from .question_bank import QuestionBankService, QUESTION_BANK
except (ImportError, ValueError):
    try:
        from social.question_bank import QuestionBankService, QUESTION_BANK
    except ImportError:
        from question_bank import QuestionBankService, QUESTION_BANK

try:
    from .quiz_logs import (
        save_quiz_log,
        get_or_create_user,
        get_user_status,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
    )
except (ImportError, ValueError):
    try:
        from social.quiz_logs import (
            save_quiz_log,
            get_or_create_user,
            get_user_status,
            append_chat_message,
            toggle_favorite,
            get_weakest_unit_and_topic,
        )
    except ImportError:
        from quiz_logs import (
            save_quiz_log,
            get_or_create_user,
            get_user_status,
            append_chat_message,
            toggle_favorite,
            get_weakest_unit_and_topic,
        )


try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def call_ai_text(prompt: str, max_tokens: int = 350, temperature: float = 0.2) -> Optional[str]:
    """
    [크레딧 초절약형 AI 호출 엔진]
    1. OpenAI 키(sk-proj-...)가 있는 경우 -> 가장 저렴하고 빠른 gpt-4o-mini 호출 (1원 미만 초저비용)
    2. Gemini 키가 있는 경우 -> gemini-3.5-flash-lite 호출
    3. 둘 다 없거나 오류 시 -> None 반환하여 100% 무과금 자체 엔진으로 안전하게 폴백
    """
    # 1) OpenAI 우선 검사 (social 전용 키)
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("SOCIAL_API_KEY")
    if openai_key and OPENAI_AVAILABLE and openai_key.strip().startswith("sk-"):
        try:
            client = OpenAI(api_key=openai_key.strip())
            resp = client.chat.completions.create(
                model=os.getenv("AI_MODEL_NAME", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "너는 2022 개정 초등학교 사회과 전문 AI 교사야. 핵심 내용만 다정하고 간결하게 응답해."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print("[OpenAI 호출 알림]:", e)

    # 2) Gemini 키 검사
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and GENAI_AVAILABLE and not gemini_key.strip().startswith("sk-"):
        try:
            client = genai.Client(api_key=gemini_key.strip(), http_options={"api_version": "v1"})
            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
            )
            return resp.text.strip()
        except Exception as e:
            print("[Gemini 호출 알림]:", e)

    return None


def has_ai_service() -> bool:
    """사용 가능한 외부 AI API(OpenAI 또는 Gemini)가 연결되어 있는지 여부"""
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("SOCIAL_API_KEY")
    if openai_key and OPENAI_AVAILABLE and openai_key.strip().startswith("sk-"):
        return True
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and GENAI_AVAILABLE and not gemini_key.strip().startswith("sk-"):
        return True
    return False


# --------------------------------------------------------------------------
# 팀 공통 규격 APIRouter 정의
# --------------------------------------------------------------------------
router = APIRouter(prefix="/social", tags=["초등사회"])

CURRICULUM_PATH = current_dir / "curriculum.txt"


def load_curriculum() -> str:
    if CURRICULUM_PATH.exists():
        with open(CURRICULUM_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "초등사회 교육과정 단원 목록"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def serve_subject_index():
    """초등사회 웹 화면 서빙 (Step B 필수 표준 엔드포인트)"""
    html_path = current_dir / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return HTMLResponse("<h3>index.html을 찾을 수 없습니다.</h3>", status_code=404)


@router.get("/logo.svg")
@router.get("/edumate_logo.svg")
def get_subject_logo():
    """공식 EduMate AI 로고 SVG 서빙"""
    logo_path = current_dir / "edumate_logo.svg"
    if logo_path.exists():
        return FileResponse(str(logo_path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="edumate_logo.svg not found")



@router.get("/questions_data.js")
def get_questions_data_js():
    """270문항 데이터베이스 JS 파일 서빙"""
    js_path = current_dir / "questions_data.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    return HTTPException(status_code=404, detail="questions_data.js not found")


@router.get("/images/{image_name}")
def get_social_image(image_name: str):
    """문화재 실물 사진 서빙"""
    img_path = current_dir / "images" / image_name
    if img_path.exists():
        media_type = "image/jpeg"
        if image_name.endswith(".webp"):
            media_type = "image/webp"
        elif image_name.endswith(".png"):
            media_type = "image/png"
        return FileResponse(str(img_path), media_type=media_type)
    return HTTPException(status_code=404, detail="Image not found")


# --------------------------------------------------------------------------
# 요청 및 응답 데이터 모델 (Pydantic DTO)
# --------------------------------------------------------------------------
class QuizGenerateRequest(BaseModel):
    grade_group: str = "3~4학년군"     # 1~2학년군, 3~4학년군, 5~6학년군
    unit_name: str = "전체 단원"
    question_type: str = "random"      # ox, multiple_choice, short_answer, descriptive, random
    recent_ids: list[str] = []         # 최근 푼 문제 ID 목록 (중복 방지)


class QuizGradeRequest(BaseModel):
    user_name: str = "김에듀"
    question_id: str = ""
    question_type: str                 # ox, multiple_choice, short_answer, descriptive
    question: str
    correct_answer: str
    user_answer: str
    base_score: int = 3                # 1, 3, 5점
    unit_name: str = ""
    grade: Optional[int] = 4
    pokemon_type: str = "grass"


class FavoriteRequest(BaseModel):
    log_id: int


class FollowupChatRequest(BaseModel):
    log_id: int
    question: str
    user_name: str = "김에듀"



# --------------------------------------------------------------------------
# 1. 문제 출제 API (API 키 없을 땐 대규모 문제은행에서 스마트 랜덤 추출)
# --------------------------------------------------------------------------
@router.post("/quiz/generate")
def generate_quiz(req: QuizGenerateRequest):
    import random

    # API 서비스가 없으면 즉시 문제은행에서 출제 (무과금 100% 자립)
    if not has_ai_service():
        return QuestionBankService.get_question(
            grade_group=req.grade_group,
            unit_name=req.unit_name,
            question_type=req.question_type,
            recent_ids=req.recent_ids
        )

    # 1) 문제 유형 정규화 (basic_all 또는 빈값인 경우 3대 기본 유형 중 랜덤 선택)
    target_type = req.question_type
    if target_type in ["basic_all", "random", "", None]:
        target_type = random.choice(["ox", "multiple_choice", "short_answer"])

    # 2) 중복 출제 완전 방지를 위한 학년군별 다채로운 세부 주제 풀
    TOPIC_POOLS = {
        "1~2학년군": [
            "학교 시설과 안전 규칙", "친구와 사이좋게 지내는 배려", "사계절의 변화와 옷차림",
            "우리 가족의 모습과 친척 호칭", "우리 동네 공공장소 이용 예절", "골목길과 신호등 교통안전",
            "전통 놀이와 명절 풍습", "병원과 보건실 이용하기", "경찰서와 소방서의 고마움"
        ],
        "3~4학년군": [
            "지도에서 방위표와 기호 읽기", "우리 고장의 자연환경과 산·하천", "우리 고장의 자랑스러운 문화유산과 유물",
            "옛날과 오늘날의 교통수단 발달 과정", "통신수단의 발달과 편리해진 생활", "환경오염 문제와 분리배출 실천",
            "촌락(농촌·어촌·산지촌)과 도시의 생활 차이", "시장의 종류와 현명한 합리적 소비", "옛날과 오늘날의 세시 풍속과 한복",
            "우리 고장의 공공기관과 주민 참여", "주민 자치와 고장의 문제 해결", "지역 특산물과 지리적 표시제"
        ],
        "5~6학년군": [
            "우리 국토의 위치, 영토·영해·영공과 독도", "우리나라의 기후와 지형적 특징(동고서저)", "인권 보장과 대한민국 헌법의 정신",
            "국민의 기본권(자유·평등·참정·청구·사회권)과 의무", "삼권분립(국회, 정부, 법원)의 상호 견제와 균형",
            "민주 선거의 4대 원칙(보통·평등·직접·비밀)", "우리나라의 경제 발전과 무역의 중요성", "세계 여러 나라의 기후와 독특한 문화",
            "지구촌 갈등(전쟁, 난민)과 평화를 위한 노력", "기후 위기, 탄소중립과 신재생 에너지", "유엔(UN)과 유네스코의 활동"
        ]
    }
    pool = TOPIC_POOLS.get(req.grade_group, TOPIC_POOLS["3~4학년군"])
    sub_topic = random.choice(pool)

    # 3) API 서비스가 있으면 크레딧 초절약형 AI 실시간 온디맨드 출제 시도 (temperature 0.85로 다양성 극대화)
    curriculum_text = load_curriculum()
    options_guide = '["1번", "2번", "3번", "4번"] (서로 다른 명확한 4개 보기 필수)' if target_type == "multiple_choice" else '[] (보기 없음)'

    prompt = f"""
너는 2022 개정 교육과정 초등학교 사회과 전문 AI 교사야.
초등학생 눈높이에 꼭 맞는 신선하고 참신한 퀴즈 1문제를 출제해줘.

[출제 요구 조건]
- 대상 학년군: {req.grade_group}
- 선택 단원: {req.unit_name}
- 핵심 세부 주제: {sub_topic} (반드시 이 세부 주제에 관련된 새로운 문제를 출제하세요!)
- 문제 유형: {target_type}
- 최근에 낸 뻔한 문제를 피하고, 학생들의 흥미를 끄는 참신한 일상 속 예시나 지문을 활용할 것.
- 객관식 문제의 해설(explanation)은 정답인 구체적인 까닭과 관련 핵심 개념 원리를 초등학생 눈높이에 맞추어 3~4문장으로 매우 친절하고 자세하게 설명할 것!
- 배점 규칙: 하(1점), 중(3점), 상(5점)

[출력 형식 JSON]
{{
  "id": "ai_gen_{os.urandom(4).hex()}",
  "question_type": "{target_type}",
  "difficulty": "중",
  "base_score": 3,
  "question": "문제 지문",
  "options": {options_guide},
  "answer": "정답",
  "explanation": "초등학생 눈높이에 맞춘 구체적이고 자세한 3~4문장 원리 해설"
}}
"""
    try:
        # 온도를 0.85로 높여 창의적이고 겹치지 않는 신선한 문제 유도
        text_resp = call_ai_text(prompt, max_tokens=350, temperature=0.85)
        if text_resp:
            text_resp = re.sub(r"^```json\s*", "", text_resp)
            text_resp = re.sub(r"^```\s*", "", text_resp)
            text_resp = re.sub(r"\s*```$", "", text_resp)
            quiz_obj = json.loads(text_resp)
            quiz_obj["question_type"] = target_type
            if target_type == "multiple_choice" and (not quiz_obj.get("options") or len(quiz_obj["options"]) < 2):
                raise ValueError("객관식 보기가 부족합니다.")
            return quiz_obj
    except Exception:
        pass

    return QuestionBankService.get_question(
        grade_group=req.grade_group,
        unit_name=req.unit_name,
        question_type=target_type,
        recent_ids=req.recent_ids
    )


# --------------------------------------------------------------------------
# 2. 답안 채점 API (API 키 없이도 자체 키워드 문맥 채점 엔진으로 1~5점 부여)
# --------------------------------------------------------------------------
@router.post("/quiz/grade")
def grade_quiz(req: QuizGradeRequest):
    # 문제은행의 원본 문제 정보에서 서술형 채점 키워드 찾기
    keywords = []
    if req.question_id:
        for q in QUESTION_BANK:
            if q["id"] == req.question_id:
                keywords = q.get("grading_keywords", [])
                break

    # 1) 기본 내장 채점 엔진 실행 (OX, 객관식, 단답형 로컬 유의어 사전 비교 포함)
    local_result = QuestionBankService.grade_answer(
        q_type=req.question_type,
        correct=req.correct_answer,
        user_ans=req.user_answer,
        base_score=req.base_score,
        keywords=keywords
    )
    result = local_result

    # 2) 단답형: 로컬에서 오답 판정되었으나 AI 서비스가 가능한 경우 -> AI 동의어/유의어 문맥 채점 시도!
    if has_ai_service() and req.question_type == "short_answer" and not local_result["is_correct"]:
        synonym_prompt = f"""
너는 2022 개정 초등학교 사회과 전문 채점관 AI야.
단답형 퀴즈에서 학생이 작성한 답안이 모범 답안과 의미상 동일한 유의어/동의어인지, 초등학생 눈높이에서 정답으로 인정할 수 있는지 공정하고 너그럽게 평가해줘.

[채점 가이드]
- '특산품'과 '특산물'은 같은 대상을 뜻하므로 무조건 정답 인정
- '문화유산'과 '문화재', '방위표'와 '방위표시', '한글'과 '훈민정음' 등 의미가 통하면 정답 인정
- 사소한 맞춤법이나 띄어쓰기 차이도 의미가 통하면 정답(true)으로 인정
- 완전히 다른 엉뚱한 개념이거나 오답인 경우만 false 판정

[문제]: {req.question}
[모범 답안]: {req.correct_answer}
[학생 답안]: {req.user_answer}

[출력 형식 JSON]
{{
  "is_correct": true 또는 false,
  "score": {req.base_score} 또는 0,
  "feedback": "초등학생 눈높이에 맞춘 다정하고 명쾌한 1문장 피드백"
}}
"""
        try:
            text_resp = call_ai_text(synonym_prompt, max_tokens=150)
            if text_resp:
                text_resp = re.sub(r"^```json\s*", "", text_resp)
                text_resp = re.sub(r"^```\s*", "", text_resp)
                text_resp = re.sub(r"\s*```$", "", text_resp)
                res_json = json.loads(text_resp)
                is_c = bool(res_json.get("is_correct", False))
                result = {
                    "score": req.base_score if is_c else 0,
                    "max_score": req.base_score,
                    "is_correct": is_c,
                    "feedback": res_json.get("feedback", f"정답입니다! '{req.user_answer}'도 같은 뜻으로 인정돼요! 🌟" if is_c else local_result["feedback"])
                }
        except Exception:
            result = local_result

    # 3) 서술형: AI 서비스가 가능한 경우 -> 5단계 서술형 문맥 부분 점수 정밀 평가
    elif has_ai_service() and req.question_type == "descriptive":
        grading_prompt = f"""
너는 2022 개정 초등학교 사회과 전문 채점관 AI야.
초등학생이 작성한 서술형 답안을 0~5점으로 따뜻하고 공정하게 평가해줘.
완벽한 문장이 아니더라도 핵심 개념이 일부 포함되어 있거나 유사한 올바른 생각을 적었다면 적극적으로 3점 또는 4점의 부분 점수를 부여하세요!

[5단계 부분 점수 채점 가이드]
- 5점 (만점): 핵심 개념과 이유(~때문이다 등)를 논리정연하고 구체적으로 설명함
- 4점 (우수 부분점수): 완벽한 문장은 아니더라도 핵심 내용과 의미가 명확히 통함 (유사 정답 적극 인정)
- 3점 (보통 부분점수): 문장이 다소 짧거나 표현이 서툴러도 핵심 생각이나 관련 단어가 포함되어 의미가 통함
- 2점 (노력 점수): 성실하게 작성하려 노력했으나 핵심 개념 설명이 다소 부족함
- 1점 (참여 점수): 한 문장을 쓰려고 시도했으나 정답과 거리가 멂
- 0점: 전혀 무관한 엉뚱한 답변, 의미 없는 장난/낙서(예: 'ㅋㅋㅋ', '몰라요'), 또는 빈칸

[문제]: {req.question}
[모범 답안]: {req.correct_answer}
[학생 답안]: {req.user_answer}

[출력 형식 JSON]
{{
  "score": 0에서 5 사이 정수,
  "max_score": 5,
  "feedback": "초등학생 눈높이에 맞춘 다정하고 격려가 담긴 1~2문장 원포인트 피드백"
}}
"""
        try:
            text_resp = call_ai_text(grading_prompt, max_tokens=200)
            if text_resp:
                text_resp = re.sub(r"^```json\s*", "", text_resp)
                text_resp = re.sub(r"^```\s*", "", text_resp)
                text_resp = re.sub(r"\s*```$", "", text_resp)
                res_json = json.loads(text_resp)
                earned = int(res_json.get("score", 0))
                result = {
                    "score": earned,
                    "max_score": 5,
                    "is_correct": (earned >= 3),
                    "feedback": res_json.get("feedback", "수고하셨습니다!")
                }
        except Exception:
            result = local_result

    try_update_score(req.user_name, result["score"])

    # 통합 DB(quiz_logs.py)에 풀이 내역 저장 및 전과목 통합 누적 총점 자동 합산
    try:
        earned_score = int(result.get("score", 0))
        save_res = save_quiz_log(
            user_name=req.user_name or "김에듀",
            quiz_id=req.question_id,
            grade=req.grade,
            unit=req.unit_name or None,
            topic=None,
            difficulty=f"{req.base_score}점",
            question_type=req.question_type,
            question=req.question,
            user_answer=req.user_answer,
            correct_answer=req.correct_answer,
            solution=result.get("feedback", ""),
            earned_score=earned_score,
            is_correct=bool(result.get("is_correct", False)),
        )
        result["log_id"] = save_res.get("log_id")
        result["total_score"] = save_res.get("total_score", 0)
        result["subject_score"] = save_res.get("subject_score", 0)
        # 최신 레벨/포켓몬 정보도 함께 전달
        user_st = get_user_status(req.user_name or "김에듀", grade=req.grade, pokemon_type=req.pokemon_type)
        result["level_info"] = user_st.get("level_info")
    except Exception as e:
        print("save_quiz_log error:", e)
        result["log_id"] = None

    return result


# --------------------------------------------------------------------------
# 3. 통합 DB 및 포켓몬 진화 등급 / AI 튜터 추가 질문 / 즐겨찾기 API
# --------------------------------------------------------------------------
@router.get("/user/status")
def get_user_status_api(user_name: str = "김에듀", grade: int = 4, pokemon_type: str = "grass"):
    """학생 상태 및 5대 포켓몬 진화 등급, 전과목 누적 총점 조회"""
    return get_or_create_user(user_name=user_name, grade=grade, pokemon_type=pokemon_type)


@router.get("/user/weakest")
def get_user_weakest_api(user_name: str = "김에듀"):
    """학생의 취약 단원 및 주제 조회 (오답 기반)"""
    return get_weakest_unit_and_topic(user_name=user_name) or {}


@router.post("/favorite/toggle")
def toggle_favorite_api(req: FavoriteRequest):
    """문제 풀이 기록 즐겨찾기 토글"""
    new_fav = toggle_favorite(req.log_id)
    return {"success": True, "log_id": req.log_id, "is_favorite": new_fav}


@router.post("/chat/ask")
def ask_chat_api(req: FollowupChatRequest):
    """AI 선생님께 이어서 질문하기 및 대화 내역 quiz_logs chat_history에 누적 저장"""
    reply = ""
    if has_ai_service():
        try:
            chat_prompt = f"""
너는 초등학교 사회과 다정한 AI 튜터 선생님이야.
초등학생이 방금 푼 사회 문제에 대해 다음과 같이 추가 질문을 했어:
"{req.question}"

초등학생 눈높이에 맞게 쉽고 친절하게 2~3문장으로 설명해줘.
"""
            text_resp = call_ai_text(chat_prompt, max_tokens=250)
            if text_resp:
                reply = text_resp
        except Exception:
            pass
    if not reply:
        reply = f"좋은 질문이에요! 사회 공부는 우리 주변의 현상과 역사를 이해하는 데서 출발해요. '{req.question}'에 대해 교과서와 지도를 함께 살펴보면 더 쉽게 알 수 있답니다!"

    new_history = append_chat_message(req.log_id, req.question, reply)
    return {"success": True, "reply": reply, "chat_history": new_history}


def try_update_score(user_name: str, score: int):
    """core/database.py의 회원 점수 누적 연동"""
    try:
        from core.database import update_user_score
        update_user_score(user_name=user_name, score=score)
    except Exception:
        pass



# --------------------------------------------------------------------------
# [가이드라인 추가지시사항 1] 단독 실행용 FastAPI 인스턴스 (app) 및 루트 라우트
# --------------------------------------------------------------------------
app = FastAPI(title="EduMate AI 초등사회")
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def root_page():
    """루트 경로 접속 시 index.html 서빙"""
    html_path = current_dir / "index.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse("<h3>index.html을 찾을 수 없습니다.</h3>", status_code=404)


@app.get("/questions_data.js")
async def root_questions_data():
    """루트 경로에서 questions_data.js 요청 시 파일 반환"""
    js_path = current_dir / "questions_data.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    return HTTPException(status_code=404, detail="questions_data.js not found")


@app.get("/images/{image_name}")
async def root_image(image_name: str):
    """루트 경로에서 문화재 실물 사진 요청 시 서빙"""
    img_path = current_dir / "images" / image_name
    if img_path.exists():
        media_type = "image/jpeg"
        if image_name.endswith(".webp"):
            media_type = "image/webp"
        elif image_name.endswith(".png"):
            media_type = "image/png"
        return FileResponse(str(img_path), media_type=media_type)
    return HTTPException(status_code=404, detail="Image not found")


# --------------------------------------------------------------------------
# [가이드라인 추가지시사항 1] 단독 실행 블록 (python router.py 실행 시 즉시 오픈)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import webbrowser

    PORT = 8080
    webbrowser.open(f"http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
