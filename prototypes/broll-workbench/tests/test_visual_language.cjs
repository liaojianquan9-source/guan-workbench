'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const index = fs.readFileSync(path.join(root, 'public/index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'public/visual-language.css'), 'utf8');

test('the workbench loads the visual language after the view styles and not the demo shell', () => {
  const links = [...index.matchAll(/href="([^"]+\.css)"/g)].map(match => match[1]);
  assert.deepEqual(links, [
    'workspace.css',
    'clips.css',
    'studio.css',
    'replica.css',
    'ai_making.css',
    'visual-language.css',
  ]);
  assert.doesNotMatch(index, /ai_making_desk|ai-making-prototype|4183|4185/);
});

test('shared tokens follow the monochrome product palette', () => {
  for (const token of [
    '--bg-base: #000000',
    '--surface-1: #111111',
    '--surface-2: #191919',
    '--surface-3: #252525',
    '--hairline: rgba(255, 255, 255, 0.08)',
    '--text-1: #F5F5F5',
    '--text-2: #A1A1A1',
    '--text-3: #707070',
    '--text-4: #4A4A4A',
    '--focus-ring: #6EA8FF',
    '--r-tile: 18px',
    '--r-pill: 999px',
    '--fs-body: 13px',
    '--fs-heading-1: 19px',
    '--bg: var(--bg-base)',
    '--panel: var(--surface-1)',
    '--accent: var(--cta)',
  ]) {
    assert.match(css, new RegExp(token.replace(/[()]/g, '\\$&')));
  }
  assert.doesNotMatch(css, /#b600a8|#7621b0|Kanit|Dynamic Island/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
});

test('shell navigation and primary actions use light capsules', () => {
  assert.match(css, /--ease-island:\s*cubic-bezier\(0\.22,\s*1,\s*0\.36,\s*1\)/);
  assert.match(css, /\.capsule-indicator\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /transform var\(--d-grand\) var\(--ease-island\)/);
  assert.match(css, /\.rail button\.active,\s*\.rail button\.active:hover\s*\{[^}]*background:\s*transparent/);
  assert.match(css, /\.rail button\.active,\s*\.rail button\.active:hover\s*\{[^}]*color:\s*var\(--cta-ink\)/);
  assert.match(css, /\.button\.primary[\s\S]*color:\s*var\(--cta-ink\)/);
  assert.match(css, /\.chip\.active\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /outline:\s*2px solid var\(--focus-ring\)/);
});

test('navigation is a top capsule bar and AI制作 has no in-page title header', () => {
  const workspace = fs.readFileSync(path.join(root, 'public/workspace.js'), 'utf8');
  const ai = fs.readFileSync(path.join(root, 'public/ai_making.js'), 'utf8');
  assert.match(workspace, /capsule-nav/);
  assert.match(workspace, /capsule-indicator/);
  assert.match(workspace, /function slideCapsule/);
  assert.match(workspace, /\['ai-making','AI制作','scan'\]/);
  assert.match(workspace, /<header class="titlebar">[\s\S]*<nav class="rail capsule-nav"/);
  assert.doesNotMatch(ai, /class="ai-header"/);
  assert.doesNotMatch(ai, /<h1>AI制作<\/h1>/);
  assert.doesNotMatch(ai, /个已确认/);
  assert.doesNotMatch(ai, /让 Agent 判断哪里值得加画面/);
});

test('拉片 player, timeline and research panel use monochrome glass capsules', () => {
  assert.match(css, /\.work-area \.play\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /\.work-area \.analysis-tool\s*\{[^}]*border-radius:\s*var\(--r-pill\)/);
  assert.match(css, /\.work-area \.clip-track-lane\.original\s*\{[^}]*background:\s*var\(--surface-3\)/);
  assert.match(css, /\.work-area \.clip-playhead\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /\.work-area \.background \.music-section-label\s*\{[^}]*background:\s*var\(--surface-3\)/);
  assert.match(css, /\.work-area \.statusbox\.error\s*\{[^}]*color:\s*var\(--text-1\)/);
  assert.doesNotMatch(css, /#183637|#b3dae3|#ffdfab|#dcece3|#203930/);
});

test('首页 drops the title blurb and keeps import beside the list tools', () => {
  const studio = fs.readFileSync(path.join(root, 'public/studio.js'), 'utf8');
  const page = studio.slice(studio.indexOf('function libraryPage'), studio.indexOf('function paintCatalog'));
  assert.doesNotMatch(page, /你的素材，值得细看|从一段参考，开始一次研究|catalog-heading/);
  assert.match(page, /data-action="filters"[\s\S]*data-action="import"[\s\S]*id="library-count"/);
  assert.match(page, /导入视频/);
});
