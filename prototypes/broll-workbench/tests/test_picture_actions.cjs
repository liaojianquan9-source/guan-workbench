const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function setup(){
 let click,locked=false,selection=[];const calls=[],errors=[];
 const p={id:'p',revision:8,shots:[{id:'a',start:0,end:3},{id:'b',start:3,end:6}],storyboard_history:[]};
 const S={p,projects:[p],position:2};
 const ctx={S,crypto:{},LapianInteraction:{SingleFlight:class{run(key,fn){return fn()}}},ClipMixer:{state:()=>({tracks:{original:{locked}}})},ClipTimeline:{paint(){},mergeSelection:()=>selection,startMerge(){calls.push('select')},clearMerge(){selection=[]}},document:{addEventListener(name,fn){if(name==='click')click=fn}},window:{addEventListener(){}},$:()=>null,current:()=>p.shots[0],url:(id,path)=>id+path,api:async(path,body)=>{calls.push({path,body});return {...p,storyboard_history:[{id:'op'}]}},upsert:next=>{S.p=next},renderTracks(){},refreshViews(){},toast(){},modalError:e=>errors.push(e.message)};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('public/clips.js','utf8'),ctx);
 return {S,calls,errors,lock(){locked=true},select(ids){selection=ids},async click(action){const el={dataset:{clipAction:action},disabled:false};click({target:{closest:()=>el}});await new Promise(r=>setImmediate(r));}};
}
test('scissors cuts the picture at the playhead without creating research data',async()=>{const h=setup();await h.click('split-picture');assert.equal(h.calls[0].path,'p/storyboard');assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].body)),{action:'split',expected_revision:8,id:'a',time:2});});
test('merge uses the two visually selected shot IDs',async()=>{const h=setup();h.select(['a','b']);await h.click('open-merge');assert.equal(h.calls[0].body.action,'merge');assert.equal(h.calls[0].body.id,'a');assert.equal(h.calls[0].body.next_id,'b');});
test('merge without a Shift selection leaves the timeline unchanged',async()=>{const h=setup();await h.click('open-merge');assert.deepEqual(h.calls,[]);});
test('picture lock prevents cut and merge',async()=>{const h=setup();h.lock();await h.click('split-picture');await h.click('open-merge');assert.equal(h.calls.length,0);assert.equal(h.errors.length,2);});
