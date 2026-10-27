// Loaded inline into index.html by the subject router; retained here as readable source.
const defaultBankUnits=['9~6급 한자어','5~1급 한자어','실용 한자어','사자성어'];
let bankUnits=defaultBankUnits.map(unit_name=>({unit_name})),bankBusy=false,bankTimer=null,bankLoaded=false,bankStatsError='';
const bankStateKey='edumate.hanja.bank.v1.'+(portalAccount().user_id||portalAccount().user_name||learnerId);
let bankState;try{bankState=JSON.parse(localStorage.getItem(bankStateKey)||'null')}catch{}
if(!bankState||typeof bankState!=='object')bankState={unit:'9~6급 한자어',ai:false,current:null};
if(/^[1-9]급 한자어$/.test(bankState.unit))bankState.unit=Number(bankState.unit[0])>=6?'9~6급 한자어':'5~1급 한자어';
function saveBankState(){localStorage.setItem(bankStateKey,JSON.stringify(bankState))}
function clearBankTimer(){if(bankTimer){clearTimeout(bankTimer);bankTimer=null}}
async function bankRequest(path,body){
 let response;try{response=await hanjaFetch(apiBase()+'question-bank/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})}catch{throw new Error('한자 문제은행 서버에 연결하지 못했습니다. AI OFF여도 서버에 있는 문제은행 DB 조회·채점·기록 저장에는 연결이 필요합니다. Python 서버를 실행하고 /hanja/ 주소로 접속해 주세요.')}
 let data;try{data=await response.json()}catch{throw new Error('문제은행 API가 JSON을 반환하지 않았습니다. HTML 파일을 직접 열지 말고 서버의 /hanja/ 주소로 접속해 주세요.')}
 if(!response.ok){if(response.status===404)throw new Error('문제은행 API를 찾지 못했습니다. 한자 폴더의 router.py, bank_router.py, question_bank.py를 함께 업데이트하고 서버를 재시작해 주세요.');const detail=data.detail;const error=new Error(typeof detail==='object'?detail.message:detail||'요청을 처리하지 못했습니다.');error.code=detail?.code;throw error}return data
}
async function refreshBankStats(){
 try{const data=await bankRequest('unit-stats');if(!Array.isArray(data.units)||!data.units.length||data.units.some(u=>!u||typeof u.unit_name!=='string'||!u.unit_name.trim()||!Number.isInteger(u.total)||!Number.isInteger(u.solved)))throw new Error('단원 통계 응답 형식이 맞지 않습니다. 최신 한자 서버 파일을 적용하고 재시작해 주세요.');bankUnits=data.units.filter(u=>! /^[1-9]급 한자$/.test(u.unit_name));if(!bankUnits.length)bankUnits=defaultBankUnits.map(unit_name=>({unit_name}));bankStatsError='';bankLoaded=true;renderBankUnits()}
 catch(e){bankStatsError=e.message;bankLoaded=false;renderBankUnits();throw e}
}
function renderBankUnits(){
 const el=$('bank-unit');el.replaceChildren();
 for(const unit of bankUnits){const option=document.createElement('option');option.value=unit.unit_name;option.textContent=unit.unit_name+(bankState.ai?'':Number.isInteger(unit.total)?` (${unit.solved}/${unit.total})`:' (통계 확인 전)');el.append(option)}
 if(!bankUnits.some(u=>u.unit_name===bankState.unit)){bankState.unit=bankUnits[0].unit_name;saveBankState()}
 el.value=bankState.unit;
 $('bank-count-note').textContent=bankStatsError?'단원 통계를 불러오지 못했어요. '+bankStatsError+' 새 문제 버튼을 누르면 다시 확인합니다.':bankState.ai?'AI가 실시간으로 새 문제를 만듭니다.':'문제은행 모드: AI 대신 서버의 저장된 문제를 사용합니다. 괄호는 맞힌 한자어 / 전체 한자어 수입니다. 한자어마다 4가지 유형 중 하나가 나오며, 틀린 한자어는 한 바퀴 뒤 다시 나옵니다.'
}
function showBankModal(message){$('bank-modal-message').textContent=message;$('bank-modal').classList.remove('hidden');$('bank-modal-close').focus?.()}
function renderBank(){clearBankTimer();$('bank-ai').checked=!!bankState.ai;$('bank-ai-label').textContent=bankState.ai?'ON · AI 기반 출제':'OFF · 문제은행 출제';$('bank-unit').disabled=bankBusy;$('bank-ai').disabled=bankBusy;$('bank-new').disabled=bankBusy;renderBankUnits();const q=bankState.current;$('bank-question').textContent=q?.question||'단원을 선택하고 새 문제를 눌러 주세요.';$('bank-source').textContent=q?(q.source==='ai'?'AI 생성 문제':q.review?'문제은행 복습':'문제은행 미풀이 문제')+' · '+q.base_score+'점':'';$('bank-notice').textContent=bankBusy?'처리 중이에요…':q?.message||'';$('bank-answer').value=q?.draft||'';$('bank-answer').disabled=bankBusy||!!q?.result;$('bank-submit').disabled=bankBusy||!q||!!q.result;$('bank-options').replaceChildren();
 if(q?.options?.length){for(const value of q.options){const button=document.createElement('button');button.textContent=value;button.disabled=bankBusy||!!q.result;button.onclick=()=>{q.draft=value;saveBankState();$('bank-answer').value=value;submitBank()};$('bank-options').append(button)}}
 $('bank-result').replaceChildren();if(q?.result){const r=q.result;for(const line of [(r.correct?'정답입니다!':'답을 확인해 보아요.')+` ${r.score}/${r.base_score}점`,'이번 누적 포인트: +'+r.added_score+'점'+(r.review?' (복습 미반영)':''),'내 답: '+q.draft,'정답 예: '+r.answer,r.feedback,r.grading_method]){const p=document.createElement('p');p.textContent=line||'';$('bank-result').append(p)}
 if(r.correct&&q.question_type!=='essay'&&mode==='bank'){const p=document.createElement('p');p.textContent='3초 뒤 다음 문제로 넘어가요.';$('bank-result').append(p);bankTimer=setTimeout(()=>{bankTimer=null;if(mode==='bank'&&bankState.current===q&&!bankBusy)newBankQuestion()},3000)}}
}
async function enterBank(){renderBank();if(!USE_API){$('bank-notice').textContent='문제은행·AI 출제는 서버로 실행한 /hanja/ 화면에서 사용할 수 있어요.';$('bank-new').disabled=true;return}if(bankLoaded)return;bankLoaded=true;try{await refreshBankStats()}catch(e){bankLoaded=false;$('bank-notice').textContent=e.message}}
async function newBankQuestion(){if(bankBusy)return;clearBankTimer();bankBusy=true;renderBank();try{if(!bankLoaded)await refreshBankStats();const q=await bankRequest('quiz',{unit_name:bankState.unit,ai_mode:!!bankState.ai});bankState.ai=q.ai_mode;bankState.current={...q,draft:'',result:null};saveBankState();await refreshBankStats()}catch(e){if(e.code==='NO_AVAILABLE_QUESTION'){bankState.ai=true;bankState.current=null;saveBankState();showBankModal(e.message)}else showBankModal(e.message)}finally{bankBusy=false;renderBank()}}
async function submitBank(){const q=bankState.current;if(bankBusy||!q||q.result)return;q.draft=$('bank-answer').value;if(!q.draft.trim()){$('bank-notice').textContent='답안을 입력해 주세요.';return}clearBankTimer();bankBusy=true;saveBankState();renderBank();let failure='';try{const r=await bankRequest('grade',{question_id:q.question_id,answer:q.draft,user_id:portalAccount().user_id});q.result=r;q.review=!!r.review;saveBankState();await refreshBankStats();refreshTeamStatus()}catch(e){failure=e.message}finally{bankBusy=false;renderBank();if(failure)$('bank-notice').textContent=failure}}
$('bank-unit').onchange=()=>{clearBankTimer();bankState.unit=$('bank-unit').value;bankState.current=null;saveBankState();renderBank()};
$('bank-ai').onchange=()=>{clearBankTimer();bankState.ai=$('bank-ai').checked;bankState.current=null;saveBankState();renderBank()};
$('bank-new').onclick=newBankQuestion;$('bank-submit').onclick=submitBank;
$('bank-answer').oninput=()=>{if(bankState.current){bankState.current.draft=$('bank-answer').value;saveBankState()}};
bindAnswerEnter($('bank-answer'),submitBank);
$('bank-modal-close').onclick=()=>$('bank-modal').classList.add('hidden');
