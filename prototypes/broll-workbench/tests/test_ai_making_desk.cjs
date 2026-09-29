const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../public/ai_making_desk_logic.js');
const P=require('../public/production_client.js');

const cards=[
 {id:'keep',decision:'keep',status:'draft',start:0,end:4},
 {id:'gap',decision:'gap',status:'draft',start:4,end:8},
 {id:'ready',decision:'broll',status:'draft',start:8,end:11,preview_url:'/api/files/p/x.mp4',render_fingerprint:'abc',render_report:{layout:{status:'passed'}}},
 {id:'unseen',decision:'broll',status:'draft',start:11,end:14},
 {id:'kept',decision:'keep',status:'rejected',start:14,end:18}
];

test('batch confirmation separates gaps and unseen visuals from eligible cards',()=>{
 const result=L.approveSelection({cards},cards.map(c=>c.id));
 assert.deepEqual(result.eligible,['keep','ready']);
 assert.deepEqual(result.skipped,['gap','unseen']);
 assert.deepEqual(P.batchBody({revision:5,cards},result.eligible,'approve'),{revision:5,card_ids:['keep','ready'],action:'approve'});
});
test('editor uses actual source duration and refuses overlap or invalid trims',()=>{
 const project={segments:[{start:0,end:15}],cards};
 assert.equal(L.duration(project,{metadata:{media:{duration:53.033}}}),53.033);
 assert.equal(L.within(cards[2],8.4,11.4,53.033,cards),false);
 assert.equal(L.within(cards[2],7,9,53.033,cards),true);
 assert.equal(L.within(cards[2],8,8.2,53.033,cards),false);
 assert.equal(L.within(cards[2],8,54,53.033,cards),false);
 assert.equal(L.activeCard(cards,9)?.id,'ready');
 assert.equal(L.activeCard(cards,4),undefined);
});
test('evidence resolves transcript and shared version, filters reflect persisted status',()=>{
 assert.match(L.reference('transcript:s1',[{id:'s1',start:2,text:'真实口播'}],[]),/真实口播/);
 assert.match(L.reference('asset:moon@2',[],[{id:'moon',name:'月球'}]),/月球.*2 版/);
 assert.equal(L.filter(cards,'pending').length,4);
 assert.deepEqual(L.filter(cards,'missing').map(c=>c.id),['gap']);
 assert.deepEqual(L.filter(cards,'done').map(c=>c.id),['kept']);
 assert.equal(L.status(cards[4]),'保留口播');
});
test('a delivery is offered only while its approved B-roll version is current',()=>{
 const project={cards:[{...cards[2],status:'approved',render_fingerprint:'abc'}],deliveries:[{url:'/old',cards:[{id:'ready',fingerprint:'abc'}]}]};
 assert.equal(L.matchingDelivery(project).url,'/old');
 project.cards[0]={...project.cards[0],status:'draft'};
 assert.equal(L.matchingDelivery(project),undefined);
 project.cards[0]={...project.cards[0],status:'approved',render_fingerprint:'new'};
 assert.equal(L.matchingDelivery(project),undefined);
});
