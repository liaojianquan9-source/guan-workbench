export const DURATION = 53.03;
export const STYLES = [
  {id:'focus',name:'聚焦时刻',version:'v2',kind:'文字动效',tone:'dark',source:'演示共享样式',match:'语义强调 / 关键句',motif:'FOCUS'},
  {id:'compare',name:'双栏对照',version:'v1',kind:'信息布局',tone:'cream',source:'演示共享样式',match:'判断 / 对照',motif:'A / B'},
  {id:'note',name:'轻笔记',version:'v3',kind:'图文卡片',tone:'sage',source:'演示共享样式',match:'行动建议 / 清单',motif:'NOTE'}
];
export const SEED = [
  {id:'d1',start:0,end:4.4,text:'我刷完那个视频就睡了。说好 AI 能省时间。',reason:'开场需要先看见说话者，建立人物关系；目前没有需要解释的视觉信息。',status:'pending',decision:'keep',style:null,confidence:'高',evidence:'开场语义与人物情绪一致',transition:'直切',crop:'铺满'},
  {id:'d2',start:8.8,end:13,text:'AI 给的一些正反馈太强了，你会觉得再改一版也好。',reason:'「正反馈太强」是抽象感受，短暂的关键词动效能帮助理解，不需要盖住完整句子。',status:'pending',decision:'broll',style:'focus',confidence:'较高',evidence:'口播 08.8–13.0s + 共享样式「聚焦时刻」v2',transition:'淡入淡出',crop:'竖屏重排'},
  {id:'d3',start:15,end:19.46,text:'甚至睡觉之前，都会去安排给 AI 一个任务点。',reason:'这里适合真实的夜间工作画面，库里没有与你的场景相符的素材；先标记缺口。',status:'missing',decision:'missing',style:null,confidence:'待素材',evidence:'口播 15.0–19.5s；共享库未找到匹配夜间桌面素材',transition:'直切',crop:'铺满'},
  {id:'d4',start:27.8,end:35.28,text:'我们平时跟 AI 协作，是需要人去做主观判断的。',reason:'关键论点，画面只突出「人做判断」；口播声音和节奏保持原样。',status:'pending',decision:'broll',style:'compare',confidence:'高',evidence:'口播 27.8–35.3s + 共享样式「双栏对照」v1',transition:'推入',crop:'竖屏重排'},
  {id:'d5',start:39.34,end:46.3,text:'设定每天的收工时间，把这些东西丢到明天再做。',reason:'行动建议适合笔记式收尾，和前面的关键论点拉开视觉层级。',status:'pending',decision:'broll',style:'note',confidence:'较高',evidence:'口播 39.3–46.3s + 共享样式「轻笔记」v3',transition:'淡入淡出',crop:'竖屏重排'},
  {id:'d6',start:49.38,end:53.03,text:'今天也好好休息哦。拜拜。',reason:'结尾保留本人画面与表情，避免在告别时继续叠加信息。',status:'pending',decision:'keep',style:null,confidence:'高',evidence:'口播 49.4–53.0s；结尾人物镜头',transition:'直切',crop:'铺满'}
];
export function createInitialState(){return {cards:SEED.map(x=>({...x})),selected:'d2',checked:[],time:9.4,playing:false,zoom:1,view:'make',filter:'all',inspector:'decision',history:[],future:[],notice:''};}
export function clamp(n,min,max){return Math.max(min,Math.min(max,n));}
export function formatTime(t){let s=clamp(Number(t)||0,0,DURATION);return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}.${String(Math.floor((s%1)*10))}`;}
function snapshot(s){return {cards:s.cards.map(x=>({...x})),selected:s.selected,checked:[...s.checked],time:s.time};}
function change(s,transform){const next={...s,cards:s.cards.map(x=>({...x})),checked:[...s.checked],history:[...s.history,snapshot(s)],future:[]};transform(next);return next;}
export function activeCard(cards,time){return cards.find(c=>c.start<=time&&time<c.end&&c.decision==='broll')||null;}
export function action(s,a){
  if(a.type==='select'){let card=s.cards.find(c=>c.id===a.id);return card?{...s,selected:card.id,time:card.start+Math.min(.6,(card.end-card.start)/2)}:s;}
  if(a.type==='seek')return {...s,time:clamp(a.time,0,DURATION)};
  if(a.type==='toggleCheck')return {...s,checked:s.checked.includes(a.id)?s.checked.filter(x=>x!==a.id):[...s.checked,a.id]};
  if(a.type==='checkVisible'){let ids=new Set(a.ids);return {...s,checked:a.checked?[...new Set([...s.checked,...ids])]:s.checked.filter(id=>!ids.has(id))};}
  if(a.type==='filter'||a.type==='view'||a.type==='inspector'||a.type==='notice'||a.type==='playing')return {...s,[a.type==='notice'?'notice':a.type]:a.value};
  if(a.type==='zoom')return {...s,zoom:clamp(s.zoom+a.delta,.75,2.5)};
  if(a.type==='undo'){if(!s.history.length)return s;const old=s.history.at(-1);return {...s,...old,history:s.history.slice(0,-1),future:[snapshot(s),...s.future]};}
  if(a.type==='redo'){if(!s.future.length)return s;const next=s.future[0];return {...s,...next,history:[...s.history,snapshot(s)],future:s.future.slice(1)};}
  if(a.type==='bulk'){let ids=s.checked.filter(id=>s.cards.some(c=>c.id===id));if(!ids.length)return s;return change(s,n=>{n.cards.forEach(c=>{if(ids.includes(c.id)){c.decision=a.decision==='accept'?(c.style?'broll':'keep'):'keep';c.status=a.decision==='accept'&&c.style?'accepted':'kept';}});n.checked=[];});}
  if(a.type==='setDecision')return change(s,n=>{let c=n.cards.find(x=>x.id===a.id);if(!c)return;c.decision=a.decision;c.status=a.decision==='keep'?'kept':a.decision==='missing'?'missing':'accepted';if(a.style)c.style=a.style;});
  if(a.type==='setStyle')return change(s,n=>{let c=n.cards.find(x=>x.id===a.id);if(!c)return;c.style=a.style;c.decision='broll';c.status='pending';});
  if(a.type==='setEffect')return change(s,n=>{let c=n.cards.find(x=>x.id===a.id);if(c){c[a.field]=a.value;c.status='pending';}});
  if(a.type==='move'||a.type==='trim')return change(s,n=>{
    let c=n.cards.find(x=>x.id===a.id);if(!c)return;
    const length=c.end-c.start, oldStart=c.start, oldEnd=c.end, neighbor=n.cards.filter(x=>x.id!==c.id&&x.decision==='broll');
    if(a.type==='move'){
      let target=clamp(a.start,0,DURATION-length);
      for(const other of neighbor){if(Math.abs(target-other.end)<.18)target=other.end;if(Math.abs(target+length-other.start)<.18)target=other.start-length;}
      const intersects=neighbor.some(x=>target<x.end&&target+length>x.start);
      if(!intersects){c.start=+target.toFixed(2);c.end=+(target+length).toFixed(2);}
    }else{
      let target=clamp(a.time,0,DURATION);
      if(a.edge==='left'){target=clamp(target,0,c.end-.6);if(!neighbor.some(x=>target<x.end&&c.end>x.start))c.start=+target.toFixed(2);}
      else {target=clamp(target,c.start+.6,DURATION);if(!neighbor.some(x=>c.start<x.end&&target>x.start))c.end=+target.toFixed(2);}
    }
    if(c.start!==oldStart||c.end!==oldEnd){c.status='pending';c.timingChanged=true;n.selected=c.id;n.time=c.start+Math.min(.5,(c.end-c.start)/2);}
  });
  return s;
}
