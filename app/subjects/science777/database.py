"""
EduMate AI - 초등 과학 전담 데이터베이스 모듈 (database.py)
==============================================================================
[모듈 출처 및 통합 히스토리]
- 원본 출처: [science_lab] 전용 로컬 데이터베이스 모듈
- 데이터베이스 연동: MySQL 우선 시도 -> 설정 부재 시 로컬 SQLite(data/quiz_logs.db) 안전 계단식 폴백
- SQLAlchemy 2.x ORM 표준 모델 준수

[주요 관리 테이블]
1) quiz_wrong_notes: 과학 취약점 오답노트 (OX/객관식 오답, 서술형 감점 문제)
2) problem_reports: 실시간 문제 오류 신고 내역 (다중 선택 오류 유형 보관)
==============================================================================
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    select,
    desc,
    text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ==============================================================================
# 1. 다중 계단식 .env 탐색 및 환경변수 로드
# ==============================================================================
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

# 로컬 SQLite 기본 저장소 준비 (data/quiz_logs.db)
DATA_DIR = current_dir / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_DB_PATH = DATA_DIR / "quiz_logs.db"

# ==============================================================================
# 2. 데이터베이스 엔진 생성 (MySQL 우선 -> SQLite 안전 계단식 폴백)
# ==============================================================================
mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_host = os.getenv("MYSQL_HOST", "localhost")
mysql_port = os.getenv("MYSQL_PORT", "3306")
mysql_db = os.getenv("MYSQL_DATABASE") or os.getenv("MYSQL_DB")

engine = None
db_mode = "SQLite (Local Fallback)"

# MySQL 정보가 입력되어 있을 경우 우선 연결 시도
if mysql_user and mysql_password and mysql_db:
    try:
        mysql_url = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db}?charset=utf8mb4"
        test_engine = create_engine(mysql_url, pool_recycle=3600, pool_pre_ping=True)
        # 연결 가능 여부 즉시 핑 테스트
        with test_engine.connect() as conn:
            pass
        engine = test_engine
        db_mode = f"MySQL Server ({mysql_host}:{mysql_port}/{mysql_db})"
        print(f"[DB 연결 성공] {db_mode}에 성공적으로 연결되었습니다.")
    except Exception as e:
        print(f"[MySQL 연결 실패 안내] {e}")
        print("[안전 계단식 폴백 작동] 로컬 SQLite 경량 DB로 자동 전환하여 무중단 서비스를 유지합니다.")
        engine = None

# MySQL 미설정 또는 연결 실패 시 SQLite로 무중단 자동 전환
if engine is None:
    sqlite_url = f"sqlite:///{SQLITE_DB_PATH}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    print(f"[SQLite 활성화] 로컬 DB 경로: {SQLITE_DB_PATH}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==============================================================================
# 3. SQLAlchemy ORM 모델 정의
# ==============================================================================
class QuizWrongNote(Base):
    """오답노트 테이블: 틀린 OX/객관식 및 5점 미만 서술형 기록"""
    __tablename__ = "quiz_wrong_notes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(100), nullable=True, default=None, comment="학생 고유 ID")
    user_name = Column(String(100), nullable=False, default="김에듀", comment="학생 이름")
    problem_id = Column(Integer, nullable=True, comment="원래 문제 번호(1~10)")
    grade = Column(Integer, nullable=False, comment="학년(1~6)")
    unit = Column(String(100), nullable=False, comment="단원명")
    quiz_type = Column(String(20), nullable=False, comment="문제 유형: ox / mcq / subjective")
    question = Column(Text, nullable=False, comment="문제 지문")
    options = Column(Text, nullable=True, comment="5지선다 보기 JSON 문자열")
    student_answer = Column(Text, nullable=True, comment="학생이 제출한 답안")
    correct_answer = Column(Text, nullable=False, comment="모범 정답")
    score = Column(Integer, default=0, comment="부여된 점수(0~5점)")
    feedback = Column(Text, nullable=True, comment="AI 맞춤형 피드백")
    deduction_reason = Column(Text, nullable=True, comment="감점 사유 또는 AI 분석 근거")
    is_mastered = Column(Boolean, default=False, comment="개념 마스터 성공 여부")
    mastered_at = Column(DateTime, nullable=True, comment="개념 마스터 일시")
    created_at = Column(DateTime, default=datetime.now, comment="풀이 일시")

    def to_dict(self) -> Dict[str, Any]:
        options_list = None
        if self.options:
            try:
                options_list = json.loads(self.options)
            except Exception:
                options_list = []
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "problem_id": self.problem_id,
            "grade": self.grade,
            "unit": self.unit,
            "quiz_type": self.quiz_type,
            "question": self.question,
            "options": options_list,
            "student_answer": self.student_answer,
            "correct_answer": self.correct_answer,
            "score": self.score,
            "feedback": self.feedback,
            "deduction_reason": self.deduction_reason,
            "is_mastered": bool(self.is_mastered),
            "mastered_at": self.mastered_at.strftime("%Y-%m-%d %H:%M:%S") if self.mastered_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else ""
        }


class ProblemReport(Base):
    """실시간 문제 오류 신고 테이블"""
    __tablename__ = "problem_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    problem_id = Column(Integer, nullable=True, comment="문제 번호")
    grade = Column(Integer, nullable=True, comment="학년")
    unit = Column(String(100), nullable=True, comment="단원명")
    quiz_type = Column(String(20), nullable=True, comment="문제 유형: ox / mcq / subjective")
    question = Column(Text, nullable=False, comment="신고 대상 문제 지문")
    error_type = Column(String(255), nullable=False, comment="선택된 오류 분류(복수 선택)")
    comment = Column(Text, nullable=True, comment="사용자 상세 의견")
    created_at = Column(DateTime, default=datetime.now, comment="신고 접수 일시")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "problem_id": self.problem_id,
            "grade": self.grade,
            "unit": self.unit,
            "quiz_type": self.quiz_type,
            "question": self.question,
            "error_type": self.error_type,
            "comment": self.comment,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else ""
        }


# 테이블 스키마 자동 생성
Base.metadata.create_all(bind=engine)

# 기존 테이블에 is_mastered, mastered_at 컬럼 자동 추가 안전 마이그레이션
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE quiz_wrong_notes ADD COLUMN user_id VARCHAR(100) DEFAULT NULL"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE quiz_wrong_notes ADD COLUMN user_name VARCHAR(100) DEFAULT '김에듀'"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE quiz_wrong_notes ADD COLUMN is_mastered BOOLEAN DEFAULT 0"))
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute(text("ALTER TABLE quiz_wrong_notes ADD COLUMN mastered_at DATETIME"))
        conn.commit()
    except Exception:
        pass


# ==============================================================================
# 4. 데이터베이스 편의 함수 (CRUD)
# ==============================================================================
def get_db():
    """FastAPI 종속성 또는 컨텍스트 매니저용 세션 생성기"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def deduplicate_existing_wrong_notes() -> int:
    """기존 오답노트에 중복으로 들어간 문제를 지문(question) 기준으로 1건만 남기고 정리"""
    db: Session = SessionLocal()
    removed_count = 0
    try:
        notes = db.scalars(select(QuizWrongNote).order_by(QuizWrongNote.id.desc())).all()
        seen_questions = set()
        for n in notes:
            q_clean = (n.question or "").strip()
            if not q_clean:
                continue
            if q_clean in seen_questions:
                db.delete(n)
                removed_count += 1
            else:
                seen_questions.add(q_clean)
        if removed_count > 0:
            db.commit()
            print(f"[오답노트 중복 정리] 기존 중복 데이터 {removed_count}건을 깔끔하게 정리했습니다.")
        return removed_count
    except Exception as e:
        db.rollback()
        print(f"[오답노트 중복 정리 실패 알림] {e}")
        return 0
    finally:
        db.close()


def save_wrong_note(
    grade: int,
    unit: str,
    quiz_type: str,
    question: str,
    correct_answer: str,
    student_answer: str = "",
    problem_id: Optional[int] = None,
    options: Optional[List[str]] = None,
    score: int = 0,
    feedback: str = "",
    deduction_reason: str = "",
    user_name: str = "김에듀",
    user_id: Optional[str] = None
) -> int:
    """오답노트에 문제 추가 (학생 계정별 중복 방지: 동일 학생의 동일 문제 지문이 이미 있으면 최신 기록으로 갱신)"""
    if not question or not question.strip():
        return -1

    clean_q = question.strip()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip() or None

    db: Session = SessionLocal()
    try:
        options_json = json.dumps(options, ensure_ascii=False) if options else None

        # 1. 학생 계정 및 지문 기준 중복 검사
        if clean_id:
            user_filter = (QuizWrongNote.user_id == clean_id) | (QuizWrongNote.user_name == clean_name)
        else:
            user_filter = (QuizWrongNote.user_name == clean_name)

        existing_notes = db.scalars(
            select(QuizWrongNote).where(
                QuizWrongNote.question == clean_q,
                user_filter
            )
        ).all()

        if existing_notes:
            # 첫 번째 항목을 최신 정보로 갱신하고, 혹시 과거에 생긴 잉여 중복본은 정리
            primary_note = existing_notes[0]
            if clean_id:
                primary_note.user_id = clean_id
            primary_note.user_name = clean_name
            primary_note.grade = grade
            primary_note.unit = unit
            primary_note.quiz_type = quiz_type
            primary_note.correct_answer = str(correct_answer)
            primary_note.student_answer = str(student_answer)
            primary_note.score = score
            primary_note.feedback = feedback
            primary_note.deduction_reason = deduction_reason
            primary_note.options = options_json or primary_note.options
            primary_note.is_mastered = False # 새 오답 시 복습 상태로 재설정
            primary_note.created_at = datetime.now()

            # 만약 2개 이상의 중복 레코드가 있었다면 나머지 삭제
            for dup in existing_notes[1:]:
                db.delete(dup)

            db.commit()
            return primary_note.id

        # 2. 신규 문제인 경우에만 새로 추가
        note = QuizWrongNote(
            user_id=clean_id,
            user_name=clean_name,
            problem_id=problem_id,
            grade=grade,
            unit=unit,
            quiz_type=quiz_type,
            question=clean_q,
            options=options_json,
            student_answer=str(student_answer),
            correct_answer=str(correct_answer),
            score=score,
            feedback=feedback,
            deduction_reason=deduction_reason,
            created_at=datetime.now()
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note.id
    except Exception as e:
        db.rollback()
        print(f"❌ [오답 저장 실패] {e}")
        return -1
    finally:
        db.close()


def get_wrong_notes(
    grade: Optional[int] = None,
    quiz_type: Optional[str] = None,
    user_name: Optional[str] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    저장된 오답 목록 최신순 조회
    - 중앙 DB(edumate.db의 quiz_logs)를 자동으로 스캔하여 새 오답을 동기화(insert)
    - 학생 계정별 격리 & 학년/유형 필터링 지원
    """
    # 1. 중앙 DB의 과학 오답을 quiz_wrong_notes로 자동 동기화
    try:
        sync_quiz_logs_to_wrong_notes(user_name=user_name, user_id=user_id)
    except Exception as e:
        print(f"[오답 자동 동기화 예외] {e}")

    # 2. 로컬 quiz_wrong_notes 테이블에서 최신 오답 조회
    db: Session = SessionLocal()
    try:
        stmt = select(QuizWrongNote)

        # 학생 계정별 오답노트 격리 필터
        clean_name = (user_name or "").strip() or None
        clean_id = (user_id or "").strip() or None

        if clean_id:
            stmt = stmt.where((QuizWrongNote.user_id == clean_id) | (QuizWrongNote.user_name == clean_name))
        elif clean_name:
            stmt = stmt.where(QuizWrongNote.user_name == clean_name)

        if grade and grade > 0:
            stmt = stmt.where(QuizWrongNote.grade == grade)
        if quiz_type and quiz_type != "all":
            stmt = stmt.where(QuizWrongNote.quiz_type == quiz_type)
        stmt = stmt.order_by(desc(QuizWrongNote.created_at))
        results = db.scalars(stmt).all()

        seen_questions = set()
        unique_list = []
        for item in results:
            clean_q = (item.question or "").strip()
            if not clean_q or clean_q in seen_questions:
                continue
            seen_questions.add(clean_q)
            unique_list.append(item.to_dict())

        return unique_list
    finally:
        db.close()


def delete_wrong_note(note_id: int) -> bool:
    """오답노트 항목 개별 삭제 (다시 풀어서 맞혔을 때 제거용)"""
    db: Session = SessionLocal()
    try:
        note = db.get(QuizWrongNote, note_id)
        if note:
            db.delete(note)
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print(f"[오답 삭제 실패] {e}")
        return False
    finally:
        db.close()


def delete_wrong_notes_by_question(question: str) -> int:
    """문제 지문으로 오답노트에서 해당 항목을 완전히 삭제 (정답 정정 승인 시 사용)"""
    if not question or not question.strip():
        return 0
    clean_q = question.strip()
    prefix_q = clean_q[:18].strip()
    db: Session = SessionLocal()
    try:
        # 정확 일치 또는 앞 18글자 이상 일치하는 오답 항목 모두 삭제
        stmt = select(QuizWrongNote).where(
            (QuizWrongNote.question == clean_q) | (QuizWrongNote.question.like(f"%{prefix_q}%"))
        )
        notes = db.scalars(stmt).all()
        count = len(notes)
        for n in notes:
            db.delete(n)
        if count > 0:
            db.commit()
            print(f"[오답노트 정답 처리 삭제 완료] '{prefix_q}...' 관련 오답 {count}건을 삭제했습니다.")
        return count
    except Exception as e:
        db.rollback()
        print(f"[지문 기반 오답 삭제 실패] {e}")
        return 0
    finally:
        db.close()


def mark_wrong_note_mastered(note_id: int) -> bool:
    """오답노트 항목을 '개념 마스터 완료' 상태로 갱신 (삭제하지 않고 배지 부여)"""
    db: Session = SessionLocal()
    try:
        note = db.get(QuizWrongNote, note_id)
        if note:
            note.is_mastered = True
            note.mastered_at = datetime.now()
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        print(f"[마스터 상태 갱신 실패] {e}")
        return False
    finally:
        db.close()



def sync_quiz_logs_to_wrong_notes(
    user_name: Optional[str] = None,
    user_id: Optional[str] = None
) -> int:
    """
    중앙 DB(edumate.db의 quiz_logs 테이블) 및 saved_results/ 폴더의 채점 기록을 자동 스캔하여,
    subject='science'이고 (is_correct=0 또는 earned_score < 만점)인 오답 데이터들을
    과학 전용 오답노트(quiz_wrong_notes)에 자동 동기화(insert)합니다.
    """
    import sqlite3
    db: Session = SessionLocal()
    imported_count = 0
    clean_name = (user_name or "").strip() or None
    clean_id = (user_id or "").strip() or None

    try:
        # 기존 등록된 지문 목록 미리 조회 (중복 방지용: 학생 키 + 지문)
        existing_notes = db.scalars(select(QuizWrongNote)).all()
        existing_keys = set()
        for n in existing_notes:
            q_clean = (n.question or "").strip()
            u_clean = (n.user_id or n.user_name or "").strip()
            if q_clean:
                if u_clean:
                    existing_keys.add((u_clean, q_clean))
                existing_keys.add(q_clean)

        # 1. 중앙 edumate.db 후보 경로 안전 탐색
        candidates = [
            current_dir / "edumate.db",
            current_dir.parent / "edumate.db",
            current_dir.parent / "data" / "edumate.db",
            current_dir.parent.parent / "edumate.db",
            current_dir.parent.parent / "data" / "edumate.db",
            current_dir.parent.parent.parent / "data" / "edumate.db",
            DATA_DIR / "edumate.db"
        ]

        valid_dbs = []
        for p in candidates:
            if p.exists() and p not in valid_dbs:
                valid_dbs.append(p)

        for target_db in valid_dbs:
            try:
                conn = sqlite3.connect(str(target_db))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # quiz_logs 테이블 존재 여부 확인
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quiz_logs'")
                if not cur.fetchone():
                    conn.close()
                    continue

                # 테이블 컬럼 스캔
                cur.execute("PRAGMA table_info(quiz_logs)")
                cols = {row["name"] for row in cur.fetchall()}

                has_uid = "user_id" in cols
                has_uname = "user_name" in cols
                has_allotted = "allotted_score" in cols
                has_options = "options" in cols
                has_solution = "solution" in cols
                has_analysis = "ai_analysis" in cols
                has_solved_at = "solved_at" in cols
                has_created_at = "created_at" in cols

                # 조건절 동적 구성
                where_clauses = ["subject = 'science'"]
                params: List[Any] = []

                # 오답 조건: is_correct가 0(또는 false)이거나, 서술형 감점, 배점 미달
                if has_allotted:
                    where_clauses.append(
                        "(is_correct = 0 OR is_correct IS NULL OR "
                        "(allotted_score IS NOT NULL AND earned_score < allotted_score) OR "
                        "(question_type = 'subjective' AND earned_score < 5))"
                    )
                else:
                    where_clauses.append(
                        "(is_correct = 0 OR is_correct IS NULL OR "
                        "(question_type = 'subjective' AND earned_score < 5) OR earned_score = 0)"
                    )

                # 사용자 필터 (특정 사용자로 조회하는 경우 해당 사용자 데이터 우선 스캔)
                if clean_id and has_uid:
                    if clean_name and has_uname:
                        where_clauses.append("(user_id = ? OR user_name = ?)")
                        params.extend([clean_id, clean_name])
                    else:
                        where_clauses.append("user_id = ?")
                        params.append(clean_id)
                elif clean_name and has_uname:
                    where_clauses.append("user_name = ?")
                    params.append(clean_name)

                query = f"SELECT * FROM quiz_logs WHERE {' AND '.join(where_clauses)} ORDER BY id DESC"
                cur.execute(query, params)
                rows = cur.fetchall()

                for r in rows:
                    q_text = (r["question"] or "").strip()
                    if not q_text:
                        continue

                    r_uid = str(r["user_id"]).strip() if (has_uid and r["user_id"]) else (clean_id or None)
                    r_uname = str(r["user_name"]).strip() if (has_uname and r["user_name"]) else (clean_name or "김에듀")
                    user_key = r_uid or r_uname

                    # 중복 검사: 동일 학생에게 동일 지문이 이미 오답노트에 있으면 건너뜀
                    if (user_key, q_text) in existing_keys:
                        continue

                    # 일시 파싱
                    solved_dt = datetime.now()
                    time_raw = None
                    if has_solved_at and r["solved_at"]:
                        time_raw = str(r["solved_at"])
                    elif has_created_at and r["created_at"]:
                        time_raw = str(r["created_at"])

                    if time_raw:
                        try:
                            solved_dt = datetime.strptime(time_raw[:19], "%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass

                    # 유형 정규화
                    raw_type = str(r["question_type"] or "ox").lower()
                    if "ox" in raw_type:
                        norm_type = "ox"
                    elif "mcq" in raw_type or "선다" in raw_type or "choice" in raw_type or "객관" in raw_type:
                        norm_type = "mcq"
                    elif "subj" in raw_type or "서술" in raw_type or "단답" in raw_type:
                        norm_type = "subjective"
                    else:
                        norm_type = "ox"

                    # 피드백 내용
                    fb_text = ""
                    if has_solution and r["solution"]:
                        fb_text = str(r["solution"])
                    elif has_analysis and r["ai_analysis"]:
                        fb_text = str(r["ai_analysis"])

                    # 보기(options) 문자열
                    opts_val = None
                    if has_options and r["options"]:
                        opt_str = str(r["options"]).strip()
                        if opt_str.startswith("[") and opt_str.endswith("]"):
                            opts_val = opt_str

                    score_val = 0
                    try:
                        score_val = int(r["earned_score"] or 0)
                    except Exception:
                        score_val = 0

                    grade_val = 3
                    try:
                        grade_val = int(r["grade"] or 3)
                    except Exception:
                        grade_val = 3

                    note = QuizWrongNote(
                        problem_id=r["id"],
                        user_id=r_uid,
                        user_name=r_uname,
                        grade=grade_val,
                        unit=str(r["unit"] or "총정리"),
                        quiz_type=norm_type,
                        question=q_text,
                        options=opts_val,
                        student_answer=str(r["user_answer"] or ""),
                        correct_answer=str(r["correct_answer"] or ""),
                        score=score_val,
                        feedback=fb_text,
                        deduction_reason="quiz_logs 중앙 기록 자동 동기화",
                        is_mastered=False,
                        created_at=solved_dt
                    )
                    db.add(note)
                    existing_keys.add((user_key, q_text))
                    existing_keys.add(q_text)
                    imported_count += 1

                conn.close()
            except Exception as e_db:
                print(f"[edumate.db 동기화 알림 - {target_db.name}] {e_db}")

        # 2. saved_results/ 폴더 보조 탐색 (하위 호환)
        saved_results_dir = current_dir / "saved_results"
        if saved_results_dir.exists():
            json_files = sorted(saved_results_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
            for jf in json_files:
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue

                grade = data.get("grade") or 1
                unit = data.get("unit") or "총정리"
                answers = data.get("answers") or []
                results = data.get("results") or []
                ans_map = {a.get("id"): a for a in answers}

                file_created_at = datetime.now()
                created_str = data.get("created_at")
                if created_str:
                    try:
                        file_created_at = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass

                for res in results:
                    sc = res.get("score", 0)
                    if sc < 5:
                        q_id = res.get("id")
                        q_info = ans_map.get(q_id, {})
                        q_text = (q_info.get("question") or "").strip()
                        s_ans = (q_info.get("student_answer") or "").strip()

                        user_key = clean_id or clean_name or "김에듀"
                        if not q_text or (user_key, q_text) in existing_keys:
                            continue

                        note = QuizWrongNote(
                            problem_id=q_id,
                            user_id=clean_id,
                            user_name=clean_name or "김에듀",
                            grade=grade,
                            unit=unit,
                            quiz_type="subjective",
                            question=q_text,
                            correct_answer=q_info.get("model_answer", ""),
                            student_answer=s_ans,
                            score=sc,
                            feedback=res.get("feedback", ""),
                            deduction_reason=res.get("analysis", "saved_results 기록 동기화"),
                            is_mastered=False,
                            created_at=file_created_at
                        )
                        db.add(note)
                        existing_keys.add((user_key, q_text))
                        existing_keys.add(q_text)
                        imported_count += 1

        if imported_count > 0:
            db.commit()
            print(f"[오답 동기화 완료] 총 {imported_count}건의 오답이 quiz_wrong_notes에 성공적으로 반영되었습니다.")
    except Exception as e:
        db.rollback()
        print(f"[오답 동기화 실패] {e}")
    finally:
        db.close()

    return imported_count


def sync_saved_results_to_wrong_notes() -> int:
    """하위 호환용 래퍼 함수"""
    return sync_quiz_logs_to_wrong_notes()


def save_problem_report(
    question: str,
    error_type: str,
    comment: str = "",
    problem_id: Optional[int] = None,
    grade: Optional[int] = None,
    unit: Optional[str] = None,
    quiz_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    문제 오류 신고 1건 접수:
    1) DB 테이블 (problem_reports) 자동 저장
    2) 비상용 백업 JSON (reported_issues/ 폴더) 동시 보관
    """
    db: Session = SessionLocal()
    record_dict = {}
    try:
        report = ProblemReport(
            problem_id=problem_id,
            grade=grade,
            unit=unit,
            quiz_type=quiz_type,
            question=question,
            error_type=error_type,
            comment=comment,
            created_at=datetime.now()
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        record_dict = report.to_dict()
    except Exception as e:
        db.rollback()
        print(f"[신고 DB 저장 실패] {e}")
        record_dict = {
            "id": None,
            "problem_id": problem_id,
            "grade": grade,
            "unit": unit,
            "quiz_type": quiz_type,
            "question": question,
            "error_type": error_type,
            "comment": comment,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    finally:
        db.close()

    # 비상용 타임스탬프 JSON 파일 저장
    try:
        report_dir = current_dir / "reported_issues"
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = report_dir / f"report_{timestamp_str}.json"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(record_dict, f, ensure_ascii=False, indent=2)
    except Exception as err:
        print(f"[비상 백업 JSON 생성 실패] {err}")

    return record_dict


def get_problem_reports() -> List[Dict[str, Any]]:
    """접수된 문제 신고 목록 최신순 조회"""
    db: Session = SessionLocal()
    try:
        stmt = select(ProblemReport).order_by(desc(ProblemReport.created_at))
        results = db.scalars(stmt).all()
        return [item.to_dict() for item in results]
    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("[EduMate AI science_lab - DB 모듈 단독 점검]")
    print(f"* 현재 활성화 모드: {db_mode}")
    print(f"* SQLite 백업 위치: {SQLITE_DB_PATH}")
    print("=" * 60)

    # 테스트 1: 오답노트 저장 및 조회 테스트
    test_id = save_wrong_note(
        grade=3,
        unit="자석의 이용",
        quiz_type="ox",
        question="자석의 같은 극끼리는 서로 끌어당긴다.",
        correct_answer="X",
        student_answer="O",
        score=0,
        feedback="자석의 같은 극(N극과 N극, S극과 S극)은 서로 밀어내고, 다른 극끼리 끌어당겨요!",
        deduction_reason="자석의 인력과 척력 개념 혼동"
    )
    print(f"[오답 샘플 저장 완료] (ID: {test_id})")

    notes = get_wrong_notes()
    print(f"[오답노트 조회 결과] 총 {len(notes)}건")

    # 테스트 2: 문제 신고 저장 및 조회 테스트
    rep = save_problem_report(
        question="자석의 같은 극끼리는 서로 끌어당긴다.",
        error_type="모범 정답/해설 오류",
        comment="해설 설명이 조금 더 쉬웠으면 좋겠어요.",
        grade=3,
        unit="자석의 이용",
        quiz_type="ox"
    )
    print(f"[문제 신고 접수 완료] (ID: {rep.get('id')})")
    reports = get_problem_reports()
    print(f"[전체 신고 접수 목록] 총 {len(reports)}건")
    print("=" * 60 + "\n")
