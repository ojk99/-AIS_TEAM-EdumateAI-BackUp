"""Run: python -m hanja.test_practical"""
import os,unittest,json
from unittest.mock import patch
from fastapi.testclient import TestClient
from .standalone import app
from .practical import WORDS,grade_practical,validate_sentence
class PracticalTests(unittest.TestCase):
    def test_all_words(self):
        self.assertEqual(len(WORDS),30)
        for w in WORDS:
            s=validate_sentence('친구들과 '+w['target_word']+' 이야기를 나누어요.',w)
            for answer in [w['reading'],s['original'].replace(w['target_word'],w['reading'])]:self.assertEqual(grade_practical(s,answer)['score'],1)
            for answer in ['','모르겠어요']:self.assertEqual(grade_practical(s,answer)['score'],0)
    def test_invalid_characters(self):
        w=next(w for w in WORDS if w['id']=='news-08')
        for bad in ['우리 家族이 Новым News를 읽어요.','우리 家族이 �를 봐요.','우리 家族이 😀를 봐요.','우리 家族이 ㄱㄴ을 봐요.','우리 家族이 あ를 봐요.','우리 家族이 숨은\u200b 문자를 봐요.']:
            with self.assertRaises(ValueError):validate_sentence(bad,w)
        for w in WORDS:self.assertEqual(validate_sentence(w['fallback_sentence'],w)['original'],w['fallback_sentence'])
    def test_api_offline(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':''}):
            c=TestClient(app,headers={'X-Hanja-Learner':__import__('uuid').uuid4().hex});c.headers['X-Hanja-Learner']=str(__import__('uuid').uuid4());q=c.post('/hanja/api/practical/quiz',json={'word_id':'news-08'});self.assertEqual(q.status_code,200,q.text);q=q.json()
            self.assertFalse(any(k in q for k in ['answer','reading','model_answer']))
            r=c.post('/hanja/api/grade',json={'question_id':q['question_id'],'answer':'가족'});self.assertEqual(r.json()['score'],1,r.text)
            self.assertEqual(c.post('/hanja/api/grade',json={'question_id':q['question_id'],'answer':'다른 답'}).json()['score'],1)
            self.assertEqual(len(c.get('/hanja/api/sentences').json()),30)
            self.assertIn('data-mode="idioms"',c.get('/hanja').text)
    def test_ai_generation_and_no_ai_grading(self):
        calls=[];sentence='우리 家族이 산책을 해요.'
        async def generate(*args,**kw):
            calls.append(kw)
            return {'sentence':sentence}
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-placeholder'}),patch('app.subjects.hanja.practical.generate_json',generate):
            c=TestClient(app,headers={'X-Hanja-Learner':__import__('uuid').uuid4().hex});c.headers['X-Hanja-Learner']=str(__import__('uuid').uuid4());q=c.post('/hanja/api/practical/quiz',json={'word_id':'news-08'});self.assertEqual(q.status_code,200,q.text);q=q.json();self.assertIn('Gemini',q['generation_method']);self.assertEqual(len(calls),1)
            r=c.post('/hanja/api/grade',json={'question_id':q['question_id'],'answer':'우리 가족이 산책을 해요.'});self.assertEqual(r.json()['score'],1,r.text);self.assertEqual(len(calls),1)
            sentence='우리 家族이 Новым News를 읽어요.'
            q=c.post('/hanja/api/practical/quiz',json={'word_id':'news-08'});self.assertEqual(q.status_code,200,q.text);self.assertEqual(q.json()['question'],next(w for w in WORDS if w['id']=='news-08')['fallback_sentence']);self.assertIn('대체',q.json()['generation_method'])
if __name__=='__main__':unittest.main()
