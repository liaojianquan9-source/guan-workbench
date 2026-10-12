'use strict';
// 拉片三轨片段化：画面 / 字幕 / 音乐共用时间尺，仅展示与定位，不改分析算法。
const StudySegmentShell=(()=>{
 const trackDefs=[['picture','画面轨','grid'],['subtitle','字幕轨','captions'],['music','音乐轨','music']];
 let owner=null,zoom=1,manualUntil=0;
 const range=()=>({start:0,end:S.p.duration});
 const maxZoom=()=>Math.max(8,Math.min(120,S.p.duration/2));
 const mode=()=>S.studySegmentMode||'manual';
 const selection=()=>S.studySelection;
 const setSelection=next=>{S.studySelection=next;renderDetail();paint();};
 const clearSelection=()=>{if(S.studySelection){S.studySelection=null;renderDetail();paint();}};
 function analysisTools(){
  const p=S.p;
  return [['scenes','画面切分','film',p.status,!!p.analysis||p.shots.length>1,p.progress,p.message],['transcript','转文字','captions',p.transcript?.status,p.transcript?.status==='ready',p.transcript?.progress,p.transcript?.message],['music','音乐分段','music',p.music_sections?.status,p.music_sections?.status==='ready',null,p.music_sections?.message]].map(([key,label,glyph,status,done,progress,message])=>{
   const busy=['processing','queued','waiting_audio'].includes(status),failed=status==='error',silent=key!=='scenes'&&!p.has_audio;
   const hint=silent?'这个视频没有声音':busy?(message||'正在处理…'):failed?(message||'处理未完成')+' · 点击重试':done?'已完成 · 点击查看':key==='music'?'准备背景声并查找音乐变化':'按镜头变化切分画面';
   const text=busy?(key==='scenes'?'切分中':key==='transcript'?'转写中':status==='waiting_audio'?'准备声音':'分段中')+(Number.isFinite(progress)?' '+Math.round(progress*100)+'%':''):label;
   return `<button class="analysis-tool ${done?'done':''} ${failed?'failed':''}" data-action="prepare-${key}" aria-label="${label}" title="${esc(hint)}" aria-busy="${busy}" ${busy||silent?'disabled':''}>${icon(busy?'refresh':glyph)}<span>${text}</span>${failed?'<i aria-label="未完成">!</i>':''}</button>`;
  }).join('');
 }
 function pictureSpans(){
  const p=S.p,pictures=p.shots.length>1||p.analysis?p.shots:S.previews?.length?S.previews.map((s,i,all)=>({...s,id:s.id||`preview-${i}`,start:i*p.duration/all.length,end:(i+1)*p.duration/all.length,thumbnail_url:s.url})):p.shots;
  return ClipLogic.shotSpans(range(),pictures);
 }
 function subtitleSpans(){return ClipLogic.shotSpans(range(),(S.p.transcript?.segments||[]).map((s,index)=>({...s,index})).filter(s=>Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.end>s.start));}
 function musicSpans(){return (MusicSections.sections()||[]).map(s=>({...s,left:s.start/S.p.duration,width:(s.end-s.start)/S.p.duration}));}
 function emptyLane(track){
  const p=S.p;
  if(track==='picture'){
   if(p.status==='processing')return {text:'正在识别镜头…'};
   if(!p.analysis&&p.shots.length<=1)return {text:'尚未切分画面',action:'prepare-scenes',label:'画面切分'};
   return null;
  }
  if(track==='subtitle'){
   const tr=p.transcript||{};
   if(tr.status==='processing')return {text:'正在转写…'};
   if(tr.status==='error')return {text:tr.message||'转写未完成',action:'prepare-transcript',label:'重试转文字'};
   if(tr.status!=='ready'||!(tr.segments||[]).length)return {text:'暂无字幕',action:'prepare-transcript',label:'转文字'};
   return null;
  }
  if(track==='music'){
   if(!p.has_audio)return {text:'原片没有声音'};
   const ms=p.music_sections||{};
   if(['processing','waiting_audio','queued'].includes(ms.status))return {text:ms.message||'正在准备声音…'};
   if(ms.status==='error')return {text:ms.message||'音乐分段未完成',action:'prepare-music',label:'重试音乐分段'};
   if(ms.status!=='ready'||!musicSpans().length)return {text:'暂无音乐分段',action:'prepare-music',label:'音乐分段'};
   return null;
  }
  return null;
 }
 function laneBlocks(track){
  if(track==='picture'){
   return pictureSpans().map((s,i)=>`<button type="button" class="segment-block picture" data-segment-track="picture" data-segment-id="${esc(s.id||String(i))}" data-start="${esc(s.start)}" data-end="${esc(s.end)}" style="left:${s.left*100}%;width:calc(${s.width*100}% - 3px)" aria-label="镜头 ${clock(s.start)}—${clock(s.end)}">${s.thumbnail_url?`<img src="${esc(safeLocalUrl(s.thumbnail_url))}" alt="" loading="lazy">`:''}<span class="segment-block-label">${clock(s.start)}</span></button>`).join('');
  }
  if(track==='subtitle'){
   return subtitleSpans().map(s=>`<button type="button" class="segment-block subtitle" data-segment-track="subtitle" data-segment-index="${esc(s.index)}" data-start="${esc(s.start)}" data-end="${esc(s.end)}" style="left:${s.left*100}%;width:calc(${s.width*100}% - 3px)" aria-label="${clock(s.start)} · ${esc(s.text)}"><span>${esc(s.text)}</span></button>`).join('');
  }
  return musicSpans().map(s=>`<button type="button" class="segment-block music" data-segment-track="music" data-segment-id="${esc(s.id)}" data-start="${esc(s.start)}" data-end="${esc(s.end)}" style="left:${s.left*100}%;width:calc(${s.width*100}% - 3px)" aria-label="音乐 ${clock(s.start)}—${clock(s.end)} · ${esc(MusicSections.title(s))}"><span>${esc(MusicSections.title(s))}</span></button>`).join('');
 }
 function laneRow(track){
  const empty=emptyLane(track),blocks=laneBlocks(track);
  const body=empty?`<div class="segment-lane-empty"><span>${esc(empty.text)}</span>${empty.action?button(empty.label,empty.action,'quiet','plus'):''}</div>`:blocks;
  return `<div class="segment-track-row" data-segment-lane="${track}"><div class="segment-track-lane ${empty?'is-empty':''}" data-segment-lane-body="${track}">${body}</div></div>`;
 }
 function render(el){
  if(!S.p)return;
  const p=S.p;
  if(owner!==p.id){owner=p.id;zoom=Math.max(1,Math.min(maxZoom(),S.zoom||1));S.studySelection=null;}
  const signature=JSON.stringify([p.id,p.shots.map(s=>s.id),p.transcript?.segments,p.music_sections,S.previews?.length,zoom,mode()]);
  if(el.dataset.segmentKey===signature){paint();return;}
  el.dataset.segmentKey=signature;
  const oldScroll=el.querySelector('.segment-track-scroll')?.scrollLeft||0;
  el.innerHTML=`<div class="segment-tracks-head"><div class="analysis-tools" role="group" aria-label="按需分析">${analysisTools()}</div><span class="spacer"></span><label class="clip-track-zoom" title="时间线缩放"><input id="segment-track-zoom" type="range" min="1" max="${maxZoom()}" step=".25" value="${zoom}" aria-label="时间线缩放"></label><button class="track-tool" data-segment-action="fit" title="显示整条时间线" aria-label="显示整条时间线">${icon('expand')}</button></div>
  <div class="segment-track-grid"><div class="segment-track-labels"><div class="segment-ruler-label"><time id="segment-timecode" aria-label="当前时间"></time></div>${trackDefs.map(([key,title,glyph])=>`<div class="segment-side-label">${icon(glyph)}<span>${title}</span></div>`).join('')}</div>
  <div class="segment-track-scroll"><div class="segment-track-content" style="width:${zoom*100}%"><div class="segment-track-ruler" aria-hidden="true"></div>${trackDefs.map(([key])=>laneRow(key)).join('')}<i class="segment-playhead" aria-hidden="true"><svg class="playhead-marker" viewBox="0 0 14 22"><path d="M3 1H11V13L7 18L3 13Z"/></svg></i></div></div></div>`;
  $('.segment-track-scroll',el).scrollLeft=oldScroll;
  bind(el);rulers();paint();renderDetail();
 }
 function rulers(){
  const ruler=$('.segment-track-ruler'),scroll=$('.segment-track-scroll');if(!S.p||!ruler||!scroll)return;
  const duration=S.p.duration,width=ruler.clientWidth,step=ClipLogic.rulerStep(duration,width),divisions=step*width/duration>=90?10:5,interval=step/divisions;
  const first=Math.max(0,Math.floor(scroll.scrollLeft/width*duration/step)-1)*divisions;
  const last=Math.min(Math.ceil(duration/interval),Math.ceil((scroll.scrollLeft+scroll.clientWidth)/width*duration/step+1)*divisions);
  const signature=[first,last,step,divisions].join(':');
  if(ruler.dataset.ticks===signature)return;
  ruler.dataset.ticks=signature;
  const ticks=[];
  for(let i=first;i<=last;i++){const t=i*interval;if(t>duration)break;const major=i%divisions===0;ticks.push(major?`<span class="ruler-second" style="left:${t/duration*100}%">${ClipLogic.rulerLabel(t)}</span>`:`<i class="ruler-tick ${i%divisions===divisions/2?'mid':''}" style="left:${t/duration*100}%"></i>`);}
  ruler.innerHTML=ticks.join('');
 }
 function paint(){
  const el=$('#timeline');if(!S.p||!el?.classList.contains('study-segment-timeline'))return;
  const tools=$('.segment-tracks-head .analysis-tools');if(tools){const html=analysisTools();if(tools.dataset.content!==html){tools.innerHTML=html;tools.dataset.content=html;}}
  const ratio=S.position/S.p.duration,head=$('.segment-playhead');if(head)head.style.left=`${ratio*100}%`;
  const timecode=$('#segment-timecode');if(timecode){const nominal=Math.max(1,Math.round(S.p.fps)),frame=Math.max(0,Math.round(S.position*S.p.fps)),seconds=Math.floor(frame/nominal);timecode.textContent=[Math.floor(seconds/60),seconds%60,frame%nominal].map(n=>String(n).padStart(2,'0')).join(':');}
  const sel=selection();
  $$('[data-segment-track]').forEach(btn=>{
   const on=sel&&btn.dataset.segmentTrack===sel.track&&((sel.track==='subtitle'&&Number(btn.dataset.segmentIndex)===sel.index)||(sel.track!=='subtitle'&&btn.dataset.segmentId===sel.id));
   btn.classList.toggle('active',on);btn.setAttribute('aria-current',String(on));
  });
  const scroll=$('.segment-track-scroll');
  if(scroll&&(!$('#video')?.paused||S.forceFollow)&&performance.now()>manualUntil){const x=ratio*scroll.scrollWidth;if(x<scroll.scrollLeft||x>scroll.scrollLeft+scroll.clientWidth)scroll.scrollLeft=Math.max(0,x-scroll.clientWidth*.35);}
 }
 function renderDetail(){
  const panel=$('#segment-detail');if(!panel)return;
  const sel=selection(),ai=mode()==='ai';
  if(ai&&!sel){panel.classList.add('is-empty');panel.innerHTML=`<div class="segment-detail-empty"><strong>AI 模式</strong><p>后续会在这里展示 AI 对片段的建议；本轮仅占位，不会自动改动时间线。</p></div>`;return;}
  if(!sel){panel.classList.add('is-empty');panel.innerHTML=`<div class="segment-detail-empty"><strong>片段详情</strong><p>点击下方画面、字幕或音乐块，预览会跳到该段起点。</p></div>`;return;}
  panel.classList.remove('is-empty');
  const p=S.p;
  let title='',body='',labels=[];
  if(sel.track==='picture'){
   const shot=p.shots.find(s=>s.id===sel.id)||{start:sel.start,end:sel.end};
   title=shotName(shot,p);body=shot.note?.trim()||'暂无备注';labels=['画面','镜头'];
  }else if(sel.track==='subtitle'){
   const seg=(p.transcript?.segments||[])[sel.index];
   title='字幕';body=seg?.text||'';labels=['字幕'];
  }else{
   const section=MusicSections.sections().find(s=>s.id===sel.id);
   title=section?MusicSections.title(section):'音乐段';body=section?'背景声变化建议位置，可回到「研究资料 → 音乐」试听或识曲。':'';labels=['音乐'];
  }
  const copyBtn=mode()==='manual'?`<button class="button quiet" data-segment-action="copy-time" type="button">${icon('copy')}复制起点时码</button>`:'';
  const aiNote=ai?`<p class="segment-ai-note">AI 建议稍后需你确认；本轮不会自动修改片段。</p>`:'';
  panel.innerHTML=`<header class="segment-detail-head"><div><strong>${esc(title)}</strong><div class="segment-detail-meta">${labels.map(l=>`<span class="chip">${esc(l)}</span>`).join('')}<time class="mono">${clock(sel.start)} — ${clock(sel.end)}</time></div></div><button class="icon-btn" data-segment-action="clear" aria-label="收起详情" title="收起">${icon('close')}</button></header><div class="segment-detail-body"><p>${esc(body)}</p>${aiNote}</div><footer class="segment-detail-foot">${copyBtn}</footer>`;
 }
 function selectFromButton(btn){
  const track=btn.dataset.segmentTrack,start=Number(btn.dataset.start),end=Number(btn.dataset.end);
  const payload={track,start,end};
  if(track==='subtitle')payload.index=Number(btn.dataset.segmentIndex);
  else payload.id=btn.dataset.segmentId;
  setSelection(payload);
  seek(start);
  if(track==='music')MusicSections.choose(btn.dataset.segmentId,false,true);
  else if(track==='subtitle')CollectionLink.reveal('transcript',payload.index);
  else{const shot=S.p.shots.find(s=>s.id===payload.id);if(shot)CollectionLink.reveal('shots',shot.id);}
 }
 function bind(el){
  const scroll=$('.segment-track-scroll',el);
  scroll.addEventListener('scroll',()=>{manualUntil=performance.now()+2500;rulers();},{passive:true});
  scroll.addEventListener('wheel',e=>{manualUntil=performance.now()+3000;if(e.ctrlKey){e.preventDefault();applyZoom(zoom*Math.exp(-e.deltaY*.01));}else if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){e.preventDefault();scroll.scrollLeft+=e.deltaY;}},{passive:false});
  $('#segment-track-zoom',el)?.addEventListener('input',e=>applyZoom(Number(e.target.value)));
  el.addEventListener('click',e=>{
   const block=e.target.closest('[data-segment-track]');if(block){selectFromButton(block);return;}
   const action=e.target.closest('[data-segment-action]')?.dataset.segmentAction;
   if(action==='fit')applyZoom(1);
   if(action==='clear')clearSelection();
   if(action==='copy-time'&&selection()){const text=clock(selection().start);navigator.clipboard?.writeText(text).then(()=>toast(`已复制 ${text}`)).catch(()=>toast(text));}
  });
  for(const lane of $$('[data-segment-lane-body]',el)){
   lane.addEventListener('pointerdown',e=>{
    if(e.button!==0||e.target.closest('[data-segment-track]'))return;
    const rect=lane.getBoundingClientRect(),time=ClipLogic.point(range(),(e.clientX-rect.left)/rect.width,{fps:S.p.fps,pixelWidth:rect.width,snap:S.snap,bypass:e.altKey,candidates:[]}).time;
    seek(time);paint();
   });
  }
  S.segmentRulerObserver?.disconnect();
  S.segmentRulerObserver=new ResizeObserver(rulers);
  S.segmentRulerObserver.observe($('.segment-track-content',el));
 }
 function applyZoom(value){
  const scroll=$('.segment-track-scroll'),content=$('.segment-track-content');if(!S.p||!scroll||!content)return;
  const oldWidth=scroll.scrollWidth,oldScroll=scroll.scrollLeft;
  zoom=Math.max(1,Math.min(maxZoom(),value));S.zoom=zoom;writeSetting('zoom:'+S.p.id,zoom);
  content.style.width=`${zoom*100}%`;
  scroll.scrollLeft=Interaction.zoomScroll({oldWidth,newWidth:scroll.scrollWidth,scrollLeft:oldScroll,viewport:scroll.clientWidth,anchorTime:S.position,duration:S.p.duration});
  const input=$('#segment-track-zoom');if(input)input.value=zoom;
  rulers();paint();
 }
 function importMetaStrip(p){
  const parts=[];
  if(p.width&&p.height)parts.push(`${p.width} × ${p.height}`);
  if(p.fps&&Number.isFinite(p.fps))parts.push(`${Number(p.fps).toFixed(2)} fps`);
  const rate=p.original_metadata?.bit_rate??p.original_metadata?.format?.bit_rate;
  if(rate&&Number.isFinite(Number(rate)))parts.push(`${Math.round(Number(rate)/1000)} kbps`);
  if(!parts.length)return '';
  return `<div class="import-meta-strip" aria-label="导入信息">${parts.map(t=>`<span>${esc(t)}</span>`).join('')}</div>`;
 }
 function studyTopbar(p){
  const manual=mode()==='manual',ai=mode()==='ai';
  return `<header class="study-topbar"><button class="button quiet study-back" data-action="study-back" type="button">${icon('arrow')}返回素材</button><h1 class="study-title" title="${esc(titleOf(p))}">${esc(titleOf(p).replace(/\.[^.]+$/,''))}</h1><div class="ai-segment-control" role="group" aria-label="拉片模式"><button type="button" data-action="study-mode-manual" class="${manual?'active':''}" aria-pressed="${manual}">手动</button><button type="button" data-action="study-mode-ai" class="${ai?'active':''}" aria-pressed="${ai}">AI</button></div></header>`;
 }
 return {render,paint,renderDetail,importMetaStrip,studyTopbar,clearSelection};
})();
