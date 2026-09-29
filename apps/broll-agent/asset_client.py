"""HTTP-only consumer of the independent asset service."""
from __future__ import annotations

import hashlib
import http.client
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlencode, urlsplit
import zipfile


class AssetClient:
    def __init__(self, base_url="http://127.0.0.1:4184", cache_root=None, timeout=120):
        self.base_url = base_url.rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("Asset service URL must be an HTTP(S) origin")
        self._url = parsed
        self.timeout = timeout
        namespace = hashlib.sha256(self.base_url.encode()).hexdigest()[:16]
        self.cache_root = Path(cache_root or (Path.home() / ".cache" / "broll-assets" / namespace)).expanduser().resolve()

    def _connection(self):
        cls = http.client.HTTPSConnection if self._url.scheme == "https" else http.client.HTTPConnection
        return cls(self._url.hostname, self._url.port, timeout=self.timeout)

    def _request(self, method, path, data=None, file_path=None, destination=None, media_type=None):
        headers, body = {}, None
        if file_path is not None:
            file_path = Path(file_path)
            if not file_path.is_file():
                raise ValueError("Upload source is not a regular file")
            headers = {"Content-Type": media_type or "application/octet-stream", "Content-Length": str(file_path.stat().st_size)}
            body = file_path.open("rb")
        elif data is not None:
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        connection = self._connection()
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            if response.status >= 400:
                payload = response.read(65536)
                try:
                    error = json.loads(payload).get("error", "Asset service request failed")
                except ValueError:
                    error = f"Asset service HTTP {response.status}"
                if response.status == 404:
                    raise KeyError(error)
                raise ValueError(error)
            if destination is not None:
                destination = Path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
                try:
                    with os.fdopen(fd, "wb") as target:
                        while chunk := response.read(1024 * 1024):
                            target.write(chunk)
                    os.replace(temporary, destination)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                return destination
            return json.loads(response.read())
        finally:
            if file_path is not None:
                body.close()
            connection.close()

    def health(self):
        return self._request("GET", "/health")

    def put_blob(self, path, media_type=None):
        return self._request("POST", "/v1/blobs", file_path=path, media_type=media_type or mimetypes.guess_type(str(path))[0])

    def blob_path(self, sha256):
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("Invalid SHA256")
        destination = self.cache_root / sha256
        if destination.is_file() and self._hash(destination) == sha256:
            return destination
        self._request("GET", "/v1/blobs/" + sha256, destination=destination)
        if self._hash(destination) != sha256:
            destination.unlink(missing_ok=True)
            raise ValueError("Downloaded blob failed SHA256 verification")
        return destination

    @staticmethod
    def _hash(path):
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def create_asset(self, kind, name, metadata=None, blob_hash=None, asset_id=None):
        return self._request("POST", "/v1/assets", {"kind": kind, "name": name, "metadata": metadata, "blob_hash": blob_hash, "asset_id": asset_id})["asset"]

    def get_asset(self, id, revision=None):
        path = "/v1/assets/" + quote(str(id), safe="")
        if revision is not None:
            path += "/revisions/" + quote(str(revision), safe="")
        return self._request("GET", path)["asset"]

    def revise_asset(self, id, expected_revision, patch):
        return self._request("PATCH", "/v1/assets/" + quote(str(id), safe=""), {"expected_revision": expected_revision, "patch": patch})["asset"]

    def list_assets(self, kind=None, query=None, status=None):
        params = {key: value for key, value in {"kind": kind, "query": query, "status": status}.items() if value is not None}
        return self._request("GET", "/v1/assets?" + urlencode(params))["assets"]

    def add_relation(self, subject_id, object_id, predicate, metadata=None):
        return self._request("POST", "/v1/relations", {"subject_id": subject_id, "object_id": object_id, "predicate": predicate, "metadata": metadata})["relation"]

    def relations(self, asset_id):
        return self._request("GET", "/v1/relations?" + urlencode({"asset_id": asset_id}))["relations"]

    def export_bundle(self, destination):
        self._request("GET", "/v1/export", destination=destination)
        with zipfile.ZipFile(destination) as archive:
            return json.loads(archive.read("manifest.json"))

    def restore_bundle(self, source):
        return self._request("POST", "/v1/restore", file_path=source, media_type="application/zip")
