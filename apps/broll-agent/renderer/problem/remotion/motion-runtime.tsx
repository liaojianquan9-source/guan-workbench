import React, {createContext, useContext} from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import contract from '../specs/motion.json';
import bindings from '../specs/motion-bindings.json';

export type Curve = {keyframes:{frame:number;value:number}[];interpolation:string;bezier?:number[]};
type Motion = (typeof contract.motions)[number] & any;
const Context=createContext<{scope:string;frame:number}|null>(null);
export const clamp=(x:number)=>Math.max(0,Math.min(1,x));
export function bezier(t:number,b:number[]=[.22,1,.36,1]){
 const axis=(u:number,a:number,c:number)=>3*(1-u)**2*u*a+3*(1-u)*u*u*c+u**3;
 let low=0,high=1;
 for(let i=0;i<24;i++){const mid=(low+high)/2;if(axis(mid,b[0],b[2])<t)low=mid;else high=mid;}
 return axis((low+high)/2,b[1],b[3]);
}
export function sample(track:Curve|undefined,frame:number,fallback=0):number{
 if(!track)return fallback;
 const points=track.keyframes;
 if(frame<=points[0].frame)return points[0].value;
 if(frame>=points.at(-1)!.frame)return points.at(-1)!.value;
 const index=points.findIndex(p=>p.frame>=frame),a=points[index-1],b=points[index];
 const t=clamp((frame-a.frame)/(b.frame-a.frame));
 const eased=track.interpolation==='bezier'?bezier(t,track.bezier):t;
 return a.value+(b.value-a.value)*eased;
}
export function activeMotions(target:string,scope:string,frame:number):Motion[]{
 return contract.motions.filter((m:any)=>{
  const binding=(bindings.motions as any)[m.id];
  return m.targetId===target&&binding?.scope===scope&&frame>=binding.mount[0]&&frame<=binding.mount[1];
 });
}
export function evaluate(target:string,scope:string,frame:number){
 const result={x:0,y:0,scaleX:1,scaleY:1,rotationDeg:0,opacity:1,blurPx:0,brightness:1,contrast:1,saturation:1,hueRotateDeg:0,reveal:1,revealMode:'none',direction:'left-to-right',textAnimation:null as any,textOptions:{} as any};
 for(const m of activeMotions(target,scope,frame)){
  for(const key of ['x','y','rotationDeg','blurPx'] as const)result[key]+=sample(m.transform?.[key],frame,0);
  for(const key of ['scaleX','scaleY','opacity'] as const)result[key]*=sample(m.transform?.[key],frame,1);
  for(const key of ['brightness','contrast','saturation'] as const)result[key]*=sample(m.effects?.[key],frame,1);
  result.hueRotateDeg+=sample(m.effects?.hueRotateDeg,frame,0);
  if(m.reveal){result.reveal*=sample(m.reveal.progress,frame,1);result.revealMode=m.reveal.mode;result.direction=m.reveal.direction??'left-to-right';}
  if(m.textAnimation){result.textAnimation=m.textAnimation;result.textOptions=(bindings.motions as any)[m.id].glyph??{};}
 }
 return result;
}
export function useMotion(id:string){
 const context=useContext(Context);
 return context?{...evaluate(id,context.scope,context.frame),frame:context.frame,enabled:true}:{...evaluate(id,'',0),frame:0,enabled:false};
}
export function styleFor(m:ReturnType<typeof useMotion>,origin='center center'):React.CSSProperties{
 if(!m.enabled)return {};
 const filters=[m.blurPx?`blur(${m.blurPx}px)`:'',m.brightness!==1?`brightness(${m.brightness})`:'',m.contrast!==1?`contrast(${m.contrast})`:'',m.saturation!==1?`saturate(${m.saturation})`:'',m.hueRotateDeg?`hue-rotate(${m.hueRotateDeg}deg)`:''].filter(Boolean);
 const progress=clamp(m.reveal);
 return {transform:`translate(${m.x}px,${m.y}px) scale(${m.scaleX},${m.scaleY}) rotate(${m.rotationDeg}deg)`,transformOrigin:origin,opacity:m.opacity*(m.revealMode==='fade'?progress:1),filter:filters.join(' ')||undefined,...(['wipe','clip','mask'].includes(m.revealMode)?{clipPath:m.direction==='bottom-to-top'?`inset(${(1-progress)*100}% 0 0 0)`:m.direction==='top-to-bottom'?`inset(0 0 ${(1-progress)*100}% 0)`:m.direction==='right-to-left'?`inset(0 0 0 ${(1-progress)*100}%)`:`inset(0 ${(1-progress)*100}% 0 0)`}:{})};
}
export function MotionScope({scope,children}:{scope:string;children:React.ReactNode}){
 const frame=useCurrentFrame();
 const window=(bindings.scopes as any)[scope];
 if(!window||frame<window.mount[0]||frame>window.mount[1])return null;
 const visibility=evaluate('@scene',scope,frame);
 return <Context.Provider value={{scope,frame}}><AbsoluteFill data-motion-scope={scope} style={styleFor({...visibility,enabled:true,frame})}>{children}</AbsoluteFill></Context.Provider>;
}
export function Camera({children,origin='640px 360px'}:{children:React.ReactNode;origin?:string}){
 const m=useMotion('@camera');
 return <AbsoluteFill data-motion-target="@camera" style={styleFor(m,origin)}>{children}</AbsoluteFill>;
}
export function Layer({id,children,style={},origin}:{id:string;children?:React.ReactNode;style?:React.CSSProperties;origin?:string}){
 const m=useMotion(id),dynamic=styleFor(m,origin);
 return <div data-element-id={id} style={{...style,...dynamic,opacity:Number(style.opacity??1)*Number(dynamic.opacity??1),filter:[style.filter,dynamic.filter].filter(Boolean).join(' ')||undefined}}>{children}</div>;
}

// One full editable glyph is clipped into character cells only during entrance.
// Prefix advances preserve proportional Latin spacing; settled text uses the
// original single <text> node, so the approved layout is pixel-identical.
const advanceCache=new Map<string,number[]>();
export function characterEdges(text:string,font:string,size:number,weight:number,italic:boolean,width:number){
 const key=JSON.stringify([text,font,size,weight,italic,width]);
 if(advanceCache.has(key))return advanceCache.get(key)!;
 const canvas=typeof document==='undefined'?null:document.createElement('canvas');
 const ctx=canvas?.getContext('2d');
 const chars=[...text],prefix=[0];
 if(ctx)ctx.font=`${italic?'italic ':''}${weight} ${size}px "${font}"`;
 for(let i=1;i<=chars.length;i++)prefix.push(ctx?ctx.measureText(chars.slice(0,i).join('')).width:i);
 const total=prefix.at(-1)||1,edges=prefix.map(v=>v/total*width);
 advanceCache.set(key,edges);return edges;
}
export function AnimatedGlyph({motion,children,text,width,size,font,weight,italic,id}:{motion:ReturnType<typeof useMotion>;children:React.ReactElement<any>;text:string;width:number;size:number;font:string;weight:number;italic:boolean;id:string}){
 const a=motion.textAnimation;
 if(!motion.enabled||!a||motion.frame>=a.endFrame)return children;
 if(motion.frame<a.startFrame)return null;
 const chars=[...text],count=chars.length;
 if(!count)return null;
 const edges=characterEdges(text,font,size,weight,italic,width);
 const span=Math.max(1,a.endFrame-a.startFrame);
 // Stagger scales down for longer replacement strings; the endpoint never slips.
 const charSpan=Math.min(span,motion.textOptions.duration??(a.preset==='typewriter'?Math.min(2,span/count):Math.min(8,Math.max(2,span*.33))));
 const stagger=Math.min(a.staggerFrames,Math.max(0,(span-charSpan)/Math.max(1,count-1)));
 const reverse=a.direction==='right-to-left';
 return <g data-text-animation={a.preset} data-seed={a.seed}>{chars.map((_,i)=>{
  const j=reverse?count-1-i:i,start=a.startFrame+j*stagger;
  const t=clamp((motion.frame-start)/charSpan),q=a.preset==='typewriter'?t:bezier(t);
  const remaining=1-q,d=a.distancePx??0;
  const dy=a.direction==='bottom-to-top'?d*remaining:a.direction==='top-to-bottom'?-d*remaining:0;
  const dx=(a.direction==='left-to-right'?d*remaining*(.25+i/Math.max(1,count-1)):a.direction==='right-to-left'?-d*remaining:0)+(motion.textOptions.spacingPx??0)*i*remaining;
  const sy=1+((a.stretchY??1)-1)*remaining;
  const clip=`${id}-char-${i}`,glyphId=`${id}-source-glyph`;
  const alpha=motion.textOptions.opacityCurve==='quadratic-in'?t*t:q;
  return <g key={i} transform={`translate(${dx} ${dy}) translate(${edges[i]} ${size*.88}) scale(1 ${sy}) translate(${-edges[i]} ${-size*.88})`} opacity={alpha} style={{filter:(a.blurPx??0)*remaining?`blur(${(a.blurPx??0)*remaining}px)`:undefined}}>
   {i===0&&<defs>{React.cloneElement(children,{id:glyphId})}</defs>}
   <defs><clipPath id={clip}><rect x={edges[i]-(i===0?size*.25:0)} y={-size} width={edges[i+1]-edges[i]+(i===0?size*.25:0)+(i===count-1?size*.3:0)} height={size*4}/></clipPath></defs>
   <g clipPath={`url(#${clip})`}><use href={`#${glyphId}`}/></g>
  </g>;
 })}</g>;
}
