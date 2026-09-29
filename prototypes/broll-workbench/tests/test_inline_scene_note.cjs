'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');

const source=fs.readFileSync('public/workspace.js','utf8');

test('scene notes edit in place instead of opening the note dialog',()=>{
 assert.match(source,/data-scene-note-input/);
 assert.match(source,/beginSceneNoteEdit\(d\.sceneNoteEdit,d\.owner\)/);
 assert.match(source,/saveSceneNoteInline/);
 assert.doesNotMatch(source,/sceneNoteEdit!==undefined\)return openNote/);
});
