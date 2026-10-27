"""실제 AI 호출 없이 재검토의 점수·소유권·재시도를 검증한다."""
import tempfile
import unittest
import uuid
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from .router import create_router
from .storage import HanjaStorage

class AppealTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.storage=HanjaStorage('sqlite:///'+self.tmp.name+'/test.db')
        app=FastAPI();app.include_router(create_router(storage=self.storage))
        self.client=TestClient(app,headers={'X-Hanja-Learner':str(uuid.uuid4())})
        self.save=patch('app.subjects.hanja.team_db.save_result',side_effect=lambda account,qid,q,answer,result:{**result,'log_id':123})
        self.save.start();self.addCleanup(self.save.stop)
        self.central=patch('app.subjects.hanja.team_db.apply_appeal');self.apply=self.central.start();self.addCleanup(self.central.stop)
        self.addCleanup(self.storage.engine.dispose);self.addCleanup(self.tmp.cleanup)
    def issue(self):
        q=self.client.post('/hanja/api/quiz',json={'grade':9,'question_type':'short_answer'}).json()
        self.qid=q['question_id']
        r=self.client.post('/hanja/api/grade',json={'question_id':self.qid,'answer':'다른 답'})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()
    def appeal(self,reason='동의어를 썼어요.'):
        return self.client.post('/hanja/api/appeal',json={'question_id':self.qid,'reason':reason})
    def test_upgrade_and_idempotence(self):
        original=self.issue();self.assertTrue(original['appeal_available'])
        with patch('app.subjects.hanja.ai_grader.generate_json',new_callable=AsyncMock,return_value={'score':3,'feedback':'동의어를 인정해요.'}) as ai:
            r=self.appeal();self.assertEqual(r.status_code,200,r.text)
            data=r.json();self.assertEqual(data['score'],3);self.assertEqual(data['added_score'],3)
            self.assertFalse(data['appeal_available']);self.assertTrue(data['ai_graded'])
            self.assertEqual(self.appeal().json(),data);self.assertEqual(ai.await_count,1)
            self.assertEqual(ai.call_args.args[1]['submitted_answer'],'다른 답')
        self.apply.assert_called_once()
        again=self.client.post('/hanja/api/grade',json={'question_id':self.qid,'answer':'바꾼 답'})
        self.assertEqual(again.json()['score'],3)
    def test_failure_retry_and_validation(self):
        self.issue()
        with patch('app.subjects.hanja.ai_grader.generate_json',new_callable=AsyncMock,side_effect=ValueError('offline')):
            self.assertEqual(self.appeal().status_code,503)
        for invalid in [True,4,-1]:
            with patch('app.subjects.hanja.ai_grader.generate_json',new_callable=AsyncMock,return_value={'score':invalid,'feedback':'검토'}):
                self.assertEqual(self.appeal().status_code,503)
        self.assertEqual(self.appeal('  ').status_code,422)
        with patch('app.subjects.hanja.ai_grader.generate_json',new_callable=AsyncMock,return_value={'score':0,'feedback':'원래 채점이 맞아요.'}):
            self.assertEqual(self.appeal().json()['added_score'],0)
    def test_other_learner_and_ai_grade_rejected(self):
        self.issue();owner='anon:'+self.client.headers['X-Hanja-Learner']
        previous=self.storage.result(self.qid,owner)
        self.client.headers['X-Hanja-Learner']=str(uuid.uuid4())
        self.assertEqual(self.appeal().status_code,404)
        self.client.headers['X-Hanja-Learner']=owner.removeprefix('anon:')
        self.storage.apply_appeal(self.qid,owner,{**previous,'feedback':'검토','ai_graded':True,'appeal_available':False})
        self.assertEqual(self.appeal().status_code,409)
    def test_score_never_decreases(self):
        self.issue();owner='anon:'+self.client.headers['X-Hanja-Learner']
        previous=self.storage.result(self.qid,owner)
        self.storage.apply_appeal(self.qid,owner,{**previous,'feedback':'부분 정답','score':2})
        with patch('app.subjects.hanja.ai_grader.generate_json',new_callable=AsyncMock,return_value={'score':0,'feedback':'유지합니다.'}):
            data=self.appeal().json();self.assertEqual(data['score'],2);self.assertEqual(data['added_score'],0)

class CentralScoreTests(unittest.TestCase):
    def test_updates_only_owned_row_without_duplicate_credit(self):
        from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, select, func
        from . import team_db
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+directory+'/central.db')
            table=Table('quiz_logs',MetaData(),Column('id',Integer,primary_key=True),
                Column('user_id',String),Column('user_name',String),Column('subject',String),
                Column('earned_score',Integer),Column('is_correct',Integer),Column('solution',String))
            table.metadata.create_all(engine)
            with engine.begin() as conn:
                conn.execute(table.insert(),[{'id':1,'user_id':'student','user_name':'학생','subject':'hanja','earned_score':0},
                                            {'id':2,'user_id':'other','user_name':'다른 학생','subject':'hanja','earned_score':1}])
            result={'score':3,'base_score':3,'feedback':'동의어 인정'}
            with patch('app.subjects.hanja.team_db.table',return_value=(engine,table)),patch.object(team_db.shared,'resolve_user_id',side_effect=lambda name,uid:uid):
                team_db.apply_appeal(1,'학생','student',result)
                team_db.apply_appeal(1,'학생','student',result)
                with self.assertRaises(LookupError):team_db.apply_appeal(2,'학생','student',result)
            with engine.connect() as conn:
                self.assertEqual(conn.scalar(select(func.sum(table.c.earned_score))),4)
            engine.dispose()

if __name__=='__main__':unittest.main()
