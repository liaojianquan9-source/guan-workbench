"""Reference studies and honest publication of audited reusable case adapters."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import threading
import uuid
import zipfile

from renderer import (ADAPTERS, FPS, REPO, RUNTIME, AUDITED_MANIFEST_SHA256,
    adapter_signature, probe, run_command, sha256, verify_source)

IMPORT_GATE = threading.RLock()

CASE_INDEX = {
    "kimi-opening": {"name": "KIMI 开头：月球标题与数字参数页", "case_path": "workspace/cases/kimi-k3-000-011-test",
        "styles": ["kimi-moon-v1", "kimi-number-v1"], "source_range": [0, 11]},
    "problem-background": {"name": "问题背景页：可换文字与背景图片", "case_path": "cases/my-broll-case-motion",
        "styles": ["problem-photo-v1"], "source_range": [20.133333333, 34.4]},
}
STYLE_DESCRIPTIONS = {
    "kimi-moon-v1": {"name": "月球质感主标题", "purpose": "单一主题、新产品或抽象概念的短标题揭示",
        "avoid": ["需要提供照片证据或展示真实操作的论点", "超过两个短标题的复杂信息", "需要看清人物表情的段落"],
        "labels": {"title": "主标题", "subtitle": "副标题", "texture_text": "纹理背景字", "image": "圆形图片"},
        "baseline": {"title": "KIMI", "subtitle": "K3", "texture_text": "月之暗面"},
        "replacement": {"title": "B-ROLL", "subtitle": "复用", "texture_text": "新项目"}},
    "kimi-number-v1": {"name": "重点数字参数页", "purpose": "突出一项已有依据的数量、规模或指标",
        "avoid": ["没有可靠数字依据的表达", "长表格或多指标比较", "纯情绪或个人表达"],
        "labels": {"number": "数字", "unit": "单位", "label": "指标", "annotation": "依据说明"},
        "baseline": {"number": "28000", "unit": "亿", "label": "个参数", "annotation": "模型权重数量"},
        "replacement": {"number": "42", "unit": "个", "label": "可编辑元素", "annotation": "本案例的元素合同记录"}},
    "problem-photo-v1": {"name": "照片背景问题标题", "purpose": "用真实图片补充环境或案例，配一个短标题说明问题与成果",
        "avoid": ["没有相关照片而必须证明实际结果的论点", "操作细节需要全屏录制", "长段落正文"],
        "labels": {"kicker": "引导语", "title": "主标题", "subtitle": "英文或辅助说明", "image": "背景图片"},
        "baseline": {"kicker": "真正困难", "title": "解决问题", "subtitle": "Truly difficult"},
        "replacement": {"kicker": "本期实践", "title": "复刻镜头", "subtitle": "REUSABLE B-ROLL"}},
}


def _ref(asset):
    return {"asset_id": asset["id"], "revision": asset["revision"]}


def _difference(left, right):
    """A probe detects no-op replacement, not semantic or fidelity correctness."""
    def pixels(path):
        with tempfile.TemporaryDirectory(prefix="broll-pixels-") as directory:
            output = Path(directory) / "pixels.rgb"
            run_command(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=64:36",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-frames:v", "1", output], timeout=30)
            return output.read_bytes()
    a, b = pixels(left), pixels(right)
    return sum(abs(x-y) for x, y in zip(a, b)) / max(1, len(a))


class ReplicaService:
    def __init__(self, asset_client, renderer, work_root):
        self.assets = asset_client
        self.renderer = renderer
        self.work_root = Path(work_root).resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)

    def available_cases(self):
        return [{"id": key, "case_id": key, "name": value["name"],
            "available": (REPO / value["case_path"] / "case.json").is_file(),
            "styles": [STYLE_DESCRIPTIONS[s]["name"] for s in value["styles"]],
            "fidelity_status": "needs_review", "source_range": value["source_range"],
            "note": "导入会在新目录重新渲染和替换验证；旧保真结论保持原样。"}
            for key, value in CASE_INDEX.items()]

    def _get(self, asset_id):
        try:
            return self.assets.get_asset(asset_id)
        except KeyError:
            return None

    def _save_file(self, path, kind, name, metadata=None, asset_id=None):
        blob = self.assets.put_blob(Path(path))
        return self.assets.create_asset(kind, name, metadata or {}, blob["sha256"], asset_id)

    def _package(self, renderer_id, output):
        verify_source(RUNTIME, ADAPTERS[renderer_id]["folder"])
        folder = RUNTIME / ADAPTERS[renderer_id]["folder"]
        package = output / f"{renderer_id}.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in folder.rglob("*"):
                if file.is_file() and "node_modules" not in file.parts:
                    archive.write(file, file.relative_to(folder))
            for name in ["package.json", "package-lock.json", "SOURCE-MANIFEST.json"]:
                archive.write(RUNTIME / name, name)
        return package

    def _replacement_image(self, output):
        asset_id = "broll-case-replacement-portrait-v1"
        existing = self._get(asset_id)
        if existing:
            return existing
        image = REPO / "outputs/talking-head-260907/full-edit/assets/episode/remotion/public/assets/episode/aroll-background-wide.png"
        if image.exists():
            return self._save_file(image, "image", "口播 150 秒 · 横版背景", {
                "source": "260907.mov 的 150 秒真实抽帧", "rights": "用户提供口播中的本人画面，使用范围由用户授权决定",
                "provenance": str(image.relative_to(REPO)), "technical_role": "replacement-smoke",
                "description": "本人竖屏照片保留完整人像，右侧放置，同图柔化补齐横版"}, asset_id)
        # Portable fallback is explicitly a test probe, never a production claim.
        image = output / "replacement-probe.svg"
        image.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="400" height="600" fill="#99522c"/><circle cx="200" cy="300" r="110" fill="#eddbb8"/></svg>')
        return self._save_file(image, "image", "替换验收用竖幅图形", {"test_fixture": True,
            "rights": "本产品原创测试图形", "description": "仅验证不同长宽比图片可以替入"}, asset_id)

    def _checkpoint_render(self, result):
        report = self.work_root / f"render-report-{uuid.uuid4().hex}.json"
        report.write_text(json.dumps(result["report"], ensure_ascii=False, indent=2))
        return {"video_hash": self.assets.put_blob(result["video"], "video/mp4")["sha256"],
            "poster_hash": self.assets.put_blob(result["poster"], "image/jpeg")["sha256"],
            "report_hash": self.assets.put_blob(report, "application/json")["sha256"]}

    def _restore_render(self, checkpoint):
        if not checkpoint:
            return None
        try:
            files = {key: Path(self.assets.blob_path(checkpoint[key])) for key in
                     ["video_hash", "poster_hash", "report_hash"]}
            if any(sha256(path) != checkpoint[key] for key, path in files.items()):
                return None
            report = json.loads(files["report_hash"].read_text())
            if report.get("status") != "passed" or report.get("video_sha256") != checkpoint["video_hash"]:
                return None
            return {"video": str(files["video_hash"]), "poster": str(files["poster_hash"]), "report": report}
        except (KeyError, OSError, ValueError):
            return None

    def import_case(self, case_id):
        # Concurrent HTTP retries cannot create duplicate revisions or Chrome jobs.
        with IMPORT_GATE:
            return self._import_case(case_id)

    def _import_case(self, case_id):
        if case_id not in CASE_INDEX:
            raise ValueError("此案例尚无经过审查的适配器；可先创建研究/复刻任务")
        info = CASE_INDEX[case_id]
        replica_id = f"replica-{case_id}-v1"
        existing = self._get(replica_id)
        if existing and existing["metadata"].get("status") == "imported":
            return {"replica": existing, "styles": [self.assets.get_asset(ref["asset_id"], ref["revision"])
                for ref in existing["metadata"]["styles"]]}
        case_dir = REPO / info["case_path"]
        case = json.loads((case_dir / "case.json").read_text())
        output = self.work_root / f"import-{case_id}-{uuid.uuid4().hex[:10]}"
        output.mkdir(parents=True)
        source_id = f"source-{case_id}-v1"
        source = self._get(source_id) or self._save_file(case_dir / case["files"]["source"],
            "source", info["name"] + " · 参考选段", {"source_sha256": case["source"]["sha256"],
                "scope": case.get("scope"), "rights": "第三方参考片，仅研究与比对；MIT 不授权参考画面",
                "provenance": info["case_path"], "status": "reference"}, source_id)
        if not existing:
            existing = self.assets.create_asset("replica", info["name"], {"status": "validating",
                "source": _ref(source), "case_id": case_id, "original_stages": case["stages"],
                "fidelity_status": "needs_review", "case_path": info["case_path"],
                "skill": "ljq-broll-replica", "styles": [], "style_progress": {}, "failures": []}, asset_id=replica_id)
        def checkpoint(**changes):
            nonlocal existing
            metadata = copy.deepcopy(existing["metadata"])
            metadata.update(copy.deepcopy(changes))
            existing = self.assets.revise_asset(existing["id"], existing["revision"], {"metadata": metadata})
        progress = copy.deepcopy(existing["metadata"].get("style_progress", {}))
        styles = []
        active_style, active_stage = None, "prepare"
        checkpoint(status="validating", work_directory=str(output), current_failure=None)
        try:
            for renderer_id in info["styles"]:
                active_style = renderer_id
                definition = STYLE_DESCRIPTIONS[renderer_id]
                adapter = ADAPTERS[renderer_id]
                signature = adapter_signature(renderer_id)
                state = progress.get(renderer_id, {})
                if state.get("adapter_contract_sha256") != signature:
                    state = {"adapter_contract_sha256": signature}
                progress[renderer_id] = state
                # Reuse exactly the version already published in this interrupted import.
                if state.get("published"):
                    saved = self.assets.get_asset(state["published"]["asset_id"], state["published"]["revision"])
                    if saved["metadata"].get("technical_status") == "passed":
                        styles.append(saved)
                        continue
                metadata = {"renderer_id": renderer_id, "status": "validating", "technical_status": "pending",
                    "source_manifest_sha256": AUDITED_MANIFEST_SHA256, "adapter_contract_sha256": signature,
                    "fidelity_status": "needs_review", "fidelity_note": "原案例静态与动态已获历史认可；时变排除区域自动保真门仍待审。",
                    "purpose": definition["purpose"], "avoid": definition["avoid"],
                    "duration": (adapter["frames"][1] - adapter["frames"][0] + 1) / FPS,
                    "native_frames": list(adapter["frames"]), "fps": FPS, "dimensions": [1280, 720],
                    "version": "1.0.0", "source": _ref(source), "replica": _ref(existing),
                    "source_evidence": {"case_path": info["case_path"], "case_stages": case["stages"],
                        "source_sha256": case["source"]["sha256"], "validation": case["files"].get("validation")},
                    "rights": "原创源码 MIT；参考片不进入运行时。第三方图片、字体保留各自许可和署名。",
                    "font_policy": "每次由实际 Chrome 检查字形字体；子集缺字回退明确记录，新内容必须审看。",
                    "field_schema": {key: {"label": definition["labels"][key], "type": kind,
                        "default": default, **({"max_length": maximum} if maximum else {})}
                        for key, (kind, default, maximum) in adapter["fields"].items()}}
                active_stage = "package"
                if not state.get("package_hash"):
                    state["package_hash"] = self.assets.put_blob(self._package(renderer_id, output), "application/zip")["sha256"]
                    checkpoint(style_progress=progress)
                metadata["package_hash"] = state["package_hash"]
                candidate = {"id": f"style-{renderer_id}", "revision": 1, "kind": "style", "metadata": metadata,
                             "blob_hash": state["package_hash"]}
                active_stage = "baseline"
                baseline = self._restore_render(state.get("baseline"))
                if baseline is None:
                    baseline = self.renderer.render(candidate, definition["baseline"], output / renderer_id / "baseline")
                    state["baseline"] = self._checkpoint_render(baseline)
                    checkpoint(style_progress=progress)
                replacement_fields = dict(definition["replacement"])
                if "image" in adapter["fields"]:
                    replacement_fields["image"] = _ref(self._replacement_image(output))
                active_stage = "replacement"
                replacement = self._restore_render(state.get("replacement"))
                if replacement is None or state.get("replacement_fields") != replacement_fields:
                    replacement = self.renderer.render(candidate, replacement_fields, output / renderer_id / "replacement")
                    state.update(replacement=self._checkpoint_render(replacement), replacement_fields=replacement_fields)
                    checkpoint(style_progress=progress)
                delta = _difference(baseline["poster"], replacement["poster"])
                if delta < 1:
                    raise ValueError(f"{renderer_id} 替换未产生可见变化，不能发布")
                report = {"baseline": baseline["report"], "replacement": replacement["report"],
                    "replacement_rgb_delta": delta, "replacement_fields": replacement_fields,
                    "interpretation": "媒体门与非空替换通过；差异分数只拒绝未生效替换，不是语义、排版或保真判定。"}
                report_file = output / f"{renderer_id}-technical.json"
                report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
                evidence_blob = self.assets.put_blob(report_file, "application/json")
                metadata.update(status="usable", technical_status="passed", technical_report=evidence_blob["sha256"],
                    poster_hash=state["baseline"]["poster_hash"], preview_hash=state["baseline"]["video_hash"],
                    replacement_preview_hash=state["replacement"]["video_hash"],
                    font_checks={"baseline": baseline["report"].get("fonts"), "replacement": replacement["report"].get("fonts")},
                    replacement_checks={"field_validation": True, "render_and_decode": True,
                        "visible_change": True, "visual_review": "每个新项目仍须审看；不继承自动保真通过"})
                active_stage = "publish"
                current = self._get(candidate["id"])
                # A retry after publication but before the replica checkpoint is idempotent.
                if current and current["metadata"].get("technical_report") == evidence_blob["sha256"]:
                    style = current
                elif current:
                    style = self.assets.revise_asset(current["id"], current["revision"], {"metadata": metadata,
                        "blob_hash": state["package_hash"]})
                else:
                    style = self.assets.create_asset("style", definition["name"], metadata, state["package_hash"], candidate["id"])
                state["published"] = _ref(style)
                styles.append(style)
                checkpoint(style_progress=progress, styles=[_ref(s) for s in styles])
                self.assets.add_relation(style["id"], existing["id"], "derived_from", {"revision": existing["revision"]})
                self.assets.add_relation(style["id"], source["id"], "reference", {"revision": source["revision"]})
            checkpoint(status="imported", technical_status="passed", styles=[_ref(s) for s in styles],
                style_progress=progress, events=[{"tool": "inspect existing case", "result": case["stages"]},
                    {"tool": "pinned package + Remotion + font load + replace + ffprobe + decode", "result": "passed"}])
            return {"replica": existing, "styles": styles}
        except Exception as error:
            failure = {"renderer_id": active_style, "stage": active_stage, "error": str(error),
                "type": type(error).__name__, "work_directory": str(output), "resumable": True}
            evidence = output / "failure.json"
            evidence.write_text(json.dumps(failure, ensure_ascii=False, indent=2))
            failure["evidence_hash"] = self.assets.put_blob(evidence, "application/json")["sha256"]
            failures = copy.deepcopy(existing["metadata"].get("failures", [])) + [failure]
            checkpoint(status="failed", current_failure=failure, failures=failures,
                style_progress=progress, styles=[_ref(s) for s in styles])
            raise

    def study(self, source_asset, start, end, note=""):
        import math
        if source_asset.get("kind") != "source" or not source_asset.get("blob_hash"):
            raise ValueError("拉片需要已入库的视频来源")
        if not isinstance(note, str) or len(note) > 10000:
            raise ValueError("研究笔记应为 10000 字符以内的文本")
        source = self.assets.blob_path(source_asset["blob_hash"])
        media = probe(source)
        if (not isinstance(start, (float, int)) or not isinstance(end, (float, int))
                or not math.isfinite(start+end) or not 0 <= start < end <= media["duration"]):
            raise ValueError("研究范围必须在源视频内")
        output = self.work_root / f"study-{uuid.uuid4().hex[:12]}"
        output.mkdir()
        evidence = []
        for index, second in enumerate([start, (start+end)/2, max(start, end-1/media["fps"])]):
            image = output / f"frame-{index}.jpg"
            run_command(["ffmpeg", "-v", "error", "-ss", str(second), "-i", source,
                "-frames:v", "1", "-q:v", "2", image], timeout=60)
            blob = self.assets.put_blob(image, "image/jpeg")
            evidence.append({"time": second, "frame": round(second*media["fps"]), "blob_hash": blob["sha256"]})
        metadata = {"source": _ref(source_asset), "source_sha256": source_asset["blob_hash"],
            "start": start, "end": end, "note": note, "frames": evidence, "media": media,
            "status": "studied", "observation": "已保存来源、范围与真实抽帧；尚未宣称布局或动效已重建。"}
        study = self.assets.create_asset("study", f"{source_asset['name']} · {start:.2f}–{end:.2f}s", metadata)
        replica = self.assets.create_asset("replica", f"复刻 · {study['name']}", {
            "status": "needs_work", "source": _ref(source_asset), "study": _ref(study),
            "scope": {"start": start, "end": end}, "stages": {"preflight": "needs_review",
                "layout": "pending", "motion": "pending", "implementation": "pending", "qa": "pending"},
            "next_action": "将范围与取证帧交给 ljq-broll-replica；完成可编辑组件和替换验收后才可发布样式。",
            "fidelity_status": "pending", "technical_status": "pending"})
        metadata["replica"] = _ref(replica)
        study = self.assets.revise_asset(study["id"], study["revision"], {"metadata": metadata})
        self.assets.add_relation(study["id"], source_asset["id"], "studies", {"revision": source_asset["revision"]})
        self.assets.add_relation(replica["id"], study["id"], "implements", {"revision": study["revision"]})
        return study
