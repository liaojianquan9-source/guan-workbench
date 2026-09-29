import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from application import Application
from asset_client import AssetClient
from asset_server import AssetHTTPServer
from asset_store import AssetStore
from server import AppServer
from test_agent import FakeRenderer, ScriptedProvider


class AppHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.asset_server=AssetHTTPServer(('127.0.0.1',0),AssetStore(self.root/'shared'))
        self.asset_thread=threading.Thread(target=self.asset_server.serve_forever,daemon=True);self.asset_thread.start()
        self.client=AssetClient(f'http://127.0.0.1:{self.asset_server.server_address[1]}',self.root/'cache')
        self.app=Application(self.root/'projects',self.client,ScriptedProvider(),FakeRenderer(self.root))
        self.server=AppServer(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.asset_server.shutdown();self.asset_server.server_close();self.asset_thread.join()
        self.temp.cleanup()
    def request(self,method,path,data=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        body=json.dumps(data).encode() if isinstance(data,dict) else data
        conn.request(method,path,body=body,headers={'Content-Type':'application/json',**(headers or {})})
        response=conn.getresponse();status=response.status;body=response.read();conn.close()
        return status,body
    def test_api_creates_real_versioned_project_and_reads_assets_from_separate_service(self):
        self.client.create_asset('image','跨产品图片',{'provenance':'external-consumer'})
        status,body=self.request('GET','/api/assets?kind=image')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['assets'][0]['name'],'跨产品图片')
        status,body=self.request('POST','/api/projects',{'name':'HTTP项目','transcript':'不要替用户批准。'})
        self.assertEqual(status,201);p=json.loads(body)['project']
        self.assertTrue(p['segments'][0]['estimated'])
        status,body=self.request('GET','/api/projects/'+p['id']+'/export')
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['project']['id'],p['id'])
    def test_range_serves_real_blob_and_traversal_is_rejected(self):
        file=self.root/'blob.jpg';file.write_bytes(b'\xff\xd8'+b'x'*100)
        blob=self.client.put_blob(file,'image/jpeg')
        status,body=self.request('GET','/api/media/'+blob['sha256'],headers={'Range':'bytes=2-5'})
        self.assertEqual((status,body),(206,b'xxxx'))
        self.assertEqual(self.request('GET','/api/media/../../project_store.py')[0],404)
        self.assertEqual(self.request('GET','/api/media/'+blob['sha256'],headers={'Range':'bytes=200-'})[0],416)
    def test_foreign_origin_cannot_modify_or_read_local_projects(self):
        for method in ('GET','POST'):
            status,_=self.request(method,'/api/projects',{'name':'attacker'} if method=='POST' else None,{'Origin':'https://evil.example'})
            self.assertEqual(status,403)
        self.assertEqual(self.request('GET','/api/status',headers={'Host':'evil.example'})[0],403)
    def test_application_html_loads_own_scripts_but_asset_payloads_stay_sandboxed(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('GET','/index.html');response=conn.getresponse();body=response.read().decode()
        self.assertIn("script-src 'self'",response.getheader('Content-Security-Policy'))
        self.assertIn('<title>观</title>',body);conn.close()
    def test_engine_root_returns_to_existing_product_instead_of_a_second_interface(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=5)
        conn.request('GET','/');response=conn.getresponse();response.read()
        self.assertEqual(response.status,302)
        self.assertEqual(response.getheader('Location'),'http://127.0.0.1:4182/?view=ai-making');conn.close()
    def test_asset_backup_endpoint_returns_restorable_zip(self):
        self.client.create_asset('study','研究记录',{'note':'备份测试'})
        status,body=self.request('GET','/api/assets/export')
        self.assertEqual(status,200);self.assertTrue(body.startswith(b'PK'))
        backup=self.root/'backup.zip';backup.write_bytes(body)
        other=AssetStore(self.root/'restored');other.restore_bundle(backup)
        self.assertEqual(other.list_assets()[0]['name'],'研究记录')

    def test_replica_detail_and_review_use_persistent_review_service(self):
        expected = {'replica': {'id': 'replica-test'}, 'scenes': [], 'review_available': False}
        with patch.object(self.app.replica_review, 'detail', return_value=expected) as detail:
            status, body = self.request('GET', '/api/replicas/replica-test')
            self.assertEqual(status, 200); self.assertEqual(json.loads(body), expected)
            detail.assert_called_once_with('replica-test')
        review = {'scene_id': 's1', 'render_hash': 'a'*64, 'expected_revision': 2, 'action': 'approve'}
        with patch.object(self.app.replica_review, 'review', return_value=expected) as persist:
            status, _ = self.request('POST', '/api/replicas/replica-test/review', review)
            self.assertEqual(status, 200); persist.assert_called_once_with('replica-test', review)

    def test_replica_job_marks_saved_skill_failure_as_failed(self):
        failed = {'id': 'replica-test', 'metadata': {'skill_bridge': {'events': [{
            'status': 'failed', 'error': '模型生成超时；没有静态帧。'}]}}}
        with patch('skill_runner.SkillRunner.advance', return_value=failed):
            status, body = self.request('POST', '/api/replicas/replica-test/advance', {'stage': 'layout'})
            self.assertEqual(status, 202)
            job = json.loads(body)['job']
            self.app.threads[-1].join(timeout=1)
        saved = self.app.repo.get(job['id'], 'job')
        self.assertEqual(saved['status'], 'failed')
        self.assertIn('模型生成超时', saved['error'])

    def test_source_import_does_not_create_a_production_project(self):
        with patch('server.import_workbench_source', return_value={'id': 'source-test'}) as ingest:
            status, body = self.request('POST', '/api/workbench-source', {'project_id': 'workbench-test'})
            self.assertEqual(status, 201); self.assertEqual(json.loads(body)['source']['id'], 'source-test')
            ingest.assert_called_once_with(self.app, 'workbench-test')
            self.assertEqual(self.app.repo.list('project'), [])


if __name__=='__main__':unittest.main()
