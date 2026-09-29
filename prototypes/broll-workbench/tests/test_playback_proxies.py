"""Real playback proxies: smaller decode surface, unchanged research source/timebase."""
import hashlib
import http.client
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import ProjectStore, WorkbenchServer, ROOT, APIError

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class PlaybackProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        path = Path(cls.fixture.name) / 'fixture.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30000/1001:d=2',
                        '-f','lavfi','-i','sine=frequency=500:duration=2','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],check=True)
        cls.source = path.read_bytes()
    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.tmp.name), detector='ffmpeg')
        self.project = self.store.import_stream('test.mp4',io.BytesIO(self.source),len(self.source))
        self.id = self.project['id']
    def tearDown(self): self.store.close(); self.tmp.cleanup()
    def wait(self,quality):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=self.store.playback.status(self.id,quality)
            if state['status'] in {'ready','error'}:return state
            time.sleep(.05)
        self.fail('proxy timed out')
    def test_quality_preserves_timebase_audio_and_source_and_reuses_cache(self):
        folder=self.store.directory(self.id)
        before={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['project.json','source.mp4']}
        original=self.store.probe(folder/'source.mp4')
        for quality,width,height in [('half',160,90),('quarter',80,44)]:
            self.store.playback.status(self.id,quality,start=True)
            state=self.wait(quality);self.assertEqual(state['status'],'ready',state)
            target=self.store.playback.file(self.id,state['url'].split('/')[-1]);metadata=self.store.probe(target)
            self.assertEqual((metadata['width'],metadata['height']),(width,height))
            self.assertTrue(metadata['has_audio']);self.assertAlmostEqual(metadata['fps'],original['fps'],places=5)
            self.assertAlmostEqual(metadata['duration'],original['duration'],places=3)
            stat=target.stat().st_mtime_ns
            self.assertEqual(self.store.playback.status(self.id,quality,start=True),state)
            self.assertEqual(target.stat().st_mtime_ns,stat)
        self.assertEqual(before,{n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in before})
    def test_duplicate_requests_share_one_job_and_invalid_quality_rejected(self):
        with self.assertRaises(APIError):self.store.playback.status(self.id,'../source')
        started=threading.Event();release=threading.Event();real=self.store.playback.generate
        def delayed(*args):started.set();release.wait(5);real(*args)
        with patch.object(self.store.playback,'generate',side_effect=delayed) as generate:
            for _ in range(4):self.store.playback.status(self.id,'half',start=True)
            started.wait(5);self.assertEqual(generate.call_count,1);release.set()
            self.assertEqual(self.wait('half')['status'],'ready')
    def test_failed_generation_can_retry_without_publishing_partial_video(self):
        with patch.object(self.store,'run',side_effect=RuntimeError('test failure')):
            self.store.playback.status(self.id,'half',start=True)
            self.assertEqual(self.wait('half')['status'],'error')
        self.assertFalse(list((self.store.directory(self.id)/'playback').glob('*.mp4')))
        self.store.playback.status(self.id,'half',start=True)
        self.assertEqual(self.wait('half')['status'],'ready')
    def test_http_endpoint_and_media_byte_ranges(self):
        server=WorkbenchServer(('127.0.0.1',0),self.store,ROOT/'public')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
        try:
            conn.request('POST',f'/api/projects/{self.id}/playback',json.dumps({'quality':'half'}),{'Content-Type':'application/json','Origin':f'http://127.0.0.1:{server.server_port}'})
            response=conn.getresponse();self.assertEqual(response.status,200);response.read()
            state=self.wait('half');self.assertEqual(state['status'],'ready')
            conn.request('GET',state['url'],headers={'Range':'bytes=0-31'})
            response=conn.getresponse();self.assertEqual(response.status,206);self.assertEqual(len(response.read()),32)
            conn.request('GET',f'/api/projects/{self.id}/playback?quality=half')
            response=conn.getresponse();self.assertEqual(json.loads(response.read())['status'],'ready')
        finally:conn.close();server.shutdown();server.server_close();thread.join(3)

if __name__=='__main__':unittest.main()
