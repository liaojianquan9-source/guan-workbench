const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const L=require('../public/logic.js');

test('timed transcript validation preserves real timing and rejects overlap, invalid JSON and missing words',()=>{
  assert.deepEqual(L.parseTranscript('[{"start":1.1,"end":3,"text":" 有依据的数字。 "}]'),{segments:[{start:1.1,end:3,text:'有依据的数字。'}]});
  assert.deepEqual(L.parseTranscript('{"segments":[{"start":0,"end":1,"text":"第一句"}]}'),{segments:[{start:0,end:1,text:'第一句'}]});
  assert.throws(()=>L.parseTranscript('[{"start":1,"end":1,"text":"无时长"}]'),/第 1 段/);
  assert.throws(()=>L.parseTranscript('[{"start":0,"end":2,"text":"一"},{"start":1,"end":3,"text":"二"}]'),/重叠/);
  assert.throws(()=>L.parseTranscript('[{"start":0,"end":2,"text":""}]'),/第 1 段/);
  assert.throws(()=>L.parseTranscript('{"segments":'),/JSON/);
  assert.throws(()=>L.parseTranscript(''),/请填写/);
});

test('text-only projects never invent timecodes; uploaded source can be transcribed after creation',()=>{
  assert.deepEqual(L.projectPayload(' 新一期 ',null,'真实文稿。'),{name:'新一期',transcript:'真实文稿。'});
  assert.deepEqual(L.projectPayload('新视频','source-7',''),{name:'新视频',source_id:'source-7'});
  assert.throws(()=>L.projectPayload('','source-7','稿'),/名称/);
  assert.throws(()=>L.projectPayload('无资料',null,''),/请填写/);
});

test('batch review always sends current revision and only IDs belonging to this project',()=>{
  const project={id:'p',revision:9,cards:[{id:'c1',status:'draft',decision:'broll'},{id:'c2',status:'approved',decision:'keep'}]};
  assert.deepEqual(L.batchPayload(project,new Set(['c2','foreign']),'reject'),{revision:9,card_ids:['c2'],action:'reject'});
  assert.deepEqual(L.batchPayload(project,['c1','c1'],'replace',{style_id:'style-v2',fields:{title:'新标题'}}),{revision:9,card_ids:['c1'],action:'replace',style_id:'style-v2',fields:{title:'新标题'}});
  assert.deepEqual(L.visibleCards(project,'keep').map(c=>c.id),['c2']);
  assert.deepEqual(L.visibleCards(project,'draft').map(c=>c.id),['c1']);
  assert.throws(()=>L.batchPayload(project,['foreign'],'approve'),/请先选择/);
  assert.throws(()=>L.batchPayload({...project,revision:null},['c1'],'approve'),/项目版本/);
  assert.throws(()=>L.batchPayload(project,['c1'],'delete'),/不支持/);
});

test('image replacement pins asset revision and text constraints reject oversized edits',()=>{
  assert.deepEqual(L.parseFieldValue({key:'image',type:'image'},'{"asset_id":"img-2","revision":3}'),{asset_id:'img-2',revision:3});
  assert.throws(()=>L.parseFieldValue({label:'背景',type:'image'},'{"asset_id":"img-2"}'),/版本无效/);
  assert.equal(L.parseFieldValue({key:'image',type:'image'},''),undefined);
  assert.throws(()=>L.parseFieldValue({label:'主标题',type:'text',max_length:3},'四个汉字'),/最多 3/);
  assert.throws(()=>L.parseFieldValue({label:'得分',type:'number'},'未知'),/有效数字/);
  assert.equal(L.parseFieldValue({type:'number'},'0'),0);
  assert.throws(()=>L.parseFieldValue({type:'integer'},'1.2'),/有效数字/);
});

test('style schemas from registry map fields without losing constraints or inventing options',()=>{
  const style={metadata:{field_schema:{title:{type:'text',label:'主标题',max_length:10},image:{type:'image'}}}};
  assert.equal(L.fieldsOf(style)[0].max_length,10);
  assert.deepEqual(L.fieldsOf(style).map(f=>f.key),['title','image']);
  assert.deepEqual(L.fieldsOf(null),[]);
  assert.deepEqual(L.fieldsOf({metadata:{field_schema:{properties:{score:{type:'number'}}}}}),[{key:'score',type:'number'}]);
});

test('asset and model text cannot introduce HTML, foreign media URLs or javascript',()=>{
  assert.equal(L.escape('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  for(const unsafe of ['javascript:alert(1)','data:text/html,x','https://foreign.test/a.mp4','//evil/a','/\\evil/a','/x%0aonload','/x%2f..'])assert.equal(L.localUrl(unsafe),'',unsafe);
  assert.equal(L.localUrl('/api/files/project/video.mp4'),'/api/files/project/video.mp4');
  assert.equal(L.mediaUrl({blob_hash:'a'.repeat(64)}),'/api/media/'+'a'.repeat(64));
  assert.equal(L.mediaUrl({blob_hash:'../file'}),'');
});

test('client surfaces server failure without returning a false successful project',async()=>{
  const requests=[];
  const client=new L.Client(async(path,options)=>{requests.push({path,options});return {ok:false,status:409,json:async()=>({error:'版本冲突，修改已保留'})};});
  await assert.rejects(client.request('/api/projects/p/batch',{revision:1,card_ids:['c'],action:'approve'}),error=>error.status===409&&/版本冲突/.test(error.message));
  assert.equal(requests[0].options.headers['Content-Type'],'application/json');
  assert.equal(JSON.parse(requests[0].options.body).revision,1);
  const broken=new L.Client(async()=>{throw new Error('offline')});
  await assert.rejects(broken.request('/api/status'),/本机服务连接中断/);
});

test('batch import is sequential, retains good files after one failure and reports each result',async()=>{
  const order=[],snapshots=[];let active=0;
  const rows=await L.importFiles({upload:async(file,kind)=>{assert.equal(active++,0);assert.equal(kind,'image');order.push(file.name);await Promise.resolve();active--;if(file.name==='bad.jpg')throw new Error('不能解码');return{id:file.name,revision:1};}},[{name:'one.png'},{name:'bad.jpg'},{name:'three.png'}],'image',rows=>snapshots.push(rows.map(r=>r.status)));
  assert.deepEqual(order,['one.png','bad.jpg','three.png']);
  assert.deepEqual(rows.map(row=>row.status),['complete','error','complete']);
  assert.equal(rows[1].error,'不能解码');assert.equal(rows[2].asset.id,'three.png');
  assert.deepEqual(snapshots[0],['queued','queued','queued']);
  assert.ok(snapshots.some(s=>s[1]==='running'));
});

test('upload uses raw bytes and encoded names rather than client-side filesystem paths',async()=>{
  let request;
  const file={name:'图片 & 背景.png',type:'image/png'};
  const client=new L.Client(async(path,options)=>{request={path,options};return{ok:true,json:async()=>({asset:{id:'a',revision:1}})}});
  assert.deepEqual(await client.upload(file,'image'),{id:'a',revision:1});
  assert.match(request.path,/name=%E5%9B%BE/);assert.ok(!request.path.includes('& 背景'));
  assert.equal(request.options.body,file);assert.equal(request.options.method,'POST');
});

async function makeUI({project,assets=[],response}={}){
  const handlers={},windowHandlers={},nodes=new Map(),requests=[];
  const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',hidden:false,open:false,value:'',addEventListener(){},close(){this.open=false},showModal(){this.open=true},querySelector(){return null},querySelectorAll(){return[]},focus(){},getBoundingClientRect(){return{left:0,right:500,top:0,bottom:500}}});return nodes.get(selector)};
  const context={BrollLogic:L,console,URL,Set,Map,Date,JSON,FormData:class{},encodeURIComponent,decodeURIComponent,
    setTimeout:()=>1,clearTimeout:()=>{},location:{hash:project?'#projects/'+project.id:'#projects'},
    document:{querySelector:node,querySelectorAll:()=>[],addEventListener:(event,handler)=>handlers[event]=handler},
    window:{addEventListener:(event,handler)=>windowHandlers[event]=handler},
    fetch:async(path,options)=>{requests.push({path,options});let value;
      if(response){value=await response(path,options,project);}
      if(value===undefined){if(path==='/api/status')value={model:{available:false},assets:{available:true}};else if(path==='/api/assets')value={assets};else if(path==='/api/projects')value={projects:project?[project]:[]};else if(path==='/api/projects/'+project?.id)value={project};else throw new Error('Unexpected '+path);}
      return{ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(value))};
    }};
  // Client defaults to the actual global's fetch; use this harness-specific boundary.
  context.BrollLogic={...L,Client:class extends L.Client{constructor(){super(context.fetch)}}};
  vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../public/app.js'),'utf8'),vm.createContext(context));
  const settle=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));};await settle();
  const click=async(action,data={})=>{const target={dataset:{action,...data},disabled:false,isConnected:true};target.closest=()=>target;handlers.click({target,preventDefault(){}});await settle();};
  return{handlers,nodes,node,requests,click,settle,context,windowHandlers};
}

const fixture=()=>({id:'p1',name:'真实测试项目',revision:3,source:null,segments:[{id:'s1',start:0,end:2,text:'一项事实'}],cards:[{id:'c1',segment_ids:['s1'],start:0,end:2,text:'一项事实',decision:'broll',reason:'数字有现成证据',evidence:[{summary:'源字幕数字'}],alternatives:[{reason:'比较另一种样式'}],style:{asset_id:'style-1',revision:1},fields:{title:'42'},missing:[],status:'draft'},{id:'c2',segment_ids:['s1'],start:0,end:2,text:'我很紧张',decision:'keep',reason:'需要看见人物表情',evidence:[],alternatives:[],style:null,fields:{},missing:[],status:'draft'}],runs:[],deliveries:[]});

test('actual UI renders server cards and evidence, then selected-only rejection calls the versioned endpoint',async()=>{
  const project=fixture();project.name='<img src=x onerror=alert(1)>';
  const ui=await makeUI({project,response:(path,options,p)=>{if(path==='/api/projects/p1/batch'){const body=JSON.parse(options.body);assert.deepEqual(body,{revision:3,card_ids:['c2'],action:'reject'});p.revision++;p.cards[1].status='rejected';return{project:p};}}});
  const markup=ui.node('#page').innerHTML;
  assert.match(markup,/&lt;img src=x onerror=alert\(1\)&gt;/);assert.doesNotMatch(markup,/<img src=x/);
  assert.match(markup,/数字有现成证据/);assert.match(markup,/比较另一种样式/);assert.match(markup,/保留口播画面/);
  ui.handlers.change({target:{dataset:{selectCard:'c2'},checked:true}});await ui.click('reject');
  assert.ok(ui.requests.some(r=>r.path==='/api/projects/p1/batch'));assert.match(ui.node('#page').innerHTML,/已舍弃/);
});

test('actual UI blocks preview for keep-only selection instead of rendering unrelated cards',async()=>{
  const ui=await makeUI({project:fixture()});
  ui.handlers.change({target:{dataset:{selectCard:'c2'},checked:true}});await ui.click('preview');
  assert.equal(ui.requests.some(r=>r.path.endsWith('/preview')),false);
  assert.match(ui.node('#toast').textContent,/保留口播不需要额外渲染/);
});

test('actual UI reloads approved output and renders completed job delivery URL, not a template preview',async()=>{
  const project=fixture();project.source={asset_id:'source-1',revision:1};
  const ui=await makeUI({project,response:path=>{
    if(path==='/api/projects/p1/render')return{job:{id:'job-1',status:'queued'}};
    if(path==='/api/jobs/job-1')return{job:{id:'job-1',status:'complete',result:{delivery:{url:'/api/files/p1/final-v3.mp4',report:{status:'passed'}}}}};
  }});
  await ui.click('render');
  assert.match(ui.node('#page').innerHTML,/src="\/api\/files\/p1\/final-v3\.mp4"/);
  assert.match(ui.node('#page').innerHTML,/下载视频/);
});

test('actual UI handles a failed Agent run as failure with resumable actions and preserved cards',async()=>{
  const ui=await makeUI({project:fixture(),response:path=>{
    if(path==='/api/projects/p1/run')return{run:{id:'run-1',status:'queued'}};
    if(path==='/api/runs/run-1')return{run:{id:'run-1',status:'failed',error:'模型连接失败',events:[{sequence:1,type:'tool',message:'已读取字幕',data:{segments:1}}]}};
  }});
  await ui.click('run');
  assert.match(ui.node('#page').innerHTML,/模型连接失败/);assert.match(ui.node('#page').innerHTML,/从已保存进度继续/);
  assert.match(ui.node('#page').innerHTML,/数字有现成证据/);assert.match(ui.node('#page').innerHTML,/已读取字幕/);
});

test('empty application starts without fabricated demo projects or suggestions',async()=>{
  const ui=await makeUI();assert.match(ui.node('#page').innerHTML,/开始第一条制作项目/);
  assert.equal((ui.node('#page').innerHTML.match(/class="project-tile"/g)||[]).length,0);
  assert.equal(ui.requests.filter(r=>r.options?.method==='POST').length,0);
});

test('replica actions persist a study link and advance only from actual completed job evidence',async()=>{
  const study={id:'study-1',revision:1,kind:'study',name:'真实片段研究',metadata:{start:1,end:3}},replica={id:'replica-1',revision:1,kind:'replica',name:'片段复刻',metadata:{status:'needs_work',stages:{preflight:'pending',layout:'pending'}}};
  const ui=await makeUI({assets:[study,replica],response:(path,options)=>{
    if(path==='/api/replicas'){assert.deepEqual(JSON.parse(options.body),{study_id:'study-1'});return{replica};}
    if(path==='/api/replicas/replica-1/advance'){assert.deepEqual(JSON.parse(options.body),{stage:'auto'});return{job:{id:'job-r1',status:'queued'}};}
    if(path==='/api/jobs/job-r1'){replica.revision=2;replica.metadata.stages.preflight='passed';return{job:{id:'job-r1',status:'complete',result:{replica}}};}
  }});
  await ui.click('create-replica',{id:'study-1'});
  assert.match(ui.node('#dialog-content').innerHTML,/范围预检/);
  assert.match(ui.node('#dialog-content').innerHTML,/待处理/);
  await ui.click('advance-replica',{id:'replica-1'});
  assert.ok(ui.requests.some(r=>r.path==='/api/jobs/job-r1'));
  assert.match(ui.node('#dialog-content').innerHTML,/通过/);
  assert.match(ui.node('#dialog-content').innerHTML,/不可变版本 v2/);
});

test('source-only creation can call local transcription without generating artificial cards',async()=>{
  const project={...fixture(),source:{asset_id:'source-1',revision:1},segments:[],cards:[]};
  const ui=await makeUI({project,response:path=>{
    if(path==='/api/projects/p1/transcribe')return{job:{id:'asr1',status:'queued'}};
    if(path==='/api/jobs/asr1'){project.segments=[{id:'s1',start:1,end:2,text:'真实转录'}];return{job:{id:'asr1',status:'complete',result:{project}}};}
  }});
  await ui.click('transcribe');
  assert.ok(ui.requests.some(r=>r.path==='/api/projects/p1/transcribe'));
  assert.match(ui.node('#page').innerHTML,/真实转录/);
  assert.equal((ui.node('#page').innerHTML.match(/class="review-card /g)||[]).length,0);
});

test('product title and both navigation brands use exactly 观 without retired aliases',()=>{
  for(const filename of ['index.html','app.js','logic.js','style.css']){
    const contents=fs.readFileSync(path.resolve(__dirname,'../public',filename),'utf8');
    assert.doesNotMatch(contents,/镜间|B-roll\s*工作台|AI\s*工作台/,filename);
  }
  const html=fs.readFileSync(path.resolve(__dirname,'../public/index.html'),'utf8');
  assert.match(html,/<title>观<\/title>/);
  const app=fs.readFileSync(path.resolve(__dirname,'../public/app.js'),'utf8');
  assert.match(app,/<span>观<small>/);
  assert.match(app,/<div class="mobile-brand">观 <span>/);
  assert.match(app,/打开原拉片工作台/);
});

test('another project is created through duplicate endpoint while existing source and fixed asset refs stay untouched',async()=>{
  const project=fixture();project.source={asset_id:'source-1',revision:2};
  const original=JSON.stringify(project);
  const ui=await makeUI({project,response:(path,options)=>{
    if(path==='/api/projects/p1/duplicate'){assert.deepEqual(JSON.parse(options.body),{});return{project:{...project,id:'p2',name:'另一期'}};}
  }});
  assert.match(ui.node('#page').innerHTML,/另建副本/);
  await ui.click('duplicate-project');
  assert.equal(ui.context.location.hash,'#projects/p2');
  assert.equal(JSON.stringify(project),original);
});

test('navigation separates production, reference research and shared assets without mutating saved projects',async()=>{
  const project=fixture(),original=JSON.stringify(project),ui=await makeUI({project});
  assert.match(ui.node('#app').innerHTML,/href="#projects"[^>]*>.*?制作项目/);
  assert.match(ui.node('#app').innerHTML,/href="#research"/);
  assert.match(ui.node('#app').innerHTML,/href="#library"/);
  assert.match(ui.node('#app').innerHTML,/href="http:\/\/127\.0\.0\.1:4182" target="_blank" rel="noopener noreferrer"[^>]*>打开原拉片工作台/);
  ui.context.location.hash='#research';ui.windowHandlers.hashchange();await ui.settle();
  assert.match(ui.node('#page').innerHTML,/先选一段真实参考视频/);
  ui.context.location.hash='#library';ui.windowHandlers.hashchange();await ui.settle();
  assert.match(ui.node('#page').innerHTML,/还没有可用样式/);
  ui.context.location.hash='#projects/p1';ui.windowHandlers.hashchange();await ui.settle();
  assert.match(ui.node('#page').innerHTML,/真实测试项目/);
  assert.equal(JSON.stringify(project),original);
  assert.equal(ui.requests.filter(r=>r.options?.method==='POST').length,0);
});

test('workbench import displays actual numeric transcript count and explicitly creates the new-domain project',async()=>{
  const ui=await makeUI({response:(path,options)=>{
    if(path==='/api/workbench-projects')return{projects:[{id:'existing-workbench-id',name:'原工作台口播',duration:53.03,segments:25,has_transcript:true}]};
    if(path==='/api/workbench-import'){assert.deepEqual(JSON.parse(options.body),{project_id:'existing-workbench-id'});return{project:{...fixture(),id:'new-domain-id'}};}
  }});
  await ui.click('workbench');
  assert.match(ui.node('#dialog-content').innerHTML,/原工作台口播/);
  assert.match(ui.node('#dialog-content').innerHTML,/25 段字幕/);
  assert.match(ui.node('#dialog-content').innerHTML,/原拉片记录保留/);
  assert.equal(ui.requests.some(r=>r.path==='/api/workbench-import'),false);
  await ui.click('import-workbench',{id:'existing-workbench-id'});
  assert.equal(ui.context.location.hash,'#projects/new-domain-id');
});
