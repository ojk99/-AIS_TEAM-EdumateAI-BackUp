"""한자 과목 범위의 문제은행 어댑터. 공통 라우트와 충돌하지 않는다."""
import asyncio, secrets, time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import question_bank as bank, team_db

class BankIssueRequest(BaseModel):
    unit_name: str = Field(min_length=1,max_length=100)
    ai_mode: bool = False

class BankGradeRequest(BaseModel):
    question_id: str = Field(min_length=1,max_length=100)
    answer: str = Field(min_length=1,max_length=2000)
    user_id: str | None = Field(default=None,max_length=200)

def create_bank_router(identity,learner,storage):
    bank.init_question_bank()
    router=APIRouter()
    grading_locks={}

    @router.get('/api/question-bank/unit-stats')
    def unit_stats(request:Request):
        account=identity(request)
        return {'subject':'hanja','units':bank.get_unit_bank_stats(account[3],account[0]),'count_label':'맞춘 문제 / 전체 문제'}

    @router.post('/api/question-bank/quiz')
    async def issue(body:BankIssueRequest,request:Request):
        account=identity(request);key=bank.user_key(account)
        try:
            stats=bank.get_unit_bank_stats(account[3],account[0])
            if body.unit_name not in {x['unit_name'] for x in stats}:raise HTTPException(422,'단원을 확인해 주세요.')
            row,public=await bank.issue_question(body.unit_name,key,body.ai_mode,account[1])
        except HTTPException:raise
        except RuntimeError as exc:
            if str(exc)==bank.EMPTY_MESSAGE:raise HTTPException(503,{'code':'NO_AVAILABLE_QUESTION','message':bank.EMPTY_MESSAGE,'ai_mode':True})
            raise HTTPException(503,'문제은행을 확인할 수 없습니다.')
        except Exception:raise HTTPException(503,'문제은행 데이터 형식 또는 연결을 확인해 주세요.')
        qid=secrets.token_urlsafe(24)
        public={**public,'question_id':qid}
        q={'public':public,'r':{'kind':'bank','bank_row':row,'unit_name':row['unit_name'],
           'character':row.get('sub_topic') or None,'bank_user_key':key},
           'answer':row['correct_answer'],'owner':learner(request),'expires':time.monotonic()+86400,'result':None}
        try:storage.issue(qid,q)
        except Exception:raise HTTPException(503,'문제 발급 기록을 저장하지 못했습니다. 다시 시도해 주세요.')
        return public

    @router.post('/api/question-bank/grade')
    async def grade(body:BankGradeRequest,request:Request):
        if not body.answer.strip():raise HTTPException(422,'답안을 입력해 주세요.')
        account=identity(request);owner=learner(request)
        if body.user_id and body.user_id!=account[3]:raise HTTPException(422,'회원 정보가 바뀌었습니다. 화면을 새로고침해 주세요.')
        q=storage.question(body.question_id,owner)
        if not q or q.get('r',{}).get('kind')!='bank':raise HTTPException(404,'다른 학습자의 문제이거나 없는 문제입니다.')
        if q['r']['bank_user_key']!=bank.user_key(account):raise HTTPException(403,'문제를 발급받은 계정과 다릅니다.')
        prior=storage.result(body.question_id,owner)
        if prior is not None:return prior
        if q['expires']<time.monotonic():raise HTTPException(404,'문제가 만료되었습니다. 새 문제를 받아 주세요.')
        # Only in-flight locks are kept; persistent ID/SQLite transactions handle restart/retry.
        entry=grading_locks.setdefault(body.question_id,[asyncio.Lock(),0]);entry[1]+=1
        try:
            async with entry[0]:
                prior=storage.result(body.question_id,owner)
                if prior is not None:return prior
                row=q['r']['bank_row']
                if row['unit_name']=='사자성어' and not bank.valid_idiom_question(row['question_text']):raise HTTPException(422,'이전에 잘못 출제된 일반 한자어입니다. 새 문제를 눌러 사자성어를 다시 받아 주세요.')
                result=await bank.grade_bank_question_by_ai(row,body.answer)
                result['ai_graded']=bool(result.get('ai_graded',False))
                result['appeal_available']=not result['ai_graded']
                try:
                    bank_id=row.get('id')
                    if bank_id:
                        # Serializes bank reward settlement across local workers. Stable quiz_id also
                        # prevents a duplicate award if central save succeeds but bank commit fails.
                        with bank.connection() as conn:
                            conn.execute('BEGIN IMMEDIATE')
                            if not conn.execute("SELECT 1 FROM question_bank WHERE id=? AND subject='hanja'",(bank_id,)).fetchone():raise ValueError('삭제된 문제')
                            solved=bank.group_is_solved(conn,bank_id,bank.user_key(account))
                            review=solved or q['public']['review']
                            display_score=result['score']
                            saved=team_db.save_result(account,f'hanja-bank:{min(bank.group_members(conn,bank_id))}',q,body.answer,{**result,'score':0 if review else display_score})
                            if result['correct']:bank.mark_bank_question_solved(conn,bank_id,bank.user_key(account))
                            result={**saved,'score':display_score,'review':review,'bank_id':bank_id}
                            if review:result.update(added_score=0,notice='복습 문제입니다. 누적 포인트에는 반영하지 않습니다.')
                    else:
                        result=team_db.save_result(account,body.question_id,q,body.answer,result)
                    result=storage.record(body.question_id,q,body.answer,result)
                except Exception:raise HTTPException(503,'학습 기록을 저장하지 못했습니다. 같은 답으로 다시 제출해 주세요.')
                return result
        finally:
            entry[1]-=1
            if entry[1]==0:grading_locks.pop(body.question_id,None)
    return router
