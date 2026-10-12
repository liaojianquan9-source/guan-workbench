'use strict';
// Public hooks only: storage, playback and panel logic remain independent of page layout.
const Clips=(()=>{
 let activeId=null, projectId=null, tab='frames', loop=false, attachedVideo=null, browsing=false, audition=null;
 let editingTimeline=false;
 const guard=new LapianInteraction.SingleFlight();
 const active=()=>S.p?.id===projectId?(S.p.research_clips?.find(c=>c.id===activeId&&!c.deleted)||null):null;
 const cb=(label,action,attrs='',kind='')=>`<button class="button ${kind}" data-clip-action="${action}" ${attrs}>${label}</button>`;
 const persist=()=>{if(S.p)writeSetting('research:'+S.p.id,{id:activeId,tab,loop})};
 function stopSound(){ClipMixer.stop();}
 function reset(){browsing=false;audition=null;stopSound();activeId=null;projectId=null;attachedVideo=null;}
 function restore(sourceTime){reset();projectId=S.p?.id;const saved=readSetting('research:'+projectId,{});activeId=Number.isFinite(sourceTime)?null:saved.id;tab=['frames','sound','subtitles','notes'].includes(saved.tab)?saved.tab:'frames';loop=Number.isFinite(sourceTime)?false:!!saved.loop;if(active()){S.collection='shots';S.collectionOpen=true;}else activeId=null;}
 function locate(time){seek(time);}
 function playbackBounds(){const c=active();return audition||(c?{start:c.start,end:c.end}:null);}
 function startAudition(start,end){if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return false;audition={start,end};loop=false;paintToolbar();return true;}
 function clearAudition(repaint=true){const changed=!!audition;audition=null;if(changed)loop=false;if(changed&&repaint)paintToolbar();return changed;}
 function isAuditioning(){return !!audition;}
 function limit(time){return time;}
 function toolbar(){return Studio.toolbar();}
 function paintToolbar(){const el=$('#clip-toolbar');if(el)el.innerHTML=toolbar();const label=$('.player-label');if(label)label.textContent='原片';if($('#timeline')?.classList.contains('study-segment-timeline'))StudySegmentShell.paint();else ClipTimeline.paint();}
 function choose(id){browsing=false;audition=null;activeId=id;projectId=S.p.id;const c=active();if(!c)return;S.collection='shots';S.collectionOpen=true;$('.collection')?.classList.add('open');Studio.syncPanels();persist();seek(c.start);ClipMixer.activate();renderTracks();renderCollection();paintToolbar();}
 function browse(){browsing=true;audition=null;activeId=null;loop=false;persist();S.collection='shots';renderCollection();renderTracks();}
 function chooseShot(shot){audition=null;activeId=null;loop=false;persist();seek(shot.start);renderTracks();}
 function exit(){$('#video')?.pause();audition=null;activeId=null;loop=false;persist();renderTracks();paintToolbar();renderCollection();}
 function assertPictureEditable(){if(editingTimeline)throw new Error('正在调整分镜，请稍候。');if(ClipMixer.state().tracks.original.locked)throw new Error('画面轨已锁定，请先解锁。');}
 async function editPicture(action,extra={},owner=S.p?.id,revision=S.p?.revision){
  assertPictureEditable();$('#video')?.pause();editingTimeline=true;ClipTimeline.paint();
  try{
   const p=await api(url(owner,'/storyboard'),{action,expected_revision:revision,...extra});upsert(p);
   if(S.p?.id===owner){renderTracks();refreshViews();}
   if(action!=='undo'){const operation=p.storyboard_history.at(-1).id;toast(action==='split'?'已在当前画面切开分镜':'相邻分镜已合并',()=>editPicture('undo',{operation_id:operation},owner,S.projects.find(p=>p.id===owner)?.revision));}
   return p;
  }finally{editingTimeline=false;ClipTimeline.paint();}
 }
 function splitPicture(){const shot=current();if(!shot)return;return editPicture('split',{id:shot.id,time:S.position});}
 async function openMerge(){
  assertPictureEditable();const ids=ClipTimeline.mergeSelection();
  if(ids.length!==2){toast('请按住 Shift 点选两个相邻画面，再点击合并');return;}
  await editPicture('merge',{id:ids[0],next_id:ids[1]});ClipTimeline.clearMerge();
 }
 async function request(action,body={},owner=S.p?.id){const result=await api(url(owner,'/research'),{action,...body});if(result.project)upsert(result.project);if(S.p?.id===owner){refreshViews();renderTracks();paintToolbar()}return result;}
 function currentBody(c=active()){return {id:c.id,expected_revision:c.revision}}
 function filesHTML(files,c){return Studio.fileCards(files,c)}
 function showTab(next){browsing=false;tab=next;persist();renderCollection();Studio.syncPanels();}
 function render(){const el=$('#collection-list');if(!el||!S.p)return;const old=el.scrollTop, clips=(S.p.research_clips||[]).filter(c=>!c.deleted),c=browsing?null:active();$('#collection-count').textContent=((S.p.analysis||S.p.shots.length>1?S.p.shots.length:0)+clips.length)+' 个分镜';
 if(!c){el.innerHTML=statusHTML(S.p,'scenes')+(clips.length?`<p class="clip-intro">已保存分镜 · ${clips.length}</p>`+clips.map(c=>Studio.clipCard(c,S.p)).join(''):'')+`<p class="clip-intro">原片镜头 · 点击定位</p><div class="scene-grid study-scenes">${sceneItems().map(s=>sceneCard(s)).join('')}</div>`;el.scrollTop=old;return;}
 const frames=c.frames.filter(f=>!f.deleted).sort((a,b)=>a.time-b.time),notes=c.notes.filter(n=>!n.deleted),sound=c.sound||{};
 let content='';
 if(tab==='frames')content=cb(icon('camera')+'保存当前画面 · '+keyHint('capture'),'capture','','primary')+`<div class="clip-frames">${frames.map(f=>Studio.frameCard(f,c)).join('')||Studio.empty('image','留下值得细看的画面','停在任意一帧，按 '+keyHint('capture')+' 保存。')}</div>`;
 if(tab==='notes')content=cb(icon('plus')+'记录当前观察','note','','primary')+Studio.noteEditor(c)+`<div class="clip-notes">${notes.map(n=>`<article><button class="clip-note-time" data-clip-action="seek" data-time="${esc(n.time)}">${clock(n.time)}${n.outside?' · 范围外':''}</button><p>${esc(n.text)}</p><div class="row">${cb(icon('edit')+'编辑','note',`data-note="${esc(n.id)}"`)}${cb(icon('trash')+'移除','remove-note',`data-item="${esc(n.id)}"`)}</div></article>`).join('')||Studio.empty('note','把看见的，变成观察','笔记会记住当前画面的位置。')}</div>`;
 if(tab==='subtitles'){const rows=ClipLogic.subtitles(c,S.p.transcript?.segments||[]);content=rows.map(s=>cb(`<time>${clock(Math.max(c.start,s.start))}</time><span>${esc(s.text)}</span>`,'seek',`data-time="${Math.max(c.start,s.start)}"`,'clip-subtitle')).join('')||Studio.empty('captions','这段还没有字幕','识别后可点击文字，定位并回听。')+button('识别原视频字幕','transcribe','','captions');}
 if(tab==='sound'){const files=sound.files||{};content=`<p class="clip-hint">在下方轨道用 S 单独回听。背景声包含音乐和音效。</p>${S.p.has_audio&&!files.original?cb(icon('download')+'保存片段原音','original'):''}${filesHTML(Object.values(files),c)}${!Object.keys(files).length?Studio.empty('audio','声音与画面对齐','在下方时间线分离人声与背景声。'):''}${c.sound_history?.length?`<details class="clip-file"><summary>旧范围的声音（${c.sound_history.length} 组）</summary>${c.sound_history.map(h=>filesHTML(Object.values(h.files||{}),c)).join('')}</details>`:''}`;}
 el.innerHTML=`<div class="clip-detail-head"><button class="clip-back" data-clip-action="back">${icon('back')}所有分镜</button><strong>${esc(c.title)}</strong><div class="clip-detail-meta"><time>${clock(c.start)}—${clock(c.end)}</time><span>· ${(c.end-c.start).toFixed(2)} s</span>${cb(icon('edit'),'edit','aria-label="改名或调整范围" title="改名或调整范围"','icon-btn')}${cb(icon('trash'),'delete','aria-label="移除分镜" title="移除分镜"','icon-btn')}</div></div><nav class="clip-detail-tabs" aria-label="分镜研究内容">${[['frames','画面'],['sound','声音'],['subtitles','字幕'],['notes','笔记']].map(([key,label])=>cb(icon(Studio.glyphs[key])+label,'tab',`data-tab="${key}" aria-pressed="${tab===key}"`,tab===key?'active':'')).join('')}</nav><section class="clip-detail-body">${content}</section>`;el.scrollTop=old;
 }
 function openEdit(){const c=active(),locked=TrackLogic.locked(ClipMixer.state()).length>0;$('#video')?.pause();S.modal={type:'clip-edit',projectId:S.p.id,...currentBody()};showModal('修改分镜',`<label class="label">名称<input id="clip-title" value="${esc(c.title)}" maxlength="120"></label><div class="row"><label class="label">开始时间（原片秒数）<input id="clip-start" ${locked?'disabled':''} type="number" min="0" max="${esc(S.p.duration)}" step="${esc(1/S.p.fps)}" value="${esc(c.start)}"></label><label class="label">结束时间（原片秒数）<input id="clip-end" ${locked?'disabled':''} type="number" min="0" max="${esc(S.p.duration)}" step="${esc(1/S.p.fps)}" value="${esc(c.end)}"></label></div><p>${locked?'轨道已锁定，起止范围不可修改；仍可改名。':'改名不会移动已存文件。改范围后，旧声音保留在历史结果，范围外的画面和笔记会标出。'}</p>`,button('取消','close-dialog')+cb('保存修改','save-edit','','primary'));}
 function draftKey(m){return `research-note:${m.projectId}:${m.id}:${m.note_id||'new'}`}
 function openNote(id){Studio.openNote(id)}
 async function capture(){const c=active();if(!c)return;if(!ClipLogic.inside(c,S.position))throw new Error('当前画面在所选分镜之外，请先点选片段内的画面。');$('#video')?.pause();const result=await request('capture',{...currentBody(c),time:S.position});if(S.p.id===result.project.id){S.collection='shots';tab='frames';browsing=false;S.collectionOpen=true;Studio.syncPanels();persist();renderCollection();}toast('关键画面已保存，可在右侧回看。');}
 function sync(){const v=$('#video'),range=playbackBounds();if(!v||S.mediaLoading)return;
  if(range&&!v.paused){if(v.currentTime<range.start-.00001)v.currentTime=range.start;
   else if(ClipLogic.atEnd(range,v.currentTime,S.p.fps)){if(loop)v.currentTime=range.start;else{v.pause();v.currentTime=ClipLogic.limit(range,range.end,S.p.fps);if(audition){audition=null;ClipTimeline.paint();}}}
  }ClipMixer.sync();
 }
 function attach(){const v=$('#video');if(v===attachedVideo)return;stopSound();attachedVideo=v;if(!v)return;
 ['pause','play','seeked','seeking','ratechange','volumechange','ended'].forEach(event=>v.addEventListener(event,()=>{const range=playbackBounds();if(event==='ended'&&range&&loop){v.currentTime=range.start;v.play().catch(reportPlaybackError)}sync()}));ClipMixer.attach(v);paintToolbar();}
 function toggleMute(){const v=$('#video');if(!v)return;return ClipMixer.toggleMaster();}
 function beforePlay(){const range=playbackBounds(),v=$('#video');if(range&&v?.paused&&(v.currentTime<range.start||v.currentTime>=range.end-1.1/S.p.fps))v.currentTime=range.start;}
 async function act(action,el){const d=el.dataset,m=S.modal,c=active();switch(action){
 case 'split-picture':await splitPicture();break;
 case 'open-merge':await openMerge();break;
 case 'undo-picture':{const op=S.p.storyboard_history?.at(-1);if(op){await editPicture('undo',{operation_id:op.id});toast('已撤销分镜调整');}break;}
 case 'choose':choose(d.id);break;
 case 'back':browse();break;case 'exit':browsing=false;exit();break;
 case 'tab':showTab(d.tab);break;
 case 'details':browsing=false;S.collection='shots';S.collectionOpen=true;$('.collection')?.classList.add('open');renderCollection();Studio.syncPanels();break;
 case 'timeline':S.collectionOpen=true;$('.collection')?.classList.remove('open');renderTracks();$('.clip-track-seek')?.focus();break;
 case 'capture':await capture();break;
 case 'edit':openEdit();break;
 case 'save-edit':{if(Number($('#clip-start').value)!==c.start||Number($('#clip-end').value)!==c.end)ClipMixer.assertEditable();const result=await request('edit',{id:m.id,expected_revision:m.expected_revision,title:$('#clip-title').value.trim(),start:Number($('#clip-start').value),end:Number($('#clip-end').value)},m.projectId);if(S.modal===m)closeModal();if(S.p.id===m.projectId)choose(result.clip_id);toast('片段已更新；已有文件保留。');break;}
 case 'note':openNote(d.note);break;
 case 'save-note':{await request('note',{...m,text:$('#clip-note').value},m.projectId);writeSetting(draftKey(m),null);if(S.modal===m)closeModal();toast('笔记已保存');break;}
 case 'seek':locate(Number(d.time));break;
 case 'play':togglePlay();break;
 case 'loop':if(playbackBounds()){loop=!loop;if(!audition)persist();ClipTimeline.paint();}break;
 case 'track-control':ClipMixer.control(d.kind,d.control);break;
 case 'separate':case 'original':case 'cancel':await request(action,currentBody());break;
 case 'reveal':await request('reveal',{id:d.clip,file_id:d.file});break;
 case 'delete':ClipMixer.assertEditable();S.modal={type:'clip-delete',projectId:S.p.id,...currentBody()};showModal('移除分镜',`<p>从分镜列表移除“${esc(c.title)}”。原视频和已存文件保留，可立即撤销。</p>`,button('取消','close-dialog')+cb('确认移除','confirm-delete','','primary'));break;
 case 'confirm-delete':{ClipMixer.assertEditable();const result=await request('delete',m,m.projectId);if(S.modal===m)closeModal();exit();toast('片段已移除',async()=>{const item=result.project.research_clips.find(c=>c.id===m.id);await request('restore',{id:m.id,expected_revision:item.revision},m.projectId)});break;}
 case 'remove-frame':case 'remove-note':await request(action,{...currentBody(),item_id:d.item});toast('记录已移除，来源文件仍保留。');break;
 }}
 document.addEventListener('click',e=>{const el=e.target.closest('[data-clip-action]');if(!el||el.disabled)return;const action=el.dataset.clipAction;if(!['split-picture','merge-picture','undo-picture','save-edit','capture','save-note','separate','original','cancel','confirm-delete','remove-frame','remove-note'].includes(action)){act(action,el).catch(modalError);return;}guard.run((S.p?.id||'')+':'+action,async()=>{el.disabled=true;try{await act(action,el)}catch(error){modalError(error)}finally{el.disabled=false}},450)});
 document.addEventListener('input',e=>{if(e.target.id==='clip-note'&&S.modal?.type==='clip-note')writeSetting(draftKey(S.modal),e.target.value)});
 window.addEventListener('pagehide',()=>{persist();stopSound()});
 return {cardAction:async(id,action)=>{choose(id);if(action!=='open')await act(action,{dataset:{}});},playbackBounds,startAudition,clearAudition,isAuditioning,active,choose,browse,chooseShot,isEditing:()=>editingTimeline,showTab,restore,reset,limit,locate,toolbar,paintToolbar,render,capture,openNote,attach,sync,beforePlay,stopSound,toggleMute,isLoop:()=>loop};
})();
