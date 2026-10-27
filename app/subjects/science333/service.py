"""
EduMate AI - 초등 과학 전담 AI 출제 및 채점 엔진 서비스 모듈 (통합 완성본)
- 지원 모드: ⭕❌ OX 퀴즈, 📝 5지선다 객관식, ✍️ 서술형 퀴즈 및 AI 일괄 문맥 채점
- 표준 기술 스택: Google GenAI SDK (gemini-3.5-flash-lite, api_version: "v1"), Pydantic v2
- 2022 개정 초등 1~6학년 전 단원 순수 자연과학 중심 출제 및 5단계 부분 점수 루브릭
"""

import os
import json
import random
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# ==========================================
# 1. .env 파일 안전 로드 (guideline.txt 261008 표준: .env -> 상위 .env -> 시스템 환경변수)
# ==========================================
current_dir = Path(__file__).resolve().parent

def find_and_load_api_key() -> str:
    """
    1) 현재 과목 폴더의 .env 확인
    2) 상위 부모 폴더(프로젝트 루트) 순차 탐색
    3) OS 시스템 환경변수(os.environ) 확인
    """
    if (current_dir / ".env").exists():
        load_dotenv(dotenv_path=current_dir / ".env", override=True)
    else:
        for folder in current_dir.parents:
            env_file = folder / ".env"
            if env_file.exists():
                load_dotenv(dotenv_path=env_file, override=True)
                break
        else:
            load_dotenv(override=True)

    key = os.getenv("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    return key.strip()

api_key = find_and_load_api_key()

# ==========================================
# 2. 결과 저장용 saved_results 폴더 경로 (edumate.db 통합으로 자동 생성 비활성화)
# ==========================================
RESULTS_DIR = current_dir / "saved_results"

# ==========================================
# 3. 최신 Google GenAI SDK v1 클라이언트 생성 & 단일 모델 설정
# ==========================================
# 가이드라인 절대 원칙: 하위 버전 불가, 무조건 gemini-3.5-flash-lite 단일 모델만 사용
MODEL_NAME = "gemini-3.5-flash-lite"

client = None
if api_key:
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})


def ensure_client():
    """클라이언트 연결 확인 및 지연 초기화"""
    global client
    key = find_and_load_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다. .env 파일이나 시스템 환경변수를 확인하세요.")
    if client is None:
        client = genai.Client(api_key=key, http_options={"api_version": "v1"})
    return client


def call_gemini(cli: genai.Client, contents: Any, config: Any = None) -> Any:
    """가이드라인 원칙: 하위 모델 배제, 오직 gemini-3.5-flash-lite 단일 모델만 호출"""
    if config:
        return cli.models.generate_content(model=MODEL_NAME, contents=contents, config=config)
    return cli.models.generate_content(model=MODEL_NAME, contents=contents)


# 기존 호출부 100% 호환용 단일 모델 호출 래퍼
call_gemini_with_fallback = call_gemini


# ==========================================
# 4. Pydantic v2 DTO 스키마 정의
# ==========================================

# [OX 및 5지선다 스키마]
class QuizItem(BaseModel):
    id: int = Field(description="문제 번호 (1~10)")
    grade: int = Field(description="초등학교 학년 (1~6)")
    unit: str = Field(description="단원명")
    question: str = Field(description="초등학생 눈높이 질문 문장")
    options: Optional[List[str]] = Field(default=None, description="5지선다 보기 배열 (객관식인 경우)")
    answer: Union[str, int] = Field(description="정답 ('O'/'X' 또는 1~5 정수)")
    explanation: str = Field(description="친절한 원포인트 과학 해설")
    type: str = Field(default="ox", description="문제 유형 ('ox' 또는 'mcq')")


class QuizRequest(BaseModel):
    grade: int = Field(default=3, ge=1, le=6, description="학년 (1~6)")
    unit: str = Field(default="총정리", description="단원명")
    mode: str = Field(default="ox", description="문제 모드 ('ox' 또는 'mcq')")


# [서술형 퀴즈 및 채점 스키마]
class SubjectiveQuizItem(BaseModel):
    id: int = Field(description="문제 번호 (1~10)")
    question: str = Field(description="초등학생 발달 수준에 맞춘 구체적이고 명확한 순수 과학 서술형 질문 문장")
    model_answer: str = Field(description="초등학교 교과서 수준의 바르고 다정한 모범 정답")
    keywords: List[str] = Field(description="초등학생 수준의 핵심 과학 단어 2~3개")
    guide: str = Field(description="학생이 과학 원리를 떠올릴 수 있도록 돕는 다정한 생각 힌트 1문장")


class SubjectiveQuizSet(BaseModel):
    items: List[SubjectiveQuizItem] = Field(description="10개의 서술형 퀴즈 문항 목록")


class SingleEvaluationResult(BaseModel):
    id: int = Field(description="문제 번호")
    is_correct: bool = Field(description="정답 인정 여부 (3점 이상 True)")
    score: int = Field(description="부여된 최종 점수 (0~5점 정수)")
    grade_label: str = Field(description="판정 라벨 ('정답 (만점 5점)', '부분 정답 (3~4점)', '노력 요함 (1~2점)', '오답 (0점)')")
    analysis: str = Field(description="AI 채점 분석 근거 (CoT: 학생의 표현과 과학 원리 일치 여부 분석)")
    feedback: str = Field(description="초등학생 눈높이에 맞춘 다정하고 명확한 1~2문장의 격려 피드백")


class BatchEvaluationResponse(BaseModel):
    total_score: int = Field(description="10문제 총점 (50점 만점)")
    average_score: float = Field(description="평균 점수")
    results: List[SingleEvaluationResult] = Field(description="10문제 각각의 채점 결과 목록")


class QuizGenerateRequest(BaseModel):
    grade: int = Field(default=1, ge=1, le=6, description="학년 (1~6)")
    unit: str = Field(default="총정리", description="단원명")
    count: int = Field(default=10, description="문항 수")


class SingleAnswerSubmit(BaseModel):
    id: int = Field(description="문제 번호 (1~10)")
    question: str = Field(..., description="문제 내용")
    model_answer: str = Field(..., description="모범 정답")
    student_answer: str = Field(..., description="학생 답안")


class BatchEvaluationRequest(BaseModel):
    grade: int = Field(default=1, ge=1, le=6, description="학년 (1~6)")
    unit: str = Field(default="총정리", description="단원명")
    answers: List[SingleAnswerSubmit] = Field(..., description="10문제의 학생 답안 목록")


# ==========================================
# 5. 2022 개정 초등 1~6학년 과학 단원 목차 데이터
# ==========================================
GRADE_UNITS = {
    1: {
        "총정리": "초등 1학년 자연탐구(오감 사물 관찰, 사계절 날씨와 계절 변화, 주변 동식물 겉모습 관찰, 낮과 밤의 해와 달과 그림자)",
        "입학": "다섯 가지 감각 기관(눈으로 보기, 코로 냄새 맡기, 귀로 소리 듣기, 입으로 맛보기, 손으로 만지기)을 활용한 사물과 주변 자연의 과학적 관찰 (생명/감각)",
        "봄": "따스해진 봄 날씨와 기온 변화, 파릇파릇 돋아나는 새싹 관찰, 개나리·진달래 꽃의 생김새, 겨울잠에서 깨어난 개구리와 곤충 (생명/지구)",
        "가족": "우리의 감각 기관(눈, 코, 귀, 피부)의 기능과 주변 동물(강아지, 고양이, 참새)의 겉모습 관찰 (생명)",
        "여름": "더운 여름 날씨와 강한 햇빛, 여름 곤충(매미, 잠자리)의 생김새, 비 오는 날과 물웅덩이 관찰 (생명/지구)",
        "하루": "낮과 밤의 하늘 모습 변화, 낮에 비치는 태양의 빛과 그림자 놀이, 밤하늘의 달과 별 관찰 (천문/물리)",
        "가을": "선선해진 가을 날씨, 울긋불긋 나뭇잎의 단풍과 낙엽 관찰, 도토리와 밤 등 열매와 씨앗 관찰 (생명/지구)",
        "나라": "우리나라 사계절(봄·여름·가을·겨울)의 뚜렷한 날씨 변화와 계절별 자연 모습 (지구)",
        "겨울": "추운 겨울 날씨와 찬 바람, 물이 얼어 생기는 눈과 얼음의 성질, 동물들의 겨울나기(겨울잠) (물질/생명)"
    },
    2: {
        "총정리": "초등 2학년 자연탐구(나의 신체 성장과 변화, 올챙이와 나비의 한살이, 곤충 몸의 생김새, 주변 물건을 이루는 재료의 느낌과 쓰임새, 따뜻한 곳에서 얼음이 녹는 현상)",
        "나": "나의 신체 성장(키와 몸무게가 쑥쑥 자람), 젖니가 빠지고 튼튼한 간니(영구치)가 나는 신체 변화 (생명)",
        "봄": "봄철 꿀벌과 나비의 날갯짓과 꽃가루받이, 민들레 씨앗의 갓털과 바람 비행, 봄꽃과 새싹 관찰 (생명)",
        "마을": "우리 주변 사물을 이루는 재료(나무, 쇠/철, 플라스틱, 유리, 고무)의 촉감과 특징(나무는 단단하고 딱딱함, 쇠는 차갑고 무거움, 고무는 팽팽하고 늘어남) (물질/감각)",
        "여름": "여름 곤충(사마귀, 방아깨비, 매미)의 몸 생김새(머리, 가슴, 배, 다리 6개), 장마철 천둥과 번개 (생명/지구)",
        "일": "자연의 힘(햇빛, 바람)을 이용하는 우리 생활(햇빛과 바람으로 바닷물이 말라 소금이 남는 현상) (자연/물리)",
        "가을": "가을철 나뭇잎이 떨어지는 까닭, 다람쥐의 도토리 모으기, 풀벌레(귀뚜라미) 울음소리 (생명/지구)",
        "세상": "사막의 선인장 줄기, 추운 극지방 북극곰의 따뜻한 털 등 사는 곳에 적응한 생물의 특징 (생명/지구)",
        "겨울": "추운 겨울에 물이 얼어 얼음이 되고, 따뜻한 방에 두면 얼음이 녹아 다시 물이 되는 직관적 현상 관찰 (물질/자연)"
    },
    3: {
        "총정리": "초등 3학년 과학 1·2학기 전체(힘과 우리 생활, 자석의 이용, 물질의 성질, 동물의 한살이, 동물의 생활, 소리의 성질, 지구와 달, 물의 여행)",
        "힘과 우리 생활": "물체에 힘을 줄 때 모양과 움직임의 변화, 중력과 탄성력",
        "자석의 이용": "자석의 극(N극, S극), 끌어당김과 밀어냄, 나침반의 원리, 일상 속 자석",
        "물질의 성질": "금속, 나무, 플라스틱, 고무, 유리의 고유한 성질과 물체의 쓰임새",
        "동물의 한살이": "배추흰나비의 한살이(알-애벌레-번데기-어른벌레), 알과 새끼를 낳는 동물",
        "동물의 생활": "땅, 물, 하늘, 사막 등 다양한 환경에 적응해 사는 동물의 특징",
        "소리의 성질": "물체의 떨림(진동), 소리의 세기와 높낮이, 기체·액체·고체를 통한 소리 전달",
        "지구와 달": "둥근 지구의 모습, 바다와 육지, 공기의 역할, 달 표면의 충돌 구덩이",
        "물의 여행": "모양과 부피에 따른 고체·액체·기체, 물의 세 가지 상태 변화와 순환"
    },
    4: {
        "총정리": "초등 4학년 과학 1·2학기 전체(식물의 생활, 지층과 화석, 물의 상태 변화, 기후변화, 식물의 한살이, 빛과 그림자, 화산과 지진, 물체의 무게)",
        "식물의 생활": "사는 곳에 따른 식물의 생김새(물에 뜨는 식물, 사막 선인장 등)",
        "지층과 화석": "퇴적물이 쌓여 생긴 지층의 줄무늬, 고생물 화석의 형성과 가치",
        "물의 상태 변화": "물의 증발과 끓음, 수증기의 응결, 물이 얼 때의 부피 변화",
        "기후변화와 우리 생활": "지구 온난화와 극지방 빙하 감소, 온실가스 줄이기 실천",
        "식물의 한살이": "강낭콩 씨앗의 싹틈 조건, 잎과 줄기의 자람, 꽃과 열매, 씨앗 맺기",
        "빛과 그림자": "빛의 직진, 그림자가 생기는 원리와 크기 변화, 거울의 빛 반사",
        "화산과 지진": "마그마와 화산 분출물, 현무암과 화강암, 지진 피해와 안전 대피 요령",
        "물체의 무게": "지구 중력과 무게, 용수철저울의 원리, 수평 잡기"
    },
    5: {
        "총정리": "초등 5학년 과학 1·2학기 전체(여러 가지 기체, 태양계와 별, 용해와 용액, 생물과 환경, 날씨, 물체의 운동, 산과 염기, 우리 몸)",
        "여러 가지 기체": "산소의 조연성과 호흡, 이산화 탄소와 석회수 반응, 소화기",
        "태양계와 별": "태양과 8개 행성, 계절별 별자리, 북극성을 이용한 방위 찾기",
        "용해와 용액": "소금의 용해와 용액의 무게 보존, 온도에 따른 용해도, 용액의 진하기",
        "생물과 환경": "생물 요소와 비생물 요소, 생산자·소비자·분해자, 먹이 그물과 생태계 평형",
        "날씨와 우리 생활": "이슬·서리·안개·구름의 생성, 기압과 바람의 이동, 계절별 기단",
        "물체의 운동": "물체의 위치 변화, 속력의 개념과 계산(이동 거리÷걸린 시간), 단위(m/s, km/h)",
        "산과 염기": "리트머스 종이와 붉은 양배추 지시약 색 변화, 산성과 염기성의 중화 반응",
        "우리 몸의 구조와 기능": "소화계, 순환계(심장과 혈관), 호흡계(폐), 배설계(신장), 신경계와 감각 기관"
    },
    6: {
        "총정리": "초등 6학년 과학 1·2학기 전체(지구와 달의 운동, 식물의 구조와 기능, 빛과 렌즈, 전기의 이용, 계절의 변화, 물질의 연소와 소화, 에너지, 과학 진로)",
        "지구와 달의 운동": "지구의 자전과 낮과 밤, 지구의 공전과 별자리 변화, 달의 위상 변화",
        "식물의 구조와 기능": "뿌리의 흡수, 줄기의 물관·체관, 잎의 기공과 증산 작용, 엽록체의 광합성",
        "빛과 렌즈": "빛의 굴절 현상, 볼록렌즈의 상과 빛 모으기, 간이 사진기",
        "전기의 이용": "전기 회로, 전류 주위의 자기장, 전자석의 성질과 극 바꾸기",
        "계절의 변화": "태양의 남중 고도와 낮의 길이, 지구 자전축 경사와 공전에 따른 사계절",
        "물질의 연소와 소화": "연소의 3요소(탈 물질, 산소, 발화점 이상 온도), 소화의 원리",
        "에너지와 생활": "다양한 형태의 에너지, 에너지 전환 과정, 에너지 절약",
        "과학과 나의 진로": "첨단 과학 기술(AI, 우주, 바이오), 미래 사회와 과학 관련 직업 탐색"
    }
}


def get_unit_description(grade: int, unit: str) -> str:
    """단원 설명 반환"""
    grade_info = GRADE_UNITS.get(grade, GRADE_UNITS[3])
    return grade_info.get(unit, unit)


# ==========================================
# 6. OX 퀴즈 실시간 출제 함수 (10문제)
# ==========================================
def generate_ox_quiz(grade: int = 3, unit: str = "총정리") -> list:
    """초등 과학 OX 퀴즈 실시간 생성 (10문제)"""
    cli = ensure_client()
    desc = get_unit_description(grade, unit)
    random_seed = random.randint(1000, 999999)

    prompt = f"""당신은 대한민국 초등학교 과학 교과서를 집필한 베테랑 수석 과학 선생님입니다.
초등학교 {grade}학년 과학 [단원: {unit}] ({desc})을 주제로,
초등학교 {grade}학년 학생들의 눈높이에 맞춘 고품질 OX 퀴즈 정확히 10문제를 출제해 주세요.

[출제 원칙 및 정답-해설 일치 교차 검증 - 절대 엄수]
1. 💡 [사고 과정(Chain of Thought) 및 해설 우선 생성 원칙]:
   - 먼저 explanation(해설)에 해당 문제 문장이 과학적으로 왜 맞는지, 혹은 왜 틀렸고 올바른 사실은 무엇인지를 1~2문장으로 명확히 서술하세요.
   - 그런 다음 방금 작성한 explanation에 근거하여 answer("O" 또는 "X")를 확정하세요.
   - 문제 문장이 참인 경우 -> explanation: 맞다는 이유 설명 -> answer: "O"
   - 문제 문장이 거짓인 경우 -> explanation: 틀린 이유 및 올바른 설명 -> answer: "X"
2. 🚫 [복합 함정 문장 및 말장난 절대 금지]: 초등 {grade}학년 어린이가 한눈에 이해할 수 있는 간결한 단문으로만 작성하세요.
3. 🎒 [초등 {grade}학년 눈높이 어휘 및 난이도 엄수]: 교과서 수준의 쉬운 어휘만 사용하세요.
4. ⚖️ [O/X 균형 비율]: 정답 O와 X의 비율이 4~6개 수준으로 균형을 맞춰주세요.
5. 난수 시드({random_seed})를 반영하여 매번 완전히 새로운 문제를 출제하세요.

반드시 다음 JSON 형식(정확히 10개의 객체 배열)으로만 응답해 주세요:
[
  {{
    "id": 1,
    "grade": {grade},
    "unit": "{unit}",
    "question": "초등학생 눈높이의 명확한 OX 문제 문장",
    "explanation": "이 문제 문장이 왜 맞는지 또는 왜 틀렸는지 올바른 과학적 원리 해설",
    "answer": "위 explanation에 근거한 정확한 정답 (O 또는 X)",
    "type": "ox"
  }}
]
"""
    response = call_gemini_with_fallback(
        cli,
        prompt
    )
    raw_text = response.text.strip()
    cleaned_json = raw_text.replace("```json", "").replace("```", "").strip()
    data = json.loads(cleaned_json)
    for idx, item in enumerate(data):
        item["id"] = idx + 1
        item["grade"] = grade
        item["unit"] = unit
        item["type"] = "ox"
    return data


# ==========================================
# 7. 5지선다 객관식 퀴즈 실시간 출제 함수 (10문제)
# ==========================================
def generate_mcq_quiz(grade: int = 3, unit: str = "총정리") -> list:
    """초등 과학 5지선다 객관식 퀴즈 실시간 생성 (10문제)"""
    cli = ensure_client()
    desc = get_unit_description(grade, unit)
    random_seed = random.randint(1000, 999999)

    prompt = f"""당신은 대한민국 초등학교 과학 교과서를 집필한 베테랑 수석 과학 선생님입니다.
초등학교 {grade}학년 과학 [단원: {unit}] ({desc})을 주제로,
초등학교 {grade}학년 학생들의 눈높이에 맞춘 고품질 5지선다 객관식 퀴즈 정확히 10문제를 출제해 주세요.

[출제 원칙 및 정답-해설 일치 교차 검증 - 절대 엄수]
1. 💡 [사고 과정(Chain of Thought) 및 해설 우선 생성 원칙]:
   - 먼저 질문(question)과 5개의 보기(options)를 구상하세요.
   - 그런 다음 explanation(해설)을 먼저 작성하여 정답 보기가 왜 정답인지, 다른 오답 보기는 왜 틀렸는지를 초등학생 눈높이에서 1~2문장으로 친절하게 설명하세요.
   - 방금 작성한 explanation에 근거하여 최종 정답 번호 answer(1, 2, 3, 4, 5 중 하나인 정수)를 결정하세요.
   - 해설의 내용과 정답 번호(answer)가 불일치하는 모순은 절대 금지합니다.
2. 🎯 [선택지(options) 구성 원칙]:
   - 반드시 5지선다 객관식이어야 하며, options 배열에 정확히 5개의 보기 문자열을 포함해야 합니다.
   - 1개의 명확한 정답과 4개의 매력적인 오답으로 구성하세요.
   - options 배열의 인덱스는 1번부터 5번까지 차례대로 대응합니다 (첫 번째 보기 = 1, 다섯 번째 보기 = 5).
3. ⚖️ [정답 번호 분산 배치]: 10문제 전체의 정답 번호(answer: 1~5)가 골고루 분배되도록 배치하세요.
4. 🎒 [초등 {grade}학년 눈높이 어휘 엄수]: 교과서 수준의 쉬운 어휘만 사용하세요.
5. 난수 시드({random_seed})를 반영하여 매번 완전히 새로운 문제를 출제하세요.

반드시 다음 JSON 형식(정확히 10개의 객체 배열)으로만 응답해 주세요:
[
  {{
    "id": 1,
    "grade": {grade},
    "unit": "{unit}",
    "question": "다음 중 자석에 붙는 물체는 무엇일까요?",
    "options": ["나무 젓가락", "철 클립", "유리컵", "플라스틱 자", "종이컵"],
    "explanation": "철 클립은 철로 만들어져 자석에 잘 붙지만, 나무, 유리, 플라스틱, 종이는 자석에 붙지 않습니다.",
    "answer": 2,
    "type": "mcq"
  }}
]
"""
    response = call_gemini_with_fallback(
        cli,
        prompt
    )
    raw_text = response.text.strip()
    cleaned_json = raw_text.replace("```json", "").replace("```", "").strip()
    data = json.loads(cleaned_json)
    for idx, item in enumerate(data):
        item["id"] = idx + 1
        item["grade"] = grade
        item["unit"] = unit
        item["type"] = "mcq"
        item["answer"] = int(item["answer"])
    return data


# ==========================================
# 8. 서술형 퀴즈 실시간 출제 함수 (10문제)
# ==========================================
def generate_subjective_quiz(grade: int = 1, unit: str = "총정리", count: int = 10) -> dict:
    """초등 과학 서술형 퀴즈 실시간 생성 (10문제)"""
    cli = ensure_client()
    desc = get_unit_description(grade, unit)

    prompt = f"""당신은 2022 개정 초등학교 과학 교육과정 전담 출제 전문가이자 교과서 집필자입니다.
초등학교 {grade}학년 학생의 발달 단계에 완벽히 부합하는 '순수 과학 서술형 퀴즈 {count}문항'을 출제해 주세요.

[출제 대상 정보]
- 학년: 초등학교 {grade}학년
- 단원: {unit}
- 단원 핵심 과학 개념: {desc}

[필수 품질 및 학년별 발달 수준 엄수 규칙 - 100% 준수]
1. [학년별 인지 발달 및 어휘 수준 엄수]:
   - 1학년: 오감(눈, 코, 귀, 입, 손)을 통한 사물 관찰, 사계절 날씨 변화와 옷차림, 주변 동식물 겉모습, 낮과 밤의 해와 달과 그림자. (전문 용어 일절 배제, 직관적이고 친근한 관찰 표현 사용)
   - 2학년: 나의 신체 성장(키, 젖니와 간니), 올챙이-개구리/나비의 한살이, 곤충 몸의 생김새(머리, 가슴, 배, 다리 6개), 물건 재료의 촉감과 특징(나무는 단단함/딱딱함, 쇠는 차갑고 무거움, 고무는 늘어남), 얼음이 녹아 물이 되는 직관적 현상.
     * 3~4학년 이상 전문 용어('상태 변화', '고체/액체/기체' 등) 출제 절대 금지!
     * 2학년 생태계/환경('세상' 단원 등) 출제 시 3~4학년의 깊은 '환경 적응 원리(바람에 꺾이지 않는 줄기 형태, 발굽 바닥 성질 등)' 출제 절대 금지! 오직 아이 눈높이의 직관적 겉모습 관찰(따뜻한 남쪽 나라에는 야자나무가 살고 잎이 넓다/열매가 열린다, 북극곰은 털이 하얗다 등)만 다룰 것!
   - 3학년: 힘과 모양/움직임 변화, 자석의 극(N극, S극)과 끌어당김/밀어냄, 물질의 성질(금속, 나무, 플라스틱의 단단함·가벼움), 배추흰나비 한살이, 소리의 떨림(진동)과 높낮이, 지구와 달의 겉모습, 물의 상태 기초.
   - 4학년: 물의 상태 변화(증발, 끓음, 수증기 응결, 얼 때 부피 늘어남), 지층의 줄무늬와 화석, 빛의 직진과 그림자 크기, 화산과 지진, 물체의 무게와 용수철저울.
   - 5학년: 산소와 이산화 탄소 기체, 태양계 행성과 별자리, 용해와 용액, 생태계(생산자, 소비자, 분해자), 이슬·안개·구름, 물체의 운동(속력), 산과 염기, 우리 몸 구조.
   - 6학년: 지구 자전과 공전, 식물의 증산 작용과 광합성, 빛의 굴절과 볼록렌즈, 전기 회로와 전자석, 연소와 소화, 에너지 전환.

2. [질문과 모범 정답의 범위 정확한 일치]:
   - 질문에서 '옷'만 물었으면 모범 정답도 옷에 집중해야 하며, 질문에 없는 다른 방한용품(목도리, 장갑 등)을 모범 정답에 슬그머니 끼워 넣지 마세요.
   - 문제 지문에 이미 주어진 전제 조건(예: '알록달록 물든 나뭇잎들이 시간이 지나면서 어떻게 변하나요?')이 있다면, 모범 정답은 그 다음 일어나는 변화(예: '바닥으로 떨어집니다 / 낙엽이 됩니다')에 집중해야 하며, 지문에 이미 있는 전제(색 변화)를 모범 정답의 필수 채점 요소로 중복 포함하지 마세요.
   - '성질이나 특징(느낌)'을 물었으면 모범 정답도 성질이나 특징이어야 합니다.
   - '물질이나 물체의 이름'을 물었으면 모범 정답도 물질 이름이어야 합니다.

3. [문제 내 정답 단어 자가 유출(스포일러) 절대 금지]:
   - 질문 문장 안에서 학생에게 물어보는 정답 단어를 스스로 말하지 마세요.

4. [초등 교과서 어휘 원칙]:
   - '인력', '척력', '항성' 같은 중고등 한자어를 쓰지 말고 초등 교과서 표현('끌어당김', '서로 밀어냄', '스스로 빛을 내는 별')을 사용하세요.

5. [국립국어원 표준 맞춤법 및 오타 생성 절대 금지]:
   - 질문 지문 작성 시 반드시 국립국어원 표준 맞춤법과 초등 교과서 공식 어휘를 100% 준수하세요.
   - '구파를 파고'(X) -> '굴을 파고'(O) 처럼 실시간 생성 과정에서 어휘가 왜곡되거나 엉뚱한 오타가 절대 섞이지 않도록 엄격하게 자가 검수하세요.

반드시 지정된 JSON 스키마 규격으로 응답하세요."""

    response = call_gemini_with_fallback(
        cli,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SubjectiveQuizSet,
            temperature=0.6,
        ),
    )

    data = json.loads(response.text)
    items = data.get("items", [])
    for idx, item in enumerate(items, 1):
        item["id"] = idx

    return {
        "grade": grade,
        "unit": unit,
        "count": len(items),
        "items": items
    }


# ==========================================
# 9. 10문제 일괄 서술형 문맥 채점 및 아카이빙
# ==========================================
def evaluate_batch_subjective_quizzes(
    grade: int,
    unit: str,
    answers_data: List[Dict[str, Any]]
) -> dict:
    """학생이 10문제를 모두 풀고 제출한 답안들을 일괄 문맥 채점하고 saved_results/에 자동 보관합니다."""
    cli = ensure_client()

    qa_list_text = ""
    for idx, item in enumerate(answers_data, 1):
        qa_list_text += f"""
[문제 {idx}] (ID: {item.get('id', idx)})
- 문제: {item.get('question')}
- 모범 정답: {item.get('model_answer')}
- 학생 답안: "{item.get('student_answer', '').strip()}"
"""

    prompt = f"""당신은 초등학교 과학 교육 전문가이자 아이들의 마음을 헤아리는 공정하고 다정한 AI 채점관입니다.
초등학교 {grade}학년 학생이 제출한 서술형 10문항의 답안을 교육적인 눈높이로 일괄 채점해 주세요.

[단원 정보]
- 학년: 초등학교 {grade}학년
- 단원: {unit}

[제출된 10문항 답안 목록]
{qa_list_text}

[채점 가이드라인 및 절대 준수 루브릭 - 100% 엄수]

🚨 [절대 원칙 1: 질문에서 요구하지 않은 부가 요소/추가 방한용품 누락에 대한 감점 엄격 금지]
- 질문이 "어떤 옷을 입어야 하나요?"라고 물었을 때, 학생이 "패딩", "두꺼운 옷", "잠바"처럼 질문에 부합하는 옷을 썼다면 **무조건 5점 만점**을 부여하세요!
- 모범 정답에 '목도리, 장갑' 같은 다른 방한용품이 적혀 있더라도, 질문에서 "다른 방한용품도 함께 쓰라"고 요구하지 않았으므로 "다른 방한용품에 대한 설명이 빠져 있다"는 이유로 감점하는 것은 심각한 채점 오류이며 절대 금지합니다!
- 질문에서 "2가지 이상 쓰라"고 명시하지 않은 한, 질문의 대상을 충족하는 대표 정답 하나만 제시해도 5점 만점입니다.

🚨 [절대 원칙 2: 단답형·단어 나열·어구 형태 감점 절대 금지 (문장 형식 강요 금지)]
- 질문에서 "완전한 문장 형태로 쓰시오"라고 명시하지 않은 한, "반팔 티셔츠, 얼음", "패딩", "떨어져요" 처럼 단어, 어구, 쉼표 나열 형태로 작성했더라도 질문이 요구한 핵심 과학적 요소(예: 옷과 음식 모두 언급)를 담고 있다면 **무조건 5점 만점**을 부여하세요!
- "전체 문장 형태로 완성되지 않아 살짝 아쉽습니다", "서술형 문장이 아닙니다" 따위의 국어 작문 식 트집으로 1점이라도 감점하는 행위를 절대 금지합니다! (초등 과학 평가는 과학적 이해도를 측정하는 것이지 국어 작문 시험이 아닙니다!)

🚨 [절대 원칙 3: 문제 지문에 이미 주어진 전제 조건의 답안 내 재서술 강요 금지]
- 문제 지문에서 이미 명시된 전제 조건(예: "알록달록 예쁘게 물든 나뭇잎들이 시간이 지나면서 어떻게 변하나요?")에 대해, 학생이 그 다음 일어나는 변화인 "떨어져요", "바닥에 떨어집니다", "낙엽이 돼요"라고 정확히 답했다면 **무조건 5점 만점**을 부여하세요!
- 문제에서 이미 '물든 나뭇잎'이라고 전제했으므로 학생이 '색이 변하는 과정'을 다시 쓸 필요가 전혀 없습니다. "색이 변하는 과정에 대한 설명이 생략되었습니다"라는 억지 판정으로 감점하는 것을 엄격히 금지합니다!

🚨 [절대 원칙 4: 초등학생의 일상어·관찰어·쉬운 표현 무조건 만점(5점) 인정]
- 아이들이 "딱딱해요", "단단해요", "녹아요", "차가워져요", "달라붙어요", "밀어내요", "떨어져요", "키가 커져요", "이가 빠져요" 처럼 일상 언어로 관찰 결과를 바르게 서술했다면 전문 용어가 없다는 이유로 감점하지 말고 **무조건 5점 만점**을 부여하세요!

🚨 [절대 원칙 5: 과학적 인과관계가 없는 엉뚱한 오답의 자의적 소설/합리화 엄격 금지 (과잉 관대화 차단)]
- 단어 형태 답안은 폭넓게 인정하되, 반드시 그 단어가 질문에서 묻는 [과학적 핵심 원인 및 자연 현상]과 올바르게 부합해야 합니다!
- 질문과 전혀 상관없는 엉뚱한 오답(예: 야자나무가 거센 바람에 꺾이지 않는 줄기의 특징을 물었는데 "겹겹이"라고 쓴 경우)에 대해, AI 채점관이 "유추하여 표현한 것으로 인정된다"라며 멋대로 소설을 쓰고 합리화하여 5점 만점을 주는 행위는 치명적인 오심이자 채점 오류입니다!
- 질문의 과학적 핵심 사실(길고 유연함, 탄력성, 질김 등)과 빗나간 엉뚱한 답변은 단호하게 오답(0점 또는 1점)으로 판정하세요!

🚨 [절대 원칙 6: 3~4점 부분 점수 엄격 제한]
- 3~4점 부분 점수는 "학생 답안에 과학적 오류가 실제로 섞여 있거나, 두 가지를 물었는데 한 가지만 답했을 때(예: 옷과 음식을 물었는데 옷만 쓰고 음식은 빠뜨린 경우)"에만 부여합니다.
- 질문에 충실히 답했으나 단어만 썼거나, 묻지도 않은 부가 예시가 없거나, 문장이 짧다는 이유로 3~4점으로 깎지 마세요.

5. [사고 과정 선행(CoT analysis)]:
   - 각 문제마다 analysis(채점 분석 근거)를 먼저 작성하세요.
   - 이때 반드시 다음 4단계를 스스로 검증하세요:
     1) [문제]에서 실제로 물어본 과학적 사실과 핵심 요구는 무엇인가?
     2) [학생 답안]이 그 질문의 과학적 인과관계에 실제로 부합하는가? (엉뚱한 단어인데 AI 혼자 소설 써서 합리화하지 않았는가?)
     3) 질문에서 묻지도 않은 부가 요소를 강요하거나, 문장 형태를 트집 잡아 억울하게 감점하고 있지는 않은가?
     4) 학생이 쓴 답이 과학적 정답인가, 아니면 질문과 무관한 오답인가를 냉정하고 공정하게 판정했는가?
   - 모범 정답과 글자가 다르다는 이유로 꼬투리를 잡지 마세요!

6. [다정한 피드백]:
   - 초등학생 눈높이에 맞춘 다정하고 명확한 1~2문장의 격려와 칭찬 피드백을 작성하세요.

반드시 지정된 JSON 스키마 규격으로 응답하세요."""

    response = call_gemini_with_fallback(
        cli,
        prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BatchEvaluationResponse,
            temperature=0.2,
        ),
    )

    batch_eval = json.loads(response.text)

    now = datetime.now()
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    record = {
        "id": f"batch_grade{grade}_{timestamp_str}",
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "grade": grade,
        "unit": unit,
        "total_score": batch_eval.get("total_score", 0),
        "average_score": batch_eval.get("average_score", 0.0),
        "question_count": len(answers_data),
        "answers": answers_data,
        "results": batch_eval.get("results", [])
    }

    # 만약 saved_results 폴더가 존재하는 경우에만 보조 파일로 저장 (폴더가 없으면 안전하게 건너뜀)
    if RESULTS_DIR.exists():
        try:
            file_path = RESULTS_DIR / f"eval_grade{grade}_{timestamp_str}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # 감점된 서술형 문제(score < 5)를 오답노트 DB(quiz_wrong_notes)에 자동 저장
    try:
        try:
            from .database import save_wrong_note
        except ImportError:
            from database import save_wrong_note

        ans_map = {a.get("id"): a for a in answers_data}
        for res in batch_eval.get("results", []):
            sc = res.get("score", 0)
            if sc < 5:
                q_id = res.get("id")
                q_info = ans_map.get(q_id, {})
                save_wrong_note(
                    problem_id=q_id,
                    grade=grade,
                    unit=unit,
                    quiz_type="subjective",
                    question=q_info.get("question", ""),
                    correct_answer=q_info.get("model_answer", ""),
                    student_answer=q_info.get("student_answer", ""),
                    score=sc,
                    feedback=res.get("feedback", ""),
                    deduction_reason=res.get("analysis", "")
                )
    except Exception as db_err:
        print(f"[서술형 오답 자동 저장 처리 중 알림] {db_err}")

    return record


def answer_student_question(
    student_question: str,
    question_context: str = "",
    student_answer: str = "",
    correct_answer: str = "",
    feedback: str = ""
) -> str:
    """
    학생이 채점 후 해당 문제에 대해 AI 선생님께 이어서 질문할 때
    초등학생 눈높이에 맞춘 다정하고 친절한 1~2문장 원포인트 답변을 생성합니다.
    """
    c = ensure_client()
    prompt = f"""당신은 초등학교 과학을 가르치는 다정하고 친절한 AI 과학 선생님입니다.
학생이 문제를 풀고 난 뒤 아래와 같이 추가 질문을 했습니다.

[문제 정보]
- 문제: {question_context}
- 학생이 썼던 답: {student_answer}
- 모범 정답: {correct_answer}
- 이전 채점 피드백: {feedback}

[학생의 추가 질문]
"{student_question}"

[답변 작성 규칙]
1. 초등학생(1~6학년)의 눈높이에 맞춰 이해하기 쉽고 친절한 존댓말(~해요, ~랍니다)로 설명하세요.
2. 길고 어려운 전문 용어 대신 일상생활의 비유나 쉬운 과학 원리를 들어 1~2문장(최대 3문장)으로 간결하게 답변하세요.
3. 학생의 호기심을 칭찬하고 격려하는 따뜻한 태도를 보여주세요.
"""
    try:
        response = call_gemini_with_fallback(
            c,
            prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=300
            )
        )
        return response.text.strip()
    except Exception as e:
        return f"좋은 질문이에요! 그 과학 원리는 '{correct_answer}'와 깊은 관련이 있답니다. 주변 자연을 관찰해보면 멋진 비밀을 더 많이 발견할 수 있어요!"

