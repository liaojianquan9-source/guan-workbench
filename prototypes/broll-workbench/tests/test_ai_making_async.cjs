const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ProductionClient=require('../public/production_client.js');
const ProductionTimeline=require('../public/production_timeline.js');

const script=fs.readFileSync(path.join(__dirname,'../public/ai_making.js'),'utf8');
const copy=value=>JSON.parse(JSON.stringify(value));
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}

function fixture(key){
 const segments=[{start:1,end:4,text:'仅属于 '+key+' 的口播'}];
 const owner={id:'owner-'+key,name:key+'.mp4',transcript:{segments}};
 const source={id:'source-'+key,kind:'source',revision:1,name:owner.name,blob_hash:'a'.repeat(64),
  metadata:{provenance:{workbench_id:owner.id},media:{duration:10,fps:'30/1',width:1080,height:1920}}};
 const style={id:'style-'+key,kind:'style',revision:1,name:key+' 样式',metadata:{technical_status:'passed',
  poster_hash:'b'.repeat(64),field_schema:{title:{type:'text',label:'标题',max_length:10}}}};
 const project={id:'project-'+key,name:key+' 制作草稿',revision:5,source:{asset_id:source.id,revision:1},segments,
  cards:[{id:'card-'+key,text:segments[0].text,start:1,end:4,decision:'broll',status:'draft',reason:key+' 证据',
   style:{asset_id:style.id,revision:1},fields:{title:key+' 已保存'},evidence:[],alternatives:[],missing:[],
   preview_url:'/api/files/project-'+key+'/current.mp4',render_fingerprint:key+'-fingerprint',
   render_report:{layout:{status:'passed'},review_context:{message:'原片声音'}}}],runs:[],deliveries:[]};
 return {owner,source,style,project};
}

// No production internals are exported or rewritten. These tests use the same
// mount and delegated events as the page, with all HTTP and timers in memory.
async function browser(fixtures,respond=()=>undefined){
 const handlers=new Map(),nodes=new Map(),settings=new Map(),requests=[],timers=new Map(),toasts=[];
 let nextTimer=0,content='';
 const root={get innerHTML(){return content;},set innerHTML(value){content=value;nodes.clear();nodes.set('#content',root);}};
 nodes.set('#content',root);
 const node=selector=>{
  if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',value:'',disabled:false,currentTime:0,
   paused:true,duration:10,readyState:0,style:{},dataset:{},classList:{toggle(){}},
   addEventListener(){},removeEventListener(){},setAttribute(){},getAttribute(){return null;},
   querySelector(){return null;},querySelectorAll(){return [];},click(){},pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();}});
  return nodes.get(selector);
 };
 const fetcher=async(url,options={})=>{
  const request={route:url.replace(ProductionClient.prefix,''),method:options.method||'GET',
   body:options.body?JSON.parse(options.body):undefined};
  requests.push(request);
  let value=await respond(request);
  if(value===undefined){
   if(request.method!=='GET')throw Error('Unexpected write in mock: '+request.route);
   if(request.route==='/projects')value={projects:fixtures.map(f=>copy(f.project))};
   else if(request.route==='/assets')value={assets:fixtures.flatMap(f=>[copy(f.source),copy(f.style)])};
   else{
    const f=fixtures.find(f=>request.route==='/projects/'+f.project.id);
    if(f)value={project:copy(f.project)};
    else throw Error('Unexpected read in mock: '+request.route);
   }
  }
  return {ok:true,status:200,json:async()=>copy(value)};
 };
 const context=vm.createContext({console,ProductionTimeline,ProductionClient:{...ProductionClient,
  Client:class extends ProductionClient.Client{constructor(){super(fetcher);}}},
  S:{view:'ai-making',p:fixtures[0].owner,projects:fixtures.map(f=>f.owner)},$:node,$$:()=>[],
  esc:value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
  icon:()=>'',clock:value=>String(value),titleOf:p=>p.name,safeLocalUrl:value=>value,
  writeSetting:(key,value)=>settings.set(key,value),readSetting:(key,fallback)=>settings.get(key)??fallback,
  toast:message=>toasts.push(message),
  document:{addEventListener(type,callback){if(!handlers.has(type))handlers.set(type,[]);handlers.get(type).push(callback);},createElement:()=>({click(){}})},
  setTimeout(callback,delay){const id=++nextTimer;timers.set(id,{callback,delay});return id;},clearTimeout:id=>timers.delete(id),
  requestAnimationFrame:()=>0,cancelAnimationFrame(){}});
 vm.runInContext(script+'\nglobalThis.workbench=AiMaking;',context);
 const emit=(type,event)=>{for(const handler of handlers.get(type)||[])handler(event);};
 const page={context,requests,settings,toasts,timers,node,
  async click(action,extra={}){
   const target={dataset:{aiAction:action,...extra},disabled:false};target.closest=()=>target;
   emit('click',{target,preventDefault(){}});await flush();
  },
  async switchOwner(owner){context.S.p=owner;context.workbench.render();await flush();},
  check(id){emit('change',{target:{dataset:{aiCheck:id},checked:true}});},
  input(key,value){emit('input',{target:{dataset:{aiField:key,aiType:'text'},value}});},
  allVisible(){return [root.innerHTML,...[...nodes.values()].filter(n=>n!==root).map(n=>n.innerHTML+' '+n.textContent)].join('\n');}
 };
 context.workbench.render();await flush();
 assert.match(root.innerHTML,new RegExp(fixtures[0].project.name),'initial saved project should load');
 assert.equal(requests.some(request=>request.method!=='GET'),false,'mount must be read-only');
 return page;
}

test('a delayed batch from the previous video cannot replace or remember the current project',async()=>{
 const a=fixture('A'),b=fixture('B'),oldBatch=deferred();
 const page=await browser([a,b],request=>{
  if(request.route==='/projects/project-A/batch')return oldBatch.promise;
  if(request.route==='/projects/project-B/batch'){
   const saved=copy(b.project);saved.revision++;saved.cards[0].status='approved';return {project:saved};
  }
 });
 await page.click('confirm');
 assert.equal(page.requests.filter(r=>r.route==='/projects/project-A/batch').length,1);
 await page.switchOwner(b.owner);
 assert.equal(page.settings.get('ai-production-project:owner-B'),'project-B');
 const savedA=copy(a.project);savedA.revision++;savedA.cards[0].status='approved';
 oldBatch.resolve({project:savedA});await flush();
 assert.equal(page.settings.get('ai-production-project:owner-B'),'project-B');
 assert.doesNotMatch(page.node('.ai-card-list').innerHTML,/仅属于 A 的口播/);
 await page.click('confirm');
 const writes=page.requests.filter(r=>r.method==='POST');
 assert.deepEqual(writes.map(r=>r.route),['/projects/project-A/batch','/projects/project-B/batch']);
 assert.deepEqual(writes[1].body.card_ids,['card-B']);assert.equal(writes[1].body.revision,5);
});

test('a delayed GET after preview cannot downgrade a newer saved approval',async()=>{
 const a=fixture('A'),oldRead=deferred();let reads=0;
 const page=await browser([a],request=>{
  if(request.route==='/projects/project-A/preview')return {job:{id:'job-A',status:'queued'}};
  if(request.route==='/jobs/job-A')return {job:{id:'job-A',status:'complete'}};
  if(request.route==='/projects/project-A'&&++reads===1)return oldRead.promise;
  if(request.route==='/projects/project-A/batch'){
   const saved=copy(a.project);saved.revision=request.body.revision+1;
   saved.cards[0].status=request.body.action==='approve'?'approved':'draft';return {project:saved};
  }
 });
 await page.click('preview-current');
 assert.equal(reads,1,'completed preview should fetch its saved project');
 await page.click('confirm');
 oldRead.resolve({project:copy(a.project)});await flush();
 await page.click('confirm');
 const batches=page.requests.filter(r=>r.route==='/projects/project-A/batch');
 assert.equal(batches.length,2);
 assert.deepEqual(batches.map(r=>[r.body.action,r.body.revision]),[['approve',5],['reset',6]],
  'the old response must not restore draft status or revision 5');
});

test('a late preview dispatch remains owned by its original project after switching videos',async()=>{
 const a=fixture('A'),b=fixture('B'),dispatchA=deferred();
 const page=await browser([a,b],request=>{
  if(request.route==='/projects/project-A/preview')return dispatchA.promise;
  if(request.route==='/projects/project-B/preview')return {job:{id:'job-B',status:'queued'}};
  if(request.route==='/jobs/job-A')return {job:{id:'job-A',status:'failed',error:'仅属于 A 的预览失败'}};
  if(request.route==='/jobs/job-B')return {job:{id:'job-B',status:'running'}};
 });
 await page.click('preview-current');await page.switchOwner(b.owner);
 const before=page.requests.filter(r=>r.route==='/projects/project-B').length;
 dispatchA.resolve({job:{id:'job-A',status:'queued'}});await flush();
 assert.equal(page.requests.filter(r=>r.route==='/projects/project-B').length,before,
  'A completion must not refresh B as if B owned A job');
 assert.equal(page.settings.get('ai-production-project:owner-B'),'project-B');
 assert.doesNotMatch(page.allVisible(),/仅属于 A 的预览失败/);
 await page.click('preview-current');
 const starts=page.requests.filter(r=>r.method==='POST'&&r.route.endsWith('/preview'));
 assert.deepEqual(starts.map(r=>r.route),['/projects/project-A/preview','/projects/project-B/preview']);
 assert.deepEqual(starts[1].body.card_ids,['card-B']);
});

for(const action of ['preview-current','preview','confirm','approve']){
 test(`unsaved field edits block ${action} without sending writes or losing the edit`,async()=>{
  const a=fixture('A');
  const page=await browser([a],request=>{
   if(request.route==='/projects/project-A/batch'){
    const saved=copy(a.project);saved.revision++;
    if(request.body.action==='replace')saved.cards[0].fields={...saved.cards[0].fields,...request.body.fields};
    return {project:saved};
   }
   if(request.route==='/projects/project-A/preview')return {job:{id:'unexpected-preview',status:'queued'}};
   if(request.route==='/jobs/unexpected-preview')return {job:{id:'unexpected-preview',status:'complete'}};
  });
  page.check('card-A');page.input('title','尚未保存的新标题');
  await page.click(action);
  assert.equal(page.requests.filter(r=>r.method!=='GET').length,0,
   'preview and approval must refer to saved content, not silently ignore edited fields');
  assert.match(page.node('#ai-status').textContent+' '+page.toasts.join(' '),/保存|未保存/);
  await page.click('save-fields');
  const writes=page.requests.filter(r=>r.method==='POST');
  assert.equal(writes.length,1);assert.equal(writes[0].route,'/projects/project-A/batch');
  assert.equal(writes[0].body.action,'replace');assert.equal(writes[0].body.fields.title,'尚未保存的新标题');
 });
}
