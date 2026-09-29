const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const logic=require('../public/ai_making_logic.js');
const catalog=require('../public/ai_making_catalog.js');
const production=require('../public/production_client.js');

test('sentence and paragraph cuts preserve spoken order',()=>{
 assert.deepEqual(logic.splitText('先提出问题。然后比较两个方案！\n最后总结。'),['先提出问题。','然后比较两个方案！','最后总结。']);
 assert.deepEqual(logic.splitText('第一段。第二句。\n第三段。','paragraph'),['第一段。第二句。','第三段。']);
 const timed=logic.splitSegments([{text:'问题是什么？我们来比较。',start:10,end:14}]);
 assert.equal(timed.length,2);
 assert.equal(timed[0].start,10);
 assert.equal(timed[1].end,14);
 assert.equal(timed[0].end,timed[1].start);
 assert.equal(timed[0].estimated,true);
});

test('suggestions use real catalog IDs and leave unclear speech on camera',()=>{
 const ids=catalog.map(item=>item.id);
 assert.equal(logic.suggest('两款模型的得分差异',ids).presetId,'SHOT-007');
 assert.equal(logic.suggest('增长了 37%',ids).presetId,'SHOT-002');
 assert.equal(logic.suggest('根据论文报告，这项研究有证据',ids).presetId,'SHOT-005');
 assert.equal(logic.suggest('我那天真的很紧张',ids).presetId,null);
 assert.equal(logic.suggest('增长了 37%',[]).presetId,null);
});

test('each catalog entry points to an actual reusable preview',()=>{
 const media=path.resolve(__dirname,'../public/ai-presets');
 for(const item of catalog){
  assert.ok(fs.existsSync(path.join(media,item.poster)),item.poster);
  assert.ok(fs.existsSync(path.join(media,item.video)),item.video);
  assert.ok(item.fields.length>0,item.id);
 }
 const workspace=fs.readFileSync(path.resolve(__dirname,'../public/workspace.js'),'utf8');
 const index=fs.readFileSync(path.resolve(__dirname,'../public/index.html'),'utf8');
 assert.match(workspace,/\['ai-making','AI制作','scan'\]/);
 assert.match(workspace,/AiMaking\.render\(\)/);
 assert.doesNotMatch(index,/ai_making_desk(?:_logic)?\.(?:js|css)/);
 assert.match(index,/ai_making\.js/);
 assert.doesNotMatch(fs.readFileSync(path.resolve(__dirname,'../public/ai_making.js'),'utf8'),/镜间/);
});

test('video upload stays in existing AI making and sends timed source to the production Agent',async()=>{
 const handlers={};
 const elements=new Map();
 const element=selector=>{if(!elements.has(selector))elements.set(selector,{innerHTML:'',textContent:'',value:'',disabled:false});return elements.get(selector)};
 const settings=new Map();
 const project={id:'video-1',name:'我的视频.mp4',has_audio:true,transcript:{status:'idle',segments:[]}};
 const completed={...project,transcript:{status:'ready',segments:[{text:'增长了百分之三十。',start:0,end:3},{text:'我们继续比较。',start:3,end:6}]}};
 const calls=[];
 const produced={id:'production-1',name:'真实制作',revision:2,source:{asset_id:'source-1',revision:1},segments:completed.transcript.segments,cards:[{id:'c1',text:'增长了百分之三十。',start:0,end:3,decision:'keep',reason:'保留口播',status:'draft',fields:{},evidence:[],alternatives:[],missing:[]}],runs:[],deliveries:[]};
 const productionFetch=async(endpoint,options)=>{calls.push([endpoint,options]);let value;if(endpoint.endsWith('/workbench-import'))value={project:produced};else if(endpoint.endsWith('/projects/production-1/run'))value={run:{id:'r1',status:'queued'}};else if(endpoint.endsWith('/runs/r1'))value={run:{id:'r1',status:'awaiting_review',events:[]}};else if(endpoint.endsWith('/projects/production-1'))value={project:produced};else if(endpoint.endsWith('/projects'))value={projects:[]};else if(endpoint.endsWith('/assets'))value={assets:[]};else throw new Error(endpoint);return{ok:true,json:async()=>value};};
 const context=vm.createContext({
  S:{view:'ai-making',p:null,projects:[]},AiMakingLogic:logic,AiMakingCatalog:catalog,ProductionTimeline:require('../public/production_timeline.js'),ProductionClient:{...production,Client:class extends production.Client{constructor(){super(productionFetch)}}},
  $:element,$$:()=>[],esc:value=>String(value??''),icon:()=>'',clock:value=>String(value),titleOf:value=>value.name,safeLocalUrl:value=>value,
  writeSetting:(key,value)=>settings.set(key,value),readSetting:(key,fallback)=>settings.get(key)??fallback,
  toast:()=>{},upsert:()=>{},url:(id,suffix='')=>`/api/projects/${id}${suffix}`,
  api:async(url,body)=>{calls.push([url,body]);return url==='/api/projects/video-1'?completed:project},
  selectProject:async(id,options)=>{assert.equal(id,project.id);assert.equal(options.stayView,true);context.S.p=project;context.AiMaking.render()},
  XMLHttpRequest:class{constructor(){this.upload={}}open(method,url){calls.push([method,url])}setRequestHeader(){}send(){this.status=200;this.responseText=JSON.stringify(project);queueMicrotask(()=>this.onload())}},
  document:{addEventListener:(name,handler)=>handlers[name]=handler},setTimeout,
 });
 vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../public/ai_making.js'),'utf8'),context);
 context.AiMaking=vm.runInContext('AiMaking',context);
 context.AiMaking.render();
 assert.match(element('#content').innerHTML,/id="ai-video-file"[^>]*accept="video\//);
 assert.match(element('#content').innerHTML,/上传视频并生成分镜/);
 handlers.change({target:{id:'ai-video-file',dataset:{},files:[{name:'我的视频.mp4',size:100}]}});
 await new Promise(resolve=>setTimeout(resolve,30));
 assert.equal(context.S.view,'ai-making');
 assert.ok(calls.some(([endpoint])=>endpoint==='/api/projects/video-1/transcribe'),JSON.stringify({calls,status:element('#ai-status').textContent}));
 assert.equal(settings.get('ai-production-project:video-1'),'production-1');
 assert.ok(calls.some(([endpoint])=>endpoint==='/api/production/workbench-import'));
 assert.ok(calls.some(([endpoint])=>endpoint==='/api/production/projects/production-1/run'));
 assert.match(element('#content').innerHTML,/保留口播/);
 assert.equal(settings.has('ai-making:video-1'),false);
});
