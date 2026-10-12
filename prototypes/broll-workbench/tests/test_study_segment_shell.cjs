'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const index = fs.readFileSync(path.join(root, 'public/index.html'), 'utf8');
const workspace = fs.readFileSync(path.join(root, 'public/workspace.js'), 'utf8');
const shell = fs.readFileSync(path.join(root, 'public/study_segment_shell.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'public/visual-language.css'), 'utf8');

test('拉片 loads the three-track segment shell module', () => {
  assert.match(index, /study_segment_shell\.js/);
  assert.match(shell, /StudySegmentShell/);
  assert.match(shell, /画面轨/);
  assert.match(shell, /字幕轨/);
  assert.match(shell, /音乐轨/);
});

test('analysis view wires segment shell, manual or AI toggle and metadata strip', () => {
  assert.match(workspace, /study-segment-shell/);
  assert.match(workspace, /StudySegmentShell\.render/);
  assert.match(workspace, /study-mode-manual/);
  assert.match(workspace, /study-mode-ai/);
  assert.match(workspace, /studySegmentMode/);
  assert.match(shell, /importMetaStrip/);
  assert.match(shell, /ai-segment-control/);
  assert.doesNotMatch(shell, /split-picture/);
});

test('segment shell styles use monochrome glass capsules', () => {
  assert.match(css, /\.work-area\.study-segment-shell \.segment-block/);
  assert.match(css, /\.ai-segment-control button\.active/);
});
