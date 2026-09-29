import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, delayRender, continueRender} from 'remotion';
import type {CaseProps} from './schema';
import layout from '../specs/layout.json';
import {MotionScope, Camera, Layer, useMotion, styleFor, AnimatedGlyph, clamp} from './motion-runtime';

const chromeFringe='drop-shadow(-1.3px 0px .6px #96592270) drop-shadow(1.3px 0px .6px #12638380)';
const uri=(value:string)=>/^(data:|https?:|blob:)/.test(value)?value:staticFile(value);
const byId=new Map(layout.elements.map(e=>[e.id,e]));
const textUnits=(v:string)=>[...v].reduce((sum,c)=>sum+(/[\x00-\x7f]/.test(c)?.52:1),0);

// Radial softness remains derived from the live children.
function Optics({id,children}:{id:string;children:React.ReactNode}){
 return <AbsoluteFill data-element-id={id}>
  <AbsoluteFill style={{filter:'blur(1.2px)'}}>{children}</AbsoluteFill>
  <AbsoluteFill style={{maskImage:'radial-gradient(ellipse 510px 310px at 640px 360px,#000 25%,transparent 100%)'}}>{children}</AbsoluteFill>
 </AbsoluteFill>;
}

type LightBand={centerX:number;centerY:number;radiusX:number;radiusY:number;intensity?:number};
function Text({id,p,x,y,w,size=40,font='PingFang SC',weight=400,italic=false,fill,opacity=1,blur=0,fringe=false,metal=false,spacing=0,blend,light}:{id:string;p:CaseProps;x:number;y:number;w:number;size?:number;font?:string;weight?:number;italic?:boolean;fill?:string;opacity?:number;blur?:number;fringe?:boolean;metal?:boolean;spacing?:number;blend?:'difference';light?:LightBand}) {
 const motion=useMotion(id);
 const dynamic=styleFor(motion);
 const original=byId.get(id)?.content??'';
 const numeric=p.numbers[id];
 const content=numeric!==undefined?`${numeric}${typeof numeric==='number'?(original.endsWith('分')?' 分':original.endsWith('%')?'%':''):''}`:(p.content[id]??original);
 const fs=size*(content===original?1:Math.min(1,(textUnits(original)||1)/(textUnits(content)||1)));
 const lines=content.split('\n');
 const glyph=(line:string,i:number,color:string,mask?:string)=><AnimatedGlyph key={i} motion={motion} text={line} width={content===original?w:Math.min(w,w*textUnits(line)/Math.max(textUnits(original.replaceAll('\n','')),1))} size={size} font={p.fonts[id]??font} weight={weight} italic={italic} id={`${id}-${mask?'lit':'base'}-${i}`}><text key={i} x={0} y={size*.88+i*size*1.8} textLength={content===original?w:Math.min(w,w*textUnits(line)/Math.max(textUnits(original.replaceAll('\n','')),1))} lengthAdjust="spacingAndGlyphs" mask={mask} style={{fontFamily:p.fonts[id]??font,fontWeight:weight,fontStyle:italic?'italic':'normal',fontSize:fs,letterSpacing:spacing,fill:color,filter:metal?`url(#${id}-metal)`:undefined,paintOrder:'stroke fill',stroke:metal?'#6b6d73':undefined,strokeWidth:metal?.5:0}}>{line}</text></AnimatedGlyph>;
 return <svg data-element-id={id} aria-label={content} style={{position:'absolute',left:x,top:y,width:w,height:Math.max(size*1.5,lines.length*size*1.8),overflow:'visible',...dynamic,opacity:opacity*Number(dynamic.opacity??1),mixBlendMode:blend,filter:[fringe?chromeFringe:'',blur?`blur(${blur}px)`:'',dynamic.filter].filter(Boolean).join(' ')}}>
  {light&&<defs><radialGradient id={`${id}-light-gradient`} gradientUnits="userSpaceOnUse" cx="0" cy="0" r="1" gradientTransform={`translate(${light.centerX-x} ${light.centerY-y}) scale(${light.radiusX} ${light.radiusY})`}><stop offset="0" stopColor="white"/><stop offset=".2" stopColor="#dedede"/><stop offset=".4" stopColor="#9f9f9f"/><stop offset=".6" stopColor="#5b5b5b"/><stop offset=".8" stopColor="#262626"/><stop offset="1" stopColor="black"/></radialGradient><mask id={`${id}-light-mask`} maskUnits="userSpaceOnUse" x={-w} y={-size} width={w*3} height={size*5} style={{maskType:'luminance'}}><rect x={-w} y={-size} width={w*3} height={size*5} fill={`url(#${id}-light-gradient)`}/></mask></defs>}
  {metal&&<defs><linearGradient id={`${id}-silver`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={p.theme.metalLight}/><stop offset=".26" stopColor={p.theme.metalDark}/><stop offset=".49" stopColor={p.theme.metalLight}/><stop offset=".52" stopColor={p.theme.metalDark}/><stop offset="1" stopColor={p.theme.metalDark}/></linearGradient><filter id={`${id}-metal`} x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".56 .018" numOctaves="2" seed="8" result="grain"/><feColorMatrix in="grain" type="saturate" values="0"/><feComposite in2="SourceAlpha" operator="in" result="clipped"/><feBlend in="SourceGraphic" in2="clipped" mode="soft-light"/></filter></defs>}
  {lines.map((line,i)=>glyph(line,i,metal?`url(#${id}-silver)`:light?p.theme.accent:fill??p.theme.ink))}
  {light&&<g data-effect="feathered-light" opacity={light.intensity??1}>{lines.map((line,i)=>glyph(line,i,p.theme.ink,`url(#${id}-light-mask)`))}</g>}
 </svg>;
}

function Backdrop({s,p,kind}:{s:string;p:CaseProps;kind:'green'|'blue'}){
 const background=p.colors[`${s}-background`]??(kind==='green'?p.theme.greenBackground:p.theme.articleBackground);
 return <><AbsoluteFill data-element-id={`${s}-background`} style={{background:kind==='green'?`linear-gradient(74deg,#11160f 2%,${background} 86%)`:background}}/>
 {kind==='blue'&&<AbsoluteFill data-element-id={`${s}-texture`} style={{opacity:.06,backgroundImage:'repeating-linear-gradient(45deg, transparent 0 1px, #465164 1px 2px, transparent 2px 4px), repeating-linear-gradient(-45deg,transparent 0 1px,#26384b 1px 2px,transparent 2px 4px)'}}/>}
 {kind==='blue'&&<AbsoluteFill data-element-id={`${s}-vignette`} style={{background:'radial-gradient(ellipse at 59% 48%,transparent 20%,rgba(0,0,0,.65) 100%)'}}/>}
 </>;
}
function Problem({p}:{p:CaseProps}){
return <><Img data-element-id="problem-background" src={uri(p.assets['problem-background']??'assets/found/problem-technology-workspace-unsplash-p-xSl33Wxyc.jpg')} style={{position:'absolute',inset:0,width:1280,height:720,objectFit:'cover',objectPosition:'center center',filter:'brightness(.31) saturate(.48) sepia(.22) hue-rotate(-8deg) blur(1.4px)',scale:p.motionEnabled?1.04:1.01}}/>
 <Text id="problem-kicker" p={p} x={543} y={225} w={204} size={29} font="BrollSubtitle" fill={p.theme.secondaryInk} spacing={9}/>
 <Text id="problem-title" p={p} x={277} y={248} w={729} size={202} font="BrollDisplay" weight={400} metal fringe/>
 <Text id="problem-english" p={p} x={466} y={465} w={338} size={28} font="BrollTech" fill={p.theme.secondaryInk}/>
 </>;
}
function Article({s,p,second,foregroundOnly=false}:{s:string;p:CaseProps;second:boolean;foregroundOnly?:boolean}){
 const x=second?218:170,y=second?158:180;
 return <>{!foregroundOnly&&<Backdrop s={s} p={p} kind="blue"/>}
 <Optics id={`${s}-optics`}>
 <Layer id={`${s}-headline-highlight`} origin="center bottom" style={{position:'absolute',left:second?440:545,top:y-1,width:second?628:556,height:65,background:p.colors[`${s}-headline-highlight`]??p.theme.paper,boxShadow:'-2px 0 3px #967758,2px 0 4px #284c6a'}}/>
 <Text id={`${s}-headline-main`} p={p} x={x} y={y} w={second?850:931} size={59} font="Songti SC" weight={400} blend="difference" blur={second?.35:.1}/>
 <Text id={`${s}-english`} p={p} x={x} y={y+88} w={second?650:696} size={21} font="Arial" weight={700} opacity={.38} blur={1.5}/>
 {second&&!p.motionEnabled&&<div data-element-id="article-two-ghost-group" style={{opacity:.2,filter:'blur(4px)',position:'absolute',inset:0}}><Text id="article-two-ghost-title" p={p} x={395} y={264} w={505} size={29} font="Songti SC" fill={p.theme.paper}/><Text id="article-two-ghost-copy" p={p} x={372} y={361} w={487} size={13} font="PingFang SC"/></div>}
 {Array.from({length:6},(_,i)=><Text key={i} id={`${s}-body-${i+1}`} p={p} x={i===0||i===4?(second?254:210):(second?214:161)} y={(second?293:326)+i*(second?43:47)} w={second?(i===3?270:i===4?762:i===5?550:i===0?774:815):(i===3?813:i===4?875:i===5?855:925)} size={second?24:25} opacity={second?.82:p.motionEnabled?1:i===5?.045:i===4?.25:1} blur={second?.65:i===5?3:i===4?1.5:i===3?.7:.1} fringe={i!==0}/>) }
 </Optics></>;
}
function ArticleOverlap({p}:{p:CaseProps}){
 return <><Backdrop s="article-two" p={p} kind="blue"/><Optics id="article-two-optics">
  <div data-element-id="article-two-headline-highlight" style={{position:'absolute',left:308,top:42,width:1000,height:112,background:p.colors['article-two-headline-highlight']??p.theme.paper,opacity:.55,filter:'blur(4px)',boxShadow:'-3px 0 5px #967758,3px 0 5px #284c6a'}}/>
  <Text id="article-two-headline-main" p={p} x={-42} y={35} w={1373} size={102} font="Songti SC" weight={400} blend="difference" blur={5} opacity={.65}/>
  <Text id="article-two-english" p={p} x={98} y={164} w={1015} size={18} font="Arial" weight={700} opacity={.12} blur={2.4}/>
  <div data-element-id="article-one-headline-highlight" style={{position:'absolute',left:558,top:184,width:529,height:65,background:p.colors['article-one-headline-highlight']??p.theme.paper,boxShadow:'-2px 0 3px #967758,2px 0 4px #284c6a',opacity:.78,filter:'blur(1.2px)'}}/>
  <Text id="article-one-headline-main" p={p} x={200} y={178} w={888} size={63} font="Songti SC" weight={400} blend="difference" blur={2} opacity={.82}/>
  <Text id="article-one-english" p={p} x={166} y={257} w={938} size={21} font="Arial" weight={700} opacity={.28} blur={3.2}/>
  <div style={{position:'absolute',inset:0,opacity:.66,filter:'blur(1.3px) drop-shadow(-13px 0 2px rgba(140,190,225,.28)) drop-shadow(17px 0 2.5px rgba(225,170,145,.2))'}}>
   {Array.from({length:6},(_,i)=><Text key={`one-${i}`} id={`article-one-body-${i+1}`} p={p} x={i===0||i===4?231:189} y={292+i*45} w={i===3?813:i===4?875:i===5?855:869} size={23} opacity={i===5?.1:.48} blur={i===5?3.2:1.8} fringe/>)}
  </div>
  <div data-element-id="article-two-ghost-group" style={{opacity:.22,filter:'blur(3.2px)',position:'absolute',inset:0}}>
   <Text id="article-two-ghost-title" p={p} x={394} y={269} w={505} size={29} font="Songti SC" fill={p.theme.paper}/>
   <Text id="article-two-ghost-copy" p={p} x={371} y={365} w={487} size={13} font="PingFang SC"/>
  </div>
  <div style={{position:'absolute',inset:0,opacity:.58,filter:'blur(1.8px) drop-shadow(-18px 0 3px rgba(170,205,235,.2)) drop-shadow(22px 0 3px rgba(229,174,143,.15))'}}>
   {Array.from({length:6},(_,i)=><Text key={`two-${i}`} id={`article-two-body-${i+1}`} p={p} x={i===0||i===4?255:215} y={292+i*40} w={i===3?270:i===4?762:i===5?550:i===0?774:815} size={21} opacity={.28} blur={2.7} fringe/>)}
  </div>
 </Optics></>;
}
function Prompt({s,p,mode}:{s:string;p:CaseProps;mode:'large'|'card'|'plain'}){
 const large=mode==='large',card=mode==='card';const x=large?322:card?266:224,y=large?228:302;
 const light=p.light[s]??(large?{centerX:970,centerY:275,radiusX:1400,radiusY:1100}:card?{centerX:650,centerY:320,radiusX:690,radiusY:600}:{centerX:610,centerY:320,radiusX:660,radiusY:600});
 return <><Backdrop s={s} p={p} kind="green"/><Optics id={`${s}-optics`}>
 {mode!=='plain'&&<svg data-element-id={`${s}-outline`} viewBox="0 0 1280 720" style={{position:'absolute',inset:0,width:1280,height:720,filter:chromeFringe,opacity:large?.9:.75}}><path d={large?'M229 465V216Q229 109 335 109H1450 M407 637H1450':'M550 248H1110Q1168 248 1168 306V425Q1168 483 1110 483H758'} fill="none" stroke={p.theme.accent} strokeWidth={large?4:2.5}/></svg>}
 <div data-element-id={`${s}-light-mask`} style={{display:'contents'}}>{large?<Text id={`${s}-input`} p={p} x={x} y={y} w={1080} size={108} font="PingFang SC" light={light} fringe/>:<>
 <Text id={`${s}-line-one`} p={p} x={x} y={y-2} w={card?889:856} size={46} font="PingFang SC" light={light} fringe/>
 <Text id={`${s}-line-two`} p={p} x={x} y={y+94} w={card?508:490} size={46} font="PingFang SC" light={light} fringe/>
 <Text id={`${s}-note`} p={p} x={card?778:719} y={y+116} w={card?277:270} size={24} font="PingFang SC" fill="#8baa86" opacity={.85}/>
 </>}</div>
 </Optics></>;
}
function Arrow({id,p,x,y,up}:{id:string;p:CaseProps;x:number;y:number;up:boolean}){
const motion=useMotion(id);
return <svg data-element-id={id} viewBox="0 0 30 56" style={{position:'absolute',left:x,top:y,width:30,height:56,...styleFor(motion)}}><path d={up?'M15 53V5M3 18L15 5L27 18':'M15 3V51M3 38L15 51L27 38'} fill="none" stroke={p.colors[id]??(up?p.theme.positive:p.theme.negative)} strokeWidth="5.5" strokeLinejoin="miter"/></svg>;
}
function Table({p,foregroundOnly=false}:{p:CaseProps;foregroundOnly?:boolean}){
return <>{!foregroundOnly&&<Backdrop s="comparison" p={p} kind="green"/>}<Optics id="comparison-optics">
 <Layer id="comparison-heading-glow" style={{position:'absolute',left:100,top:154,width:1120,height:100,background:'linear-gradient(90deg,#e5dca520,transparent 31%,#d1e7b217)',filter:'blur(30px)'}}/>
 <Text id="comparison-label" p={p} x={123} y={161} w={197} size={63} fringe/>
 <Text id="comparison-model-kimi" p={p} x={470} y={158} w={222} size={73} font="BrollLatin" italic/>
 <Text id="comparison-model-claude" p={p} x={764} y={158} w={439} size={73} font="BrollLatin" italic fringe/>
 <Text id="comparison-platform-label" p={p} x={126} y={290} w={137} size={35} fringe/>
 <Text id="comparison-score-label" p={p} x={126} y={359} w={163} size={35} fringe/>
 <Text id="comparison-rate-label" p={p} x={126} y={426} w={163} size={35} fringe/>
 <Text id="comparison-kimi-platform" p={p} x={419} y={289} w={315} size={36} font="BrollLatin" italic/>
 <Text id="comparison-claude-platform" p={p} x={821} y={289} w={318} size={36} font="BrollLatin" italic fringe/>
 <Text id="comparison-kimi-score" p={p} x={419} y={357} w={99} size={35} font="BrollLatin" italic/>
 <Text id="comparison-claude-score" p={p} x={825} y={357} w={99} size={35} font="BrollLatin" italic/>
 <Text id="comparison-kimi-rate" p={p} x={419} y={423} w={60} size={35} font="BrollLatin" italic/>
 <Text id="comparison-claude-rate" p={p} x={827} y={423} w={61} size={35} font="BrollLatin" italic/>
 <Arrow id="comparison-kimi-score-arrow" p={p} x={529} y={344} up/>
 <Arrow id="comparison-claude-score-arrow" p={p} x={933} y={344} up={false}/>
 <Arrow id="comparison-kimi-rate-arrow" p={p} x={487} y={410} up/>
 <Arrow id="comparison-claude-rate-arrow" p={p} x={901} y={413} up={false}/>
 <Text id="comparison-note-one" p={p} x={123} y={493} w={1037} size={24} font="PingFang SC" opacity={.64} blur={.4} fringe/>
 <Text id="comparison-note-two" p={p} x={123} y={536} w={692} size={24} font="PingFang SC" opacity={.65} blur={.4} fringe/>
 </Optics></>;
}

export const StaticCase:React.FC<CaseProps>=(p)=>{
 const frame=useCurrentFrame();
 const [handle]=useState(()=>delayRender('Loading editable typography'));
 const [fontsReady,setFontsReady]=useState(false);
 useEffect(()=>{Promise.all([document.fonts.load('202px BrollDisplay'),document.fonts.load('italic 73px BrollLatin'),document.fonts.load('59px \"Songti SC\"'),document.fonts.ready]).then(()=>setFontsReady(true));},[]);
 useEffect(()=>{if(fontsReady)continueRender(handle);},[handle,fontsReady]);

 const s=p.sceneId==='auto'?(frame<4?'aroll':frame<80?'problem':frame<127?'article-one':frame<157?'article-overlap':frame<177?'article-two':frame<207?'prompt-large':frame<289?'prompt-card':frame<339?'prompt-plain':'comparison'):p.sceneId;
 return <AbsoluteFill data-scene-id={s} style={{background:'#fff',overflow:'hidden'}}>
  <style>{`@font-face{font-family:BrollDisplay;src:url('${staticFile('assets/fonts/YouSheBiaoTiHei.ttf')}')}@font-face{font-family:BrollSubtitle;src:local('STHeitiSC-Light')}@font-face{font-family:BrollTech;src:local('Monaco')}@font-face{font-family:BrollLatin;src:url('${staticFile('assets/fonts/Carlito-Italic.ttf')}');font-style:italic}`}</style>
  {fontsReady&&(p.motionEnabled?<MotionContent p={p}/>:s==='aroll'?<AbsoluteFill data-element-id="aroll-person-exclusion" style={{background:'#fff'}}/>:s==='problem'?<Problem p={p}/>:s==='article-overlap'?<ArticleOverlap p={p}/>:s==='article-one'||s==='article-two'?<Article s={s} p={p} second={s==='article-two'}/>:s.startsWith('prompt-')?<Prompt s={s} p={p} mode={s==='prompt-large'?'large':s==='prompt-card'?'card':'plain'}/>:<Table p={p}/>)} 
 </AbsoluteFill>;
};

// The prompt remains one continuous live group across card→plain; only its
// perimeter is removed. The actual source reframe at207 remains a hard cut.
function MotionPrompt({p,large}:{p:CaseProps;large:boolean}){
 const frame=useCurrentFrame(),s=large?'prompt-large':frame<289?'prompt-card':'prompt-plain';
 const outline=useMotion(large?'prompt-large-outline':'prompt-card-outline');
 const beam=useMotion(large?'prompt-large-light-mask':`${s}-light-mask`);
 const base=p.light[s]??(large?{centerX:970,centerY:275,radiusX:1400,radiusY:1100}:{centerX:610,centerY:320,radiusX:660,radiusY:600});
 const light={...base,centerX:base.centerX+beam.x,centerY:base.centerY+beam.y,radiusX:base.radiusX*beam.scaleX,radiusY:base.radiusY*beam.scaleY,intensity:beam.opacity};
 const t=clamp(outline.reveal);
 // Two endpoint motion progress drives a calibrated rounded-perimeter trim.
 // Start/end distances reproduce the approved252 segment; they converge at289.
 const length=2184,start=-200+511.5*t+608.5*t*t,end=1861-575*t-366*t*t;
 const path=large?`M229 ${637-172*t}V216Q229 109 335 109H${335+1115*t} M${335+72*t} 637H1450`:'M234 252H1036Q1092 252 1092 308V422Q1092 478 1036 478H234Q178 478 178 422V308Q178 252 234 252Z';
 return <Optics id={`${s}-optics`}>
  {(large||frame<289)&&<svg data-element-id={large?'prompt-large-outline':'prompt-card-outline'} viewBox="0 0 1280 720" style={{position:'absolute',inset:0,width:1280,height:720,filter:chromeFringe,opacity:(large?.9:.75)*outline.opacity}}><path d={path} pathLength={large?undefined:length} strokeDasharray={large?undefined:`${Math.max(0,end-start)} ${length-Math.max(0,end-start)}`} strokeDashoffset={large?undefined:-start} fill="none" stroke={p.theme.accent} strokeWidth={large?4:2.5}/></svg>}
  <div data-element-id={`${s}-light-mask`} style={{display:'contents'}}>{large?<Text id="prompt-large-input" p={p} x={322} y={228} w={1080} size={108} light={light} fringe/>:<>
   <Text id={`${s}-line-one`} p={p} x={224} y={300} w={856} size={46} light={light} fringe/>
   <Text id={`${s}-line-two`} p={p} x={224} y={396} w={490} size={46} light={light} fringe/>
   <Text id={`${s}-note`} p={p} x={719} y={418} w={270} size={24} fill="#8baa86" opacity={.85}/>
  </>}</div>
 </Optics>;
}
function MotionContent({p}:{p:CaseProps}){
 const frame=useCurrentFrame();
 if(frame<4)return <AbsoluteFill data-element-id="aroll-person-exclusion" style={{background:'#fff'}}/>;
 if(frame<80)return <MotionScope scope="problem"><Camera><Problem p={p}/></Camera></MotionScope>;
 if(frame<177)return <>
  <Backdrop s="article-one" p={p} kind="blue"/>
  <MotionScope scope="article-one"><Camera><Article s="article-one" p={p} second={false} foregroundOnly/></Camera></MotionScope>
  <MotionScope scope="article-two"><Camera origin="640px 334px"><Article s="article-two" p={p} second foregroundOnly/></Camera></MotionScope>
 </>;
 if(frame<339)return <>
  <Backdrop s={frame<207?'prompt-large':frame<289?'prompt-card':'prompt-plain'} p={p} kind="green"/>
  <MotionScope scope={frame<207?'prompt-large':'prompt-small'}><Camera><MotionPrompt p={p} large={frame<207}/></Camera></MotionScope>
 </>;
 return <><Backdrop s="comparison" p={p} kind="green"/><MotionScope scope="comparison"><Camera><Table p={p} foregroundOnly/></Camera></MotionScope></>;
}
