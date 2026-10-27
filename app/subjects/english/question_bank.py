"""
================================================================================
[EduMate AI 표준 문제은행 모듈 - english/question_bank.py]
================================================================================
- 공통 표준 스키마: question_bank, question_bank_solved 테이블 자동 관리
- 2022 개정 초등영어 표준 어휘/문장 데이터 마이그레이션 (DB_GRADE_34 / DB_GRADE_56)
- 단원별 출제 통계 (맞춘 문제 / 전체 문제) 실시간 계산
- 양방향(AI <-> 문제은행) 출제 지원 및 기풀이 복습 모드 연동
================================================================================
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUBJECT_NAME = "english"


def _resolve_bank_db_path() -> Path:
    """단독 폴더 환경 및 통합 프로젝트 환경 자동 호환 경로 탐색"""
    current_dir = Path(__file__).resolve().parent
    return current_dir / "question_bank.db"


BANK_DB_PATH = _resolve_bank_db_path()


def _get_bank_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(BANK_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_question_bank_db() -> None:
    """표준 문제은행 테이블(question_bank, question_bank_solved) 생성 및 시드 마이그레이션"""
    conn = _get_bank_conn()
    try:
        cur = conn.cursor()
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
            )
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
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qb_subj_unit ON question_bank (subject, unit_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qbs_user ON question_bank_solved (subject, user_key)")
        conn.commit()

        # 기존 문제은행 데이터 마이그레이션 실행 (비어있을 때 자동 채움)
        _migrate_english_curriculum_questions(cur)
        conn.commit()
    finally:
        conn.close()


def _migrate_english_curriculum_questions(cur: sqlite3.Cursor) -> None:
    """초등영어 교육과정 어휘/표현 데이터를 표준 문제은행 DB로 마이그레이션"""
    cur.execute("SELECT COUNT(*) AS cnt FROM question_bank WHERE subject = ?", (SUBJECT_NAME,))
    row = cur.fetchone()
    if row and row["cnt"] > 0:
        return  # 이미 마이그레이션 완료됨

    # 3~4학년 새싹반 (기초 어휘 32개 단원별 데이터)
    raw_grade_34 = [
        ("dog", "/dɔːɡ/", "개, 강아지", "동물", "멍멍 짖는 귀여운 동물", "하", 1),
        ("cat", "/kæt/", "고양이", "동물", "야옹 소리를 내는 동물", "하", 1),
        ("rabbit", "/ˈræb.ɪt/", "토끼", "동물", "귀가 길고 깡충깡충 뛰는 동물", "중", 3),
        ("bear", "/ber/", "곰", "동물", "겨울잠을 자고 꿀을 좋아하는 동물", "하", 1),
        ("bird", "/bɜːrd/", "새", "동물", "날개가 있어 하늘을 나는 동물", "하", 1),
        ("duck", "/dʌk/", "오리", "동물", "꽥꽥 소리를 내며 헤엄치는 새", "하", 1),
        ("pig", "/pɪɡ/", "돼지", "동물", "꿀꿀 소리를 내는 분홍빛 동물", "하", 1),
        ("lion", "/ˈlaɪ.ən/", "사자", "동물", "멋진 갈기를 가진 동물의 왕", "중", 3),
        ("tiger", "/ˈtaɪ.ɡɚ/", "호랑이", "동물", "용맹한 줄무늬를 가진 동물", "중", 3),
        ("monkey", "/ˈmʌŋ.ki/", "원숭이", "동물", "나무를 잘 타고 바나나를 좋아하는 동물", "중", 3),
        ("elephant", "/ˈel.ə.fənt/", "코끼리", "동물", "코가 길고 몸집이 아주 커다란 동물", "상", 5),
        ("frog", "/frɑːɡ/", "개구리", "동물", "개골개골 울며 연못에 사는 동물", "중", 3),
        ("horse", "/hɔːrs/", "말", "동물", "다그닥다그닥 빠르게 달리는 동물", "중", 3),
        ("cow", "/kaʊ/", "소", "동물", "음매 소리를 내며 풀을 먹는 동물", "하", 1),
        ("sheep", "/ʃiːp/", "양", "동물", "복슬복슬 하얀 털을 가진 온순한 동물", "중", 3),
        ("fish", "/fɪʃ/", "물고기", "동물", "물속에서 헤엄치며 아가미로 숨쉬는 동물", "하", 1),
        ("red", "/red/", "빨간색", "색깔", "잘 익은 사과와 딸기의 색깔", "하", 1),
        ("blue", "/bluː/", "파란색", "색깔", "맑은 가을 하늘과 깊은 바다의 색", "하", 1),
        ("yellow", "/ˈjel.oʊ/", "노란색", "색깔", "달콤한 바나나와 개나리의 색", "중", 3),
        ("green", "/ɡriːn/", "초록색", "색깔", "싱그러운 나뭇잎과 잔디의 색", "중", 3),
        ("pink", "/pɪŋk/", "분홍색", "색깔", "화사한 벚꽃과 솜사탕의 색", "하", 1),
        ("black", "/blæk/", "검은색", "색깔", "깜깜한 밤하늘의 색", "하", 1),
        ("white", "/waɪt/", "하얀색", "색깔", "소복소복 내린 깨끗한 눈의 색", "중", 3),
        ("orange", "/ˈɔːr.ɪndʒ/", "주황색", "색깔", "상큼한 귤과 당근의 색", "중", 3),
        ("purple", "/ˈpɜːr.pəl/", "보라색", "색깔", "달콤한 포도와 제비꽃의 색", "상", 5),
        ("brown", "/braʊn/", "갈색", "색깔", "달콤한 초콜릿과 나무 기둥의 색", "중", 3),
        ("apple", "/ˈæp.əl/", "사과", "음식 & 과일", "빨갛고 아삭아삭 맛있는 과일", "하", 1),
        ("banana", "/bəˈnæn.ə/", "바나나", "음식 & 과일", "껍질을 까먹는 길쭉한 노란 과일", "중", 3),
        ("milk", "/mɪlk/", "우유", "음식 & 과일", "매일 아침 마시는 고소한 하얀 음료", "하", 1),
        ("bread", "/bred/", "빵", "음식 & 과일", "밀가루를 오븐에 구워 만든 음식", "하", 1),
        ("water", "/ˈwɔː.tər/", "물", "음식 & 과일", "목마를 때 마시는 시원하고 투명한 음료", "하", 1),
        ("egg", "/eɡ/", "달걀", "음식 & 과일", "둥글고 영양이 풍부한 닭의 알", "하", 1),
        ("cheese", "/tʃiːz/", "치즈", "음식 & 과일", "피자에 얹어 먹는 짭짤하고 고소한 유제품", "중", 3),
        ("juice", "/dʒuːs/", "주스", "음식 & 과일", "과일을 짜서 만든 달콤한 음료", "중", 3),
        ("cookie", "/ˈkʊk.i/", "쿠키, 과자", "음식 & 과일", "바삭바삭 구운 달콤한 간식", "중", 3),
        ("pizza", "/ˈpiːt.sə/", "피자", "음식 & 과일", "치즈와 토핑을 얹어 구운 둥근 이탈리아 요리", "중", 3),
        ("book", "/bʊk/", "책", "학교 & 학용품", "이야기와 그림이 담긴 읽을거리", "하", 1),
        ("pencil", "/ˈpen.səl/", "연필", "학교 & 학용품", "공책에 사각사각 글씨를 쓰는 필기도구", "중", 3),
        ("desk", "/desk/", "책상", "학교 & 학용품", "공부할 때 책을 펴놓는 가구", "하", 1),
        ("chair", "/tʃer/", "의자", "학교 & 학용품", "다리가 4개 있고 편하게 앉는 가구", "중", 3),
        ("bag", "/bæɡ/", "가방", "학교 & 학용품", "교과서와 필통을 넣어 메는 가방", "하", 1),
        ("ruler", "/ˈruː.lɚ/", "자", "학교 & 학용품", "길이를 재거나 반듯하게 줄을 긋는 도구", "중", 3),
        ("eraser", "/ɪˈreɪ.sɚ/", "지우개", "학교 & 학용품", "틀린 연필 글씨를 쓱쓱 지우는 도구", "상", 5),
        ("mom", "/mɑːm/", "엄마", "가족", "나를 사랑으로 안아주시는 어머니", "하", 1),
        ("dad", "/dæd/", "아빠", "가족", "나를 든든하게 지켜주시는 아버지", "하", 1),
        ("sun", "/sʌn/", "해, 태양", "자연 & 날씨", "낮 하늘에 환하게 떠서 온 세상을 비추는 빛", "하", 1),
        ("star", "/stɑːr/", "별", "자연 & 날씨", "깜깜한 밤하늘에 반짝반짝 빛나는 보석 같은 빛", "하", 1),
    ]

    # 5~6학년 열매반 (실전 응용 어휘 데이터)
    raw_grade_56 = [
        ("library", "/ˈlaɪ.brer.i/", "도서관", "공공장소", "조용히 책을 읽고 빌리는 지혜의 공간", "중", 3),
        ("hospital", "/ˈhɑː.spɪ.t̬əl/", "병원", "공공장소", "의사 선생님과 간호사님이 아픈 사람을 치료하는 곳", "상", 5),
        ("museum", "/mjuːˈziː.əm/", "박물관", "공공장소", "귀중한 역사 유물과 예술품을 전시하고 보존하는 곳", "상", 5),
        ("station", "/ˈsteɪ.ʃən/", "역, 정류장", "공공장소", "기차나 지하철을 타고 내리는 교통 중심지", "중", 3),
        ("market", "/ˈmɑːr.kɪt/", "시장", "공공장소", "싱싱한 채소와 과일, 생선 등을 파는 활기찬 장소", "중", 3),
        ("restaurant", "/ˈres.tə.rɑːnt/", "식당", "공공장소", "맛있는 요리를 주문하여 먹을 수 있는 음식점", "상", 5),
        ("bank", "/bæŋk/", "은행", "공공장소", "돈을 안전하게 저축하고 빌려주는 금융 기관", "중", 3),
        ("park", "/pɑːrk/", "공원", "공공장소", "나무와 벤치가 있어 산책하고 뛰어놀 수 있는 쉼터", "하", 1),
        ("cinema", "/ˈsɪn.ə.mə/", "영화관", "공공장소", "커다란 스크린으로 재미있는 영화를 감상하는 곳", "중", 3),
        ("doctor", "/ˈdɑːk.tɚ/", "의사", "직업", "아픈 환자의 병을 진찰하고 치료해 주시는 분", "중", 3),
        ("teacher", "/ˈtiː.tʃɚ/", "선생님", "직업", "학교에서 학생들에게 지식과 바른 인성을 가르치는 분", "중", 3),
        ("pilot", "/ˈpaɪ.lət/", "비행기 조종사", "직업", "하늘을 나는 거대한 비행기를 안전하게 운항하는 분", "상", 5),
        ("cook", "/kʊk/", "요리사", "직업", "신선한 재료로 맛있는 음식을 정성껏 만드는 전문가", "하", 1),
        ("scientist", "/ˈsaɪ.ən.tɪst/", "과학자", "직업", "자연의 신비와 우주의 원리를 깊이 탐구하고 연구하는 분", "상", 5),
        ("artist", "/ˈɑːr.tɪst/", "화가, 예술가", "직업", "도화지에 아름다운 그림을 그리거나 예술품을 빚는 분", "중", 3),
        ("singer", "/ˈsɪŋ.ɚ/", "가수", "직업", "아름다운 목소리로 사람들에게 감동을 주는 노래를 부르는 분", "하", 1),
        ("police", "/pəˈliːs/", "경찰관", "직업", "시민의 안전을 지키고 범죄를 예방하는 멋진 분", "중", 3),
        ("firefighter", "/ˈfaɪrˌfaɪ.t̬ɚ/", "소방관", "직업", "위험한 불을 끄고 위급한 사람들을 구조하는 영웅", "상", 5),
        ("farmer", "/ˈfɑːr.mɚ/", "농부", "직업", "땅을 일구어 벼와 곡식, 채소를 정성스레 기르는 분", "중", 3),
        ("weather", "/ˈweð.ɚ/", "날씨", "자연 & 환경", "비, 눈, 맑음 등 매일매일 변화하는 하늘의 상태", "중", 3),
        ("season", "/ˈsiː.zən/", "계절", "자연 & 환경", "봄, 여름, 가을, 겨울의 아름다운 순환", "중", 3),
        ("planet", "/ˈplæn.ɪt/", "행성", "자연 & 우주", "태양 주위를 공전하는 지구, 화성 같은 천체", "상", 5),
        ("forest", "/ˈfɔːr.ɪst/", "숲", "자연 & 환경", "많은 나무들이 울창하게 모여 있어 공기가 맑은 곳", "중", 3),
        ("ocean", "/ˈoʊ.ʃən/", "대양, 바다", "자연 & 환경", "지구의 대부분을 덮고 있는 넓고 푸른 깊은 바다", "중", 3),
        ("bridge", "/brɪdʒ/", "다리", "교통 & 도시", "강이나 바다를 건널 수 있도록 건설된 구조물", "상", 5),
        ("traffic", "/ˈtræf.ɪk/", "교통", "교통 & 도시", "도로 위를 오가는 많은 자동차와 버스의 흐름", "상", 5),
        ("subway", "/ˈsʌb.weɪ/", "지하철", "교통 & 도시", "땅속 터널을 빠르게 달리는 편리한 전철", "중", 3),
        ("bicycle", "/ˈbaɪ.sə.kəl/", "자전거", "교통 & 도시", "두 페달을 밟아 바퀴를 굴리며 타는 탈것", "중", 3),
        ("journey", "/ˈdʒɜːr.ni/", "여행, 여정", "활동 & 여가", "새로운 곳을 향해 떠나는 설레는 발걸음", "상", 5),
    ]

    all_seed = [(34, "3~4학년군", item) for item in raw_grade_34] + [(56, "5~6학년군", item) for item in raw_grade_56]

    for g_num, g_group, (word, ipa, meaning, unit, hint, diff, pts) in all_seed:
        # 1) 객관식 문제 등록
        distractors = [w for w, _, m, u, _, _, _ in raw_grade_34 if w != word][:3] if g_num == 34 else [w for w, _, m, u, _, _, _ in raw_grade_56 if w != word][:3]
        choices = [word] + distractors
        choices_str = json.dumps(choices, ensure_ascii=False)
        q_text_choice = f"'{meaning}'을(를) 뜻하는 알맞은 영어 단어는 무엇일까요?"
        expl_choice = f"정답은 '{word}' ({ipa})입니다. 뜻: {meaning}"

        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation, source_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 'master')
            """,
            (
                SUBJECT_NAME,
                4 if g_num == 34 else 6,
                g_group,
                unit,
                meaning,
                "객관식",
                diff,
                pts,
                q_text_choice,
                choices_str,
                word,
                expl_choice,
            ),
        )

        # 2) 단답형 철자 쓰기 문제 등록
        w_len = len(word)
        f_char = word[0].upper()
        l_char = word[-1].upper() if w_len >= 3 else ""
        hint_slot = f"총 {w_len}글자 (첫 글자 '{f_char}'" + (f", 끝 글자 '{l_char}'" if l_char else "") + ")"
        q_text_short = f"[힌트: {hint}] '{meaning}'을(를) 뜻하는 영어 단어의 올바른 철자를 작성하세요. ({hint_slot})"
        expl_short = f"정답 단어는 '{word}' ({ipa})입니다. 뜻: {meaning}"

        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation, source_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 'master')
            """,
            (
                SUBJECT_NAME,
                4 if g_num == 34 else 6,
                g_group,
                unit,
                meaning,
                "단답형",
                diff,
                pts,
                q_text_short,
                "[]",
                word,
                expl_short,
            ),
        )

        # 3) 서술형 문장 표현 문제 등록
        sample_sentence = f"I like {word}s." if unit in ["동물", "음식 & 과일"] else f"This is a {word}."
        q_text_desc = f"오늘 배운 단어 '{word}'({meaning})을(를) 포함하여 초등 수준의 자연스러운 영어 문장을 1개 만들어 보세요."
        expl_desc = f"모범 문장 예시: '{sample_sentence}' (목표 단어 '{word}'를 문맥에 맞게 활용하고 주어와 동사를 갖추면 만점)"

        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation, source_type, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', 'master')
            """,
            (
                SUBJECT_NAME,
                4 if g_num == 34 else 6,
                g_group,
                unit,
                meaning,
                "서술형",
                "상" if g_num == 56 else "중",
                5 if g_num == 56 else 3,
                q_text_desc,
                "[]",
                sample_sentence,
                expl_desc,
            ),
        )


def get_unit_bank_stats(
    subject: str = "english",
    user_key: str = "김에듀",
    grade: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    각 단원별 (맞춘 문제 / 전체 은행 문제) 실시간 통계 계산
    반환 예시: [{'unit_name': '동물', 'solved': 2, 'total': 48, 'remaining': 46}, ...]
    """
    init_question_bank_db()
    clean_user = (user_key or "김에듀").strip() or "김에듀"
    conn = _get_bank_conn()
    try:
        cur = conn.cursor()
        grade_cond = "AND grade = ?" if grade else ""
        params_total: List[Any] = [subject]
        if grade:
            params_total.append(int(grade))

        cur.execute(
            f"""
            SELECT unit_name, COUNT(*) as total_cnt
            FROM question_bank
            WHERE subject = ? {grade_cond}
            GROUP BY unit_name
            ORDER BY MIN(id) ASC
            """,
            params_total,
        )
        total_rows = cur.fetchall()

        params_solved: List[Any] = [subject, clean_user]
        if grade:
            params_solved.append(int(grade))

        cur.execute(
            f"""
            SELECT qb.unit_name, COUNT(DISTINCT qbs.bank_id) as solved_cnt
            FROM question_bank_solved qbs
            JOIN question_bank qb ON qbs.bank_id = qb.id
            WHERE qbs.subject = ? AND qbs.user_key = ? {grade_cond.replace('grade', 'qb.grade')}
            GROUP BY qb.unit_name
            """,
            params_solved,
        )
        solved_map = {r["unit_name"]: r["solved_cnt"] for r in cur.fetchall()}

        result = []
        for r in total_rows:
            u_name = r["unit_name"]
            tot = int(r["total_cnt"])
            sol = int(solved_map.get(u_name, 0))
            result.append({
                "unit_name": u_name,
                "solved": sol,
                "total": tot,
                "remaining": max(0, tot - sol),
                "ratio_text": f"({sol}/{tot})",
            })
        return result
    finally:
        conn.close()


def mark_bank_question_solved(bank_id: int, subject: str = "english", user_key: str = "김에듀") -> bool:
    """학생이 문제은행 문제를 해결했을 때 question_bank_solved 에 기록"""
    init_question_bank_db()
    clean_user = (user_key or "김에듀").strip() or "김에듀"
    conn = _get_bank_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key)
            VALUES (?, ?, ?)
            """,
            (int(bank_id), subject, clean_user),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[mark_bank_question_solved Error]: {e}")
        return False
    finally:
        conn.close()


def fetch_next_bank_question(
    subject: str = "english",
    unit_name: Optional[str] = None,
    grade: Optional[int] = None,
    question_type: Optional[str] = None,
    user_key: str = "김에듀",
    allow_review: bool = False,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    문제은행 출제 코어 함수
    반환: (question_dict, is_review)
    - 1순위: 아직 안 푼 문제 (is_review = False)
    - 2순위 (allow_review=True): 이미 푼 문제 중 랜덤 출제 (is_review = True)
    - 3순위: 문제 없음 (None, False)
    """
    init_question_bank_db()
    clean_user = (user_key or "김에듀").strip() or "김에듀"
    conn = _get_bank_conn()
    try:
        cur = conn.cursor()

        # 조건 빌드
        conds = ["subject = ?"]
        params: List[Any] = [subject]

        if unit_name and unit_name != "전체 단원":
            conds.append("unit_name = ?")
            params.append(unit_name)

        if grade:
            conds.append("grade = ?")
            params.append(int(grade))

        if question_type:
            conds.append("question_type = ?")
            params.append(question_type)

        where_clause = " AND ".join(conds)

        # 1단계: 미풀이 문제 조회
        cur.execute(
            f"""
            SELECT * FROM question_bank
            WHERE {where_clause}
              AND id NOT IN (
                  SELECT bank_id FROM question_bank_solved
                  WHERE subject = ? AND user_key = ?
              )
            ORDER BY RANDOM()
            LIMIT 1
            """,
            params + [subject, clean_user],
        )
        row = cur.fetchone()
        if row:
            return _row_to_dict(row), False

        # 2단계: 다 풀었을 때 복습 모드 (allow_review = True 일 때)
        if allow_review:
            cur.execute(
                f"""
                SELECT * FROM question_bank
                WHERE {where_clause}
                ORDER BY RANDOM()
                LIMIT 1
                """,
                params,
            )
            row_rev = cur.fetchone()
            if row_rev:
                return _row_to_dict(row_rev), True

        # 3단계: 해당 조건의 문제가 전혀 없음
        return None, False
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    choices = []
    raw_choices = row["choices_json"]
    if raw_choices:
        try:
            choices = json.loads(raw_choices)
        except Exception:
            choices = []

    return {
        "id": row["id"],
        "bank_id": row["id"],
        "subject": row["subject"],
        "grade": row["grade"],
        "grade_group": row["grade_group"],
        "unit_name": row["unit_name"],
        "sub_topic": row["sub_topic"],
        "question_type": row["question_type"],
        "difficulty": row["difficulty"],
        "points": row["points"],
        "question_text": row["question_text"],
        "choices": choices,
        "correct_answer": row["correct_answer"],
        "explanation": row["explanation"],
        "source_type": row["source_type"],
    }


def save_question_to_bank(
    question_text: str,
    correct_answer: str,
    question_type: str = "객관식",
    grade: int = 4,
    grade_group: str = "3~4학년군",
    unit_name: str = "기본 어휘",
    sub_topic: str = "",
    difficulty: str = "중",
    points: int = 3,
    choices: Optional[List[str]] = None,
    explanation: str = "",
    source_type: str = "manual",
    source_log_id: Optional[int] = None,
    created_by: str = "master",
    created_by_name: str = "총 관리자",
) -> int:
    """새로운 문제를 표준 question_bank 테이블에 저장/등록"""
    init_question_bank_db()
    conn = _get_bank_conn()
    try:
        cur = conn.cursor()
        choices_json = json.dumps(choices, ensure_ascii=False) if choices else "[]"
        cur.execute(
            """
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation,
                source_type, source_log_id, created_by, created_by_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SUBJECT_NAME,
                grade,
                grade_group,
                unit_name,
                sub_topic,
                question_type,
                difficulty,
                points,
                question_text,
                choices_json,
                correct_answer,
                explanation,
                source_type,
                source_log_id,
                created_by,
                created_by_name,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# 모듈 임포트 시 표준 문제은행 DB 자동 초기화 (테이블 및 시드 데이터 보장)
try:
    init_question_bank_db()
except Exception:
    pass


