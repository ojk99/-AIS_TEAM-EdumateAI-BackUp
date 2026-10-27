"""
================================================================================
[EduMate AI 팀원 배포용 표준 DB 모듈 템플릿 - sample/quiz_logs.py]
================================================================================
🚨 [팀원 및 AI 어시스턴트(Antigravity/Cursor/ChatGPT) 절대 준수 경고문] 🚨
1. 절대로 `quiz_logs` 테이블의 컬럼(열) 이름을 변경하거나, 열을 임의로 삭제·추가하지 마세요!
   - 모든 과목(국어, 영어, 수학, 사회, 과학, 한문)이 나중에 조장님의 전 과목 통합 DB(edumate.db)와
     100% 동일한 테이블 구조로 병합되어야 하며, 추후 통합 AI 튜터가 이 표준 열들을 조회합니다.
2. 본인 과목에서 사용하지 않거나 해당 사항이 없는 열(예: unit, topic, solution, chat_history 등)이 있더라도
   절대 열을 지우지 마세요!
   - ⚠️ 특히 해당 사항이 없는 열에 숫자 `0`을 넣으면 '0점'이나 '오답(0)'으로 잘못 집계될 수 있으므로,
     해당 사항이 없는 항목은 반드시 파이썬 `None` (DB에서는 전용 결측값인 `NULL`로 자동 기록됨)으로 넣어주세요!
   - 아래 `save_quiz_log()` 함수에 이미 선택 항목들의 기본값이 `None`(`NULL`)으로 설정되어 있으므로,
     본인 과목에서 안 쓰는 항목은 아예 인자를 생략하고 호출하면 자동으로 `NULL`(해당사항 없음)로 안전하게 저장됩니다.
3. 조원 수정 사항: 아래 `SUBJECT_NAME = "sample"` 줄만 본인 과목 영문명
   ("korean", "english", "social", "science", "hanja")으로 바꾸면 세팅이 끝납니다!
================================================================================
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ★ 조원 수정 구역: 본인 담당 과목 영문명으로 변경하세요! (예: "korean", "english", "social", "science", "hanja")
SUBJECT_NAME = "english"
SUBJECT_CODE = "english"

# 아직 문제를 풀지 않은 학생의 학년 선택값을 유지하기 위한 메모리 캐시
_USER_GRADE_CACHE: Dict[str, int] = {"김에듀": 4}


def _resolve_db_path() -> Path:
    """
    [단독 폴더 환경 & 통합 프로젝트 환경 100% 자동 호환 경로 탐색기]
    - 경우 1 (조장님 통합 환경): 상위 또는 현재 작업 폴더에 data/edumate.db 가 이미 있거나 app/main.py, main.py가 존재하면
      팀 공통 중앙 DB인 data/edumate.db 를 자동 생성/연결합니다.
    - 경우 2 (팀원 단독 폴더 환경): data 폴더나 상위 프로젝트 폴더 없이 본인 과목 폴더만 단독으로 테스트할 때는
      에러 없이 본인 과목 폴더 내부에 'edumate.db' 파일을 자동 생성합니다.
    """
    current_dir = Path(__file__).resolve().parent
    search_dirs = [
        current_dir.parent.parent.parent,
        current_dir.parent.parent,
        current_dir.parent,
        current_dir,
        Path.cwd(),
    ]
    for p in search_dirs:
        # 이미 존재하는 data/edumate.db가 있으면 최우선 연결
        if (p / "data" / "edumate.db").exists():
            return p / "data" / "edumate.db"
        # 통합 프로젝트 루트 감지 시 data/edumate.db 생성/연결
        if (p / "app" / "main.py").exists() or (p / "main.py").exists():
            data_dir = p / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir / "edumate.db"

    # 작업 디렉터리에 data 폴더가 있는 경우
    cwd_data = Path.cwd() / "data"
    if cwd_data.exists():
        return cwd_data / "edumate.db"

    # 팀원이 본인 과목 폴더만 단독으로 가지고 있을 때
    return current_dir / "edumate.db"


DB_PATH = _resolve_db_path()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    """
    전 과목 공통 표준 테이블(quiz_logs) 및 통합 회원 테이블(users, accounts) 자동 생성
    ⚠️ 주의: quiz_logs 테이블 18개 표준 열 이름과 순서는 절대 변경하지 않습니다.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT NULL,
                quiz_id TEXT NOT NULL DEFAULT '',
                user_name TEXT NOT NULL DEFAULT '김에듀',
                grade INTEGER DEFAULT NULL,
                subject TEXT NOT NULL DEFAULT 'sample',
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_id ON quiz_logs (user_id)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_subj ON quiz_logs (user_name, subject)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_quiz_id ON quiz_logs (user_name, quiz_id)"
        )
        # 1. 조장님 통합 포털 users 테이블 (전과목 누적 총점 total_score 핵심 관리)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_name TEXT PRIMARY KEY,
                total_score INTEGER NOT NULL DEFAULT 0,
                grade INTEGER NOT NULL DEFAULT 4,
                pokemon_type TEXT NOT NULL DEFAULT 'grass',
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # 2. 통합 로그인/회원 계정 accounts 테이블
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                password TEXT NOT NULL DEFAULT '1234',
                user_name TEXT NOT NULL,
                grade INTEGER NOT NULL DEFAULT 4,
                role TEXT NOT NULL DEFAULT 'student',
                pokemon_type TEXT NOT NULL DEFAULT 'grass',
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# [포켓몬 5대 타입 진화 등급 (9단계 × 각 5티어) 및 경험치통(EXP) 자동 환산 체계]
# - 회원 DB에 별도의 레벨 등급 칼럼을 두지 않고, 전 과목 통합 누적 총점(total_score)으로 자동 환산합니다.
# - 1등급(알) 이후 풀(초록)/불(빨강)/물(파랑)/전기(노랑)/에스퍼(분홍) 5가지 타입을 언제든 스위칭할 수 있습니다.
# - 5등급(메가진화 단계)의 1티어부터 경험치통(EXP)이 대폭 상승합니다!
# ---------------------------------------------------------------------------
POKEMON_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "grass": {
        "type_no": 1,
        "type_kr": "풀",
        "color_name": "초록색",
        "color_hex": "#22c55e",
        "stages": ["알", "이상해씨", "이상해풀", "이상해꽃", "메가이상해꽃", "비리디온", "세레비", "레쿠쟈", "메가레쿠쟈"],
        "emojis": ["", "", "", "", "", "", "", "", ""],  # 추후 단계별 포켓몬 이모지 입력 슬롯 (1~9단계)
    },
    "fire": {
        "type_no": 2,
        "type_kr": "불",
        "color_name": "빨간색",
        "color_hex": "#ef4444",
        "stages": ["알", "파이리", "리자드", "리자몽", "메가리자몽X", "파이어", "비크티니", "그란돈", "원시그란돈"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
    "water": {
        "type_no": 3,
        "type_kr": "물",
        "color_name": "파란색",
        "color_hex": "#3b82f6",
        "stages": ["알", "꼬부기", "어니부기", "거북왕", "메가거북왕", "스이쿤", "마나피", "가이오가", "원시가이오가"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
    "electric": {
        "type_no": 4,
        "type_kr": "전기",
        "color_name": "노란색",
        "color_hex": "#eab308",
        "stages": ["알", "피츄", "피카츄", "라이츄", "메가라이츄X", "레지에레키", "제라오라", "제크로무", "블랙큐레무"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
    "psychic": {
        "type_no": 5,
        "type_kr": "에스퍼",
        "color_name": "분홍색",
        "color_hex": "#ec4899",
        "stages": ["알", "케이시", "윤겔라", "후딘", "메가후딘", "크레세리아", "뮤", "뮤츠", "메가뮤츠Y"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
}

# 9개 등급(stage_idx 0~8) × 각 5개 티어([5티어, 4티어, 3티어, 2티어, 1티어]) 경험치통(EXP)
# ★ 5등급(stage_idx=4, 예: 메가이상해꽃)의 1티어부터 경험치통이 대폭 늘어납니다!
STAGE_TIER_EXP_TABLE: List[List[int]] = [
    [10, 10, 10, 10, 10],         # 1등급 (알): 티어당 10 EXP (총 50점 달성 시 2단계 부화)
    [15, 15, 15, 15, 15],         # 2등급 (이상해씨 등): 티어당 15 EXP
    [25, 25, 25, 25, 25],         # 3등급 (이상해풀 등): 티어당 25 EXP
    [40, 40, 40, 40, 40],         # 4등급 (이상해꽃 등): 티어당 40 EXP
    [60, 60, 60, 60, 180],        # 5등급 (메가이상해꽃 등): 5~2티어 60 EXP / ★1티어부터 180 EXP로 대폭 상승!
    [250, 250, 250, 250, 250],    # 6등급 (비리디온 등): 티어당 250 EXP
    [350, 350, 350, 350, 350],    # 7등급 (세레비 등): 티어당 350 EXP
    [500, 500, 500, 500, 500],    # 8등급 (레쿠쟈 등): 티어당 500 EXP
    [800, 800, 800, 800, 800],    # 9등급 (메가레쿠쟈 등): 티어당 800 EXP
]


def calculate_level_tier(total_score: int, pokemon_type: str = "grass") -> Dict[str, Any]:
    """
    전 과목 통합 누적 총점(total_score)과 선택된 포켓몬 타입(grass/fire/water/electric/psychic)으로
    현재 포켓몬 등급명, 티어(5~1티어), 글자색, 경험치통(EXP)을 자동 환산합니다.
    - 1단계(알)일 때는 글자색이 짙은 회색(#64748b)이며, 2단계(알 부화, 누적 50점 이상)부터 타입(글자색) 선택이 활성화됩니다.
    """
    ptype = pokemon_type if pokemon_type in POKEMON_TYPE_CONFIG else "grass"
    tcfg = POKEMON_TYPE_CONFIG[ptype]
    stages = tcfg["stages"]
    emojis = tcfg.get("emojis", [""] * 9)

    score = max(0, int(total_score or 0))
    remaining = score
    level_num = 1

    for s_idx, tier_exps in enumerate(STAGE_TIER_EXP_TABLE):
        poke_name = stages[s_idx]
        poke_emoji = emojis[s_idx] if s_idx < len(emojis) else ""
        is_egg_stage = (s_idx == 0)
        effective_color_hex = "#64748b" if is_egg_stage else tcfg["color_hex"]
        effective_color_name = "짙은 회색" if is_egg_stage else tcfg["color_name"]

        for t_idx, cap in enumerate(tier_exps):
            tier_num = 5 - t_idx  # 5티어 -> 4티어 -> 3티어 -> 2티어 -> 1티어
            is_max_tier = (s_idx == len(STAGE_TIER_EXP_TABLE) - 1 and tier_num == 1)
            if remaining < cap or is_max_tier:
                current_exp = min(remaining, cap) if is_max_tier else remaining
                progress_pct = 100 if (is_max_tier and remaining >= cap) else min(100, int(round((current_exp / cap) * 100)))
                next_remain = 0 if (is_max_tier and remaining >= cap) else max(0, cap - remaining)

                if is_max_tier:
                    next_label = "최고 등급 달성 (MAX)"
                elif tier_num > 1:
                    next_label = f"{poke_name} {tier_num - 1}티어"
                else:
                    next_poke = stages[s_idx + 1]
                    next_label = f"{next_poke} 5티어"

                full_title = f"{poke_name} {tier_num}티어"
                return {
                    "pokemon_type": ptype,
                    "type_kr": "알" if is_egg_stage else tcfg["type_kr"],
                    "color_name": effective_color_name,
                    "color_hex": effective_color_hex,
                    "can_select_type": not is_egg_stage,
                    "stage_num": s_idx + 1,
                    "level_num": level_num,
                    "level": level_num,
                    "pokemon_name": poke_name,
                    "pokemon_emoji": poke_emoji,
                    "gem_name": poke_name,
                    "gem_icon": poke_emoji,
                    "tier": tier_num,
                    "full_title": full_title,
                    "tier_label": full_title,
                    "badge_text": full_title,
                    "current_exp": current_exp,
                    "tier_exp_max": cap,
                    "max_exp": cap,
                    "progress_pct": progress_pct,
                    "exp_percent": progress_pct,
                    "next_tier_remain": next_remain,
                    "next_tier_need": next_remain,
                    "next_tier_label": next_label,
                }
            remaining -= cap
            level_num += 1

    last_poke = stages[-1]
    last_emoji = emojis[-1] if emojis else ""
    return {
        "pokemon_type": ptype,
        "type_kr": tcfg["type_kr"],
        "color_name": tcfg["color_name"],
        "color_hex": tcfg["color_hex"],
        "can_select_type": True,
        "stage_num": 9,
        "level_num": 45,
        "level": 45,
        "pokemon_name": last_poke,
        "pokemon_emoji": last_emoji,
        "gem_name": last_poke,
        "gem_icon": last_emoji,
        "tier": 1,
        "full_title": f"{last_poke} 1티어",
        "tier_label": f"{last_poke} 1티어",
        "badge_text": f"{last_poke} 1티어",
        "current_exp": 800,
        "tier_exp_max": 800,
        "max_exp": 800,
        "progress_pct": 100,
        "exp_percent": 100,
        "next_tier_remain": 0,
        "next_tier_need": 0,
        "next_tier_label": "최고 등급 달성 (MAX)",
    }


def get_user_status(
    user_name: str = "김에듀",
    grade: Optional[int] = None,
    pokemon_type: str = "grass",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    별도의 회원 레벨 칼럼 없이 quiz_logs 단일 통합 테이블에서
    학생의 학년, 현재 과목 점수, 전 과목 통합 누적 총점(total_score) 및 포켓몬 진화 등급/티어를 실시간 환산합니다.
    """
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip() or None

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

        if grade is not None and 1 <= grade <= 6:
            _USER_GRADE_CACHE[clean_name] = int(grade)

        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN subject = ? THEN earned_score ELSE 0 END), 0) AS subject_score,
                COALESCE(SUM(earned_score), 0) AS total_score,
                (SELECT grade FROM quiz_logs WHERE ((user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?)) AND grade IS NOT NULL ORDER BY id DESC LIMIT 1) AS latest_grade
            FROM quiz_logs
            WHERE ((user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))
            """,
            (SUBJECT_NAME, clean_id, clean_name, clean_id, clean_name),
        )
        row = cur.fetchone()
        db_grade = row["latest_grade"] if (row and row["latest_grade"]) else None
        resolved_grade = (
            int(grade)
            if (grade and 1 <= grade <= 6)
            else (_USER_GRADE_CACHE.get(clean_name) or (int(db_grade) if db_grade else 4))
        )
        integrated_score = int(row["total_score"]) if row else 0
        try:
            cur.execute("SELECT total_score FROM users WHERE user_name = ?", (clean_name,))
            u_row = cur.fetchone()
            if u_row and u_row["total_score"] is not None:
                integrated_score = max(integrated_score, int(u_row["total_score"]))
        except Exception:
            pass

        level_info = calculate_level_tier(integrated_score, pokemon_type=pokemon_type)
        return {
            "user_name": clean_name,
            "user_id": clean_id,
            "grade": resolved_grade,
            "subject_score": int(row["subject_score"]) if row else 0,
            "total_score": integrated_score,  # 전 과목 통합 누적 총점!
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
    is_correct: bool = False,
    is_favorite: Optional[int] = None,
    chat_history: Optional[str] = None,
    is_solution_revealed: bool = False,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    채점 결과를 통합 quiz_logs 테이블에 기록합니다.
    - 본인 과목에서 해당 사항이 없는 항목(예: unit, topic, solution, is_favorite, chat_history 등)은
      전달하지 않거나 `None`을 넣으면 DB에 숫자 0이 아닌 전용 결측값(`NULL`)으로 안전하게 저장됩니다!
    - 같은 문제(quiz_id)를 다시 제출한 경우 기존 최고점 대비 오른 차액(added_score)만 반영하여 점수 중복 누적을 방지합니다.
    """
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip() or None

    if grade is not None and 1 <= grade <= 6:
        _USER_GRADE_CACHE[clean_name] = int(grade)
    effective_grade = int(grade) if (grade is not None and 1 <= grade <= 6) else _USER_GRADE_CACHE.get(clean_name)
    now = _now_str()
    effective_quiz_id = quiz_id or f"{SUBJECT_NAME}_{now}_{question[:20]}"

    conn = _get_conn()
    try:
        cur = conn.cursor()
        # [폴백] 만약 user_id가 비어있다면 accounts 테이블에서 해당 user_name의 user_id를 자동 조회
        if not clean_id:
            try:
                cur.execute("SELECT user_id FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1", (clean_name,))
                a_row = cur.fetchone()
                if a_row:
                    clean_id = a_row["user_id"]
            except Exception:
                pass

        cur.execute(
            """
            SELECT id, earned_score, is_correct
            FROM quiz_logs
            WHERE ((user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))
              AND subject = ? AND quiz_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (clean_id, clean_name, SUBJECT_NAME, effective_quiz_id),
        )
        existing = cur.fetchone()

        added_score = 0
        if existing:
            log_id = existing["id"]
            prev_best = int(existing["earned_score"] or 0)
            if not is_solution_revealed and earned_score > prev_best:
                added_score = earned_score - prev_best
                new_best = earned_score
            else:
                new_best = prev_best

            new_is_correct = 1 if (is_correct or existing["is_correct"]) else 0
            cur.execute(
                """
                UPDATE quiz_logs
                SET user_id = COALESCE(?, user_id), grade = ?, user_answer = ?, earned_score = ?, is_correct = ?, solved_at = ?
                WHERE id = ?
                """,
                (clean_id, effective_grade, user_answer, new_best, new_is_correct, now, log_id),
            )
            best_score = new_best
        else:
            added_score = 0 if is_solution_revealed else max(0, int(earned_score))
            best_score = added_score
            cur.execute(
                """
                INSERT INTO quiz_logs (
                    user_id, quiz_id, user_name, grade, subject, unit, topic,
                    difficulty, question_type, question, user_answer,
                    correct_answer, solution, earned_score, is_correct,
                    is_favorite, chat_history, solved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_id,
                    effective_quiz_id,
                    clean_name,
                    effective_grade,
                    SUBJECT_NAME,
                    unit,          # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    topic,         # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    difficulty,    # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    question_type, # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    question or "",
                    user_answer,
                    correct_answer,
                    solution,      # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    best_score,
                    1 if is_correct else 0,
                    is_favorite,   # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    chat_history,  # 해당사항 없으면 None -> DB에 NULL로 저장됨
                    now,
                ),
            )
            log_id = cur.lastrowid

        # -------------------------------------------------------------------
        # [핵심] 조장님 전과목 통합 users 테이블 및 accounts 테이블 total_score 자동 합산
        # -------------------------------------------------------------------
        if added_score > 0:
            try:
                # 1) users 테이블: 이미 존재하면 누적 점수 합산, 없으면 신규 생성
                cur.execute("SELECT total_score FROM users WHERE user_name = ?", (clean_name,))
                u_row = cur.fetchone()
                if u_row:
                    cur.execute(
                        "UPDATE users SET total_score = total_score + ?, grade = COALESCE(?, grade) WHERE user_name = ?",
                        (added_score, effective_grade, clean_name),
                    )
                else:
                    cur.execute(
                        "INSERT INTO users (user_name, total_score, grade, created_at) VALUES (?, ?, ?, ?)",
                        (clean_name, added_score, effective_grade or 4, now),
                    )
            except Exception:
                pass

            try:
                # 2) accounts 테이블 동기화
                if clean_id:
                    cur.execute("SELECT user_id FROM accounts WHERE user_id = ?", (clean_id,))
                    if cur.fetchone():
                        cur.execute(
                            "UPDATE accounts SET grade = COALESCE(?, grade) WHERE user_id = ?",
                            (effective_grade, clean_id),
                        )
                else:
                    cur.execute("SELECT user_id FROM accounts WHERE user_name = ?", (clean_name,))
                    if cur.fetchone():
                        cur.execute(
                            "UPDATE accounts SET grade = COALESCE(?, grade) WHERE user_name = ?",
                            (effective_grade, clean_name),
                        )
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()

    status = get_user_status(clean_name, _USER_GRADE_CACHE.get(clean_name, effective_grade or 4), user_id=clean_id)
    return {
        "log_id": log_id,
        "quiz_id": effective_quiz_id,
        "user_id": clean_id,
        "added_score": added_score,
        "best_score": best_score,
        "subject_score": status["subject_score"],
        "total_score": status["total_score"],
    }


def get_recent_logs_for_custom(user_name: str = "김에듀", limit: int = 20) -> List[Dict[str, Any]]:
    """맞춤문제 출제를 위해 해당 학생의 최근 풀이/오답 기록을 DB에서 조회합니다."""
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT grade, unit, topic, difficulty, question_type, is_correct, earned_score
            FROM quiz_logs
            WHERE user_name = ? AND subject = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (clean_name, SUBJECT_NAME, limit),
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


def append_chat_message(log_id: int, student_question: str, ai_reply: str) -> Dict[str, Any]:
    """
    해당 문제 풀이 기록(log_id)에 학생의 추가 질문과 AI 답변을 대화 내역(chat_history)으로 누적 저장합니다.
    """
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT chat_history FROM quiz_logs WHERE id = ?", (log_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": f"log_id {log_id}를 찾을 수 없습니다."}

        raw_history = row["chat_history"]
        try:
            history = json.loads(raw_history) if raw_history else []
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []

        now = _now_str()
        if student_question:
            history.append({
                "role": "student",
                "content": student_question,
                "message": student_question,
                "time": now,
                "timestamp": now
            })
        if ai_reply:
            history.append({
                "role": "teacher",
                "content": ai_reply,
                "message": ai_reply,
                "time": now,
                "timestamp": now
            })

        updated_json = json.dumps(history, ensure_ascii=False)
        cur.execute("UPDATE quiz_logs SET chat_history = ? WHERE id = ?", (updated_json, log_id))
        conn.commit()
        return {"success": True, "log_id": log_id, "chat_history": history}
    finally:
        conn.close()


def toggle_favorite(log_id: int) -> Dict[str, Any]:
    """
    해당 문제 풀이 기록(log_id)의 즐겨찾기(is_favorite) 상태를 토글(1 <-> 0)합니다.
    """
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_favorite FROM quiz_logs WHERE id = ?", (log_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": f"log_id {log_id}를 찾을 수 없습니다."}

        current_fav = 1 if row["is_favorite"] == 1 else 0
        new_fav = 0 if current_fav == 1 else 1
        cur.execute("UPDATE quiz_logs SET is_favorite = ? WHERE id = ?", (new_fav, log_id))
        conn.commit()
        return {"success": True, "log_id": log_id, "is_favorite": new_fav}
    finally:
        conn.close()


def get_weakest_unit_and_topic(user_name: str = "김에듀", user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    과거 오답 데이터를 분석하여 해당 학생이 가장 많이 틀린 취약 단원(unit) 및 주제(topic)를 추출합니다.
    """
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip() or None
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

        cur.execute(
            """
            SELECT unit, topic, COUNT(*) as wrong_count
            FROM quiz_logs
            WHERE ((user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))
              AND subject = ? AND is_correct = 0 AND unit IS NOT NULL AND unit != ''
            GROUP BY unit, topic
            ORDER BY wrong_count DESC
            LIMIT 1
            """,
            (clean_id, clean_name, SUBJECT_NAME),
        )
        row = cur.fetchone()
        if row:
            return {
                "unit": row["unit"],
                "topic": row["topic"],
                "wrong_count": row["wrong_count"],
            }
        return {"unit": None, "topic": None, "wrong_count": 0}
    finally:
        conn.close()


def get_or_create_user(
    user_name: str = "김에듀",
    grade: Optional[int] = None,
    pokemon_type: str = "grass",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    통합 로그인 계정(accounts)을 확인/생성하고,
    학생의 전과목 통합 누적점수(total_score) 및 5대 포켓몬 진화 등급 정보(level_info)를 함께 반환합니다.
    """
    init_db()
    clean_name = (user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip() or None
    resolved_grade = int(grade) if (grade and 1 <= grade <= 6) else _USER_GRADE_CACHE.get(clean_name, 4)
    ptype = pokemon_type if pokemon_type in POKEMON_TYPE_CONFIG else "grass"

    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id:
            cur.execute("SELECT user_id, user_name, grade, role, pokemon_type FROM accounts WHERE user_id = ? OR user_name = ?", (clean_id, clean_name))
        else:
            cur.execute("SELECT user_id, user_name, grade, role, pokemon_type FROM accounts WHERE user_name = ?", (clean_name,))
        acc = cur.fetchone()
        now = _now_str()

        if not acc:
            effective_uid = clean_id or f"user_{clean_name}_{now[:10].replace('-', '')}"
            cur.execute(
                """
                INSERT INTO accounts (user_id, password, user_name, grade, role, pokemon_type, created_at)
                VALUES (?, '1234', ?, ?, 'student', ?, ?)
                """,
                (effective_uid, clean_name, resolved_grade, ptype, now),
            )
            conn.commit()
            clean_id = effective_uid
        else:
            clean_id = acc["user_id"]
            if grade and 1 <= grade <= 6:
                cur.execute("UPDATE accounts SET grade = ? WHERE user_id = ?", (resolved_grade, clean_id))
                conn.commit()
            if pokemon_type in POKEMON_TYPE_CONFIG:
                cur.execute("UPDATE accounts SET pokemon_type = ? WHERE user_id = ?", (ptype, clean_id))
                conn.commit()
    finally:
        conn.close()

    status = get_user_status(clean_name, resolved_grade, pokemon_type=ptype, user_id=clean_id)
    return {
        "user_name": clean_name,
        "user_id": clean_id,
        "grade": status["grade"],
        "pokemon_type": ptype,
        "subject_score": status["subject_score"],
        "total_score": status["total_score"],
        "level_info": status["level_info"],
    }
