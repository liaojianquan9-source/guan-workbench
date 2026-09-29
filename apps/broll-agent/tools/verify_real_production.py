#!/usr/bin/env python3
"""Real, resumable acceptance through the existing AI 制作 HTTP entry.

Creates one clearly labelled acceptance project. Never edits the source project;
all batch decisions are tagged acceptance-test, so they cannot become user taste.
Evidence (including downloaded video) belongs outside Git. --check-only verifies
an existing evidence run without making any product mutations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORIGINAL = "23db4d3f88134c4fb51d0fd54d346698"
CARDS = ["c004", "c007"]
NAME = "验收副本 · 跨项目复用"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def object_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def command(*args, timeout=300):
    result = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout)
    require(result.returncode == 0, result.stderr.decode(errors="replace")[-2000:])
    return result.stdout


def media_probe(path):
    raw = json.loads(command("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path))
    video = next(s for s in raw["streams"] if s["codec_type"] == "video")
    audios = [s for s in raw["streams"] if s["codec_type"] == "audio"]
    a, b = video["avg_frame_rate"].split("/")
    return {"width": video["width"], "height": video["height"], "fps": float(a) / float(b),
            "duration": float(video.get("duration", raw["format"]["duration"])),
            "frames": int(video["nb_frames"]) if video.get("nb_frames", "N/A") != "N/A" else None,
            "audio": [{k: s.get(k) for k in ("codec_name", "sample_rate", "channels", "start_time", "duration", "nb_frames")} for s in audios]}


class Acceptance:
    def __init__(self, args):
        self.base = args.base.rstrip("/")
        self.root = Path(args.evidence).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"base": self.base, "original_id": args.original}
        require(self.state["base"] == self.base and self.state["original_id"] == args.original, "Evidence belongs to another API/original project")
        self.original = args.original
        self.check_only = args.check_only

    def save(self, name, value):
        target = self.root / name
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        temp.replace(target)

    def checkpoint(self, **values):
        self.state.update(values)
        self.save("state.json", self.state)

    def request(self, path, payload=None, expected=None):
        require(not self.check_only or payload is None, "--check-only prohibits product mutations")
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"Content-Type": "application/json"} if payload is not None else {})
        try:
            response = urlopen(request, timeout=90)
        except HTTPError as error:
            response = error
        with response:
            status = response.status
            raw = response.read()
        result = json.loads(raw)
        event = {"time": time.time(), "method": request.get_method(), "path": path, "status": status, "payload": payload,
                 "response_sha256": hashlib.sha256(raw).hexdigest()}
        with (self.root / "http.jsonl").open("a") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        require((200 <= status < 300) if expected is None else status == expected, f"{path}: HTTP {status}; {result}")
        return result

    def project(self, identity=None):
        return self.request("/projects/" + (identity or self.state["clone_id"]))["project"]

    def batch(self, ids, action, **values):
        current = self.project()
        return self.request(f"/projects/{current['id']}/batch", {
            "revision": current["revision"], "card_ids": ids, "action": action,
            "reviewer": "acceptance-test", **values})["project"]

    def wait_job(self, identity):
        deadline = time.monotonic() + 1800
        seen = None
        while time.monotonic() < deadline:
            job = self.request("/jobs/" + identity)["job"]
            if job["status"] != seen:
                print(f"job {identity}: {job['status']}", flush=True)
                seen = job["status"]
            if job["status"] in ("complete", "failed", "interrupted"):
                self.save(f"job-{identity}.json", job)
                require(job["status"] == "complete", f"Job failed: {job.get('error')}")
                return job
            time.sleep(3)
        raise RuntimeError("Job timed out; evidence is resumable, job was not cancelled")

    def media_path(self, backend_url):
        require(backend_url.startswith("/api/"), "Unexpected backend media URL")
        return backend_url[len("/api"):]

    def download(self, path, name, expected_hash=None):
        target = self.root / name
        if not target.exists() or (expected_hash and digest(target) != expected_hash):
            part = target.with_suffix(target.suffix + ".part")
            with urlopen(self.base + path, timeout=90) as response, part.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
            part.replace(target)
        if expected_hash:
            require(digest(target) == expected_hash, f"Downloaded media hash mismatch: {name}")
        return target

    def range_check(self, path, local):
        request = Request(self.base + path, headers={"Range": "bytes=0-1023"})
        with urlopen(request, timeout=90) as response:
            body, status, headers = response.read(), response.status, dict(response.headers)
        expected_range = f"bytes 0-1023/{local.stat().st_size}"
        require(status == 206, "Proxy did not preserve HTTP Range status")
        require(headers.get("Content-Range") == expected_range, "Proxy Range metadata is wrong")
        with local.open("rb") as handle:
            require(body == handle.read(1024), "Range returned different bytes")
        return {"status": status, "content_range": headers["Content-Range"], "bytes": len(body), "matches_file": True}

    def run(self):
        if "clone_id" not in self.state:
            require(not self.check_only, "No completed acceptance state")
            original = self.project(self.original)
            require(original["cards"], "Original has no real Agent draft")
            self.save("original-before.json", original)
            self.checkpoint(original_hash=object_digest(original), original_revision=original["revision"])
            clone = self.request(f"/projects/{self.original}/duplicate", {"name": NAME})["project"]
            self.checkpoint(clone_id=clone["id"])
            self.save("clone-created.json", clone)
        original = json.loads((self.root / "original-before.json").read_text())
        clone = self.project()
        require(clone["id"] != original["id"] and clone["source"] == original["source"], "Clone source is not pinned to the original asset revision")
        require(clone["derived_from"] == {"project_id": self.original, "revision": original["revision"]}, "Clone provenance differs")
        moon = next(c for c in original["cards"] if c["id"] == "c004")["style"]
        require(moon == {"asset_id": "style-kimi-moon-v1", "revision": 1}, "Unexpected original style revision")
        sources = self.request("/assets?kind=source")["assets"]
        styles = self.request("/assets?kind=style")["assets"]
        source = next(a for a in sources if a["id"] == clone["source"]["asset_id"])
        style = next(a for a in styles if a["id"] == moon["asset_id"])
        require(source["revision"] == clone["source"]["revision"] and style["revision"] == moon["revision"], "Current assets changed; this acceptance must use the pinned revisions")
        self.save("assets.json", {"source": source, "style": style})

        if not self.state.get("bulk_fields_changed"):
            if not self.state.get("replacements_complete"):
                self.batch(["c004"], "replace", fields={"subtitle": "用好AI"})
                self.batch(["c007"], "replace", style_id=moon["asset_id"], fields={"title": "收工", "subtitle": "明天", "texture_text": "好好休息"})
            # Prove actual changes on both cards, not just a no-op bulk payload.
            before = self.project()
            self.save("clone-before-batch-replacement.json", before)
            intermediate = self.batch(CARDS, "replace", fields={"texture_text": "待替换纹理"})
            for card in intermediate["cards"]:
                if card["id"] in CARDS:
                    require(card["fields"]["texture_text"] == "待替换纹理" and card["status"] == "draft"
                            and "render_path" not in card and "render_fingerprint" not in card,
                            "Bulk replacement did not change both cards and invalidate their approval/preview")
            self.save("clone-intermediate-batch-replacement.json", intermediate)
            clone = self.batch(CARDS, "replace", fields={"texture_text": "好好休息"})
            for card in clone["cards"]:
                if card["id"] in CARDS:
                    require(card["style"] == moon and card["fields"]["texture_text"] == "好好休息"
                            and card["status"] == "draft" and "render_path" not in card,
                            "Replacement did not restore intended fields with the pinned style")
            self.save("clone-after-batch-replacement.json", clone)
            denied = self.request(f"/projects/{clone['id']}/batch", {"revision": clone["revision"], "card_ids": CARDS,
                "action": "approve", "reviewer": "acceptance-test"}, expected=400)
            require(self.project()["revision"] == clone["revision"], "Failed batch approval mutated the project")
            self.save("unrendered-approval-rejected.json", denied)
            prior = self.state.get("earlier_jobs", [])
            if self.state.get("preview_job"):
                prior.append({"preview_job": self.state["preview_job"], "render_job": self.state.get("render_job")})
            self.checkpoint(replacements_complete=True, bulk_fields_changed=True, preview_job=None,
                            render_job=None, approved=False, complete=False, earlier_jobs=prior)

        if not self.state.get("preview_job"):
            job = self.request(f"/projects/{clone['id']}/preview", {"card_ids": CARDS})["job"]
            self.checkpoint(preview_job=job["id"])
        self.wait_job(self.state["preview_job"])
        clone = self.project()
        self.save("clone-after-preview.json", clone)
        expected_fields = {"c004": {"title": "睡好觉", "subtitle": "用好AI", "texture_text": "好好休息"},
                           "c007": {"title": "收工", "subtitle": "明天", "texture_text": "好好休息"}}
        card_evidence = []
        for card in clone["cards"]:
            if card["id"] not in CARDS:
                continue
            report = card["render_report"]
            require(card["fields"] == expected_fields[card["id"]] == report["fields"], "Replacement fields differ from rendered fields")
            require(card["style"] == report["style"] == moon, "Render did not use the same fixed shared style")
            require(report["status"] == "passed" and report["layout"]["status"] == "passed", "Technical/layout review failed")
            require(report["source_origin"] == "immutable_asset_package", "Render did not restore immutable shared package")
            require(report["source_manifest_sha256"] == style["metadata"]["source_manifest_sha256"], "Source manifest drift")
            for field, prop in {"title": "kimiTitle", "subtitle": "k3Title", "texture_text": "moonTitle"}.items():
                require(report["props"][prop] == expected_fields[card["id"]][field], "Real Remotion props do not match replacement")
            context = report["review_context"]
            require(context["source"] == clone["source"] and context["range"] == [card["start"], card["end"]] and context["review_only"], "Context preview source/range is not pinned")
            native = Path(card["render_path"])
            require(digest(native) == report["video_sha256"], "Native rendered file differs from report")
            preview = self.download(self.media_path(card["preview_url"]), f"{card['id']}-context.mp4", context["report"]["video_sha256"])
            poster = self.download(self.media_path(card["poster_url"]), f"{card['id']}-poster.jpg")
            media = media_probe(preview)
            require((media["width"], media["height"], media["fps"]) == (1080, 1920, 30), "Context preview is not the real portrait source format")
            require(media["audio"] and abs(media["duration"] - (card["end"] - card["start"])) <= 2/30, "Context preview audio/duration mismatch")
            require(media_probe(native)["width"] == 1280, "Native style version changed format")
            card_evidence.append({"id": card["id"], "range": context["range"], "style": card["style"], "fields": card["fields"],
                "fingerprint": card["render_fingerprint"], "native_path": str(native), "native_sha256": report["video_sha256"],
                "context_path": str(preview), "context_sha256": digest(preview), "poster_path": card["poster_path"],
                "downloaded_poster": str(poster), "media": media, "layout": report["layout"], "fonts": report["fonts"],
                "fidelity_status": report["fidelity_status"]})
        require(len(card_evidence) == 2, "Both requested cards were not previewed")
        self.save("cards-evidence.json", card_evidence)

        if not self.state.get("approved"):
            clone = self.batch(CARDS, "approve")
            require(all(c["status"] == "approved" for c in clone["cards"] if c["id"] in CARDS), "Batch approval incomplete")
            self.save("clone-after-approval.json", clone)
            self.checkpoint(approved=True)
        if not self.state.get("render_job"):
            job = self.request(f"/projects/{clone['id']}/render", {})["job"]
            self.checkpoint(render_job=job["id"])
        completed = self.wait_job(self.state["render_job"])
        delivery = completed["result"]["delivery"]
        self.save("delivery.json", delivery)
        clone = self.project()
        self.save("clone-final.json", clone)
        for untouched in clone["cards"]:
            if untouched["id"] not in CARDS:
                require(untouched == next(c for c in original["cards"] if c["id"] == untouched["id"]), "Acceptance changed an unselected card")
        require([c["id"] for c in delivery["cards"]] == CARDS, "Final composition included different cards")
        require(all(c["style"] == moon and c["fingerprint"] == next(x["fingerprint"] for x in card_evidence if x["id"] == c["id"]) for c in delivery["cards"]), "Final delivery is not bound to approved rendered fields")
        require(all(h["actor"] == "acceptance-test" for h in clone["history"]), "Acceptance leaked a user preference history entry")
        require(any(h["action"] == "replace" and h["card_ids"] == CARDS for h in clone["history"]), "No real two-card bulk replacement occurred")
        require(any(h["action"] == "approve" and h["card_ids"] == CARDS for h in clone["history"]), "No real two-card bulk approval occurred")
        original_after = self.project(self.original)
        self.save("original-after.json", original_after)
        require(object_digest(original_after) == self.state["original_hash"], "Original project changed during acceptance")

        source_file = self.download("/media/" + source["blob_hash"], "source.mov", source["blob_hash"])
        final_file = self.download(self.media_path(delivery["url"]), "final.mp4", delivery["report"]["video_sha256"])
        final_path = Path(card_evidence[0]["native_path"]).parent / delivery["url"].rsplit("/", 1)[-1]
        require(final_path.is_file() and digest(final_path) == digest(final_file), "HTTP final differs from saved product final")
        source_probe, final_probe = media_probe(source_file), media_probe(final_file)
        require((final_probe["width"], final_probe["height"], final_probe["fps"], final_probe["frames"]) ==
                (source_probe["width"], source_probe["height"], source_probe["fps"], source_probe["frames"]), "Final dimensions/fps/frame count changed")
        require(abs(final_probe["duration"] - source_probe["duration"]) <= 1/30 and final_probe["audio"], "Final duration/audio changed")
        for key in ("codec_name", "sample_rate", "channels", "start_time", "nb_frames"):
            require(final_probe["audio"][0][key] == source_probe["audio"][0][key], f"Final audio {key} changed")
        command("ffmpeg", "-v", "error", "-i", final_file, "-f", "null", "-")
        audio_hashes = {}
        for label, file in [("source", source_file), ("final", final_file)]:
            # Decode both whole soundtracks to equal PCM; this catches silence, clipping and accidental shifts.
            value = command("ffmpeg", "-v", "error", "-i", file, "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "hash", "-hash", "sha256", "-").decode().strip()
            audio_hashes[label] = value
        require(audio_hashes["source"] == audio_hashes["final"], "Decoded original/final soundtracks differ")
        frames = []
        for label, seconds in [("original-preserved", 10), ("c004-replacement", 25.8), ("c007-replacement", 43.8), ("ending-preserved", 50.0)]:
            frame = self.root / f"final-{label}.jpg"
            command("ffmpeg", "-y", "-v", "error", "-ss", seconds, "-i", final_file, "-frames:v", "1", "-q:v", "2", frame)
            frames.append({"label": label, "seconds": seconds, "path": str(frame), "sha256": digest(frame)})
        result = {"status": "passed", "base": self.base, "original_id": self.original,
            "original_revision": original["revision"], "original_unchanged_sha256": self.state["original_hash"],
            "clone_id": clone["id"], "clone_revision": clone["revision"], "clone_name": clone["name"],
            "source": clone["source"], "source_sha256": source["blob_hash"], "shared_style": moon,
            "style_package_sha256": style["blob_hash"], "source_manifest_sha256": style["metadata"]["source_manifest_sha256"],
            "cards": card_evidence, "delivery": delivery, "final_path": str(final_path),
            "downloaded_final": str(final_file), "source_media": source_probe, "final_media": final_probe,
            "decoded_audio_sha256": audio_hashes, "range": self.range_check(self.media_path(delivery["url"]), final_file),
            "source_range": self.range_check("/media/" + source["blob_hash"], source_file),
            "frames": frames, "reviewer": "acceptance-test", "meaning": "技术链路验收；样式选择仅为验收，不代表用户审美批准，原片保真仍待审。"}
        self.save("result.json", result)
        self.checkpoint(complete=True)
        print(json.dumps({k: result[k] for k in ["status", "clone_id", "final_path", "final_media", "range"]}, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:4182/api/production")
    parser.add_argument("--original", default=ORIGINAL)
    parser.add_argument("--evidence", required=True, help="Persistent evidence directory outside the repository")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    acceptance = Acceptance(args)
    try:
        acceptance.run()
    except Exception as error:
        acceptance.save("failure.json", {"error": str(error), "type": type(error).__name__, "state": acceptance.state})
        raise


if __name__ == "__main__":
    main()
