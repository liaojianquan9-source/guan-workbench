const test=require('node:test');
const assert=require('node:assert/strict');
const {formatTime,frameTime,shotIndexAt,adjacentCutTime,snapTime,zoomScroll,SingleFlight}=require('../public/interaction.js');
const args={fps:30,duration:12,pixelWidth:600,candidates:[{time:5.133333,label:'镜头边界'},{time:6.833333,label:'镜头边界'}]};

test('jumping one frame before a cut reaches that cut without skipping it or adding a frame',()=>{
 const shots=[{start:0,end:5.133333},{start:5.133333,end:6.833333},{start:6.833333,end:12}];
 assert.equal(adjacentCutTime(shots,153/30,1,30,12),154/30);
 assert.equal(adjacentCutTime(shots,154/30,1,30,12),205/30);
 assert.equal(adjacentCutTime(shots,155/30,-1,30,12),154/30);
 assert.equal(adjacentCutTime(shots,154/30,-1,30,12),0);
 assert.equal(adjacentCutTime(shots,0,-1,30,12),0);
 assert.equal(adjacentCutTime(shots,11,1,30,12),359/30);
});
test('rounded cut timestamps select the correct shot at fractional frame rates',()=>{
 for(const fps of [23.976,29.97,30,30.000003708,60,120]){
  const cut=Number((154/fps).toFixed(6)),shots=[{start:0,end:cut},{start:cut,end:300/fps}];
  assert.equal(shotIndexAt(shots,153/fps,fps),0);
  assert.equal(shotIndexAt(shots,154/fps,fps),1);
  assert.equal(adjacentCutTime(shots,153/fps,1,fps,300/fps),154/fps);
 }
 assert.equal(shotIndexAt([],0,30),-1);
});

test('time display carries minute boundaries without ever showing 00:60.00',()=>{
 assert.equal(formatTime(59.999),'01:00.00');assert.equal(formatTime(59.97),'00:59.97');
 assert.equal(formatTime(-3),'00:00.00');assert.equal(formatTime(Infinity),'00:00.00');
});

test('near a cut snaps to its frame; Alt and free mode retain the chosen frame',()=>{
 const near=snapTime({...args,time:5.2});
 assert.equal(near.snapped,true);assert.equal(near.time,154/30);
 assert.equal(snapTime({...args,time:5.2,bypass:true}).time,5.2);
 assert.equal(snapTime({...args,time:5.2,enabled:false}).snapped,false);
 assert.equal(snapTime({...args,time:5.6}).snapped,false);
});
test('snap is bounded by both screen distance and time; nearest boundary wins',()=>{
 assert.equal(snapTime({...args,time:5.2,pixelWidth:6000}).snapped,false);
 assert.equal(snapTime({...args,duration:3600,pixelWidth:300,time:5.6}).snapped,false);
 const result=snapTime({...args,time:5.21,candidates:[{time:5.133333,label:'cut'},{time:5.233333,label:'note'}]});
 assert.equal(result.label,'note');assert.equal(result.time,157/30);
});
test('seek positions never pass the last frame while explicit boundaries can reach media end',()=>{
 assert.equal(frameTime(-20,30,12),0);assert.equal(frameTime(99,30,12),359/30);
 assert.equal(frameTime(12,30,12,true),12);
 assert.equal(frameTime(337.066667,30,337.066667),10111/30);
 assert.equal(frameTime(1,30,.02),0);
});
test('zoom preserves visible playhead screen position and otherwise the visible midpoint',()=>{
 const left=zoomScroll({oldWidth:1200,newWidth:2400,scrollLeft:300,viewport:600,anchorTime:6,duration:12});
 assert.equal(left,900);assert.equal(6/12*2400-left,300);
 assert.equal(zoomScroll({oldWidth:1200,newWidth:2400,scrollLeft:600,viewport:600,anchorTime:0,duration:12}),1500);
});
test('rapid duplicate saves share one operation; different projects are independent',async()=>{
 let release,calls=0;
 const guard=new SingleFlight();
 const work=()=>{calls++;return new Promise(resolve=>release=resolve)};
 const a=guard.run('A:capture',work),b=guard.run('A:capture',work);
 await Promise.resolve();assert.equal(calls,1);release('saved');assert.deepEqual(await Promise.all([a,b]),['saved','saved']);
 await guard.run('B:capture',()=>++calls);assert.equal(calls,2);
});
test('double click cooldown suppresses duplicate output and failures allow retry',async()=>{
 let now=0,calls=0;const guard=new SingleFlight(()=>now),work=()=>++calls;
 await guard.run('save',work,500);await guard.run('save',work,500);assert.equal(calls,1);
 now=501;await guard.run('save',work,500);assert.equal(calls,2);
 await assert.rejects(guard.run('retry',()=>Promise.reject(new Error('offline')),500));
 assert.equal(await guard.run('retry',()=>42,500),42);
});
