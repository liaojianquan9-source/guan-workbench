'use strict';
const SubtitleEditor=(()=>{
 let draft=null,busy=false;
 const owns=()=>draft?.owner===S.p?.id;
 const holdsPanel=()=>owns()&&!!$('#subtitle-edit-text');
 function row(s,index){
  if(!owns()||draft.index!==index)return `<button class="subtitle-row" data-subtitle="${index}" title="单击定位 · 双击修改文字"><time>${clock(s.start)}</time><span>${esc(s.text)}</span></button>`;
  return `<div class="subtitle-edit" data-editing-subtitle="${index}"><time>${clock(s.start)}—${clock(s.end)}</time><textarea id="subtitle-edit-text" aria-label="修改字幕文字" maxlength="5000" rows="3" ${busy?'disabled':''}>${esc(draft.text)}</textarea><div class="subtitle-edit-actions"><small>⌘ / Ctrl + Enter 保存 · Esc 取消</small><button class="button" data-subtitle-edit="cancel" ${busy?'disabled':''}>取消</button><button class="button primary" data-subtitle-edit="save" ${busy?'disabled':''}>${busy?'保存中…':'保存'}</button></div><p class="subtitle-edit-error" role="alert">${esc(draft.error||'')}</p></div>`;
 }
 function focus(){const input=$('#subtitle-edit-text');input?.focus();input?.select();input?.scrollIntoView({block:'nearest'});}
 function open(index){
  if(!S.p?.transcript?.segments?.[index])return;
  if(draft&&(draft.owner!==S.p.id||draft.index!==index)){toast('请先保存或取消正在修改的字幕。');return;}
  if(S.p.transcript.status==='processing'){toast('字幕正在识别，请完成后再修改。');return;}
  $('#video')?.pause();S.autoplay=false;
  if(!draft)draft={owner:S.p.id,index,revision:S.p.transcript.revision||0,text:S.p.transcript.segments[index].text};
  S.collection='transcript';S.collectionOpen=true;renderCollection();focus();
 }
 async function save(){
  if(!owns()||busy)return;const current=draft,input=$('#subtitle-edit-text');current.text=input?.value??current.text;
  if(!current.text.trim()){current.error='字幕不能为空。';$('.subtitle-edit-error').textContent=current.error;input?.focus();return;}
  busy=true;input.disabled=true;$$('[data-subtitle-edit]').forEach(b=>b.disabled=true);
  try{
   const result=await api(url(current.owner,'/subtitle'),{index:current.index,text:current.text,expected_revision:current.revision});
   upsert(result);if(draft===current)draft=null;
   if(S.p?.id===current.owner){renderTracks();renderCollection();paintClock();}toast('字幕已修改，导出时会使用新文字');
  }catch(error){current.error=error.message;if(owns()&&$('.subtitle-edit-error'))$('.subtitle-edit-error').textContent=current.error;else toast(error.message);}
  finally{busy=false;if(owns()&&$('#subtitle-edit-text')){$('#subtitle-edit-text').disabled=false;$$('[data-subtitle-edit]').forEach(b=>b.disabled=false);}}
 }
 function cancel(){if(busy)return;draft=null;renderCollection();}
 document.addEventListener('dblclick',e=>{const row=e.target.closest('[data-subtitle],[data-timeline-text]');if(row){e.preventDefault();open(Number(row.dataset.subtitle??row.dataset.timelineText));}});
 document.addEventListener('click',e=>{const action=e.target.closest('[data-subtitle-edit]')?.dataset.subtitleEdit;if(action==='save')save();if(action==='cancel')cancel();});
 document.addEventListener('input',e=>{if(e.target.id==='subtitle-edit-text'&&owns())draft.text=e.target.value;});
 document.addEventListener('keydown',e=>{if(e.target.id!=='subtitle-edit-text')return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();cancel();}else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();e.stopImmediatePropagation();save();}});
 return {row,holdsPanel};
})();
