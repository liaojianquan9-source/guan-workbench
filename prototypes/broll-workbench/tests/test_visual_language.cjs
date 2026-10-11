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
  assert.match(css, /\.rail button\.active\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /\.button\.primary[\s\S]*color:\s*var\(--cta-ink\)/);
  assert.match(css, /\.chip\.active\s*\{[^}]*background:\s*var\(--cta\)/);
  assert.match(css, /outline:\s*2px solid var\(--focus-ring\)/);
});
