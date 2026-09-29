"""Source-linked research clips. UI and model runtimes are deliberately independent."""
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid
import wave
import sys
import tempfile
from array import array
from datetime import datetime, timezone

from runtime_env import check_python_runtime, configured_python


def stamp():
    return datetime.now(timezone.utc).isoformat()


def safe_part(value, limit=22):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', str(value)).strip(' ._')
    return (text or '未命名')[:limit]


def file_time(value):
    millis = max(0, round(value * 1000))
    seconds, ms = divmod(millis, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    return (f'{hours:02}h' if hours else '') + f'{mins:02}m{sec:02}s{ms:03}'


def clip_prefix(clip):
    result = f"{safe_part(clip['source_name'])}_片段{clip['number']:02}"
    if clip.get('custom_title'):
        result += '_' + safe_part(clip['title'], 18)
    return result


def interval_name(clip, kind, extension):
    return f"{clip_prefix(clip)}_{kind}_{file_time(clip['start'])}-{file_time(clip['end'])}.{extension}"


class ResearchClips:
    def __init__(self, store, error, number, safe_input, root):
        self.store, self.Error, self.number, self.safe_input, self.root = store, error, number, safe_input, root
        self.workers = {}
        self.guard = threading.Lock()
        self.model_slot = threading.Semaphore(1)
        self.separation_python = configured_python(self.root, 'separation')
        self.separation_python_overridden = bool(os.environ.get('BROLL_SEPARATION_PYTHON'))

    def separation_runtime(self):
        check = check_python_runtime(
            self.root, 'separation',
            executable=self.separation_python if self.separation_python_overridden else None,
        )
        if not check.available:
            raise self.Error(503, check.message + '请重新运行 start.command 修复；原音和已有资料均已保留。')
        return check.executable

    def clip(self, project, clip_id, include_deleted=False):
        # Whole-source sound belongs to the project, never to a saved storyboard.
        source = project.get('source_audio')
        if source and source['id'] == clip_id:
            return source
        result = next((c for c in project.get('research_clips', []) if c['id'] == clip_id and (include_deleted or not c.get('deleted'))), None)
        if not result:
            raise self.Error(404, '找不到这个片段。')
        return result

    def revision(self, clip, body):
        expected = body.get('expected_revision')
        if isinstance(expected, bool) or not isinstance(expected, int) or expected != clip['revision']:
            raise self.Error(409, '片段已在别处修改，请重新打开核对；当前输入未覆盖已保存内容。')

    def bounds(self, project, body):
        start, end = self.number(body.get('start'), '开始时间'), self.number(body.get('end'), '结束时间')
        if start < 0 or end > project['duration'] or end - start < 1 / project['fps'] - 1e-6:
            raise self.Error(400, '片段需要至少一帧，并且位于原视频范围内。')
        return start, end

    def text(self, value, limit=120):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise self.Error(400, f'请输入 1—{limit} 字的内容。')
        return value.strip()

    def dispatch(self, project_id, body):
        action = body.get('action')
        if action in {'original', 'separate', 'cancel'}:
            return self.audio_action(project_id, body)
        s = self.store
        with s.lock(project_id):
            project = s.read(project_id)
            clips = project.setdefault('research_clips', [])
            if action == 'create':
                start, end = self.bounds(project, body)
                # Retry of one intent is idempotent, even after page/client reconnect.
                request_id = body.get('request_id')
                if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{8,80}', request_id):
                    raise self.Error(400, '保存请求标识无效。')
                old = next((c for c in clips if c.get('request_id') == request_id), None)
                if old:
                    return {'project': project, 'clip_id': old['id']}
                number = max(project.get('next_clip_number', 1), max((c['number'] + 1 for c in clips), default=1))
                source_name = Path(project['name']).stem
                title = self.text(body['title']) if body.get('title') else f'{source_name} · 片段{number:02}'
                clip = dict(id=uuid.uuid4().hex, number=number, title=title, custom_title=bool(body.get('title')),
                            source_name=source_name, source_project_id=project_id, start=start, end=end,
                            revision=0, frames=[], notes=[], sound={'status': 'idle'}, sound_history=[],
                            request_id=request_id, created_at=stamp())
                clips.append(clip)
                project['next_clip_number'] = number + 1
            else:
                clip = self.clip(project, body.get('id'), action == 'restore')
                if clip.get('scope') == 'source':
                    raise self.Error(400, '整片声音由拉片自动管理，不能作为分镜修改。')
                if action == 'capture':
                    position = self.number(body.get('time'), '画面时间')
                    frame = round(position * project['fps'])
                    position = frame / project['fps']
                    if not clip['start'] - 1e-7 <= position < clip['end']:
                        raise self.Error(400, '请先定位到这个片段内，再保存关键画面。')
                    existing = next((f for f in clip['frames'] if f['frame'] == frame and not f.get('deleted')), None)
                    if existing:
                        return {'project': project, 'clip_id': clip['id'], 'file': existing}
                self.revision(clip, body)
                if action == 'edit':
                    if 'title' in body:
                        clip['title'] = self.text(body['title'])
                        clip['custom_title'] = True
                    if 'start' in body or 'end' in body:
                        start, end = self.bounds(project, body)
                        if (start, end) != (clip['start'], clip['end']):
                            if clip['sound'].get('status') in {'queued', 'processing'}:
                                raise self.Error(409, '先取消正在处理的声音，再修改范围。')
                            old = copy.deepcopy(clip['sound'])
                            if old.get('files'):
                                old['stale'] = True
                                clip['sound_history'].append(old)
                            clip.update(start=start, end=end, sound={'status': 'idle'})
                            for f in clip['frames']:
                                f['outside'] = not start <= f['time'] < end
                            for n in clip['notes']:
                                n['outside'] = not start <= n['time'] < end
                elif action in {'delete', 'restore'}:
                    if clip['sound'].get('status') in {'queued', 'processing'}:
                        raise self.Error(409, '先取消正在处理的声音，再移除片段。')
                    clip['deleted'] = action == 'delete'
                elif action == 'capture':
                    clip['next_frame_number'] = max(clip.get('next_frame_number', 1), max((f['number'] + 1 for f in clip['frames']), default=1))
                    seq = clip['next_frame_number']
                    name = f"{clip_prefix(clip)}_画面{seq:02}_{file_time(position)}.png"
                    item, target = self.new_file(project, clip, name)
                    temp = target.with_name('.' + target.name)
                    try:
                        s.require_tools()
                        result = s.run([s.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                                        *self.safe_input, '-ss', f'{position:.9f}', '-i', str(s.directory(project_id) / 'source.mp4'),
                                        '-an', '-frames:v', '1', '-threads', '1', str(temp)], timeout=45)
                        if result.returncode or not temp.is_file() or not temp.stat().st_size:
                            raise self.Error(422, '关键画面未能保存，请移动一帧后重试。')
                        os.replace(temp, target)
                    finally:
                        temp.unlink(missing_ok=True)
                    item.update(time=position, frame=frame, number=seq, outside=False)
                    clip['frames'].append(item)
                    clip['next_frame_number'] = seq + 1
                elif action == 'note':
                    text = self.text(body.get('text'), 10000)
                    position = self.number(body.get('time'), '笔记时间')
                    if not clip['start'] <= position < clip['end']:
                        raise self.Error(400, '请在片段范围内添加时间点笔记。')
                    note_id = body.get('note_id')
                    if note_id:
                        note = next((n for n in clip['notes'] if n['id'] == note_id), None)
                        if not note:
                            raise self.Error(404, '笔记不存在。')
                        note.update(text=text, time=position, outside=False)
                    else:
                        clip['notes'].append(dict(id=uuid.uuid4().hex, time=position, text=text, created_at=stamp()))
                elif action in {'remove-frame', 'remove-note'}:
                    field = 'frames' if action == 'remove-frame' else 'notes'
                    item = next((a for a in clip[field] if a['id'] == body.get('item_id')), None)
                    if not item:
                        raise self.Error(404, '这条记录已不存在。')
                    item['deleted'] = True
                else:
                    raise self.Error(400, '不支持这个片段操作。')
                clip['revision'] += 1
            clip['updated_at'] = stamp()
            s.write(project)
            response = {'project': project, 'clip_id': clip['id']}
            if action == 'capture':
                response['file'] = item
            return response

    def new_file(self, project, clip, name):
        folder = self.store.directory(project['id']) / 'clips' / clip['id']
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        version = 2
        while target.exists():
            target = folder / f'{Path(name).stem}_v{version:02}{Path(name).suffix}'
            version += 1
        file_id = uuid.uuid4().hex
        return dict(id=file_id, filename=target.name, folder=f"clips/{clip['id']}",
                    url=f"/research-media/{project['id']}/{clip['id']}/{file_id}",
                    created_at=stamp()), target

    def file(self, project_id, clip_id, file_id):
        project = self.store.read(project_id)
        clip = self.clip(project, clip_id, True)
        items = clip['frames'] + [f for sound in [clip['sound'], *clip.get('sound_history', [])] for f in sound.get('files', {}).values()]
        item = next((f for f in items if f['id'] == file_id), None)
        if not item or Path(item['filename']).name != item['filename']:
            raise self.Error(404, '找不到这个文件。')
        folder = (self.store.directory(project_id) / 'clips' / clip['id']).resolve()
        target = (folder / item['filename']).resolve()
        if not target.is_relative_to(folder) or not target.is_file():
            raise self.Error(404, '文件不存在，请保留原项目目录。')
        return target

    @staticmethod
    def pcm_peaks(path, count=1000):
        """Read real PCM peaks in bounded blocks; retain one shared amplitude scale."""
        with wave.open(str(path), 'rb') as audio:
            if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
                raise ValueError('Expected PCM 16-bit audio')
            total, channels = audio.getnframes(), audio.getnchannels()
            peaks = []
            for index in range(count):
                remaining = round((index + 1) * total / count) - round(index * total / count)
                peak = 0
                while remaining:
                    block = min(remaining, 65536)
                    values = array('h', audio.readframes(block))
                    if sys.byteorder != 'little':
                        values.byteswap()
                    if values:
                        peak = max(peak, abs(min(values)), abs(max(values)))
                    remaining -= block
                peaks.append(round(peak / 32768, 6))
            return dict(samples=peaks, duration=total / audio.getframerate(), channels=channels,
                        sample_rate=audio.getframerate(), method='pcm-peak')

    def waveforms(self, project_id, clip_id):
        s = self.store
        project = s.read(project_id)
        clip = copy.deepcopy(self.clip(project, clip_id))
        files = clip.get('sound', {}).get('files', {})
        identity = dict(version=1, start=clip['start'], end=clip['end'],
                        files={kind: item['id'] for kind, item in files.items()})
        result = dict(identity=identity, tracks={}, duration=clip['end'] - clip['start'])
        if not project.get('has_audio'):
            return result
        folder = s.directory(project_id) / 'clips' / clip_id
        folder.mkdir(parents=True, exist_ok=True)
        cache = folder / 'waveforms.json'
        # This cache is independent from project records and model processing.
        with s.waveform_guard:
            if cache.is_file():
                try:
                    saved = json.loads(cache.read_text())
                    if saved.get('identity') == identity:
                        return saved
                except (OSError, ValueError):
                    pass
            try:
                with tempfile.TemporaryDirectory(prefix='.waveforms-', dir=folder) as temp:
                    if files.get('original'):
                        original = self.file(project_id, clip_id, files['original']['id'])
                    else:
                        original = Path(temp) / 'original.wav'
                        output = s.run([s.ffmpeg, '-v', 'error', '-nostdin', '-y', *self.safe_input,
                                        '-ss', str(clip['start']), '-i', str(s.directory(project_id) / 'source.mp4'),
                                        '-t', str(result['duration']), '-vn', '-map', '0:a:0',
                                        '-af', f"apad,atrim=duration={result['duration']}",
                                        '-ar', '8000', '-ac', '1', '-c:a', 'pcm_s16le', str(original)], timeout=120)
                        if output.returncode:
                            raise self.Error(422, '片段波形读取失败，仍可播放原片；请重试。')
                    result['tracks']['original'] = self.pcm_peaks(original)
                    for kind in ('vocals', 'background'):
                        if files.get(kind):
                            result['tracks'][kind] = self.pcm_peaks(self.file(project_id, clip_id, files[kind]['id']))
                    temporary = Path(temp) / 'waveforms.json'
                    temporary.write_text(json.dumps(result, ensure_ascii=False))
                    os.replace(temporary, cache)
            except (wave.Error, ValueError, OSError, subprocess.TimeoutExpired):
                raise self.Error(422, '片段波形读取失败，声音文件保留；请重试。') from None
            return result

    def ensure_source(self, project_id, retry=False):
        """Idempotent project audio; deleting or trimming a clip cannot remove it."""
        s = self.store
        with s.lock(project_id):
            project = s.read(project_id)
            if not project.get('has_audio'):
                return project
            clip = project.get('source_audio')
            if not clip:
                clip = dict(id=uuid.uuid4().hex, scope='source', number=0,
                            title='整片声音', source_name=Path(project['name']).stem,
                            source_project_id=project_id, start=0, end=project['duration'],
                            revision=0, frames=[], notes=[], sound={'status': 'idle'},
                            sound_history=[], created_at=stamp())
                project['source_audio'] = clip
                s.write(project)
            if clip['sound'].get('status') != 'idle' and not retry:
                return project
            try:
                return self.audio_action(project_id, {'action': 'separate', 'id': clip['id']})['project']
            except self.Error as error:
                project = s.read(project_id)
                project['source_audio']['sound'].update(status='error', message=error.message)
                s.write(project)
                return project

    def audio_action(self, project_id, body):
        s, action = self.store, body['action']
        key = f"research:{project_id}:{body.get('id')}"
        with s.lock(project_id):
            project = s.read(project_id)
            clip = self.clip(project, body.get('id'))
            if action == 'cancel':
                with self.guard:
                    event = self.workers.get(key)
                    if event:
                        event.set()
                clip['sound'].update(status='cancelled', message='已取消；原音仍可直接回听。')
                s.write(project)
                return {'project': project, 'clip_id': clip['id']}
            if not project.get('has_audio'):
                raise self.Error(422, '此视频没有音轨，可以继续研究画面与笔记。')
            if clip['sound'].get('status') in {'queued', 'processing'}:
                return {'project': project, 'clip_id': clip['id']}
            files = clip['sound'].get('files', {})
            if (action == 'original' and 'original' in files) or (action == 'separate' and {'vocals', 'background'} <= files.keys()):
                return {'project': project, 'clip_id': clip['id']}
            separation_python = self.separation_runtime() if action == 'separate' else None
            with self.guard:
                if key in self.workers:
                    raise self.Error(409, '上次任务正在停止，请稍后重试。')
                event = threading.Event()
                self.workers[key] = event
            clip['sound'].update(status='queued', message='等待本地声音处理…', start=clip['start'], end=clip['end'], task=action)
            s.write(project)
            thread = threading.Thread(
                target=self.audio_job,
                args=(project_id, clip['id'], key, event, action, separation_python),
                daemon=True,
            )
            s.jobs[key] = thread
            thread.start()
            return {'project': copy.deepcopy(project), 'clip_id': clip['id']}

    def cancellable(self, command, event, log_path, timeout=900):
        s = self.store
        # Publish a newly-created regular file over any old entry.  This never
        # follows a pre-existing symlink or hard link at the predictable name.
        temporary_log = log_path.with_name(f'.{log_path.name}.{uuid.uuid4().hex}.tmp')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary_log, flags, 0o600)
        try:
            os.replace(temporary_log, log_path)
        except Exception:
            os.close(descriptor)
            temporary_log.unlink(missing_ok=True)
            raise
        with os.fdopen(descriptor, 'w', encoding='utf-8') as log:
            process = s.spawn(command, stdout=log, stderr=subprocess.STDOUT)
            start = time.monotonic()
            try:
                while process.poll() is None:
                    if event.wait(.15) or s.stopping:
                        s.terminate(process)
                        raise self.Error(409, '已取消声音处理。')
                    if time.monotonic() - start > timeout:
                        s.terminate(process)
                        raise self.Error(422, '声音处理超时，可缩短片段后重试。')
                if process.returncode:
                    print(f'Research audio process exited {process.returncode}; log: {log_path}', flush=True)
                    raise self.Error(422, '声音处理失败，原音不受影响；可重试。')
            finally:
                s.forget(process)

    def audio_job(self, project_id, clip_id, key, event, action, separation_python=None):
        s = self.store
        started = time.monotonic()
        acquired = False
        created = []
        output = None
        try:
            while not acquired:
                if event.is_set() or s.stopping:
                    raise self.Error(409, '已取消声音处理。')
                acquired = self.model_slot.acquire(timeout=.2)
            with s.lock(project_id):
                project = s.read(project_id)
                clip = self.clip(project, clip_id)
                if event.is_set():
                    raise self.Error(409, '已取消声音处理。')
                clip['sound'].update(status='processing', message='正在提取片段原音…')
                s.write(project)
                snapshot = copy.deepcopy(clip)
            original, target = self.new_file(project, snapshot, interval_name(snapshot, '原音', 'wav'))
            folder = target.parent
            temp = target.with_name('.' + target.name)
            created.append(temp)
            length = snapshot['end'] - snapshot['start']
            self.cancellable([s.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *self.safe_input,
                              '-ss', str(snapshot['start']), '-i', str(s.directory(project_id) / 'source.mp4'), '-t', str(length),
                              '-vn', '-map', '0:a:0', '-af', f'apad,atrim=duration={length}', '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', str(temp)], event, folder / 'audio-extract.log')
            os.replace(temp, target)
            created.append(target)
            files = {'original': original}
            if action == 'separate':
                with s.lock(project_id):
                    project = s.read(project_id)
                    self.clip(project, clip_id)['sound']['message'] = '正在本机分离人声与背景声；首次加载模型稍慢…'
                    s.write(project)
                output = folder / ('.separate-' + uuid.uuid4().hex)
                output.mkdir()
                command = [str(separation_python), str(self.root / 'tools/separate_audio.py'), str(target), str(output)]
                try:
                    self.cancellable(command, event, folder / 'separation.log')
                except self.Error as error:
                    if event.is_set() or s.stopping or error.status != 422:
                        raise
                    with s.lock(project_id):
                        project = s.read(project_id)
                        self.clip(project, clip_id)['sound']['message'] = '加速处理未完成，正在使用本机兼容模式重试…'
                        s.write(project)
                    self.cancellable(command + ['--cpu'], event, folder / 'separation-cpu.log')
                model_run = json.loads((output / 'result.json').read_text())
                for kind, label in [('vocals', '人声'), ('background', '背景声')]:
                    item, destination = self.new_file(project, snapshot, interval_name(snapshot, label, 'wav'))
                    source = output / (kind + '.wav')
                    import wave
                    with wave.open(str(source), 'rb') as audio:
                        actual = audio.getnframes() / audio.getframerate()
                        if abs(actual - length) > .025:
                            raise self.Error(422, '分离声音长度与片段不一致，结果未启用。请使用原音。')
                        item['duration'] = actual
                    os.replace(source, destination)
                    created.append(destination)
                    files[kind] = item
                import shutil
                shutil.rmtree(output)
            with s.lock(project_id):
                project = s.read(project_id)
                clip = self.clip(project, clip_id)
                if event.is_set():
                    raise self.Error(409, '已取消声音处理。')
                old = clip['sound']
                if old.get('files'):
                    clip['sound_history'].append(copy.deepcopy(old))
                clip['sound'] = dict(status='ready', start=snapshot['start'], end=snapshot['end'], files=files,
                                     elapsed=round(time.monotonic() - started, 3),
                                     model='UVR-MDX-NET-Inst_HQ_3.onnx' if action == 'separate' else None,
                                     model_run=model_run if action == 'separate' else None,
                                     message='声音已保存；分离结果请与原音对照回听。' if action == 'separate' else '片段原音已保存。')
                s.write(project)
                created.clear()
            if snapshot.get('scope') == 'source' and action == 'separate':
                try:
                    s.sections.after_source(project_id)
                except Exception as error:
                    print(f'Music section scheduling failed: {error}', flush=True)
        except Exception as error:
            print(f'Research clip {clip_id}: {type(error).__name__}: {error}', flush=True)
            with s.lock(project_id):
                project = s.read(project_id)
                clip = self.clip(project, clip_id, True)
                clip['sound'].update(status='cancelled' if event.is_set() or s.stopping else 'error',
                                     message=getattr(error, 'message', '声音处理失败，可重试；原音仍可直接回听。'))
                if clip.get('scope') == 'source' and project.get('music_sections', {}).get('status') == 'waiting_audio':
                    project['music_sections'].update(status='error', message=clip['sound']['message'])
                s.write(project)
        finally:
            if output and output.exists():
                import shutil
                shutil.rmtree(output)
            for path in created:
                path.unlink(missing_ok=True)
            if acquired:
                self.model_slot.release()
            with self.guard:
                self.workers.pop(key, None)
