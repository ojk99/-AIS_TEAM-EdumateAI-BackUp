"""뜻과 음의 순서를 바꾸거나 구두점을 넣어도 같은 답으로 채점."""
import re,unicodedata

def compact(value):
    value=unicodedata.normalize('NFKC',value)
    value=re.sub(r'(뜻|읽는말|읽는방법|독음|음)\s*[:：]','',value)
    return re.sub(r'[\s.,!?·:：/()\-]','',value)

def grade_meaning_reading(item,answer):
    text=compact(answer)
    readings=item.get('accepted_readings') or [item['reading']]
    meanings=[item['meaning'],*item.get('accepted_meanings',[])]
    if item.get('character')=='心身':meanings+=['몸과 마음','마음과 신체','신체와 마음']
    full=[*item.get('accepted_huneum',[]),*(m+' '+r for m in meanings for r in readings),*(r+' '+m for m in meanings for r in readings)]
    if text and any(text==compact(v) for v in full):return 5
    if text and (any(text==compact(r) for r in readings) or any(text==compact(m) for m in meanings)):return 2
    return 0
