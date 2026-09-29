'use strict';
(function(root,factory){
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.ReplicaLogic=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 const sceneKey=(taskId,sceneId,revision=1)=>`${taskId}:${sceneId}:v${Number(revision)}`;
 const groupPrototypeShots=(shots,sizes=[3,2,4])=>{
  const groups=[];
  let cursor=0;
  while(cursor<shots.length){
   const size=Math.max(1,Number(sizes[groups.length%sizes.length])||1);
   groups.push(shots.slice(cursor,cursor+size));
   cursor+=size;
  }
  return groups;
 };
 const taskSceneStatus=(task,statuses,revision=1)=>{
  const values=(task.scenes||[]).map(scene=>statuses[sceneKey(task.id,scene.id,revision)]||'review');
  if(values.length&&values.every(value=>value==='approved'))return 'approved';
  if(values.some(value=>value==='changes'))return 'changes';
  if(values.some(value=>value==='generating'))return 'generating';
  return 'review';
 };
 const sceneCounts=(tasks,statuses,revision=1)=>tasks.reduce((result,task)=>{
  for(const scene of task.scenes||[]){
   const value=statuses[sceneKey(task.id,scene.id,revision)]||'review';
   result[value]=(result[value]||0)+1;
  }
  return result;
 },{approved:0,review:0,changes:0,generating:0});
 const areAllScenesApproved=(task,statuses,revision=1)=>(task.scenes||[]).length>0&&(task.scenes||[]).every(scene=>statuses[sceneKey(task.id,scene.id,revision)]==='approved');
 const firstReviewableScene=(tasks,statuses,revision=1,startTask=0,startScene=-1)=>{
  const flat=[];
  tasks.forEach((task,taskIndex)=>(task.scenes||[]).forEach((scene,sceneIndex)=>flat.push({task,scene,taskIndex,sceneIndex})));
  if(!flat.length)return null;
  const start=Math.max(-1,flat.findIndex(item=>item.taskIndex===startTask&&item.sceneIndex===startScene));
  for(let offset=1;offset<=flat.length;offset++){
   const item=flat[(start+offset)%flat.length];
   if(['review','changes'].includes(statuses[sceneKey(item.task.id,item.scene.id,revision)]||'review'))return {taskIndex:item.taskIndex,sceneIndex:item.sceneIndex};
  }
  return null;
 };
 return {sceneKey,groupPrototypeShots,taskSceneStatus,sceneCounts,areAllScenesApproved,firstReviewableScene};
});
