const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
class Element{
 constructor(){this.events={};this.style={};this.classList={toggle(){}};this.attributes={};this.textContent='';}
 addEventListener(k,fn){(this.events[k]??=new Set()).add(fn)} removeEventListener(k,fn){this.events[k]?.delete(fn)}
 emit(k,event={}){for(const fn of [...this.events[k]||[]])fn(event)} setAttribute(k,v){this.attributes[k]=v}getAttribute(k){return this.attributes[k]}
 hidePopover(){}focus(){}querySelector(){return new Element()}querySelectorAll(){return []}
}
function setup({playing=false,api,failProxy=false}={}){
 const video=new Element();Object.assign(video,{currentTime:7.2,paused:!playing,playbackRate:1.5,readyState:4,seeking:false,src:'/source.mp4',pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()},getAttribute(k){return k==='src'?this.src:this.attributes[k]},load(){this.paused=true;this.currentTime=0;queueMicrotask(()=>{if(failProxy&&this.src!=='/source.mp4')this.emit('error');else{this.emit('loadedmetadata');this.emit('canplay')}})}});
 const menu=new Element(),elements={'#video':video,'#player-quality-menu':menu,'#player-quality':new Element(),'#preview-quality-label':new Element(),'#preview-quality-status':new Element(),'#play-button':new Element()};
 const p={id:'p',video_url:'/source.mp4',fps:30,duration:40},S={p,position:7.2,mediaLoading:false};let syncs=0;
 const c={Object,S,$:q=>elements[q],$$:()=>[],innerWidth:1000,document:{activeElement:null},icon:()=>'',readSetting:()=>null,writeSetting(){},safeLocalUrl:value=>String(value).startsWith('/')?value:'',url:id=>'/api/'+id,api:api|| (async()=>({status:'ready',url:'/proxy.mp4'})),ClipMixer:{sync(){syncs++}},Interaction:require('../public/interaction.js'),paintClock(){},reportPlaybackError(){},toast(){},setTimeout:()=>1,clearTimeout(){}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('public/playback_preview.js','utf8')+';this.preview=PlaybackPreview;',c);c.preview.attach(video,p);
 return {video,S,elements,select:q=>menu.emit('click',{target:{closest:()=>({dataset:{previewQuality:q}})}}),syncs:()=>syncs};
}
const flush=async()=>{for(let n=0;n<12;n++)await Promise.resolve()};
test('switching a paused preview keeps frame, playback rate and source identity',async()=>{const h=setup();h.select('half');await flush();assert.equal(h.video.src,'/proxy.mp4');assert.equal(h.video.currentTime,7.2);assert.equal(h.video.playbackRate,1.5);assert.equal(h.video.paused,true);assert.equal(h.S.p.video_url,'/source.mp4');assert.equal(h.S.mediaLoading,false);});
test('switching during playback resumes and resynchronizes monitoring',async()=>{const h=setup({playing:true});h.select('quarter');await flush();assert.equal(h.video.paused,false);assert.equal(h.video.currentTime,7.2);assert.ok(h.syncs()>=2);});
test('returning to HQ prevents an older pending proxy response from taking over',async()=>{let answer;const h=setup({api:()=>new Promise(r=>answer=r)});h.select('half');h.select('original');answer({status:'ready',url:'/stale.mp4'});await flush();assert.equal(h.video.src,'/source.mp4');assert.equal(h.elements['#preview-quality-label'].textContent,'HQ');});
test('unreadable proxy falls back to HQ with the paused position intact',async()=>{const h=setup({failProxy:true});h.select('half');await flush();assert.equal(h.video.src,'/source.mp4');assert.equal(h.video.currentTime,7.2);assert.equal(h.S.mediaLoading,false);assert.equal(h.video.paused,true);});
test('an old response cannot replace video after changing projects',async()=>{let answer;const h=setup({api:()=>new Promise(r=>answer=r)});h.select('half');h.S.p={id:'other',video_url:'/other.mp4'};answer({status:'ready',url:'/stale.mp4'});await flush();assert.equal(h.video.src,'/source.mp4');assert.equal(h.S.p.video_url,'/other.mp4');});
