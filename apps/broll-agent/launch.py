"""Launch the existing workbench and its services; stop only owned children."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent


def reachable(url):
    try:
        with urlopen(url, timeout=1) as response: return response.status == 200
    except Exception: return False


def start_service(url, command, children, label):
    if reachable(url):
        return
    child = subprocess.Popen(command)
    children.append(child)
    for _ in range(100):
        if child.poll() is not None:
            raise RuntimeError(f'{label}启动失败。')
        if reachable(url):
            return
        time.sleep(.1)
    raise RuntimeError(f'{label}没有响应。')


def main():
    asset_root = Path(os.environ.get('BROLL_ASSET_ROOT', str(Path.home()/'Documents/BrollAssets')))
    project_root = Path(os.environ.get('BROLL_PROJECT_ROOT', str(Path.home()/'Documents/BrollProjects')))
    children=[]
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        start_service('http://127.0.0.1:4184/health',
            [sys.executable,str(HERE/'asset_server.py'),'--root',str(asset_root)], children, '共享资产服务')
        start_service('http://127.0.0.1:4183/api/status',
            [sys.executable,str(HERE/'server.py'),'--root',str(project_root)], children, '制作引擎')
        workbench = HERE.parents[1] / 'prototypes/broll-workbench'
        python = workbench / '.venv/bin/python'
        start_service('http://127.0.0.1:4182/api/projects',
            [str(python) if python.exists() else sys.executable,str(workbench/'server.py')], children, '观·工作台')
        print('观：http://127.0.0.1:4182/?view=ai-making\n保持此窗口开启；按 Ctrl+C 停止本次启动的服务。',flush=True)
        while True:
            if any(p.poll() is not None for p in children): raise RuntimeError('服务进程已退出。')
            time.sleep(.5)
    except KeyboardInterrupt: pass
    finally:
        for p in reversed(children):
            if p.poll() is None: p.terminate()
        for p in children:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill(); p.wait()


if __name__=='__main__': main()
