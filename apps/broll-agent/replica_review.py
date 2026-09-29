"""Evidence-backed review for the existing workbench; never publishes model code.

Candidate evidence is read from immutable shared snapshots, not mutable model-
provided host paths. Historical case files are read only through the explicit
case allowlist. An approval binds to exact images and does not grant code trust.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from media import extract_frame, probe, read_workbench
from replica import CASE_INDEX
from renderer import REPO

MAX_IMAGE = 32 * 1024 * 1024
MAX_JSON = 4 * 1024 * 1024


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('证据路径无效。')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value:
        raise ValueError('证据路径必须留在复刻包内。')
    return value


def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if data.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'image/webp'
    raise ValueError('静帧不是受支持的图片，不能用于审查。')


def import_workbench_source(app, identity):
    """Copy a selected source to shared storage; never creates a production project."""
    with app.guard:
        project, path = read_workbench(identity)
        actual_hash = digest(path)
        existing = next((a for a in app.assets.list_assets(kind='source')
            if isinstance(a['metadata'].get('provenance'), dict)
            and a['metadata']['provenance'].get('workbench_id') == identity), None)
        provenance = {'workbench_id': identity, 'workbench_revision': project.get('revision'), 'imported_at': stamp()}
        if existing and existing.get('blob_hash') == actual_hash:
            return existing
        if not existing:
            return app.ingest(path, 'source', project['name'], provenance)
        info = probe(path)
        if not info['has_video'] or info['duration'] <= 0:
            raise ValueError('当前工作台原片不可解码，旧共享版本仍保留。')
        blob = app.assets.put_blob(path, 'video/mp4')
        metadata = copy.deepcopy(existing['metadata'])
        metadata.update(media=info, provenance=provenance)
        return app.assets.revise_asset(existing['id'], existing['revision'], {'blob_hash': blob['sha256'], 'metadata': metadata})


class ReplicaReviewService:
    def __init__(self, assets, work_root):
        self.assets = assets
        self.work_root = Path(work_root).expanduser().resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._verified_images = set()

    def _blob(self, data):
        media_type = image_type(data)
        if len(data) > MAX_IMAGE:
            raise ValueError('静帧超过审查大小限制。')
        # put_blob accepts paths for both the in-process store and the HTTP client.
        with tempfile.NamedTemporaryFile(dir=self.work_root, suffix='.image') as file:
            file.write(data); file.flush()
            image_hash = hashlib.sha256(data).hexdigest()
            if image_hash not in self._verified_images:
                info = probe(file.name)
                if not info['has_video'] or not 0 < info['width'] * info['height'] <= 32_000_000:
                    raise ValueError('静帧不可解码或尺寸过大。')
                with tempfile.TemporaryDirectory(dir=self.work_root) as directory:
                    extract_frame(file.name, 0, Path(directory) / 'decode.jpg')
                self._verified_images.add(image_hash)
            return self.assets.put_blob(Path(file.name), media_type)['sha256']

    def _snapshot_reader(self, replica):
        bridge = replica['metadata'].get('skill_bridge', {})
        package = replica.get('blob_hash')
        if not package or package != bridge.get('package_hash'):
            return None, None
        archive = zipfile.ZipFile(self.assets.blob_path(package))
        entries = archive.infolist()
        if len({item.filename for item in entries}) != len(entries):
            archive.close(); raise ValueError('复刻包包含重名文件，无法核查证据。')
        files = {item['path']: item for item in bridge.get('files', [])}
        def read(name, limit=MAX_JSON):
            name = relative(name)
            if name not in files: raise ValueError('静帧缺少已保存的文件指纹。')
            info = archive.getinfo(name)
            if info.file_size > limit or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('静帧大小或文件类型无效。')
            data = archive.read(name)
            if len(data) != files[name]['size'] or hashlib.sha256(data).hexdigest() != files[name]['sha256']:
                raise ValueError('静帧与共享快照的指纹不一致。')
            return data
        return read, archive.close

    def _historical_reader(self, replica):
        case_id = replica['metadata'].get('case_id')
        if case_id not in CASE_INDEX:
            return None
        base = REPO / CASE_INDEX[case_id]['case_path']
        root = base.resolve()
        if base.is_symlink() or not root.is_relative_to(REPO.resolve()):
            raise ValueError('历史案例不在已登记的只读范围内。')
        def read(name, limit=MAX_JSON):
            target = base / relative(name)
            if target.is_symlink() or not target.resolve().is_relative_to(root) or target.stat().st_size > limit:
                raise ValueError('历史静帧路径或大小无效。')
            return target.read_bytes()
        return read

    def _scenes(self, replica):
        warnings = []
        close = None
        bridge = replica['metadata'].get('skill_bridge', {})
        try:
            if bridge.get('version') == 1:
                read, close = self._snapshot_reader(replica)
                origin = 'shared_skill_snapshot'
            else:
                read = self._historical_reader(replica)
                origin = 'historical_case_still'
            if not read: return [], warnings
            case = json.loads(read('case.json'))
            layout_path = case.get('files', {}).get('layout')
            if not layout_path:
                return [], ['尚未生成可审查的静态布局；已保存的原片取证不计为复刻结果。']
            layout = json.loads(read(layout_path))
            raw_scenes = layout.get('scenes', [])
            if not isinstance(raw_scenes, list) or len(raw_scenes) > 200:
                raise ValueError('布局场景列表无效。')
            scenes, ids = [], set()
            for index, item in enumerate(raw_scenes):
                scene_id = item.get('id')
                if not isinstance(scene_id, str) or not scene_id or len(scene_id) > 200 or scene_id in ids:
                    raise ValueError('布局场景必须有唯一且稳定的 ID。')
                ids.add(scene_id)
                result = {'id': scene_id, 'label': item.get('name') or item.get('label') or f'静态帧 {index+1:02}',
                    'source_time': item.get('settledFrame', {}).get('timeSeconds'), 'evidence_origin': origin,
                    'source_hash': None, 'render_hash': None, 'comparison_hash': None}
                for key, field in [('sourceStill', 'source_hash'), ('renderStill', 'render_hash'), ('comparisonStill', 'comparison_hash')]:
                    if not item.get(key): continue
                    try: result[field] = self._blob(read(item[key], MAX_IMAGE))
                    except (OSError, KeyError, ValueError, RuntimeError) as exc: warnings.append(f'{scene_id} / {key}: {exc}')
                if result['render_hash'] and result['render_hash'] == result['source_hash']:
                    warnings.append(f'{scene_id}: 原片和复刻静帧是相同文件，不能当作已生成。')
                    result['render_hash'] = None
                scenes.append(result)
            return scenes, warnings
        except (OSError, KeyError, TypeError, AttributeError, ValueError, zipfile.BadZipFile) as exc:
            # Preflight-only projects legitimately have no layout spec yet.
            return [], [f'当前没有可核查的布局静帧：{exc}']
        finally:
            if close: close()

    def detail(self, identity):
        replica = self.assets.get_asset(identity)
        if replica.get('kind') != 'replica': raise ValueError('该共享资产不是复刻项目。')
        scenes, warnings = self._scenes(replica)
        review = replica['metadata'].get('layout_review', {}).get('scenes', {})
        active = bool(replica['metadata'].get('skill_bridge', {}).get('active_run'))
        for scene in scenes:
            previous = review.get(scene['id'], {})
            same = (scene['render_hash'] and previous.get('render_hash') == scene['render_hash']
                and previous.get('source_hash') == scene['source_hash'])
            scene['review'] = previous if same else {'status': 'needs_review', 'note': ''}
        complete = bool(scenes) and all(s['render_hash'] and s['source_hash']
            and s['review'].get('status') == 'approved' for s in scenes)
        return {'replica': replica, 'scenes': scenes, 'review_available': not active,
            'layout_review_complete': complete and not active, 'warnings': warnings,
            'review_scope': '只确认当前静帧，不授予源码执行信任，不代表动效或最终成片验收。'}

    def review(self, identity, payload):
        detail = self.detail(identity)
        replica = detail['replica']
        if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != replica['revision']:
            raise ValueError('Revision conflict：复刻已更新，请重新审看当前版本。')
        if not detail['review_available']:
            raise ValueError('复刻正在生成，请等待这一轮保存后再审查。')
        scene = next((s for s in detail['scenes'] if s['id'] == payload.get('scene_id')), None)
        if not scene or not scene['render_hash'] or not scene['source_hash']:
            raise ValueError('缺少真实复刻或原片取证静帧，不能提交审查。')
        if payload.get('render_hash') != scene['render_hash']:
            raise ValueError('Render conflict：静帧已变化，请审看当前产物。')
        action, note = payload.get('action'), payload.get('note', '')
        if action not in ('approve', 'changes') or not isinstance(note, str) or len(note) > 10000:
            raise ValueError('审查操作或意见无效。')
        if action == 'changes' and not note.strip(): raise ValueError('要求修改时必须说明具体问题。')
        record = {'status': 'approved' if action == 'approve' else 'changes', 'note': note.strip(),
            'render_hash': scene['render_hash'], 'source_hash': scene['source_hash'],
            'reviewed_revision': replica['revision'], 'reviewer': 'user', 'time': stamp()}
        metadata = copy.deepcopy(replica['metadata'])
        review = metadata.setdefault('layout_review', {'version': 1, 'scenes': {}, 'history': []})
        review['scenes'][scene['id']] = record
        review.setdefault('history', []).append({'scene_id': scene['id'], **record})
        self.assets.revise_asset(identity, replica['revision'], {'metadata': metadata})
        return self.detail(identity)
