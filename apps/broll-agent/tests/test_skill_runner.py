import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_store import AssetStore
from skill_runner import SkillRunner, file_hash

SKILL_ROOT = Path.home() / ".codex/skills"
HAS_TOOLS = all(shutil.which(name) for name in ("ffmpeg", "ffprobe", "node")) and (SKILL_ROOT / "ljq-broll-replica/.venv/bin/python").exists()


@unittest.skipUnless(HAS_TOOLS, "Installed replica Skill, FFmpeg and Node are required")
class SkillRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.video = Path(cls.shared.name) / "source.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = AssetStore(self.root / "assets")
        blob = self.assets.put_blob(self.video)
        self.source = self.assets.create_asset("source", "Real encoded test clip", blob_hash=blob["sha256"])
        self.study = self.assets.create_asset("study", "Selected 0.1–0.5 seconds", {"source": {"asset_id": self.source["id"], "revision": 1},
            "source_sha256": blob["sha256"], "start": 0.1, "end": 0.5, "note": "test fixture"})
        self.runner = SkillRunner(self.assets, self.root / "work")

    def prepared(self):
        replica = self.runner.create(self.study)
        result = self.runner.advance(replica["id"], "preflight")
        self.assertEqual(result["metadata"]["stages"]["preflight"], "passed")
        return result

    def last_run(self, replica):
        event = replica["metadata"]["skill_bridge"]["events"][-1]
        return json.loads(self.assets.blob_path(event["evidence_hash"]).read_text())

    def test_create_adopts_existing_replica_and_preserves_fixed_study_source(self):
        replica = self.assets.create_asset("replica", "Existing queued replica", {"study": {"asset_id": self.study["id"], "revision": 1}, "status": "needs_work"})
        study = self.assets.revise_asset(self.study["id"], 1, {"metadata": {**self.study["metadata"], "replica": {"asset_id": replica["id"], "revision": 1}}})
        adopted = self.runner.create(study)
        self.assertEqual(adopted["id"], replica["id"])
        self.assertEqual(len(self.assets.list_assets(kind="replica")), 1)
        self.assertEqual(len(adopted["metadata"]["skill_bridge"]["skills"]), 4)
        self.assertEqual(self.runner.create(study)["revision"], adopted["revision"])

    def test_actual_skill_preflight_and_validator_preserve_source_and_save_tools(self):
        before = file_hash(self.video)
        result = self.prepared()
        self.assertEqual(file_hash(self.video), before)
        case = Path(result["metadata"]["skill_bridge"]["case_directory"])
        state = json.loads((case / "case.json").read_text())
        self.assertEqual(state["source"]["decodedFrames"], 12)
        self.assertEqual(state["scope"]["startSeconds"], 0.1)
        self.assertEqual(state["scope"]["endSeconds"], 0.5)
        run = self.last_run(result)
        self.assertEqual([tool["tool"] for tool in run["tools"]], ["inspect-clip", "validate-case"])
        self.assertTrue(all(tool["exit_code"] == 0 for tool in run["tools"]))
        self.assertEqual(result["metadata"]["execution_trust"], "untrusted_candidate")
        self.assertEqual(self.assets.list_assets(kind="style"), [])
        with zipfile.ZipFile(self.assets.blob_path(result["blob_hash"])) as archive:
            self.assertIn("case.json", archive.namelist())
            self.assertIn("evidence/contact-sheet.png", archive.namelist())

    def test_resume_restores_shared_snapshot_after_workspace_loss(self):
        original = self.prepared()
        shutil.rmtree(self.root / "work")
        runner = SkillRunner(self.assets, self.root / "new-product-work")
        restored = runner.advance(original["id"], "validate")
        self.assertEqual(restored["metadata"]["stages"]["preflight"], "passed")
        self.assertEqual(self.last_run(restored)["status"], "needs_review")
        self.assertEqual([t["tool"] for t in self.last_run(restored)["tools"]], ["validate-case"])

    def test_wrong_stage_and_model_failure_remain_retryable(self):
        original = self.prepared()
        invalid = self.runner.advance(original["id"], "motion")
        self.assertIn("first unfinished", self.last_run(invalid)["error"])
        failure = {"exit_code": 1, "timed_out": False, "stderr": "provider unavailable", "result": None}
        with patch.object(self.runner, "_generate", return_value=failure) as generator:
            failed = self.runner.advance(original["id"], "layout")
            retried = self.runner.advance(original["id"], "layout")
        self.assertEqual(generator.call_count, 2)
        self.assertEqual(failed["metadata"]["stages"]["layout"], "needs_review")
        self.assertEqual(self.last_run(retried)["status"], "failed")
        self.assertEqual(retried["metadata"]["status"], "needs_review")

    def test_auto_model_can_wait_without_running_generation(self):
        original = self.prepared()
        decision = {"exit_code": 0, "timed_out": False, "result": {"action": "wait", "reason": "缺少可确认字体证据", "evidence_paths": ["evidence/source.json"]}}
        with patch.object(self.runner, "_choose_action", return_value=decision) as chooser, patch.object(self.runner, "_generate") as generator:
            result = self.runner.advance(original["id"])
        chooser.assert_called_once()
        generator.assert_not_called()
        self.assertEqual(self.last_run(result)["decision"]["reason"], "缺少可确认字体证据")

    def test_model_cannot_promote_visual_stages_or_mutate_protected_source(self):
        original = self.prepared()
        case = Path(original["metadata"]["skill_bridge"]["case_directory"])
        before = json.loads((case / "case.json").read_text())
        digest = file_hash(case / before["files"]["source"])
        def malicious_generator(case, stage):
            altered = copy.deepcopy(before)
            altered["stages"] = {name: "passed" for name in altered["stages"]}
            altered["status"] = "passed"
            altered["scope"]["endSeconds"] = 9
            (case / "case.json").write_text(json.dumps(altered))
            (case / before["files"]["source"]).write_bytes(b"fake source")
            return {"exit_code": 0, "timed_out": False, "result": {"summary": "untrusted model claims success"}}
        with patch.object(self.runner, "_generate", side_effect=malicious_generator):
            result = self.runner.advance(original["id"], "layout")
        after = json.loads((case / "case.json").read_text())
        self.assertEqual(file_hash(case / before["files"]["source"]), digest)
        self.assertEqual(after["scope"], before["scope"])
        self.assertEqual(after["stages"]["layout"], "needs_review")
        self.assertEqual(after["stages"]["qa"], "pending")
        self.assertIn("protected", self.last_run(result)["error"].lower())
        self.assertFalse(result["metadata"]["skill_bridge"]["trusted_renderer"])

    def test_scope_mismatch_rejected_without_reinterpreting_study(self):
        altered = copy.deepcopy(self.study)
        altered["metadata"]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.runner.create(altered)
        with self.assertRaises(ValueError):
            self.runner.advance("../../outside")

    def test_interrupted_preflight_is_archived_before_clean_retry(self):
        replica = self.runner.create(self.study)
        workspace = self.runner._workspace(replica["id"])
        evidence = workspace / "case/evidence"
        evidence.mkdir(parents=True)
        (evidence / "keyframe-001.png").write_bytes(b"interrupted partial output")
        restored = self.runner.advance(replica["id"], "preflight")
        run = self.last_run(restored)
        self.assertEqual(restored["metadata"]["stages"]["preflight"], "passed")
        retained = workspace / run["archived_incomplete_case"] / "evidence/keyframe-001.png"
        self.assertEqual(retained.read_bytes(), b"interrupted partial output")

    def test_generated_symlink_cannot_redirect_host_evidence_writes(self):
        original = self.prepared()
        outside = self.root / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("unchanged")
        def bad_links(case, stage):
            shutil.rmtree(case / ".agent")
            (case / ".agent").symlink_to(outside, target_is_directory=True)
            return {"exit_code": 0, "timed_out": False, "result": {"summary": "candidate"}}
        with patch.object(self.runner, "_generate", side_effect=bad_links):
            result = self.runner.advance(original["id"], "layout")
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["keep.txt"])
        self.assertEqual(sentinel.read_text(), "unchanged")
        self.assertIn(".agent", self.last_run(result)["removed_candidate_symlinks"])
        self.assertEqual(result["metadata"]["stages"]["layout"], "needs_review")

    def test_process_timeout_stops_descendants_and_discards_reasoning_events(self):
        process_script = self.root / "slow.py"
        process_script.write_text("import subprocess,time\np=subprocess.Popen(['sleep','30'])\nprint(p.pid,flush=True)\ntime.sleep(30)\n")
        outcome = self.runner._run_command([sys.executable, process_script], self.root, timeout=0.2)
        self.assertTrue(outcome["timed_out"])
        self.assertLess(outcome["duration_seconds"], 5)
        pid = outcome["stdout"].strip()
        inspected = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True)
        self.assertTrue(not inspected.stdout.strip() or inspected.stdout.strip().startswith("Z"))
        event_script = self.root / "events.py"
        event_script.write_text("import json\nprint(json.dumps({'type':'item.completed','item':{'type':'reasoning','text':'secret-thought'}}))\nprint(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'validate','status':'completed'}}))\n")
        result = self.runner._run_command([sys.executable, event_script], self.root, model=True)
        self.assertNotIn("secret-thought", json.dumps(result))
        self.assertEqual(len(result["events"]), 1)

    def test_codex_command_enforces_scoped_execution_and_explicit_skills(self):
        original = self.prepared()
        case = Path(original["metadata"]["skill_bridge"]["case_directory"])
        self.runner.codex_binary = "codex"
        (case / ".git").mkdir()
        captured = {}
        def run(command, cwd, **kwargs):
            captured.update(command=command, cwd=cwd, **kwargs)
            result_path = Path(command[command.index("--output-last-message") + 1])
            result_path.write_text(json.dumps({"summary": "candidate only", "limitations": "not rendered", "next_action": "review"}))
            return {"exit_code": 0, "timed_out": False, "events": []}
        with patch.object(self.runner, "_run_command", side_effect=run):
            self.runner._generate(case, "layout")
        self.assertIn("--ignore-user-config", captured["command"])
        self.assertIn("--ephemeral", captured["command"])
        self.assertEqual(captured["command"][captured["command"].index("--sandbox") + 1], "workspace-write")
        self.assertEqual(captured["cwd"], case)
        result_path = Path(captured["command"][captured["command"].index("--output-last-message") + 1])
        self.assertFalse(result_path.is_relative_to(case))
        for skill in ("ljq-broll-replica", "ljq-broll-layout-structure", "ljq-broll-motion-forensics", "ljq-broll-fidelity-qa"):
            self.assertIn(skill + "/SKILL.md", captured["input_text"])


if __name__ == "__main__":
    unittest.main()
