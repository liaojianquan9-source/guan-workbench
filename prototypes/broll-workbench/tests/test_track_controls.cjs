const test=require('node:test'),assert=require('node:assert/strict'),L=require('../public/track_logic.js');
const all=L.kinds;
test('opening a clip monitors only original and all controls have explicit defaults',()=>{
 const s=L.normalize();assert.equal(s.solo,'original');assert.deepEqual(L.audible(s,all),['original']);
 for(const k of all)assert.deepEqual(s.tracks[k],{locked:false,hidden:false,muted:false,gainDb:0});
});
test('solo is exclusive and turning it off restores per-track mute choices',()=>{
 let s=L.normalize();s=L.toggle(s,'background','muted');
 s=L.toggle(s,'vocals','solo');assert.deepEqual(L.audible(s,all),['vocals']);
 s=L.toggle(s,'vocals','solo');assert.equal(s.solo,null);assert.deepEqual(L.audible(s,all),['vocals']);
 assert.equal(s.tracks.background.muted,true);
});
test('mute, solo and master mute route every combination without overriding mute',()=>{
 for(const solo of [null,...all])for(let bits=0;bits<8;bits++)for(const master of [false,true]){
  const s=L.normalize({solo});all.forEach((k,i)=>s.tracks[k].muted=!!(bits&(1<<i)));
  const heard=L.audible(s,all,master);
  assert.deepEqual(heard,master?[]:all.filter((k,i)=>!(bits&(1<<i))&&(solo?solo===k:k!=='original')));
  assert.ok(!(heard.includes('original')&&heard.some(k=>k!=='original')));
 }
});
test('hidden and locked tracks keep their sound, while lock protects shared edits',()=>{
 let s=L.normalize({solo:'vocals'});s=L.toggle(s,'vocals','hidden');s=L.toggle(s,'vocals','locked');
 assert.deepEqual(L.audible(s,all),['vocals']);assert.deepEqual(L.locked(s),['vocals']);
 s=L.toggle(s,'vocals','locked');assert.deepEqual(L.locked(s),[]);
});
test('missing or unavailable audio never falls back to a different track',()=>{
 const s=L.normalize({solo:'vocals'});assert.deepEqual(L.audible(s,['original']),[]);assert.deepEqual(L.audible(s,[]),[]);
});
test('controls are isolated and saved settings are validated without mutating input',()=>{
 const source=L.normalize();const next=L.toggle(source,'vocals','muted');assert.equal(source.tracks.vocals.muted,false);assert.equal(next.tracks.vocals.muted,true);
 assert.deepEqual(L.normalize(JSON.parse(JSON.stringify(next))),next);
 assert.equal(L.normalize({solo:'invalid',tracks:{original:{muted:'false'}}}).solo,'original');assert.equal(L.normalize({tracks:{original:{muted:'true'}}}).tracks.original.muted,false);
});

test('muting both separated tracks stays silent instead of bringing back original',()=>{let s=L.normalize({solo:null});s=L.toggle(s,'vocals','muted');s=L.toggle(s,'background','muted');assert.deepEqual(L.audible(s,all),[]);assert.deepEqual(L.audible(s,['original']),['original']);});
