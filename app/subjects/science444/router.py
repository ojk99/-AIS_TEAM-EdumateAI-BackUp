"""
EduMate AI - 초등 과학 전담 메인 API 라우터 (router.py)
==============================================================================
[모듈 출처 및 통합 히스토리]
- 퀴즈 출제 및 기본 웹 라우팅: [science_lab] 모듈 기반
- 서술형 AI 문맥 채점 및 피드백 엔진: [science_eval] 모듈 통합
- 채점 아카이빙 & 공통 계정/포켓몬 연동: edumate.db & quiz_logs 표준 통합

[과목 격리 및 연동 원칙]
- 팀 메인 관제탑(app/main.py) include_router 접점 단일화 (router: APIRouter)
- 본인 과목 단독 실행(Standalone) 및 팀 통합 모드 동시 지원

[지원 기능 목록]
- ⭕❌ OX 퀴즈 실시간 10문제 출제
- 📝 5지선다 객관식 퀴즈 실시간 10문제 출제
- ✍️ 서술형 퀴즈 10문제 출제 및 AI 5단계 문맥 채점 & 피드백
- 📖 스마트 오답노트 (실시간 자동 기록, 원클릭 다시 풀기, 개념 마스터 배지)
- 📂 지난 전체 채점 리포트 아카이브 (edumate.db 실시간 열람 및 복습)
- 🚨 실시간 문제 오류 신고 (다중 선택 체크박스, DB 저장 및 비상 백업)
==============================================================================
"""

import os
import json
import webbrowser
import threading
import time
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

try:
    from .service import (
        generate_ox_quiz,
        generate_mcq_quiz,
        generate_subjective_quiz,
        evaluate_batch_subjective_quizzes,
        answer_student_question,
        QuizRequest,
        QuizGenerateRequest,
        BatchEvaluationRequest,
        GRADE_UNITS,
        RESULTS_DIR
    )
    from .database import (
        save_wrong_note,
        get_wrong_notes,
        delete_wrong_note,
        save_problem_report,
        get_problem_reports,
        sync_saved_results_to_wrong_notes,
        mark_wrong_note_mastered,
        db_mode
    )
    from .quiz_logs import (
        save_quiz_log,
        get_user_status,
        get_or_create_user,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_evaluation_history_from_db,
        POKEMON_TYPE_CONFIG
    )
except ImportError:
    from service import (
        generate_ox_quiz,
        generate_mcq_quiz,
        generate_subjective_quiz,
        evaluate_batch_subjective_quizzes,
        answer_student_question,
        QuizRequest,
        QuizGenerateRequest,
        BatchEvaluationRequest,
        GRADE_UNITS,
        RESULTS_DIR
    )
    from database import (
        save_wrong_note,
        get_wrong_notes,
        delete_wrong_note,
        save_problem_report,
        get_problem_reports,
        sync_saved_results_to_wrong_notes,
        mark_wrong_note_mastered,
        db_mode
    )
    from quiz_logs import (
        save_quiz_log,
        get_user_status,
        get_or_create_user,
        append_chat_message,
        toggle_favorite,
        get_weakest_unit_and_topic,
        get_evaluation_history_from_db,
        POKEMON_TYPE_CONFIG
    )

current_dir = Path(__file__).resolve().parent
html_file_path = current_dir / "index.html"
logo_file_path = current_dir / "edumate_logo.svg"

# ==============================================================================
# 0. Pydantic DTO 스키마 (공통 DB 모듈 & 오답노트 & 신고 & AI 질문)
# ==============================================================================
class QuizLogRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, description="회원 고유 ID")
    user_name: str = Field(default="김에듀", description="학생 이름")
    quiz_id: Optional[str] = Field(default=None, description="고유 문제 ID")
    grade: Optional[int] = Field(default=4, ge=1, le=6, description="학년(1~6)")
    unit: Optional[str] = Field(default=None, description="단원명")
    topic: Optional[str] = Field(default=None, description="주제명")
    difficulty: Optional[str] = Field(default=None, description="난이도(상/중/하)")
    question_type: Optional[str] = Field(default=None, description="문제 유형(ox/mcq/subjective)")
    question: str = Field(..., description="문제 지문")
    user_answer: Optional[str] = Field(default=None, description="학생 답안")
    correct_answer: Optional[str] = Field(default=None, description="모범 정답")
    solution: Optional[str] = Field(default=None, description="해설")
    earned_score: int = Field(default=0, ge=0, le=5, description="획득 점수")
    is_correct: bool = Field(default=False, description="정답 여부")


class ChatAskRequest(BaseModel):
    log_id: int = Field(..., description="quiz_logs 고유 PK 번호")
    student_question: str = Field(..., description="학생의 추가 질문")
    question_context: Optional[str] = Field(default="", description="문제 지문")
    student_answer: Optional[str] = Field(default="", description="학생 답안")
    correct_answer: Optional[str] = Field(default="", description="모범 정답")
    feedback: Optional[str] = Field(default="", description="기존 피드백")


class WrongNoteCreateRequest(BaseModel):
    problem_id: Optional[int] = Field(default=None, description="문제 번호")
    grade: int = Field(default=3, ge=1, le=6, description="학년(1~6)")
    unit: str = Field(default="총정리", description="단원명")
    quiz_type: str = Field(default="ox", description="문제 유형(ox/mcq/subjective)")
    question: str = Field(..., description="문제 지문")
    options: Optional[List[str]] = Field(default=None, description="5지선다 보기 배열")
    student_answer: Optional[str] = Field(default="", description="학생 답안")
    correct_answer: str = Field(..., description="모범 정답")
    score: int = Field(default=0, description="부여된 점수")
    feedback: Optional[str] = Field(default="", description="AI 피드백")
    deduction_reason: Optional[str] = Field(default="", description="감점 사유")


class ProblemReportRequest(BaseModel):
    problem_id: Optional[int] = Field(default=None, description="문제 번호")
    grade: Optional[int] = Field(default=None, description="학년")
    unit: Optional[str] = Field(default=None, description="단원명")
    quiz_type: Optional[str] = Field(default=None, description="문제 유형")
    question: str = Field(..., description="신고 대상 문제 지문")
    error_type: str = Field(..., description="선택된 오류 분류")
    comment: Optional[str] = Field(default="", description="상세 의견")


# ==============================================================================
# 1. FastAPI APIRouter 인스턴스 (팀 프로젝트 결합용 - 조장 접점 Step B)
# ==============================================================================
router = APIRouter(prefix="/science", tags=["초등과학"])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def serve_subject_index():
    """초등 과학 통합 퀴즈 웹 페이지 서빙 (메인 로비 연동 표준 규격)"""
    if html_file_path.exists():
        return FileResponse(str(html_file_path), media_type="text/html")
    return HTMLResponse("<h3>index.html 파일을 찾을 수 없습니다.</h3>", status_code=404)


@router.get("/logo.svg")
async def serve_logo():
    """EduMate AI 팀 공통 로고 SVG 서빙"""
    if logo_file_path.exists():
        return FileResponse(str(logo_file_path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="로고 파일(edumate_logo.svg)을 찾을 수 없습니다.")



@router.get("/api/curriculum")
async def get_curriculum():
    """1~6학년 전체 단원 목차 목록 반환"""
    curriculum_data = {}
    for grade, units in GRADE_UNITS.items():
        curriculum_data[grade] = list(units.keys())
    return JSONResponse(content={"curriculum": curriculum_data})


@router.post("/api/quiz")
async def create_quiz(req: QuizRequest):
    """OX 또는 5지선다 퀴즈 실시간 출제 API"""
    try:
        if req.mode == "mcq":
            quiz_data = generate_mcq_quiz(grade=req.grade, unit=req.unit)
        else:
            quiz_data = generate_ox_quiz(grade=req.grade, unit=req.unit)
        return quiz_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/quiz/mcq")
async def create_mcq_quiz_direct(req: QuizRequest):
    """5지선다 객관식 퀴즈 전용 엔드포인트"""
    try:
        return generate_mcq_quiz(grade=req.grade, unit=req.unit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/quiz/subjective")
async def create_subjective_quiz(req: QuizGenerateRequest):
    """서술형 10문제 실시간 출제 API"""
    try:
        quiz_data = generate_subjective_quiz(grade=req.grade, unit=req.unit, count=req.count)
        return JSONResponse(content={"status": "success", "data": quiz_data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/quiz/evaluate_batch")
async def evaluate_batch_quiz_answers(
    req: BatchEvaluationRequest,
    user_name: str = Query(default="김에듀"),
    pokemon_type: str = Query(default="grass"),
    user_id: Optional[str] = Query(default=None)
):
    """10문제 서술형 답안 일괄 문맥 채점 & 공통 DB(quiz_logs) 18개 칼럼 표준 저장 & 포켓몬 누적점수 갱신"""
    try:
        answers_dict = [a.model_dump() for a in req.answers]
        record = evaluate_batch_subjective_quizzes(
            grade=req.grade,
            unit=req.unit,
            answers_data=answers_dict
        )

        effective_user_id = req.user_id or user_id

        # 공통 DB(quiz_logs) 18개 표준 칼럼 규격대로 10문제 각각 저장 및 log_id 주입
        # 동일 단원 반복 풀이 시 이전 세트가 덮어씌워지지 않도록 세트 고유 시간값 부여
        batch_session_time = time.strftime("%Y%m%d%H%M%S")
        ans_map = {a.get("id"): a for a in answers_dict}
        for res in record.get("results", []):
            q_id = res.get("id")
            q_info = ans_map.get(q_id, {})
            sc = int(res.get("score", 0))
            is_cor = bool(sc >= 3)
            
            db_res = save_quiz_log(
                user_id=effective_user_id,
                user_name=user_name,
                quiz_id=f"science_g{req.grade}_{req.unit}_{batch_session_time}_q{q_id}",
                grade=req.grade,
                unit=req.unit,
                topic=None,
                difficulty="중",
                question_type="subjective",
                question=q_info.get("question", ""),
                user_answer=q_info.get("student_answer", ""),
                correct_answer=q_info.get("model_answer", ""),
                solution=res.get("feedback", ""),
                earned_score=sc,
                is_correct=is_cor,
                is_favorite=None,
                chat_history=None
            )
            res["log_id"] = db_res.get("log_id")

            # 감점된 서술형 문제(5점 미만)를 스마트 오답노트(quiz_wrong_notes)에 즉시 자동 저장
            if sc < 5:
                try:
                    save_wrong_note(
                        problem_id=q_id,
                        grade=req.grade,
                        unit=req.unit,
                        quiz_type="subjective",
                        question=q_info.get("question", ""),
                        correct_answer=q_info.get("model_answer", ""),
                        student_answer=q_info.get("student_answer", ""),
                        score=sc,
                        feedback=res.get("feedback", ""),
                        deduction_reason=res.get("analysis", "")
                    )
                except Exception as wn_err:
                    print(f"[서술형 오답노트 저장 알림] {wn_err}")

        latest_status = get_user_status(user_name=user_name, grade=req.grade, pokemon_type=pokemon_type, user_id=effective_user_id)
        record["user_status"] = latest_status

        return JSONResponse(content={"status": "success", "data": record})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/user/status")
async def get_student_status(
    user_name: str = Query(default="김에듀"),
    grade: Optional[int] = Query(default=None),
    pokemon_type: str = Query(default="grass"),
    user_id: Optional[str] = Query(default=None)
):
    """학생 전과목 누적 총점 및 포켓몬 진화 등급 조회/생성 (EduMate AI 공통 규격)"""
    try:
        status = get_or_create_user(user_name=user_name, grade=grade, pokemon_type=pokemon_type, user_id=user_id)
        return JSONResponse(content={"status": "success", "data": status})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/quiz/log")
async def record_quiz_log(req: QuizLogRequest):
    """OX/객관식 퀴즈 채점 결과를 공통 DB(quiz_logs)에 기록하고 누적점수/포켓몬 등급 갱신"""
    try:
        result = save_quiz_log(
            user_id=req.user_id,
            user_name=req.user_name,
            quiz_id=req.quiz_id,
            grade=req.grade,
            unit=req.unit,
            topic=req.topic,
            difficulty=req.difficulty,
            question_type=req.question_type,
            question=req.question,
            user_answer=req.user_answer,
            correct_answer=req.correct_answer,
            solution=req.solution,
            earned_score=req.earned_score,
            is_correct=req.is_correct
        )
        return JSONResponse(content={"status": "success", "data": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat")
async def ask_ai_teacher_question(req: ChatAskRequest):
    """학생이 해당 문제 풀이 후 AI 선생님께 이어서 추가 질문하기 & chat_history 누적"""
    try:
        ai_reply = answer_student_question(
            student_question=req.student_question,
            question_context=req.question_context or "",
            student_answer=req.student_answer or "",
            correct_answer=req.correct_answer or "",
            feedback=req.feedback or ""
        )
        updated_history = append_chat_message(
            log_id=req.log_id,
            student_question=req.student_question,
            ai_reply=ai_reply
        )
        return JSONResponse(content={
            "status": "success",
            "reply": ai_reply,
            "chat_history": updated_history
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/favorite/{log_id}")
async def toggle_quiz_favorite_status(log_id: int):
    """문제 즐겨찾기(is_favorite: 1 or 0) 상태 토글"""
    try:
        is_fav = toggle_favorite(log_id)
        return JSONResponse(content={"status": "success", "log_id": log_id, "is_favorite": is_fav})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/recommend/weakness")
async def get_user_weakness_recommendation(
    user_name: str = Query(default="김에듀")
):
    """과거 오답 데이터 기반 가장 취약한 단원 및 주제 추천 조회"""
    try:
        weakness = get_weakest_unit_and_topic(user_name=user_name)
        return JSONResponse(content={"status": "success", "data": weakness})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/history")
async def get_evaluation_history(
    user_name: str = Query(default="김에듀"),
    user_id: Optional[str] = Query(default=None)
):
    """edumate.db의 quiz_logs 테이블에서 10문제 채점 기록을 직접 조회하고 최신순 반환"""
    try:
        db_history = get_evaluation_history_from_db(user_name=user_name, limit=30, user_id=user_id)
    except Exception as e:
        db_history = []

    # 기존 JSON 파일 기록도 보조로 병합 (중복 방지)
    file_history = []
    if RESULTS_DIR.exists():
        for p in sorted(RESULTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    file_history.append(json.load(f))
            except Exception:
                continue

    # DB 기록 우선, 없는 경우 파일 기록 보충
    existing_keys = {h.get("id") for h in db_history}
    merged_history = list(db_history)
    for fh in file_history:
        if fh.get("id") not in existing_keys:
            merged_history.append(fh)

    return JSONResponse(content={"history": merged_history[:30]})


# --- [기능 A] 스마트 오답노트 API ---
@router.get("/api/wrong-notes")
async def fetch_wrong_notes(
    grade: Optional[int] = Query(default=None),
    quiz_type: Optional[str] = Query(default=None)
):
    """오답노트 목록 최신순 조회 (학년, 문제유형 필터 지원)"""
    try:
        notes = get_wrong_notes(grade=grade, quiz_type=quiz_type)
        return JSONResponse(content={
            "status": "success",
            "data": notes,
            "count": len(notes),
            "db_mode": db_mode
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/wrong-notes")
async def record_wrong_note(req: WrongNoteCreateRequest):
    """틀린 문제 1건 오답노트에 수동/자동 등록"""
    try:
        note_id = save_wrong_note(
            problem_id=req.problem_id,
            grade=req.grade,
            unit=req.unit,
            quiz_type=req.quiz_type,
            question=req.question,
            options=req.options,
            student_answer=req.student_answer or "",
            correct_answer=req.correct_answer,
            score=req.score,
            feedback=req.feedback or "",
            deduction_reason=req.deduction_reason or ""
        )
        return JSONResponse(content={"status": "success", "id": note_id, "db_mode": db_mode})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/wrong-notes/{note_id}")
async def remove_wrong_note(note_id: int):
    """오답노트 항목 개별 삭제 (다시 풀어보기 성공 시 등)"""
    try:
        success = delete_wrong_note(note_id)
        return JSONResponse(content={"status": "success", "deleted": success})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/wrong-notes/sync")
async def sync_wrong_notes_from_saved():
    """saved_results 폴더에 보관된 과거 채점 파일에서 감점된 문제들을 오답노트에 동기화"""
    try:
        count = sync_saved_results_to_wrong_notes()
        return JSONResponse(content={"status": "success", "synced_count": count})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/wrong-notes/{note_id}/master")
async def master_wrong_note(note_id: int):
    """오답노트 항목을 삭제하지 않고 '개념 마스터 완료' 배지 상태로 갱신"""
    try:
        success = mark_wrong_note_mastered(note_id)
        return JSONResponse(content={"status": "success", "mastered": success})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- [기능 B] 실시간 문제 오류 신고 API ---
@router.post("/api/reports")
async def report_problem(req: ProblemReportRequest):
    """실시간 문제 오류 신고 접수 (DB 저장 + 비상용 백업 JSON 동시 저장)"""
    try:
        result = save_problem_report(
            question=req.question,
            error_type=req.error_type,
            comment=req.comment or "",
            problem_id=req.problem_id,
            grade=req.grade,
            unit=req.unit,
            quiz_type=req.quiz_type
        )
        return JSONResponse(content={"status": "success", "data": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/reports")
async def fetch_reports():
    """접수된 문제 오류 신고 목록 최신순 조회"""
    try:
        reports = get_problem_reports()
        return JSONResponse(content={"status": "success", "data": reports, "count": len(reports)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# 2. 조원 단독 로컬 테스트 지원 블록 (uvicorn router:app 또는 python router.py)
# ==============================================================================
app = FastAPI(
    title="EduMate AI - 초등 과학 통합 학습관 (Step B 공통 DB & 포켓몬 진화 & 로고 연동)",
    description="2022 개정 초등 과학 1~6학년 통합 퀴즈 & 공통 DB(quiz_logs) & 오답노트 & 신고시스템",
    version="3.6.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# 루트("/") 및 공통 로고 단독 접속 지원
@app.get("/", response_class=HTMLResponse)
async def root_page():
    return FileResponse(str(html_file_path), media_type="text/html")


@app.get("/logo.svg")
async def root_logo():
    if logo_file_path.exists():
        return FileResponse(str(logo_file_path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Logo not found")


# 상대 경로 호출 호환성 지원 (/api/...)
@app.get("/api/user/status")
async def standalone_user_status(
    user_name: str = Query(default="김에듀"),
    grade: Optional[int] = Query(default=None),
    pokemon_type: str = Query(default="grass"),
    user_id: Optional[str] = Query(default=None)
):
    return await get_student_status(user_name=user_name, grade=grade, pokemon_type=pokemon_type, user_id=user_id)


@app.post("/api/quiz/log")
async def standalone_record_quiz_log(req: QuizLogRequest):
    return await record_quiz_log(req)


@app.post("/api/chat")
async def standalone_ask_chat(req: ChatAskRequest):
    return await ask_ai_teacher_question(req)


@app.post("/api/favorite/{log_id}")
async def standalone_toggle_favorite(log_id: int):
    return await toggle_quiz_favorite_status(log_id)


@app.get("/api/recommend/weakness")
async def standalone_weakness(user_name: str = Query(default="김에듀")):
    return await get_user_weakness_recommendation(user_name=user_name)


@app.post("/api/quiz")
async def standalone_create_quiz(req: QuizRequest):
    return await create_quiz(req)


@app.post("/api/quiz/mcq")
async def standalone_create_mcq(req: QuizRequest):
    return await create_mcq_quiz_direct(req)


@app.post("/api/quiz/subjective")
async def standalone_create_subjective(req: QuizGenerateRequest):
    return await create_subjective_quiz(req)


@app.post("/api/quiz/evaluate_batch")
async def standalone_evaluate_batch(
    req: BatchEvaluationRequest,
    user_name: str = Query(default="김에듀"),
    pokemon_type: str = Query(default="grass"),
    user_id: Optional[str] = Query(default=None)
):
    return await evaluate_batch_quiz_answers(req=req, user_name=user_name, pokemon_type=pokemon_type, user_id=user_id)


@app.get("/api/history")
async def standalone_history(
    user_name: str = Query(default="김에듀"),
    user_id: Optional[str] = Query(default=None)
):
    return await get_evaluation_history(user_name=user_name, user_id=user_id)


@app.get("/api/curriculum")
async def standalone_curriculum():
    return await get_curriculum()


# [기능 A 호환] 오답노트
@app.get("/api/wrong-notes")
async def standalone_fetch_wrong_notes(
    grade: Optional[int] = Query(default=None),
    quiz_type: Optional[str] = Query(default=None)
):
    return await fetch_wrong_notes(grade=grade, quiz_type=quiz_type)


@app.post("/api/wrong-notes")
async def standalone_record_wrong_note(req: WrongNoteCreateRequest):
    return await record_wrong_note(req)


@app.delete("/api/wrong-notes/{note_id}")
async def standalone_remove_wrong_note(note_id: int):
    return await remove_wrong_note(note_id)


@app.post("/api/wrong-notes/sync")
async def standalone_sync_wrong_notes():
    return await sync_wrong_notes_from_saved()


@app.post("/api/wrong-notes/{note_id}/master")
async def standalone_master_wrong_note(note_id: int):
    return await master_wrong_note(note_id)


# [기능 B 호환] 문제 오류 신고
@app.post("/api/reports")
async def standalone_report_problem(req: ProblemReportRequest):
    return await report_problem(req)


@app.get("/api/reports")
async def standalone_fetch_reports():
    return await fetch_reports()


def open_browser(port: int = 8000):
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")


# 서버 구동 시 기존 채점 기록 자동 동기화
try:
    sync_saved_results_to_wrong_notes()
except Exception as _e:
    pass


if __name__ == "__main__":
    PORT = 8000
    print("\n" + "=" * 68)
    print("[EduMate AI 초등 과학 - FastAPI 스마트 통합 서버 실행 (Step B)]")
    print("=" * 68)
    print("* 담당 과목: 초등 과학 (1~6학년 전 단원)")
    print("* 지원 모드: OX 퀴즈 | 5지선다 객관식 | 서술형 문맥 채점")
    print(f"* DB 모드: {db_mode} & 중앙 통합 quiz_logs (18개 칼럼 표준)")
    print("* 연동 기능: [포켓몬 5대 진화 바] & [AI 추가 질문] & [즐겨찾기] & [취약단원 추천]")
    print(f"* 접속 주소: http://localhost:{PORT}")
    print("* 팀 프로젝트 통합 시: app.include_router(science_router) 로 연결")
    print("=" * 68 + "\n")

    threading.Thread(target=open_browser, args=(PORT,), daemon=True).start()
    uvicorn.run("router:app", host="0.0.0.0", port=PORT, reload=True)

