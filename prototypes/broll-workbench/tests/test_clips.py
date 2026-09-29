"""Clip workflow tests using real source video, PNGs and PCM audio; no production data."""
import io
import json
import sys
import threading
import time
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import test_backend as fixtures
backend = fixtures.backend
from research_clips import file_time, safe_part


class ClipTest(TestCase):
    setUpClass = classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp = fixtures.BackendTest.setUp
    tearDown = fixtures.BackendTest.tearDown
    upload = fixtures.BackendTest.upload
    def command(self, p, action, **body):
        return self.store.research.dispatch(p['id'], dict(action=action, **body))

    def create(self, p, **body):
        return self.command(p, 'create', start=.5, end=2.5, request_id='test-request-0001', **body)

    def clip(self, result):
        return next(c for c in result['project']['research_clips'] if c['id'] == result['clip_id'])

    def test_clip_create_retry_persist_sequence_and_stale_edit(self):
        p = self.upload()
        first = self.create(p, title='数值 / 动画')
        c = self.clip(first)
        self.assertEqual(c['number'], 1)
        self.assertEqual(c['source_project_id'], p['id'])
        self.assertEqual(self.create(p)['clip_id'], c['id'])
        self.assertEqual(len(self.store.read(p['id'])['research_clips']), 1)
        edited = self.command(p, 'edit', id=c['id'], expected_revision=0, title='新标题')
        with self.assertRaises(backend.APIError) as conflict:
            self.command(p, 'edit', id=c['id'], expected_revision=0, title='旧页覆盖')
        self.assertEqual(conflict.exception.status, 409)
        self.command(p, 'delete', id=c['id'], expected_revision=1)
        second = self.command(p, 'create', start=1, end=2, request_id='test-request-0002')
        self.assertEqual(self.clip(second)['number'], 2)
        location = self.store.data_dir
        self.store.close()
        self.store = backend.ProjectStore(location, detector='ffmpeg')
        self.assertEqual(self.store.read(p['id'])['research_clips'][0]['title'], '新标题')

    def test_multi_frames_precise_content_names_duplicate_and_old_files(self):
        p = self.upload()
        c = self.clip(self.create(p, title='动画/测试'))
        r = self.command(p, 'capture', id=c['id'], expected_revision=0, time=.6)
        f = r['file']
        path = self.store.research.file(p['id'], c['id'], f['id'])
        self.assertIn('画面01_00m00s600.png', path.name)
        self.assertNotIn('/', path.name)
        self.assertTrue(path.read_bytes().startswith(b'\x89PNG'))
        duplicate = self.command(p, 'capture', id=c['id'], expected_revision=0, time=.61)
        self.assertEqual(duplicate['file']['id'], f['id'])
        r2 = self.command(p, 'capture', id=c['id'], expected_revision=1, time=1.6)
        self.assertNotEqual(path.read_bytes(), self.store.research.file(p['id'], c['id'], r2['file']['id']).read_bytes())
        change = self.command(p, 'edit', id=c['id'], expected_revision=2, start=1, end=2, title='改名')
        changed = self.clip(change)
        self.assertTrue(changed['frames'][0]['outside'])
        self.assertFalse(changed['frames'][1]['outside'])
        self.assertTrue(path.exists())
        self.assertEqual(changed['frames'][0]['filename'], path.name)

    def test_note_provenance_and_invalid_ranges(self):
        p = self.upload()
        for start, end in [(-1, 1), (2, 1), (0, 99), (1, 1.01), (float('nan'), 2)]:
            with self.assertRaises(backend.APIError):
                self.command(p, 'create', start=start, end=end, request_id='bad-range-0000')
        c = self.clip(self.create(p))
        r = self.command(p, 'note', id=c['id'], expected_revision=0, time=1.5, text='第二次出现的数字')
        self.assertEqual(self.clip(r)['notes'][0]['time'], 1.5)
        for action, args in [('note', dict(time=2.9, text='outside')), ('capture', dict(time=2.9))]:
            with self.assertRaises(backend.APIError):
                self.command(p, action, id=c['id'], expected_revision=1, **args)
        with self.assertRaises(backend.APIError):
            self.command(p, 'separate', id=c['id'])  # silent video still permits all visual work

    def test_original_audio_cache_range_invalidation_restart_and_path_safety(self):
        content = self.long_audio.read_bytes()
        p = self.store.import_stream('音画测试.mp4', io.BytesIO(content), len(content))
        c = self.clip(self.create(p))
        self.command(p, 'original', id=c['id'])
        key = f"research:{p['id']}:{c['id']}"
        self.store.jobs[key].join(timeout=30)
        c = self.store.read(p['id'])['research_clips'][0]
        self.assertEqual(c['sound']['status'], 'ready', c['sound'])
        f = c['sound']['files']['original']
        path = self.store.research.file(p['id'], c['id'], f['id'])
        with wave.open(str(path)) as audio:
            self.assertAlmostEqual(audio.getnframes()/audio.getframerate(), 2, places=4)
        cached = self.command(p, 'original', id=c['id'])
        self.assertEqual(self.clip(cached)['sound']['files']['original']['id'], f['id'])
        r = self.command(p, 'edit', id=c['id'], expected_revision=0, start=1, end=2)
        self.assertEqual(self.clip(r)['sound']['status'], 'idle')
        self.assertTrue(self.clip(r)['sound_history'][0]['stale'])
        self.assertTrue(path.exists())
        with self.assertRaises(backend.APIError):
            self.store.research.file(p['id'], '../../escape', '../file')
        with self.assertRaises(backend.APIError):
            self.store.research.file(p['id'], c['id'], '../source.mp4')
        proj = self.store.read(p['id']);proj['research_clips'][0]['sound']['status']='processing';self.store.write(proj)
        location = self.store.data_dir
        self.store.close()
        self.store = backend.ProjectStore(location, detector='ffmpeg')
        self.assertEqual(self.store.read(p['id'])['research_clips'][0]['sound']['status'], 'error')

    def test_cancellation_and_retry_are_serialized(self):
        content = self.long_audio.read_bytes()
        p = self.store.import_stream('声音.mp4', io.BytesIO(content), len(content))
        c = self.clip(self.create(p))
        def slow(command, event, logfile, timeout=900):
            event.wait(5)
            raise backend.APIError(409, '已取消')
        with patch.object(self.store.research, 'cancellable', side_effect=slow):
            self.command(p, 'original', id=c['id'])
            self.command(p, 'cancel', id=c['id'])
            self.store.jobs[f"research:{p['id']}:{c['id']}"].join(timeout=10)
        self.assertEqual(self.store.read(p['id'])['research_clips'][0]['sound']['status'], 'cancelled')
        self.command(p, 'original', id=c['id'])
        self.store.jobs[f"research:{p['id']}:{c['id']}"].join(timeout=30)
        self.assertEqual(self.store.read(p['id'])['research_clips'][0]['sound']['status'], 'ready')

    def test_three_track_waveforms_are_distinct_cached_and_invalidated_by_range(self):
        from array import array
        content = self.long_audio.read_bytes()
        p = self.store.import_stream('三层波形.mp4', io.BytesIO(content), len(content))
        c = self.clip(self.create(p))
        before = self.store.read(p['id'])
        initial = self.store.research.waveforms(p['id'], c['id'])
        self.assertEqual(set(initial['tracks']), {'original'})
        self.assertEqual(self.store.read(p['id']), before)  # read-only project record
        for kind, level in [('vocals', 8192), ('background', 2048)]:
            item, path = self.store.research.new_file(p, c, kind + '.wav')
            with wave.open(str(path), 'wb') as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                audio.writeframes(array('h', [level] * 8000 + [0] * 8000).tobytes())
            c['sound'].setdefault('files', {})[kind] = item
        project = self.store.read(p['id']);project['research_clips'][0] = c;self.store.write(project)
        actual = self.store.research.waveforms(p['id'], c['id'])
        self.assertEqual(set(actual['tracks']), {'original', 'vocals', 'background'})
        self.assertEqual(actual['tracks']['vocals']['samples'][:500], [.25] * 500)
        self.assertEqual(actual['tracks']['background']['samples'][:500], [.0625] * 500)
        self.assertEqual(actual['tracks']['vocals']['samples'][500:], [0] * 500)
        with patch.object(self.store.research, 'pcm_peaks', side_effect=AssertionError('cache missed')):
            self.assertEqual(self.store.research.waveforms(p['id'], c['id']), actual)
        self.command(p, 'edit', id=c['id'], expected_revision=0, start=1, end=2)
        changed = self.store.research.waveforms(p['id'], c['id'])
        self.assertEqual(set(changed['tracks']), {'original'})
        self.assertEqual(changed['duration'], 1)
        self.assertNotEqual(changed['identity'], actual['identity'])

    def test_silent_clip_has_no_fabricated_waveforms(self):
        p = self.upload();c = self.clip(self.create(p))
        self.assertEqual(self.store.research.waveforms(p['id'], c['id'])['tracks'], {})

    def test_acceleration_failure_retries_cpu_and_keeps_valid_clock(self):
        content = self.long_audio.read_bytes()
        p = self.store.import_stream('声音.mp4', io.BytesIO(content), len(content))
        c = self.clip(self.create(p))
        original_runner = self.store.research.cancellable
        calls = []
        def runner(command, event, logfile, timeout=900):
            if 'separate_audio.py' not in ' '.join(command):
                return original_runner(command, event, logfile, timeout)
            calls.append(command)
            if '--cpu' not in command:
                raise backend.APIError(422, '模拟加速进程失败')
            import shutil
            source, folder = Path(command[2]), Path(command[3])
            for stem in ['vocals', 'background']:
                shutil.copyfile(source, folder / (stem + '.wav'))
            (folder / 'result.json').write_text(json.dumps({'device':'cpu', 'simulated':True}))
        with patch.object(self.store.research, 'separation_runtime', return_value=Path(sys.executable)), \
             patch.object(self.store.research, 'cancellable', side_effect=runner):
            self.command(p, 'separate', id=c['id'])
            self.store.jobs[f"research:{p['id']}:{c['id']}"].join(timeout=30)
        sound = self.store.read(p['id'])['research_clips'][0]['sound']
        self.assertEqual(sound['status'], 'ready', sound)
        self.assertEqual(len(calls), 2)
        self.assertIn('--cpu', calls[1])
        self.assertEqual(sound['model_run']['device'], 'cpu')
        self.assertEqual(sound['files']['vocals']['duration'], 2)

    def test_missing_separation_runtime_fails_before_mutating_or_queuing(self):
        content = self.long_audio.read_bytes()
        p = self.store.import_stream('依赖缺失.mp4', io.BytesIO(content), len(content))
        c = self.clip(self.create(p))
        before = self.store.read(p['id'])
        self.store.research.separation_python = self.root / 'deleted-codex-runtime' / 'python'
        self.store.research.separation_python_overridden = True
        with self.assertRaises(backend.APIError) as failure:
            self.command(p, 'separate', id=c['id'])
        self.assertEqual(failure.exception.status, 503)
        self.assertIn('已保留', failure.exception.message)
        self.assertEqual(self.store.read(p['id']), before)
        self.assertNotIn(f"research:{p['id']}:{c['id']}", self.store.jobs)

    def test_processing_log_replaces_symlink_without_touching_target(self):
        folder = self.root / 'logs'
        folder.mkdir()
        outside = self.root / 'outside.txt'
        outside.write_text('不可改动', encoding='utf-8')
        log = folder / 'separation.log'
        log.symlink_to(outside)
        self.store.research.cancellable(['/usr/bin/true'], threading.Event(), log)
        self.assertEqual(outside.read_text(encoding='utf-8'), '不可改动')
        self.assertFalse(log.is_symlink())
        self.assertTrue(log.is_file())


class NamingTest(TestCase):
    def test_timestamps_carry_and_illegal_path_characters(self):
        self.assertEqual(file_time(59.9999), '01m00s000')
        self.assertEqual(file_time(3723.4), '01h02m03s400')
        self.assertEqual(safe_part('../A:B/C\\D'), 'A_B_C_D')
