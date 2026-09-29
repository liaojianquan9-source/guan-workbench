from unittest import TestCase
import test_backend as fixtures
backend=fixtures.backend

class SubtitleEditTest(TestCase):
    setUpClass=classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp=fixtures.BackendTest.setUp
    tearDown=fixtures.BackendTest.tearDown
    upload=fixtures.BackendTest.upload

    def project(self):
        p=self.upload();p['transcript'].update(status='ready',segments=[{'start':.8,'end':2.1,'text':'英伟答'}]);self.store.write(p);return p

    def test_persist_corrected_text_and_export_original_timing(self):
        p=self.project()
        result=self.store.subtitle(p['id'],{'index':0,'text':'英伟达\nNVIDIA','expected_revision':0})
        segment=self.store.read(p['id'])['transcript']['segments'][0]
        self.assertEqual(segment,{'start':.8,'end':2.1,'text':'英伟达\nNVIDIA','original_text':'英伟答'})
        data,_=self.store.export(p['id'],'srt')
        self.assertIn('00:00:00,800 --> 00:00:02,100',data.decode('utf-8-sig'))
        self.assertIn('英伟达\nNVIDIA',data.decode('utf-8-sig'))
        self.assertEqual(result['transcript']['revision'],1)
        self.assertEqual(result['shots'],p['shots'])

    def test_reject_stale_invalid_empty_and_recognition_in_progress(self):
        p=self.project();body={'index':0,'text':'正确文字','expected_revision':0}
        self.store.subtitle(p['id'],body)
        with self.assertRaises(backend.APIError):self.store.subtitle(p['id'],body)
        for text in ['', ' '*3, None, '字'*5001]:
            with self.assertRaises(backend.APIError):self.store.subtitle(p['id'],dict(body,text=text,expected_revision=1))
        for index in [-1,True,5,'0']:
            with self.assertRaises(backend.APIError):self.store.subtitle(p['id'],dict(body,index=index,expected_revision=1))
        p=self.store.read(p['id']);p['transcript']['status']='processing';self.store.write(p)
        with self.assertRaises(backend.APIError):self.store.subtitle(p['id'],dict(body,expected_revision=1))
        self.assertEqual(self.store.read(p['id'])['transcript']['segments'][0]['text'],'正确文字')
