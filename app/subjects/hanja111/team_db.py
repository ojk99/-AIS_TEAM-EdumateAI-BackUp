"""최신 팀 모듈 연결. 표준 18개 컬럼을 변경하지 않는 보조 기능."""
import json,threading
from sqlalchemy import create_engine,MetaData,Table,select,update,func
from . import quiz_logs as shared
LOCK=threading.RLock()

def table():
    shared.init_db()
    engine=create_engine('sqlite:///'+str(shared.DB_PATH),connect_args={'timeout':20})
    return engine,Table('quiz_logs',MetaData(),autoload_with=engine)

def get_or_create_user(user_name,grade=None,pokemon_type='grass'):
    return shared.get_user_status(user_name,grade,pokemon_type)

def save_result(identity,qid,q,answer,result):
    name,grade,ptype=identity;r=q['r'];public=q['public']
    with LOCK:
        # 최신 모듈은 학년 캐시를 먼저 설정해야 신규 이름 저장시 KeyError를 피함.
        shared.get_user_status(name,grade,ptype)
        data=shared.save_quiz_log(user_name=name,quiz_id=qid,grade=grade,
            unit=('사자성어' if r.get('kind')=='idiom' else '실용 한자어' if r.get('kind')=='practical_word' else str(r.get('grade'))+'급' if r.get('grade') else None),
            topic=r.get('original') if r.get('kind')=='idiom' else r.get('target_word') or r.get('character'),
            difficulty=public.get('difficulty'),question_type=public.get('question_type'),question=public['question'],user_answer=answer,
            correct_answer=q.get('answer') or r.get('model_answer') or r.get('reading'),solution=result.get('feedback') or result.get('explanation'),
            earned_score=result['score'],is_correct=result['correct'])
        status=shared.get_user_status(name,grade,ptype)
    return {**result,**data,'level_info':status['level_info'],'central_score_status':'saved'}

def owned_log(log_id,name):
    engine,t=table()
    try:
        with engine.connect() as conn:
            row=conn.execute(select(t).where(t.c.id==log_id,t.c.user_name==name,t.c.subject=='hanja')).mappings().first()
            return dict(row) if row else None
    finally:engine.dispose()

def toggle_favorite(log_id,name):
    engine,t=table()
    try:
        with LOCK,engine.begin() as conn:
            row=conn.execute(select(t).where(t.c.id==log_id,t.c.user_name==name,t.c.subject=='hanja')).mappings().first()
            if row is None:raise LookupError('다른 학생의 기록이거나 없는 기록입니다.')
            value=0 if row['is_favorite'] else 1
            conn.execute(update(t).where(t.c.id==log_id).values(is_favorite=value))
            return bool(value)
    finally:engine.dispose()

def append_chat_message(log_id,name,student_question,ai_reply):
    engine,t=table()
    try:
        with LOCK,engine.begin() as conn:
            row=conn.execute(select(t).where(t.c.id==log_id,t.c.user_name==name,t.c.subject=='hanja')).mappings().first()
            if row is None:raise LookupError('다른 학생의 기록이거나 없는 기록입니다.')
            history=json.loads(row['chat_history']) if row['chat_history'] else []
            if not isinstance(history,list):raise ValueError('대화 기록 형식이 맞지 않습니다.')
            history.append({'student_question':student_question,'ai_reply':ai_reply})
            conn.execute(update(t).where(t.c.id==log_id).values(chat_history=json.dumps(history,ensure_ascii=False)))
            return history
    finally:engine.dispose()

def get_weakest_unit_and_topic(name):
    engine,t=table()
    try:
        with engine.connect() as conn:
            row=conn.execute(select(t.c.unit,t.c.topic,func.count().label('wrong_count')).where(t.c.user_name==name,t.c.subject=='hanja',t.c.is_correct==0,t.c.topic.is_not(None)).group_by(t.c.unit,t.c.topic).order_by(func.count().desc(),func.max(t.c.id).desc()).limit(1)).mappings().first()
            return dict(row) if row else None
    finally:engine.dispose()

def history(name,limit=50,offset=0):
    engine,t=table()
    try:
        with engine.connect() as conn:
            rows=conn.execute(select(t).where(t.c.user_name==name,t.c.subject=='hanja').order_by(t.c.id.desc()).limit(limit).offset(offset)).mappings().all()
            count,correct=conn.execute(select(func.count(),func.coalesce(func.sum(t.c.is_correct),0)).where(t.c.user_name==name,t.c.subject=='hanja')).one()
            return {'total_score':shared.get_user_status(name)['total_score'],'answered_count':count,'correct_count':correct,'items':[{'log_id':r['id'],'question_id':r['quiz_id'],'question':r['question'],'grade':r['grade'],'submitted_answer':r['user_answer'],'expected_answer':r['correct_answer'],'feedback':r['solution'],'score':r['earned_score'],'created_at':r['solved_at'],'is_favorite':bool(r['is_favorite']),'chat_history':json.loads(r['chat_history']) if r['chat_history'] else None} for r in rows]}
    finally:engine.dispose()
