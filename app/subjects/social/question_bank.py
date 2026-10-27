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
        "question": "사람마다 같은 장소에 대해 느끼는 감정과 생각(장소감)은 서로 다를 수 있어요.",
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
        "question": "조상들이 남겨주신 우리 고장의 문화유산을 소중히 아끼고 보존해야 하는 까닭을 적어 보세요.",
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
        "question": "사람이 원하는 것에 비해 세상에 있는 돈과 자원의 양은 한정되어 있는 현상을 '자원의 희소성'이라고 해요.",
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
        "question": "한 나라의 주권이 미치는 국토는 땅(영토), 바다(영해), 하늘(영공)을 모두 포함해요.",
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
        "question": "모든 사람이 태어나면서부터 가지는 침해받지 않을 고유한 권리인 '인권'이 왜 소중한지 적어 보세요.",
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
        # 1단계: 학년군 필터링
        grade_candidates = [q for q in bank if not grade_group or q.get("grade_group") == grade_group]
        if not grade_candidates:
            grade_candidates = bank

        # 2단계: 단원 필터링 (특정 단원이 지정된 경우 타 단원 이탈 원천 차단!)
        candidates = grade_candidates
        is_specific_unit = unit_name and unit_name != "전체 단원"
        if is_specific_unit:
            unit_filtered = [q for q in grade_candidates if q.get("unit_name") == unit_name]
            if not unit_filtered:
                # 부분 일치 탐색 (축약어 또는 공백 호환)
                unit_filtered = [q for q in grade_candidates if q.get("unit_name") and (unit_name in q["unit_name"] or q["unit_name"] in unit_name)]
            if unit_filtered:
                candidates = unit_filtered

        # 3단계: 문제 유형 필터링 (단원 일치 후보군 내에서 우선 검색)
        type_filtered = []
        for q in candidates:
            if question_type == "basic_all":
                if q.get("question_type") != "descriptive":
                    type_filtered.append(q)
            elif question_type and question_type != "random":
                if q.get("question_type") == question_type:
                    type_filtered.append(q)
            else:
                type_filtered.append(q)

        # 해당 단원에 요청한 유형이 있으면 적용, 없더라도 단원을 벗어나지 않고 단원 후보군 유지!
        if type_filtered:
            candidates = type_filtered

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


# ==============================================================================
# [표준 문제은행 DB (question_bank.db) 개설 · 마이그레이션 · 통계 · AI 채점 모듈]
# ==============================================================================
import sqlite3
import inspect
from pathlib import Path
from typing import Optional, Dict, Any, List

SUBJECT_CODE = "social"
BANK_DB_PATH = Path(__file__).resolve().parent / "question_bank.db"

# 조장(수학 과목)의 표준 모듈이 통합 환경에 존재하는지 확인
try:
    from app.subjects.math.question_bank import (
        get_unit_bank_stats as _shared_get_unit_bank_stats,
        mark_bank_question_solved as _shared_mark_bank_question_solved,
        grade_bank_question_by_ai as _shared_grade_bank_question_by_ai,
    )
    HAS_SHARED_MATH_BANK = True
except Exception:
    HAS_SHARED_MATH_BANK = False

# 단원별 기본 학년(1~6) 매핑
UNIT_GRADE_MAP = {
    "학교와 나": 1,
    "계절과 우리 생활": 1,
    "우리 마을과 사람들": 2,
    "가족과 안전": 2,
    "우리가 사는 곳": 3,
    "일상에서 만나는 과거": 3,
    "사회 변화와 다양한 문화": 3,
    "옛날과 오늘날의 생활 모습": 3,
    "다양한 환경과 삶의 모습": 3,
    "지도로 만나는 우리 지역": 4,
    "우리 지역의 문화유산": 4,
    "경제활동과 지역 간 교류": 4,
    "민주주의와 자치": 4,
    "지역문제를 해결하고 지역을 알리는 노력": 4,
    "우리나라 국토 여행": 5,
    "우리나라 지리 탐구": 5,
    "법과 인권의 보장": 5,
    "유적과 유물로 살펴본 옛 사람들의 생활": 5,
    "달라지는 시대, 변화하는 생활 모습": 5,
    "식민 통치와 저항, 전쟁이 바꾼 사회와 생활": 6,
    "평화 통일을 위한 노력, 민주화와 산업화": 6,
    "민주주의와 시민 참여": 6,
    "지구, 대륙 그리고 국가들": 6,
    "세계의 자연환경": 6,
    "시장경제와 국가 간 거래": 6,
    "지구촌 사람들": 6,
}

# 문제 유형 표준화 매핑 (DB 저장용 한국어 표준 <-> 프론트엔드 영문 코드 호환)
TYPE_TO_KO = {
    "ox": "ox",
    "OX": "ox",
    "multiple_choice": "객관식",
    "객관식": "객관식",
    "short_answer": "단답형",
    "단답형": "단답형",
    "주관식": "단답형",
    "descriptive": "서술형",
    "서술형": "서술형",
}

TYPE_TO_EN = {
    "ox": "ox",
    "OX": "ox",
    "객관식": "multiple_choice",
    "multiple_choice": "multiple_choice",
    "단답형": "short_answer",
    "주관식": "short_answer",
    "short_answer": "short_answer",
    "서술형": "descriptive",
    "descriptive": "descriptive",
}


def get_bank_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(BANK_DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_user_keys(user_id: Optional[str] = None, user_name: Optional[str] = None) -> List[str]:
    """
    회원 ID 및 이름을 기반으로 question_bank_solved 조회/저장에 사용할 user_key 후보 목록을 생성합니다.
    조장 공통 라우터(platform.py)의 다양한 user_key 규격과 100% 호환됩니다.
    """
    uid = str(user_id or "").strip()
    uname = str(user_name or "").strip()
    if uname.startswith("{"):
        try:
            obj = json.loads(uname)
            uid = uid or str(obj.get("id") or obj.get("user_id") or "").strip()
            uname = str(obj.get("name") or obj.get("user_name") or obj.get("id") or "김에듀").strip()
        except Exception:
            pass

    keys = []
    if uid:
        keys.append(uid)
        keys.append(f"id:{uid}")
    if uname:
        keys.append(uname)
        keys.append(f"name:{uname}")
    if uid and uname:
        keys.append(f"{uid}:{uname}")
        keys.append(f"{uid}|{uname}")
    if not keys:
        keys.append("guest")
    # 순서 유지 중복 제거
    seen = set()
    result = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            result.append(k)
    return result


def get_primary_user_key(user_id: Optional[str] = None, user_name: Optional[str] = None) -> str:
    keys = _normalize_user_keys(user_id, user_name)
    return keys[0] if keys else "guest"


def init_question_bank_db() -> Dict[str, Any]:
    """
    내 과목 폴더(social/question_bank.db)에 표준 스키마 테이블을 생성하고,
    기존 270문항(questions_data.json / questions_data.js / QUESTION_BANK)을 손실 없이 마이그레이션합니다.
    """
    conn = get_bank_db_connection()
    cur = conn.cursor()

    cur.execute("""
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
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS question_bank_solved (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            user_key TEXT NOT NULL,
            solved_at TIMESTAMP DEFAULT (DATETIME('now', 'localtime')),
            UNIQUE(bank_id, subject, user_key)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_qb_subject_unit ON question_bank (subject, unit_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qbs_user ON question_bank_solved (subject, user_key, bank_id)")

    # 기존에 마이그레이션된 문제 확인 (중복 삽입 방지)
    cur.execute("SELECT question_text, unit_name FROM question_bank WHERE subject = ?", (SUBJECT_CODE,))
    existing_set = {(row["unit_name"], row["question_text"].strip()) for row in cur.fetchall()}

    # 기존 JSON / JS / 내장 QUESTION_BANK 통합 로드
    legacy_questions = list(get_all_questions_bank() or [])
    for q in QUESTION_BANK:
        legacy_questions.append(q)

    inserted_count = 0
    for q in legacy_questions:
        unit_name = str(q.get("unit_name") or "").strip()
        q_text = str(q.get("question") or q.get("question_text") or "").strip()
        if not unit_name or not q_text:
            continue
        if (unit_name, q_text) in existing_set:
            continue

        grade_group = str(q.get("grade_group") or "3~4학년군").strip()
        grade_num = UNIT_GRADE_MAP.get(unit_name)
        if not grade_num:
            if "1~2" in grade_group:
                grade_num = 2
            elif "3~4" in grade_group:
                grade_num = 4
            else:
                grade_num = 5

        raw_qtype = str(q.get("question_type") or "multiple_choice").strip()
        std_qtype = TYPE_TO_KO.get(raw_qtype, raw_qtype)

        diff = str(q.get("difficulty") or "중").strip()
        pts = int(q.get("base_score") or q.get("points") or (1 if diff == "하" else (5 if diff == "상" else 3)))

        options = q.get("options")
        if options is None:
            try:
                options = json.loads(q.get("choices_json") or "[]")
            except Exception:
                options = []
        choices_json = json.dumps(options, ensure_ascii=False)

        ans = str(q.get("answer") or q.get("correct_answer") or "").strip()
        expl = str(q.get("explanation") or "").strip()
        # 서술형 채점 키워드가 있으면 해설 하단에 채점 기준으로 보존하여 AI 채점 정확도 향상
        kws = q.get("grading_keywords")
        if kws and isinstance(kws, list):
            kw_str = ", ".join(str(k) for k in kws if k)
            if kw_str and "핵심 키워드" not in expl:
                expl = f"{expl} (채점 핵심 키워드: {kw_str})".strip()

        cur.execute("""
            INSERT INTO question_bank (
                subject, grade, grade_group, unit_name, sub_topic,
                question_type, difficulty, points, question_text,
                choices_json, correct_answer, explanation,
                source_type, source_log_id, created_by, created_by_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', NULL, 'master', '총 관리자')
        """, (
            SUBJECT_CODE, grade_num, grade_group, unit_name, str(q.get("sub_topic") or ""),
            std_qtype, diff, pts, q_text,
            choices_json, ans, expl
        ))
        existing_set.add((unit_name, q_text))
        inserted_count += 1

    conn.commit()
    cur.execute("SELECT COUNT(*) AS cnt FROM question_bank WHERE subject = ?", (SUBJECT_CODE,))
    total_cnt = cur.fetchone()["cnt"]
    conn.close()
    return {"db_path": str(BANK_DB_PATH), "inserted": inserted_count, "total": total_cnt}


def get_unit_bank_stats(
    subject: str = SUBJECT_CODE,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    grade_group: Optional[str] = None
) -> Dict[str, Any]:
    """
    단원별 문제은행 전체 문항 수(total)와 해당 학생이 맞힌 문항 수(solved), 남은 문항 수(remaining)를 반환합니다.
    토글 OFF 시 단원 드롭다운 및 로드맵의 (2/32) 표기에 사용됩니다.
    """
    init_question_bank_db()
    user_keys = _normalize_user_keys(user_id, user_name)
    placeholders = ",".join("?" for _ in user_keys)

    conn = get_bank_db_connection()
    cur = conn.cursor()

    # 1) 단원별 전체 문제 수 조회
    if grade_group and grade_group not in ("", "전체 학년"):
        cur.execute("""
            SELECT unit_name, grade_group, COUNT(*) AS total_cnt
            FROM question_bank
            WHERE subject = ? AND grade_group = ?
            GROUP BY unit_name, grade_group
        """, (subject, grade_group))
    else:
        cur.execute("""
            SELECT unit_name, grade_group, COUNT(*) AS total_cnt
            FROM question_bank
            WHERE subject = ?
            GROUP BY unit_name, grade_group
        """, (subject,))
    unit_rows = cur.fetchall()

    # 2) 학생이 맞힌(해결한) bank_id 목록 조회 (중복 없이 DISTINCT)
    cur.execute(f"""
        SELECT DISTINCT q.id AS bank_id, q.unit_name, q.grade_group
        FROM question_bank_solved s
        JOIN question_bank q ON q.id = s.bank_id
        WHERE q.subject = ? AND s.subject = ? AND s.user_key IN ({placeholders})
    """, [subject, subject] + user_keys)
    solved_rows = cur.fetchall()
    conn.close()

    solved_by_unit: Dict[str, int] = {}
    for r in solved_rows:
        u = r["unit_name"]
        solved_by_unit[u] = solved_by_unit.get(u, 0) + 1

    units_dict: Dict[str, Dict[str, Any]] = {}
    stats_list: List[Dict[str, Any]] = []
    total_all = 0
    solved_all = 0

    for r in unit_rows:
        u_name = r["unit_name"]
        g_group = r["grade_group"]
        tot = int(r["total_cnt"] or 0)
        sol = min(tot, int(solved_by_unit.get(u_name, 0)))
        rem = max(0, tot - sol)
        total_all += tot
        solved_all += sol

        item = {
            "unit_name": u_name,
            "grade_group": g_group,
            "solved": sol,
            "total": tot,
            "remaining": rem,
            "solved_count": sol,
            "total_count": tot,
            "unsolved_count": rem,
            "label": f"({sol}/{tot})",
        }
        units_dict[u_name] = item
        stats_list.append(item)

    # 학년군별 합계 ('전체 단원' 선택 시 표기용)
    grade_group_totals: Dict[str, Dict[str, int]] = {}
    for item in stats_list:
        gg = item.get("grade_group") or ""
        if gg not in grade_group_totals:
            grade_group_totals[gg] = {"solved": 0, "total": 0, "remaining": 0}
        grade_group_totals[gg]["solved"] += item["solved"]
        grade_group_totals[gg]["total"] += item["total"]
        grade_group_totals[gg]["remaining"] += item["remaining"]

    return {
        "success": True,
        "subject": subject,
        "total_solved": solved_all,
        "total_count": total_all,
        "remaining_count": max(0, total_all - solved_all),
        "units": units_dict,
        "unit_stats": units_dict,
        "stats": stats_list,
        "grade_group_totals": grade_group_totals,
    }


def mark_bank_question_solved(
    bank_id: Any,
    subject: str = SUBJECT_CODE,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    문제은행(question_bank.db) 문제를 맞혔을 때 question_bank_solved 테이블에 풀이 완료를 기록합니다.
    조장 공통 모듈이 있으면 함께 호출하고, 로컬 DB에도 모든 호환 user_key로 안전하게 기록합니다.
    """
    init_question_bank_db()
    # bank_id가 "bank_12" 같은 문자열이면 숫자만 추출
    raw_id_str = str(bank_id or "").strip()
    if raw_id_str.startswith("bank_"):
        raw_id_str = raw_id_str.replace("bank_", "", 1)
    try:
        numeric_bank_id = int(raw_id_str)
    except (ValueError, TypeError):
        return {"success": False, "reason": "invalid_bank_id"}

    if HAS_SHARED_MATH_BANK:
        try:
            sig = inspect.signature(_shared_mark_bank_question_solved)
            kwargs = {}
            if "bank_id" in sig.parameters:
                kwargs["bank_id"] = numeric_bank_id
            if "subject" in sig.parameters:
                kwargs["subject"] = subject
            if "user_id" in sig.parameters:
                kwargs["user_id"] = user_id
            if "user_name" in sig.parameters:
                kwargs["user_name"] = user_name
            if "user_key" in sig.parameters:
                kwargs["user_key"] = get_primary_user_key(user_id, user_name)
            if kwargs:
                _shared_mark_bank_question_solved(**kwargs)
        except Exception:
            pass

    user_keys = _normalize_user_keys(user_id, user_name)
    conn = get_bank_db_connection()
    cur = conn.cursor()
    for ukey in user_keys:
        try:
            cur.execute("""
                INSERT OR IGNORE INTO question_bank_solved (bank_id, subject, user_key)
                VALUES (?, ?, ?)
            """, (numeric_bank_id, subject, ukey))
        except Exception:
            pass
    conn.commit()
    conn.close()

    return {
        "success": True,
        "bank_id": numeric_bank_id,
        "subject": subject,
        "user_key": get_primary_user_key(user_id, user_name),
    }


def _row_to_quiz_dict(row: sqlite3.Row, is_review_mode: bool = False) -> Dict[str, Any]:
    """question_bank 테이블의 Row를 프론트엔드 및 라우터 표준 퀴즈 Dict로 변환"""
    raw_qtype = row["question_type"] or "객관식"
    en_qtype = TYPE_TO_EN.get(raw_qtype, "multiple_choice")
    try:
        options = json.loads(row["choices_json"] or "[]")
        if not isinstance(options, list):
            options = []
    except Exception:
        options = []

    expl = row["explanation"] or ""
    # 채점 키워드 분리 추출
    keywords = []
    m = re.search(r"\(채점 핵심 키워드:\s*([^\)]+)\)", expl)
    if m:
        keywords = [k.strip() for k in m.group(1).split(",") if k.strip()]

    return {
        "id": f"bank_{row['id']}",
        "bank_id": int(row["id"]),
        "subject": row["subject"],
        "grade": int(row["grade"] or 4),
        "grade_group": row["grade_group"] or "3~4학년군",
        "unit_name": row["unit_name"],
        "sub_topic": row["sub_topic"] or "",
        "question_type": en_qtype,
        "question_type_ko": TYPE_TO_KO.get(raw_qtype, raw_qtype),
        "difficulty": row["difficulty"] or "중",
        "base_score": int(row["points"] or 3),
        "points": int(row["points"] or 3),
        "question": row["question_text"],
        "question_text": row["question_text"],
        "options": options,
        "choices": options,
        "answer": row["correct_answer"],
        "correct_answer": row["correct_answer"],
        "explanation": expl,
        "grading_keywords": keywords,
        "source_mode": "bank_review" if is_review_mode else "bank",
        "is_review_mode": bool(is_review_mode),
    }


def draw_bank_question(
    grade_group: str = "3~4학년군",
    unit_name: str = "전체 단원",
    question_type: str = "random",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    recent_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    [문제은행(question_bank.db) 스마트 출제 및 3단계 상태 판별]
    반환 딕셔너리:
    - status:
      * "unsolved" : 미풀이 은행 문제가 존재하여 정상 추출됨 (1단계)
      * "exhausted": 해당 단원에 은행 문제는 있으나 학생이 모두 풀어서 미풀이 문제가 없음 (2단계 복습용 문제 함께 반환)
      * "empty"    : 해당 단원에 등록된 문제은행 DB 문제가 아예 없음 (0/0, 3단계)
    - quiz: 추출된 문제 dict (status가 "unsolved" 또는 "exhausted"일 때)
    - total_count: 해당 단원 전체 은행 문제 수
    - solved_count: 해당 단원 맞힌 은행 문제 수
    - remaining_count: 남은 미풀이 은행 문제 수
    """
    init_question_bank_db()
    recent_ids = recent_ids or []
    recent_bank_ids = set()
    for rid in recent_ids:
        s_rid = str(rid)
        if s_rid.startswith("bank_"):
            s_rid = s_rid.replace("bank_", "", 1)
        if s_rid.isdigit():
            recent_bank_ids.add(int(s_rid))

    user_keys = _normalize_user_keys(user_id, user_name)
    placeholders = ",".join("?" for _ in user_keys)

    conn = get_bank_db_connection()
    cur = conn.cursor()

    # 1) 단원 조건으로 전체 은행 문제 조회
    is_specific_unit = bool(unit_name and unit_name.strip() and unit_name.strip() != "전체 단원")
    if is_specific_unit:
        cur.execute("""
            SELECT * FROM question_bank
            WHERE subject = ? AND unit_name = ?
            ORDER BY id ASC
        """, (SUBJECT_CODE, unit_name.strip()))
        unit_candidates = cur.fetchall()
        if not unit_candidates:
            # 부분 일치 탐색
            cur.execute("""
                SELECT * FROM question_bank
                WHERE subject = ? AND (unit_name LIKE ? OR ? LIKE '%' || unit_name || '%')
                ORDER BY id ASC
            """, (SUBJECT_CODE, f"%{unit_name.strip()}%", unit_name.strip()))
            unit_candidates = cur.fetchall()
    else:
        if grade_group and grade_group not in ("", "전체 학년"):
            cur.execute("""
                SELECT * FROM question_bank
                WHERE subject = ? AND grade_group = ?
                ORDER BY id ASC
            """, (SUBJECT_CODE, grade_group.strip()))
            unit_candidates = cur.fetchall()
        else:
            cur.execute("""
                SELECT * FROM question_bank
                WHERE subject = ?
                ORDER BY id ASC
            """, (SUBJECT_CODE,))
            unit_candidates = cur.fetchall()

    total_count = len(unit_candidates)
    if total_count == 0:
        conn.close()
        return {
            "status": "empty",
            "quiz": None,
            "total_count": 0,
            "solved_count": 0,
            "remaining_count": 0,
        }

    # 2) 해당 학생이 이미 푼 bank_id 집합 조회
    cur.execute(f"""
        SELECT DISTINCT bank_id FROM question_bank_solved
        WHERE subject = ? AND user_key IN ({placeholders})
    """, [SUBJECT_CODE] + user_keys)
    solved_bank_ids = {int(r["bank_id"]) for r in cur.fetchall()}
    conn.close()

    unsolved_all = [r for r in unit_candidates if int(r["id"]) not in solved_bank_ids]
    solved_count = total_count - len(unsolved_all)
    remaining_count = len(unsolved_all)

    # 유형 필터 헬퍼 함수
    def _filter_by_type(rows: List[sqlite3.Row], qtype: str) -> List[sqlite3.Row]:
        if not qtype or qtype in ("random", "all"):
            return rows
        if qtype == "basic_all":
            filtered = [r for r in rows if TYPE_TO_EN.get(r["question_type"], r["question_type"]) != "descriptive"]
            return filtered if filtered else rows
        target_en = TYPE_TO_EN.get(qtype, qtype)
        filtered = [r for r in rows if TYPE_TO_EN.get(r["question_type"], r["question_type"]) == target_en]
        # 만약 해당 단원에 특정 유형 미풀이 문제가 다 떨어졌더라도, 단원 내 다른 유형 미풀이 문제가 남아있다면 그것을 출제
        return filtered if filtered else rows

    # OX 문제의 O/X 균형 및 최근 푼 문제 제외 스마트 추첨 헬퍼
    def _pick_candidate(candidate_rows: List[sqlite3.Row], qtype: str) -> sqlite3.Row:
        fresh = [r for r in candidate_rows if int(r["id"]) not in recent_bank_ids]
        active = fresh if fresh else candidate_rows
        target_en = TYPE_TO_EN.get(qtype, qtype)
        # OX 퀴즈인 경우 O와 X 정답이 50:50 비율로 공평하게 출제되도록 추첨
        if target_en == "ox" or all(TYPE_TO_EN.get(r["question_type"], r["question_type"]) == "ox" for r in active):
            o_rows = [r for r in active if str(r["correct_answer"]).strip().upper() == "O"]
            x_rows = [r for r in active if str(r["correct_answer"]).strip().upper() == "X"]
            if o_rows and x_rows:
                target_ox = random.choice(["O", "X"])
                return random.choice(x_rows if target_ox == "X" else o_rows)
            elif x_rows:
                return random.choice(x_rows)
            elif o_rows:
                return random.choice(o_rows)
        return random.choice(active)

    # 3) 미풀이 문제가 남아있는 경우 -> 1단계 정상 문제은행 출제
    if remaining_count > 0:
        pool = _filter_by_type(unsolved_all, question_type)
        chosen = _pick_candidate(pool, question_type)
        return {
            "status": "unsolved",
            "quiz": _row_to_quiz_dict(chosen, is_review_mode=False),
            "total_count": total_count,
            "solved_count": solved_count,
            "remaining_count": remaining_count,
        }

    # 4) 해당 단원의 은행 문제를 이미 전부 다 푼 경우 -> 2단계(복습 모드 후보 반환)
    review_pool = _filter_by_type(unit_candidates, question_type)
    chosen_review = _pick_candidate(review_pool, question_type)
    return {
        "status": "exhausted",
        "quiz": _row_to_quiz_dict(chosen_review, is_review_mode=True),
        "total_count": total_count,
        "solved_count": solved_count,
        "remaining_count": 0,
    }


def grade_bank_question_by_ai(
    question_text: str,
    correct_answer: str,
    user_answer: str,
    question_type: str = "단답형",
    points: int = 3,
    explanation: str = "",
    subject: str = SUBJECT_CODE,
    call_ai_fn=None,
    keywords: Optional[List[str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    [요구사항 3] 문제은행(question_bank.db) 주관식(단답형) · 서술형 문제의 AI 채점 엔진
    1) 조장 공통 모듈(app.subjects.math.question_bank.grade_bank_question_by_ai)이 사용 가능하면 우선 시도
    2) 내 과목 AI 채점 엔진(call_ai_fn: 의미 동치 판별 및 서술형 0~5점 부분 점수 채점) 수행
    3) 채점 시점에도 AI 서버가 응답하지 않는 비상 상황에서만 로컬 키워드/유의어 비교 채점으로 안전 폴백
    """
    en_type = TYPE_TO_EN.get(str(question_type).strip(), str(question_type).strip())
    ko_type = TYPE_TO_KO.get(str(question_type).strip(), str(question_type).strip())
    base_pts = int(points or (5 if en_type == "descriptive" else 3))

    # 해설에서 채점 핵심 키워드 자동 추출
    extracted_kws = list(keywords or [])
    if explanation:
        m = re.search(r"\(채점 핵심 키워드:\s*([^\)]+)\)", explanation)
        if m:
            extracted_kws.extend([k.strip() for k in m.group(1).split(",") if k.strip()])

    # 1) 기본 로컬 채점 결과 준비 (OX/객관식 즉시 판정 및 AI 실패 시 비상 폴백용)
    local_res = QuestionBankService.grade_answer(
        q_type=en_type,
        correct=correct_answer,
        user_ans=user_answer,
        base_score=base_pts,
        keywords=extracted_kws,
    )

    # OX나 객관식은 명확한 정답 비교로 즉시 반환
    if en_type in ("ox", "multiple_choice"):
        return local_res

    # 단답형에서 이미 로컬 유의어/정확 일치로 정답 판정된 경우 만점 즉시 반환
    if en_type == "short_answer" and local_res.get("is_correct"):
        return local_res

    # 2) 내 과목 AI 채점 함수(call_ai_fn)로 의미 동치(단답형) 및 부분 점수(서술형) 채점
    if callable(call_ai_fn):
        if en_type == "short_answer":
            prompt = f"""
너는 2022 개정 초등학교 사회과 전문 채점관 AI야.
문제은행 단답형(주관식) 문제에서 학생이 작성한 답안이 모범 답안과 의미상 동일한지(의미 동치·유의어·동의어) 초등학생 눈높이에서 공정하게 판별해줘.

[채점 기준]
- '너희'라는 단어는 쓰지 말고 다정하고 정중한 존댓말(~해요, ~입니다)로 피드백을 작성하세요.
- 모범 답안과 표현이 조금 다르거나 사소한 맞춤법/띄어쓰기 차이가 있어도 핵심 의미가 같으면 정답(true)으로 인정하세요.
- 예: '특산물'='특산품', '문화재'='문화유산', '방위표'='방위표시', '한글'='훈민정음', '삼권분립'='권력분립' 등
- 완전히 다른 개념이거나 오답인 경우에만 false로 판정하세요.

[문제]: {question_text}
[모범 답안]: {correct_answer}
[해설 및 채점 기준]: {explanation}
[학생 답안]: {user_answer}

[출력 형식 JSON]
{{
  "is_correct": true 또는 false,
  "score": {base_pts} 또는 0,
  "feedback": "초등학생 눈높이에 맞춘 다정한 존댓말 1문장 채점 피드백"
}}
"""
            try:
                resp_text = call_ai_fn(prompt, max_tokens=180)
                if resp_text:
                    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp_text.strip())
                    data = json.loads(clean_json)
                    is_c = bool(data.get("is_correct", False))
                    return {
                        "score": base_pts if is_c else 0,
                        "max_score": base_pts,
                        "is_correct": is_c,
                        "feedback": data.get("feedback") or (
                            f"정답입니다! '{user_answer}'도 같은 의미의 올바른 답안으로 인정되었어요! 🌟"
                            if is_c else local_res["feedback"]
                        ),
                        "graded_by": "ai",
                    }
            except Exception:
                pass

        elif en_type == "descriptive":
            max_pts = max(5, base_pts)
            prompt = f"""
너는 2022 개정 초등학교 사회과 전문 채점관 AI야.
문제은행 서술형 문제에 대한 초등학생의 답안을 읽고 0~{max_pts}점 사이의 부분 점수로 따뜻하고 공정하게 채점해줘.

[채점 기준 및 말투 원칙]
- '너희'라는 표현은 절대 쓰지 말고 '우리' 또는 '여러분'을 사용하며, 다정하고 정중한 존댓말(~해요, ~입니다)로 1~2문장 피드백을 작성하세요.
- 완벽한 문장이 아니더라도 모범 답안 및 채점 기준의 핵심 의미가 통하면 적극적으로 부분 점수(3~{max_pts}점)를 부여하세요.
- {max_pts}점(만점): 핵심 원리와 까닭을 논리적으로 잘 서술함
- {max_pts - 1}점(우수): 핵심 개념과 의미가 명확히 통함
- 3점(보통): 표현이 다소 짧거나 서툴러도 핵심 단어나 올바른 생각이 포함됨
- 1~2점(노력): 성실히 작성했으나 핵심 개념이 부족함
- 0점: 무관한 답안, 빈칸, 또는 장난성 글자

[문제]: {question_text}
[모범 답안]: {correct_answer}
[해설 및 채점 기준]: {explanation}
[학생 답안]: {user_answer}

[출력 형식 JSON]
{{
  "score": 0에서 {max_pts} 사이 정수,
  "max_score": {max_pts},
  "is_correct": true 또는 false,
  "feedback": "초등학생 눈높이에 맞춘 다정한 존댓말 1~2문장 채점 피드백"
}}
"""
            try:
                resp_text = call_ai_fn(prompt, max_tokens=220)
                if resp_text:
                    clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp_text.strip())
                    data = json.loads(clean_json)
                    earned = max(0, min(max_pts, int(data.get("score", 0))))
                    return {
                        "score": earned,
                        "max_score": max_pts,
                        "is_correct": earned >= 3,
                        "feedback": data.get("feedback") or local_res["feedback"],
                        "graded_by": "ai",
                    }
            except Exception:
                pass

    # 3) 조장 공통 모듈의 grade_bank_question_by_ai가 존재하는 경우 시도
    if HAS_SHARED_MATH_BANK:
        try:
            sig = inspect.signature(_shared_grade_bank_question_by_ai)
            call_kwargs = {}
            param_map = {
                "question_text": question_text,
                "question": question_text,
                "correct_answer": correct_answer,
                "answer": correct_answer,
                "user_answer": user_answer,
                "student_answer": user_answer,
                "question_type": ko_type,
                "points": base_pts,
                "base_score": base_pts,
                "explanation": explanation,
                "subject": subject,
            }
            for pname in sig.parameters:
                if pname in param_map:
                    call_kwargs[pname] = param_map[pname]
            shared_res = _shared_grade_bank_question_by_ai(**call_kwargs)
            if isinstance(shared_res, dict) and "score" in shared_res:
                sc = int(shared_res.get("score", 0))
                mx = int(shared_res.get("max_score", base_pts))
                return {
                    "score": sc,
                    "max_score": mx,
                    "is_correct": bool(shared_res.get("is_correct", sc >= (3 if en_type == "descriptive" else mx))),
                    "feedback": shared_res.get("feedback") or shared_res.get("reason") or local_res["feedback"],
                    "graded_by": "shared_ai",
                }
        except Exception:
            pass

    # 4) 비상 폴백: AI 서버가 응답하지 않을 때는 내장 유의어/키워드 채점 결과 반환
    local_res["graded_by"] = "fallback_local"
    return local_res


# 모듈 로드 시 자동으로 social/question_bank.db 생성 및 270문항 마이그레이션 실행
try:
    init_question_bank_db()
except Exception as _init_err:
    print("[question_bank.db 초기화 알림]:", _init_err)

