import os
import re
import time
import json
import random
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from google import genai

try:
    from .curriculum_parser import (
        get_grade_group,
        get_sliced_curriculum_text,
        parse_curriculum_data,
    )
except ImportError:
    from curriculum_parser import (
        get_grade_group,
        get_sliced_curriculum_text,
        parse_curriculum_data,
    )

# ---------------------------------------------------------------------------
# 1. API 키 다중 폴백 로더 (guideline.txt 261008 표준: .env -> 상위 .env -> 시스템 환경변수)
# ---------------------------------------------------------------------------
current_dir = Path(__file__).resolve().parent

def _load_env_hierarchy():
    # 1단계: 현재 과목 폴더의 .env 확인
    if (current_dir / ".env").exists():
        load_dotenv(dotenv_path=current_dir / ".env", override=True)
        return
    # 2단계: 상위 부모 폴더(프로젝트 루트) 순차 탐색
    for parent in current_dir.parents:
        if (parent / ".env").exists():
            load_dotenv(dotenv_path=parent / ".env", override=True)
            return
    # 3단계: 기본 load_dotenv
    load_dotenv(override=True)

_load_env_hierarchy()


def get_genai_client() -> genai.Client:
    """guideline.txt 표준 규격: Google GenAI SDK v1 클라이언트 생성"""
    # 1) .env 및 환경변수에서 1차 확인
    key = os.getenv("GEMINI_API_KEY")
    # 2) 없으면 상위 부모 .env 재순회
    if not key:
        _load_env_hierarchy()
        key = os.getenv("GEMINI_API_KEY")
    # 3) OS 시스템 환경변수 직접 조회
    if not key:
        key = os.environ.get("GEMINI_API_KEY")
    # 4) 미설정 시 직관적인 한글 에러
    if not key or not str(key).strip():
        raise ValueError(
            "GEMINI_API_KEY가 설정되지 않았습니다. 프로젝트 루트의 .env 파일이나 시스템 환경변수를 확인하세요."
        )
    return genai.Client(api_key=str(key).strip(), http_options={"api_version": "v1"})


# 가이드라인 절대 원칙: 무조건 3.5 라이트 단일 모델만 사용
MODEL_NAME = "gemini-3.5-flash-lite"

# 난이도별 배점 기준 (guideline.txt 및 조장 기획안)
DIFFICULTY_SCORES = {
    "하": 1,
    "중": 3,
    "상": 5,
}

QUESTION_TYPES = ["ox", "객관식", "단답형", "서술형", "단답형 주관식 2"]

# 난이도별 허용 문제 유형 & 문제 유형별 허용 난이도 규칙
# - OX 퀴즈: 하(1점)만 가능 (3점, 5점 절대 제외)
# - 서술형: 중(3점), 상(5점)만 가능 (1점 절대 제외)
# - 객관식, 단답형, 단답형 주관식 2: 하(1점), 중(3점), 상(5점) 모두 가능
ALLOWED_TYPES_BY_DIFF = {
    "하": ["ox", "객관식", "단답형", "단답형 주관식 2"],
    "중": ["객관식", "단답형", "서술형", "단답형 주관식 2"],
    "상": ["객관식", "단답형", "서술형", "단답형 주관식 2"],
}

ALLOWED_DIFFS_BY_TYPE = {
    "ox": ["하"],
    "객관식": ["하", "중", "상"],
    "단답형": ["하", "중", "상"],
    "서술형": ["중", "상"],
    "단답형 주관식 2": ["하", "중", "상"],
}


def _escape_newlines_in_json_strings(text: str) -> str:
    """JSON 문자열("") 내부에 이스케이프되지 않은 실제 줄바꿈(\n, \r)이나 탭(\t)이 있으면 안전하게 치환합니다."""
    out = []
    in_str = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str:
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                continue
            if ch == "\t":
                out.append(" ")
                continue
        out.append(ch)
    return "".join(out)


def _clean_json_text(raw_text: str) -> str:
    """
    마크다운 코드블록 제거, 후행 쉼표(trailing comma) 제거, 주석 제거 및
    JSON 내부 LaTeX 역슬래시(\\)로 인한 파싱 에러를 100% 원천 차단하는 전처리기
    """
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # 0단계: 문자열 밖의 // 주석 제거 및 문자열 내부 생(raw) 줄바꿈 보호
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    text = _escape_newlines_in_json_strings(text)

    # 1단계: JSON 제어문자(\f, \t, \b, \r, \n)와 앞글자가 겹치는 모든 LaTeX 명령어를 이중 역슬래시(\\)로 선제 보호
    latex_conflict_cmds = (
        r"frac|times|text|triangle|theta|to|tan|tau|textbf|textit|"
        r"boxed|begin|bar|beta|binom|big|Big|"
        r"right|rho|rangle|"
        r"neq|nabla|natural|not|nu"
    )
    text = re.sub(rf"(?<!\\)\\({latex_conflict_cmds})", r"\\\\\1", text)

    # 2단계: 표준 JSON 이스케이프(\", \\, \/, \b, \f, \n, \r, \t, \uXXXX)가 아닌
    # 모든 단일 역슬래시를 자동으로 \\ 로 변환하여 Invalid \escape 에러를 0%로 차단
    text = re.sub(r'(?<!\\)\\(?![/\"\\bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", text)

    # 3단계: AI가 배열이나 객체의 마지막 항목 뒤에 실수로 붙인 후행 쉼표(trailing comma: , } 또는 , ]) 제거!
    # ('Expecting property name enclosed in double quotes' 오류의 제1원인)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


def _call_gemini_json(prompt: str, temperature: float = 0.6) -> Dict[str, Any]:
    """
    guideline.txt 표준: gemini-3.5-flash-lite (api_version: v1) 호출 후 안전하게 JSON 파싱
    (일시적 JSON 문법 깨짐 발생 시 자동 복구 및 최대 2회 재시도)
    """
    import ast

    client = get_genai_client()
    last_err = None
    for attempt in range(2):
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"temperature": temperature if attempt == 0 else max(0.3, temperature - 0.15)},
        )
        cleaned = _clean_json_text(response.text)
        try:
            return json.loads(cleaned)
        except Exception as e:
            last_err = e
            # 작은따옴표(') 키/값 또는 파이썬 리터럴 형태로 출력된 경우 2차 복구 시도
            try:
                fallback_str = re.sub(r"\btrue\b", "True", cleaned)
                fallback_str = re.sub(r"\bfalse\b", "False", fallback_str)
                fallback_str = re.sub(r"\bnull\b", "None", fallback_str)
                parsed = ast.literal_eval(fallback_str)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    raise last_err


def _ensure_latex_wrapped(val: str) -> str:
    """
    56\\frac{1}{4}\\text{m}^2 처럼 $ 기호 없이 날것으로 온 LaTeX 수식 문자열을
    KaTeX가 완벽히 렌더링할 수 있도록 $...$로 감싸주는 후처리 함수
    """
    if not isinstance(val, str):
        return str(val)
    s = val.strip()
    if not s:
        return s
    # 이미 $ 기호가 있으면 그대로 유지
    if "$" in s or "\\(" in s or "\\[" in s:
        return s
    # LaTeX 명령어나 지수(^)가 포함되어 있는데 $가 아예 없는 경우 전체 또는 수식 블록을 $로 감쌈
    if re.search(r"\\(?:frac|text|sqrt|times|div|cdot|le|ge|neq)|\^\d", s):
        return f"${s}$"
    return s


def _clean_display_text(val: str) -> str:
    """
    AI가 지문(question)이나 해설(solution)에 실수로 섞어 보낸
    리터럴 \\n 개행문자, HTML 태그(<br>), 마크다운 볼드(**), 한글 대괄호 수식 오인(\\[한글\\]),
    수식 밖의 \\quad 등을 깔끔하게 정화합니다.
    """
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    s = val
    # 0) LaTeX 명령어(\neq, \not, \nu, \nabla 등: 뒤에 영문자가 옴)가 아닌 리터럴 \n, \r 문자열을 실제 줄바꿈으로 변환!
    s = re.sub(r"\\r(?![a-zA-Z])", "", s)
    s = re.sub(r"\\n(?![a-zA-Z])", "\n", s)
    # 1) <br>, <br/>, <br /> 태그를 실제 줄바꿈(\n)으로 변환
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    # 2) 마크다운 강조(**텍스트**) 기호 제거
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    # 3) 한글이 포함된 \[ ... \] 가 KaTeX 수식 박스로 중복 렌더링되는 현상 방지
    s = re.sub(r"\\\[([^\[\]]*[가-힣][^\[\]]*)\\\]", r"[\1]", s)
    # 4) 수식 밖에서 쓰인 \quad, \qquad 를 공백으로 치환
    if "$" not in s:
        s = re.sub(r"\\q?quad\b\s*", "   ", s)
    else:
        parts = s.split("$")
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"\\q?quad\b\s*", "   ", parts[i])
        s = "$".join(parts)
    return s.strip()


def _has_solution_contradiction(sol_text: str, q_text: str = "", visual_data: Optional[Dict[str, Any]] = None) -> bool:
    """
    1) 해설(solution) 내부에 AI가 계산 착오를 일으켜 당황하며 남긴 자기모순/정정 문구가 있는지 감지합니다.
    2) 문제 지문(question + visual_data)의 조건 수치(예: 전체 40명, 6명)와 해설(solution)에서 전제로 쓰는 수치가
       서로 다른 '수치 말바꾸기(예: 지문은 40명인데 해설은 전체 50명)' 현상을 파이썬으로 즉시 적발합니다!
    """
    if not sol_text:
        return False
    panic_patterns = [
        r"다시\s*계산",
        r"아,\s*잠깐",
        r"잠시만요",
        r"정정\s*:",
        r"정정합니다",
        r"오류가\s*생깁니다",
        r"지문을\s*수정할\s*수\s*없",
        r"해설\s*재작성",
        r"올바른\s*해설\s*재작성",
        r"원칙\s*2에\s*따라",
        r"아닙니다\.\s*다시",
    ]
    for pat in panic_patterns:
        if re.search(pat, sol_text):
            return True

    # 지문+표에 등장하는 숫자 집합 추출
    if q_text:
        combined_q = q_text + " " + json.dumps(visual_data or {}, ensure_ascii=False)
        q_nums = set(re.findall(r"\d+(?:\.\d+)?", combined_q))
        # 해설에서 '전체 학생 50명', '50명의 20%', '학생은 7명이므로' 처럼 문제의 기본 전제 조건으로 쓰인 숫자가
        # 지문(q_nums)에 아예 없는 숫자인지 검사
        premise_matches = re.findall(
            r"(?:전체\s*(?:학생\s*)?|학생\s*(?:수는?\s*)?|학생은\s*)(\d+)\s*명(?:의|에서|이므로|입니다|일\s*때)",
            sol_text,
        )
        for p_num in premise_matches:
            if p_num not in q_nums:
                return True

    return False


def _has_floating_block(v_raw: Any) -> bool:
    """쌓기나무 층별 모양(1층, 2층, 3층)에서 아래층이 비어있는데 위층에 블록이 존재하는 물리적 오류(허공 블록) 감지"""
    if not isinstance(v_raw, list):
        return False
    floor_grids = []
    for item in v_raw:
        if isinstance(item, dict) and item.get("type") == "grid":
            title = str(item.get("title", ""))
            rows = item.get("rows", [])
            if "층" in title and isinstance(rows, list):
                floor_grids.append((title, rows))
    if len(floor_grids) < 2:
        return False

    def _is_filled(val):
        s = str(val).strip()
        return s not in ["", "0", "None", "False"]

    for i in range(1, len(floor_grids)):
        lower_rows = floor_grids[i - 1][1]
        upper_rows = floor_grids[i][1]
        for r_idx in range(len(upper_rows)):
            if r_idx >= len(lower_rows):
                continue
            u_row = upper_rows[r_idx]
            l_row = lower_rows[r_idx]
            if isinstance(u_row, list) and isinstance(l_row, list):
                for c_idx in range(len(u_row)):
                    if c_idx >= len(l_row):
                        continue
                    if _is_filled(u_row[c_idx]) and not _is_filled(l_row[c_idx]):
                        return True
    return False


def _fix_floating_blocks(v_raw: Any) -> Any:
    """층별 쌓기나무에서 위층에 블록이 있는데 아래층이 비어있는 경우 아래층을 자동으로 채워 중력 법칙 보장"""
    if not isinstance(v_raw, list):
        return v_raw
    floor_grids = []
    for item in v_raw:
        if isinstance(item, dict) and item.get("type") == "grid":
            title = str(item.get("title", ""))
            rows = item.get("rows", [])
            if "층" in title and isinstance(rows, list):
                floor_grids.append(item)
    if len(floor_grids) < 2:
        return v_raw

    def _is_filled(val):
        s = str(val).strip()
        return s not in ["", "0", "None", "False"]

    for i in range(len(floor_grids) - 1, 0, -1):
        upper_rows = floor_grids[i].get("rows", [])
        lower_rows = floor_grids[i - 1].get("rows", [])
        for r_idx in range(len(upper_rows)):
            if r_idx < len(lower_rows) and isinstance(upper_rows[r_idx], list) and isinstance(lower_rows[r_idx], list):
                for c_idx in range(len(upper_rows[r_idx])):
                    if c_idx < len(lower_rows[r_idx]):
                        if _is_filled(upper_rows[r_idx][c_idx]) and not _is_filled(lower_rows[r_idx][c_idx]):
                            lower_rows[r_idx][c_idx] = "1"
    return v_raw


def _sanitize_spatial_visual_data(v_raw: Any) -> Any:
    """
    1) 층별 모양(1층, 2층, 3층) 그리드에 2 이상의 숫자가 들어가 정답을 스포일러하거나 혼란을 주는 현상을 원천 방지!
       - 층별 모양 그리드는 오직 '1'(블록 있음)과 ''(빈칸)만 유지합니다.
    2) 허공 블록(중력 법칙 위배)을 자동으로 보정합니다.
    """
    if isinstance(v_raw, list):
        for item in v_raw:
            if isinstance(item, dict) and item.get("type") == "grid":
                title = str(item.get("title", ""))
                if "층" in title:
                    rows = item.get("rows", [])
                    new_rows = []
                    for row in rows:
                        if isinstance(row, list):
                            new_row = ["1" if str(c).strip() not in ["", "0", "None", "False"] else "" for c in row]
                            new_rows.append(new_row)
                    item["rows"] = new_rows
        return _fix_floating_blocks(v_raw)
    return v_raw


def _generate_spatial_blocks_quiz(
    quiz_id: str,
    actual_grade: int,
    actual_grade_group: str,
    target_unit: str,
    target_topic: str,
    target_difficulty: str,
    score: int,
    target_question_type: str,
    random_seed_num: int,
) -> Dict[str, Any]:
    """
    [초등수학 공간 감각 / 쌓기나무 전용 온디맨드 퀴즈 출제 파이프라인]
    일반 연산/분수 프롬프트와 완전히 분리하여 다음 4대 공간추론 유형을 무결점 수학 규칙으로 출제:
    1. [단답형 주관식 2]: 위에서 본 모양에 수를 쓴 모양 -> 모눈종이 클릭 색칠하기 (앞/옆 모양)
    2. [객관식 미니 그리드]: 위에서 본 모양에 수를 쓴 모양 -> 앞/옆 모양 4지선다 미니 그리드
    3. [3방향 투영도 (위/앞/옆)]: 블록 유무만 표시된 투영도를 보고 총 개수 또는 최대·최소 개수 추론
    4. [층별 모양 (1층/2층/3층)]: 허공 블록(중력 법칙 위배) 0% 보장 및 숫자 스포일러 없이 총 개수 구하기
    """
    rng = random.Random(random_seed_num + int(time.time() * 1000) % 100000)

    # 템플릿 결정
    if target_question_type == "단답형 주관식 2":
        template = "coloring"
    elif target_question_type == "객관식":
        template = rng.choice(["projection_mc", "3view_mc", "floor_layers_mc"])
    elif target_question_type == "ox":
        template = "ox_concept"
    elif target_question_type in ["단답형", "서술형"]:
        template = rng.choice(["3view", "floor_layers"])
    else:
        template = rng.choice(["coloring", "projection_mc", "3view", "floor_layers"])

    # 바둑판 크기 다양화 (2x2, 2x3, 3x2, 3x3)
    grid_dim = rng.choice([(2, 2), (2, 3), (3, 2), (3, 3)])
    R, C = grid_dim

    # -----------------------------------------------------------------------
    # 1. [단답형 주관식 2] 모눈종이 클릭 색칠하기
    # -----------------------------------------------------------------------
    if template == "coloring":
        M = [[rng.choice([1, 2, 3]) if rng.random() > 0.3 else 0 for _ in range(C)] for _ in range(R)]
        if sum(1 for r in M for c in r if c > 0) < 2:
            M[0][0] = 2
            M[-1][-1] = 1
        if max(c for r in M for c in r) < 2:
            M[0][0] = 2

        # 1) 앞에서 본 모양 계산 (각 열별 최댓값)
        col_heights = [max(M[r][c] for r in range(R)) for c in range(C)]
        W_f = C
        H_max_f = max(col_heights)
        ans_matrix_f = [[1 if col_heights[c] >= (H_max_f - f) else 0 for c in range(W_f)] for f in range(H_max_f)]
        col_desc_f = ", ".join([f"{c+1}번째 줄(왼쪽부터): {col_heights[c]}층" for c in range(W_f)])

        # 2) 옆(오른쪽)에서 본 모양 계산 (각 행별 최댓값, 초등 약속: 왼쪽=앞줄, 오른쪽=뒷줄)
        row_heights = [max(M[r][c] for c in range(C)) for r in reversed(range(R))]
        W_s = R
        H_max_s = max(row_heights)
        ans_matrix_s = [[1 if row_heights[i] >= (H_max_s - f) else 0 for i in range(W_s)] for f in range(H_max_s)]
        row_labels = ["앞줄(1열)", "가운데줄(2열)", "뒷줄(3열)"] if R == 3 else ["앞줄(1열)", "뒷줄(2열)"]
        col_desc_s = ", ".join([f"{row_labels[i]}: {row_heights[i]}층" for i in range(W_s)])

        vis_grid = {
            "type": "grid",
            "title": "위에서 본 모양에 수를 쓴 모양",
            "rows": [[str(c) if c > 0 else "" for c in r] for r in M],
            "footer": "앞",
        }

        # 난이도 '상'(5점)일 때 2개 모눈종이(앞, 옆) 동시 색칠 출제! (난이도 상향)
        if target_difficulty == "상":
            ans_payload = {
                "multi": True,
                "grids": [
                    {
                        "id": "front",
                        "title": "앞에서 본 모양",
                        "direction_footer": "왼쪽 ◀ ▶ 오른쪽",
                        "matrix": ans_matrix_f,
                    },
                    {
                        "id": "side",
                        "title": "옆(오른쪽)에서 본 모양",
                        "direction_footer": "앞 ◀ ▶ 뒤",
                        "matrix": ans_matrix_s,
                    },
                ],
            }
            sol = (
                f"위에서 본 모양에 적힌 수를 바탕으로 앞과 옆에서 바라볼 때 보이는 모양을 각각 구합니다:\n"
                f"1. **앞에서 본 모양**: 왼쪽 줄부터 오른쪽 줄 순서대로 각 열의 최고 높이를 찾습니다: {col_desc_f}\n"
                f"2. **옆(오른쪽)에서 본 모양**: 초등학교 수학 약속에 따라 모눈종이의 왼쪽은 앞줄, 오른쪽은 뒷줄입니다: {col_desc_s}\n"
                f"3. 따라서 모눈종이 1에는 앞에서 본 모양, 모눈종이 2에는 옆에서 본 모양을 알맞게 색칠하면 정답이 됩니다."
            )
            return {
                "quiz_id": quiz_id,
                "grade": actual_grade,
                "grade_group": actual_grade_group,
                "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
                "topic": "공간 감각",
                "difficulty": target_difficulty,
                "score": score,
                "question_type": "단답형 주관식 2",
                "question": "그림은 쌓기나무로 쌓은 모양을 위에서 본 모양에 각 자리에 쌓인 쌓기나무의 수를 적은 것입니다. 이 쌓기나무를 **[앞에서 본 모양]**과 **[옆(오른쪽)에서 본 모양]**을 각각 아래 두 모눈종이에 알맞게 색칠하시오.",
                "visual_data": vis_grid,
                "direction_footer": "앞: 왼쪽 ◀ ▶ 오른쪽 / 옆: 앞 ◀ ▶ 뒤",
                "solution": sol,
                "calculated_answer_value": "[앞 & 옆 2개 모눈종이 색칠 완성]",
                "correct_answer": json.dumps(ans_payload, ensure_ascii=False),
                "options": [],
                "rubric": [],
                "is_multi_grid": True,
            }
        else:
            # 난이도 '하', '중'일 때 단일 방향(앞 또는 옆) 모눈종이 출제
            direction = rng.choice(["앞", "옆(오른쪽)"])
            if direction == "앞":
                ans_matrix = ans_matrix_f
                col_desc = col_desc_f
                direction_footer = "왼쪽 ◀ ▶ 오른쪽"
                direction_guide = "앞에서 바라볼 때 왼쪽 줄부터 오른쪽 줄 순서대로 각 줄의 최고 높이를 찾습니다."
            else:
                ans_matrix = ans_matrix_s
                col_desc = col_desc_s
                direction_footer = "앞 ◀ ▶ 뒤"
                direction_guide = "초등학교 수학 약속에 따라 옆(오른쪽)에서 볼 때 모눈종이의 **왼쪽은 '앞줄'**, **오른쪽은 '뒷줄'**입니다."

            sol = (
                f"위에서 본 모양에 적힌 수를 바탕으로 {direction}에서 바라볼 때 보이는 모양을 찾습니다:\n"
                f"1. {direction_guide}\n"
                f"2. 각 줄에서 가장 높이 쌓인 쌓기나무의 높이를 구합니다: {col_desc}\n"
                f"3. 따라서 바닥(1층)부터 이 높이만큼 모눈종이에 색칠하면 알맞은 모양이 완성됩니다."
            )

            return {
                "quiz_id": quiz_id,
                "grade": actual_grade,
                "grade_group": actual_grade_group,
                "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
                "topic": "공간 감각",
                "difficulty": target_difficulty,
                "score": score,
                "question_type": "단답형 주관식 2",
                "question": f"그림은 쌓기나무로 쌓은 모양을 위에서 본 모양에 각 자리에 쌓인 쌓기나무의 수를 적은 것입니다. 이 쌓기나무를 **{direction}에서** 바라보았을 때 보이는 모양을 아래 모눈종이 칸을 클릭하여 알맞게 색칠하시오.",
                "visual_data": vis_grid,
                "direction_footer": direction_footer,
                "solution": sol,
                "calculated_answer_value": json.dumps(ans_matrix),
                "correct_answer": json.dumps(ans_matrix),
                "options": [],
                "rubric": [],
                "is_multi_grid": False,
            }

    # -----------------------------------------------------------------------
    # 2. [객관식 미니 그리드] 위에서 수 쓰기 -> 앞/옆 모양 4지선다 보기
    # -----------------------------------------------------------------------
    if template == "projection_mc":
        M = [[rng.choice([1, 2, 3]) if rng.random() > 0.3 else 0 for _ in range(C)] for _ in range(R)]
        if sum(1 for r in M for c in r if c > 0) < 2:
            M[0][0] = 2
            M[-1][-1] = 1
        if max(c for r in M for c in r) < 2:
            M[0][0] = 2

        direction = rng.choice(["앞", "옆(오른쪽)"])
        if direction == "앞":
            col_heights = [max(M[r][c] for r in range(R)) for c in range(C)]
            W = C
            H_max = max(col_heights)
            ans_matrix = [[1 if col_heights[c] >= (H_max - f) else 0 for c in range(W)] for f in range(H_max)]
            col_desc = ", ".join([f"{c+1}번째 줄(왼쪽부터): {col_heights[c]}층" for c in range(W)])
            direction_footer = "왼쪽 ◀ ▶ 오른쪽"
            direction_guide = "앞에서 바라볼 때 왼쪽 줄부터 오른쪽 줄 순서대로 각 줄의 최고 높이를 찾습니다."
        else:
            # 초등수학 표준 약속: 옆(오른쪽)에서 볼 때 그림의 왼쪽이 '앞줄(r = R - 1)', 오른쪽이 '뒷줄(r = 0)'입니다!
            row_heights = [max(M[r][c] for c in range(C)) for r in reversed(range(R))]
            W = R
            H_max = max(row_heights)
            ans_matrix = [[1 if row_heights[i] >= (H_max - f) else 0 for i in range(W)] for f in range(H_max)]
            row_labels = ["앞줄(1열)", "가운데줄(2열)", "뒷줄(3열)"] if R == 3 else ["앞줄(1열)", "뒷줄(2열)"]
            col_desc = ", ".join([f"{row_labels[i]}: {row_heights[i]}층" for i in range(W)])
            direction_footer = "앞 ◀ ▶ 뒤"
            direction_guide = "초등학교 수학 약속에 따라 옆(오른쪽)에서 볼 때 모눈종이의 **왼쪽은 '앞줄'**, **오른쪽은 '뒷줄'**입니다."

        correct_rows = [["1" if c == 1 else "" for c in r] for r in ans_matrix]
        correct_opt = {"type": "grid", "title": "보기", "rows": correct_rows, "footer": direction_footer}

        # 오답 3개 생성 (대칭 변형, 높이 ±1 변형 등)
        distractors = []
        rev_rows = [r[::-1] for r in correct_rows]
        if rev_rows != correct_rows:
            distractors.append({"type": "grid", "title": "보기", "rows": rev_rows, "footer": direction_footer})

        alt_heights = list(col_heights if direction == "앞" else row_heights)
        alt_heights[0] = max(1, (alt_heights[0] % H_max) + 1)
        alt_h_max = max(H_max, max(alt_heights))
        alt_b_rows = [["1" if alt_heights[c] >= (alt_h_max - f) else "" for c in range(W)] for f in range(alt_h_max)]
        if alt_b_rows != correct_rows and alt_b_rows not in [d["rows"] for d in distractors]:
            distractors.append({"type": "grid", "title": "보기", "rows": alt_b_rows, "footer": direction_footer})

        alt_heights2 = list(col_heights if direction == "앞" else row_heights)
        alt_heights2[-1] = max(1, (alt_heights2[-1] + 1) if alt_heights2[-1] < 3 else alt_heights2[-1] - 1)
        alt_h_max2 = max(H_max, max(alt_heights2))
        alt_c_rows = [["1" if alt_heights2[c] >= (alt_h_max2 - f) else "" for c in range(W)] for f in range(alt_h_max2)]
        if alt_c_rows != correct_rows and alt_c_rows not in [d["rows"] for d in distractors]:
            distractors.append({"type": "grid", "title": "보기", "rows": alt_c_rows, "footer": direction_footer})

        while len(distractors) < 3:
            dummy_rows = [["1" for _ in range(W)]]
            if dummy_rows != correct_rows and dummy_rows not in [d["rows"] for d in distractors]:
                distractors.append({"type": "grid", "title": "보기", "rows": dummy_rows, "footer": direction_footer})
            else:
                dummy_rows2 = [["1" if i == 0 else "" for _ in range(W)] for i in range(2)]
                distractors.append({"type": "grid", "title": "보기", "rows": dummy_rows2, "footer": direction_footer})

        all_opts = [correct_opt] + distractors[:3]
        rng.shuffle(all_opts)
        corr_idx = all_opts.index(correct_opt)
        corr_ans_str = str(corr_idx + 1)

        vis_grid = {
            "type": "grid",
            "title": "위에서 본 모양에 수를 쓴 모양",
            "rows": [[str(c) if c > 0 else "" for c in r] for r in M],
            "footer": "앞",
        }

        return {
            "quiz_id": quiz_id,
            "grade": actual_grade,
            "grade_group": actual_grade_group,
            "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
            "topic": "공간 감각",
            "difficulty": target_difficulty,
            "score": score,
            "question_type": "객관식",
            "question": f"그림은 쌓기나무로 쌓은 모양을 위에서 본 모양에 각 자리에 쌓인 쌓기나무의 수를 적은 것입니다. 이 쌓기나무를 **{direction}에서** 바라보았을 때 보이는 모양으로 알맞은 것을 고르시오.",
            "visual_data": vis_grid,
            "solution": f"위에서 본 모양에 적힌 수를 바탕으로 {direction}에서 바라볼 때 보이는 모양을 찾습니다:\n- 각 줄에서 가장 높이 쌓인 쌓기나무의 높이를 구하면 왼쪽부터 차례대로 {col_desc}입니다.\n- 따라서 이 모양과 일치하는 보기는 {corr_ans_str}번입니다.",
            "calculated_answer_value": f"{corr_ans_str}번",
            "correct_answer": corr_ans_str,
            "options": all_opts,
            "rubric": [],
        }

    # -----------------------------------------------------------------------
    # 3. [층별 모양 (1층/2층/3층)] 허공 블록 0% 보장 및 숫자 스포일러 방지
    # -----------------------------------------------------------------------
    if template in ["floor_layers", "floor_layers_mc"]:
        f1 = [[True if rng.random() > 0.3 else False for _ in range(C)] for _ in range(R)]
        if sum(1 for r in f1 for c in r if c) < 3:
            f1[0][0] = f1[0][1] = f1[1][0] = True

        f1_positions = [(r, c) for r in range(R) for c in range(C) if f1[r][c]]
        k2 = rng.randint(1, max(1, len(f1_positions) - 1))
        f2_pos = set(rng.sample(f1_positions, k2))
        f2 = [[(r, c) in f2_pos for c in range(C)] for r in range(R)]

        f3_pos = set()
        if len(f2_pos) >= 2 and rng.random() > 0.4:
            k3 = rng.randint(1, len(f2_pos))
            f3_pos = set(rng.sample(list(f2_pos), k3))
        f3 = [[(r, c) in f3_pos for c in range(C)] for r in range(R)]

        n1 = len(f1_positions)
        n2 = len(f2_pos)
        n3 = len(f3_pos)
        total_blocks = n1 + n2 + n3

        v_grids = [
            {"type": "grid", "title": "1층 모양", "rows": [["1" if c else "" for c in r] for r in f1]},
            {"type": "grid", "title": "2층 모양", "rows": [["1" if c else "" for c in r] for r in f2]},
        ]
        if n3 > 0:
            v_grids.append({"type": "grid", "title": "3층 모양", "rows": [["1" if c else "" for c in r] for r in f3]})

        q_type = "객관식" if template == "floor_layers_mc" else target_question_type
        if q_type not in ["ox", "객관식", "단답형", "서술형"]:
            q_type = "단답형"

        question = "쌓기나무로 쌓은 입체도형을 층별로 나타낸 모양입니다. 이 입체도형을 만드는 데 사용된 쌓기나무는 모두 몇 개입니까?"
        sol = f"층별로 사용된 쌓기나무의 개수를 구하면 다음과 같습니다:\n- 1층: {n1}개\n- 2층: {n2}개\n" + (f"- 3층: {n3}개\n" if n3 > 0 else "") + f"따라서 필요한 쌓기나무는 모두 {n1} + {n2}" + (f" + {n3}" if n3 > 0 else "") + f" = {total_blocks}개입니다."

        opts = []
        corr_ans = f"{total_blocks}개"
        if q_type == "객관식":
            c_opts = [f"{total_blocks}개", f"{total_blocks + 1}개", f"{max(1, total_blocks - 1)}개", f"{total_blocks + 2}개"]
            rng.shuffle(c_opts)
            corr_ans = str(c_opts.index(f"{total_blocks}개") + 1)
            opts = c_opts

        rubric = []
        if q_type == "서술형":
            rubric = [
                {"step": "1단계: 1층, 2층, 3층에 놓인 쌓기나무 개수 각각 구하기", "points": 1},
                {"step": "2단계: 각 층의 개수를 모두 더하여 전체 개수 구하기", "points": max(1, score - 1)},
            ]

        return {
            "quiz_id": quiz_id,
            "grade": actual_grade,
            "grade_group": actual_grade_group,
            "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
            "topic": "공간 감각",
            "difficulty": target_difficulty,
            "score": score,
            "question_type": q_type,
            "question": question,
            "visual_data": v_grids,
            "solution": sol,
            "calculated_answer_value": f"{total_blocks}개",
            "correct_answer": corr_ans,
            "options": opts,
            "rubric": rubric,
        }

    # -----------------------------------------------------------------------
    # 4. [OX 퀴즈] 핵심 공간 개념 판별
    # -----------------------------------------------------------------------
    if template == "ox_concept":
        ox_items = [
            ("쌓기나무를 위에서 본 모양만 알면, 쌓은 데 사용된 쌓기나무의 전체 개수를 항상 정확하게 알 수 있다.", "X", "위에서 본 모양만으로는 각 자리에 쌓인 쌓기나무의 높이를 알 수 없으므로, 전체 개수를 정확히 알 수 없습니다."),
            ("쌓기나무를 위에서 본 모양의 각 자리에 쌓인 개수를 적어 놓으면, 쌓은 모양을 하나로 정확하게 나타낼 수 있다.", "O", "위에서 본 모양의 각 칸에 쌓인 개수를 숫자로 쓰면 숨겨진 블록 없이 전체 입체 모양을 정확하게 하나로 나타낼 수 있습니다."),
            ("쌓기나무를 앞에서 본 모양은 위에서 본 모양의 각 열(세로줄)에서 가장 높은 층의 높이와 같다.", "O", "앞에서 바라보면 각 열에서 가장 높이 쌓인 쌓기나무만 보이게 되므로, 각 열의 최댓값과 일치합니다."),
            ("쌓기나무를 층별로 나타낸 모양(1층, 2층, 3층)을 모두 합하면 사용된 쌓기나무의 전체 개수를 구할 수 있다.", "O", "각 층에 놓인 쌓기나무의 개수를 모두 세어 더하면 전체 쌓기나무의 개수를 정확히 구할 수 있습니다."),
        ]
        q_item = rng.choice(ox_items)
        return {
            "quiz_id": quiz_id,
            "grade": actual_grade,
            "grade_group": actual_grade_group,
            "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
            "topic": "공간 감각",
            "difficulty": target_difficulty,
            "score": score,
            "question_type": "ox",
            "question": f"다음 설명이 맞으면 O, 틀리면 X를 선택하세요.\n\n\"{q_item[0]}\"",
            "visual_data": {"type": "none"},
            "solution": q_item[2],
            "calculated_answer_value": q_item[1],
            "correct_answer": q_item[1],
            "options": ["O", "X"],
            "rubric": [],
        }

    # -----------------------------------------------------------------------
    # 5. [3방향 투영도 (위/앞/옆)] 총 개수 및 최대·최소 개수 추론
    # -----------------------------------------------------------------------
    M = [[rng.choice([1, 2, 3]) if rng.random() > 0.3 else 0 for _ in range(C)] for _ in range(R)]
    if sum(1 for r in M for c in r if c > 0) < 2:
        M[0][0] = 2
        M[-1][-1] = 1

    top_rows = [["1" if M[r][c] >= 1 else "" for c in range(C)] for r in range(R)]
    col_heights = [max(M[r][c] for r in range(R)) for c in range(C)]
    H_f = max(col_heights)
    front_rows = [["1" if col_heights[c] >= (H_f - f) else "" for c in range(C)] for f in range(H_f)]

    row_heights = [max(M[r][c] for c in range(C)) for r in range(R)]
    # 옆(오른쪽)에서 본 모양: 초등 표준 약속에 따라 왼쪽 칼럼=앞줄, 오른쪽 칼럼=뒷줄!
    side_col_heights = [max(M[r][c] for c in range(C)) for r in reversed(range(R))]
    H_s = max(side_col_heights)
    side_rows = [["1" if side_col_heights[i] >= (H_s - f) else "" for i in range(R)] for f in range(H_s)]

    v_grids = [
        {"type": "grid", "title": "위에서 본 모양", "rows": top_rows, "footer": "앞"},
        {"type": "grid", "title": "앞에서 본 모양", "rows": front_rows, "footer": "왼쪽 ◀ ▶ 오른쪽"},
        {"type": "grid", "title": "옆(오른쪽)에서 본 모양", "rows": side_rows, "footer": "앞 ◀ ▶ 뒤"},
    ]

    max_blocks = sum(min(col_heights[c], row_heights[r]) for r in range(R) for c in range(C) if M[r][c] >= 1)
    min_blocks = min(max_blocks, max(sum(col_heights), sum(row_heights)))
    diff = max_blocks - min_blocks

    # 각 자리별(행, 열) 최댓값 분석 상세 해설 생성
    cell_desc = []
    for r in range(R):
        for c in range(C):
            if M[r][c] >= 1:
                r_name = ["뒷줄(1행)", "가운데줄(2행)", "앞줄(3행)"][r] if R == 3 else (["뒷줄(1행)", "앞줄(2행)"][r] if R == 2 else f"{r+1}행")
                c_name = ["왼쪽(1열)", "오른쪽(2열)"][c] if C == 2 else (["왼쪽(1열)", "가운데(2열)", "오른쪽(3열)"][c] if C == 3 else f"{c+1}열")
                cap = min(col_heights[c], row_heights[r])
                cell_desc.append(f"  - {r_name} {c_name}: 앞({col_heights[c]}층)과 옆({row_heights[r]}층) 조건에 따라 최대 **{cap}개**")
    cell_text = "\n".join(cell_desc)

    ask_diff = (diff > 0) and (rng.random() > 0.4)
    if ask_diff:
        question = "쌓기나무로 쌓은 모양을 위, 앞, 옆에서 본 모양입니다. 이 모양을 만드는 데 필요한 쌓기나무의 가능한 **최대 개수와 최소 개수의 차**는 몇 개입니까?"
        ans_num = diff
        ans_val = f"{diff}개"
        sol = (
            f"위, 앞, 옆에서 본 모양을 분석하여 각 자리에 놓일 수 있는 쌓기나무의 개수를 구합니다:\n"
            f"1. 초등학교 수학 약속에 따라 옆(오른쪽)에서 본 모양은 **왼쪽이 '앞줄'**, **오른쪽이 '뒷줄'**입니다.\n"
            f"2. 위에서 본 모양의 각 자리에 들어갈 수 있는 가장 큰 수는 '앞에서 본 높이'와 '옆에서 본 높이' 중 작은 값입니다.\n"
            f"{cell_text}\n"
            f"- 가능한 최대 개수: {max_blocks}개\n"
            f"- 가능한 최소 개수: {min_blocks}개\n"
            f"따라서 최대 개수와 최소 개수의 차는 {max_blocks} - {min_blocks} = {diff}개입니다.\n"
            f"(💡 참고: 앞에서 볼 때 3층으로 보이는 줄은 그 줄의 앞쪽 칸이 1층이어도 뒤쪽 칸에 3층이 있으면 앞에서 3층 전체가 보입니다.)"
        )
    else:
        question = "쌓기나무로 쌓은 모양을 위, 앞, 옆에서 본 모양입니다. 이 모양을 만드는 데 필요한 쌓기나무의 **최대 개수**는 몇 개입니까?"
        ans_num = max_blocks
        ans_val = f"{max_blocks}개"
        sol = (
            f"위, 앞, 옆에서 본 모양을 바탕으로 각 자리에 최대로 쌓을 수 있는 개수를 분석합니다:\n"
            f"1. 초등학교 수학 약속에 따라 옆(오른쪽)에서 본 모양은 **왼쪽이 '앞줄'**, **오른쪽이 '뒷줄'**입니다.\n"
            f"2. 각 자리에 들어갈 수 있는 최댓값은 해당 자리의 '앞에서 본 높이'와 '옆에서 본 높이'를 동시에 만족해야 합니다.\n"
            f"{cell_text}\n"
            f"- 각 자리에 최대로 쌓을 수 있는 개수를 모두 더하면 {max_blocks}개입니다.\n"
            f"(💡 참고: 앞에서 볼 때 3층으로 보이는 줄은 그 줄의 앞쪽 칸이 1층이어도 뒤쪽 칸에 3층이 있으면 앞에서 3층 전체가 보입니다.)"
        )

    q_type = "객관식" if template == "3view_mc" else target_question_type
    if q_type not in ["ox", "객관식", "단답형", "서술형"]:
        q_type = "단답형"

    opts = []
    corr_ans = ans_val
    if q_type == "객관식":
        c_opts = [ans_val, f"{ans_num + 1}개", f"{max(0, ans_num - 1)}개", f"{ans_num + 2}개"]
        rng.shuffle(c_opts)
        corr_ans = str(c_opts.index(ans_val) + 1)
        opts = c_opts

    rubric = []
    if q_type == "서술형":
        rubric = [
            {"step": "1단계: 위, 앞, 옆 모양을 바탕으로 각 자리에 쌓을 수 있는 개수 범위 파악하기", "points": 1},
            {"step": "2단계: 최종 개수 또는 차이 계산하기", "points": max(1, score - 1)},
        ]

    return {
        "quiz_id": quiz_id,
        "grade": actual_grade,
        "grade_group": actual_grade_group,
        "unit": target_unit if ("공간" in target_unit or "도형" in target_unit) else "(3) 공간과 입체",
        "topic": "공간 감각",
        "difficulty": target_difficulty,
        "score": score,
        "question_type": q_type,
        "question": question,
        "visual_data": v_grids,
        "solution": sol,
        "calculated_answer_value": ans_val,
        "correct_answer": corr_ans,
        "options": opts,
        "rubric": rubric,
    }


# ---------------------------------------------------------------------------
# 2. 100% 실시간 AI 온디맨드 퀴즈 출제 로직
#    [황금 순서: 1. 연습장에서 나누어떨어지는지 끝까지 먼저 계산·검산 -> 2. 검증된 숫자로 지문/표 작성 -> 3. 해설 작성 -> 4. 정답/보기 도출]
# ---------------------------------------------------------------------------
def generate_math_quiz(
    mode: str = "custom",  # "custom" (맞춤문제) or "manual" (직접선택)
    grade: Optional[int] = None,
    grade_group: Optional[str] = None,
    unit: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
    question_type: Optional[str] = None,
    quiz_logs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    초등수학 온디맨드 퀴즈 실시간 AI 생성
    """
    # 1) 학년 및 학년군 결정
    if mode == "custom":
        actual_grade = grade if grade else 4
        actual_grade_group = get_grade_group(actual_grade)
    else:
        actual_grade_group = (
            grade_group
            if grade_group in ["1~2학년군", "3~4학년군", "5~6학년군"]
            else "3~4학년군"
        )
        actual_grade = (
            grade
            if grade
            else (
                3
                if actual_grade_group == "3~4학년군"
                else (1 if actual_grade_group == "1~2학년군" else 5)
            )
        )

    # 2) 커리큘럼 데이터 로드 및 슬라이싱 (토큰 최적화)
    sliced_curriculum = get_sliced_curriculum_text(actual_grade_group)
    curriculum_tree = parse_curriculum_data().get(actual_grade_group, {})

    # 3) 대단원 및 세부주제 결정 + 선택된 세부주제의 성취기준 설명 추출
    available_units = list(curriculum_tree.keys())
    if not unit or unit == "랜덤":
        target_unit = random.choice(available_units) if available_units else "(1) 수와 연산"
    elif unit not in curriculum_tree:
        # 유사 단원 매칭 시도 (예: '공간' or '도형' or '입체'가 포함된 단원)
        matched_unit = next((u for u in available_units if any(k in u for k in ["공간", "도형", "입체"]) and any(k in unit for k in ["공간", "도형", "입체"])), None)
        target_unit = matched_unit if matched_unit else (random.choice(available_units) if available_units else "(1) 수와 연산")
    else:
        target_unit = unit

    unit_topics_list = curriculum_tree.get(target_unit, [])
    available_topics = [t["title"] for t in unit_topics_list]
    if not topic or topic == "랜덤":
        target_topic = random.choice(available_topics) if available_topics else "기본 연산"
    elif topic not in available_topics:
        # '공간 감각' or '쌓기나무' 매칭
        matched_topic = next((t for t in available_topics if any(k in t for k in ["공간", "쌓기나무", "입체"]) and any(k in topic for k in ["공간", "쌓기나무", "입체"])), None)
        target_topic = matched_topic if matched_topic else (random.choice(available_topics) if available_topics else "기본 연산")
    else:
        target_topic = topic

    # 해당 세부주제의 상세 성취기준 텍스트 찾기
    topic_detail = target_topic
    for t_obj in unit_topics_list:
        if t_obj["title"] == target_topic:
            topic_detail = f"{t_obj['title']}: {t_obj['detail']}"
            break

    # 4) 난이도 및 문제유형 결정 (OX는 '하'만, 서술형은 '중/상'만, 객관식/단답형은 모두 허용)
    has_valid_type = question_type and question_type != "랜덤" and question_type in QUESTION_TYPES
    has_valid_diff = difficulty and difficulty != "랜덤" and difficulty in DIFFICULTY_SCORES

    if has_valid_type and has_valid_diff:
        target_question_type = question_type
        allowed_diffs = ALLOWED_DIFFS_BY_TYPE[target_question_type]
        target_difficulty = difficulty if difficulty in allowed_diffs else random.choice(allowed_diffs)
    elif has_valid_type:
        target_question_type = question_type
        target_difficulty = random.choice(ALLOWED_DIFFS_BY_TYPE[target_question_type])
    elif has_valid_diff:
        target_difficulty = difficulty
        target_question_type = random.choice(ALLOWED_TYPES_BY_DIFF[target_difficulty])
    else:
        target_difficulty = random.choice(["하", "중", "상"])
        target_question_type = random.choice(ALLOWED_TYPES_BY_DIFF[target_difficulty])

    score = DIFFICULTY_SCORES[target_difficulty]

    # 5) 난이도별 진도 및 출제 수준 통제 지침 (중학교 방정식 등은 '상' 난이도에만 허용!)
    if target_difficulty in ["하", "중"]:
        difficulty_level_instruction = (
            f"- 현재 난이도는 '{target_difficulty}({score}점)'입니다. **반드시 제시된 [{actual_grade_group}] 교육과정 성취기준 범위 안의 초등 개념과 풀이법만 사용하세요!**\n"
            f"- 중학교 과정인 일차방정식(미지수 $x, y$ 설정 및 이항 등)이나 상위 학년 선행 공식을 절대 사용하지 말고, 미지수가 필요하면 초등학교 교과서 방식인 `$\\square$`(네모)와 역연산 또는 초등 산술 풀이를 사용하세요."
        )
    else:
        difficulty_level_instruction = (
            f"- 현재 난이도는 '상(5점 - 심화)'입니다. 제시된 성취기준의 복합 응용 문제는 물론, 상위 진도(방정식적 사고나 심화 추론 등)와 연계된 도전적인 고난도 문제를 출제할 수 있습니다."
        )

    # 6) 맞춤문제 취약점 컨텍스트 구성
    weakness_context = ""
    if mode == "custom" and quiz_logs:
        incorrect_items = [
            f"- {log.get('topic', '주제미상')} (난이도: {log.get('difficulty', '중')})"
            for log in quiz_logs
            if not log.get("is_correct", False)
        ]
        if incorrect_items:
            weakness_context = (
                f"\n[학생 취약점 로그]\n학생이 최근 다음 개념에서 오답을 기록했습니다:\n"
                + "\n".join(incorrect_items[-3:])
                + "\n이 취약 개념을 보완할 수 있도록 핵심 원리를 점검하는 문제를 출제해 주세요.\n"
            )

    random_seed_num = random.randint(1000, 9999)
    quiz_id = f"math_{int(time.time() * 1000)}_{random_seed_num}"

    # 공간 감각 및 쌓기나무 전용 파이프라인 (선택된 단원/주제가 실제로 공간/도형 파트일 때만 실행)
    is_spatial = (
        ("공간" in str(target_topic) or "쌓기나무" in str(target_topic) or
         "공간" in str(topic_detail) or "쌓기나무" in str(topic_detail) or
         "공간" in str(topic or "") or "쌓기나무" in str(topic or "")) and
        ("도형" in str(target_unit) or "공간" in str(target_unit) or "입체" in str(target_unit) or target_unit == "랜덤")
    )

    # 비-공간감각 단원인데 '단답형 주관식 2'로 들어온 경우 단원을 강제로 바꾸지 않고 일반 '단답형'으로 유연 전환
    if target_question_type == "단답형 주관식 2":
        if is_spatial:
            return _generate_spatial_blocks_quiz(
                quiz_id=quiz_id,
                actual_grade=actual_grade,
                actual_grade_group=actual_grade_group,
                target_unit=target_unit if ("공간" in str(target_unit) or "도형" in str(target_unit)) else "(3) 공간과 입체",
                target_topic=target_topic if ("공간" in str(target_topic) or "입체" in str(target_topic)) else "공간 감각",
                target_difficulty=target_difficulty,
                score=score,
                target_question_type=target_question_type,
                random_seed_num=random_seed_num,
            )
        else:
            target_question_type = "단답형"
    elif is_spatial:
        return _generate_spatial_blocks_quiz(
            quiz_id=quiz_id,
            actual_grade=actual_grade,
            actual_grade_group=actual_grade_group,
            target_unit=target_unit if ("공간" in str(target_unit) or "도형" in str(target_unit)) else "(3) 공간과 입체",
            target_topic=target_topic if ("공간" in str(target_topic) or "입체" in str(target_topic)) else "공간 감각",
            target_difficulty=target_difficulty,
            score=score,
            target_question_type=target_question_type,
            random_seed_num=random_seed_num,
        )

    # 7) AI 프롬프트 구성 (황금 순서: 1. internal_scratchpad 설계·검산 -> 2. question/visual_data -> 3. solution -> 4. calculated_answer_value/options/correct_answer)
    system_instruction = (
        "당신은 2022 개정 교육과정에 정통한 대한민국 초등학교 수학 수석 교사입니다.\n"
        "문제를 출제할 때 다음 5가지 절대 원칙을 지키세요:\n"
        "1. [1단계: `internal_scratchpad`에서 수치 완결성 사전 검산]:\n"
        "   - 문제를 쓰기 전에 반드시 첫 번째 키인 `internal_scratchpad`에서 사용할 숫자들을 먼저 설정하고 끝까지 계산해 보세요.\n"
        "   - 특히 사람 수(명), 개수(개) 등은 반드시 자연수로 나누어떨어져야 합니다! 만약 연습장에서 계산하다가 나누어떨어지지 않아 숫자를 수정했다면(예: 40명->50명), 연습장 맨 마지막에 `[최종 확정 조건: 전체 50명, 바나나 7명... -> 최종 답: 22명]`이라고 명확히 정리하세요.\n"
        "2. [2단계: `question` · `visual_data` · `solution` 수치 100% 통일 (말바꾸기 절대 금지!)]:\n"
        "   - `question`(문제 지문)과 `visual_data`(표/그래프), 그리고 `solution`(해설)에는 오직 `internal_scratchpad` 맨 마지막에 **[최종 확정]**된 똑같은 숫자만 적으세요!\n"
        "   - 지문에는 '40명, 6명'이라고 적어놓고 해설에서 갑자기 '50명, 7명'으로 숫자를 바꿔서 푸는 행위는 절대 금지입니다!\n"
        "3. [3단계: `solution` 및 `calculated_answer_value` · `options` 도출]:\n"
        "   - `solution`을 다 적은 뒤, 그 풀이의 최종 결론 값을 `calculated_answer_value`에 적고, 객관식이면 그 값을 반드시 4개의 `options` 안에 포함시키세요.\n"
        "4. [LaTeX 수식 및 텍스트 표기 원칙]:\n"
        "   - 분수, 단위, 제곱, 곱셈기호 등을 표기할 때는 웹 화면의 KaTeX 모듈이 렌더링할 수 있도록 반드시 전체 수식을 `$56\\\\frac{1}{4}\\\\text{ m}^2$`처럼 앞뒤로 `$` 기호로 감싸서 표기하세요!\n"
        "   - **절대 금지**: `question`이나 `solution` 안에 HTML 태그(`<br>`), 마크다운 기호(`**`), 글자로 된 역슬래시+n, 수식(`$...$`) 밖의 `\\\\quad`, 또는 한글이 들어간 `\\\\[...\\\\]`를 절대 사용하지 마세요!\n"
        "5. [표·격자판·그래프 자동 시각화 주문서(`visual_data`) 활용 원칙]:\n"
        "   - 쌓기나무 위에서 본 모양(3×3 격자 등), 규칙과 대응 표, 자료 조사 결과표, 막대그래프, 꺾은선그래프, 띠그래프, 원그래프가 필요한 문제일 때는 **절대 `question` 본문 안에 텍스트로 나열하지 말고 `visual_data`에 작성하세요!**\n"
        "   - **[표 필수 포함 원칙]**: 지문이 '조사하여 나타낸 표입니다', '이 자료를 바탕으로 막대/꺾은선그래프를 그릴 때'처럼 표의 자료를 바탕으로 그래프를 그리는 문제라면, **반드시 `visual_data`에 `table`(표)을 필수 포함**하세요! (표와 미완성 그래프를 함께 보여주려면 `[ {표 객체}, {그래프 객체} ]` 배열로 담으세요.)\n"
        "   - **[정답 스포일러 절대 금지]**: 특정 항목(예: '귤', '4반')의 막대 칸수나 그리기 방법을 묻는 문제라면, 막대그래프에서 질문 대상인 그 항목의 막대는 **`values`를 0으로 두거나 `labels`에 '귤(?)'로 지정하여 정답 막대가 꽉 찬 채로 미리 그려져서 답을 스포일러하지 않도록 미완성 막대로 제시하세요!**\n"
        "   - **[공간 감각: 쌓기나무 입체도형 출제 절대 원칙 (3x3 고정 금지 & 허공 블록 절대 금지!)]**:\n"
        "     ※ [격자 크기 다양화]: 절대 모든 문제를 3×3으로 고정하지 마세요! 2×2, 2×3, 3×2, 3×3, 2×4 등 다양한 직사각형/정사각형 크기의 격자를 골고루 사용하세요!\n"
        "     ※ [중력/물리 법칙 절대 준수 (허공 블록 절대 금지!)]: 쌓기나무는 공중에 떠 있을 수 없습니다! 2층의 (행, 열) 자리에 블록이 있으려면 반드시 1층의 같은 자리에 블록이 있어야 하고, 3층에 블록이 있으려면 반드시 2층과 1층의 같은 자리에 블록이 있어야 합니다! (아래층이 비어 있는데 윗층에 블록이 존재하는 물리적 오류는 절대 금지!)\n"
        "     ※ [층별 모양 표현]: 블록이 있는 칸에는 \"1\", 없는 칸에는 \"\"(빈 문자열)을 적으세요. (웹 화면에서 자동으로 따뜻한 원목 블록 색상으로 채워집니다!)\n"
        "     ① **[층별로 나타낸 모양 (1층, 2층, 3층)]**: 각 층의 모양을 3개의 격자판 배열로 출제하세요!\n"
        "        -> `visual_data`: `[ {\"type\": \"grid\", \"title\": \"1층 모양\", \"rows\": [[\"1\",\"1\",\"1\"], [\"1\",\"1\",\"\"]], \"footer\": \"앞\"}, {\"type\": \"grid\", \"title\": \"2층 모양\", \"rows\": [[\"1\",\"1\",\"\"], [\"1\",\"\",\"\"]], \"footer\": \"앞\"}, {\"type\": \"grid\", \"title\": \"3층 모양\", \"rows\": [[\"1\",\"\",\"\"]], \"footer\": \"앞\"} ]`\n"
        "        -> 질문 예시: '1층, 2층, 3층의 모양이 다음과 같을 때, 사용된 쌓기나무는 모두 몇 개입니까?' 또는 '앞(옆)에서 본 모양은 어떤 모양입니까?'\n"
        "     ② **[위·앞·옆에서 본 모양 (3방향 투영도)]**: 위, 앞, 옆 3개의 격자판 배열로 출제하세요!\n"
        "        -> `visual_data`: `[ {\"type\": \"grid\", \"title\": \"위에서 본 모양\", \"rows\": [[\"1\",\"1\",\"\"]], \"footer\": \"앞\"}, {\"type\": \"grid\", \"title\": \"앞에서 본 모양\", \"rows\": [[\"1\",\"1\",\"1\"], [\"1\",\"1\",\"\"]]}, {\"type\": \"grid\", \"title\": \"옆에서 본 모양\", \"rows\": [[\"1\",\"1\"], [\"1\",\"\"]]} ]`\n"
        "        -> 질문 예시: '위, 앞, 옆에서 본 모양이 다음과 같을 때 사용된 쌓기나무의 최소 개수/최대 개수/총 개수를 구하시오.'\n"
        "     ③ **[위에서 본 모양에 수를 쓴 모양]**: 2×2, 2×3, 3×3 등 다양한 크기의 단일 격자!\n"
        "        -> 각 칸에는 해당 자리에 쌓인 **총 높이(개수) 딱 1개의 자연수(\"1\", \"2\", \"3\", 빈자리는 \"\")**만 적기! (절대 한 칸에 \"3, 2, 1\"처럼 여러 숫자를 넣지 말 것)\n"
        "     ④ **[앞과 옆에서 본 모양 추론]**: 앞과 옆 2개의 격자판 배열로 출제!\n"
        "        -> `visual_data`: `[ {\"type\": \"grid\", \"title\": \"앞에서 본 모양\", \"rows\": ...}, {\"type\": \"grid\", \"title\": \"옆에서 본 모양\", \"rows\": ...} ]`\n"
        "     (a) 표/그래프가 필요 없을 때: `{\"type\": \"none\"}`\n"
        "     (b) 정사각형 바둑판 격자(쌓기나무 등): `{\"type\": \"grid\", \"title\": \"격자 제목\", \"headers\": [], \"rows\": [[\"3\", \"2\", \"1\"], [\"2\", \"1\", \"\"], [\"1\", \"\", \"\"]], \"footer\": \"앞\"}`\n"
        "     (c) 일반 데이터 표(자료 조사 결과, 규칙 찾기, 비와 비율 등): `{\"type\": \"table\", \"title\": \"좋아하는 과일별 학생 수\", \"headers\": [\"사과\", \"포도\", \"귤\", \"기타\", \"합계\"], \"rows\": [[\"15명\", \"10명\", \"20명\", \"5명\", \"50명\"]]}`\n"
        "     (d) 막대그래프(`bar_chart`) 또는 꺾은선그래프(`line_chart`): `{\"type\": \"bar_chart\", \"title\": \"그래프 제목\", \"unit\": \"명\", \"y_step\": 5, \"labels\": [\"사과\", \"포도\", \"귤(?)\", \"기타\"], \"values\": [15, 10, 0, 5]}` (※ 지문에 '세로 눈금 한 칸은 N명'이라고 언급했다면 반드시 `\"y_step\": N`을 똑같이 지정하세요!)\n"
        "     (e) 띠그래프(`band_chart`) 또는 원그래프(`pie_chart`): `{\"type\": \"pie_chart\", \"title\": \"좋아하는 과일별 비율\", \"unit\": \"%\", \"labels\": [\"사과\", \"포도\", \"귤\", \"기타(?%)\"], \"values\": [40, 25, 20, 15]}` (※ `values`에는 단위 기호 없이 순수 숫자만 적어 합이 100이 되게 하세요! 학생이 구해야 하는 미지수 항목은 `values`에는 실제 비율 숫자를 적고 `labels` 이름을 `\"기타(?%)\"`처럼 표기하면 그래프에 정답 숫자가 노출되지 않고 `?%`로 표시됩니다!)"
    )

    type_instructions = {
        "ox": (
            "- 문제 형태: OX 퀴즈 (1점 기초 개념 점검)\n"
            "- options 배열: [\"O\", \"X\"]\n"
            "- correct_answer: \"O\" 또는 \"X\"\n"
            "- 해당 세부주제의 핵심 수학 개념이나 계산 결과의 참/거짓을 묻는 명확한 명제를 출제하세요."
        ),
        "객관식": (
            "- 문제 형태: 4지선다 객관식\n"
            "- options 배열: 4개의 서로 다른 보기 문자열 (반드시 `calculated_answer_value`를 4개 보기 중 하나에 정확히 포함시킬 것!)\n"
            "- calculated_answer_value: `solution`에서 최종 도출된 정확한 정답 값\n"
            "- correct_answer: options 배열에서 calculated_answer_value가 위치한 번호 (\"1\", \"2\", \"3\", \"4\" 중 하나)"
        ),
        "단답형": (
            "- 문제 형태: 단답형 주관식\n"
            "- options 배열: [] (빈 배열)\n"
            "- correct_answer: 정답 표기 (분수나 수식인 경우 `$1\\\\frac{1}{3}$` 또는 `4/3` 등 명확한 정답)\n"
            "- 문제 지문 끝에 답 입력 안내(예: '분수는 1과 1/3 또는 4/3 형태로 입력 가능하며, 단위는 생략해도 됩니다')를 친절히 덧붙이세요."
        ),
        "서술형": (
            "- 문제 형태: 서술형 (풀이 과정 서술)\n"
            "- options 배열: [] (빈 배열)\n"
            "- correct_answer: 최종 정답 수치 및 단위 (반드시 `$56\\\\frac{1}{4}\\\\text{ m}^2$`처럼 전체를 `$`로 감싸서 표기)\n"
            "- rubric 배열: 단계별 채점 기준 객체 목록 (예: [{\"step\": \"1단계: 상추를 심은 밭의 넓이를 구하는 식 세우기\", \"points\": 1}, {\"step\": \"2단계: 고추를 심은 밭의 넓이를 계산하여 최종 답 구하기\", \"points\": 2}])\n"
            "- **[채점 기준(rubric) 정답 스포일러 절대 금지]**: `rubric`은 학생이 문제를 풀 때와 오답일 때 화면에 표시됩니다. 따라서 `rubric`의 `step` 문구 안에 중간 계산값이나 최종 정답 수치(예: `(27 m^2)`, `(18 m^2)`, `= 18` 등)를 **절대 포함하지 마세요!**\n"
            "- solution: 초등학생이 한눈에 이해할 수 있도록 단계별로 깔끔하게 정서된 최종 모범 풀이"
        ),
    }

    prompt = f"""{system_instruction}

[출제 조건 (창작 시드: #{random_seed_num})]
- 대상 학년: 초등학교 {actual_grade}학년 ({actual_grade_group})
- 대단원: {target_unit}
- 세부주제 및 학습성취목표: **{topic_detail}**
- 난이도: {target_difficulty} (배점: {score}점)
- 문제유형: {target_question_type}

[난이도별 교육과정 범위 지침]
{difficulty_level_instruction}

[참조 교육과정 ({actual_grade_group})]
{sliced_curriculum}
{weakness_context}
[문제유형별 세부 지침]
{type_instructions[target_question_type]}

반드시 아래 JSON 키 순서대로(`internal_scratchpad`에서 먼저 자연수로 딱 떨어지는 수치를 설계·검산하여 확정한 뒤 -> 그 확정된 수치를 `question`, `visual_data`, `solution`에 100% 똑같이 적고 -> 마지막에 `calculated_answer_value`, `options`, `correct_answer`를 도출하여) 순수 JSON만 출력하세요:
{{
  "internal_scratchpad": "1단계 교사용 연습장(화면 비노출): 문제 수치 설계 및 끝까지 계산·검산. 나누어떨어지지 않으면 여기서 숫자를 먼저 수정한 뒤, 맨 끝에 [최종 확정된 문제 수치와 정답]을 명확히 적으세요.",
  "grade": {actual_grade},
  "grade_group": "{actual_grade_group}",
  "unit": "{target_unit}",
  "topic": "{target_topic}",
  "difficulty": "{target_difficulty}",
  "score": {score},
  "question_type": "{target_question_type}",
  "question": "2단계 문제 지문: 위 internal_scratchpad 맨 마지막에 [최종 확정]된 수치를 단 하나도 바꾸지 말고 그대로 사용하여 작성하세요.",
  "visual_data": {{
    "type": "none 또는 grid / table / bar_chart / line_chart / band_chart / pie_chart (표와 그래프 2개 이상이 필요하면 [{{표 객체}}, {{그래프 객체}}] 배열로 작성 가능)",
    "title": "표/격자/그래프 제목 (없으면 빈 문자열)",
    "headers": [],
    "rows": [],
    "footer": "",
    "unit": "",
    "y_step": 0,
    "labels": [],
    "values": []
  }},
  "solution": "3단계 모범 해설: 바로 위 question 및 visual_data에 적힌 숫자와 100% 동일한 숫자로만 단계별 풀이를 작성하세요. (해설에서 다른 숫자로 바꾸기 및 정정 혼잣말 절대 금지)",
  "calculated_answer_value": "4단계 최종 정답 값: 바로 위 solution의 마지막 계산 결과값 (단위 포함)",
  "options": { '["O", "X"]' if target_question_type == 'ox' else ('["보기1", "보기2", "보기3", "보기4"]' if target_question_type == '객관식' else '[]') },
  "correct_answer": "{ 'O 또는 X' if target_question_type == 'ox' else ('options 중 calculated_answer_value가 들어간 보기의 번호(1~4)' if target_question_type == '객관식' else '최종 정답 값 (수식은 $...$로 감싸기)') }",
  "rubric": { '[{"step": "1단계 채점 기준 (절대 정답 수치 포함 금지)", "points": 1}, {"step": "2단계 채점 기준 (절대 정답 수치 포함 금지)", "points": 2}]' if target_question_type == '서술형' else '[]' }
}}
"""

    # 해설 내 자기모순/패닉 문구, 지문-해설 수치 불일치, 또는 쌓기나무 허공 블록 감지 시 자동 재출제 (최대 3회)
    data = {}
    for _gen_try in range(3):
        data = _call_gemini_json(prompt, temperature=0.45 if _gen_try == 0 else 0.3)
        sol_raw = str(data.get("solution", ""))
        q_raw = str(data.get("question", ""))
        v_raw = data.get("visual_data") if isinstance(data.get("visual_data"), (dict, list)) else {}
        if not _has_solution_contradiction(sol_raw, q_raw, v_raw) and not _has_floating_block(v_raw):
            break

    # 쌓기나무 층별 블록 물리적 지지 및 숫자 스포일러 방지 최종 보장
    if isinstance(data.get("visual_data"), (dict, list)):
        data["visual_data"] = _sanitize_spatial_visual_data(data["visual_data"])

    # 필수 메타 필드 보장
    data["quiz_id"] = quiz_id
    data["grade"] = actual_grade
    data["grade_group"] = actual_grade_group
    data["unit"] = target_unit
    data["topic"] = target_topic
    data["difficulty"] = target_difficulty
    data["score"] = score
    data["question_type"] = target_question_type
    data["question"] = _clean_display_text(data.get("question", ""))
    data["solution"] = _clean_display_text(data.get("solution", ""))
    if not isinstance(data.get("visual_data"), (dict, list)):
        data["visual_data"] = {"type": "none"}
    data.setdefault("options", ["O", "X"] if target_question_type == "ox" else [])
    data.setdefault("rubric", [])

    # 객관식 번호 및 보기 무결성 자동 교차 검증 (정답이 보기에 없는 현상 100% 차단!)
    if target_question_type == "객관식" and isinstance(data.get("options"), list) and len(data["options"]) == 4:
        calc_val = _clean_display_text(str(data.get("calculated_answer_value", "")).strip())
        corr_ans = _clean_display_text(str(data.get("correct_answer", "")).strip())
        cleaned_opts = [_clean_display_text(str(o)).strip() for o in data["options"]]

        def _norm_cmp(s: str) -> str:
            return re.sub(r"[\s$]", "", s)

        matched_idx = -1
        if calc_val:
            for idx, opt in enumerate(cleaned_opts):
                if _norm_cmp(opt) == _norm_cmp(calc_val):
                    matched_idx = idx
                    break
        if matched_idx != -1:
            data["correct_answer"] = str(matched_idx + 1)
        else:
            # 만약 AI가 calculated_answer_value("20명")는 맞게 구했는데 options에 넣는 것을 깜빡했다면,
            # 지정된 정답 번호(1~4) 위치에 calculated_answer_value를 강제 주입하여 정답 누락을 원천 방지!
            if corr_ans in ["1", "2", "3", "4"] and calc_val:
                target_idx = int(corr_ans) - 1
                cleaned_opts[target_idx] = calc_val
            elif corr_ans not in ["1", "2", "3", "4"]:
                for idx, opt in enumerate(cleaned_opts):
                    if _norm_cmp(opt) == _norm_cmp(corr_ans):
                        data["correct_answer"] = str(idx + 1)
                        break
                else:
                    if calc_val:
                        cleaned_opts[0] = calc_val
                    data["correct_answer"] = "1"

        # 보기 내부 수식도 $ 감싸기 보정
        data["options"] = [_ensure_latex_wrapped(o) for o in cleaned_opts]
    elif target_question_type in ["단답형", "서술형"]:
        # 정답 라벨에 56\frac{1}{4}\text{m}^2 처럼 $가 빠진 경우 자동으로 $...$ 감싸기
        data["correct_answer"] = _ensure_latex_wrapped(_clean_display_text(str(data.get("correct_answer", ""))))
        # 서술형 채점 기준(rubric) 안에 괄호로 정답 수치(예: (27 m^2), ($18\text{ m}^2$))가 들어간 경우 자동 제거!
        if isinstance(data.get("rubric"), list):
            cleaned_rubric = []
            for r in data["rubric"]:
                if isinstance(r, dict):
                    step_txt = _clean_display_text(str(r.get("step", r.get("criteria", ""))))
                    # 괄호 안에 숫자나 수식(\frac 등)이 들어간 스포일러 패턴 제거
                    step_txt = re.sub(r"\(\s*\$?[^()]*?(?:\d|\\frac)[^()]*?\$?\s*\)", "", step_txt).strip()
                    r["step"] = step_txt
                    cleaned_rubric.append(r)
            data["rubric"] = cleaned_rubric

    return data


# ---------------------------------------------------------------------------
# 3. 채점 및 AI 문맥/수식 동치 정밀 평가 로직
# ---------------------------------------------------------------------------
def grade_math_submission(
    question_type: str,
    difficulty: str,
    score: int,
    user_answer: str,
    correct_answer: str,
    solution: str,
    question: str,
    rubric: Optional[List[Dict[str, Any]]] = None,
    options: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    학생 제출 답안 채점:
    - OX, 객관식: 정확도 고속 판별 (문제은행 직접 출제 시 번호(1~4) 및 보기 텍스트 모두 매칭 지원)
    - 단답형(주관식): 1차 문자열 정규화 비교 후, 불일치 시 AI 문맥/수식 동치 판별 (수동 출제 문제 포함 100% AI 채점 적용)
    - 서술형: AI 문맥 정밀 채점 (수동 출제 문제 포함 1~5점 부분 점수 및 원포인트 첨삭 피드백)
    """
    user_ans = str(user_answer).strip()
    corr_ans = str(correct_answer).strip()

    # 1) OX 및 객관식 판별
    if question_type in ["ox", "객관식"]:
        norm_user = re.sub(r"\s+", "", user_ans).lower()
        norm_corr = re.sub(r"\s+", "", corr_ans).lower()
        is_correct = norm_user == norm_corr

        # 객관식에서 문제은행 수동 등록 시 정답이 보기 텍스트로 저장되었거나 번호로 저장된 경우 교차 매칭
        if not is_correct and question_type == "객관식" and isinstance(options, list) and len(options) > 0:
            if user_ans.isdigit():
                idx = int(user_ans) - 1
                if 0 <= idx < len(options):
                    opt_txt = re.sub(r"\s+", "", str(options[idx])).replace("$", "").lower()
                    corr_clean = norm_corr.replace("$", "")
                    if opt_txt == corr_clean:
                        is_correct = True
            elif corr_ans.isdigit():
                idx = int(corr_ans) - 1
                if 0 <= idx < len(options):
                    opt_txt = re.sub(r"\s+", "", str(options[idx])).replace("$", "").lower()
                    user_clean = norm_user.replace("$", "")
                    if opt_txt == user_clean:
                        is_correct = True

        earned_score = score if is_correct else 0
        feedback = (
            f"정답입니다! 참 잘했어요. (+{earned_score}점)"
            if is_correct
            else "아쉬워요! 다시 한 번 생각해서 풀어보거나 해설을 확인해 보세요."
        )

        return {
            "is_correct": is_correct,
            "earned_score": earned_score,
            "max_score": score,
            "feedback": feedback,
            "user_answer": user_answer,
            "correct_answer": _ensure_latex_wrapped(correct_answer),
            "solution": solution,
            "step_evaluations": [],
        }

    # 2) 단답형 주관식 2 (모눈종이 클릭 색칠하기 2D 행렬 채점 - 단일 및 2개 모눈종이 지원)
    if question_type == "단답형 주관식 2":
        try:
            user_val = json.loads(user_ans) if isinstance(user_ans, str) else user_ans
        except Exception:
            user_val = None

        try:
            corr_val = json.loads(corr_ans) if isinstance(corr_ans, str) else corr_ans
        except Exception:
            corr_val = None

        def _normalize_mat(m):
            if not isinstance(m, list):
                return []
            res = []
            for r in m:
                if isinstance(r, list):
                    res.append([1 if str(c).strip() in ["1", "true", "True"] else 0 for c in r])
            return res

        def _strip_empty_top_rows(mat):
            while mat and all(v == 0 for v in mat[0]):
                mat = mat[1:]
            return mat

        def _is_mat_match(u_m, c_m):
            nu = _normalize_mat(u_m)
            nc = _normalize_mat(c_m)
            if not nu or not nc:
                return False
            if nu == nc:
                return True
            return _strip_empty_top_rows(nu) == _strip_empty_top_rows(nc)

        is_correct = False
        earned_score = 0
        feedback = ""

        # 멀티 모눈종이 (2개 이상: 난이도 상 전용) 채점
        is_multi_corr = isinstance(corr_val, dict) and corr_val.get("multi") is True
        if is_multi_corr:
            corr_grids = corr_val.get("grids", [])
            correct_count = 0
            total_count = len(corr_grids)
            grid_feedbacks = []

            for idx, c_item in enumerate(corr_grids):
                g_id = c_item.get("id", f"grid_{idx}")
                g_title = c_item.get("title", f"모눈종이 {idx+1}")
                c_mat = c_item.get("matrix", [])

                u_mat = []
                if isinstance(user_val, dict):
                    if g_id in user_val:
                        u_mat = user_val[g_id]
                    elif "grids" in user_val and isinstance(user_val["grids"], list) and len(user_val["grids"]) > idx:
                        u_mat = user_val["grids"][idx]
                    elif idx == 0 and "front" in user_val:
                        u_mat = user_val["front"]
                    elif idx == 1 and "side" in user_val:
                        u_mat = user_val["side"]
                elif isinstance(user_val, list) and len(user_val) > idx:
                    u_mat = user_val[idx]

                if _is_mat_match(u_mat, c_mat):
                    correct_count += 1
                    grid_feedbacks.append(f"'{g_title}' 정답!")
                else:
                    grid_feedbacks.append(f"'{g_title}' 확인 필요")

            if correct_count == total_count:
                is_correct = True
                earned_score = score
                feedback = f"정답입니다! 앞과 옆에서 본 두 가지 모양을 모두 완벽하게 색칠했습니다! (+{earned_score}점 만점)"
            elif correct_count > 0:
                is_correct = False
                earned_score = max(1, int(round(score * (correct_count / total_count))))
                feedback = (
                    f"부분 점수 인정! {', '.join(grid_feedbacks)}. "
                    f"하나의 모양은 정확하지만 다른 모양에 오답이 있습니다. (+{earned_score}점 부분 점수)"
                )
            else:
                is_correct = False
                earned_score = 0
                feedback = f"아쉽습니다. {', '.join(grid_feedbacks)}. 해설의 앞과 옆 투영 원리를 확인해 보세요."
        else:
            # 단일 모눈종이 채점
            norm_u = _normalize_mat(user_val)
            norm_c = _normalize_mat(corr_val)
            if norm_u and norm_c and _is_mat_match(norm_u, norm_c):
                is_correct = True
                earned_score = score
                feedback = f"정답입니다! 모양을 정확하게 잘 칠했어요! (+{score}점)"
            else:
                is_correct = False
                earned_score = 0
                feedback = "아쉬워요! 앞에서(또는 옆에서) 볼 때 각 줄(열)마다 가장 높은 층의 높이를 다시 확인해 보세요."

        return {
            "is_correct": is_correct,
            "earned_score": earned_score,
            "max_score": score,
            "feedback": feedback,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "solution": solution,
            "step_evaluations": [],
        }

    # 3) 단답형 주관식: AI 수학적/문맥적 동치(Equivalence) 채점 지원! (문제은행 직접 출제 문제 포함)
    if question_type == "단답형":
        if not user_ans:
            return {
                "is_correct": False,
                "earned_score": 0,
                "max_score": score,
                "feedback": "답안을 입력해 주세요!",
                "user_answer": "",
                "correct_answer": _ensure_latex_wrapped(correct_answer),
                "solution": solution,
                "step_evaluations": [],
            }

        # 1차 고속 비교: 단순 공백/$ 제거 후 똑같으면 즉시 정답 처리
        def _simple_clean(s: str) -> str:
            s = re.sub(r"\$?\\+frac\{([^{}]+)\}\{([^{}]+)\}\$?", r"\1/\2", s)
            s = re.sub(r"\\+text\{([^{}]*)\}", r"\1", s)
            s = s.replace("$", "")
            return re.sub(r"\s+", "", s).lower()

        if _simple_clean(user_ans) == _simple_clean(corr_ans):
            return {
                "is_correct": True,
                "earned_score": score,
                "max_score": score,
                "feedback": f"정답입니다! 정확하게 잘 구했어요. (+{score}점)",
                "user_answer": user_answer,
                "correct_answer": _ensure_latex_wrapped(correct_answer),
                "solution": solution,
                "step_evaluations": [],
            }

        # 2차 AI 수학적/의미적 동치 판별 (예: 1과 1/3 == 1 1/3 == 4/3, 단위 포함/생략, 한글/숫자 표기, 띄어쓰기 등)
        short_grade_prompt = f"""당신은 초등학교 단답형 주관식 채점 교사입니다.
학생이 제출한 단답형 답안이 실제 정답과 수학적·의미적으로 같은 값(동치)인지 판별하세요. (관리자가 직접 문제은행에 출제한 주관식 문제도 포함됩니다.)

[문제 지문]
{question}

[모범 정답]
{correct_answer} (해설 요약: {solution or '별도 해설 없음'})

[학생 제출 답안]
{user_answer}

[판별 기준]
1. 분수의 다양한 표기법(예: `1과 1/3`, `1 1/3`, `4/3`, `1又1/3`)은 문제 지문에서 특정 형태를 강제하지 않은 이상 모두 정답(`is_correct: true`)으로 인정하세요!
2. 기약분수와 크기가 같은 분수나 소수 표기, 단위(cm, kg, 개, 명 등)나 조사 생략·포함, 띄어쓰기 차이, 동의어 표기 역시 핵심 답이 정확하다면 정답으로 인정하세요.
3. 수치가 틀렸거나 핵심 답이 다르다면 오답(`is_correct: false`)으로 판정하고, 정답을 직접 노출하지 않는 선에서 짧은 힌트 피드백을 주세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "is_correct": true,
  "feedback": "정답입니다! 정확한 답이에요!"
}}
"""
        try:
            ai_res = _call_gemini_json(short_grade_prompt, temperature=0.0)
            is_corr = bool(ai_res.get("is_correct", False))
            earned = score if is_corr else 0
            fb = ai_res.get(
                "feedback",
                f"정답입니다! (+{score}점)" if is_corr else "아쉬워요! 계산 결과를 다시 한 번 점검해 보세요.",
            )
            return {
                "is_correct": is_corr,
                "earned_score": earned,
                "max_score": score,
                "feedback": fb,
                "user_answer": user_answer,
                "correct_answer": _ensure_latex_wrapped(correct_answer),
                "solution": solution,
                "step_evaluations": [],
            }
        except Exception:
            return {
                "is_correct": False,
                "earned_score": 0,
                "max_score": score,
                "feedback": "아쉬워요! 다시 한 번 풀어보거나 정답 및 해설을 확인해 보세요.",
                "user_answer": user_answer,
                "correct_answer": _ensure_latex_wrapped(correct_answer),
                "solution": solution,
                "step_evaluations": [],
            }

    # 3) 서술형 AI 문맥 정밀 채점 (Semantic Rubric Evaluation - 직접 출제/문제은행 서술형 포함)
    if not user_ans:
        return {
            "is_correct": False,
            "earned_score": 0,
            "max_score": score,
            "feedback": "답안이 작성되지 않았습니다. 풀이 과정을 적어보세요!",
            "user_answer": "",
            "correct_answer": _ensure_latex_wrapped(correct_answer),
            "solution": solution,
            "step_evaluations": [],
        }

    rubric_desc = (
        json.dumps(rubric, ensure_ascii=False)
        if (rubric and len(rubric) > 0)
        else "별도 지정된 단계별 루브릭 없음 (문제은행 직접 출제 문제이므로 문제 지문, 최종 정답, 모범 해설을 기준으로 풀이 과정과 정답 도출 여부를 평가하여 자체 단계별 부분 점수를 부여할 것)"
    )

    grading_prompt = f"""당신은 초등학교 서술형 답안을 채점하는 따뜻하고 공정한 수석 교사입니다.
학생의 풀이 과정을 채점 기준과 모범 답안에 비추어 일관성 있게 채점하세요.

[문제 정보]
- 문제 지문: {question}
- 최종 정답: {correct_answer}
- 모범 해설: {solution or '최종 정답 및 문제 지문 참조'}
- 배점(최대 점수): {score}점
- 채점 기준: {rubric_desc}

[학생 제출 답안]
{user_answer}

[채점 절대 지침]
1. 모범 해설과 글자나 식의 형태가 완전히 똑같지 않더라도, **수학적 논리(식 또는 풀이 과정)가 올바르고 최종 정답({correct_answer}, 대분수/가분수 동치 인정)이 맞으면 무조건 만점({score}점)**을 부여하세요.
2. 풀이 과정(식)은 맞았으나 마지막 계산 실수나 단위 누락이 있는 경우, 채점 기준에 따라 공정하게 부분 점수(1~{score - 1}점)를 부여하세요.
3. 풀이 과정 없이 정답 숫자만 달랑 적었거나, 식의 방향이 일부만 맞은 경우에도 해당하는 단계 점수를 부분 점수로 부여하세요.
4. 전혀 엉뚱한 내용이거나 무의미한 글자만 적은 경우에만 0점을 부여하세요.
5. **[정답 스포일러 절대 금지]**: 학생이 만점({score}점)을 받지 못한 경우(오답 또는 부분 점수), 학생이 다시 풀어볼 수 있도록 `feedback`과 `step_evaluations`의 `step` 및 `comment` 안에 **중간 계산 답이나 최종 정답 수치({correct_answer})를 절대 직접 적지 마세요!** 어떤 식을 세워야 하는지 방향만 힌트로 안내하세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "earned_score": {score},
  "is_correct": true,
  "feedback": "문제 조건에 맞게 식을 세우고 정확하게 계산했어요! 참 잘했습니다.",
  "step_evaluations": [
    {{"step": "1단계: 식 세우기", "comment": "올바른 수식 작성 완료", "points": 2}},
    {{"step": "2단계: 계산 및 정답", "comment": "정확한 정답 도출", "points": {max(1, score - 2)}}}
  ]
}}
"""

    result = _call_gemini_json(grading_prompt, temperature=0.0)

    earned = int(result.get("earned_score", 0))
    earned = max(0, min(earned, score))
    is_pass = earned >= (score * 0.6)

    step_evals = result.get("step_evaluations", [])
    if earned < score and isinstance(step_evals, list):
        # 만점 미만일 때 step_evaluations 내부 괄호에 정답 수치가 스포일러된 경우 자동 제거
        for se in step_evals:
            if isinstance(se, dict):
                if "step" in se:
                    se["step"] = re.sub(r"\(\s*\$?[^()]*?(?:\d|\\frac)[^()]*?\$?\s*\)", "", str(se["step"])).strip()
                if "comment" in se:
                    se["comment"] = re.sub(r"\(\s*\$?[^()]*?(?:\d|\\frac)[^()]*?\$?\s*\)", "", str(se["comment"])).strip()

    return {
        "is_correct": is_pass,
        "earned_score": earned,
        "max_score": score,
        "feedback": result.get("feedback", "수고하셨습니다!"),
        "user_answer": user_answer,
        "correct_answer": _ensure_latex_wrapped(correct_answer),
        "solution": solution,
        "step_evaluations": step_evals,
    }


class TutorReplyStr(str):
    """문자열(str)과 100% 호환되면서 점수 정정 승인 여부(grant_full_score) 속성을 함께 전달하는 래퍼"""
    grant_full_score: bool = False


# ---------------------------------------------------------------------------
# 4. [2단계 킬러 기능] 방금 푼 문제에 대해 AI 선생님께 이어서 질문하기 (1:1 튜터 채팅)
# ---------------------------------------------------------------------------
def ask_math_ai_tutor(
    question: str,
    user_answer: str,
    correct_answer: str,
    solution: str,
    user_message: str,
    grade: int = 4,
    unit: str = "",
    topic: str = "",
    chat_history: Optional[List[Dict[str, Any]]] = None,
    is_solution_revealed: bool = True,
) -> TutorReplyStr:
    """
    학생이 푼 문제에 대해 추가 질문을 하면, 문제 문맥과 이전 대화 내역을 바탕으로
    초등학생 눈높이에 맞춰 친절하게 설명해 주는 AI 튜터 응답 생성 함수입니다.
    - 출제 오류나 억울한 오답임이 수학적으로 확인되면 grant_full_score = True를 함께 반환합니다.
    """
    client = get_genai_client()

    history_lines = []
    for msg in (chat_history or [])[-8:]:
        role = msg.get("role", "")
        speaker = "학생" if role in ("student", "user") else "AI 선생님"
        history_lines.append(f"{speaker}: {msg.get('content', '')}")
    history_text = "\n".join(history_lines) if history_lines else "(첫 질문입니다)"

    spoiler_rule = (
        "현재 학생이 아직 정답을 맞히지 못했고 해설도 열람하기 전입니다. 최종 정답 수치를 직접 말하지 말고 스스로 풀 수 있도록 친절한 징검다리 힌트와 개념 설명만 해주세요!"
        if not is_solution_revealed
        else "학생이 이미 정답(또는 부분 점수)을 맞혔거나 해설을 확인한 상태이므로, 수식과 계산 원리를 단계별로 알기 쉽게 설명해 주세요."
    )

    tutor_prompt = f"""당신은 초등학교 {grade}학년 학생을 1:1로 가르치는 다정하고 친절한 초등수학 AI 선생님입니다.
학생이 방금 푼 수학 문제에 대해 궁금한 점을 질문했습니다.

[문제 정보]
- 단원/주제: {unit} / {topic}
- 문제 지문: {question}
- 학생이 제출했던 답안: {user_answer}
- 실제 정답: {correct_answer}
- 모범 해설: {solution}

[이전 대화 기록]
{history_text}

[학생의 새 질문]
{user_message}

[답변 작성 지침]
1. 초등학교 {grade}학년 학생이 이해하기 쉬운 다정한 말투(~해요, ~해 볼까요?)로 2~4문장 이내로 명확하게 설명하세요.
2. {spoiler_rule}
3. 분수나 수식을 쓸 때는 화면에서 예쁘게 표시되도록 반드시 `$\\frac{{1}}{{2}}$`처럼 앞뒤를 `$` 기호로 감싸서 작성하세요.
4. [독립 검산 및 출제 오류·부분점수·정답 정정 권한]:
   - 만약 학생이 '보기에 정답이 없어요', '계산 결과가 이상해요', '제 답도 맞지 않나요?', '풀이 과정 맞았는데 부분점수 주세요'라고 컴플레인이나 이의제기를 하면, 기존 [실제 정답]이나 [모범 해설]을 무조건 맹신하여 억지로 끼워 맞추지 마세요!
   - 반드시 **[문제 지문]의 조건과 숫자로 직접 다시 계산 및 검산**해 보세요.
   - 검산 결과:
     (A) **출제 오류**: 문제 지문 조건대로 계산한 진짜 답이 보기에 없거나 등록된 정답과 다른 출제 오류를 학생이 지적한 경우
     (B) **정답 인정**: 학생의 답안이 수학적으로 올바른 정답인데(기약분수/대분수 표기 차이, 단위 생략, 동의 표현 등) 억울하게 오답 처리된 경우
     (C) **부분점수 인정**: 서술형 풀이 과정의 핵심 단계나 논리가 맞았는데 감점/0점 처리되어 부분점수 요구가 타당한 경우
   - 위 (A), (B), (C) 중 하나라도 해당하면, 학생에게 정직하게 오류/타당성을 인정하고 점수를 정정해 주겠다고 칭찬한 뒤, 답변 맨 마지막 줄 끝에:
     - 만점으로 정정할 경우: `[SCORE_UPGRADE_APPROVED]`
     - 특정 부분점수로 정정할 경우: `[SCORE_UPGRADE_APPROVED: 점수]` (예: `[SCORE_UPGRADE_APPROVED: 3]`)
     태그를 정확히 붙이세요.
   - (주의: 단순 질문이거나, 학생의 풀이/계산이 명백히 틀렸거나, 근거 없이 점수만 떼쓰는 경우에는 절대 태그를 붙이지 마세요!)
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=tutor_prompt,
        config={"temperature": 0.25},
    )
    raw_reply = (response.text or "").strip()
    grant_score = False
    target_score = None

    import re
    m = re.search(r"\[SCORE_UPGRADE_APPROVED(?::\s*(\d+))?\]", raw_reply)
    if m:
        grant_score = True
        if m.group(1):
            try:
                target_score = int(m.group(1))
            except Exception:
                target_score = None
        raw_reply = re.sub(r"\[SCORE_UPGRADE_APPROVED(?::\s*\d+)?\]", "", raw_reply).strip()

    cleaned_reply = _clean_display_text(raw_reply) or "좋은 질문이에요! 문제의 조건을 차근차근 다시 살펴보며 함께 풀어볼까요?"
    res_str = TutorReplyStr(cleaned_reply)
    res_str.grant_full_score = grant_score
    res_str.target_score = target_score
    return res_str




