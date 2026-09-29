import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {marked} from '/Users/liaojianquan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js';

const root = '/Users/liaojianquan/Documents/ChatGPT/B-roll 剪辑/publications/ljq-broll-video-generator';
const mime = {'.png':'image/png','.gif':'image/gif','.jpg':'image/jpeg','.mp4':'video/mp4','.json':'application/json','.svg':'image/svg+xml'};
const css = `:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:#1f2328;font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.banner{background:#fff;border-bottom:1px solid #d1d9e0;padding:12px 24px;font-size:13px;color:#59636e}main{max-width:1012px;margin:24px auto;padding:32px 48px;background:#fff;border:1px solid #d1d9e0;border-radius:8px}h1,h2,h3{line-height:1.3;margin-top:1.5em;margin-bottom:.7em}h1{font-size:32px;margin-top:0;border-bottom:1px solid #d1d9e0;padding-bottom:12px}h2{font-size:24px;border-bottom:1px solid #d1d9e0;padding-bottom:8px}h3{font-size:20px}a{color:#0969da;text-decoration:none}a:hover{text-decoration:underline}p{margin:0 0 16px}img{max-width:100%;height:auto}table{border-collapse:collapse;display:block;overflow:auto;margin-bottom:20px}th,td{padding:7px 13px;border:1px solid #d1d9e0;text-align:left}tr:nth-child(even){background:#f6f8fa}pre{background:#f6f8fa;padding:16px;border-radius:6px;overflow:auto;font-size:13px;line-height:1.5}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}p code,li code,td code{padding:2px 5px;background:#eff1f3;border-radius:4px;font-size:.85em}ul,ol{padding-left:26px}li+li{margin-top:5px}@media(max-width:700px){main{margin:0;padding:24px 18px;border:0;border-radius:0}.banner{padding:10px 18px}h1{font-size:28px}}`;

http.createServer(async(req,res)=>{
  try {
    const name = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    const file = path.resolve(root, '.'+(name==='/'?'/README.md':name));
    if (!file.startsWith(root+path.sep)) { res.writeHead(403);res.end();return; }
    const bytes=await fs.readFile(file);
    if(path.extname(file)==='.md') {
      const ids=new Map();
      const content=marked.parse(bytes.toString()).replace(/<h([1-6])>([\s\S]*?)<\/h\1>/g,(_,level,html)=>{
        const plain=html.replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').replace(/&[^;]+;/g,'');
        const base=plain.toLowerCase().replace(/ /g,'-').replace(/[^\p{L}\p{N}_-]/gu,'');
        const count=ids.get(base)||0;ids.set(base,count+1);
        return `<h${level} id="${base}${count?'-'+count:''}">${html}</h${level}>`;
      });
      const english=file.endsWith('.en.md');
      res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});
      res.end(`<!doctype html><html lang="${english?'en':'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LJQ B-roll · ${path.basename(file)}</title><style>${css}</style></head><body><div class="banner">${english?'Local documentation preview · Not published to GitHub':'文档本地预览 · 尚未发布到 GitHub'}</div><main>${content}</main></body></html>`);
    } else {
      res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'text/plain; charset=utf-8'});res.end(bytes);
    }
  } catch {
    res.writeHead(404,{'Content-Type':'text/plain; charset=utf-8'});res.end('File not found');
  }
}).listen(0,'127.0.0.1',function(){console.log('Preview: http://127.0.0.1:'+this.address().port+'/');});
