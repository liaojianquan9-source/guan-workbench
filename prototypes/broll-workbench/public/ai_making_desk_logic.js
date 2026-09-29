'use strict';
(function(root,factory){const result=factory();if(typeof module==='object'&&module.exports)module.exports=result;else root.AiMakingDeskLogic=result;})(typeof globalThis==='undefined'?this:globalThis,function(){
 const duration=(project,source)=>Math.max(Number(source?.metadata?.media?.duration)||0,...(project?.segments||[]).map(segment=>Number(segment.end)||0),...(project?.cards||[]).map(card=>Number(card.end)||0),1);
 const status=card=>card.status==='approved'?'已确认':card.status==='rejected'?'保留口播':card.decision==='gap'?'待补素材':card.decision==='keep'?'建议不加':'待审看';
 const filter=(cards,kind)=>kind==='pending'?cards.filter(c=>c.status==='draft'):kind==='missing'?cards.filter(c=>c.decision==='gap'&&c.status!=='rejected'):kind==='done'?cards.filter(c=>c.status==='approved'||c.status==='rejected'):cards;
 const ready=card=>card.decision==='keep'||card.decision==='broll'&&!!card.preview_url&&!!card.render_fingerprint&&card.render_report?.layout?.status==='passed';
 const approveSelection=(project,ids)=>{const chosen=(project?.cards||[]).filter(c=>ids.includes(c.id)&&c.status!=='approved'&&c.status!=='rejected');return{eligible:chosen.filter(ready).map(c=>c.id),skipped:chosen.filter(c=>!ready(c)).map(c=>c.id)};};
 const activeCard=(cards,time)=>(cards||[]).find(c=>c.decision==='broll'&&c.status!=='rejected'&&c.start<=time&&time<c.end);
 const time=value=>`${String(Math.floor(Number(value||0)/60)).padStart(2,'0')}:${(Number(value||0)%60).toFixed(1).padStart(4,'0')}`;
 const reference=(id,segments,styles)=>{if(id.startsWith('transcript:')){const segment=segments.find(x=>x.id===id.slice(11));return segment?`口播 ${time(segment.start)} · ${segment.text}`:id;}if(id.startsWith('asset:')){const name=id.slice(6).split('@')[0];return `共享样式 · ${styles.find(x=>x.id===name)?.name||name} · ${id.split('@')[1]||''} 版`;}if(id.startsWith('video:'))return `原片画面 · ${id.slice(6)} 秒`;if(id.startsWith('history:'))return `既有项目记录 · ${id.slice(8)}`;return id;};
 const within=(card,start,end,total,cards)=>Number.isFinite(start)&&Number.isFinite(end)&&start>=0&&end<=total+.001&&end-start>=.4&&end-start<=15&&!cards.some(c=>c.id!==card.id&&c.decision==='broll'&&c.status!=='rejected'&&start<c.end-.001&&end>c.start+.001);
 const matchingDelivery=project=>[...(project?.deliveries||[])].reverse().find(delivery=>delivery.cards?.every(ref=>(project?.cards||[]).some(card=>card.id===ref.id&&card.status==='approved'&&card.render_fingerprint===ref.fingerprint)));
 return{duration,status,filter,ready,approveSelection,activeCard,time,reference,within,matchingDelivery};
});
