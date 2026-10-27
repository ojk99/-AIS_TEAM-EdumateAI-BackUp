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
from dotenv import load_dotenv, find_dotenv

# --------------------------------------------------------------------------
# [가이드라인 추가지시사항 3] .env 안전 계단식 탐색 (다중 폴백 메커니즘)
# --------------------------------------------------------------------------
current_dir = Path(__file__).resolve().parent

env_found = False
p = current_dir
while p != p.parent:
    if (p / ".env").exists():
        load_dotenv(dotenv_path=p / ".env")
        env_found = True
        break
    p = p.parent

if not env_found:
    auto_env = find_dotenv(usecwd=True)
    if auto_env:
        load_dotenv(dotenv_path=auto_env)
    else:
        load_dotenv()

# --------------------------------------------------------------------------
# 모듈 임포트 (통합 패키지 환경 및 조원 단독 실행 환경 100% 양방향 호환)
# --------------------------------------------------------------------------
try:
    from .question_bank import (
        QuestionBankService,
        QUESTION_BANK,
        init_question_bank_db,
        get_unit_bank_stats,
        mark_bank_question_solved,
        draw_bank_question,
        grade_bank_question_by_ai,
    )
except (ImportError, ValueError):
    try:
        from social.question_bank import (
            QuestionBankService,
            QUESTION_BANK,
            init_question_bank_db,
            get_unit_bank_stats,
            mark_bank_question_solved,
            draw_bank_question,
            grade_bank_question_by_ai,
        )
    except ImportError:
        from question_bank import (
            QuestionBankService,
            QUESTION_BANK,
            init_question_bank_db,
            get_unit_bank_stats,
            mark_bank_question_solved,
            draw_bank_question,
            grade_bank_question_by_ai,
        )

try:
    from .quiz_logs import (
        save_quiz_log,
        get_or_create_user,
        get_user_status,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        _clean_user_name,
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
            _clean_user_name,
        )
    except ImportError:
        from quiz_logs import (
            save_quiz_log,
            get_or_create_user,
            get_user_status,
            append_chat_message,
            toggle_favorite,
            get_weakest_unit_and_topic,
            _clean_user_name,
        )

try:
    from .quiz_engines import generate_specialized_quiz, is_answer_leaked
except (ImportError, ValueError):
    try:
        from social.quiz_engines import generate_specialized_quiz, is_answer_leaked
    except ImportError:
        from quiz_engines import generate_specialized_quiz, is_answer_leaked


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
                    {"role": "system", "content": "너는 2022 개정 초등학교 사회과 전문 AI 교사야. 초등학생을 존중하며 모든 문장을 다정하고 정중한 존댓말(~해요, ~일까요?, ~입니다)로 말해. '너희'라는 표현은 절대로 쓰지 말고 항상 '우리' 또는 '여러분'이라고 표현해."},
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
                model=os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash"),
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


def get_curriculum_context(grade_group: str, unit_name: str = "") -> str:
    """curriculum.txt에서 해당 학년군 및 단원의 핵심 개념/주요 내용을 스마트 추출"""
    full_text = load_curriculum()
    if not full_text:
        return ""

    target_tag = ""
    if "1~2" in grade_group:
        target_tag = "[초등학교 1~2학년군"
    elif "3~4" in grade_group:
        target_tag = "[초등학교 3~4학년군]"
    elif "5~6" in grade_group:
        target_tag = "[초등학교 5~6학년군]"

    # 해당 학년군 구간 추출
    if target_tag and target_tag in full_text:
        parts = full_text.split(target_tag)
        if len(parts) > 1:
            section = parts[1]
            for next_tag in ["[초등학교 1~2학년군", "[초등학교 3~4학년군]", "[초등학교 5~6학년군]"]:
                if next_tag != target_tag and next_tag in section:
                    section = section.split(next_tag)[0]

            # 특정 단원이 지정된 경우 해당 단원의 핵심 개념/주요 내용 우선 추출
            if unit_name and unit_name != "전체 단원" and unit_name in section:
                lines = section.splitlines()
                extracted = []
                capture = False
                for line in lines:
                    if unit_name in line:
                        capture = True
                    elif capture and line.strip().startswith(tuple(f"{i}." for i in range(1, 20))):
                        break
                    if capture:
                        extracted.append(line)
                if extracted:
                    return f"[선택 단원 상세 교육과정 ({unit_name})]\n" + "\n".join(extracted)

            return f"[{grade_group} 교육과정 단원 체계]\n" + section.strip()

    return full_text


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


@router.get("/current_affairs_data.js")
def get_current_affairs_data_js():
    """93개 시사상식 데이터베이스 JS 파일 서빙"""
    js_path = current_dir / "current_affairs_data.js"
    if js_path.exists():
        return FileResponse(str(js_path), media_type="application/javascript")
    return HTTPException(status_code=404, detail="current_affairs_data.js not found")


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
    use_ai: bool = True                # 토글 ON: AI 실시간 출제(True), 토글 OFF: 문제은행 출제(False)
    user_id: Optional[str] = None
    user_name: str = "김에듀"


class QuizGradeRequest(BaseModel):
    user_name: str = "김에듀"
    user_id: Optional[str] = None
    question_id: str = ""
    bank_id: Optional[Any] = None      # 문제은행(question_bank.db) 고유 ID
    question_type: str                 # ox, multiple_choice, short_answer, descriptive (또는 한국어 유형명)
    question: str
    correct_answer: str
    user_answer: str
    explanation: Optional[str] = ""
    base_score: int = 3                # 1, 3, 5점
    unit_name: str = ""
    grade: Optional[int] = 4
    pokemon_type: str = "grass"
    is_review_mode: bool = False       # 역방향 폴백 2단계(기풀이 복습 출제) 여부 (True일 때 누적 점수 미반영)


class BankMarkSolvedRequest(BaseModel):
    bank_id: Any
    subject: str = "social"
    user_id: Optional[str] = None
    user_name: Optional[str] = "김에듀"


class BankGradeRequest(BaseModel):
    subject: str = "social"
    bank_id: Optional[Any] = None
    question_type: str = "단답형"
    question_text: str = ""
    question: Optional[str] = ""
    correct_answer: str = ""
    user_answer: str = ""
    explanation: str = ""
    points: int = 3


class FavoriteRequest(BaseModel):
    log_id: int


class FollowupChatRequest(BaseModel):
    log_id: int
    question: str
    user_name: str = "김에듀"


# 단원별 세부 주제 풀 매핑 (AI 실시간 출제용)
UNIT_TOPIC_POOLS = {
    # 1~2학년군
    "학교와 나": [
        "학교 시설과 이용 규칙", "친구와 사이좋게 지내는 배려", "교실 생활 규칙과 우측통행", "선생님과 친구들에게 바른 인사"
    ],
    "계절과 우리 생활": [
        "봄의 날씨와 새싹 관찰", "여름의 더위와 물놀이 안전", "가을의 단풍과 추수", "겨울의 추위와 따뜻한 옷차림"
    ],
    "우리 마을과 사람들": [
        "우리 동네 공공장소 이용 예절", "소방서와 경찰서의 고마움", "도서관과 보건소 이용", "마을 사람들의 다양한 직업"
    ],
    "가족과 안전": [
        "우리 가족의 모습과 화목", "친척 호칭과 가족 예절", "골목길과 횡단보도 교통안전", "가정 내 생활 안전 수칙"
    ],

    # 3~4학년군
    "우리가 사는 곳": [
        "우리 고장의 위치와 모습", "주변 여러 장소에서의 경험과 느낌", "우리 고장을 더 살기 좋은 곳으로 만드는 방법", "고장의 대표 장소와 자랑거리"
    ],
    "일상에서 만나는 과거": [
        "일상 속에서 경험하는 시간의 흐름", "오래된 물건과 도구를 통해 본 과거의 생활", "지역의 옛 사진과 이야기로 보는 변화상", "세시 풍속과 전통 명절의 의미"
    ],
    "사회 변화와 다양한 문화": [
        "저출생·고령화와 가족 형태의 변화", "다문화 사회와 다양한 문화 존중", "정보화와 디지털 생활의 변화", "편견과 차별 없는 사회 만들기"
    ],
    "옛날과 오늘날의 생활 모습": [
        "옛날과 오늘날의 옷차림(의생활) 비교", "옛날과 오늘날의 음식과 집(식생활·주생활)", "교통수단의 발달 과정과 생활의 변화", "통신수단의 발달과 정보 교류 방식의 변화"
    ],
    "지도로 만나는 우리 지역": [
        "지도의 4대 요소(방위표, 기호와 범례, 축척, 등고선)", "지도에서 방위표를 보고 위치 찾기", "지도의 기호와 범례 읽는 법", "우리 지역의 위치와 지리 정보 탐색"
    ],
    "우리 지역의 문화유산": [
        "유형 문화유산과 무형 문화유산의 구분", "우리 지역의 유적지, 유물, 기념관", "문화유산에 담긴 조상들의 지혜와 슬기", "문화유산을 지키고 보호하는 태도"
    ],
    "경제활동과 지역 간 교류": [
        "자원의 희소성과 선택의 문제", "현명하고 합리적인 소비 생활", "생산 활동과 소비 활동의 관계", "지역 간의 물적·인적 교류와 상호 의존"
    ],
    "민주주의와 자치": [
        "학급 회의와 학교 자치 실천", "다수결의 원칙과 소수의견 존중", "주민 자치와 주민 참여의 중요성", "지방자치단체와 지방의회의 역할"
    ],
    "지역문제를 해결하고 지역을 알리는 노력": [
        "우리 지역의 문제 발견과 대화와 타협", "주민 참여를 통한 지역 문제 해결 과정", "지역 특산물과 지리적 표시제", "지역 축제와 문화 행사로 지역 알리기"
    ],
    "다양한 환경과 삶의 모습": [
        "자연환경(산지촌, 농촌, 어촌)에 따른 생활 모습", "도시의 특징(인구 집중, 교통 발달, 고층 건물)", "도시와 촌락의 교류와 상생", "환경오염 문제와 친환경 생태 도시"
    ],

    # 5~6학년군
    "우리나라 국토 여행": [
        "우리 국토의 위치와 영역(영토, 영해, 영공)", "대한민국의 소중한 영토 독도와 마라도", "우리나라 산지, 하천, 해안 지형의 특징", "동고서저의 지형적 특징과 평야"
    ],
    "우리나라 지리 탐구": [
        "우리나라의 사계절 기후와 계절풍", "기후변화와 자연재해(가뭄, 홍수, 태풍, 폭설)", "우리나라의 지역별 인구 분포 특징", "인구 과밀과 인구 감소 지역의 문제와 대책"
    ],
    "법과 인권의 보장": [
        "법의 의미와 사회 질서 유지의 역할", "인권의 의미와 인권 보장의 중요성", "대한민국 헌법과 국민의 기본권", "일상 속 인권 침해 사례와 인권 보호 노력"
    ],
    "유적과 유물로 살펴본 옛 사람들의 생활": [
        "선사 시대(구석기, 신석기, 청동기) 사람들의 도구와 생활", "고조선의 건국과 단군신화", "삼국 시대(고구려, 백제, 신라)의 발전과 문화", "통일신라와 발해, 고려의 생활상과 문화유산"
    ],
    "달라지는 시대, 변화하는 생활 모습": [
        "조선 시대 사람들의 생활과 유교 문화", "조선 후기 서민 문화의 발달(탈춤, 판소리, 풍속화)", "개항기 근대 문물의 수용과 생활의 변화", "신분제의 폐지와 근대 사회로의 진전"
    ],
    "식민 통치와 저항, 전쟁이 바꾼 사회와 생활": [
        "일제의 식민 통치와 3·1 운동, 대한민국 임시정부", "국내외 독립운동과 문화유산 수호 노력", "8·15 광복과 남북 분단의 아픔", "6·25 전쟁의 참상과 전후 복구"
    ],
    "평화 통일을 위한 노력, 민주화와 산업화": [
        "분단으로 인한 이산가족과 국토 분단의 현실", "평화 통일을 위한 다양한 교류와 노력", "4·19 혁명, 5·18 민주화 운동, 6월 민주항쟁", "대한민국의 눈부신 경제 성장과 산업화 과정"
    ],
    "민주주의와 시민 참여": [
        "민주 선거의 4대 원칙(보통, 평등, 직접, 비밀)", "국민의 주권 행사와 투표 참여", "국회, 정부, 법원의 역할과 삼권분립", "미디어 리터러시와 가짜뉴스 분별"
    ],
    "지구, 대륙 그리고 국가들": [
        "지구본, 세계지도, 디지털 공간 정보의 특징", "세계의 5대양 6대주 위치와 특징", "우리나라와 이웃 나라(중국, 일본, 러시아)의 지리적 관계", "세계 주요 국가의 위치와 영역"
    ],
    "세계의 자연환경": [
        "세계의 다양한 기후(열대, 건조, 온대, 냉대, 한대 기후)", "기후 환경에 적응한 세계 사람들의 의식주 생활", "세계의 유명한 지형 경관(산맥, 사막, 빙하 등)", "지구온난화로 인한 세계 환경 위기"
    ],
    "시장경제와 국가 간 거래": [
        "시장경제 체제에서 가계와 기업의 경제적 역할", "근로자의 권리와 기업의 사회적 책임", "국가 간 무역이 일어나는 까닭과 수출입", "세계화 시대의 무역 갈등과 경제 협력"
    ],
    "지구촌 사람들": [
        "세계의 인구 분포와 인구 문제", "지구촌의 다양한 문화와 종교, 축제", "지구촌 갈등(전쟁, 난민, 빈곤)과 평화를 위한 노력", "국제연합(UN)과 비정부기구(NGO)의 지구촌 협력", "지속가능발전목표(SDGs)와 세계 시민 의식"
    ]
}


def _try_generate_ai_quiz(grade_group: str, unit_name: str, question_type: str) -> Optional[Dict[str, Any]]:
    """
    AI 실시간 문제 생성 시도 함수 (연동 불가 또는 파싱/누설 실패 시 None 반환)
    """
    import random
    if not has_ai_service():
        return None

    target_type = question_type
    if target_type in ["basic_all", "random", "", None]:
        target_type = random.choice(["ox", "multiple_choice", "short_answer"])

    effective_unit = unit_name
    if not effective_unit or effective_unit == "전체 단원":
        grade_units = [u for u in UNIT_TOPIC_POOLS.keys() if (
            ("1~2" in grade_group and u in ["학교와 나", "계절과 우리 생활", "우리 마을과 사람들", "가족과 안전"]) or
            ("3~4" in grade_group and u in ["우리가 사는 곳", "일상에서 만나는 과거", "사회 변화와 다양한 문화", "옛날과 오늘날의 생활 모습", "지도로 만나는 우리 지역", "우리 지역의 문화유산", "경제활동과 지역 간 교류", "민주주의와 자치", "지역문제를 해결하고 지역을 알리는 노력", "다양한 환경과 삶의 모습"]) or
            ("5~6" in grade_group and u in ["우리나라 국토 여행", "우리나라 지리 탐구", "법과 인권의 보장", "유적과 유물로 살펴본 옛 사람들의 생활", "달라지는 시대, 변화하는 생활 모습", "식민 통치와 저항, 전쟁이 바꾼 사회와 생활", "평화 통일을 위한 노력, 민주화와 산업화", "민주주의와 시민 참여", "지구, 대륙 그리고 국가들", "세계의 자연환경", "시장경제와 국가 간 거래", "지구촌 사람들"])
        )]
        effective_unit = random.choice(grade_units) if grade_units else "우리가 사는 곳"

    topics = UNIT_TOPIC_POOLS.get(effective_unit)
    if not topics:
        for u_key, t_list in UNIT_TOPIC_POOLS.items():
            if effective_unit in u_key or u_key in effective_unit:
                topics = t_list
                effective_unit = u_key
                break
    if not topics:
        topics = [f"{effective_unit}의 핵심 개념과 주요 생활 모습"]

    sub_topic = random.choice(topics)
    curriculum_snippet = get_curriculum_context(grade_group, effective_unit)

    try:
        specialized_quiz = generate_specialized_quiz(
            question_type=target_type,
            grade_group=grade_group,
            unit_name=effective_unit,
            sub_topic=sub_topic,
            curriculum_snippet=curriculum_snippet,
            call_ai_fn=call_ai_text
        )
        if not specialized_quiz and len(topics) > 1:
            alt_sub_topic = random.choice([t for t in topics if t != sub_topic] or topics)
            specialized_quiz = generate_specialized_quiz(
                question_type=target_type,
                grade_group=grade_group,
                unit_name=effective_unit,
                sub_topic=alt_sub_topic,
                curriculum_snippet=curriculum_snippet,
                call_ai_fn=call_ai_text
            )

        if specialized_quiz:
            q_text = specialized_quiz.get("question", "")
            ans_text = specialized_quiz.get("answer", "")
            q_type = specialized_quiz.get("question_type", target_type)
            if not is_answer_leaked(q_text, ans_text, q_type):
                specialized_quiz["unit_name"] = effective_unit
                specialized_quiz["source_mode"] = "ai"
                specialized_quiz["is_review_mode"] = False
                return specialized_quiz
    except Exception as e:
        print("[AI 실시간 출제 알림]:", e)

    return None


# --------------------------------------------------------------------------
# 1. 문제 출제 API (AI ↔ 문제은행 양방향 자동 전환 및 3단계 폴백 완벽 지원)
# --------------------------------------------------------------------------
@router.post("/quiz/generate")
def generate_quiz(req: QuizGenerateRequest):
    clean_user = _clean_user_name(req.user_name)

    # ======================================================================
    # [Case A] 토글 OFF (문제은행 출제 모드: req.use_ai == False)
    # ======================================================================
    if not req.use_ai:
        bank_draw = draw_bank_question(
            grade_group=req.grade_group,
            unit_name=req.unit_name,
            question_type=req.question_type,
            user_id=req.user_id,
            user_name=clean_user,
            recent_ids=req.recent_ids,
        )
        # 1) 미풀이 은행 문제가 남아있는 경우 -> 정상 문제은행 출제
        if bank_draw["status"] == "unsolved" and bank_draw["quiz"]:
            quiz = bank_draw["quiz"]
            quiz["auto_switched_to_ai"] = False
            quiz["auto_switched_to_bank"] = False
            quiz["bank_stats"] = {
                "solved": bank_draw["solved_count"],
                "total": bank_draw["total_count"],
                "remaining": bank_draw["remaining_count"],
            }
            return quiz

        # 2) [정방향 폴백] 문제은행 DB가 비어있거나(0/0) 학생이 이미 다 풀어서 남은 미풀이 문제가 없는 경우
        # -> 자동으로 AI 기반 출제 토글을 활성화(ON)로 전환하고 AI 출제 시도!
        ai_quiz = _try_generate_ai_quiz(req.grade_group, req.unit_name, req.question_type)
        if ai_quiz:
            ai_quiz["auto_switched_to_ai"] = True
            ai_quiz["auto_switched_to_bank"] = False
            if bank_draw["status"] == "empty":
                ai_quiz["switch_message"] = "선택한 단원에 등록된 문제은행 문제가 없어(0/0) AI 기반 실시간 출제 모드(ON)로 자동 전환되었습니다."
            else:
                ai_quiz["switch_message"] = f"선택한 단원의 문제은행 문제를 모두 해결하여({bank_draw['solved_count']}/{bank_draw['total_count']}) AI 기반 실시간 출제 모드(ON)로 자동 전환되었습니다."
            return ai_quiz

        # 3) 만약 정방향 폴백으로 AI 출제를 시도했으나 AI도 연동되지 않는 경우 -> 역방향 2단계/3단계 적용
        if bank_draw["status"] == "exhausted" and bank_draw["quiz"]:
            # 2단계: 이미 풀었던 문제은행 문제 랜덤 복습 출제 (누적 포인트 미반영)
            review_quiz = bank_draw["quiz"]
            review_quiz["is_review_mode"] = True
            review_quiz["source_mode"] = "bank_review"
            review_quiz["auto_switched_to_bank"] = True
            review_quiz["review_notice"] = "AI 연결이 원활하지 않아 이미 해결한 문제은행 문제를 복습용으로 출제했습니다. (누적 포인트 미반영)"
            return review_quiz

        # 3단계: 문제은행도 0/0이고 AI도 연동 불가
        return {
            "error_empty": True,
            "source_mode": "error_empty",
            "error_message": "현재 AI 출제 서버와 연결할 수 없으며, 선택한 단원의 문제은행 DB에도 등록된 문제가 없습니다."
        }

    # ======================================================================
    # [Case B] 토글 ON (AI 기반 출제 모드: req.use_ai == True)
    # ======================================================================
    ai_quiz = _try_generate_ai_quiz(req.grade_group, req.unit_name, req.question_type)
    if ai_quiz:
        ai_quiz["auto_switched_to_ai"] = False
        ai_quiz["auto_switched_to_bank"] = False
        return ai_quiz

    # [역방향 폴백] AI 출제 연동 실패 시 -> 문제은행(question_bank.db) 3단계 자동 전환
    bank_draw = draw_bank_question(
        grade_group=req.grade_group,
        unit_name=req.unit_name,
        question_type=req.question_type,
        user_id=req.user_id,
        user_name=clean_user,
        recent_ids=req.recent_ids,
    )

    # 1단계 (미풀이 은행문제 존재 시): 자동으로 토글 OFF(문제은행 모드) 전환 + 미풀이 문제 출제 (정상 포인트 반영)
    if bank_draw["status"] == "unsolved" and bank_draw["quiz"]:
        quiz = bank_draw["quiz"]
        quiz["auto_switched_to_bank"] = True
        quiz["auto_switched_to_ai"] = False
        quiz["switch_message"] = "AI 출제 서버 연결이 원활하지 않아 문제은행 출제 모드(OFF)로 자동 전환하여 미풀이 문제를 출제했습니다."
        quiz["bank_stats"] = {
            "solved": bank_draw["solved_count"],
            "total": bank_draw["total_count"],
            "remaining": bank_draw["remaining_count"],
        }
        return quiz

    # 2단계 (해당 단원 은행 문제를 이미 다 풀었고 + AI도 연동 안 될 경우): 기풀이 은행문제 복습 출제 (포인트 미반영)
    if bank_draw["status"] == "exhausted" and bank_draw["quiz"]:
        review_quiz = bank_draw["quiz"]
        review_quiz["is_review_mode"] = True
        review_quiz["source_mode"] = "bank_review"
        review_quiz["auto_switched_to_bank"] = True
        review_quiz["auto_switched_to_ai"] = False
        review_quiz["review_notice"] = "AI 연결이 원활하지 않아 이미 해결한 문제은행 문제를 복습용으로 출제했습니다. (누적 포인트 미반영)"
        return review_quiz

    # 3단계 (해당 단원 문제은행 DB도 아예 비어 있고 0/0 + AI도 연동 안 될 경우): 명확한 에러 안내 반환
    return {
        "error_empty": True,
        "source_mode": "error_empty",
        "error_message": "현재 AI 출제 서버와 연결할 수 없으며, 선택한 단원의 문제은행 DB에도 등록된 문제가 없습니다."
    }


# --------------------------------------------------------------------------
# 2. 답안 채점 API (문제은행 주관식/서술형 AI 채점 + 복습 모드 중복 가산 방지)
# --------------------------------------------------------------------------
@router.post("/quiz/grade")
def grade_quiz(req: QuizGradeRequest):
    clean_user = _clean_user_name(req.user_name)

    # 문제은행의 원본 문제 정보에서 서술형 채점 키워드 및 해설 찾기
    keywords = []
    explanation_text = req.explanation or ""
    if req.question_id:
        for q in QUESTION_BANK:
            if q["id"] == req.question_id:
                keywords = q.get("grading_keywords", [])
                if not explanation_text:
                    explanation_text = q.get("explanation", "")
                break

    # [요구사항 3] AI 채점 함수(grade_bank_question_by_ai)를 통해
    # AI 출제 문제와 문제은행(question_bank.db) 수동 문제 모두 의미 동치(단답형) 및 부분 점수(서술형) AI 채점 수행
    result = grade_bank_question_by_ai(
        question_text=req.question,
        correct_answer=req.correct_answer,
        user_answer=req.user_answer,
        question_type=req.question_type,
        points=req.base_score,
        explanation=explanation_text,
        subject="social",
        call_ai_fn=call_ai_text if has_ai_service() else None,
        keywords=keywords,
    )

    raw_earned = int(result.get("score", 0))
    is_correct = bool(result.get("is_correct", False))

    # 문제은행 문제인 경우 정답 맞혔을 때 question_bank_solved에 즉시 기록
    bank_id = req.bank_id
    if not bank_id and req.question_id and str(req.question_id).startswith("bank_"):
        bank_id = str(req.question_id).replace("bank_", "", 1)

    if bank_id and is_correct:
        mark_bank_question_solved(
            bank_id=bank_id,
            subject="social",
            user_id=req.user_id,
            user_name=clean_user,
        )

    # [역방향 폴백 2단계 복습 모드 처리]: 이미 해결한 은행 문제를 복습용으로 푼 경우 누적 포인트 중복 반영 차단
    if req.is_review_mode:
        added_score = 0
        result["raw_score"] = raw_earned
        result["score"] = 0
        result["added_score"] = 0
        result["is_review_mode"] = True
        result["feedback"] = f"[복습 모드 · 누적 포인트 미반영] {result.get('feedback', '')}".strip()
    else:
        added_score = raw_earned
        result["added_score"] = added_score
        result["is_review_mode"] = False
        try_update_score(clean_user, added_score)

    # 통합 DB(quiz_logs.py)에 풀이 내역 저장 및 전과목 통합 누적 총점 자동 합산
    try:
        save_res = save_quiz_log(
            user_name=clean_user,
            user_id=req.user_id,
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
            earned_score=added_score,
            is_correct=is_correct,
        )
        result["log_id"] = save_res.get("log_id")
        result["user_id"] = save_res.get("user_id")
        result["total_score"] = save_res.get("total_score", 0)
        result["subject_score"] = save_res.get("subject_score", 0)
        user_st = get_user_status(clean_user, grade=req.grade, pokemon_type=req.pokemon_type, user_id=req.user_id)
        result["level_info"] = user_st.get("level_info")
    except Exception as e:
        print("save_quiz_log error:", e)
        result["log_id"] = None

    return result


# --------------------------------------------------------------------------
# 2-2. 문제은행 전용 통계 · 풀이 완료 마킹 · AI 채점 엔드포인트
# --------------------------------------------------------------------------
@router.get("/question-bank/unit-stats")
def social_unit_bank_stats_api(
    subject: str = "social",
    user_id: Optional[str] = None,
    user_name: Optional[str] = "김에듀",
    grade_group: Optional[str] = None,
):
    """단원별 (맞춘 문제 / 전체 은행문제) 통계 조회 API"""
    clean_user = _clean_user_name(user_name or "김에듀")
    return get_unit_bank_stats(subject="social", user_id=user_id, user_name=clean_user, grade_group=grade_group)


@router.post("/question-bank/mark-solved")
def social_mark_bank_solved_api(req: BankMarkSolvedRequest):
    """문제은행 문제 정답 시 풀이 완료(question_bank_solved) 기록 API"""
    clean_user = _clean_user_name(req.user_name or "김에듀")
    res = mark_bank_question_solved(
        bank_id=req.bank_id,
        subject="social",
        user_id=req.user_id,
        user_name=clean_user,
    )
    stats = get_unit_bank_stats(subject="social", user_id=req.user_id, user_name=clean_user)
    res["unit_stats"] = stats.get("units", {})
    return res


@router.post("/question-bank/grade")
def social_grade_bank_question_api(req: BankGradeRequest):
    """문제은행 수동 출제 주관식(단답형)·서술형 문제 AI 채점 API"""
    q_text = req.question_text or req.question or ""
    return grade_bank_question_by_ai(
        question_text=q_text,
        correct_answer=req.correct_answer,
        user_answer=req.user_answer,
        question_type=req.question_type,
        points=req.points,
        explanation=req.explanation,
        subject="social",
        call_ai_fn=call_ai_text if has_ai_service() else None,
    )


# --------------------------------------------------------------------------
# 3. 통합 DB 및 포켓몬 진화 등급 / AI 튜터 추가 질문 / 즐겨찾기 API
# --------------------------------------------------------------------------
@router.get("/user/status")
def get_user_status_api(user_name: str = "김에듀", grade: int = 4, pokemon_type: str = "grass", user_id: Optional[str] = None):
    """학생 상태 및 5대 포켓몬 진화 등급, 전과목 누적 총점 조회 (회원 고유 ID 분리 지원)"""
    clean_user = _clean_user_name(user_name)
    return get_or_create_user(user_name=clean_user, grade=grade, pokemon_type=pokemon_type, user_id=user_id)


@router.get("/user/weakest")
def get_user_weakest_api(user_name: str = "김에듀"):
    """학생의 취약 단원 및 주제 조회 (오답 기반)"""
    clean_user = _clean_user_name(user_name)
    return get_weakest_unit_and_topic(user_name=clean_user) or {}


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

[말투 및 표현 절대 원칙]
- '너희'라는 표현은 일절 쓰지 말고 '우리' 또는 '여러분'이라고 불러주세요.
- 초등학생 눈높이에 맞추어 아주 다정하고 정중한 존댓말(~해요, ~일까요?, ~해 볼까요?, ~입니다)로 2~3문장으로 설명해 주세요. 반말은 절대 금지합니다.
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
    clean_user = _clean_user_name(user_name)
    try:
        from core.database import update_user_score
        update_user_score(user_name=clean_user, score=score)
    except Exception:
        pass


# --------------------------------------------------------------------------
# [가이드라인 추가지시사항 1] 단독 실행용 FastAPI 인스턴스 (app) 및 루트 라우트
# --------------------------------------------------------------------------
app = FastAPI(title="EduMate AI 초등사회")
app.include_router(router)


# 단독 실행 시에도 공통 경로(/api/question-bank/...) 요청이 100% 작동하도록 호환 라우트 연결
@app.get("/api/question-bank/unit-stats")
def standalone_api_unit_stats(
    subject: str = "social",
    user_id: Optional[str] = None,
    user_name: Optional[str] = "김에듀",
    grade_group: Optional[str] = None,
):
    return social_unit_bank_stats_api(subject=subject, user_id=user_id, user_name=user_name, grade_group=grade_group)


@app.post("/api/question-bank/mark-solved")
def standalone_api_mark_solved(req: BankMarkSolvedRequest):
    return social_mark_bank_solved_api(req)


@app.post("/api/question-bank/grade")
def standalone_api_grade_bank(req: BankGradeRequest):
    return social_grade_bank_question_api(req)


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
