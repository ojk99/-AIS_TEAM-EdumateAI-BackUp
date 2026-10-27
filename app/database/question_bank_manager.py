# -*- coding: utf-8 -*-
"""
[EduMate AI - 문제은행(Question Bank) 통합 DB 및 메타데이터 관리 모듈]
- 위치: app/subjects/math/question_bank.py (DB 파일: app/subjects/math/question_bank.db)
- 역할:
  1) 수학 과목 폴더 내 표준 문제은행 SQLite DB(`question_bank.db`) 초기화 및 CRUD 관리
  2) 총 관리자 및 과목별 부관리자 권한(`check_subject_permission`) 검증 연동
  3) 6개 과목(국어, 수학, 영어, 사회, 과학, 한자)의 커리큘럼(`curriculum.txt`)을 읽기 전용으로 파싱하여
     과목 -> 학년군/단계 -> 대단원 -> 하위주제 동적 드롭트리 및 과목별 지원 문제유형/난이도 메타데이터 제공
  4) 수학 과목 OX 퀴즈 선택 시 난이도 '하(1점)' 강제 고정 규칙 적용
  5) 개인정보 문제풀이 DB 내역(`quiz_logs`)에서 마음에 드는 AI 출제 문제를 문제은행으로 즉시 저장
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database.quiz_manager import (
    ALL_SUBJECT_CODES,
    SUBJECT_CODE_TO_LABEL,
    _get_conn as _get_control_conn,
    check_subject_permission,
    get_or_create_user,
    normalize_subject_code,
)
from app.subjects.math.curriculum_parser import get_curriculum_tree_for_ui

DB_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DB_DIR.parent.parent
SUBJECTS_ROOT_DIR = PROJECT_ROOT / "app" / "subjects"
MATH_DIR = SUBJECTS_ROOT_DIR / "math"
QUESTION_BANK_DB_PATH = MATH_DIR / "question_bank.db"

DIFFICULTY_TO_POINTS: Dict[str, int] = {
    "하": 1,
    "중": 3,
    "상": 5,
}

POINTS_TO_DIFFICULTY: Dict[int, str] = {
    1: "하",
    3: "중",
    5: "상",
}

# 과목별 실제 지원하는 문제유형 정의 (각 과목 라우터/프론트엔드 출제 로직 기준)
SUBJECT_QUESTION_TYPES: Dict[str, List[Dict[str, Any]]] = {
    "math": [
        {"code": "ox", "label": "OX 퀴즈 (난이도 '하' 1점 고정)", "fixed_difficulty": "하"},
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "단답형", "label": "단답형 주관식", "fixed_difficulty": None},
        {"code": "단답형 주관식 2", "label": "단답형 주관식 2 (블록 칠하기)", "fixed_difficulty": None},
        {"code": "서술형", "label": "서술형 (풀이 과정 채점)", "fixed_difficulty": None},
    ],
    "korean": [
        {"code": "ox", "label": "OX 퀴즈", "fixed_difficulty": None},
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "단답형", "label": "단답형 주관식", "fixed_difficulty": None},
        {"code": "서술형", "label": "서술형", "fixed_difficulty": None},
    ],
    "english": [
        # 영어 과목은 OX 유형이 없음 (객관식, 단답형, 서술형만 존재)
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "단답형", "label": "단답형 주관식", "fixed_difficulty": None},
        {"code": "서술형", "label": "서술형 (영작/문장)", "fixed_difficulty": None},
    ],
    "social": [
        {"code": "ox", "label": "OX 퀴즈", "fixed_difficulty": None},
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "단답형", "label": "단답형 주관식", "fixed_difficulty": None},
        {"code": "서술형", "label": "서술형", "fixed_difficulty": None},
    ],
    "science": [
        # 과학 과목은 OX, 객관식, 서술형 3가지 유형으로 구성됨
        {"code": "ox", "label": "OX 진위형 퀴즈", "fixed_difficulty": None},
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "서술형", "label": "탐구 서술형", "fixed_difficulty": None},
    ],
    "hanja": [
        # 한자 과목은 OX 유형이 없음 (객관식, 단답형, 서술형만 존재)
        {"code": "객관식", "label": "4지선다 객관식", "fixed_difficulty": None},
        {"code": "단답형", "label": "단답형 주관식 (훈음/독음)", "fixed_difficulty": None},
        {"code": "서술형", "label": "서술형 (뜻풀이/문장)", "fixed_difficulty": None},
    ],
}

DIFFICULTY_OPTIONS: List[Dict[str, Any]] = [
    {"code": "하", "points": 1, "label": "하 (1점)"},
    {"code": "중", "points": 3, "label": "중 (3점)"},
    {"code": "상", "points": 5, "label": "상 (5점)"},
]


def _resolve_bank_db_path(subject_code: Optional[str] = None, for_write: bool = False) -> Path:
    """
    과목 코드가 주어졌을 때 해당 과목 폴더(`app/subjects/{subject_code}/question_bank.db`) 경로를 결정합니다.
    - 이미 해당 과목 폴더에 `question_bank.db`가 존재하거나, 문제 저장(`for_write=True`) 시 해당 과목 폴더가 존재하면
      `app/subjects/{subject_code}/question_bank.db`를 반환하여 과목별 DB에 직접 저장합니다.
    - 단순 조회 시 아직 해당 과목 DB 파일이 생성 전이면 `app/subjects/math/question_bank.db`를 반환합니다.
    """
    norm_s = normalize_subject_code(subject_code or "math") or "math"
    if norm_s != "math":
        subj_dir = SUBJECTS_ROOT_DIR / norm_s
        subj_db = subj_dir / "question_bank.db"
        if subj_db.exists():
            return subj_db
        if for_write and subj_dir.exists() and subj_dir.is_dir():
            return subj_db
    return QUESTION_BANK_DB_PATH


def _ensure_bank_table_on_conn(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS question_bank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL DEFAULT 'math',
            grade INTEGER NOT NULL DEFAULT 4,
            grade_group TEXT NOT NULL DEFAULT '',
            unit_name TEXT NOT NULL DEFAULT '',
            sub_topic TEXT NOT NULL DEFAULT '',
            question_type TEXT NOT NULL DEFAULT '객관식',
            difficulty TEXT NOT NULL DEFAULT '중',
            points INTEGER NOT NULL DEFAULT 3,
            question_text TEXT NOT NULL,
            choices_json TEXT DEFAULT '[]',
            visual_data_json TEXT DEFAULT '{}',
            correct_answer TEXT NOT NULL,
            explanation TEXT DEFAULT '',
            source_type TEXT DEFAULT 'manual',
            source_log_id INTEGER DEFAULT NULL,
            created_by TEXT DEFAULT '',
            created_by_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        cur.execute("ALTER TABLE question_bank ADD COLUMN visual_data_json TEXT DEFAULT '{}'")
    except Exception:
        pass
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS question_bank_solved (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            subject TEXT NOT NULL DEFAULT 'math',
            user_key TEXT NOT NULL DEFAULT '',
            solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bank_id, subject, user_key)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qbank_subject ON question_bank(subject, grade_group, unit_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qbank_qtype ON question_bank(subject, question_type, difficulty)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qbank_solved_user ON question_bank_solved(subject, user_key)")
    conn.commit()


def _get_bank_conn(subject_code: Optional[str] = None, for_write: bool = False) -> sqlite3.Connection:
    target_path = _resolve_bank_db_path(subject_code, for_write=for_write)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    _ensure_bank_table_on_conn(conn)
    return conn


def init_question_bank_db() -> None:
    """
    app/subjects/math/question_bank.db 내에 표준 question_bank 테이블을 생성합니다.
    조원들이 타 과목에서 동일한 스키마로 통일하거나 공용 연동할 수 있도록 표준 컬럼을 구성합니다.
    """
    conn = _get_bank_conn("math")
    conn.close()


# ==============================================================================
# 6개 과목 커리큘럼(curriculum.txt) 읽기 전용 파서 (타 과목 파일 수정 없이 동적 트리 생성)
# ==============================================================================
def _parse_korean_curriculum() -> Dict[str, Dict[str, List[str]]]:
    """국어 과목은 하위 주제가 없고 학년군별 단원까지만 구성됩니다."""
    tree: Dict[str, Dict[str, List[str]]] = {}
    path = SUBJECTS_ROOT_DIR / "korean" / "curriculum.txt"
    if not path.exists():
        return {"전학년": {"국어 기본 단원": []}}
    text = path.read_text(encoding="utf-8")
    current_group = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        m_group = re.match(r"^\[(.+?)\]$", line)
        if m_group:
            current_group = m_group.group(1).strip()
            tree.setdefault(current_group, {})
            continue
        if line.startswith("- ") and current_group:
            unit_part = line[2:].strip()
            unit_title = unit_part.split(" - ")[0].strip() if " - " in unit_part else unit_part
            tree[current_group].setdefault(unit_title, [])
    return tree


def _parse_english_curriculum() -> Dict[str, Dict[str, List[str]]]:
    """영어 과목은 단원 구분이 따로 없고 학년군 및 문제유형으로만 구성됩니다."""
    return {
        "3~4학년군 (새싹반)": {"전체": []},
        "5~6학년군 (열매반)": {"전체": []},
    }


def _parse_social_curriculum() -> Dict[str, Dict[str, List[str]]]:
    """사회 과목은 하위 주제가 없고 학년군별 단원까지만 구성됩니다."""
    tree: Dict[str, Dict[str, List[str]]] = {}
    path = SUBJECTS_ROOT_DIR / "social" / "curriculum.txt"
    if not path.exists():
        return {"3~4학년군": {"사회 일반": []}, "5~6학년군": {"역사와 사회": []}}
    text = path.read_text(encoding="utf-8")
    current_group = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        m_group = re.match(r"^\[(.+?)\]$", line)
        if m_group:
            current_group = m_group.group(1).strip()
            tree.setdefault(current_group, {})
            continue
        m_unit = re.match(r"^(\d+\.\s*.+)$", line)
        if m_unit and current_group:
            unit_title = m_unit.group(1).strip()
            tree[current_group].setdefault(unit_title, [])
    return tree


def _parse_science_curriculum() -> Dict[str, Dict[str, List[str]]]:
    """과학 과목은 하위 주제가 없고 학년/학기별 단원까지만 구성됩니다."""
    tree: Dict[str, Dict[str, List[str]]] = {}
    path = SUBJECTS_ROOT_DIR / "science" / "curriculum.txt"
    if not path.exists():
        return {"3~4학년군": {"기초 과학": []}, "5~6학년군": {"심화 과학": []}}
    text = path.read_text(encoding="utf-8")
    current_group = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        m_group = re.match(r"^\[(.+?)\]$", line)
        if m_group:
            current_group = m_group.group(1).strip()
            tree.setdefault(current_group, {})
            continue
        if line.startswith("- ") and current_group:
            body = line[2:].strip()
            unit_title = body.split(":", 1)[0].strip() if ":" in body else body
            tree[current_group].setdefault(unit_title, [])
    return tree


def _parse_hanja_curriculum() -> Dict[str, Dict[str, List[str]]]:
    return {
        "급수별 한자 (9급~6급)": {
            "9급 배정 한자 (기초 50자)": ["요일·숫자·방향 한자", "자연·가족 기초 한자"],
            "8급 배정 한자 (초급 100자)": ["학교·생활 한자", "반대어·유의어 기초 한자"],
            "7급 배정 한자 (중급 150자)": ["교과서 필수 한자", "일상 한자어 활용"],
            "6급 배정 한자 (심화 300자)": ["초등 심화 한자", "동음이의어 한자"],
        },
        "주제별 한자·성어": {
            "실용 한자어": ["교과 학습 용어", "일상 어휘 한자어"],
            "사자성어": ["초등 필수 사자성어", "교훈·고사성어"],
        },
    }


def get_all_subjects_question_bank_meta(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    과목별 커리큘럼 드롭트리(학년군 -> 대단원 -> 하위주제),
    과목별 지원 문제유형, 난이도/배점 규칙, 그리고 현재 사용자의 관리 가능 과목 목록을 반환합니다.
    """
    init_question_bank_db()
    math_tree = get_curriculum_tree_for_ui()

    curriculum_by_subject: Dict[str, Dict[str, Dict[str, List[str]]]] = {
        "korean": _parse_korean_curriculum(),
        "math": math_tree,
        "english": _parse_english_curriculum(),
        "social": _parse_social_curriculum(),
        "science": _parse_science_curriculum(),
        "hanja": _parse_hanja_curriculum(),
    }

    subjects_meta: Dict[str, Any] = {}
    for code in ALL_SUBJECT_CODES:
        subjects_meta[code] = {
            "code": code,
            "label": SUBJECT_CODE_TO_LABEL.get(code, code),
            "question_types": SUBJECT_QUESTION_TYPES.get(code, SUBJECT_QUESTION_TYPES["korean"]),
            "curriculum": curriculum_by_subject.get(code, {}),
            "difficulty_options": DIFFICULTY_OPTIONS,
            "has_units": (code != "english"),
            "has_subtopics": (code in ("math", "hanja")),
        }

    allowed_subjects: List[str] = []
    user_role = "student"
    role_display = ""
    if user_id:
        profile = get_or_create_user(user_id=user_id)
        user_role = profile.get("role", "student")
        role_display = profile.get("role_display", "")
        if user_role == "admin":
            allowed_subjects = ALL_SUBJECT_CODES[:]
        elif user_role == "sub_admin":
            allowed_subjects = profile.get("managed_subjects", [])

    return {
        "subjects": subjects_meta,
        "subject_order": [
            {"code": c, "label": SUBJECT_CODE_TO_LABEL[c]} for c in ALL_SUBJECT_CODES
        ],
        "difficulty_options": DIFFICULTY_OPTIONS,
        "user_permission": {
            "user_id": user_id or "",
            "role": user_role,
            "role_display": role_display,
            "allowed_subjects": allowed_subjects,
            "allowed_subjects_kr": [SUBJECT_CODE_TO_LABEL[c] for c in allowed_subjects if c in SUBJECT_CODE_TO_LABEL],
        },
    }


def _infer_grade_from_group(grade_group: str, fallback: int = 4) -> int:
    text = (grade_group or "").strip()
    if "1~2" in text or "1학년" in text or "9급" in text or "8급" in text:
        return 2
    if "3~4" in text or "3학년" in text or "4학년" in text or "새싹" in text or "7급" in text:
        return 4
    if "5~6" in text or "5학년" in text or "6학년" in text or "열매" in text or "6급" in text:
        return 6
    if "2학년" in text:
        return 2
    return fallback if (1 <= int(fallback or 4) <= 6) else 4


def _extract_visual_data_from_logged_question(raw_question: str) -> tuple[str, Any, str]:
    """
    기존 quiz_logs에 getFullQuestionForContext()로 합쳐져 저장된 지문에서
    순수 지문(clean_question)과 시각 자료(visual_data: grid/table/chart), 방향 표시(direction_footer)를 자동 복원합니다.
    """
    text = (raw_question or "").strip()
    if not text:
        return "", {"type": "none"}, ""

    dir_footer = ""
    if "옆(오른쪽)에서" in text or "옆에서" in text:
        dir_footer = "앞 ◀ ▶ 뒤"
    elif "앞에서" in text:
        dir_footer = "왼쪽 ◀ ▶ 오른쪽"

    blocks = text.split("\n\n")
    if len(blocks) < 2:
        return text, {"type": "none"}, dir_footer

    base_paragraphs: List[str] = []
    extracted_visuals: List[Dict[str, Any]] = []

    for idx, blk in enumerate(blocks):
        lines = [ln.rstrip("\r") for ln in blk.splitlines() if ln.strip() != "" or "   " in ln]
        if idx > 0 and lines and re.match(r"^\[.+\]$", lines[0].strip()):
            title = lines[0].strip()[1:-1].strip()
            body_lines = lines[1:]
            if body_lines:
                if " | " in body_lines[0]:
                    headers = [h.strip() for h in body_lines[0].split(" | ")]
                    rows = [[c.strip() for c in ln.split("   ")] for ln in body_lines[1:]]
                    extracted_visuals.append({
                        "type": "table",
                        "title": title,
                        "headers": headers,
                        "rows": rows,
                    })
                    continue
                elif any(k in title for k in ("모양", "층", "격자", "배열")) or all(("   " in ln or ln.strip().isdigit()) for ln in body_lines):
                    rows = [ln.split("   ") for ln in body_lines]
                    footer = ""
                    if "위에서" in title:
                        footer = "앞"
                    elif "앞에서" in title:
                        footer = "왼쪽 ◀ ▶ 오른쪽"
                    elif "옆" in title:
                        footer = "앞 ◀ ▶ 뒤"
                    extracted_visuals.append({
                        "type": "grid",
                        "title": title,
                        "rows": rows,
                        "footer": footer,
                    })
                    continue
        base_paragraphs.append(blk)

    if not extracted_visuals:
        return text, {"type": "none"}, dir_footer

    clean_q = "\n\n".join(base_paragraphs).strip() or text
    vis_out: Any = extracted_visuals[0] if len(extracted_visuals) == 1 else extracted_visuals
    return clean_q, vis_out, dir_footer


def _pack_visual_meta(
    visual_data: Optional[Any] = None,
    direction_footer: str = "",
    rubric: Optional[List[Dict[str, Any]]] = None,
) -> str:
    v_obj = visual_data if isinstance(visual_data, (dict, list)) else {"type": "none"}
    r_list = rubric if isinstance(rubric, list) else []
    meta = {
        "_wrapped_meta": True,
        "visual_data": v_obj,
        "direction_footer": (direction_footer or "").strip(),
        "rubric": r_list,
    }
    try:
        return json.dumps(meta, ensure_ascii=False)
    except Exception:
        return "{}"


def _unpack_visual_meta(
    raw_visual_json: Optional[str],
    question_text: str = "",
    question_type: str = "",
) -> tuple[str, Any, str, List[Dict[str, Any]]]:
    visual_data: Any = {"type": "none"}
    direction_footer: str = ""
    rubric: List[Dict[str, Any]] = []

    if raw_visual_json and str(raw_visual_json).strip() not in ("", "{}"):
        try:
            parsed = json.loads(raw_visual_json)
            if isinstance(parsed, dict) and parsed.get("_wrapped_meta"):
                visual_data = parsed.get("visual_data") or {"type": "none"}
                direction_footer = str(parsed.get("direction_footer") or "")
                rubric = parsed.get("rubric") if isinstance(parsed.get("rubric"), list) else []
            elif isinstance(parsed, (dict, list)):
                visual_data = parsed
        except Exception:
            pass

    clean_q = question_text or ""
    is_empty_vis = (
        not visual_data
        or (isinstance(visual_data, dict) and str(visual_data.get("type", "none")).lower() in ("none", ""))
    )
    if is_empty_vis and "\n\n[" in clean_q:
        clean_q, extracted_vis, extracted_dir = _extract_visual_data_from_logged_question(clean_q)
        if not (isinstance(extracted_vis, dict) and extracted_vis.get("type") == "none"):
            visual_data = extracted_vis
        if not direction_footer and extracted_dir:
            direction_footer = extracted_dir

    if not direction_footer and question_type == "단답형 주관식 2":
        direction_footer = "앞 ◀ ▶ 뒤" if "옆" in clean_q else "왼쪽 ◀ ▶ 오른쪽"

    return clean_q, visual_data, direction_footer, rubric


def add_question_to_bank(
    user_id: str,
    subject: str,
    grade_group: str,
    unit_name: str,
    sub_topic: str,
    question_type: str,
    difficulty: str,
    question_text: str,
    correct_answer: str,
    choices: Optional[List[Any]] = None,
    explanation: str = "",
    grade: Optional[int] = None,
    source_type: str = "manual",
    source_log_id: Optional[int] = None,
    visual_data: Optional[Any] = None,
    direction_footer: str = "",
    rubric: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    부관리자 이상 권한을 검증한 뒤 문제은행 DB(`question_bank.db`)에 문제를 저장합니다.
    - 수학 과목에서 'ox' 선택 시 난이도는 무조건 '하'(1점)로 고정됩니다.
    - 수학 과목의 '단답형 주관식 2 (공간감각 그리드)' 및 표/격자/그래프 시각자료(visual_data)도 완벽히 저장합니다.
    - 과목별로 존재하지 않는 문제유형은 거부합니다.
    """
    init_question_bank_db()
    clean_uid = (user_id or "").strip()
    subj_code = normalize_subject_code(subject)
    if not subj_code:
        raise ValueError(f"유효하지 않은 과목 코드입니다: {subject}")

    if not check_subject_permission(clean_uid, subj_code):
        subj_kr = SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code)
        raise PermissionError(f"'{subj_kr}' 과목 문제은행에 접근할 권한이 없습니다.")

    q_text = (question_text or "").strip()
    c_ans = (correct_answer or "").strip()
    if not q_text:
        raise ValueError("문제 지문(question_text)을 입력해 주세요.")
    if not c_ans:
        raise ValueError("정답(correct_answer)을 입력해 주세요.")

    # 과목별 허용 문제유형 검증
    allowed_qtypes = [qt["code"] for qt in SUBJECT_QUESTION_TYPES.get(subj_code, [])]
    norm_qtype = (question_type or "객관식").strip()
    if norm_qtype.lower() == "ox":
        norm_qtype = "ox"
    elif norm_qtype in ("multiple_choice", "4지선다"):
        norm_qtype = "객관식"
    elif norm_qtype in ("short_answer", "주관식"):
        norm_qtype = "단답형"
    elif norm_qtype in ("short_answer_2", "단답형 주관식2", "주관식2", "공간감각"):
        norm_qtype = "단답형 주관식 2"
    elif norm_qtype in ("descriptive", "essay"):
        norm_qtype = "서술형"

    if allowed_qtypes and norm_qtype not in allowed_qtypes:
        subj_kr = SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code)
        raise ValueError(
            f"'{subj_kr}' 과목에서는 '{norm_qtype}' 유형을 지원하지 않습니다. (지원 유형: {', '.join(allowed_qtypes)})"
        )

    # 지문 내 텍스트 블록으로 시각 자료가 포함된 경우 자동 추출 및 정제
    if not visual_data or (isinstance(visual_data, dict) and visual_data.get("type") in (None, "none", "")):
        extracted_q, extracted_vis, extracted_dir = _extract_visual_data_from_logged_question(q_text)
        if not (isinstance(extracted_vis, dict) and extracted_vis.get("type") == "none"):
            q_text = extracted_q
            visual_data = extracted_vis
        if not direction_footer and extracted_dir:
            direction_footer = extracted_dir

    if norm_qtype == "단답형 주관식 2" and not direction_footer:
        direction_footer = "앞 ◀ ▶ 뒤" if "옆" in q_text else "왼쪽 ◀ ▶ 오른쪽"

    # 난이도 및 배점 결정 (수학 OX는 '하(1점)' 고정!)
    norm_diff = (difficulty or "중").strip()
    if norm_diff not in DIFFICULTY_TO_POINTS:
        norm_diff = "중"
    if subj_code == "math" and norm_qtype == "ox":
        norm_diff = "하"
    points = DIFFICULTY_TO_POINTS[norm_diff]

    # 객관식 보기 정리 (문자열 보기 및 공간감각 미니 그리드 dict 보기 모두 보존)
    clean_choices: List[Any] = []
    if choices:
        for c in choices:
            if isinstance(c, dict):
                clean_choices.append(c)
            elif str(c).strip():
                clean_choices.append(str(c).strip())
    if norm_qtype == "ox" and not clean_choices:
        clean_choices = ["O", "X"]

    visual_json_str = _pack_visual_meta(visual_data, direction_footer, rubric)

    resolved_grade = int(grade) if (grade and 1 <= int(grade) <= 6) else _infer_grade_from_group(grade_group, 4)
    profile = get_or_create_user(user_id=clean_uid)
    creator_name = profile.get("user_name", clean_uid)

    conn = _get_bank_conn(subj_code, for_write=True)
    try:
        cur = conn.cursor()
        if source_log_id is not None:
            cur.execute(
                "SELECT id FROM question_bank WHERE source_log_id = ? LIMIT 1",
                (int(source_log_id),),
            )
            dup = cur.fetchone()
            if dup:
                return {
                    "id": int(dup["id"]),
                    "duplicated": True,
                    "subject": subj_code,
                    "subject_kr": SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code),
                    "message": f"이미 문제은행에 저장된 문제입니다. (문제은행 번호 #{dup['id']})",
                }

        # [2차 차단]: 동일한 지문과 정답을 가진 문제가 이미 등록되어 있는지 대조
        cur.execute(
            "SELECT id FROM question_bank WHERE subject = ? AND question_text = ? AND correct_answer = ? LIMIT 1",
            (subj_code, q_text, c_ans),
        )
        dup_content = cur.fetchone()
        if dup_content:
            return {
                "id": int(dup_content["id"]),
                "duplicated": True,
                "subject": subj_code,
                "subject_kr": SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code),
                "message": f"이미 문제은행에 등록된 동일한 문제입니다. (문제은행 번호 #{dup_content['id']})",
            }

        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points,
                question_text, choices_json, visual_data_json, correct_answer, explanation,
                source_type, source_log_id, created_by, created_by_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subj_code,
                resolved_grade,
                (grade_group or "").strip() or f"{resolved_grade}학년",
                (unit_name or "").strip() or ("전체" if subj_code == "english" else "기본 단원"),
                (sub_topic or "").strip(),
                norm_qtype,
                norm_diff,
                points,
                q_text,
                json.dumps(clean_choices, ensure_ascii=False),
                visual_json_str,
                c_ans,
                (explanation or "").strip(),
                (source_type or "manual").strip(),
                int(source_log_id) if source_log_id is not None else None,
                clean_uid,
                creator_name,
            ),
        )
        conn.commit()
        new_id = int(cur.lastrowid or 0)
        return {
            "id": new_id,
            "duplicated": False,
            "subject": subj_code,
            "subject_kr": SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code),
            "grade": resolved_grade,
            "grade_group": (grade_group or "").strip() or f"{resolved_grade}학년",
            "unit_name": (unit_name or "").strip() or ("전체" if subj_code == "english" else "기본 단원"),
            "sub_topic": (sub_topic or "").strip(),
            "question_type": norm_qtype,
            "difficulty": norm_diff,
            "points": points,
            "question_text": q_text,
            "choices": clean_choices,
            "visual_data": visual_data if isinstance(visual_data, (dict, list)) else {"type": "none"},
            "direction_footer": direction_footer,
            "correct_answer": c_ans,
            "explanation": (explanation or "").strip(),
            "source_type": source_type,
            "source_log_id": source_log_id,
            "created_by": clean_uid,
            "created_by_name": creator_name,
            "message": f"[{SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code)}] 문제은행에 새 문제가 저장되었습니다! (#{new_id})",
        }
    finally:
        conn.close()


def save_quiz_log_to_bank(log_id: int, user_id: str) -> Dict[str, Any]:
    """
    개인정보의 문제풀이 DB 조회 내역(`quiz_logs`)에서 특정 문제를 선택해
    담당 과목 권한 확인 후 문제은행(`question_bank.db`)에 즉시 저장합니다.
    (sqlite3.Row 키 누락 예외 원천 차단 및 공간감각/표/그래프 visual_data 자동 복원 지원)
    """
    init_question_bank_db()
    clean_uid = (user_id or "").strip()
    ctrl_conn = _get_control_conn()
    try:
        cur = ctrl_conn.cursor()
        cur.execute("SELECT * FROM quiz_logs WHERE id = ? LIMIT 1", (int(log_id),))
        row = cur.fetchone()
    finally:
        ctrl_conn.close()

    if not row:
        raise ValueError(f"문제풀이 로그(ID={log_id})를 찾을 수 없습니다.")

    row_dict = dict(row)

    # [1차 차단]: 문제은행에서 출제된 문제는 문제풀이 로그에서 문제은행으로 중복 저장 차단
    q_id_str = str(row_dict.get("quiz_id") or "").strip()
    src_type_str = str(row_dict.get("source_type") or "").strip()
    if q_id_str.startswith("bank_") or src_type_str == "question_bank":
        raise ValueError("이미 문제은행에서 출제된 문제입니다. 문제은행에 중복 저장할 수 없습니다.")

    raw_subj = row_dict.get("subject") or "math"
    subj_code = normalize_subject_code(raw_subj) or "math"
    if not check_subject_permission(clean_uid, subj_code):
        subj_kr = SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code)
        raise PermissionError(f"'{subj_kr}' 과목 문제를 문제은행에 저장할 권한이 없습니다.")

    grade = int(row_dict.get("grade") or 4)
    if grade <= 2:
        grade_group = "1~2학년군"
    elif grade <= 4:
        grade_group = "3~4학년군"
    else:
        grade_group = "5~6학년군"

    unit_name = str(row_dict.get("unit") or row_dict.get("unit_name") or "").strip() or "AI 출제 단원"
    sub_topic = str(row_dict.get("topic") or row_dict.get("sub_topic") or "").strip()
    q_type = str(row_dict.get("question_type") or "객관식").strip()

    allowed_qtypes = [qt["code"] for qt in SUBJECT_QUESTION_TYPES.get(subj_code, [])]
    if allowed_qtypes and q_type not in allowed_qtypes:
        if q_type.lower() == "ox" and "ox" in allowed_qtypes:
            q_type = "ox"
        elif q_type in ("단답형 주관식2", "short_answer_2") and "단답형 주관식 2" in allowed_qtypes:
            q_type = "단답형 주관식 2"
        else:
            q_type = allowed_qtypes[0]

    diff = str(row_dict.get("difficulty") or "중").strip()
    if diff not in DIFFICULTY_TO_POINTS:
        pts = int(row_dict.get("points") or row_dict.get("score") or row_dict.get("earned_score") or 3)
        diff = POINTS_TO_DIFFICULTY.get(pts, "중")

    choices: List[Any] = []
    raw_choices = row_dict.get("choices_json") or "[]"
    if raw_choices:
        try:
            parsed = json.loads(raw_choices)
            if isinstance(parsed, list):
                choices = [x if isinstance(x, dict) else str(x) for x in parsed]
        except Exception:
            choices = []

    raw_q_text = str(row_dict.get("question") or row_dict.get("question_text") or "").strip()
    c_ans = str(row_dict.get("correct_answer") or "").strip()
    expl = str(row_dict.get("solution") or row_dict.get("ai_feedback") or row_dict.get("explanation") or "").strip()

    clean_q_text, visual_data, dir_footer, rubric = _unpack_visual_meta(
        row_dict.get("visual_data_json"),
        question_text=raw_q_text,
        question_type=q_type,
    )

    # 이전 로그에서 객관식 보기(choices_json)가 저장되지 않았던 경우, 정답이 번호(1~4)가 아닌 실제 값이면 단답형 또는 보기 자동 보강
    if q_type == "객관식" and not choices:
        if c_ans in ("1", "2", "3", "4"):
            # 해설에서 정답 값을 추출하거나 번호 선택형 보기 구성
            choices = ["1번", "2번", "3번", "4번"]
        else:
            num_m = re.search(r"(-?\d+)", c_ans)
            if num_m:
                n_val = int(num_m.group(1))
                unit_suffix = c_ans.replace(num_m.group(1), "").strip()
                choices = [
                    c_ans,
                    f"{n_val + 1}{unit_suffix}",
                    f"{max(0, n_val - 1) if n_val > 1 else n_val + 3}{unit_suffix}",
                    f"{n_val + 2}{unit_suffix}",
                ]
            else:
                q_type = "단답형" if "단답형" in allowed_qtypes else q_type

    return add_question_to_bank(
        user_id=clean_uid,
        subject=subj_code,
        grade_group=grade_group,
        unit_name=unit_name,
        sub_topic=sub_topic,
        question_type=q_type,
        difficulty=diff,
        question_text=clean_q_text,
        correct_answer=c_ans,
        choices=choices,
        explanation=expl,
        grade=grade,
        source_type="ai_log",
        source_log_id=int(log_id),
        visual_data=visual_data,
        direction_footer=dir_footer,
        rubric=rubric,
    )


def _get_existing_bank_db_paths(subjects: Optional[List[str]] = None) -> List[Path]:
    """존재하는 모든 과목별 question_bank.db 경로(중복 제거)를 반환합니다."""
    init_question_bank_db()
    target_codes = subjects if subjects else ALL_SUBJECT_CODES[:]
    paths: List[Path] = []
    seen = set()
    for sc in target_codes:
        p = _resolve_bank_db_path(sc)
        if str(p) not in seen and p.exists():
            seen.add(str(p))
            paths.append(p)
    if str(QUESTION_BANK_DB_PATH) not in seen and QUESTION_BANK_DB_PATH.exists():
        paths.append(QUESTION_BANK_DB_PATH)
    return paths


def list_question_bank(
    user_id: Optional[str] = None,
    subject: Optional[str] = None,
    grade_group: Optional[str] = None,
    unit_name: Optional[str] = None,
    question_type: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    문제은행에 저장된 문제 목록을 조회합니다.
    조원이 각 과목 폴더(`app/subjects/<과목>/question_bank.db`)에 개설한 DB와
    기본 `app/subjects/math/question_bank.db`를 모두 자동 탐색하여 반환합니다.
    """
    init_question_bank_db()
    allowed: List[str] = ALL_SUBJECT_CODES[:]
    if user_id:
        profile = get_or_create_user(user_id=user_id)
        role = profile.get("role", "student")
        if role == "admin":
            allowed = ALL_SUBJECT_CODES[:]
        elif role == "sub_admin":
            allowed = profile.get("managed_subjects", [])
        else:
            allowed = []
        if not allowed:
            return []

    norm_filter_subj: Optional[str] = None
    if subject and subject not in ("all", "전과목", ""):
        norm_filter_subj = normalize_subject_code(subject)

    search_subjects = [norm_filter_subj] if norm_filter_subj else allowed
    db_paths = _get_existing_bank_db_paths(search_subjects)

    items: List[Dict[str, Any]] = []
    for db_p in db_paths:
        conn = sqlite3.connect(str(db_p), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_bank_table_on_conn(conn)
            cur = conn.cursor()
            clauses: List[str] = []
            params: List[Any] = []

            if allowed:
                placeholders = ", ".join(["?"] * len(allowed))
                clauses.append(f"subject IN ({placeholders})")
                params.extend(allowed)

            if norm_filter_subj:
                clauses.append("subject = ?")
                params.append(norm_filter_subj)

            if grade_group and grade_group.strip():
                clauses.append("grade_group = ?")
                params.append(grade_group.strip())

            if unit_name and unit_name.strip():
                clauses.append("unit_name = ?")
                params.append(unit_name.strip())

            if question_type and question_type.strip():
                clauses.append("question_type = ?")
                params.append(question_type.strip())

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cur.execute(
                f"""
                SELECT *
                FROM question_bank
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params + [int(limit)]),
            )
            rows = cur.fetchall()
            for r in rows:
                r_dict = dict(r)
                choices_list: List[Any] = []
                try:
                    parsed = json.loads(r_dict.get("choices_json") or "[]")
                    if isinstance(parsed, list):
                        choices_list = [c if isinstance(c, dict) else str(c) for c in parsed]
                except Exception:
                    choices_list = []

                q_type_val = r_dict.get("question_type") or "객관식"
                clean_q_txt, vis_data, dir_footer, rubric_list = _unpack_visual_meta(
                    r_dict.get("visual_data_json"),
                    question_text=r_dict.get("question_text") or "",
                    question_type=q_type_val,
                )

                subj_code = r_dict.get("subject") or "math"
                items.append(
                    {
                        "id": int(r_dict["id"]),
                        "subject": subj_code,
                        "subject_kr": SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code),
                        "grade": int(r_dict.get("grade") or 4),
                        "grade_group": r_dict.get("grade_group") or "",
                        "unit_name": r_dict.get("unit_name") or "",
                        "sub_topic": r_dict.get("sub_topic") or "",
                        "question_type": q_type_val,
                        "difficulty": r_dict.get("difficulty") or "중",
                        "points": int(r_dict.get("points") or 3),
                        "question_text": clean_q_txt,
                        "choices": choices_list,
                        "visual_data": vis_data,
                        "direction_footer": dir_footer,
                        "rubric": rubric_list,
                        "correct_answer": r_dict.get("correct_answer") or "",
                        "explanation": r_dict.get("explanation") or "",
                        "source_type": r_dict.get("source_type") or "manual",
                        "source_log_id": r_dict.get("source_log_id"),
                        "created_by": r_dict.get("created_by") or "",
                        "created_by_name": r_dict.get("created_by_name") or "",
                        "created_at": r_dict.get("created_at") or "",
                    }
                )
        finally:
            conn.close()

    items.sort(key=lambda x: (x.get("created_at", ""), x.get("id", 0)), reverse=True)
    return items[: int(limit)]


def delete_question_from_bank(bank_id: int, user_id: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """
    문제은행에서 특정 문제를 삭제합니다. (해당 문제의 과목 권한이 있는 부관리자/총 관리자만 삭제 가능)
    """
    init_question_bank_db()
    clean_uid = (user_id or "").strip()
    search_subjects = [normalize_subject_code(subject)] if subject and normalize_subject_code(subject) else None
    db_paths = _get_existing_bank_db_paths(search_subjects)

    for db_p in db_paths:
        conn = sqlite3.connect(str(db_p), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            _ensure_bank_table_on_conn(conn)
            cur = conn.cursor()
            cur.execute("SELECT id, subject, unit_name FROM question_bank WHERE id = ? LIMIT 1", (int(bank_id),))
            row = cur.fetchone()
            if not row:
                continue

            subj_code = row["subject"] or "math"
            if not check_subject_permission(clean_uid, subj_code):
                subj_kr = SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code)
                raise PermissionError(f"'{subj_kr}' 과목 문제를 삭제할 권한이 없습니다.")

            cur.execute("DELETE FROM question_bank WHERE id = ?", (int(bank_id),))
            cur.execute("DELETE FROM question_bank_solved WHERE bank_id = ?", (int(bank_id),))
            conn.commit()
            return {
                "deleted_id": int(bank_id),
                "subject": subj_code,
                "subject_kr": SUBJECT_CODE_TO_LABEL.get(subj_code, subj_code),
                "message": f"문제은행 번호 #{bank_id} 문제가 삭제되었습니다.",
            }
        finally:
            conn.close()

    raise ValueError(f"문제은행 번호 #{bank_id} 문제를 찾을 수 없습니다.")


# ==============================================================================
# 단원별 문제은행 현황((맞춘 문제 / 전체·남은 문제) 표기) 및 문제은행 출제/AI 채점 엔진
# ==============================================================================
def _resolve_user_key(user_id: Optional[str] = None, user_name: Optional[str] = None) -> str:
    uid = (user_id or "").strip()
    if uid and uid.lower() not in ("guest", "게스트"):
        return f"id:{uid}"
    uname = (user_name or "김에듀").strip()
    return f"name:{uname}"


def mark_bank_question_solved(
    bank_id: int,
    subject: str = "math",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
) -> bool:
    """학생이 문제은행 출처 문제를 풀어서 정답(만점)을 맞혔을 때 풀이 완료 기록을 저장합니다."""
    if not bank_id or int(bank_id) <= 0:
        return False
    subj_code = normalize_subject_code(subject or "math") or "math"
    ukey = _resolve_user_key(user_id, user_name)
    conn = _get_bank_conn(subj_code, for_write=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key)
            VALUES (?, ?, ?)
            """,
            (int(bank_id), subj_code, ukey),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _get_solved_bank_ids_for_user(
    conn: sqlite3.Connection,
    subject_code: str,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
) -> set:
    ukey = _resolve_user_key(user_id, user_name)
    cur = conn.cursor()
    cur.execute(
        "SELECT bank_id FROM question_bank_solved WHERE subject = ? AND user_key = ?",
        (subject_code, ukey),
    )
    solved_set = {int(r["bank_id"]) for r in cur.fetchall() if r["bank_id"] is not None}

    # 통합 quiz_logs에 bank_{subject}_{id} 형태로 정답 기록된 내역도 교차 반영
    try:
        ctrl_conn = _get_control_conn()
        try:
            c_cur = ctrl_conn.cursor()
            clean_uid = (user_id or "").strip()
            clean_uname = (user_name or "").strip()
            if clean_uid and clean_uid.lower() not in ("guest", "게스트"):
                c_cur.execute(
                    "SELECT quiz_id FROM quiz_logs WHERE user_id = ? AND LOWER(subject) = ? AND is_correct = 1 AND quiz_id LIKE 'bank_%'",
                    (clean_uid, subject_code),
                )
            elif clean_uname:
                c_cur.execute(
                    "SELECT quiz_id FROM quiz_logs WHERE user_name = ? AND LOWER(subject) = ? AND is_correct = 1 AND quiz_id LIKE 'bank_%'",
                    (clean_uname, subject_code),
                )
            else:
                c_cur.execute("SELECT quiz_id FROM quiz_logs WHERE 1=0")

            for row in c_cur.fetchall():
                qid = str(row["quiz_id"] or "")
                parts = qid.split("_")
                if len(parts) >= 3 and parts[0] == "bank" and parts[2].isdigit():
                    solved_set.add(int(parts[2]))
        finally:
            ctrl_conn.close()
    except Exception:
        pass

    return solved_set


def get_unit_bank_stats(
    subject: str = "math",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    특정 과목의 학년군/대단원/하위주제별 문제은행 총 문제 수, 맞춘 문제 수, 남은 문제 수를 반환합니다.
    프론트엔드에서 토글 비활성화(문제은행 출제 모드) 시 '(2/32)' 표시에 사용됩니다.
    """
    subj_code = normalize_subject_code(subject or "math") or "math"
    conn = _get_bank_conn(subj_code)
    try:
        solved_ids = _get_solved_bank_ids_for_user(conn, subj_code, user_id, user_name)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, grade_group, unit_name, sub_topic FROM question_bank WHERE subject = ?",
            (subj_code,),
        )
        rows = cur.fetchall()

        overall_total = 0
        overall_solved = 0
        by_grade_group: Dict[str, Dict[str, int]] = {}
        by_unit: Dict[str, Dict[str, Dict[str, int]]] = {}
        by_unit_flat: Dict[str, Dict[str, int]] = {}
        by_topic: Dict[str, Dict[str, Dict[str, Dict[str, int]]]] = {}

        def _inc(bucket: Dict[str, int], is_solved: bool) -> None:
            bucket["total"] = bucket.get("total", 0) + 1
            if is_solved:
                bucket["solved"] = bucket.get("solved", 0) + 1
            else:
                bucket.setdefault("solved", 0)
            bucket["remaining"] = max(0, bucket["total"] - bucket["solved"])

        for r in rows:
            bid = int(r["id"])
            g_group = (r["grade_group"] or "").strip() or "기타"
            u_name = (r["unit_name"] or "").strip() or "기본 단원"
            s_topic = (r["sub_topic"] or "").strip()
            is_s = bid in solved_ids

            overall_total += 1
            if is_s:
                overall_solved += 1

            by_grade_group.setdefault(g_group, {"solved": 0, "total": 0, "remaining": 0})
            _inc(by_grade_group[g_group], is_s)

            by_unit.setdefault(g_group, {})
            by_unit[g_group].setdefault(u_name, {"solved": 0, "total": 0, "remaining": 0})
            _inc(by_unit[g_group][u_name], is_s)

            by_unit_flat.setdefault(u_name, {"solved": 0, "total": 0, "remaining": 0})
            _inc(by_unit_flat[u_name], is_s)

            if s_topic:
                by_topic.setdefault(g_group, {})
                by_topic[g_group].setdefault(u_name, {})
                by_topic[g_group][u_name].setdefault(s_topic, {"solved": 0, "total": 0, "remaining": 0})
                _inc(by_topic[g_group][u_name][s_topic], is_s)

        return {
            "subject": subj_code,
            "overall": {
                "solved": overall_solved,
                "total": overall_total,
                "remaining": max(0, overall_total - overall_solved),
            },
            "by_grade_group": by_grade_group,
            "by_unit": by_unit,
            "by_unit_flat": by_unit_flat,
            "units": by_unit_flat,
            "by_topic": by_topic,
        }
    finally:
        conn.close()


def pick_unsolved_bank_question(
    subject: str = "math",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    grade: int = 4,
    grade_group: Optional[str] = None,
    unit_name: Optional[str] = None,
    sub_topic: Optional[str] = None,
    question_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    allow_solved_fallback: bool = False,
) -> Dict[str, Any]:
    """
    문제은행(`question_bank.db`)에서 아직 학생이 맞추지 않은(미풀이) 문제를 1개 추출합니다.
    - 정방향(문제은행 모드, `allow_solved_fallback=False`):
      해당 단원/조건에 문제은행 문제가 아예 없거나(`empty`), 이미 다 풀어서 남은 문제가 없다면(`exhausted`),
      `found: False` 및 사유를 반환하여 자동으로 AI 기반 출제로 전환하도록 합니다.
    - 역방향(AI 연동 실패 시 폴백, `allow_solved_fallback=True`):
      1순위: 해당 단원의 미풀이 문제를 출제 (`is_review_mode: False`).
      2순위: 해당 단원의 미풀이 문제를 모두 풀었지만 기풀이 문제가 존재하면, 이미 풀었던 문제를 복습 모드로 출제 (`is_review_mode: True`, 누적 포인트 미반영).
      3순위: 해당 단원의 문제은행 DB가 아예 비어 있으면 `found: False, reason: "empty"`를 반환하여 에러창을 띄우도록 합니다.
    """
    import random

    subj_code = normalize_subject_code(subject or "math") or "math"
    conn = _get_bank_conn(subj_code)
    try:
        solved_ids = _get_solved_bank_ids_for_user(conn, subj_code, user_id, user_name)
        cur = conn.cursor()

        base_clauses = ["subject = ?"]
        base_params: List[Any] = [subj_code]

        clean_gg = (grade_group or "").strip()
        if clean_gg and clean_gg not in ("custom", "맞춤문제", "랜덤", "전체"):
            base_clauses.append("grade_group = ?")
            base_params.append(clean_gg)

        clean_unit = (unit_name or "").strip()
        if clean_unit and clean_unit not in ("랜덤", "전체", "all"):
            base_clauses.append("unit_name = ?")
            base_params.append(clean_unit)

        clauses = list(base_clauses)
        params = list(base_params)
        clean_topic = (sub_topic or "").strip()
        if clean_topic and clean_topic not in ("랜덤", "전체", "all", "하위 주제 없음"):
            clauses.append("(sub_topic = ? OR sub_topic = '')")
            params.append(clean_topic)

        where_sql = " AND ".join(clauses)
        cur.execute(f"SELECT * FROM question_bank WHERE {where_sql} ORDER BY id ASC", tuple(params))
        unit_rows = cur.fetchall()

        # 세부주제 필터로 조회했을 때 0건이면 같은 대단원 전체에서 재조회
        if len(unit_rows) == 0 and len(clauses) > len(base_clauses):
            base_where_sql = " AND ".join(base_clauses)
            cur.execute(f"SELECT * FROM question_bank WHERE {base_where_sql} ORDER BY id ASC", tuple(base_params))
            unit_rows = cur.fetchall()

        total_in_scope = len(unit_rows)
        if total_in_scope == 0:
            return {
                "found": False,
                "reason": "empty",
                "is_review_mode": False,
                "total": 0,
                "solved": 0,
                "remaining": 0,
                "message": "해당 단원에 등록된 문제은행 문제가 없어 자동으로 'AI 기반 출제' 모드로 전환합니다.",
            }

        unsolved_in_scope = [r for r in unit_rows if int(r["id"]) not in solved_ids]
        solved_in_scope = total_in_scope - len(unsolved_in_scope)
        is_review_mode = False

        if len(unsolved_in_scope) == 0:
            if not allow_solved_fallback:
                return {
                    "found": False,
                    "reason": "exhausted",
                    "is_review_mode": False,
                    "total": total_in_scope,
                    "solved": solved_in_scope,
                    "remaining": 0,
                    "message": f"해당 단원의 문제은행 문제({total_in_scope}/{total_in_scope})를 모두 맞혀서 자동으로 'AI 기반 출제' 모드로 전환합니다!",
                }
            # AI 출제도 실패하고 해당 단원 미풀이 문제도 모두 소진된 경우 -> 이미 풀었던 문제라도 복습 모드로 출제!
            is_review_mode = True
            candidate_pool = list(unit_rows)
        else:
            candidate_pool = list(unsolved_in_scope)

        # 난이도 및 문제유형 필터가 지정된 경우 우선 매칭하되, 해당 세부 유형에 문제가 없으면 단원 내 후보 문제에서 출제
        clean_qtype = (question_type or "").strip()
        clean_diff = (difficulty or "").strip()
        filtered = candidate_pool
        if clean_qtype and clean_qtype not in ("랜덤", "전체", "all"):
            q_matches = [r for r in filtered if (r["question_type"] or "") == clean_qtype]
            if q_matches:
                filtered = q_matches
        if clean_diff and clean_diff not in ("랜덤", "전체", "all"):
            d_matches = [r for r in filtered if (r["difficulty"] or "") == clean_diff]
            if d_matches:
                filtered = d_matches

        chosen = random.choice(filtered)
        chosen_dict = dict(chosen)
        bid = int(chosen_dict["id"])
        q_type = chosen_dict.get("question_type") or "객관식"
        diff = chosen_dict.get("difficulty") or "중"
        pts = int(chosen_dict.get("points") or DIFFICULTY_TO_POINTS.get(diff, 3))

        choices_list: List[Any] = []
        try:
            parsed = json.loads(chosen_dict.get("choices_json") or "[]")
            if isinstance(parsed, list):
                choices_list = [c if isinstance(c, dict) else str(c) for c in parsed]
        except Exception:
            choices_list = []

        if q_type == "ox" and not choices_list:
            choices_list = ["O", "X"]

        c_ans = str(chosen_dict.get("correct_answer") or "").strip()
        # 객관식에서 정답이 보기 문자열로 저장된 경우 보기 번호(1~4)로 정규화 지원
        if q_type == "객관식" and choices_list and c_ans not in ("1", "2", "3", "4"):
            norm_ca = re.sub(r"\s+", "", c_ans).replace("$", "").lower()
            for idx, opt in enumerate(choices_list):
                if not isinstance(opt, dict) and re.sub(r"\s+", "", str(opt)).replace("$", "").lower() == norm_ca:
                    c_ans = str(idx + 1)
                    break

        expl = str(chosen_dict.get("explanation") or "").strip()
        if not expl:
            expl = f"문제은행 등록 문제입니다. 정답은 {chosen_dict.get('correct_answer')}입니다."

        clean_q_txt, vis_data, dir_footer, rubric_list = _unpack_visual_meta(
            chosen_dict.get("visual_data_json"),
            question_text=chosen_dict.get("question_text") or "",
            question_type=q_type,
        )

        # 고유 quiz_id를 bank_{과목}_{번호}로 고정하여 이미 맞힌 문제를 복습할 때 중복 점수 누적을 원천 차단
        quiz_obj = {
            "quiz_id": f"bank_{subj_code}_{bid}",
            "bank_id": bid,
            "source": "question_bank",
            "source_type": "question_bank",
            "is_review_mode": is_review_mode,
            "grade": int(chosen_dict.get("grade") or grade or 4),
            "grade_group": chosen_dict.get("grade_group") or clean_gg or "3~4학년군",
            "unit": chosen_dict.get("unit_name") or clean_unit or "(1) 수와 연산",
            "topic": chosen_dict.get("sub_topic") or chosen_dict.get("unit_name") or "문제은행",
            "difficulty": diff,
            "score": pts,
            "question_type": q_type,
            "question": clean_q_txt,
            "visual_data": vis_data,
            "direction_footer": dir_footer,
            "options": choices_list,
            "correct_answer": c_ans,
            "solution": expl,
            "rubric": rubric_list,
        }

        return {
            "found": True,
            "reason": "review_solved" if is_review_mode else "unsolved",
            "is_review_mode": is_review_mode,
            "quiz": quiz_obj,
            "total": total_in_scope,
            "solved": solved_in_scope,
            "remaining": len(unsolved_in_scope),
            "message": (
                "AI 연결이 원활하지 않고 해당 단원의 새 문제를 모두 해결하여, 이미 풀었던 문제은행 문제를 복습 모드로 출제합니다. (추가 누적 포인트 미반영)"
                if is_review_mode
                else "문제은행에서 미풀이 문제를 출제했습니다."
            ),
        }
    finally:
        conn.close()


def grade_bank_question_by_ai(
    subject: str,
    question_type: str,
    difficulty: str,
    points: int,
    question_text: str,
    correct_answer: str,
    user_answer: str,
    explanation: str = "",
    choices: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    [전 과목 공용] 문제은행(`question_bank.db`) 수동 출제 문제에 대한 AI 채점 함수:
    - 주관식(단답형): 1차 정규화 일치 확인 후, 불일치 시 Gemini AI 의미적/수치적 동치 채점 수행
    - 서술형: Gemini AI 문맥 및 채점기준(explanation/correct_answer) 기반 부분 점수(0~points점) 및 피드백 채점
    """
    subj_code = normalize_subject_code(subject or "math") or "math"
    subj_kr = SUBJECT_CODE_TO_LABEL.get(subj_code, "초등")
    score = int(points or DIFFICULTY_TO_POINTS.get(difficulty, 3))

    # 수학 과목은 기존 수학 전용 고정밀 채점 엔진 사용
    if subj_code == "math":
        from app.subjects.math.service import grade_math_submission
        return grade_math_submission(
            question_type=question_type,
            difficulty=difficulty,
            score=score,
            user_answer=user_answer,
            correct_answer=correct_answer,
            solution=explanation,
            question=question_text,
            rubric=[],
            options=choices or [],
        )

    from app.subjects.math.service import _call_gemini_json

    u_ans = (user_answer or "").strip()
    c_ans = (correct_answer or "").strip()
    norm_qtype = (question_type or "객관식").strip()

    # 1) OX 및 객관식
    if norm_qtype in ("ox", "객관식", "multiple_choice"):
        nu = re.sub(r"\s+", "", u_ans).lower()
        nc = re.sub(r"\s+", "", c_ans).lower()
        is_corr = (nu == nc)
        if not is_corr and choices and isinstance(choices, list):
            if u_ans.isdigit() and 1 <= int(u_ans) <= len(choices):
                opt_val = re.sub(r"\s+", "", str(choices[int(u_ans) - 1])).lower()
                if opt_val == nc:
                    is_corr = True
            elif c_ans.isdigit() and 1 <= int(c_ans) <= len(choices):
                opt_val = re.sub(r"\s+", "", str(choices[int(c_ans) - 1])).lower()
                if opt_val == nu:
                    is_corr = True
        earned = score if is_corr else 0
        return {
            "is_correct": is_corr,
            "earned_score": earned,
            "max_score": score,
            "feedback": f"정답입니다! 참 잘했어요. (+{earned}점)" if is_corr else "아쉬워요! 해설을 확인하며 다시 정리해 보세요.",
            "user_answer": u_ans,
            "correct_answer": c_ans,
            "solution": explanation,
        }

    # 2) 단답형 주관식 (전 과목 AI 의미적 동치 채점)
    if norm_qtype in ("단답형", "short_answer", "주관식"):
        if not u_ans:
            return {
                "is_correct": False,
                "earned_score": 0,
                "max_score": score,
                "feedback": "답안을 입력해 주세요!",
                "user_answer": "",
                "correct_answer": c_ans,
                "solution": explanation,
            }
        if re.sub(r"\s+", "", u_ans).lower() == re.sub(r"\s+", "", c_ans).lower():
            return {
                "is_correct": True,
                "earned_score": score,
                "max_score": score,
                "feedback": f"정답입니다! 정확하게 잘 적었어요. (+{score}점)",
                "user_answer": u_ans,
                "correct_answer": c_ans,
                "solution": explanation,
            }

        prompt = f"""당신은 초등학교 {subj_kr} 과목 단답형 주관식 채점 교사입니다.
학생이 제출한 답안이 모범 정답과 의미적·내용적으로 같은 정답(동치)인지 판별하세요.

[과목]: 초등 {subj_kr}
[문제 지문]: {question_text}
[모범 정답]: {c_ans}
[해설/참고]: {explanation or '없음'}
[학생 제출 답안]: {u_ans}

[채점 기준]
1. 띄어쓰기 차이, 조사(은/는/이/가/을/를) 유무, 괄호 표기, 단위 유무, 명백한 동의어나 같은 뜻의 표현은 모두 정답(`is_correct: true`)으로 인정하세요.
2. 핵심 개념이나 답이 틀린 경우에만 오답(`is_correct: false`)으로 판정하고 짧은 힌트 피드백을 작성하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "is_correct": true,
  "feedback": "정답입니다! 의미를 정확하게 알고 있네요!"
}}"""
        try:
            ai_res = _call_gemini_json(prompt, temperature=0.0)
            is_corr = bool(ai_res.get("is_correct", False))
            earned = score if is_corr else 0
            return {
                "is_correct": is_corr,
                "earned_score": earned,
                "max_score": score,
                "feedback": ai_res.get("feedback", f"정답입니다! (+{score}점)" if is_corr else "아쉬워요! 다시 한 번 생각해 보세요."),
                "user_answer": u_ans,
                "correct_answer": c_ans,
                "solution": explanation,
            }
        except Exception:
            return {
                "is_correct": False,
                "earned_score": 0,
                "max_score": score,
                "feedback": "아쉬워요! 정답과 해설을 확인해 보세요.",
                "user_answer": u_ans,
                "correct_answer": c_ans,
                "solution": explanation,
            }

    # 3) 서술형 (전 과목 AI 문맥 부분 점수 채점)
    if not u_ans:
        return {
            "is_correct": False,
            "earned_score": 0,
            "max_score": score,
            "feedback": "서술형 답안을 입력해 주세요!",
            "user_answer": "",
            "correct_answer": c_ans,
            "solution": explanation,
        }

    desc_prompt = f"""당신은 초등학교 {subj_kr} 과목 서술형 답안을 채점하는 따뜻하고 공정한 교사입니다.
학생이 작성한 서술형 답안을 모범 정답 및 해설에 비추어 0점부터 {score}점 만점까지 부분 점수를 포함해 공정하게 채점하세요.

[과목]: 초등 {subj_kr}
[문제 지문]: {question_text}
[모범 정답]: {c_ans}
[해설 및 채점 기준]: {explanation or c_ans}
[배점]: {score}점 만점
[학생 제출 답안]: {u_ans}

[채점 지침]
1. 모범 정답과 표현이 완전히 같지 않아도 핵심 의미와 논리가 맞으면 만점({score}점)을 부여하세요.
2. 핵심 내용 중 일부만 맞았거나 설명이 조금 부족하면 1~{max(1, score - 1)}점의 부분 점수를 부여하세요.
3. 전혀 무관한 내용이면 0점을 부여하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "earned_score": {score},
  "is_correct": true,
  "feedback": "핵심 내용을 정확하고 조리 있게 잘 서술했어요!"
}}"""
    try:
        ai_res = _call_gemini_json(desc_prompt, temperature=0.0)
        earned = max(0, min(int(ai_res.get("earned_score", 0)), score))
        is_pass = earned >= (score * 0.6)
        return {
            "is_correct": is_pass,
            "earned_score": earned,
            "max_score": score,
            "feedback": ai_res.get("feedback", "수고하셨습니다!"),
            "user_answer": u_ans,
            "correct_answer": c_ans,
            "solution": explanation,
        }
    except Exception:
        return {
            "is_correct": False,
            "earned_score": 0,
            "max_score": score,
            "feedback": "채점 중 오류가 발생했습니다.",
            "user_answer": u_ans,
            "correct_answer": c_ans,
            "solution": explanation,
        }

