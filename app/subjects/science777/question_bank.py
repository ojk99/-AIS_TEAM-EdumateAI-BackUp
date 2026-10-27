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
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

current_dir = Path(__file__).resolve().parent
DB_PATH = current_dir / "question_bank.db"
SUBJECT_NAME = "science"

# [규격 설정] 자동 리필 1회 생성 수량 및 단원별 최대 저장 상한선
REFILL_BATCH_SIZE = 15      # 1회 자동 리필 시 보충할 문제 수 (15개)
MAX_UNIT_QUESTIONS = 30     # 각 단원별 최대 문제 저장 한도 (30개 제한)

# [소진율 70% 자동 리필 엔진] 동시 중복 생성 방지용 락 & 세트
_refilling_lock = threading.Lock()
_refilling_keys = set()


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
    """초등 과학 1~6학년 전 단원 고품질 표준 문제은행 시드 데이터 자동 적재"""
    try:
        from .seed_rich_data import RICH_SEEDS
        seeds = RICH_SEEDS
    except Exception:
        from seed_rich_data import RICH_SEEDS
        seeds = RICH_SEEDS

    cur = conn.cursor()
    for s in seeds:
        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank (
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

                # [버튼 클릭 / 화면 진입 시] 소진율 70% 도달 단원 자동 리필 가동
                if t > 0 and (sol / t >= 0.7 or (t - sol) <= 3) and t < MAX_UNIT_QUESTIONS:
                    check_and_trigger_auto_refill(stats[u_name]["grade"], u_name, "all", clean_user)

        return stats
    finally:
        conn.close()


def check_and_trigger_auto_refill(
    grade: int,
    unit: str,
    question_type: str = "all",
    user_key: str = "김에듀"
) -> bool:
    """
    [소진율 70% 이상 자동 리필 엔진]
    소진율(맞춘 문제 / 전체 문제)이 70% 이상이거나, 잔여 문제가 3개 이하이거나,
    전체 문제가 0개일 때 백그라운드 스레드로 AI 새 문제 15개를 자동 생성하여 문제은행에 보충
    (단, 각 단원별 최대 문제 저장 한도는 30개로 엄격히 제한)
    """
    if not unit or unit == "총정리":
        return False

    clean_user = (user_key or "김에듀").strip()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 1. 해당 학년/단원 전체 문제 수
        cur.execute(
            """
            SELECT COUNT(*) FROM question_bank
            WHERE subject = ? AND grade = ? AND unit_name = ?
            """,
            (SUBJECT_NAME, grade, unit)
        )
        total_cnt = cur.fetchone()[0]

        # 2. 해당 학생이 맞춘 문제 수
        cur.execute(
            """
            SELECT COUNT(DISTINCT s.bank_id) FROM question_bank_solved s
            JOIN question_bank q ON s.bank_id = q.id
            WHERE s.subject = ? AND s.user_key = ? AND q.grade = ? AND q.unit_name = ?
            """,
            (SUBJECT_NAME, clean_user, grade, unit)
        )
        solved_cnt = cur.fetchone()[0]

        burn_rate = (solved_cnt / total_cnt) if total_cnt > 0 else 1.0
        remaining = total_cnt - solved_cnt

        # 소진율 70% 이상 또는 10문제를 낼 수 없을 때(잔여 문제 10개 미만) 또는 전체 0문제
        if total_cnt == 0 or burn_rate >= 0.7 or remaining < 10:
            target_refill = REFILL_BATCH_SIZE  # 기본 15문제 보충 (30개 초과분은 가장 오래된 문제부터 FIFO 자동 삭제)

            lock_key = (grade, unit, question_type)
            with _refilling_lock:
                if lock_key in _refilling_keys:
                    return False  # 이미 해당 단원 백그라운드 리필 작업 중
                _refilling_keys.add(lock_key)

            print(f"[문제은행 자동 리필 감지] 학년: {grade}, 단원: {unit}, 소진율: {burn_rate*100:.1f}%, 잔여: {remaining}개 (현재 {total_cnt}/최대 {MAX_UNIT_QUESTIONS}개) -> {target_refill}문제 순환 리필 가동")
            t = threading.Thread(
                target=_auto_refill_worker,
                args=(grade, unit, question_type, lock_key, target_refill),
                daemon=True
            )
            t.start()
            return True
        return False
    except Exception as e:
        print(f"[자동 리필 체크 오류] {e}")
        return False
    finally:
        conn.close()


def _auto_refill_worker(grade: int, unit: str, question_type: str, lock_key: tuple, target_count: int = 15) -> None:
    """백그라운드에서 AI(Gemini)로 새 15문제(최대 30개 한도) 생성 후 question_bank 테이블에 INSERT"""
    try:
        try:
            from .service import generate_ox_quiz, generate_mcq_quiz, generate_subjective_quiz
        except Exception:
            from service import generate_ox_quiz, generate_mcq_quiz, generate_subjective_quiz

        new_items = []
        if question_type == "ox":
            raw_data = generate_ox_quiz(grade=grade, unit=unit, count=target_count)
            for item in raw_data:
                new_items.append((
                    grade, f"{grade}학년", unit, "",
                    "ox", "하", 1, item.get("question", ""),
                    "[]", str(item.get("answer", "O")),
                    item.get("explanation", ""), "auto_refill"
                ))
        elif question_type == "subjective":
            res = generate_subjective_quiz(grade=grade, unit=unit, count=target_count)
            for item in res.get("items", []):
                ans = str(item.get("model_answer", "")).strip()
                q_type = "서술형" if len(ans) > 15 else "단답형"
                pts = 5 if q_type == "서술형" else 3
                new_items.append((
                    grade, f"{grade}학년", unit, "",
                    q_type, "상" if q_type == "서술형" else "중", pts, item.get("question", ""),
                    "[]", ans,
                    item.get("explanation", "") or item.get("grading_criteria", ""), "auto_refill"
                ))
        else:  # mcq 또는 all
            raw_data = generate_mcq_quiz(grade=grade, unit=unit, count=target_count)
            for item in raw_data:
                opts = item.get("options", [])
                ans = str(item.get("answer", 1))
                new_items.append((
                    grade, f"{grade}학년", unit, "",
                    "객관식", "중", 3, item.get("question", ""),
                    json.dumps(opts, ensure_ascii=False), ans,
                    item.get("explanation", ""), "auto_refill"
                ))

        if new_items:
            conn = _get_conn()
            try:
                cur = conn.cursor()

                # 1) 현재 단원에 저장된 기존 문제 목록 (1순위: 이미 풀었던 헌 문제, 2순위: 가장 오래된 문제 순)
                cur.execute(
                    """
                    SELECT q.id, 
                           CASE WHEN s.id IS NOT NULL THEN 1 ELSE 2 END as is_solved
                    FROM question_bank q
                    LEFT JOIN question_bank_solved s ON q.id = s.bank_id
                    WHERE q.subject = ? AND q.grade = ? AND q.unit_name = ?
                    ORDER BY is_solved ASC, q.id ASC
                    """,
                    (SUBJECT_NAME, grade, unit)
                )
                existing_rows = cur.fetchall()
                curr_total = len(existing_rows)

                # 2) 30개 초과분 계산 -> 학생이 이미 푼 헌 문제부터 우선 삭제!
                overflow = (curr_total + len(new_items)) - MAX_UNIT_QUESTIONS
                if overflow > 0:
                    delete_targets = [r["id"] for r in existing_rows[:overflow]]
                    if delete_targets:
                        placeholders = ",".join("?" * len(delete_targets))
                        cur.execute(
                            f"DELETE FROM question_bank_solved WHERE bank_id IN ({placeholders})",
                            delete_targets
                        )
                        cur.execute(
                            f"DELETE FROM question_bank WHERE id IN ({placeholders})",
                            delete_targets
                        )
                        print(f"[문제은행 스마트 순환 삭제] [{unit}] 단원 30개 유지: 학생이 이미 풀었던 헌 문제 {len(delete_targets)}개를 우선 삭제하고 새 문제로 교체합니다.")

                # 3) 신규 생성 문제 INSERT
                inserted_count = 0
                for item in new_items:
                    # 중복 지문 체크
                    cur.execute(
                        "SELECT 1 FROM question_bank WHERE subject = ? AND question_text = ?",
                        (SUBJECT_NAME, item[7])
                    )
                    if cur.fetchone():
                        continue

                    cur.execute(
                        """
                        INSERT INTO question_bank (
                            subject, grade, grade_group, unit_name, sub_topic,
                            question_type, difficulty, points, question_text,
                            choices_json, correct_answer, explanation, source_type,
                            created_by, created_by_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai_system', 'AI 자동 리필봇')
                        """,
                        (SUBJECT_NAME,) + item
                    )
                    inserted_count += 1
                conn.commit()

                cur.execute(
                    "SELECT COUNT(*) FROM question_bank WHERE subject = ? AND grade = ? AND unit_name = ?",
                    (SUBJECT_NAME, grade, unit)
                )
                final_total = cur.fetchone()[0]
                print(f"[문제은행 자동 리필 완료] [{unit}] 단원에 신규 문제 {inserted_count}개가 충전되었습니다! (현재 총 {final_total}/{MAX_UNIT_QUESTIONS}개)")
            finally:
                conn.close()
    except Exception as e:
        print(f"[문제은행 자동 리필 오류] {e}")
    finally:
        with _refilling_lock:
            _refilling_keys.discard(lock_key)


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
    동시에 소진율 70% 도달 시 백그라운드 자동 리필 트리거
    반환값: (questions, is_review_mode, message)
    """
    init_question_bank_db()
    conn = _get_conn()
    clean_user = (user_key or "김에듀").strip()

    # 단원 선택 시 소진율 선제 검사 및 자동 리필 가동
    if unit and unit != "총정리":
        check_and_trigger_auto_refill(grade, unit, question_type, clean_user)

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

        # 1. 현재 미풀이 문제 수 조회
        query_unsolved_count = f"""
            SELECT COUNT(*) FROM question_bank
            WHERE subject = ? AND grade = ? {unit_filter} {type_filter}
              AND id NOT IN (
                  SELECT bank_id FROM question_bank_solved
                  WHERE subject = ? AND user_key = ?
              )
        """
        cur.execute(query_unsolved_count, list(params) + [SUBJECT_NAME, clean_user])
        unsolved_cnt = cur.fetchone()[0]

        # 2. [핵심] 10문제를 낼 수 없으면 (미풀이 문제 < count) 즉시 FIFO 순환 리필 가동!
        # (30개 한도에 도달했더라도 가장 오래된 문제부터 삭제하고 새 15문제를 즉시 채워 넣음)
        if unsolved_cnt < count and unit and unit != "총정리":
            lock_key = (grade, unit, question_type)
            print(f"[즉시 출제 리필] [{unit}] 단원 미풀이 문제가 {unsolved_cnt}개로 10문제 미달 -> 가장 오래된 문제부터 삭제하고 AI 15문제 즉시 충전")
            try:
                _auto_refill_worker(grade, unit, question_type, lock_key, REFILL_BATCH_SIZE)
            except Exception as e_refill:
                print(f"[즉시 출제 리필 예외] {e_refill}")

        # 3. 리필 후 미풀이 문제 조회 (10문제 온전히 추출)
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

        if len(unsolved_rows) >= count:
            formatted = [_format_bank_item(r) for r in unsolved_rows[:count]]
            return formatted, False, "미풀이 문제은행 출제"

        # 4. 미풀이 문제가 10개 미만인 경우 (단원 최대 한도 30개 도달 후 거의 다 풀었을 때)
        # 부족한 개수만큼 기풀이 문제(복습 모드)를 보충하여 무조건 10문제를 완성
        needed = count - len(unsolved_rows)
        existing_ids = [r["id"] for r in unsolved_rows]
        id_placeholder = f"AND id NOT IN ({','.join(['?']*len(existing_ids))})" if existing_ids else ""

        query_review = f"""
            SELECT * FROM question_bank
            WHERE subject = ? AND grade = ? {unit_filter} {type_filter} {id_placeholder}
            ORDER BY RANDOM()
            LIMIT ?
        """
        cur.execute(query_review, list(params) + existing_ids + [needed])
        review_rows = [dict(r) for r in cur.fetchall()]

        combined_rows = unsolved_rows + review_rows
        if combined_rows:
            is_review = len(unsolved_rows) < count
            msg = "미풀이 문제와 복습 문제가 함께 출제되었습니다." if is_review else "문제은행 출제"
            formatted = [_format_bank_item(r) for r in combined_rows[:count]]
            return formatted, is_review, msg

        # 5. 문제은행에 단 1문제도 없는 경우
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
    """학생이 문제은행 문제를 맞혔을 때 완료 기록 저장 및 소진율 감지 자동 리필 연동"""
    init_question_bank_db()
    conn = _get_conn()
    clean_subj = subject or SUBJECT_NAME
    clean_user = (user_key or "김에듀").strip()
    grade = 4
    unit_name = ""
    q_type = "all"
    try:
        cur = conn.cursor()
        # 문제의 학년, 단원, 유형 파악
        cur.execute("SELECT grade, unit_name, question_type FROM question_bank WHERE id = ?", (bank_id,))
        row = cur.fetchone()
        if row:
            grade = row["grade"]
            unit_name = row["unit_name"]
            q_type = row["question_type"]

        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key, solved_at)
            VALUES (?, ?, ?, DATETIME('now', 'localtime'))
            """,
            (bank_id, clean_subj, clean_user)
        )
        conn.commit()
    except Exception as e:
        print(f"[문제은행 풀이 기록 오류] {e}")
        return False
    finally:
        conn.close()

    # 정답 맞춤 후 해당 단원 소진율 70% 도달 여부 점검 및 비동기 자동 리필 가동
    if unit_name:
        check_and_trigger_auto_refill(grade, unit_name, q_type, clean_user)

    return True


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
        try:
            from .service import ensure_client
        except Exception:
            from service import ensure_client
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

