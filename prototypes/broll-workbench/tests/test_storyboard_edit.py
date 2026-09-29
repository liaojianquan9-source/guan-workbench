"""Real media verification of visual cuts and adjacent joins."""
from unittest import TestCase
import test_backend as fixtures
backend = fixtures.backend

class StoryboardTest(TestCase):
    setUpClass = classmethod(fixtures.BackendTest.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.BackendTest.tearDownClass.__func__)
    setUp = fixtures.BackendTest.setUp
    tearDown = fixtures.BackendTest.tearDown
    upload = fixtures.BackendTest.upload

    def edit(self, p, action, **kwargs):
        return self.store.storyboard(p['id'], dict(action=action, expected_revision=p['revision'], **kwargs))

    def test_split_frame_undo_and_other_tracks(self):
        p = self.upload()
        p['transcript']['segments'] = [{'start':0,'end':3,'text':'unchanged'}]
        p['shots'][0]['note'] = 'observation'
        self.store.write(p)
        before = self.store.read(p['id'])
        source = (self.store.directory(p['id'])/'source.mp4').read_bytes()
        p = self.edit(p,'split',id=p['shots'][0]['id'],time=1.24)
        self.assertEqual([(s['start'],s['end']) for s in p['shots']],[(0,1.2),(1.2,3)])
        self.assertEqual(p['shots'][0]['note'],'observation')
        self.assertEqual(p['transcript'],before['transcript'])
        self.assertTrue((self.store.directory(p['id'])/'thumbnails'/(p['shots'][1]['id']+'.jpg')).exists())
        self.assertEqual((self.store.directory(p['id'])/'source.mp4').read_bytes(),source)
        p = self.edit(p,'undo',operation_id=p['storyboard_history'][-1]['id'])
        self.assertEqual(p['shots'],before['shots'])

    def test_join_preserves_notes_and_is_reversible(self):
        p=self.upload();p=self.edit(p,'split',id=p['shots'][0]['id'],time=1)
        p['shots'][0]['note']='first';p['shots'][1]['note']='second';self.store.write(p)
        before=self.store.read(p['id'])['shots']
        p=self.edit(p,'merge',id=before[0]['id'],next_id=before[1]['id'])
        self.assertEqual(len(p['shots']),1)
        self.assertEqual(p['shots'][0]['note'],'first\nsecond')
        self.assertEqual(p['shots'][0]['end'],3)
        p=self.edit(p,'undo',operation_id=p['storyboard_history'][-1]['id'])
        self.assertEqual(p['shots'],before)

    def test_reject_edges_stale_nonadjacent_and_undo_over_notes(self):
        p=self.upload()
        for at in [0,3,.001]:
            with self.assertRaises(backend.APIError):self.edit(p,'split',id=p['shots'][0]['id'],time=at)
        first=p;p=self.edit(p,'split',id=p['shots'][0]['id'],time=1)
        with self.assertRaises(backend.APIError):self.edit(first,'split',id=first['shots'][0]['id'],time=.5)
        p=self.edit(p,'split',id=p['shots'][1]['id'],time=2)
        with self.assertRaises(backend.APIError):self.edit(p,'merge',id=p['shots'][0]['id'],next_id=p['shots'][2]['id'])
        p['shots'][0]['note']='new';self.store.write(p)
        with self.assertRaises(backend.APIError):self.edit(p,'undo',operation_id=p['storyboard_history'][-1]['id'])
        self.assertEqual(self.store.read(p['id'])['shots'][0]['note'],'new')
