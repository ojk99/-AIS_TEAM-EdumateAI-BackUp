from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from .curriculum_parser import get_curriculum_tree_for_ui
    from .service import generate_math_quiz, grade_math_submission, ask_math_ai_tutor
    from .quiz_logs import (
        init_math_db,
        get_or_create_user,
        save_or_update_quiz_log,
        get_user_quiz_logs_for_custom,
        toggle_favorite_log,
        append_chat_message,
        get_quiz_log_by_id,
        grant_full_score_by_tutor,
        get_user_study_history,
    )
    from app.database.quiz_manager import (
        login_account,
        register_account,
        create_temp_account,
        update_account_profile,
        list_all_accounts,
        reset_account_password,
        delegate_sub_admin,
        get_ranking_list,
        get_user_subject_score,
    )
    from .question_bank import (
        init_question_bank_db,
        get_all_subjects_question_bank_meta,
        add_question_to_bank,
        save_quiz_log_to_bank,
        list_question_bank,
        delete_question_from_bank,
        get_unit_bank_stats,
        pick_unsolved_bank_question,
        mark_bank_question_solved,
        grade_bank_question_by_ai,
    )
except ImportError:
    import sys
    _root_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(_root_dir) not in sys.path:
        sys.path.insert(0, str(_root_dir))
    from curriculum_parser import get_curriculum_tree_for_ui
    from service import generate_math_quiz, grade_math_submission, ask_math_ai_tutor
    from quiz_logs import (
        init_math_db,
        get_or_create_user,
        save_or_update_quiz_log,
        get_user_quiz_logs_for_custom,
        toggle_favorite_log,
        append_chat_message,
        get_quiz_log_by_id,
        grant_full_score_by_tutor,
        get_user_study_history,
    )
    from app.database.quiz_manager import (
        login_account,
        register_account,
        create_temp_account,
        update_account_profile,
        list_all_accounts,
        reset_account_password,
        delegate_sub_admin,
        get_ranking_list,
        get_user_subject_score,
    )
    from question_bank import (
        init_question_bank_db,
        get_all_subjects_question_bank_meta,
        add_question_to_bank,
        save_quiz_log_to_bank,
        list_question_bank,
        delete_question_from_bank,
        get_unit_bank_stats,
        pick_unsolved_bank_question,
        mark_bank_question_solved,
        grade_bank_question_by_ai,
    )

# 서버 로드 시 통합 SQLite DB 및 문제은행 DB(question_bank.db) 자동 초기화
init_math_db()
init_question_bank_db()

# ---------------------------------------------------------------------------
# 1. 과목 전용 FastAPI APIRouter 정의 (guideline.txt 표준 규격)
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/math", tags=["초등수학"])


# ---------------------------------------------------------------------------
# 2. 입출력 Pydantic DTO (Schemas)
# ---------------------------------------------------------------------------
class UserProfileRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="학생 아이디")
    user_name: str = Field(default="김에듀", description="학생 이름")
    grade: Optional[int] = Field(default=None, description="학생 학년 (1~6)")
    pokemon_type: Optional[str] = Field(default=None, description="포켓몬 진화 타입 (grass/fire/water/electric/psychic)")
    custom_skin_stage: Optional[int] = Field(default=None, description="커스텀 외형 스킨 단계 (1~9, 0은 해제)")


class LoginRequest(BaseModel):
    user_id: str = Field(..., description="로그인 아이디 (마스터: master)")
    password: str = Field(..., description="비밀번호 (마스터: 1111)")


class RegisterRequest(BaseModel):
    user_id: str = Field(..., description="사용할 아이디 (2자 이상)")
    password: str = Field(..., description="비밀번호 (4자 이상)")
    password_confirm: str = Field(..., description="비밀번호 확인")
    user_name: str = Field(..., description="학생 이름")
    grade: int = Field(default=4, description="학생 학년 (1~6)")
    guest_id: Optional[str] = Field(default=None, description="이관할 비회원 게스트 세션 아이디")



class CreateAccountRequest(BaseModel):
    user_id: str = Field(..., description="생성할 임시 아이디")
    password: str = Field(..., description="생성할 비밀번호")
    user_name: str = Field(..., description="학생 이름")
    grade: int = Field(default=4, description="학생 학년 (1~6)")


class UpdateProfileRequest(BaseModel):
    current_user_id: str = Field(default="guest", description="현재 아이디")
    current_user_name: str = Field(default="김에듀", description="현재 이름")
    current_password: Optional[str] = Field(default=None, description="현재 비밀번호 확인")
    new_user_id: Optional[str] = Field(default=None, description="변경할 새 아이디")
    new_password: Optional[str] = Field(default=None, description="변경할 새 비밀번호")
    new_password_confirm: Optional[str] = Field(default=None, description="새 비밀번호 확인")
    new_user_name: str = Field(..., description="변경할 새 이름")
    new_grade: Optional[int] = Field(default=4, description="변경할 새 학년 (1~6)")


class QuizGenerateRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="학생 아이디 (DB 조회용)")
    user_name: str = Field(default="김에듀", description="학생 이름 (DB 조회용)")
    mode: str = Field(default="custom", description="출제 모드 ('custom': 맞춤문제, 'manual': 직접선택)")
    ai_mode: bool = Field(default=True, description="AI 기반 출제 토글 (True: AI 실시간 생성, False: 문제은행 출제)")
    grade: Optional[int] = Field(default=None, description="학생 학년 (1~6)")
    grade_group: Optional[str] = Field(default=None, description="학년군 ('1~2학년군', '3~4학년군', '5~6학년군')")
    unit: Optional[str] = Field(default=None, description="대단원명 (예: '(1) 수와 연산')")
    topic: Optional[str] = Field(default=None, description="세부 주제명")
    difficulty: Optional[str] = Field(default="랜덤", description="난이도 ('하', '중', '상', '랜덤')")
    question_type: Optional[str] = Field(default="랜덤", description="문제 유형 ('ox', '객관식', '단답형', '단답형 주관식 2', '서술형', '랜덤')")
    quiz_logs: Optional[List[Dict[str, Any]]] = Field(default=None, description="과거 학습 오답 로그 (맞춤형 분석용)")


class QuizGradeRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="학생 아이디")
    user_name: str = Field(default="김에듀", description="학생 이름")
    quiz_id: str = Field(default="", description="문제 고유 ID (재제출 시 차액 점수 갱신용)")
    bank_id: Optional[int] = Field(default=None, description="문제은행 출처 문제 번호 (정답 시 맞춘 문제 카운트 갱신용)")
    grade: int = Field(default=4, description="학생 학년 (1~6)")
    grade_group: str = Field(default="3~4학년군", description="학년군")
    unit: str = Field(default="(1) 수와 연산", description="대단원명")
    topic: str = Field(default="", description="세부 주제명")
    question_type: str = Field(..., description="문제 유형 ('ox', '객관식', '단답형', '단답형 주관식 2', '서술형')")
    difficulty: str = Field(default="중", description="문제 난이도 ('하', '중', '상')")
    score: int = Field(default=3, description="문제 기본 배점 (1, 3, 5)")
    options: Optional[List[Any]] = Field(default=None, description="객관식 보기 목록 (텍스트 또는 미니 그리드 객체)")
    visual_data: Optional[Any] = Field(default=None, description="표/격자/그래프 시각 자료")
    direction_footer: Optional[str] = Field(default="", description="단답형 주관식 2 방향 라벨")
    user_answer: str = Field(..., description="학생이 제출한 답안 문자열")
    correct_answer: str = Field(..., description="문제의 정답")
    solution: str = Field(default="", description="문제 해설 및 모범 풀이")
    question: str = Field(default="", description="문제 지문 본문")
    rubric: Optional[List[Dict[str, Any]]] = Field(default=None, description="서술형 단계별 채점 기준표")
    is_solution_revealed: bool = Field(default=False, description="해설 열람 후 제출 여부 (열람 후에는 점수 미반영)")
    is_review_mode: bool = Field(default=False, description="기풀이 문제 복습 출제 여부 (True이면 누적 포인트 미반영)")


class TutorChatRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="학생 아이디")
    log_id: Optional[int] = Field(default=None, description="DB에 저장된 문제 풀이 로그 ID")
    message: Optional[str] = Field(default=None, description="학생이 AI 선생님께 질문한 내용")
    user_question: Optional[str] = Field(default=None, description="학생 질문(프론트엔드 호환 키)")
    user_name: Optional[str] = Field(default="김에듀", description="학생 이름")
    quiz_id: Optional[str] = Field(default=None, description="문제 고유 ID")
    grade: Optional[int] = Field(default=4, description="학생 학년")
    unit: Optional[str] = Field(default="", description="단원명")
    topic: Optional[str] = Field(default="", description="주제명")
    question: Optional[str] = Field(default="", description="문제 지문")
    user_answer: Optional[str] = Field(default="", description="학생 제출 답안")
    correct_answer: Optional[str] = Field(default="", description="정답")
    solution: Optional[str] = Field(default="", description="해설")
    is_solution_revealed: bool = Field(default=True, description="정답/해설 공개 상태 여부")


class FavoriteToggleRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="학생 아이디")
    log_id: Optional[int] = Field(default=None, description="DB에 저장된 문제 풀이 로그 ID")
    user_name: Optional[str] = Field(default=None, description="학생 이름 (폴백 조회용)")
    quiz_id: Optional[str] = Field(default=None, description="문제 고유 ID (폴백 조회용)")
    is_favorite: Optional[bool] = Field(default=None, description="즐겨찾기 상태 (None이면 토글)")


class AdminResetPasswordRequest(BaseModel):
    user_id: str = Field(..., description="비밀번호를 초기화할 대상 학생 아이디")
    new_password: Optional[str] = Field(default="0000", description="초기화할 비밀번호 (기본값: 0000)")


class DelegateSubAdminRequest(BaseModel):
    user_id: str = Field(..., description="부관리자 권한을 위임/수정할 대상 회원 아이디")
    subjects: List[str] = Field(default_factory=list, description="위임할 과목 목록 (korean, math, english, social, science, hanja)")


class QuestionBankAddRequest(BaseModel):
    user_id: str = Field(..., description="저장 요청자 아이디 (총 관리자 또는 부관리자)")
    subject: str = Field(..., description="과목 코드 (korean, math, english, social, science, hanja)")
    grade_group: str = Field(default="3~4학년군", description="학년군 또는 단계")
    unit_name: str = Field(..., description="대단원명")
    sub_topic: Optional[str] = Field(default="", description="하위 주제명")
    question_type: str = Field(..., description="문제 유형 (ox, 객관식, 단답형, 단답형 주관식 2, 서술형)")
    difficulty: str = Field(default="중", description="난이도 (하, 중, 상)")
    question_text: str = Field(..., description="문제 지문")
    choices: Optional[List[Any]] = Field(default_factory=list, description="객관식 보기 목록")
    visual_data: Optional[Any] = Field(default=None, description="표/격자/그래프 시각 자료")
    direction_footer: Optional[str] = Field(default="", description="단답형 주관식 2 방향 라벨")
    rubric: Optional[List[Dict[str, Any]]] = Field(default=None, description="서술형 채점 기준")
    correct_answer: str = Field(..., description="정답")
    explanation: Optional[str] = Field(default="", description="해설 및 모범 답안")
    grade: Optional[int] = Field(default=None, description="대상 학년 (1~6)")


class QuestionBankFromLogRequest(BaseModel):
    user_id: str = Field(..., description="저장 요청자 아이디 (총 관리자 또는 부관리자)")
    log_id: int = Field(..., description="문제풀이 DB 로그 ID (quiz_logs.id)")


class QuestionBankDeleteRequest(BaseModel):
    user_id: str = Field(..., description="삭제 요청자 아이디 (총 관리자 또는 부관리자)")
    bank_id: int = Field(..., description="삭제할 문제은행 번호 (question_bank.id)")


# ---------------------------------------------------------------------------
# 3. 라우터 엔드포인트 구현
# ---------------------------------------------------------------------------
@router.post("/login", summary="로그인 (마스터 관리자: master/1111 및 학생 임시 계정)")
async def login(req: LoginRequest):
    """아이디와 비밀번호로 로그인하고 학생/관리자 프로필 및 점수를 반환합니다."""
    try:
        user_data = login_account(user_id=req.user_id, password=req.password)
        return {"status": "success", "user": user_data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그인 처리 실패: {str(e)}")


@router.post("/register", summary="학생 신규 회원가입 (비회원 풀이기록 안전 이관 지원)")
async def register(req: RegisterRequest):
    """학생이 아이디, 비번, 비번확인, 이름, 학년으로 직접 회원가입합니다."""
    try:
        user_data = register_account(
            user_id=req.user_id,
            password=req.password,
            password_confirm=req.password_confirm,
            user_name=req.user_name,
            grade=req.grade,
            guest_id=req.guest_id,
        )
        return {"status": "success", "message": "회원가입이 완료되었습니다!", "user": user_data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원가입 처리 실패: {str(e)}")


@router.post("/guest/clear", summary="비회원 로그아웃 시 임시 문제풀이 기록 증발(삭제)")
async def clear_guest(req: Dict[str, Any]):
    """비회원 체험 중 풀었던 임시 로그를 로그아웃 시 완전 삭제합니다."""
    try:
        from app.database.quiz_manager import clear_guest_logs
        guest_id = str(req.get("guest_id") or "").strip()
        deleted = clear_guest_logs(guest_id)
        return {"status": "success", "deleted": deleted}
    except Exception as e:
        return {"status": "success", "deleted": 0}



@router.get("/admin/accounts", summary="[총 관리자 전용] 등록된 전체 계정 및 학생 학습 현황 조회")
async def get_admin_accounts():
    """총 관리자 탭에서 전체 계정 목록과 점수/풀이 수를 조회합니다."""
    try:
        accounts = list_all_accounts()
        return {"status": "success", "accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계정 목록 조회 실패: {str(e)}")


@router.post("/admin/create-account", summary="[총 관리자 전용] 학생용 임시 아이디 생성")
async def create_admin_account(req: CreateAccountRequest):
    """총 관리자가 새로운 임시 아이디(비밀번호, 이름, 학년 포함)를 생성합니다."""
    try:
        created = create_temp_account(
            new_user_id=req.user_id,
            new_password=req.password,
            user_name=req.user_name,
            grade=req.grade,
        )
        accounts = list_all_accounts()
        return {"status": "success", "created": created, "accounts": accounts}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임시 아이디 생성 실패: {str(e)}")


@router.post("/admin/reset-password", summary="[총 관리자 전용] 회원 비밀번호 '0000' 초기화")
async def admin_reset_password(req: AdminResetPasswordRequest):
    """총 관리자가 특정 학생 계정의 비밀번호를 기본값('0000')으로 초기화합니다."""
    try:
        success = reset_account_password(user_id=req.user_id, new_password=req.new_password or "0000")
        if not success:
            raise HTTPException(status_code=400, detail="비밀번호 초기화 실패: 대상 아이디가 존재하지 않거나 관리자 계정입니다.")
        accounts = list_all_accounts()
        return {
            "status": "success",
            "message": f"아이디 '{req.user_id}' 계정의 비밀번호가 '0000'으로 초기화되었습니다.",
            "accounts": accounts,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비밀번호 초기화 실패: {str(e)}")


@router.post("/admin/delegate-sub-admin", summary="[총 관리자 전용] 회원별 부관리자 과목 권한 위임/해제")
async def admin_delegate_sub_admin(req: DelegateSubAdminRequest):
    """총 관리자가 특정 회원에게 국, 수, 영, 사, 과, 한자 과목 부관리자 권한을 위임하거나 해제합니다."""
    try:
        updated = delegate_sub_admin(user_id=req.user_id, subjects=req.subjects)
        accounts = list_all_accounts()
        return {
            "status": "success",
            "message": f"'{updated['user_name']}({updated['user_id']})' 회원의 권한이 [{updated['role_display']}](으)로 설정되었습니다.",
            "updated": updated,
            "accounts": accounts,
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"부관리자 위임 실패: {str(e)}")


@router.get("/question-bank/meta", summary="과목별 문제은행 드롭트리(단원/하위주제/문제유형/난이도) 메타데이터 조회")
async def math_question_bank_meta(user_id: Optional[str] = None):
    try:
        meta = get_all_subjects_question_bank_meta(user_id=user_id)
        return {"status": "success", **meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 메타데이터 조회 실패: {str(e)}")


@router.get("/question-bank/list", summary="문제은행 저장 문제 목록 조회")
async def math_question_bank_list(
    user_id: Optional[str] = None,
    subject: Optional[str] = None,
    grade_group: Optional[str] = None,
    unit_name: Optional[str] = None,
    question_type: Optional[str] = None,
    limit: int = 200,
):
    try:
        items = list_question_bank(
            user_id=user_id,
            subject=subject,
            grade_group=grade_group,
            unit_name=unit_name,
            question_type=question_type,
            limit=limit,
        )
        return {"status": "success", "count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 목록 조회 실패: {str(e)}")


@router.post("/question-bank/add", summary="[총 관리자/부관리자] 문제은행에 수동 문제 추가")
async def math_question_bank_add(req: QuestionBankAddRequest):
    try:
        saved = add_question_to_bank(
            user_id=req.user_id,
            subject=req.subject,
            grade_group=req.grade_group,
            unit_name=req.unit_name,
            sub_topic=req.sub_topic or "",
            question_type=req.question_type,
            difficulty=req.difficulty,
            question_text=req.question_text,
            correct_answer=req.correct_answer,
            choices=req.choices or [],
            explanation=req.explanation or "",
            grade=req.grade,
            source_type="manual",
            visual_data=req.visual_data,
            direction_footer=req.direction_footer or "",
            rubric=req.rubric,
        )
        return {"status": "success", "item": saved, "message": saved.get("message", "저장 완료")}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 저장 실패: {str(e)}")


@router.post("/question-bank/from-log", summary="[총 관리자/부관리자] 문제풀이 DB 로그에서 문제은행으로 즉시 저장")
async def math_question_bank_from_log(req: QuestionBankFromLogRequest):
    try:
        saved = save_quiz_log_to_bank(log_id=req.log_id, user_id=req.user_id)
        return {"status": "success", "item": saved, "message": saved.get("message", "문제은행 저장 완료")}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 문제은행 저장 실패: {str(e)}")


@router.post("/question-bank/delete", summary="[총 관리자/부관리자] 문제은행 문제 삭제")
async def math_question_bank_delete(req: QuestionBankDeleteRequest):
    try:
        deleted = delete_question_from_bank(bank_id=req.bank_id, user_id=req.user_id)
        return {"status": "success", **deleted}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 삭제 실패: {str(e)}")


@router.get("/question-bank/unit-stats", summary="과목/단원별 문제은행 맞춘 문제 및 전체/남은 문제 현황 조회")
async def math_question_bank_unit_stats(
    subject: str = "math",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
):
    try:
        stats = get_unit_bank_stats(subject=subject, user_id=user_id, user_name=user_name)
        return {"status": "success", "stats": stats, "bank_stats": stats, **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"단원별 문제은행 현황 조회 실패: {str(e)}")


@router.get("/ranking", summary="로비 포탈 및 플랫폼 실시간 랭킹 (1~10위)")
async def ranking(limit: int = 10):
    """전 과목 누적 점수 상위 1~10위 학생들의 랭킹 정보를 반환합니다."""
    try:
        data = get_ranking_list(limit=limit)
        return {"status": "success", "ranking": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랭킹 조회 실패: {str(e)}")


@router.post("/profile/update", summary="개인정보(학생 이름, 비번, 학년) 변경 및 DB 동기화")
async def update_profile(req: UpdateProfileRequest):
    """회원(마스터 관리자 포함)이 본인의 아이디, 비밀번호, 이름, 학년을 직접 변경하고 누적 점수 및 풀이 기록을 승계합니다."""
    if req.new_password and req.new_password_confirm and req.new_password != req.new_password_confirm:
        raise HTTPException(status_code=400, detail="새 비밀번호와 비밀번호 확인이 일치하지 않습니다.")
    try:
        user_data = update_account_profile(
            current_user_id=req.current_user_id,
            current_user_name=req.current_user_name,
            new_user_id=req.new_user_id,
            new_password=req.new_password,
            new_user_name=req.new_user_name,
            new_grade=req.new_grade,
            current_password=req.current_password,
        )
        return {"status": "success", "user": user_data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"개인정보 변경 실패: {str(e)}")


@router.get("/user", summary="학생 프로필(이름, 학년, 포켓몬 타입) 및 DB 누적 총점 조회")
async def get_user_info(
    user_name: str = "김에듀",
    pokemon_type: Optional[str] = None,
    custom_skin_stage: Optional[int] = None,
    user_id: Optional[str] = None,
):
    """DB(quiz_logs)에 저장된 학생의 학년과 영구 누적 총점 및 포켓몬 진화 등급을 조회합니다."""
    try:
        # GET 조회 시에는 클라이언트의 기본값(풀타입 등)으로 DB 속성을 덮어쓰지 않도록 안전 조회
        user_data = get_or_create_user(user_name=user_name, pokemon_type=None, custom_skin_stage=None, user_id=user_id)
        return {"status": "success", "user": user_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학생 정보 조회 실패: {str(e)}")


@router.post("/user", summary="학생 프로필(이름, 학년, 포켓몬 타입) 변경 및 DB 저장")
async def update_user_info(req: UserProfileRequest):
    """학생 이름, 학년(1~6학년), 포켓몬 진화 타입을 변경하여 저장하고 누적 총점을 반환합니다."""
    try:
        user_data = get_or_create_user(
            user_name=req.user_name,
            grade=req.grade,
            pokemon_type=req.pokemon_type,
            custom_skin_stage=req.custom_skin_stage,
            user_id=req.user_id,
        )
        return {"status": "success", "user": user_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학생 정보 저장 실패: {str(e)}")


@router.get("/curriculum", summary="학년군별 단원/주제 계층 트리 반환")
async def get_curriculum():
    """프론트엔드 동적 드롭다운(학년군 -> 대단원 -> 세부주제) 바인딩용 데이터"""
    try:
        data = get_curriculum_tree_for_ui()
        return {"status": "success", "curriculum": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"커리큘럼 로드 실패: {str(e)}")


@router.post("/generate", summary="초등수학 온디맨드 퀴즈 실시간 생성 (AI 출제 토글 및 문제은행 연동)")
async def generate_quiz(req: QuizGenerateRequest):
    """
    학년, 단원, 주제, 난이도, 유형에 따라 최적화된 초등수학 퀴즈를 생성합니다.
    - ai_mode=False(문제은행 출제 모드)일 때:
      1) 해당 단원에 남은 문제은행 문제가 있으면 문제은행(`question_bank.db`)에서 우선 출제
      2) 해당 단원에 문제은행 DB가 없거나 이미 다 풀어서 남은 문제가 없다면 자동으로 ai_mode=True(AI 출제)로 전환하여 출제!
    """
    try:
        user_info = get_or_create_user(req.user_name, req.grade, user_id=req.user_id)
        target_grade = req.grade or user_info["grade"]

        effective_gg = req.grade_group
        if not effective_gg or effective_gg == "custom":
            effective_gg = "1~2학년군" if target_grade <= 2 else ("3~4학년군" if target_grade <= 4 else "5~6학년군")

        auto_switched_to_ai = False
        auto_switched_to_bank = False
        auto_switch_reason = ""
        auto_switch_message = ""

        target_unit_for_bank = req.unit if req.mode != "custom" else "랜덤"
        target_topic_for_bank = req.topic if req.mode != "custom" else "랜덤"

        # 1) [문제은행 출제 모드 (토글 OFF)] 우선 처리
        if not req.ai_mode:
            bank_res = pick_unsolved_bank_question(
                subject="math",
                user_id=req.user_id,
                user_name=req.user_name,
                grade=target_grade,
                grade_group=effective_gg,
                unit_name=target_unit_for_bank,
                sub_topic=target_topic_for_bank,
                question_type=req.question_type,
                difficulty=req.difficulty,
                allow_solved_fallback=False,
            )
            if bank_res.get("found") and bank_res.get("quiz"):
                bank_stats = get_unit_bank_stats("math", req.user_id, req.user_name)
                return {
                    "status": "success",
                    "quiz": bank_res["quiz"],
                    "user": user_info,
                    "source": "question_bank",
                    "is_review_mode": False,
                    "auto_switched_to_ai": False,
                    "auto_switched_to_bank": False,
                    "bank_stats": bank_stats,
                }
            else:
                auto_switched_to_ai = True
                auto_switch_reason = bank_res.get("reason", "empty")
                auto_switch_message = bank_res.get(
                    "message",
                    "해당 단원에 남은 문제은행 문제가 없어 자동으로 'AI 기반 출제' 모드로 전환하여 출제합니다.",
                )

        # 2) [AI 기반 출제 모드 (토글 ON) 또는 문제은행 소진/부재로 AI 자동 전환된 경우]
        db_logs = get_user_quiz_logs_for_custom(req.user_name, limit=30, user_id=req.user_id)
        effective_logs = db_logs if db_logs else (req.quiz_logs or [])

        try:
            quiz_data = generate_math_quiz(
                mode=req.mode,
                grade=target_grade,
                grade_group=req.grade_group,
                unit=req.unit,
                topic=req.topic,
                difficulty=req.difficulty,
                question_type=req.question_type,
                quiz_logs=effective_logs,
            )
            quiz_data["source"] = "ai"
            quiz_data["is_review_mode"] = False
            bank_stats = get_unit_bank_stats("math", req.user_id, req.user_name)
            return {
                "status": "success",
                "quiz": quiz_data,
                "user": user_info,
                "source": "ai",
                "is_review_mode": False,
                "auto_switched_to_ai": auto_switched_to_ai,
                "auto_switched_to_bank": False,
                "auto_switch_reason": auto_switch_reason,
                "auto_switch_message": auto_switch_message,
                "bank_stats": bank_stats,
            }
        except Exception as ai_err:
            # 3) [역방향 폴백: AI 출제 연동 실패 시 -> 문제은행 DB 자동 출제 (미풀이 우선 -> 기풀이 복습 폴백 -> DB 비었으면 에러)]
            fallback_bank_res = pick_unsolved_bank_question(
                subject="math",
                user_id=req.user_id,
                user_name=req.user_name,
                grade=target_grade,
                grade_group=effective_gg,
                unit_name=target_unit_for_bank,
                sub_topic=target_topic_for_bank,
                question_type=req.question_type,
                difficulty=req.difficulty,
                allow_solved_fallback=True,
            )
            if fallback_bank_res.get("found") and fallback_bank_res.get("quiz"):
                is_review = bool(fallback_bank_res.get("is_review_mode", False))
                bank_stats = get_unit_bank_stats("math", req.user_id, req.user_name)
                if is_review:
                    fb_msg = (
                        "AI 출제 서버 연결이 원활하지 않고 해당 단원의 새 문제를 모두 해결하여, "
                        "이미 풀었던 문제은행 문제를 복습 모드로 출제합니다. (정답 시 추가 누적 포인트 미반영)"
                    )
                else:
                    fb_msg = "AI 출제 서버 연결이 원활하지 않아 자동으로 '문제은행 출제' 모드로 전환하여 미풀이 문제를 출제했습니다."

                return {
                    "status": "success",
                    "quiz": fallback_bank_res["quiz"],
                    "user": user_info,
                    "source": "question_bank",
                    "is_review_mode": is_review,
                    "auto_switched_to_ai": False,
                    "auto_switched_to_bank": True,
                    "auto_switch_reason": "ai_failed_review" if is_review else "ai_failed_unsolved",
                    "auto_switch_message": fb_msg,
                    "bank_stats": bank_stats,
                }

            # 해당 단원 문제은행 DB도 아예 비어 있고(0/0), AI 출제도 실패한 경우 -> 에러 반환 (프론트엔드 에러창 표시)
            raise HTTPException(
                status_code=503,
                detail="현재 AI 출제 서버와 연결할 수 없으며, 선택한 단원의 문제은행 DB에도 등록된 문제가 없습니다.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"퀴즈 생성 실패: {str(e)}")


@router.post("/grade", summary="학생 답안 채점, 주관식/서술형 AI 문맥 평가 및 DB 영구 기록")
async def grade_quiz(req: QuizGradeRequest):
    """
    제출된 답안을 평가하고 결과를 SQLite DB(quiz_logs)에 영구 기록합니다.
    - 문제은행 출처 문제든 AI 출제 문제든 주관식(단답형)/서술형 모두 AI 문맥 채점이 동일하게 적용됩니다.
    - 문제은행 문제를 맞힌 경우 question_bank_solved에 기록하여 (맞춘 문제 / 전체 은행문제) 현황을 즉시 갱신합니다.
    - 이미 풀었던 문제은행 문제를 복습 모드(is_review_mode=True)로 다시 푼 경우 누적 포인트(added_score)는 0점으로 처리합니다.
    """
    try:
        grade_result = grade_math_submission(
            question_type=req.question_type,
            difficulty=req.difficulty,
            score=req.score,
            user_answer=req.user_answer,
            correct_answer=req.correct_answer,
            solution=req.solution,
            question=req.question,
            rubric=req.rubric,
            options=req.options,
        )

        # 문제은행 출처 문제이고 정답(만점)을 맞힌 경우 풀이 완료 처리
        resolved_bank_id = req.bank_id
        if not resolved_bank_id and req.quiz_id and req.quiz_id.startswith("bank_"):
            parts = req.quiz_id.split("_")
            if len(parts) >= 3 and parts[2].isdigit():
                resolved_bank_id = int(parts[2])

        if resolved_bank_id and bool(grade_result.get("is_correct", False)):
            mark_bank_question_solved(
                bank_id=int(resolved_bank_id),
                subject="math",
                user_id=req.user_id,
                user_name=req.user_name,
            )

        # DB에 풀이 로그 저장 및 학생 누적 총점(차액만) 업데이트 (복습 모드일 때는 점수 미반영)
        quiz_key = req.quiz_id or f"{req.question_type}_{req.question[:40]}"
        effective_no_score = bool(req.is_solution_revealed or req.is_review_mode)
        db_sync = save_or_update_quiz_log(
            user_name=req.user_name,
            quiz_id=quiz_key,
            grade=req.grade,
            unit=req.unit,
            topic=req.topic,
            difficulty=req.difficulty,
            question_type=req.question_type,
            question=req.question,
            user_answer=req.user_answer,
            correct_answer=grade_result.get("correct_answer", req.correct_answer),
            solution=grade_result.get("solution", req.solution),
            earned_score=grade_result.get("earned_score", 0),
            max_score=grade_result.get("max_score", req.score),
            is_correct=bool(grade_result.get("is_correct", False)),
            is_solution_revealed=effective_no_score,
            user_id=req.user_id,
            options=req.options,
            visual_data=req.visual_data,
            direction_footer=req.direction_footer,
            rubric=req.rubric,
        )

        grade_result["log_id"] = db_sync["log_id"]
        grade_result["added_score"] = 0 if req.is_review_mode else db_sync["added_score"]
        grade_result["best_score"] = db_sync["best_score"]
        grade_result["total_score"] = db_sync["total_score"]
        grade_result["level_info"] = db_sync.get("level_info")
        grade_result["is_review_mode"] = bool(req.is_review_mode)
        grade_result["bank_stats"] = get_unit_bank_stats("math", req.user_id, req.user_name)

        return {"status": "success", "result": grade_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"채점 처리 실패: {str(e)}")


@router.post("/chat", summary="[2단계] 방금 푼 문제에 대해 AI 선생님께 이어서 질문하기 (DB 영구 보존)")
async def chat_with_tutor(req: TutorChatRequest):
    """
    학생이 푼 문제에 대해 추가 질문을 하면 AI 선생님이 답변하고,
    질문과 답변 모두 quiz_logs 테이블의 chat_history 컬럼에 영구 저장합니다.
    """
    try:
        user_msg = (req.message or req.user_question or "").strip()
        if not user_msg:
            raise HTTPException(status_code=400, detail="질문 내용을 입력해 주세요.")

        log_data = get_quiz_log_by_id(
            log_id=req.log_id,
            user_name=req.user_name,
            quiz_id=req.quiz_id,
        )

        target_log_id = log_data["id"] if log_data else None

        # 1) DB 로그가 있으면 학생 질문 먼저 DB에 추가
        if target_log_id:
            append_chat_message(target_log_id, role="student", content=user_msg)

        # 2) AI 선생님 답변 생성 (DB 기록 또는 요청 폴백 데이터 사용)
        reply = ask_math_ai_tutor(
            question=(log_data["question"] if log_data else req.question) or "",
            user_answer=(log_data["user_answer"] if log_data else req.user_answer) or "",
            correct_answer=(log_data["correct_answer"] if log_data else req.correct_answer) or "",
            solution=(log_data["solution"] if log_data else req.solution) or "",
            user_message=user_msg,
            grade=int((log_data["grade"] if log_data else req.grade) or 4),
            unit=(log_data["unit"] if log_data else req.unit) or "",
            topic=(log_data["topic"] if log_data else req.topic) or "",
            chat_history=(log_data["chat_history"] if log_data else []),
            is_solution_revealed=req.is_solution_revealed,
        )

        # 3) AI 선생님이 출제 오류 또는 억울한 오답/부분점수 인정 시: DB 정답 및 점수 보상 정산 처리!
        score_upgrade_info = None
        if getattr(reply, "grant_full_score", False):
            target_sc = getattr(reply, "target_score", None)
            score_upgrade_info = grant_full_score_by_tutor(
                log_id=target_log_id,
                user_name=req.user_name,
                user_id=req.user_id,
                quiz_id=req.quiz_id,
                target_score=target_sc,
            )

        # 4) AI 선생님 답변 DB에 추가 후 전체 대화 기록 반환
        if target_log_id:
            updated_history = append_chat_message(target_log_id, role="teacher", content=str(reply))
        else:
            updated_history = [
                {"role": "student", "content": user_msg},
                {"role": "teacher", "content": str(reply)},
            ]

        res_payload = {
            "status": "success",
            "log_id": target_log_id,
            "reply": str(reply),
            "chat_history": updated_history,
        }
        if score_upgrade_info:
            res_payload["score_corrected"] = True
            res_payload["added_score"] = score_upgrade_info["added_score"]
            res_payload["best_score"] = score_upgrade_info["best_score"]
            res_payload["max_score"] = score_upgrade_info["max_score"]
            res_payload["total_score"] = score_upgrade_info["total_score"]
            res_payload["user_status"] = score_upgrade_info.get("user_status")

        return res_payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 선생님 질문 처리 실패: {str(e)}")


@router.post("/favorite", summary="[2단계] 문제 및 대화 내역 즐겨찾기(⭐) 저장/해제")
async def toggle_favorite(req: FavoriteToggleRequest):
    """특정 문제 풀이 기록(log_id)의 즐겨찾기(is_favorite) 상태를 토글하여 DB에 저장합니다."""
    try:
        fav_res = toggle_favorite_log(
            log_id=req.log_id,
            is_favorite=req.is_favorite,
            user_name=req.user_name,
            quiz_id=req.quiz_id,
        )
        return {"status": "success", **fav_res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"즐겨찾기 변경 실패: {str(e)}")


@router.get("/history", summary="[3단계] 내 공부 기록 및 즐겨찾기 모아보기 조회 (전과목/과목별/날짜별 필터)")
async def get_history(
    user_name: str = "김에듀",
    favorites_only: bool = False,
    subject: str = "all",
    target_date: Optional[str] = None,
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
):
    """학생이 과거에 푼 문제, 해설, AI 선생님과의 질문 대화 내역을 전과목 또는 선택한 과목별, 날짜별로 최신순 전체 조회합니다."""
    try:
        items = get_user_study_history(
            user_name=user_name,
            favorites_only=favorites_only,
            subject_filter=subject,
            target_date=target_date,
            limit=limit,
            user_id=user_id,
        )
        subj_score = get_user_subject_score(user_name=user_name, subject=subject, user_id=user_id)
        tot_score = get_user_subject_score(user_name=user_name, subject="all", user_id=user_id)
        return {
            "status": "success",
            "count": len(items),
            "history": items,
            "subject": subject,
            "subject_score": subj_score,
            "total_score": tot_score,
            "target_date": target_date,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"공부 기록 조회 실패: {str(e)}")


@router.get("/logo.svg", summary="EduMate AI 공식 로고 이미지")
async def math_logo_svg():
    current_dir = Path(__file__).resolve().parent
    for candidate in [
        current_dir.parent.parent.parent / "web" / "static" / "edumate_logo.svg",
        current_dir.parent.parent.parent / "sample" / "edumate_logo.svg",
    ]:
        if candidate.exists():
            return FileResponse(str(candidate), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="edumate_logo.svg 파일을 찾을 수 없습니다.")


@router.get("/", summary="초등수학 전용 웹 화면 제공")
@router.get("/ui", summary="초등수학 전용 웹 화면 제공 (별칭)")
async def math_ui():
    """초등수학 퀴즈 풀이 및 피드백 전용 웹 인터페이스 서빙 (브라우저 캐시 방지 헤더 적용)"""
    html_path = Path(__file__).resolve().parent / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="index.html 파일을 찾을 수 없습니다.")
    return FileResponse(
        str(html_path),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ---------------------------------------------------------------------------
# 4. 단독 테스트 실행 블록 (guideline.txt [261008 추가지시사항] 표준 템플릿)
# ---------------------------------------------------------------------------
# 단독 실행용 FastAPI 인스턴스 (uvicorn router:app 및 python router.py 모두 지원)
app = FastAPI(title="EduMate AI - [초등수학] 단독 테스트 서버")
app.include_router(router)

# 단독 테스트 시에도 포켓몬 이미지(webp) 등 정적 파일(/static) 정상 서빙 지원
from fastapi.staticfiles import StaticFiles
_project_root = Path(__file__).resolve().parent.parent.parent.parent
_static_dir = _project_root / "web" / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root_page():
    return FileResponse(
        str(Path(__file__).resolve().parent / "index.html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


if __name__ == "__main__":
    import os
    import subprocess
    import uvicorn
    import webbrowser

    PORT = 8000

    # [자동 포트 클리너] python router.py 실행 시 8000번 포트를 점유 중인 이전 서버 프로세스를 자동으로 정리합니다.
    # 이제 별도의 taskkill 명령어 없이 'python router.py'만 실행해도 언제나 최신 코드가 100% 반영됩니다!
    current_pid = os.getpid()
    try:
        out = subprocess.check_output(f"netstat -ano | findstr :{PORT}", shell=True, text=True)
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                old_pid = int(parts[-1])
                if old_pid != current_pid and old_pid > 0:
                    subprocess.run(
                        f"taskkill /F /PID {old_pid}",
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
    except Exception:
        pass

    print(f"\n[초등수학] 단독 서버 시작 (기존 8000번 포트 자동 정리 완료): http://localhost:{PORT}/\n")
    webbrowser.open(f"http://localhost:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
