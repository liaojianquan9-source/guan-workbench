/* Portable project folders; exports write directly to the chosen destination. */
window.StorageUI=(()=>{
 let timer=null,last=null,controller=null;
 const names={export:'导出完整资料',restore:'恢复资料',migrate:'更换资料库位置',release:'释放本机空间'};
 function settings(status){return `<div class="storage-actions">${button('更换位置','storage-migrate','','folder')}${button('导出整个资料库','storage-export-library','','download')}${button('恢复资料','storage-restore','','refresh')}</div><p class="settings-explain">项目可以搬到移动硬盘，再恢复回来继续拉片。导出校验完成后，可单独释放本机空间。</p>${status?.tasks?.length?`<div class="storage-history">${status.tasks.slice().reverse().map(t=>`<button class="storage-history-row" data-action="storage-task" data-task="${esc(t.id)}"><span>${esc(names[t.action])}</span><small>${esc(t.message)}</small><span>${t.can_release?'可释放空间':t.status==='complete'?'已完成':t.status==='error'?'未完成':t.status==='cancelled'?'已取消':'查看进度'}</span></button>`).join('')}</div>`:''}`;}
 function open(action,projectId){
  clearTimeout(timer);S.modal={type:'storage',storageAction:action,projectId};
  const intro=action==='export'?'视频、分镜、字幕修改、图片、声音和笔记将一起保存到目标文件夹。':action==='restore'?'选择导出的完整项目或资料库文件夹，也可以直接把文件夹拖进工作台。': '选择一个空文件夹。资料复制并校验后切换位置，旧目录等你主动释放空间。';
  showModal(names[action],`<p>${intro}</p><label class="storage-path-label" for="storage-path">${action==='restore'?'项目文件夹':'目标文件夹'}</label><div class="storage-path-row"><input id="storage-path" placeholder="选择文件夹，或粘贴完整路径" autocomplete="off"><button class="button" data-action="storage-choose">${icon('folder')}选择文件夹</button></div><p class="settings-explain">${action==='export'?'直接写入目标位置，不会先在本机生成压缩包。':action==='restore'?'恢复会保留你的修改，不会重新进行自动分析。':'新的导入和研究结果将保存在这里。'}</p><div id="storage-error" class="storage-error" role="alert"></div>`,`${action==='restore'?button('从文件夹上传恢复','storage-upload-picker'):''}${button('取消','close-dialog')}${button(action==='restore'?'开始恢复':action==='migrate'?'迁移并切换':'开始导出','storage-start','primary')}`);
 }
 async function choose(){const r=await api('/api/storage/choose-folder',{});if(r.path&&$('#storage-path'))$('#storage-path').value=r.path;}
 async function start(){const m=S.modal,path=$('#storage-path')?.value.trim();if(!path)throw new Error('请先选择文件夹。');
  pauseVideo();const task=await api('/api/storage/tasks',{action:m.storageAction,...(m.storageAction==='restore'?{source:path}:{destination:path}),...(m.projectId?{project_id:m.projectId}:{})});showTask(task);
 }
 function pauseVideo(){ $('#video')?.pause();Clips.stopSound(); }
 function showTask(task){
  last=task;clearTimeout(timer);S.modal={type:'storage-task',taskId:task.id};
  showModal(names[task.action],'<div id="storage-task-progress" aria-live="polite"></div>',button('收起','close-dialog'));
  paintTask(task);if(['running','uploading'].includes(task.status))timer=setTimeout(()=>poll(task.id),700);
 }
 function paintTask(t){const el=$('#storage-task-progress');if(!el)return;const working=['running','uploading'].includes(t.status),percent=t.total_bytes?Math.min(100,t.done_bytes/t.total_bytes*100):0;
  el.innerHTML=`<div class="storage-task-state ${t.status==='error'?'storage-error':''}">${icon(t.verified?'check':t.status==='error'?'info':'folder')}<strong>${esc(t.message)}</strong></div>${working?`<progress max="100" value="${percent}" aria-label="搬运进度"></progress><p class="muted">${size(t.done_bytes)} / ${size(t.total_bytes)}</p>`:''}${t.destination?`<p class="storage-destination">${esc(t.destination)}</p>`:''}${t.verified?'<p class="settings-explain">文件完整性校验通过。</p>':''}<div class="storage-actions">${working&&!t.committing?button('取消任务','storage-cancel'):''}${t.can_release?button(t.action==='migrate'?'释放旧目录空间':'释放本机空间','storage-release-prompt','','trash'):''}${t.status==='complete'&&!t.can_release?button('完成','close-dialog','primary'):''}</div>`;
 }
 async function poll(id){try{const r=await api('/api/storage');const t=r.tasks.find(t=>t.id===id);if(!t)return;if(last?.id===id)last=t;if(S.modal?.type==='storage-task'&&S.modal.taskId===id)paintTask(t);if(['running','uploading'].includes(t.status))timer=setTimeout(()=>poll(id),900);else {await refresh();if(t.status==='complete')toast(t.message);}}catch(e){if($('#storage-task-progress'))$('#storage-task-progress').textContent=e.message;}}
 async function refresh(){const [projects,music]=await Promise.all([api('/api/projects'),api('/api/music')]);S.projects=projects.projects;S.music=music.tracks;S.runtime=null;if(S.p){S.p=S.projects.find(p=>p.id===S.p.id)||null;}if(!S.p&&S.view==='analysis'){S.view='library';shell();}else if(S.view==='settings')await renderSettings();else refreshViews();}
 function releasePrompt(){const receipt=last;S.modal={type:'storage-release',receipt:receipt.id};showModal('释放本机空间',`<p>将删除${receipt.action==='migrate'?'旧目录':'本机'}中的视频及对应拉片文件，腾出磁盘空间。</p><p>完整副本保存在：</p><p class="storage-destination">${esc(receipt.destination)}</p><p>操作前会再次校验副本；如果本机资料有新修改，将停止删除并提醒重新导出。</p>`,`${button('保留本机资料','close-dialog')}${button('确认释放空间','storage-release','danger','trash')}`);}
 async function action(name,el){try{switch(name){
  case 'storage-export-project':open('export',S.modal?.projectId||S.p?.id);break;
  case 'storage-export-library':open('export');break;
  case 'storage-migrate':open('migrate');break;
  case 'storage-restore':open('restore');break;
  case 'storage-choose':await choose();break;
  case 'storage-start':el.disabled=true;try{await start();}finally{el.disabled=false;}break;
  case 'storage-task':{const r=await api('/api/storage');const t=r.tasks.find(t=>t.id===el.dataset.task);if(t)showTask(t);break;}
  case 'storage-cancel':controller?.abort();await api(`/api/storage/tasks/${last.id}/cancel`,{});await poll(last.id);break;
  case 'storage-release-prompt':releasePrompt();break;
  case 'storage-release':el.disabled=true;try{pauseVideo();showTask(await api('/api/storage/tasks',{action:'release',receipt:S.modal.receipt}));}finally{el.disabled=false;}break;
  case 'storage-upload-picker':$('#restore-files').click();break;
 }}catch(e){const target=$('#storage-error');if(target)target.textContent=e.message;else toast(e.message);}}
 async function restoreFiles(files){
  const manifestFiles=files.filter(f=>f.relativePath.endsWith('/项目清单.json')||f.relativePath==='项目清单.json');
  if(manifestFiles.length!==1)throw new Error('请选择一个完整的项目或资料库文件夹。');
  const selected=manifestFiles[0],prefix=selected.relativePath.slice(0,-'项目清单.json'.length);
  const manifest=JSON.parse(await selected.file.text());const map=new Map(files.map(f=>[f.relativePath,f.file]));
  if(!Array.isArray(manifest.files))throw new Error('项目清单无效。');
  for(const item of manifest.files){const file=map.get(prefix+'项目资料/'+item.path);if(!file||file.size!==item.size)throw new Error('项目包缺少文件或文件大小不符：'+item.path);}
  pauseVideo();const task=await api('/api/storage/uploads',manifest);showTask(task);controller=new AbortController();
  try{
   for(const item of manifest.files){const response=await fetch(`/api/storage/uploads/${task.id}?path=${encodeURIComponent(item.path)}`,{method:'POST',body:map.get(prefix+'项目资料/'+item.path),signal:controller.signal});const result=await response.json();if(!response.ok)throw new Error(result.error);last=result;paintTask(result);}
   showTask(await api(`/api/storage/uploads/${task.id}/finish`,{}));
  }catch(e){await api(`/api/storage/tasks/${task.id}/cancel`,{}).catch(()=>{});if(e.name!=='AbortError')toast(e.message);await poll(task.id);}finally{controller=null;}
 }
 async function walk(entry,prefix=''){
  const path=prefix+entry.name;
  if(entry.isFile)return [{file:await new Promise((resolve,reject)=>entry.file(resolve,reject)),relativePath:path}];
  const reader=entry.createReader(),children=[];while(true){const batch=await new Promise((resolve,reject)=>reader.readEntries(resolve,reject));if(!batch.length)break;children.push(...batch);}
  const result=[];for(const child of children)result.push(...await walk(child,path+'/'));return result;
 }
 document.addEventListener('drop',e=>{
  const entries=[...(e.dataTransfer?.items||[])].map(i=>i.webkitGetAsEntry?.()).filter(Boolean);
  if(!entries.some(i=>i.isDirectory))return;
  e.preventDefault();e.stopImmediatePropagation();document.body.classList.remove('drag-over');
  (async()=>{const files=[];for(const entry of entries)files.push(...await walk(entry));if(files.some(f=>f.relativePath.endsWith('/项目清单.json')))await restoreFiles(files);else await enqueue(files.map(f=>f.file).filter(f=>/\.(mp4|mov|mkv|webm|avi|mp3|m4a|wav|flac)$/i.test(f.name)),S.view==='music');})().catch(e=>toast(e.message));
 },true);
 document.addEventListener('change',e=>{if(e.target.id==='restore-files'){const files=[...e.target.files].map(file=>({file,relativePath:file.webkitRelativePath||file.name}));e.target.value='';if(files.length)restoreFiles(files).catch(e=>toast(e.message));}});
 return {settings,action,restoreFiles};
})();
