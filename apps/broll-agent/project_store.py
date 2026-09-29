"""Versioned production projects and resumable, append-only decision traces."""
from __future__ import annotations
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid


def now(): return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
def uid(): return uuid.uuid4().hex
def dumps(value): return json.dumps(value, ensure_ascii=False, allow_nan=False)


def segments_from_input(segments=None, transcript="", duration=None):
    if not segments:
        pieces = [x.strip() for x in re.split(r"(?<=[。！？!?])|\n+", str(transcript)) if x.strip()]
        if not pieces: return []
        total = sum(map(len, pieces)); cursor = 0
        # Untimed text is explicitly estimated and cannot enter final composition until timed.
        length = duration or max(1, total / 4)
        segments = []
        for text in pieces:
            end = cursor + length * len(text) / total
            segments.append({"start": cursor, "end": end, "text": text, "estimated": True}); cursor = end
    if not isinstance(segments, list) or len(segments) > 1500: raise ValueError("字幕须为不超过1500条的列表。")
    result = []; previous = 0.0
    for i, item in enumerate(segments):
        start, end = float(item["start"]), float(item["end"])
        text = str(item["text"]).strip()
        if not all(map(math.isfinite, [start, end])) or start < previous - .001 or end <= start or not text:
            raise ValueError("字幕时间码必须递增、互不重叠且文字非空。")
        if duration and end > duration + .1: raise ValueError("字幕超出原视频时长。")
        result.append({"id": f"s{i+1:03d}", "start": round(start, 3), "end": round(end, 3), "text": text,
                       "estimated": bool(item.get("estimated", False))})
        previous = end
    return result


class ProjectRepository:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "projects.sqlite3"
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions(id TEXT, revision INTEGER, data TEXT, PRIMARY KEY(id, revision));
            CREATE TABLE IF NOT EXISTS events(run_id TEXT, sequence INTEGER, data TEXT, PRIMARY KEY(run_id,sequence));
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=20)
        try:
            with connection: yield connection
        finally: connection.close()

    def create(self, kind, data):
        v = {**copy.deepcopy(data), "id": uid(), "revision": 1, "created_at": now(), "updated_at": now()}
        with self.connect() as c:
            c.execute("INSERT INTO documents VALUES(?,?,?,?)", (v["id"], kind, 1, dumps(v)))
            c.execute("INSERT INTO versions VALUES(?,?,?)", (v["id"], 1, dumps(v)))
        return v

    def get(self, identity, kind=None):
        with self.connect() as c: row = c.execute("SELECT kind,data FROM documents WHERE id=?", (identity,)).fetchone()
        if not row or (kind and row[0] != kind): raise KeyError("记录不存在。")
        value = json.loads(row[1])
        if row[0] == "run": value["events"] = self.events(identity)
        return value

    def list(self, kind):
        with self.connect() as c: rows = c.execute("SELECT data FROM documents WHERE kind=? ORDER BY rowid DESC", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def update(self, identity, expected_revision, change):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT revision,data FROM documents WHERE id=?", (identity,)).fetchone()
            if not row: raise KeyError("记录不存在。")
            if row[0] != expected_revision: raise ValueError("内容已更新，请刷新后重试，旧修改未覆盖新版本。")
            value = json.loads(row[1]); change(value)
            value.update(revision=expected_revision+1, updated_at=now())
            c.execute("UPDATE documents SET revision=?,data=? WHERE id=?", (value["revision"], dumps(value), identity))
            c.execute("INSERT INTO versions VALUES(?,?,?)", (identity, value["revision"], dumps(value)))
        return value

    def event(self, run_id, event_type, message, data=None):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            sequence = c.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            value = {"sequence": sequence, "type": event_type, "message": message, "data": data or {}, "time": now()}
            c.execute("INSERT INTO events VALUES(?,?,?)", (run_id, sequence, dumps(value)))
        return value

    def events(self, run_id):
        with self.connect() as c: rows = c.execute("SELECT data FROM events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def recover(self):
        for kind in ("run", "job"):
            for item in self.list(kind):
                if item.get("status") in ("queued", "running"):
                    self.update(item["id"], item["revision"], lambda v: v.update(status="interrupted", error="服务上次中断；已保留工具记录和草稿，可继续。"))

    def project(self, name, source=None, segments=None):
        if not str(name).strip(): raise ValueError("项目名称不能为空。")
        return self.create("project", {"name": str(name).strip()[:200], "source": source, "segments": segments or [],
            "cards": [], "runs": [], "history": [], "deliveries": []})

    def memory(self, exclude=None):
        # Human outcomes are evidence scoped to their project, never rewritten as universal taste.
        result = []
        for p in self.list("project"):
            decisions = [h for h in p.get("history", []) if h.get("actor") == "user"][-12:]
            if p["id"] == exclude or not decisions: continue
            reviewed = {identity for h in decisions for identity in h.get("card_ids", [])}
            result.append({"project_id": p["id"], "name": p["name"], "decisions": decisions,
                "cards": [{k: c.get(k) for k in ("text", "decision", "reason", "style", "status")}
                          for c in p["cards"] if c["status"] != "draft" and c["id"] in reviewed]})
        return result[:8]
