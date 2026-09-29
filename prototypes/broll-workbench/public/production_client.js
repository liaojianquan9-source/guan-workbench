'use strict';
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.ProductionClient=value;})(typeof globalThis==='undefined'?this:globalThis,function(){
 const prefix='/api/production';
 const labels={draft:'待确认',approved:'已确认',rejected:'已舍弃',broll:'建议画面',keep:'保留口播',gap:'待补素材',queued:'排队中',running:'执行中',processing:'执行中',complete:'已完成',completed:'已完成',awaiting_review:'待审看',failed:'失败',error:'失败',interrupted:'已中断',cancelled:'已取消',passed:'通过',needs_review:'待审',pending:'待处理'};
 const pending=status=>['queued','running','processing','pending'].includes(status);
 function media(value){if(typeof value!=='string'||/[\s\\]/.test(value)||!/^\/api\//.test(value))return '';return value.startsWith(prefix+'/')?value:prefix+value.slice(4);}
 const blob=hash=>/^[a-f0-9]{64}$/.test(hash||'')?`${prefix}/media/${hash}`:'';
 function matchingProjects(workbenchId,projects,assets){const sources=new Set(assets.filter(item=>item.kind==='source'&&item.metadata?.provenance?.workbench_id===workbenchId).map(item=>item.id));return projects.filter(project=>sources.has(project.source?.asset_id)).sort((a,b)=>Number(!!a.derived_from)-Number(!!b.derived_from)||Number(!!b.cards?.length)-Number(!!a.cards?.length)||String(b.updated_at||'').localeCompare(String(a.updated_at||'')));}
 function chooseProject(workbenchId,projects,assets,savedId){const candidates=workbenchId?matchingProjects(workbenchId,projects,assets):projects;return candidates.find(project=>project.id===savedId)||candidates[0]||null;}
 function fields(style){const schema=style?.metadata?.field_schema||{};return Object.entries(schema.properties||schema).map(([key,value])=>({key,...value}));}
 function selection(project,ids){const available=new Set((project?.cards||[]).map(card=>card.id));return [...new Set(ids)].filter(id=>available.has(id));}
 function batchBody(project,ids,action,extra={}){const card_ids=selection(project,ids);if(!card_ids.length)throw new Error('请先选择分镜卡。');if(!Number.isInteger(project?.revision))throw new Error('项目版本不可用，请刷新重试。');return{revision:project.revision,card_ids,action,...extra};}
 class Client{
  constructor(fetcher){this.fetch=fetcher||globalThis.fetch.bind(globalThis);}
  async request(path,body){if(!/^\/(?!\/)/.test(path))throw new Error('制作服务路径无效。');let response;try{response=await this.fetch(prefix+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}catch{throw new Error('制作服务暂时无法连接，已有草稿仍保留。请重新启动「观」本机服务后重试。');}let result;try{result=await response.json();}catch{throw new Error(`制作服务响应无法读取（${response.status}）。`);}if(!response.ok){const error=new Error(result.error||result.message||'制作操作未完成。');error.status=response.status;throw error;}return result;}
  async library(){const [projects,assets]=await Promise.all([this.request('/projects'),this.request('/assets')]);return{projects:projects.projects||[],assets:assets.assets||[]};}
  async upload(file,kind='image'){const response=await this.fetch(`${prefix}/upload?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});let result;try{result=await response.json();}catch{throw new Error('素材上传响应无法读取。');}if(!response.ok)throw new Error(result.error||'素材上传失败。');return result.asset;}
 }
 return{prefix,labels,label:value=>labels[value]||value||'',pending,media,blob,matchingProjects,chooseProject,fields,selection,batchBody,Client};
});
