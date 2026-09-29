const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const publicDir=path.resolve(__dirname,'../public');
const prototype=fs.readFileSync(path.join(publicDir,'ai-making-prototype.html'),'utf8');
const script=fs.readFileSync(path.join(publicDir,'ai-making-prototype.js'),'utf8');

test('AI making prototype shows a clear video-first flow and its result',()=>{
 for(const label of ['选择原片','自动识别口播','逐句换画面','选择视频上传','使用这个视频','分镜已生成','换画面','替换元素','导出分镜方案']){
  assert.ok(prototype.includes(label),label);
 }
 assert.match(prototype,/id="start-pane" class="pane active"/);
 assert.match(prototype,/id="result-pane" class="pane"/);
 assert.match(prototype,/ai-making-prototype\.css/);
 assert.match(prototype,/ai-making-prototype\.js/);
 assert.match(script,/function show\(which\)/);
 for(const image of prototype.matchAll(/(?:src)="(ai-presets\/[^"]+)"/g)){
  assert.ok(fs.existsSync(path.join(publicDir,image[1])),image[1]);
 }
});
