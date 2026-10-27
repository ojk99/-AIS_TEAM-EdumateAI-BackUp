"""
================================================================================
[EduMate AI 공통 플랫폼 관제 라우터 - app/routers/platform.py]
================================================================================
- 가이드라인 표준 디렉터리 아키텍처(app/routers/)에 따른 플랫폼 공통 관제 라우터입니다.
- 개별 과목(math, korean 등)과 분리된 플랫폼 레벨의 중앙 API를 제공합니다:
  1) /api/ranking : 로비 포탈 실시간 전과목 랭킹 (1~10위)
  2) /admin/accounts : [마스터 관리자 전용] 등록된 전체 계정 및 학습 현황
  3) /admin/create-account : [마스터 관리자 전용] 임시 아이디 생성
  4) /admin/reset-password : [마스터 관리자 전용] 회원 비밀번호 '0000' 초기화
  5) /api/login : 통합 로그인
  6) /api/profile/update : 일반 회원 개인정보(아이디, 비번, 이름, 학년) 직접 변경
  7) /api/user : 학생 프로필 및 전 과목 통합 누적 점수/포켓몬 등급 조회
================================================================================
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.quiz_manager import (
    init_control_db,
    get_or_create_user,
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
from app.database.question_bank_manager import (
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

# 서버 시작 시 관제탑 DB 및 문제은행 DB 자동 초기화
init_control_db()
init_question_bank_db()

router = APIRouter(tags=["플랫폼 공통 관제"])


# ---------------------------------------------------------------------------
# Pydantic DTO (Schemas)
# ---------------------------------------------------------------------------
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
    unit_name: Optional[str] = Field(default="", description="단원명 (영어는 빈 문자열 허용)")
    sub_topic: Optional[str] = Field(default="", description="하위 주제명 (국어/영어/사회/과학은 빈 문자열 허용)")
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


class UpdateProfileRequest(BaseModel):
    current_user_id: str = Field(default="guest", description="현재 아이디")
    current_user_name: str = Field(default="김에듀", description="현재 이름")
    current_password: Optional[str] = Field(default=None, description="현재 비밀번호 확인")
    new_user_id: Optional[str] = Field(default=None, description="변경할 새 아이디")
    new_password: Optional[str] = Field(default=None, description="변경할 새 비밀번호")
    new_password_confirm: Optional[str] = Field(default=None, description="새 비밀번호 확인")
    new_user_name: str = Field(..., description="변경할 새 이름")
    new_grade: Optional[int] = Field(default=4, description="변경할 새 학년 (1~6)")


class UserProfileRequest(BaseModel):
    user_name: str = Field(default="김에듀", description="학생 이름")
    grade: Optional[int] = Field(default=None, description="학생 학년 (1~6)")
    pokemon_type: Optional[str] = Field(default=None, description="포켓몬 진화 타입 (grass/fire/water/electric/psychic)")
    custom_skin_stage: Optional[int] = Field(default=None, description="커스텀 외형 스킨 단계 (1~9, 0은 해제)")


# ---------------------------------------------------------------------------
# 엔드포인트 구현
# ---------------------------------------------------------------------------
@router.get("/api/ranking", summary="로비 포탈 실시간 랭킹 (1~10위)")
async def api_ranking(limit: int = 10):
    """전 과목 통합 누적 점수 상위 1~10위 학생들의 랭킹 정보를 반환합니다."""
    try:
        data = get_ranking_list(limit=limit)
        return {"status": "success", "ranking": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"랭킹 조회 실패: {str(e)}")


@router.post("/api/register", summary="학생 신규 회원가입 (비회원 풀이기록 안전 이관 지원)")
async def api_register(req: RegisterRequest):
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


@router.post("/api/guest/clear", summary="비회원 로그아웃 시 임시 문제풀이 기록 증발(삭제)")
async def api_clear_guest(req: Dict[str, Any]):
    """비회원 체험 중 풀었던 임시 로그를 로그아웃 시 완전 삭제합니다."""
    try:
        from app.database.quiz_manager import clear_guest_logs
        guest_id = str(req.get("guest_id") or "").strip()
        deleted = clear_guest_logs(guest_id)
        return {"status": "success", "deleted": deleted}
    except Exception as e:
        return {"status": "success", "deleted": 0}


@router.post("/api/login", summary="통합 로그인")
async def api_login(req: LoginRequest):
    """아이디와 비밀번호로 로그인하고 학생/관리자 프로필 및 점수를 반환합니다."""
    try:
        user_data = login_account(user_id=req.user_id, password=req.password)
        return {"status": "success", "user": user_data}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그인 처리 실패: {str(e)}")


@router.get("/admin/accounts", summary="[총 관리자 전용] 등록된 전체 계정 및 학습 현황 조회")
async def get_admin_accounts():
    """총 관리자가 등록된 전체 계정 목록과 학습 점수를 조회합니다."""
    try:
        accounts = list_all_accounts()
        return {"status": "success", "accounts": accounts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계정 목록 조회 실패: {str(e)}")


@router.post("/admin/create-account", summary="[총 관리자 전용] 학생용 임시 아이디 생성")
async def create_admin_account(req: CreateAccountRequest):
    """총 관리자가 새로운 학생용 임시 계정을 생성합니다."""
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


@router.get("/api/question-bank/meta", summary="과목별 문제은행 드롭트리(단원/하위주제/문제유형/난이도) 메타데이터 조회")
async def api_question_bank_meta(user_id: Optional[str] = None):
    try:
        meta = get_all_subjects_question_bank_meta(user_id=user_id)
        return {"status": "success", **meta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 메타데이터 조회 실패: {str(e)}")


@router.get("/api/question-bank/list", summary="문제은행 저장 문제 목록 조회")
async def api_question_bank_list(
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


@router.post("/api/question-bank/add", summary="[총 관리자/부관리자] 문제은행에 수동 문제 추가")
async def api_question_bank_add(req: QuestionBankAddRequest):
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


@router.post("/api/question-bank/from-log", summary="[총 관리자/부관리자] 문제풀이 DB 로그에서 문제은행으로 즉시 저장")
async def api_question_bank_from_log(req: QuestionBankFromLogRequest):
    try:
        saved = save_quiz_log_to_bank(log_id=req.log_id, user_id=req.user_id)
        return {"status": "success", "item": saved, "message": saved.get("message", "문제은행 저장 완료")}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"로그 문제은행 저장 실패: {str(e)}")


@router.post("/api/question-bank/delete", summary="[총 관리자/부관리자] 문제은행 문제 삭제")
async def api_question_bank_delete(req: QuestionBankDeleteRequest):
    try:
        deleted = delete_question_from_bank(bank_id=req.bank_id, user_id=req.user_id)
        return {"status": "success", **deleted}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 삭제 실패: {str(e)}")


@router.get("/api/question-bank/unit-stats", summary="[전 과목 공용] 단원별 문제은행 맞춘 문제 및 전체/남은 문제 현황 조회")
async def api_question_bank_unit_stats(
    subject: str = "math",
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
):
    try:
        stats = get_unit_bank_stats(subject=subject, user_id=user_id, user_name=user_name)
        return {"status": "success", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"단원별 문제은행 현황 조회 실패: {str(e)}")


class QuestionBankPickRequest(BaseModel):
    subject: str = Field(..., description="과목 코드")
    user_id: Optional[str] = Field(default=None)
    user_name: Optional[str] = Field(default="김에듀")
    grade: int = Field(default=4)
    grade_group: Optional[str] = Field(default=None)
    unit_name: Optional[str] = Field(default=None)
    sub_topic: Optional[str] = Field(default=None)
    question_type: Optional[str] = Field(default=None)
    difficulty: Optional[str] = Field(default=None)
    allow_solved_fallback: bool = Field(default=False, description="미풀이 문제가 없을 때 기풀이 복습 문제 반환 허용 여부")


@router.post("/api/question-bank/pick", summary="[전 과목 공용] 문제은행 미풀이 문제 추출 (없거나 다 풀었으면 found=False 반환)")
async def api_question_bank_pick(req: QuestionBankPickRequest):
    try:
        res = pick_unsolved_bank_question(
            subject=req.subject,
            user_id=req.user_id,
            user_name=req.user_name,
            grade=req.grade,
            grade_group=req.grade_group,
            unit_name=req.unit_name,
            sub_topic=req.sub_topic,
            question_type=req.question_type,
            difficulty=req.difficulty,
            allow_solved_fallback=req.allow_solved_fallback,
        )
        return {"status": "success", **res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 문제 추출 실패: {str(e)}")


class QuestionBankMarkSolvedRequest(BaseModel):
    bank_id: int = Field(..., description="문제은행 번호")
    subject: str = Field(default="math", description="과목 코드")
    user_id: Optional[str] = Field(default=None)
    user_name: Optional[str] = Field(default="김에듀")


@router.post("/api/question-bank/mark-solved", summary="[전 과목 공용] 문제은행 문제 정답 풀이 완료 기록")
async def api_question_bank_mark_solved(req: QuestionBankMarkSolvedRequest):
    try:
        mark_bank_question_solved(
            bank_id=req.bank_id,
            subject=req.subject,
            user_id=req.user_id,
            user_name=req.user_name,
        )
        stats = get_unit_bank_stats(subject=req.subject, user_id=req.user_id, user_name=req.user_name)
        return {"status": "success", "bank_stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 정답 기록 실패: {str(e)}")


class QuestionBankGradeRequest(BaseModel):
    subject: str = Field(..., description="과목 코드 (korean, math, english, social, science, hanja)")
    question_type: str = Field(..., description="문제 유형 (ox, 객관식, 단답형, 서술형)")
    difficulty: str = Field(default="중", description="난이도 (하, 중, 상)")
    points: int = Field(default=3, description="배점 (1, 3, 5)")
    question_text: str = Field(..., description="문제 지문")
    correct_answer: str = Field(..., description="모범 정답")
    user_answer: str = Field(..., description="학생 제출 답안")
    explanation: Optional[str] = Field(default="", description="해설 및 채점 기준")
    choices: Optional[List[str]] = Field(default_factory=list, description="객관식 보기")
    bank_id: Optional[int] = Field(default=None, description="문제은행 번호 (정답 시 풀이 완료 처리용)")
    user_id: Optional[str] = Field(default=None)
    user_name: Optional[str] = Field(default="김에듀")


@router.post("/api/question-bank/grade", summary="[전 과목 공용] 문제은행 직접 출제 주관식/서술형 AI 채점")
async def api_question_bank_grade(req: QuestionBankGradeRequest):
    try:
        result = grade_bank_question_by_ai(
            subject=req.subject,
            question_type=req.question_type,
            difficulty=req.difficulty,
            points=req.points,
            question_text=req.question_text,
            correct_answer=req.correct_answer,
            user_answer=req.user_answer,
            explanation=req.explanation or "",
            choices=req.choices or [],
        )
        if req.bank_id and bool(result.get("is_correct", False)):
            mark_bank_question_solved(
                bank_id=int(req.bank_id),
                subject=req.subject,
                user_id=req.user_id,
                user_name=req.user_name,
            )
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문제은행 AI 채점 실패: {str(e)}")


@router.post("/api/profile/update", summary="개인정보(학생 이름, 비번, 학년) 변경 및 DB 동기화")
async def update_profile(req: UpdateProfileRequest):
    """회원(마스터 관리자 포함)이 본인의 학생 이름, 비밀번호, 학년을 직접 변경하고 누적 점수를 승계합니다."""
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


@router.get("/api/user", summary="학생 프로필 및 통합 누적 점수 조회")
async def get_user_info(user_name: str = "김에듀", pokemon_type: Optional[str] = None, custom_skin_stage: Optional[int] = None, user_id: Optional[str] = None):
    """학생의 학년, 누적 점수, 포켓몬 진화 등급을 조회합니다."""
    try:
        user_data = get_or_create_user(user_name=user_name, pokemon_type=pokemon_type, custom_skin_stage=custom_skin_stage, user_id=user_id)
        return {"status": "success", "user": user_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학생 정보 조회 실패: {str(e)}")


@router.post("/api/user", summary="학생 프로필 변경 및 DB 저장")
async def update_user_info(req: UserProfileRequest):
    """학생 학년, 포켓몬 타입, 외형 스킨을 변경하여 저장합니다."""
    try:
        user_data = get_or_create_user(
            user_name=req.user_name,
            grade=req.grade,
            pokemon_type=req.pokemon_type,
            custom_skin_stage=req.custom_skin_stage,
        )
        return {"status": "success", "user": user_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학생 정보 저장 실패: {str(e)}")
