import {readFileSync} from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const source=readFileSync(new URL('./bank_ui.js',import.meta.url),'utf8');
class Element{constructor(){this.value='';this.textContent='';this.checked=false;this.children=[];this.hidden=true;this.classList={add:()=>{this.hidden=true},remove:()=>{this.hidden=false}}}replaceChildren(){this.children=[]}append(x){this.children.push(x)}focus(){}}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id)};
let requestMode='bank',calls=[],solved=0;const timers=new Map();let timer=0;
const currentUser={user_id:'u',user_name:'학생'};
const context=vm.createContext({console,document:{createElement:()=>new Element()},localStorage:{getItem:()=>null,setItem(){}},portalAccount:()=>currentUser,learnerId:'device',apiBase:()=>'/hanja/api/',USE_API:true,mode:'bank',$:get,bindAnswerEnter(){},refreshTeamStatus(){},setTimeout(fn){timers.set(++timer,fn);return timer},clearTimeout(id){timers.delete(id)},hanjaFetch:async(url,options)=>{
 calls.push({url,body:options?.body&&JSON.parse(options.body)});
 if(url.endsWith('unit-stats'))return {ok:true,json:async()=>({units:[{unit_name:'9~6급 한자어',total:2,solved,remaining:2-solved}]})};
 if(url.endsWith('/quiz')){
  if(requestMode==='empty')return {ok:false,json:async()=>({detail:{code:'NO_AVAILABLE_QUESTION',message:'현재 AI 출제 서버와 연결할 수 없으며, 선택한 단원의 문제은행 DB에도 등록된 문제가 없습니다.'}})};
  return {ok:true,json:async()=>({question_id:'q',question:'뜻풀이',question_type:'essay',base_score:5,source:requestMode==='ai'?'ai':'bank',ai_mode:requestMode==='ai',review:requestMode==='review',options:[],message:requestMode==='review'?'복습 안내':''})};
 }
 if(url.endsWith('/grade')){solved=1;return {ok:true,json:async()=>({score:5,base_score:5,correct:true,added_score:requestMode==='review'?0:5,review:requestMode==='review',answer:'정답',feedback:'해설',grading_method:'AI'})}};
 throw Error(url);
}});
vm.runInContext(source,context);const run=s=>vm.runInContext(s,context);
await run('enterBank()');assert.equal(get('bank-unit').children[0].textContent,'9~6급 한자어 (0/2)');
requestMode='ai';await run('newBankQuestion()');assert(get('bank-ai').checked);assert.equal(get('bank-unit').children[0].textContent,'9~6급 한자어');
requestMode='bank';await run('newBankQuestion()');assert.equal(get('bank-ai').checked,false);
get('bank-answer').value='내 답';await run('submitBank()');assert.equal(get('bank-unit').children[0].textContent,'9~6급 한자어 (1/2)');assert.equal(timers.size,0,'essay must not auto-advance');
const before=calls.length;await run('submitBank()');assert.equal(calls.length,before,'no duplicate submit');
requestMode='review';await run('newBankQuestion()');get('bank-answer').value='내 답';await run('submitBank()');assert(get('bank-result').children.some(x=>x.textContent.includes('+0점')));
requestMode='empty';await run('newBankQuestion()');assert.equal(get('bank-modal').hidden,false);assert(get('bank-modal-message').textContent.includes('등록된 문제가 없습니다.'));
const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');assert(html.includes(source.trim()),'inline bank UI source must match');
console.log('PASS bank UI: OFF counts, ON transition, reverse fallback, solved refresh, review +0, essay manual, duplicate submit, empty modal');
const workingFetch=context.hanjaFetch;
context.hanjaFetch=async()=>{throw Error('offline')};
run("bankUnits=defaultBankUnits.map(unit_name=>({unit_name}));bankState.unit='삭제된 단원';bankLoaded=false");
await run('enterBank()');assert.equal(get('bank-unit').children.length,4);assert.equal(get('bank-unit').value,'9~6급 한자어');assert(get('bank-count-note').textContent.includes('서버에 연결하지 못했습니다'));
assert(!get('bank-unit').children[0].textContent.includes('0/0'));
context.hanjaFetch=async()=>({ok:false,status:404,json:async()=>({detail:'Not Found'})});
await run('enterBank()');assert(get('bank-count-note').textContent.includes('서버를 재시작'));
context.hanjaFetch=async()=>({ok:true,json:async()=>({units:[]})});
await run('enterBank()');assert.equal(get('bank-unit').children.length,4);assert(get('bank-count-note').textContent.includes('응답 형식'));
context.hanjaFetch=workingFetch;
requestMode='bank';await run('newBankQuestion()');assert.equal(get('bank-unit').children.length,1);assert.equal(run('bankStatsError'),'');
console.log('PASS units: offline, missing API, invalid response, stale selection, retry recovery');
