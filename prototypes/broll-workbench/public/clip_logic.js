(function(root){
 'use strict';
 const logic={
  rulerStep:(duration,width)=>{
   const desired=80*Math.max(0,duration)/Math.max(1,width);
   return [.1,.2,.5,1,2,5,10,30,60,120,300,600,1800,3600].find(v=>v>=desired)||Math.ceil(desired/3600)*3600;
  },
  rulerLabel:time=>{
   const ticks=Math.round(Math.max(0,time)*100),seconds=Math.floor(ticks/100),fraction=ticks%100;
   const tail=fraction?'.'+String(fraction).padStart(2,'0').replace(/0$/,''):'';
   if(seconds<60)return seconds+tail+'s';
   const minutes=Math.floor(seconds/60),part=String(seconds%60).padStart(2,'0')+tail;
   return minutes<60?minutes+':'+part:Math.floor(minutes/60)+':'+String(minutes%60).padStart(2,'0')+':'+part;
  },
  inside:(clip,time)=>!!clip&&time>=clip.start&&time<clip.end,
  soundRegions:(clips,preferredId=null)=>{
   const ready=(clips||[]).filter(c=>!c.deleted&&c.end>c.start&&(c.sound?.files?.vocals||c.sound?.files?.background));
   const edges=[...new Set(ready.flatMap(c=>[c.start,c.end]))].sort((a,b)=>a-b),regions=[];
   for(let i=0;i<edges.length-1;i++){
    const start=edges[i],end=edges[i+1],cover=ready.filter(c=>c.start<=start&&c.end>=end).sort((a,b)=>Number(a.scope==='source')-Number(b.scope==='source')||b.start-a.start||String(a.id).localeCompare(String(b.id)));
    const clip=cover.find(c=>c.id===preferredId)||cover[0];if(!clip)continue;
    const last=regions.at(-1);if(last?.clip.id===clip.id&&last.end===start)last.end=end;else regions.push({start,end,clip});
   }return regions;
  },
  soundAt:(regions,time)=>regions.find(r=>time>=r.start&&time<r.end)?.clip||null,
  limit:(clip,time,fps=30)=>clip?Math.max(Math.ceil(clip.start*fps-1e-7)/fps,Math.min((Math.ceil(clip.end*fps-1e-7)-1)/fps,time)):time,
  relative:(clip,time)=>Math.max(0,Math.min(clip.end-clip.start,time-clip.start)),
  subtitles:(clip,segments)=>segments.filter(s=>s.end>clip.start&&s.start<clip.end),
  atEnd:(clip,time,fps=30)=>!!clip&&time>=clip.end-0.5/fps,
  ratio:(clip,time)=>Math.max(0,Math.min(1,(time-clip.start)/(clip.end-clip.start))),
  shotSpans:(clip,shots)=>shots.filter(s=>s.end>clip.start&&s.start<clip.end).map(s=>({...s,
   left:(Math.max(clip.start,s.start)-clip.start)/(clip.end-clip.start),
   width:(Math.min(clip.end,s.end)-Math.max(clip.start,s.start))/(clip.end-clip.start)})),
  point:(clip,ratio,{fps=30,pixelWidth=1,candidates=[],snap=true,bypass=false}={})=>{
   const raw=clip.start+Math.max(0,Math.min(1,ratio))*(clip.end-clip.start);
   const threshold=Math.min(.3,8*(clip.end-clip.start)/Math.max(1,pixelWidth));
   let target=null,distance=Infinity;
   if(snap&&!bypass)for(const candidate of candidates){const d=Math.abs(candidate.time-raw);
    if(candidate.time>=clip.start&&candidate.time<=clip.end&&d<=threshold&&d<distance){target=candidate;distance=d;}}
   return {time:logic.limit(clip,Math.round((target?.time??raw)*fps)/fps,fps),snapped:!!target,label:target?.label||''};
  },
 };
 if(typeof module!=='undefined')module.exports=logic;else root.ClipLogic=logic;
})(typeof globalThis!=='undefined'?globalThis:this);
