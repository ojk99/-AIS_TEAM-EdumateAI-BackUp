"""
EduMate AI - 초등 과학 1~6학년 전 단원 문제은행 안전 대량 사전 적재 배치 스크립트
==============================================================================
- 규격 준수: Gemini 3.5 Flash-lite (v1 API)
- 속도 제한 준수: 분당 13회 이하 (4.5초 텀 유지 -> 429 Rate Limit 방지)
- 상한선 준수: 단원별 최대 30개 한도 엄수 (MAX_UNIT_QUESTIONS = 30)
- 충전 단위: 단원별 15개 가변 리필
==============================================================================
"""
import sys
import time
import json
import sqlite3
from pathlib import Path

current_dir = Path(__file__).resolve().parent
DB_PATH = current_dir / "question_bank.db"
SUBJECT_NAME = "science"
MAX_UNIT_QUESTIONS = 30
REFILL_BATCH_SIZE = 15

# 1~6학년 대표 단원 목록 (curriculum.txt 기준)
ALL_CURRICULUM_UNITS = [
    # 1학년
    (1, "입학", "ox"),
    (1, "봄", "mcq"),
    (1, "가족", "ox"),
    (1, "여름", "mcq"),
    (1, "하루", "subjective"),
    (1, "가을", "mcq"),
    (1, "나라", "ox"),
    (1, "겨울", "subjective"),

    # 2학년
    (2, "나", "ox"),
    (2, "봄", "mcq"),
    (2, "마을", "ox"),
    (2, "여름", "mcq"),
    (2, "일", "ox"),
    (2, "가을", "mcq"),
    (2, "세상", "subjective"),
    (2, "겨울", "ox"),

    # 3학년
    (3, "힘과 우리 생활", "mcq"),
    (3, "자석의 이용", "ox"),
    (3, "물질의 성질", "subjective"),
    (3, "동물의 한살이", "mcq"),
    (3, "동물의 생활", "subjective"),
    (3, "소리의 성질", "ox"),
    (3, "지구와 달", "mcq"),
    (3, "물의 여행", "ox"),

    # 4학년
    (4, "식물의 생활", "mcq"),
    (4, "지층과 화석", "subjective"),
    (4, "물의 상태 변화", "ox"),
    (4, "기후변화와 우리 생활", "mcq"),
    (4, "식물의 한살이", "ox"),
    (4, "빛과 그림자", "mcq"),
    (4, "화산과 지진", "subjective"),
    (4, "물체의 무게", "ox"),

    # 5학년
    (5, "여러 가지 기체", "mcq"),
    (5, "태양계와 별", "ox"),
    (5, "용해와 용액", "subjective"),
    (5, "생물과 환경", "mcq"),
    (5, "날씨와 우리 생활", "ox"),
    (5, "물체의 운동", "subjective"),
    (5, "산과 염기", "mcq"),
    (5, "우리 몸의 구조와 기능", "ox"),

    # 6학년
    (6, "지구와 달의 운동", "mcq"),
    (6, "식물의 구조와 기능", "subjective"),
    (6, "빛과 렌즈", "ox"),
    (6, "전기의 이용", "mcq"),
    (6, "계절의 변화", "subjective"),
    (6, "물질의 연소와 소화", "ox"),
    (6, "에너지와 생활", "mcq"),
    (6, "과학과 나의 진로", "ox")
]


def run_batch_fill():
    from service import generate_ox_quiz, generate_mcq_quiz, generate_subjective_quiz

    conn = sqlite3.connect(str(DB_PATH))
    print("\n" + "=" * 65)
    print("🚀 [EduMate AI 초등 과학 - 전 단원 문제은행 안전 대량 충전 시작]")
    print(f"* 총 대상 단원/유형: {len(ALL_CURRICULUM_UNITS)}개 세트")
    print(f"* 안전 딜레이: 4.5초 간격 (분당 요청 한도 100% 안전 보장)")
    print(f"* 단원별 상한선: 최대 {MAX_UNIT_QUESTIONS}개")
    print("=" * 65 + "\n")

    success_units = 0
    total_added_questions = 0

    try:
        cur = conn.cursor()

        for idx, (grade, unit, q_type) in enumerate(ALL_CURRICULUM_UNITS, 1):
            # 1. 현재 단원 문제 수 확인
            cur.execute(
                "SELECT COUNT(*) FROM question_bank WHERE subject = ? AND grade = ? AND unit_name = ?",
                (SUBJECT_NAME, grade, unit)
            )
            curr_cnt = cur.fetchone()[0]

            if curr_cnt >= MAX_UNIT_QUESTIONS:
                print(f"[{idx}/{len(ALL_CURRICULUM_UNITS)}] {grade}학년 [{unit}] - 이미 {curr_cnt}개 등록됨 (한도 충족, 건너뜀)")
                continue

            capacity = MAX_UNIT_QUESTIONS - curr_cnt
            req_count = min(REFILL_BATCH_SIZE, capacity)

            print(f"[{idx}/{len(ALL_CURRICULUM_UNITS)}] {grade}학년 [{unit}] ({q_type} 모드) -> {req_count}문제 생성 중... (현재: {curr_cnt}개)")

            new_items = []
            try:
                if q_type == "ox":
                    raw_data = generate_ox_quiz(grade=grade, unit=unit, count=req_count)
                    for item in raw_data:
                        new_items.append((
                            grade, f"{grade}학년", unit, "",
                            "ox", "하", 1, item.get("question", ""),
                            "[]", str(item.get("answer", "O")),
                            item.get("explanation", ""), "batch_fill"
                        ))
                elif q_type == "subjective":
                    res = generate_subjective_quiz(grade=grade, unit=unit, count=req_count)
                    for item in res.get("items", []):
                        ans = str(item.get("model_answer", "")).strip()
                        q_t = "서술형" if len(ans) > 15 else "단답형"
                        pts = 5 if q_t == "서술형" else 3
                        new_items.append((
                            grade, f"{grade}학년", unit, "",
                            q_t, "상" if q_t == "서술형" else "중", pts, item.get("question", ""),
                            "[]", ans,
                            item.get("explanation", "") or item.get("grading_criteria", ""), "batch_fill"
                        ))
                else:  # mcq
                    raw_data = generate_mcq_quiz(grade=grade, unit=unit, count=req_count)
                    for item in raw_data:
                        opts = item.get("options", [])
                        ans = str(item.get("answer", 1))
                        new_items.append((
                            grade, f"{grade}학년", unit, "",
                            "객관식", "중", 3, item.get("question", ""),
                            json.dumps(opts, ensure_ascii=False), ans,
                            item.get("explanation", ""), "batch_fill"
                        ))

                # DB 저장
                inserted_count = 0
                for item in new_items:
                    # 상한선 실시간 점검
                    cur.execute(
                        "SELECT COUNT(*) FROM question_bank WHERE subject = ? AND grade = ? AND unit_name = ?",
                        (SUBJECT_NAME, grade, unit)
                    )
                    now_cnt = cur.fetchone()[0]
                    if now_cnt >= MAX_UNIT_QUESTIONS:
                        break

                    # 중복 지문 스킵
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
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'batch_system', '대량 충전봇')
                        """,
                        (SUBJECT_NAME,) + item
                    )
                    inserted_count += 1
                conn.commit()

                cur.execute(
                    "SELECT COUNT(*) FROM question_bank WHERE subject = ? AND grade = ? AND unit_name = ?",
                    (SUBJECT_NAME, grade, unit)
                )
                final_cnt = cur.fetchone()[0]
                print(f"    ➡️ {inserted_count}문제 추가 완료! (현재 총: {final_cnt}/{MAX_UNIT_QUESTIONS}개)")
                total_added_questions += inserted_count
                success_units += 1

            except Exception as e_gen:
                print(f"    ⚠️ [{unit}] 생성 중 오류: {e_gen}")

            # API 속도 제한 방지 (4.5초 슬립)
            time.sleep(4.5)

        print("\n" + "=" * 65)
        print(f"🎉 [전 단원 대량 충전 완료!] 추가된 총 문제 수: {total_added_questions}개 (성공 단원: {success_units}개)")
        print("=" * 65 + "\n")

    finally:
        conn.close()


if __name__ == "__main__":
    run_batch_fill()
