"""Disposable playback-only proxies. Research always reads source.mp4."""
import hashlib
import os
from pathlib import Path
import re
import threading
import uuid


class PlaybackProxies:
    FACTORS = {'half': 2, 'quarter': 4}

    def __init__(self, store, error, safe_input):
        self.store, self.error, self.safe_input = store, error, safe_input
        self.guard = threading.RLock()
        self.slot = threading.Semaphore(1)
        self.states = {}

    def identity(self, project_id, quality):
        if quality not in self.FACTORS:
            raise self.error(400, '请选择原画、标准或流畅。')
        project = self.store.read(project_id)
        source = self.store.directory(project_id) / 'source.mp4'
        stat = source.stat()
        key = hashlib.sha256(f'preview-v1:{quality}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:24]
        target = source.parent / 'playback' / f'{key}.mp4'
        return project, source, target

    def status(self, project_id, quality, start=False):
        project, source, target = self.identity(project_id, quality)
        identity = (project_id, target.stem)
        with self.guard:
            if target.is_file():
                return {'status': 'ready', 'quality': quality,
                        'url': f'/playback-media/{project_id}/{target.name}'}
            state = self.states.get(identity, {'status': 'idle', 'quality': quality})
            if start and state['status'] in {'idle', 'error'}:
                self.store.require_tools()
                state = {'status': 'processing', 'quality': quality, 'message': '正在准备低清预览，原画仍可播放。'}
                self.states[identity] = state
                thread = threading.Thread(target=self.generate, args=(identity, quality, project, source, target), daemon=True)
                self.store.jobs['playback:' + ':'.join(identity)] = thread
                thread.start()
            return dict(state)

    def generate(self, identity, quality, project, source, target):
        temp = target.with_name('.' + uuid.uuid4().hex + '.mp4')
        try:
            with self.slot:
                if self.store.stopping:
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                factor = self.FACTORS[quality]
                scale = f'scale=max(2\\,trunc(iw/{factor}/2)*2):max(2\\,trunc(ih/{factor}/2)*2)'
                result = self.store.run([
                    self.store.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-threads', '2', '-filter_threads', '1', *self.safe_input, '-i', str(source),
                    '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn', '-vf', scale,
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '25', '-pix_fmt', 'yuv420p',
                    '-threads', '2', '-fps_mode', 'passthrough', '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart', str(temp),
                ], timeout=max(120, min(project['duration'] * 5, 7200)))
                if result.returncode:
                    raise RuntimeError('低清预览生成失败，请重试。')
                metadata = self.store.probe(temp)
                if abs(metadata['duration'] - project['duration']) > max(.1, 2 / project['fps']):
                    raise RuntimeError('预览时长与原片不一致，已保留原画播放。')
                # Source files are normally immutable. Reject a proxy if one changed meanwhile.
                if self.identity(project['id'], quality)[2] != target:
                    raise RuntimeError('原视频已变化，请重新选择清晰度。')
                os.replace(temp, target)
                with self.guard:
                    self.states[identity] = {'status': 'ready', 'quality': quality,
                                            'url': f'/playback-media/{project["id"]}/{target.name}'}
        except Exception:
            with self.guard:
                self.states[identity] = {'status': 'error', 'quality': quality,
                                        'message': '低清预览生成失败，原视频未改动，请重试。'}
        finally:
            temp.unlink(missing_ok=True)

    def file(self, project_id, filename):
        self.store.read(project_id)
        if not re.fullmatch(r'[a-f0-9]{24}\.mp4', filename):
            raise self.error(404, '找不到预览视频。')
        return self.store.directory(project_id) / 'playback' / filename
