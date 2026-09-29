const test=require('node:test'),assert=require('node:assert/strict'),L=require('../public/clip_logic.js');
const clip=(id,start,end)=>({id,start,end,sound:{files:{vocals:{id:id+'v'},background:{id:id+'b'}}}});
test('saved stems remain available without selecting a research clip',()=>{
 const c=clip('a',.5,12),r=L.soundRegions([c]);
 assert.equal(L.soundAt(r,3),c);assert.equal(L.soundAt(r,12),null);assert.equal(L.soundAt(r,0),null);
});
test('source-aligned regions preserve gaps and do not extend stem audio beyond its range',()=>{
 const a=clip('a',.5,12),b=clip('b',20,25),r=L.soundRegions([a,b]);
 assert.deepEqual(r.map(({start,end})=>[start,end]),[[.5,12],[20,25]]);
 for(const t of [0,12,15,25,40])assert.equal(L.soundAt(r,t),null);
 assert.equal(L.relative(L.soundAt(r,21),21),1);
});
test('overlapping results choose one consistent waveform and audio source, preferring selection',()=>{
 const a=clip('a',0,20),b=clip('b',5,10);
 assert.deepEqual(L.soundRegions([a,b]).map(r=>[r.start,r.end,r.clip.id]),[[0,5,'a'],[5,10,'b'],[10,20,'a']]);
 assert.deepEqual(L.soundRegions([a,b],'a').map(r=>[r.start,r.end,r.clip.id]),[[0,20,'a']]);
 assert.equal(L.soundAt(L.soundRegions([a,b]),10),a);
});
test('deleted clips, pending separations and old-range history do not appear on live tracks',()=>{
 const ready=clip('a',0,4),deleted={...clip('b',10,20),deleted:true},pending={id:'c',start:20,end:30,sound:{status:'processing',files:{}},sound_history:[clip('old',20,30).sound]};
 assert.deepEqual(L.soundRegions([pending,deleted,ready]).map(r=>r.clip.id),['a']);
});

const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function mixerHarness(){
 const makeMedia=()=>({currentTime:0,readyState:4,paused:true,muted:false,volume:.7,playbackRate:1,addEventListener(){},pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},load(){},removeAttribute(){this.src=null;}});
 const video=makeMedia(),vocals=makeMedia(),background=makeMedia();let active=null;
 const a=clip('a',.5,12),b=clip('b',20,25);
 for(const c of [a,b])for(const k of ['vocals','background'])c.sound.files[k].url=`/${c.id}-${k}`;
 const context={S:{p:{id:'project',has_audio:true,research_clips:[a,b]},position:0},Clips:{active:()=>active,paintToolbar(){}},TrackLogic:require('../public/track_logic.js'),ClipLogic:L,ClipTimeline:{paint(){}},GainLogic:require('../public/audio_gain.js'),AudioGain:{apply(){},release(){},resume:()=>Promise.resolve()},readSetting:()=>null,writeSetting(){},safeLocalUrl:value=>String(value).startsWith('/')?value:'',toast(){},$:selector=>({'#clip-vocals':vocals,'#clip-background':background,'.player-stage':{classList:{toggle(){},remove(){}}}}[selector]||null)};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../public/clip_mixer.js'),'utf8')+'\nthis.mixer=ClipMixer;',context);
 const mixer=context.mixer;mixer.attach(video);
 return {mixer,video,vocals,background,select:c=>active=c,a,b};
}
test('source transport can solo stems without entering a clip and routes each file at its own offset',()=>{
 const {mixer,video,vocals}=mixerHarness();video.currentTime=5;video.paused=false;mixer.control('vocals','solo');
 assert.equal(video.muted,true);assert.equal(vocals.src,'/a-vocals');assert.equal(vocals.currentTime,4.5);assert.equal(vocals.muted,false);
 video.currentTime=21;mixer.sync();assert.equal(vocals.src,'/b-vocals');assert.equal(vocals.currentTime,1);
});
test('crossing a separated region end stops stem playback without restarting the selected clip',()=>{
 const {mixer,video,vocals,select,a}=mixerHarness();select(a);video.currentTime=11.9;video.paused=false;mixer.control('vocals','solo');
 video.currentTime=12;mixer.sync();assert.equal(vocals.paused,true);assert.equal(vocals.src,null);assert.equal(video.currentTime,12);assert.equal(video.muted,true);
 video.currentTime=14.9;mixer.sync();assert.equal(vocals.paused,true);assert.deepEqual(Array.from(mixer.audible()),[]);
});
test('selection and deselection keep source-wide monitoring, mute, lock and visibility settings',()=>{
 const {mixer,video,select,a}=mixerHarness();video.currentTime=3;mixer.control('background','solo');mixer.control('vocals','locked');
 select(a);mixer.sync();select(null);mixer.sync();assert.equal(mixer.state().solo,'background');assert.equal(mixer.state().tracks.vocals.locked,true);
 mixer.toggleMaster();assert.deepEqual(Array.from(mixer.audible()),[]);
});
test('whole-source stems fill gaps and survive saved storyboard removal',()=>{
 const source={...clip('source',0,337),scope:'source'},saved=clip('saved',0,12);
 const regions=L.soundRegions([source,saved]);
 assert.deepEqual(regions.map(r=>[r.start,r.end,r.clip.id]),[[0,12,'saved'],[12,337,'source']]);
 saved.deleted=true;
 assert.deepEqual(L.soundRegions([source,saved]).map(r=>[r.start,r.end,r.clip.id]),[[0,337,'source']]);
 assert.equal(L.relative(L.soundAt(L.soundRegions([source,saved]),125),125),125);
});

test('disabling solo mixes only stems and switching to original stops both stems',async()=>{const {mixer,video,vocals,background}=mixerHarness();video.currentTime=5;video.paused=false;mixer.control('original','solo');await Promise.resolve();assert.equal(video.muted,true);assert.equal(vocals.paused,false);assert.equal(background.paused,false);assert.deepEqual(Array.from(mixer.audible()),['vocals','background']);mixer.control('original','muted');assert.equal(video.muted,false);assert.equal(vocals.paused,true);assert.equal(background.paused,true);assert.deepEqual(Array.from(mixer.audible()),['original']);});
test('per-track gain clamps, resets and respects track locking without changing solo',()=>{const {mixer,video}=mixerHarness();video.currentTime=5;mixer.control('background','solo');mixer.setGain('background',6);assert.equal(mixer.state().tracks.background.gainDb,6);assert.equal(mixer.state().tracks.vocals.gainDb,0);assert.equal(mixer.state().solo,'background');mixer.setGain('background',100);assert.equal(mixer.state().tracks.background.gainDb,12);mixer.control('background','locked');assert.equal(mixer.setGain('background',0),false);assert.equal(mixer.state().tracks.background.gainDb,12);mixer.control('background','locked');mixer.setGain('background',0);assert.equal(mixer.state().tracks.background.gainDb,0);});
