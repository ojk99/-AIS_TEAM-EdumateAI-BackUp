"""
================================================================================
[EduMate AI 초등국어] 표준 문제은행 모듈 - question_bank.py
================================================================================
- 전 과목 공통 표준 스키마 준수: question_bank, question_bank_solved
- 양방향 자동 폴백 및 (맞춘문제/전체문제) 단원별 통계 제공
- 주관식/서술형 AI 의미 동치 채점 및 안전 폴백
================================================================================
"""

import os
import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUBJECT_CODE = "korean"
CURRENT_DIR = Path(__file__).resolve().parent
BANK_DB_PATH = CURRENT_DIR / "question_bank.db"

# 난이도별 표준 배점
DIFFICULTY_POINTS = {
    "하": 1,
    "중": 3,
    "상": 5
}


def get_bank_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(BANK_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_bank_db() -> None:
    """표준 문제은행 테이블 초기화 및 2022 개정 초등국어 시드 데이터 탑재"""
    conn = get_bank_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,                  -- 'korean'
                grade INTEGER DEFAULT 4,                -- 1 ~ 6
                grade_group TEXT DEFAULT '',            -- '1~2학년군' | '3~4학년군' | '5~6학년군' | '전체 학년'
                unit_name TEXT NOT NULL,                -- 대단원명
                sub_topic TEXT DEFAULT '',              -- 세부주제명
                question_type TEXT NOT NULL,            -- 'ox' | '객관식' | '단답형' | '서술형'
                difficulty TEXT NOT NULL DEFAULT '중',   -- '하' | '중' | '상'
                points INTEGER NOT NULL DEFAULT 3,      -- 하:1, 중:3, 상:5
                question_text TEXT NOT NULL,            -- 문제 지문
                choices_json TEXT DEFAULT '[]',         -- 보기 JSON 문자열
                correct_answer TEXT NOT NULL,           -- 정답 텍스트
                explanation TEXT DEFAULT '',            -- 해설
                source_type TEXT DEFAULT 'manual',      -- 'manual' | 'ai_log'
                source_log_id INTEGER DEFAULT NULL,
                created_by TEXT DEFAULT 'master',
                created_by_name TEXT DEFAULT '총 관리자',
                created_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime'))
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS question_bank_solved (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                user_key TEXT NOT NULL,
                solved_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
                UNIQUE(bank_id, subject, user_key)
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_qbank_subj_unit ON question_bank (subject, grade, unit_name)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_qbank_solved_key ON question_bank_solved (subject, user_key, bank_id)"
        )
        conn.commit()

        # 시드 데이터가 비어있으면 초기 2022 개정 초등국어 문제은행 데이터 투입
        cur.execute("SELECT COUNT(*) as cnt FROM question_bank WHERE subject = ?", (SUBJECT_CODE,))
        cnt = cur.fetchone()["cnt"]
        if cnt == 0:
            _seed_korean_questions(cur)
            conn.commit()
    finally:
        conn.close()


def _seed_korean_questions(cur: sqlite3.Cursor) -> None:
    """학년/단원별 대표 문제은행 데이터 셋업 (OX, 객관식, 단답형, 서술형 골고루 탑재)"""
    seeds = [
        # -------------------------------------------------------------
        # 4학년 1학기 1단원: 생각과 느낌을 나누어요
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 4, "3~4학년군", "1단원: 생각과 느낌을 나누어요", "시의 느낌",
            "ox", "하", 1,
            "시를 읽고 떠오르는 생각이나 느낌은 사람마다 서로 다를 수 있다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "O",
            "사람마다 경험과 가치관이 다르므로 시를 읽고 떠오르는 느낌이나 생각은 다를 수 있습니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "1단원: 생각과 느낌을 나누어요", "시적 표현",
            "객관식", "중", 3,
            "다음 중 시나 노래를 감상할 때 느낀 점을 표현하는 방법으로 가장 알맞지 않은 것은?",
            '["시 속 인물의 마음에 공감해 본다.", "떠오르는 장면을 그림으로 나타낸다.", "친구가 느낀 점과 내 생각을 비교해 본다.", "글쓴이의 의도와 완전히 똑같은 생각만 정답으로 적는다."]',
            "글쓴이의 의도와 완전히 똑같은 생각만 정답으로 적는다.",
            "문학 작품에 대한 생각과 느낌은 사람마다 다양할 수 있으며, 하나의 정답만 강요되지 않습니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "1단원: 생각과 느낌을 나누어요", "감각적 표현",
            "단답형", "중", 3,
            "어떤 현상이나 사물의 모양, 소리, 촉감 등을 생생하게 느낄 수 있도록 나타낸 표현을 무슨 표현이라고 하는지 쓰시오.",
            '[]', "감각적 표현",
            "눈, 귀, 코, 혀, 피부 등 감각 기관으로 느끼는 것처럼 생생하게 드러내는 표현을 '감각적 표현'이라고 합니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "1단원: 생각과 느낌을 나누어요", "표현의 까닭",
            "서술형", "상", 5,
            "시에서 소리나 모양을 흉내 내는 말을 사용하면 어떤 좋은 점이 있는지 한 문장으로 서술하시오.",
            '[]', "장면이 머릿속에 더 생생하고 실감 나게 떠오르는 좋은 점이 있습니다.",
            "소리나 모양을 흉내 내는 말을 활용하면 글을 읽을 때 장면이 더욱 생생하고 흥미롭게 다가옵니다."
        ),

        # -------------------------------------------------------------
        # 4학년 1학기 2단원: 내용을 짐작해요
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 4, "3~4학년군", "2단원: 내용을 짐작해요", "글의 내용 짐작",
            "ox", "하", 1,
            "글의 제목이나 그림을 보고도 앞으로 일어날 일이나 글의 전체 내용을 짐작할 수 있다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "O",
            "제목, 차례, 삽화나 사진 등은 글의 내용을 미리 짐작하는 중요한 단서가 됩니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "2단원: 내용을 짐작해요", "경험 떠올리기",
            "객관식", "중", 3,
            "글을 읽으며 뒷이야기나 인물의 행동을 짐작할 때 활용하는 방법으로 가장 거리가 먼 것은?",
            '["글에 나타난 단서를 자세히 살펴본다.", "자신이 겪었던 비슷한 경험을 떠올린다.", "단서와 관련 없는 엉뚱한 결말을 상상한다.", "앞뒤 인과관계를 차근차근 따져본다."]',
            "단서와 관련 없는 엉뚱한 결말을 상상한다.",
            "내용 짐작은 글 속의 단서와 자신의 배경지식(경험)을 바탕으로 타당하게 추론해야 합니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "2단원: 내용을 짐작해요", "어휘 뜻 짐작",
            "단답형", "상", 5,
            "글을 읽다가 뜻을 모르는 낱말이 나왔을 때, 그 낱말의 앞뒤 문맥을 살펴 뜻을 헤아려 보는 것을 무엇이라고 하는지 쓰시오.",
            '[]', "낱말 뜻 짐작",
            "앞뒤 문장의 흐름과 맥락을 통해 낯선 낱말의 의미를 파악하는 것을 '낱말의 뜻 짐작하기'라고 합니다."
        ),

        # -------------------------------------------------------------
        # 4학년 1학기 4단원: 사실과 의견을 구별해요
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 4, "3~4학년군", "4단원: 사실과 의견을 구별해요", "사실의 정의",
            "ox", "하", 1,
            "‘우리 학교는 3층 건물이다’라는 문장은 글쓴이의 생각이 드러난 ‘의견’에 해당한다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "X",
            "실제로 확인하고 검증할 수 있는 객관적 정보이므로 '사실'에 해당합니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "4단원: 사실과 의견을 구별해요", "사실과 의견 구별",
            "객관식", "중", 3,
            "다음 중 ‘의견’에 해당하는 문장은 어느 것인가요?",
            '["한글은 세종대왕이 창제하였다.", "도서관에서는 조용히 책을 읽어야 한다.", "대한민국의 수도는 서울이다.", "물은 섭씨 100도에서 끓는다."]',
            "도서관에서는 조용히 책을 읽어야 한다.",
            "사람의 가치 판단이나 주장이 담긴 문장은 '의견'입니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "4단원: 사실과 의견을 구별해요", "개념 서술",
            "서술형", "상", 5,
            "‘사실’과 ‘의견’의 차이점을 한 문장으로 알기 쉽게 서술하시오.",
            '[]', "사실은 실제로 일어난 일이나 증명할 수 있는 객관적인 것이고, 의견은 어떤 대상에 대한 사람의 생각이나 느낌입니다.",
            "사실(객관적 검증 가능)과 의견(주관적 생각 및 판단)의 핵심 차이를 서술하면 정답입니다."
        ),

        # -------------------------------------------------------------
        # 4학년 1학기 5단원: 국어사전과 친해져요
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 4, "3~4학년군", "5단원: 국어사전과 친해져요", "사전 배열 순서",
            "ox", "하", 1,
            "국어사전에서 낱말을 찾을 때 첫 자음자는 ‘ㄱ, ㄴ, ㄷ, ㄹ’의 순서로 실린다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "O",
            "한글 자모 순서에 따라 'ㄱ, ㄲ, ㄴ, ㄷ, ㄸ ...' 순으로 사전 표제어가 배열됩니다."
        ),
        (
            SUBJECT_CODE, 4, "3~4학년군", "5단원: 국어사전과 친해져요", "기본형 찾기",
            "단답형", "중", 3,
            "‘먹었다’, ‘먹으니’, ‘먹고’라는 낱말을 국어사전에서 찾을 때 찾아야 하는 기본형 낱말을 쓰시오.",
            '[]', "먹다",
            "동사나 형용사는 어미 변화를 거치기 전의 기본형(어간 + '-다') 형태로 사전에 실립니다."
        ),

        # -------------------------------------------------------------
        # 1학년 1학기 1단원: 바른 자세로 읽고 쓰기
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 1, "1~2학년군", "1단원: 바른 자세로 읽고 쓰기", "바른 자세",
            "ox", "하", 1,
            "책을 읽을 때는 허리를 곧게 펴고 책과 눈 사이에 적당한 거리를 두어야 한다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "O",
            "바른 자세는 시력 보호와 척추 건강, 집중력 향상에 필수적입니다."
        ),
        (
            SUBJECT_CODE, 1, "1~2학년군", "1단원: 바른 자세로 읽고 쓰기", "글자 쓰기",
            "객관식", "중", 3,
            "연필을 쥐고 글씨를 바르게 쓸 때 알맞은 모습은 어느 것인가요?",
            '["연필의 끝부분을 꼭 쥐고 눕혀 쓴다.", "엄지와 검지, 중지로 연필심 위 2~3cm 부위를 안정되게 잡는다.", "손가락 전체로 주먹 쥐듯이 잡는다.", "양손으로 연필을 잡고 누른다."]',
            "엄지와 검지, 중지로 연필심 위 2~3cm 부위를 안정되게 잡는다.",
            "바른 연필 쥐기는 엄지와 검지, 중지로 균형 있게 잡는 자세입니다."
        ),

        # -------------------------------------------------------------
        # 6학년 1학기 1단원: 비유하는 표현
        # -------------------------------------------------------------
        (
            SUBJECT_CODE, 6, "5~6학년군", "1단원: 비유하는 표현", "비유 표현의 정의",
            "ox", "하", 1,
            "‘내 동생은 천사 같다’처럼 ‘~처럼, ~같이, ~듯이’ 등의 연결어를 써서 직접 빗대는 비유법을 직유법이라고 한다. (이 설명이 맞으면 O, 틀리면 X를 선택하세요.)",
            '["O", "X"]', "O",
            "원관념과 보조관념을 '마치, 처럼, 같이, 듯이'로 직접 연결하는 표현법을 직유법이라고 합니다."
        ),
        (
            SUBJECT_CODE, 6, "5~6학년군", "1단원: 비유하는 표현", "은유법",
            "객관식", "중", 3,
            "‘내 마음은 호수요’처럼 연결어 없이 ‘A는 B이다’ 형식으로 빗대어 나타내는 비유법은 무엇인가요?",
            '["직유법", "은유법", "의인법", "과장법"]',
            "은유법",
            "연결어 없이 암시적으로 빗대는 비유 방법을 '은유법'이라고 합니다."
        ),
        (
            SUBJECT_CODE, 6, "5~6학년군", "1단원: 비유하는 표현", "비유 표현 창작",
            "서술형", "상", 5,
            "‘선생님의 따뜻한 미소’를 비유하는 표현(직유법 또는 은유법)을 활용하여 한 문장으로 아름답게 표현해 보시오.",
            '[]', "선생님의 따뜻한 미소는 봄날의 햇살처럼 포근하다.",
            "선생님의 미소를 다른 사물(봄 햇살, 등대 등)에 적절한 연결어나 은유로 빗대어 표현하면 정답입니다."
        ),
    ]

    for s in seeds:
        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            s
        )


def get_unit_bank_stats(grade_num: Optional[int] = None, user_key: str = "guest", grade_str: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """
    각 단원별 문제은행 현황 통계 반환:
    { "1단원: 생각과 느낌을 나누어요": { "total": 4, "solved": 2, "unsolved": 2 }, ... }
    """
    init_bank_db()
    conn = get_bank_conn()
    try:
        cur = conn.cursor()

        # 학년 조건 조합
        query = """
            SELECT 
                qb.unit_name,
                COUNT(qb.id) as total_count,
                COUNT(qbs.id) as solved_count
            FROM question_bank qb
            LEFT JOIN question_bank_solved qbs 
                ON qb.id = qbs.bank_id 
                AND qbs.subject = qb.subject 
                AND qbs.user_key = ?
            WHERE qb.subject = ?
        """
        params: List[Any] = [user_key, SUBJECT_CODE]

        if grade_num is not None and 1 <= grade_num <= 6:
            query += " AND qb.grade = ?"
            params.append(grade_num)

        query += " GROUP BY qb.unit_name"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        stats: Dict[str, Dict[str, int]] = {}
        for r in rows:
            u_name = str(r["unit_name"]).strip()
            total = int(r["total_count"] or 0)
            solved = int(r["solved_count"] or 0)
            stats[u_name] = {
                "total": total,
                "solved": solved,
                "unsolved": max(0, total - solved)
            }
        return stats
    finally:
        conn.close()


def get_bank_questions(
    grade_num: int = 4,
    unit_name: Optional[str] = None,
    question_type: Optional[str] = None,
    user_key: str = "guest",
    count: int = 5,
    allow_review: bool = False
) -> Tuple[List[Dict[str, Any]], bool, bool]:
    """
    문제은행에서 조건에 맞는 문제 목록을 추출합니다.
    - 반환값: (questions_list, is_fallback, is_review)
    - 1순위: 아직 풀지 않은 문제 (solved되지 않은 문제)
    - 2순위 (allow_review=True): 미풀이 문제가 부족할 때 기해결 문제를 복습용으로 충원 (is_review=True)
    """
    init_bank_db()
    conn = get_bank_conn()
    try:
        cur = conn.cursor()

        clean_unit = (unit_name or "").strip()
        if clean_unit == "전체" or clean_unit == "":
            clean_unit = None

        # 1. 미풀이 문제 조회
        query = """
            SELECT qb.*
            FROM question_bank qb
            WHERE qb.subject = ?
              AND qb.id NOT IN (
                  SELECT bank_id FROM question_bank_solved 
                  WHERE subject = ? AND user_key = ?
              )
        """
        params: List[Any] = [SUBJECT_CODE, SUBJECT_CODE, user_key]

        if grade_num:
            query += " AND qb.grade = ?"
            params.append(grade_num)

        if clean_unit:
            query += " AND (qb.unit_name = ? OR qb.unit_name LIKE ?)"
            params.extend([clean_unit, f"%{clean_unit[:6]}%"])

        if question_type and question_type != "전체":
            # ox 소문자/대문자 호환
            q_type_term = "ox" if question_type.upper() == "OX" else question_type
            query += " AND (qb.question_type = ? OR UPPER(qb.question_type) = ?)"
            params.extend([q_type_term, question_type.upper()])

        query += " ORDER BY RANDOM() LIMIT ?"
        params.append(count)

        cur.execute(query, tuple(params))
        unsolved_rows = cur.fetchall()
        result = [dict(r) for r in unsolved_rows]

        # 미풀이 문제가 충분하면 즉시 반환 (is_fallback=False, is_review=False)
        if len(result) >= count or not allow_review:
            return result, False, False

        # 2. 미풀이 문제가 부족하고 복습 모드(allow_review=True) 허용 시: 기풀이 문제 추가 조회
        needed = count - len(result)
        existing_ids = [r["id"] for r in result]
        placeholders = ",".join(["?"] * len(existing_ids)) if existing_ids else "0"

        rev_query = f"""
            SELECT qb.*
            FROM question_bank qb
            WHERE qb.subject = ?
              AND qb.id NOT IN ({placeholders})
        """
        rev_params: List[Any] = [SUBJECT_CODE] + existing_ids

        if grade_num:
            rev_query += " AND qb.grade = ?"
            rev_params.append(grade_num)

        if clean_unit:
            rev_query += " AND (qb.unit_name = ? OR qb.unit_name LIKE ?)"
            rev_params.extend([clean_unit, f"%{clean_unit[:6]}%"])

        if question_type and question_type != "전체":
            q_type_term = "ox" if question_type.upper() == "OX" else question_type
            rev_query += " AND (qb.question_type = ? OR UPPER(qb.question_type) = ?)"
            rev_params.extend([q_type_term, question_type.upper()])

        rev_query += " ORDER BY RANDOM() LIMIT ?"
        rev_params.append(needed)

        cur.execute(rev_query, tuple(rev_params))
        reviewed_rows = cur.fetchall()
        for r in reviewed_rows:
            d = dict(r)
            d["is_review"] = True  # 복습 문제 표시
            result.append(d)

        is_review_mode = any(r.get("is_review") for r in result)
        return result, False, is_review_mode
    finally:
        conn.close()


def mark_bank_question_solved(bank_id: int, user_key: str) -> bool:
    """문제은행 문제를 정답으로 맞혔을 때 해결 완료로 기록"""
    init_bank_db()
    conn = get_bank_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key, solved_at)
            VALUES (?, ?, ?, DATETIME('now', 'localtime'))
            """,
            (bank_id, SUBJECT_CODE, user_key),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def grade_bank_question_by_ai(
    question_text: str,
    model_answer: str,
    user_answer: str,
    question_type: str,
    max_points: int = 3,
    genai_client: Any = None
) -> Tuple[int, bool, str]:
    """
    직접 출제(문제은행) 문제의 주관식/서술형 AI 의미 동치 및 부분 점수 판정
    - 반환값: (earned_score, is_correct, feedback)
    - AI 서버 비응답 시 규칙 기반(문자열/키워드 일치)으로 안전하게 폴백
    """
    user_clean = (user_answer or "").strip()
    model_clean = (model_answer or "").strip()

    if not user_clean:
        return 0, False, "답안이 입력되지 않았습니다."

    # 1. 단순 일치 여부 확인 (빠른 패스)
    if user_clean.lower() == model_clean.lower():
        return max_points, True, "정답입니다! 완벽하게 일치합니다. 🎉"

    # 2. AI 채점 시도
    if genai_client:
        try:
            prompt = f"""
당신은 2022 개정 초등국어 공정 채점관입니다.
문제은행에 수동 등록된 주관식({question_type}) 문제에 대해 학생의 답안을 평가해주세요.

[문제 내용]: {question_text}
[모범 정답/해설]: {model_clean}
[학생 답안]: {user_clean}
[문항 만점 배점]: {max_points}점

채점 기준:
1. 학생의 표현이 모범 정답과 문맥상 일치하거나 동일한 핵심 의미를 담고 있으면 만점({max_points}점)을 부여하세요.
2. 서술형의 경우 취지는 맞으나 일부 설명이 부족한 경우 비례하여 부분 점수(0 ~ {max_points}점)를 부여하세요.
3. 정답 여부(is_correct)는 {max_points // 2 + 1}점 이상이면 true, 미만이면 false로 판정하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "score": {max_points},
  "is_correct": true,
  "feedback": "초등학생 눈높이의 친절하고 따뜻한 1문장 피드백"
}}
"""
            resp = genai_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2}
            )
            raw = resp.text.strip()
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()
            data = json.loads(cleaned)

            sc = min(max_points, max(0, int(data.get("score", 0))))
            corr = bool(data.get("is_correct", sc >= (max_points / 2)))
            fb = str(data.get("feedback", "문맥 평가가 완료되었습니다."))
            return sc, corr, fb
        except Exception:
            pass  # AI 실패 시 아래 3단계 규칙 기반 폴백

    # 3. 비상 규칙 기반 폴백 채점
    # 포함 관계 확인
    if user_clean in model_clean or model_clean in user_clean:
        sc = max(1, max_points - 1)
    return 0, False, f"오답입니다. 모범 정답은 '{model_clean}'입니다."


# 모듈 임포트 시 question_bank.db 자동 생성 및 시드 데이터 탑재
try:
    init_bank_db()
except Exception as _e:
    pass

