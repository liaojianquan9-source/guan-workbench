import copy
import io
import json
import subprocess
from unittest import TestCase
from unittest.mock import patch
import test_backend as fixtures
from music_sections import split_section, new_section
backend=fixtures.backend

class SectionMathTest(TestCase):
    def test_split_preserves_coverage_but_invalidates_previous_song_assignment(self):
        original=new_section(0,100); original['recognition']={'status':'ready','tracks':[{'title':'A'}]}
        segments=split_section([original],40,.1)
        self.assertEqual([(s['start'],s['end']) for s in segments],[(0,40),(40,100)])
        self.assertTrue(all(not s['recognition']['tracks'] for s in segments))
        self.assertEqual(original['recognition']['tracks'][0]['title'],'A')
        for at in [0,.01,100,101,float('nan')]:
            with self.assertRaises(ValueError):split_section([original],at,.1)

class MusicSectionsTest(TestCase):
    setUpClass=classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp=fixtures.BackendTest.setUp
    tearDown=fixtures.BackendTest.tearDown
    def project(self):
        data=self.long_audio.read_bytes();return self.store.import_stream('music.mp4',io.BytesIO(data),len(data))
    def command(self,p,action,**kwargs):return self.store.sections.dispatch(p['id'],{'action':action,**kwargs})
    def initial(self,p):
        with patch.object(self.store.sections,'launch'):
            return self.command(p,'analyze')

    def test_split_boundary_merge_and_undo_persist_and_reject_stale_edit(self):
        p=self.project();p=self.initial(p)
        p=self.command(p,'split',time=1,expected_revision=0)
        state=p['music_sections'];self.assertEqual([(s['start'],s['end']) for s in state['sections']],[(0,1),(1,p['duration'])])
        with self.assertRaises(backend.APIError):self.command(p,'split',time=2,expected_revision=0)
        right=state['sections'][1]
        p=self.command(p,'boundary',id=right['id'],time=1.5,expected_revision=1)
        self.assertEqual(p['music_sections']['sections'][0]['end'],1.5)
        p=self.command(p,'merge',id=p['music_sections']['sections'][1]['id'],expected_revision=2)
        self.assertEqual(len(p['music_sections']['sections']),1)
        p=self.command(p,'undo',expected_revision=3)
        self.assertEqual(p['music_sections']['sections'][0]['end'],1.5)
        self.assertEqual(p['research_clips'],[])
        self.assertEqual(self.store.read(p['id'])['music_sections']['revision'],4)

    def test_automatic_results_cannot_overwrite_manual_adjustments(self):
        p=self.project();self.initial(p)
        self.command(p,'split',time=1,expected_revision=0)
        with patch.object(self.store,'run',return_value=subprocess.CompletedProcess([],0,json.dumps({'cuts':[2],'method':'test'}),'')):
            self.store.sections.analyze_job(p['id'],0)
        result=self.store.read(p['id'])['music_sections']['sections']
        self.assertEqual(result[0]['end'],1)
        with patch.object(self.store.sections,'launch') as launch:
            self.command(p,'analyze');launch.assert_not_called()

    def test_recognition_stays_with_exact_range_and_discards_stale_response(self):
        p=self.project();self.initial(p)
        p=self.command(p,'split',time=1,expected_revision=0)
        section=p['music_sections']['sections'][1]
        with patch.object(self.store.sections,'launch'):
            p=self.command(p,'recognize',id=section['id'])
        snapshot=copy.deepcopy(p['music_sections']['sections'][1])
        commands=[]
        def result(command,**kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command,0,'{"type":"found","track":{"key":"a","title":"Song A","time":1}}\n{"type":"done"}\n','')
        with patch.object(self.store,'run',side_effect=result):self.store.sections.recognize_job(p['id'],snapshot)
        self.assertEqual(commands[0][-2:],[str(p['duration']-1),'1.0'])
        self.assertEqual(self.store.read(p['id'])['music_sections']['sections'][1]['recognition']['tracks'][0]['title'],'Song A')
        self.command(p,'split',time=2,expected_revision=1)
        with patch.object(self.store,'run',side_effect=AssertionError('stale task must not run')):
            self.store.sections.recognize_job(p['id'],snapshot)
        self.assertTrue(all(not s['recognition']['tracks'] for s in self.store.read(p['id'])['music_sections']['sections']))

    def test_failed_recognition_and_unmatched_are_distinct(self):
        p=self.project();p=self.initial(p);section=p['music_sections']['sections'][0]
        for code,output,status in [(0,'{"type":"done"}','ready'),(1,'{"type":"error","message":"network"}','error')]:
            with patch.object(self.store.sections,'launch'):p=self.command(p,'recognize',id=section['id'])
            snapshot=copy.deepcopy(p['music_sections']['sections'][0])
            with patch.object(self.store,'run',return_value=subprocess.CompletedProcess([],code,output,'')):
                self.store.sections.recognize_job(p['id'],snapshot)
            self.assertEqual(self.store.read(p['id'])['music_sections']['sections'][0]['recognition']['status'],status)
