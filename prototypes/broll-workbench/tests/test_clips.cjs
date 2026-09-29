const test=require('node:test'),assert=require('node:assert/strict'),L=require('../public/clip_logic.js');
const c={start:18.2,end:26.4};
test('source seek stays inside clip and last frame never enters following shot',()=>{assert.equal(L.limit(c,0),18.2);assert.ok(L.limit(c,99)<26.4);assert.equal(L.limit(null,99),99)});
test('audio time is relative while image/note times remain source-absolute',()=>{assert.ok(Math.abs(L.relative(c,20.6)-2.4)<1e-9);assert.equal(L.relative(c,0),0);assert.ok(L.relative(c,99)<=8.2+1e-9)});
test('subtitle overlap includes text crossing either clip edge and excludes adjacent text',()=>{const segments=[{start:17,end:19},{start:20,end:21},{start:26,end:27},{start:26.4,end:29},{start:10,end:18.2}];assert.deepEqual(L.subtitles(c,segments),segments.slice(0,3))});
test('half-open clip bounds and loop threshold work at fractional frame rates',()=>{assert.equal(L.inside(c,18.2),true);assert.equal(L.inside(c,26.4),false);for(const fps of [23.976,29.97,30,60]){assert.equal(L.atEnd(c,c.end-.4/fps,fps),true);assert.equal(L.atEnd(c,c.end-1/fps,fps),false)}});

test('typed non-frame-aligned ranges seek to an included frame',()=>{const c={start:.51,end:1.01};assert.equal(L.limit(c,0,30),16/30);assert.equal(L.limit(c,99,30),1);});

test('three tracks share the same source clock and exclude frames beyond clip edges',()=>{
 const clip={start:.51,end:12};
 assert.equal(L.ratio(clip,.51),0);assert.equal(L.ratio(clip,12),1);
 assert.equal(L.point(clip,0,{fps:30,snap:false}).time,16/30);
 assert.equal(L.point(clip,1,{fps:30,snap:false}).time,359/30);
 for(const ratio of [-1,0,.2,.5,1,2]){const t=L.point(clip,ratio,{fps:30,snap:false}).time;assert.ok(t>=clip.start&&t<clip.end);}
});
test('clip zoom snapping uses visible clip duration and Alt bypass, not whole-video length',()=>{
 const clip={start:10,end:20},opts={fps:30,pixelWidth:1000,candidates:[{time:12,label:'镜头边界'},{time:25,label:'范围外'}]};
 assert.equal(L.point(clip,.205,opts).time,12);assert.equal(L.point(clip,.205,opts).snapped,true);
 assert.equal(L.point(clip,.22,opts).snapped,false);assert.equal(L.point(clip,.205,{...opts,bypass:true}).snapped,false);
});
test('filmstrip trims partial edge shots while keeping their source identity',()=>{
 const clip={start:2,end:8},shots=[{id:'a',start:0,end:3},{id:'b',start:3,end:7},{id:'c',start:7,end:10},{id:'d',start:10,end:20}];
 const spans=L.shotSpans(clip,shots);assert.deepEqual(spans.map(s=>s.id),['a','b','c']);assert.equal(spans[0].left,0);assert.equal(spans[2].left+spans[2].width,1);assert.ok(Math.abs(spans.reduce((s,t)=>s+t.width,0)-1)<1e-12);
});
