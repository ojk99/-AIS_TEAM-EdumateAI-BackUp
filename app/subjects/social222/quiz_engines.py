# -*- coding: utf-8 -*-
"""
[EduMate AI - 초등사회] 문제 유형별 독립 출제 엔진 모듈 (social/quiz_engines.py)
==============================================================================
- 역할: OX, 객관식, 단답형, 서술형 4대 문제 유형을 완전히 독립된 엔진으로 분리
- 비전공자 개발자 친화형 구조:
  각 유형별로 전용 프롬프트, 배점, 출력 형식이 독립된 함수로 분리되어 있어
  수정이나 새 규칙 추가 시 해당 구역만 쉽게 찾아 편집할 수 있습니다!
==============================================================================
"""

import os
import json
import re
import random
from typing import Callable, Optional, Dict, Any


# ==============================================================================
# 1. [OX 퀴즈 전용 출제 엔진]
# - 배점: 1점 (기초 개념 확인)
# - 특징: 초등학생이 흔히 오해하기 쉬운 사회 개념을 O/X로 확인
# - ✏️ 수정 팁: OX 문제의 말투나 난이도를 바꾸고 싶다면 아래 prompt_ox를 수정하세요!
# ==============================================================================
def generate_ox_quiz(
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    curriculum_snippet: str,
    call_ai_fn: Callable[[str, int, float], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """OX 퀴즈 전용 AI 출제 함수"""

    prompt_ox = f"""
너는 2022 개정 초등학교 사회과 전문 AI 교사야.
아래 [교육과정 체계]를 엄격히 참고하여 초등학생이 풀기 좋은 다정하고 신선한 'OX 퀴즈' 1문제를 출제해줘.

[2022 개정 초등사회 교육과정 체계 (curriculum.txt)]
{curriculum_snippet}

[말투 및 언어 절대 수칙]
- '너희'라는 표현은 절대로 사용하지 마세요! 언제나 '우리' 또는 '여러분'(예: '우리 고장', '우리나라', '우리 학교')이라고 표현하세요.
- 지문과 해설 모두 100% 다정하고 정중한 존댓말(~해요, ~일까요?, ~입니다)을 사용하세요. 반말이나 명령조는 절대 금지합니다.

[OX 퀴즈 출제 요구 조건]
- 대상 학년군: {grade_group}
- 선택 단원: {unit_name}
- 핵심 세부 주제: {sub_topic}
- [단원 일치 절대 엄수]: 반드시 선택 단원 [{unit_name}]의 교과 범위와 세부 주제 [{sub_topic}]에 100% 일치하는 문제를 출제해야 합니다. 다른 단원의 주제를 섞거나 침범하지 마세요!
- 배점: 1점 (난이도: 하)
- 문제 지문: 초등학생이 개념을 바르게 알고 있는지 묻는 명확한 문장 (~해요. 또는 ~일까요?)
- 정답(answer): 반드시 'O' 또는 'X' 중 하나
- 해설(explanation): 왜 O인지, 혹은 왜 X인지(어떤 점이 틀렸고 바른 사실은 무엇인지) 초등학생 눈높이에서 다정한 존댓말로 2~3문장 설명

[출력 형식 JSON]
{{
  "id": "ai_gen_ox_{os.urandom(3).hex()}",
  "unit_name": "{unit_name}",
  "question_type": "ox",
  "difficulty": "하",
  "base_score": 1,
  "question": "초등학생 눈높이의 다정한 존댓말 OX 문제 지문",
  "options": [],
  "answer": "O 또는 X",
  "explanation": "왜 O/X인지 바르게 짚어주는 다정한 존댓말 해설 (~해요, ~입니다)"
}}
"""
    try:
        raw_text = call_ai_fn(prompt_ox, 300, 0.8)
        if raw_text:
            cleaned = _parse_json_from_text(raw_text)
            if cleaned and cleaned.get("answer") in ["O", "X", "o", "x"]:
                cleaned["unit_name"] = unit_name
                cleaned["question_type"] = "ox"
                cleaned["answer"] = cleaned["answer"].upper()
                cleaned["options"] = []
                cleaned["base_score"] = 1
                return cleaned
    except Exception as e:
        print("[OX 출제 알림]:", e)
    return None


def _clean_option_text(text: str) -> str:
    """보기 내용 앞의 '1번 보기:', '1.', '①' 등 불필요한 번호 접두사를 제거하는 헬퍼 함수"""
    if not isinstance(text, str):
        return str(text)
    cleaned = re.sub(r'^(?:[0-9]+번\s*(?:보기)?[:\.]?\s*|[0-9]+[\.\)]\s*|[①②③④⑤]\s*|(?:보기\s*[0-9]+[:\.]?\s*))', '', text.strip())
    return cleaned.strip()


# ==============================================================================
# 2. [객관식(4지선다) 전용 출제 엔진]
# - 배점: 3점 (실전 개념 응용)
# - 특징: 매력적인 오답 3개 + 확실한 정답 1개 + 오답/정답 비교 상세 원리 해설
# - ✏️ 수정 팁: 보기 개수나 해설 방식을 조절하고 싶다면 아래 prompt_mc를 수정하세요!
# ==============================================================================
def generate_multiple_choice_quiz(
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    curriculum_snippet: str,
    call_ai_fn: Callable[[str, int, float], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """객관식(4지선다) 전용 AI 출제 함수"""

    prompt_mc = f"""
너는 2022 개정 초등학교 사회과 전문 AI 교사야.
아래 [교육과정 체계]를 엄격히 참고하여 초등학생의 흥미를 끄는 '4지선다 객관식 퀴즈' 1문제를 출제해줘.

[2022 개정 초등사회 교육과정 체계 (curriculum.txt)]
{curriculum_snippet}

[말투 및 언어 절대 수칙]
- '너희'라는 표현은 절대로 사용하지 마세요! 언제나 '우리' 또는 '여러분'(예: '우리 고장', '우리나라', '우리 학교')이라고 표현하세요.
- 문제 지문과 보기, 해설까지 100% 다정하고 정중한 존댓말(~일까요?, ~골라 보세요, ~해요, ~입니다)을 사용하세요. 반말 금지!

[객관식 출제 요구 조건]
- 대상 학년군: {grade_group}
- 선택 단원: {unit_name}
- 핵심 세부 주제: {sub_topic}
- [단원 일치 절대 엄수]: 반드시 선택 단원 [{unit_name}]의 교과 범위와 세부 주제 [{sub_topic}]에 100% 일치하는 문제를 출제해야 합니다. 다른 단원의 주제를 섞거나 침범하지 마세요!
- 배점: 3점 (난이도: 중)
- 문제 지문: 일상 속 상황이나 흥미로운 자료를 곁들인 친절한 질문
- 보기(options): 서로 헷갈리지만 교육적인 오답 3개와 확실한 정답 1개 (총 4개 보기 필수)
  * 중요: 보기 앞에 '1번', '1번 보기', '1.', '①' 등 번호나 라벨을 절대 붙이지 마세요! 순수하게 내용만 작성하세요.
- 정답(answer): 4개 보기 중 하나와 글자 그대로 100% 정확히 일치할 것 (앞에 번호 붙이지 마세요)
- 해설(explanation): 정답인 구체적인 까닭과 핵심 개념 원리를 3~4문장으로 매우 친절하고 자세하게 다정한 존댓말로 설명

[출력 형식 JSON]
{{
  "id": "ai_gen_mc_{os.urandom(3).hex()}",
  "unit_name": "{unit_name}",
  "question_type": "multiple_choice",
  "difficulty": "중",
  "base_score": 3,
  "question": "초등학생 눈높이의 다정한 질문 (~일까요?, ~골라 보세요)",
  "options": ["첫 번째 보기 내용", "두 번째 보기 내용", "세 번째 보기 내용", "네 번째 보기 내용"],
  "answer": "4개 보기 중 하나와 글자 그대로 일치하는 정답 내용",
  "explanation": "정답인 까닭과 핵심 원리를 친절히 비교해주는 3~4문장 존댓말 해설"
}}
"""
    try:
        raw_text = call_ai_fn(prompt_mc, 380, 0.85)
        if raw_text:
            cleaned = _parse_json_from_text(raw_text)
            opts = cleaned.get("options", [])
            ans = cleaned.get("answer", "")
            if cleaned and isinstance(opts, list) and len(opts) == 4 and ans:
                # '1번 보기', '1.', '①' 등 번호 접두사 자동 정제
                clean_opts = [_clean_option_text(o) for o in opts]
                clean_ans = _clean_option_text(ans)
                if clean_ans not in clean_opts:
                    for orig_o, c_o in zip(opts, clean_opts):
                        if str(ans).strip() == str(orig_o).strip():
                            clean_ans = c_o
                            break
                cleaned["unit_name"] = unit_name
                cleaned["options"] = clean_opts
                cleaned["answer"] = clean_ans
                cleaned["question_type"] = "multiple_choice"
                cleaned["base_score"] = 3
                return cleaned
    except Exception as e:
        print("[객관식 출제 알림]:", e)
    return None


# ==============================================================================
# 3. [단답형 주관식 전용 출제 엔진]
# - 배점: 3점 (핵심 키워드/용어 기억)
# - 특징: 문맥을 읽고 핵심 사회과 용어(단어)를 직접 입력하도록 유도
# - ✏️ 수정 팁: 정답 단어 유형이나 힌트 방식을 조절하고 싶다면 아래 prompt_sa를 수정하세요!
# ==============================================================================
def generate_short_answer_quiz(
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    curriculum_snippet: str,
    call_ai_fn: Callable[[str, int, float], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """단답형 주관식 전용 AI 출제 함수"""

    prompt_sa = f"""
너는 2022 개정 초등학교 사회과 전문 AI 교사야.
아래 [교육과정 체계]를 엄격히 참고하여 초등학생이 핵심 사회과 개념어를 맞히는 '단답형 주관식 퀴즈' 1문제를 출제해줘.

[2022 개정 초등사회 교육과정 체계 (curriculum.txt)]
{curriculum_snippet}

[말투 및 언어 절대 수칙]
- '너희'라는 표현은 절대로 사용하지 마세요! 언제나 '우리' 또는 '여러분'(예: '우리 고장', '우리나라', '우리 학교')이라고 표현하세요.
- 문제 지문과 해설 모두 100% 다정하고 정중한 존댓말(~은 무엇일까요?, ~은 어디일까요?, ~입니다)을 사용하세요.

[단답형 출제 요구 조건]
- 대상 학년군: {grade_group}
- 선택 단원: {unit_name}
- 핵심 세부 주제: {sub_topic}
- [단원 일치 절대 엄수]: 반드시 선택 단원 [{unit_name}]의 교과 범위와 세부 주제 [{sub_topic}]에 100% 일치하는 문제를 출제해야 합니다. 다른 단원의 주제를 섞거나 침범하지 마세요!
- 배점: 3점 (난이도: 중)
- 문제 지문: 개념의 특징이나 쓰임새를 설명한 뒤 그 명칭(단어)을 묻는 질문
- 정답(answer): 초등학생이 키보드로 치기 좋은 1~3단어 이내의 명확한 핵심 용어 (예: '방위표', '축척', '독도', '보건실', '소방서')
- 해설(explanation): 그 단어의 뜻과 우리 생활 속 중요성을 2~3문장으로 알기 쉽게 풀어쓴 존댓말 해설

[출력 형식 JSON]
{{
  "id": "ai_gen_sa_{os.urandom(3).hex()}",
  "unit_name": "{unit_name}",
  "question_type": "short_answer",
  "difficulty": "중",
  "base_score": 3,
  "question": "개념을 설명하고 명칭을 묻는 다정한 질문 (~은 무엇일까요?)",
  "options": [],
  "answer": "핵심 개념 단어",
  "explanation": "해당 단어의 뜻을 쉽게 설명해주는 존댓말 해설"
}}
"""
    try:
        raw_text = call_ai_fn(prompt_sa, 300, 0.8)
        if raw_text:
            cleaned = _parse_json_from_text(raw_text)
            if cleaned and cleaned.get("answer"):
                cleaned["unit_name"] = unit_name
                cleaned["question_type"] = "short_answer"
                cleaned["options"] = []
                cleaned["base_score"] = 3
                return cleaned
    except Exception as e:
        print("[단답형 출제 알림]:", e)
    return None


# ==============================================================================
# 4. [서술형 탐구 전용 출제 엔진]
# - 배점: 5점 (논리적 사고력 & 까닭 설명)
# - 특징: 문맥 기반 0~5점 부분 점수를 채점할 수 있는 모범 답안 및 채점 키워드 포함
# - ✏️ 수정 팁: 서술 질문 주제나 모범답안 문맥을 바꾸고 싶다면 아래 prompt_desc를 수정하세요!
# ==============================================================================
def generate_descriptive_quiz(
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    curriculum_snippet: str,
    call_ai_fn: Callable[[str, int, float], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """서술형 탐구 전용 AI 출제 함수"""

    prompt_desc = f"""
너는 2022 개정 초등학교 사회과 전문 AI 교사야.
아래 [교육과정 체계]를 엄격히 참고하여 초등학생의 생각하는 힘을 길러주는 '서술형 탐구 퀴즈' 1문제를 출제해줘.

[2022 개정 초등사회 교육과정 체계 (curriculum.txt)]
{curriculum_snippet}

[말투 및 언어 절대 수칙]
- '너희'라는 표현은 절대로 사용하지 마세요! 언제나 '우리' 또는 '여러분'(예: '우리 고장', '우리나라', '우리 학교')이라고 표현하세요.
- 지문, 모범답안, 해설 모두 다정하고 정중한 존댓말(~적어 보세요, ~설명해 볼까요?, ~하기 때문입니다)을 사용하세요.

[서술형 출제 요구 조건]
- 대상 학년군: {grade_group}
- 선택 단원: {unit_name}
- 핵심 세부 주제: {sub_topic}
- [단원 일치 절대 엄수]: 반드시 선택 단원 [{unit_name}]의 교과 범위와 세부 주제 [{sub_topic}]에 100% 일치하는 문제를 출제해야 합니다. 다른 단원의 주제를 섞거나 침범하지 마세요!
- 배점: 5점 (난이도: 상)
- 문제 지문: 사회 현상이나 역사, 규칙에 대해 '까닭이나 이유'를 서술하도록 유도하는 질문 (~하는 까닭을 적어 보세요.)
- 모범답안(answer): '~하기 때문입니다.' 형태로 끝나는 1~2문장의 논리적인 모범 서술문
- 채점 키워드(grading_keywords): 학생 답안에 들어가야 할 핵심 단어 3~5개 리스트
- 해설(explanation): 학생이 어떤 점에 집중해서 생각을 펼쳐야 하는지 격려해주는 친절한 가이드 해설

[출력 형식 JSON]
{{
  "id": "ai_gen_desc_{os.urandom(3).hex()}",
  "unit_name": "{unit_name}",
  "question_type": "descriptive",
  "difficulty": "상",
  "base_score": 5,
  "question": "이유나 까닭을 묻는 다정한 서술형 질문 (~까닭을 적어 보세요.)",
  "options": [],
  "answer": "핵심 개념이 담긴 모범 답안 문장 (~때문입니다.)",
  "grading_keywords": ["키워드1", "키워드2", "키워드3"],
  "explanation": "답안 작성 시 중요한 생각의 포인트를 짚어주는 존댓말 해설"
}}
"""
    try:
        raw_text = call_ai_fn(prompt_desc, 380, 0.85)
        if raw_text:
            cleaned = _parse_json_from_text(raw_text)
            if cleaned and cleaned.get("answer"):
                cleaned["unit_name"] = unit_name
                cleaned["question_type"] = "descriptive"
                cleaned["options"] = []
                cleaned["base_score"] = 5
                return cleaned
    except Exception as e:
        print("[서술형 출제 알림]:", e)
    return None


# ==============================================================================
# 5. [통합 출제 디스패처 (관제탑)]
# - 역할: 요청된 유형(ox, multiple_choice, short_answer, descriptive)에 맞는 전용 엔진 호출
# ==============================================================================
def generate_specialized_quiz(
    question_type: str,
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    curriculum_snippet: str,
    call_ai_fn: Callable[[str, int, float], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """유형별 전용 출제 엔진으로 분기 안내"""
    if question_type == "ox":
        return generate_ox_quiz(grade_group, unit_name, sub_topic, curriculum_snippet, call_ai_fn)
    elif question_type == "multiple_choice":
        return generate_multiple_choice_quiz(grade_group, unit_name, sub_topic, curriculum_snippet, call_ai_fn)
    elif question_type == "short_answer":
        return generate_short_answer_quiz(grade_group, unit_name, sub_topic, curriculum_snippet, call_ai_fn)
    elif question_type == "descriptive":
        return generate_descriptive_quiz(grade_group, unit_name, sub_topic, curriculum_snippet, call_ai_fn)
    return None


def _parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """AI 텍스트 응답에서 순수 JSON 객체를 안전하게 추출 파싱"""
    try:
        cleaned = re.sub(r"^```json\s*", "", text.strip())
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        # JSON 블록이 텍스트 중간에 끼어있는 경우 대비
        m = re.search(r"(\{[\s\S]*\})", cleaned)
        if m:
            cleaned = m.group(1)
        return json.loads(cleaned)
    except Exception:
        return None
