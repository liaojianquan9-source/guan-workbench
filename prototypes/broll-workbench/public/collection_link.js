'use strict';
// Explicit timeline selections reveal only the matching, already-open collection.
const CollectionLink=(()=>{
 let highlighted=null,timer=null;
 function reveal(kind,id){
  if(S.view!=='analysis'||!S.collectionOpen||S.collection!==kind)return false;
  const list=$('#collection-list');if(!list)return false;
  const field={transcript:'subtitle',shots:'cardId',music:'musicSection'}[kind];
  const selector={transcript:'[data-subtitle],[data-editing-subtitle]',shots:'[data-card-id]',music:'.music-section-row[data-music-section]'}[kind];
  if(!selector)return false;
  const row=[...list.querySelectorAll(selector)].find(el=>String(el.dataset[field]??el.dataset.editingSubtitle)===String(id));
  if(!row)return false;
  clearTimeout(timer);highlighted?.classList.remove('timeline-linked');highlighted=row;row.classList.add('timeline-linked');
  const box=list.getBoundingClientRect(),item=row.getBoundingClientRect();
  if(item.top<box.top+8||item.bottom>box.bottom-8){
   list.scrollTop=Math.max(0,Math.min(list.scrollHeight-list.clientHeight,list.scrollTop+item.top-box.top-(list.clientHeight-item.height)/2));
  }
  timer=setTimeout(()=>{row.classList.remove('timeline-linked');if(highlighted===row)highlighted=null;},1800);
  return true;
 }
 return {reveal};
})();
