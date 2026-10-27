"""넉넉한 1·3·5점 연습 채점. 무관한 답은 1점, 빈 답 제출은 라우터에서 차단."""
import re, unicodedata

def compact(s):
    return re.sub(r'[\s.,!?，。！？·]', '', unicodedata.normalize('NFKC',s))

def grade_sentence(sentence, answer):
    text=compact(answer)
    exact=bool(text) and text==compact(sentence['model_answer'])
    criteria=[]
    for rule in sentence['rubric']:
        matched=bool(text) and (exact or any(re.search(p,text) for p in rule['patterns']))
        contradicted=not exact and any(re.search(p,text) for p in rule.get('blocks',[]))
        criteria.append({'label':rule['label'],'matched':matched and not contradicted,'contradicted':contradicted})
    count=sum(c['matched'] for c in criteria)
    keyword=bool(text) and any(compact(k) in text for k in sentence.get('keywords',[]))
    score=5 if exact or count==len(criteria) or count>=2 and not any(c['contradicted'] for c in criteria) else 1 if text and any(text==compact(k) for k in sentence.get("keywords",[])) else 3 if count else 1
    feedback={5:'정답입니다',3:'뜻의 일부를 잘 설명했어요. 나머지도 이어서 풀어 볼까요?',1:'아직 뜻풀이가 부족해요. 풀이 예와 비교해 보세요.',0:'문장의 뜻과 관련된 내용을 적어 보세요.'}[score]
    return {'score':score,'base_score':5,'correct':score==5,'criteria':criteria,'feedback':feedback,'model_answer':sentence['model_answer'] if score<5 else None,'grading_method':'핵심 의미·동의 표현 기준 연습 채점'}
