"""Real HTTP boundary checks for the AI-making voice and preset routes."""
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ai_making_server", ROOT / "server.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class AiMakingRoutesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="ai-making-test-")
        base = Path(self.folder.name)
        self.store = backend.ProjectStore(base / "data", detector="ffmpeg")
        script = base / "fake-asr.py"
        script.write_text("import json\nprint(json.dumps({'segments':[{'start':0,'end':1.5,'text':'比较两款产品。'}], 'engine':'test'}))\n")
        self.store.asr_python = Path(sys.executable)
        self.store.asr_script = script
        self.server = backend.WorkbenchServer(("127.0.0.1", 0), self.store, ROOT / "public")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.store.close()
        self.folder.cleanup()

    def request(self, method, path, body=None, headers=None):
        port = self.server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request(method, path, body=body, headers={"Host": f"127.0.0.1:{port}", **(headers or {})})
        response = conn.getresponse()
        content = response.read()
        conn.close()
        return response.status, content

    def test_voice_upload_returns_real_adapter_segments(self):
        status, content = self.request("POST", "/api/ai-making/transcribe", b"audio-data", {"Content-Type": "audio/wav"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(content)["segments"][0]["text"], "比较两款产品。")
        self.assertEqual(self.request("POST", "/api/ai-making/transcribe", b"", {"Content-Type": "audio/wav"})[0], 400)

    def test_preset_preview_is_allowlisted(self):
        status, content = self.request("GET", "/ai-preset-media/shot-001.mp4", headers={"Range": "bytes=0-31"})
        self.assertEqual(status, 206)
        self.assertEqual(len(content), 32)
        self.assertEqual(self.request("GET", "/ai-preset-media/..%2Fserver.py")[0], 404)

    def test_image_replacement_is_local_and_rejects_non_images(self):
        image = b"\x89PNG\r\n\x1a\n" + b"test-image"
        status, content = self.request("POST", "/api/ai-making/assets", image, {"Content-Type": "image/png"})
        self.assertEqual(status, 201)
        url = json.loads(content)["url"]
        self.assertTrue(url.startswith("/ai-making-assets/"))
        self.assertEqual(self.request("GET", url), (200, image))
        self.assertEqual(self.request("POST", "/api/ai-making/assets", b"script", {"Content-Type": "image/png"})[0], 415)
        self.assertEqual(self.request("GET", "/ai-making-assets/..%2Fserver.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
