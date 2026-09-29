"""Production domain. The asset service stays independent and is consumed over HTTP."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import shutil
import threading
import uuid
from agent_engine import AgentEngine, card_fingerprint
from media import extract_frame, probe, read_workbench, transcribe, workbench_projects
from project_store import ProjectRepository, now, segments_from_input
from provider import CodexProvider, run_process
from renderer import Renderer, validate_fields
from replica import ReplicaService
from replica_review import ReplicaReviewService


class Application:
    def __init__(self, root, assets, provider=None, renderer=None):
        self.repo = ProjectRepository(root)
        self.assets = assets
        self.renderer = renderer or Renderer(assets, self.repo.root / "renders")
        self.replica = ReplicaService(assets, self.renderer, self.repo.root / "replicas")
        self.replica_review = ReplicaReviewService(assets, self.repo.root / "replica-review")
        self.provider = provider or CodexProvider()
        self.engine = AgentEngine(self.repo, assets, self.renderer, self.provider, self.preview)
        self.guard = threading.RLock(); self.running = {}; self.threads = []

    def status(self):
        try: asset_status = {"available": True, "count": len(self.assets.list_assets()), "url": getattr(self.assets, "base_url", "in-process-test")}
        except Exception: asset_status = {"available": False, "message": "共享资产服务未启动，请通过 start.command 启动。"}
        return {"model": self.provider.status(), "assets": asset_status, "capabilities": {
            "agent_loop": True, "real_rendering": True, "shared_versions": True,
            "replica": "已审查案例可执行导入；新参考先建立真实研究与复刻任务，阶段结果需核查。",
            "fidelity": "技术可用与原片保真分开记录。"}}

    def ingest(self, path, kind, name, provenance=None):
        if kind not in ("source", "image", "audio"): raise ValueError("只接受视频、图片或音频。")
        info = probe(path)
        if kind in ("source", "image") and not info["has_video"]: raise ValueError("没有可解码画面。")
        if kind == "source" and info["duration"] <= 0: raise ValueError("视频时长无效。")
        if kind == "image":
            from media import extract_frame
            # Decode uploaded bytes rather than trusting filename or magic bytes.
            check = self.repo.root / "cache" / f"decode-{uuid.uuid4().hex}.jpg"
            extract_frame(path, 0, check); check.unlink()
            if info["duration"] > 1: raise ValueError("图片槽位不能上传视频。")
        mime = {"source": "video/mp4", "image": "image/png", "audio": "audio/wav"}[kind]
        blob = self.assets.put_blob(path, media_type=mime)
        return self.assets.create_asset(kind, name, {"media": info, "provenance": provenance or {"origin": "user_upload"},
            "rights": {"status": "user_supplied_unverified", "usage_scope": "local_project", "redistribution_allowed": False}}, blob["sha256"])

    def create_project(self, payload):
        source = None; duration = None
        if payload.get("source_id"):
            a = self.assets.get_asset(payload["source_id"])
            if a["kind"] != "source": raise ValueError("制作项目需要视频源资产。")
            source = {"asset_id": a["id"], "revision": a["revision"]}
            duration = a["metadata"].get("media", {}).get("duration")
        segments = segments_from_input(payload.get("segments"), payload.get("transcript", ""), duration)
        return self.repo.project(payload.get("name", "新制作项目"), source, segments)

    def import_workbench(self, identity):
        old, source = read_workbench(identity)
        existing = [a for a in self.assets.list_assets(kind="source")
                    if isinstance(a["metadata"].get("provenance"), dict)
                    and a["metadata"]["provenance"].get("workbench_id") == identity]
        asset = existing[0] if existing else self.ingest(source, "source", old["name"], {"workbench_id": identity, "imported_at": now(), "workbench_revision": old.get("revision")})
        p = self.create_project({"name": old["name"].rsplit(".", 1)[0], "source_id": asset["id"], "segments": old.get("transcript", {}).get("segments", [])})
        return p

    def batch(self, identity, payload):
        project = self.repo.get(identity, "project")
        ids = payload.get("card_ids", [])
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids): raise ValueError("请先选择卡片。")
        if not set(ids) <= {c["id"] for c in project["cards"]}: raise ValueError("有卡片已不存在，请刷新。")
        action = payload.get("action")
        if action not in ("approve", "reject", "reset", "replace", "retime", "effect"): raise ValueError("未知批量操作。")
        if action in ("retime", "effect") and len(ids) != 1: raise ValueError("时间和动效请逐段调整。")
        timing = None
        if action == "retime":
            try: start, end = float(payload["start"]), float(payload["end"])
            except (KeyError, TypeError, ValueError): raise ValueError("请提供有效起止时间。")
            if not all(map(math.isfinite, (start, end))) or start < 0 or not .4 <= end-start <= 15:
                raise ValueError("片段时长须为0.4–15秒，时间码不得为负。")
            if not project.get("source"): raise ValueError("请先关联真实口播视频，才能调整时间线。")
            source = self.assets.get_asset(project["source"]["asset_id"], project["source"]["revision"])
            duration = source["metadata"].get("media", {}).get("duration")
            if not isinstance(duration, (int, float)) or end > duration + .001: raise ValueError("片段超出原视频范围。")
            if any(c["id"] not in ids and c["decision"] == "broll" and c["status"] != "rejected"
                   and start < c["end"] - .001 and end > c["start"] + .001 for c in project["cards"]):
                raise ValueError("B-roll画面不能与另一段B-roll重叠。")
            timing = (round(start, 3), round(end, 3))
        if action == "effect" and (payload.get("crop_mode") not in ("contain", "cover")
                                    or payload.get("transition") not in ("cut", "dissolve")):
            raise ValueError("未知画幅或转场方式。")
        def edit(p):
            for card in p["cards"]:
                if card["id"] not in ids: continue
                if action == "retime":
                    if card["decision"] != "broll": raise ValueError("只可调整B-roll覆盖片段的时间。")
                    card["start"], card["end"] = timing
                    card["timing_adjusted"] = True
                    card["status"] = "draft"
                    for key in ("preview_url", "poster_url", "render_path", "poster_path", "render_report", "render_fingerprint"):
                        card.pop(key, None)
                elif action == "effect":
                    if card["decision"] != "broll": raise ValueError("转场与画幅只适用于B-roll。")
                    card["crop_mode"] = payload["crop_mode"]
                    card["transition"] = payload["transition"]
                    card["status"] = "draft"
                    for key in ("preview_url", "poster_url", "render_path", "poster_path", "render_report", "render_fingerprint"):
                        card.pop(key, None)
                elif action == "replace":
                    if payload.get("style_id"):
                        a = self.assets.get_asset(payload["style_id"])
                        if a["kind"] != "style" or a["metadata"].get("technical_status") != "passed": raise ValueError("所选样式不可用。")
                        card["style"] = {"asset_id": a["id"], "revision": a["revision"]}; card["decision"] = "broll"; card["fields"] = {}; card["missing"] = []
                    if not card.get("style"): raise ValueError("请为保留口播卡先选择样式，再替换字段。")
                    a = self.assets.get_asset(card["style"]["asset_id"], card["style"]["revision"])
                    fields = {**card["fields"], **payload.get("fields", {})}
                    card["fields"] = validate_fields(a["metadata"]["renderer_id"], fields)
                    for value in card["fields"].values():
                        if isinstance(value, dict):
                            image = self.assets.get_asset(value["asset_id"], value["revision"])
                            if image["kind"] != "image": raise ValueError("替换图片必须来自图片资产。")
                    if not .4 <= card["end"]-card["start"] <= 15: raise ValueError("该卡时长不适合样式，请调整字幕分组。")
                    card["status"] = "draft"
                    for key in ("preview_url", "poster_url", "render_path", "poster_path", "render_report", "render_fingerprint"):
                        card.pop(key, None)
                elif action == "approve":
                    if card["decision"] == "gap": raise ValueError("缺口未补齐，请先选样式和素材，或拒绝以保留口播。")
                    if card["decision"] == "broll" and card.get("render_fingerprint") != card_fingerprint(card):
                        raise ValueError("请先预览当前版本，再批准；旧预览不能代表新内容。")
                    if card["decision"] == "broll" and card.get("render_report", {}).get("layout", {}).get("status") != "passed":
                        raise ValueError("版式检查尚未通过，请重新预览并缩短挤压的文字或换用样式。")
                    card["status"] = "approved"
                else: card["status"] = "rejected" if action == "reject" else "draft"
            p["history"].append({"time": now(), "action": action, "card_ids": ids,
                "actor": "acceptance-test" if payload.get("reviewer") == "acceptance-test" else "user", "fields": payload.get("fields", {}),
                "timing": timing, "crop_mode": payload.get("crop_mode"), "transition": payload.get("transition")})
        return self.repo.update(identity, payload.get("revision"), edit)

    def duplicate(self, identity, name=None):
        old = self.repo.get(identity, "project")
        p = self.repo.project(name or old["name"] + " · 副本", copy.deepcopy(old["source"]), copy.deepcopy(old["segments"]))
        cards = copy.deepcopy(old["cards"])
        for card in cards:
            card["status"] = "draft"
            for key in ("preview_url", "poster_url", "render_path", "poster_path", "render_report", "render_fingerprint"):
                card.pop(key, None)
        return self.repo.update(p["id"], p["revision"], lambda v: v.update(cards=cards, derived_from={"project_id": identity, "revision": old["revision"]}))

    def preview(self, identity, ids):
        p = self.repo.get(identity, "project")
        if not isinstance(ids, list) or not ids: raise ValueError("请选择需要预览的B-roll卡片。")
        if not set(ids) <= {c["id"] for c in p["cards"]}: raise ValueError("卡片不存在。")
        cards = [c for c in p["cards"] if c["id"] in ids and c["decision"] == "broll"]
        for card in cards:
            fingerprint = card_fingerprint(card)
            if (card.get("render_fingerprint") == fingerprint and card.get("render_report", {}).get("layout")
                    and (not p["source"] or card.get("render_report", {}).get("review_context"))
                    and Path(card.get("render_path", "missing")).is_file()): continue
            a = self.assets.get_asset(card["style"]["asset_id"], card["style"]["revision"])
            result = self.renderer.render(a, card["fields"], self.repo.root / "renders" / identity, duration=card["end"]-card["start"])
            if result["report"].get("status") != "passed": raise ValueError("预览技术检查未通过。")
            media_dir = self.repo.root / "files" / identity; media_dir.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            video, poster = media_dir / f"{token}.mp4", media_dir / f"{token}.jpg"
            native = media_dir / f"{token}-native.mp4"
            shutil.copyfile(result["video"], native)
            context = self.context_preview(p, card, native, video, poster)
            if context: result["report"]["review_context"] = context
            else:
                shutil.copyfile(result["video"], video); shutil.copyfile(result["poster"], poster)
            if card.get("crop_mode") == "cover" and p["source"]:
                source_info = self.assets.get_asset(p["source"]["asset_id"], p["source"]["revision"])["metadata"].get("media", {})
                style_width, style_height = a["metadata"].get("dimensions", (0, 0))
                width, height = source_info.get("width", 0), source_info.get("height", 0)
                if width and height and style_width and style_height:
                    visible_fraction = min((width / height) / (style_width / style_height),
                                           (style_width / style_height) / (width / height))
                    if visible_fraction < .7:
                        layout = result["report"].setdefault("layout", {})
                        layout["status"] = "needs_revision"
                        layout.setdefault("issues", []).append({"message":
                            f"铺满裁剪仅保留约{visible_fraction:.0%}原画面，文字或主体可能被截断。请改用完整画面，或制作适配当前画幅的新样式。"})
            def attach(current):
                target = next((c for c in current["cards"] if c["id"] == card["id"]), None)
                if not target or card_fingerprint(target) != fingerprint: raise ValueError("渲染期间卡片已更新，旧预览已保留但没有覆盖新内容。")
                target.update(render_path=str(native), poster_path=str(poster), preview_url=f"/api/files/{identity}/{video.name}",
                    poster_url=f"/api/files/{identity}/{poster.name}", render_report=result["report"], render_fingerprint=fingerprint)
            latest = self.repo.get(identity)
            self.repo.update(identity, latest["revision"], attach)
        return self.repo.get(identity)

    def context_preview(self, project, card, native, video, poster):
        if not project["source"]: return None
        asset = self.assets.get_asset(project["source"]["asset_id"], project["source"]["revision"])
        source = self.assets.blob_path(asset["blob_hash"])
        clip = self.repo.root / "cache" / f"review-{uuid.uuid4().hex}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        length = card["end"] - card["start"]
        try:
            run_process(["ffmpeg", "-v", "error", "-ss", str(card["start"]), "-i", source, "-t", str(length),
                "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-movflags", "+faststart", clip], timeout=180)
            result = self.renderer.compose(clip, [{"id": card["id"], "start": 0, "end": length, "render_path": str(native),
                "crop_mode": card.get("crop_mode", "contain"), "transition": card.get("transition", "cut")}], video)
            extract_frame(video, min(length-.04, length*.65), poster)
            return {"source": project["source"], "range": [card["start"], card["end"]], "report": result["report"],
                    "review_only": True, "message": "此预览已放入口播原画幅与声音，仅供审看，不代表用户批准。"}
        finally: clip.unlink(missing_ok=True)

    def compose(self, identity):
        p = self.repo.get(identity, "project")
        if not p["source"]: raise ValueError("请关联真实口播视频后再导出成片。")
        cards = [c for c in p["cards"] if c["status"] == "approved" and c["decision"] == "broll"]
        if not cards: raise ValueError("请先预览并批准至少一张B-roll卡片。")
        used = {s for c in cards for s in c["segment_ids"]}
        if any(s["estimated"] for s in p["segments"] if s["id"] in used): raise ValueError("这些时间码是文稿估算，请先转录或导入真实字幕。")
        if any(c.get("render_fingerprint") != card_fingerprint(c) for c in cards): raise ValueError("批准版本与当前渲染不一致，请重新预览确认。")
        if any(c.get("render_report", {}).get("layout", {}).get("status") != "passed" for c in cards): raise ValueError("批准卡片需要通过当前版式检查，请重新预览。")
        source = self.assets.get_asset(p["source"]["asset_id"], p["source"]["revision"])
        directory = self.repo.root / "files" / identity; directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"final-{uuid.uuid4().hex}.mp4"
        result = self.renderer.compose(self.assets.blob_path(source["blob_hash"]), cards, output)
        delivery = {"url": f"/api/files/{identity}/{output.name}", "project_revision": p["revision"], "created_at": now(),
                    "cards": [{"id": c["id"], "fingerprint": c["render_fingerprint"], "style": c["style"]} for c in cards], "report": result["report"]}
        # CAS means changes during encoding never get silently labeled as the current final cut.
        updated = self.repo.update(identity, p["revision"], lambda v: v["deliveries"].append(delivery))
        return {"delivery": delivery, "project": updated}

    def start_job(self, kind, project_id, operation):
        job = self.repo.create("job", {"kind": kind, "project_id": project_id, "status": "queued"})
        def work():
            try:
                self.repo.update(job["id"], job["revision"], lambda v: v.update(status="running"))
                result = operation()
                current = self.repo.get(job["id"])
                self.repo.update(job["id"], current["revision"], lambda v: v.update(status="complete", result=result))
            except Exception as error:
                current = self.repo.get(job["id"])
                self.repo.update(job["id"], current["revision"], lambda v: v.update(status="failed", error=str(error)))
        t = threading.Thread(target=work, daemon=True); self.threads.append(t); t.start()
        return job

    def start_run(self, identity, resume=None):
        with self.guard:
            if identity in self.running: raise ValueError("这个项目的Agent仍在运行。")
            p = self.repo.get(identity, "project")
            if resume:
                run = self.repo.get(resume, "run")
                if run["project_id"] != identity or run["status"] not in ("failed", "interrupted"): raise ValueError("此运行不能恢复。")
            else:
                run = self.repo.create("run", {"project_id": identity, "status": "queued", "input_revision": p["revision"], "model": self.provider.status()})
                self.repo.update(identity, p["revision"], lambda v: v["runs"].append(run["id"]))
            cancel = threading.Event(); self.running[identity] = cancel
        def work():
            try:
                # One model/render loop at a time keeps local memory use bounded; other UI actions remain live.
                with self.engine.gate: self.engine.execute(run["id"], cancel=cancel)
            finally:
                with self.guard: self.running.pop(identity, None)
        t = threading.Thread(target=work, daemon=True); self.threads.append(t); t.start()
        return run

    def transcribe_project(self, identity):
        p = self.repo.get(identity, "project")
        if not p["source"]: raise ValueError("转录需要口播视频。")
        if any(c["status"] in ("approved", "rejected") for c in p["cards"]): raise ValueError("请先重置已确认卡片，避免新字幕改变已批准的时间码。")
        a = self.assets.get_asset(p["source"]["asset_id"], p["source"]["revision"])
        path = self.assets.blob_path(a["blob_hash"])
        segments = segments_from_input(transcribe(path), duration=probe(path)["duration"])
        return self.repo.update(identity, p["revision"], lambda v: v.update(segments=segments, cards=[]))

    def close(self):
        with self.guard:
            for event in self.running.values(): event.set()
        for t in self.threads: t.join(timeout=3)
