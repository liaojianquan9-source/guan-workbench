'use strict';
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.AssetLibrary=value;})(typeof globalThis==='undefined'?this:globalThis,function(){
 const views=new Set(['library','analysis','replica','ai-making','assets','settings']);
 function resolveAssetRoute(view,tab){
  if(view==='frames')return {view:'assets',tab:'images',redirected:true};
  if(view==='music')return {view:'assets',tab:'music',redirected:true};
  if(view==='assets')return {view:'assets',tab:tab==='music'?'music':'images',redirected:false};
  if(views.has(view))return {view,tab:null,redirected:false};
  return {view:'library',tab:null,redirected:false};
 }
 function routeQuery({project,view,tab,reference}={}){
  const params=new URLSearchParams();
  if(project)params.set('project',String(project));
  params.set('view',view||'library');
  if(view==='assets')params.set('tab',tab==='music'?'music':'images');
  if(view==='replica'&&reference)params.set('reference',String(reference));
  return '?'+params.toString();
 }
 function reusableStyles(assets){
  return (Array.isArray(assets)?assets:[]).filter(item=>item&&item.kind==='style'&&item.metadata&&item.metadata.technical_status==='passed');
 }
 function replacementImages(assets){
  return (Array.isArray(assets)?assets:[]).filter(item=>item&&item.kind==='image');
 }
 function musicGroups(rows,localOnly){
  const list=Array.isArray(rows)?rows:[];
  const local=list.filter(row=>row&&!row.projectId);
  const identified=list.filter(row=>row&&row.projectId);
  if(localOnly)return local.length?[{id:'local',title:'本地曲库',rows:local}]:[];
  const groups=[];
  if(identified.length)groups.push({id:'identified',title:'识曲结果',rows:identified});
  if(local.length)groups.push({id:'local',title:'本地曲库',rows:local});
  return groups;
 }
 return {resolveAssetRoute,routeQuery,reusableStyles,replacementImages,musicGroups};
});
