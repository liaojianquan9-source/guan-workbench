"""Product-independent, revisioned assets and immutable content-addressed blobs."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
import uuid
import zipfile

KINDS = frozenset({"source", "image", "audio", "style", "study", "replica"})
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_BUNDLE_BYTES = 50 * 1024 ** 3


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def json_text(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Metadata must be finite JSON data") from exc


def valid_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError("Invalid asset identifier")
    return value


def valid_hash(value):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError("Invalid SHA256")
    return value


class AssetStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self.database = self.root / "assets.sqlite3"
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS blobs (
                    sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL,
                    media_type TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
                    name TEXT NOT NULL, metadata TEXT NOT NULL, blob_hash TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(id, revision),
                    FOREIGN KEY(blob_hash) REFERENCES blobs(sha256)
                );
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL,
                    object_id TEXT NOT NULL, predicate TEXT NOT NULL,
                    metadata TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS relation_subject ON relations(subject_id);
                CREATE INDEX IF NOT EXISTS relation_object ON relations(object_id);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _asset(row):
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def put_blob(self, path, media_type=None):
        source = Path(path)
        if not source.is_file():
            raise ValueError("Blob source is not a regular file")
        content_type = media_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        if not isinstance(content_type, str) or len(content_type) > 200 or "\r" in content_type or "\n" in content_type:
            raise ValueError("Invalid media type")
        digest, size = hashlib.sha256(), 0
        fd, temporary = tempfile.mkstemp(prefix=".ingest-", dir=self.blobs)
        try:
            with os.fdopen(fd, "wb") as target, source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            sha = digest.hexdigest()
            destination = self.blobs / sha[:2] / sha
            destination.parent.mkdir(exist_ok=True)
            try:
                # Atomic create, never replace an existing blob, even under concurrent uploads.
                os.link(temporary, destination)
                destination.chmod(0o444)
            except FileExistsError:
                if destination.stat().st_size != size or self._file_hash(destination) != sha:
                    raise ValueError("Existing blob failed integrity verification")
            with self._connect() as db:
                db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?, ?, ?)", (sha, size, content_type, now()))
                row = db.execute("SELECT sha256,size,media_type FROM blobs WHERE sha256=?", (sha,)).fetchone()
            return dict(row)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _file_hash(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def blob_info(self, sha256):
        valid_hash(sha256)
        with self._connect() as db:
            row = db.execute("SELECT sha256,size,media_type FROM blobs WHERE sha256=?", (sha256,)).fetchone()
        if row is None:
            raise KeyError("Blob not found")
        return dict(row)

    def blob_path(self, sha256):
        self.blob_info(sha256)
        path = self.blobs / sha256[:2] / sha256
        if not path.is_file():
            raise KeyError("Blob content is missing")
        return path

    def create_asset(self, kind, name, metadata=None, blob_hash=None, asset_id=None):
        identifier = valid_id(asset_id or str(uuid.uuid4()))
        metadata = {} if metadata is None else metadata
        self._validate_fields(kind, name, metadata, blob_hash)
        timestamp = now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM assets WHERE id=?", (identifier,)).fetchone():
                raise ValueError("Asset already exists")
            self._require_blob(db, blob_hash)
            db.execute("INSERT INTO assets VALUES (?,1,?,?,?,?,?,?)", (identifier, kind, name, json_text(metadata), blob_hash, timestamp, timestamp))
        return self.get_asset(identifier)

    @staticmethod
    def _validate_fields(kind, name, metadata, blob_hash):
        if kind not in KINDS:
            raise ValueError("Unsupported asset kind")
        if not isinstance(name, str) or not name.strip() or len(name) > 1000:
            raise ValueError("Asset name must contain 1–1000 characters")
        if not isinstance(metadata, dict):
            raise ValueError("Asset metadata must be an object")
        if len(json_text(metadata).encode("utf-8")) > 10 * 1024 ** 2:
            raise ValueError("Asset metadata is too large")
        if blob_hash is not None:
            valid_hash(blob_hash)

    @staticmethod
    def _require_blob(db, blob_hash):
        if blob_hash is not None and not db.execute("SELECT 1 FROM blobs WHERE sha256=?", (blob_hash,)).fetchone():
            raise ValueError("Referenced blob does not exist")

    def get_asset(self, id, revision=None):
        valid_id(id)
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ValueError("Revision must be a positive integer")
        with self._connect() as db:
            if revision is None:
                row = db.execute("SELECT * FROM assets WHERE id=? ORDER BY revision DESC LIMIT 1", (id,)).fetchone()
            else:
                row = db.execute("SELECT * FROM assets WHERE id=? AND revision=?", (id, revision)).fetchone()
        if row is None:
            raise KeyError("Asset or revision not found")
        return self._asset(row)

    def revise_asset(self, id, expected_revision, patch):
        valid_id(id)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        if not isinstance(patch, dict) or not patch or set(patch) - {"name", "metadata", "blob_hash"}:
            raise ValueError("Patch must contain name, metadata, or blob_hash only")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM assets WHERE id=? ORDER BY revision DESC LIMIT 1", (id,)).fetchone()
            if row is None:
                raise KeyError("Asset not found")
            current = self._asset(row)
            if current["revision"] != expected_revision:
                raise ValueError(f"Revision conflict: expected {expected_revision}, current {current['revision']}")
            revised = {**current, **patch, "revision": expected_revision + 1, "updated_at": now()}
            self._validate_fields(revised["kind"], revised["name"], revised["metadata"], revised["blob_hash"])
            self._require_blob(db, revised["blob_hash"])
            db.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)", tuple(json_text(revised[k]) if k == "metadata" else revised[k] for k in ("id", "revision", "kind", "name", "metadata", "blob_hash", "created_at", "updated_at")))
        return revised

    def list_assets(self, kind=None, query=None, status=None):
        if kind is not None and kind not in KINDS:
            raise ValueError("Unsupported asset kind")
        with self._connect() as db:
            rows = db.execute("SELECT a.* FROM assets a JOIN (SELECT id,MAX(revision) revision FROM assets GROUP BY id) latest USING(id,revision) ORDER BY a.created_at,a.id").fetchall()
        assets = [self._asset(row) for row in rows]
        if kind is not None:
            assets = [a for a in assets if a["kind"] == kind]
        if status is not None:
            assets = [a for a in assets if a["metadata"].get("status") == status]
        if query:
            tokens = str(query).casefold().split()
            assets = [a for a in assets if all(token in (a["name"] + " " + json_text(a["metadata"])).casefold() for token in tokens)]
        return assets

    def add_relation(self, subject_id, object_id, predicate, metadata=None):
        self.get_asset(subject_id)
        self.get_asset(object_id)
        if not isinstance(predicate, str) or not predicate.strip() or len(predicate) > 200:
            raise ValueError("Invalid relation predicate")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Relation metadata must be an object")
        relation = {"id": str(uuid.uuid4()), "subject_id": subject_id, "object_id": object_id, "predicate": predicate, "metadata": metadata or {}, "created_at": now()}
        with self._connect() as db:
            db.execute("INSERT INTO relations VALUES (?,?,?,?,?,?)", (relation["id"], subject_id, object_id, predicate, json_text(relation["metadata"]), relation["created_at"]))
        return relation

    def relations(self, asset_id):
        self.get_asset(asset_id)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM relations WHERE subject_id=? OR object_id=? ORDER BY created_at,id", (asset_id, asset_id)).fetchall()
        return [self._asset(row) for row in rows]

    def export_bundle(self, destination):
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("BEGIN")
            assets = [self._asset(row) for row in db.execute("SELECT * FROM assets ORDER BY id,revision")]
            relations = [self._asset(row) for row in db.execute("SELECT * FROM relations ORDER BY id")]
            blobs = [dict(row) for row in db.execute("SELECT * FROM blobs ORDER BY sha256")]
        manifest = {"format": "broll-assets", "version": 1, "exported_at": now(), "assets": assets, "relations": relations, "blobs": blobs}
        fd, temporary = tempfile.mkstemp(prefix=".bundle-", suffix=".zip", dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                archive.writestr("manifest.json", json_text(manifest))
                for blob in blobs:
                    path = self.blob_path(blob["sha256"])
                    if self._file_hash(path) != blob["sha256"]:
                        raise ValueError("Cannot export corrupt blob")
                    archive.write(path, "blobs/" + blob["sha256"])
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return manifest

    def restore_bundle(self, source):
        try:
            return self._restore_bundle(source)
        except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
            raise ValueError("Invalid asset bundle") from exc

    def _restore_bundle(self, source):
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise ValueError("Bundle manifest missing or duplicate entries")
            if archive.getinfo("manifest.json").file_size > 50 * 1024 ** 2:
                raise ValueError("Bundle manifest exceeds limit")
            if sum(i.file_size for i in archive.infolist()) > MAX_BUNDLE_BYTES:
                raise ValueError("Bundle exceeds size limit")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != "broll-assets" or manifest.get("version") != 1:
                raise ValueError("Unsupported asset bundle format")
            for key in ("assets", "relations", "blobs"):
                if not isinstance(manifest.get(key), list):
                    raise ValueError("Invalid bundle manifest")
            blob_records = manifest["blobs"]
            expected_names = {"manifest.json"}
            blob_hashes = set()
            for blob in blob_records:
                valid_hash(blob["sha256"])
                if blob["sha256"] in blob_hashes or type(blob["size"]) is not int or blob["size"] < 0:
                    raise ValueError("Invalid or duplicate blob record")
                blob_hashes.add(blob["sha256"])
                expected_names.add("blobs/" + blob["sha256"])
                if archive.getinfo("blobs/" + blob["sha256"]).file_size != blob["size"]:
                    raise ValueError("Bundle blob size mismatch")
            if set(names) != expected_names:
                raise ValueError("Unexpected or missing bundle files")
            # Validate records and revision continuity before committing any database state.
            revisions = {}
            for asset in manifest["assets"]:
                if not isinstance(asset, dict) or set(asset) != {"id", "revision", "kind", "name", "metadata", "blob_hash", "created_at", "updated_at"}:
                    raise ValueError("Invalid asset record")
                valid_id(asset["id"])
                self._validate_fields(asset["kind"], asset["name"], asset["metadata"], asset["blob_hash"])
                if not all(isinstance(asset[key], str) and asset[key] for key in ("created_at", "updated_at")):
                    raise ValueError("Invalid asset timestamps")
                if type(asset["revision"]) is not int or asset["revision"] < 1:
                    raise ValueError("Invalid asset revision")
                if asset["blob_hash"] is not None and asset["blob_hash"] not in blob_hashes:
                    raise ValueError("Asset references missing blob")
                revisions.setdefault(asset["id"], []).append(asset["revision"])
            if any(sorted(items) != list(range(1, len(items) + 1)) for items in revisions.values()):
                raise ValueError("Bundle must contain complete, unique revision history")
            for relation in manifest["relations"]:
                valid_id(relation["id"])
                if relation["subject_id"] not in revisions or relation["object_id"] not in revisions:
                    raise ValueError("Relation references missing asset")
                if not isinstance(relation["metadata"], dict) or not isinstance(relation["predicate"], str) or not relation["predicate"].strip():
                    raise ValueError("Invalid bundle relation")
                json_text(relation["metadata"])
            with tempfile.TemporaryDirectory(prefix="restore-", dir=self.root) as temp:
                staged = []
                for blob in blob_records:
                    path = Path(temp) / blob["sha256"]
                    with archive.open("blobs/" + blob["sha256"]) as stream, path.open("wb") as target:
                        shutil.copyfileobj(stream, target, 1024 * 1024)
                    if self._file_hash(path) != blob["sha256"]:
                        raise ValueError("Bundle SHA256 mismatch")
                    staged.append((blob, path))
                # Content-addressed blobs can safely exist before the atomic metadata transaction.
                for blob, path in staged:
                    self.put_blob(path, blob["media_type"])
                imported = 0
                with self._connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    for asset in sorted(manifest["assets"], key=lambda a: (a["id"], a["revision"])):
                        existing = db.execute("SELECT * FROM assets WHERE id=? AND revision=?", (asset["id"], asset["revision"])).fetchone()
                        if existing:
                            if self._asset(existing) != asset:
                                raise ValueError("Restore conflict: immutable asset revision differs")
                            continue
                        previous = db.execute("SELECT * FROM assets WHERE id=? ORDER BY revision DESC LIMIT 1", (asset["id"],)).fetchone()
                        if previous and (previous["kind"] != asset["kind"] or previous["created_at"] != asset["created_at"]):
                            raise ValueError("Restore conflict: asset identity differs")
                        db.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)", tuple(json_text(asset[k]) if k == "metadata" else asset[k] for k in ("id", "revision", "kind", "name", "metadata", "blob_hash", "created_at", "updated_at")))
                        imported += 1
                    for relation in manifest["relations"]:
                        existing = db.execute("SELECT * FROM relations WHERE id=?", (relation["id"],)).fetchone()
                        if existing and self._asset(existing) != relation:
                            raise ValueError("Restore conflict: relation differs")
                        db.execute("INSERT OR IGNORE INTO relations VALUES (?,?,?,?,?,?)", tuple(json_text(relation[k]) if k == "metadata" else relation[k] for k in ("id", "subject_id", "object_id", "predicate", "metadata", "created_at")))
                return {"assets": len(revisions), "revisions_imported": imported, "blobs": len(blob_records), "relations": len(manifest["relations"])}
