"""
================================================================================
[EduMate AI 공통 플랫폼 관제탑 DB 관리자 - app/database/quiz_manager.py]
================================================================================
- 가이드라인 표준 디렉터리 아키텍처에 따른 중앙 플랫폼 전용 관제탑 모듈입니다.
- 개별 과목(math, korean, english 등)에 종속되지 않는 플랫폼 공통 기능을 전담합니다:
  1) 마스터 관리자(admin) 및 학생 계정(accounts) CRUD 및 비밀번호 '0000' 초기화
  2) 로비 포탈 실시간 전과목 랭킹 (1~10위) 집계
  3) 과목별 누적점수 필터링 및 통합 학생 리포트
  4) 전 과목 통합 SQLite DB(data/edumate.db) 표준 초기화
================================================================================
"""

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
INTEGRATED_DB_PATH = DATA_DIR / "edumate.db"

# ---------------------------------------------------------------------------
# 포켓몬 5대 속성 진화 체계 (9단계 × 각 5티어)
# ---------------------------------------------------------------------------
POKEMON_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "grass": {
        "type_no": 1,
        "type_kr": "풀",
        "color_name": "초록색",
        "color_hex": "#22c55e",
        "stages": ["알", "이상해씨", "이상해풀", "이상해꽃", "메가이상해꽃", "비리디온", "세레비", "레쿠쟈", "메가레쿠쟈"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
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
        "stages": ["알", "캐이시", "윤겔라", "후딘", "메가후딘", "크레세리아", "뮤", "뮤츠", "메가뮤츠Y"],
        "display_stages": ["알", "캐이시", "윤겔라", "후딘", "메가후딘", "크레세리아", "뮤", "뮤츠", "메가뮤츠Y"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
    "dragon": {
        "type_no": 6,
        "type_kr": "드래곤",
        "color_name": "보라색",
        "color_hex": "#8b5cf6",
        "stages": ["알", "미뇽", "신뇽", "망나뇽", "메가망나뇽", "메가한카리아스Z", "디아루가", "흑쿠쟈", "메가흑쿠쟈"],
        "display_stages": ["알", "미뇽", "신뇽", "망나뇽", "메가망나뇽", "메가한카리아스Z", "디아루가", "레쿠쟈", "메가레쿠쟈"],
        "emojis": ["", "", "", "", "", "", "", "", ""],
    },
}

STAGE_TIER_EXP_TABLE: List[List[int]] = [
    [10, 10, 10, 10, 10],         # 1등급 (알)
    [15, 15, 15, 15, 15],         # 2등급
    [25, 25, 25, 25, 25],         # 3등급
    [40, 40, 40, 40, 40],         # 4등급
    [60, 60, 60, 60, 180],        # 5등급 (1티어 180 EXP 대폭 상승)
    [250, 250, 250, 250, 250],    # 6등급
    [350, 350, 350, 350, 350],    # 7등급
    [500, 500, 500, 500, 500],    # 8등급
    [800, 800, 800, 800, 800],    # 9등급
]

SUBJECT_FILTER_ALIASES = {
    "korean": ("korean", "kor", "국어", "초등국어"),
    "math": ("math", "수학", "초등수학"),
    "english": ("english", "eng", "영어", "초등영어"),
    "social": ("social", "soc", "society", "사회", "초등사회"),
    "science": ("science", "sci", "과학", "초등과학"),
    "hanja": ("hanja", "한자", "초등한자", "한문", "초등한문"),
}

SUBJECT_CODE_TO_LABEL: Dict[str, str] = {
    "korean": "국어",
    "math": "수학",
    "english": "영어",
    "social": "사회",
    "science": "과학",
    "hanja": "한자",
}
SUBJECT_LABEL_TO_CODE: Dict[str, str] = {v: k for k, v in SUBJECT_CODE_TO_LABEL.items()}
ALL_SUBJECT_CODES: List[str] = ["korean", "math", "english", "social", "science", "hanja"]


def normalize_subject_code(raw: str) -> Optional[str]:
    """과목 코드 또는 한글 과목명을 표준 영문 코드(korean/math/english/social/science/hanja)로 정규화"""
    val = (raw or "").strip().lower()
    if val in SUBJECT_CODE_TO_LABEL:
        return val
    for code, aliases in SUBJECT_FILTER_ALIASES.items():
        if val in [a.lower() for a in aliases]:
            return code
    return None


def parse_managed_subjects(raw_val: Optional[str], role: str = "student") -> List[str]:
    """DB의 managed_subjects 문자열을 표준 순서(국,수,영,사,과,한자)의 과목 코드 리스트로 반환"""
    if role == "admin":
        return list(ALL_SUBJECT_CODES)
    if not raw_val:
        return []
    text = str(raw_val).strip()
    if not text:
        return []
    items: List[str] = []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                items = [str(x) for x in parsed]
        except Exception:
            items = [x.strip() for x in text.split(",")]
    else:
        items = [x.strip() for x in text.split(",")]

    normalized_set = set()
    for it in items:
        code = normalize_subject_code(it)
        if code:
            normalized_set.add(code)
    return [c for c in ALL_SUBJECT_CODES if c in normalized_set]


def format_role_display(role: Any, managed_subjects: List[str], grade: Optional[int] = None) -> str:
    """권한 및 담당 과목에 따른 표준 표시명 반환 ('총 관리자', '부관리자(수학, 과학)', '초등 4학년', '비회원 체험')"""
    if role == "admin" or role == 1:
        return "총 관리자"
    if managed_subjects:
        kr_labels = [SUBJECT_CODE_TO_LABEL[c] for c in ALL_SUBJECT_CODES if c in managed_subjects]
        if kr_labels:
            return f"부관리자({', '.join(kr_labels)})"
    if role == "sub_admin":
        return "부관리자"
    if role == "guest":
        return "비회원 체험"
    if grade:
        return f"초등 {grade}학년"
    return "학생"



_USER_POKEMON_TYPE_CACHE: Dict[str, str] = {"김에듀": "grass"}
_USER_POKEMON_TYPE_EXPLICIT: Dict[str, bool] = {}
_USER_GRADE_CACHE: Dict[str, int] = {"김에듀": 4, "마스터": 6}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(INTEGRATED_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_name(name: str) -> str:
    """JSON 문자열 파편 방어 및 순수 학생 이름 정제"""
    clean = (name or "김에듀").strip() or "김에듀"
    if clean.startswith("{") and clean.endswith("}"):
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return str(parsed.get("name") or parsed.get("user_name") or "김에듀").strip()
        except Exception:
            pass
    return clean


def init_control_db() -> None:
    """전 과목 통합 표준 테이블(quiz_logs) 및 계정 테이블(accounts) 초기화"""
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
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_subj ON quiz_logs (user_name, subject)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_quiz_logs_quiz_id ON quiz_logs (user_name, quiz_id)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                user_name TEXT NOT NULL,
                grade INTEGER NOT NULL DEFAULT 4,
                role TEXT NOT NULL DEFAULT 'student',
                pokemon_type TEXT NOT NULL DEFAULT 'grass',
                custom_skin_stage INTEGER NOT NULL DEFAULT 0,
                managed_subjects TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        try:
            cur.execute("ALTER TABLE accounts ADD COLUMN pokemon_type TEXT DEFAULT 'grass'")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE accounts ADD COLUMN custom_skin_stage INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE accounts ADD COLUMN managed_subjects TEXT DEFAULT ''")
        except Exception:
            pass

        now = _now_str()
        cur.execute("UPDATE accounts SET user_id = 'master' WHERE user_id = '1234'")
        cur.execute(
            """
            INSERT INTO accounts (user_id, password, user_name, grade, role, created_at)
            VALUES ('master', '1111', '마스터', 6, 'admin', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                role = 'admin',
                user_name = COALESCE(NULLIF(accounts.user_name, ''), excluded.user_name),
                password = COALESCE(NULLIF(accounts.password, ''), excluded.password)
            """,
            (now,),
        )
        cur.execute("UPDATE accounts SET password = '1111' WHERE (user_id = 'master' OR role = 'admin') AND (password IS NULL OR password = '')")

        # [요청사항 반영] 불필요 테스트 계정 'user_테스트_1792138264' 영구 삭제
        cur.execute("DELETE FROM accounts WHERE user_id = 'user_테스트_1792138264' OR user_name = 'user_테스트_1792138264'")
        cur.execute("DELETE FROM quiz_logs WHERE user_id = 'user_테스트_1792138264' OR user_name = 'user_테스트_1792138264'")

        # [데이터 무결성 자동 복구] JSON 파편이 들어간 비정상 계정 정리 및 quiz_logs 학생명 복구
        cur.execute("UPDATE quiz_logs SET user_name = '오준교' WHERE user_name LIKE '%오준교%' AND user_name != '오준교'")
        cur.execute("UPDATE quiz_logs SET user_name = '이승한' WHERE user_name LIKE '%이승한%' AND user_name != '이승한'")
        cur.execute("DELETE FROM accounts WHERE user_id LIKE '{%' OR user_id LIKE 'user_{%' OR user_name LIKE '{%'")
        cur.execute("DELETE FROM quiz_logs WHERE user_name LIKE '{%' OR user_name LIKE 'user_{%'")
        # [회원별 고유 속성 보존] 이승한 회원의 전기(라이츄) 속성 복구
        cur.execute("UPDATE accounts SET pokemon_type = 'electric' WHERE (user_name = '이승한' OR user_id = '이승한')")
        cur.execute("UPDATE accounts SET pokemon_type = 'dragon' WHERE (user_name = '마스터' OR user_id = 'master') AND (pokemon_type = 'grass' OR pokemon_type IS NULL)")
        # [관리자 계정 단일화] 한글 '마스터' 아이디 등 중복 관리자 계정 삭제 (관리자는 오직 아이디 'master' 하나만 유지)
        cur.execute("DELETE FROM accounts WHERE user_id = '마스터' OR (user_name = '마스터' AND user_id != 'master')")

        # [동명이인 및 게스트 계정 분리 패치] quiz_logs 테이블에 user_id 컬럼 추가 및 인덱싱
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_quiz_logs_user_id ON quiz_logs (user_id)")

        # 기존 게스트 테스트 기록 중 user_id가 비어있는 항목을 guest00으로 귀속하여 guest02, guest03과 분리
        cur.execute("UPDATE quiz_logs SET user_id = 'guest00' WHERE (user_id IS NULL OR user_id = '') AND user_name = '게스트'")
        # 마스터 계정 로그도 user_id = 'master'로 동기화
        cur.execute("UPDATE quiz_logs SET user_id = 'master' WHERE (user_id IS NULL OR user_id = '') AND user_name = '마스터'")

        conn.commit()
    finally:
        conn.close()


def calculate_level_tier(
    total_score: int,
    pokemon_type: str = "grass",
    custom_skin_stage: int = 0,
) -> Dict[str, Any]:
    """전 과목 통합 누적 점수 기반 레벨 및 포켓몬 진화 등급 자동 산출 (외형 스킨 변환 지원)"""
    ptype = pokemon_type if pokemon_type in POKEMON_TYPE_CONFIG else "grass"
    tcfg = POKEMON_TYPE_CONFIG[ptype]
    stages = tcfg["stages"]
    display_stages = tcfg.get("display_stages", stages)
    emojis = tcfg.get("emojis", [""] * 9)

    score = max(0, int(total_score or 0))
    remaining = score
    level_num = 1
    res: Optional[Dict[str, Any]] = None

    for s_idx, tier_exps in enumerate(STAGE_TIER_EXP_TABLE):
        poke_name = stages[s_idx]
        display_name = display_stages[s_idx]
        poke_emoji = emojis[s_idx] if s_idx < len(emojis) else ""
        is_egg_stage = (s_idx == 0)
        effective_color_hex = "#64748b" if is_egg_stage else tcfg["color_hex"]
        effective_color_name = "짙은 회색" if is_egg_stage else tcfg["color_name"]

        for t_idx, cap in enumerate(tier_exps):
            tier_num = 5 - t_idx
            is_max_tier = (s_idx == len(STAGE_TIER_EXP_TABLE) - 1 and tier_num == 1)
            if remaining < cap or is_max_tier:
                current_exp = min(remaining, cap) if is_max_tier else remaining
                progress_pct = 100 if (is_max_tier and remaining >= cap) else min(100, int(round((current_exp / cap) * 100)))
                next_remain = 0 if (is_max_tier and remaining >= cap) else max(0, cap - remaining)
                full_title = f"{display_name} {tier_num}티어"

                res = {
                    "pokemon_type": ptype,
                    "type_kr": "알" if is_egg_stage else tcfg["type_kr"],
                    "color_name": effective_color_name,
                    "color_hex": effective_color_hex,
                    "can_select_type": not is_egg_stage,
                    "stage_num": s_idx + 1,
                    "level_num": level_num,
                    "level": level_num,
                    "pokemon_name": poke_name,
                    "display_pokemon_name": display_name,
                    "pokemon_emoji": poke_emoji,
                    "tier": tier_num,
                    "full_title": full_title,
                    "badge_text": full_title,
                    "current_exp": current_exp,
                    "tier_exp_max": cap,
                    "progress_pct": progress_pct,
                    "next_tier_remain": next_remain,
                    "next_tier_label": "최고 등급 달성 (MAX)" if is_max_tier else (f"{display_name} {tier_num - 1}티어" if tier_num > 1 else f"{display_stages[s_idx + 1]} 5티어"),
                    "evo_line_text": " ➔ ".join(display_stages),
                }
                break
            remaining -= cap
            level_num += 1
        if res is not None:
            break

    if res is None:
        last_poke = stages[-1]
        last_display = display_stages[-1]
        res = {
            "pokemon_type": ptype,
            "type_kr": tcfg["type_kr"],
            "color_name": tcfg["color_name"],
            "color_hex": tcfg["color_hex"],
            "can_select_type": True,
            "stage_num": 9,
            "level_num": 45,
            "level": 45,
            "pokemon_name": last_poke,
            "display_pokemon_name": last_display,
            "pokemon_emoji": emojis[-1] if emojis else "",
            "tier": 1,
            "full_title": f"{last_display} 1티어",
            "badge_text": f"{last_display} 1티어",
            "current_exp": 800,
            "tier_exp_max": 800,
            "progress_pct": 100,
            "next_tier_remain": 0,
            "next_tier_label": "최고 등급 달성 (MAX)",
            "evo_line_text": " ➔ ".join(display_stages),
        }

    # 커스텀 외형 스킨(이전 달성 단계 외형 변환) 반영
    try:
        s_stage = int(custom_skin_stage or 0)
    except Exception:
        s_stage = 0

    if 1 <= s_stage <= res["stage_num"]:
        skin_poke = stages[s_stage - 1]
        skin_disp = display_stages[s_stage - 1]
        skin_emoji = emojis[s_stage - 1] if (s_stage - 1 < len(emojis)) else ""
        res["pokemon_name"] = skin_poke
        res["display_pokemon_name"] = skin_disp
        res["pokemon_emoji"] = skin_emoji
        res["badge_text"] = skin_disp
        res["full_title"] = f"{skin_disp} (Lv.{res['level_num']})"
        res["custom_skin_stage"] = s_stage
        res["color_hex"] = "#64748b" if s_stage == 1 else tcfg["color_hex"]
    else:
        res["custom_skin_stage"] = 0

    return res


def list_all_accounts() -> List[Dict[str, Any]]:
    """전체 학생 계정 목록 조회 (보안 원칙: 비밀번호 마스킹, 부관리자 위임 과목 및 개별 포켓몬 속성 반영)"""
    init_control_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                a.user_id,
                a.password,
                a.user_name,
                a.grade,
                a.role,
                COALESCE(a.pokemon_type, 'grass') AS pokemon_type,
                COALESCE(a.custom_skin_stage, 0) AS custom_skin_stage,
                COALESCE(a.managed_subjects, '') AS managed_subjects,
                a.created_at,
                COALESCE((
                    SELECT SUM(earned_score)
                    FROM quiz_logs q
                    WHERE (q.user_id IS NOT NULL AND q.user_id != '' AND q.user_id = a.user_id)
                       OR ((q.user_id IS NULL OR q.user_id = '') AND q.user_name = a.user_name)
                ), 0) AS total_score,
                COALESCE((
                    SELECT COUNT(*)
                    FROM quiz_logs q
                    WHERE (q.user_id IS NOT NULL AND q.user_id != '' AND q.user_id = a.user_id)
                       OR ((q.user_id IS NULL OR q.user_id = '') AND q.user_name = a.user_name)
                ), 0) AS solved_count
            FROM accounts a
            WHERE a.user_id != '마스터' AND (a.user_name != '마스터' OR a.user_id = 'master') AND a.user_id NOT IN ('guest', '게스트') AND a.role != 'guest'
            ORDER BY CASE WHEN a.role = 'admin' THEN 0 WHEN a.role = 'sub_admin' THEN 1 ELSE 2 END, a.created_at DESC
            """
        )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["password"] = "••••••••"
            tot = int(d["total_score"] or 0)
            ptype = d.get("pokemon_type") or _USER_POKEMON_TYPE_CACHE.get(d["user_name"], "grass")
            skin_st = int(d.get("custom_skin_stage") or 0)
            role_str = d.get("role") or "student"
            m_subjs = parse_managed_subjects(d.get("managed_subjects"), role=role_str)
            if role_str != "admin" and m_subjs:
                role_str = "sub_admin"
            d["role"] = role_str
            d["managed_subjects"] = m_subjs
            d["managed_subjects_kr"] = [SUBJECT_CODE_TO_LABEL[c] for c in m_subjs if c in SUBJECT_CODE_TO_LABEL]
            d["role_display"] = format_role_display(role_str, m_subjs)
            d["pokemon_type"] = ptype
            d["custom_skin_stage"] = skin_st
            d["level_info"] = calculate_level_tier(tot, pokemon_type=ptype, custom_skin_stage=skin_st)
            results.append(d)
        return results
    finally:
        conn.close()


def delegate_sub_admin(user_id: str, subjects: List[str]) -> Dict[str, Any]:
    """[총 관리자 전용] 특정 회원에게 부관리자 과목 권한(국,수,영,사,과,한자 중복 선택 가능) 위임 또는 해제"""
    init_control_db()
    clean_id = (user_id or "").strip()
    if not clean_id or clean_id in ("master", "1234", "마스터"):
        raise ValueError("총 관리자(master) 계정의 권한은 변경할 수 없습니다.")

    normalized_set = set()
    for s in (subjects or []):
        code = normalize_subject_code(str(s))
        if code:
            normalized_set.add(code)
    ordered_codes = [c for c in ALL_SUBJECT_CODES if c in normalized_set]
    new_role = "sub_admin" if ordered_codes else "student"
    raw_managed = ",".join(ordered_codes)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, user_name, grade FROM accounts WHERE user_id = ?", (clean_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"대상 계정('{clean_id}')을 찾을 수 없습니다.")

        cur.execute(
            "UPDATE accounts SET role = ?, managed_subjects = ? WHERE user_id = ?",
            (new_role, raw_managed, clean_id),
        )
        conn.commit()
        return {
            "user_id": clean_id,
            "user_name": row["user_name"],
            "grade": row["grade"],
            "role": new_role,
            "managed_subjects": ordered_codes,
            "managed_subjects_kr": [SUBJECT_CODE_TO_LABEL[c] for c in ordered_codes],
            "role_display": format_role_display(new_role, ordered_codes),
        }
    finally:
        conn.close()


def check_subject_permission(user_id: Optional[str], subject: str) -> bool:
    """해당 회원(user_id)이 특정 과목(subject)의 문제은행 저장/삭제 권한을 보유하고 있는지 확인"""
    init_control_db()
    clean_id = (user_id or "").strip()
    if not clean_id or clean_id.lower() in ("guest", "게스트"):
        return False
    if clean_id == "master":
        return True
    target_code = normalize_subject_code(subject)
    if not target_code:
        return False

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role, COALESCE(managed_subjects, '') AS managed_subjects FROM accounts WHERE user_id = ? LIMIT 1", (clean_id,))
        row = cur.fetchone()
        if not row:
            return False
        if row["role"] == "admin":
            return True
        m_subjs = parse_managed_subjects(row["managed_subjects"], role=row["role"])
        return target_code in m_subjs
    finally:
        conn.close()


def reset_account_password(user_id: str, new_password: str = "0000") -> bool:
    """[마스터 관리자 전용] 특정 학생 계정 비밀번호 '0000' 초기화"""
    init_control_db()
    clean_id = (user_id or "").strip()
    clean_pw = (new_password or "0000").strip()
    if not clean_id or clean_id in ("master", "1234"):
        return False
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET password = ? WHERE user_id = ?", (clean_pw, clean_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def create_temp_account(new_user_id: str, new_password: str, user_name: str, grade: int = 4) -> Dict[str, Any]:
    """[마스터 관리자 전용] 학생 임시 계정 발급"""
    init_control_db()
    clean_id = _sanitize_name(new_user_id or "").strip()
    clean_pw = (new_password or "").strip()
    clean_name = _sanitize_name(user_name or "").strip()
    valid_grade = int(grade) if (grade and 1 <= int(grade) <= 6) else 4

    if not clean_id or not clean_pw or not clean_name:
        raise ValueError("아이디, 비밀번호, 이름을 모두 입력해 주세요.")
    if clean_id in ("master", "1234"):
        raise ValueError("'master'는 마스터 관리자 전용 아이디입니다.")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM accounts WHERE user_id = ?", (clean_id,))
        if cur.fetchone():
            raise ValueError(f"이미 존재하는 아이디('{clean_id}')입니다.")

        now = _now_str()
        cur.execute(
            """
            INSERT INTO accounts (user_id, password, user_name, grade, role, created_at)
            VALUES (?, ?, ?, ?, 'student', ?)
            """,
            (clean_id, clean_pw, clean_name, valid_grade, now),
        )
        conn.commit()
        return {
            "user_id": clean_id,
            "password": clean_pw,
            "user_name": clean_name,
            "grade": valid_grade,
            "role": "student",
            "managed_subjects": [],
            "managed_subjects_kr": [],
            "role_display": "학생 계정",
            "created_at": now,
        }
    finally:
        conn.close()


def register_account(
    user_id: str,
    password: str,
    password_confirm: str,
    user_name: str,
    grade: int = 4,
    guest_id: Optional[str] = None,
) -> Dict[str, Any]:
    """[일반 학생] 신규 계정 회원가입 (비회원 체험 기록 안전 이관 지원)"""
    init_control_db()
    clean_id = (user_id or "").strip()
    clean_pw = (password or "").strip()
    clean_pw_conf = (password_confirm or "").strip()
    clean_name = _sanitize_name(user_name or "").strip()
    valid_grade = int(grade) if (grade and 1 <= int(grade) <= 6) else 4

    if not clean_id or not clean_pw or not clean_name:
        raise ValueError("아이디, 비밀번호, 이름을 모두 입력해 주세요.")
    if len(clean_id) < 2:
        raise ValueError("아이디는 2자 이상이어야 합니다.")
    if clean_id.lower() in ("master", "admin", "guest", "게스트", "1234"):
        raise ValueError(f"'{clean_id}'는 시스템 예약 아이디이므로 사용할 수 없습니다.")
    if len(clean_pw) < 4:
        raise ValueError("비밀번호는 최소 4자 이상이어야 합니다.")
    if clean_pw != clean_pw_conf:
        raise ValueError("비밀번호와 비밀번호 확인이 일치하지 않습니다.")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM accounts WHERE user_id = ?", (clean_id,))
        if cur.fetchone():
            raise ValueError(f"이미 존재하는 아이디('{clean_id}')입니다.")

        now = _now_str()
        cur.execute(
            """
            INSERT INTO accounts (user_id, password, user_name, grade, role, pokemon_type, custom_skin_stage, created_at)
            VALUES (?, ?, ?, ?, 'student', 'grass', 0, ?)
            """,
            (clean_id, clean_pw, clean_name, valid_grade, now),
        )
        conn.commit()

        # 비회원 체험 중 푼 문제 기록이 있는 경우 신규 회원 계정으로 안전 이관
        migrated_score = 0
        clean_guest_id = (guest_id or "").strip()
        if clean_guest_id and clean_guest_id != clean_id:
            try:
                cur.execute(
                    "UPDATE quiz_logs SET user_id = ?, user_name = ? WHERE user_id = ?",
                    (clean_id, clean_name, clean_guest_id),
                )
                conn.commit()
                cur.execute("SELECT COALESCE(SUM(earned_score), 0) FROM quiz_logs WHERE user_id = ?", (clean_id,))
                migrated_score = int(cur.fetchone()[0] or 0)
            except Exception:
                pass

        return {
            "user_id": clean_id,
            "user_name": clean_name,
            "grade": valid_grade,
            "role": "student",
            "managed_subjects": [],
            "managed_subjects_kr": [],
            "role_display": "학생 계정",
            "total_score": migrated_score,
            "pokemon_type": "grass",
            "created_at": now,
        }
    finally:
        conn.close()


def clear_guest_logs(guest_id: str) -> int:
    """비회원 체험 로그아웃 시 해당 게스트의 임시 문제풀이 기록 증발(삭제)"""
    init_control_db()
    clean_id = (guest_id or "").strip()
    if not clean_id or clean_id in ("master", "admin"):
        return 0
    if not (clean_id == "guest" or clean_id.startswith("guest")):
        return 0
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM quiz_logs WHERE user_id = ?", (clean_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def login_account(user_id: str, password: str) -> Dict[str, Any]:
    """아이디 및 비밀번호 검증 로그인"""
    init_control_db()
    clean_id = (user_id or "").strip()
    clean_pw = (password or "").strip()
    if not clean_id or not clean_pw:
        raise ValueError("아이디와 비밀번호를 모두 입력해 주세요.")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id == "master":
            cur.execute(
                "SELECT user_id, user_name, grade, role, COALESCE(pokemon_type, 'grass') AS pokemon_type, COALESCE(custom_skin_stage, 0) AS custom_skin_stage, COALESCE(managed_subjects, '') AS managed_subjects FROM accounts WHERE user_id = 'master' AND password = ?",
                (clean_pw,),
            )
        else:
            cur.execute(
                "SELECT user_id, user_name, grade, role, COALESCE(pokemon_type, 'grass') AS pokemon_type, COALESCE(custom_skin_stage, 0) AS custom_skin_stage, COALESCE(managed_subjects, '') AS managed_subjects FROM accounts WHERE user_id = ? AND password = ?",
                (clean_id, clean_pw),
            )
        acc = cur.fetchone()
        if not acc:
            raise ValueError("아이디 또는 비밀번호가 일치하지 않습니다.")

        clean_name = _sanitize_name(acc["user_name"])
        cur.execute(
            """
            SELECT
                COALESCE(SUM(earned_score), 0) AS total_score,
                COUNT(*) AS solved_count,
                COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS correct_count
            FROM quiz_logs
            WHERE (user_id IS NOT NULL AND user_id != '' AND user_id = ?)
               OR ((user_id IS NULL OR user_id = '') AND user_name = ?)
            """,
            (acc["user_id"], clean_name),
        )
        stat = cur.fetchone()
        tot = int(stat["total_score"] or 0) if stat else 0
        ptype = acc["pokemon_type"] or _USER_POKEMON_TYPE_CACHE.get(clean_name, "grass")
        skin_st = int(acc["custom_skin_stage"] or 0)
        _USER_POKEMON_TYPE_CACHE[clean_name] = ptype
        _USER_POKEMON_TYPE_EXPLICIT[clean_name] = True

        role_str = acc["role"] or "student"
        m_subjs = parse_managed_subjects(acc["managed_subjects"], role=role_str)
        if role_str != "admin" and m_subjs:
            role_str = "sub_admin"

        return {
            "user_id": acc["user_id"],
            "user_name": clean_name,
            "grade": acc["grade"],
            "role": role_str,
            "managed_subjects": m_subjs,
            "managed_subjects_kr": [SUBJECT_CODE_TO_LABEL[c] for c in m_subjs if c in SUBJECT_CODE_TO_LABEL],
            "role_display": format_role_display(role_str, m_subjs),
            "total_score": tot,
            "solved_count": int(stat["solved_count"] or 0) if stat else 0,
            "correct_count": int(stat["correct_count"] or 0) if stat else 0,
            "level_info": calculate_level_tier(tot, pokemon_type=ptype, custom_skin_stage=skin_st),
            "pokemon_type": ptype,
            "custom_skin_stage": skin_st,
        }
    finally:
        conn.close()


def update_account_profile(
    current_user_id: str,
    current_user_name: str,
    new_user_id: Optional[str] = None,
    new_password: Optional[str] = None,
    new_user_name: Optional[str] = None,
    new_grade: Optional[int] = None,
    current_password: Optional[str] = None,
) -> Dict[str, Any]:
    """일반 회원 및 마스터 관리자의 학생 이름, 비밀번호, 학년 변경 및 quiz_logs 동기화"""
    init_control_db()
    cur_id = (current_user_id or "guest").strip()
    cur_name = _sanitize_name(current_user_name or "김에듀").strip()
    clean_new_name = _sanitize_name(new_user_name or "").strip()
    if not clean_new_name:
        raise ValueError("변경할 학생 이름을 입력해 주세요.")

    is_master_account = (cur_id in ("master", "1234") or cur_name == "마스터")

    if is_master_account:
        clean_new_id = "master"
    else:
        clean_new_id = (new_user_id or cur_id or "").strip()
        if clean_new_id in ("master", "1234"):
            raise ValueError("'master'는 관리자 전용 아이디이므로 사용할 수 없습니다.")
        if clean_new_name == "마스터":
            raise ValueError("'마스터'는 관리자 전용 이름이므로 사용할 수 없습니다.")

    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_name, password, grade, role, COALESCE(managed_subjects, '') AS managed_subjects, COALESCE(pokemon_type, 'grass') AS pokemon_type FROM accounts WHERE user_id = ? OR user_name = ? LIMIT 1",
            (cur_id, cur_name),
        )
        existing = cur.fetchone()
        if not existing:
            raise ValueError(f"계정 정보를 찾을 수 없습니다. (ID: {cur_id})")

        # 현재 비밀번호 입력 시 검증
        clean_cur_pw = (current_password or "").strip()
        if clean_cur_pw and clean_cur_pw != str(existing["password"]).strip():
            raise ValueError("현재 비밀번호가 일치하지 않습니다.")

        # 타 회원과의 학생 이름 중복 검사
        if clean_new_name != existing["user_name"]:
            cur.execute(
                "SELECT user_id FROM accounts WHERE user_name = ? AND user_id != ?",
                (clean_new_name, existing["user_id"]),
            )
            dup_name = cur.fetchone()
            if dup_name:
                raise ValueError(f"'{clean_new_name}' 이름은 이미 다른 회원이 사용 중입니다.")

        # 타 회원과의 아이디 중복 검사 (아이디 변경 시)
        if clean_new_id != existing["user_id"]:
            cur.execute("SELECT user_id FROM accounts WHERE user_id = ?", (clean_new_id,))
            dup_id = cur.fetchone()
            if dup_id:
                raise ValueError(f"이미 사용 중인 아이디('{clean_new_id}')입니다.")

        valid_grade = int(new_grade) if (new_grade and 1 <= int(new_grade) <= 6) else (int(existing["grade"] or (6 if is_master_account else 4)))
        clean_new_pw = (new_password or "").strip()
        final_pw = clean_new_pw if clean_new_pw else existing["password"]
        target_role = existing["role"] or ("admin" if is_master_account else "student")

        cur.execute(
            """
            UPDATE accounts
            SET user_id = ?, password = ?, user_name = ?, grade = ?
            WHERE user_id = ?
            """,
            (clean_new_id, final_pw, clean_new_name, valid_grade, existing["user_id"]),
        )

        old_name = existing["user_name"]
        if old_name != clean_new_name:
            cur.execute(
                "UPDATE quiz_logs SET user_name = ?, user_id = ?, grade = ? WHERE user_id = ? OR ((user_id IS NULL OR user_id = '') AND user_name = ?)",
                (clean_new_name, clean_new_id, valid_grade, existing["user_id"], old_name),
            )
        else:
            cur.execute(
                "UPDATE quiz_logs SET user_id = ?, grade = ? WHERE user_id = ? OR ((user_id IS NULL OR user_id = '') AND user_name = ?)",
                (clean_new_id, valid_grade, existing["user_id"], clean_new_name),
            )

        if old_name in _USER_POKEMON_TYPE_CACHE:
            _USER_POKEMON_TYPE_CACHE[clean_new_name] = _USER_POKEMON_TYPE_CACHE.pop(old_name)
        elif existing["pokemon_type"]:
            _USER_POKEMON_TYPE_CACHE[clean_new_name] = existing["pokemon_type"]
        _USER_POKEMON_TYPE_EXPLICIT[clean_new_name] = True
        _USER_GRADE_CACHE[clean_new_name] = valid_grade

        conn.commit()

        m_subjs = parse_managed_subjects(existing["managed_subjects"], role=target_role)
        return {
            "user_id": clean_new_id,
            "user_name": clean_new_name,
            "grade": valid_grade,
            "role": target_role,
            "managed_subjects": m_subjs,
            "managed_subjects_kr": [SUBJECT_CODE_TO_LABEL[c] for c in m_subjs if c in SUBJECT_CODE_TO_LABEL],
            "role_display": format_role_display(target_role, m_subjs, valid_grade),
        }
    finally:
        conn.close()


def get_ranking_list(limit: int = 10) -> List[Dict[str, Any]]:
    """로비 포탈 실시간 랭킹 (1~10위, 선택된 포켓몬 외형 스킨 반영)"""
    init_control_db()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                a.user_id,
                a.user_name,
                a.grade,
                a.role,
                COALESCE(a.pokemon_type, 'grass') AS pokemon_type,
                COALESCE(a.custom_skin_stage, 0) AS custom_skin_stage,
                COALESCE((
                    SELECT SUM(earned_score)
                    FROM quiz_logs q
                    WHERE (q.user_id IS NOT NULL AND q.user_id != '' AND q.user_id = a.user_id)
                       OR ((q.user_id IS NULL OR q.user_id = '') AND q.user_name = a.user_name)
                ), 0) AS total_score
            FROM accounts a
            WHERE a.user_id != '마스터' AND (a.user_name != '마스터' OR a.user_id = 'master') AND a.user_id NOT IN ('guest', '게스트') AND a.role != 'guest'
            ORDER BY total_score DESC, a.created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        ranking = []
        for rank_idx, r in enumerate(rows, start=1):
            tot = int(r["total_score"] or 0)
            ptype = r["pokemon_type"] or _USER_POKEMON_TYPE_CACHE.get(r["user_name"], "grass")
            skin_st = int(r["custom_skin_stage"] or 0)
            lv_info = calculate_level_tier(tot, pokemon_type=ptype, custom_skin_stage=skin_st)
            ranking.append({
                "rank": rank_idx,
                "user_id": r["user_id"],
                "user_name": r["user_name"],
                "grade": r["grade"],
                "total_score": tot,
                "level_num": lv_info["level_num"],
                "pokemon_name": lv_info["pokemon_name"],
                "display_pokemon_name": lv_info.get("display_pokemon_name", lv_info["pokemon_name"]),
                "tier": lv_info["tier"],
                "badge_text": lv_info["badge_text"],
                "color_hex": lv_info["color_hex"],
                "pokemon_type": lv_info["pokemon_type"],
                "custom_skin_stage": lv_info.get("custom_skin_stage", 0),
                "image_filename": f"{lv_info['pokemon_name']}.webp",
            })
        return ranking
    finally:
        conn.close()


def get_user_subject_score(user_name: str, subject: str = "all", user_id: Optional[str] = None) -> int:
    """특정 과목 또는 전과목 누적 점수 집계 (아이디 기준 우선 매칭)"""
    init_control_db()
    clean_name = _sanitize_name(user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()
    subj_key = (subject or "all").strip().lower()
    conn = _get_conn()
    try:
        cur = conn.cursor()
        if clean_id:
            user_cond = "((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))"
            user_params = [clean_id, clean_name]
        else:
            user_cond = "(user_name = ?)"
            user_params = [clean_name]

        if subj_key in ("all", "", "전과목"):
            cur.execute(f"SELECT COALESCE(SUM(earned_score), 0) FROM quiz_logs WHERE {user_cond}", tuple(user_params))
        else:
            aliases = SUBJECT_FILTER_ALIASES.get(subj_key, (subj_key,))
            placeholders = ", ".join(["?"] * len(aliases))
            params = user_params + [a.lower() for a in aliases]
            cur.execute(
                f"SELECT COALESCE(SUM(earned_score), 0) FROM quiz_logs WHERE {user_cond} AND LOWER(subject) IN ({placeholders})",
                tuple(params),
            )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0
    finally:
        conn.close()


def get_or_create_user(
    user_name: str = "김에듀",
    grade: Optional[int] = None,
    pokemon_type: Optional[str] = None,
    custom_skin_stage: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    accounts 테이블과 quiz_logs 테이블을 연동하여
    학생의 학년, 권한(role), 전 과목 통합 누적 총점(SUM(earned_score)) 및 포켓몬 진화 등급/티어를 실시간 조회합니다.
    (아이디 user_id 우선 식별을 통해 동명이인 완전 분리 지원, 게스트는 DB 접근 없이 0점 가상 프로필 반환)
    """
    init_control_db()
    clean_name = _sanitize_name(user_name or "김에듀").strip() or "김에듀"
    clean_id = (user_id or "").strip()

    # 비회원 체험(게스트): 아이디가 명시적으로 'guest'이거나, 게스트 세션이거나, 아이디 없이 이름만 '게스트'/'guest'인 경우
    if clean_id.lower() == "guest" or clean_id.lower().startswith("guest_") or (not clean_id and clean_name.lower() in ("게스트", "guest")):
        resolved_grade = int(grade) if (grade and 1 <= int(grade) <= 6) else 4
        # 비회원 체험 중 풀이한 임시 누적 점수 및 풀이 수 실시간 반영
        guest_score = 0
        solved_count = 0
        correct_count = 0
        if clean_id:
            conn = _get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COALESCE(SUM(earned_score), 0), COUNT(*), COALESCE(SUM(is_correct), 0) FROM quiz_logs WHERE user_id = ?",
                    (clean_id,),
                )
                row = cur.fetchone()
                if row:
                    guest_score = int(row[0] or 0)
                    solved_count = int(row[1] or 0)
                    correct_count = int(row[2] or 0)
            except Exception:
                pass
            finally:
                conn.close()

        level_info = calculate_level_tier(guest_score, pokemon_type="grass")
        return {
            "user_id": clean_id or "guest",
            "user_name": clean_name if clean_name.lower() not in ("게스트", "guest") else "게스트",
            "grade": resolved_grade,
            "pokemon_type": "grass",
            "custom_skin_stage": 0,
            "role": "guest",
            "managed_subjects": [],
            "managed_subjects_kr": [],
            "role_display": format_role_display("guest", [], resolved_grade),
            "subject_score": guest_score,
            "math_score": guest_score,
            "total_score": guest_score,
            "integrated_total_score": guest_score,
            "level_info": level_info,
            "solved_count": solved_count,
            "correct_count": correct_count,
        }

    if grade is not None and 1 <= grade <= 6:
        _USER_GRADE_CACHE[clean_name] = int(grade)

    conn = _get_conn()
    try:
        cur = conn.cursor()
        acc_row = None
        if clean_id:
            cur.execute(
                "SELECT user_id, user_name, grade, role, COALESCE(pokemon_type, 'grass') AS pokemon_type, COALESCE(custom_skin_stage, 0) AS custom_skin_stage, COALESCE(managed_subjects, '') AS managed_subjects FROM accounts WHERE user_id = ? LIMIT 1",
                (clean_id,),
            )
            acc_row = cur.fetchone()

        if not acc_row:
            cur.execute(
                "SELECT user_id, user_name, grade, role, COALESCE(pokemon_type, 'grass') AS pokemon_type, COALESCE(custom_skin_stage, 0) AS custom_skin_stage, COALESCE(managed_subjects, '') AS managed_subjects FROM accounts WHERE user_name = ? ORDER BY rowid DESC LIMIT 1",
                (clean_name,),
            )
            acc_row = cur.fetchone()


        resolved_user_id = acc_row["user_id"] if acc_row else (clean_id or "guest")
        if acc_row and acc_row["user_name"]:
            clean_name = _sanitize_name(acc_row["user_name"])

        is_admin_user = (resolved_user_id == "master" or (acc_row and acc_row["role"] == "admin") or clean_name == "마스터")

        if acc_row:
            db_ptype = acc_row["pokemon_type"] or ("dragon" if is_admin_user else "grass")
            # 모바일 및 타 기기 접속 시 초기값('grass') 전송으로 기존 등록 속성이 덮어써지는 현상 원천 방지
            should_update_ptype = False
            if pokemon_type and pokemon_type in POKEMON_TYPE_CONFIG:
                if pokemon_type != db_ptype:
                    # DB에 이미 고유 속성이 있고 클라이언트가 기본값 'grass'를 보낸 경우는 타 기기 초기 접속이므로 덮어쓰지 않음
                    if pokemon_type != "grass" or db_ptype == "grass":
                        should_update_ptype = True

            if should_update_ptype:
                cur.execute("UPDATE accounts SET pokemon_type = ? WHERE user_id = ?", (pokemon_type, acc_row["user_id"]))
                _USER_POKEMON_TYPE_CACHE[clean_name] = pokemon_type
                _USER_POKEMON_TYPE_EXPLICIT[clean_name] = True
            else:
                _USER_POKEMON_TYPE_CACHE[clean_name] = db_ptype
                _USER_POKEMON_TYPE_EXPLICIT[clean_name] = True

            if grade is not None and 1 <= grade <= 6 and not is_admin_user:
                cur.execute("UPDATE accounts SET grade = ? WHERE user_id = ?", (int(grade), acc_row["user_id"]))
            if custom_skin_stage is not None and int(custom_skin_stage) > 0:
                cur.execute("UPDATE accounts SET custom_skin_stage = ? WHERE user_id = ?", (int(custom_skin_stage), acc_row["user_id"]))
            conn.commit()

        cur.execute(
            """
            SELECT
                COALESCE(SUM(earned_score), 0) AS total_score,
                COUNT(*) AS total_solved_count,
                COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0) AS total_correct_count,
                (
                    SELECT grade FROM quiz_logs
                    WHERE ((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))
                      AND grade IS NOT NULL
                    ORDER BY id DESC LIMIT 1
                ) AS latest_grade
            FROM quiz_logs
            WHERE (user_id IS NOT NULL AND user_id != '' AND user_id = ?)
               OR ((user_id IS NULL OR user_id = '') AND user_name = ?)
            """,
            (resolved_user_id, clean_name, resolved_user_id, clean_name),
        )
        row = cur.fetchone()
        db_grade = row["latest_grade"] if (row and row["latest_grade"]) else None

        if is_admin_user:
            resolved_grade = int(acc_row["grade"]) if (acc_row and acc_row["grade"]) else 6
        elif grade is not None and 1 <= grade <= 6:
            resolved_grade = int(grade)
        elif acc_row and acc_row["grade"]:
            resolved_grade = int(acc_row["grade"])
        elif clean_name in _USER_GRADE_CACHE:
            resolved_grade = _USER_GRADE_CACHE[clean_name]
        elif db_grade:
            resolved_grade = int(db_grade)
        else:
            resolved_grade = 4

        _USER_GRADE_CACHE[clean_name] = resolved_grade
        integrated_score = int(row["total_score"] or 0) if row else 0

        # 알(50점 미만)에서 2단계(50점 이상) 진입 시 풀(이상해씨) 고정이 아닌 5대 속성 중 무작위 랜덤 진화!
        # 단, 이미 속성이 명시되었거나 관리자(마스터)인 경우 랜덤 재선택 방지!
        if integrated_score >= 50 and not is_admin_user and not _USER_POKEMON_TYPE_EXPLICIT.get(clean_name, False):
            saved_p = acc_row["pokemon_type"] if acc_row else "grass"
            if saved_p == "grass" and (clean_name not in _USER_POKEMON_TYPE_CACHE or _USER_POKEMON_TYPE_CACHE[clean_name] == "grass"):
                chosen_random_type = random.choice(["grass", "fire", "water", "electric", "psychic"])
                _USER_POKEMON_TYPE_CACHE[clean_name] = chosen_random_type
                _USER_POKEMON_TYPE_EXPLICIT[clean_name] = True
                if acc_row:
                    cur.execute("UPDATE accounts SET pokemon_type = ? WHERE user_id = ?", (chosen_random_type, acc_row["user_id"]))
                    conn.commit()

        resolved_ptype = _USER_POKEMON_TYPE_CACHE.get(clean_name) or (acc_row["pokemon_type"] if acc_row else "grass")
        resolved_skin_stage = int(custom_skin_stage if custom_skin_stage is not None else (acc_row["custom_skin_stage"] if acc_row else 0))
        solved_cnt = int(row["total_solved_count"] or 0) if row else 0
        correct_cnt = int(row["total_correct_count"] or 0) if row else 0
        level_info = calculate_level_tier(integrated_score, pokemon_type=resolved_ptype, custom_skin_stage=resolved_skin_stage)

        # 초등수학 과목 누적 점수
        cur.execute(
            """
            SELECT COALESCE(SUM(earned_score), 0)
            FROM quiz_logs
            WHERE ((user_id IS NOT NULL AND user_id != '' AND user_id = ?) OR ((user_id IS NULL OR user_id = '') AND user_name = ?))
              AND LOWER(subject) = 'math'
            """,
            (resolved_user_id, clean_name),
        )
        math_score_row = cur.fetchone()
        math_score = int(math_score_row[0] or 0) if math_score_row else 0

        resolved_role = acc_row["role"] if acc_row else ("admin" if is_admin_user else "student")
        raw_ms = acc_row["managed_subjects"] if acc_row else ""
        ms_codes = ALL_SUBJECT_CODES[:] if resolved_role == "admin" else parse_managed_subjects(raw_ms)
        ms_labels = [SUBJECT_CODE_TO_LABEL[c] for c in ms_codes if c in SUBJECT_CODE_TO_LABEL]

        return {
            "user_id": acc_row["user_id"] if acc_row else "guest",
            "user_name": clean_name,
            "grade": resolved_grade,
            "pokemon_type": resolved_ptype,
            "custom_skin_stage": resolved_skin_stage,
            "role": resolved_role,
            "managed_subjects": ms_codes,
            "managed_subjects_kr": ms_labels,
            "role_display": format_role_display(resolved_role, ms_codes, resolved_grade),
            "subject_score": math_score,
            "math_score": math_score,
            "total_score": integrated_score,
            "integrated_total_score": integrated_score,
            "level_info": level_info,
            "solved_count": solved_cnt,
            "correct_count": correct_cnt,
        }
    finally:
        conn.close()

