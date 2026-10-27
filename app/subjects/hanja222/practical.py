"""AI는 예문만 생성하고, 정답은 검증한 한자어의 독음으로 채점한다."""
import json, os, re, unicodedata, uuid
from pathlib import Path
from .config import api_key
from .gemini_client import generate_json
WORDS=json.loads((Path(__file__).parent/'data/practical_words.json').read_text(encoding='utf-8'))
def compact(text):
    return re.sub(r'[\s.,!?，。！？·]','',unicodedata.normalize('NFKC',text))
def grade_practical(word,answer):
    correct=bool(answer.strip()) and compact(word['reading']) in compact(answer)
    return {'score':int(correct),'base_score':1,'correct':correct,'answer':word['reading'],'model_answer':word['original'].replace(word['target_word'],word['reading']),'meaning':word['target_meaning'],'feedback':'정답입니다!' if correct else '다시 익혀 보아요.','grading_method':'한자어 일치 채점 · AI 사용 안 함','central_score_status':'not_configured'}
def validate_sentence(sentence,word):
    if not isinstance(sentence,str) or not len(word['target_word'])+4<=len(sentence)<=100 or re.search(r'[<>\n\r]',sentence):raise ValueError('Invalid sentence')
    text=unicodedata.normalize('NFKC',sentence);target=unicodedata.normalize('NFKC',word['target_word'])
    if text.count(target)!=1 or not re.fullmatch(r"[가-힣0-9 .,!?，。！？·…'\"‘’“”()\-]+",text.replace(target,'')) or not re.search('[가-힣]',text) or compact(word['reading']) in compact(text):raise ValueError('Invalid sentence')
    return {**word,'original':text.strip().replace(target,word['target_word']),'kind':'practical_word'}
async def _generate_practical(word):
    key=api_key()
    if not key:return validate_sentence(word['fallback_sentence'],word),'준비된 예문 · 30개 중 출제'
    schema={'type':'OBJECT','properties':{'sentence':{'type':'STRING'}},'required':['sentence']}
    system='초등학교 저학년용 실용 한자어 퀴즈 문장을 만들어라. 지정한 한자어를 정확히 한 번 넣고 나머지는 쉬운 한글로 작성한다. 정답인 한글 독음을 쓰지 않는다. 일상생활, 가족, 학교, 안전, 문화 주제에서 15~50자 안팎의 자연스럽고 새로운 문장 하나만 만든다. 다른 한자, 폭력적 내용, 정답 설명, 괄호, 외국어를 넣지 않는다. 실제 신문 인용이라고 주장하지 않는다.'
    raw=await generate_json(system,{'word':word['target_word'],'reading':word['reading'],'meaning':word['target_meaning'],'request_id':str(uuid.uuid4())},schema,temperature=0.4)
    return validate_sentence(raw['sentence'],word),'Gemini AI가 새로 만든 연습 문장'

async def generate_practical(word):
    try:return await _generate_practical(word)
    except Exception:return validate_sentence(word['fallback_sentence'],word),'준비된 예문 · AI 생성 실패로 대체'
