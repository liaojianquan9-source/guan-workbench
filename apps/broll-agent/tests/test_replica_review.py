import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_store import AssetStore
from replica_review import ReplicaReviewService, import_workbench_source


def png(red):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\x00' + bytes([red, 80, 120]) * 2) * 2)) + chunk(b'IEND', b'')


class ReplicaReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = AssetStore(self.root / 'assets')
        self.service = ReplicaReviewService(self.assets, self.root / 'review')
        self.files = {'case.json': json.dumps({'files': {'layout': 'specs/layout.json'}}).encode(),
            'specs/layout.json': json.dumps({'scenes': [{'id': 'layout-one', 'sourceStill': 'evidence/source.png',
                'renderStill': 'evidence/render.png', 'comparisonStill': 'evidence/comparison.png', 'status': 'passed'}]}).encode(),
            'evidence/source.png': png(20), 'evidence/render.png': png(100), 'evidence/comparison.png': png(200)}

    def candidate(self, files=None, manifest_override=None):
        files = files or self.files
        path = self.root / 'candidate.zip'
        with zipfile.ZipFile(path, 'w') as package:
            for name, data in files.items(): package.writestr(name, data)
        digest = self.assets.put_blob(path)['sha256']
        manifest = [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()]
        if manifest_override: manifest_override(manifest)
        return self.assets.create_asset('replica', 'Snapshot candidate', {'stages': {'layout': 'needs_review'},
            'execution_trust': 'untrusted_candidate', 'skill_bridge': {'version': 1, 'package_hash': digest,
            'files': manifest, 'trusted_renderer': False, 'human_review': 'pending'}}, digest)

    def approve(self, detail, action='approve', **extra):
        scene = detail['scenes'][0]
        return self.service.review(detail['replica']['id'], {'expected_revision': detail['replica']['revision'],
            'scene_id': scene['id'], 'render_hash': scene['render_hash'], 'action': action, 'note': 'checked', **extra})

    def test_real_snapshot_images_decode_and_review_persists_without_code_trust(self):
        replica = self.candidate()
        detail = self.service.detail(replica['id'])
        self.assertFalse(detail['layout_review_complete'])
        self.assertEqual(detail['warnings'], [])
        scene = detail['scenes'][0]
        self.assertNotEqual(scene['source_hash'], scene['render_hash'])
        self.assertEqual(self.assets.blob_path(scene['render_hash']).read_bytes(), png(100))
        result = self.approve(detail)
        self.assertTrue(result['layout_review_complete'])
        self.assertEqual(result['replica']['revision'], 2)
        self.assertEqual(result['scenes'][0]['review']['reviewer'], 'user')
        metadata = result['replica']['metadata']
        self.assertEqual(metadata['execution_trust'], 'untrusted_candidate')
        self.assertEqual(metadata['stages']['layout'], 'needs_review')
        self.assertFalse(metadata['skill_bridge']['trusted_renderer'])
        self.assertEqual(metadata['skill_bridge']['human_review'], 'pending')
        self.assertEqual(self.assets.list_assets(kind='style'), [])
        restarted = ReplicaReviewService(self.assets, self.root / 'restart').detail(replica['id'])
        self.assertEqual(restarted['scenes'][0]['review'], result['scenes'][0]['review'])

    def test_stale_revision_stale_render_empty_note_and_active_generation_reject(self):
        replica = self.candidate()
        detail = self.service.detail(replica['id'])
        with self.assertRaisesRegex(ValueError, 'conflict'): self.approve(detail, expected_revision=0)
        with self.assertRaisesRegex(ValueError, 'conflict'): self.approve(detail, render_hash='c'*64)
        with self.assertRaisesRegex(ValueError, '具体问题'): self.approve(detail, action='changes', note=' ')
        result = self.approve(detail, action='changes')
        self.assertFalse(result['layout_review_complete'])
        self.assertEqual(result['scenes'][0]['review']['status'], 'changes')
        m = copy.deepcopy(result['replica']['metadata']);m['skill_bridge']['active_run']='running'
        busy = self.assets.revise_asset(replica['id'], 2, {'metadata':m})
        with self.assertRaisesRegex(ValueError, '正在生成'):
            self.approve(self.service.detail(busy['id']))

    def test_no_layout_no_render_and_source_copy_never_become_approvable(self):
        for mode in ['preflight', 'missing-render', 'source-copy', 'invalid-image']:
            with self.subTest(mode=mode):
                files = dict(self.files)
                if mode == 'preflight': del files['specs/layout.json']
                if mode == 'missing-render': del files['evidence/render.png']
                if mode == 'source-copy': files['evidence/render.png'] = files['evidence/source.png']
                if mode == 'invalid-image': files['evidence/render.png'] = b'\x89PNG\r\n\x1a\nnot an image'
                replica = self.candidate(files)
                detail = self.service.detail(replica['id'])
                self.assertFalse(detail['layout_review_complete'])
                self.assertTrue(detail['warnings'])
                self.assertTrue(not detail['scenes'] or detail['scenes'][0]['render_hash'] is None)
                with self.assertRaisesRegex(ValueError, '缺少真实'):
                    self.service.review(replica['id'], {'expected_revision':1,'scene_id':'layout-one','render_hash':'a'*64,'action':'approve'})

    def test_manifest_mismatch_and_model_host_paths_are_rejected(self):
        replica = self.candidate(manifest_override=lambda entries: entries[-2].update(sha256='0'*64))
        detail = self.service.detail(replica['id'])
        self.assertIsNone(detail['scenes'][0]['render_hash'])
        self.assertTrue(any('指纹' in message for message in detail['warnings']))
        files = dict(self.files)
        files['specs/layout.json'] = json.dumps({'scenes':[{'id':'unsafe','sourceStill':'../../outside.png','renderStill':'/etc/passwd'}]}).encode()
        unsafe = self.service.detail(self.candidate(files)['id'])
        self.assertIsNone(unsafe['scenes'][0]['render_hash'])
        self.assertIsNone(unsafe['scenes'][0]['source_hash'])

    def test_replaced_source_or_render_invalidates_older_approval(self):
        replica = self.candidate();result = self.approve(self.service.detail(replica['id']))
        changed = dict(self.files);changed['evidence/source.png'] = png(50)
        fresh = self.candidate(changed)
        m = copy.deepcopy(fresh['metadata']);m['layout_review'] = result['replica']['metadata']['layout_review']
        self.assets.revise_asset(fresh['id'], 1, {'metadata':m})
        detail = self.service.detail(fresh['id'])
        self.assertFalse(detail['layout_review_complete'])
        self.assertEqual(detail['scenes'][0]['review']['status'], 'needs_review')

    def test_historical_case_is_readonly_and_old_passed_does_not_approve_new_review(self):
        directory = self.root / 'historical'
        for name, data in self.files.items():
            path = directory / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
        before = {name: (directory / name).read_bytes() for name in self.files}
        replica = self.assets.create_asset('replica', 'Old case', {'case_id':'audited', 'original_stages':{'layout':'passed'}})
        with patch('replica_review.REPO',self.root), patch('replica_review.CASE_INDEX',{'audited':{'case_path':'historical'}}):
            detail = self.service.detail(replica['id'])
            self.assertFalse(detail['layout_review_complete'])
            self.assertEqual(detail['scenes'][0]['evidence_origin'],'historical_case_still')
            result = self.approve(detail)
            self.assertTrue(result['layout_review_complete'])
        self.assertEqual({name:(directory/name).read_bytes() for name in self.files},before)

    def test_unrecognized_case_path_is_never_read(self):
        asset = self.assets.create_asset('replica','Injected host path',{'case_id':'unknown','case_path':'/etc','stages':{'layout':'passed'}})
        detail = self.service.detail(asset['id'])
        self.assertEqual(detail['scenes'],[])
        self.assertFalse(detail['layout_review_complete'])

    def test_source_import_is_idempotent_readonly_and_does_not_create_production_project(self):
        original = self.root / 'original.mp4';original.write_bytes(b'original video fixture')
        project = {'id':'old','revision':3,'name':'old.mp4'}
        class App:
            assets=self.assets
            guard=threading.RLock()
            def ingest(inner,path,kind,name,provenance):
                blob=inner.assets.put_blob(path)
                return inner.assets.create_asset(kind,name,{'provenance':provenance},blob['sha256'])
            def create_project(inner,*args): raise AssertionError('must not create production project')
        app=App()
        with patch('replica_review.read_workbench',return_value=(project,original)):
            first=import_workbench_source(app,'old');again=import_workbench_source(app,'old')
            self.assertEqual(first,again)
            self.assertEqual(original.read_bytes(),b'original video fixture')
            original.write_bytes(b'new original revision')
            with patch('replica_review.probe',return_value={'has_video':True,'duration':1}):
                changed=import_workbench_source(app,'old')
        self.assertEqual(changed['id'],first['id']);self.assertEqual(changed['revision'],2)
        self.assertEqual(self.assets.get_asset(first['id'],1)['blob_hash'],first['blob_hash'])
        self.assertEqual(len(self.assets.list_assets(kind='source')),1)


if __name__ == '__main__':
    unittest.main()
