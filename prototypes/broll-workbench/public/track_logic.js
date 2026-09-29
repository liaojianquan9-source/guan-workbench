(function(root){
 'use strict';
 const kinds=['original','vocals','background'];
 function normalize(saved){
  const result={solo:saved?.solo===null?null:kinds.includes(saved?.solo)?saved.solo:'original',tracks:{}};
  for(const kind of kinds){const old=saved?.tracks?.[kind];result.tracks[kind]={locked:old?.locked===true,hidden:old?.hidden===true,muted:old?.muted===true,gainDb:Number.isFinite(old?.gainDb)?Math.max(-60,Math.min(12,Math.round(old.gainDb*10)/10)):0};}
  return result;
 }
 function audible(state,available,masterMuted=false){
  if(masterMuted)return [];
  const routed=state.solo?[state.solo]:originalSuppressed(state,available)?['vocals','background']:['original'];
  return routed.filter(kind=>available.includes(kind)&&!state.tracks[kind].muted);
 }
 function originalSuppressed(state,available){return state.solo?state.solo!=='original':available.some(k=>k==='vocals'||k==='background');}
 function toggle(state,kind,control){
  const next=normalize(state);if(!kinds.includes(kind))return next;
  if(control==='solo')next.solo=next.solo===kind?null:kind;
  else if(['locked','hidden','muted'].includes(control))next.tracks[kind][control]=!next.tracks[kind][control];
  return next;
 }
 const api={kinds,normalize,audible,originalSuppressed,toggle,locked:state=>kinds.filter(kind=>state.tracks[kind].locked)};
 if(typeof module!=='undefined')module.exports=api;else root.TrackLogic=api;
})(typeof globalThis!=='undefined'?globalThis:this);
