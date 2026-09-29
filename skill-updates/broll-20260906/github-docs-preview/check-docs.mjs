import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {marked} from '/Users/liaojianquan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js';

const root='/Users/liaojianquan/Documents/ChatGPT/B-roll 剪辑/publications/ljq-broll-video-generator';
const git=(...args)=>execFileSync('git',args,{cwd:root,encoding:'utf8'}).trim();
const changed=[...new Set([...git('diff','--name-only').split('\n'),...git('ls-files','--others','--exclude-standard').split('\n')])].filter(Boolean);
const errors=[];let links=0;let anchors=0;let images=0;
const read=p=>fs.readFileSync(path.resolve(root,p),'utf8');
const slug=s=>s.toLowerCase().replace(/<[^>]*>/g,'').replace(/ /g,'-').replace(/[^\p{L}\p{N}_-]/gu,'');
const headingIds=file=>{
  const seen=new Map();const ids=[];
  marked.walkTokens(marked.lexer(read(file)),token=>{
    if(token.type==='heading'){
      const id=slug(token.text);const count=seen.get(id)||0;seen.set(id,count+1);ids.push(id+(count?'-'+count:''));
    }
  });return ids;
};
function check(from,dest,isImage=false){
  if(/^(https?:|mailto:)/i.test(dest))return;
  links++;if(isImage)images++;
  const [pathname,anchor]=dest.split('#');
  const target=pathname?path.resolve(root,path.dirname(from),decodeURIComponent(pathname)):path.resolve(root,from);
  if(!fs.existsSync(target)){errors.push(`${from}: missing ${dest}`);return;}
  if(anchor&&target.endsWith('.md')){
    anchors++;
    if(!headingIds(target).includes(decodeURIComponent(anchor)))errors.push(`${from}: missing anchor ${dest}`);
  }
}
for(const file of changed){
  if(!file.endsWith('.md')){errors.push(`Non-document change: ${file}`);continue;}
  const content=read(file);
  marked.walkTokens(marked.lexer(content),token=>{
    if(token.type==='link'||token.type==='image')check(file,token.href,token.type==='image');
    if(token.type==='html')for(const match of token.text.matchAll(/\b(?:href|src)=["']([^"']+)["']/g))check(file,match[1],/\bsrc=/.test(match[0]));
  });
  if(/020-034|my-broll-case-motion|comparison-video\.md|锁定版本的 Python/.test(content))errors.push(`Out-of-scope or stale text: ${file}`);
}
const zh=read('docs/getting-started.md');const en=read('docs/getting-started.en.md');
const blocks=(s,lang)=>marked.lexer(s).filter(t=>t.type==='code'&&t.lang===lang).map(t=>t.text);
if(JSON.stringify(blocks(zh,'bash'))!==JSON.stringify(blocks(en,'bash')))errors.push('Installation commands differ across languages');
if(blocks(zh,'text').length!==3||blocks(en,'text').length!==3)errors.push('Expected three matching workflow prompt stages');
if(headingIds('README.md').length!==headingIds('README.en.md').length)errors.push('Homepage sections differ');
const pairs=[['README.md','README.en.md'],['docs/getting-started.md','docs/getting-started.en.md']];
for(const [a,b] of pairs){if(!read(a).includes(path.basename(b))||!read(b).includes(path.basename(a)))errors.push(`Language navigation missing: ${a}`);}
const syncFiles=['ljq-broll-layout-structure/SKILL.md','ljq-broll-layout-structure/references/element-taxonomy.md','ljq-broll-layout-structure/references/static-compositing.md','ljq-broll-layout-structure/references/visual-grammar.md','ljq-broll-motion-forensics/SKILL.md','ljq-broll-motion-forensics/references/implementation-checks.md','ljq-broll-motion-forensics/references/measurement-guide.md'];
for(const file of syncFiles){if(read('skills/'+file)!==fs.readFileSync('/Users/liaojianquan/.codex/skills/'+file,'utf8'))errors.push(`Skill sync mismatch: ${file}`);}
execFileSync('git',['diff','--check'],{cwd:root});
const result={status:errors.length?'failed':'passed',changedFiles:changed,localLinks:links,anchors,images,languageCommands:'identical',syncedGeneralSkillDocuments:syncFiles.length,scope:'Markdown only; no code, install script, video, or new case changes',verificationLimit:'Documentation and preview checks only; installation and video tests were not executed',preview:'http://127.0.0.1:50872/',errors};
fs.writeFileSync(new URL('checks.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
fs.writeFileSync(new URL('tracked-changes.patch',import.meta.url),execFileSync('git',['diff'],{cwd:root,encoding:'utf8'}));
console.log(JSON.stringify(result,null,2));
process.exitCode=errors.length?1:0;
