"""SQLAlchemy 2.x만 사용. 누적 점수는 중복 없는 풀이 기록의 합계."""
from datetime import datetime,timezone
from pathlib import Path
import os,time
from sqlalchemy import create_engine,select,func,Integer
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from .models import Base,IssuedQuestion,QuizLog
class HanjaStorage:
    def __init__(self,url=None,engine=None):
        if engine is None:
            path=Path(__file__).resolve().parent/'data/hanja.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
            url=url or os.getenv('HANJA_DATABASE_URL') or 'sqlite:///'+str(path)
            engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':20} if url.startswith('sqlite:') else {})
        self.engine=engine;self.sessions=sessionmaker(engine,expire_on_commit=False)
        Base.metadata.create_all(engine)
    def issue(self,qid,q):
        payload={k:q[k] for k in ['public','r','owner']}
        if 'answer' in q:payload['answer']=q['answer']
        with self.sessions.begin() as session:session.add(IssuedQuestion(id=qid,owner=q['owner'],payload=payload,expires=time.time()+max(0,q['expires']-time.monotonic())))
    def question(self,qid,owner):
        with self.sessions() as session:
            q=session.get(IssuedQuestion,qid)
            if q is None or q.owner!=owner:return None
            return {**q.payload,'expires':time.monotonic()+q.expires-time.time(),'result':None}
    def result(self,qid,owner):
        with self.sessions() as session:
            row=session.get(QuizLog,qid)
            return dict(row.result) if row is not None and row.owner==owner else None
    def record(self,qid,q,answer,result):
        public=q['public'];r=q['r'];expected=q.get('answer') or r.get('model_answer') or r.get('reading','')
        result={**result,'record_status':'saved'}
        try:
            with self.sessions.begin() as session:
                session.add(QuizLog(question_id=qid,owner=q['owner'],question_type=public['question_type'],question=public['question'],character=r.get('character') or r.get('target_word') or r.get('original',''),grade=r.get('grade'),submitted_answer=answer,expected_answer=expected,score=result['score'],base_score=result['base_score'],correct=result['correct'],feedback=result.get('feedback') or result.get('explanation',''),result=result,created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        except IntegrityError:
            prior=self.result(qid,q['owner'])
            if prior is None:raise
            return prior
        return result
    def history(self,owner,limit=50,offset=0):
        with self.sessions() as session:
            score,count,correct=session.execute(select(func.coalesce(func.sum(QuizLog.score),0),func.count(),func.coalesce(func.sum(QuizLog.correct.cast(Integer)),0)).where(QuizLog.owner==owner)).one()
            rows=session.scalars(select(QuizLog).where(QuizLog.owner==owner).order_by(QuizLog.created_at.desc(),QuizLog.question_id).limit(limit).offset(offset)).all()
            fields=['question_id','question_type','question','character','grade','submitted_answer','expected_answer','score','base_score','correct','feedback']
            return {'total_score':int(score),'answered_count':int(count),'correct_count':int(correct),'items':[{**{k:getattr(row,k) for k in fields},'created_at':row.created_at.isoformat()+'Z'} for row in rows]}

    def submission(self,qid,owner):
        with self.sessions() as session:
            row=session.get(QuizLog,qid)
            if row is None or row.owner!=owner:return None
            return row.submitted_answer

    def apply_appeal(self,qid,owner,result):
        with self.sessions.begin() as session:
            row=session.get(QuizLog,qid)
            if row is None or row.owner!=owner:raise LookupError('없는 풀이입니다.')
            row.score=result['score'];row.correct=result['correct']
            row.feedback=result['feedback'];row.result=dict(result)
        return result
