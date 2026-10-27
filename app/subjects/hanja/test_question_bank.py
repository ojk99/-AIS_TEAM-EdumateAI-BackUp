import asyncio,json,sqlite3,uuid
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from . import question_bank as bank,quiz_logs,team_db
from .router import create_router
from .storage import HanjaStorage

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(bank,'DB_PATH',tmp_path/'question_bank.db')
    monkeypatch.setattr(quiz_logs,'DB_PATH',tmp_path/'edumate.db')
    original=bank.source_data
    monkeypatch.setattr(bank,'source_data',lambda name:original(name)[:2])
    bank.init_question_bank()
    async def no_ai(*args,**kwargs):raise RuntimeError('offline')
    monkeypatch.setattr(bank,'generate_ai_question',no_ai)
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',no_ai)

def add_manual(unit='手動',typ='단답형',points=3):
    with bank.connection() as c:
        cur=c.execute('''INSERT INTO question_bank(subject,unit_name,question_type,points,question_text,correct_answer,explanation)
         VALUES ('hanja',?,?,?,?,?,?)''',(unit,typ,points,'父의 뜻을 쓰세요.','아버지','아비도 같은 의미입니다.'))
        return cur.lastrowid

def api(tmp_path,uid='student'):
    app=FastAPI();app.include_router(create_router(storage=HanjaStorage('sqlite:///'+str(tmp_path/'sessions.db'))))
    return TestClient(app,headers={'X-Hanja-Learner':str(uuid.uuid4()),'X-EduMate-Account':quote(json.dumps({'user_name':'학생','user_id':uid,'grade':2}))})

def test_schema_migration_preserves_sources_and_is_idempotent():
    with bank.connection() as c:
        count=c.execute('SELECT COUNT(*) FROM question_bank').fetchone()[0]
        columns=[r['name'] for r in c.execute('PRAGMA table_info(question_bank)')]
        assert columns==['id','subject','grade','grade_group','unit_name','sub_topic','question_type','difficulty','points','question_text','choices_json','correct_answer','explanation','source_type','source_log_id','created_by','created_by_name','created_at']
        assert count==28 # 2 chars*4 + 4 words*4 + 2 practical + 2 idioms
        assert c.execute('SELECT COUNT(*) FROM hanja_bank_seeds WHERE source_json IS NOT NULL').fetchone()[0]==count
    mid=add_manual()
    bank.init_question_bank();bank.init_question_bank()
    with bank.connection() as c:assert c.execute('SELECT COUNT(*) FROM question_bank').fetchone()[0]==count+1
    assert bank.get_question(mid)['correct_answer']=='아버지'

def test_forward_reverse_and_empty_fallback(monkeypatch):
    mid=add_manual();row=bank.get_question(mid)
    async def ai(*args):return {**row,'id':None}
    monkeypatch.setattr(bank,'generate_ai_question',ai)
    r,p=asyncio.run(bank.issue_question('빈 단원','u',False,2));assert p['ai_mode'] and p['source']=='ai'
    async def fail(*args):raise RuntimeError()
    monkeypatch.setattr(bank,'generate_ai_question',fail)
    r,p=asyncio.run(bank.issue_question('手動','u',True,2));assert p['ai_mode'] is False and not p['review']
    with bank.connection() as c:bank.mark_bank_question_solved(c,mid,'u')
    r,p=asyncio.run(bank.issue_question('手動','u',False,2));assert p['review'] and p['message']==bank.REVIEW_MESSAGE
    with pytest.raises(RuntimeError,match='현재 AI 출제 서버'):asyncio.run(bank.issue_question('빈 단원','u',False,2))

def test_manual_short_and_essay_use_ai(monkeypatch):
    calls=[]
    async def semantic(system,data,schema,**kwargs):calls.append(data);return {'score':data['max_score'],'feedback':'같은 의미입니다.'}
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',semantic)
    for typ in ('단답형','서술형'):
        row=bank.get_question(add_manual(typ=typ))
        result=asyncio.run(bank.grade_bank_question_by_ai(row,'아비'))
        assert result['correct'] and result['score']==3 and 'Gemini' in result['grading_method']
    assert len(calls)==2

def test_invalid_ai_grading_uses_emergency(monkeypatch):
    async def invalid(*args,**kwargs):return {'score':100,'feedback':'wrong'}
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',invalid)
    result=asyncio.run(bank.grade_bank_question_by_ai(bank.get_question(add_manual()),'아버지'))
    assert result['score']==3 and '비상' in result['grading_method']

def test_stats_and_review_zero_reward(tmp_path):
    mid=add_manual();c=api(tmp_path)
    q=c.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動','ai_mode':True}).json()
    assert q['source']=='bank' and 'correct_answer' not in q and 'answer' not in q
    r=c.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아버지','user_id':'student'})
    assert r.status_code==200,r.text
    r=r.json();assert r['added_score']==3 and r['total_score']==3
    units=c.get('/hanja/api/question-bank/unit-stats').json()['units'];u=next(x for x in units if x['unit_name']=='手動')
    assert (u['solved'],u['total'],u['remaining'])==(1,1,0)
    repeat=c.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아버지'}).json()
    assert repeat['log_id']==r['log_id']
    review=c.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動','ai_mode':False}).json();assert review['review']
    rr=c.post('/hanja/api/question-bank/grade',json={'question_id':review['question_id'],'answer':'아버지'}).json()
    assert rr['correct'] and rr['score']==3 and rr['added_score']==0 and rr['total_score']==3
    other=api(tmp_path,'another')
    assert other.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아버지'}).status_code==404
    assert next(x for x in other.get('/hanja/api/question-bank/unit-stats').json()['units'] if x['unit_name']=='手動')['solved']==0

def test_two_outstanding_questions_cannot_double_award(tmp_path):
    add_manual();c=api(tmp_path)
    qs=[c.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動'}).json() for _ in range(2)]
    def grade(q):return c.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아버지'}).json()
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(grade,qs))
    assert sorted(r['added_score'] for r in results)==[0,3],results
    assert quiz_logs.get_user_status('학생',user_id='student')['total_score']==3

def test_bank_mark_failure_retry_no_duplicate_points(tmp_path,monkeypatch):
    add_manual();c=api(tmp_path);q=c.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動'}).json()
    mark=bank.mark_bank_question_solved
    def fail(*args):raise RuntimeError('disk')
    monkeypatch.setattr(bank,'mark_bank_question_solved',fail)
    body={'question_id':q['question_id'],'answer':'아버지'}
    assert c.post('/hanja/api/question-bank/grade',json=body).status_code==503
    monkeypatch.setattr(bank,'mark_bank_question_solved',mark)
    r=c.post('/hanja/api/question-bank/grade',json=body).json()
    assert r['total_score']==3 and r['added_score']==0
    with bank.connection() as conn:assert conn.execute('SELECT COUNT(*) FROM question_bank_solved').fetchone()[0]==1

def test_empty_bank_api_has_exact_modal_message(tmp_path):
    c=api(tmp_path)
    with bank.connection() as conn:conn.execute("DELETE FROM question_bank WHERE unit_name=?",(bank.WORD_UNITS[0],))
    response=c.post('/hanja/api/question-bank/quiz',json={'unit_name':bank.WORD_UNITS[0],'ai_mode':False})
    assert response.status_code==503
    assert response.json()['detail']['message']==bank.EMPTY_MESSAGE

def test_previously_marked_shared_problem_is_zero_reward(tmp_path):
    mid=add_manual()
    with bank.connection() as conn:bank.mark_bank_question_solved(conn,mid,'student')
    c=api(tmp_path);q=c.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動'}).json()
    r=c.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아버지'}).json()
    assert r['added_score']==0 and r['total_score']==0 and r['score']==3

# Retain the real generator before the offline fixture replaces it.
_real_generate_ai_question=bank.generate_ai_question

def test_ox_separates_claim_without_changing_answer():
    for key,file,item,unit,topic,typ,pts,text,opts,answer,explanation in bank._seed_rows():
        if typ=='ox':
            assert '의 뜻은 ' in text and '이고, 음은 ' in text and text.endswith('(O/X)')
    for answer in ('O','X'):
        row={'question_type':'ox','points':1,'unit_name':'한자어','difficulty':'하',
             'question_text':"經濟의 뜻과 음은 '물건을 만들고 쓰는 생활의 활동 경제'입니다.",'correct_answer':answer}
        public=bank.question_payload(row,'bank')
        assert public['question']=="經濟의 뜻은 '물건을 만들고 쓰는 생활의 활동'이고, 음은 '경제'입니다. (O/X)"
        assert row['correct_answer']==answer
        assert asyncio.run(bank.grade_bank_question_by_ai(row,answer))['correct']

def test_ai_ox_requires_separate_meaning_and_reading(monkeypatch):
    raw={'question_type':'ox','points':1,'choices':['O','X'],'correct_answer':'X',
         'question_text':'經濟의 뜻은 “학교에서 배우는 일”이고, 음은 “경제”입니다. (O/X)',
         'explanation':'음은 경제가 맞지만 뜻이 틀립니다.'}
    async def generate(*args,**kwargs):return dict(raw)
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',generate)
    row=asyncio.run(_real_generate_ai_question('한자어',4))
    assert row['correct_answer']=='X' and '음은 “경제”' in row['question_text']
    raw['question_text']="經濟의 뜻과 음은 '생활 활동 경제'입니다."
    with pytest.raises(ValueError,match='뜻·음 구분'):asyncio.run(_real_generate_ai_question('한자어',4))


def test_word_cycle_counts_and_group_completion():
    unit=bank.WORD_UNITS[0]
    stats=next(r for r in bank.get_unit_bank_stats('student') if r['unit_name']==unit)
    with bank.connection() as conn:
        raw_count=conn.execute('SELECT COUNT(*) FROM question_bank WHERE unit_name=?',(unit,)).fetchone()[0]
    assert raw_count==stats['total']*4
    first_round=[bank.pick_bank_question(unit,'student') for _ in range(stats['total'])]
    assert len({r['sub_topic'] for r in first_round})==stats['total']
    # No correct marks: every word can reappear only in the next cycle.
    second_round=[bank.pick_bank_question(unit,'student') for _ in range(stats['total'])]
    assert {r['sub_topic'] for r in first_round}=={r['sub_topic'] for r in second_round}
    with bank.connection() as conn:bank.mark_bank_question_solved(conn,first_round[0]['id'],'student')
    stats2=next(r for r in bank.get_unit_bank_stats('student') if r['unit_name']==unit)
    assert stats2['solved']==1 and stats2['remaining']==stats['total']-1
    for _ in range(stats['total']*2):
        assert bank.pick_bank_question(unit,'student')['sub_topic']!=first_round[0]['sub_topic']
    assert next(r for r in bank.get_unit_bank_stats('other') if r['unit_name']==unit)['solved']==0

def test_legacy_word_units_preserve_rows_and_solved():
    unit=bank.WORD_UNITS[0]
    row=bank.pick_bank_question(unit,'student')
    with bank.connection() as conn:
        conn.execute("UPDATE question_bank SET unit_name='9급 한자어' WHERE id=?",(row['id'],))
        conn.execute("INSERT INTO question_bank_solved(bank_id,subject,user_key) VALUES (?,'hanja','student')",(row['id'],))
    bank.init_question_bank()
    assert bank.get_question(row['id'])['unit_name']==unit
    with bank.connection() as conn:assert bank.group_is_solved(conn,row['id'],'student')
    for _ in range(8):assert bank.pick_bank_question(unit,'student')['sub_topic']!=row['sub_topic']

def test_two_variants_award_once(tmp_path):
    c=api(tmp_path);unit=bank.WORD_UNITS[0]
    with bank.connection() as conn:
        variants=[dict(r) for r in conn.execute('SELECT * FROM question_bank WHERE unit_name=? ORDER BY id LIMIT 4',(unit,))]
    # Two outstanding sessions for the same word, with different variation IDs.
    from . import bank_router
    original=bank.issue_question
    async def issue(*args):
        row=variants.pop(0);return row,bank.question_payload(row,'bank')
    bank.issue_question=issue
    try:
        q1=c.post('/hanja/api/question-bank/quiz',json={'unit_name':unit}).json()
        q2=c.post('/hanja/api/question-bank/quiz',json={'unit_name':unit}).json()
    finally:bank.issue_question=original
    with bank.connection() as conn:
        a1=conn.execute('SELECT correct_answer FROM question_bank WHERE id=?',(q1['bank_id'],)).fetchone()[0]
        a2=conn.execute('SELECT correct_answer FROM question_bank WHERE id=?',(q2['bank_id'],)).fetchone()[0]
    r1=c.post('/hanja/api/question-bank/grade',json={'question_id':q1['question_id'],'answer':a1}).json()
    r2=c.post('/hanja/api/question-bank/grade',json={'question_id':q2['question_id'],'answer':a2}).json()
    assert r1['added_score']>0 and r2['added_score']==0 and r2['review']


def test_group_ai_failure_keeps_reserved_word(monkeypatch):
    unit=bank.WORD_UNITS[0];targets=[]
    async def generate(unit,grade,target=None):
        targets.append(target['sub_topic'])
        raise RuntimeError('AI offline')
    monkeypatch.setattr(bank,'generate_ai_question',generate)
    count=next(r for r in bank.get_unit_bank_stats('u') if r['unit_name']==unit)['total']
    for _ in range(count):
        row,public=asyncio.run(bank.issue_question(unit,'u',True,4))
        assert row['sub_topic']==targets[-1] and not public['ai_mode']
    assert len(set(targets))==count
    # Seen state is persisted in SQLite, not reset by initialization/restart.
    bank.init_question_bank()
    with bank.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hanja_bank_seen WHERE user_key=? AND unit_name=?',('u',unit)).fetchone()[0]==count


def test_idiom_guard_blocks_general_words_in_bank_and_ai(monkeypatch):
    assert bank.valid_idiom_question('一石二鳥의 뜻을 써 주세요.')
    for text in ('衣食住의 뜻을 써 주세요.','의식주의 뜻을 써 주세요.','環境保護의 뜻을 써 주세요.'):
        assert not bank.valid_idiom_question(text)
    with bank.connection() as conn:
        cur=conn.execute("INSERT INTO question_bank(subject,unit_name,question_type,points,question_text,correct_answer) VALUES ('hanja','사자성어','서술형',5,?,?)",('衣食住의 뜻을 써 주세요.','옷 음식 집'))
        bad_id=cur.lastrowid
    stats=next(r for r in bank.get_unit_bank_stats('u') if r['unit_name']=='사자성어')
    assert stats['total']==2
    for _ in range(8):assert bank.pick_bank_question('사자성어','u')['id']!=bad_id
    with pytest.raises(ValueError,match='사자성어'):bank.question_payload(bank.get_question(bad_id),'bank')
    calls=[]
    async def bad(system,data,schema,**kwargs):
        calls.append(data)
        return {'question_type':'서술형','points':5,'choices':[],'question_text':'衣食住의 뜻을 써 주세요.','correct_answer':'옷 음식 집','explanation':'생활의 기본 조건'}
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',bad)
    monkeypatch.setattr(bank,'generate_ai_question',_real_generate_ai_question)
    row,public=asyncio.run(bank.issue_question('사자성어','u',True,4))
    assert public['source']=='bank' and bank.valid_idiom_question(public['question'])
    assert calls[0]['target_word'] in {r['original'] for r in bank.source_data('sentences.json')}

def test_bank_appeal_updates_points_and_solved_once(tmp_path,monkeypatch):
    mid=add_manual();client=api(tmp_path)
    q=client.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動','ai_mode':False}).json()
    graded=client.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아비'}).json()
    assert graded['score']==0 and graded['appeal_available']
    async def review(*args,**kwargs):return {'score':3,'feedback':'아비와 아버지는 같은 뜻입니다.'}
    monkeypatch.setattr('app.subjects.hanja.ai_grader.generate_json',review)
    payload={'question_id':q['question_id'],'reason':'아비도 아버지라는 뜻입니다.'}
    response=client.post('/hanja/api/appeal',json=payload)
    assert response.status_code==200,response.text
    result=response.json();assert result['score']==3 and result['added_score']==3
    assert client.post('/hanja/api/appeal',json=payload).json()==result
    with bank.connection() as conn:assert bank.group_is_solved(conn,mid,'student')
    row=team_db.owned_log(result['log_id'],'학생','student')
    assert row['earned_score']==3 and row['is_correct']==1


def test_bank_ai_grade_has_no_appeal(tmp_path,monkeypatch):
    add_manual();client=api(tmp_path)
    q=client.post('/hanja/api/question-bank/quiz',json={'unit_name':'手動','ai_mode':False}).json()
    async def grade(*args,**kwargs):return {'score':3,'feedback':'동의어를 인정합니다.'}
    monkeypatch.setattr('app.subjects.hanja.gemini_client.generate_json',grade)
    result=client.post('/hanja/api/question-bank/grade',json={'question_id':q['question_id'],'answer':'아비'}).json()
    assert result['ai_graded'] and not result['appeal_available']
    assert client.post('/hanja/api/appeal',json={'question_id':q['question_id'],'reason':'검토 요청'}).status_code==409
