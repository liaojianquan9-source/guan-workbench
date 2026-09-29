const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function setup(kind='transcript',opened=true){
 const S={view:'analysis',collection:kind,collectionOpen:opened},classes=new Set();let expiry;
 const row={dataset:{subtitle:'42',cardId:'shot42',musicSection:'music42'},classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},getBoundingClientRect:()=>({top:900,bottom:960,height:60})};
 const list={scrollTop:0,scrollHeight:1800,clientHeight:400,getBoundingClientRect:()=>({top:100,bottom:500}),querySelectorAll:()=>[row]};
 const ctx={S,$:()=>list,setTimeout:fn=>{expiry=fn;return 1},clearTimeout(){}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('public/collection_link.js','utf8')+';this.link=CollectionLink;',ctx);
 return {S,row,list,classes,link:ctx.link,expire:()=>expiry()};
}
test('timeline subtitle selection reveals offscreen row in the inspector only',()=>{const h=setup();assert.equal(h.link.reveal('transcript',42),true);assert.equal(h.list.scrollTop,630);assert.ok(h.classes.has('timeline-linked'));h.expire();assert.equal(h.classes.size,0)});
test('other tabs and a closed inspector stay untouched',()=>{for(const h of [setup('shots'),setup('transcript',false)]){assert.equal(h.link.reveal('transcript',42),false);assert.equal(h.list.scrollTop,0);assert.equal(h.classes.size,0)} });
test('visible rows do not jump and a subtitle being edited remains the target',()=>{const h=setup();h.row.dataset={editingSubtitle:'42'};h.row.getBoundingClientRect=()=>({top:200,bottom:280,height:80});assert.equal(h.link.reveal('transcript',42),true);assert.equal(h.list.scrollTop,0)});
test('shot and music selections use stable IDs and missing targets do not move the list',()=>{for(const [kind,id] of [['shots','shot42'],['music','music42']]){const h=setup(kind);assert.equal(h.link.reveal(kind,'missing'),false);assert.equal(h.list.scrollTop,0);assert.equal(h.link.reveal(kind,id),true);assert.ok(h.list.scrollTop>0)}});
