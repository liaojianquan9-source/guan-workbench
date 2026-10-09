const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const library=require('../public/assets_library.js');

const root=path.resolve(__dirname,'..');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');

test('old frame and music views open the matching material-library tab',()=>{
 assert.deepEqual(library.resolveAssetRoute('frames'),{view:'assets',tab:'images',redirected:true});
 assert.deepEqual(library.resolveAssetRoute('music'),{view:'assets',tab:'music',redirected:true});
 assert.deepEqual(library.resolveAssetRoute('assets','music'),{view:'assets',tab:'music',redirected:false});
 assert.deepEqual(library.resolveAssetRoute('assets','images'),{view:'assets',tab:'images',redirected:false});
 assert.deepEqual(library.resolveAssetRoute('assets'),{view:'assets',tab:'images',redirected:false});
 assert.deepEqual(library.resolveAssetRoute('analysis'),{view:'analysis',tab:null,redirected:false});
 assert.deepEqual(library.resolveAssetRoute('nope'),{view:'library',tab:null,redirected:false});
 assert.equal(library.routeQuery({project:'p1',view:'assets',tab:'music'}),'?project=p1&view=assets&tab=music');
 assert.equal(library.routeQuery({view:'replica',reference:'shot 1'}),'?view=replica&reference=shot+1');
});

test('only technically passed styles are reusable; unfinished replica objects stay out',()=>{
 const assets=[
  {id:'style-ok',kind:'style',metadata:{technical_status:'passed'}},
  {id:'style-wait',kind:'style',metadata:{technical_status:'pending'}},
  {id:'replica',kind:'replica',metadata:{technical_status:'passed'}},
  {id:'study',kind:'study',metadata:{}},
  {id:'image',kind:'image',name:'替换图'},
  null
 ];
 assert.deepEqual(library.reusableStyles(assets).map(item=>item.id),['style-ok']);
 assert.deepEqual(library.replacementImages(assets).map(item=>item.id),['image']);
 assert.deepEqual(library.reusableStyles(null),[]);
});

test('music library groups identified tracks separately from local files',()=>{
 const rows=[{id:'song',projectId:'video'},{id:'file',projectId:null}];
 assert.deepEqual(library.musicGroups(rows,false).map(group=>group.title),['识曲结果','本地曲库']);
 assert.deepEqual(library.musicGroups(rows,true).map(group=>[group.title,group.rows.map(row=>row.id)]),[['本地曲库',['file']]]);
 assert.deepEqual(library.musicGroups([],false),[]);
});

test('sidebar uses one material library and keeps in-project research panels',()=>{
 const workspace=read('public/workspace.js');
 const clips=read('public/clips.js');
 const index=read('public/index.html');
 const making=read('public/ai_making.js');
 const studio=read('public/studio.js');
 assert.match(workspace,/\['assets','素材库','grid'\]/);
 assert.doesNotMatch(workspace,/\['frames','画面','grid'\]/);
 assert.doesNotMatch(workspace,/\['music','声音','music'\]/);
 assert.match(workspace,/data-asset-tab="images"/);
 assert.match(workspace,/data-asset-tab="music"/);
 assert.match(workspace,/拉片画面/);
 assert.match(workspace,/复刻样式/);
 assert.match(workspace,/识曲结果/);
 assert.match(workspace,/AssetLibrary\.resolveAssetRoute/);
 assert.match(workspace,/\['shots','分镜'\],\['images','图片'\],\['transcript','字幕'\],\['music','音乐'\]/);
 assert.match(clips,/\['frames','画面'\],\['sound','声音'\],\['subtitles','字幕'\],\['notes','笔记'\]/);
 assert.match(index,/assets_library\.js/);
 assert.doesNotMatch(index,/ai_making_desk|ai-making-prototype|4183/);
 assert.doesNotMatch(workspace,/AiMakingDesk|ai-desk-host/);
 assert.match(making,/来自素材库/);
 assert.match(making,/在素材库中打开/);
 assert.match(making,/批量导入图片/);
 assert.match(studio,/assets:'素材库'/);
 assert.match(studio,/打开素材库/);
 assert.match(studio,/点进拉片继续研究/);
});
