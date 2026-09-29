const {test}=require('node:test'),assert=require('node:assert/strict');
const L=require('../public/clip_logic.js');
test('zooming out steps through 5 seconds, 10 seconds, 30 seconds and 1 minute',()=>{
 assert.deepEqual([6400,3200,1600,800].map(width=>L.rulerStep(337,width)),[5,10,30,60]);
});
test('labels use minutes and hours without losing precise positions',()=>{
 assert.deepEqual([0,5,30,59.9,60,90,300,300.2,3599.9,3600,3665].map(L.rulerLabel),['0s','5s','30s','59.9s','1:00','1:30','5:00','5:00.2','59:59.9','1:00:00','1:01:05']);
});
test('ruler adapts to panel resizing and maintains room for time labels',()=>{
 for(const duration of [4,337,7200,100000])for(const width of [300,800,1600,20000])assert.ok(L.rulerStep(duration,width)*width/duration>=80);
 assert.ok(L.rulerStep(337,400)>L.rulerStep(337,800));
});
