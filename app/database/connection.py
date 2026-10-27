import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# [전 과목 통합 DB] data/edumate.db
# - 국어, 영어, 수학, 사회, 과학, 한문 등 모든 과목이 단일 테이블(quiz_logs)을 공유합니다.
# - 별도의 회원 점수 테이블을 두지 않고, quiz_logs의 earned_score 합계(SUM)로
#   과목별 점수 및 전 과목 통합 총점을 실시간 산출하여 데이터 불일치를 원천 차단합니다.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INTEGRATED_DB_PATH = DATA_DIR / "edumate.db"


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or INTEGRATED_DB_PATH
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_integrated_db(db_path: Optional[Path] = None) -> None:
    """
    전 과목 통합 표준 테이블(quiz_logs) 및 계정 테이블(accounts) 초기화
    - 해당 사항이 없는 선택 컬럼은 숫자 0 대신 전용 결측값(NULL / 파이썬 None)을 저장합니다.
    """
    conn = get_db_connection(db_path)
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_subj ON quiz_logs (user_name, subject)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_quiz_id ON quiz_logs (user_name, quiz_id)"
        )

        # 로그인 및 마스터 관리자 계정 테이블 초기화
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
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 마스터 관리자 계정 기본 시드 (아이디: master / 비번: 1234 / 이름: 마스터 / 학년: 6학년)
        cur.execute("UPDATE accounts SET user_id = 'master' WHERE user_id = '1234'")
        cur.execute(
            """
            INSERT OR IGNORE INTO accounts (user_id, password, user_name, grade, role, created_at)
            VALUES ('master', '1234', '마스터', 6, 'admin', ?)
            """,
            (now,),
        )
        conn.commit()
    finally:
        conn.close()


def get_integrated_student_report(user_name: str = "김에듀") -> Dict[str, Any]:
    """
    [통합과목 AI 튜터 & 메인 대시보드 전용 조회 함수]
    학생 1명의 전 과목 총점, 과목별 획득 점수·정답률, 과목별 취약 단원(오답 목록)을 한 번에 조회합니다.
    """
    init_integrated_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # 1) 최근 학습 학년 및 전 과목 누적 총점 조회
        cur.execute(
            """
            SELECT
                COALESCE(SUM(earned_score), 0) AS total_score,
                COUNT(*) AS total_solved,
                (SELECT grade FROM quiz_logs WHERE user_name = ? ORDER BY id DESC LIMIT 1) AS latest_grade
            FROM quiz_logs
            WHERE user_name = ?
            """,
            (clean_name, clean_name),
        )
        summary_row = cur.fetchone()
        total_score = int(summary_row["total_score"]) if summary_row else 0
        total_solved = int(summary_row["total_solved"]) if summary_row else 0
        latest_grade = int(summary_row["latest_grade"]) if (summary_row and summary_row["latest_grade"]) else 4

        # 2) 과목별 점수 및 정답률 집계
        cur.execute(
            """
            SELECT
                subject,
                COUNT(*) AS solved_count,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_count,
                COALESCE(SUM(earned_score), 0) AS subject_score
            FROM quiz_logs
            WHERE user_name = ?
            GROUP BY subject
            """,
            (clean_name,),
        )
        subject_stats = [
            {
                "subject": r["subject"],
                "solved_count": r["solved_count"],
                "correct_count": r["correct_count"],
                "subject_score": r["subject_score"],
                "accuracy": round((r["correct_count"] / r["solved_count"]) * 100, 1) if r["solved_count"] else 0.0,
            }
            for r in cur.fetchall()
        ]

        # 3) 전 과목 최근 오답(취약 단원·주제) 내역 조회 (통합 튜터 상담 및 맞춤 복습용)
        cur.execute(
            """
            SELECT subject, unit, topic, difficulty, question_type, solved_at
            FROM quiz_logs
            WHERE user_name = ? AND is_correct = 0
            ORDER BY id DESC
            LIMIT 15
            """,
            (clean_name,),
        )
        weak_points = [dict(r) for r in cur.fetchall()]

        return {
            "user_name": clean_name,
            "grade": latest_grade,
            "total_score": total_score,
            "total_solved": total_solved,
            "subject_stats": subject_stats,
            "weak_points": weak_points,
        }
    finally:
        conn.close()
