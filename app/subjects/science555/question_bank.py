"""
EduMate AI - 초등 과학 전용 표준 문제은행 모듈 (question_bank.py)
==============================================================================
[표준 준수 사양]
1. 표준 SQLite DB: app/subjects/science/question_bank.db
2. 표준 테이블: question_bank (문제 마스터), question_bank_solved (사용자별 풀이 완료 기록)
3. 양방향 3단계 자동 폴백 연동: AI ↔ 문제은행
4. 주관식(단답형) 및 서술형 AI 문맥 채점 및 비상 시 키워드 폴백
==============================================================================
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

current_dir = Path(__file__).resolve().parent
DB_PATH = current_dir / "question_bank.db"
SUBJECT_NAME = "science"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_question_bank_db() -> None:
    """표준 문제은행 테이블 자동 개설 및 기초 시드 데이터 마이그레이션"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 1. 문제은행 마스터 테이블
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                grade INTEGER DEFAULT 4,
                grade_group TEXT DEFAULT '',
                unit_name TEXT NOT NULL,
                sub_topic TEXT DEFAULT '',
                question_type TEXT NOT NULL,
                difficulty TEXT NOT NULL DEFAULT '중',
                points INTEGER NOT NULL DEFAULT 3,
                question_text TEXT NOT NULL,
                choices_json TEXT DEFAULT '[]',
                correct_answer TEXT NOT NULL,
                explanation TEXT DEFAULT '',
                source_type TEXT DEFAULT 'manual',
                source_log_id INTEGER DEFAULT NULL,
                created_by TEXT DEFAULT 'master',
                created_by_name TEXT DEFAULT '총 관리자',
                created_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime'))
            );
            """
        )

        # 2. 문제은행 학생별 풀이 완료 테이블
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qb_unit ON question_bank (subject, grade, unit_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qb_solved ON question_bank_solved (subject, user_key)")
        conn.commit()

        # 3. 기초 시드 데이터 자동 적재 (문제가 비어있을 때만)
        cur.execute("SELECT COUNT(*) FROM question_bank WHERE subject = ?", (SUBJECT_NAME,))
        cnt = cur.fetchone()[0]
        if cnt == 0:
            _seed_initial_questions(conn)
    finally:
        conn.close()


def _seed_initial_questions(conn: sqlite3.Connection) -> None:
    """초등 과학 1~6학년 대표 단원별 고품질 표준 문제은행 시드 데이터"""
    cur = conn.cursor()
    seeds = [
        # 3학년
        (3, "3~4학년군", "물질의 성질", "금속과 플라스틱", "ox", "하", 1, "자석에 붙는 쇠붙이는 모두 금속으로 만들어졌습니다.", "[]", "O", "철이나 스테인리스 등 자석에 붙는 물질은 금속의 고유한 성질입니다."),
        (3, "3~4학년군", "물질의 성질", "물질의 상태", "객관식", "중", 3, "다음 중 담는 그릇에 따라 모양은 변하지만 부피는 변하지 않는 상태는 무엇일까요?", json.dumps(["고체", "액체", "기체", "플라스마", "진공"], ensure_ascii=False), "2", "액체는 담는 용기에 따라 모양은 변하지만 일정한 부피를 유지합니다."),
        (3, "3~4학년군", "동물의 생활", "동물의 특징", "단답형", "중", 3, "땅 위에서 기어 다니며 다리가 없고 피부로 숨을 쉬는 환형동물은 무엇일까요?", "[]", "지렁이", "지렁이는 다리가 없고 피부로 호흡하며 땅속을 부드럽게 만듭니다."),
        (3, "3~4학년군", "동물의 생활", "서식지 적응", "서술형", "상", 5, "사막에 사는 낙타의 신체적 특징 중 물 부족에 적응한 방법 1가지를 서술하세요.", "[]", "혹에 지방을 저장하여 물과 에너지를 얻고 소변을 적게 배출합니다.", "낙타의 등에 있는 혹은 지방 덩어리로, 물이 부족할 때 지방을 분해해 에너지와 수분을 보충합니다."),

        # 4학년
        (4, "3~4학년군", "식물의 생활", "수생식물", "ox", "하", 1, "개구리밥은 잎에 공기주머니가 있어서 물 위에 둥둥 떠서 살아갑니다.", "[]", "O", "개구리밥, 부레옥잠 등은 공기주머니가 있어 물 위에 떠서 살아가는 부유식물입니다."),
        (4, "3~4학년군", "식물의 생활", "사막식물", "객관식", "중", 3, "사막에 사는 선인장의 가시는 본래 식물의 어떤 부분이 변한 것일까요?", json.dumps(["줄기", "뿌리", "잎", "꽃잎", "열매"], ensure_ascii=False), "3", "선인장의 가시는 수분 증발을 막기 위해 잎이 바늘 모양으로 변형된 것입니다."),
        (4, "3~4학년군", "지층과 화석", "퇴적암", "단답형", "중", 3, "자갈, 모래, 진흙 등이 물속에 가라앉아 굳어져 만들어진 암석을 무엇이라고 할까요?", "[]", "퇴적암", "자갈, 모래, 진흙 등 퇴적물이 쌓여 굳어진 암석을 퇴적암이라고 합니다."),
        (4, "3~4학년군", "물의 상태 변화", "증발과 끓음", "서술형", "상", 5, "젖은 빨래가 마르는 '증발'과 주전자의 물이 부글부글 끓는 '끓음'의 차이점을 1문장으로 쓰세요.", "[]", "증발은 물의 표면에서만 일어나고 끓음은 물의 표면과 내부 전체에서 일어납니다.", "증발은 모든 온도에서 표면에서 기화하는 현상이고, 끓음은 끓는점(100℃)에서 내부와 표면 모두에서 격렬하게 일어납니다."),
        (4, "3~4학년군", "화산과 지진", "화산 분출물", "객관식", "중", 3, "화산이 분출할 때 지하 깊은 곳에 녹아있던 마그마가 지표 밖으로 흘러나온 것을 무엇이라고 할까요?", json.dumps(["화산재", "용암", "화산가스", "현무암", "화강암"], ensure_ascii=False), "2", "마그마가 지표면 밖으로 분출되어 가스가 빠져나가고 흐르는 액체 상태를 용암이라고 합니다."),

        # 5학년
        (5, "5~6학년군", "태양계와 별", "행성의 특징", "ox", "하", 1, "태양계 행성 중 가장 큰 행성은 목성입니다.", "[]", "O", "목성은 태양계에서 부피와 질량이 가장 거대한 가스 행성입니다."),
        (5, "5~6학년군", "태양계와 별", "행성 분류", "객관식", "중", 3, "다음 중 암석으로 이루어진 지구형 행성으로만 짝지어진 것은 무엇일까요?", json.dumps(["수성, 금성, 지구, 화성", "목성, 토성, 천왕성, 해왕성", "지구, 목성, 토성, 화성", "수성, 토성, 해왕성, 금성", "천왕성, 해왕성, 명왕성, 지구"], ensure_ascii=False), "1", "수성, 금성, 지구, 화성은 표면이 단단한 암석으로 이루어진 지구형 행성입니다."),
        (5, "5~6학년군", "산과 염기", "지시약", "단답형", "중", 3, "붉은 양배추 지시약에 식초를 떨어뜨렸을 때 변하는 색깔은 무엇일까요?", "[]", "붉은색", "붉은 양배추 지시약은 산성 용액(식초, 레몬즙)에서 붉은색 계열로 변합니다."),
        (5, "5~6학년군", "빛과 렌즈", "빛의 굴절", "서술형", "상", 5, "물속에 넣은 빨대가 꺾여 보이는 까닭을 '빛'의 성질과 관련지어 설명하세요.", "[]", "빛이 공기에서 물로 들어갈 때 두 물질의 경계면에서 빛의 속도가 달라져 굴절하기 때문입니다.", "빛이 공기와 물처럼 서로 다른 물질을 통과할 때 진행 속도가 달라져 경계면에서 꺾이는 굴절 현상 때문입니다."),

        # 6학년
        (6, "5~6학년군", "지구와 달의 운동", "자전과 낮밤", "ox", "하", 1, "지구가 하루에 한 바퀴씩 스스로 도는 자전 때문에 낮과 밤이 생깁니다.", "[]", "O", "지구가 자전축을 중심으로 서에서 동으로 하루 1회 자전하여 태양빛을 받는 쪽이 낮이 됩니다."),
        (6, "5~6학년군", "지구와 달의 운동", "자전 방향", "객관식", "중", 3, "지구의 자전 방향과 태양이 매일 뜨고 지는 겉보기 운동 방향의 설명으로 옳은 것은?", json.dumps(["지구는 서→동으로 자전하고 태양은 동→서로 움직여 보인다", "지구는 동→서로 자전하고 태양은 서→동으로 움직여 보인다", "지구와 태양 모두 서→동으로 움직인다", "지구와 태양 모두 동→서로 움직인다", "계절마다 자전 방향이 반대로 바뀐다"], ensure_ascii=False), "1", "지구가 서쪽에서 동쪽으로 회전하므로, 반대로 천체인 태양은 동쪽에서 떠서 서쪽으로 지는 것처럼 보입니다."),
        (6, "5~6학년군", "계절의 변화", "태양의 남중고도", "단답형", "중", 3, "우리나라에서 1년 중 낮의 길이가 가장 길고 태양의 남중 고도가 가장 높은 절기는 무엇일까요?", "[]", "하지", "하지는 태양의 남중 고도가 가장 높고 그림자가 가장 짧으며 낮이 가장 긴 날입니다."),
        (6, "5~6학년군", "생물과 환경", "생태계 평형", "서술형", "상", 5, "어느 숲에서 늑대와 같은 상위 포식자가 사라졌을 때 초식동물과 풀밭에 일어나는 변화를 1문장으로 서술하세요.", "[]", "초식동물의 수가 급격히 늘어나 풀을 과도하게 뜯어먹음으로써 숲이 황폐해집니다.", "상위 포식자가 사라지면 초식동물이 급증하여 식물 군락이 파괴되고 결국 생태계 평형이 무너집니다.")
    ]

    for s in seeds:
        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')
            """,
            (SUBJECT_NAME,) + s
        )
    conn.commit()


def get_unit_bank_stats(subject: str = "science", user_key: str = "김에듀") -> Dict[str, Dict[str, Any]]:
    """
    각 단원별 (맞춘 문제 수 / 전체 문제 수) 통계 반환
    반환 예시: {"지구와 달의 운동": {"total": 4, "solved": 1, "display": "(1/4)"}}
    """
    init_question_bank_db()
    conn = _get_conn()
    clean_subj = subject or SUBJECT_NAME
    clean_user = (user_key or "김에듀").strip()
    stats = {}
    try:
        cur = conn.cursor()
        # 전체 문제 수 집계
        cur.execute(
            """
            SELECT grade, unit_name, COUNT(*) as total_cnt
            FROM question_bank
            WHERE subject = ?
            GROUP BY grade, unit_name
            """,
            (clean_subj,)
        )
        for row in cur.fetchall():
            u_name = row["unit_name"]
            stats[u_name] = {
                "grade": row["grade"],
                "unit": u_name,
                "total": row["total_cnt"],
                "solved": 0,
                "display": f"(0/{row['total_cnt']})"
            }

        # 사용자가 맞춘(solved) 문제 수 집계
        cur.execute(
            """
            SELECT qb.unit_name, COUNT(DISTINCT s.bank_id) as solved_cnt
            FROM question_bank_solved s
            JOIN question_bank qb ON s.bank_id = qb.id
            WHERE s.subject = ? AND s.user_key = ?
            GROUP BY qb.unit_name
            """,
            (clean_subj, clean_user)
        )
        for row in cur.fetchall():
            u_name = row["unit_name"]
            if u_name in stats:
                t = stats[u_name]["total"]
                sol = row["solved_cnt"]
                stats[u_name]["solved"] = sol
                stats[u_name]["display"] = f"({sol}/{t})"

        return stats
    finally:
        conn.close()


def get_bank_quiz_questions(
    grade: int = 4,
    unit: str = "총정리",
    question_type: str = "all",
    count: int = 10,
    user_key: str = "김에듀"
) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    문제은행에서 해당 단원 출제
    1순위: 미풀이 문제 우선 추출
    2순위: 다 풀었으면 기풀이 문제 랜덤 복습 모드 추출 (is_review = True)
    반환값: (questions, is_review_mode, message)
    """
    init_question_bank_db()
    conn = _get_conn()
    clean_user = (user_key or "김에듀").strip()
    try:
        cur = conn.cursor()
        type_filter = ""
        params = [SUBJECT_NAME, grade]

        if unit and unit != "총정리":
            unit_filter = "AND unit_name = ?"
            params.append(unit)
        else:
            unit_filter = ""

        if question_type == "ox":
            type_filter = "AND question_type = 'ox'"
        elif question_type == "mcq":
            type_filter = "AND question_type = '객관식'"
        elif question_type == "subjective":
            type_filter = "AND question_type IN ('단답형', '서술형')"

        # 1. 미풀이 문제 조회
        query_unsolved = f"""
            SELECT * FROM question_bank
            WHERE subject = ? AND grade = ? {unit_filter} {type_filter}
              AND id NOT IN (
                  SELECT bank_id FROM question_bank_solved
                  WHERE subject = ? AND user_key = ?
              )
            ORDER BY RANDOM()
            LIMIT ?
        """
        params_unsolved = list(params) + [SUBJECT_NAME, clean_user, count]
        cur.execute(query_unsolved, params_unsolved)
        unsolved_rows = [dict(r) for r in cur.fetchall()]

        if len(unsolved_rows) >= count or len(unsolved_rows) > 0:
            formatted = [_format_bank_item(r) for r in unsolved_rows]
            return formatted, False, "미풀이 문제은행 출제"

        # 2. 미풀이 문제가 0개인 경우 -> 이미 다 풀었는지 확인 후 복습 모드로 출제
        query_all = f"""
            SELECT * FROM question_bank
            WHERE subject = ? AND grade = ? {unit_filter} {type_filter}
            ORDER BY RANDOM()
            LIMIT ?
        """
        params_all = list(params) + [count]
        cur.execute(query_all, params_all)
        all_rows = [dict(r) for r in cur.fetchall()]

        if all_rows:
            formatted = [_format_bank_item(r) for r in all_rows]
            return formatted, True, "AI 연결이 원활하지 않아 이미 해결한 문제은행 문제를 복습용으로 출제했습니다. (누적 포인트 미반영)"

        # 3. 문제은행에 아예 문제가 0개인 경우
        return [], False, "문제은행 DB에 등록된 문제가 없습니다."
    finally:
        conn.close()


def _format_bank_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """프론트엔드 호환 표준 JSON 구조 변환"""
    choices = []
    if row.get("choices_json"):
        try:
            choices = json.loads(row["choices_json"])
        except Exception:
            choices = []

    ans_str = str(row.get("correct_answer", ""))
    numeric_ans = None
    if ans_str.isdigit():
        numeric_ans = int(ans_str)

    return {
        "id": row["id"],
        "bank_id": row["id"],
        "grade": row.get("grade", 4),
        "unit": row.get("unit_name", ""),
        "sub_topic": row.get("sub_topic", ""),
        "question": row.get("question_text", ""),
        "options": choices,
        "answer": numeric_ans if numeric_ans is not None else ans_str,
        "correct_answer": ans_str,
        "model_answer": ans_str,
        "explanation": row.get("explanation", ""),
        "difficulty": row.get("difficulty", "중"),
        "points": row.get("points", 3),
        "quiz_type": row.get("question_type", "mcq")
    }


def mark_bank_question_solved(bank_id: int, subject: str = "science", user_key: str = "김에듀") -> bool:
    """학생이 문제은행 문제를 맞혔을 때 완료 기록 저장"""
    init_question_bank_db()
    conn = _get_conn()
    clean_subj = subject or SUBJECT_NAME
    clean_user = (user_key or "김에듀").strip()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key, solved_at)
            VALUES (?, ?, ?, DATETIME('now', 'localtime'))
            """,
            (bank_id, clean_subj, clean_user)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[문제은행 풀이 기록 오류] {e}")
        return False
    finally:
        conn.close()


def grade_bank_question_by_ai(
    question_text: str,
    correct_answer: str,
    student_answer: str,
    points: int = 3,
    explanation: str = ""
) -> Tuple[int, bool, str]:
    """
    문제은행 주관식/단답형/서술형 문제를 Gemini AI로 채점 (부분 점수 및 동치 인정)
    AI 미응답 또는 비상 시 단순 문자열/키워드 비교로 안전하게 폴백
    반환값: (earned_score, is_correct, feedback)
    """
    clean_student = (student_answer or "").strip()
    clean_correct = (correct_answer or "").strip()

    if not clean_student:
        return 0, False, "답안이 제출되지 않았습니다."

    # 1. 완전 일치 시 빠른 반환
    if clean_student.lower() == clean_correct.lower():
        return points, True, "완벽한 정답입니다! 훌륭해요."

    # 2. AI 문맥 채점 시도
    try:
        from .service import ensure_client
        from google.genai import types

        client = ensure_client()
        prompt = f"""당신은 초등학교 과학 교사입니다. 학생이 문제은행의 주관식 문제를 풀었습니다.
질문: {question_text}
모범 정답: {correct_answer}
출제 해설: {explanation}
학생 답안: {student_answer}
배점: {points}점 만점

[채점 규칙]
1. 단순 띄어쓰기나 맞춤법 차이, 유사한 동의어(예: '빛의 굴절' vs '굴절하기 때문')는 과학적 의미가 통하면 만점을 부여하세요.
2. 서술형 문제의 경우 핵심 키워드가 일부 포함되었으나 설명이 미흡하면 1~{points-1}점 사이의 부분 점수를 부여하세요.
3. 초등학생 눈높이에 맞춘 다정한 1문장 피드백을 작성하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{"score": {points}, "feedback": "다정한 피드백"}}
"""
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=200
            )
        )
        res_json = json.loads(response.text.strip())
        score = int(res_json.get("score", 0))
        score = max(0, min(points, score))
        feedback = res_json.get("feedback", "잘 풀었습니다.")
        is_correct = bool(score >= (points * 0.6))
        return score, is_correct, feedback
    except Exception as e:
        # 3. 비상 상황: 단순 키워드 포함 기반 안전 폴백 채점
        print(f"[AI 채점 실패, 키워드 폴백 작동] {e}")
        if clean_correct in clean_student or clean_student in clean_correct:
            return points, True, "핵심 단어가 올바르게 포함된 정답입니다!"
        return 0, False, f"아쉬워요! 모범 정답은 '{correct_answer}'입니다."


# 모듈 임포트 시 표준 문제은행 DB 자동 초기화 (테이블 생성 및 17문항 시드 적재)
try:
    init_question_bank_db()
except Exception as _e_init:
    print(f"[문제은행 DB 초기화 알림] {_e_init}")

