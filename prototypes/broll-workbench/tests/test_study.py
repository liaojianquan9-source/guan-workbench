"""Analysis runs only on explicit requests; browsing keeps existing results intact."""
import io
import json
import shutil
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import test_backend as fixtures
backend = fixtures.backend

class StudyTest(TestCase):
    setUpClass = classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp = fixtures.BackendTest.setUp
    tearDown = fixtures.BackendTest.tearDown
    upload = fixtures.BackendTest.upload

    def audio_project(self):
        content = self.long_audio.read_bytes()
        return self.store.import_stream('sound.mp4', io.BytesIO(content), len(content))

    def test_import_and_study_are_passive_and_retain_existing_results(self):
        with patch.object(self.store, 'analyze') as scenes, patch.object(self.store, 'transcribe') as words, patch.object(self.store, 'music') as music, patch.object(self.store.research, 'ensure_source') as sound, patch.object(self.store.sections, 'dispatch') as sections:
            p = self.audio_project()
            before = self.store.read(p['id'])
            self.store.study(p['id'], {})
            self.store.study(p['id'], {'retry_sound': True})  # Old clients cannot auto-run work.
            self.assertEqual(self.store.read(p['id']), before)
            p.update(analysis={'method':'keep'})
            p['transcript'].update(status='ready', segments=[{'text':'keep'}])
            self.store.write(p)
            self.assertEqual(self.store.study(p['id'], {}), p)
            for operation in [scenes, words, music, sound, sections]:
                operation.assert_not_called()

    def test_music_request_only_prepares_audio_then_segments_once(self):
        p = self.audio_project()
        def prepare(pid, retry=False):
            q = self.store.read(pid)
            q['source_audio'] = {'sound': {'status':'processing'}}
            self.store.write(q)
            return q
        with patch.object(self.store, 'analyze') as scenes, patch.object(self.store, 'transcribe') as words, patch.object(self.store, 'music') as music, patch.object(self.store.research, 'ensure_source', side_effect=prepare) as sound, patch.object(self.store.sections, 'launch') as launch:
            result = self.store.study(p['id'], {'task':'music_sections'})
            self.assertEqual(result['music_sections']['status'], 'waiting_audio')
            self.store.study(p['id'], {'task':'music_sections'})
            self.assertEqual(sound.call_count, 1)
            launch.assert_not_called()
            result = self.store.sections.after_source(p['id'])
            self.assertEqual(result['music_sections']['status'], 'processing')
            self.store.sections.after_source(p['id'])
            self.assertEqual(launch.call_count, 1)
            scenes.assert_not_called(); words.assert_not_called(); music.assert_not_called()

    def test_audio_completion_without_music_request_does_not_segment(self):
        p = self.audio_project()
        with patch.object(self.store.sections, 'dispatch') as launch:
            self.store.sections.after_source(p['id'])
            launch.assert_not_called()
        self.assertNotIn('music_sections', self.store.read(p['id']))

    def test_music_request_reuses_ready_audio_and_retry_is_explicit(self):
        p = self.audio_project()
        def prepare(pid, retry=False):
            q = self.store.read(pid)
            q['source_audio'] = {'sound': {'status':'error', 'message':'model failed'}}
            self.store.write(q)
            return q
        with patch.object(self.store.research, 'ensure_source', side_effect=prepare) as sound, patch.object(self.store.sections, 'launch') as launch:
            result = self.store.study(p['id'], {'task':'music_sections'})
            self.assertEqual(result['music_sections']['status'], 'error')
            self.store.study(p['id'], {})
            self.assertEqual(sound.call_count, 1)
            def ready(pid, retry=False):
                q = self.store.read(pid); q['source_audio']['sound']['status'] = 'ready'; self.store.write(q); return q
            sound.side_effect = ready
            result = self.store.study(p['id'], {'task':'music_sections'})
            self.assertEqual(result['music_sections']['status'], 'processing')
            self.assertEqual(sound.call_count, 2)
            self.assertEqual(launch.call_count, 1)

    def test_source_audio_survives_clip_delete_and_has_full_length_waveforms(self):
        p = self.audio_project()
        original_runner = self.store.research.cancellable
        def runner(command, event, logfile, timeout=900):
            if 'separate_audio.py' not in ' '.join(command):
                return original_runner(command, event, logfile, timeout)
            source, folder = Path(command[2]), Path(command[3])
            for stem in ['vocals', 'background']:
                shutil.copyfile(source, folder / (stem + '.wav'))
            (folder / 'result.json').write_text(json.dumps({'simulated': True}))
        with patch.object(self.store.research, 'separation_runtime', return_value=Path(sys.executable)), \
             patch.object(self.store.research, 'cancellable', side_effect=runner):
            first = self.store.research.ensure_source(p['id'])
            source = first['source_audio']
            second = self.store.research.ensure_source(p['id'])
            self.assertEqual(source['id'], second['source_audio']['id'])
            self.store.jobs[f"research:{p['id']}:{source['id']}"].join(timeout=30)
        q = self.store.read(p['id'])
        self.assertEqual(q['research_clips'], [])
        self.assertEqual(q['source_audio']['sound']['status'], 'ready')
        self.assertEqual(q['source_audio']['end'], p['duration'])
        result = self.store.research.dispatch(p['id'], {'action':'create','start':.5,'end':2,'request_id':'source-independent'})
        clip = result['project']['research_clips'][0]
        self.store.research.dispatch(p['id'], {'action':'delete','id':clip['id'],'expected_revision':0})
        q = self.store.read(p['id'])
        self.assertEqual(q['source_audio']['sound']['status'], 'ready')
        waves = self.store.research.waveforms(p['id'], source['id'])
        self.assertEqual(set(waves['tracks']), {'original','vocals','background'})
        self.assertAlmostEqual(waves['duration'], p['duration'])
        with self.assertRaises(backend.APIError):
            self.store.research.dispatch(p['id'], {'action':'delete','id':source['id'],'expected_revision':0})

    def test_source_failure_is_visible_and_requires_explicit_retry(self):
        p = self.audio_project()
        with patch.object(self.store.research, 'audio_action', side_effect=backend.APIError(503, '模型不可用')) as action:
            self.store.research.ensure_source(p['id'])
            self.store.research.ensure_source(p['id'])
            self.assertEqual(action.call_count, 1)
            self.assertEqual(self.store.read(p['id'])['source_audio']['sound']['status'], 'error')
            self.store.research.ensure_source(p['id'], retry=True)
            self.assertEqual(action.call_count, 2)

    def test_silent_video_skips_sound_and_subtitles(self):
        p = self.upload()
        with patch.object(self.store, 'analyze'), patch.object(self.store, 'music') as music, patch.object(self.store, 'transcribe') as words:
            self.store.study(p['id'], {})
            music.assert_not_called(); words.assert_not_called()
            self.assertNotIn('source_audio', self.store.read(p['id']))
