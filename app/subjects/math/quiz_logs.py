"""
================================================================================
[EduMate AI 초등수학 과목 전용 DB 모듈 - app/subjects/math/quiz_logs.py]
================================================================================
- 팀원 배포용 표준 템플릿(sample/quiz_logs.py)을 100% 준수한 초등수학 과목 모듈입니다.
- SUBJECT_NAME = "math" 표준 설정.
- 공통 플랫폼 관제탑(계정 관리, 비밀번호 초기화, 전과목 랭킹)은 app/database/quiz_manager.py로 독립 분리되었습니다.
- 본 모듈은 순수하게 초등수학 문제 풀이 로그 기록 및 수학 학습 이력/즐겨찾기/챗 히스토리 관리를 전담합니다.
================================================================================
"""

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 과목 영문 식별자: 초등수학
SUBJECT_NAME = "math"

# 아직 문제를 풀지 않은 학생의 학년 선택값을 유지하기 위한 메모리 캐시
_USER_GRADE_CACHE: Dict[str, int] = {"김에듀": 4, "마스터": 6}


def _resolve_db_path() -> Path:
    """
    [단독 폴더 환경 & 통합 프로젝트 환경 100% 자동 호환 경로 탐색기]
    - 경우 1 (조장님 통합 환경): 상위 폴더에 app/main.py가 존재하면 루트의 data/edumate.db를 자동 생성/연결합니다.
    - 경우 2 (단독 폴더 환경): data 폴더나 상위 프로젝트 폴더 없이 단독으로 실행 시 현재 폴더에 edumate.db 자동 생성.
    """
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir.parent.parent.parent, current_dir.parent.parent, current_dir.parent]:
        if (parent / "app" / "main.py").exists():
            data_dir = parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir / "edumate.db"
    return current_dir / "edumate.db"


DB_PATH = _resolve_db_path()

# 패키지 임포트 지원을 위한 프로젝트 루트 추가
_proj_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_proj_root) not in sys.path:
    sys.path.insert(0, str(_proj_root))

try:
    from app.database.quiz_manager import (
        POKEMON_TYPE_CONFIG,
        STAGE_TIER_EXP_TABLE,
        calculate_level_tier,
        get_or_create_user,
    )
except ImportError:
    from sample.quiz_logs import (
        POKEMON_TYPE_CONFIG,
        STAGE_TIER_EXP_TABLE,
        calculate_level_tier,
    )

    def get_or_create_user(user_name="김에듀", grade=None, pokemon_type=None):
        return get_user_status(user_name, grade, pokemon_type or "grass")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    """전 과목 공통 표준 테이블(quiz_logs) 및 계정 테이블(accounts) 자동 생성"""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id TEXT NOT NULL DEFAULT '',
                user_name TEXT NOT NULL DEFAULT '김에듀',
                grade INTEGER DEFAULT NULL,
                subject TEXT NOT NULL DEFAULT 'math',
                unit TEXT DEFAULT NULL,
                topic TEXT DEFAULT NULL,
                difficulty TEXT DEFAULT NULL,
                question_type TEXT DEFAULT NULL,
                question TEXT NOT NULL DEFAULT '',
                user_answer TEXT DEFAULT NULL,
                correct_answer TEXT DEFAULT NULL,
                solution TEXT DEFAULT NULL,
                earned_score INTEGER NOT NULL DEFAULT 0,
                is_correct INTEGER NOT NULL DEFAULT 0,
                is_favorite INTEGER DEFAULT NULL,
                chat_history TEXT DEFAULT NULL,
                solved_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        try:
            cur.execute("ALTER TABLE quiz_logs ADD COLUMN user_id TEXT DEFAULT NULL")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE quiz_logs ADD COLUMN choices_json TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE quiz_logs ADD COLUMN visual_data_json TEXT DEFAULT '{}'")
        except Exception:
            pass
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_subj ON quiz_logs (user_name, subject)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_quiz_id ON quiz_logs (user_name, quiz_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_id ON quiz_logs (user_id)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                user_name TEXT NOT NULL,
                grade INTEGER NOT NULL DEFAULT 4,
                role TEXT NOT NULL DEFAULT 'student',
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


init_math_db = init_db


def get_user_status(user_name: str = "김에듀", grade: Optional[int] = None, pokemon_type: str = "grass", user_id: Optional[str] = None) -> Dict[str, Any]:
    """초등수학 과목 점수 및 전 과목 통합 누적 점수 실시간 조회"""
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()
    if clean_id.lower() == "guest" or (not clean_id and clean_name.lower() in ("게스트", "guest")):
        resolved_grade = int(grade) if (grade and 1 <= grade <= 6) else 4
        level_info = calculate_level_tier(0, pokemon_type=pokemon_type)
        return {
            "user_id": "guest",
            "user_name": clean_name if clean_name.lower() not in ("게스트", "guest") else "게스트",
            "grade": resolved_grade,
            "subject_score": 0,
            "total_score": 0,
            "level_info": level_info,
        }

    if grade is not None and 1 <= grade <= 6:
        _USER_GRADE_CACHE[clean_name] = int(grade)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id:
            user_cond = "((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))"
            p_args = (clean_id, clean_name, clean_id, clean_name)
        else:
            user_cond = "user_name = ?"
            p_args = (clean_name, clean_name)

        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN LOWER(subject) = 'math' THEN earned_score ELSE 0 END), 0) AS subject_score,
                COALESCE(SUM(earned_score), 0) AS total_score,
                (SELECT grade FROM quiz_logs WHERE {user_cond} AND grade IS NOT NULL ORDER BY id DESC LIMIT 1) AS latest_grade
            FROM quiz_logs
            WHERE {user_cond}
            """,
            p_args,
        )
        row = cur.fetchone()
        db_grade = row["latest_grade"] if (row and row["latest_grade"]) else None
        resolved_grade = (
            int(grade)
            if (grade and 1 <= grade <= 6)
            else (_USER_GRADE_CACHE.get(clean_name) or (int(db_grade) if db_grade else 4))
        )
        _USER_GRADE_CACHE[clean_name] = resolved_grade
        integrated_score = int(row["total_score"]) if row else 0
        level_info = calculate_level_tier(integrated_score, pokemon_type=pokemon_type)
        return {
            "user_id": clean_id or "guest",
            "user_name": clean_name,
            "grade": resolved_grade,
            "subject_score": int(row["subject_score"]) if row else 0,
            "total_score": integrated_score,
            "level_info": level_info,
        }
    finally:
        conn.close()


def save_quiz_log(
    user_name: str = "김에듀",
    quiz_id: Optional[str] = None,
    grade: Optional[int] = None,
    unit: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
    question_type: Optional[str] = None,
    question: str = "",
    user_answer: Optional[str] = None,
    correct_answer: Optional[str] = None,
    solution: Optional[str] = None,
    earned_score: int = 0,
    max_score: Optional[int] = None,
    is_correct: bool = False,
    is_favorite: Optional[int] = None,
    chat_history: Optional[str] = None,
    is_solution_revealed: bool = False,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """초등수학 채점 결과를 통합 quiz_logs 테이블에 안전하게 기록 (차액 누적 & user_id 연동, 게스트는 DB 미저장)"""
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or kwargs.get("user_id") or "").strip()
    grade_val = None
    if grade is not None:
        try:
            g = int(grade)
            if 1 <= g <= 6:
                grade_val = g
                _USER_GRADE_CACHE[clean_name] = g
        except (ValueError, TypeError):
            pass
    effective_grade = grade_val if grade_val is not None else _USER_GRADE_CACHE.get(clean_name, 4)
    now = _now_str()
    effective_quiz_id = quiz_id or f"{SUBJECT_NAME}_{now}_{question[:20]}"

    capped_earned = max(0, int(earned_score))
    if max_score is not None and max_score > 0:
        capped_earned = min(capped_earned, int(max_score))

    is_guest = (
        clean_id.lower() == "guest"
        or clean_id.lower().startswith("guest_")
        or (not clean_id and clean_name.lower() in ("게스트", "guest"))
        or kwargs.get("is_guest") is True
        or kwargs.get("role") == "guest"
    )
    if is_guest and not clean_id:
        clean_id = "guest"

    conn = _get_conn()
    try:
        cur = conn.cursor()
        if not clean_id:
            try:
                cur.execute("SELECT user_id FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1", (clean_name,))
                a_row = cur.fetchone()
                if a_row:
                    clean_id = a_row["user_id"]
            except Exception:
                pass

        user_cond = "((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))" if clean_id else "user_name = ?"
        user_params = [clean_id, clean_name] if clean_id else [clean_name]

        cur.execute(
            f"""
            SELECT id, earned_score, is_correct
            FROM quiz_logs
            WHERE {user_cond} AND subject = ? AND quiz_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            tuple(user_params + [SUBJECT_NAME, effective_quiz_id]),
        )
        existing = cur.fetchone()

        raw_options = kwargs.get("options") or kwargs.get("choices") or []
        try:
            choices_json_str = json.dumps(raw_options if isinstance(raw_options, list) else [], ensure_ascii=False)
        except Exception:
            choices_json_str = "[]"

        raw_visual_data = kwargs.get("visual_data")
        raw_dir_footer = kwargs.get("direction_footer") or ""
        raw_rubric = kwargs.get("rubric") or []
        visual_meta_obj = {
            "_wrapped_meta": True,
            "visual_data": raw_visual_data if isinstance(raw_visual_data, (dict, list)) else {"type": "none"},
            "direction_footer": str(raw_dir_footer or ""),
            "rubric": raw_rubric if isinstance(raw_rubric, list) else [],
        }
        try:
            visual_data_json_str = json.dumps(visual_meta_obj, ensure_ascii=False)
        except Exception:
            visual_data_json_str = "{}"

        added_score = 0
        if existing:
            log_id = existing["id"]
            prev_best = int(existing["earned_score"] or 0)
            if not is_solution_revealed and capped_earned > prev_best:
                added_score = capped_earned - prev_best
                new_best = capped_earned
            else:
                new_best = prev_best

            new_is_correct = 1 if (is_correct or existing["is_correct"]) else 0
            cur.execute(
                """
                UPDATE quiz_logs
                SET grade = ?, user_answer = ?, earned_score = ?, is_correct = ?, solved_at = ?, user_id = COALESCE(?, user_id),
                    choices_json = CASE WHEN ? != '[]' THEN ? ELSE COALESCE(choices_json, '[]') END,
                    visual_data_json = CASE WHEN ? != '{}' THEN ? ELSE COALESCE(visual_data_json, '{}') END
                WHERE id = ?
                """,
                (
                    effective_grade,
                    user_answer,
                    new_best,
                    new_is_correct,
                    now,
                    clean_id or None,
                    choices_json_str,
                    choices_json_str,
                    visual_data_json_str,
                    visual_data_json_str,
                    log_id,
                ),
            )
            best_score = new_best
        else:
            added_score = 0 if is_solution_revealed else capped_earned
            best_score = added_score
            cur.execute(
                """
                INSERT INTO quiz_logs (
                    quiz_id, user_id, user_name, grade, subject, unit, topic,
                    difficulty, question_type, question, user_answer,
                    correct_answer, solution, earned_score, is_correct,
                    is_favorite, chat_history, solved_at, choices_json, visual_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    effective_quiz_id,
                    clean_id or None,
                    clean_name,
                    effective_grade,
                    SUBJECT_NAME,
                    unit,
                    topic,
                    difficulty,
                    question_type,
                    question or "",
                    user_answer,
                    correct_answer,
                    solution,
                    best_score,
                    1 if is_correct else 0,
                    is_favorite or 0,
                    chat_history or "[]",
                    now,
                    choices_json_str,
                    visual_data_json_str,
                ),
            )
            log_id = cur.lastrowid

        conn.commit()
    finally:
        conn.close()

    status = get_user_status(clean_name, _USER_GRADE_CACHE.get(clean_name, 4), user_id=clean_id)
    return {
        "log_id": log_id,
        "quiz_id": effective_quiz_id,
        "added_score": added_score,
        "best_score": best_score,
        "subject_score": status["subject_score"],
        "total_score": status["total_score"],
        "level_info": status.get("level_info"),
    }


# 라우터 호환용 별칭
save_or_update_quiz_log = save_quiz_log


def get_recent_logs_for_custom(user_name: str = "김에듀", limit: int = 30, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """'🌟 맞춤문제' 출제 시 DB(quiz_logs)에서 해당 학생의 최근 수학 풀이/오답 기록을 조회 (user_id 우선 매칭, 비회원은 빈 목록)"""
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()
    is_guest = (clean_id.lower() == "guest") or (clean_id.lower().startswith("guest_")) or (not clean_id and clean_name.lower() in ("게스트", "guest"))
    if is_guest:
        return []

    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id:
            user_cond = "((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))"
            params = [clean_id, clean_name, SUBJECT_NAME, limit]
        else:
            user_cond = "user_name = ?"
            params = [clean_name, SUBJECT_NAME, limit]

        cur.execute(
            f"""
            SELECT grade, unit, topic, difficulty, question_type, is_correct, earned_score
            FROM quiz_logs
            WHERE {user_cond} AND subject = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [
            {
                "grade": r["grade"],
                "unit": r["unit"],
                "topic": r["topic"],
                "difficulty": r["difficulty"],
                "question_type": r["question_type"],
                "is_correct": bool(r["is_correct"]),
                "earned_score": r["earned_score"],
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


get_user_quiz_logs_for_custom = get_recent_logs_for_custom


def toggle_favorite_log(
    log_id: Optional[int] = None,
    is_favorite: Optional[bool] = None,
    user_name: Optional[str] = None,
    quiz_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """특정 문제 풀이 로그의 ⭐ 즐겨찾기 상태를 토글 (게스트는 메모리 응답)"""
    clean_id = (user_id or "").strip()
    is_guest = (clean_id.lower() == "guest") or (clean_id.lower().startswith("guest_")) or (not clean_id and user_name and user_name.strip().lower() in ("게스트", "guest"))
    if (log_id and int(log_id) <= 0) or is_guest:
        return {"log_id": 0, "is_favorite": 1 if is_favorite else 0}

    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        row = None
        if log_id:
            cur.execute("SELECT id, is_favorite FROM quiz_logs WHERE id = ?", (log_id,))
            row = cur.fetchone()
        if not row and user_name and quiz_id:
            cur.execute(
                "SELECT id, is_favorite FROM quiz_logs WHERE user_name = ? AND quiz_id = ? ORDER BY id DESC LIMIT 1",
                (user_name.strip(), quiz_id.strip()),
            )
            row = cur.fetchone()
        if not row and user_name:
            cur.execute(
                "SELECT id, is_favorite FROM quiz_logs WHERE user_name = ? AND subject = ? ORDER BY id DESC LIMIT 1",
                (user_name.strip(), SUBJECT_NAME),
            )
            row = cur.fetchone()
        if not row:
            raise ValueError("해당 풀이 기록을 찾을 수 없습니다.")

        target_id = row["id"]
        new_fav = (1 if is_favorite else 0) if is_favorite is not None else (0 if row["is_favorite"] else 1)
        cur.execute("UPDATE quiz_logs SET is_favorite = ? WHERE id = ?", (new_fav, target_id))
        conn.commit()
        return {"log_id": target_id, "is_favorite": int(new_fav)}
    finally:
        conn.close()


def append_chat_message(log_id: int, role: str, content: str) -> List[Dict[str, Any]]:
    """특정 문제 풀이 로그에 💬 AI 선생님과의 추가 대화 내역 저장 (비회원은 메모리 유지)"""
    normalized_role = "student" if role in ("user", "student") else "teacher"
    if not log_id or int(log_id) <= 0:
        return [{"role": normalized_role, "content": content, "timestamp": _now_str()}]

    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT chat_history FROM quiz_logs WHERE id = ?", (log_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"해당 풀이 기록(ID: {log_id})을 찾을 수 없습니다.")


        try:
            history = json.loads(row["chat_history"] or "[]")
        except Exception:
            history = []

        history.append({"role": normalized_role, "content": content, "timestamp": _now_str()})
        cur.execute(
            "UPDATE quiz_logs SET chat_history = ? WHERE id = ?",
            (json.dumps(history, ensure_ascii=False), log_id),
        )
        conn.commit()
        return history
    finally:
        conn.close()


def get_quiz_log_by_id(
    log_id: Optional[int] = None,
    user_name: Optional[str] = None,
    quiz_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """특정 문제 풀이 로그 1건 상세 조회"""
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        row = None
        if log_id:
            cur.execute("SELECT * FROM quiz_logs WHERE id = ?", (log_id,))
            row = cur.fetchone()
        if not row and user_name and quiz_id:
            cur.execute(
                "SELECT * FROM quiz_logs WHERE user_name = ? AND quiz_id = ? ORDER BY id DESC LIMIT 1",
                (user_name.strip(), quiz_id.strip()),
            )
            row = cur.fetchone()
        if not row and user_name:
            cur.execute(
                "SELECT * FROM quiz_logs WHERE user_name = ? AND subject = ? ORDER BY id DESC LIMIT 1",
                (user_name.strip(), SUBJECT_NAME),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def grant_full_score_by_tutor(
    log_id: Optional[int] = None,
    user_name: Optional[str] = None,
    user_id: Optional[str] = None,
    quiz_id: Optional[str] = None,
    target_score: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    AI 선생님이 질문 대화 중 '출제 오류' 또는 '학생의 답안/논리가 실제로 정답 또는 부분점수 대상임'을 인정했을 때,
    해당 문제 풀이 기록(quiz_logs)의 점수를 정정하고 차액 점수를 반영한 최신 누적 점수 및 상태를 반환합니다.
    """
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()
    if clean_id.lower() == "guest" or (log_id and int(log_id) <= 0):
        t_score = target_score or 5
        return {
            "log_id": 0,
            "added_score": t_score,
            "best_score": t_score,
            "max_score": t_score,
            "total_score": 0,
            "subject_score": 0,
            "user_status": get_user_status(clean_name, 4, user_id="guest"),
        }

    conn = _get_conn()
    try:
        cur = conn.cursor()
        row = None
        if log_id:
            cur.execute("SELECT * FROM quiz_logs WHERE id = ?", (log_id,))
            row = cur.fetchone()
        if not row and quiz_id:
            if clean_id:
                cur.execute(
                    "SELECT * FROM quiz_logs WHERE ((user_id = ?) OR (user_name = ?)) AND quiz_id = ? ORDER BY id DESC LIMIT 1",
                    (clean_id, clean_name, quiz_id.strip()),
                )
            else:
                cur.execute(
                    "SELECT * FROM quiz_logs WHERE user_name = ? AND quiz_id = ? ORDER BY id DESC LIMIT 1",
                    (clean_name, quiz_id.strip()),
                )
            row = cur.fetchone()
        if not row:
            return None

        target_id = row["id"]
        diff_val = row["difficulty"] or "중"
        max_score = 5 if diff_val == "상" else (1 if diff_val == "하" else 3)
        prev_earned = int(row["earned_score"] or 0)

        if target_score is not None and target_score > 0:
            new_score = min(max_score, max(prev_earned, target_score))
        else:
            new_score = max_score

        new_is_correct = 1 if new_score >= max_score else (1 if prev_earned > 0 or new_score > 0 else 0)
        added_score = max(0, new_score - prev_earned)

        cur.execute(
            """
            UPDATE quiz_logs
            SET earned_score = ?, is_correct = ?
            WHERE id = ?
            """,
            (new_score, new_is_correct, target_id),
        )
        conn.commit()
    finally:
        conn.close()

    status = get_user_status(clean_name, _USER_GRADE_CACHE.get(clean_name, 4), user_id=clean_id)
    return {
        "log_id": target_id,
        "added_score": added_score,
        "best_score": new_score,
        "max_score": max_score,
        "total_score": status["total_score"],
        "subject_score": status["subject_score"],
        "user_status": status,
    }


def get_user_study_history(
    user_name: str = "김에듀",
    favorites_only: bool = False,
    subject_filter: str = "all",
    target_date: Optional[str] = None,
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """학생의 공부 기록 및 즐겨찾기 조회 (user_id 우선 분리, 전과목/과목별/날짜별 필터 및 전체 표시 지원, 비회원은 빈 목록)"""
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()
    is_guest = (clean_id.lower() == "guest") or (clean_id.lower().startswith("guest_")) or (not clean_id and clean_name.lower() in ("게스트", "guest"))
    if is_guest:
        return []

    subj_key = (subject_filter or "all").strip().lower()

    aliases_map = {
        "korean": ("korean", "kor", "국어", "초등국어"),
        "math": ("math", "수학", "초등수학"),
        "english": ("english", "eng", "영어", "초등영어"),
        "social": ("social", "soc", "society", "사회", "초등사회"),
        "science": ("science", "sci", "과학", "초등과학"),
        "hanja": ("hanja", "한자", "초등한자", "한문", "초등한문"),
    }

    conn = _get_conn()
    try:
        cur = conn.cursor()
        clauses = []
        params: List[Any] = []
        if clean_id:
            clauses.append("((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))")
            params.extend([clean_id, clean_name])
        else:
            clauses.append("user_name = ?")
            params.append(clean_name)

        if subj_key not in ("all", "", "전과목"):
            aliases = aliases_map.get(subj_key, (subj_key,))
            placeholders = ", ".join(["?"] * len(aliases))
            clauses.append(f"LOWER(subject) IN ({placeholders})")
            params.extend([a.lower() for a in aliases])

        if favorites_only:
            clauses.append("is_favorite = 1")

        if target_date and str(target_date).strip():
            clean_date = str(target_date).strip()
            clauses.append("solved_at LIKE ?")
            params.append(f"{clean_date}%")

        where_sql = " AND ".join(clauses)

        if limit is not None and int(limit) > 0:
            query = f"""
            SELECT * FROM quiz_logs
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """
            params.append(int(limit))
        else:
            query = f"""
            SELECT * FROM quiz_logs
            WHERE {where_sql}
            ORDER BY id DESC
            """

        cur.execute(query, tuple(params))
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _extract_visual_meta_from_question(q_text: str) -> tuple[str, Dict[str, Any], str]:
    """구형 로그 중 지문 끝에 [위에서 본 모양에 수를 쓴 모양] 텍스트가 합쳐져 있는 경우 2D 격자 및 방향 복원"""
    if not q_text:
        return "", {"type": "none"}, ""
    clean_q = q_text
    visual_data: Dict[str, Any] = {"type": "none"}
    direction_footer = ""

    block_m = re.search(
        r"\[위에서\s*본\s*모양에?\s*(?:수를?\s*쓴\s*모양|수\s*표기)?\]\s*([\s\d\r\n]+)",
        clean_q,
    )
    if block_m:
        raw_grid_text = block_m.group(1).strip()
        lines = [line.strip() for line in raw_grid_text.splitlines() if line.strip()]
        grid_2d = []
        for line in lines:
            nums = [int(n) for n in re.findall(r"\d+", line)]
            if nums:
                grid_2d.append(nums)
        if grid_2d:
            max_c = max(len(r) for r in grid_2d)
            for r in grid_2d:
                while len(r) < max_c:
                    r.append(0)
            visual_data = {
                "type": "grid",
                "rows": grid_2d,
                "label": "위에서 본 모양 (수 표기)",
                "title": "위에서 본 모양 (수 표기)",
            }
            clean_q = clean_q[: block_m.start()].strip()

    if "옆" in clean_q or "오른쪽" in clean_q:
        direction_footer = "앞 ◀ ▶ 뒤"
    else:
        direction_footer = "왼쪽 ◀ ▶ 오른쪽"

    return clean_q, visual_data, direction_footer


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    row_keys = row.keys() if hasattr(row, "keys") else []
    try:
        raw_chat = json.loads(row["chat_history"] or "[]")
        chat_history = [
            {
                "role": "student" if m.get("role") in ("user", "student") else "teacher",
                "content": m.get("content") or m.get("message") or "",
                "timestamp": m.get("timestamp") or m.get("time") or "",
            }
            for m in raw_chat
            if isinstance(m, dict)
        ]
    except Exception:
        chat_history = []

    grade_val = int(row["grade"]) if row["grade"] is not None else None
    grade_group = (
        ""
        if grade_val is None
        else ("1~2학년군" if grade_val <= 2 else ("3~4학년군" if grade_val <= 4 else "5~6학년군"))
    )
    diff_val = row["difficulty"]
    max_score = 5 if diff_val == "상" else (1 if diff_val == "하" else 3)

    raw_question = row["question"] or ""
    q_type = row["question_type"] or ""

    # 시각자료 및 보기 복원
    visual_data: Any = {"type": "none"}
    direction_footer = ""
    rubric: List[Any] = []
    choices: List[Any] = []

    if "visual_data_json" in row_keys and row["visual_data_json"]:
        try:
            parsed_v = json.loads(row["visual_data_json"])
            if isinstance(parsed_v, dict):
                visual_data = parsed_v.get("visual_data", parsed_v)
                direction_footer = parsed_v.get("direction_footer", "")
                rubric = parsed_v.get("rubric", [])
            elif isinstance(parsed_v, list):
                visual_data = parsed_v
        except Exception:
            visual_data = {"type": "none"}

    if "choices_json" in row_keys and row["choices_json"]:
        try:
            parsed_c = json.loads(row["choices_json"])
            if isinstance(parsed_c, list):
                choices = parsed_c
        except Exception:
            choices = []

    # 구형 로그 또는 visual_data가 비어있는데 지문에 쌓기나무 텍스트 블록이 포함된 경우 자동 추출
    clean_question = raw_question
    if not visual_data or (isinstance(visual_data, dict) and visual_data.get("type") in (None, "none", "")):
        cq, ev, ed = _extract_visual_meta_from_question(raw_question)
        if isinstance(ev, dict) and ev.get("type") != "none":
            clean_question = cq
            visual_data = ev
            if not direction_footer:
                direction_footer = ed

    if q_type == "단답형 주관식 2" and not direction_footer:
        direction_footer = "앞 ◀ ▶ 뒤" if "옆" in clean_question else "왼쪽 ◀ ▶ 오른쪽"

    return {
        "id": row["id"],
        "quiz_id": row["quiz_id"],
        "user_name": row["user_name"],
        "grade": grade_val,
        "grade_group": grade_group,
        "subject": row["subject"] or "math",
        "unit": row["unit"] or "",
        "topic": row["topic"] or "",
        "difficulty": diff_val or "",
        "question_type": q_type,
        "question": clean_question,
        "raw_question": raw_question,
        "user_answer": row["user_answer"] or "",
        "correct_answer": row["correct_answer"] or "",
        "solution": row["solution"] or "",
        "earned_score": int(row["earned_score"] or 0),
        "max_score": max_score,
        "is_correct": 1 if row["is_correct"] else 0,
        "is_favorite": 1 if row["is_favorite"] else 0,
        "chat_history": chat_history,
        "choices": choices,
        "options": choices,
        "visual_data": visual_data,
        "direction_footer": direction_footer,
        "rubric": rubric,
        "solved_at": row["solved_at"] or "",
        "created_at": row["solved_at"] or "",
    }
