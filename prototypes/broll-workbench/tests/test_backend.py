"""Behavioral tests with a real generated MP4 and real FFmpeg, using a temporary library."""

import concurrent.futures
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workbench_server", ROOT / "server.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class RangesTest(unittest.TestCase):
    def test_full_coverage_short_edges_and_duplicates(self):
        ranges = backend.shot_ranges(8, [0, 0.1, 2, 2.05, 2, 5, 7.8, 9, float("nan")], 0.5)
        self.assertEqual(ranges, [(0, 2), (2, 5), (5, 8)])
        self.assertTrue(all(end - start >= 0.5 for start, end in ranges))
        self.assertEqual(backend.shot_ranges(0.2, [0.1], 0.5), [(0, 0.2)])


class SystemUsageTest(unittest.TestCase):
    def test_memory_snapshot_includes_only_workbench_process_tree(self):
        rows = """\
1 0 50
100 1 100
101 100 200
102 101 300
200 1 900
"""
        usage = backend.memory_usage_snapshot(
            100,
            process_rows=rows,
            total_memory_bytes=1000 * 1024,
        )
        self.assertTrue(usage["available"])
        self.assertEqual(usage["memory_bytes"], 600 * 1024)
        self.assertEqual(usage["memory_percent"], 60.0)
        self.assertEqual(usage["process_count"], 3)
        self.assertEqual(usage["scope"], "workbench_and_children")

    def test_memory_snapshot_fails_closed_when_root_is_missing(self):
        usage = backend.memory_usage_snapshot(
            999,
            process_rows="1 0 50\n",
            total_memory_bytes=1000 * 1024,
        )
        self.assertFalse(usage["available"])
        self.assertIsNone(usage["memory_percent"])

    def test_memory_snapshot_fails_closed_when_process_list_is_unavailable(self):
        with patch.object(backend.subprocess, "Popen", side_effect=OSError("unavailable")):
            usage = backend.memory_usage_snapshot(100, total_memory_bytes=1000 * 1024)
        self.assertFalse(usage["available"])
        self.assertEqual(usage["measurement"], "rss_sum")


class LibraryLockTest(unittest.TestCase):
    def test_second_workbench_is_refused_before_recovery_touches_projects(self):
        with tempfile.TemporaryDirectory(prefix="broll-library-lock-") as temporary:
            root = Path(temporary)
            first = backend.ProjectStore(root, detector="ffmpeg")
            project_id = "a" * 32
            project_dir = root / project_id
            project_dir.mkdir()
            record = {
                "id": project_id, "status": "processing", "revision": 7, "updated_at": "before",
                "shots": [], "transcript": {}, "music": {}, "music_sections": {}, "research_clips": [],
            }
            (project_dir / "project.json").write_text(json.dumps(record), encoding="utf-8")
            try:
                duplicate = subprocess.run(
                    [sys.executable, str(ROOT / "server.py"), "--data-dir", str(root), "--port", "0"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(duplicate.returncode, 2, duplicate.stderr)
                self.assertIn("资料库已由另一个拉片工作台打开", duplicate.stderr)
                untouched = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
                self.assertEqual((untouched["status"], untouched["revision"]), ("processing", 7))
            finally:
                first.close()

            reopened = backend.ProjectStore(root, detector="ffmpeg")
            try:
                recovered = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
                self.assertEqual((recovered["status"], recovered["revision"]), ("error", 8))
            finally:
                reopened.close()

    def test_lock_stays_held_until_all_writers_have_stopped(self):
        with tempfile.TemporaryDirectory(prefix="broll-library-shutdown-") as temporary:
            root = Path(temporary)
            store = backend.ProjectStore(root, detector="ffmpeg")
            store.jobs["current-writer"] = threading.current_thread()
            store.close()
            with self.assertRaises(backend.LibraryInUseError):
                backend.ProjectStore(root, detector="ffmpeg")
            store.jobs.clear()
            store.close()
            reopened = backend.ProjectStore(root, detector="ffmpeg")
            reopened.close()

    def test_lock_file_symlink_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory(prefix="broll-library-symlink-") as temporary:
            root = Path(temporary)
            target = root / "important.txt"
            target.write_text("must stay intact", encoding="utf-8")
            library = root / "library"
            library.mkdir()
            (library / ".workbench.lock").symlink_to(target)
            with self.assertRaises(backend.LibraryInUseError):
                backend.ProjectStore(library, detector="ffmpeg")
            self.assertEqual(target.read_text(encoding="utf-8"), "must stay intact")

    def test_schema_migrates_and_corrupt_primary_recovers_from_backup(self):
        with tempfile.TemporaryDirectory(prefix="broll-project-recovery-") as temporary:
            root = Path(temporary)
            store = backend.ProjectStore(root, detector="ffmpeg")
            project_id = "d" * 32
            folder = root / project_id
            folder.mkdir()
            legacy = {"id": project_id, "name": "legacy", "shots": [], "revision": 4, "updated_at": "old"}
            (folder / "project.json").write_text(json.dumps(legacy), encoding="utf-8")
            migrated = store.read(project_id)
            self.assertEqual(migrated["schema_version"], backend.PROJECT_SCHEMA_VERSION)
            self.assertTrue((folder / backend.PROJECT_BACKUP).is_file())
            migrated["name"] = "new edit"
            store.write(migrated)
            (folder / "project.json").write_bytes(b"{broken")
            recovered = store.read(project_id)
            self.assertEqual(recovered["name"], "legacy")
            self.assertTrue(list(folder.glob(".project.json.corrupt-*")))
            self.assertEqual(json.loads((folder / "project.json").read_text())["name"], "legacy")
            store.close()

    def test_newer_project_schema_is_not_downgraded_from_backup(self):
        with tempfile.TemporaryDirectory(prefix="broll-project-version-") as temporary:
            root = Path(temporary)
            store = backend.ProjectStore(root, detector="ffmpeg")
            project_id = "e" * 32
            folder = root / project_id
            folder.mkdir()
            current = {"id": project_id, "shots": [], "schema_version": 999}
            (folder / "project.json").write_text(json.dumps(current), encoding="utf-8")
            (folder / backend.PROJECT_BACKUP).write_text(json.dumps({"id": project_id, "shots": []}), encoding="utf-8")
            with self.assertRaises(backend.APIError):
                store.read(project_id)
            self.assertEqual(json.loads((folder / "project.json").read_text())["schema_version"], 999)
            store.close()

    def test_main_reports_missing_or_corrupt_config_without_traceback(self):
        for value in [json.dumps({"data_directory": "/definitely/missing/broll-library"}), "{broken"]:
            with self.subTest(value=value), tempfile.TemporaryDirectory(prefix="broll-config-") as temporary:
                home = Path(temporary)
                config = home / ".config/lapian-workbench/storage.json"
                config.parent.mkdir(parents=True)
                config.write_text(value, encoding="utf-8")
                environment = {**os.environ, "HOME": str(home)}
                result = subprocess.run([sys.executable, str(ROOT / "server.py"), "--port", "0"],
                                        capture_output=True, text=True, timeout=10, env=environment)
                self.assertEqual(result.returncode, 2)
                self.assertIn("无法打开拉片工作台", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class BackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_tmp = tempfile.TemporaryDirectory(prefix="broll-fixtures-")
        cls.video = Path(cls.fixture_tmp.name) / "three-shots.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=1",
            "-f", "lavfi", "-i", "color=c=white:s=160x90:r=10:d=1",
            "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=1",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "1", str(cls.video),
        ], check=True, timeout=30)
        cls.video_bytes = cls.video.read_bytes()
        cls.long_audio = Path(cls.fixture_tmp.name) / "long-audio.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(cls.video),
            "-f", "lavfi", "-i", "sine=frequency=440:duration=10", "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", str(cls.long_audio),
        ], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="broll-backend-")
        self.root = Path(self.tmp.name)
        self.store = backend.ProjectStore(self.root / "data", detector="ffmpeg")

    def tearDown(self):
        for thread in self.store.jobs.values():
            thread.join(timeout=30)
        self.store.close()
        self.tmp.cleanup()

    def upload(self):
        return self.store.import_stream("三镜头.mp4", io.BytesIO(self.video_bytes), len(self.video_bytes))

    def seed_legacy_audio_clip(self, project, *, tags=None):
        """Install an old saved-audio record without relying on the removed creator."""
        clip_id = backend.uid()
        payload = b"legacy-saved-audio"
        folder = self.store.directory(project["id"]) / "audio"
        folder.mkdir(exist_ok=True)
        (folder / f"{clip_id}.m4a").write_bytes(payload)
        clip = {
            "id": clip_id, "start": 0.25, "end": 1.25,
            "url": f"/media/{project['id']}/audio/{clip_id}.m4a",
            "duration": 1.0, "created_at": backend.now(), "note": "", "tag": "",
            "tags": list(tags or []), "asset_revision": 0,
        }
        latest = self.store.read(project["id"])
        latest["audio_clips"].append(clip)
        self.store.write(latest)
        return self.store.read(project["id"]), clip, payload

    def assert_contiguous(self, project):
        self.assertEqual(project["shots"][0]["start"], 0)
        self.assertEqual(project["shots"][-1]["end"], project["duration"])
        for first, second in zip(project["shots"], project["shots"][1:]):
            self.assertEqual(first["end"], second["start"])
        self.assertTrue(all(shot["end"] > shot["start"] for shot in project["shots"]))

    def test_real_analysis_and_thumbnails(self):
        project = self.upload()
        self.assertEqual(project["duration"], 3)
        initial = self.store.analyze(project["id"], {"threshold": 0.22, "min_duration": 0.5})
        self.assertEqual(initial["status"], "processing")
        self.store.jobs[project["id"]].join(timeout=30)
        project = self.store.read(project["id"])
        self.assertEqual(project["status"], "ready", project["message"])
        self.assertEqual(project["analysis"]["method"], "ffmpeg-scene")
        self.assertEqual(len(project["shots"]), 3)
        self.assert_contiguous(project)
        self.assertTrue(all(shot["end"] - shot["start"] >= 0.5 for shot in project["shots"]))
        hashes = []
        for shot in project["shots"]:
            image = self.store.directory(project["id"]) / "thumbnails" / f"{shot['id']}.jpg"
            self.assertTrue(image.read_bytes().startswith(b"\xff\xd8"))
            hashes.append(image.read_bytes())
        self.assertEqual(len(set(hashes)), 3)
        self.assertEqual((self.store.directory(project["id"]) / "source.mp4").read_bytes(), self.video_bytes)

    def test_notes_persist_and_no_stale_overwrite(self):
        project = self.upload()
        shot_id = project["shots"][0]["id"]
        stale_revision = project["revision"]
        project = self.store.annotate(project["id"], shot_id, {"note": "已保存笔记", "tag": "人物"})
        with self.assertRaises(backend.APIError) as conflict:
            self.store.annotate(project["id"], shot_id, {"note": "迟到的旧页内容", "expected_revision": stale_revision})
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(backend.LibraryInUseError):
            backend.ProjectStore(self.root / "data", detector="ffmpeg")
        reopened = self.store.read(project["id"])
        self.assertEqual(reopened, project)
        self.assert_contiguous(reopened)
        with self.assertRaises(backend.APIError) as overwritten:
            self.store.analyze(project["id"], {})
        self.assertEqual(overwritten.exception.status, 409)

    def test_concurrent_different_field_updates_and_exports(self):
        project = self.upload()
        shot_id = project["shots"][0]["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            actions = [pool.submit(self.store.annotate, project["id"], shot_id, patch)
                       for patch in [{"note": "=HYPERLINK(\"example\")\n真实笔记"}, {"tag": "主题"}]]
            for action in actions:
                action.result()
        project = self.store.read(project["id"])
        self.assertEqual(project["shots"][0]["tag"], "主题")
        self.assertIn("真实笔记", project["shots"][0]["note"])
        data, _ = self.store.export(project["id"], "json")
        self.assertEqual(json.loads(data), project)
        data, _ = self.store.export(project["id"], "csv")
        self.assertIn("'=HYPERLINK", data.decode("utf-8-sig"))
        self.assertIn("真实笔记", self.store.export(project["id"], "md")[0].decode())

    def test_invalid_upload_cleans_partial_and_missing_model_is_explicit(self):
        for content, size in [(b"not video", 9), (b"x", 50)]:
            with self.assertRaises(backend.APIError):
                self.store.import_stream("坏视频.mp4", io.BytesIO(content), size)
        self.assertEqual([p for p in (self.root / "data").iterdir() if not p.name.startswith(".")], [])
        project = self.upload()
        self.store.detector = "transnetv2"
        self.store.detector_python = self.root / "missing-python"
        with self.assertRaises(backend.APIError) as missing:
            self.store.analyze(project["id"], {})
        self.assertEqual(missing.exception.status, 503)
        self.assertIn("TransNetV2", missing.exception.message)
        self.assertEqual(self.store.read(project["id"])["status"], "ready")

    def test_reanalysis_refuses_to_discard_a_manual_shot_title(self):
        project = self.upload()
        shot = project["shots"][0]
        self.store.annotate(project["id"], shot["id"], {"title": "手工命名的重要镜头"})
        with self.assertRaises(backend.APIError) as conflict:
            self.store.analyze(project["id"], {})
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(self.store.read(project["id"])["shots"][0]["title"], "手工命名的重要镜头")

    def test_capture_collect_and_previews_do_not_hold_the_project_lock(self):
        project = self.upload()
        project_id, shot_id = project["id"], project["shots"][0]["id"]

        def exercise(operation, note):
            started, release = threading.Event(), threading.Event()

            def delayed_run(command, **kwargs):
                output = Path(command[-1])
                if "%03d" in output.name:
                    output = output.parent / "frame-001.jpg"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"generated")
                started.set()
                release.wait(3)
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(self.store, "run", side_effect=delayed_run):
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    work = pool.submit(operation)
                    self.assertTrue(started.wait(1), "generation did not start")
                    edit = pool.submit(self.store.annotate, project_id, shot_id, {"note": note})
                    edited = edit.result(timeout=0.7)
                    self.assertEqual(edited["shots"][0]["note"], note)
                    release.set()
                    work.result(timeout=3)

        exercise(lambda: self.store.capture(project_id, {"time": 0.2}), "capture remained editable")
        exercise(lambda: self.store.collect(project_id, {"shot_id": shot_id, "tags": ["收藏"]}), "collect remained editable")
        exercise(lambda: self.store.previews(project_id), "previews remained editable")
        latest = self.store.read(project_id)
        self.assertEqual(latest["shots"][0]["note"], "previews remained editable")
        self.assertTrue(any(item.get("shot_id") == shot_id for item in latest["captures"]))

    def test_errors_do_not_damage_existing_shots_and_restart_recovers(self):
        project = self.upload()
        for threshold in [0, 3, -1, float("nan"), "invalid"]:
            with self.assertRaises(backend.APIError):
                self.store.analyze(project["id"], {"threshold": threshold})
        self.assertEqual(self.store.read(project["id"]), project)
        project["status"] = "processing"
        self.store.write(project)
        self.store.close()
        self.store = backend.ProjectStore(self.root / "data", detector="ffmpeg")
        reopened = self.store.read(project["id"])
        self.assertEqual(reopened["status"], "error")
        self.assertEqual(reopened["shots"], project["shots"])

    def test_longer_audio_does_not_extend_video_shots(self):
        data = self.long_audio.read_bytes()
        project = self.store.import_stream("音轨更长.mp4", io.BytesIO(data), len(data))
        self.assertEqual(project["duration"], 3)
        self.assertEqual(project["shots"][0]["end"], 3)
        self.assertTrue(project["has_audio"])

    def test_real_capture_waveform_and_legacy_audio_persistence(self):
        source = self.long_audio.read_bytes()
        project = self.store.import_stream("媒体操作.mp4", io.BytesIO(source), len(source))
        project = self.store.capture(project["id"], {"time": 1.25})
        project = self.store.capture(project["id"], {"time": 2.25})
        frames = [self.store.directory(project["id"]) / "captures" / f"{item['id']}.jpg" for item in project["captures"]]
        self.assertTrue(all(frame.read_bytes().startswith(b"\xff\xd8") for frame in frames))
        self.assertNotEqual(frames[0].read_bytes(), frames[1].read_bytes())
        self.assertEqual([item["time"] for item in project["captures"]], [1.25, 2.25])
        waveform = self.store.waveform(project["id"])
        self.assertEqual(len(waveform["samples"]), 1000)
        self.assertEqual(waveform["duration"], 3)
        self.assertTrue(all(0 <= value <= 1 for value in waveform["samples"]))
        self.assertGreater(max(waveform["samples"]), 0.05)
        self.assertLess(max(waveform["samples"]), 0.5)
        self.assertEqual(self.store.waveform(project["id"]), waveform)
        project, legacy_clip, legacy_payload = self.seed_legacy_audio_clip(project, tags=["历史资料"])
        self.store.close()
        self.store = backend.ProjectStore(self.root / "data", detector="ffmpeg")
        reopened = self.store.read(project["id"])
        self.assertEqual(reopened, project)
        self.assertEqual(reopened["audio_clips"], [legacy_clip])
        legacy_file = self.store.directory(project["id"]) / "audio" / f"{legacy_clip['id']}.m4a"
        self.assertEqual(legacy_file.read_bytes(), legacy_payload)
        self.assertEqual((self.store.directory(project["id"]) / "source.mp4").read_bytes(), source)

    def test_invalid_captures_and_silent_waveform_do_not_create_assets(self):
        project = self.upload()
        for position in [-1, project["duration"], float("nan")]:
            with self.assertRaises(backend.APIError):
                self.store.capture(project["id"], {"time": position})
        with self.assertRaises(backend.APIError):
            self.store.waveform(project["id"])
        self.assertEqual(self.store.read(project["id"])["captures"], [])
        self.assertEqual(self.store.read(project["id"])["audio_clips"], [])

    def test_annotation_revision_ignores_background_progress_but_rejects_other_note(self):
        project = self.upload()
        shot = project["shots"][0]
        self.store.transcript_progress(project["id"], 0.25, "后台进度")
        saved = self.store.annotate(project["id"], shot["id"], {"note": "不会被后台进度阻断",
            "expected_revision": project["revision"], "expected_annotation_revision": 0})
        self.assertEqual(saved["shots"][0]["annotation_revision"], 1)
        with self.assertRaises(backend.APIError) as stale:
            self.store.annotate(project["id"], shot["id"], {"note": "旧草稿", "expected_annotation_revision": 0})
        self.assertEqual(stale.exception.status, 409)
        self.assertEqual(self.store.read(project["id"])["shots"][0]["note"], "不会被后台进度阻断")

    def test_transcription_lifecycle_exports_and_restart_recovery(self):
        source = self.long_audio.read_bytes()
        project = self.store.import_stream("字幕测试.mp4", io.BytesIO(source), len(source))
        self.store.analyze(project["id"], {"threshold": 0.22, "min_duration": 0.5})
        self.store.jobs[project["id"]].join(timeout=30)
        project = self.store.read(project["id"])
        self.assertEqual(len(project["shots"]), 3)
        adapter = self.root / "test-asr-adapter.py"
        adapter.write_text('import json,sys,time\nprint(json.dumps({"progress":0.5,"message":"测试协议进度"}),file=sys.stderr,flush=True)\ntime.sleep(0.1)\nprint(json.dumps({"segments":[{"start":0.5,"end":2.0,"text":"跨两个镜头 <& 字幕"},{"start":2.1,"end":2.9,"text":"第二句"}],"engine":"test-protocol-only","language":"zh"}))\n', encoding="utf-8")
        self.store.asr_python, self.store.asr_script = Path(sys.executable), adapter
        started = self.store.transcribe(project["id"], {})
        self.assertEqual(started["status"], "ready")
        self.assertEqual(started["transcript"]["status"], "processing")
        self.store.jobs["transcript:" + project["id"]].join(timeout=5)
        result = self.store.read(project["id"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["shots"], project["shots"])
        self.assertEqual(result["transcript"]["status"], "ready")
        self.assertEqual(result["transcript"]["engine"], "test-protocol-only")
        srt, _ = self.store.export(project["id"], "srt")
        self.assertIn("00:00:00,500 --> 00:00:02,000", srt.decode())
        self.assertIn("第二句", self.store.export(project["id"], "txt")[0].decode())
        docx, mime = self.store.export(project["id"], "docx")
        self.assertIn("wordprocessingml", mime)
        with zipfile.ZipFile(io.BytesIO(docx)) as document:
            image_names = [name for name in document.namelist() if name.startswith("word/media/")]
            self.assertEqual(len(image_names), 3)
            for name in image_names:
                self.assertTrue(document.read(name).startswith(b"\xff\xd8"))
            for name in document.namelist():
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(document.read(name))
            xml = document.read("word/document.xml").decode()
            self.assertEqual(xml.count("跨两个镜头 &lt;&amp; 字幕"), 2)
            self.assertEqual(xml.count("第二句"), 1)
        result["transcript"]["status"] = "processing"
        self.store.write(result)
        self.store.close()
        self.store = backend.ProjectStore(self.root / "data", detector="ffmpeg")
        reopened = self.store.read(project["id"])
        self.assertEqual(reopened["transcript"]["status"], "error")
        self.assertEqual(reopened["transcript"]["segments"], result["transcript"]["segments"])
        self.assertEqual(reopened["shots"], result["shots"])

    def test_transcription_failure_retains_previous_result_and_can_retry(self):
        source = self.long_audio.read_bytes()
        project = self.store.import_stream("字幕失败重试.mp4", io.BytesIO(source), len(source))
        project["transcript"] = {"status": "ready", "progress": 1, "message": "", "engine": "prior",
                                 "segments": [{"start": 0, "end": 1, "text": "已保存字幕"}]}
        self.store.write(project)
        adapter = self.root / "failing-asr-adapter.py"
        adapter.write_text('import json,sys\nprint(json.dumps({"error":True,"message":"测试模型错误"}),file=sys.stderr)\nsys.exit(1)\n', encoding="utf-8")
        self.store.asr_python, self.store.asr_script = Path(sys.executable), adapter
        self.store.transcribe(project["id"], {})
        self.store.jobs["transcript:" + project["id"]].join(timeout=5)
        result = self.store.read(project["id"])
        self.assertEqual(result["transcript"]["status"], "error")
        self.assertIn("测试模型错误", result["transcript"]["message"])
        self.assertEqual(result["transcript"]["segments"], project["transcript"]["segments"])
        adapter.write_text('import json\nprint(json.dumps({"segments":[],"engine":"test-protocol-only","language":"zh"}))\n', encoding="utf-8")
        self.store.transcribe(project["id"], {})
        self.store.jobs["transcript:" + project["id"]].join(timeout=5)
        self.assertEqual(self.store.read(project["id"])["transcript"]["status"], "ready")

    def test_service_close_stops_its_owned_process(self):
        process = self.store.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        self.assertIsNone(process.poll())
        self.store.close()
        self.assertIsNotNone(process.poll())
        with self.assertRaises(backend.APIError):
            self.store.spawn([sys.executable, "-c", "print('must not run')"])

    def test_multiple_projects_queue_detector_without_parallel_models(self):
        first, second = self.upload(), self.upload()
        entered = threading.Event()
        release = threading.Event()
        counter_lock = threading.Lock()
        active, maximum = 0, 0

        def slow_detector(project, threshold):
            nonlocal active, maximum
            with counter_lock:
                active += 1
                maximum = max(maximum, active)
            entered.set()
            release.wait(timeout=5)
            with counter_lock:
                active -= 1
            return {"method": "test-queue-only", "cuts": [1, 2]}

        self.store.detect_scene_cuts = slow_detector
        self.store.analyze(first["id"], {})
        self.assertTrue(entered.wait(timeout=2))
        self.store.analyze(second["id"], {})
        deadline = time.monotonic() + 2
        queued = self.store.read(second["id"])
        while "等待" not in queued["message"] and time.monotonic() < deadline:
            time.sleep(0.01)
            queued = self.store.read(second["id"])
        self.assertEqual(queued["status"], "processing")
        self.assertIn("等待", queued["message"])
        release.set()
        for thread in self.store.jobs.values():
            thread.join(timeout=10)
        self.assertEqual(maximum, 1)
        for project in [first, second]:
            self.assertEqual(self.store.read(project["id"])["status"], "ready")

    def test_annotations_and_asset_versions_survive_other_background_writes(self):
        project = self.upload()
        result = self.store.annotation(project['id'], {'time':1.2,'kind':'frame','text':'第一条笔记'})
        note=result['annotations'][0]
        self.store.progress(project['id'],.4,'background')
        edited=self.store.annotation(project['id'], {'id':note['id'],'text':'修改笔记','expected_revision':note['revision']})
        self.assertEqual(edited['annotations'][0]['text'],'修改笔记')
        with self.assertRaises(backend.APIError):
            self.store.annotation(project['id'], {'id':note['id'],'text':'过期写入','expected_revision':note['revision']})
        tagged=self.store.metadata(project['id'], {'tags':['人物','人物','片头'],'source':{'platform':'本地','author':'测试'},'expected_revision':0})
        self.assertEqual(tagged['tags'],['人物','片头'])
        with self.assertRaises(backend.APIError):
            self.store.metadata(project['id'],{'source':{'url':'javascript:alert(1)'},'expected_revision':1})
        self.assertEqual(self.store.read(project['id'])['annotations'],edited['annotations'])

    def test_collect_is_idempotent_and_tag_removal_does_not_remove_image(self):
        project=self.upload(); shot=project['shots'][0]
        first=self.store.collect(project['id'],{'shot_id':shot['id'],'tags':['标题']})
        captured=first['captures'][0]
        again=self.store.collect(project['id'],{'shot_id':shot['id']})
        self.assertEqual(len(again['captures']),1)
        item=again['captures'][0]
        result=self.store.asset(project['id'],{'kind':'captures','id':item['id'],'tags':[],'expected_revision':item['asset_revision']})
        self.assertFalse(result['captures'][0].get('deleted',False))
        self.assertTrue((self.store.directory(project['id'])/'captures'/f"{item['id']}.jpg").is_file())
        removed=self.store.asset(project['id'],{'kind':'captures','id':item['id'],'deleted':True,'expected_revision':result['captures'][0]['asset_revision']})
        self.assertTrue(removed['captures'][0]['deleted'])
        restored=self.store.collect(project['id'],{'shot_id':shot['id']})
        self.assertFalse(restored['captures'][0]['deleted'])
        self.assertEqual(restored['shots'],project['shots'])

    def test_preview_cache_exports_and_cross_library_tag_rename(self):
        content=self.long_audio.read_bytes()
        project=self.store.import_stream('有声.mp4',io.BytesIO(content),len(content))
        project,clip,_=self.seed_legacy_audio_clip(project)
        self.store.asset(project['id'],{'kind':'audio_clips','id':clip['id'],'tags':['旧标签'],'expected_revision':0})
        preview=self.store.previews(project['id'])
        self.assertGreater(len(preview['frames']),0)
        self.assertEqual(self.store.previews(project['id']),preview)
        project=self.store.collect(project['id'],{'shot_id':project['shots'][0]['id'],'tags':['旧标签']})
        self.store.rename_tag({'domain':'image','old':'旧标签','new':'新标签'})
        self.assertEqual(self.store.read(project['id'])['captures'][0]['tags'],['新标签'])
        self.assertEqual(self.store.read(project['id'])['audio_clips'][0]['tags'],['旧标签'])
        exported=self.store.save_export(project['id'],{'format':'docx'})
        asset=exported['exports'][0]
        self.assertTrue((self.store.directory(project['id'])/'exports'/f"{asset['id']}.docx").is_file())
        self.assertEqual(self.store.read(project['id'])['exports'],exported['exports'])
        self.store.metadata(project['id'],{'removed':True,'expected_revision':0})
        self.assertFalse(self.store.list())
        self.assertTrue((self.store.directory(project['id'])/'source.mp4').is_file())

    def test_music_partial_failure_retry_dedup_preserves_tags(self):
        project=self.upload()
        original_spawn=self.store.spawn
        fixture=self.root/'music-protocol-fixture.py'
        def run_events(events):
            fixture.write_text('import json\nfor event in '+repr(events)+': print(json.dumps(event), flush=True)\n')
            with patch.object(self.store,'spawn',lambda args,**kwargs: original_spawn([sys.executable,str(fixture)],**kwargs)):
                self.store._music_job(project['id'],sys.executable)
            return self.store.read(project['id'])['music']
        track={'key':'protocol-test-song','title':'协议测试歌曲','artist':'测试','time':1,'positions':[1]}
        music=run_events([{'type':'found','track':track},{'type':'error','message':'测试网络中断'}])
        self.assertEqual(music['status'],'error')
        self.assertEqual(len(music['tracks']),1)
        item=music['tracks'][0]
        self.store.asset(project['id'],{'kind':'music','id':item['id'],'tags':['用户标签'],'expected_revision':0})
        music=run_events([{'type':'found','track':dict(track,time=2,positions=[2])},{'type':'done'}])
        self.assertEqual(music['status'],'ready')
        self.assertEqual(len(music['tracks']),1)
        self.assertEqual(music['tracks'][0]['positions'],[1,2])
        self.assertEqual(music['tracks'][0]['tags'],['用户标签'])

    def test_local_music_real_audio_import_and_tags(self):
        content=self.long_audio.read_bytes()
        result=self.store.import_music('本地音乐.m4a',io.BytesIO(content),len(content))
        item=result['tracks'][0]
        self.assertGreater(item['duration'],0)
        self.assertTrue((self.store.data_dir/'music'/f"{item['id']}.m4a").is_file())
        edited=self.store.edit_local_music({'id':item['id'],'tags':['音乐'],'expected_revision':0})
        self.assertEqual(edited['tracks'][0]['tags'],['音乐'])
        with self.assertRaises(backend.APIError):
            self.store.edit_local_music({'id':item['id'],'tags':['旧内容'],'expected_revision':0})
        self.store.rename_tag({'domain':'music','old':'音乐','new':'配乐'})
        self.assertEqual(self.store.local_music()['tracks'][0]['tags'],['配乐'])

    def test_compatible_mov_and_real_incompatible_video_conversion(self):
        project=self.store.import_stream('camera.mov',io.BytesIO(self.video_bytes),len(self.video_bytes))
        self.assertFalse(project['converted'])
        webm=self.root/'sample.webm'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(self.video),'-c:v','libvpx-vp9','-threads','1',str(webm)],check=True,timeout=30)
        data=webm.read_bytes()
        converted=self.store.import_stream('sample.webm',io.BytesIO(data),len(data))
        self.assertTrue(converted['converted'])
        self.assertEqual(converted['codec'],'h264')
        self.assertEqual((self.store.directory(converted['id'])/'original-media').read_bytes(),data)

    def test_http_upload_range_export_and_origin_protection(self):
        public = self.root / "public"
        public.mkdir()
        (public / "index.html").write_text("本地拉片", encoding="utf-8")
        server = backend.WorkbenchServer(("127.0.0.1", 0), self.store, public)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            result = response.status, dict(response.headers), response.read()
            connection.close()
            return result

        try:
            status, headers, data = request("GET", "/")
            self.assertEqual((status, data), (200, "本地拉片".encode()))
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertEqual(headers["Cross-Origin-Opener-Policy"], "same-origin")
            self.assertEqual(headers["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")
            self.assertIn("base-uri 'none'", headers["Content-Security-Policy"])
            self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            status, _, data = request("GET", "/api/system-usage")
            self.assertEqual(status, 200)
            usage = json.loads(data)
            self.assertTrue(usage["available"], usage)
            self.assertGreater(usage["memory_bytes"], 0)
            self.assertGreater(usage["total_memory_bytes"], usage["memory_bytes"])
            self.assertGreaterEqual(usage["memory_percent"], 0)
            self.assertGreaterEqual(usage["process_count"], 1)
            self.assertEqual(usage["measurement"], "rss_sum")
            self.assertEqual(request("HEAD", "/api/system-usage")[:1], (200,))
            status, _, data = request("POST", "/api/projects?name=http-test.mp4", self.video_bytes,
                                      {"Content-Type": "video/mp4", "Origin": f"http://127.0.0.1:{port}"})
            self.assertEqual(status, 201, data)
            project = json.loads(data)
            record = self.store.directory(project["id"]) / "project.json"
            before_removed_audio_post = record.read_bytes()
            status, _, data = request(
                "POST", f"/api/projects/{project['id']}/audio",
                json.dumps({"start": 0.2, "end": 1.2}),
                {"Content-Type": "application/json"},
            )
            self.assertEqual(status, 405, data)
            self.assertEqual(record.read_bytes(), before_removed_audio_post)
            self.assertEqual(self.store.read(project["id"])["audio_clips"], [])
            self.assertFalse((self.store.directory(project["id"]) / "audio").exists())
            _, legacy_clip, legacy_payload = self.seed_legacy_audio_clip(project)
            status, headers, data = request("GET", legacy_clip["url"])
            self.assertEqual((status, data), (200, legacy_payload))
            self.assertTrue(headers["Content-Type"].startswith("audio/"))
            for removed_route in ("split", "merge"):
                self.assertEqual(request("POST", f"/api/projects/{project['id']}/{removed_route}", "{}", {"Content-Type": "application/json"})[0], 405)
            status, _, data = request("POST", f"/api/projects/{project['id']}/capture", json.dumps({"time": 1.2}),
                                     {"Content-Type": "application/json"})
            self.assertEqual(status, 200, data)
            captured = json.loads(data)["captures"][0]
            status, headers, data = request("GET", captured["url"])
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "image/jpeg")
            self.assertTrue(data.startswith(b"\xff\xd8"))
            status, headers, data = request("GET", project["video_url"], headers={"Range": "bytes=0-31"})
            self.assertEqual(status, 206)
            self.assertEqual(data, self.video_bytes[:32])
            self.assertEqual(headers["Content-Range"], f"bytes 0-31/{len(self.video_bytes)}")
            status, _, data = request("GET", project["video_url"], headers={"Range": "bytes=-15"})
            self.assertEqual((status, data), (206, self.video_bytes[-15:]))
            self.assertEqual(request("HEAD", project["video_url"])[2], b"")
            self.assertEqual(request("GET", project["video_url"], headers={"Range": "bytes=999999999-"})[0], 416)
            self.assertEqual(request("GET", "/media/../../server.py")[0], 404)
            self.assertEqual(request("GET", "/%2e%2e/server.py")[0], 404)
            self.assertEqual(request("GET", "/api/projects/not-valid")[0], 404)
            status, _, data = request("PATCH", f"/api/projects/{project['id']}/shots/{project['shots'][0]['id']}",
                                     json.dumps({"note": "从 HTTP 保存"}), {"Content-Type": "application/json"})
            self.assertEqual(status, 200, data)
            status, headers, data = request("GET", f"/api/projects/{project['id']}/export?format=csv")
            self.assertEqual(status, 200)
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertIn("从 HTTP 保存", data.decode("utf-8-sig"))
            self.assertEqual(request("POST", "/api/projects?name=evil.mp4", b"", {"Origin": "https://evil.example"})[0], 403)
            self.assertEqual(request("POST", "/api/projects?name=evil.mp4", b"", {"Sec-Fetch-Site": "cross-site"})[0], 403)
            self.assertEqual(request("GET", "/", headers={"Host": "attacker.example"})[0], 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_http_admission_is_nonblocking_and_shutdown_waits_for_active_writer(self):
        project = self.upload()
        started, release = threading.Event(), threading.Event()
        public = self.root / "shutdown-public"
        public.mkdir()
        (public / "index.html").write_text("local", encoding="utf-8")
        http_server = backend.WorkbenchServer(("127.0.0.1", 0), self.store, public)
        serve_thread = threading.Thread(target=http_server.serve_forever)
        serve_thread.start()
        port = http_server.server_address[1]

        def request(method, path, data=None):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            body = json.dumps(data).encode() if data is not None else None
            headers = {"Content-Type": "application/json"} if data is not None else {}
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            result = response.status, response.read()
            connection.close()
            return result

        def slow_capture(project_id, body):
            started.set()
            release.wait(5)
            return self.store.read(project_id)

        external = self.root / "shutdown-external"
        external.mkdir()
        with patch.object(self.store, "capture", side_effect=slow_capture):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                writer = pool.submit(request, "POST", f"/api/projects/{project['id']}/capture", {"time": 0.2})
                self.assertTrue(started.wait(1))
                reader = pool.submit(request, "GET", f"/api/projects/{project['id']}")
                self.assertEqual(reader.result(timeout=0.7)[0], 200)
                blocked = request("POST", "/api/storage/tasks", {
                    "action": "export", "destination": str(external), "project_id": project["id"],
                })
                self.assertEqual(blocked[0], 409)

                http_server.shutdown()
                serve_thread.join(timeout=3)
                # Even an early close attempt must retain the inter-process lock.
                self.store.close()
                with self.assertRaises(backend.LibraryInUseError):
                    backend.ProjectStore(self.store.data_dir, detector="ffmpeg")
                closing = pool.submit(http_server.server_close)
                with self.assertRaises(concurrent.futures.TimeoutError):
                    closing.result(timeout=0.2)
                release.set()
                self.assertEqual(writer.result(timeout=3)[0], 200)
                closing.result(timeout=3)
        self.store.close()
        reopened = backend.ProjectStore(self.root / "data", detector="ffmpeg")
        reopened.close()

    def test_shutdown_wakes_idle_http_keepalive(self):
        public = self.root / "keepalive-public"
        public.mkdir()
        (public / "index.html").write_text("local", encoding="utf-8")
        http_server = backend.WorkbenchServer(("127.0.0.1", 0), self.store, public)
        serve_thread = threading.Thread(target=http_server.serve_forever)
        serve_thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", http_server.server_address[1], timeout=3)
        try:
            connection.request("GET", "/api/projects")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertIsNotNone(connection.sock, "the test needs a live HTTP/1.1 keep-alive socket")

            http_server.shutdown()
            serve_thread.join(timeout=3)
            started = time.monotonic()
            http_server.server_close()
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            connection.close()
            if serve_thread.is_alive():
                http_server.shutdown()
                serve_thread.join(timeout=3)
            http_server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
