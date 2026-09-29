const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const P=require('../public/production_client.js');

const source={id:'source1',revision:2,kind:'source',metadata:{provenance:{workbench_id:'old1'}}};
const sharedStyle={id:'style1',revision:3,kind:'style',name:'共享标题',metadata:{technical_status:'passed',poster_hash:'a'.repeat(64),field_schema:{title:{type:'text',label:'主标题',max_length:10},image:{type:'image',label:'图片'}}}};
function fixture(){return{id:'p1',name:'本期真实口播',revision:5,source:{asset_id:'source1',revision:2},segments:[{start:1,end:3,text:'一项事实'},{start:3,end:5,text:'我的感受'}],cards:[{id:'c1',text:'一项事实',start:1,end:3,decision:'broll',status:'draft',reason:'需要证据画面',style:{asset_id:'style1',revision:3},fields:{title:'事实'},evidence:[{summary:'源视频中的事实'}],alternatives:[{reason:'比较过另一候选'}],missing:[],preview_url:'/api/files/p1/current.mp4',render_fingerprint:'fp1',render_report:{layout:{status:'passed'},review_context:{message:'原画幅与声音'}}},{id:'c2',text:'我的感受',start:3,end:5,decision:'keep',status:'draft',reason:'表情本身重要',style:null,fields:{},evidence:[],alternatives:[],missing:[]}],runs:[],deliveries:[]};}

test('all production API and media use the existing same-origin 4182 proxy',async()=>{
 let request;const client=new P.Client(async(url,options)=>{request={url,options};return{ok:true,json:async()=>({run:{id:'r'}})}});
 await client.request('/projects/p/run',{});assert.equal(request.url,'/api/production/projects/p/run');assert.equal(request.options.method,'POST');
 assert.equal(P.media('/api/files/p/clip.mp4'),'/api/production/files/p/clip.mp4');
 assert.equal(P.media('/api/production/files/p/clip.mp4'),'/api/production/files/p/clip.mp4');
 for(const url of ['http://127.0.0.1:4183/api/files/p/x','//evil.test/x','javascript:bad','/media/source.mp4'])assert.equal(P.media(url),'');
 assert.equal(P.blob('a'.repeat(64)),'/api/production/media/'+'a'.repeat(64));
});

test('existing real draft is matched through workbench provenance and fixed source reference',()=>{
 const original=fixture(),copy={...original,id:'copy',derived_from:{project_id:'p1'},updated_at:'2030'},foreign={...original,id:'foreign',source:{asset_id:'another',revision:1}};
 assert.equal(P.chooseProject('old1',[copy,foreign,original],[source],null).id,'p1');
 assert.equal(P.chooseProject('old1',[copy,foreign,original],[source],'copy').id,'copy');
 assert.equal(P.chooseProject('old1',[foreign],[source],'foreign'),null);
 assert.equal(P.chooseProject('missing',[original],[source],null),null);
});

test('batch payload pins current revision, deduplicates selected cards and ignores unrelated IDs',()=>{
 assert.deepEqual(P.batchBody(fixture(),['c1','unknown','c1'],'replace',{fields:{image:{asset_id:'image1',revision:4}}}),{revision:5,card_ids:['c1'],action:'replace',fields:{image:{asset_id:'image1',revision:4}}});
 assert.throws(()=>P.batchBody(fixture(),['unknown'],'approve'),/选择/);
 assert.throws(()=>P.batchBody({...fixture(),revision:null},['c1'],'approve'),/版本/);
});

async function ui({project=fixture(),assets=[source,sharedStyle],response,legacy=false}={}){
 const handlers={},nodes=new Map(),requests=[],settings=new Map();
 if(legacy)settings.set('ai-making:old1',{cards:[{text:'旧规则草稿'}]});
 const element=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',value:'',disabled:false,click(){},classList:{toggle(){}}});return nodes.get(selector)};
 const fetcher=async(url,options)=>{requests.push({url,options});let value=response?await response(url,options,project):undefined;if(value===undefined){if(url==='/api/production/projects')value={projects:project?[project]:[]};else if(url==='/api/production/assets')value={assets};else if(url==='/api/production/projects/p1')value={project};else throw new Error('Unexpected '+url);}if(value.__error)return{ok:false,status:400,json:async()=>({error:value.__error})};return{ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(value))};};
 const context=vm.createContext({S:{view:'ai-making',p:{id:'old1',name:'本期口播.mov',transcript:{segments:project?.segments||[]}},projects:[]},ProductionTimeline:require('../public/production_timeline.js'),ProductionClient:{...P,Client:class extends P.Client{constructor(){super(fetcher)}}},$:element,$$:selector=>selector==='[data-ai-action="preview-current"]'?[element('#top-preview'),element('#editor-preview')]:[],esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),icon:()=>'',clock:value=>String(value),titleOf:project=>project.name,writeSetting:(key,value)=>settings.set(key,value),readSetting:(key,fallback)=>settings.get(key)??fallback,toast:message=>element('#toast').textContent=message,document:{addEventListener:(event,handler)=>handlers[event]=handler,createElement:()=>({click(){}})},setTimeout:()=>1,fetch:fetcher});
 vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../public/ai_making.js'),'utf8'),context);context.AiMaking=vm.runInContext('AiMaking',context);context.AiMaking.render();
 const settle=async()=>{for(let i=0;i<12;i++)await new Promise(resolve=>setImmediate(resolve));};await settle();
 const click=async(action,extra={})=>{const target={dataset:{aiAction:action,...extra},disabled:false};target.closest=()=>target;handlers.click({target,preventDefault(){}});await settle();};
 return{handlers,element,requests,settings,context,settle,click};
}

test('entering AI制作 loads the saved server draft without POST or replacing old browser draft',async()=>{
 const screen=await ui({legacy:true});
 assert.equal(screen.requests.filter(item=>item.options?.method==='POST').length,0);
 assert.equal(screen.settings.get('ai-production-project:old1'),'p1');
 assert.equal(screen.settings.get('ai-making:old1').cards[0].text,'旧规则草稿');
 const html=screen.element('#content').innerHTML;
 for(const klass of ['ai-input','ai-work','ai-board','ai-inspector'])assert.ok(html.includes(`class="${klass}"`));
 assert.match(html,/需要证据画面/);assert.match(html,/表情本身重要/);assert.match(html,/旧浏览器草稿仍保留/);
 assert.match(html,/src="\/api\/production\/files\/p1\/current.mp4"/);
 assert.match(html,/口播原画幅 · 原声音预览/);
 assert.doesNotMatch(html,/http:\/\/127\.0\.0\.1:4183/);
});

test('generation calls the real Agent and displays evidence events, not local regex suggestions',async()=>{
 const screen=await ui({response:(url,options,project)=>{
  if(url==='/api/production/projects/p1/run')return{run:{id:'run1',status:'queued'}};
  if(url==='/api/production/runs/run1')return{run:{id:'run1',status:'awaiting_review',events:[{sequence:1,type:'tool',message:'已比较共享样式与源视频',data:{candidate_count:3}}]}};
 }});
 await screen.click('generate');
 assert.ok(screen.requests.some(item=>item.url==='/api/production/projects/p1/run'));
 assert.match(screen.element('#content').innerHTML,/已比较共享样式与源视频/);
 assert.equal(screen.settings.has('ai-making:old1'),false);
 assert.doesNotMatch(fs.readFileSync(path.resolve(__dirname,'../public/ai_making.js'),'utf8'),/AiMakingLogic\.(?:suggest|createCards)/);
});

test('batch image replacement sends a shared asset revision and only checked cards',async()=>{
 let saved;const image={id:'image1',revision:4,kind:'image',name:'真实图片',blob_hash:'b'.repeat(64),metadata:{}};
 const screen=await ui({assets:[source,sharedStyle,image],response:(url,options,project)=>{if(url==='/api/production/projects/p1/batch'){saved=JSON.parse(options.body);project.revision++;return{project};}}});
 screen.handlers.change({target:{dataset:{aiCheck:'c1'},checked:true}});
 screen.handlers.change({target:{dataset:{aiField:'image',aiType:'image'},value:JSON.stringify({asset_id:'image1',revision:4})}});
 await screen.click('save-batch');
 assert.deepEqual(saved,{revision:5,card_ids:['c1'],action:'replace',fields:{image:{asset_id:'image1',revision:4}}});
 assert.match(screen.element('#ai-status').textContent,/旧确认与预览已失效/);
});

test('preview rejects keep-only selection and layout failures remain visibly blocked',async()=>{
 const project=fixture();project.cards[0].render_report.layout={status:'needs_revision',issues:[{message:'标题过长，缩短到四字'}]};
 const screen=await ui({project});assert.match(screen.element('#content').innerHTML,/版式需修改 · 暂不能确认/);assert.match(screen.element('#content').innerHTML,/标题过长/);
 screen.handlers.change({target:{dataset:{aiCheck:'c2'},checked:true}});await screen.click('preview');
 assert.equal(screen.requests.some(item=>item.url.endsWith('/preview')),false);assert.match(screen.element('#toast').textContent,/保留口播不需要额外渲染/);
});

test('model failure preserves saved cards and exposes resume action',async()=>{
 const screen=await ui({response:url=>{if(url.endsWith('/p1/run'))return{run:{id:'failed1',status:'queued'}};if(url.endsWith('/runs/failed1'))return{run:{id:'failed1',status:'failed',error:'模型连接中断',events:[]}};}});
 await screen.click('generate');assert.match(screen.element('#content').innerHTML,/需要证据画面/);assert.match(screen.element('#content').innerHTML,/从保存进度继续/);assert.match(screen.element('#ai-status').textContent,/模型连接中断/);
});

test('multi-file image import continues after a rejected file and keeps each failure in its result',async()=>{
 const uploaded=[];const screen=await ui({response:url=>{if(url.startsWith('/api/production/upload?')){uploaded.push(url);if(url.includes('bad.png'))return{__error:'图片不能解码'};return{asset:{id:'good',revision:1,kind:'image'}};}}});
 assert.match(screen.element('#content').innerHTML,/id="ai-shared-images"[^>]*multiple/);
 screen.handlers.change({target:{id:'ai-shared-images',dataset:{},files:[{name:'good.png',type:'image/png'},{name:'bad.png',type:'image/png'},{name:'last.png',type:'image/png'}]}});await screen.settle();
 assert.equal(uploaded.length,3);assert.match(screen.element('#ai-status').textContent,/2\/3/);assert.match(screen.element('#ai-status').textContent,/bad.png：图片不能解码/);
});

test('new production copy reuses fixed style references and stays in the same AI-making entry',async()=>{
 const screen=await ui({response:(url,options,project)=>{if(url==='/api/production/projects/p1/duplicate')return{project:{...project,id:'p2',name:'下一期',derived_from:{project_id:'p1',revision:5}}};}});
 await screen.click('duplicate');assert.equal(screen.context.S.view,'ai-making');assert.equal(screen.context.S.p.id,'old1');assert.equal(screen.settings.get('ai-production-project:old1'),'p2');assert.match(screen.element('#content').innerHTML,/下一期/);
});

test('completed composition is served through the proxy and restored after reload',async()=>{
 const project=fixture();project.cards[0].status='approved';project.deliveries=[{cards:[{id:'c1',fingerprint:'fp1'}],url:'/api/files/p1/final.mp4',project_revision:5,report:{status:'passed'}}];const screen=await ui({project});assert.match(screen.element('#content').innerHTML,/src="\/api\/production\/files\/p1\/final.mp4"/);assert.match(screen.element('#content').innerHTML,/下载审阅成片/);
});

test('native time and effect controls persist the existing API contract and invalidate old previews',async()=>{
 const video={...source,blob_hash:'c'.repeat(64),metadata:{...source.metadata,media:{duration:53.03,fps:'30/1'}}};
 const writes=[];
 const screen=await ui({assets:[video,sharedStyle],response:(url,options,project)=>{
  if(url.endsWith('/p1/batch')){const body=JSON.parse(options.body);writes.push(body);project.revision++;project.cards[0]={...project.cards[0],...body,preview_url:null,render_fingerprint:null,status:'draft'};return{project};}
 }});
 assert.match(screen.element('#content').innerHTML,/原片时间定位/);
 screen.element('#ai-cut-start').value='1.5';screen.element('#ai-cut-end').value='3.5';
 await screen.click('save-time');
 assert.deepEqual(writes[0],{revision:5,card_ids:['c1'],action:'retime',start:1.5,end:3.5});
 screen.element('#ai-crop').value='contain';screen.element('#ai-transition').value='dissolve';
 await screen.click('save-effect');
 assert.deepEqual(writes[1],{revision:6,card_ids:['c1'],action:'effect',crop_mode:'contain',transition:'dissolve'});
 assert.equal(screen.element('#top-preview').disabled,false);assert.equal(screen.element('#editor-preview').disabled,false);
 assert.doesNotMatch(screen.element('.ai-card-list').innerHTML,/current\.mp4/);
 assert.equal(screen.context.S.view,'ai-making');
});

test('mixed batch confirms only reviewable cards and visibly retains the missing ones',async()=>{
 const project=fixture();project.cards.push({id:'gap',start:8,end:10,decision:'gap',status:'draft',fields:{},text:'待补'});
 let saved;
 const screen=await ui({project,response:(url,options,p)=>{if(url.endsWith('/p1/batch')){saved=JSON.parse(options.body);p.revision++;return{project:p};}}});
 for(const id of ['c1','c2','gap'])screen.handlers.change({target:{dataset:{aiCheck:id},checked:true}});
 await screen.click('approve');assert.deepEqual(saved.card_ids,['c1','c2']);
 assert.match(screen.element('#ai-status').textContent,/1 段缺口或未通过预览/);
});

test('AI制作 keeps the existing shell and has no demo, embedded page or alternate-product navigation',()=>{
 const index=fs.readFileSync(path.resolve(__dirname,'../public/index.html'),'utf8');
 const workspace=fs.readFileSync(path.resolve(__dirname,'../public/workspace.js'),'utf8');
 const ui=fs.readFileSync(path.resolve(__dirname,'../public/ai_making.js'),'utf8');
 assert.match(workspace,/AiMaking\.render\(\)/);assert.doesNotMatch(workspace,/ai-desk-host|AiMakingDesk/);
 assert.doesNotMatch(index,/ai_making_desk|replica_desk|replica_native/);
 assert.match(index,/production_timeline\.js/);
 assert.doesNotMatch(ui,/window\.open|location\.(?:href|assign|replace)|<iframe|data-desk-view|4183|4185/);
 assert.match(ui,/批量导入图片/);assert.match(ui,/导入复刻样式/);assert.match(ui,/生成审阅成片/);
});

test('discarding an unsaved replacement restores saved fields without changing the server',async()=>{
 const screen=await ui();
 screen.handlers.input({target:{dataset:{aiField:'title',aiType:'text'},value:'尚未保存'}});
 await screen.click('discard-edits');
 assert.match(screen.element('.ai-inspector-scroll').innerHTML,/value="事实"/);
 assert.doesNotMatch(screen.element('.ai-inspector-scroll').innerHTML,/尚未保存/);
 assert.equal(screen.requests.some(r=>r.options?.method==='POST'),false);
});

test('a fixed historical style never displays the newer revision as its saved evidence',async()=>{
 const project=fixture();project.cards[0].style.revision=2;
 delete project.cards[0].preview_url;
 const screen=await ui({project});
 assert.match(screen.element('#content').innerHTML,/历史样式版本暂未载入/);
 const selectedCard=screen.element('#content').innerHTML.split('data-ai-card="0"')[1].split('</article>')[0];
 assert.doesNotMatch(selectedCard,/样式参考 · 当前内容待预览/);
 assert.doesNotMatch(selectedCard,new RegExp('poster=".*'+'a'.repeat(64)));
});


test('review cards retain content-sized rows and reachable scrolling when the input grows',()=>{
 const css=fs.readFileSync(path.resolve(__dirname,'../public/ai_making.css'),'utf8');
 const rules=selector=>Object.fromEntries([...css.replace(/\/\*[\s\S]*?\*\//g,'').matchAll(/([^{}]+)\{([^{}]+)\}/g)].filter(match=>match[1].trim().split(',').map(s=>s.trim()).includes(selector)).flatMap(match=>match[2].split(';').filter(Boolean).map(rule=>{const split=rule.indexOf(':');return[rule.slice(0,split).trim(),rule.slice(split+1).trim()];})));
 // Rows must be intrinsic; overflow hidden on a card otherwise makes grid's auto minimum zero.
 assert.equal(rules('.ai-card-list')['grid-auto-rows'],'max-content');
 assert.equal(rules('.ai-card-list')['align-items'],'start');
 assert.equal(rules('.ai-making')['overflow-y'],'auto');
 assert.match(css,/\.ai-work\{flex:1 0 540px;min-height:540px\}/);
 assert.equal(rules('.ai-section-head')['flex-shrink'],'0');
 // Existing narrow-screen layout keeps full card content rather than a second clipped scroll box.
 assert.match(css,/@media\(max-width:850px\)\{\.ai-work\{flex:none;min-height:0\}\.ai-card-list,\.ai-inspector-scroll\{flex:none\}\}/);
});
