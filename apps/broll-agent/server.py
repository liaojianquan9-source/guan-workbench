"""Local B-roll production HTTP application (assets run as a separate service)."""
from __future__ import annotations
import argparse
import fcntl
from http.server import ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import signal
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit
from application import Application
from asset_client import AssetClient
from asset_server import AssetHandler
from media import workbench_projects
from replica_review import import_workbench_source

HERE = Path(__file__).resolve().parent


def advance_replica_skill(app, identity, stage):
    """Turn a saved Skill failure into a failed job instead of a false success."""
    from skill_runner import SkillRunner
    replica = SkillRunner(app.assets, app.repo.root / 'skill-work').advance(identity, stage)
    event = replica.get('metadata', {}).get('skill_bridge', {}).get('events', [])[-1:]
    event = event[0] if event else {}
    if event.get('status') == 'failed':
        raise RuntimeError(event.get('error') or '复刻 Skill 失败；请查看保存的工具记录。')
    if event.get('status') == 'interrupted':
        raise RuntimeError(event.get('error') or '复刻 Skill 已中断；请查看保存的工具记录。')
    return {'replica': replica}


def media_type(path):
    with Path(path).open('rb') as f: head = f.read(32)
    if head.startswith(b'\xff\xd8'): return 'image/jpeg'
    if head.startswith(b'\x89PNG'): return 'image/png'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP': return 'image/webp'
    if b'ftyp' in head: return 'video/mp4'
    return mimetypes.guess_type(str(path))[0] or 'application/octet-stream'


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, app):
        self.app = app; self.store = app.repo
        super().__init__(address, Handler)
        port = self.server_address[1]
        self.allowed_origins = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}


class Handler(AssetHandler):
    def send_header(self, keyword, value):
        if keyword.lower() == 'content-security-policy' and not urlsplit(self.path).path.startswith('/api/'):
            value = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        super().send_header(keyword, value)

    def end_headers(self):
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    def _dispatch(self):
        if not self._validate_request(): return
        self.connection.settimeout(180)
        parsed = urlsplit(self.path); path = unquote(parsed.path); query = parse_qs(parsed.query)
        method = 'GET' if self.command == 'HEAD' else self.command
        app = self.server.app
        value = lambda key, default=None: query.get(key, [default])[0]
        if path == '/' and method == 'GET':
            self.send_response(302)
            self.send_header('Location', 'http://127.0.0.1:4182/?view=ai-making')
            self.send_header('Content-Length', '0'); self.end_headers(); return
        if method == 'GET' and path == '/api/status': return self._json(200, app.status())
        if method == 'GET' and path == '/api/assets': return self._json(200, {'assets': app.assets.list_assets(kind=value('kind'), query=value('query'))})
        if method == 'POST' and path == '/api/upload':
            return self._json(201, {'asset': self._receive_file(lambda p: app.ingest(p, value('kind', 'source'), value('name', '新素材')))})
        match = re.fullmatch(r'/api/media/([a-f0-9]{64})', path)
        if match and method == 'GET':
            file = app.assets.blob_path(match[1]); return self._file(file, media_type(file), match[1])
        if path == '/api/cases' and method == 'GET': return self._json(200, {'cases': app.replica.available_cases()})
        if path == '/api/cases/import' and method == 'POST':
            return self._json(201, app.replica.import_case(self._read_json()['case_id']))
        if path == '/api/studies' and method == 'POST':
            body = self._read_json(); source = app.assets.get_asset(body['source_id'])
            return self._json(201, {'study': app.replica.study(source, float(body['start']), float(body['end']), body.get('note', ''))})
        if path == '/api/replicas' and method == 'POST':
            from skill_runner import SkillRunner
            body = self._read_json()
            return self._json(201, {'replica': SkillRunner(app.assets, app.repo.root / 'skill-work').create(app.assets.get_asset(body['study_id']))})
        match = re.fullmatch(r'/api/replicas/([a-zA-Z0-9_-]+)(?:/(review))?', path)
        if match:
            identity, operation = match.groups()
            if method == 'GET' and not operation:
                return self._json(200, app.replica_review.detail(identity))
            if method == 'POST' and operation == 'review':
                return self._json(200, app.replica_review.review(identity, self._read_json()))
        match = re.fullmatch(r'/api/replicas/([a-zA-Z0-9_-]+)/advance', path)
        if match and method == 'POST':
            body = self._read_json(); identity = match[1]
            return self._json(202, {'job': app.start_job('replica', None,
                lambda: advance_replica_skill(app, identity, body.get('stage', 'auto')))})
        if path == '/api/workbench-projects' and method == 'GET': return self._json(200, {'projects': workbench_projects()})
        if path == '/api/workbench-source' and method == 'POST':
            return self._json(201, {'source': import_workbench_source(app, self._read_json()['project_id'])})
        if path == '/api/workbench-import' and method == 'POST': return self._json(201, {'project': app.import_workbench(self._read_json()['project_id'])})
        if path == '/api/projects':
            if method == 'GET': return self._json(200, {'projects': app.repo.list('project')})
            if method == 'POST': return self._json(201, {'project': app.create_project(self._read_json())})
        match = re.fullmatch(r'/api/projects/([a-f0-9]{32})(?:/(run|batch|preview|render|export|transcribe|duplicate))?', path)
        if match:
            identity, operation = match.groups()
            if not operation and method == 'GET': return self._json(200, {'project': app.repo.get(identity, 'project')})
            if operation == 'export' and method == 'GET':
                p = app.repo.get(identity, 'project')
                # Local paths are runtime details; exported records contain portable IDs + hashes.
                for c in p['cards']:
                    c.pop('render_path', None); c.pop('poster_path', None)
                return self._json(200, {'schema_version': 1, 'project': p, 'asset_service': app.assets.base_url,
                                        'note': '资产与所有历史版本请同时导出共享库备份。'})
            if method == 'POST':
                body = self._read_json()
                if operation == 'run': return self._json(202, {'run': app.start_run(identity, body.get('resume_run_id'))})
                if operation == 'duplicate': return self._json(201, {'project': app.duplicate(identity, body.get('name'))})
                if operation == 'batch': return self._json(200, {'project': app.batch(identity, body)})
                if operation == 'preview': return self._json(202, {'job': app.start_job('preview', identity, lambda: {'project': app.preview(identity, body.get('card_ids', []))})})
                if operation == 'render': return self._json(202, {'job': app.start_job('render', identity, lambda: app.compose(identity))})
                if operation == 'transcribe': return self._json(202, {'job': app.start_job('transcribe', identity, lambda: {'project': app.transcribe_project(identity)})})
        match = re.fullmatch(r'/api/(runs|jobs)/([a-f0-9]{32})(?:/(cancel))?', path)
        if match:
            kind, identity, operation = match.groups()
            record = app.repo.get(identity, 'run' if kind == 'runs' else 'job')
            if method == 'GET' and not operation: return self._json(200, {'run' if kind == 'runs' else 'job': record})
            if method == 'POST' and operation == 'cancel' and kind == 'runs':
                self._read_json()
                with app.guard:
                    event = app.running.get(record['project_id'])
                    if event: event.set()
                return self._json(200, {'status': 'cancel_requested'})
        match = re.fullmatch(r'/api/files/([a-f0-9]{32})/([a-zA-Z0-9-]+\.(?:mp4|jpg|json))', path)
        if match and method == 'GET':
            file = app.repo.root / 'files' / match[1] / match[2]
            return self._file(file, media_type(file))
        if path == '/api/assets/export' and method == 'GET':
            with tempfile.TemporaryDirectory(prefix='broll-export-') as folder:
                zip_path = Path(folder) / 'assets.zip'
                app.assets.export_bundle(zip_path)
                return self._file(zip_path, 'application/zip', allow_range=False)
        if method == 'GET':
            target = (HERE / 'public' / path.lstrip('/')).resolve()
            if not target.is_relative_to(HERE / 'public') or not target.is_file(): raise KeyError('页面不存在。')
            return self._file(target, mimetypes.guess_type(str(target))[0] or 'text/plain')
        raise KeyError('接口不存在。')

    def _handle(self):
        try: self._dispatch()
        except (BrokenPipeError, ConnectionResetError): pass
        except (KeyError, FileNotFoundError) as error: self.close_connection = True; self._json(404, {'error': str(error)})
        except (ValueError, TypeError) as error: self.close_connection = True; self._json(400, {'error': str(error)})
        except Exception as error: self.close_connection = True; self._json(500, {'error': str(error)})

    do_GET = do_HEAD = do_POST = do_PATCH = _handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=4183)
    parser.add_argument('--root', type=Path, default=Path.home() / 'Documents' / 'BrollProjects')
    parser.add_argument('--assets', default='http://127.0.0.1:4184')
    args = parser.parse_args(); args.root.mkdir(parents=True, exist_ok=True)
    lock = (args.root / '.app.lock').open('a+')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('这个制作资料库已由其他进程打开。')
    app = Application(args.root, AssetClient(args.assets, args.root / 'cache/blobs'))
    app.repo.recover()
    server = AppServer(('127.0.0.1', args.port), app)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    print(f'内部制作引擎：http://127.0.0.1:{args.port}；请在4182现有工作台中使用。', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: app.close(); server.server_close(); lock.close()


if __name__ == '__main__': main()
