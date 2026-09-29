const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const D=require('../public/replica.js');
const root=path.resolve(__dirname,'..');
const H='a'.repeat(64),R='b'.repeat(64),C='c'.repeat(64);
const project={id:'old-workbench',name:'参考视频.mp4',shots:[{id:'s1',start:0,end:2,thumbnail_url:'/media/source.jpg'},{id:'s2',start:2,end:5,thumbnail_url:'/media/other.jpg'}],research_clips:[{id:'c1',title:'已选择范围',start:0,end:2,notes:[{text:'原笔记'}]}]};
const source={id:'source',revision:1,kind:'source',metadata:{provenance:{workbench_id:project.id}}};
const study={id:'study',revision:2,kind:'study',metadata:{source:{asset_id:'source',revision:1},start:0,end:2,frames:[{blob_hash:H}]}};
const replica={id:'replica',revision:4,kind:'replica',name:'已保存复刻',metadata:{study:{asset_id:'study',revision:1},source:{asset_id:'source',revision:1},scope:{start:0,end:2},stages:{preflight:'passed',layout:'needs_review'},skill_bridge:{version:1,active_run:null},execution_trust:'untrusted_candidate'}};
const detail={replica,review_available:true,layout_review_complete:false,scenes:[{id:'layout-1',source_hash:H,render_hash:R,comparison_hash:C,review:{status:'needs_review'}}]};

test('queue uses exact saved research and shot ranges, never arbitrary groups',()=>{
 const before=JSON.stringify(project),ranges=D.ranges(project);
 assert.equal(ranges.length,2);assert.equal(ranges[0].kind,'research');assert.equal(ranges[0].note,'原笔记');
 assert.deepEqual(ranges.map(r=>[r.start,r.end]),[[0,2],[2,5]]);
 assert.equal(JSON.stringify(project),before);
 const shots=Array.from({length:35},(_,i)=>({id:String(i),start:i,end:i+1,thumbnail_url:'/media/image.jpg'}));
 assert.equal(D.ranges({shots}).length,35);
 assert.equal(D.ranges({shots:[{start:0,end:0},{start:NaN,end:5},{start:0,end:1,deleted:true}]}).length,0);
});

test('missing real layout stays empty even with source frame and historical passed claims',()=>{
 const tasks=D.buildTasks(project,[source,study,{...replica,metadata:{...replica.metadata,stages:{layout:'passed'}}}]);
 assert.equal(tasks.length,2);assert.equal(tasks[0].scenes[0].sourceStill,D.blob(H));
 assert.equal(tasks[0].scenes[0].renderStill,'');assert.equal(tasks[0].scenes[0].status,'locked');assert.equal(tasks[0].reviewAvailable,false);
 assert.throws(()=>D.reviewBody(tasks[0],tasks[0].scenes[0],'approve'),/尚未就绪/);
 assert.equal(D.buildTasks(project,[study,replica]).some(t=>t.replica),false);
});

test('server evidence replaces placeholders, approval binds source and render hashes',()=>{
 const t=D.buildTasks(project,[source,study,replica],{replica:detail})[0];
 assert.equal(t.scenes[0].renderStill,D.blob(R));assert.notEqual(t.scenes[0].renderStill,t.scenes[0].sourceStill);
 assert.equal(t.scenes[0].comparisonStill,D.blob(C));assert.equal(t.scenes[0].status,'review');
 assert.equal(D.scene({source_hash:H,render_hash:R,review:{status:'approved',source_hash:H,render_hash:R}},0).status,'approved');
 assert.equal(D.scene({source_hash:H,render_hash:R,review:{status:'approved',source_hash:H,render_hash:C}},0).status,'review');
 assert.equal(D.scene({source_hash:C,render_hash:R,review:{status:'approved',source_hash:H,render_hash:R}},0).status,'review');
 assert.equal(D.blob('../../secret'),'');assert.equal(D.blob('javascript:alert(1)'),'');
});

test('old detail cannot hide newer shared revision or authorize its review',()=>{
 const newer={...replica,revision:5};const task=D.buildTasks(project,[source,study,newer],{replica:detail})[0];
 assert.equal(task.replica.revision,5);assert.equal(task.reviewAvailable,false);assert.equal(task.scenes[0].renderStill,'');
});

test('review POST persists exact version and evidence; empty change request is rejected',async()=>{
 const calls=[],client=new D.Client(async(path,body)=>(calls.push({path,body}),detail));
 const t=D.buildTasks(project,[source,study,replica],{replica:detail})[0];
 await client.review(t,t.scenes[0],'approve',' 已查看 ');
 assert.deepEqual(calls,[{path:'/replicas/replica/review',body:{expected_revision:4,scene_id:'layout-1',render_hash:R,action:'approve',note:'已查看'}}]);
 assert.throws(()=>D.reviewBody(t,t.scenes[0],'changes',' '),/先写明/);
});

test('create imports only reference source then actual study and replica, preserving selected scope',async()=>{
 const calls=[],client=new D.Client(async(route,body)=>{calls.push({route,body});if(route==='/workbench-source')return{source};if(route==='/studies')return{study};if(route==='/replicas')return{replica};throw Error(route);});
 const range=D.buildTasks(project,[])[0];const result=await client.create(range,project);assert.equal(result.replica.id,'replica');
 assert.deepEqual(calls.map(c=>c.route),['/workbench-source','/studies','/replicas']);
 assert.deepEqual(calls[1].body,{source_id:'source',start:0,end:2,note:'原笔记'});
 calls.length=0;await client.create({...range,source,study},project);assert.deepEqual(calls,[{route:'/replicas',body:{study_id:'study'}}]);
});

test('controlled stage execution calls real job API and never changes local approval',async()=>{
 const calls=[],client=new D.Client(async(route,body)=>(calls.push({route,body}),{job:{id:'job',status:'queued'}}));
 const task=D.buildTasks(project,[source,study,replica])[0];
 await client.advance(task,'preflight');await client.advance(task,'layout');
 assert.deepEqual(calls.map(c=>c.body.stage),['preflight','layout']);assert.ok(calls.every(c=>c.route==='/replicas/replica/advance'));
 assert.equal(task.scenes[0].status,'locked');
});

test('job completion copy distinguishes preflight, real static frames, and saved Skill failures',()=>{
 const preflightReplica={...replica,metadata:{...replica.metadata,stages:{preflight:'passed',layout:'pending'},skill_bridge:{version:1,active_run:null,events:[{stage:'preflight',status:'needs_review'}]}}};
 const preflight=D.buildTasks(project,[source,study,preflightReplica],{replica:{replica:preflightReplica,scenes:[]}})[0];
 const failedReplica={...replica,metadata:{...replica.metadata,skill_bridge:{version:1,active_run:null,events:[{stage:'layout',status:'failed',error:'模型超时'}]}}};
 const failed=D.buildTasks(project,[source,study,failedReplica],{replica:{replica:failedReplica,scenes:[]}})[0];
 const rendered=D.buildTasks(project,[source,study,replica],{replica:detail})[0];
 assert.match(D.jobOutcome({status:'complete'},preflight).message,/尚未生成任何定格帧/);
 const failure=D.jobOutcome({status:'complete'},failed);assert.equal(failure.status,'failed');assert.equal(failure.error,'模型超时');assert.match(failure.message,/尚未生成可审查的静态帧/);
 assert.equal(D.jobOutcome({status:'complete'},rendered).status,'generated');assert.match(D.jobOutcome({status:'complete'},rendered).message,/已生成 1 张/);
});

test('existing three-column UI uses real state and preserves navigation and six modes',()=>{
 const workspace=fs.readFileSync(path.join(root,'public/workspace.js'),'utf8'),replicaJS=fs.readFileSync(path.join(root,'public/replica.js'),'utf8');
 assert.match(workspace,/\['replica','AI复刻','layers'\]/);assert.match(workspace,/ReplicaWorkbench\.render/);
 for(const key of ['replica-reference-layout','replica-batch','replica-viewer','replica-inspector','replica-task-stills'])assert.ok(replicaJS.includes(key));
 for(const mode of ['current','source','side','overlay','wipe','diff'])assert.ok(replicaJS.includes(`viewButton('${mode}'`));
 assert.doesNotMatch(replicaJS,/localStorage|groupPrototypeShots|复刻占位图|模拟重新生成|演示通过/);
 assert.match(replicaJS,/真实复刻静帧/);assert.match(replicaJS,/尚未生成，不可批准/);
});

test('browser mounts saved replica without source-as-render, and review waits for the server',async()=>{
 const html={innerHTML:''},handlers={},calls=[];
 const context={console,setTimeout:()=>0,clearTimeout:()=>{},S:{view:'replica'},document:{addEventListener:(type,callback)=>{handlers[type]=callback;}},
  $:selector=>selector==='#content'?html:selector==='#replica-note'?{value:'真实意见'}:null,
  esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),safeLocalUrl:v=>v,icon:()=>'',clock:v=>String(v),titleOf:p=>p.name,toast:()=>{},
  api:async(route,body)=>{calls.push({route,body});if(route.endsWith('/assets'))return{assets:[source,study,replica]};if(route.endsWith('/cases'))return{cases:[]};if(route.endsWith('/replicas/replica'))return detail;if(route.endsWith('/review'))return{...detail,replica:{...replica,revision:5},scenes:[{...detail.scenes[0],review:{status:'approved',source_hash:H,render_hash:R}}]};throw Error(route);}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'public/replica.js'),'utf8')+'\nthis.workbench=ReplicaWorkbench;',context);
 context.workbench.render([project],project);await new Promise(resolve=>setImmediate(resolve));
 assert.match(html.innerHTML,/真实复刻静帧/);assert.ok(html.innerHTML.includes(D.blob(R)));assert.doesNotMatch(html.innerHTML,/演示通过/);
 handlers.click({target:{closest:()=>({disabled:false,dataset:{replicaAction:'approve'}})}});await new Promise(resolve=>setImmediate(resolve));
 const submitted=calls.find(c=>c.route.endsWith('/review'));assert.equal(submitted.body.expected_revision,4);assert.equal(submitted.body.render_hash,R);assert.match(html.innerHTML,/已审通过/);
});
