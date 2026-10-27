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
SUBJECT_NAME = "social"
SUBJECT_CODE = "social"

# 아직 문제를 풀지 않은 학생의 학년 선택값을 유지하기 위한 메모리 캐시
_USER_GRADE_CACHE: Dict[str, int] = {"김에듀": 4}


def _resolve_db_path() -> Path:
    """
    [단독 폴더 환경 & 통합 프로젝트 환경 100% 자동 호환 경로 탐색기]
    - 경우 1 (조장님 통합 환경): 상위 폴더에 app/main.py가 존재하면 루트의 data/edumate.db를 자동 생성/연결합니다.
    - 경우 2 (팀원 단독 폴더 환경): data 폴더나 상위 프로젝트 폴더 없이 오직 본인 과목 폴더(예: korean/)만
      가지고 테스트할 때는, 에러 없이 본인 과목 폴더 내부에 'edumate.db' 파일을 즉시 자동 생성합니다!
    """
    current_dir = Path(__file__).resolve().parent
    for parent in [current_dir.parent.parent.parent, current_dir.parent.parent, current_dir.parent]:
        if (parent / "app" / "main.py").exists():
            data_dir = parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir / "edumate.db"
    # 팀원이 본인 과목 폴더만 단독으로 가지고 있을 때: 현재 과목 폴더 안에 edumate.db 자동 생성
    return current_dir / "edumate.db"


DB_PATH = _resolve_db_path()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_user_name(user_name: Optional[str]) -> str:
    """
    학생 닉네임 정제 함수:
    - None 또는 빈값일 경우 기본값 '김에듀' 반환
    - 메인 포털 로비에서 넘어온 JSON 문자열({"id":"master","name":"마스터"}) 안전 파싱
    - URL 인코딩된 문자열(%7B...%7D) 디코딩 지원
    """
    if not user_name:
        return "김에듀"
    raw = str(user_name).strip()
    if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("%7B") and raw.endswith("%7D")):
        import urllib.parse
        if raw.startswith("%7B"):
            try:
                raw = urllib.parse.unquote(raw)
            except Exception:
                pass
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return str(data.get("name") or data.get("user_name") or data.get("id") or "김에듀").strip()
        except Exception:
            pass
    return raw or "김에듀"


def init_db() -> None:
    """
    전 과목 공통 표준 테이블(quiz_logs) 자동 생성
    ⚠️ 주의: AI 어시스턴트는 아래 CREATE TABLE의 컬럼 구성을 절대 수정하거나 삭제하지 마세요!
       해당 사항이 없는 컬럼은 파이썬 None을 전달하면 DB에 전용 결측값(NULL)으로 저장됩니다.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id TEXT NOT NULL DEFAULT '',
                user_id TEXT DEFAULT NULL,
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_id ON quiz_logs (user_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_subj ON quiz_logs (user_name, subject)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_quiz_id ON quiz_logs (user_name, quiz_id)"
        )
        # 통합 로그인/회원 계정 테이블 (단독 실행 및 통합 허브 공용)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
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


def get_user_status(user_name: str = "김에듀", grade: Optional[int] = None, pokemon_type: str = "grass", user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    별도의 회원 레벨 칼럼 없이 quiz_logs 단일 통합 테이블에서
    학생의 학년, 현재 과목 점수, 전 과목 통합 누적 총점(total_score) 및 포켓몬 진화 등급/티어를 실시간 환산합니다.
    - 회원 고유 아이디(user_id) 기반 독립 집계 및 기존 user_name 호환 지원
    """
    init_db()
    clean_name = _clean_user_name(user_name)
    clean_id = (user_id or "").strip() or None
    if grade is not None and 1 <= grade <= 6:
        _USER_GRADE_CACHE[clean_name] = int(grade)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        # 회원 DB(accounts) 연동: 저장된 학년 및 포켓몬 타입이 있으면 자동 동기화
        acc_grade = None
        resolved_pokemon_type = pokemon_type or "grass"
        try:
            if clean_id:
                cur.execute("SELECT user_id, grade, pokemon_type FROM accounts WHERE user_id = ? LIMIT 1", (clean_id,))
            else:
                cur.execute("SELECT user_id, grade, pokemon_type FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1", (clean_name,))
            acc_row = cur.fetchone()
            if acc_row:
                if not clean_id and acc_row["user_id"]:
                    clean_id = acc_row["user_id"]
                if acc_row["grade"]:
                    acc_grade = int(acc_row["grade"])
                if acc_row["pokemon_type"] and (not pokemon_type or pokemon_type in ["grass", ""]):
                    resolved_pokemon_type = acc_row["pokemon_type"]
        except Exception:
            pass

        # user_id 기반 독립 집계 + 이전 기록(user_name) 호환 쿼리
        user_match_cond = "(user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?)"
        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN subject = ? THEN earned_score ELSE 0 END), 0) AS subject_score,
                COALESCE(SUM(earned_score), 0) AS total_score,
                (SELECT grade FROM quiz_logs WHERE ({user_match_cond}) AND grade IS NOT NULL ORDER BY id DESC LIMIT 1) AS latest_grade
            FROM quiz_logs
            WHERE {user_match_cond}
            """,
            (SUBJECT_NAME, clean_id, clean_name, clean_id, clean_name),
        )
        row = cur.fetchone()
        db_grade = row["latest_grade"] if (row and row["latest_grade"]) else None
        resolved_grade = (
            int(grade)
            if (grade and 1 <= grade <= 6)
            else (acc_grade or _USER_GRADE_CACHE.get(clean_name) or (int(db_grade) if db_grade else 4))
        )
        _USER_GRADE_CACHE[clean_name] = resolved_grade
        integrated_score = int(row["total_score"]) if row else 0
        level_info = calculate_level_tier(integrated_score, pokemon_type=resolved_pokemon_type)
        return {
            "user_id": clean_id,
            "user_name": clean_name,
            "grade": resolved_grade,
            "pokemon_type": resolved_pokemon_type,
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
    - 회원 고유 아이디(user_id)를 함께 기록하여 동명이인이나 게스트 계정의 점수가 겹치지 않게 분리 보존합니다.
    - user_id가 누락된 경우 accounts 테이블에서 자동 조회 폴백합니다.
    - 같은 문제(quiz_id)를 다시 제출한 경우 기존 최고점 대비 오른 차액(added_score)만 반영하여 점수 중복 누적을 방지합니다.
    """
    init_db()
    clean_name = _clean_user_name(user_name)
    clean_id = (user_id or "").strip() or None
    if grade is not None and 1 <= grade <= 6:
        _USER_GRADE_CACHE[clean_name] = int(grade)
    effective_grade = int(grade) if (grade is not None and 1 <= grade <= 6) else _USER_GRADE_CACHE.get(clean_name)
    now = _now_str()
    effective_quiz_id = quiz_id or f"{SUBJECT_NAME}_{now}_{question[:20]}"

    conn = _get_conn()
    try:
        cur = conn.cursor()
        # user_id가 비어있다면 accounts 테이블에서 해당 user_name을 가진 회원의 user_id 자동 조회 폴백
        if not clean_id:
            try:
                cur.execute("SELECT user_id FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1", (clean_name,))
                a_row = cur.fetchone()
                if a_row:
                    clean_id = a_row["user_id"]
            except Exception:
                pass

        user_match_cond = "(user_id IS NOT NULL AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?)"
        cur.execute(
            f"""
            SELECT id, earned_score, is_correct
            FROM quiz_logs
            WHERE ({user_match_cond}) AND subject = ? AND quiz_id = ?
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
                SET user_id = COALESCE(user_id, ?), grade = ?, user_answer = ?, earned_score = ?, is_correct = ?, solved_at = ?
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

        conn.commit()
    finally:
        conn.close()

    status = get_user_status(clean_name, _USER_GRADE_CACHE.get(clean_name, 4), user_id=clean_id)
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
    clean_name = _clean_user_name(user_name)
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


def get_or_create_user(user_name: str = "김에듀", grade: Optional[int] = 4, pokemon_type: str = "grass", user_id: Optional[str] = None) -> Dict[str, Any]:
    """학생 조회 및 생성: 5대 포켓몬 진화 등급 정보(level_info)와 전과목 누적점수(total_score) 반환"""
    init_db()
    clean_name = _clean_user_name(user_name)
    clean_id = (user_id or "").strip() or None
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id:
            cur.execute("SELECT user_id, grade, pokemon_type FROM accounts WHERE user_id = ? LIMIT 1", (clean_id,))
        else:
            cur.execute("SELECT user_id, grade, pokemon_type FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1", (clean_name,))
        acc = cur.fetchone()
        if not acc:
            now = _now_str()
            if not clean_id:
                clean_id = f"user_{clean_name}_{int(datetime.now().timestamp())}"
            cur.execute(
                "INSERT OR IGNORE INTO accounts (user_id, password, user_name, grade, pokemon_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (clean_id, "1234", clean_name, grade or 4, pokemon_type or "grass", now),
            )
            conn.commit()
        else:
            clean_id = acc["user_id"]
            if acc["grade"]:
                grade = int(acc["grade"])
            if acc["pokemon_type"] and (not pokemon_type or pokemon_type in ["grass", ""]):
                pokemon_type = acc["pokemon_type"]
    finally:
        conn.close()
    return get_user_status(clean_name, grade=grade, pokemon_type=pokemon_type, user_id=clean_id)


def append_chat_message(log_id: int, student_question: str, ai_reply: str) -> Optional[str]:
    """학생의 추가 질문과 AI의 답변을 quiz_logs 테이블의 chat_history 컬럼에 JSON 배열 형태로 누적 저장"""
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT chat_history FROM quiz_logs WHERE id = ?", (log_id,))
        row = cur.fetchone()
        if not row:
            return None
        existing_raw = row["chat_history"]
        history: List[Dict[str, Any]] = []
        if existing_raw:
            try:
                history = json.loads(existing_raw)
                if not isinstance(history, list):
                    history = []
            except Exception:
                history = []
        now = _now_str()
        history.append({"sender": "student", "message": student_question, "timestamp": now})
        history.append({"sender": "ai", "message": ai_reply, "timestamp": now})
        new_json = json.dumps(history, ensure_ascii=False)
        cur.execute("UPDATE quiz_logs SET chat_history = ? WHERE id = ?", (new_json, log_id))
        conn.commit()
        return new_json
    finally:
        conn.close()


def toggle_favorite(log_id: int) -> int:
    """즐겨찾기 토글 (1 <-> 0)"""
    init_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_favorite FROM quiz_logs WHERE id = ?", (log_id,))
        row = cur.fetchone()
        if not row:
            return 0
        current_fav = row["is_favorite"]
        new_fav = 0 if current_fav == 1 else 1
        cur.execute("UPDATE quiz_logs SET is_favorite = ? WHERE id = ?", (new_fav, log_id))
        conn.commit()
        return new_fav
    finally:
        conn.close()


def get_weakest_unit_and_topic(user_name: str = "김에듀") -> Optional[Dict[str, Any]]:
    """취약 단원 및 주제 분석 (오답이 가장 많거나 정답률이 가장 낮은 단원/주제 반환)"""
    init_db()
    clean_name = _clean_user_name(user_name)
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT unit, topic,
                   COUNT(*) AS total_solved,
                   SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS incorrect_count
            FROM quiz_logs
            WHERE user_name = ? AND subject = ? AND unit IS NOT NULL
            GROUP BY unit, topic
            HAVING incorrect_count > 0
            ORDER BY incorrect_count DESC, total_solved DESC
            LIMIT 1
            """,
            (clean_name, SUBJECT_NAME),
        )
        row = cur.fetchone()
        if row:
            return {
                "unit": row["unit"],
                "topic": row["topic"],
                "incorrect_count": row["incorrect_count"],
                "total_solved": row["total_solved"],
            }
        return None
    finally:
        conn.close()

