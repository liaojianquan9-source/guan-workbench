import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from renderer import (ADAPTERS, RUNTIME, AUDITED_MANIFEST_SHA256, Renderer,
    adapter_signature, layout_check, probe, run_command, sha256, validate_fields, verify_source)
from replica import ReplicaService


class MemoryAssets:
    def __init__(self, root):
        self.root = Path(root)
        self.assets = {}
        self.links = []

    def put_blob(self, path, media_type=None):
        digest = sha256(path)
        target = self.root / digest
        if not target.exists():
            shutil.copyfile(path, target)
        return {"sha256": digest, "size": target.stat().st_size, "media_type": media_type}

    def blob_path(self, digest):
        return self.root / digest

    def create_asset(self, kind, name, metadata=None, blob_hash=None, asset_id=None):
        asset_id = asset_id or f"asset-{len(self.assets)}"
        asset = {"id": asset_id, "revision": 1, "kind": kind, "name": name,
            "metadata": metadata or {}, "blob_hash": blob_hash}
        self.assets[asset_id] = [asset]
        return asset

    def get_asset(self, asset_id, revision=None):
        values = self.assets[asset_id]
        return values[-1] if revision is None else values[revision-1]

    def revise_asset(self, asset_id, expected_revision, patch):
        old = self.get_asset(asset_id)
        if expected_revision != old["revision"]:
            raise ValueError("conflict")
        value = {**old, **patch, "revision": expected_revision+1}
        self.assets[asset_id].append(value)
        return value

    def add_relation(self, *args, **kwargs):
        self.links.append((args, kwargs))


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = MemoryAssets(self.root)
        self.renderer = Renderer(self.assets, self.root / "work")

    def tearDown(self):
        self.temp.cleanup()

    def video(self, name, seconds=1, color="blue", audio=False):
        path = self.root / name
        args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color={color}:s=160x240:r=30:d={seconds}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            args += ["-c:a", "aac", "-shortest"]
        run_command(args + [path])
        return path

    def test_untrusted_renderer_and_fields_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            validate_fields("../../arbitrary", {})
        with self.assertRaises(ValueError):
            validate_fields("kimi-moon-v1", {"title": "x"*15})
        with self.assertRaises(ValueError):
            validate_fields("kimi-moon-v1", {"sourceVideo": "/etc/passwd"})
        with self.assertRaises(ValueError):
            validate_fields("kimi-moon-v1", {"image": "https://example.test/a.jpg"})
        with self.assertRaises(ValueError):
            validate_fields("kimi-moon-v1", {"image": {"asset_id": "a", "revision": 0}})

    def test_actual_fields_map_to_original_remotion_props(self):
        fields = validate_fields("kimi-moon-v1", {"title": "新素材", "subtitle": "复用", "texture_text": "证据"})
        result = self.renderer._props("kimi-moon-v1", fields, self.root)
        self.assertEqual(result, {"motionEnabled": True, "kimiTitle": "新素材", "k3Title": "复用", "moonTitle": "证据"})
        problem = self.renderer._props("problem-photo-v1", validate_fields("problem-photo-v1", {"title": "换文字"}), self.root)
        self.assertEqual(problem["content"]["problem-title"], "换文字")
        number = self.renderer._props("kimi-number-v1", validate_fields("kimi-number-v1", {}), self.root)
        self.assertEqual(number["weightsLabel"], "", "通用数字不能留下旧案例的 Weights 语义")

    def test_image_resolution_pins_historical_revision(self):
        old = self.root / "old.svg"
        old.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="60"/>')
        blob = self.assets.put_blob(old)
        asset = self.assets.create_asset("image", "old", blob_hash=blob["sha256"])
        self.assets.revise_asset(asset["id"], 1, {"blob_hash": "missing-new-file"})
        fields = validate_fields("problem-photo-v1", {"image": {"asset_id": asset["id"], "revision": 1}})
        result = self.renderer._props("problem-photo-v1", fields, self.root / "public")
        self.assertEqual((self.root / "public" / result["assets"]["problem-background"]).read_bytes(), old.read_bytes())

    def test_copied_audited_source_hashes_match_manifest(self):
        records = json.loads((RUNTIME / "SOURCE-MANIFEST.json").read_text())
        self.assertGreater(len(records), 10)
        for record in records:
            self.assertEqual(sha256(RUNTIME / record["file"]), record["sha256"], record["file"])

    def style_package(self):
        service = ReplicaService(self.assets, self.renderer, self.root / "imports")
        package = service._package("kimi-moon-v1", self.root)
        blob = self.assets.put_blob(package)
        return {"id": "fixed-style", "revision": 1, "blob_hash": blob["sha256"], "metadata": {
            "renderer_id": "kimi-moon-v1", "source_manifest_sha256": AUDITED_MANIFEST_SHA256,
            "adapter_contract_sha256": adapter_signature("kimi-moon-v1"), "package_hash": blob["sha256"]}}

    def test_style_restores_exact_shared_package_without_source_checkout(self):
        style = self.style_package()
        with patch("renderer.RUNTIME", self.root / "missing-checkout"):
            source, evidence = self.renderer.source_snapshot(style, self.root / "restored")
        self.assertEqual(evidence["source_origin"], "immutable_asset_package")
        self.assertEqual(sha256(source / "remotion/composition.tsx"), sha256(RUNTIME / "kimi/remotion/composition.tsx"))

    def test_style_rejects_wrong_release_and_tampered_or_added_code(self):
        style = self.style_package()
        changed = {**style, "metadata": {**style["metadata"], "source_manifest_sha256": "0"*64}}
        with self.assertRaisesRegex(ValueError, "固定版本"):
            self.renderer.source_snapshot(changed, self.root / "wrong")
        package = self.assets.blob_path(style["blob_hash"])
        for mode in ["alter", "added", "traversal"]:
            altered = self.root / f"{mode}.zip"
            with zipfile.ZipFile(package) as original, zipfile.ZipFile(altered, "w") as target:
                for member in original.infolist():
                    content = original.read(member)
                    if mode == "alter" and member.filename == "remotion/composition.tsx":
                        content += b"\n// changed after approval"
                    target.writestr(member, content)
                if mode == "added": target.writestr("remotion/extra.ts", "throw new Error('unapproved')")
                if mode == "traversal": target.writestr("../escape.ts", "unapproved")
            blob = self.assets.put_blob(altered)
            changed = {**style, "blob_hash": blob["sha256"], "metadata": {**style["metadata"], "package_hash": blob["sha256"]}}
            with self.assertRaises(ValueError, msg=mode):
                self.renderer.source_snapshot(changed, self.root / f"bad-{mode}")
        self.assertFalse((self.root / "escape.ts").exists())

    def test_snapshot_ignores_later_global_source_changes(self):
        style = self.style_package()
        snapshot, _ = self.renderer.source_snapshot(style, self.root / "snapshot")
        before = sha256(snapshot / "remotion/composition.tsx")
        fake = self.root / "mutable-copy"
        shutil.copytree(RUNTIME / "kimi", fake / "kimi")
        for name in ["SOURCE-MANIFEST.json", "package.json", "package-lock.json"]:
            shutil.copyfile(RUNTIME / name, fake / name)
        (fake / "kimi/remotion/composition.tsx").write_text("bad drift")
        with self.assertRaisesRegex(ValueError, "被修改"):
            verify_source(fake, "kimi")
        self.assertEqual(sha256(snapshot / "remotion/composition.tsx"), before)

    def test_timeout_kills_descendant_even_when_it_ignores_sigterm(self):
        started = self.root / "child-started"
        escaped = self.root / "child-escaped"
        child = ("import signal,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"Path({str(started)!r}).write_text('started'); time.sleep(1.2); "
            f"Path({str(escaped)!r}).write_text('survived')")
        parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
        log = self.root / "timeout.json"
        with self.assertRaisesRegex(ValueError, "超时"):
            run_command([sys.executable, "-c", parent], timeout=.35, log=log)
        self.assertTrue(started.exists())
        time.sleep(1.2)
        self.assertFalse(escaped.exists())
        self.assertTrue(json.loads(log.read_text())["timed_out"])

    def test_fixed_box_layout_requires_shorter_mixed_subtitle(self):
        fields = validate_fields("kimi-moon-v1", {"title": "睡好觉", "subtitle": "才能用好AI", "texture_text": "好好休息"})
        result = layout_check("kimi-moon-v1", fields)
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual(result["issues"][0]["field"], "subtitle")
        fields["subtitle"] = "用好AI"
        self.assertEqual(layout_check("kimi-moon-v1", fields)["status"], "passed")

    def test_chrome_reports_real_subset_font_and_chinese_fallback(self):
        cli, browser = self.renderer._runtime()
        results = []
        for index, text in enumerate(["解决问题", "复刻镜头"]):
            out = self.root / f"font-{index}"
            out.mkdir()
            result = self.renderer.font_report("problem-photo-v1",
                validate_fields("problem-photo-v1", {"title": text}), RUNTIME / "problem", out, cli, browser)
            results.append(next(f for f in result["fields"] if f["field"] == "title"))
        self.assertFalse(results[0]["fallback_detected"])
        self.assertTrue(results[0]["fonts"][0]["isCustomFont"])
        self.assertTrue(results[1]["fallback_detected"])
        self.assertFalse(results[1]["fonts"][0]["isCustomFont"])
        numeric_output = self.root / "number-fonts"
        numeric_output.mkdir()
        numeric = self.renderer.font_report("kimi-number-v1", validate_fields("kimi-number-v1", {}),
            RUNTIME / "kimi", numeric_output, cli, browser)
        fonts = {item["field"]: item for item in numeric["fields"]}
        self.assertEqual(fonts["unit"]["weight"], 900)
        self.assertEqual(fonts["annotation"]["weight"], 700)
        self.assertNotEqual(fonts["unit"]["fonts"][0]["postScriptName"], fonts["annotation"]["fonts"][0]["postScriptName"])

    def test_failed_import_resumes_only_unfinished_style_and_stage(self):
        from types import SimpleNamespace
        calls = []
        def fake_render(style, fields, output_dir, **kwargs):
            renderer_id = style["metadata"]["renderer_id"]
            stage = Path(output_dir).name
            calls.append((renderer_id, stage))
            if renderer_id == "kimi-number-v1" and stage == "replacement" and len(calls) == 4:
                raise ValueError("deterministic renderer failure")
            out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
            video, poster = out / "video.mp4", out / "poster.jpg"
            video.write_bytes(f"{renderer_id}:{stage}".encode()); poster.write_bytes(stage.encode())
            return {"video": str(video), "poster": str(poster), "report": {"status": "passed", "video_sha256": sha256(video)}}
        service = ReplicaService(self.assets, SimpleNamespace(render=fake_render), self.root / "resume")
        with patch("replica._difference", return_value=10):
            with self.assertRaisesRegex(ValueError, "renderer failure"):
                service.import_case("kimi-opening")
            failed = self.assets.get_asset("replica-kimi-opening-v1")
            self.assertEqual(failed["metadata"]["status"], "failed")
            self.assertEqual(failed["metadata"]["current_failure"]["stage"], "replacement")
            self.assertEqual(len(failed["metadata"]["styles"]), 1)
            failure_hash = failed["metadata"]["current_failure"]["evidence_hash"]
            self.assertEqual(json.loads(self.assets.blob_path(failure_hash).read_text())["type"], "ValueError")
            resumed = service.import_case("kimi-opening")
            self.assertEqual(resumed["replica"]["metadata"]["status"], "imported")
            self.assertEqual(len(resumed["styles"]), 2)
            self.assertEqual(calls.count(("kimi-moon-v1", "baseline")), 1)
            self.assertEqual(calls.count(("kimi-moon-v1", "replacement")), 1)
            self.assertEqual(calls.count(("kimi-number-v1", "baseline")), 1)
            self.assertEqual(calls.count(("kimi-number-v1", "replacement")), 2)
            self.assertEqual(self.assets.get_asset("style-kimi-moon-v1")["revision"], 1)
            self.assertEqual(len(resumed["replica"]["metadata"]["failures"]), 1)

    def test_compose_preserves_dimensions_duration_and_original_audio(self):
        source = self.video("talk.mp4", 2, audio=True)
        broll = self.video("broll.mp4", 1, "red")
        result = self.renderer.compose(source, [{"id": "approved", "start": .5, "end": 1.5,
            "render_path": str(broll)}], self.root / "final.mp4")
        self.assertTrue(all(result["report"]["checks"].values()))
        self.assertTrue(probe(result["video"])["has_audio"])
        self.assertEqual(probe(result["video"])["frames"], 60)
        # Audio packets are copied, not retimed or regenerated.
        def audio_bytes(path):
            import subprocess
            return subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "adts", "-"])
        self.assertEqual(audio_bytes(source), audio_bytes(result["video"]))

    def test_cover_crop_and_dissolve_are_encoded_in_review_video(self):
        source=self.video('effect-source.mp4',2,audio=True)
        broll=self.video('effect-broll.mp4',1,'red')
        result=self.renderer.compose(source,[{'id':'effect','start':.5,'end':1.5,
            'render_path':str(broll),'crop_mode':'cover','transition':'dissolve'}],self.root/'effect-final.mp4')
        self.assertTrue(all(result['report']['checks'].values()))
        self.assertEqual(result['report']['effects'],[{'card_id':'effect','crop_mode':'cover','transition':'dissolve'}])
        self.assertTrue(probe(result['video'])['has_audio'])

    def test_compose_rejects_overlap_and_stale_duration(self):
        source = self.video("talk.mp4", 2)
        broll = self.video("broll.mp4", 1)
        a = {"id": "a", "start": .2, "end": 1.2, "render_path": str(broll)}
        with self.assertRaises(ValueError):
            self.renderer.compose(source, [a, {**a, "id": "b", "start": .5, "end": 1.5}], self.root / "final.mp4")
        with self.assertRaises(ValueError):
            self.renderer.compose(source, [{**a, "end": 1.8}], self.root / "final.mp4")

    def test_study_extracts_real_frames_and_leaves_replica_unfinished(self):
        source_path = self.video("study.mp4", 2)
        blob = self.assets.put_blob(source_path)
        source = self.assets.create_asset("source", "reference", blob_hash=blob["sha256"])
        service = ReplicaService(self.assets, self.renderer, self.root / "studies")
        study = service.study(source, .2, 1.4, "研究转场")
        self.assertEqual(len(study["metadata"]["frames"]), 3)
        for frame in study["metadata"]["frames"]:
            self.assertGreater(self.assets.blob_path(frame["blob_hash"]).stat().st_size, 0)
        replica = self.assets.get_asset(study["metadata"]["replica"]["asset_id"])
        self.assertEqual(replica["metadata"]["status"], "needs_work")
        self.assertEqual(replica["metadata"]["stages"]["implementation"], "pending")
        with self.assertRaises(ValueError):
            service.study(source, 1, 3)


if __name__ == "__main__":
    unittest.main()
