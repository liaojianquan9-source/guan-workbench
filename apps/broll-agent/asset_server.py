"""Local HTTP asset service. Run: python3 asset_server.py --root ~/Documents/BrollAssets."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import parse_qs, unquote, urlsplit

from asset_store import AssetStore, MAX_BUNDLE_BYTES

MAX_UPLOAD_BYTES = MAX_BUNDLE_BYTES
MAX_JSON_BYTES = 12 * 1024 ** 2
LOOPBACK_NAMES = {"127.0.0.1", "localhost", "[::1]", "::1"}


class AssetHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, allowed_origins=None):
        self.store = store
        self.allowed_origins = set(allowed_origins or ())
        super().__init__(address, AssetHandler)
        port = self.server_address[1]
        self.allowed_origins.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}", "http://127.0.0.1:4183", "http://localhost:4183"})


class AssetHandler(BaseHTTPRequestHandler):
    server: AssetHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def end_headers(self):
        origin = self.headers.get("Origin")
        if origin in self.server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def _json(self, status, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _validate_request(self):
        try:
            host = urlsplit("http://" + self.headers.get("Host", ""))
            if host.hostname not in LOOPBACK_NAMES or host.port != self.server.server_address[1] or host.username or host.password:
                raise ValueError("Invalid Host")
        except ValueError:
            self.close_connection = True
            self._json(403, {"error": "Host is not this local asset service"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.allowed_origins:
            self.close_connection = True
            self._json(403, {"error": "Cross-site asset access is not allowed"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.close_connection = True
            self._json(403, {"error": "Cross-site asset access is not allowed"})
            return False
        return True

    def _length(self, maximum):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked requests are not supported; provide Content-Length")
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0 or length > maximum:
            raise ValueError("Missing Content-Length or request exceeds size limit")
        return length

    def _read_json(self):
        length = self._length(MAX_JSON_BYTES)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Incomplete request body")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON request") from exc
        if not isinstance(value, dict):
            raise ValueError("Request body must be an object")
        return value

    def _receive_file(self, action):
        length = self._length(MAX_UPLOAD_BYTES)
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=self.server.store.root)
        try:
            with os.fdopen(fd, "wb") as target:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Incomplete upload")
                    target.write(chunk)
                    remaining -= len(chunk)
            return action(Path(temporary))
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _file(self, path, content_type, sha=None, allow_range=True):
        size = Path(path).stat().st_size
        first, last, partial = 0, size - 1, False
        range_header = self.headers.get("Range") if allow_range else None
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or not any(match.groups()) or size == 0:
                self._range_error(size)
                return
            start, end = match.groups()
            if start:
                first = int(start)
                last = int(end) if end else size - 1
                if first >= size or first > last:
                    self._range_error(size)
                    return
                last = min(last, size - 1)
            else:
                if int(end) < 1:
                    self._range_error(size)
                    return
                first = max(0, size - int(end))
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(max(0, last - first + 1)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
        if sha:
            self.send_header("ETag", '"' + sha + '"')
            self.send_header("Cache-Control", "private, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-store")
        if partial:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with Path(path).open("rb") as stream:
            stream.seek(first)
            remaining = max(0, last - first + 1)
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _range_error(self, size):
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _dispatch(self):
        if not self._validate_request():
            return
        self.connection.settimeout(120)
        parsed = urlsplit(self.path)
        parts = [unquote(p) for p in parsed.path.split("/") if p]
        query = parse_qs(parsed.query)
        method = "GET" if self.command == "HEAD" else self.command
        store = self.server.store
        if parts == ["health"] and method == "GET":
            return self._json(200, {"status": "ok", "service": "broll-assets", "schema_version": 1})
        if parts == ["v1", "assets"]:
            if method == "GET":
                return self._json(200, {"assets": store.list_assets(**{key: query[key][0] for key in ("kind", "query", "status") if key in query})})
            if method == "POST":
                data = self._read_json()
                return self._json(201, {"asset": store.create_asset(**data)})
        if len(parts) >= 3 and parts[:2] == ["v1", "assets"]:
            if len(parts) == 3 and method == "GET":
                return self._json(200, {"asset": store.get_asset(parts[2])})
            if len(parts) == 5 and parts[3] == "revisions" and method == "GET":
                return self._json(200, {"asset": store.get_asset(parts[2], int(parts[4]))})
            if len(parts) == 3 and method == "PATCH":
                data = self._read_json()
                return self._json(200, {"asset": store.revise_asset(parts[2], data["expected_revision"], data["patch"])})
        if parts == ["v1", "relations"]:
            if method == "POST":
                return self._json(201, {"relation": store.add_relation(**self._read_json())})
            if method == "GET":
                if "asset_id" not in query:
                    raise ValueError("asset_id is required")
                return self._json(200, {"relations": store.relations(query["asset_id"][0])})
        if parts == ["v1", "blobs"] and method == "POST":
            blob = self._receive_file(lambda path: store.put_blob(path, self.headers.get("Content-Type", "application/octet-stream")))
            return self._json(201, blob)
        if len(parts) == 3 and parts[:2] == ["v1", "blobs"] and method == "GET":
            info = store.blob_info(parts[2])
            return self._file(store.blob_path(parts[2]), info["media_type"], parts[2])
        if parts == ["v1", "export"] and method == "GET":
            with tempfile.TemporaryDirectory(prefix="export-", dir=store.root) as directory:
                path = Path(directory) / "assets.zip"
                store.export_bundle(path)
                return self._file(path, "application/zip", allow_range=False)
        if parts == ["v1", "restore"] and method == "POST":
            return self._json(200, self._receive_file(store.restore_bundle))
        self._json(404, {"error": "Route not found"})

    def _handle(self):
        try:
            self._dispatch()
        except KeyError as exc:
            self.close_connection = True
            self._json(404, {"error": str(exc).strip("'")})
        except (TypeError, ValueError) as exc:
            self.close_connection = True
            self._json(409 if "conflict" in str(exc).lower() else 400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            self._json(500, {"error": "Asset service operation failed"})

    do_GET = _handle
    do_HEAD = _handle
    do_POST = _handle
    do_PATCH = _handle

    def do_OPTIONS(self):
        if not self._validate_request():
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="Independent shared B-roll asset service")
    parser.add_argument("--root", default=os.environ.get("BROLL_ASSET_ROOT", str(Path.home() / "Documents" / "BrollAssets")))
    parser.add_argument("--port", type=int, default=4184)
    parser.add_argument("--allow-origin", action="append", default=[])
    args = parser.parse_args()
    server = AssetHTTPServer(("127.0.0.1", args.port), AssetStore(args.root), args.allow_origin)
    print(f"B-roll assets: http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
