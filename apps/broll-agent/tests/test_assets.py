"""Real temporary SQLite + HTTP tests; no user asset library is touched."""
import concurrent.futures
import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_client import AssetClient
from asset_server import AssetHTTPServer
from asset_store import AssetStore


class AssetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = AssetStore(self.root / "library")
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"video fixture bytes\x00\x01" * 100)

    def test_content_addressed_upload_deduplicates_and_survives_source_change(self):
        first = self.store.put_blob(self.source)
        second = self.store.put_blob(self.source)
        self.assertEqual(first, second)
        self.assertEqual(first["media_type"], "video/mp4")
        before = self.store.blob_path(first["sha256"]).read_bytes()
        self.source.write_bytes(b"source later changed")
        self.assertEqual(self.store.blob_path(first["sha256"]).read_bytes(), before)
        self.assertEqual(hashlib.sha256(before).hexdigest(), first["sha256"])
        with self.assertRaises(ValueError):
            self.store.blob_path("../assets.sqlite3")

    def test_historical_project_references_survive_revision_and_search(self):
        original = self.store.create_asset("style", "科技数据强调", {"status": "usable", "用途": "数字 对比"})
        project_a = {"style": {"asset_id": original["id"], "revision": 1}}
        project_b = {"style": {"asset_id": original["id"], "revision": 1}}
        revised = self.store.revise_asset(original["id"], 1, {"metadata": {"status": "draft"}, "name": "新版"})
        self.assertEqual(revised["revision"], 2)
        for project in (project_a, project_b):
            reference = project["style"]
            self.assertEqual(self.store.get_asset(reference["asset_id"], reference["revision"]), original)
        self.assertEqual(self.store.list_assets(status="usable"), [])
        self.assertEqual(self.store.list_assets(query="新版", kind="style"), [revised])
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.store.revise_asset(original["id"], 1, {"name": "stale"})

    def test_concurrent_compare_and_swap_has_one_winner(self):
        asset = self.store.create_asset("study", "Research")
        def revise(index):
            try:
                return self.store.revise_asset(asset["id"], 1, {"name": str(index)})["revision"]
            except ValueError:
                return "conflict"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(revise, range(8)))
        self.assertEqual(results.count(2), 1)
        self.assertEqual(results.count("conflict"), 7)

    def test_reject_invalid_records_and_dangling_references(self):
        for values in [("bad-kind", "name", {}), ("image", "", {}), ("image", "name", []), ("image", "name", {"n": float("nan")})]:
            with self.assertRaises(ValueError):
                self.store.create_asset(*values)
        with self.assertRaises(ValueError):
            self.store.create_asset("image", "missing", blob_hash="0" * 64)
        with self.assertRaises(KeyError):
            self.store.add_relation("missing", "missing2", "derived_from")
        a = self.store.create_asset("image", "Image")
        for patch in ({"kind": "style"}, {}, {"metadata": []}):
            with self.assertRaises(ValueError):
                self.store.revise_asset(a["id"], 1, patch)

    def make_bundle(self):
        blob = self.store.put_blob(self.source)
        source = self.store.create_asset("source", "reference", {"rights_status": "user-provided"}, blob["sha256"])
        style = self.store.create_asset("style", "caption card", {"status": "usable"})
        self.store.revise_asset(style["id"], 1, {"name": "caption card v2"})
        self.store.add_relation(style["id"], source["id"], "derived_from", {"source_revision": 1})
        bundle = self.root / "export.zip"
        manifest = self.store.export_bundle(bundle)
        return bundle, manifest

    def test_portable_bundle_restores_all_revisions_blobs_relations(self):
        bundle, manifest = self.make_bundle()
        destination = AssetStore(self.root / "second-product")
        restored = destination.restore_bundle(bundle)
        self.assertEqual(restored, {"assets": 2, "revisions_imported": 3, "blobs": 1, "relations": 1})
        for asset in manifest["assets"]:
            self.assertEqual(destination.get_asset(asset["id"], asset["revision"]), asset)
        for blob in manifest["blobs"]:
            self.assertEqual(destination.blob_path(blob["sha256"]).read_bytes(), self.source.read_bytes())
        self.assertEqual(destination.restore_bundle(bundle)["revisions_imported"], 0)

    def test_bundle_integrity_path_traversal_and_conflict_do_not_change_assets(self):
        bundle, manifest = self.make_bundle()
        for change in ("tamper", "traversal", "invalid-reference"):
            malicious = self.root / (change + ".zip")
            with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(malicious, "w") as target:
                for name in source.namelist():
                    data = source.read(name)
                    if change == "tamper" and name.startswith("blobs/"):
                        data = b"X" * len(data)
                    if change == "invalid-reference" and name == "manifest.json":
                        body = json.loads(data)
                        body["relations"][0]["object_id"] = "missing"
                        data = json.dumps(body).encode()
                    target.writestr(name, data)
                if change == "traversal":
                    target.writestr("../../escaped.txt", "bad")
            restored = AssetStore(self.root / change)
            with self.assertRaises(ValueError):
                restored.restore_bundle(malicious)
            self.assertEqual(restored.list_assets(), [])
        conflict = AssetStore(self.root / "conflict")
        first = manifest["assets"][0]
        original = conflict.create_asset(first["kind"], "different content", asset_id=first["id"])
        with self.assertRaisesRegex(ValueError, "conflict"):
            conflict.restore_bundle(bundle)
        self.assertEqual(conflict.list_assets(), [original])
        self.assertFalse((self.root.parent / "escaped.txt").exists())


class AssetHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = AssetStore(self.root / "library")
        self.server = AssetHTTPServer(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.client = AssetClient(self.url, self.root / "cache")
        self.other_client = AssetClient(self.url, self.root / "other-cache")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_two_independent_http_clients_share_fixed_revisions(self):
        self.assertEqual(self.client.health()["status"], "ok")
        image = self.root / "image.png"
        image.write_bytes(b"real independent product bytes")
        blob = self.client.put_blob(image)
        original = self.client.create_asset("image", "封面", {"status": "usable"}, blob["sha256"])
        self.assertEqual(self.other_client.get_asset(original["id"], 1), original)
        self.assertEqual(self.other_client.blob_path(blob["sha256"]).read_bytes(), image.read_bytes())
        self.client.revise_asset(original["id"], 1, {"name": "new name"})
        self.assertEqual(self.other_client.get_asset(original["id"], 1)["name"], "封面")
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.other_client.revise_asset(original["id"], 1, {"name": "lost update"})
        with self.assertRaises(KeyError):
            self.other_client.get_asset("does-not-exist")
        self.assertEqual(len(self.other_client.list_assets(kind="image", query="new", status="usable")), 1)
        relation = self.client.add_relation(original["id"], original["id"], "test-reuse", {"revision": 1})
        self.assertEqual(self.other_client.relations(original["id"]), [relation])
        export = self.root / "http-export.zip"
        manifest = self.client.export_bundle(export)
        self.assertEqual(len(manifest["assets"]), 2)
        self.assertEqual(self.client.restore_bundle(export)["revisions_imported"], 0)

    def test_blob_range_suffix_head_and_invalid_range(self):
        source = self.root / "bytes.mp4"
        source.write_bytes(b"0123456789")
        blob = self.client.put_blob(source)
        path = "/v1/blobs/" + blob["sha256"]
        for header, expected, interval in (("bytes=2-5", b"2345", "bytes 2-5/10"), ("bytes=-3", b"789", "bytes 7-9/10"), ("bytes=8-99", b"89", "bytes 8-9/10")):
            code, headers, data = self.request("GET", path, headers={"Range": header})
            self.assertEqual((code, data, headers["Content-Range"]), (206, expected, interval))
        code, headers, data = self.request("HEAD", path)
        self.assertEqual((code, headers["Content-Length"], data), (200, "10", b""))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        for invalid in ("bytes=30-", "bytes=3-1", "bytes=0-1,5-6", "bytes=-0"):
            self.assertEqual(self.request("GET", path, headers={"Range": invalid})[0], 416)

    def test_cross_site_and_dns_rebinding_rejected_before_write(self):
        body = json.dumps({"kind": "image", "name": "attack"}).encode()
        for headers in ({"Origin": "https://evil.example"}, {"Host": "evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("POST", "/v1/assets", body, headers)[0], 403)
        self.assertEqual(self.client.list_assets(), [])
        code, headers, _ = self.request("POST", "/v1/assets", body, {"Origin": "http://127.0.0.1:4183", "Content-Type": "application/json"})
        self.assertEqual(code, 201)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://127.0.0.1:4183")

    def test_client_repairs_corrupt_download_cache(self):
        source = self.root / "media.bin"
        source.write_bytes(b"verify downloaded bytes")
        blob = self.client.put_blob(source)
        cached = self.client.blob_path(blob["sha256"])
        cached.write_bytes(b"corrupt cache")
        self.assertEqual(self.client.blob_path(blob["sha256"]).read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
