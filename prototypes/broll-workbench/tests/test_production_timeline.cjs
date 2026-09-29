const test=require('node:test');
const assert=require('node:assert/strict');
const T=require('../public/production_timeline.js');
const source={metadata:{media:{duration:53.033333,fps:'30/1'}}};
const a={id:'a',start:3,end:6,decision:'broll',status:'draft'};
const b={id:'b',start:12,end:15,decision:'broll',status:'approved'};
const project={source:{asset_id:'source',revision:1},cards:[a,b],segments:[{start:0,end:50.8}]};

test('source duration and fractional frame rates define the actual editing range',()=>{
 assert.equal(T.duration(project,source),53.033333);
 assert.equal(T.fps(source),30);
 assert.equal(T.fps({metadata:{media:{fps:'30000/1001'}}}),30000/1001);
 assert.equal(T.fps({metadata:{media:{fps:'0/0'}}}),30);
});
test('time edits reject gaps, overlap, missing source, invalid and excessive ranges',()=>{
 assert.deepEqual(T.timing(project,source,a,4,8),{start:4,end:8});
 assert.throws(()=>T.timing(project,source,{...a,decision:'gap'},4,8),/B-roll/);
 assert.throws(()=>T.timing(project,source,a,11,13),/重叠/);
 assert.throws(()=>T.timing(project,null,a,4,8),/原视频/);
 for(const range of [[NaN,5],[-1,5],[50,54],[3,3.2],[3,20]])assert.throws(()=>T.timing(project,source,a,...range));
 assert.deepEqual(T.timing({...project,cards:[a,{...b,status:'rejected'}]},source,a,11,13),{start:11,end:13});
});
test('move and trim preserve duration and stop at media boundaries',()=>{
 assert.deepEqual(T.drag(a,'move',-20,53),{start:0,end:3});
 assert.deepEqual(T.drag(a,'move',60,53),{start:50,end:53});
 assert.deepEqual(T.drag(a,'start',7,53),{start:5.6,end:6});
 assert.deepEqual(T.drag(a,'end',-8,53),{start:3,end:3.4});
 assert.deepEqual(T.drag(a,'end',40,53),{start:3,end:18});
});
test('only outputs matching the currently confirmed B-roll may be presented as current',()=>{
 const p={cards:[{...b,render_fingerprint:'one'}],deliveries:[{url:'/one',cards:[{id:'b',fingerprint:'one'}]}]};
 assert.equal(T.delivery(p).url,'/one');
 p.cards[0].status='draft';assert.equal(T.delivery(p),undefined);
 p.cards[0].status='approved';p.cards[0].render_fingerprint='two';assert.equal(T.delivery(p),undefined);
 p.deliveries.push({url:'/two',cards:[{id:'b',fingerprint:'two'}]});assert.equal(T.delivery(p).url,'/two');
 p.cards.push({...a,status:'approved',render_fingerprint:'new'});assert.equal(T.delivery(p),undefined);
});
test('mixed batch review keeps gaps and unrendered or failed layouts pending',()=>{
 const ready={...a,preview_url:'/real',render_fingerprint:'fp',render_report:{layout:{status:'passed'}}};
 const cards=[ready,{id:'keep',decision:'keep'},{id:'gap',decision:'gap'},{...b,id:'no-preview'}, {...ready,id:'bad-layout',render_report:{layout:{status:'needs_revision'}}}];
 assert.deepEqual(T.approval({cards},cards.map(c=>c.id)),{ready:['a','keep'],blocked:['gap','no-preview','bad-layout']});
});
