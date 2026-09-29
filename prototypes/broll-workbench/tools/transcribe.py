#!/usr/bin/env python3
"""Local whisper.cpp large-v3-turbo adapter; no model downloads during inference."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENGINE='whisper.cpp-large-v3-turbo-q5_0'

def progress(value,message,**extra):
    print(json.dumps({'progress':value,'message':message,**extra},ensure_ascii=False),file=sys.stderr,flush=True)

def meaningful_text(text):
    """Discard punctuation/noise-only model emissions without inventing text."""
    return any(character.isalnum() for character in text)

def transcribe(source):
    cli=ROOT/'runtime/whisper.cpp/build/bin/whisper-cli'
    model=ROOT/'runtime/models/ggml-large-v3-turbo-q5_0.bin'
    if not source.is_file(): raise RuntimeError('视频文件不存在。')
    if not cli.is_file() or not model.is_file(): raise RuntimeError('本地 Whisper large-v3-turbo 环境缺失，请运行安装程序。')
    ffmpeg=shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
    with tempfile.TemporaryDirectory(prefix='lapian-transcript-') as folder:
        wav=Path(folder)/'audio.wav'; output=Path(folder)/'transcript'
        progress(.02,'正在本地提取语音……')
        result=subprocess.run([ffmpeg,'-v','error','-nostdin','-y','-i',str(source),'-vn','-map','0:a:0','-ar','16000','-ac','1',
              '-af','highpass=f=80,lowpass=f=7600,loudnorm=I=-18:TP=-1.5:LRA=11','-c:a','pcm_s16le',str(wav)],capture_output=True,timeout=1800)
        if result.returncode: raise RuntimeError('未能读取音轨，请确认视频有可用声音。')
        command=[str(cli),'-m',str(model),'-f',str(wav),'-l','auto','-oj','-of',str(output),'-pp','-t','4']
        for cpu in (False,True):
            progress(.08,'正在本地识别字幕……' if not cpu else '正在使用 CPU 继续本地识别……')
            process=subprocess.Popen(command+(['-ng'] if cpu else []),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace')
            for line in process.stdout:
                match=re.search(r'progress\s*=\s*(\d+)%',line)
                if match: progress(.08+.9*int(match[1])/100,f'正在本地识别字幕 {match[1]}%')
            code=process.wait(); process.stdout.close()
            if code==0: break
        result_path=output.with_suffix('.json')
        if code or not result_path.is_file(): raise RuntimeError('Whisper 本地识别失败，原视频与已有字幕已保留。')
        result=json.loads(result_path.read_text())
        segments=[]
        for item in result.get('transcription',[]):
            offsets=item.get('offsets',{}); text=str(item.get('text','')).strip()
            start=float(offsets.get('from',0))/1000; end=float(offsets.get('to',0))/1000
            if meaningful_text(text) and end>start and not re.fullmatch(r'\[.*\]',text):
                segments.append({'start':start,'end':end,'text':text})
        return {'engine':ENGINE,'segments':segments,'language':result.get('result',{}).get('language','auto')}

if __name__=='__main__':
    try: print(json.dumps(transcribe(Path(sys.argv[1])),ensure_ascii=False),flush=True)
    except Exception as error:
        progress(0,str(error),error=True);raise SystemExit(1)
