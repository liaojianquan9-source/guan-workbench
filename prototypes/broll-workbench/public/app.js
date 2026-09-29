"use strict";
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Restored project folders are untrusted input. Validate values again at the
// browser boundary before they become URLs, filenames or DOM identifiers.
function safeLocalUrl(value){
 const raw=String(value??'').trim();if(!raw)return '';
 try{const base=new URL(location.href),candidate=new URL(raw,base);return ['http:','https:'].includes(candidate.protocol)&&candidate.origin===base.origin?raw:'';}catch{return ''}
}
function safeDownloadName(value){const cleaned=String(value??'').replace(/[\u0000-\u001f\u007f/\\:]/g,'-').trim().slice(0,240);return cleaned&&/[^.-]/.test(cleaned)?cleaned:'download'}
const domId=value=>'i-'+[...String(value??'')].map(c=>c.codePointAt(0).toString(16)).join('-');
const symbols = {
 film:'M4 4h16v16H4zM4 9h16M4 15h16M8 4v16M16 4v16',copy:'M8 8h12v12H8zM4 16V4h12',edit:'m15 4 5 5M3 21l5-1L21 7l-5-5L3 15z',folder:'M3 6h7l2 2h9v12H3zM3 6V4h7l2 2',plus:'M12 5v14M5 12h14',search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',play:'m8 5 11 7-11 7V5',pause:'M8 5v14M16 5v14',prev:'M5 5v14m14-14-10 7 10 7V5',next:'M19 5v14M5 5l10 7L5 19V5',frameprev:'M5 5v14M19 5l-9 7 9 7V5',framenext:'M19 5v14M5 5l9 7-9 7V5',camera:'M3 7h5l2-3h4l2 3h5v13H3V7m13 6a4 4 0 1 0-8 0 4 4 0 0 0 8 0',note:'M4 3h16v14l-4 4H4V3m4 5h8m-8 4h8m-8 4h4',download:'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',volume:'M3 9h4l5-4v14l-5-4H3V9m13-1a6 6 0 0 1 0 8',info:'M12 16v-5M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',refresh:'M20 8a8 8 0 1 0 0 8M20 3v5h-5',loop:'M4 7h12l4 4M20 7v4h-4M20 17H8l-4-4M4 17v-4h4',check:'m5 12 4 4L19 6',arrow:'M5 12h14M13 6l6 6-6 6',close:'M5 5l14 14M19 5 5 19'
};
const icon = name => `<svg aria-hidden="true" viewBox="0 0 24 24">${window.STUDIO_ICONS?.[name] || `<path d="${symbols[name] || symbols.info}"/>`}</svg>`;
const button = (label,action,kind='',glyph='',disabled=false) => `<button class="button ${kind}" data-action="${action}" ${disabled?'disabled':''}>${glyph?icon(glyph):''}${label}</button>`;
const ib = (label,action,glyph) => `<button class="icon-btn" data-action="${action}" title="${esc(label)}" aria-label="${esc(label)}">${icon(glyph)}</button>`;

Object.assign(symbols,{music:'M9 18V5l11-2v13M9 15c-6-1-7 6-2 5 2 0 2-2 2-3m11-5c-6-1-7 6-2 5 2 0 2-2 2-3',grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',more:'M5 12h.1M12 12h.1M19 12h.1',expand:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',chevron:'m8 4 8 8-8 8',trash:'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',filter:'M4 6h16M7 12h10M10 18h4',tag:'M3 3h8l10 10-8 8L3 11V3m4 4h.1',audio:'M3 10v4m4-8v12m5-16v20m5-16v12m4-8v4',menu:'M4 6h16M4 12h16M4 18h16'});
Object.assign(symbols,{layers:'M12 2 2 7l10 5 10-5-10-5M2 12l10 5 10-5M2 17l10 5 10-5',columns:'M4 4h16v16H4zM12 4v16',blend:'M12 3a9 9 0 1 0 0 18A9 9 0 0 0 12 3m0 0a9 9 0 0 1 0 18',scan:'M4 7V4h3m10 0h3v3M4 17v3h3m10 0h3v-3M8 12h8',diff:'M4 6h16M4 18h16M8 3v6m8 6v6'});
const clock=v=>LapianInteraction.formatTime(v);
const size=v=>v>=1073741824?`${(v/1073741824).toFixed(1)} GB`:`${(v/1048576).toFixed(1)} MB`;
function systemUsageLabel(usage){const raw=usage?.memory_bytes,bytes=Number(raw);return usage?.available&&raw!==null&&raw!==undefined&&Number.isFinite(bytes)&&bytes>=0?`约 ${size(bytes)}`:'暂时无法读取'}
async function api(url,body,method){const r=await fetch(url,body===undefined?{}:{method:method||'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let d;try{d=await r.json()}catch{throw new Error('本机服务连接中断，请确认服务仍在运行。')}if(!r.ok){const e=new Error(d.error||'操作未完成');e.status=r.status;throw e}return d}
const url=(id,suffix='')=>`/api/projects/${encodeURIComponent(id)}${suffix}`;
function readSetting(k,fallback){try{return JSON.parse(localStorage.getItem('lapian:'+k))??fallback}catch{return fallback}}
function writeSetting(k,v){try{localStorage.setItem('lapian:'+k,JSON.stringify(v))}catch{}}
let toastTimer;
function toast(text,undo){const target=$('#toast');target.textContent=text;target.classList.add('visible');clearTimeout(toastTimer);if(undo){const b=document.createElement('button');b.className='undo-button';b.textContent='撤销';b.addEventListener('click',async()=>{if(b.disabled)return;b.disabled=true;clearTimeout(toastTimer);try{await undo();toast('已撤销')}catch(error){toast(error.message)}});target.append(b)}toastTimer=setTimeout(()=>target.classList.remove('visible'),undo?12000:4500)}
function download(href,name){const source=safeLocalUrl(href);if(!source){toast('这个文件地址无效，已阻止打开。');return false}const a=document.createElement('a');a.href=source;a.download=safeDownloadName(name);document.body.append(a);a.click();a.remove();return true}
function safeLink(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?u.href:''}catch{return ''}}
