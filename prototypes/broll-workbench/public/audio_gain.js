(function(root){
 'use strict';
 const minDb=-60,maxDb=12;
 const clampDb=value=>Number.isFinite(value)?Math.max(minDb,Math.min(maxDb,Math.round(value*10)/10)):0;
 const amplitude=db=>Math.pow(10,clampDb(db)/20);
 // 0 dB sits at the centre; each half has its own range.
 const position=db=>{db=clampDb(db);return db>=0?.5-db/maxDb*.5:.5+db/minDb*.5;};
 const fromPosition=y=>clampDb(y<=.5?(1-y*2)*maxDb:-(y-.5)*2*-minDb);
 const label=db=>(db>0?'+':'')+Number(clampDb(db).toFixed(1))+' dB';
 function wave(samples,columns=250){if(!samples?.length)return '';const count=Math.max(1,Math.floor(columns)),bars=[];for(let i=0;i<count;i++){const a=Math.floor(i*samples.length/count),b=Math.max(a+1,Math.floor((i+1)*samples.length/count));let peak=0;if(count>samples.length){const at=count===1?0:i*(samples.length-1)/(count-1),left=Math.floor(at),mix=at-left;peak=(Number(samples[left])||0)*(1-mix)+(Number(samples[Math.min(left+1,samples.length-1)])||0)*mix;}else{for(let j=a;j<b;j++)peak=Math.max(peak,Number(samples[j])||0);}const height=Math.min(1,Math.max(0,peak)*3)*47;bars.push(`M${Number(((i+.5)*1000/count).toFixed(2))},49 V${Number((49-height).toFixed(2))}`);}return bars.join(' ');}
 function createEngine(Context){let context=null;const nodes=new WeakMap();
  function bind(media){if(!Context)throw new Error('当前浏览器不支持音轨增益，请使用支持 Web Audio 的浏览器。');if(!context)context=new Context();let node=nodes.get(media);if(!node){node={source:context.createMediaElementSource(media),gain:context.createGain(),connected:false,target:null};nodes.set(media,node);}if(!node.connected){node.source.connect(node.gain);node.gain.connect(context.destination);node.connected=true;}return node;}
  function apply(media,db,wanted=true){if(!media||(!context&&db===0))return;const node=bind(media),target=wanted?amplitude(db):0;if(node.target!==target){node.gain.gain.cancelScheduledValues(context.currentTime);node.gain.gain.setTargetAtTime(target,context.currentTime,.012);node.target=target;}return node;}
  function resume(){if(context?.state==='suspended')return context.resume();return Promise.resolve();}
  function release(media){const n=nodes.get(media);if(n?.connected){n.source.disconnect();n.gain.disconnect();n.connected=false;}}
  return {apply,resume,release};
 }
 const api={minDb,maxDb,clampDb,amplitude,position,fromPosition,label,wave,createEngine};
 if(typeof module!=='undefined')module.exports=api;else{root.GainLogic=api;root.AudioGain=createEngine(root.AudioContext||root.webkitAudioContext);}
})(typeof globalThis!=='undefined'?globalThis:this);
