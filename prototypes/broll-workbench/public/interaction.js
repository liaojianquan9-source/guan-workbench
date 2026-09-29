/* Shared time and interaction rules, also exercised with node --test. */
(function(root){
  'use strict';
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  function formatTime(value){
    const seconds=Number(value);
    const ticks=Math.round(Math.max(0,Number.isFinite(seconds)?seconds:0)*100);
    return String(Math.floor(ticks/6000)).padStart(2,'0')+':'+((ticks%6000)/100).toFixed(2).padStart(5,'0');
  }
  function frameTime(time,fps,duration,allowEnd=false){
    fps=Number(fps)||30;
    duration=Math.max(0,Number(duration)||0);
    time=clamp(Number(time)||0,0,duration);
    if(allowEnd&&time>=duration-.5/fps)return duration;
    const last=Math.max(0,Math.ceil(duration*fps-1e-4)-1);
    return clamp(Math.round(time*fps),0,last)/fps;
  }
  // Compare frame numbers so rounded cut timestamps still belong to the new shot.
  function shotIndexAt(shots,time,fps){
    fps=Number(fps)||30;
    const frame=Math.floor(Math.max(0,Number(time)||0)*fps+1e-4);
    return shots.findIndex((shot,i)=>frame>=Math.round(shot.start*fps)&&
      (frame<Math.round(shot.end*fps)||i===shots.length-1));
  }
  function adjacentCutTime(shots,time,direction,fps,duration){
    fps=Number(fps)||30;
    const frame=Math.floor(Math.max(0,Number(time)||0)*fps+1e-4);
    const cuts=[...new Set(shots.map(shot=>Math.round(shot.start*fps)))].sort((a,b)=>a-b);
    const target=direction<0?cuts.reverse().find(cut=>cut<frame):cuts.find(cut=>cut>frame);
    return frameTime(target===undefined?(direction<0?0:duration):target/fps,fps,duration);
  }
  function snapTime({time,fps,duration,pixelWidth,candidates=[],enabled=true,bypass=false,allowEnd=false}){
    const raw=clamp(Number(time)||0,0,duration);
    let target=null,distance=Infinity;
    const threshold=Math.min(.3,8*duration/Math.max(1,pixelWidth));
    if(enabled&&!bypass)for(const candidate of candidates){
      if(!Number.isFinite(candidate.time)||candidate.time<0||candidate.time>duration)continue;
      const d=Math.abs(candidate.time-raw);
      if(d<=threshold+1e-9&&d<distance){distance=d;target=candidate;}
    }
    return {time:frameTime(target?target.time:raw,fps,duration,allowEnd),snapped:!!target,label:target?.label||''};
  }
  function zoomScroll({oldWidth,newWidth,scrollLeft,viewport,anchorTime,duration}){
    const x=anchorTime/duration*oldWidth;
    const anchorVisible=x>=scrollLeft&&x<=scrollLeft+viewport;
    const ratio=anchorVisible?anchorTime/duration:(scrollLeft+viewport/2)/oldWidth;
    const offset=anchorVisible?x-scrollLeft:viewport/2;
    return clamp(ratio*newWidth-offset,0,Math.max(0,newWidth-viewport));
  }
  class SingleFlight{
    constructor(now=()=>Date.now()){this.tasks=new Map();this.now=now;}
    run(key,work,cooldown=0){
      const prior=this.tasks.get(key);
      if(prior&&(prior.pending||this.now()<prior.until))return prior.promise;
      const task={pending:true,until:0};
      task.promise=Promise.resolve().then(work).then(value=>{task.pending=false;task.until=this.now()+cooldown;return value;},error=>{this.tasks.delete(key);throw error;});
      this.tasks.set(key,task);
      if(this.tasks.size>100)for(const [k,t] of this.tasks)if(!t.pending&&this.now()>=t.until)this.tasks.delete(k);
      return task.promise;
    }
  }
  const api={formatTime,frameTime,shotIndexAt,adjacentCutTime,snapTime,zoomScroll,SingleFlight};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.LapianInteraction=api;
})(typeof window!=='undefined'?window:globalThis);
