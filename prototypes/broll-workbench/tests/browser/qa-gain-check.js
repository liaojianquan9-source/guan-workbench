
const result=document.querySelector('#result'),a=document.querySelector('#sample');
document.querySelector('#run').onclick=async()=>{result.textContent='开始测量';try{let analyser;function Context(){const c=new AudioContext(),make=c.createGain.bind(c);c.createGain=()=>{const g=make();analyser=c.createAnalyser();analyser.fftSize=8192;g.connect(analyser);return g;};return c;}
 const engine=GainLogic.createEngine(Context);engine.apply(a,6);engine.apply(a,0);result.textContent='等待音频引擎';await engine.resume();result.textContent='等待播放';await a.play();result.textContent='正在测量';
 async function rms(db){engine.apply(a,db);await new Promise(r=>setTimeout(r,350));let sum=0;for(let i=0;i<5;i++){const values=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(values);sum+=Math.sqrt(values.reduce((n,v)=>n+v*v,0)/values.length);await new Promise(r=>setTimeout(r,45));}return sum/5;}
 const base=await rms(0),up=await rms(6),down=await rms(-12);a.pause();const r={baseRms:base,plus6DbRatio:up/base,minus12DbRatio:down/base,pass:base>.001&&Math.abs(up/base-GainLogic.amplitude(6))<.08&&Math.abs(down/base-GainLogic.amplitude(-12))<.03};result.textContent=JSON.stringify(r,null,2);engine.release(a);
}catch(e){a.pause();result.textContent=e.stack;}};
