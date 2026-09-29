import test from 'node:test';
import assert from 'node:assert/strict';
import {DURATION,createInitialState,activeCard,action,formatTime} from '../model.js';

test('speaking video stays beneath overlays and non-B-roll decisions never appear as overlays',()=>{
  let s=createInitialState();
  assert.equal(activeCard(s.cards,1),null);
  assert.equal(activeCard(s.cards,9.4)?.id,'d2');
  assert.equal(activeCard(s.cards,16),null);
  assert.equal(activeCard(s.cards,51),null);
  assert.equal(formatTime(DURATION),'00:53.0');
});

test('bulk review accepts matched proposals but keeps a missing asset on original footage',()=>{
  let s=createInitialState();
  s=action(s,{type:'toggleCheck',id:'d2'});
  s=action(s,{type:'toggleCheck',id:'d3'});
  s=action(s,{type:'bulk',decision:'accept'});
  assert.equal(s.cards.find(c=>c.id==='d2').status,'accepted');
  assert.equal(s.cards.find(c=>c.id==='d3').decision,'keep');
  assert.equal(s.cards.find(c=>c.id==='d3').status,'kept');
  assert.deepEqual(s.checked,[]);
  s=action(s,{type:'undo'});
  assert.equal(s.cards.find(c=>c.id==='d3').status,'missing');
  assert.deepEqual(s.checked,['d2','d3']);
  s=action(s,{type:'redo'});
  assert.equal(s.cards.find(c=>c.id==='d2').status,'accepted');
});

test('choosing a reusable style on a missing segment returns it to review',()=>{
  let s=action(createInitialState(),{type:'setStyle',id:'d3',style:'note'});
  assert.equal(s.cards.find(c=>c.id==='d3').status,'pending');
  s=action(s,{type:'setDecision',id:'d3',decision:'broll'});
  assert.equal(s.cards.find(c=>c.id==='d3').status,'accepted');
  assert.equal(activeCard(s.cards,16)?.style,'note');
});

test('moving and trimming respect footage bounds and avoid adjacent B-roll overlaps',()=>{
  let s=createInitialState();
  s=action(s,{type:'move',id:'d2',start:-5});
  assert.equal(s.cards.find(c=>c.id==='d2').start,0);
  assert.equal(s.time,.5);
  assert.equal(s.cards.find(c=>c.id==='d2').timingChanged,true);
  s=action(s,{type:'move',id:'d2',start:28});
  assert.equal(s.cards.find(c=>c.id==='d2').start,0);
  s=action(s,{type:'trim',id:'d4',edge:'left',time:34.8});
  assert.ok(s.cards.find(c=>c.id==='d4').end-s.cards.find(c=>c.id==='d4').start>=.6);
  s=action(s,{type:'trim',id:'d5',edge:'right',time:100});
  assert.equal(s.cards.find(c=>c.id==='d5').end,DURATION);
  s=action(s,{type:'undo'});
  assert.equal(s.cards.find(c=>c.id==='d5').end,46.3);
});

test('editing a previously approved segment requires review again',()=>{
  let s=action(createInitialState(),{type:'setDecision',id:'d2',decision:'broll'});
  assert.equal(s.cards.find(c=>c.id==='d2').status,'accepted');
  s=action(s,{type:'setEffect',id:'d2',field:'transition',value:'推入'});
  assert.equal(s.cards.find(c=>c.id==='d2').status,'pending');
  assert.equal(s.cards.find(c=>c.id==='d2').transition,'推入');
});
