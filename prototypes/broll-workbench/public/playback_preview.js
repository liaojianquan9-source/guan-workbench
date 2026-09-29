'use strict';
// Only the preview element changes source. Project media and analysis remain untouched.
const PlaybackPreview=(()=>{
 const labels={original:'HQ',half:'SQ',quarter:'LQ'},names={original:'原画',half:'标准',quarter:'流畅'};
 let video=null,project=null,current='original',desired='original',generation=0,timer=null,cancelSwap=null,resumeAfterLoad=false;
 const valid=q=>Object.hasOwn(labels,q)?q:'original';
 function toolbar(){return `<button class="preview-quality" id="player-quality" popovertarget="player-quality-menu" title="预览清晰度" aria-label="预览清晰度 · 原画 HQ" aria-haspopup="menu" aria-expanded="false">${icon('film')}<span id="preview-quality-label">HQ</span><span class="quality-chevron">⌄</span></button><div id="player-quality-menu" class="player-more-menu quality-menu" popover="auto" role="menu" aria-label="预览清晰度"><p>播放清晰度</p>${Object.keys(labels).map(q=>`<button role="menuitemradio" aria-checked="${q==='original'}" data-preview-quality="${q}"><b>${labels[q]}</b><span>${names[q]}</span><small>${q==='original'?'原始画质':q==='half'?'½ 分辨率':'¼ 分辨率'}</small></button>`).join('')}<p id="preview-quality-status" role="status">仅影响播放；截图、分析和导出使用原片。</p></div>`;}
 function paint(message=''){const button=$('#player-quality'),label=$('#preview-quality-label'),status=$('#preview-quality-status');if(!button)return;
  label.textContent=labels[current]+(desired!==current?'…':'');button.classList.toggle('preparing',desired!==current);button.title=(desired!==current?'正在准备'+names[desired]+'预览':'预览清晰度：'+names[current]);button.setAttribute('aria-label','预览清晰度 · '+names[current]+' '+labels[current]);
  $$('[data-preview-quality]').forEach(b=>b.setAttribute('aria-checked',String(b.dataset.previewQuality===current)));
  if(status)status.textContent=message||(desired!==current?'正在本机准备预览，可继续播放…':'仅影响播放；截图、分析和导出使用原片。');
 }
 function attach(v,p){generation++;clearTimeout(timer);cancelSwap?.();video=v;project=p;current='original';desired='original';
  const menu=$('#player-quality-menu'),trigger=$('#player-quality');if(!menu)return;
  menu.addEventListener('beforetoggle',e=>{trigger.setAttribute('aria-expanded',String(e.newState==='open'));if(e.newState==='open'){const r=trigger.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(r.right-240,innerWidth-248))+'px';menu.style.top=(r.bottom+6)+'px';}});
  menu.addEventListener('toggle',()=>{if(menu.matches(':popover-open'))menu.querySelector('[aria-checked="true"]')?.focus();});
  menu.addEventListener('click',e=>{const q=e.target.closest('[data-preview-quality]');if(q){menu.hidePopover();trigger.focus();choose(q.dataset.previewQuality);}});
  menu.addEventListener('keydown',e=>{const items=[...menu.querySelectorAll('button')],i=items.indexOf(document.activeElement);let next;if(e.key==='ArrowDown')next=(i+1)%items.length;if(e.key==='ArrowUp')next=(i+items.length-1)%items.length;if(e.key==='Home')next=0;if(e.key==='End')next=items.length-1;if(next!==undefined){e.preventDefault();e.stopPropagation();items[next].focus();}});
  const saved=valid(readSetting('preview-quality:'+p.id,'original'));if(saved!=='original')choose(saved);else paint();
 }
 function isCurrent(token,v,p){return token===generation&&v===$('#video')&&S.p?.id===p.id;}
 async function choose(raw){const quality=valid(raw),token=++generation,v=video,p=project,interrupted=!!cancelSwap;clearTimeout(timer);cancelSwap?.();desired=quality;paint();
  try{
   if(interrupted&&quality!=='original'){await activate(p.video_url,'original',token,v,p);if(!isCurrent(token,v,p))return;desired=quality;paint();}
   if(quality==='original'){await activate(p.video_url,quality,token,v,p);return;}
   const state=await api(url(p.id,'/playback'),{quality});if(!isCurrent(token,v,p))return;
   await ready(state,quality,token,v,p);
  }catch(error){await recover(error,token,v,p);}
 }
 async function recover(error,token,v,p){if(!isCurrent(token,v,p)||error.name==='AbortError')return;desired=current;paint('未能切换清晰度，可重新选择重试。');toast('低清预览暂未就绪，可重新选择重试。');
  if(S.mediaLoading){try{await activate(p.video_url,'original',token,v,p);}catch{if(isCurrent(token,v,p)){S.mediaLoading=false;S.pendingSeek=null;$('#play-button').disabled=false;paint('视频加载失败，请重新打开视频。');}}}
 }

 async function ready(state,quality,token,v,p){if(!isCurrent(token,v,p))return;
  if(state.status==='ready'){await activate(state.url,quality,token,v,p);return;}
  if(state.status==='error')throw new Error(state.message);
  paint(state.message);timer=setTimeout(async()=>{try{await ready(await api(url(p.id,'/playback')+'?quality='+quality),quality,token,v,p);}catch(error){await recover(error,token,v,p);}},1200);
 }
 async function activate(source,quality,token,v,p){if(!isCurrent(token,v,p))return;const local=safeLocalUrl(source);if(!local)throw new Error('预览地址无效');
  if(v.getAttribute('src')!==local||S.mediaLoading){await swap(local,token,v,p);}
  if(!isCurrent(token,v,p))return;current=desired=quality;writeSetting('preview-quality:'+p.id,quality);paint();
 }
 function swap(source,token,v,p){return new Promise((resolve,reject)=>{
  const time=S.mediaLoading?(S.pendingSeek??S.position):v.currentTime,playing=S.mediaLoading?resumeAfterLoad:!v.paused,rate=v.playbackRate;
  resumeAfterLoad=playing;v.pause();ClipMixer.sync();S.position=time;S.pendingSeek=time;S.mediaLoading=true;$('#play-button').disabled=true;
  let metadata=false,done=false;
  const cleanup=()=>{clearTimeout(timeout);for(const [name,fn] of events)v.removeEventListener(name,fn);if(cancelSwap===cancel)cancelSwap=null;};
  const fail=error=>{if(done)return;done=true;cleanup();if(isCurrent(token,v,p)){$('#play-button').disabled=false;}reject(error);};
  const finish=()=>{if(done||!metadata||v.seeking||v.readyState<2)return;if(!isCurrent(token,v,p)){cancel();return;}done=true;cleanup();S.mediaLoading=false;S.pendingSeek=null;S.position=v.currentTime;v.playbackRate=rate;$('#play-button').disabled=false;ClipMixer.sync();paintClock();if(playing)v.play().catch(reportPlaybackError);resolve();};
  const loaded=()=>{if(!isCurrent(token,v,p)){cancel();return;}metadata=true;v.currentTime=Interaction.frameTime(S.pendingSeek??time,p.fps,p.duration);finish();};
  const cancel=()=>fail(Object.assign(new Error('切换已取消'),{name:'AbortError'}));
  const events=[['loadedmetadata',loaded],['seeked',finish],['canplay',finish],['error',()=>fail(new Error('预览读取失败'))]];
  const timeout=setTimeout(()=>fail(new Error('预览加载超时')),15000);cancelSwap=cancel;
  for(const [name,fn] of events)v.addEventListener(name,fn);v.src=source;v.load();
 });}
 return {toolbar,attach};
})();
