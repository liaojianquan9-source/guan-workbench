"""Conservative acoustic change suggestions, not claims of exact song boundaries."""
import json
import shutil
import subprocess
import sys
import numpy as np


def suggest_cuts(audio, rate=8000):
    hop = rate//2
    if len(audio) < 12*rate:
        return []
    frequencies = np.fft.rfftfreq(2048, 1/rate)
    bands = np.geomspace(60, rate/2, 33)
    masks = [(frequencies >= a) & (frequencies < b) for a,b in zip(bands,bands[1:])]
    features, powers = [], []
    # One second summaries suppress isolated percussion/transient effects.
    for start in range(0, len(audio)-rate+1, hop):
        piece = audio[start:start+rate]
        spectrum = np.mean([np.abs(np.fft.rfft(piece[k:k+2048]*np.hanning(2048)))**2 for k in range(0,rate-2048+1,1024)],axis=0)
        vector = np.sqrt(np.array([spectrum[mask].sum() for mask in masks]))
        features.append(vector/(np.linalg.norm(vector)+1e-12))
        powers.append(np.sqrt(np.mean(piece**2)))
    features, powers = np.array(features), np.array(powers)
    span = 8 # Four seconds on each side; boundaries remain suggestions.
    scores = np.zeros(len(features))
    noise = max(1e-5, float(np.quantile(powers,.75))*.025)
    for i in range(span, len(features)-span):
        left, right = features[i-span:i].mean(axis=0), features[i:i+span].mean(axis=0)
        similarity = np.dot(left,right)/(np.linalg.norm(left)*np.linalg.norm(right)+1e-12)
        # Silence is an optional boundary, not an identified new song.
        a,b = np.median(powers[i-span:i]), np.median(powers[i:i+span])
        if max(a,b)<noise: continue
        scores[i] = max(0,1-similarity)
        if min(a,b)<noise and max(a,b)>noise*4:scores[i]=max(scores[i],.4)
    candidates = [i for i in range(span,len(scores)-span) if scores[i]>.28 and scores[i]>=max(scores[i-4:i+5])]
    chosen=[]
    for i in sorted(candidates,key=lambda i:scores[i],reverse=True):
        time=i*.5
        if time>=6 and len(audio)/rate-time>=6 and all(abs(time-j*.5)>=8 for j in chosen):
            chosen.append(i)
        if len(chosen)>=64:break
    return [i*.5 for i in sorted(chosen)]


if __name__=='__main__':
    command=[shutil.which('ffmpeg') or 'ffmpeg','-v','error','-nostdin','-i',sys.argv[1],'-t',sys.argv[2],'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1']
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=True)
    audio=np.frombuffer(result.stdout,dtype='<f4')
    print(json.dumps({'cuts':suggest_cuts(audio),'method':'acoustic-change-suggestions-v1'}))
