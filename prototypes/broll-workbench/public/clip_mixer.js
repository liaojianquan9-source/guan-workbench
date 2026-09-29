'use strict';
// Transport follows the source video. Track switches only change monitoring and view state.
const ClipMixer=(()=>{
 let owner=null,settings=null,video=null,enabled=false,masterMuted=false,syncing=false;
 const channels={},titles={original:'画面与原声',vocals:'人声',background:'背景声'};
 function regions(){return ClipLogic.soundRegions([...(S.p?.source_audio?[S.p.source_audio]:[]),...(S.p?.research_clips||[])],Clips.active()?.id);}
 // Media seeks can land a few microseconds before the requested frame timestamp.
 function source(){return ClipLogic.soundAt(regions(),(video?.currentTime??S.position)+.00001);}
 function state(){if(!S.p)return TrackLogic.normalize();const id=S.p.id;
  if(owner!==id){owner=id;settings=TrackLogic.normalize(readSetting('source-tracks:'+id,null));}return settings;
 }
 function available(){const c=source();return !S.p?.has_audio?[]:['original',...['vocals','background'].filter(k=>safeLocalUrl(c?.sound?.files?.[k]?.url)&&(!channels[k]?.error||channels[k]?.url!==safeLocalUrl(c.sound.files[k].url)))];}
 function existing(){return !S.p?.has_audio?[]:['original',...['vocals','background'].filter(k=>regions().some(r=>safeLocalUrl(r.clip.sound.files[k]?.url)))];}
 function audible(){return TrackLogic.audible(state(),available(),masterMuted);}
 function ensureChannel(kind,file){let channel=channels[kind];
  if(!channel){const audio=$('#clip-'+kind);channel=channels[kind]={audio,url:null,error:false,pending:false};
   audio.addEventListener('loadedmetadata',sync);audio.addEventListener('canplay',sync);
   audio.addEventListener('error',()=>{if(!enabled||!channel.url)return;channel.error=true;audio.pause();toast(titles[kind]+'音轨读取失败，请重新打开片段。');sync();ClipTimeline.paint();});}
  const source=safeLocalUrl(file?.url);if(channel.url!==source){channel.audio.pause();channel.url=source||null;channel.error=false;
   if(source){channel.audio.src=source;channel.audio.load();}else{channel.audio.removeAttribute('src');channel.audio.load();}}
  return channel;
 }
 function sync(){if(syncing||!enabled||!video||!S.p)return;const c=source();syncing=true;
  try{const settings=state();for(const kind of ['vocals','background'])ensureChannel(kind,c?.sound?.files?.[kind]);
   const heard=audible();video.muted=!heard.includes('original');AudioGain.apply(video,settings.tracks.original.gainDb,heard.includes('original'));
   $('.player-stage')?.classList.toggle('clip-picture-hidden',settings.tracks.original.hidden);
   for(const kind of ['vocals','background']){const channel=channels[kind],a=channel.audio,wanted=heard.includes(kind),relative=c?ClipLogic.relative(c,video.currentTime):0;
    a.volume=video.volume;a.playbackRate=video.playbackRate;a.muted=!wanted;AudioGain.apply(a,settings.tracks[kind].gainDb,wanted);
    if(a.readyState>=1&&(wanted||video.paused)&&Math.abs(a.currentTime-relative)>((video.paused||video.seeking) ? .001 : .06))a.currentTime=relative;
    if(!wanted||video.paused||video.seeking||channel.error)a.pause();
    else if(a.paused&&a.readyState>=2&&!channel.pending){channel.pending=true;const source=channel.url;
     a.play().catch(error=>{if(error.name!=='AbortError'&&enabled&&channel.url===source){channel.error=true;toast(titles[kind]+'未能播放，请重新打开片段。');}}).finally(()=>{channel.pending=false;});}
   }
  }finally{syncing=false;}
 }
 function stop(){enabled=false;for(const channel of Object.values(channels)){channel.audio.pause();channel.error=false;channel.url=null;}
  if(video){AudioGain.release(video);video.muted=masterMuted;}$('.player-stage')?.classList.remove('clip-picture-hidden');
 }
 function attach(v){stop();video=v;masterMuted=!!v?.muted;enabled=!!S.p;sync();v?.addEventListener('play',()=>{if(video!==v)return;sync();AudioGain.resume().catch(()=>{});});}
 function activate(){enabled=true;state();sync();}
 function control(kind,control){if(!S.p)return;if(['muted','solo'].includes(control)&&!existing().includes(kind))return;
  if(kind==='original'&&control==='muted'&&TrackLogic.originalSuppressed(state(),available())){settings=TrackLogic.normalize(state());settings.solo='original';settings.tracks.original.muted=false;}
  else settings=TrackLogic.toggle(state(),kind,control);writeSetting('source-tracks:'+owner,settings);sync();Clips.paintToolbar();ClipTimeline.paint();
 }
 function setGain(kind,value,{persist=true}={}){if(!S.p||!TrackLogic.kinds.includes(kind)||state().tracks[kind].locked)return false;const db=GainLogic.clampDb(value),media=kind==='original'?video:channels[kind]?.audio;AudioGain.apply(media,db,audible().includes(kind));settings.tracks[kind].gainDb=db;if(persist)writeSetting('source-tracks:'+owner,settings);sync();AudioGain.resume().catch(()=>{});ClipTimeline.paint();return true;}
 function toggleMaster(){masterMuted=!masterMuted;sync();ClipTimeline.paint();return masterMuted;}
 function assertEditable(){const locked=TrackLogic.locked(state());if(locked.length)throw new Error(locked.map(k=>titles[k]).join('、')+'已锁定，请先解锁再修改片段范围或移除片段。');}
 return {state,available,existing,regions,source,audible,sync,stop,attach,activate,control,toggleMaster,setGain,assertEditable,masterMuted:()=>masterMuted};
})();
