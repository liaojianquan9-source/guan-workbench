"""Portable, verified local libraries. No archive extraction or media re-encoding."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

PROJECT_ID = re.compile(r'^[a-f0-9]{32}$')
MANIFEST = '项目清单.json'
PAYLOAD = '项目资料'
CHUNK = 1024 * 1024
RELEASE_JOURNAL_PREFIX = '.release-journal-'


def portable_project(project, *, clone=True):
    if clone: project = copy.deepcopy(project)
    for clip in [*project.get('research_clips', []), *([project['source_audio']] if project.get('source_audio') else [])]:
        for item in [*clip.get('frames', []), *[f for sound in [clip.get('sound', {}), *clip.get('sound_history', [])] for f in sound.get('files', {}).values()]]:
            item['folder'] = f"clips/{clip['id']}"
    return project


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('项目包包含无效路径。')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {'', '.', '..'} or x.startswith('.') for x in value.split('/')):
        raise ValueError('项目包包含不安全路径。')
    return p


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_json(path, data, *, backup=False):
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    backup_temp = None
    try:
        if backup:
            previous = encoded(data)
            if path.is_file():
                try:
                    previous = path.read_bytes()
                    json.loads(previous)
                except (OSError, ValueError, UnicodeDecodeError):
                    previous = None
            if previous is not None:
                backup_path = path.with_name('.' + path.name + '.backup')
                backup_temp = path.with_name(f'.{backup_path.name}.{uuid.uuid4().hex}.tmp')
                with backup_temp.open('wb') as f:
                    f.write(previous); f.flush(); os.fsync(f.fileno())
                os.replace(backup_temp, backup_path)
                fsync_directory(path.parent)
        with temp.open('wb') as f:
            f.write(encoded(data)); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
        fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)
        if backup_temp is not None: backup_temp.unlink(missing_ok=True)


def read_json_with_backup(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeDecodeError) as primary:
        backup = path.with_name('.' + path.name + '.backup')
        try:
            return json.loads(backup.read_text(encoding='utf-8'))
        except (OSError, ValueError, UnicodeDecodeError):
            raise primary


def configured_directory(legacy, config):
    if config.exists() or config.with_name('.' + config.name + '.backup').exists():
        value = read_json_with_backup(config)
        # Do not silently create an empty library when an external disk is absent.
        root = Path(value['data_directory']).expanduser().resolve()
        if not root.is_dir():
            raise RuntimeError(f'资料库暂不可用，请连接对应硬盘：{root}')
        return root
    if legacy.is_dir() and (any(legacy.glob('*/project.json')) or (legacy / 'music-library.json').exists()):
        return legacy
    return Path.home() / 'Documents' / '拉片资料库'


class StorageManager:
    def __init__(self, store, error, config_path=None):
        self.store, self.Error = store, error
        self.config_path = config_path
        self.gate = threading.RLock()
        self.active = None
        self.regular_operations = 0
        self.tasks = {}
        self.receipts = {}
        self.uploads = {}
        registry = store.data_dir / '.storage-receipts.json'
        if registry.is_file() or registry.with_name('.' + registry.name + '.backup').is_file():
            try:
                values = read_json_with_backup(registry)
                if not isinstance(values, dict): raise ValueError('invalid receipt registry')
                for key, item in values.items():
                    self.validate_manifest(item['manifest'])
                    self.receipts[key] = item
                    self.tasks[key] = {'id': key, 'action': 'migrate' if 'destination' in item else 'export',
                        'status': 'complete', 'message': '完整副本已导出；释放空间前会再次校验。',
                        'verified': True, 'can_release': True, 'destination': item.get('destination', item.get('bundle')),
                        'done_bytes': 0, 'total_bytes': 0, '_cancel': threading.Event()}
            except (ValueError, KeyError, TypeError, OSError):
                self.receipts.clear(); self.tasks.clear()
        self.recover_releases()

    def save_receipts(self):
        durable_json(self.store.data_dir / '.storage-receipts.json', self.receipts, backup=True)

    def recover_releases(self):
        """Finish or roll back a release interrupted by a crash, never guess by directory contents."""
        for journal in sorted(self.store.data_dir.glob(RELEASE_JOURNAL_PREFIX + '*.json')):
            try:
                value = read_json_with_backup(journal)
                task_id = journal.name[len(RELEASE_JOURNAL_PREFIX):-5]
                if (not PROJECT_ID.fullmatch(task_id) or not isinstance(value, dict)
                        or value.get('version') != 1 or value.get('task_id') != task_id
                        or value.get('state') not in {'prepared', 'committed'}):
                    raise ValueError('invalid release journal')
                source = Path(value['source']).resolve()
                quarantine = source / ('.release-' + task_id)
                if Path(value['quarantine']).resolve() != quarantine:
                    raise ValueError('invalid release quarantine')
                names = value.get('targets')
                if (not isinstance(names, list) or len(set(names)) != len(names)
                        or any(not (PROJECT_ID.fullmatch(str(name)) or name in {'music', 'music-library.json'}) for name in names)):
                    raise ValueError('invalid release targets')
                if value['state'] == 'prepared':
                    for name in names:
                        hidden, original = quarantine / name, source / name
                        if hidden.exists():
                            if original.exists():
                                raise RuntimeError('检测到未完成的空间释放，原位置已有同名资料，已停止自动恢复。')
                            os.replace(hidden, original)
                    fsync_directory(source)
                    receipt_id, receipt = value.get('receipt_id'), value.get('receipt')
                    if not PROJECT_ID.fullmatch(str(receipt_id)) or not isinstance(receipt, dict):
                        raise ValueError('invalid release receipt')
                    self.validate_manifest(receipt['manifest'])
                    self.receipts[receipt_id] = receipt
                    self.tasks[receipt_id] = {
                        'id': receipt_id, 'action': 'migrate' if 'destination' in receipt else 'export',
                        'status': 'complete', 'message': '上次空间释放被中断，原资料已自动恢复。',
                        'verified': True, 'can_release': True,
                        'destination': receipt.get('destination', receipt.get('bundle')),
                        'done_bytes': 0, 'total_bytes': 0, '_cancel': threading.Event(),
                    }
                    self.save_receipts()
                    if quarantine.exists(): quarantine.rmdir()
                else:
                    receipt_id = value.get('receipt_id')
                    if receipt_id in self.receipts:
                        self.receipts.pop(receipt_id, None)
                        self.tasks.pop(receipt_id, None)
                        self.save_receipts()
                    if quarantine.exists():
                        shutil.rmtree(quarantine, ignore_errors=False)
                    fsync_directory(source)
                journal.with_name('.' + journal.name + '.backup').unlink(missing_ok=True)
                journal.unlink(missing_ok=True)
                fsync_directory(journal.parent)
            except (KeyError, TypeError, OSError, ValueError) as error:
                raise RuntimeError(
                    f'发现未完成的空间释放记录，已保留所有资料。请勿删除：{journal}'
                ) from error

    def close(self):
        with self.gate:
            task = self.tasks.get(self.active)
            if task and not task.get('committing'): task['_cancel'].set()
        if task and task.get('_thread'): task['_thread'].join(timeout=10)
        for upload in list(self.uploads.values()):
            if not upload.get('writing'): shutil.rmtree(upload['path'], ignore_errors=True)

    def has_live_writers(self):
        with self.gate:
            task = self.tasks.get(self.active)
            thread = task.get('_thread') if task else None
            return (self.regular_operations > 0 or (thread is not None and thread.is_alive())
                    or any(upload.get('writing') for upload in self.uploads.values()))

    def regular_started(self):
        with self.gate:
            if self.store.stopping:
                raise self.Error(503, '本地服务正在停止，请稍后重新打开。')
            self.regular_operations += 1

    def regular_finished(self):
        with self.gate:
            self.regular_operations = max(0, self.regular_operations - 1)

    def status(self):
        with self.gate:
            return {'directory': str(self.store.data_dir), 'default_directory': str(Path.home() / 'Documents' / '拉片资料库'),
                    'active': self.public(self.tasks[self.active]) if self.active else None,
                    'tasks': [self.public(t) for t in list(self.tasks.values())[-12:]]}

    @staticmethod
    def public(task):
        return {k: v for k, v in task.copy().items() if not k.startswith('_')}

    def assert_idle(self):
        if self.active:
            raise self.Error(409, '资料正在搬运，请完成或取消后再编辑。')
        if self.regular_operations:
            raise self.Error(409, '还有读取或处理正在进行，请完成后再搬运资料。')
        if any(t.is_alive() for t in list(self.store.jobs.values())) or self.store.processes:
            raise self.Error(409, '视频或声音仍在处理中，请完成后再搬运资料。')

    def check(self, task):
        if task['_cancel'].is_set() or self.store.stopping:
            raise InterruptedError('已取消，原资料已保留。')

    def progress(self, task, message, done=None, total=None):
        with self.gate:
            task['message'] = message
            if done is not None: task['done_bytes'] = done
            if total is not None: task['total_bytes'] = total

    def new_task(self, action):
        task = {'id': uuid.uuid4().hex, 'action': action, 'status': 'running', 'message': '正在检查资料…',
                'done_bytes': 0, 'total_bytes': 0, 'verified': False, 'can_release': False,
                '_cancel': threading.Event()}
        self.tasks[task['id']] = task
        self.active = task['id']
        return task

    def start(self, body):
        with self.gate:
            self.assert_idle()
            action = body.get('action')
            if action not in {'export', 'restore', 'migrate', 'release'}:
                raise self.Error(400, '不支持这个存储操作。')
            field = 'source' if action == 'restore' else 'destination'
            if action != 'release':
                value = body.get(field)
                if not isinstance(value, str) or not value.strip() or not Path(value).expanduser().is_absolute():
                    raise self.Error(400, '请选择文件夹或填写完整路径。')
            if action == 'release' and body.get('receipt') not in self.receipts:
                raise self.Error(409, '请先完成导出和校验，再释放本机空间。')
            task = self.new_task(action)
            thread = threading.Thread(target=self.run, args=(task, dict(body)), daemon=True)
            task['_thread'] = thread
            thread.start()
            return self.public(task)

    def run(self, task, body):
        try:
            {'export': self.export, 'restore': self.restore, 'migrate': self.migrate, 'release': self.release}[task['action']](task, body)
            with self.gate:
                task.update(status='complete')
        except InterruptedError as e:
            task.update(status='cancelled', message=str(e))
        except Exception as e:
            task.update(status='error', message=getattr(e, 'message', str(e)) or '搬运失败，原资料已保留。')
        finally:
            upload = body.get('_upload')
            if upload:
                shutil.rmtree(upload, ignore_errors=True)
            with self.gate:
                if self.active == task['id']: self.active = None

    def cancel(self, task_id):
        with self.gate:
            task = self.tasks.get(task_id)
            if not task: raise self.Error(404, '找不到这个搬运任务。')
            if task.get('committing'): raise self.Error(409, '正在完成最后一步，请稍候。')
            task['_cancel'].set()
            if task['status'] == 'uploading':
                upload = self.uploads.get(task_id)
                if upload and not upload.get('writing'):
                    shutil.rmtree(self.uploads.pop(task_id)['path'], ignore_errors=True)
                    task.update(status='cancelled', message='已取消，原资料已保留。')
                    self.active = None
                else:
                    task.update(message='正在取消文件传输…')
            return self.public(task)

    def begin_commit(self, task):
        with self.gate:
            self.check(task)
            task['committing'] = True

    def inventory(self, root, ids=None, music=True):
        ids = sorted(ids if ids is not None else [p.parent.name for p in root.glob('*/project.json') if PROJECT_ID.fullmatch(p.parent.name)])
        paths = []
        for pid in ids:
            if not PROJECT_ID.fullmatch(pid) or not (root / pid / 'project.json').is_file():
                raise ValueError('项目记录不存在。')
            paths.append(root / pid)
        if music:
            paths.extend(p for p in [root / 'music', root / 'music-library.json'] if p.exists())
        result = []
        for base in paths:
            if base.is_symlink(): raise ValueError('资料包含文件夹链接，请先将链接替换为真实文件夹。')
            candidates = sorted(base.rglob('*')) if base.is_dir() else [base]
            for p in candidates:
                rel = p.relative_to(root)
                if p.is_symlink(): raise ValueError('资料包含文件链接，请先将链接替换为真实文件。')
                if not p.is_file(): continue
                if any(x.startswith('.') for x in rel.parts) or any(x in {'playback', 'previews'} for x in rel.parts[1:]): continue
                if p.name in {'waveform.json', 'waveforms.json'} or p.suffix in {'.part', '.tmp', '.log'}: continue
                data = self.metadata_bytes(p) if p.name == 'project.json' else None
                result.append((str(rel), p, data))
        return ids, result

    @staticmethod
    def metadata_bytes(path):
        return encoded(portable_project(json.loads(path.read_text(encoding='utf-8'))))

    def fingerprint(self, task, entries):
        files = []
        for rel, path, data in entries:
            self.check(task)
            digest = hashlib.sha256(); length = 0
            if data is not None:
                digest.update(data); length = len(data)
            else:
                with path.open('rb') as f:
                    while chunk := f.read(CHUNK):
                        self.check(task); digest.update(chunk); length += len(chunk)
            files.append({'path': rel, 'size': length, 'sha256': digest.hexdigest()})
        return sorted(files, key=lambda f: f['path'])

    def space(self, target, count):
        if shutil.disk_usage(target).free < count + 16 * CHUNK:
            raise ValueError('目标磁盘空间不足，请选择其他位置或先腾出空间。')

    def outside(self, target, source):
        if target == source or target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError('请选择资料库之外的独立文件夹，避免把资料复制进自身。')

    def copy_entries(self, task, entries, dest):
        total = sum(len(data) if data is not None else p.stat().st_size for _, p, data in entries)
        self.space(dest, total)
        self.progress(task, '正在复制资料…', 0, total)
        files, done = [], 0
        for rel, source, data in entries:
            self.check(task)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(); length = 0
            with target.open('xb') as out:
                if data is not None:
                    out.write(data); digest.update(data); length = len(data); done += length
                else:
                    with source.open('rb') as src:
                        while chunk := src.read(CHUNK):
                            self.check(task); out.write(chunk); digest.update(chunk); length += len(chunk); done += len(chunk)
                            self.progress(task, '正在复制资料…', done)
                out.flush(); os.fsync(out.fileno())
            self.progress(task, '正在复制资料…', done)
            files.append({'path': rel, 'size': length, 'sha256': digest.hexdigest()})
        return sorted(files, key=lambda f: f['path'])

    def validate_manifest(self, value):
        if not isinstance(value, dict) or value.get('format') != 'lapian-library' or value.get('version') != 1:
            raise ValueError('不支持这个项目包版本，请选择拉片工作台导出的完整文件夹。')
        if value.get('kind') not in {'project', 'library'}: raise ValueError('项目包类型无效。')
        ids, files = value.get('project_ids'), value.get('files')
        if not isinstance(ids, list) or any(not isinstance(x, str) or not PROJECT_ID.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
            raise ValueError('项目清单无效。')
        if value['kind'] == 'project' and len(ids) != 1: raise ValueError('单项目清单无效。')
        if not isinstance(files, list) or len(files) > 200000: raise ValueError('文件清单无效。')
        seen = set()
        for f in files:
            if not isinstance(f, dict): raise ValueError('文件清单无效。')
            p = safe_path(f.get('path')); first = p.parts[0]
            if first not in ids and not (value['kind'] == 'library' and (str(p) == 'music-library.json' or first == 'music' and len(p.parts) == 2)):
                raise ValueError('文件不属于这个项目包。')
            if str(p).casefold() in seen: raise ValueError('项目包有重复文件路径。')
            seen.add(str(p).casefold())
            if type(f.get('size')) is not int or f['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', str(f.get('sha256', ''))):
                raise ValueError('文件校验记录无效。')
        for pid in ids:
            if not {f'{pid}/project.json', f'{pid}/source.mp4'} <= seen: raise ValueError('项目包缺少原视频或项目记录。')
        value['files'] = sorted(files, key=lambda f: f['path'])
        return value

    def read_bundle(self, folder):
        path = Path(folder).expanduser().resolve()
        if not (path / MANIFEST).is_file(): raise ValueError('请选择包含“项目清单.json”的完整项目文件夹。')
        if (path / MANIFEST).stat().st_size > 64 * CHUNK: raise ValueError('项目清单过大。')
        return path, self.validate_manifest(json.loads((path / MANIFEST).read_text(encoding='utf-8')))

    def verify(self, task, root, manifest):
        manifest = self.validate_manifest(manifest)
        listed = {f['path'] for f in manifest['files']}
        self.progress(task, '正在校验文件完整性…', 0, sum(f['size'] for f in manifest['files']))
        done = 0
        for item in manifest['files']:
            self.check(task)
            p = root / item['path']
            if not p.resolve().is_relative_to(root.resolve()) or any(a.is_symlink() for a in [p, *p.parents] if a != root.parent):
                raise ValueError('项目包包含文件链接或越界路径。')
            if not p.is_file() or p.stat().st_size != item['size']: raise ValueError(f"文件缺失或大小不符：{item['path']}")
            digest = hashlib.sha256()
            with p.open('rb') as f:
                while chunk := f.read(CHUNK):
                    self.check(task); digest.update(chunk); done += len(chunk)
                    self.progress(task, '正在校验文件完整性…', done)
            if digest.hexdigest() != item['sha256']: raise ValueError(f"文件校验失败：{item['path']}")
        for pid in manifest['project_ids']:
            p = json.loads((root / pid / 'project.json').read_text(encoding='utf-8'))
            if p.get('id') != pid or not isinstance(p.get('shots'), list): raise ValueError('项目记录与清单不一致。')
            required = []
            for field in ['captures', 'audio_clips', 'exports', 'shots']:
                for asset in p.get(field, []):
                    if asset.get('deleted'): continue
                    url = asset.get('thumbnail_url' if field == 'shots' else 'url', '')
                    if url.startswith('/media/'):
                        if not url.startswith(f'/media/{pid}/'): raise ValueError('项目包含其他项目的媒体引用。')
                        required.append(url[len('/media/'):])
            for clip in [*p.get('research_clips', []), *([p['source_audio']] if p.get('source_audio') else [])]:
                if clip.get('deleted'): continue
                for asset in [*clip.get('frames', []), *[f for sound in [clip.get('sound', {}), *clip.get('sound_history', [])] for f in sound.get('files', {}).values()]]:
                    if not asset.get('deleted'):
                        required.append(f"{pid}/clips/{clip['id']}/{asset['filename']}")
            for name in required:
                safe_path(name)
                if name not in listed: raise ValueError(f'项目缺少已保存的媒体文件：{name}')
        if (root / 'music-library.json').exists():
            lib = json.loads((root / 'music-library.json').read_text())
            if not isinstance(lib.get('tracks'), list): raise ValueError('音乐库记录无效。')
            for track in lib['tracks']:
                if not PROJECT_ID.fullmatch(str(track.get('id', ''))) or not (root / 'music' / (track['id'] + '.m4a')).is_file():
                    raise ValueError('音乐库缺少对应声音文件。')

    def export(self, task, body):
        root = self.store.data_dir
        pid = body.get('project_id')
        if pid:
            self.store.read(pid)
        else:
            for project_file in root.glob('*/project.json'):
                if PROJECT_ID.fullmatch(project_file.parent.name): self.store.read(project_file.parent.name)
        ids, entries = self.inventory(root, [pid] if pid else None, not pid)
        parent = Path(body.get('destination', '')).expanduser().resolve()
        if not parent.is_dir(): raise ValueError('请选择可用的目标文件夹。')
        label = Path(self.store.read(pid)['name']).stem if pid else '拉片资料库'
        label = re.sub(r'[/\\:\x00-\x1f]', '_', label)[:70]
        target = parent / f'{label}_拉片项目_{time.strftime("%Y%m%d-%H%M%S")}_{task["id"][:6]}'
        self.outside(target, root)
        partial = parent / ('.' + target.name + '.partial')
        try:
            (partial / PAYLOAD).mkdir(parents=True)
            files = self.copy_entries(task, entries, partial / PAYLOAD)
            manifest = {'format': 'lapian-library', 'version': 1, 'kind': 'project' if pid else 'library', 'project_ids': ids, 'files': files}
            durable_json(partial / MANIFEST, manifest)
            self.verify(task, partial / PAYLOAD, manifest)
            self.begin_commit(task)
            os.replace(partial, target)
            self.receipts[task['id']] = {'source': str(root), 'bundle': str(target), 'manifest': manifest}
            self.save_receipts()
            task.update(message='导出完成，全部文件已校验。', verified=True, can_release=True, destination=str(target))
        finally:
            shutil.rmtree(partial, ignore_errors=True)

    def restore(self, task, body):
        bundle, manifest = self.read_bundle(body.get('source', ''))
        root = self.store.data_dir
        self.outside(bundle, root) if not body.get('_upload') else None
        self.verify(task, bundle / PAYLOAD, manifest)
        # Preflight all conflicts before copying or publishing any project.
        existing = set()
        for pid in manifest['project_ids']:
            if (root / pid).exists():
                _, entries = self.inventory(root, [pid], False)
                current = self.fingerprint(task, entries)
                incoming = [f for f in manifest['files'] if f['path'].startswith(pid + '/')]
                if current != incoming: raise ValueError('本机已有同一项目的不同版本，请先导出并移走本机版本，再恢复。')
                existing.add(pid)
        old_music = self.store.local_music()
        incoming_music = json.loads((bundle / PAYLOAD / 'music-library.json').read_text()) if (bundle / PAYLOAD / 'music-library.json').exists() else {'tracks': []}
        tracks = {t['id']: t for t in old_music['tracks']}
        new_files = [f for f in manifest['files'] if f['path'].split('/')[0] not in existing and f['path'] != 'music-library.json']
        for item in incoming_music['tracks']:
            if item['id'] in tracks and tracks[item['id']] != item: raise ValueError('本机存在不同版本的同一音乐记录，未覆盖。')
            tracks[item['id']] = item
        for f in list(new_files):
            if f['path'].startswith('music/') and (root / f['path']).exists():
                if self.fingerprint(task, [(f['path'], root / f['path'], None)])[0] != f: raise ValueError('本机同名音乐内容不同，未覆盖。')
                new_files.remove(f)
        staging = root / ('.restore-' + task['id'])
        published = []
        try:
            staging.mkdir()
            if body.get('_upload'):
                # Uploaded files already live on the destination volume; move instead of doubling disk usage.
                for f in new_files:
                    dest = staging / f['path']; dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(bundle / PAYLOAD / f['path'], dest)
            else:
                entries = [(f['path'], bundle / PAYLOAD / f['path'], None) for f in new_files]
                self.copy_entries(task, entries, staging)
            for f in new_files:
                # A second read catches disk failures during the destination copy.
                actual = self.fingerprint(task, [(f['path'], staging / f['path'], None)])[0]
                if actual != f: raise ValueError('恢复副本校验失败，原资料未改动。')
            self.begin_commit(task)
            with self.gate:
                try:
                    for pid in manifest['project_ids']:
                        if pid not in existing:
                            os.replace(staging / pid, root / pid); published.append(root / pid)
                    if (staging / 'music').exists():
                        (root / 'music').mkdir(exist_ok=True)
                        for f in (staging / 'music').iterdir():
                            dest = root / 'music' / f.name; os.replace(f, dest); published.append(dest)
                    if incoming_music['tracks']:
                        durable_json(root / 'music-library.json', {**old_music, 'tracks': list(tracks.values())})
                except Exception:
                    for p in reversed(published):
                        if p.is_dir(): shutil.rmtree(p)
                        else: p.unlink(missing_ok=True)
                    raise
            task.update(message=f'恢复完成：{len(manifest["project_ids"]) - len(existing)} 个项目，跳过 {len(existing)} 个相同项目。', verified=True)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def migrate(self, task, body):
        source = self.store.data_dir
        dest = Path(body.get('destination', '')).expanduser().resolve()
        self.outside(dest, source)
        destination_lock = None
        config_previous = None
        config_existed = False
        config_changed = False
        if not dest.is_dir(): raise ValueError('请选择一个空文件夹作为新的资料库。')
        try:
            # Reserve the destination before checking or writing it. A stale lock file is harmless;
            # the operating-system lock, not the file's mere presence, decides ownership.
            destination_lock = self.store.acquire_library_lock(dest)
            if any(p.name != '.workbench.lock' for p in dest.iterdir()):
                raise ValueError('请选择一个空文件夹作为新的资料库。')
            for project_file in source.glob('*/project.json'):
                if PROJECT_ID.fullmatch(project_file.parent.name): self.store.read(project_file.parent.name)
            ids, entries = self.inventory(source)
            staging = dest / ('.migration-' + task['id'])
            published = []
            staging.mkdir()
            files = self.copy_entries(task, entries, staging)
            manifest = {'format': 'lapian-library', 'version': 1, 'kind': 'library', 'project_ids': ids, 'files': files}
            self.verify(task, staging, manifest)
            self.begin_commit(task)
            with self.gate:
                try:
                    for p in list(staging.iterdir()):
                        target = dest / p.name; os.replace(p, target); published.append(target)
                    fsync_directory(dest)
                    receipt = {'source': str(source), 'destination': str(dest), 'manifest': manifest}
                    receipts = {**self.receipts, task['id']: receipt}
                    registry = dest / '.storage-receipts.json'
                    durable_json(registry, receipts, backup=True); published.append(registry)
                    if self.config_path:
                        self.config_path.parent.mkdir(parents=True, exist_ok=True)
                        config_existed = self.config_path.is_file()
                        if config_existed: config_previous = self.config_path.read_bytes()
                        durable_json(self.config_path, {'data_directory': str(dest)}, backup=True)
                        config_changed = True
                    self.receipts = receipts
                    self.store.adopt_library_directory(dest, destination_lock)
                    destination_lock = None
                except Exception:
                    config_restored = True
                    if config_changed:
                        try:
                            if config_existed:
                                previous = json.loads(config_previous)
                                durable_json(self.config_path, previous, backup=True)
                            else:
                                self.config_path.unlink(missing_ok=True)
                                self.config_path.with_name('.' + self.config_path.name + '.backup').unlink(missing_ok=True)
                                fsync_directory(self.config_path.parent)
                        except Exception:
                            # The config may already point at the fully verified destination.
                            # Keep that destination intact rather than creating a dangling config.
                            config_restored = False
                    if config_restored:
                        self.receipts.pop(task['id'], None)
                        for p in reversed(published):
                            if p.is_dir(): shutil.rmtree(p)
                            else:
                                p.unlink(missing_ok=True)
                                p.with_name('.' + p.name + '.backup').unlink(missing_ok=True)
                        fsync_directory(dest)
                    raise
            task.update(message='资料库已切换，校验完成；旧目录保留到你主动释放空间。', verified=True, can_release=True, destination=str(dest))
        finally:
            if destination_lock is not None:
                self.store.release_library_lock(destination_lock)
            if 'staging' in locals():
                shutil.rmtree(staging, ignore_errors=True)

    def release(self, task, body):
        receipt_id = body['receipt']
        receipt = self.receipts[receipt_id]
        manifest = receipt['manifest']; source = Path(receipt['source'])
        dest = Path(receipt['destination']) if 'destination' in receipt else Path(receipt['bundle']) / PAYLOAD
        self.outside(dest, source)
        self.verify(task, dest, manifest)
        _, entries = self.inventory(source, manifest['project_ids'], manifest['kind'] == 'library')
        if self.fingerprint(task, entries) != manifest['files']:
            raise ValueError('本机资料在导出后有变化，请重新导出后再释放空间。')
        self.begin_commit(task)
        quarantine = source / ('.release-' + task['id'])
        targets = [source / pid for pid in manifest['project_ids']]
        if manifest['kind'] == 'library': targets += [p for p in [source / 'music', source / 'music-library.json'] if p.exists()]
        journal = self.store.data_dir / f'{RELEASE_JOURNAL_PREFIX}{task["id"]}.json'
        journal_value = {
            'version': 1, 'state': 'prepared', 'task_id': task['id'], 'receipt_id': receipt_id,
            'receipt': receipt, 'source': str(source), 'quarantine': str(quarantine),
            'targets': [p.name for p in targets],
        }
        moved = []
        with self.gate:
            durable_json(journal, journal_value, backup=True)
            quarantine.mkdir()
            fsync_directory(source)
            try:
                for p in targets:
                    q = quarantine / p.name; os.replace(p, q); moved.append((p, q))
                fsync_directory(source)
                fsync_directory(quarantine)
                updated_receipts = {key: value for key, value in self.receipts.items() if key != receipt_id}
                self.receipts = updated_receipts
                self.save_receipts()
                journal_value['state'] = 'committed'
                durable_json(journal, journal_value, backup=True)
            except Exception:
                rollback_error = None
                try:
                    for p, q in reversed(moved):
                        if q.exists() and not p.exists(): os.replace(q, p)
                    fsync_directory(source)
                    self.receipts[receipt_id] = receipt
                    self.save_receipts()
                    if quarantine.exists(): quarantine.rmdir()
                    journal.with_name('.' + journal.name + '.backup').unlink(missing_ok=True)
                    journal.unlink(missing_ok=True)
                    fsync_directory(journal.parent)
                except Exception as error:
                    # Keep the prepared journal: startup recovery has enough information
                    # to restore the visible paths and receipt without guessing.
                    rollback_error = error
                if rollback_error:
                    raise RuntimeError('空间释放未完成，恢复记录已保留，重新打开工作台后会自动恢复。') from rollback_error
                raise
            self.tasks[receipt_id]['can_release'] = False
            try:
                shutil.rmtree(quarantine)
                fsync_directory(source)
                journal.with_name('.' + journal.name + '.backup').unlink(missing_ok=True)
                journal.unlink(missing_ok=True)
                fsync_directory(journal.parent)
                message = '已释放本机空间，完整资料保存在导出位置。'
            except OSError:
                # The durable committed journal makes this safe to finish next start.
                message = '完整资料已确认保存；剩余空间将在下次打开时自动清理。'
        task.update(message=message, verified=True)

    def prepare_upload(self, manifest):
        with self.gate:
            self.assert_idle()
            manifest = self.validate_manifest(manifest)
            self.space(self.store.data_dir, sum(f['size'] for f in manifest['files']))
            task = self.new_task('restore'); task.update(status='uploading', message='正在接收项目文件夹…')
            path = self.store.data_dir / ('.incoming-' + task['id'])
            try:
                (path / PAYLOAD).mkdir(parents=True)
                durable_json(path / MANIFEST, manifest)
            except Exception:
                shutil.rmtree(path, ignore_errors=True)
                task.update(status='error', message='无法创建恢复目录，请检查磁盘空间。')
                self.active = None
                raise
            self.uploads[task['id']] = {'path': path, 'manifest': manifest, 'received': set()}
            task['total_bytes'] = sum(f['size'] for f in manifest['files'])
            return self.public(task)

    def upload_file(self, task_id, name, stream, length):
        with self.gate:
            upload = self.uploads.get(task_id)
            if not upload or self.active != task_id: raise self.Error(404, '恢复任务已结束，请重新选择文件夹。')
            item = next((f for f in upload['manifest']['files'] if f['path'] == name), None)
            if not item or item['size'] != length or name in upload['received'] or upload.get('writing'):
                raise self.Error(400, '上传文件与项目清单不符，或上一个文件仍在传输。')
            task = self.tasks[task_id]; self.check(task)
            upload['writing'] = True
        target = upload['path'] / PAYLOAD / name
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(); left = length
        try:
            with target.open('wb') as f:
                while left:
                    chunk = stream.read(min(CHUNK, left))
                    if not chunk: raise ValueError('文件传输中断，请重试恢复。')
                    self.check(task); f.write(chunk); digest.update(chunk); left -= len(chunk)
                f.flush(); os.fsync(f.fileno())
            self.check(task)
            if digest.hexdigest() != item['sha256']: raise ValueError('文件校验失败，请使用完整的项目包。')
            with self.gate:
                upload['received'].add(name); task['done_bytes'] += length
            return self.public(task)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            with self.gate:
                upload['writing'] = False
                if task['_cancel'].is_set():
                    self.uploads.pop(task_id, None)
                    shutil.rmtree(upload['path'], ignore_errors=True)
                    task.update(status='cancelled', message='已取消，原资料已保留。')
                    if self.active == task_id: self.active = None

    def finish_upload(self, task_id):
        with self.gate:
            upload = self.uploads.get(task_id)
            if not upload or upload.get('writing') or len(upload['received']) != len(upload['manifest']['files']): raise self.Error(409, '项目文件还没有传输完整。')
            task = self.tasks[task_id]; task['status'] = 'running'
            body = {'source': str(upload['path']), '_upload': str(upload['path'])}
            thread = threading.Thread(target=self.run, args=(task, body), daemon=True)
            task['_thread'] = thread; del self.uploads[task_id]; thread.start()
            return self.public(task)

    def choose_folder(self):
        if sys.platform != 'darwin': raise self.Error(400, '请在输入框中填写文件夹的完整路径。')
        result = subprocess.run(['/usr/bin/osascript', '-e', 'POSIX path of (choose folder with prompt "选择拉片资料文件夹")'], capture_output=True, text=True, timeout=180)
        if result.returncode: return {'path': ''}
        return {'path': result.stdout.strip()}
