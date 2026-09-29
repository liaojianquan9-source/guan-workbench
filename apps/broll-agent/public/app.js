'use strict';
(() => {
  const L = BrollLogic, esc = L.escape, $ = selector => document.querySelector(selector);
  const client = new L.Client();
  const state = {page:'projects', project:null, projects:[], assets:[], cases:[], workbench:[], status:null, selected:new Set(), filter:'all', libraryKind:'style', libraryQuery:'', sourceId:'', run:null, job:null, replicaJob:null, detailAssetId:null, busy:new Set(), error:'', loading:true, routeToken:0};
  const icons = {
    layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
    film:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    close:'<path d="m6 6 12 12M6 18 18 6"/>',
    play:'<path d="m8 4 12 8-12 8V4Z"/>',
    upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
    download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v6l4 2"/>',
    spark:'<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z"/>',
    settings:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
    file:'<path d="M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8M8 16h6"/>',
    folder:'<path d="M3 7V4h6l3 3h9v14H3V7Z"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
  const action = (label, name, extra='', classes='button') => `<button class="${classes}" data-action="${name}" ${extra}>${label}</button>`;
  const busy = key => state.busy.has(key);
  const asset = id => state.assets.find(item => item.id === id);
  const styleFor = card => asset(card.style?.asset_id);
  const kindName = kind => ({style:'可用样式',image:'图片元素',source:'源视频',study:'研究记录',replica:'复刻项目',audio:'音频'}[kind] || kind);
  const badge = (text, variant='') => `<span class="badge ${variant}">${esc(text)}</span>`;
  const fieldSummary = value => Array.isArray(value) ? value.map(L.shortDetail).join(' · ') : L.shortDetail(value);
  const empty = (title, text, buttons='') => `<div class="empty"><span class="empty-mark">${icon('film')}</span><h2>${esc(title)}</h2><p>${esc(text)}</p><div class="actions">${buttons}</div></div>`;
  function toast(message) { const el = $('#toast'); el.textContent = message; el.hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 5500); }
  function showError(error) { const message = error?.message || String(error); if ($('#dialog').open && $('#dialog-error')) $('#dialog-error').textContent = message; else { state.error = message; const target = $('#page-error'); if (target) { target.textContent = message; target.hidden = false; } } toast(message); }
  function modal(title, content, footer='', wide=false) {
    const dialog = $('#dialog'); dialog.className = wide ? 'wide-dialog' : '';
    $('#dialog-content').innerHTML = `<header class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2>${action(icon('close'),'close','aria-label="关闭"','icon-button')}</header><div class="dialog-body">${content}</div><p id="dialog-error" class="error" role="alert"></p>${footer ? `<footer class="dialog-foot">${footer}</footer>` : ''}`;
    if (!dialog.open) dialog.showModal();
  }
  function closeModal() { $('#dialog').close(); }
  function setRoute(page, id='') { const next = `#${page}${id ? `/${encodeURIComponent(id)}` : ''}`; if (location.hash === next) route(); else location.hash = next; }
  function shell() {
    const routes = [['projects','制作项目','film'],['research','参考研究','search'],['library','共享资产','grid']];
    $('#app').innerHTML = `<div class="app-shell"><aside class="sidebar"><a class="brand" href="#projects" aria-label="观首页"><span class="brand-symbol">${icon('film')}</span><span>观<small>制作 / 研究 / 复用</small></span></a><nav aria-label="主导航">${routes.map(([id,label,glyph])=>`<a href="#${id}" class="nav-item ${state.page===id?'active':''}" ${state.page===id?'aria-current="page"':''}>${icon(glyph)}<span>${label}</span></a>`).join('')}</nav><div class="sidebar-note"><span class="eyebrow">一次复刻 · 多次使用</span><p>从参考里研究表达，<br>在新作品里再次用起来。</p></div><div class="sidebar-bottom">${action(`${icon('settings')}<span>能力与连接</span>`,'status','','nav-item')}<span class="connection"><i class="${state.status?'online':''}"></i>${state.status?'本机服务已连接':'正在连接本机服务'}</span><a href="http://127.0.0.1:4182" target="_blank" rel="noopener noreferrer" class="legacy-link">打开原拉片工作台 ↗</a></div></aside><main id="main" tabindex="-1"><div class="mobile-brand">观 <span>制作 / 研究 / 复用</span></div><div id="page-error" class="page-error" role="alert" ${state.error?'':'hidden'}>${esc(state.error)}</div><div id="page"></div><footer class="app-footer"><span>内容留在项目，成果进入共享库。</span><span>本机制作 · 4183</span></footer></main></div>`;
    renderPage();
  }
  function renderPage() {
    if (state.loading) { $('#page').innerHTML = '<div class="loading" role="status"><span class="spinner"></span>正在读取工作空间…</div>'; return; }
    if (state.page === 'library') renderLibrary();
    else if (state.page === 'research') renderResearch();
    else if (state.project) renderProject();
    else renderProjects();
  }
  function renderProjects() {
    $('#page').innerHTML = `<header class="page-heading"><div><span class="eyebrow">01 / 制作项目</span><h1>让值得看见的内容，<br><em>有自己的画面。</em></h1><p>Agent 查找、比较与制作；你审看草稿，决定最终取舍。</p></div><div class="heading-actions">${action(`${icon('plus')}新建制作项目`,'new-project','','button primary')}${action('从拉片工作台导入','workbench')}</div></header><section class="project-section"><div class="section-heading"><h2>继续制作 <span>${state.projects.length}</span></h2>${action(`${icon('history')}刷新`,'refresh','','button quiet')}</div>${state.projects.length ? `<div class="project-grid">${state.projects.map(project=>{const cards=project.cards||[], approved=cards.filter(card=>card.status==='approved').length;return `<a class="project-tile" href="#projects/${encodeURIComponent(project.id)}"><div class="project-tile-top">${icon('film')}<span>${esc(new Date(project.updated_at||project.created_at).toLocaleDateString('zh-CN'))}</span></div><h3>${esc(project.name)}</h3><p>${(project.segments||[]).length} 段口播${cards.length?` · ${approved} / ${cards.length} 已通过`:' · 等待制作草稿'}</p><div class="project-tile-foot"><span>${project.source?'已关联源视频':'文稿项目'}</span>${icon('arrow')}</div></a>`}).join('')}</div>` : empty('开始第一条制作项目','使用已有口播视频与字幕，或先从一份文稿开始。',action('导入已有工作台项目','workbench','','button primary')+action('输入口播文稿','new-project'))}</section><section class="workflow-note"><span>制作前，也可以先积累</span><a href="#research"><strong>研究一个参考片段</strong><p>保留来源、范围与观察。</p>${icon('arrow')}</a><a href="#library"><strong>把复刻成果加入共享库</strong><p>同一份样式，可在不同项目中使用。</p>${icon('arrow')}</a></section>`;
  }
  function sourceFor(project) { return asset(project.source?.asset_id); }
  function renderProject() {
    const project = state.project, cards = project.cards || [], source = sourceFor(project), visible = L.visibleCards(project,state.filter), selected = [...state.selected].filter(id=>cards.some(card=>card.id===id));
    const counts = {approved:cards.filter(card=>card.status==='approved').length,draft:cards.filter(card=>card.status==='draft').length,keep:cards.filter(card=>card.decision==='keep').length,gap:cards.filter(card=>card.decision==='gap').length};
    const running = busy('run') || L.isPending(state.run?.status), rendering = busy('render') || L.isPending(state.job?.status);
    $('#page').innerHTML = `<a href="#projects" class="back-link">← 所有制作项目</a><header class="project-heading"><div><span class="eyebrow">制作草稿 / V${project.revision}</span><h1>${esc(project.name)}</h1><p>${project.segments.length} 段口播 · ${counts.approved} 张已通过${counts.gap?` · ${counts.gap} 处待补充`:''}</p></div><div class="heading-actions">${action(`${icon('spark')}${running?'Agent 正在制作…':cards.length?'重新分析草稿':'让 Agent 制作草稿'}`,'run',running?'disabled':'','button primary')}${project.source?action(`${icon('file')}本地转写`,'transcribe',rendering||running?'disabled':'','button quiet'):''}${action(`${icon('play')}${rendering?'正在处理…':'生成审阅成片'}`,'render',rendering||!project.source?'disabled':'')}${action(`${icon('plus')}另建副本`,'duplicate-project','','button quiet')}<a class="button quiet" href="/api/projects/${encodeURIComponent(project.id)}/export" download>${icon('download')}导出项目</a></div></header><div class="project-context"><details class="source-panel"><summary>${icon('film')}<span>${source?'源视频与口播文稿':'查看口播文稿'}</span><small>${source?esc(source.name):'尚未关联源视频'}</small></summary><div class="source-content">${source&&L.mediaUrl(source)?`<video src="${L.mediaUrl(source)}" controls preload="metadata" aria-label="口播源视频"></video>`:''}<div class="transcript-list">${project.segments.map(segment=>`<p><time>${L.time(segment.start)} — ${L.time(segment.end)}</time><span>${esc(segment.text)}${segment.estimated?'<small class="estimated-label">估算时间 · 转录后才能合成</small>':''}</span></p>`).join('')}</div></div></details><div id="run-panel">${runPanel()}</div><div id="job-panel">${jobPanel()}</div>${(project.deliveries||[]).length?deliveriesPanel(project):''}</div>${cards.length ? `<div class="review-heading"><div><h2>制作草稿</h2><p>每个画面都有理由。替换内容后，原确认与预览会失效。</p></div><span>${cards.length} 个决定</span></div><div class="filters" role="group" aria-label="筛选制作草稿">${[['all','全部',cards.length],['draft','待审看',counts.draft],['approved','已通过',counts.approved],['keep','保留口播',counts.keep],['gap','待补充',counts.gap],['rejected','已舍弃',cards.filter(c=>c.status==='rejected').length]].map(([key,label,count])=>action(`${label}<span>${count}</span>`,'filter',`data-value="${key}" aria-pressed="${state.filter===key}"`,'filter'+(state.filter===key?' active':''))).join('')}</div><div class="batch-bar"><label class="select-all"><input type="checkbox" id="select-all" ${visible.length&&visible.every(card=>state.selected.has(card.id))?'checked':''} ${!visible.length?'disabled':''}>选择当前 ${visible.length} 张</label><span class="selected-count">已选 <b>${selected.length}</b></span><div class="batch-actions">${action('批量替换','replace',selected.length?'':'disabled')}${action(`${icon('play')}预览`,'preview',selected.length&&!rendering?'':'disabled')}${action(`${icon('check')}通过`,'approve',selected.length&&!busy('batch')?'':'disabled','button approve')}${action('舍弃','reject',selected.length&&!busy('batch')?'':'disabled')}${action('重置','reset',selected.length&&!busy('batch')?'':'disabled','button quiet')}</div></div><section class="cards-grid" aria-label="制作草稿卡片">${visible.length?visible.map(card=>cardHTML(card,cards.indexOf(card))).join(''):empty('没有符合条件的草稿','切换上方筛选，查看其他制作决定。')}</section>` : `<section class="draft-empty">${empty('让 Agent 从口播开始判断','它会查看源视频、检索共享样式与已有素材，比较选择，并标出该保留口播的位置。',action(`${icon('spark')}开始制作草稿`,'run',running?'disabled':'','button primary'))}<div class="draft-readiness"><span>${icon('file')}${project.segments.length} 段口播已保存</span><a href="#library">${icon('grid')}${state.assets.filter(a=>a.kind==='style').length} 个库内样式</a><span>${icon('film')}${source?'已关联源视频':'文稿模式；合成成片需源视频'}</span></div></section>`}`;
  }
  function cardHTML(card,index) {
    const style = styleFor(card), preview = L.localUrl(card.preview_url), poster = L.localUrl(card.poster_url)||L.localUrl(style?.metadata?.poster_url)||L.mediaUrl({blob_hash:style?.metadata?.poster_hash}), missing = card.missing || [];
    const visual = preview ? `<video src="${esc(preview)}" ${poster?`poster="${esc(poster)}"`:''} controls preload="metadata" aria-label="第 ${index+1} 张替换预览"></video>` : `<div class="card-no-preview ${card.decision==='keep'?'keep-frame':''}">${icon(card.decision==='keep'?'film':card.decision==='gap'?'search':'layers')}<strong>${card.decision==='keep'?'保留口播画面':card.decision==='gap'?'等待合适的素材':esc(style?.name||'样式待选')}</strong><span>${card.decision==='broll'?'替换内容后生成实际预览':card.decision==='keep'?'这一段让表达本身留下来':'Agent 的缺口与下一步见下方'}</span></div>`;
    return `<article class="review-card ${state.selected.has(card.id)?'selected':''}" data-card="${esc(card.id)}"><header class="card-head"><label class="card-select"><input type="checkbox" data-select-card="${esc(card.id)}" ${state.selected.has(card.id)?'checked':''}><span>${String(index+1).padStart(2,'0')}</span><span class="sr-only">选择第 ${index+1} 张</span></label>${badge(L.statusLabel(card.decision),card.decision)}<span class="card-status ${esc(card.status)}">${esc(L.statusLabel(card.status))}</span></header><div class="card-visual">${visual}</div><div class="card-body"><time>${L.time(card.start)} — ${L.time(card.end)}</time><p class="card-script">${esc(card.text)}</p><p class="card-reason">${esc(card.reason || '尚未提供判断依据。')}</p>${missing.length?`<div class="missing-list"><strong>还缺什么</strong>${missing.map(item=>`<span>${esc(fieldSummary(item))}</span>`).join('')}</div>`:''}<details class="evidence"><summary>依据与候选 <span>${(card.evidence||[]).length} 条依据 · ${(card.alternatives||[]).length} 个候选</span></summary>${(card.evidence||[]).length?`<h4>判断依据</h4>${card.evidence.map(item=>`<pre>${esc(L.shortDetail(item))}</pre>`).join('')}`:'<p>当前没有附加证据。</p>'}${(card.alternatives||[]).length?`<h4>比较过的候选</h4>${card.alternatives.map(item=>`<pre>${esc(L.shortDetail(item))}</pre>`).join('')}`:''}${card.render_report?`<h4>渲染检查</h4><pre>${esc(L.shortDetail(card.render_report))}</pre>`:''}</details></div><footer class="card-foot"><span>${style?`${esc(style.name)} · v${card.style.revision}`:'未使用库内样式'}</span>${action('查看与修改 →','edit-card',`data-id="${esc(card.id)}"`,'text-button')}</footer></article>`;
  }
  function runPanel() {
    const run = state.run;
    if (!run) return '';
    const events = run.events || [], last = events[events.length-1];
    return `<details class="run-panel" ${L.isPending(run.status)||run.error?'open':''}><summary><span class="run-indicator ${L.isPending(run.status)?'pulsing':''}">${icon('spark')}</span><strong>Agent · ${esc(L.statusLabel(run.status))}</strong><span>${esc(last?.message || '正在准备执行记录')}</span><small>${events.length} 步</small></summary>${run.error?`<p class="error">${esc(run.error)}</p>`:''}<ol class="event-list">${events.map(event=>`<li><span class="event-index">${String(event.sequence??events.indexOf(event)+1).padStart(2,'0')}</span><div><div class="event-title"><strong>${esc(event.message || event.type)}</strong><span>${esc(event.type)}</span></div>${event.data&&Object.keys(event.data).length?`<details><summary>查看输入与结果</summary><pre>${esc(L.shortDetail(event.data))}</pre></details>`:''}</div></li>`).join('')}</ol><p class="event-note">这里记录工具动作、依据与检查结果，便于回看和重试。</p><div class="run-actions">${L.isPending(run.status)?action('停止本次执行','cancel-run','','button quiet'):['failed','interrupted','error'].includes(run.status)?action('从已保存进度继续','resume-run','','button'):''}</div></details>`;
  }
  function jobPanel() {
    const job = state.job;
    if (!job) return '';
    const file = L.localUrl(job.video_url || job.output_url || job.url || job.result?.video_url || job.result?.url || job.result?.delivery?.url || ''), report = job.report || job.result?.report || job.result?.delivery?.report;
    return `<section class="job-panel"><div><span class="${L.isPending(job.status)?'spinner':''}">${L.isPending(job.status)?'':icon(job.error?'close':'check')}</span><strong>${esc(job.kind==='render'||job.type==='render'?'审阅成片':job.kind==='transcribe'?'本地转写':'预览任务')} · ${esc(L.statusLabel(job.status))}</strong><p>${esc(job.message || job.error || (L.isPending(job.status)?'完成后会自动更新画面。':'处理结果已保存到项目。'))}</p></div>${file?`<video controls preload="metadata" src="${esc(file)}" aria-label="审阅成片"></video><a class="button" href="${esc(file)}" download>${icon('download')}下载视频</a>`:''}${report?`<details><summary>查看检查报告</summary><pre>${esc(L.shortDetail(report))}</pre></details>`:''}</section>`;
  }
  function deliveriesPanel(project) {
    return `<details class="deliveries"><summary>${icon('film')}已保存的审阅成片 <span>${project.deliveries.length}</span></summary><div>${project.deliveries.slice().reverse().map(delivery=>{const url=L.localUrl(delivery.url);return `<article><div><strong>项目 v${delivery.project_revision}</strong><small>${esc(delivery.created_at)}</small><span>${(delivery.cards||[]).length} 张已确认画面</span></div>${url?`<video controls preload="none" src="${esc(url)}" aria-label="已保存审阅成片"></video><a class="button" href="${esc(url)}" download>下载视频</a>`:''}</article>`}).join('')}</div></details>`;
  }
  function renderLibrary() {
    const kinds = ['style','image','source','study','replica'], query=state.libraryQuery.toLowerCase(), items=state.assets.filter(item=>item.kind===state.libraryKind&&`${item.name} ${fieldSummary(item.metadata?.use_cases||item.metadata?.purpose||'')}`.toLowerCase().includes(query));
    $('#page').innerHTML = `<header class="page-heading compact"><div><span class="eyebrow">03 / 共享资产</span><h1>一份成果，<em>多次使用。</em></h1><p>样式、元素与研究保存为独立资产。制作项目引用确定的版本。</p></div><div class="heading-actions">${action(`${icon('upload')}批量导入素材`,'upload','','button primary')}${action('导入已有复刻案例','cases')}<a class="button quiet" href="/api/assets/export" download="共享资产库.zip">${icon('download')}导出整个共享库</a></div></header><div class="library-toolbar"><div class="filters" role="group" aria-label="资产类型">${kinds.map(kind=>action(`${kindName(kind)}<span>${state.assets.filter(a=>a.kind===kind).length}</span>`,'library-kind',`data-value="${kind}" aria-pressed="${state.libraryKind===kind}"`,'filter'+(state.libraryKind===kind?' active':''))).join('')}</div><label class="search-field">${icon('search')}<input id="library-search" type="search" placeholder="搜索名称或用途" aria-label="搜索共享资产" value="${esc(state.libraryQuery)}"></label></div><section class="asset-grid">${items.length?items.map(assetHTML).join(''):empty(`还没有${kindName(state.libraryKind)}`,state.libraryKind==='style'?'导入已有复刻案例，完成真实渲染与替换检查后，再用于制作项目。':'导入文件，或从参考视频保存一条研究记录。',state.libraryKind==='style'?action('查看可导入案例','cases','','button primary'):action('批量导入素材','upload','','button primary'))}</section>`;
  }
  function assetHTML(item) {
    const url = L.mediaUrl(item), meta = item.metadata || {}, stylePoster=L.mediaUrl({blob_hash:meta.poster_hash}), visual = item.kind==='style'&&stylePoster?`<img src="${stylePoster}" alt="${esc(item.name)} 实际渲染静帧" loading="lazy">`: item.kind==='image'&&url?`<img src="${url}" alt="${esc(item.name)}" loading="lazy">`:item.kind==='source'&&url?`<video src="${url}" controls preload="metadata" aria-label="${esc(item.name)}"></video>`:`<div class="asset-placeholder ${item.kind==='style'?'style-placeholder':''}">${icon(item.kind==='style'?'spark':item.kind==='study'?'search':'folder')}<span>${esc(kindName(item.kind))}</span></div>`;
    const purpose=meta.description||meta.purpose||fieldSummary(meta.use_cases||meta.uses||meta.note||'');
    return `<article class="asset-card"><div class="asset-visual">${visual}</div><div class="asset-copy"><div class="asset-meta"><span>${esc(kindName(item.kind))}</span><span>v${item.revision}</span></div><h3>${esc(item.name)}</h3><p>${esc(purpose||'来源、版本与关联信息保存在资产详情。')}</p>${item.kind==='style'?`<div class="asset-status">${badge(`技术：${L.statusLabel(meta.technical_status||'待检查')}`)}${badge(`保真：${L.statusLabel(meta.fidelity_status||'待审')}`,'muted')}</div>`:''}<footer>${action('资产详情','asset-detail',`data-id="${esc(item.id)}"`,'text-button')}${item.kind==='source'?action('研究此视频 →','study-source',`data-id="${esc(item.id)}"`,'text-button'):item.kind==='study'?action('建立复刻项目 →','create-replica',`data-id="${esc(item.id)}"`,'text-button'):item.kind==='replica'?action('继续下一阶段 →','advance-replica',`data-id="${esc(item.id)}"`,'text-button'):''}</footer></div></article>`;
  }
  function renderResearch() {
    const sources=state.assets.filter(item=>item.kind==='source'), source=asset(state.sourceId)||sources[0];
    if (source) state.sourceId=source.id;
    const studies=state.assets.filter(item=>item.kind==='study');
    $('#page').innerHTML = `<header class="page-heading compact"><div><span class="eyebrow">02 / 参考研究</span><h1>看懂一个片段，<em>留下制作依据。</em></h1><p>选择范围，保存原片、抽帧与观察。复刻过程与可用样式分开保存。</p></div>${action(`${icon('upload')}导入参考视频`,'upload-source','','button primary')}</header>${sources.length?`<section class="research-workspace"><div class="research-view"><label class="field-label" for="research-source">当前参考视频</label><select id="research-source">${sources.map(item=>`<option value="${esc(item.id)}" ${source?.id===item.id?'selected':''}>${esc(item.name)}</option>`).join('')}</select><video id="research-video" src="${L.mediaUrl(source)}" controls preload="metadata" aria-label="参考视频"></video><div class="research-player-foot"><span>${esc(source.name)} · v${source.revision}</span>${action('查看来源与版本','asset-detail',`data-id="${esc(source.id)}"`,'text-button')}</div></div><form id="study-form" class="research-form"><span class="eyebrow">保存研究范围</span><h2>这个片段如何表达？</h2><div class="range-fields"><label>开始（秒）<input name="start" type="number" min="0" step="0.01" value="0" required></label><label>结束（秒）<input name="end" type="number" min="0.01" step="0.01" placeholder="片段结束时间" required></label></div><div class="range-actions">${action('当前时间作开始','range-start','','button quiet')}${action('当前时间作结束','range-end','','button quiet')}</div><label>研究笔记<textarea name="note" rows="6" placeholder="记录叙事用途、关键元素、布局或转场，也可以写下一次复刻要保留什么。"></textarea></label><button type="submit" class="button primary" ${busy('study')?'disabled':''}>${icon('plus')}${busy('study')?'正在保存与抽帧…':'保存研究记录'}</button><p class="form-hint">研究保存来源与范围。尚未实现的任意片段复刻会如实保留为待处理任务。</p></form></section>`:empty('先选一段真实参考视频','可一次导入多个视频。源文件保存到共享资产服务，后续研究与项目共同引用。',action('导入参考视频','upload-source','','button primary'))}<section class="research-collection"><div class="section-heading"><h2>已保存的研究 <span>${studies.length}</span></h2>${action('查看已有案例复刻成果','cases','','button quiet')}</div>${studies.length?`<div class="study-list">${studies.map(item=>`<button class="study-row" data-action="asset-detail" data-id="${esc(item.id)}"><span class="study-icon">${icon('search')}</span><span><strong>${esc(item.name)}</strong><small>${esc(item.metadata?.note||'查看范围、抽帧与来源证据')}</small></span><span>v${item.revision}</span>${icon('arrow')}</button>${action('建立复刻项目','create-replica',`data-id="${esc(item.id)}"`,'button quiet study-replica-action')}`).join('')}</div>`:'<p class="muted-text">还没有保存研究。选择一个片段开始。</p>'}</section>`;
  }
  function newProject() {
    const sources=state.assets.filter(item=>item.kind==='source');
    modal('新建制作项目',`<form id="project-form"><label>项目名称<input name="name" maxlength="160" placeholder="这一期视频的名称" required autofocus></label><label>关联口播源视频<select name="source_id"><option value="">先创建文稿项目</option>${sources.map(item=>`<option value="${esc(item.id)}">${esc(item.name)}</option>`).join('')}</select></label><p class="form-hint">源视频从共享库选择。选定源视频后可以留空文稿，在项目内完成本地转写。</p><label>口播文稿或带时间码的 JSON<textarea name="transcript" rows="9" placeholder="粘贴真实口播文稿，或 [{&quot;start&quot;:0,&quot;end&quot;:3,&quot;text&quot;:&quot;口播内容&quot;}]"></textarea></label><p class="form-hint">JSON 时间单位为秒。纯文稿的时间需要校对，准确回填请使用源视频字幕。</p></form>`,action('取消','close')+'<button class="button primary" type="submit" form="project-form">创建项目</button>');
  }
  async function workbenchImport() {
    modal('从拉片工作台导入','<p class="loading">正在读取已有视频与字幕…</p>');
    const result=await client.request('/api/workbench-projects'); state.workbench=result.projects||[];
    modal('从拉片工作台导入',`<p class="dialog-intro">读取已有原片与字幕，创建独立制作项目。原拉片记录保留。</p>${state.workbench.length?`<div class="import-project-list">${state.workbench.map(project=>`<div class="import-project-row"><span>${icon('film')}</span><div><strong>${esc(project.name)}</strong><small>${L.time(project.duration)} · ${project.transcript?.segments?.length??project.segment_count??(typeof project.segments==='number'?project.segments:project.segments?.length)??0} 段字幕</small></div>${action('导入','import-workbench',`data-id="${esc(project.id)}"`,'button primary')}</div>`).join('')}</div>`:empty('没有发现可导入项目','请先在原拉片工作台导入视频并完成转写。')}`,action('关闭','close'),true);
  }
  function openUpload(kind='image') {
    modal('批量导入共享素材',`<div class="upload-options"><label>素材类型<select id="upload-kind"><option value="image" ${kind==='image'?'selected':''}>图片元素</option><option value="source" ${kind==='source'?'selected':''}>源视频 / 参考视频</option></select></label><label class="upload-zone" id="upload-zone">${icon('upload')}<strong>选择文件，也可以拖入这里</strong><span>支持多选；每个文件单独显示处理结果</span><input id="asset-files" type="file" ${kind==='image'?'accept="image/png,image/jpeg,image/webp"':'accept="video/*,.mp4,.mov,.mkv,.webm"'} multiple></label><div id="upload-progress" class="upload-progress" aria-live="polite"></div></div>`,action('完成','close'));
  }
  async function uploadFiles(files) {
    if (!files?.length || busy('upload')) return;
    const kind=$('#upload-kind').value; state.busy.add('upload'); $('#asset-files').disabled=true; $('#upload-kind').disabled=true;
    try {
      const rows=await L.importFiles(client,files,kind,rows=>{ const target=$('#upload-progress'); if(target)target.innerHTML=rows.map(row=>`<div class="upload-row ${row.status==='error'?'error':''}"><span>${row.status==='running'?'<i class="spinner"></i>':icon(row.status==='complete'?'check':row.status==='error'?'close':'file')}</span><div><strong>${esc(row.name)}</strong><small>${esc(row.error||L.statusLabel(row.status))}</small></div></div>`).join(''); });
      await loadAssets(); const successful=rows.filter(row=>row.status==='complete');
      if (kind==='source'&&successful.length) state.sourceId=successful[0].asset.id;
      renderPage(); toast(`${successful.length} / ${rows.length} 个文件已保存到共享资产库。`);
    } finally { state.busy.delete('upload'); if($('#asset-files'))$('#asset-files').disabled=false; if($('#upload-kind'))$('#upload-kind').disabled=false; }
  }
  async function casesModal() {
    modal('导入已有复刻案例','<p class="loading">正在读取真实案例…</p>');
    const result=await client.request('/api/cases'); state.cases=result.cases||[];
    modal('导入已有复刻案例',`<p class="dialog-intro">导入会整理原有工程，执行真实渲染与替换检查，然后把成果写入共享资产库。技术可用性与视觉保真审阅分别保留。</p><div class="case-list">${state.cases.map(item=>`<article class="case-row"><span class="case-icon">${icon('layers')}</span><div><h3>${esc(item.name||item.title||item.id||item.case_id)}</h3><p>${esc(item.description||item.note||'来自本机已存在的复刻工程。')}</p><small>${esc(item.source||item.case_id||item.id)}</small></div>${action('检查并导入','import-case',`data-id="${esc(item.case_id||item.id)}"`,'button primary')}</article>`).join('')||'<p>当前没有已配置的案例适配器。</p>'}</div><div id="case-progress" role="status"></div>`,action('关闭','close'),true);
  }
  function assetDetail(id) {
    const item=asset(id); if(!item)return;state.detailAssetId=id;
    const meta=item.metadata||{}, refs=fieldsOfMedia(meta), source=L.mediaUrl(item), styleVideo=L.mediaUrl({blob_hash:meta.preview_hash}), replacement=L.mediaUrl({blob_hash:meta.replacement_preview_hash});
    modal(item.name,`<div class="asset-detail-meta">${badge(kindName(item.kind))}${badge(`不可变版本 v${item.revision}`)}</div>${item.kind==='replica'?replicaPanel(item):''}${styleVideo?`<div class="style-preview"><h3>实际复刻预览</h3><video class="detail-video" src="${styleVideo}" controls preload="metadata"></video>${replacement?`<details><summary>查看真实替换验收</summary><video class="detail-video" src="${replacement}" controls preload="none"></video></details>`:''}</div>`:''}${item.kind==='image'&&source?`<img class="detail-image" src="${source}" alt="${esc(item.name)}">`:''}${item.kind==='source'&&source?`<video class="detail-video" src="${source}" controls preload="metadata"></video>`:''}${refs.length?`<div class="detail-stills">${refs.map(ref=>`<img src="${ref}" loading="lazy" alt="研究取证帧">`).join('')}</div>`:''}<dl class="asset-identifiers"><dt>资产 ID</dt><dd>${esc(item.id)}</dd><dt>创建时间</dt><dd>${esc(item.created_at)}</dd>${item.blob_hash?`<dt>内容指纹</dt><dd>${esc(item.blob_hash)}</dd>`:''}</dl><details open class="metadata-detail"><summary>来源、许可、检查与版本记录</summary><pre>${esc(L.shortDetail(meta))}</pre></details>`,action('关闭','close')+(item.kind==='source'?action('研究此视频','study-source',`data-id="${esc(item.id)}"`,'button primary'):item.kind==='study'?action('建立复刻项目','create-replica',`data-id="${esc(item.id)}"`,'button primary'):item.kind==='replica'?action('继续下一阶段','advance-replica',`data-id="${esc(item.id)}" ${busy('replica')?'disabled':''}`,'button primary'):''),true);
  }
  function replicaPanel(item) {
    const metadata=item.metadata||{}, stages=metadata.stages||{}, labels={preflight:'范围预检',layout:'静态布局',motion:'动效取证',implementation:'可编辑实现',qa:'验收检查'}, current=state.replicaJob?.replicaId===item.id?state.replicaJob:null;
    return `<section class="replica-progress"><h3>复刻进度 ${badge(L.statusLabel(metadata.status||'pending'))}</h3><p>${esc(metadata.next_action||metadata.message||'每一阶段保存可检查的证据，未验证的结果不会标为可用。')}</p><div class="replica-stages">${Object.entries(stages).map(([key,value])=>`<div><span>${esc(labels[key]||key)}</span>${badge(L.statusLabel(typeof value==='string'?value:value.status||'pending'))}${typeof value==='object'?`<details><summary>阶段证据</summary><pre>${esc(L.shortDetail(value))}</pre></details>`:''}</div>`).join('')}</div>${current?`<div class="replica-job" role="status"><strong>${esc(L.statusLabel(current.status))}</strong><p>${esc(current.error||current.message||(L.isPending(current.status)?'正在调用复刻工具，完成后会自动更新阶段记录。':'该阶段的结果已保存。'))}</p></div>`:''}${metadata.events?`<details><summary>执行记录</summary><pre>${esc(L.shortDetail(metadata.events))}</pre></details>`:''}</section>`;
  }
  async function createReplica(studyId) {
    if(busy('replica'))return;state.busy.add('replica');
    try{const result=await client.request('/api/replicas',{study_id:studyId});await loadAssets();state.busy.delete('replica');assetDetail(result.replica.id);renderPage();toast('复刻项目已建立，范围与研究证据已关联。');}
    finally{state.busy.delete('replica');}
  }
  async function advanceReplica(replicaId) {
    if(busy('replica'))return;state.busy.add('replica');
    try{const result=await client.request(`/api/replicas/${encodeURIComponent(replicaId)}/advance`,{stage:'auto'});state.replicaJob={...result.job,replicaId};assetDetail(replicaId);pollReplica(result.job.id,replicaId);}
    catch(error){state.busy.delete('replica');throw error;}
  }
  async function pollReplica(jobId,replicaId) {
    try{const result=await client.request(`/api/jobs/${encodeURIComponent(jobId)}`);state.replicaJob={...result.job,replicaId};
      if(L.isPending(result.job.status)){if($('#dialog').open&&state.detailAssetId===replicaId)assetDetail(replicaId);setTimeout(()=>pollReplica(jobId,replicaId),1500);return;}
      state.busy.delete('replica');await loadAssets();renderPage();if($('#dialog').open&&state.detailAssetId===replicaId)assetDetail(replicaId);if(result.job.error)showError(new Error(result.job.error));else toast('复刻阶段已更新，请查看实际证据与待审状态。');
    }catch(error){state.busy.delete('replica');state.replicaJob={...state.replicaJob,status:'failed',error:error.message};if($('#dialog').open&&state.detailAssetId===replicaId)assetDetail(replicaId);showError(error);}
  }
  function fieldsOfMedia(meta) {
    const values=meta.frames||meta.stills||meta.evidence?.frames||[];
    if(!Array.isArray(values))return [];
    return values.map(item=>typeof item==='string'?L.localUrl(item):L.localUrl(item.url)||L.mediaUrl({blob_hash:item.blob_hash||item.sha256})).filter(Boolean);
  }
  function editCards(ids) {
    const cards=state.project.cards.filter(card=>ids.includes(card.id)); if(!cards.length)return;
    const styleIds=new Set(cards.map(card=>card.style?.asset_id)), styleId=styleIds.size===1?cards[0].style?.asset_id||'':'';
    state.editing={ids:cards.map(card=>card.id),styleId,initialStyleId:styleId,fields:cards.length===1?{...cards[0].fields}:{},single:cards.length===1,changed:new Set()};
    modal(cards.length===1?'修改这张制作草稿':`批量替换 ${cards.length} 张草稿`,`<div class="edit-context">${cards.length===1?`<p class="edit-script">${esc(cards[0].text)}</p><p>${esc(cards[0].reason)}</p>`:`<p>只更新你改动的字段；未填写的内容保留。</p>`}</div><form id="replace-form"><label>使用的共享样式<select id="replace-style"><option value="">${styleIds.size>1?'保留各自样式':'选择一个可用样式'}</option>${state.assets.filter(item=>item.kind==='style').map(item=>`<option value="${esc(item.id)}" ${styleId===item.id?'selected':''}>${esc(item.name)} · v${item.revision}</option>`).join('')}</select></label><div id="replace-fields">${editFields()}</div><details class="advanced-fields"><summary>高级：按字段名批量填写</summary><p class="form-hint">使用 JSON 对象，仅提交需要替换的字段。图片须引用资产 ID 和版本。</p><textarea id="replace-json" rows="5" placeholder="{}"></textarea></details><p class="form-hint">保存会重置已通过状态与旧预览。重新预览后再确认。</p></form>`,action('取消','close')+'<button type="submit" form="replace-form" class="button primary">保存替换</button>',true);
  }
  function editFields() {
    const editing=state.editing, style=asset(editing.styleId), fields=L.fieldsOf(style), images=state.assets.filter(item=>item.kind==='image');
    if(!fields.length)return '<p class="form-hint">选择样式后显示替换字段，或展开高级编辑使用字段名。</p>';
    return `<div class="field-grid">${fields.map(field=>{const current=editing.fields[field.key], value=current??'', image=['image','asset','image_asset'].includes(field.type);return `<label class="${image?'image-field':''}"><span>${esc(field.label||field.key)}${field.max_length?`<small>最多 ${field.max_length} 字符</small>`:''}</span>${image?`<select data-edit-field="${esc(field.key)}"><option value="">${editing.single?'沿用现有图片':'保留各自图片'}</option>${images.map(item=>{const ref=JSON.stringify({asset_id:item.id,revision:item.revision}), match=current?.asset_id===item.id&&current?.revision===item.revision;return `<option value="${esc(ref)}" ${match?'selected':''}>${esc(item.name)} · v${item.revision}</option>`}).join('')}</select><small>在共享资产中批量导入图片后，可回到这里选择。</small>`:field.type==='boolean'?`<select data-edit-field="${esc(field.key)}"><option value="false" ${!value?'selected':''}>否</option><option value="true" ${value?'selected':''}>是</option></select>`:field.enum?`<select data-edit-field="${esc(field.key)}">${field.enum.map(option=>`<option value="${esc(option)}" ${option===value?'selected':''}>${esc(option)}</option>`).join('')}</select>`:`<textarea rows="${String(value).length>60?4:2}" data-edit-field="${esc(field.key)}" ${field.max_length?`maxlength="${Number(field.max_length)}"`:''} placeholder="${editing.single?'填写替换内容':'不改动则保留各自内容'}">${esc(typeof value==='object'?L.shortDetail(value):value)}</textarea>`}${field.description?`<small>${esc(field.description)}</small>`:''}</label>`}).join('')}</div>`;
  }
  async function saveReplacement() {
    const editing=state.editing, style=asset(editing.styleId), definitions=L.fieldsOf(style), fields={};
    for(const element of document.querySelectorAll('[data-edit-field]')) {
      const key=element.dataset.editField; if(!editing.changed.has(key))continue;
      const value=L.parseFieldValue(definitions.find(field=>field.key===key)||{key,type:'text'},element.value); if(value!==undefined)fields[key]=value;
    }
    const raw=$('#replace-json').value.trim(); if(raw){let value;try{value=JSON.parse(raw)}catch{throw new Error('高级字段 JSON 格式有误。')}if(!value||Array.isArray(value)||typeof value!=='object')throw new Error('高级字段必须是 JSON 对象。');Object.assign(fields,value);}
    const styleChanged=editing.styleId&&editing.styleId!==editing.initialStyleId;
    if(!Object.keys(fields).length&&!styleChanged)throw new Error('还没有改动字段或样式。');
    const payload=L.batchPayload(state.project,editing.ids,'replace',{fields,...(styleChanged?{style_id:editing.styleId}:{})});
    const result=await client.request(`/api/projects/${encodeURIComponent(state.project.id)}/batch`,payload); state.project=result.project; updateProjectList(); closeModal();renderProject();toast('替换已保存；请重新预览并审看。');
  }
  function updateProjectList() { const index=state.projects.findIndex(project=>project.id===state.project.id);if(index>=0)state.projects[index]=state.project;else state.projects.unshift(state.project); }
  async function batch(actionName) {
    if(busy('batch'))return;const payload=L.batchPayload(state.project,state.selected,actionName);state.busy.add('batch');
    try {const result=await client.request(`/api/projects/${encodeURIComponent(state.project.id)}/batch`,payload);state.project=result.project;updateProjectList();state.selected.clear();toast(`${payload.card_ids.length} 张草稿已${actionName==='approve'?'通过':actionName==='reject'?'舍弃':'重置'}。`);}
    finally {state.busy.delete('batch');renderProject();}
  }
  async function startRun(resume=null) {
    if(busy('run')||L.isPending(state.run?.status))return;state.busy.add('run');state.error='';const projectId=state.project.id;renderProject();
    try {const result=await client.request(`/api/projects/${encodeURIComponent(projectId)}/run`,resume?{resume_run_id:resume}:{});state.run=result.run;renderProject();pollRun(result.run.id,projectId);}
    finally {state.busy.delete('run');if(state.project?.id===projectId)renderProject();}
  }
  async function pollRun(runId,projectId) {
    try {const result=await client.request(`/api/runs/${encodeURIComponent(runId)}`);if(state.project?.id!==projectId)return;state.run=result.run;const panel=$('#run-panel');if(panel){const open=panel.querySelector('details')?.open;panel.innerHTML=runPanel();if(open&&panel.querySelector('details'))panel.querySelector('details').open=true;}
      if(L.isPending(result.run.status)){setTimeout(()=>pollRun(runId,projectId),1200);return;}
      const loaded=await client.request(`/api/projects/${encodeURIComponent(projectId)}`);if(state.project?.id!==projectId)return;state.project=loaded.project;updateProjectList();renderProject();if(result.run.error)showError(new Error(result.run.error));else toast('制作草稿已更新，可以批量审看。');
    } catch(error) { if(state.project?.id===projectId){state.run={...state.run,status:'error',error:error.message};renderProject();showError(error);} }
  }
  async function startJob(type) {
    if(busy('render')||L.isPending(state.job?.status))return; const project=state.project;
    const ids=[...state.selected].filter(id=>project.cards.some(card=>card.id===id&&card.decision==='broll'&&card.style));
    if(type==='preview'&&!ids.length)throw new Error('请先选择有样式的 B-roll 草稿。保留口播不需要额外渲染。');
    if(type==='render'&&!project.source)throw new Error('项目还没有源视频，请从已有工作台项目导入后合成。');
    state.busy.add('render');renderProject();
    try {const result=await client.request(`/api/projects/${encodeURIComponent(project.id)}/${type}`,type==='preview'?{card_ids:ids}:{});state.job={...result.job,kind:type};renderProject();pollJob(result.job.id,project.id,type);}
    finally{state.busy.delete('render');if(state.project?.id===project.id)renderProject();}
  }
  async function pollJob(id,projectId,kind) {
    try {const result=await client.request(`/api/jobs/${encodeURIComponent(id)}`);if(state.project?.id!==projectId)return;state.job={...result.job,kind};const panel=$('#job-panel');if(panel)panel.innerHTML=jobPanel();
      if(L.isPending(result.job.status)){setTimeout(()=>pollJob(id,projectId,kind),1200);return;}
      const loaded=await client.request(`/api/projects/${encodeURIComponent(projectId)}`);if(state.project?.id!==projectId)return;state.project=loaded.project;updateProjectList();renderProject();if(result.job.error)showError(new Error(result.job.error));else toast(kind==='preview'?'实际替换预览已生成。':kind==='transcribe'?'本地转写已完成，可以开始制作草稿。':'审阅成片已完成。');
    } catch(error){if(state.project?.id===projectId){state.job={...state.job,status:'error',error:error.message};renderProject();showError(error);}}
  }
  async function loadAssets(){state.assets=(await client.request('/api/assets')).assets||[];}
  async function refreshAll() {
    const results=await Promise.allSettled([client.request('/api/status'),client.request('/api/assets'),client.request('/api/projects')]);
    if(results[0].status==='fulfilled')state.status=results[0].value;
    if(results[1].status==='fulfilled')state.assets=results[1].value.assets||[];
    if(results[2].status==='fulfilled')state.projects=results[2].value.projects||[];
    const failures=results.filter(result=>result.status==='rejected');state.error=failures.map(result=>result.reason.message).join(' ');state.loading=false;
  }
  async function route() {
    const token=++state.routeToken,[page,id]=location.hash.replace(/^#/,'').split('/');state.page=['projects','research','library'].includes(page)?page:'projects';state.filter='all';state.selected.clear();state.run=null;state.job=null;state.project=null;closeModal();
    if(state.page==='projects'&&id){state.loading=true;shell();try{const result=await client.request(`/api/projects/${encodeURIComponent(decodeURIComponent(id))}`);if(token!==state.routeToken)return;state.project=result.project;const last=state.project.runs?.at(-1),runId=typeof last==='string'?last:last?.id;if(runId){try{state.run=(await client.request(`/api/runs/${encodeURIComponent(runId)}`)).run;if(L.isPending(state.run.status))pollRun(runId,state.project.id);}catch{}}}catch(error){state.error=error.message;}finally{state.loading=false;}}
    if(token===state.routeToken)shell();
  }
  const tasks = {
    close:()=>closeModal(), 'new-project':()=>newProject(), workbench:()=>workbenchImport(), upload:()=>openUpload(), 'upload-source':()=>openUpload('source'), cases:()=>casesModal(),
    refresh:async()=>{await refreshAll();if(state.project)state.project=(await client.request(`/api/projects/${encodeURIComponent(state.project.id)}`)).project;shell();},
    status:()=>modal('能力与连接',`<p class="dialog-intro">服务与模型状态来自当前运行环境。模型失败时，已有项目和提案继续保留。</p><pre>${esc(L.shortDetail(state.status||{error:'未连接到本机服务'}))}</pre>`,action('重新检查','refresh-status','','button primary')+action('关闭','close'),true),
    'refresh-status':async()=>{state.status=await client.request('/api/status');tasks.status();},
    'import-workbench':async target=>{target.disabled=true;target.textContent='正在复制与导入…';try{const result=await client.request('/api/workbench-import',{project_id:target.dataset.id});await refreshAll();setRoute('projects',result.project.id);}finally{if(target.isConnected){target.disabled=false;target.textContent='导入';}}},
    'import-case':async target=>{if(busy('case'))return;state.busy.add('case');document.querySelectorAll('[data-action="import-case"]').forEach(button=>button.disabled=true);$('#case-progress').innerHTML='<p class="loading"><span class="spinner"></span>正在整理案例并执行真实渲染检查。这可能需要几分钟，结果会保存在共享库。</p>';try{const result=await client.request('/api/cases/import',{case_id:target.dataset.id});await loadAssets();$('#case-progress').innerHTML=`<p class="success">${icon('check')}${result.styles?.length||0} 个样式已写入共享库。检查记录与保真状态随版本保存。</p><a class="button" href="#library">查看共享库</a>`;renderPage();}finally{state.busy.delete('case');document.querySelectorAll('[data-action="import-case"]').forEach(button=>button.disabled=false);}},
    'asset-detail':target=>assetDetail(target.dataset.id),
    'create-replica':target=>createReplica(target.dataset.id), 'advance-replica':target=>advanceReplica(target.dataset.id),
    'study-source':target=>{state.sourceId=target.dataset.id;setRoute('research');},
    'library-kind':target=>{state.libraryKind=target.dataset.value;renderLibrary();},
    filter:target=>{state.filter=target.dataset.value;renderProject();},
    'duplicate-project':async target=>{if(!state.project)return;target.disabled=true;try{const result=await client.request(`/api/projects/${encodeURIComponent(state.project.id)}/duplicate`,{});await refreshAll();setRoute('projects',result.project.id);toast('已建立独立制作副本，共享样式与素材继续引用固定版本。');}finally{if(target.isConnected)target.disabled=false;}},
    run:()=>startRun(), preview:()=>startJob('preview'), render:()=>startJob('render'), transcribe:()=>startJob('transcribe'), 'resume-run':()=>startRun(state.run?.id), 'cancel-run':async()=>{if(!state.run?.id)return;await client.request(`/api/runs/${encodeURIComponent(state.run.id)}/cancel`,{});toast('已请求停止；正在完成当前工具的安全退出。');}, approve:()=>batch('approve'), reject:()=>batch('reject'), reset:()=>batch('reset'),
    replace:()=>editCards([...state.selected]), 'edit-card':target=>editCards([target.dataset.id]),
    'range-start':()=>{const video=$('#research-video');if(video)$('#study-form [name="start"]').value=video.currentTime.toFixed(2);},
    'range-end':()=>{const video=$('#research-video');if(video)$('#study-form [name="end"]').value=video.currentTime.toFixed(2);},
  };
  document.addEventListener('click',event=>{const target=event.target.closest('[data-action]');if(!target||target.disabled)return;event.preventDefault();const fn=tasks[target.dataset.action];if(fn)Promise.resolve().then(()=>fn(target)).catch(showError);});
  document.addEventListener('change',event=>{const target=event.target;
    if(target.id==='select-all'){L.visibleCards(state.project,state.filter).forEach(card=>target.checked?state.selected.add(card.id):state.selected.delete(card.id));renderProject();}
    if(target.dataset.selectCard){target.checked?state.selected.add(target.dataset.selectCard):state.selected.delete(target.dataset.selectCard);renderProject();}
    if(target.id==='research-source'){state.sourceId=target.value;renderResearch();}
    if(target.id==='upload-kind')$('#asset-files').accept=target.value==='image'?'image/png,image/jpeg,image/webp':'video/*,.mp4,.mov,.mkv,.webm';
    if(target.id==='asset-files')uploadFiles(target.files).catch(showError);
    if(target.id==='replace-style'){document.querySelectorAll('[data-edit-field]').forEach(element=>{state.editing.fields[element.dataset.editField]=element.value});state.editing.styleId=target.value;state.editing.changed.clear();$('#replace-fields').innerHTML=editFields();}
    if(target.dataset.editField)state.editing.changed.add(target.dataset.editField);
  });
  document.addEventListener('input',event=>{if(event.target.dataset.editField)state.editing.changed.add(event.target.dataset.editField);if(event.target.id==='library-search'){const position=event.target.selectionStart;state.libraryQuery=event.target.value;renderLibrary();$('#library-search').focus();try{$('#library-search').setSelectionRange(position,position)}catch{}}});
  document.addEventListener('submit',event=>{const form=event.target;if(!['project-form','study-form','replace-form'].includes(form.id))return;event.preventDefault();
    Promise.resolve().then(async()=>{const buttons=[...document.querySelectorAll(`button[form="${form.id}"]`),...form.querySelectorAll('button[type="submit"]')];buttons.forEach(button=>button.disabled=true);try{
      if(form.id==='project-form'){const data=new FormData(form),payload=L.projectPayload(data.get('name'),data.get('source_id'),data.get('transcript'));const result=await client.request('/api/projects',payload);await refreshAll();setRoute('projects',result.project.id);}
      if(form.id==='replace-form')await saveReplacement();
      if(form.id==='study-form'){const data=new FormData(form),start=Number(data.get('start')),end=Number(data.get('end'));if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start)throw new Error('结束时间需要大于开始时间。');state.busy.add('study');await client.request('/api/studies',{source_id:state.sourceId,start,end,note:String(data.get('note')||'')});await loadAssets();renderResearch();toast('研究范围、原片引用与证据已保存。');}
    }finally{state.busy.delete('study');buttons.forEach(button=>{if(button.isConnected)button.disabled=false;});}}).catch(showError);
  });
  document.addEventListener('dragover',event=>{if(event.target.closest('#upload-zone')){event.preventDefault();event.target.closest('#upload-zone').classList.add('dragging');}});
  document.addEventListener('dragleave',event=>{event.target.closest('#upload-zone')?.classList.remove('dragging');});
  document.addEventListener('drop',event=>{if(event.target.closest('#upload-zone')){event.preventDefault();event.target.closest('#upload-zone').classList.remove('dragging');uploadFiles(event.dataTransfer.files).catch(showError);}});
  window.addEventListener('hashchange',()=>route().catch(showError));
  $('#dialog').addEventListener('click',event=>{if(event.target===$('#dialog')){const bounds=$('#dialog').getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)closeModal();}});
  shell();refreshAll().then(()=>route()).catch(showError);
})();
