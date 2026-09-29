import copy
import http.client
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import server
from storage import (MANIFEST, PAYLOAD, RELEASE_JOURNAL_PREFIX, StorageManager,
                     configured_directory, durable_json, encoded, fsync_directory)

PID = 'a' * 32
SID = 'b' * 32
MID = 'c' * 32

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.store = server.ProjectStore(self.root / 'local')
        self.manager = self.store.storage
        self.external = self.root / 'external'; self.external.mkdir()
        p = self.store.directory(PID); p.mkdir()
        self.project = {'id': PID, 'name': '黄仁勋.mp4', 'duration': 10, 'fps': 30, 'status': 'ready', 'updated_at': 'today',
            'shots': [{'id': 'shot1', 'title': '估值数字动画', 'start': 0, 'end': 10, 'tag': '画面', 'note': '研究笔记'}],
            'transcript': {'status': 'ready', 'revision': 3, 'segments': [{'start': 1, 'end': 4, 'text': '修改后的字幕'}]},
            'research_clips': [{'id': SID, 'frames': [{'id': 'frame', 'filename': '画面.png', 'folder': str(p / 'clips' / SID)}],
                'sound': {'status': 'ready', 'files': {'vocals': {'id': 'voice', 'filename': '人声.wav', 'folder': str(p / 'clips' / SID)}}}}],
            'music_sections': {'status': 'ready', 'sections': [{'start': 0, 'end': 10, 'title': '配乐'}]}}
        (p / 'project.json').write_bytes(encoded(self.project))
        for name, data in [('source.mp4', b'video-content' * 100), (f'clips/{SID}/画面.png', b'picture'), (f'clips/{SID}/人声.wav', b'audio'), ('playback/preview.mp4', b'cache'), ('waveform.json', b'cache')]:
            f = p / name; f.parent.mkdir(exist_ok=True, parents=True); f.write_bytes(data)

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def run_task(self, **body):
        task = self.manager.start(body)
        self.manager.tasks[task['id']]['_thread'].join(10)
        self.assertIsNone(self.manager.active)
        return self.manager.public(self.manager.tasks[task['id']])

    def export(self, library=False):
        result = self.run_task(action='export', destination=str(self.external), **({} if library else {'project_id': PID}))
        self.assertEqual(result['status'], 'complete', result)
        return result

    def test_project_round_trip_releases_bytes_and_keeps_edits(self):
        result = self.export(); bundle = Path(result['destination'])
        manifest = json.loads((bundle / MANIFEST).read_text())
        names = [f['path'] for f in manifest['files']]
        self.assertNotIn(PID + '/waveform.json', names)
        self.assertNotIn(PID + '/playback/preview.mp4', names)
        self.assertTrue(all(not f['path'].startswith('/') for f in manifest['files']))
        portable = json.loads((bundle / PAYLOAD / PID / 'project.json').read_text())
        self.assertEqual(portable['research_clips'][0]['frames'][0]['folder'], 'clips/' + SID)
        release = self.run_task(action='release', receipt=result['id'])
        self.assertEqual(release['status'], 'complete', release)
        self.assertFalse(self.store.directory(PID).exists())
        renamed = self.external / '移动过的项目'; bundle.rename(renamed)
        restored = self.run_task(action='restore', source=str(renamed))
        self.assertEqual(restored['status'], 'complete', restored)
        p = self.store.read(PID)
        self.assertEqual((p['shots'][0]['start'], p['shots'][0]['end']), (0, 10))
        self.assertEqual(p['shots'][0]['title'], '估值数字动画')
        self.assertEqual(p['shots'][0]['note'], '研究笔记')
        self.assertEqual(p['transcript']['segments'][0]['text'], '修改后的字幕')
        self.assertIn('修改后的字幕', self.store.export(PID, 'srt')[0].decode())
        self.assertEqual((self.store.directory(PID) / f'clips/{SID}/人声.wav').read_bytes(), b'audio')
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(self.store.jobs, {})

    def test_changed_local_data_cannot_be_released(self):
        result = self.export()
        p = self.store.read(PID); p['shots'][0]['title'] = '新修改'; self.store.write(p)
        release = self.run_task(action='release', receipt=result['id'])
        self.assertEqual(release['status'], 'error')
        self.assertTrue(self.store.directory(PID).exists())

    def test_missing_or_corrupt_backup_never_deletes_local(self):
        result = self.export()
        (Path(result['destination']) / PAYLOAD / PID / 'source.mp4').write_bytes(b'bad')
        self.assertEqual(self.run_task(action='release', receipt=result['id'])['status'], 'error')
        self.assertTrue(self.store.directory(PID).exists())
        self.assertEqual(self.run_task(action='restore', source=result['destination'])['status'], 'error')

    def test_duplicate_skips_and_conflict_does_not_overwrite(self):
        result = self.export()
        r = self.run_task(action='restore', source=result['destination'])
        self.assertEqual(r['status'], 'complete', r); self.assertIn('跳过 1', r['message'])
        p = self.store.read(PID); p['shots'][0]['title'] = '保留我'; self.store.write(p)
        self.assertEqual(self.run_task(action='restore', source=result['destination'])['status'], 'error')
        self.assertEqual(self.store.read(PID)['shots'][0]['title'], '保留我')

    def test_library_round_trip_includes_music_tags(self):
        (self.store.data_dir / 'music').mkdir()
        (self.store.data_dir / 'music' / (MID + '.m4a')).write_bytes(b'music')
        music = {'tracks': [{'id': MID, 'title': '我的音乐', 'tags': ['氛围']}]}
        (self.store.data_dir / 'music-library.json').write_bytes(encoded(music))
        result = self.export(True)
        self.assertEqual(self.run_task(action='release', receipt=result['id'])['status'], 'complete')
        self.assertFalse((self.store.data_dir / 'music').exists())
        self.assertEqual(self.run_task(action='restore', source=result['destination'])['status'], 'complete')
        self.assertEqual(self.store.local_music(), music)

    def test_migrate_switches_only_after_verification_and_old_release_is_explicit(self):
        dest = self.external / '新资料库'; dest.mkdir()
        self.manager.config_path = self.root / 'settings' / 'storage.json'
        old = self.store.data_dir
        result = self.run_task(action='migrate', destination=str(dest))
        self.assertEqual(result['status'], 'complete', result)
        self.assertEqual(self.store.data_dir, dest)
        self.assertTrue((old / PID / 'source.mp4').exists())
        self.assertEqual(configured_directory(old, self.manager.config_path), dest)
        with self.assertRaises(server.LibraryInUseError):
            server.ProjectStore(dest)
        self.assertEqual(self.run_task(action='release', receipt=result['id'])['status'], 'complete')
        self.assertFalse((old / PID).exists())
        self.assertTrue((dest / PID / 'source.mp4').exists())

    def test_receipt_survives_restart(self):
        result = self.export()
        self.manager = self.store.storage = StorageManager(self.store, server.APIError)
        self.assertTrue(self.manager.tasks[result['id']]['can_release'])
        self.assertEqual(self.run_task(action='release', receipt=result['id'])['status'], 'complete')

    def test_disk_space_and_copy_failure_preserve_source(self):
        with patch('storage.shutil.disk_usage', return_value=type('Usage', (), {'free': 0})()):
            self.assertEqual(self.run_task(action='export', destination=str(self.external), project_id=PID)['status'], 'error')
        with patch.object(self.manager, 'copy_entries', side_effect=OSError('目标硬盘断开')):
            self.assertEqual(self.run_task(action='export', destination=str(self.external), project_id=PID)['status'], 'error')
        self.assertTrue((self.store.directory(PID) / 'source.mp4').exists())
        self.assertEqual(list(self.external.iterdir()), [])

    def test_cancel_copy_and_busy_rejection(self):
        original = self.manager.progress
        def cancel(task, message, done=None, total=None):
            original(task, message, done, total)
            if done and done > 0: task['_cancel'].set()
        with patch.object(self.manager, 'progress', side_effect=cancel):
            task = self.run_task(action='export', destination=str(self.external), project_id=PID)
        self.assertEqual(task['status'], 'cancelled')
        self.assertEqual(list(self.external.iterdir()), [])
        event = threading.Event(); thread = threading.Thread(target=event.wait); thread.start()
        self.store.jobs['test'] = thread
        try:
            with self.assertRaises(server.APIError): self.manager.start({'action': 'export'})
        finally: event.set(); thread.join()

    def test_traversal_symlink_and_incomplete_packages_rejected(self):
        result = self.export(); bundle = Path(result['destination'])
        manifest = json.loads((bundle / MANIFEST).read_text())
        for bad in ['../../outside', '/tmp/escape', 'a/../escape', 'a\\escape']:
            value = copy.deepcopy(manifest); value['files'][0]['path'] = bad
            with self.assertRaises(ValueError): self.manager.validate_manifest(value)
        source = bundle / PAYLOAD / PID / 'source.mp4'; source.unlink(); source.symlink_to(self.store.directory(PID) / 'source.mp4')
        self.assertEqual(self.run_task(action='restore', source=str(bundle))['status'], 'error')

    def test_upload_folder_restore_without_second_full_copy(self):
        result = self.export(); bundle = Path(result['destination']); manifest = json.loads((bundle / MANIFEST).read_text())
        self.assertEqual(self.run_task(action='release', receipt=result['id'])['status'], 'complete')
        upload = self.manager.prepare_upload(manifest)
        for f in manifest['files']:
            data = (bundle / PAYLOAD / f['path']).read_bytes()
            self.manager.upload_file(upload['id'], f['path'], io.BytesIO(data), len(data))
        self.manager.finish_upload(upload['id'])
        self.manager.tasks[upload['id']]['_thread'].join(10)
        self.assertEqual(self.manager.tasks[upload['id']]['status'], 'complete', self.manager.public(self.manager.tasks[upload['id']]))
        self.assertTrue((self.store.directory(PID) / 'source.mp4').exists())
        self.assertFalse(list(self.store.data_dir.glob('.incoming-*')))

    def test_upload_cancel_cleans_staging(self):
        result = self.export(); manifest = json.loads((Path(result['destination']) / MANIFEST).read_text())
        upload = self.manager.prepare_upload(manifest)
        self.manager.cancel(upload['id'])
        self.assertIsNone(self.manager.active)
        self.assertFalse(list(self.store.data_dir.glob('.incoming-*')))

    def test_missing_original_or_saved_asset_prevents_verified_export(self):
        source = self.store.directory(PID)
        (source / f'clips/{SID}/画面.png').unlink()
        result = self.run_task(action='export', destination=str(self.external), project_id=PID)
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['can_release'])
        self.assertTrue((source / 'source.mp4').exists())
        (source / 'source.mp4').unlink()
        result = self.run_task(action='export', destination=str(self.external), project_id=PID)
        self.assertEqual(result['status'], 'error')

    def test_http_freezes_edits_but_allows_status_and_origin_is_checked(self):
        result = self.export(); manifest = json.loads((Path(result['destination']) / MANIFEST).read_text())
        upload = self.manager.prepare_upload(manifest)
        http_server = server.WorkbenchServer(('127.0.0.1', 0), self.store, Path(server.ROOT) / 'public')
        thread = threading.Thread(target=http_server.serve_forever, daemon=True); thread.start()
        def request(method, path, data=None, origin=None):
            conn = http.client.HTTPConnection('127.0.0.1', http_server.server_address[1], timeout=3)
            headers = {'Content-Type': 'application/json'}
            if origin: headers['Origin'] = origin
            conn.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
            response = conn.getresponse(); status = response.status; body = json.loads(response.read()); conn.close()
            return status, body
        try:
            self.assertEqual(request('POST', f'/api/projects/{PID}/metadata', {'tags': ['blocked']})[0], 409)
            self.assertEqual(request('GET', '/api/storage')[0], 200)
            self.assertEqual(request('GET', '/api/projects')[0], 200)
            self.assertEqual(request('POST', '/api/storage/tasks', {'action': 'release'}, 'https://foreign.test')[0], 403)
            self.assertEqual(request('POST', f'/api/storage/tasks/{upload["id"]}/cancel', {})[0], 200)
        finally:
            http_server.shutdown(); http_server.server_close(); thread.join(3)

    def test_upload_corruption_is_rejected_and_can_be_cancelled(self):
        result = self.export(); manifest = json.loads((Path(result['destination']) / MANIFEST).read_text())
        upload = self.manager.prepare_upload(manifest); item = manifest['files'][0]
        with self.assertRaises(ValueError):
            self.manager.upload_file(upload['id'], item['path'], io.BytesIO(b'x' * item['size']), item['size'])
        self.manager.cancel(upload['id'])
        self.assertTrue(self.store.directory(PID).exists())

    def test_migration_failure_does_not_change_config_or_source(self):
        dest = self.external / 'empty'; dest.mkdir()
        self.manager.config_path = self.root / 'config.json'
        previous = self.store.data_dir
        with patch.object(self.manager, 'verify', side_effect=OSError('校验读取失败')):
            result = self.run_task(action='migrate', destination=str(dest))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.store.data_dir, previous)
        self.assertFalse(self.manager.config_path.exists())
        self.assertEqual([p for p in dest.iterdir() if p.name != '.workbench.lock'], [])
        probe = server.ProjectStore(dest)
        probe.close()

    def test_migration_rolls_back_published_destination_and_config_if_adoption_fails(self):
        dest = self.external / 'adopt-failure'; dest.mkdir()
        self.manager.config_path = self.root / 'settings/storage.json'
        with patch.object(self.store, 'adopt_library_directory', side_effect=OSError('注入切换失败')):
            result = self.run_task(action='migrate', destination=str(dest))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.store.data_dir, self.root / 'local')
        self.assertFalse(self.manager.config_path.exists())
        self.assertTrue((self.store.directory(PID) / 'source.mp4').exists())
        self.assertEqual([p for p in dest.iterdir() if p.name != '.workbench.lock'], [])

    def test_release_registry_failure_rolls_back_before_any_deletion(self):
        result = self.export()
        with patch.object(self.manager, 'save_receipts', side_effect=[OSError('注入回执写入失败'), None]):
            release = self.run_task(action='release', receipt=result['id'])
        self.assertEqual(release['status'], 'error')
        self.assertTrue((self.store.directory(PID) / 'source.mp4').is_file())
        self.assertIn(result['id'], self.manager.receipts)
        self.assertFalse(list(self.store.data_dir.glob('.release-*')))

    def test_prepared_release_journal_restores_hidden_data_after_restart(self):
        result = self.export()
        receipt = self.manager.receipts[result['id']]
        task_id = 'd' * 32
        source = self.store.data_dir
        quarantine = source / ('.release-' + task_id)
        quarantine.mkdir()
        journal = source / f'{RELEASE_JOURNAL_PREFIX}{task_id}.json'
        durable_json(journal, {
            'version': 1, 'state': 'prepared', 'task_id': task_id, 'receipt_id': result['id'],
            'receipt': receipt, 'source': str(source), 'quarantine': str(quarantine), 'targets': [PID],
        }, backup=True)
        os.replace(source / PID, quarantine / PID)
        fsync_directory(source)
        self.assertFalse((source / PID).exists())
        self.manager = self.store.storage = StorageManager(self.store, server.APIError)
        self.assertTrue((source / PID / 'source.mp4').is_file())
        self.assertIn(result['id'], self.manager.receipts)
        self.assertFalse(journal.exists())
        self.assertFalse(quarantine.exists())

    def test_committed_release_journal_finishes_cleanup_even_if_registry_uses_backup(self):
        result = self.export()
        receipt = self.manager.receipts[result['id']]
        task_id = 'e' * 32
        source = self.store.data_dir
        quarantine = source / ('.release-' + task_id)
        quarantine.mkdir()
        journal = source / f'{RELEASE_JOURNAL_PREFIX}{task_id}.json'
        durable_json(journal, {
            'version': 1, 'state': 'committed', 'task_id': task_id, 'receipt_id': result['id'],
            'receipt': receipt, 'source': str(source), 'quarantine': str(quarantine), 'targets': [PID],
        }, backup=True)
        os.replace(source / PID, quarantine / PID)
        self.manager.receipts.pop(result['id'])
        self.manager.save_receipts()
        (source / '.storage-receipts.json').write_bytes(b'{broken')
        self.manager = self.store.storage = StorageManager(self.store, server.APIError)
        self.assertFalse(quarantine.exists())
        self.assertFalse((source / PID).exists())
        self.assertNotIn(result['id'], self.manager.receipts)
        self.assertFalse(journal.exists())

if __name__ == '__main__': unittest.main()
