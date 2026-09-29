'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function securityHelpers(){
 const context={URL,location:{href:'http://127.0.0.1:8765/?view=library'},window:{}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('public/app.js','utf8')+';this.helpers={esc,safeLocalUrl,safeDownloadName,domId,systemUsageLabel};',context);
 return context.helpers;
}

test('local media URLs reject script, data and foreign origins',()=>{
 const {safeLocalUrl}=securityHelpers();
 assert.equal(safeLocalUrl('/media/abc/source.mp4'),'/media/abc/source.mp4');
 assert.equal(safeLocalUrl('http://127.0.0.1:8765/music-media/a.m4a'),'http://127.0.0.1:8765/music-media/a.m4a');
 for(const unsafe of ['javascript:alert(1)','data:text/html,<script>alert(1)</script>','https://example.com/file.mp4','//example.com/file.mp4'])assert.equal(safeLocalUrl(unsafe),'');
});

test('download names cannot inject a drag payload or filesystem path',()=>{
 const {safeDownloadName}=securityHelpers();
 assert.equal(safeDownloadName('../bad:\\name\r\ntext.jpg'),'..-bad--name--text.jpg');
 assert.equal(safeDownloadName('\0\n'),'download');
 assert.equal(safeDownloadName('normal 画面.jpg'),'normal 画面.jpg');
});

test('DOM identifiers are deterministic and contain selector-safe characters only',()=>{
 const {domId}=securityHelpers(),hostile='x\" autofocus onfocus=alert(1)';
 assert.match(domId(hostile),/^[a-z0-9-]+$/);
 assert.equal(domId(hostile),domId(hostile));
 assert.notEqual(domId(hostile),domId('different'));
});

test('memory usage is shown in MB or GB and remains safe when unavailable',()=>{
 const {systemUsageLabel}=securityHelpers();
 assert.equal(systemUsageLabel({available:true,memory_bytes:50*1024*1024}),'约 50.0 MB');
 assert.equal(systemUsageLabel({available:true,memory_bytes:2*1024*1024*1024}),'约 2.0 GB');
 assert.equal(systemUsageLabel({available:true,memory_bytes:null}),'暂时无法读取');
 assert.equal(systemUsageLabel({available:false,memory_percent:null,memory_bytes:null}),'暂时无法读取');
});

test('rendered clip metadata cannot break out of attributes or create active URLs',()=>{
 const h=securityHelpers(),listeners=[];
 const context={...h,S:{projects:[],p:null},document:{addEventListener:(...args)=>listeners.push(args),querySelector:()=>null},window:{addEventListener(){}},innerWidth:1200,innerHeight:800,
  titleOf:p=>p.name,clock:n=>String(n),icon:()=>'',chipList:()=>'',iconAction:()=>'',safeLink:()=>'',readSetting:()=>null,writeSetting(){},Clips:{active:()=>null},$:()=>null,$$:()=>[],renderCollection(){},refreshViews(){},toast(){},api(){},url(){}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('public/studio.js','utf8')+';this.Studio=Studio;',context);
 const attack='x\" autofocus onfocus=alert(1)';
 const project={id:'a'.repeat(32),name:'safe.mp4',duration:10,created_at:'2026-01-01',shots:[{start:0,end:10,thumbnail_url:'javascript:alert(1)'}],research_clips:[]};
 const clip={id:attack,title:'clip',start:0,end:1,created_at:'2026-01-01',frames:[]};
 const html=context.Studio.clipCard(clip,project,true);
 assert.doesNotMatch(html,/"\s+onfocus=/i);
 assert.doesNotMatch(html,/javascript:/i);
 assert.match(html,/data-studio-clip="x&amp;quot;|data-studio-clip="x&quot;/);
});

test('restored shot IDs, titles, numbers and media URLs stay inert in scene cards',()=>{
 const h=securityHelpers(),source=fs.readFileSync('public/workspace.js','utf8');
 const project={id:'a'.repeat(32),name:'safe.mp4',source:{title:'safe'},created_at:'2026-01-01',captures:[],shots:[]};
 const attack='x\" onfocus=alert(1)',item={id:attack,projectId:project.id,kind:'scene',title:'</button><img src=x onerror=alert(1)>',number:'</span><script>alert(1)</script>',start:0,end:1,time:0,url:'javascript:alert(1)'};project.shots=[item];
 const context={...h,S:{projects:[project],p:project,position:0,sceneNoteEdit:null},Studio:{cardDate:()=>''},titleOf:p=>p.source?.title||p.name,clock:n=>String(n),icon:()=>'',current:()=>item};
 vm.createContext(context);
 const fragment=source.slice(source.indexOf('function shotName('),source.indexOf('function sceneNoteDraftKey('));
 vm.runInContext(fragment+';this.sceneCard=sceneCard;',context);
 const html=context.sceneCard(item);
 assert.doesNotMatch(html,/javascript:/i);
 assert.doesNotMatch(html,/"\s+(?:onfocus|onerror)=/i);
 assert.doesNotMatch(html,/<script|<img src=x/i);
 assert.match(html,/&lt;\/button&gt;/);
});

test('every new-window link explicitly severs its opener',()=>{
 const source=fs.readdirSync('public').filter(name=>name.endsWith('.js')).map(name=>fs.readFileSync('public/'+name,'utf8')).join('\n');
 for(const tag of source.match(/<a\b[^>]*target="_blank"[^>]*>/g)||[])assert.match(tag,/rel="[^"]*noopener[^"]*"/);
});

test('the page enforces a script policy that blocks inline injected handlers',()=>{
 const html=fs.readFileSync('public/index.html','utf8');
 const policy=html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/i)?.[1]||'';
 assert.match(policy,/script-src 'self'/);
 assert.doesNotMatch(policy,/script-src[^;]*'unsafe-inline'/);
 assert.match(policy,/object-src 'none'/);
 assert.match(policy,/base-uri 'none'/);
});
