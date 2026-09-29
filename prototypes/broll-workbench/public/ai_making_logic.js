'use strict';
const AiMakingLogic=(()=>{
 const sentenceBreak=/[^。！？!?；;\n]+[。！？!?；;]?/g;
 function splitText(raw,mode='sentence'){
  const text=String(raw||'').trim();
  if(!text)return [];
  if(mode==='paragraph')return text.split(/\n+/).map(x=>x.trim()).filter(Boolean);
  return (text.match(sentenceBreak)||[]).map(x=>x.trim()).filter(Boolean);
 }
 function splitSegments(segments,mode='sentence'){
  const result=[];
  for(const segment of segments||[]){
   const text=String(segment.text||'').trim();
   const pieces=splitText(text,mode);
   if(!pieces.length)continue;
   const start=Number(segment.start),end=Number(segment.end),timed=Number.isFinite(start)&&Number.isFinite(end)&&end>start;
   const total=pieces.reduce((n,x)=>n+x.length,0);let offset=0;
   for(const piece of pieces){const next=offset+piece.length;result.push({text:piece,start:timed?start+(end-start)*offset/total:null,end:timed?start+(end-start)*next/total:null,estimated:timed&&pieces.length>1});offset=next;}
  }
  return result;
 }
 const signals=[
  {id:'SHOT-007',reason:'这句话在比较两项内容',pattern:/对比|比较|相比|差异|优于|超过|高于|低于|vs\.?| versus |两种|两款|分别/i},
  {id:'SHOT-002',reason:'这句话包含值得强调的数字',pattern:/\d|[一二三四五六七八九十百千万亿]+(?:个|倍|亿|万|%|％|年|秒|分|元|美元|参数|用户)/},
  {id:'SHOT-005',reason:'这句话在引用文章或外部证据',pattern:/文章|报告|研究|新闻|论文|数据指出|根据|引用|证据|标题/i},
  {id:'SHOT-006',reason:'这句话在讲操作或步骤',pattern:/提示词|输入|点击|操作|步骤|首先|然后|接着|打开|生成|上传|选择/i},
  {id:'SHOT-004',reason:'这句话提出问题',pattern:/为什么|怎么|问题|难点|痛点|困惑|如何|怎么办|瓶颈/i},
  {id:'SHOT-003',reason:'这句话介绍产品或名称',pattern:/产品|品牌|模型|发布|推出|名字|名称|Kimi|GPT|Claude/i},
  {id:'SHOT-001',reason:'这句话适合作为观点标题',pattern:/核心|关键|结论|重点|本质|其实|真正|就是|意味着/i},
 ];
 function suggest(text,availableIds){
  const allowed=new Set(availableIds||[]);
  const hit=signals.find(rule=>allowed.has(rule.id)&&rule.pattern.test(String(text||'')));
  return hit?{presetId:hit.id,reason:hit.reason}:{presetId:null,reason:'当前没有足够明确的库内匹配，先保留口播画面'};
 }
 function createCards(parts,presetIds){return parts.map((part,index)=>{const match=suggest(part.text,presetIds);return {id:`line-${index+1}`,text:part.text,start:part.start??null,end:part.end??null,estimated:!!part.estimated,presetId:match.presetId,reason:match.reason,confirmed:false,fields:{}}});}
 return {splitText,splitSegments,suggest,createCards};
})();
if(typeof module!=='undefined')module.exports=AiMakingLogic;
