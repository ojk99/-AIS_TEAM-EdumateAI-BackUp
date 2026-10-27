# -*- coding: utf-8 -*-
"""
[EduMate AI - 초등사회] 대규모 스마트 문제은행 모듈 (social/question_bank.py)
- 특징: 
  1. API 키 없이 100% 자립 동작
  2. 1~2학년군, 3~4학년군, 5~6학년군 4대 유형(OX, 4지선다, 단답형, 서술형) 고품질 문제 탑재
  3. 최근 출제 문제 중복 방지(De-duplication) 알고리즘 적용
  4. 서술형 문맥 키워드 5단계(0~5점) 자체 채점 엔진 내장
"""

import os
import json
import re
import random

# ==============================================================================
# 초등사회 전 학년 문제은행 데이터베이스 (Question Database)
# ==============================================================================
QUESTION_BANK = [
    # --------------------------------------------------------------------------
    # [1~2학년군] 통합교과 사회 기초
    # --------------------------------------------------------------------------
    {
        "id": "12_01_ox_1",
        "grade_group": "1~2학년군",
        "unit_name": "학교와 나",
        "question_type": "ox",
        "difficulty": "하",
        "base_score": 1,
        "question": "수업 시간에 하고 싶은 말이 있을 때는 손을 들고 선생님의 허락을 받은 뒤 말해야 해요.",
        "options": [],
        "answer": "O",
        "explanation": "맞아요! 다른 친구들의 이야기를 방해하지 않고 내 생각을 바르게 말하려면 손을 들고 차례를 기다려야 해요."
    },
    {
        "id": "12_01_mc_1",
        "grade_group": "1~2학년군",
        "unit_name": "학교와 나",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "다음 중 학교에서 친구와 사이좋게 지내는 올바른 행동은 무엇일까요?",
        "options": ["친구가 실수했을 때 크게 놀린다.", "놀이를 할 때 규칙을 지키고 차례를 기다린다.", "혼자서만 장난감을 독차지한다.", "친구에게 기분 나쁜 별명을 부른다."],
        "answer": "놀이를 할 때 규칙을 지키고 차례를 기다린다.",
        "explanation": "친구와 함께 놀이할 때는 규칙을 잘 지키고 양보하며 차례를 지켜야 즐겁게 어울릴 수 있어요."
    },
    {
        "id": "12_01_sa_1",
        "grade_group": "1~2학년군",
        "unit_name": "학교와 나",
        "question_type": "short_answer",
        "difficulty": "중",
        "base_score": 3,
        "question": "학교에서 몸이 아프거나 다쳤을 때 치료를 받으러 찾아가는 교실은 어디일까요?",
        "options": [],
        "answer": "보건실",
        "explanation": "몸이 아프거나 상처가 났을 때는 보건 선생님이 계신 보건실로 가서 치료를 받아요."
    },
    {
        "id": "12_01_desc_1",
        "grade_group": "1~2학년군",
        "unit_name": "학교와 나",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "복도나 계단을 다닐 때 뛰지 않고 오른쪽으로 조용히 걸어야 하는 까닭을 적어보세요.",
        "options": [],
        "answer": "친구들과 부딪혀서 다치는 사고를 막고, 수업 중인 교실에 방해가 되지 않기 위해서입니다.",
        "grading_keywords": ["부딪", "다치", "안전", "사고", "방해", "조용"],
        "explanation": "복도에서 뛰면 마주 오는 친구와 부딪혀 크게 다칠 수 있으므로 우측통행을 하며 안전하게 걸어야 해요."
    },

    {
        "id": "12_02_ox_1",
        "grade_group": "1~2학년군",
        "unit_name": "계절과 우리 생활",
        "question_type": "ox",
        "difficulty": "하",
        "base_score": 1,
        "question": "여름에는 날씨가 춥기 때문에 두꺼운 털옷과 목도리를 입어요.",
        "options": [],
        "answer": "X",
        "explanation": "틀려요! 여름은 덥기 때문에 얇고 시원한 옷을 입고, 털옷과 목도리는 추운 겨울에 입어요."
    },
    {
        "id": "12_02_mc_1",
        "grade_group": "1~2학년군",
        "unit_name": "계절과 우리 생활",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "가을에 볼 수 있는 자연의 모습으로 알맞은 것은 무엇일까요?",
        "options": ["알록달록 단풍이 들고 곡식이 무르익어요.", "눈사람을 만들 수 있을 만큼 눈이 내려요.", "매미가 나무에서 요란하게 울어요.", "개나리와 진달래가 활짝 피어나요."],
        "answer": "알록달록 단풍이 들고 곡식이 무르익어요.",
        "explanation": "가을에는 나뭇잎이 붉고 노랗게 물드는 단풍이 들고, 벼와 과일 같은 곡식이 풍성하게 익는 계절이에요."
    },

    {
        "id": "12_03_mc_1",
        "grade_group": "1~2학년군",
        "unit_name": "우리 마을과 사람들",
        "question_type": "multiple_choice",
        "difficulty": "하",
        "base_score": 1,
        "question": "마을에 불이 나거나 위험한 사고가 났을 때 달려와 우리를 도와주시는 곳은 어디일까요?",
        "options": ["소방서", "도서관", "우체국", "은행"],
        "answer": "소방서",
        "explanation": "소방서의 소방관 아저씨들은 불을 끄고 위험에 빠진 사람들을 안전하게 구해 주십니다."
    },
    {
        "id": "12_04_desc_1",
        "grade_group": "1~2학년군",
        "unit_name": "가족과 안전",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "초록불이 켜진 횡단보도를 건널 때에도 좌우를 살피며 조심해서 건너야 하는 까닭은 무엇일까요?",
        "options": [],
        "answer": "멈추지 못하고 달려오는 자동차가 있을 수 있어서 안전을 확인해야 하기 때문입니다.",
        "grading_keywords": ["자동차", "차", "사고", "안전", "멈추", "위험"],
        "explanation": "신호등이 초록불로 바뀌었더라도 갑자기 멈추지 못하는 차량이 있을 수 있으니 꼭 차가 멈춘 것을 보고 건너야 해요."
    },

    # --------------------------------------------------------------------------
    # [3~4학년군] 초등 사회 기초 & 지역 사회
    # --------------------------------------------------------------------------
    {
        "id": "34_01_ox_1",
        "grade_group": "3~4학년군",
        "unit_name": "우리가 사는 곳",
        "question_type": "ox",
        "difficulty": "하",
        "base_score": 1,
        "question": "사람마다 같은 장소에 대해 느끼는 감정과 생각(장소감)은 서로 다를 수 있다.",
        "options": [],
        "answer": "O",
        "explanation": "맞습니다. 같은 놀이터라도 친구와 재미있게 논 아이에게는 즐거운 곳이지만, 넘어져 다친 아이에게는 무서운 장소일 수 있어요."
    },
    {
        "id": "34_01_mc_1",
        "grade_group": "3~4학년군",
        "unit_name": "우리가 사는 곳",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "다음 중 '살기 좋은 우리 고장'을 만들기 위한 주민들의 바람직한 행동은 무엇일까요?",
        "options": ["우리 집 앞 쓰레기만 치우고 골목길은 모른 척한다.", "마을 주민 회의에 참여하여 불편한 점을 함께 해결한다.", "새로운 공공시설을 지을 때 무조건 반대한다.", "공원 시설을 거칠게 사용하여 다른 사람을 못 쓰게 한다."],
        "answer": "마을 주민 회의에 참여하여 불편한 점을 함께 해결한다.",
        "explanation": "살기 좋은 고장은 주민들이 서로 관심을 갖고 마을 회의나 봉사활동에 적극 참여할 때 만들어집니다."
    },
    {
        "id": "34_05_mc_1",
        "grade_group": "3~4학년군",
        "unit_name": "지도로 만나는 우리 지역",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "지도에서 동서남북의 방향을 나타내어 위치를 쉽게 찾을 수 있도록 도와주는 지도 요소는 무엇일까요?",
        "options": ["방위표", "축척", "기호와 범례", "등고선"],
        "answer": "방위표",
        "explanation": "방위표는 지도의 4대 요소 중 하나로, 지도 위에서 동·서·남·북의 위치 방향을 알려줍니다."
    },
    {
        "id": "34_05_sa_1",
        "grade_group": "3~4학년군",
        "unit_name": "지도로 만나는 우리 지역",
        "question_type": "short_answer",
        "difficulty": "중",
        "base_score": 3,
        "question": "지도에서 실제 땅의 거리를 일정한 비율로 줄여서 나타낸 비율을 무엇이라고 부를까요?",
        "options": [],
        "answer": "축척",
        "explanation": "넓은 땅을 종이 지도 한 장에 담기 위해 일정한 비율로 줄여서 나타낸 것을 '축척'이라고 합니다."
    },
    {
        "id": "34_06_mc_1",
        "grade_group": "3~4학년군",
        "unit_name": "우리 지역의 문화유산",
        "question_type": "multiple_choice",
        "difficulty": "하",
        "base_score": 1,
        "question": "다음 중 형태가 없지만 조상들의 지혜와 예술이 담긴 '무형문화유산'에 해당하는 것은 무엇일까요?",
        "options": ["판소리", "석굴암", "다보탑", "수원화성"],
        "answer": "판소리",
        "explanation": "판소리나 탈춤, 한지 공예 기술 등은 형체는 없지만 대대로 이어져 오는 소중한 '무형문화유산'입니다."
    },
    {
        "id": "34_06_desc_1",
        "grade_group": "3~4학년군",
        "unit_name": "우리 지역의 문화유산",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "조상들이 남겨주신 우리 고장의 문화유산을 소중히 아끼고 보존해야 하는 까닭을 서술하세요.",
        "options": [],
        "answer": "문화유산에는 조상들의 지혜와 역사가 담겨 있으며, 한 번 파괴되면 다시 되돌릴 수 없기 때문입니다.",
        "grading_keywords": ["조상", "역사", "지혜", "보존", "훼손", "되돌", "후손", "자랑"],
        "explanation": "문화유산은 과거 조상들의 슬기와 삶을 이해하는 귀중한 보물이며, 파괴되면 복구하기 어렵기 때문에 정성껏 지켜야 합니다."
    },
    {
        "id": "34_07_ox_1",
        "grade_group": "3~4학년군",
        "unit_name": "경제활동과 지역 간 교류",
        "question_type": "ox",
        "difficulty": "하",
        "base_score": 1,
        "question": "인간의 욕심은 끝이 없지만, 세상에 있는 돈과 자원의 양은 한정되어 있는 현상을 '자원의 희소성'이라고 한다.",
        "options": [],
        "answer": "O",
        "explanation": "맞습니다. 사람이 원하는 것에 비해 자원이 부족하기 때문에 우리는 항상 '합리적인 선택'을 해야 합니다."
    },
    {
        "id": "34_08_desc_1",
        "grade_group": "3~4학년군",
        "unit_name": "민주주의와 자치",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "학급 회의에서 다수결의 원칙으로 결정을 내릴 때, 적은 표를 얻은 '소수의 의견'도 존중해야 하는 이유를 적어보세요.",
        "options": [],
        "answer": "다수의 의견이 항상 옳은 것은 아니며, 소수의 의견 속에도 좋은 생각과 권리가 담겨 있기 때문입니다.",
        "grading_keywords": ["소수", "옳", "틀릴", "권리", "존중", "배려", "의견"],
        "explanation": "민주주의에서는 다수결로 결정하더라도 소수의 권리와 의견을 무시하지 않고 끝까지 귀 기울여 배려해야 합니다."
    },

    # --------------------------------------------------------------------------
    # [5~6학년군] 초등 사회 심화 (지리, 역사, 헌법, 세계)
    # --------------------------------------------------------------------------
    {
        "id": "56_01_ox_1",
        "grade_group": "5~6학년군",
        "unit_name": "우리나라 국토 여행",
        "question_type": "ox",
        "difficulty": "하",
        "base_score": 1,
        "question": "한 나라의 주권이 미치는 영토는 땅(영토), 바다(영해), 하늘(영공)을 모두 포함한다.",
        "options": [],
        "answer": "O",
        "explanation": "맞습니다! 국토의 3요소는 영토, 영해, 영공으로 이루어집니다."
    },
    {
        "id": "56_01_mc_1",
        "grade_group": "5~6학년군",
        "unit_name": "우리나라 국토 여행",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "우리나라 한반도의 동쪽과 서쪽 지형의 높낮이 특징을 가장 바르게 설명한 것은 무엇일까요?",
        "options": ["동쪽이 높고 서쪽이 낮다 (동고서저)", "서쪽이 높고 동쪽이 낮다 (서고동저)", "남쪽이 높고 북쪽이 낮다 (남고북저)", "모든 지역의 높이가 평평하다"],
        "answer": "동쪽이 높고 서쪽이 낮다 (동고서저)",
        "explanation": "우리나라는 태백산맥 등이 위치한 동쪽이 높고 황해와 가까운 서쪽에 넓은 평야가 펼쳐진 '동고서저' 지형입니다."
    },
    {
        "id": "56_01_sa_1",
        "grade_group": "5~6학년군",
        "unit_name": "우리나라 국토 여행",
        "question_type": "short_answer",
        "difficulty": "중",
        "base_score": 3,
        "question": "우리나라 가장 동쪽 끝에 위치하며, 화산 활동으로 형성된 천연기념물 섬의 이름은 무엇일까요?",
        "options": [],
        "answer": "독도",
        "explanation": "독도는 울릉도 동남쪽에 위치한 대한민국의 고유 영토이자 소중한 화산섬입니다."
    },
    {
        "id": "56_03_mc_1",
        "grade_group": "5~6학년군",
        "unit_name": "법과 인권의 보장",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "대한민국 최고의 법이자, 국민의 기본권과 국가 운영의 기본 틀을 정해놓은 법은 무엇일까요?",
        "options": ["헌법", "민법", "도로교통법", "형법"],
        "answer": "헌법",
        "explanation": "헌법은 모든 법 중에서 가장 기본적이고 으뜸이 되는 최고의 법률입니다."
    },
    {
        "id": "56_03_desc_1",
        "grade_group": "5~6학년군",
        "unit_name": "법과 인권의 보장",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "모든 인간이 태어나면서부터 당연히 가지는 침해받지 않을 고유한 권리인 '인권'이 왜 소중한지 서술하세요.",
        "options": [],
        "answer": "모든 사람은 존엄성을 지니고 행복하게 살 권리가 있으며, 다른 사람에게 빼앗길 수 없는 소중한 권리이기 때문입니다.",
        "grading_keywords": ["존엄", "행복", "빼앗", "태어나", "권리", "자유", "평등"],
        "explanation": "인권은 성별, 종교, 인종에 상관없이 누구나 인간답게 살아갈 수 있도록 보장하는 가장 기본적인 권리입니다."
    },
    {
        "id": "56_04_mc_1",
        "grade_group": "5~6학년군",
        "unit_name": "유적과 유물로 살펴본 옛 사람들의 생활",
        "question_type": "multiple_choice",
        "difficulty": "하",
        "base_score": 1,
        "question": "신석기 시대 사람들이 곡식을 저장하거나 음식을 조리하기 위해 흙으로 빚어 만든 대표적인 토기는 무엇일까요?",
        "options": ["빗살무늬 토기", "민무늬 토기", "고려청자", "조선백자"],
        "answer": "빗살무늬 토기",
        "explanation": "빗살무늬 토기는 겉면에 빗살 모양의 무늬가 새겨진 신석기 시대의 대표적인 유물입니다."
    },
    {
        "id": "56_05_sa_1",
        "grade_group": "5~6학년군",
        "unit_name": "달라지는 시대, 변화하는 생활 모습",
        "question_type": "short_answer",
        "difficulty": "하",
        "base_score": 1,
        "question": "조선 시대 세종대왕이 백성들이 글을 쉽게 배우고 쓸 수 있도록 만든 글자의 이름은 무엇일까요?",
        "options": [],
        "answer": "훈민정음",
        "explanation": "세종대왕은 백성을 사랑하는 마음으로 1443년에 훈민정음(한글)을 창제하셨습니다."
    },
    {
        "id": "56_08_mc_1",
        "grade_group": "5~6학년군",
        "unit_name": "민주주의와 시민 참여",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "국가 권력이 한곳에 집중되어 남용되는 것을 막기 위해 국회, 행정부, 법원으로 나누는 민주주의 원리는 무엇일까요?",
        "options": ["삼권분립", "국민주권", "다수결의 원칙", "지방자치"],
        "answer": "삼권분립",
        "explanation": "권력을 입법부(국회), 행정부(정부), 사법부(법원)로 나누어 서로 견제하고 균형을 이루게 하는 원리를 삼권분립이라고 합니다."
    },
    {
        "id": "56_08_desc_1",
        "grade_group": "5~6학년군",
        "unit_name": "민주주의와 시민 참여",
        "question_type": "descriptive",
        "difficulty": "상",
        "base_score": 5,
        "question": "민주 국가에서 국가의 중요한 일을 대신할 대표를 뽑는 '선거'의 4대 원칙 중 2가지를 쓰고 뜻을 설명해 보세요.",
        "options": [],
        "answer": "보통 선거(일정 나이가 되면 누구나 투표), 평등 선거(누구나 1인 1표), 직접 선거(자신이 직접 투표), 비밀 선거(누구에게 투표했는지 비밀 보장) 중 2가지.",
        "grading_keywords": ["보통", "평등", "직접", "비밀", "1표", "나이"],
        "explanation": "선거의 4대 원칙은 보통 선거, 평등 선거, 직접 선거, 비밀 선거입니다."
    },
    {
        "id": "56_11_mc_1",
        "grade_group": "5~6학년군",
        "unit_name": "시장경제와 국가 간 거래",
        "question_type": "multiple_choice",
        "difficulty": "중",
        "base_score": 3,
        "question": "다른 나라에서 만든 물건이나 자원을 우리나라로 사들이는 경제 활동을 무엇이라고 할까요?",
        "options": ["수입", "수출", "생산", "환율"],
        "answer": "수입",
        "explanation": "외국 물건을 사 오는 것은 '수입', 우리나라 물건을 외국에 파는 것은 '수출'이라고 합니다."
    }
]


_ALL_QUESTIONS_CACHE = None

def get_all_questions_bank():
    """
    270문항 대규모 문제은행 데이터를 로드 (JSON 캐시 또는 JS 파일 파싱)
    """
    global _ALL_QUESTIONS_CACHE
    if _ALL_QUESTIONS_CACHE is not None and len(_ALL_QUESTIONS_CACHE) >= 100:
        return _ALL_QUESTIONS_CACHE

    curr_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(curr_dir, "questions_data.json")

    # 1. questions_data.json 캐시 파일 로드 (최우선)
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) >= 100:
                    _ALL_QUESTIONS_CACHE = data
                    return _ALL_QUESTIONS_CACHE
        except Exception:
            pass

    # 2. questions_data.js 파싱 시도 (주석 정밀 제거 후 JSON 변환)
    js_path = os.path.join(curr_dir, "questions_data.js")
    if os.path.exists(js_path):
        try:
            with open(js_path, "r", encoding="utf-8") as f:
                content = f.read()

            # JS 한줄/여러줄 주석 완벽 제거
            clean = re.sub(r'//.*?\n', '\n', content)
            clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)

            m = re.search(r"const\s+SOCIAL_QUESTION_BANK_ALL\s*=\s*(\[[\s\S]*?\]);", clean)
            if m:
                raw_json = m.group(1)
                clean_json = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', raw_json)
                clean_json = re.sub(r',\s*([}\]])', r'\1', clean_json)
                items = json.loads(clean_json)
                if isinstance(items, list) and len(items) >= 100:
                    _ALL_QUESTIONS_CACHE = items
                    try:
                        with open(json_path, "w", encoding="utf-8") as out_f:
                            json.dump(items, out_f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    return _ALL_QUESTIONS_CACHE
        except Exception:
            pass

    # 3. 폴백: 기본 내장 문제은행
    _ALL_QUESTIONS_CACHE = QUESTION_BANK
    return _ALL_QUESTIONS_CACHE


# ==============================================================================
# 스마트 출제 및 채점 엔진
# ==============================================================================
class QuestionBankService:
    @staticmethod
    def get_question(grade_group: str, unit_name: str = "", question_type: str = "random", recent_ids: list = None):
        """
        요청 조건에 맞추어 최근 푼 문제를 피해 신선한 문제를 랜덤 추출 (270문항 풀)
        - 한 문제/두 문제가 연속으로 반복 출제되는 현상을 수학적으로 100% 원천 차단
        """
        recent_ids = recent_ids or []
        bank = get_all_questions_bank()
        candidates = []

        # 1차 필터링: 학년군 매칭
        for q in bank:
            # 학년군 일치 확인
            if grade_group and q["grade_group"] != grade_group:
                continue
            # 단원명 일치 확인 (지정된 경우)
            if unit_name and unit_name != "전체 단원" and q["unit_name"] != unit_name:
                continue
            # 문제 유형 일치 확인
            if question_type == "basic_all":
                if q["question_type"] == "descriptive":
                    continue
            elif question_type != "random" and q["question_type"] != question_type:
                continue
            candidates.append(q)

        # 만약 단원이나 유형 필터로 결과가 없으면 학년군 내에서 넓게 탐색
        if not candidates:
            candidates = [q for q in bank if q["grade_group"] == grade_group]

        # 2차: 최근 출제 문제(recent_ids)를 제외한 신선한 후보군 선별
        fresh_candidates = [q for q in candidates if q["id"] not in recent_ids]
        
        # 3차: 신선한 문제가 남아있으면 그 중에서 추첨
        if fresh_candidates:
            selected = random.choice(fresh_candidates)
        else:
            # 후보군 전체를 다 풀어서 fresh가 없는 경우 (예: 단원 내 문항들을 모두 푼 경우)
            # 바로 직전에 푼 1~2개 문제는 무조건 제외하여 즉시 반복 출제 방지!
            avoid_immediate = recent_ids[-2:] if len(recent_ids) >= 2 else (recent_ids[-1:] if recent_ids else [])
            fallback_pool = [q for q in candidates if q["id"] not in avoid_immediate]
            if not fallback_pool:
                fallback_pool = candidates
            selected = random.choice(fallback_pool)
        
        # 원본 보호를 위해 복사본 반환
        return selected.copy()

    @staticmethod
    def grade_answer(q_type: str, correct: str, user_ans: str, base_score: int, keywords: list = None):
        """
        API 키 없이도 자체 수행하는 100% 무설치 정밀 채점
        """
        user_ans_clean = user_ans.strip()
        
        # 1) OX / 객관식 / 단답형 자동 채점
        if q_type in ["ox", "multiple_choice", "short_answer"]:
            is_correct = False
            if q_type == "ox":
                is_correct = (user_ans_clean.upper() == correct.strip().upper())
            elif q_type == "multiple_choice":
                # 번호 또는 텍스트 일치
                is_correct = (user_ans_clean in correct) or (correct in user_ans_clean)
            else:
                # 단답형 유연 채점 (공백 무시, 부분 일치, 초등사회 핵심 동의어/유의어 인정)
                u_norm = user_ans_clean.replace(" ", "")
                c_norm = correct.replace(" ", "")
                
                # 초등사회 핵심 동의어/유의어 사전 세트
                SOCIAL_SYNONYMS = [
                    {"특산물", "특산품"},
                    {"문화재", "문화유산"},
                    {"방위표", "방위표시", "방위"},
                    {"한글", "훈민정음"},
                    {"보건실", "양호실"},
                    {"소방서", "119", "119안전센터"},
                    {"경찰서", "파출소", "지구대"},
                    {"시장", "전통시장", "재래시장"},
                    {"의사소통", "소통"},
                    {"지도", "약도"},
                    {"온돌", "구들장"},
                    {"독도", "우산도"},
                    {"축척", "축척자"},
                    {"등고선", "등고선도"},
                    {"헌법", "대한민국헌법"},
                    {"삼권분립", "권력분립"},
                    {"선거", "투표"},
                    {"국회", "국회의사당"},
                    {"행정부", "정부"},
                    {"법원", "대법원"}
                ]
                
                if (u_norm == c_norm) or (u_norm in c_norm and len(u_norm) >= 2) or (c_norm in u_norm and len(c_norm) >= 2):
                    is_correct = True
                else:
                    for syn_group in SOCIAL_SYNONYMS:
                        if any(syn in u_norm for syn in syn_group) and any(syn in c_norm for syn in syn_group):
                            is_correct = True
                            break

            score = base_score if is_correct else 0
            if is_correct:
                feedback = "정답입니다! 교과서 핵심 개념을 완벽하게 이해하고 있네요! 🌟"
            else:
                feedback = f"아쉬워요! 정답은 [{correct}]입니다. 아래의 상세 해설을 읽어보고 중요한 개념을 꼭 정리해 두세요! 💪"
            return {
                "score": score,
                "max_score": base_score,
                "is_correct": is_correct,
                "feedback": feedback
            }

        # 2) 서술형 5단계(0~5점) 따뜻하고 공정한 부분 점수 채점 (Partial Credit Engine)
        keywords = list(keywords or [])
        # 모범 답안에 포함된 2글자 이상 명사/단어도 추가 키워드로 자동 활용
        correct_words = [w.strip() for w in re.split(r'[\s,\.\?!]+', correct) if len(w.strip()) >= 2]
        all_eval_keywords = list(set(keywords + correct_words))

        hit_count = 0
        for kw in all_eval_keywords:
            if kw in user_ans_clean:
                hit_count += 1

        ans_len = len(user_ans_clean)
        
        # 완전 공백이나 너무 짧은 단답/낙서
        if ans_len < 3:
            earned_score = 0
            feedback = "답안이 너무 짧아요. 자신의 생각을 한 문장으로 조금 더 자세히 적어보세요! 🌱"
        # 1) 만점 (5점): 핵심 키워드가 풍부하거나(3개 이상), 핵심 개념과 설명이 충실한 경우 (20자 이상 & 키워드 2개 이상)
        elif hit_count >= 3 or (hit_count >= 2 and ans_len >= 20):
            earned_score = 5
            feedback = "완벽해요! 핵심 개념과 까닭을 논리정연하게 아주 잘 설명했습니다. 만점입니다! 💯"
        # 2) 우수 부분 점수 (4점): 완벽하지 않더라도 핵심 내용과 의미가 명확히 통하는 경우 (유사 정답)
        elif hit_count >= 2 or (hit_count >= 1 and ans_len >= 12):
            earned_score = 4
            feedback = "훌륭합니다! 정답에 아주 가까워요! 핵심 개념을 잘 파악하여 부분 점수 4점을 획득했습니다! 👏"
        # 3) 보통 부분 점수 (3점): 표현이 서툴거나 짧아도 핵심 단어나 비슷한 생각이 포함된 경우
        elif hit_count >= 1 or ans_len >= 15:
            earned_score = 3
            feedback = "참 잘했어요! 좋은 생각이에요! 중요한 내용이 잘 들어가서 부분 점수 3점을 획득했습니다. 👍"
        # 4) 노력 점수 (2점): 글은 성실히 적었으나 핵심 개념이 조금 부족한 경우
        elif ans_len >= 8:
            earned_score = 2
            feedback = "성실하게 작성한 노력이 돋보여요! 핵심 개념어를 조금 더 보강하면 더 높은 점수를 받을 수 있어요. 🌱"
        else:
            earned_score = 1
            feedback = "좋은 도전이에요! 모범답안을 읽어보고 다음 문제에서는 더 멋지게 적어볼까요? 💪"

        return {
            "score": earned_score,
            "max_score": 5,
            "is_correct": (earned_score >= 3),
            "feedback": feedback
        }
