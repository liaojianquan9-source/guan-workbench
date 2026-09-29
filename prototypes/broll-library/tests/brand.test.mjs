import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';

test('active library interface uses a descriptive name', () => {
  for (const file of ['src/App.tsx', 'public/index.html']) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /镜间/, file);
    assert.match(source, /B-roll 样式库/, file);
  }
});
