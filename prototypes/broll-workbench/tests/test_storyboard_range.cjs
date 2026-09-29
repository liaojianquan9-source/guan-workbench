const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
function harness(){
 const original={id:'existing',revision:2,start:1,end:4,sound:{}};
 const project={id:'p',duration:20,fps:30,next_clip_number:2,research_clips:[original]};
 const video={currentTime:2,paused:true,pause(){this.paused=true},play(){this.paused=false;return Promise.resolve()}};
 const S={p:project,position:2,collection:'shots'};const calls=[];
 const context={S,LapianInteraction:{SingleFlight:class{}},ClipLogic:require('../public/clip_logic.js'),ClipMixer:{assertEditable(){},stop(){},activate(){},sync(){},state:()=>({tracks:{original:{locked:false}}})},ClipTimeline:{paint(){},mergeSelection:()=>[]},Studio:{toolbar:()=>'',syncPanels(){}},document:{addEventListener(){}},window:{addEventListener(){}},$:selector=>selector==='#video'?video:null,$$:()=>[],readSetting:()=>({}),writeSetting(){},seek:t=>{S.position=t;video.currentTime=t},renderTracks(){},renderCollection(){},refreshViews(){},toast(){},url:(id)=>id,upsert:p=>{if(S.p.id===p.id)S.p=p},api:async(owner,body)=>{calls.push({owner,body});return{project}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('public/clips.js','utf8')+';this.Clips=Clips;',context);
 return {S,video,calls,Clips:context.Clips};
}
test('choosing a saved research clip derives playback bounds from its own data',()=>{const h=harness();h.Clips.choose('existing');assert.equal(h.calls.length,0);assert.equal(h.Clips.active().id,'existing');assert.deepEqual(JSON.parse(JSON.stringify(h.Clips.playbackBounds())),{start:1,end:4});});
test('saved clip playback starts inside the clip and stops on its final frame',()=>{const h=harness();h.Clips.choose('existing');h.video.currentTime=8;h.Clips.beforePlay();assert.equal(h.video.currentTime,1);h.video.paused=false;h.video.currentTime=4.01;h.Clips.sync();assert.equal(h.video.paused,true);assert.ok(h.video.currentTime<4&&h.video.currentTime>=3.96);assert.equal(h.calls.length,0);});
test('returning to the clip list clears the active playback bound',()=>{const h=harness();h.Clips.choose('existing');h.Clips.browse();assert.equal(h.Clips.active(),null);assert.equal(h.Clips.playbackBounds(),null);assert.equal(h.calls.length,0);});
test('clicking a source shot only locates it and never creates a research record',()=>{const h=harness();h.Clips.choose('existing');h.Clips.chooseShot({id:'shot',start:7,end:9});assert.equal(h.S.position,7);assert.equal(h.Clips.active(),null);assert.equal(h.Clips.playbackBounds(),null);assert.equal(h.calls.length,0);});
test('music audition temporarily overrides a selected clip and clears after stopping',()=>{const h=harness();h.Clips.choose('existing');h.Clips.startAudition(6,8);assert.deepEqual(JSON.parse(JSON.stringify(h.Clips.playbackBounds())),{start:6,end:8});h.video.paused=false;h.video.currentTime=8.01;h.Clips.sync();assert.equal(h.video.paused,true);assert.equal(h.Clips.isAuditioning(),false);assert.deepEqual(JSON.parse(JSON.stringify(h.Clips.playbackBounds())),{start:1,end:4});});
test('bounded playback tolerates media timestamp rounding without repeated seeking',()=>{const h=harness();h.Clips.choose('existing');h.video.paused=false;let seeks=0;Object.defineProperty(h.video,'currentTime',{get:()=>.999995,set:()=>{seeks++}});h.Clips.sync();h.Clips.sync();assert.equal(seeks,0);assert.equal(h.video.paused,false);});
