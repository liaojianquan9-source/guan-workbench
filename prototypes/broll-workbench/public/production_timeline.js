'use strict';
(function(root,factory){
 const value=factory();
 if(typeof module==='object'&&module.exports)module.exports=value;
 else root.ProductionTimeline=value;
})(typeof globalThis==='object'?globalThis:this,()=>{
 const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
 const active=card=>card.decision==='broll'&&card.status!=='rejected';
 function duration(project,source){
  const actual=Number(source?.metadata?.media?.duration);
  return actual>0?actual:Math.max(1,...(project?.segments||[]).map(s=>Number(s.end)||0),...(project?.cards||[]).map(c=>Number(c.end)||0));
 }
 function fps(source){
  const [n,d=1]=String(source?.metadata?.media?.fps||30).split('/').map(Number);
  return n>0&&d>0&&Number.isFinite(n/d)?n/d:30;
 }
 function timing(project,source,card,start,end){
  if(!card||!active(card))throw new Error('选择一段使用中的 B-roll，才能调整覆盖时间。');
  if(!project?.source||!source)throw new Error('原视频尚未载入，请先读取保存草稿。');
  start=Number(start);end=Number(end);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>duration(project,source)+.001)
   throw new Error('覆盖范围必须位于原视频内。');
  if(end-start<.4-.001||end-start>15+.001)throw new Error('B-roll 时长须为 0.4–15 秒。');
  if((project.cards||[]).some(c=>c.id!==card.id&&active(c)&&start<c.end-.001&&end>c.start+.001))
   throw new Error('这次调整会与另一段 B-roll 重叠。');
  return {start:Math.round(start*1000)/1000,end:Math.round(end*1000)/1000};
 }
 function drag(card,part,seconds,total){
  const length=card.end-card.start;
  if(part==='start')return {start:clamp(card.start+seconds,Math.max(0,card.end-15),card.end-.4),end:card.end};
  if(part==='end')return {start:card.start,end:clamp(card.end+seconds,card.start+.4,Math.min(total,card.start+15))};
  const start=clamp(card.start+seconds,0,Math.max(0,total-length));
  return {start,end:start+length};
 }
 function delivery(project){
  const expected=(project?.cards||[]).filter(c=>active(c)&&c.status==='approved');
  return [...(project?.deliveries||[])].reverse().find(item=>
   Array.isArray(item.cards)&&item.cards.length===expected.length&&
   expected.every(c=>c.render_fingerprint&&item.cards.some(v=>v.id===c.id&&v.fingerprint===c.render_fingerprint)));
 }
 function approval(project,ids){
  const selected=new Set(ids),ready=[],blocked=[];
  for(const c of project?.cards||[]){
   if(!selected.has(c.id))continue;
   if(c.decision==='keep'||c.decision==='broll'&&c.preview_url&&c.render_fingerprint&&c.render_report?.layout?.status==='passed')ready.push(c.id);
   else blocked.push(c.id);
  }
  return {ready,blocked};
 }
 return {active,duration,fps,timing,drag,delivery,approval};
});
