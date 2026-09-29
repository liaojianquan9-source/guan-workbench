const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('public/workspace.js','utf8');
function harness(){
 const calls=[];
 const S={p:{id:'video',status:'ready',shots:[{}],transcript:{status:'idle'}},collectionOpen:false};
 const c={S,Clips:{browse(){}},Studio:{syncPanels(){}},writeSetting(){},renderCollection(){},renderTracks(){},refreshViews(){},url:(id,suffix)=>id+suffix,upsert:p=>{S.p=p},api:async(path,body)=>{calls.push({path,body});return S.p},begin:async kind=>calls.push(kind)};
 vm.createContext(c);
 vm.runInContext(source.slice(source.indexOf('async function startStudy('),source.indexOf('async function poll('))+source.slice(source.indexOf('async function expand('),source.indexOf('async function capture(')),c);
 return {...c,calls};
}
test('opening either track only reveals results and never starts analysis',async()=>{const h=harness();await h.expand('frames');assert.equal(h.S.collection,'shots');await h.expand('audio');assert.equal(h.S.collection,'transcript');assert.equal(h.calls.length,0)});
test('each manual text or picture command only starts that analysis',async()=>{for(const [kind,wanted] of [['scenes','scenes'],['transcript','transcript']]){const h=harness();await h.prepareAnalysis(kind);assert.deepEqual(h.calls,[wanted]);}});
test('completed or running picture and text analysis is not restarted',async()=>{for(const kind of ['scenes','transcript'])for(const status of ['ready','processing']){const h=harness();h.S.p.status=status;h.S.p.analysis=status==='ready'?{}:null;h.S.p.transcript.status=status;await h.prepareAnalysis(kind);assert.equal(h.calls.length,0)}});
test('music command requests music sections, sound retry requests only sound',async()=>{const h=harness();await h.prepareAnalysis('music');assert.equal(h.S.collection,'music');assert.equal(h.calls[0].body.task,'music_sections');await h.startStudy('video','sound');assert.equal(h.calls[1].body.task,'sound');});
