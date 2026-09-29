from unittest import TestCase
import test_backend as fixtures
backend=fixtures.backend
class ShotNamesTest(TestCase):
    setUpClass=classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp=fixtures.BackendTest.setUp
    tearDown=fixtures.BackendTest.tearDown
    upload=fixtures.BackendTest.upload
    def test_name_preserves_identity_time_source_and_can_reset(self):
        p=self.upload();shot=p['shots'][0];original=dict(shot)
        result=self.store.annotate(p['id'],shot['id'],{'title':'估值数字动画','expected_annotation_revision':0})
        saved=self.store.read(p['id'])['shots'][0]
        self.assertEqual(saved['title'],'估值数字动画')
        for key in ['id','start','end','thumbnail_url','note','tag']:self.assertEqual(saved[key],original[key])
        self.assertEqual(result['name'],p['name'])
        self.assertEqual(result['video_url'],p['video_url'])
        with self.assertRaises(backend.APIError):self.store.annotate(p['id'],shot['id'],{'title':'过期修改','expected_annotation_revision':0})
        result=self.store.annotate(p['id'],shot['id'],{'title':'','expected_annotation_revision':1})
        self.assertEqual(result['shots'][0]['title'],'')
    def test_invalid_names_rejected(self):
        p=self.upload()
        for value in [None,12,'字'*121]:
            with self.assertRaises(backend.APIError):self.store.annotate(p['id'],p['shots'][0]['id'],{'title':value,'expected_annotation_revision':0})
