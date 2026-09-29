'use strict';
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BrollLogic = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function() {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const localUrl = value => typeof value === 'string' && /^\/(?!\/)[^\s\\]*$/.test(value) && !/%(?:2f|5c|0a|0d)/i.test(value) ? value : '';
  const mediaUrl = asset => asset?.blob_hash && /^[a-f0-9]{64}$/.test(asset.blob_hash) ? `/api/media/${asset.blob_hash}` : '';
  const time = value => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '时间待定';
    const seconds = Math.max(0, Number(value));
    return `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${(seconds % 60).toFixed(1).padStart(4,'0')}`;
  };
  const statuses = {draft:'待审看', approved:'已通过', rejected:'已舍弃', broll:'建议画面', keep:'保留口播', gap:'缺少素材', queued:'排队中', running:'执行中', processing:'执行中', completed:'已完成', complete:'已完成', ready:'已就绪', failed:'失败', error:'失败', cancelled:'已取消', awaiting_review:'待审看', interrupted:'已中断', passed:'通过', needs_review:'待审', pending:'待处理', usable:'可使用', imported:'已入库', needs_work:'待复刻'};
  const statusLabel = value => statuses[value] || value || '未知';
  const isPending = value => ['queued','running','processing','pending'].includes(value);
  const fieldsOf = style => {
    const schema = style?.metadata?.field_schema || {};
    if (Array.isArray(schema)) return schema.map(item => ({...item, key:item.key || item.id || item.name})).filter(item => item.key);
    const fields = schema.properties || schema;
    return Object.entries(fields).map(([key, value]) => ({key, ...(typeof value === 'object' && value !== null ? value : {type:'text', label:key})}));
  };
  function parseTranscript(raw) {
    const value = String(raw || '').trim();
    if (!value) throw new Error('请填写口播文稿，或粘贴带 start、end、text 的字幕 JSON。');
    if (!/^[\[{]/.test(value)) return {transcript:value};
    let parsed;
    try { parsed = JSON.parse(value); } catch { throw new Error('字幕 JSON 格式有误，请检查引号与逗号。'); }
    const segments = Array.isArray(parsed) ? parsed : parsed?.segments;
    if (!Array.isArray(segments) || !segments.length) throw new Error('字幕 JSON 需要一个非空 segments 数组。');
    let lastEnd = -1;
    const normalized = segments.map((item, index) => {
      if (!item || typeof item.text !== 'string' || !item.text.trim() || typeof item.start !== 'number' || typeof item.end !== 'number' || !Number.isFinite(item.start) || !Number.isFinite(item.end) || item.start < 0 || item.end <= item.start) throw new Error(`第 ${index + 1} 段需要有效的 start、end 秒数和文字。`);
      if (item.start < lastEnd - 0.001) throw new Error(`第 ${index + 1} 段与上一段重叠，请先校正时间。`);
      lastEnd = item.end;
      return {start:item.start, end:item.end, text:item.text.trim(), ...(item.id ? {id:String(item.id)} : {})};
    });
    return {segments:normalized};
  }
  function projectPayload(name, sourceId, raw) {
    if (!String(name || '').trim()) throw new Error('请给制作项目起一个名称。');
    return {name:String(name).trim(), ...(sourceId ? {source_id:sourceId} : {}), ...(String(raw || '').trim() ? parseTranscript(raw) : sourceId ? {} : parseTranscript(raw))};
  }
  function visibleCards(project, filter='all') {
    const cards = project?.cards || [];
    return filter === 'all' ? cards : cards.filter(card => ['broll','keep','gap'].includes(filter) ? card.decision === filter : card.status === filter);
  }
  function batchPayload(project, selected, action, extras={}) {
    if (!project?.id || !Number.isInteger(project.revision)) throw new Error('项目版本不可用，请重新打开项目。');
    if (!['approve','reject','reset','replace'].includes(action)) throw new Error('不支持这个批量操作。');
    const ids = [...new Set(selected)].filter(id => project.cards.some(card => card.id === id));
    if (!ids.length) throw new Error('请先选择至少一张分镜卡。');
    return {revision:project.revision, card_ids:ids, action, ...(extras.fields ? {fields:extras.fields} : {}), ...(extras.style_id ? {style_id:extras.style_id} : {})};
  }
  function parseFieldValue(field, raw) {
    if (field.type === 'image' || field.type === 'asset' || field.type === 'image_asset') {
      if (!raw) return undefined;
      let ref;
      try { ref = JSON.parse(raw); } catch { throw new Error(`${field.label || field.key} 的素材引用无效。`); }
      if (!ref?.asset_id || !Number.isInteger(ref.revision) || ref.revision < 1) throw new Error(`${field.label || field.key} 的素材版本无效。`);
      return {asset_id:ref.asset_id, revision:ref.revision};
    }
    if (field.type === 'number' || field.type === 'integer') {
      if (raw === '') return undefined;
      const n = Number(raw);
      if (!Number.isFinite(n) || field.type === 'integer' && !Number.isInteger(n)) throw new Error(`${field.label || field.key} 需要有效数字。`);
      if (field.minimum !== undefined && n < field.minimum || field.maximum !== undefined && n > field.maximum) throw new Error(`${field.label || field.key} 超出允许范围。`);
      return n;
    }
    if (field.type === 'boolean') return raw === true || raw === 'true';
    const text = String(raw);
    if (field.max_length && text.length > field.max_length) throw new Error(`${field.label || field.key} 最多 ${field.max_length} 个字符。`);
    return text;
  }
  function shortDetail(value) {
    if (value === null || value === undefined) return '';
    return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  }
  class Client {
    constructor(fetcher) { this.fetch = fetcher || globalThis.fetch.bind(globalThis); }
    async request(path, body, options={}) {
      const init = {...options};
      if (body !== undefined) { init.method ||= 'POST'; init.headers = {'Content-Type':'application/json', ...(init.headers || {})}; init.body = JSON.stringify(body); }
      let response;
      try { response = await this.fetch(path, init); } catch { throw new Error('本机服务连接中断。请确认启动窗口仍然打开，再重试。'); }
      let result;
      try { result = await response.json(); } catch { throw new Error(`服务返回了无法读取的内容（${response.status}）。`); }
      if (!response.ok) { const error = new Error(result.error || result.message || `请求未完成（${response.status}）。`); error.status = response.status; throw error; }
      return result;
    }
    async upload(file, kind) {
      let response;
      try { response = await this.fetch(`/api/upload?kind=${encodeURIComponent(kind)}&name=${encodeURIComponent(file.name)}`, {method:'POST', headers:{'Content-Type':file.type || 'application/octet-stream'}, body:file}); } catch { throw new Error('上传连接中断，请重试。'); }
      let result;
      try { result = await response.json(); } catch { throw new Error('上传服务返回了无法读取的内容。'); }
      if (!response.ok) throw new Error(result.error || '文件上传失败。');
      return result.asset;
    }
  }
  async function importFiles(client, files, kind, onProgress=()=>{}) {
    const rows = [...files].map(file => ({name:file.name, status:'queued', file}));
    onProgress(rows);
    for (const row of rows) {
      row.status = 'running'; onProgress(rows);
      try { row.asset = await client.upload(row.file, kind); row.status = 'complete'; }
      catch (error) { row.status = 'error'; row.error = error.message; }
      onProgress(rows);
    }
    return rows;
  }
  return {escape,localUrl,mediaUrl,time,statusLabel,isPending,fieldsOf,parseTranscript,projectPayload,visibleCards,batchPayload,parseFieldValue,shortDetail,Client,importFiles};
});
