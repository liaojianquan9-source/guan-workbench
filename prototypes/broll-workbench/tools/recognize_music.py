#!/usr/bin/env python3
"""Bounded Shazam fingerprint recognition; never searches for/downloads audio."""
import asyncio
from http.client import HTTPSConnection
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode


def emit(kind, **data):
    print(json.dumps({'type':kind,**data},ensure_ascii=False),flush=True)


def windows(duration):
    if duration <= 0: return []
    end=max(0,duration-12)
    candidates=sorted(set([0.0,min(8,end)]+[float(v) for v in range(18,int(end)+1,18)]+[end]))
    if len(candidates)>12:
        candidates=[candidates[round(i*(len(candidates)-1)/11)] for i in range(12)]
    return candidates


def normalize(text):
    return re.sub(r'\W+', '', str(text).casefold())


def enrich(title,artist):
    path='/search?'+urlencode({'term':f'{artist} {title}','media':'music','entity':'song','limit':5})
    connection = HTTPSConnection('itunes.apple.com', timeout=3)
    try:
        # Keep the host and HTTPS transport fixed; song metadata must never choose
        # an arbitrary URL or local file scheme.
        connection.request('GET', path, headers={'User-Agent':'LocalVideoStudy/1.0', 'Accept':'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            return {}
        payload = response.read(500001)
        if len(payload) > 500000:
            return {}
        matches=json.loads(payload).get('results',[])
        # Do not assign a different recording's artwork on a loose first-result match.
        found=next((r for r in matches if normalize(r.get('trackName'))==normalize(title) and normalize(r.get('artistName'))==normalize(artist)),None)
        if found:
            return {'artwork_url':found.get('artworkUrl100','').replace('100x100','600x600'),'song_url':found.get('trackViewUrl',''),'genre':found.get('primaryGenreName','')}
    except Exception:
        return {}
    finally:
        connection.close()
    return {}


async def recognize(source,duration,offset=0):
    from shazamio import Shazam
    shazam=Shazam()
    positions=windows(duration); deadline=time.monotonic()+120; failures=0; completed=0
    with tempfile.TemporaryDirectory(prefix='lapian-music-') as folder:
        sample=Path(folder)/'sample.wav'
        for index,start in enumerate(positions):
            if time.monotonic()>=deadline:
                failures+=1; break
            emit('progress',value=index/max(1,len(positions)),message=f'正在识别第 {index+1}/{len(positions)} 段声音')
            result=subprocess.run([shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg','-v','error','-nostdin','-y','-ss',str(offset+start),'-i',str(source),'-t',str(min(12,duration-start)),'-vn','-ar','44100','-ac','1','-c:a','pcm_s16le',str(sample)],capture_output=True,timeout=15)
            if result.returncode: failures+=1; continue
            try:
                response=await asyncio.wait_for(shazam.recognize(str(sample)),timeout=min(10,max(1,deadline-time.monotonic())))
                if not isinstance(response,dict) or ('track' not in response and 'matches' not in response):
                    raise ValueError('invalid recognition response')
                completed+=1
                track=response.get('track')
                if not track: continue
                title=str(track.get('title','')).strip(); artist=str(track.get('subtitle','')).strip()
                if not title: raise ValueError('empty title')
                extra=await asyncio.to_thread(enrich,title,artist)
                genre=extra.get('genre') or track.get('genres',{}).get('primary','')
                emit('found',track={'key':str(track.get('key') or normalize(title+artist)), 'title':title,'artist':artist,'time':offset+start,'positions':[offset+start],
                                   'artwork_url':extra.get('artwork_url') or track.get('images',{}).get('coverart',''),
                                   'song_url':extra.get('song_url') or track.get('url',''),'tags':[genre] if genre else []})
            except Exception:
                failures+=1
        if failures:
            emit('error',message=f'有 {failures} 段声音未能完成识别（网络或服务响应异常）；已完成 {completed} 段，已有识别结果已保留。可以重试。')
            return 1
        emit('done',completed=completed)
        return 0

if __name__=='__main__':
    try: raise SystemExit(asyncio.run(recognize(Path(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3]) if len(sys.argv)>3 else 0)))
    except (Exception,KeyboardInterrupt) as error:
        emit('error',message='识曲运行中断，请检查本地环境和网络后重试。'+(' 缺少识曲依赖。' if isinstance(error,ImportError) else ''))
        raise SystemExit(1)
