import re
from pathlib import Path
from typing import Dict, List, Any


CURRICULUM_FILE = Path(__file__).resolve().parent / "curriculum.txt"


def get_grade_group(grade: int) -> str:
    """학년 숫자를 학년군 문자열로 변환"""
    if grade in [1, 2]:
        return "1~2학년군"
    elif grade in [3, 4]:
        return "3~4학년군"
    elif grade in [5, 6]:
        return "5~6학년군"
    return "3~4학년군"  # 기본값


def parse_curriculum_data() -> Dict[str, Any]:
    """
    curriculum.txt를 파싱하여 학년군 -> 대단원 -> 세부주제 계층형 딕셔너리로 반환
    반환 구조:
    {
        "1~2학년군": {
            "(1) 수와 연산": [
                {"title": "네 자리 이하의 수", "detail": "0과 100까지의 수 개념 이해 및 읽기/쓰기..."},
                ...
            ],
            ...
        },
        ...
    }
    """
    if not CURRICULUM_FILE.exists():
        return {}

    with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    result: Dict[str, Dict[str, List[Dict[str, str]]]] = {
        "1~2학년군": {},
        "3~4학년군": {},
        "5~6학년군": {},
    }

    current_group = ""
    current_unit = ""

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.startswith("-"):
            # 구분선 건너뛰기 (단, 세부주제 '-'는 제외)
            if not line.startswith("- "):
                continue

        # 1. 학년군 태그 감지: [1~2학년군], [3~4학년군], [5~6학년군]
        group_match = re.match(r"^\[([1-6]~[1-6]학년군)\]", line)
        if group_match:
            current_group = group_match.group(1)
            current_unit = ""
            continue

        # 2. 대단원 감지: (1) 수와 연산, (2) 변화와 관계 등
        unit_match = re.match(r"^\(\d+\)\s*(.+)$", line)
        if unit_match and current_group in result:
            current_unit = line  # 예: "(1) 수와 연산"
            if current_unit not in result[current_group]:
                result[current_group][current_unit] = []
            continue

        # 3. 세부 주제 감지: - 네 자리 이하의 수: 0과 100까지의...
        if line.startswith("- ") and current_group and current_unit:
            topic_raw = line[2:].strip()
            if ":" in topic_raw:
                topic_title, topic_detail = topic_raw.split(":", 1)
                result[current_group][current_unit].append({
                    "title": topic_title.strip(),
                    "detail": topic_detail.strip()
                })
            else:
                result[current_group][current_unit].append({
                    "title": topic_raw,
                    "detail": topic_raw
                })

    return result


def get_sliced_curriculum_text(grade_group: str) -> str:
    """
    지정된 학년군 파트만 curriculum.txt에서 슬라이싱 추출하여 프롬프트 토큰 절약
    """
    if not CURRICULUM_FILE.exists():
        return ""

    with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 정규식으로 해당 학년군 블록만 추출
    pattern = rf"\[{re.escape(grade_group)}\](.*?)(?=\n\[\d~\d학년군\]|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return f"[{grade_group}]\n" + match.group(1).strip()
    return content  # 매칭 실패 시 전체 폴백


def get_curriculum_tree_for_ui() -> Dict[str, Any]:
    """
    프론트엔드 드롭다운(동적 셀렉트박스) 바인딩용 가공 데이터
    {
        "1~2학년군": {
            "(1) 수와 연산": ["네 자리 이하의 수", "두 자리 수 범위의 덧셈과 뺄셈", "한 자리 수의 곱셈"],
            ...
        }
    }
    """
    full_data = parse_curriculum_data()
    ui_tree: Dict[str, Dict[str, List[str]]] = {}

    for group, units in full_data.items():
        ui_tree[group] = {}
        for unit, topics in units.items():
            ui_tree[group][unit] = [t["title"] for t in topics]

    return ui_tree
