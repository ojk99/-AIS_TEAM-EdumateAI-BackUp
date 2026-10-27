"""Google GenAI SDK. v1 우선, 지원하지 않는 기능만 v1beta로 재시도."""
import asyncio,json,re
from google import genai
from google.genai import types, errors
from .config import load_settings, api_key, key_help

async def generate_json(system, data, schema, temperature=0):
    settings=load_settings();key=api_key()
    if not key:raise ValueError(key_help())
    preferred=settings.get('HANJA_GEMINI_MODEL','gemini-3.5-flash-lite')
    if not re.fullmatch(r'[a-zA-Z0-9._-]+',preferred):raise ValueError('Gemini 모델 이름을 확인해 주세요.')
    version=settings.get('HANJA_GEMINI_API_VERSION','v1')
    if version not in ('v1','v1beta'):raise ValueError('Gemini API 버전은 v1 또는 v1beta로 설정해 주세요.')
    # v1은 일부 모델의 systemInstruction/JSON 스키마를 지원하지 않을 수 있음.
    # 인증/한도/네트워크 오류는 다른 버전으로 우회하지 않고 호출자에게 전달.
    for candidate_version in ([version,'v1beta'] if version=='v1' else [version]):
        client=genai.Client(api_key=key,http_options=types.HttpOptions(api_version=candidate_version,timeout=25000))
        try:
            async with client.aio as ai:
                listed=await ai.models.list(config={'page_size':100})
                models=[]
                async for model in listed:
                    name=(model.name or '').removeprefix('models/')
                    if 'generateContent' in (model.supported_actions or []):models.append(name)
                # 실제 키로 조회된 모델만 사용. 지정 모델이 없으면 경량 모델 선택.
                choices=[preferred,'gemini-2.5-flash-lite','gemini-2.5-flash']
                selected=next((name for name in choices if name in models),None)
                if selected is None:
                    selected=next((name for name in sorted(models) if 'flash' in name and not any(x in name for x in ['image','audio','tts','live'])),None)
                if selected is None:raise ValueError('사용 가능한 Gemini 텍스트 모델이 없습니다. 모델 설정과 API 키 권한을 확인해 주세요.')
                response=await ai.models.generate_content(model=selected,contents=json.dumps(data,ensure_ascii=False),config=types.GenerateContentConfig(system_instruction=system,temperature=temperature,response_mime_type='application/json',response_schema=schema,max_output_tokens=1600))
                if not response.candidates or response.candidates[0].finish_reason!=types.FinishReason.STOP:raise ValueError('AI 응답이 완성되지 않았습니다.')
                return json.loads(response.text)
        except errors.APIError as exc:
            if candidate_version=='v1' and exc.code in (400,404):continue
            raise
    raise ValueError('현재 모델/API 버전이 해당 기능을 지원하지 않습니다.')
