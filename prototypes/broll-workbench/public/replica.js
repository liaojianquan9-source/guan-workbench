'use strict';
// Data contracts are exported for the same tests used by the browser. Source
// thumbnails are evidence only; a rendered still always needs its own blob.
const ReplicaData=(()=>{
 const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value)?value:'';
 const blob=value=>hash(value)?`/api/production/media/${value}`:'';
 const pending=asset=>!!asset?.metadata?.skill_bridge?.active_run;
 const rangeKey=(start,end)=>`${Number(start).toFixed(6)}:${Number(end).toFixed(6)}`;
 function sourceFor(project,assets){return project?.sharedSourceId?assets.find(a=>a.id===project.sharedSourceId):assets.find(a=>a.kind==='source'&&a.metadata?.provenance?.workbench_id===project?.id);}
 function ranges(project){
  const result=[],seen=new Set();
  for(const [kind,items] of [['research',project?.research_clips||[]],['shot',project?.shots||[]]])for(const item of items){
   const start=Number(item.start),end=Number(item.end),key=rangeKey(start,end);
   if(item.deleted||!Number.isFinite(start+end)||start<0||end<=start||seen.has(key))continue;
   seen.add(key);const shot=(project.shots||[]).find(s=>Number(s.start)<=start&&Number(s.end)>start);
   result.push({id:`${kind}:${item.id}`,rangeId:item.id,kind,start,end,title:item.title||(kind==='research'?'已存研究片段':'原片分镜'),thumbnail_url:item.thumbnail_url||item.frames?.find(f=>!f.deleted)?.url||shot?.thumbnail_url||'',note:(item.notes||[]).filter(n=>!n.deleted).map(n=>n.text).filter(Boolean).join('\n')});
  }
  return result;
 }
 function scene(raw,index){
  const renderHash=hash(raw.render_hash),review=raw.review||{};
  const status=renderHash&&review.source_hash===hash(raw.source_hash)&&review.render_hash===renderHash&&['approved','changes'].includes(review.status)?review.status:renderHash?'review':'locked';
  return{id:String(raw.id||`frame-${index+1}`),index,label:raw.label||`静态帧 ${String(index+1).padStart(2,'0')}`,sourceStill:blob(raw.source_hash),renderStill:blob(renderHash),comparisonStill:blob(raw.comparison_hash),preview:blob(raw.preview_hash),renderHash,status,note:review.note||'',sourceTime:raw.source_time};
 }
 function buildTasks(project,assets,details={}){
  const source=sourceFor(project,assets),sourceId=source?.id,lookup=new Map(assets.map(a=>[a.id,a]));
  const studies=assets.filter(a=>sourceId&&a.kind==='study'&&a.metadata?.source?.asset_id===sourceId);
  const replicas=assets.filter(a=>sourceId&&a.kind==='replica'&&a.metadata?.source?.asset_id===sourceId);
  const tasks=replicas.map(replica=>{
   const m=replica.metadata||{},study=lookup.get(m.study?.asset_id),cached=details[replica.id],d=cached?.replica?.revision===replica.revision?cached:null,selected=d?.replica||replica;
   const scope=m.scope||study?.metadata||{},frames=study?.metadata?.frames||[];
   const scenes=(d?.scenes||[]).map(scene);
   // Older servers expose imported adapter posters as genuine render evidence,
   // but cannot accept review until the version-aware review route is present.
   if(!d)for(const ref of m.styles||[]){const style=lookup.get(ref.asset_id);if(style?.revision===ref.revision&&hash(style.metadata?.poster_hash))scenes.push(scene({id:style.id,label:style.name,render_hash:style.metadata.poster_hash,preview_hash:style.metadata.preview_hash},scenes.length));}
   if(!scenes.length)scenes.push({id:'pending-layout',index:0,label:'静态布局待生成',sourceStill:blob(frames[0]?.blob_hash),renderStill:'',comparisonStill:'',preview:'',renderHash:'',status:'locked',note:''});
   const active=pending(selected);if(active)for(const item of scenes)if(item.status!=='approved')item.status='generating';
   return{id:replica.id,replica:selected,study,source,kind:'replica',start:Number(scope.start)||0,end:Number(scope.end)||Number(source?.metadata?.media?.duration)||Number(source?.metadata?.scope?.durationSeconds)||0,title:replica.name,thumbnail_url:scenes.find(s=>s.sourceStill)?.sourceStill||blob(frames[0]?.blob_hash),scenes,reviewAvailable:d?.review_available===true,layoutReviewComplete:d?.layout_review_complete===true,detailLoaded:!!d,active};
  });
  for(const study of studies.filter(s=>!replicas.some(r=>r.metadata?.study?.asset_id===s.id))){const m=study.metadata;tasks.push({id:study.id,study,source,kind:'study',start:m.start,end:m.end,title:study.name,thumbnail_url:blob(m.frames?.[0]?.blob_hash),scenes:[{...scene({},0),id:'pending-layout',sourceStill:blob(m.frames?.[0]?.blob_hash),label:'静态布局待生成'}]});}
  const saved=new Set(tasks.map(t=>rangeKey(t.start,t.end)));
  for(const range of ranges(project))if(!saved.has(rangeKey(range.start,range.end)))tasks.push({...range,source,scenes:[{...scene({},0),id:'pending-layout',sourceStill:range.thumbnail_url,label:'静态布局待生成'}]});
  return tasks.map((task,index)=>({...task,index}));
 }
 const counts=tasks=>tasks.flatMap(task=>task.scenes).reduce((out,item)=>(out[item.status]=(out[item.status]||0)+1,out),{approved:0,review:0,changes:0,generating:0,locked:0});
 const taskStatus=task=>task.active?'generating':task.scenes.every(s=>s.status==='approved')?'approved':task.scenes.some(s=>s.status==='changes')?'changes':task.scenes.some(s=>s.renderStill)?'review':'locked';
 function jobOutcome(job,task){
  const metadata=task?.replica?.metadata||{},event=metadata.skill_bridge?.events?.at(-1),rendered=task?.scenes?.filter(scene=>scene.renderStill).length||0;
  const error=typeof job?.error==='string'?job.error:event?.error||'';
  if(job?.status==='failed'||event?.status==='failed')return{status:'failed',error,message:'本轮复刻执行失败，尚未生成可审查的静态帧；已保存失败记录，可修复后重试。'};
  if(job?.status==='interrupted'||event?.status==='interrupted')return{status:'interrupted',error,message:'本轮复刻已中断，尚未生成可审查的静态帧；可查看记录后继续。'};
  if(event?.stage==='preflight')return{status:'preflight',error:'',message:'参考范围检查已完成，尚未生成任何定格帧。下一步请生成静态布局。'};
  if(rendered)return{status:'generated',error:'',message:`已生成 ${rendered} 张真实复刻静态帧，请逐张审看。`};
  return{status:'empty',error,message:'本轮没有生成可审查的静态帧；请查看本轮记录后重试。'};
 }
 function reviewBody(task,item,action,note=''){
  if(!task.reviewAvailable||!item.sourceStill||!item.renderHash||!Number.isInteger(task.replica?.revision))throw new Error('真实静态帧和可保存的审查版本尚未就绪。');
  if(!['approve','changes'].includes(action))throw new Error('审查操作无效。');
  if(action==='changes'&&!note.trim())throw new Error('请先写明这一张静态帧需要修改的内容。');
  return{expected_revision:task.replica.revision,scene_id:item.id,render_hash:item.renderHash,action,note:note.trim()};
 }
 class Client{
  constructor(request){this.request=request;}
  async library(){const [a,c]=await Promise.all([this.request('/assets'),this.request('/cases')]);return{assets:a.assets||[],cases:c.cases||[]};}
  source(project){return this.request('/workbench-source',{project_id:project.id});}
  details(id){return this.request(`/replicas/${encodeURIComponent(id)}`);}
  async create(task,project){
   const source=task.source||(await this.source(project)).source;
   if(!source?.id)throw new Error('参考视频尚未保存到共享资产库。');
   const study=task.study||(await this.request('/studies',{source_id:source.id,start:task.start,end:task.end,note:task.note||task.title||''})).study;
   if(!study?.id)throw new Error('研究片段尚未保存。');
   return this.request('/replicas',{study_id:study.id});
  }
  advance(task,stage){if(!task.replica?.id)throw new Error('请先建立复刻项目。');return this.request(`/replicas/${encodeURIComponent(task.replica.id)}/advance`,{stage});}
  review(task,item,action,note){return this.request(`/replicas/${encodeURIComponent(task.replica.id)}/review`,reviewBody(task,item,action,note));}
 }
 return{hash,blob,pending,rangeKey,sourceFor,ranges,scene,buildTasks,counts,taskStatus,jobOutcome,reviewBody,Client};
})();
if(typeof module==='object'&&module.exports)module.exports=ReplicaData;

const ReplicaWorkbench=(()=>{
 const D=ReplicaData,client=new D.Client((path,body)=>api('/api/production'+path,body));
 const statusCopy={approved:'已审通过',review:'待审查',changes:'需修改',generating:'执行中',locked:'待生成'};
 const state={projectId:null,taskIndex:0,sceneIndex:0,mode:'current',opacity:52,wipe:50,projects:[],localProjects:[],tasks:[],assets:[],details:{},cases:[],notes:{},error:'',message:'',busy:false,loading:false,token:0,job:null};
 let timer=null;
 const currentProject=()=>state.projects.find(project=>project.id===state.projectId)||state.projects[0];
 const currentTask=()=>state.tasks[state.taskIndex];
 const jobRunning=()=>['queued','running','processing'].includes(state.job?.status);
 const cleanTitle=project=>titleOf(project).replace(/\.[^.]+$/,'');
 const taskLabel=task=>task.kind==='research'?'研究片段':task.kind==='shot'?'原片分镜':`复刻 ${String(task.index+1).padStart(2,'0')}`;
 const sceneLabel=scene=>scene.label;
 const taskRange=task=>`${clock(task.start)} — ${clock(task.end)}`;
 const sceneKey=(task,scene)=>`${task.id}:${scene.id}:${scene.renderHash}`;
 const sceneStatus=(task,scene)=>scene.status;
 const taskStatus=task=>D.taskStatus(task);
 const statusPill=value=>`<span class="replica-status ${value}"><i></i>${statusCopy[value]||esc(value)}</span>`;
 function media(source,alt='',classes=''){
  const address=safeLocalUrl(source||'');
  return address?`<img class="replica-media ${classes}" src="${esc(address)}" alt="${esc(alt)}" loading="lazy">`:`<span class="replica-missing">${icon('film')}<small>静态帧待生成</small></span>`;
 }
 function syncTasks(keepId){
  const oldId=keepId||currentTask()?.id;state.tasks=D.buildTasks(currentProject(),state.assets,state.details);
  const index=state.tasks.findIndex(t=>t.id===oldId);state.taskIndex=index>=0?index:Math.min(state.taskIndex,Math.max(0,state.tasks.length-1));
  state.sceneIndex=Math.min(state.sceneIndex,Math.max(0,(currentTask()?.scenes.length||0)-1));
 }
 function syncProjects(){
  const imported=state.assets.filter(a=>a.kind==='source'&&!state.localProjects.some(p=>a.metadata?.provenance?.workbench_id===p.id)).map(a=>({id:`asset:${a.id}`,sharedSourceId:a.id,name:a.name,shots:[],research_clips:[]}));
  state.projects=[...state.localProjects,...imported];if(!currentProject()&&state.projects[0])state.projectId=state.projects[0].id;
 }
 function viewButton(mode,label,glyph){return `<button class="replica-view-button ${state.mode===mode?'active':''}" data-replica-mode="${mode}" aria-label="${label}" title="${label}" aria-pressed="${state.mode===mode}">${icon(glyph)}<span>${label}</span></button>`;}
 function toolbar(project){const counts=D.counts(state.tasks);return `<header class="replica-workspace-toolbar"><select id="replica-project" aria-label="选择参考视频" ${state.busy?'disabled':''}>${state.projects.map(item=>`<option value="${esc(item.id)}" ${item.id===project?.id?'selected':''}>${esc(cleanTitle(item))}</option>`).join('')}</select><span>/</span><strong>静态布局审查</strong><small>${counts.review+counts.changes} 帧待审 · ${counts.approved} 帧已审</small><span class="spacer"></span><button class="button" data-replica-action="refresh" ${state.busy?'disabled':''}>${icon('refresh')}刷新</button><span class="replica-prototype">${state.loading?'正在读取共享资产':'复刻进度已连接共享库'}</span></header>`;}
 function sceneTile(task,scene){const value=sceneStatus(task,scene),selected=state.taskIndex===task.index&&state.sceneIndex===scene.index;return `<button class="replica-scene-tile ${value} ${selected?'active':''}" data-replica-scene="${task.index}:${scene.index}" aria-current="${selected?'true':'false'}" aria-label="${esc(taskLabel(task))} · ${esc(sceneLabel(scene))} · ${statusCopy[value]}"><span>${media(scene.renderStill,`${taskLabel(task)} ${sceneLabel(scene)} 真实渲染`)}</span><b>${esc(sceneLabel(scene))}</b><i title="${statusCopy[value]}"></i></button>`;}
 function taskCard(task){const value=taskStatus(task),selected=state.taskIndex===task.index,approved=task.scenes.filter(s=>s.status==='approved').length;return `<article class="replica-task-card ${selected?'active':''}" aria-label="${esc(task.title||taskLabel(task))}"><button class="replica-task-source" data-replica-task="${task.index}" aria-label="查看 ${esc(task.title||taskLabel(task))}"><span class="replica-task-source-media">${media(task.thumbnail_url,`${taskLabel(task)} 原视频片段`)}</span><span class="replica-task-source-copy"><b>${String(task.index+1).padStart(2,'0')}</b><span><strong title="${esc(task.title)}">${esc(task.title||taskLabel(task))}</strong><small>${taskRange(task)}</small></span></span></button><div class="replica-task-stills" aria-label="${esc(taskLabel(task))} 的静态布局帧">${task.scenes.map(scene=>sceneTile(task,scene)).join('')}</div><div class="replica-task-completion ${value}" title="${statusCopy[value]}"><span>${icon(value==='approved'?'check':value==='changes'?'edit':value==='generating'?'refresh':'info')}</span><strong>${approved}/${task.scenes.filter(s=>s.renderStill).length}</strong><small>${statusCopy[value]}</small></div></article>`;}
 function batchPanel(){const counts=D.counts(state.tasks);return `<aside class="replica-batch"><div class="replica-batch-heading"><div><strong>片段任务</strong><small>${state.tasks.length} 个真实范围 · ${counts.review+counts.changes+counts.approved} 个渲染静帧</small></div></div><div class="replica-batch-scroll"><div class="replica-task-list">${state.tasks.map(taskCard).join('')||'<p class="replica-empty-copy">先在拉片页选择或保存研究范围，也可以导入已有复刻案例。</p>'}</div></div><div class="replica-case-import"><label for="replica-case">已有复刻案例</label><select id="replica-case" ${state.busy?'disabled':''}>${state.cases.map(item=>`<option value="${esc(item.id||item.case_id)}">${esc(item.name)}</option>`).join('')}</select><button class="button" data-replica-action="import-case" ${state.busy||!state.cases.length?'disabled':''}>导入共享库</button></div><footer class="replica-batch-footer"><span>${icon('info')}待审 <b>${counts.review+counts.changes}</b></span><span>${icon('check')}已审 <b>${counts.approved}</b></span></footer></aside>`;}
 function stage(scene){
  const source=media(scene.sourceStill,'原片取证静帧'),current=media(scene.renderStill,'真实复刻静帧');
  if(state.mode==='current')return `<div class="replica-single-frame">${current}<span>${scene.renderStill?'真实复刻静帧':'静态布局待生成 · 原片不会充当复刻结果'}</span></div>`;
  if(state.mode==='source')return `<div class="replica-single-frame">${source}<span>原片取证静帧</span></div>`;
  if(!scene.renderStill||!scene.sourceStill)return `<div class="replica-single-frame">${media('')}<span>需要原片取证帧与真实复刻静帧，才能进行比较</span></div>`;
  if(state.mode==='side')return `<div class="replica-side"><div>${source}<span>原片</span></div><div>${current}<span>复刻</span></div></div>`;
  if(state.mode==='overlay')return `<div class="replica-stack">${source}<div class="replica-overlay" style="opacity:${state.opacity/100}">${current}</div><span class="replica-canvas-label">叠加 · 复刻 ${state.opacity}%</span></div>`;
  if(state.mode==='wipe')return `<div class="replica-stack">${source}<div class="replica-wipe" style="clip-path:inset(0 ${100-state.wipe}% 0 0)">${current}</div><i class="replica-wipe-line" style="left:${state.wipe}%"></i><span class="replica-canvas-label">左：复刻 · 右：原片</span></div>`;
  if(scene.comparisonStill)return `<div class="replica-single-frame">${media(scene.comparisonStill,'Skill 比较证据')}<span>Skill 保存的比较证据</span></div>`;
  return `<div class="replica-stack replica-difference">${source}<div>${current}</div><span class="replica-canvas-label">浏览器差值预览 · 不代表保真通过</span></div>`;
 }
 function modeControl(scene){if(state.mode==='overlay'&&scene.renderStill&&scene.sourceStill)return `<label class="replica-compare-range"><span>复刻透明度</span><input id="replica-opacity" type="range" min="0" max="100" value="${state.opacity}" aria-label="复刻透明度"><output>${state.opacity}%</output></label>`;if(state.mode==='wipe'&&scene.renderStill&&scene.sourceStill)return `<label class="replica-compare-range"><span>划像位置</span><input id="replica-wipe" type="range" min="0" max="100" value="${state.wipe}" aria-label="划像位置"><output>${state.wipe}%</output></label>`;return `<p class="replica-mode-hint" role="status">${esc(state.error||state.message||'从左侧选择研究范围或复刻项目；原片与真实产物分别保存。')}</p>`;}
 function stageGate(task){const stages=task.replica?.metadata?.stages||{};return `<div class="replica-stage-gate" aria-label="复刻阶段"><span class="${task.layoutReviewComplete?'done':'ready'}"><b>1</b>静态布局</span><i>→</i><span class="${stages.motion==='passed'?'done':'locked'}"><b>2</b>动效分析</span><i>→</i><span class="${stages.qa==='passed'?'done':'locked'}"><b>3</b>完整特效</span></div>`;}
 function inspector(task,scene){
  const value=scene.status,key=sceneKey(task,scene),note=Object.hasOwn(state.notes,key)?state.notes[key]:scene.note||'',m=task.replica?.metadata||{},bridge=m.skill_bridge||{},canReview=task.reviewAvailable&&!!scene.renderHash&&!!scene.sourceStill&&!state.busy&&!task.active&&!jobRunning();
  const event=bridge.events?.at(-1),preflight=m.stages?.preflight==='passed',isBridge=bridge.version===1;
  let actions='';
  if(!task.replica||!isBridge&&task.study)actions=`<button class="button primary" data-replica-action="create" ${state.busy?'disabled':''}>${icon('layers')}建立复刻项目</button>`;
  else if(isBridge)actions=`<button class="button primary" data-replica-action="${preflight?'layout':'preflight'}" ${state.busy||task.active||jobRunning()?'disabled':''}>${icon('refresh')}${task.active?'Skill 执行中…':preflight?'生成 / 修正静态布局':'运行范围预检'}</button>`;
  const evidence=event?.evidence_hash?`<a href="${D.blob(event.evidence_hash)}" target="_blank" rel="noopener">查看本轮工具记录</a>`:'';
  return `<aside class="replica-inspector"><div class="replica-panel-heading"><div><h2>静态帧审查</h2><p>${esc(taskLabel(task))} · ${task.replica?'v'+task.replica.revision:'尚未建项'}</p></div>${statusPill(value)}</div>${stageGate(task)}<section class="replica-inspection"><h3>本帧证据</h3><ul><li class="${scene.sourceStill?'':'pending'}"><span>${icon(scene.sourceStill?'check':'info')}</span><div><strong>原片取证帧</strong><small>${scene.sourceStill?'来自所选参考范围':'尚无对应取证静帧'}</small></div></li><li class="${scene.renderStill?'':'pending'}"><span>${icon(scene.renderStill?'check':'info')}</span><div><strong>复刻静态帧</strong><small>${scene.renderStill?'已保存真实渲染产物':'尚未生成，不可批准'}</small></div></li><li class="${scene.comparisonStill?'':'pending'}"><span>${icon(scene.comparisonStill?'check':'info')}</span><div><strong>比较图</strong><small>${scene.comparisonStill?'Skill 已保存比较证据':'暂无 Skill 比较证据'}</small></div></li></ul><p class="replica-next-action">${esc(m.next_action||(!task.replica?'将当前范围保存为共享研究，再交给复刻 Skill。':'已有可编辑样式；本轮视觉审查独立记录。'))}</p>${event?`<p class="replica-tool-result">最近阶段：${esc(event.stage)} · ${esc(event.status)}${event.error?'<br>'+esc(event.error):''}</p>`:''}${evidence}${scene.preview?`<a href="${scene.preview}" target="_blank" rel="noopener">打开真实视频预览</a>`:''}</section><section class="replica-comment"><label for="replica-note"><strong>本帧审查意见</strong><span>要求修改时必须填写</span></label><textarea id="replica-note" placeholder="指出这一张静态帧的位置、比例、层级或材质问题…">${esc(note)}</textarea><p class="replica-error" role="alert">${esc(state.error)}</p></section><div class="replica-run-actions">${actions}${task.replica?'<small>生成结果需人工审看；不会自动成为可信样式。</small>':''}${!task.reviewAvailable&&scene.renderStill?'<small>审查服务尚未就绪，本帧不会在浏览器中伪批准。</small>':''}</div><div class="replica-approval-actions"><button class="button" data-replica-action="changes" ${canReview?'':'disabled'}>${icon('edit')}要求修改</button><button class="button primary" data-replica-action="approve" ${canReview?'':'disabled'}>${icon('check')}批准此静态帧</button></div></aside>`;
 }
 function sceneProgress(task){const count=task.scenes.filter(s=>s.renderStill).length,approved=task.scenes.filter(s=>s.status==='approved').length;return `<div class="replica-scene-progress"><span>${task.layoutReviewComplete?'本轮静态布局已审':'本轮静态布局门'}</span><strong>${approved} / ${count} 已审</strong><div><i style="width:${count?approved/count*100:0}%"></i></div></div>`;}
 function render(){
  if(typeof S!=='undefined'&&S.view!=='replica')return;
  const project=currentProject(),task=currentTask(),scene=task?.scenes[state.sceneIndex],root=$('#content');if(!root)return;
  const viewer=scene?`<main class="replica-viewer"><div class="replica-view-toolbar"><div class="replica-current-copy"><strong>${esc(taskLabel(task))} · ${esc(sceneLabel(scene))}</strong><small>${taskRange(task)}</small></div><div class="replica-view-tabs" role="group" aria-label="静态帧对比视图">${viewButton('current','复刻','film')}${viewButton('source','原片','image')}${viewButton('side','左右','columns')}${viewButton('overlay','叠加','blend')}${viewButton('wipe','划像','scan')}${viewButton('diff','差异','diff')}</div><button class="icon-btn" data-replica-action="fullscreen" aria-label="全屏查看">${icon('expand')}</button></div><div class="replica-canvas" id="replica-canvas">${stage(scene)}</div><div class="replica-mode-control">${modeControl(scene)}</div>${sceneProgress(task)}</main>${inspector(task,scene)}`:`<main class="replica-viewer"><div class="replica-canvas">${media('')}</div><div class="replica-mode-control"><p class="replica-mode-hint" role="status">${esc(state.error||state.message||(state.loading?'正在读取复刻项目…':'选择研究范围后，复刻结果会保存在这里。'))}</p></div></main><aside class="replica-inspector"><div class="replica-panel-heading"><h2>静态帧审查</h2></div><p class="replica-empty-copy">研究范围、生成结果和审查进度使用同一共享资产体系保存。</p></aside>`;
  root.innerHTML=`<section class="replica-shell replica-reference-shell">${toolbar(project)}<div class="replica-reference-layout">${batchPanel()}${viewer}</div></section>`;
 }
 function fail(error){state.error=error.message||String(error);render();toast(state.error);}
 async function detail(task=currentTask(),paint=true){
  if(!task?.replica)return;const id=task.replica.id;
  try{const result=await client.details(id);state.details[id]=result;if(paint){syncTasks();render();}}catch(error){if(error.status!==404)throw error;}
 }
 function schedule(){clearTimeout(timer);if(state.tasks.some(task=>task.active))timer=setTimeout(()=>{if(S.view==='replica')hydrate().catch(fail);},2500);}
 async function hydrate(keepId){
  const token=++state.token;state.loading=true;render();
  try{const result=await client.library();if(token!==state.token)return;state.assets=result.assets;state.cases=result.cases;syncProjects();syncTasks(keepId);const queue=state.tasks.filter(task=>task.replica);await Promise.all([0,1].map(async()=>{while(queue.length&&token===state.token)await detail(queue.shift(),false);}));if(token!==state.token)return;syncTasks(keepId);state.error='';}
  catch(error){if(token===state.token)fail(error);}
  finally{if(token===state.token){state.loading=false;render();schedule();}}
 }
 async function selectTask(index,sceneIndex=0){state.taskIndex=Math.max(0,Math.min(state.tasks.length-1,Number(index)));state.sceneIndex=Math.max(0,Math.min((currentTask()?.scenes.length||1)-1,Number(sceneIndex)));state.mode='current';state.error='';render();await detail();}
 async function review(action){const task=currentTask(),item=task.scenes[state.sceneIndex],note=$('#replica-note')?.value||'';state.busy=true;state.error='';render();try{const result=await client.review(task,item,action,note);state.details[task.id]=result;state.assets=state.assets.map(a=>a.id===task.id?result.replica:a);delete state.notes[sceneKey(task,item)];syncTasks(task.id);state.message='审查结果已保存到共享资产的新版本。';}catch(error){if(error.status===409){await hydrate(task.id);throw new Error('复刻项目已更新，已读取最新结果。请重新审看后提交。');}throw error;}finally{state.busy=false;render();}}
 async function run(stage){const task=currentTask();if(task.active||jobRunning())throw new Error('当前复刻项目仍在执行。');state.busy=true;state.error='';state.message=stage==='preflight'?'正在运行真实范围预检…':'正在调用复刻 Skill，进度和失败证据都会保存。';render();try{const result=await client.advance(task,stage);state.job=result.job;state.message='复刻任务已排队，可离开后继续。';pollJob(result.job.id,task.id);}finally{state.busy=false;render();}}
 function pollJob(jobId,taskId){clearTimeout(timer);timer=setTimeout(async()=>{try{const {job}=await client.request(`/jobs/${encodeURIComponent(jobId)}`);state.job=job;if(['queued','running','processing'].includes(job.status)){state.message='Skill 正在执行；结果完成后更新到共享库。';if(S.view==='replica')render();pollJob(jobId,taskId);return;}await hydrate(taskId);const task=state.tasks.find(item=>item.id===taskId);const outcome=D.jobOutcome(job,task);state.message=outcome.message;state.error=outcome.error;render();}catch(error){fail(error);}},2000);}
 async function create(){const task=currentTask(),project=currentProject();state.busy=true;state.error='';render();try{const result=await client.create(task,project);state.message='研究范围与复刻项目已保存。下一步运行真实范围预检。';await hydrate(result.replica.id);}finally{state.busy=false;render();}}
 async function importCase(){const id=$('#replica-case')?.value;if(!id)return;state.busy=true;state.error='';state.message='正在校验并导入真实可编辑案例，首次导入需要渲染。';render();try{const result=await client.request('/cases/import',{case_id:id});state.projectId=`asset:${result.replica.metadata.source.asset_id}`;state.message='真实案例和可复用样式已进入共享库；视觉审查保持待审。';await hydrate(result.replica.id);}finally{state.busy=false;render();}}
 if(typeof document!=='undefined'){
  document.addEventListener('click',event=>{
   const target=event.target.closest('[data-replica-task],[data-replica-scene],[data-replica-mode],[data-replica-action]');if(!target||S.view!=='replica'||target.disabled)return;
   Promise.resolve().then(async()=>{if(target.dataset.replicaTask!==undefined)return selectTask(target.dataset.replicaTask);if(target.dataset.replicaScene){const [a,b]=target.dataset.replicaScene.split(':');return selectTask(a,b);}if(target.dataset.replicaMode){state.mode=target.dataset.replicaMode;render();return;}
    const action=target.dataset.replicaAction;if(action==='approve'||action==='changes')return review(action);if(action==='create')return create();if(action==='preflight'||action==='layout')return run(action);if(action==='refresh')return hydrate();if(action==='import-case')return importCase();if(action==='fullscreen')$('#replica-canvas')?.requestFullscreen?.();
   }).catch(fail);
  });
  document.addEventListener('input',event=>{if(S.view!=='replica')return;const field=event.target;if(field.id==='replica-opacity'){state.opacity=Number(field.value);if($('.replica-overlay'))$('.replica-overlay').style.opacity=state.opacity/100;if($('.replica-canvas-label'))$('.replica-canvas-label').textContent=`叠加 · 复刻 ${state.opacity}%`;if($('.replica-compare-range output'))$('.replica-compare-range output').textContent=`${state.opacity}%`;}if(field.id==='replica-wipe'){state.wipe=Number(field.value);if($('.replica-wipe'))$('.replica-wipe').style.clipPath=`inset(0 ${100-state.wipe}% 0 0)`;if($('.replica-wipe-line'))$('.replica-wipe-line').style.left=`${state.wipe}%`;if($('.replica-compare-range output'))$('.replica-compare-range output').textContent=`${state.wipe}%`;}if(field.id==='replica-note'){const task=currentTask(),item=task?.scenes[state.sceneIndex];if(item)state.notes[sceneKey(task,item)]=field.value;}});
  document.addEventListener('change',event=>{if(S.view!=='replica'||event.target.id!=='replica-project')return;state.projectId=event.target.value;state.taskIndex=0;state.sceneIndex=0;state.error='';state.message='';syncTasks();render();hydrate().catch(fail);});
 }
 function mount(projects,current){
  state.localProjects=projects||[];syncProjects();if(!state.projectId)state.projectId=current?.id||state.projects[0]?.id;syncTasks();
  const selected=typeof Clips!=='undefined'?Clips.active?.():null;if(selected&&current?.id===state.projectId){const index=state.tasks.findIndex(t=>D.rangeKey(t.start,t.end)===D.rangeKey(selected.start,selected.end));if(index>=0)state.taskIndex=index;}
  render();hydrate();
 }
 return{render:mount};
})();
