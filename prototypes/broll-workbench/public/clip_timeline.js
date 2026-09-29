'use strict';
// Three aligned source-linked tracks. Rendering never changes the saved media.
const ClipTimeline=(()=>{
 Object.assign(symbols,{
  monitor:'M3 5h18v14H3zM10 9l5 3-5 3V9',
  person:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
  locked:'M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4M12 14v3',
  unlocked:'M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0M12 14v3',
  eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  eyeoff:'M3 3l18 18M4 7c-1 2-2 5-2 5s4 7 10 7c2 0 4-1 5-2M9 5c1 0 2 0 3 0 6 0 10 7 10 7s-1 2-3 4M10 10a3 3 0 0 0 4 4',
  volumeoff:'M3 9h4l5-4v14l-5-4H3V9M16 9l6 6m0-6-6 6',
  magnet:'M5 3v10a7 7 0 0 0 14 0V3h-5v10a2 2 0 0 1-4 0V3H5M5 7h5m4 0h5',
  scissors:'M9 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0M9 17a3 3 0 1 1-6 0 3 3 0 0 1 6 0M8 9l13 12M8 15 21 3',
  join:'M3 7h6v10H3zM15 7h6v10h-6zM9 12h6',
  splitAudio:'M4 5h5v14H4zM15 3v18M20 7v10',
 });
 const tracks=[['original','画面与原声'],['vocals','人声'],['background','背景声']];
 const cache=new Map();let owner=null,zoom=1,manualUntil=0,textVisible=true,textActive=null,mergeMode=false,selectedPictures=[];
 const key=c=>JSON.stringify([S.p.id,c.id,c.start,c.end,Object.values(c.sound?.files||{}).map(f=>f.id)]);
 const range=()=>({start:0,end:S.p.duration});
 const boundaryCandidates=kind=>{const spans=kind==='frame'?S.p.shots:[...ClipMixer.regions(),...MusicSections.sections()];const label=kind==='frame'?'镜头边界':'声音边界',points=[];for(const span of spans||[])for(const time of [span.start,span.end])if(Number.isFinite(time))points.push({time,label});return [...new Map(points.map(point=>[point.time,point])).values()];};
 const maxZoom=()=>Math.max(12,Math.min(240,S.p.duration/2));
 const tool=(title,action,glyph,attrs='')=>`<button class="track-tool" data-clip-action="${action}" title="${esc(title)}" aria-label="${esc(title)}" ${attrs}>${icon(glyph)}</button>`;
 const controlTool=(title,action,glyph)=>`<button class="track-tool" data-timeline-action="${action}" title="${title}" aria-label="${title}">${icon(glyph)}</button>`;
 function controls(kind,title){return (kind==='background'?`<button class="background-sections-open" data-collection="music" title="音乐分段与识曲" aria-label="音乐分段与识曲">${icon('music')}</button>`:'')+`<span class="track-type" title="${title}" role="img" aria-label="${title}">${icon({original:'monitor',vocals:'person',background:'volume'}[kind])}</span>`+['locked','hidden','muted','solo'].map(control=>`<button class="track-control" data-clip-action="track-control" data-kind="${kind}" data-control="${control}" aria-label="${title} ${control}" title="${title}" aria-pressed="false">${control==='solo'?'S':icon({locked:'unlocked',hidden:'eye',muted:'volume'}[control])}</button>`).join('');}
 const wave=(samples,duration=S.p.duration)=>GainLogic.wave(samples,Math.max(1,($('.clip-track-content')?.clientWidth||1000)*duration/S.p.duration/2.5));
 function analysisTools(){const p=S.p;
  return [['scenes','画面切分','film',p.status,!!p.analysis||p.shots.length>1,p.progress,p.message],['transcript','转文字','captions',p.transcript?.status,p.transcript?.status==='ready',p.transcript?.progress,p.transcript?.message],['music','音乐分段','music',p.music_sections?.status,p.music_sections?.status==='ready',null,p.music_sections?.message]].map(([key,label,glyph,status,done,progress,message])=>{
   const busy=['processing','queued','waiting_audio'].includes(status),failed=status==='error',silent=key!=='scenes'&&!p.has_audio;
   const hint=silent?'这个视频没有声音':busy?(message||'正在处理…'):failed?(message||'处理未完成')+' · 点击重试':done?'已完成 · 点击查看':key==='music'?'准备背景声并查找音乐变化，不区分音乐与音效':key==='scenes'?'按镜头变化切分画面':'将说话内容转成文字';
   const text=busy?(key==='scenes'?'切分中':key==='transcript'?'转写中':status==='waiting_audio'?'准备声音':'分段中')+(Number.isFinite(progress)?' '+Math.round(progress*100)+'%':''):label;
   return `<button class="analysis-tool ${done?'done':''} ${failed?'failed':''}" data-action="prepare-${key}" aria-label="${label}" title="${esc(hint)}" aria-busy="${busy}" ${busy||silent?'disabled':''}>${icon(busy?'refresh':glyph)}<span>${text}</span>${failed?'<i aria-label="未完成">!</i>':''}</button>`;
  }).join('');
 }
 function render(el){if(!S.p)return;const p=S.p,c=Clips.active();
  if(owner!==p.id){mergeMode=false;selectedPictures=[];owner=p.id;zoom=Math.max(1,Math.min(maxZoom(),S.zoom||1));el.dataset.trackKey='';textVisible=readSetting('text-track-visible:'+p.id,true)!==false;}
  const signature=JSON.stringify([p.id,p.music_sections,p.source_audio?.sound,p.shots.map(s=>s.id),S.previews.map(s=>s.url),p.research_clips?.filter(c=>!c.deleted).map(c=>[key(c),c.sound?.status]),c?.id,S.snap,p.has_audio,p.transcript?.status,p.transcript?.segments]);
  if(el.dataset.trackKey===signature){drawWaves();paint();return;}
  el.dataset.trackKey=signature;textActive=null;const oldScroll=el.querySelector('.clip-track-scroll')?.scrollLeft||0;
  const busy=['queued','processing'].includes(c?.sound?.status),ready=!!c?.sound?.files?.vocals;
  const pictures=p.shots.length>1||p.analysis?p.shots:S.previews.map((s,i,all)=>({...s,start:i*p.duration/all.length,end:(i+1)*p.duration/all.length,thumbnail_url:s.url}));
  const thumbnails=ClipLogic.shotSpans(range(),pictures).map(s=>`<div class="clip-film-frame" data-picture-id="${esc(s.id||'')}" style="left:${s.left*100}%;width:${s.width*100}%"><img src="${esc(safeLocalUrl(s.thumbnail_url))}" alt="" loading="lazy"></div>`).join('');
  const words=ClipLogic.shotSpans(range(),(p.transcript?.segments||[]).map((s,index)=>({...s,index})).filter(s=>Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.end>s.start));
  const textLane=`<div class="clip-track-lane text" data-track="text" aria-label="文字轨道">${words.map(s=>`<button class="source-text-block" data-timeline-text="${s.index}" data-start="${esc(s.start)}" data-end="${esc(s.end)}" style="left:${s.left*100}%;width:calc(${s.width*100}% - 3px)" aria-label="字幕 ${clock(s.start)} · ${esc(s.text)}" title="${clock(s.start)}—${clock(s.end)} · ${esc(s.text)} · 双击修改文字"><span>${esc(s.text)}</span></button>`).join('')||`<button class="text-track-empty" data-action="expand-audio">${p.transcript?.status==='processing'?'正在识别字幕…':p.transcript?.status==='ready'?'未识别到文字 · 查看字幕':'暂无文字 · 点击上方转文字'}</button>`}</div>`;
  const textLabel=`<div class="clip-track-label text"><span class="track-type text-type" role="img" aria-label="文字">T</span><button class="text-track-title" data-action="expand-audio" title="查看完整字幕">文字</button><button class="track-control" data-timeline-action="text-visibility" aria-label="隐藏文字轨道内容" title="隐藏轨道文字，不影响原视频" aria-pressed="false">${icon('eye')}</button></div>`;
  el.innerHTML=`<div class="clip-tracks-head"><button class="timeline-story" data-action="expand-frames" aria-label="查看分镜，保留声音轨道">${icon('film')}<span>分镜 <small>${p.analysis||p.shots.length>1?p.shots.length+' 镜头':'未切分'}</small></span></button><div class="analysis-tools" role="group" aria-label="按需分析">${analysisTools()}</div><span class="spacer"></span><button class="track-tool ${S.snap?'active':''}" data-action="toggle-snap" title="边界吸附 · Alt 临时关闭" aria-label="边界吸附" aria-pressed="${S.snap}">${icon('magnet')}</button><label class="clip-track-zoom" title="时间线缩放"><input id="clip-track-zoom" type="range" min="1" max="${maxZoom()}" step=".25" value="${zoom}" aria-label="时间线缩放"></label>${controlTool('显示整条时间线','fit','expand')}${c?controlTool('放大选中分镜','focus','search'):''}${tool('循环播放当前片段','loop','loop','id="clip-track-loop"')}${tool('在当前画面切开分镜','split-picture','scissors','id="split-picture-button"')}${tool('合并相邻分镜','open-merge','join','id="merge-picture-button"')}${tool('撤销分镜调整','undo-picture','back','id="undo-picture-button"')}${c&&p.has_audio&&!ready?tool(busy?'取消分离':'分离选中分镜的人声与背景声',busy?'cancel':'separate',busy?'close':'splitAudio'):''}</div>
   <div class="clip-track-grid"><div class="clip-track-labels"><div class="clip-ruler-label"><time id="source-timecode" aria-label="当前时间（分：秒：帧）" title="当前时间 · 分:秒:帧"></time></div>${textLabel}${tracks.map(([kind,title])=>`<div class="clip-track-label ${kind}" data-track-label="${kind}">${controls(kind,title)}</div>`).join('')}</div>
   <div class="clip-track-scroll"><div class="clip-track-content" style="width:${zoom*100}%"><div class="clip-track-ruler" aria-hidden="true"></div>${textLane}${tracks.map(([kind,title])=>`<div class="clip-track-lane ${kind}" data-track="${kind}">${kind==='original'?`<div class="clip-filmstrip ${p.analysis||p.shots.length>1?'':'unsplit'}">${thumbnails}</div><svg class="clip-track-wave" viewBox="0 0 1000 50" preserveAspectRatio="none" role="img" aria-label="原片真实波形"><path></path></svg>`:'<div class="source-sound-regions"></div>'}<span class="clip-track-empty"></span>${kind==='original'?noteMarkers('frame'):kind==='background'?noteMarkers('audio'):''}<div class="track-gain-area"><div class="track-gain-zero" aria-hidden="true"></div><div class="track-gain-line" data-track-gain="${kind}" role="slider" tabindex="0" aria-label="${title}音量增益" aria-orientation="vertical" aria-valuemin="-60" aria-valuemax="12" title="上下拖动调整音量 · 双击恢复 0 dB · 方向键微调"><span class="track-gain-value">0 dB</span></div></div><input class="clip-track-seek" type="range" min="0" max="${ClipLogic.limit(range(),p.duration,p.fps)}" step="${1/p.fps}" value="${S.position}" aria-label="${title}时间定位"></div>`).join('')}<i class="clip-playback-range" hidden></i><i class="clip-playhead" aria-hidden="true"><svg class="playhead-marker" viewBox="0 0 14 22"><path d="M3 1H11V13L7 18L3 13Z"/></svg></i></div></div></div>
   <div class="clip-tracks-foot"><span id="playback-bound-status"></span><span id="clip-track-feedback"></span><span id="source-audio-status" role="status"></span><span class="spacer"></span><span id="clip-track-audible" role="status"></span></div>`;
  $('.clip-track-scroll',el).scrollLeft=oldScroll;bind(el);drawWaves();load();paint();
 }
 async function load(force=false){if(!S.p?.has_audio)return;const project=S.p.id;
  const clips=[...new Map(ClipMixer.regions().map(r=>[r.clip.id,r.clip])).values()];
  await Promise.allSettled(clips.map(async c=>{const id=key(c);if(!force&&cache.has(id))return;cache.set(id,{status:'loading'});
   try{const data=await api(url(project,`/research/${c.id}/waveforms`));cache.set(id,{status:'ready',data});}
   catch(error){cache.set(id,{status:'error',message:error.message});}
  }));if(S.p?.id===project){drawWaves();if(clips.some(c=>cache.get(key(c))?.status==='error'))$('#clip-track-feedback').innerHTML='波形读取失败 <button data-track-retry>重试</button>';}
 }
 function drawWaves(){if(!S.p||!$('#timeline')?.classList.contains('clip-timeline'))return;const regions=ClipMixer.regions();
  const sound=S.p.source_audio?.sound,status=$('#source-audio-status');if(status){const busy=['queued','processing'].includes(sound?.status),failed=['error','cancelled'].includes(sound?.status);status.innerHTML=busy?'整片声音处理中…':failed?'<button data-action="retry-source-audio">声音未完成 · 重试</button>':sound?.status==='ready'?'背景声含音乐与音效':'';status.title=sound?.message||'';}
  for(const [kind] of tracks){const lane=$(`[data-track="${kind}"]`);if(!lane)continue;const message=$('.clip-track-empty',lane);let text='';
   if(kind==='original'){$('path',lane).setAttribute('d',wave(S.wave?.samples));if(!S.p.has_audio)text='原片没有声音';}
   else{let available=regions.filter(r=>r.clip.sound.files[kind]);if(kind==='background'&&MusicSections.sections().length)available=available.flatMap(r=>MusicSections.sections().filter(s=>s.end>r.start&&s.start<r.end).map(s=>({...r,start:Math.max(r.start,s.start),end:Math.min(r.end,s.end)})));$('.source-sound-regions',lane).innerHTML=available.map(r=>{const state=cache.get(key(r.clip)),samples=state?.data?.tracks?.[kind]?.samples;
     const offset=(r.start-r.clip.start)/(r.clip.end-r.clip.start)*1000,width=(r.end-r.start)/(r.clip.end-r.clip.start)*1000;
     return `<div class="source-sound-region" data-region-clip="${esc(r.clip.id)}" style="left:${r.start/S.p.duration*100}%;width:calc(${(r.end-r.start)/S.p.duration*100}% - ${kind==='background'?4:0}px)" title="${esc(r.clip.title)} · ${clock(r.start)}—${clock(r.end)}"><svg class="clip-track-wave" viewBox="${offset} 0 ${width} 50" preserveAspectRatio="none" role="img" aria-label="${esc(r.clip.title)} · ${kind==='vocals'?'人声':'背景声'}真实波形"><path d="${wave(samples,r.clip.end-r.clip.start)}"></path></svg>${!samples?`<span class="region-loading">${state?.status==='error'?'读取失败':'读取中'}</span>`:''}</div>`;
    }).join('')+(kind==='background'?MusicSections.labels():'');if(!available.length)text=S.p.has_audio?(['queued','processing'].includes(S.p.source_audio?.sound?.status)?'整片声音处理中…':S.p.source_audio?.sound?.status==='error'?'声音处理失败 · 点击下方重试':'点击上方「音乐分段」准备声音'):'原片没有声音';}
   message.textContent=text;message.hidden=!text;lane.classList.toggle('empty',!!text);
  }
 }
 function rulers(){const ruler=$('.clip-track-ruler'),scroll=$('.clip-track-scroll');if(!S.p||!ruler||!scroll)return;const duration=S.p.duration,width=ruler.clientWidth;
  const step=ClipLogic.rulerStep(duration,width);
  const divisions=step*width/duration>=90?10:5,interval=step/divisions;
  const first=Math.max(0,Math.floor(scroll.scrollLeft/width*duration/step)-1)*divisions;
  const last=Math.min(Math.ceil(duration/interval),Math.ceil((scroll.scrollLeft+scroll.clientWidth)/width*duration/step+1)*divisions);
  const signature=[first,last,step,divisions].join(':');if(ruler.dataset.ticks===signature)return;ruler.dataset.ticks=signature;
  const ticks=[];for(let i=first;i<=last;i++){const t=i*interval;if(t>duration)break;const major=i%divisions===0;ticks.push(major?`<span class="ruler-second" style="left:${t/duration*100}%">${ClipLogic.rulerLabel(t)}</span>`:`<i class="ruler-tick ${i%divisions===divisions/2?'mid':''}" style="left:${t/duration*100}%"></i>`);}ruler.innerHTML=ticks.join('');
 }
 function paint(){MusicSections.paint();const tools=$('.analysis-tools');if(S.p&&tools){const html=analysisTools();if(tools.dataset.content!==html){tools.innerHTML=html;tools.dataset.content=html;}}const el=$('#timeline');if(!S.p||!el?.classList.contains('clip-timeline'))return;const settings=ClipMixer.state(),heard=ClipMixer.audible(),v=$('#video');
  const ratio=S.position/S.p.duration,head=$('.clip-playhead');if(head)head.style.left=`${ratio*100}%`;
  const timecode=$('#source-timecode');if(timecode){const nominal=Math.max(1,Math.round(S.p.fps)),frame=Math.max(0,Math.round(S.position*S.p.fps)),seconds=Math.floor(frame/nominal);timecode.textContent=[Math.floor(seconds/60),seconds%60,frame%nominal].map(n=>String(n).padStart(2,'0')).join(':');}
  $$('.clip-track-seek').forEach(input=>{if(!S.dragging)input.value=S.position});
  const textLane=$('[data-track="text"]'),visibility=$('[data-timeline-action="text-visibility"]');
  if(textLane)textLane.classList.toggle('text-hidden',!textVisible);
  if(visibility){visibility.setAttribute('aria-pressed',String(!textVisible));visibility.setAttribute('aria-label',textVisible?'隐藏文字轨道内容':'显示文字轨道内容');visibility.title=(textVisible?'隐藏':'显示')+'轨道文字，不影响原视频';const glyph=textVisible?'eye':'eyeoff';if(visibility.dataset.glyph!==glyph){visibility.innerHTML=icon(glyph);visibility.dataset.glyph=glyph;}}
  const currentText=(S.p.transcript?.segments||[]).findIndex(s=>S.position+.00001>=s.start&&S.position+.00001<s.end);
  if(currentText!==textActive){textActive=currentText;$$('[data-timeline-text]').forEach(b=>{const on=Number(b.dataset.timelineText)===currentText;b.classList.toggle('active',on);b.setAttribute('aria-current',String(on));});}

  for(const [kind,title] of tracks){const label=$(`[data-track-label="${kind}"]`),lane=$(`[data-track="${kind}"]`),state=settings.tracks[kind];if(!label)continue;
   const gain=$('[data-track-gain]',lane);if(gain){const value=state.gainDb,disabled=state.locked||!ClipMixer.existing().includes(kind);gain.style.top=(GainLogic.position(value)*100)+'%';gain.setAttribute('aria-valuenow',value);gain.setAttribute('aria-valuetext',GainLogic.label(value));gain.setAttribute('aria-disabled',String(disabled));gain.tabIndex=disabled?-1:0;gain.hidden=!ClipMixer.existing().includes(kind);const badge=$('.track-gain-value',gain);badge.textContent=GainLogic.label(value);badge.style.transform=`translateX(${$('.clip-track-scroll')?.scrollLeft||0}px)`;gain.closest('.track-gain-area').classList.toggle('gain-adjusted',value!==0);}
   label.classList.toggle('selected',settings.solo===kind);lane?.classList.toggle('selected',settings.solo===kind);lane?.classList.toggle('track-hidden',state.hidden);lane?.classList.toggle('track-locked',state.locked);lane?.classList.toggle('track-muted',state.muted);
   for(const b of $$('.track-control',label)){const control=b.dataset.control,suppressed=kind==='original'&&TrackLogic.originalSuppressed(settings,ClipMixer.available()),on=control==='solo'?settings.solo===kind:control==='muted'&&suppressed?true:state[control];
    const glyph=control==='solo'?'solo':{locked:on?'locked':'unlocked',hidden:on?'eyeoff':'eye',muted:on?'volumeoff':'volume'}[control];
    if(b.dataset.glyph!==glyph){b.innerHTML=glyph==='solo'?'S':icon(glyph);b.dataset.glyph=glyph;}
    const text=title+' · '+{locked:on?'解锁':'锁定',hidden:on?'显示':'隐藏',muted:suppressed?'切回原声试听（分轨将停止）':on?'取消静音':'静音',solo:on?'取消单独播放':'单独播放'}[control];
    b.title=text+(control==='hidden'?'（声音不变）':'');b.setAttribute('aria-label',text);b.setAttribute('aria-pressed',String(on));b.classList.toggle('active',on);b.disabled=['muted','solo'].includes(control)&&!ClipMixer.existing().includes(kind);
   }
  }
  const audible=$('#clip-track-audible');if(audible)audible.textContent=heard.length?'试听：'+tracks.filter(t=>heard.includes(t[0])).map(t=>t[1]).join('、'):settings.solo&&settings.solo!=='original'&&!ClipMixer.source()?'当前位置未分轨':'静音';
  const master=$('[data-action="mute"]');if(master){const muted=ClipMixer.masterMuted();master.classList.toggle('active',muted);master.setAttribute('aria-label',muted?'取消总静音':'总静音');master.title=muted?'取消总静音':'总静音';const glyph=muted?'volumeoff':'volume';if(master.dataset.glyph!==glyph){master.innerHTML=icon(glyph);master.dataset.glyph=glyph;}}
  const bounded=Clips.playbackBounds(),status=$('#playback-bound-status'),split=$('#split-picture-button');if(status)status.textContent=bounded?`${Clips.isAuditioning()?'本段试听':'分镜播放'} ${clock(bounded.start)}—${clock(bounded.end)} · ${Clips.isLoop()?'循环':'到结尾停止'}`:'';if(split)split.disabled=Clips.isEditing()||S.p.status==='processing'||ClipMixer.state().tracks.original.locked;const merge=$('#merge-picture-button'),undo=$('#undo-picture-button');if(merge){merge.disabled=split?.disabled||S.p.shots.length<2;merge.classList.toggle('active',mergeMode);merge.setAttribute('aria-pressed',String(mergeMode));merge.title=mergeMode?'选中相邻两段后，点击合并':'合并相邻分镜';}paintMerge();if(undo)undo.disabled=split?.disabled||!S.p.storyboard_history?.length;
  const loop=$('#clip-track-loop');if(loop){loop.disabled=!bounded;loop.classList.toggle('active',Clips.isLoop());loop.setAttribute('aria-pressed',String(Clips.isLoop()));}
  const playback=$('.clip-playback-range');if(playback){playback.hidden=!bounded;if(bounded){playback.style.left=`${bounded.start/S.p.duration*100}%`;playback.style.width=`${Math.max(0,bounded.end-bounded.start)/S.p.duration*100}%`;}}
  const scroll=$('.clip-track-scroll');if(scroll&&(!v?.paused||S.forceFollow)&&performance.now()>manualUntil){const x=ratio*scroll.scrollWidth;if(x<scroll.scrollLeft||x>scroll.scrollLeft+scroll.clientWidth)scroll.scrollLeft=Math.max(0,x-scroll.clientWidth*.35);}
 }
 function mergeSelection(){return S.p.shots.filter(s=>selectedPictures.includes(s.id)).map(s=>s.id);}
 function paintMerge(){
  selectedPictures=mergeSelection();
  $$('.clip-film-frame').forEach(el=>el.classList.toggle('merge-selected',selectedPictures.includes(el.dataset.pictureId)));
  const feedback=$('#clip-track-feedback');if(mergeMode&&feedback)feedback.textContent=selectedPictures.length===2?'已选中两段画面 · 点击合并按钮接回 · Esc 取消':'点击要合并的两个相邻画面 · Esc 取消';
 }
 function startMerge(){if(mergeMode){clearMerge();return;}mergeMode=true;$('#video')?.pause();paint();}
 function clearMerge(){mergeMode=false;selectedPictures=[];const feedback=$('#clip-track-feedback');if(feedback)feedback.textContent='';paint();}
 function selectPicture(time){const shots=S.p.shots,shot=shots[Interaction.shotIndexAt(shots,time,S.p.fps)];if(!shot)return;
  if(selectedPictures.includes(shot.id))selectedPictures=selectedPictures.filter(id=>id!==shot.id);
  else if(selectedPictures.length===1&&Math.abs(shots.findIndex(s=>s.id===selectedPictures[0])-shots.indexOf(shot))===1)selectedPictures.push(shot.id);
  else selectedPictures=[shot.id];
  seek(time);paint();
 }
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&mergeMode){e.preventDefault();e.stopImmediatePropagation();clearMerge();}},true);
 function bindGains(el){for(const line of $$('[data-track-gain]',el)){
  const kind=line.dataset.trackGain,change=(db,persist=true)=>{try{return ClipMixer.setGain(kind,db,{persist});}catch(e){toast(e.message);return false;}};
  line.addEventListener('pointerdown',event=>{if(event.button!==0||S.dragging||line.getAttribute('aria-disabled')==='true')return;event.preventDefault();event.stopPropagation();line.focus();line.setPointerCapture(event.pointerId);S.dragging=true;const start=ClipMixer.state().tracks[kind].gainDb,rect=line.parentElement.getBoundingClientRect(),initial=GainLogic.position(start);line.classList.add('dragging');
   const move=e=>{if(e.pointerId===event.pointerId)change(GainLogic.fromPosition(initial+(e.clientY-event.clientY)/Math.max(1,rect.height)),false);};
   const finish=e=>{if(e.pointerId!==event.pointerId)return;line.removeEventListener('pointermove',move);line.removeEventListener('pointerup',finish);line.removeEventListener('pointercancel',finish);line.removeEventListener('lostpointercapture',finish);S.dragging=false;line.classList.remove('dragging');change(e.type==='pointercancel'?start:ClipMixer.state().tracks[kind].gainDb);};
   line.addEventListener('pointermove',move);line.addEventListener('pointerup',finish);line.addEventListener('pointercancel',finish);line.addEventListener('lostpointercapture',finish);
  });
  line.addEventListener('dblclick',e=>{e.preventDefault();e.stopPropagation();change(0);});
  line.addEventListener('keydown',e=>{e.stopPropagation();const db=ClipMixer.state().tracks[kind].gainDb,step=e.shiftKey?.1:1;let value;if(e.key==='ArrowUp'||e.key==='ArrowRight')value=db+step;else if(e.key==='ArrowDown'||e.key==='ArrowLeft')value=db-step;else if(e.key==='Home')value=0;else if(e.key==='End')value=GainLogic.minDb;else return;e.preventDefault();change(value);});
 }}
 function point(event,lane){const r=lane.getBoundingClientRect();return ClipLogic.point(range(),(event.clientX-r.left)/r.width,{fps:S.p.fps,pixelWidth:r.width,snap:S.snap,bypass:event.altKey,candidates:boundaryCandidates(lane.dataset.track==='original'?'frame':'audio')});}
 function bind(el){bindGains(el);const scroll=$('.clip-track-scroll',el);scroll.addEventListener('scroll',()=>{rulers();MusicSections.paint();$$('.track-gain-value',el).forEach(b=>b.style.transform=`translateX(${scroll.scrollLeft}px)`);},{passive:true});scroll.addEventListener('wheel',e=>{manualUntil=performance.now()+3000;if(e.ctrlKey){e.preventDefault();applyZoom(zoom*Math.exp(-e.deltaY*.01));}else if(Math.abs(e.deltaY)>Math.abs(e.deltaX)){e.preventDefault();scroll.scrollLeft+=e.deltaY;}},{passive:false});
  for(const lane of $$('.clip-track-lane',el)){const input=$('.clip-track-seek',lane);if(!input)continue;
   input.addEventListener('pointerdown',event=>{if(event.button!==0||S.dragging)return;const picture=lane.dataset.track==='original';if(Clips.isEditing())return;
    event.preventDefault();input.focus();input.setPointerCapture(event.pointerId);S.dragging=true;S.activeLane=picture?'frame':'audio';$('#video')?.pause();
    const anchor=point(event,lane).time;
    if(picture&&(mergeMode||event.shiftKey)){mergeMode=true;selectPicture(anchor);S.dragging=false;input.releasePointerCapture(event.pointerId);return;}
    const move=e=>{if(e.pointerId!==event.pointerId)return;const p=point(e,lane);
     seek(p.time);input.value=p.time;$('#clip-track-feedback').textContent=`${p.snapped?'已吸附 · '+p.label+' · ':''}${clock(p.time)}`;};
    const end=e=>{if(e.pointerId!==event.pointerId)return;S.dragging=false;input.removeEventListener('pointermove',move);input.removeEventListener('pointerup',end);input.removeEventListener('pointercancel',end);
     $('#clip-track-feedback').textContent='';if(picture&&e.type!=='pointercancel'){const shot=S.p.shots[Interaction.shotIndexAt(S.p.shots,S.position,S.p.fps)];selectedPictures=shot?[shot.id]:[];if(shot)CollectionLink.reveal('shots',shot.id);}paint();};
    input.addEventListener('pointermove',move);input.addEventListener('pointerup',end);input.addEventListener('pointercancel',end);move(event);
   });input.addEventListener('input',()=>{S.activeLane=lane.dataset.track==='original'?'frame':'audio';seek(Number(input.value));if(lane.dataset.track==='original'){const shot=S.p.shots[Interaction.shotIndexAt(S.p.shots,S.position,S.p.fps)];if(shot)CollectionLink.reveal('shots',shot.id);}});
  }
  $('#clip-track-zoom',el).addEventListener('input',e=>applyZoom(Number(e.target.value)));
  el.addEventListener('click',handleClick);S.rulerObserver?.disconnect();S.rulerObserver=new ResizeObserver(rulers);S.rulerObserver.observe($('.clip-track-content',el));rulers();
 }
 function handleClick(e){const text=e.target.closest('[data-timeline-text]');if(text){const fps=S.p.fps||30;seek(Math.ceil(Number(text.dataset.start)*fps-1e-7)/fps);CollectionLink.reveal('transcript',Number(text.dataset.timelineText));return;}const action=e.target.closest('[data-timeline-action]')?.dataset.timelineAction;if(action==='text-visibility'){textVisible=!textVisible;writeSetting('text-track-visible:'+S.p.id,textVisible);paint();}if(action==='fit')applyZoom(1);if(action==='focus'&&Clips.active()){const c=Clips.active();applyZoom(S.p.duration/((c.end-c.start)*1.25));$('.clip-track-scroll').scrollLeft=Math.max(0,(c.start-(c.end-c.start)*.1)/S.p.duration*$('.clip-track-scroll').scrollWidth);}if(e.target.closest('[data-track-retry]'))load(true);}
 function applyZoom(value){const scroll=$('.clip-track-scroll'),content=$('.clip-track-content');if(!S.p||!scroll||!content)return;
  const oldWidth=scroll.scrollWidth,oldScroll=scroll.scrollLeft;zoom=Math.max(1,Math.min(maxZoom(),value));S.zoom=zoom;writeSetting('zoom:'+S.p.id,zoom);content.style.width=`${zoom*100}%`;
  scroll.scrollLeft=Interaction.zoomScroll({oldWidth,newWidth:scroll.scrollWidth,scrollLeft:oldScroll,viewport:scroll.clientWidth,anchorTime:S.position,duration:S.p.duration});$('#clip-track-zoom').value=zoom;rulers();drawWaves();paint();
 }
 return {render,paint,startMerge,clearMerge,mergeSelection};
})();
