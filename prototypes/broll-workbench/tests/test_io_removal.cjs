const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');

const read=path=>fs.readFileSync(path,'utf8');

test('manual I/O controls, state and actions stay removed from the active frontend',()=>{
  const workspace=read('public/workspace.js');
  const clips=read('public/clips.js');
  const timeline=read('public/clip_timeline.js');
  const interaction=read('public/interaction.js');
  const active=[workspace,clips,timeline,interaction].join('\n');

  assert.doesNotMatch(active,/S\.(?:in|out)\b/);
  assert.doesNotMatch(active,/mark-(?:in|out)|clear-range|export-audio|source-range-handle|timeline-io|io-range-status|rangeEndpoint/);
  assert.match(workspace,/const defaults=\{capture:'e',back:'j',forward:'l',play:'k'\}/);
  assert.match(workspace,/startsWith\('lapian:selection:'\)/);
  assert.match(timeline,/tool\('在当前画面切开分镜','split-picture'/);
  assert.match(timeline,/clip-playback-range/);
});

test('saved clip and music playback use object-owned bounds, not global markers',()=>{
  const clips=read('public/clips.js');
  const music=read('public/music_sections.js');

  assert.match(clips,/function playbackBounds\(\).*return audition\|\|\(c\?\{start:c\.start,end:c\.end\}:null\)/);
  assert.match(music,/Clips\.startAudition\(s\.start,s\.end\)/);
  assert.doesNotMatch(music,/S\.(?:in|out)\b|rememberSelection|clearRange/);
});

test('legacy audio assets remain readable while the manual generator is absent',()=>{
  const workspace=read('public/workspace.js');
  const server=read('server.py');

  assert.match(workspace,/audio_clips/);
  assert.match(server,/audio\/\[a-f0-9\]\{32\}\\\.m4a/);
  assert.doesNotMatch(server,/def audio\s*\(/);
  assert.doesNotMatch(server,/\|audio\|/);
});
