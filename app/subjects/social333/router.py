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
    from .quiz_engines import generate_specialized_quiz
except (ImportError, ValueError):
    try:
        from social.quiz_engines import generate_specialized_quiz
    except ImportError:
        from quiz_engines import generate_specialized_quiz


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

    # 2) [단원 일치 절대 보장] 단원별(unit_name) 맞춤형 세부 주제 풀 매핑
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

    # 선택된 단원 확인 및 세부 주제 추출
    effective_unit = req.unit_name
    if not effective_unit or effective_unit == "전체 단원":
        # 학년군에 속한 단원들 중 하나를 무작위 선택
        grade_units = [u for u in UNIT_TOPIC_POOLS.keys() if (
            ("1~2" in req.grade_group and u in ["학교와 나", "계절과 우리 생활", "우리 마을과 사람들", "가족과 안전"]) or
            ("3~4" in req.grade_group and u in ["우리가 사는 곳", "일상에서 만나는 과거", "사회 변화와 다양한 문화", "옛날과 오늘날의 생활 모습", "지도로 만나는 우리 지역", "우리 지역의 문화유산", "경제활동과 지역 간 교류", "민주주의와 자치", "지역문제를 해결하고 지역을 알리는 노력", "다양한 환경과 삶의 모습"]) or
            ("5~6" in req.grade_group and u in ["우리나라 국토 여행", "우리나라 지리 탐구", "법과 인권의 보장", "유적과 유물로 살펴본 옛 사람들의 생활", "달라지는 시대, 변화하는 생활 모습", "식민 통치와 저항, 전쟁이 바꾼 사회와 생활", "평화 통일을 위한 노력, 민주화와 산업화", "민주주의와 시민 참여", "지구, 대륙 그리고 국가들", "세계의 자연환경", "시장경제와 국가 간 거래", "지구촌 사람들"])
        )]
        effective_unit = random.choice(grade_units) if grade_units else "우리가 사는 곳"

    topics = UNIT_TOPIC_POOLS.get(effective_unit)
    if not topics:
        # 단원명 부분 일치 검색
        for u_key, t_list in UNIT_TOPIC_POOLS.items():
            if effective_unit in u_key or u_key in effective_unit:
                topics = t_list
                effective_unit = u_key
                break
    if not topics:
        topics = [f"{effective_unit}의 핵심 개념과 주요 생활 모습"]

    sub_topic = random.choice(topics)

    # 3) API 서비스가 있으면 유형별 독립 출제 엔진(quiz_engines.py)을 호출하여 실시간 최적화 출제!
    curriculum_snippet = get_curriculum_context(req.grade_group, effective_unit)
    try:
        specialized_quiz = generate_specialized_quiz(
            question_type=target_type,
            grade_group=req.grade_group,
            unit_name=effective_unit,
            sub_topic=sub_topic,
            curriculum_snippet=curriculum_snippet,
            call_ai_fn=call_ai_text
        )
        if specialized_quiz:
            specialized_quiz["unit_name"] = effective_unit
            return specialized_quiz
    except Exception as e:
        print("[유형별 엔진 호출 알림]:", e)

    return QuestionBankService.get_question(
        grade_group=req.grade_group,
        unit_name=req.unit_name if req.unit_name != "전체 단원" else effective_unit,
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

[채점 가이드 및 말투 원칙]
- '너희'라는 단어는 일절 쓰지 말고 '우리' 또는 '학생'을 사용하세요.
- 피드백(feedback)은 100% 다정하고 친절한 존댓말(~해요, ~일까요?, ~입니다)로 작성하세요. 반말 금지!
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
  "feedback": "초등학생 눈높이에 맞춘 다정하고 정중한 존댓말 1문장 피드백"
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

[말투 및 표현 절대 원칙]
- '너희'라는 단어는 일절 쓰지 말고 '우리' 또는 '여러분'을 사용하세요.
- 피드백(feedback)은 학생을 존중하고 격려하는 다정하고 정중한 존댓말(~해요, ~했네요, ~입니다)로 1~2문장 작성하세요. 반말 금지!

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
  "feedback": "초등학생 눈높이에 맞춘 다정하고 따뜻한 존댓말 1~2문장 원포인트 피드백"
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

    clean_user = _clean_user_name(req.user_name)
    try_update_score(clean_user, result["score"])

    # 통합 DB(quiz_logs.py)에 풀이 내역 저장 및 전과목 통합 누적 총점 자동 합산
    try:
        earned_score = int(result.get("score", 0))
        save_res = save_quiz_log(
            user_name=clean_user,
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
        user_st = get_user_status(clean_user, grade=req.grade, pokemon_type=req.pokemon_type)
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
    clean_user = _clean_user_name(user_name)
    return get_or_create_user(user_name=clean_user, grade=grade, pokemon_type=pokemon_type)


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
