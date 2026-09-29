#!/usr/bin/env python3
"""Local video analysis workbench. Python standard library + ffmpeg/ffprobe only."""

from __future__ import annotations

import argparse
from array import array
import copy
import csv
import fcntl
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import signal
import socket
import stat
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit
import uuid
import zipfile
from xml.sax.saxutils import escape as xml_escape
from storage import StorageManager, portable_project, configured_directory
from runtime_env import check_python_runtime, check_whisper_runtime, configured_python

ROOT = Path(__file__).resolve().parent
PRESET_MEDIA_ROOT = (ROOT / "public" / "ai-presets").resolve()
PRESET_MEDIA_FILES = {
    *{f"shot-{number:03d}.mp4" for number in range(1, 8)},
    "case-001-title.jpg", "case-001-parameter.jpg", "case-001-moon.jpg",
    "case-002-problem.png", "case-002-article.png", "case-002-prompt.png",
    "case-002-comparison.png",
}
ID_RE = re.compile(r"^[a-f0-9]{32}$")
MAX_UPLOAD = 20 * 1024**3
MAX_JSON = 1024 * 1024
SAFE_INPUT = ["-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi,asf,mpeg,mpegts,flv,ogg,mp3,wav,aac,flac,aiff"]
PROJECT_SCHEMA_VERSION = 1
PROJECT_BACKUP = ".project.json.backup"
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "style-src-elem 'self'; style-src-attr 'unsafe-inline'; img-src 'self' https: data:; "
    "media-src 'self'; connect-src 'self'; frame-src 'none'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class LibraryInUseError(RuntimeError):
    """Raised before any library data is read when another workbench owns it."""


class ProjectVersionError(RuntimeError):
    """A valid record from a newer application must never be downgraded."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid() -> str:
    return uuid.uuid4().hex


def memory_usage_snapshot(root_pid: int | None = None, *, process_rows: str | None = None,
                          total_memory_bytes: int | None = None) -> dict:
    """Return current RSS for this process and all descendants.

    The workbench deliberately uses operating-system data instead of an optional
    Python package so the status remains available before any AI environment is
    repaired.  ``process_rows`` and ``total_memory_bytes`` are injectable to keep
    the process-tree accounting deterministic in tests.
    """
    root_pid = int(root_pid or os.getpid())
    sampler_pid = None
    try:
        if total_memory_bytes is None:
            total_memory_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        if process_rows is None:
            ps = Path("/bin/ps")
            if not ps.is_file():
                ps = Path("/usr/bin/ps")
            sampler = subprocess.Popen(
                [str(ps), "-axo", "pid=,ppid=,rss="],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            sampler_pid = sampler.pid
            try:
                process_rows, _ = sampler.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                sampler.kill()
                sampler.communicate()
                raise
            if sampler.returncode != 0:
                raise OSError("process list unavailable")

        rss_by_pid: dict[int, int] = {}
        children: dict[int, list[int]] = {}
        for row in process_rows.splitlines():
            fields = row.split()
            if len(fields) != 3:
                continue
            try:
                pid, parent_pid, rss_kib = (int(value) for value in fields)
            except ValueError:
                continue
            if pid <= 0 or parent_pid < 0 or rss_kib < 0:
                continue
            rss_by_pid[pid] = rss_kib * 1024
            children.setdefault(parent_pid, []).append(pid)

        if root_pid not in rss_by_pid or not total_memory_bytes or total_memory_bytes <= 0:
            raise OSError("memory sample unavailable")
        included: set[int] = set()
        pending = [root_pid]
        while pending:
            pid = pending.pop()
            if pid in included:
                continue
            included.add(pid)
            pending.extend(children.get(pid, ()))
        if sampler_pid is not None:
            included.discard(sampler_pid)
        used = sum(rss_by_pid.get(pid, 0) for pid in included)
        return {
            "available": True,
            "memory_bytes": used,
            "total_memory_bytes": total_memory_bytes,
            "memory_percent": round(used * 100 / total_memory_bytes, 3),
            "process_count": len(included),
            "scope": "workbench_and_children",
            "measurement": "rss_sum",
            "sampled_at": now(),
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return {
            "available": False,
            "memory_bytes": None,
            "total_memory_bytes": total_memory_bytes if isinstance(total_memory_bytes, int) else None,
            "memory_percent": None,
            "process_count": 0,
            "scope": "workbench_and_children",
            "measurement": "rss_sum",
            "sampled_at": now(),
        }


def valid_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise APIError(404, "项目或镜头不存在。")
    return value


def number(value, label: str) -> float:
    if isinstance(value, bool):
        raise APIError(400, f"{label}必须是有效数字。")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise APIError(400, f"{label}必须是有效数字。") from None
    if not math.isfinite(result):
        raise APIError(400, f"{label}必须是有效数字。")
    return result


def fsync_directory(path: Path):
    """Make preceding creates, renames and unlinks durable across a power loss."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: dict, *, backup=False):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    temp = path.with_name(f".{path.name}.{uid()}.tmp")
    backup_temp = None
    try:
        if backup:
            backup_path = path.with_name(PROJECT_BACKUP)
            previous = data
            if path.is_file():
                try:
                    candidate = path.read_bytes()
                    if isinstance(json.loads(candidate), dict):
                        previous = candidate
                except (OSError, ValueError, UnicodeDecodeError):
                    # Never replace a known-good backup with a corrupt primary.
                    previous = None
            if previous is not None:
                backup_temp = path.with_name(f".{backup_path.name}.{uid()}.tmp")
                with backup_temp.open("wb") as file:
                    file.write(previous)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(backup_temp, backup_path)
                fsync_directory(path.parent)
        with temp.open("wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
        fsync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)
        if backup_temp is not None:
            backup_temp.unlink(missing_ok=True)


def shot_ranges(duration: float, candidates: list[float], min_duration: float):
    """Filter cut times, including a too-short final shot, and cover the full video."""
    boundaries = [0.0]
    for candidate in sorted(set(candidates)):
        if not math.isfinite(candidate):
            continue
        if candidate - boundaries[-1] >= min_duration and duration - candidate >= min_duration:
            boundaries.append(candidate)
    boundaries.append(duration)
    return list(zip(boundaries, boundaries[1:]))


def subtitle_clock(seconds: float, separator=",") -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{milliseconds:03}"


def overlap_subtitles(project: dict, shot: dict) -> str:
    return " ".join(segment["text"].strip() for segment in project.get("transcript", {}).get("segments", [])
                    if segment["start"] < shot["end"] and segment["end"] > shot["start"])


def clean_xml(text: str) -> str:
    return xml_escape("".join(char for char in str(text) if char in "\t\r\n" or ord(char) >= 32))


def word_paragraph(text: str, *, bold=False, size=20) -> str:
    paragraphs = []
    for line in str(text).split("\n"):
        paragraphs.append(f'<w:p><w:pPr><w:spacing w:after="70"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Arial" w:eastAsia="PingFang SC"/>'
                          f'{"<w:b/>" if bold else ""}<w:sz w:val="{size}"/></w:rPr><w:t xml:space="preserve">{clean_xml(line)}</w:t></w:r></w:p>')
    return "".join(paragraphs)


def storyboard_docx(project: dict, directory: Path) -> bytes:
    """A portable DOCX package with actual images and subtitles overlapping each shot."""
    columns = [550, 2400, 2100, 650, 650, 4000, 1700, 2700]
    image_width = 1350000
    image_height = round(image_width * project["height"] / project["width"])
    # Tall portrait sources should fit a readable row too.
    if image_height > 2600000:
        image_width = round(image_width * 2600000 / image_height)
        image_height = 2600000
    def cell(width, content, fill=None):
        shading = f'<w:shd w:fill="{fill}"/>' if fill else ""
        return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shading}<w:vAlign w:val="top"/></w:tcPr>{content}</w:tc>'
    headers = ["镜号", "画面", "起止", "长度", "景别", "脚本字幕", "音乐 / 声音", "备注"]
    rows = ['<w:tr><w:trPr><w:tblHeader/></w:trPr>' + "".join(cell(width, word_paragraph(title, bold=True), "E9EDF2")
                                                               for width, title in zip(columns, headers)) + '</w:tr>']
    images = []
    relationships = []
    for index, shot in enumerate(project["shots"], 1):
        image_path = directory / "thumbnails" / f"{valid_id(shot['id'])}.jpg"
        if not image_path.is_file():
            raise APIError(422, f"镜头 {index} 的关键帧文件缺失，暂时无法导出完整 Word 分镜表。")
        filename = f"shot-{index:04}.jpg"
        images.append(("word/media/" + filename, image_path.read_bytes()))
        relationships.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{filename}"/>')
        image_xml = f'''<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
<wp:extent cx="{image_width}" cy="{image_height}"/><wp:docPr id="{index}" name="镜头 {index}"/>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>
<pic:nvPicPr><pic:cNvPr id="{index}" name="{filename}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="rId{index}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{image_width}" cy="{image_height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'''
        timing = f"{subtitle_clock(shot['start'], '.')}\n至 {subtitle_clock(shot['end'], '.')}\n{shot['end'] - shot['start']:.3f} 秒"
        subtitles = overlap_subtitles(project, shot)
        notes = [shot.get('note','')] + [a['text'] for a in project.get('annotations',[]) if shot['start'] <= a['time'] < shot['end']]
        music = [m['title'] + ' — ' + m.get('artist','') for m in project.get('music',{}).get('tracks',[])
                 if not m.get('deleted') and any(shot['start'] <= t < shot['end'] for t in m.get('positions',[m.get('time',0)]))]
        contents = [word_paragraph(str(index)), image_xml, word_paragraph(f"{subtitle_clock(shot['start'], '.')}\n{subtitle_clock(shot['end'], '.')}",size=16),
                    word_paragraph(f"{shot['end']-shot['start']:.2f}s",size=16), word_paragraph(''),
                    word_paragraph(subtitles), word_paragraph('\n'.join(music)), word_paragraph('\n'.join(n for n in notes if n))]
        rows.append('<w:tr>' + ''.join(cell(width,content) for width,content in zip(columns,contents)) + '</w:tr>')
    intro = word_paragraph(project["name"], bold=True, size=32)
    intro += word_paragraph(f"分镜表 · {len(project['shots'])} 个镜头 · 画面时长 {project['duration']:.3f} 秒")
    intro += word_paragraph("字幕按与镜头重叠的时间段归入。自动识别的切点与字幕需人工核对。", size=18)
    borders = ''.join(f'<w:{side} w:val="single" w:sz="4" w:color="C8CED7"/>' for side in ["top", "left", "bottom", "right", "insideH", "insideV"])
    table = '<w:tbl><w:tblPr><w:tblW w:w="14750" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>' + borders + '</w:tblBorders>'
    table += '<w:tblCellMar><w:top w:w="90" w:type="dxa"/><w:left w:w="90" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar></w:tblPr>'
    table += '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{width}"/>' for width in columns) + '</w:tblGrid>' + ''.join(rows) + '</w:tbl>'
    document = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>'''
    document += intro + table + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/><w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720"/></w:sectPr></w:body></w:document>'
    types = '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="jpg" ContentType="image/jpeg"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
    package_rels = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    document_rels = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(relationships) + '</Relationships>'
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, content in [("[Content_Types].xml", types), ("_rels/.rels", package_rels),
                              ("word/document.xml", document), ("word/_rels/document.xml.rels", document_rels), *images]:
            package.writestr(name, content)
    return result.getvalue()


from research_clips import ResearchClips
from music_sections import MusicSections
from playback_proxies import PlaybackProxies


class ProjectStore:
    def __init__(self, data_dir: Path, ffmpeg: str | None = None, ffprobe: str | None = None,
                 detector: str = "transnetv2", detector_python: Path | None = None,
                 asr_python: Path | None = None, asr_script: Path | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._library_locks_guard = threading.Lock()
        self._library_locks = {}
        initial_lock = self.acquire_library_lock(self.data_dir)
        self._library_locks[self.data_dir] = initial_lock
        try:
            self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
            self.ffprobe = ffprobe or shutil.which("ffprobe")
            self.detector = detector
            self.detector_python = detector_python or ROOT / ".venv" / "bin" / "python"
            self.asr_python = asr_python
            self.asr_script = asr_script or ROOT / "tools" / "transcribe.py"
            self.locks_guard = threading.Lock()
            self.locks: dict[str, threading.RLock] = {}
            self.jobs: dict[str, threading.Thread] = {}
            self.research = ResearchClips(self, APIError, number, SAFE_INPUT, ROOT)
            self.sections = MusicSections(self, APIError, number, ROOT)
            self.process_guard = threading.Lock()
            self.processes: set[subprocess.Popen] = set()
            self.stopping = False
            self.storage = StorageManager(self, APIError)
            self.detector_slot = threading.Semaphore(1)
            self.waveform_guard = threading.Lock()
            self.preview_guard = threading.Lock()
            self.music_lock = threading.RLock()
            self.system_usage_guard = threading.Lock()
            self._system_usage_cache = None
            self.playback = PlaybackProxies(self, APIError, SAFE_INPUT)
            # A stopped process cannot finish its old jobs. Keep its original shots intact.
            for file in self.data_dir.glob("*/project.json"):
                try:
                    project = self._load_project_file(file, file.parent.name)
                    interrupted = False
                    if project.get("status") == "processing":
                        project.update(status="error", message="上次分析被中断，可重新开始分析。", progress=0)
                        interrupted = True
                    transcript = project.get("transcript", {})
                    if transcript.get("status") == "processing":
                        transcript.update(status="error", message="上次字幕识别被中断，可重新识别；已有字幕已保留。", progress=0)
                        interrupted = True
                    music = project.get('music', {})
                    if music.get('status') == 'processing':
                        music.update(status='error', message='上次识曲已中断，可重试；已有结果已保留。')
                        interrupted = True
                    sections = project.get('music_sections', {})
                    if sections.get('status') in {'processing', 'waiting_audio'}:
                        sections.update(status='error', message='上次音乐分段中断，可重试。')
                        interrupted = True
                    for section in sections.get('sections', []):
                        if section.get('recognition', {}).get('status') in {'queued', 'processing'}:
                            section['recognition'].update(status='error', message='上次识曲中断，可重试。')
                            interrupted = True
                    for clip in [*project.get('research_clips', []), *([project['source_audio']] if project.get('source_audio') else [])]:
                        if clip.get('sound', {}).get('status') in {'queued', 'processing'}:
                            clip['sound'].update(status='error', message='上次声音处理已中断，可重试；原音仍可回听。')
                            interrupted = True
                    if interrupted:
                        project["updated_at"] = now()
                        project["revision"] = project.get("revision", 0) + 1
                        atomic_json(file, project, backup=True)
                except (OSError, ValueError):
                    continue
        except Exception:
            self.release_library_locks()
            raise

    @staticmethod
    def acquire_library_lock(directory: Path):
        directory = Path(directory).resolve()
        lock_path = directory / ".workbench.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as error:
            raise LibraryInUseError("资料库锁文件不安全或无法打开，请保留现场并检查 .workbench.lock。") from error
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (hasattr(os, "getuid") and info.st_uid != os.getuid()) or info.st_size > 16 * 1024):
                raise OSError("unsafe lock file")
            os.fchmod(descriptor, 0o600)
            lock_file = os.fdopen(descriptor, "r+", encoding="utf-8")
        except Exception as error:
            os.close(descriptor)
            raise LibraryInUseError("资料库锁文件不安全，已停止打开以避免损坏其他文件。") from error
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.seek(0)
            try:
                owner = json.loads(lock_file.read() or "{}")
                detail = f"（进程 {int(owner['pid'])}）" if owner.get("pid") else ""
            except (ValueError, TypeError, KeyError):
                detail = ""
            lock_file.close()
            raise LibraryInUseError(
                f"资料库已由另一个拉片工作台打开{detail}。请回到已打开的窗口，或先正常退出后再试。"
            ) from None
        try:
            lock_file.seek(0)
            lock_file.truncate()
            json.dump({"pid": os.getpid(), "started_at": now(), "directory": str(directory)}, lock_file,
                      ensure_ascii=False)
            lock_file.flush()
            os.fsync(lock_file.fileno())
            fsync_directory(directory)
        except Exception:
            ProjectStore.release_library_lock(lock_file)
            raise
        return lock_file

    @staticmethod
    def release_library_lock(lock_file):
        if lock_file is None or lock_file.closed:
            return
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()

    def adopt_library_directory(self, directory: Path, lock_file):
        directory = Path(directory).resolve()
        with self._library_locks_guard:
            self._library_locks[directory] = lock_file
            self.data_dir = directory

    def release_library_locks(self):
        with self._library_locks_guard:
            locks = list(self._library_locks.values())
            self._library_locks.clear()
        for lock_file in locks:
            self.release_library_lock(lock_file)

    def lock(self, project_id: str):
        valid_id(project_id)
        with self.locks_guard:
            return self.locks.setdefault(project_id, threading.RLock())

    def directory(self, project_id: str) -> Path:
        return self.data_dir / valid_id(project_id)

    def read(self, project_id: str) -> dict:
        with self.lock(project_id):
            try:
                path = self.directory(project_id) / "project.json"
                project = self._load_project_file(path, project_id)
                return portable_project(project)
            except FileNotFoundError:
                raise APIError(404, "找不到这个项目。") from None
            except ProjectVersionError:
                raise APIError(500, "这个项目由更新版本的拉片工作台创建，请升级后再打开。") from None
            except (OSError, ValueError):
                raise APIError(500, "项目记录无法读取，请保留 data 目录以便恢复。") from None

    def _load_project_file(self, path: Path, expected_id: str) -> dict:
        def decode(candidate: Path):
            value = json.loads(candidate.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("id") != expected_id or not isinstance(value.get("shots"), list):
                raise ValueError("invalid project record")
            version = value.get("schema_version", 0)
            if type(version) is not int or version < 0:
                raise ValueError("invalid project schema version")
            if version > PROJECT_SCHEMA_VERSION:
                raise ProjectVersionError("project was created by a newer workbench")
            changed = self.normalize(value)
            if version < PROJECT_SCHEMA_VERSION:
                value["schema_version"] = PROJECT_SCHEMA_VERSION
                changed = True
            return value, changed

        recovered = False
        try:
            project, migrated = decode(path)
        except (OSError, ValueError, UnicodeDecodeError, TypeError, KeyError) as primary_error:
            backup_path = path.with_name(PROJECT_BACKUP)
            try:
                project, migrated = decode(backup_path)
            except (OSError, ValueError, UnicodeDecodeError, TypeError, KeyError):
                raise primary_error
            corrupt = path.with_name(f".project.json.corrupt-{uid()}")
            try:
                os.replace(path, corrupt)
                fsync_directory(path.parent)
            except FileNotFoundError:
                pass
            atomic_json(path, project, backup=True)
            recovered = True
        if migrated and not recovered:
            # Schema-only migrations preserve the user's edit revision and timestamp.
            atomic_json(path, project, backup=True)
        return project

    @staticmethod
    def normalize(project):
        changed = False

        def default(key, value):
            nonlocal changed
            if key not in project:
                project[key] = copy.deepcopy(value)
                changed = True

        default("research_clips", [])
        default("captures", [])
        default("audio_clips", [])
        default("transcript", {"status": "idle", "progress": 0, "message": "尚未识别字幕。", "segments": [], "engine": ""})
        default('tags', [])
        default('source', {})
        default('metadata_revision', 0)
        default('annotations', [])
        default('exports', [])
        default('music', {'status':'idle','progress':0,'message':'尚未识别音乐。','tracks':[]})
        for field in ['captures','audio_clips','exports']:
            for item in project[field]:
                if 'asset_revision' not in item:
                    item['asset_revision'] = 0
                    changed = True
                if 'tags' not in item:
                    item['tags'] = [item['tag']] if item.get('tag') else []
                    changed = True
        for shot in project["shots"]:
            if "annotation_revision" not in shot:
                shot["annotation_revision"] = 0
                changed = True
        return changed

    def write(self, project: dict):
        portable_project(project, clone=False)
        self.normalize(project)
        project["schema_version"] = PROJECT_SCHEMA_VERSION
        project["revision"] = project.get("revision", 0) + 1
        project["updated_at"] = now()
        atomic_json(self.directory(project["id"]) / "project.json", project, backup=True)

    def list(self) -> list[dict]:
        projects = []
        for path in self.data_dir.glob("*/project.json"):
            try:
                project = self.read(path.parent.name)
                if not project.get('removed'): projects.append(project)
            except APIError:
                continue
        return sorted(projects, key=lambda project: project["updated_at"], reverse=True)

    def require_tools(self):
        if not self.ffmpeg or not self.ffprobe:
            raise APIError(503, "本机缺少 FFmpeg 或 ffprobe，暂时无法处理视频。")

    def spawn(self, command, **kwargs):
        with self.process_guard:
            if self.stopping:
                raise APIError(503, "本地服务正在停止，请稍后重新打开。")
            process = subprocess.Popen(command, start_new_session=True, **kwargs)
            self.processes.add(process)
            return process

    def forget(self, process):
        with self.process_guard:
            self.processes.discard(process)

    def terminate(self, process):
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        except ProcessLookupError:
            pass

    def run(self, command, *, timeout=45, text=False):
        process = self.spawn(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            self.terminate(process)
            process.communicate()
            raise
        finally:
            self.forget(process)

    def close(self):
        self.begin_shutdown()
        try:
            self.storage.close()
            for thread in list(self.jobs.values()):
                if thread is not threading.current_thread():
                    thread.join(timeout=5)
        finally:
            active_task = self.storage.tasks.get(self.storage.active) if self.storage.active else None
            storage_thread = active_task.get("_thread") if active_task else None
            jobs_stopped = all(not thread.is_alive() for thread in self.jobs.values())
            storage_stopped = ((storage_thread is None or not storage_thread.is_alive())
                               and not self.storage.has_live_writers())
            # Never let another process enter while an old worker can still write.
            # If shutdown is forced, the OS releases these locks when this process exits.
            if jobs_stopped and storage_stopped:
                self.release_library_locks()

    def begin_shutdown(self):
        with self.process_guard:
            self.stopping = True
            running = list(self.processes)
        for process in running:
            self.terminate(process)

    def probe(self, path: Path) -> dict:
        self.require_tools()
        try:
            result = self.run(
                [self.ffprobe, "-v", "error", *SAFE_INPUT, "-show_format", "-show_streams", "-of", "json", str(path)],
                text=True, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise APIError(422, "视频信息读取失败或超时，请换一个完整的视频文件。") from None
        try:
            metadata = json.loads(result.stdout)
            stream = next(item for item in metadata["streams"] if item["codec_type"] == "video"
                          and not item.get("disposition", {}).get("attached_pic"))
            # An audio track can outlast the picture. Do not create shots beyond
            # the selected video stream and then ask FFmpeg for nonexistent frames.
            duration = float(stream.get("duration") or metadata.get("format", {}).get("duration"))
            ratio = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
            top, bottom = ratio.split("/")
            fps = float(top) / float(bottom) if float(bottom) else 0
            width, height = int(stream["width"]), int(stream["height"])
            if result.returncode or not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
                raise ValueError("invalid video")
            if not math.isfinite(fps) or fps <= 0:
                fps = 25.0
            return {"duration": duration, "fps": fps, "width": width, "height": height,
                    "codec": stream.get("codec_name", "unknown"),
                    "pixel_format": stream.get("pix_fmt", "unknown"),
                    "container": metadata.get("format", {}).get("format_name", "unknown"),
                    "audio_codecs": [item.get("codec_name", "unknown") for item in metadata["streams"] if item["codec_type"] == "audio"],
                    "has_audio": any(item["codec_type"] == "audio" for item in metadata["streams"])}
        except (ValueError, KeyError, TypeError, StopIteration):
            raise APIError(422, "没有读到有效视频，请上传完整的视频文件。") from None

    def thumbnail(self, project: dict, shot: dict):
        self.require_tools()
        folder = self.directory(project["id"])
        thumbnails = folder / "thumbnails"
        created = not thumbnails.exists()
        thumbnails.mkdir(exist_ok=True)
        if created: fsync_directory(folder)
        target = thumbnails / f"{shot['id']}.jpg"
        temp = target.with_name(f".{shot['id']}.{uid()}.jpg")
        midpoint = min(shot["start"] + 0.08, (shot["start"] + shot["end"]) / 2)
        try:
            result = self.run(
                [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "2",
                 "-ss", f"{midpoint:.8f}", *SAFE_INPUT, "-i", str(folder / "source.mp4"), "-an",
                 "-frames:v", "1", "-vf", "scale=min(640\\,iw):-2", "-q:v", "3", "-threads", "1", str(temp)],
                timeout=45,
            )
            if result.returncode or not temp.exists() or temp.stat().st_size == 0:
                raise APIError(422, "关键帧提取失败，原始视频和已有记录已保留。")
            os.replace(temp, target)
            fsync_directory(thumbnails)
        except (OSError, subprocess.TimeoutExpired):
            raise APIError(422, "关键帧提取失败或超时，原始视频和已有记录已保留。") from None
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def file_identity(path: Path):
        value = path.stat()
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns

    def source_snapshot(self, project_id: str):
        directory = self.directory(project_id)
        source = directory / "source.mp4"
        return directory, source, self.file_identity(source)

    def validate_source_snapshot(self, project_id: str, directory: Path, source: Path, identity):
        if self.directory(project_id) != directory or self.file_identity(source) != identity:
            raise APIError(409, "项目资料位置已变化，本次生成结果未写入，请重试。")

    def render_capture(self, project_id: str, directory: Path, source: Path, identity,
                       position: float, capture_id: str) -> Path:
        folder = directory / "captures"
        created = not folder.exists()
        folder.mkdir(exist_ok=True)
        if created: fsync_directory(directory)
        target = folder / f"{capture_id}.jpg"
        temp = folder / f".{capture_id}.jpg"
        try:
            result = self.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                               "-threads", "2", *SAFE_INPUT, "-ss", f"{position:.8f}", "-i", str(source),
                               "-an", "-frames:v", "1", "-q:v", "2", "-threads", "1", str(temp)], timeout=45)
            if result.returncode or not temp.is_file() or temp.stat().st_size == 0:
                raise APIError(422, "这个位置的画面未能导出，请移动一点再截图。")
            self.validate_source_snapshot(project_id, directory, source, identity)
            os.replace(temp, target)
            fsync_directory(folder)
            return target
        except subprocess.TimeoutExpired:
            raise APIError(422, "截图处理超时，请重试。") from None
        finally:
            temp.unlink(missing_ok=True)

    def new_shot(self, project_id: str, start: float, end: float) -> dict:
        shot_id = uid()
        return {"id": shot_id, "start": start, "end": end,
                "thumbnail_url": f"/media/{project_id}/thumbnails/{shot_id}.jpg", "note": "", "tag": "", "annotation_revision": 0}

    def import_stream(self, name: str, stream, size: int) -> dict:
        self.require_tools()
        if size <= 0:
            raise APIError(400, "视频文件为空。")
        if size > MAX_UPLOAD:
            raise APIError(413, "单个视频暂时最多支持 20 GB。")
        name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        name = "".join(char for char in name if ord(char) >= 32)[:240]
        if not name:
            raise APIError(400, "请提供视频文件名。")
        project_id = uid()
        folder = self.directory(project_id)
        folder.mkdir()
        temp = folder / "upload.part"
        complete = False
        try:
            remaining = size
            with temp.open("wb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise APIError(400, "视频上传中断，请重新选择文件上传。")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            metadata = self.probe(temp)
            compatible = ("mp4" in metadata["container"].split(",") and metadata["codec"] == "h264"
                          and metadata["pixel_format"] in {"yuv420p", "yuvj420p"}
                          and all(codec == "aac" for codec in metadata["audio_codecs"]))
            original_metadata = dict(metadata)
            if compatible:
                os.replace(temp, folder / "source.mp4")
            else:
                # Retain original bytes and make a browser-compatible viewing copy.
                os.replace(temp, folder / "original-media")
                converted = self.run([self.ffmpeg, "-v", "error", "-nostdin", "-y", *SAFE_INPUT,
                    "-i", str(folder / "original-media"), "-map", "0:V:0", "-map", "0:a:0?",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(folder / "source.mp4")],
                    timeout=max(120, min(metadata['duration'] * 12, 14400)))
                if converted.returncode:
                    raise APIError(422, "这个视频未能转换为可播放副本，请确认原文件完整。")
                metadata = self.probe(folder / "source.mp4")
            project = {"id": project_id, "name": name, **metadata,
                       "video_url": f"/media/{project_id}/source.mp4", "status": "ready", "progress": 1,
                       "message": "导入完成。可开始自动识别镜头。",
                       "shots": [self.new_shot(project_id, 0, metadata["duration"])],
                       "revision": 0, "created_at": now(), "updated_at": now(), "size": size,
                       "analysis": None, "captures": [], "audio_clips": [], "original_metadata": original_metadata, "converted": not compatible,
                       "transcript": {"status": "idle", "progress": 0, "message": "尚未识别字幕。", "segments": [], "engine": ""}}
            self.thumbnail(project, project["shots"][0])
            with self.lock(project_id):
                self.write(project)
            complete = True
            return project
        finally:
            if not complete:
                shutil.rmtree(folder, ignore_errors=True)

    def ensure_editable(self, project: dict):
        if project["status"] == "processing":
            raise APIError(409, "正在分析视频，请等分析完成后再修改。")

    def check_revision(self, project: dict, body: dict):
        if "expected_revision" not in body:
            return
        revision = body["expected_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise APIError(400, "项目版本号无效，请刷新项目后重试。")
        if revision != project["revision"]:
            raise APIError(409, "这个项目刚刚发生了修改。请刷新项目后再保存，当前修改未覆盖已有记录。")

    def progress(self, project_id: str, progress: float, message: str):
        with self.lock(project_id):
            project = self.read(project_id)
            project.update(progress=min(max(progress, 0), 1), message=message)
            self.write(project)

    def study(self, project_id: str, body: dict) -> dict:
        """Opening a workspace is passive; audio work requires an explicit task."""
        with self.lock(project_id):
            project = self.read(project_id)
            if project.get('removed'):
                raise APIError(404, '这个视频已移除。')
            task = body.get('task')
            if task is None:
                return project
            if task not in {'sound', 'music_sections'}:
                raise APIError(400, '请选择需要执行的分析。')
            if not project.get('has_audio'):
                raise APIError(422, '这个视频没有声音。')
            if task == 'sound':
                return self.research.ensure_source(project_id, retry=body.get('retry_sound') is True)
            state = self.sections.state(project)
            if state['status'] in {'ready', 'processing', 'waiting_audio'}:
                return project
            state.update(status='waiting_audio', message='正在准备背景声，随后查找音乐变化位置…')
            self.write(project)
            source = self.research.ensure_source(project_id, retry=True)
            sound = source.get('source_audio', {}).get('sound', {})
            if sound.get('status') == 'ready':
                return self.sections.after_source(project_id)
            if sound.get('status') in {'error', 'cancelled'}:
                source['music_sections'].update(status='error', message=sound.get('message', '背景声准备失败，请重试。'))
                self.write(source)
            return self.read(project_id)

    def analyze(self, project_id: str, body: dict) -> dict:
        threshold = number(body.get("threshold", 0.35), "灵敏度")
        minimum = number(body.get("min_duration", 0.3), "最短镜头时长")
        if not 0.01 <= threshold <= 0.99:
            raise APIError(400, "场景变化阈值需在 0.01 到 0.99 之间。")
        if self.detector == "transnetv2" and not 0.05 <= threshold <= 0.95:
            raise APIError(400, "TransNetV2 的场景变化阈值需在 0.05 到 0.95 之间。")
        if not 0.1 <= minimum <= 60:
            raise APIError(400, "最短镜头时长需在 0.1 到 60 秒之间。")
        self.require_tools()
        if self.detector == "transnetv2":
            runtime = check_python_runtime(ROOT, "scenes", Path(self.detector_python))
            if not runtime.available:
                raise APIError(503, "TransNetV2：" + runtime.message + " 视频与已有笔记已保留。")
        with self.lock(project_id):
            project = self.read(project_id)
            self.ensure_editable(project)
            self.check_revision(project, body)
            if any(shot.get("note", "").strip() or shot.get("tag", "").strip() or shot.get("title", "").strip()
                   for shot in project["shots"]):
                raise APIError(409, "已有镜头名称、笔记或标签。为避免覆盖，请先导出记录并清空这些内容后再重新分析。")
            engine_name = "TransNetV2" if self.detector == "transnetv2" else "FFmpeg 画面变化（备用算法）"
            project.update(status="processing", progress=0.01, message=f"正在使用 {engine_name} 检查画面变化……")
            self.write(project)
            thread = threading.Thread(target=self._analysis_job, args=(project_id, threshold, minimum), daemon=True)
            self.jobs[project_id] = thread
            thread.start()
            return copy.deepcopy(project)

    def detect_scene_cuts(self, project: dict, threshold: float) -> dict:
        """Independent detector boundary: original model route or explicitly selected FFmpeg fallback."""
        if self.detector == "transnetv2":
            command = [str(self.detector_python), str(ROOT / "tools" / "detect_shots.py"),
                       str(self.directory(project["id"]) / "source.mp4"),
                       "--threshold", str(threshold), "--device", "auto"]
        else:
            command = [self.ffmpeg, "-hide_banner", "-nostdin", "-threads", "2", "-filter_threads", "1",
                       *SAFE_INPUT, "-i", str(self.directory(project["id"]) / "source.mp4"), "-an", "-sn", "-dn",
                       "-vf", rf"scale=320:-2,select=gt(scene\,{threshold}),showinfo",
                       "-fps_mode", "vfr", "-f", "null", "-", "-progress", "pipe:1", "-nostats"]
        process = None
        stderr_tail = []
        try:
            process = self.spawn(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", bufsize=1)
            candidates = []
            model_result = None
            last_update = 0
            # Timeout is handled by a watchdog even if FFmpeg stops producing output.
            timed_out = threading.Event()
            def abort():
                if process.poll() is None:
                    timed_out.set()
                    self.terminate(process)
            watchdog = threading.Timer(max(300, min(project["duration"] * 10, 14400)), abort)
            watchdog.daemon = True
            watchdog.start()
            try:
                for line in process.stdout:
                    stderr_tail.append(line.rstrip())
                    stderr_tail = stderr_tail[-20:]
                    if self.detector == "transnetv2":
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if "cut_times" in event:
                            model_result = event
                        elif "progress" in event and time.monotonic() - last_update > 0.5:
                            self.progress(project["id"], 0.02 + max(0, min(float(event["progress"]), 1)) * 0.68,
                                          "TransNetV2：" + str(event.get("message", "正在分析画面……")))
                            last_update = time.monotonic()
                        continue
                    match = re.search(r"pts_time:([0-9.eE+-]+)", line)
                    if match:
                        candidates.append(float(match.group(1)))
                    if line.startswith("out_time_us="):
                        try:
                            seconds = int(line.split("=", 1)[1]) / 1000000
                        except ValueError:
                            continue
                        if time.monotonic() - last_update > 0.7:
                            self.progress(project["id"], min(0.7, 0.02 + seconds / project["duration"] * 0.68),
                                          f"FFmpeg 备用算法：已找到 {len(candidates)} 个候选切点……")
                            last_update = time.monotonic()
                code = process.wait()
            finally:
                watchdog.cancel()
                if process.stdout:
                    process.stdout.close()
                self.forget(process)
            if timed_out.is_set():
                raise APIError(422, "画面分析超时。原视频和已有镜头已保留，可重试。")
            if code:
                engine = "TransNetV2 本地模型" if self.detector == "transnetv2" else "FFmpeg 备用算法"
                raise APIError(422, f"{engine}分析失败，请检查本地运行环境或视频文件。原视频和已有镜头已保留，未切换到其他算法。")
            if self.detector == "transnetv2":
                if not isinstance(model_result, dict) or model_result.get("engine") != "transnetv2":
                    raise APIError(422, "TransNetV2 未返回有效结果，原视频和已有镜头已保留。")
                candidates = [number(value, "模型切点") for value in model_result["cut_times"]]
                return {"method": "transnetv2", "cuts": candidates, "device": model_result.get("device"),
                        "model_scene_count": model_result.get("scene_count")}
            return {"method": "ffmpeg-scene", "cuts": candidates}
        except Exception:
            if process and process.poll() is None:
                self.terminate(process)
                self.forget(process)
            if stderr_tail:
                print("\n".join(stderr_tail[-10:]), flush=True)
            raise

    def _analysis_job(self, project_id: str, threshold: float, minimum: float):
        acquired = False
        try:
            project = self.read(project_id)
            if not self.detector_slot.acquire(blocking=False):
                self.progress(project_id, 0.01, "等待前一个视频分析完成……")
                while not self.stopping:
                    if self.detector_slot.acquire(timeout=0.25):
                        acquired = True
                        break
                if not acquired:
                    raise APIError(503, "本地服务已停止，待分析项目可在下次打开后重试。")
            else:
                acquired = True
            detection = self.detect_scene_cuts(project, threshold)
            self.detector_slot.release()
            acquired = False
            candidates = detection.pop("cuts")
            ranges = shot_ranges(project["duration"], candidates, minimum)
            shots = [self.new_shot(project_id, start, end) for start, end in ranges]
            self.progress(project_id, 0.72, f"已分出 {len(shots)} 个镜头，正在生成关键帧……")
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(self.thumbnail, project, shot) for shot in shots]
                for index, future in enumerate(as_completed(futures), 1):
                    future.result()
                    self.progress(project_id, 0.72 + 0.27 * index / len(shots),
                                  f"正在生成关键帧 {index}/{len(shots)}……")
            with self.lock(project_id):
                result = self.read(project_id)
                result.update(shots=shots, status="ready", progress=1,
                              message=f"完成：共 {len(shots)} 个镜头。可点选回看并记录笔记。",
                              analysis={**detection, "threshold": threshold,
                                        "min_duration": minimum, "candidate_count": len(candidates), "completed_at": now()})
                self.write(result)
                self._clean_thumbnails(result)
        except Exception as error:
            message = error.message if isinstance(error, APIError) else "分析暂时失败，原视频和已有镜头已保留。请重试。"
            try:
                with self.lock(project_id):
                    project = self.read(project_id)
                    project.update(status="error", message=message)
                    self.write(project)
                    self._clean_thumbnails(project)
            except Exception as cleanup_error:
                print(f"Analysis cleanup {project_id}: {type(cleanup_error).__name__}: {cleanup_error}", flush=True)
            print(f"Analysis {project_id}: {type(error).__name__}: {error}", flush=True)
        finally:
            if acquired:
                self.detector_slot.release()

    def _clean_thumbnails(self, project: dict):
        retained = {f"{shot['id']}.jpg" for shot in project["shots"]}
        for file in (self.directory(project["id"]) / "thumbnails").glob("*.jpg"):
            if file.name not in retained:
                file.unlink(missing_ok=True)

    def annotate(self, project_id: str, shot_id: str, body: dict) -> dict:
        valid_id(shot_id)
        if not any(key in body for key in {"note", "tag", "title"}) or any(key not in {"note", "tag", "title", "expected_revision", "expected_annotation_revision"} for key in body):
            raise APIError(400, "只能修改分镜名称、笔记和标签。")
        for key, value in body.items():
            if key in {"expected_revision", "expected_annotation_revision"}:
                continue
            if not isinstance(value, str) or len(value) > (20000 if key == "note" else 120 if key == "title" else 500):
                raise APIError(400, "名称最多 120 字，笔记最多 20000 字，标签最多 500 字。")
        with self.lock(project_id):
            project = self.read(project_id)
            self.ensure_editable(project)
            shot = next((shot for shot in project["shots"] if shot["id"] == shot_id), None)
            if not shot:
                raise APIError(404, "这个镜头不存在。")
            if "expected_annotation_revision" in body:
                revision = body["expected_annotation_revision"]
                if isinstance(revision, bool) or not isinstance(revision, int):
                    raise APIError(400, "镜头笔记版本号无效，请重新打开镜头。")
                if revision != shot.get("annotation_revision", 0):
                    raise APIError(409, "这个镜头的笔记已在别处修改。当前输入未覆盖已有笔记，请重新打开镜头核对。")
            else:
                self.check_revision(project, body)
            shot.update({key: value for key, value in body.items() if key in {"note", "tag", "title"}})
            shot["annotation_revision"] = shot.get("annotation_revision", 0) + 1
            self.write(project)
            return project

    def storyboard(self, project_id: str, body: dict) -> dict:
        """Edit source shot boundaries only; audio and saved research stay intact."""
        action = body.get('action')
        if action == 'split':
            with self.lock(project_id):
                project = self.read(project_id)
                self.ensure_editable(project)
                self.check_revision(project, body)
                index = next((i for i, shot in enumerate(project['shots']) if shot['id'] == body.get('id')), None)
                if index is None:
                    raise APIError(404, '当前分镜已变化，请重新选择画面。')
                left = project['shots'][index]
                fps = project['fps'] or 30
                at = round(number(body.get('time'), '裁切位置') * fps) / fps
                if min(at - left['start'], left['end'] - at) < 1 / fps - 1e-7:
                    raise APIError(400, '播放头已在分镜边缘，请移到需要切开的画面。')
                snapshot_revision = project['revision']
                shot_snapshot = (left['id'], left['start'], left['end'])
                right = self.new_shot(project_id, at, left['end'])
                project_directory = self.directory(project_id)
            committed = False
            try:
                self.thumbnail(project, right)
                with self.lock(project_id):
                    if self.directory(project_id) != project_directory:
                        raise APIError(409, '项目资料位置已变化，本次裁切未写入，请重试。')
                    latest = self.read(project_id)
                    if latest['revision'] != snapshot_revision:
                        raise APIError(409, '分镜在生成关键帧时已被修改，本次裁切未写入，请重试。')
                    index = next((i for i, shot in enumerate(latest['shots']) if shot['id'] == shot_snapshot[0]), None)
                    if index is None or (latest['shots'][index]['start'], latest['shots'][index]['end']) != shot_snapshot[1:]:
                        raise APIError(409, '当前分镜已变化，本次裁切未写入，请重试。')
                    before = copy.deepcopy(latest['shots'])
                    latest['shots'][index]['end'] = at
                    latest['shots'].insert(index + 1, right)
                    history = latest.setdefault('storyboard_history', [])
                    history.append({'id': uid(), 'before': before, 'after': copy.deepcopy(latest['shots'])})
                    del history[:-20]
                    self.write(latest)
                    committed = True
                    return latest
            finally:
                if not committed:
                    thumbnail = project_directory / 'thumbnails' / f"{right['id']}.jpg"
                    thumbnail.unlink(missing_ok=True)
                    if thumbnail.parent.exists(): fsync_directory(thumbnail.parent)

        with self.lock(project_id):
            project = self.read(project_id)
            self.ensure_editable(project)
            self.check_revision(project, body)
            shots = project['shots']
            history = project.setdefault('storyboard_history', [])
            if action == 'undo':
                if not history or history[-1]['id'] != body.get('operation_id'):
                    raise APIError(409, '分镜已有其他调整，请撤销最近一次操作。')
                entry = history[-1]
                if shots != entry['after']:
                    raise APIError(409, '分镜或笔记已有修改，不能覆盖这些新内容。')
                project['shots'] = entry['before']
                history.pop()
            elif action == 'merge':
                index = next((i for i, s in enumerate(shots) if s['id'] == body.get('id')), None)
                if index is None:
                    raise APIError(404, '当前分镜已变化，请重新选择画面。')
                before = copy.deepcopy(shots)
                left = shots[index]
                if index + 1 >= len(shots) or shots[index + 1]['id'] != body.get('next_id'):
                    raise APIError(400, '只能合并相邻的两个分镜。')
                right = shots[index + 1]
                if abs(left['end'] - right['start']) > 1e-6:
                    raise APIError(400, '这两个分镜时间不连续，不能合并。')
                left['end'] = right['end']
                for key in ('note', 'tag'):
                    left[key] = '\n'.join(dict.fromkeys(v for v in [left.get(key), right.get(key)] if v))
                left['annotation_revision'] = max(left.get('annotation_revision', 0), right.get('annotation_revision', 0)) + 1
                shots.pop(index + 1)
                history.append({'id': uid(), 'before': before, 'after': copy.deepcopy(shots)})
                del history[:-20]
            else:
                raise APIError(400, '请选择裁切、合并或撤销。')
            self.write(project)
            return project

    def capture(self, project_id: str, body: dict) -> dict:
        position = number(body.get("time"), "截图时间")
        self.require_tools()
        with self.lock(project_id):
            project = self.read(project_id)
            self.check_revision(project, body)
            if not 0 <= position < project["duration"]:
                raise APIError(400, "请在视频开始到结束之间选择截图位置。")
            capture_id = uid()
            snapshot_revision = project["revision"]
            directory, source, identity = self.source_snapshot(project_id)
        target = self.render_capture(project_id, directory, source, identity, position, capture_id)
        saved = False
        try:
            with self.lock(project_id):
                latest = self.read(project_id)
                self.validate_source_snapshot(project_id, directory, source, identity)
                if "expected_revision" in body and latest["revision"] != snapshot_revision:
                    raise APIError(409, "这个项目刚刚发生了修改。请刷新后重试，本次截图未写入。")
                capture = {"id": capture_id, "time": position, "url": f"/media/{project_id}/captures/{capture_id}.jpg",
                           "created_at": now(), "note": "", "tag": ""}
                latest["captures"].append(capture)
                latest["captures"].sort(key=lambda item: item["time"])
                self.write(latest)
                saved = True
                return latest
        finally:
            if not saved:
                target.unlink(missing_ok=True)
                fsync_directory(target.parent)

    def waveform(self, project_id: str) -> dict:
        project = self.read(project_id)
        if not project.get("has_audio"):
            raise APIError(422, "这个视频没有音轨，无法显示音频波形。")
        directory, source, identity = self.source_snapshot(project_id)
        cache = directory / "waveform.json"
        # Independent from project edits: decoding must not hold the project lock.
        with self.waveform_guard:
            if cache.is_file():
                try:
                    return json.loads(cache.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            self.require_tools()
            pcm = cache.with_name(f".waveform-{uid()}.pcm")
            rate, count = 8000, 1000
            try:
                result = self.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                                   *SAFE_INPUT, "-i", str(source),
                                   "-t", f"{project['duration']:.8f}", "-vn", "-map", "0:a:0", "-ac", "1",
                                   "-ar", str(rate), "-f", "s16le", str(pcm)],
                                  timeout=max(60, min(project["duration"], 3600)))
                if result.returncode or not pcm.is_file() or pcm.stat().st_size == 0:
                    raise APIError(422, "音频波形读取失败，请重试。")
                total = max(1, round(project["duration"] * rate))
                samples = []
                with pcm.open("rb") as audio_file:
                    for index in range(count):
                        width = round((index + 1) * total / count) - round(index * total / count)
                        values = array("h")
                        values.frombytes(audio_file.read(width * 2))
                        if sys.byteorder != "little":
                            values.byteswap()
                        peak = max(abs(min(values)), abs(max(values))) / 32768 if values else 0
                        samples.append(round(min(1, peak), 6))
                data = {"samples": samples, "duration": project["duration"], "method": "pcm-peak", "sample_rate": rate}
                self.validate_source_snapshot(project_id, directory, source, identity)
                atomic_json(cache, data)
                return data
            except subprocess.TimeoutExpired:
                raise APIError(422, "音频波形读取超时，请重试。") from None
            finally:
                pcm.unlink(missing_ok=True)

    def transcription_python(self) -> Path:
        if self.asr_python:
            return Path(self.asr_python)
        return Path(sys.executable)

    def transcribe(self, project_id: str, body: dict) -> dict:
        python = self.transcription_python()
        with self.lock(project_id):
            project = self.read(project_id)
            if not project.get("has_audio"):
                raise APIError(422, "这个视频没有音轨，无法识别字幕。")
            if project["transcript"]["status"] == "processing":
                raise APIError(409, "字幕正在识别，请等本次识别完成。")
            native_runtime_unavailable = self.asr_python is None and not check_whisper_runtime(ROOT).available
            if not python.is_file() or not Path(self.asr_script).is_file() or native_runtime_unavailable:
                project["transcript"].update(status="error", progress=0, message="本地字幕识别环境尚未就绪，已有字幕和镜头已保留。")
                self.write(project)
                raise APIError(503, project["transcript"]["message"])
            project["transcript"].update(status="processing", progress=0.01, message="准备本地字幕识别……")
            self.write(project)
            thread = threading.Thread(target=self._transcription_job, args=(project_id, python), daemon=True)
            self.jobs["transcript:" + project_id] = thread
            thread.start()
            return copy.deepcopy(project)

    def transcript_progress(self, project_id: str, progress: float, message: str):
        with self.lock(project_id):
            project = self.read(project_id)
            project["transcript"].update(progress=max(0, min(progress, 0.99)), message=message)
            self.write(project)

    def _transcription_job(self, project_id: str, python: Path):
        process, acquired, watchdog = None, False, None
        try:
            project = self.read(project_id)
            if not self.detector_slot.acquire(blocking=False):
                self.transcript_progress(project_id, 0.01, "等待前一个本地分析任务完成后识别字幕……")
                while not self.stopping:
                    if self.detector_slot.acquire(timeout=0.25):
                        acquired = True
                        break
                if not acquired:
                    raise APIError(503, "服务已停止，字幕可在下次打开后重新识别。")
            else:
                acquired = True
            process = self.spawn([str(python), str(self.asr_script), str(self.directory(project_id) / "source.mp4")],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1)
            timed_out = threading.Event()
            def abort():
                if process.poll() is None:
                    timed_out.set()
                    self.terminate(process)
            watchdog = threading.Timer(max(300, min(project["duration"] * 30, 14400)), abort)
            watchdog.daemon = True
            watchdog.start()
            result, last_update, last_error = None, 0, ""
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if "segments" in event:
                    result = event
                elif event.get("error"):
                    last_error = str(event.get("message") or "本地字幕识别失败。")[:800]
                elif "progress" in event and time.monotonic() - last_update > 0.6:
                    self.transcript_progress(project_id, number(event["progress"], "字幕进度"),
                                             str(event.get("message", "正在识别字幕……"))[:800])
                    last_update = time.monotonic()
            code = process.wait()
            if timed_out.is_set():
                raise APIError(422, "本地字幕识别超时，已有字幕和镜头已保留，可重试。")
            if code or not isinstance(result, dict) or not isinstance(result.get("segments"), list):
                raise APIError(422, last_error or "本地字幕识别失败，已有字幕和镜头已保留，请检查本地模型环境后重试。")
            segments = []
            for item in result["segments"]:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    raise APIError(422, "字幕结果格式不完整，已有结果已保留。")
                start = max(0, number(item.get("start"), "字幕开始时间"))
                end = min(project["duration"], number(item.get("end"), "字幕结束时间"))
                text = item["text"].strip()
                if end > start and text:
                    segments.append({"start": start, "end": end, "text": text})
            segments.sort(key=lambda item: (item["start"], item["end"]))
            with self.lock(project_id):
                latest = self.read(project_id)
                latest["transcript"] = {"status": "ready", "progress": 1, "segments": segments,
                                        "revision": latest['transcript'].get('revision', 0) + 1,
                                        "message": f"字幕识别完成，共 {len(segments)} 段。自动识别可能有错字，请核对。" if segments else "未识别到可用语音，可回听音轨后重试。",
                                        "engine": str(result.get("engine", "local-asr")), "language": result.get("language"),
                                        "completed_at": now()}
                self.write(latest)
        except Exception as error:
            message = error.message if isinstance(error, APIError) else "字幕识别失败，已有字幕和镜头已保留，可重试。"
            with self.lock(project_id):
                project = self.read(project_id)
                project["transcript"].update(status="error", message=message)
                self.write(project)
            print(f"Transcription {project_id}: {type(error).__name__}: {error}", flush=True)
        finally:
            if watchdog:
                watchdog.cancel()
            if process:
                if process.poll() is None:
                    self.terminate(process)
                if process.stdout:
                    process.stdout.close()
                self.forget(process)
            if acquired:
                self.detector_slot.release()

    def subtitle(self, project_id: str, body: dict) -> dict:
        text = body.get('text')
        index = body.get('index')
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise APIError(400, '字幕不能为空，最多 5000 字。')
        with self.lock(project_id):
            project = self.read(project_id)
            transcript = project['transcript']
            if transcript['status'] == 'processing':
                raise APIError(409, '正在重新识别字幕，请完成后再修改。')
            self.entity_revision(transcript, body, 'revision')
            segments = transcript.get('segments', [])
            if type(index) is not int or not 0 <= index < len(segments):
                raise APIError(404, '这条字幕已不存在，请重新打开。')
            segment = segments[index]
            if segment['text'] == text.strip():
                return project
            segment.setdefault('original_text', segment['text'])
            segment['text'] = text.strip()
            transcript['revision'] = transcript.get('revision', 0) + 1
            self.write(project)
            return project

    def metadata(self, project_id: str, body: dict) -> dict:
        with self.lock(project_id):
            project = self.read(project_id)
            self.entity_revision(project, body, 'metadata_revision')
            if 'tags' in body:
                project['tags'] = self.tags(body['tags'])
            if 'source' in body:
                source = body['source']
                if not isinstance(source, dict) or any(k not in {'url', 'title', 'author', 'platform'} for k in source):
                    raise APIError(400, '来源信息无效。')
                if any(not isinstance(v, str) or len(v) > 2000 for v in source.values()):
                    raise APIError(400, '来源信息过长。')
                if source.get('url') and urlsplit(source['url']).scheme not in {'http', 'https'}:
                    raise APIError(400, '来源链接须以 http 或 https 开头。')
                project['source'] = source
            if 'removed' in body:
                if type(body['removed']) is not bool:
                    raise APIError(400, '移除状态无效。')
                if body['removed'] and (project['status'] == 'processing' or project['transcript']['status'] == 'processing' or project['music']['status'] == 'processing'):
                    raise APIError(409, '分析正在进行，请完成后移除。')
                project['removed'] = body['removed']
            project['metadata_revision'] = project.get('metadata_revision', 0) + 1
            self.write(project)
            return project

    @staticmethod
    def entity_revision(entity: dict, body: dict, key='asset_revision'):
        expected = body.get('expected_revision')
        if type(expected) is not int or expected != entity.get(key, 0):
            raise APIError(409, '此记录已在别处更新。当前输入已保留，请重新打开核对。')

    @staticmethod
    def tags(value) -> list:
        if not isinstance(value, list) or len(value) > 50 or any(not isinstance(s, str) or len(s) > 60 for s in value):
            raise APIError(400, '最多 50 个标签，每个标签最多 60 字。')
        return list(dict.fromkeys(s.strip() for s in value if s.strip()))

    def annotation(self, project_id: str, body: dict) -> dict:
        with self.lock(project_id):
            project = self.read(project_id)
            annotation_id = body.get('id')
            if annotation_id:
                item = next((a for a in project['annotations'] if a['id'] == annotation_id), None)
                if not item:
                    raise APIError(404, '笔记已移除，当前输入未保存。')
                self.entity_revision(item, body, 'revision')
            else:
                position = number(body.get('time'), '笔记时间')
                kind = body.get('kind', 'frame')
                if not 0 <= position <= project['duration'] or kind not in {'frame', 'audio', 'content'}:
                    raise APIError(400, '笔记位置或类别无效。')
                item = {'id': uid(), 'time': position, 'kind': kind, 'revision': 0, 'created_at': now()}
            if body.get('delete'):
                project['annotations'] = [a for a in project['annotations'] if a['id'] != annotation_id]
            else:
                value = body.get('text')
                if not isinstance(value, str) or not value.strip() or len(value) > 20000:
                    raise APIError(400, '请输入笔记内容，最多 20000 字。')
                item.update(text=value.strip(), revision=item['revision'] + 1, updated_at=now())
                if not annotation_id:
                    project['annotations'].append(item)
            self.write(project)
            return project

    def asset(self, project_id: str, body: dict) -> dict:
        kind = body.get('kind')
        if kind not in {'captures', 'audio_clips', 'exports', 'music'}:
            raise APIError(400, '素材类别无效。')
        with self.lock(project_id):
            project = self.read(project_id)
            entries = project['music']['tracks'] if kind == 'music' else project[kind]
            item = next((a for a in entries if a['id'] == body.get('id')), None)
            if not item:
                raise APIError(404, '找不到此素材。')
            self.entity_revision(item, body)
            if 'tags' in body:
                item['tags'] = self.tags(body['tags'])
            if 'note' in body:
                if not isinstance(body['note'], str) or len(body['note']) > 20000:
                    raise APIError(400, '备注最多 20000 字。')
                item['note'] = body['note']
            if 'deleted' in body:
                if type(body['deleted']) is not bool:
                    raise APIError(400, '删除状态无效。')
                item['deleted'] = body['deleted']
            item['asset_revision'] = item.get('asset_revision', 0) + 1
            self.write(project)
            return project

    def collect(self, project_id: str, body: dict) -> dict:
        tags = self.tags(body.get('tags', []))
        with self.lock(project_id):
            project = self.read(project_id)
            shot = next((s for s in project['shots'] if s['id'] == body.get('shot_id')), None)
            if not shot:
                raise APIError(404, '找不到这个镜头。')
            prior = next((c for c in project['captures'] if c.get('shot_id') == shot['id']), None)
            if prior:
                prior['deleted'] = False
                if 'tags' in body:
                    prior['tags'] = tags
                prior['asset_revision'] = prior.get('asset_revision', 0) + 1
                self.write(project)
                return project
            position = min(shot['start'] + 0.08, (shot['start'] + shot['end']) / 2)
            shot_snapshot = (shot['id'], shot['start'], shot['end'])
            capture_id = uid()
            directory, source, identity = self.source_snapshot(project_id)
        target = self.render_capture(project_id, directory, source, identity, position, capture_id)
        saved = False
        try:
            with self.lock(project_id):
                latest = self.read(project_id)
                self.validate_source_snapshot(project_id, directory, source, identity)
                shot = next((s for s in latest['shots'] if s['id'] == shot_snapshot[0]), None)
                if not shot or (shot['start'], shot['end']) != shot_snapshot[1:]:
                    raise APIError(409, '分镜已变化，本次收藏未写入，请重新选择。')
                prior = next((c for c in latest['captures'] if c.get('shot_id') == shot['id']), None)
                if prior:
                    prior.update(deleted=False, tags=tags,
                                 asset_revision=prior.get('asset_revision', 0) + 1)
                    target.unlink(missing_ok=True)
                    fsync_directory(target.parent)
                else:
                    latest['captures'].append({
                        'id': capture_id, 'time': position,
                        'url': f'/media/{project_id}/captures/{capture_id}.jpg',
                        'created_at': now(), 'note': '', 'tag': '', 'shot_id': shot['id'],
                        'start': shot['start'], 'end': shot['end'], 'tags': tags, 'asset_revision': 0,
                    })
                    latest['captures'].sort(key=lambda item: item['time'])
                self.write(latest)
                saved = True
                return latest
        finally:
            if not saved:
                target.unlink(missing_ok=True)
                fsync_directory(target.parent)

    def previews(self, project_id: str) -> dict:
        project = self.read(project_id)
        directory, source, identity = self.source_snapshot(project_id)
        with self.preview_guard:
            folder = directory / 'previews'
            count = min(24, max(1, int(project['duration'])))
            if not (folder / 'complete.json').is_file():
                created = not folder.exists()
                folder.mkdir(exist_ok=True)
                if created: fsync_directory(directory)
                result = self.run([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    *SAFE_INPUT, '-i', str(source), '-an',
                    '-vf', f"fps={count/project['duration']:.10f}:start_time=0,scale=200:-2", '-frames:v', str(count),
                    '-q:v', '4', '-threads', '1', str(folder/'frame-%03d.jpg')], timeout=max(60, project['duration']))
                if result.returncode or not list(folder.glob('frame-*.jpg')):
                    raise APIError(422, '预览帧生成失败，请重试。')
                self.validate_source_snapshot(project_id, directory, source, identity)
                atomic_json(folder/'complete.json', {'count': len(list(folder.glob('frame-*.jpg')))})
            images = sorted(folder.glob('frame-*.jpg'))
            return {'frames': [{'time': i*project['duration']/len(images), 'url': f'/media/{project_id}/previews/{p.name}'} for i,p in enumerate(images)]}

    def save_export(self, project_id: str, body: dict) -> dict:
        format_name = body.get('format', 'docx')
        data, content_type = self.export(project_id, format_name)
        with self.lock(project_id):
            project = self.read(project_id)
            asset_id = uid()
            folder = self.directory(project_id)/'exports'
            folder.mkdir(exist_ok=True)
            filename = f'{asset_id}.{format_name}'
            temp = folder/('.' + filename)
            temp.write_bytes(data)
            os.replace(temp, folder/filename)
            label = '字幕脚本' if format_name in {'srt','txt','md'} else '分镜表'
            item = {'id': asset_id, 'url': f'/media/{project_id}/exports/{filename}', 'format': format_name,
                    'title': f"{Path(project['name']).stem}-{label}.{format_name}", 'time': 0,
                    'created_at': now(), 'tags': [], 'asset_revision': 0}
            project['exports'].append(item)
            self.write(project)
            return project

    def reveal(self, project_id: str, body: dict):
        project = self.read(project_id)
        kind, asset_id = body.get('kind'), body.get('id')
        filename = 'source.mp4'
        if kind != 'video':
            if kind not in {'captures','audio_clips','exports'}:
                raise APIError(400, '此项目没有本地文件。')
            item = next((a for a in project[kind] if a['id']==asset_id and not a.get('deleted')), None)
            if not item:
                raise APIError(404, '文件记录不存在。')
            filename = item['url'].split(f'/media/{project_id}/',1)[-1]
        target = (self.directory(project_id)/filename).resolve()
        if not target.is_relative_to(self.directory(project_id)) or not target.is_file():
            raise APIError(404, '文件不存在。')
        if sys.platform != 'darwin':
            raise APIError(422, '此系统请使用下载按钮保存文件。')
        result=self.run(['/usr/bin/open','-R', str(target)], timeout=10)
        if result.returncode: raise APIError(422,'访达未能打开文件，请使用下载按钮。')
        return {'ok': True}

    def music(self, project_id: str, body: dict) -> dict:
        with self.lock(project_id):
            project = self.read(project_id)
            if not project.get('has_audio'):
                raise APIError(422, '此视频没有音轨。')
            if project['music']['status'] == 'processing':
                return project
            python = configured_python(ROOT, 'music')
            runtime = check_python_runtime(ROOT, 'music')
            if not runtime.available:
                raise APIError(503, runtime.message)
            project['music'].update(status='processing', progress=0, message='正在提取声音并连接识曲服务……')
            self.write(project)
            thread=threading.Thread(target=self._music_job,args=(project_id,python),daemon=True)
            self.jobs['music:'+project_id]=thread
            thread.start()
            return copy.deepcopy(project)

    def _music_job(self, project_id, python):
        process, watchdog = None, None
        try:
            project = self.read(project_id)
            process=self.spawn([str(python),str(ROOT/'tools/recognize_music.py'),str(self.directory(project_id)/'source.mp4'),str(project['duration'])], stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            watchdog=threading.Timer(155,lambda: self.terminate(process) if process.poll() is None else None)
            watchdog.daemon=True; watchdog.start()
            done=False; error=''
            for line in process.stdout:
                try: event=json.loads(line)
                except ValueError: continue
                if not isinstance(event,dict): continue
                with self.lock(project_id):
                    latest=self.read(project_id); music=latest['music']
                    if event.get('type')=='found':
                        track=event['track']; key=str(track['key'])
                        existing=next((s for s in music['tracks'] if s.get('key')==key),None)
                        if existing:
                            existing['positions']=sorted(set(existing.get('positions',[existing['time']])+[track['time']]))
                        else:
                            music['tracks'].append({**track,'id':uid(),'created_at':now(),'asset_revision':0,'tags':track.get('tags',[])})
                    elif event.get('type')=='progress':
                        music.update(progress=max(0,min(.99,number(event['value'],'识曲进度'))),message=str(event.get('message','识别中')))
                    elif event.get('type')=='done': done=True
                    elif event.get('type')=='error': error=str(event.get('message','音乐识别失败。'))
                    self.write(latest)
            code=process.wait()
            if code or not done:
                raise APIError(422,error or '识曲服务未完成响应，请检查网络后重试。已有结果已保留。')
            with self.lock(project_id):
                latest=self.read(project_id); music=latest['music']
                music.update(status='ready',progress=1,completed_at=now(),message=f"识别完成，共 {len(music['tracks'])} 首。" if music['tracks'] else '本次未匹配到歌曲。可回听后重新识别。')
                self.write(latest)
        except Exception as error:
            with self.lock(project_id):
                latest=self.read(project_id)
                latest['music'].update(status='error',message=error.message if isinstance(error,APIError) else '识曲处理失败，请重试。')
                self.write(latest)
        finally:
            if watchdog: watchdog.cancel()
            if process:
                if process.poll() is None: self.terminate(process)
                if process.stdout: process.stdout.close()
                self.forget(process)

    def local_music(self):
        with self.music_lock:
            path=self.data_dir/'music-library.json'
            if not path.exists(): return {'tracks':[]}
            try: return json.loads(path.read_text())
            except (OSError,ValueError): raise APIError(500,'本地音乐记录无法读取，已停止写入以保护数据。')

    def import_music(self,name,stream,size):
        self.require_tools()
        if size<=0 or size>2*1024**3: raise APIError(400,'音频文件需小于 2 GB。')
        name=Path(name.replace('\\','/')).name[:240]
        asset_id=uid(); folder=self.data_dir/'music'; folder.mkdir(exist_ok=True)
        source=folder/(asset_id+'.part'); target=folder/(asset_id+'.m4a')
        saved=False
        try:
            with source.open('wb') as f:
                left=size
                while left:
                    chunk=stream.read(min(left,1024*1024))
                    if not chunk: raise APIError(400,'音频上传中断。')
                    f.write(chunk); left-=len(chunk)
            result=self.run([self.ffmpeg,'-v','error','-nostdin','-y',*SAFE_INPUT,'-i',str(source),'-map','0:a:0','-vn','-c:a','aac','-b:a','192k','-movflags','+faststart',str(target)],timeout=1800)
            if result.returncode: raise APIError(422,'无法读取音轨，请选择完整音频文件。')
            result=self.run([self.ffprobe,'-v','error','-show_entries','format=duration:format_tags=title,artist','-of','json',str(target)],text=True,timeout=20)
            info=json.loads(result.stdout)['format']; tags=info.get('tags',{})
            item={'id':asset_id,'title':tags.get('title') or Path(name).stem,'artist':tags.get('artist',''),'name':name,'duration':float(info['duration']),
                  'url':f'/music-media/{asset_id}.m4a','created_at':now(),'tags':[],'asset_revision':0}
            with self.music_lock:
                library=self.local_music(); library['tracks'].append(item); atomic_json(self.data_dir/'music-library.json',library)
            saved=True; return library
        finally:
            source.unlink(missing_ok=True)
            if not saved: target.unlink(missing_ok=True)

    def edit_local_music(self,body):
        with self.music_lock:
            library=self.local_music()
            item=next((a for a in library['tracks'] if a['id']==body.get('id')),None)
            if not item: raise APIError(404,'找不到音乐。')
            self.entity_revision(item,body)
            if 'tags' in body: item['tags']=self.tags(body['tags'])
            if 'deleted' in body:
                if type(body['deleted']) is not bool: raise APIError(400,'状态无效。')
                item['deleted']=body['deleted']
            item['asset_revision']=item.get('asset_revision',0)+1
            atomic_json(self.data_dir/'music-library.json',library)
            return library

    def rename_tag(self, body):
        domain, old, new = body.get('domain'), body.get('old'), body.get('new')
        if domain not in {'video','image','audio','music'} or not isinstance(old,str) or not old or not isinstance(new,str) or len(new)>60:
            raise APIError(400,'标签信息无效。')
        def update(entries,key):
            changed=False
            for item in entries:
                tags=item.get('tags') or ([item['tag']] if item.get('tag') else [])
                if old not in tags: continue
                item['tags']=list(dict.fromkeys((new if t==old else t) for t in tags if t!=old or new))
                if 'tag' in item: item['tag']=''
                item[key]=item.get(key,0)+1; changed=True
            return changed
        for project in self.list():
            with self.lock(project['id']):
                latest=self.read(project['id'])
                entries=[latest] if domain=='video' else latest['music']['tracks'] if domain=='music' else latest['audio_clips'] if domain=='audio' else latest['captures']
                if update(entries,'metadata_revision' if domain=='video' else 'asset_revision'): self.write(latest)
        if domain=='music':
            with self.music_lock:
                library=self.local_music()
                if update(library['tracks'],'asset_revision'): atomic_json(self.data_dir/'music-library.json',library)
        return {'ok':True}

    def runtime_status(self):
        scenes = check_python_runtime(ROOT, 'scenes', Path(self.detector_python))
        separation = check_python_runtime(ROOT, 'separation')
        music = check_python_runtime(ROOT, 'music')
        transcript = check_whisper_runtime(ROOT)
        return {'video':bool(self.ffmpeg and self.ffprobe),'scenes':scenes.available,
                'separation': separation.available, 'transcript':transcript.available,
                'music':music.available, 'transcript_engine':'Whisper large-v3-turbo · 本地',
                'music_service':'Shazam 音频指纹匹配 · iTunes 歌曲资料', 'data_directory':str(self.data_dir)}

    def system_usage(self):
        with self.system_usage_guard:
            sampled = time.monotonic()
            if self._system_usage_cache and sampled - self._system_usage_cache[0] < 1:
                return dict(self._system_usage_cache[1])
            usage = memory_usage_snapshot()
            self._system_usage_cache = (sampled, usage)
            return dict(usage)


    def export(self, project_id: str, format_name: str):
        project = self.read(project_id)
        if format_name in {"srt", "txt"}:
            transcript = project["transcript"]
            if transcript["status"] != "ready" and not transcript.get("segments"):
                raise APIError(409, "还没有可导出的字幕，请先完成字幕识别。")
            segments = transcript.get("segments", [])
            if format_name == "txt":
                text = "\n".join(segment["text"] for segment in segments) + ("\n" if segments else "")
                return text.encode("utf-8"), "text/plain; charset=utf-8"
            blocks = [f"{index}\n{subtitle_clock(segment['start'])} --> {subtitle_clock(segment['end'])}\n{segment['text']}"
                      for index, segment in enumerate(segments, 1)]
            return ("\n\n".join(blocks) + ("\n" if blocks else "")).encode("utf-8"), "application/x-subrip; charset=utf-8"
        if format_name == "docx":
            # Keep structural edits from removing thumbnail files during export.
            with self.lock(project_id):
                project = self.read(project_id)
                return storyboard_docx(project, self.directory(project_id)), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if format_name == "json":
            return json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8"
        if format_name == "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["镜头", "开始秒", "结束秒", "时长秒", "标签", "笔记", "重叠字幕"])
            def safe_cell(value):
                # A saved note must remain text when opened in a spreadsheet.
                return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
            for index, shot in enumerate(project["shots"], 1):
                writer.writerow([index, f"{shot['start']:.6f}", f"{shot['end']:.6f}",
                                 f"{shot['end'] - shot['start']:.6f}", safe_cell(shot["tag"]), safe_cell(shot["note"]), safe_cell(overlap_subtitles(project, shot))])
            return ("\ufeff" + output.getvalue()).encode("utf-8"), "text/csv; charset=utf-8"
        if format_name == "md":
            lines = [f"# {project['name']}", "", f"视频时长：{project['duration']:.3f} 秒；镜头数：{len(project['shots'])}", "",
                     "自动分镜基于画面变化，切点可人工修正。", ""]
            for index, shot in enumerate(project["shots"], 1):
                lines.extend([f"## 镜头 {index}", "", f"{shot['start']:.3f}–{shot['end']:.3f} 秒", "",
                              f"标签：{shot['tag'] or '未标注'}", "", "字幕：" + (overlap_subtitles(project, shot) or "暂无字幕"), "",
                              shot["note"] or "（暂无笔记）", ""])
            return "\n".join(lines).encode("utf-8"), "text/markdown; charset=utf-8"
        raise APIError(400, "导出格式可选 json、csv、md、docx、srt 或 txt。")


class WorkbenchServer(ThreadingHTTPServer):
    # server_close() must wait for request handlers before the library lock is released.
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = True

    def __init__(self, address, store: ProjectStore, public_dir: Path):
        self.store = store
        self.public_dir = Path(public_dir).resolve()
        self._connections_guard = threading.Lock()
        self._connections = {}
        self._closing_connections = False
        super().__init__(address, WorkbenchHandler)

    def process_request(self, request, client_address):
        with self._connections_guard:
            self._connections[request] = False
        try:
            return super().process_request(request, client_address)
        except BaseException:
            with self._connections_guard:
                self._connections.pop(request, None)
            raise

    def shutdown_request(self, request):
        with self._connections_guard:
            self._connections.pop(request, None)
        super().shutdown_request(request)

    def mark_connection_active(self, connection, active):
        should_close = False
        with self._connections_guard:
            if connection in self._connections:
                self._connections[connection] = active
                should_close = self._closing_connections and not active
        if should_close:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close_client_connections(self):
        # A HTTP/1.1 browser may leave an idle keep-alive handler blocked while
        # server_close() waits for non-daemon request threads.  Wake those reads;
        # handlers already doing real work still run to their safe commit point.
        with self._connections_guard:
            self._closing_connections = True
            connections = [connection for connection, active in self._connections.items() if not active]
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def server_close(self):
        self.close_client_connections()
        super().server_close()


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "LocalBroll/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Avoid noisy polling logs while retaining errors and writes.
        if args and (str(args[0]).startswith("GET /api/projects") or str(args[0]).startswith("GET /media/")):
            return
        super().log_message(format, *args)

    def run_request(self, operation):
        self.server.mark_connection_active(self.connection, True)
        try:
            return operation()
        finally:
            self.server.mark_connection_active(self.connection, False)

    def do_GET(self):
        self.run_request(lambda: self.dispatch(False))

    def do_HEAD(self):
        self.run_request(lambda: self.dispatch(True))

    def do_POST(self):
        self.run_request(lambda: self.dispatch(False))

    def do_PATCH(self):
        self.run_request(lambda: self.dispatch(False))

    def do_OPTIONS(self):
        self.run_request(lambda: self.send_json(405, {"error": "不支持跨站访问。"}))

    def check_host(self):
        port = self.server.server_address[1]
        if self.headers.get("Host", "") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise APIError(403, "仅允许通过本机地址访问。")

    def check_write_origin(self):
        origin = self.headers.get("Origin")
        expected = "http://" + self.headers.get("Host", "")
        if origin and origin != expected:
            raise APIError(403, "只允许在本地工作台页面上传或修改项目。")
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise APIError(403, "不接受其他网页发起的修改请求。")
        # A browser may omit Origin on some same-origin requests. Reject a foreign Referer too.
        referer = self.headers.get("Referer")
        if referer:
            parsed = urlsplit(referer)
            if f"{parsed.scheme}://{parsed.netloc}" != expected:
                raise APIError(403, "只允许在本地工作台页面修改项目。")

    def read_json(self, maximum=MAX_JSON):
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "请使用 JSON 格式提交修改。")
        size = self.content_length(maximum)
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "提交内容不是有效 JSON。") from None
        if not isinstance(value, dict):
            raise APIError(400, "提交内容需要是 JSON 对象。")
        return value

    def content_length(self, maximum=MAX_UPLOAD):
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "上传请求需要提供文件长度。")
        try:
            value = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise APIError(411, "缺少上传内容长度。") from None
        if value < 0:
            raise APIError(400, "上传内容长度无效。")
        if value > maximum:
            raise APIError(413, "上传内容超出限制。")
        return value

    def transcribe_ai_audio(self, store):
        maximum = 60 * 1024 * 1024
        size = self.content_length(maximum)
        if not size:
            raise APIError(400, "请选择一段有声音的文件。")
        python = store.transcription_python()
        if not python.is_file() or not store.asr_script.is_file() or (store.asr_python is None and not check_whisper_runtime(ROOT).available):
            raise APIError(503, "本地语音识别环境尚未就绪，请先在设置中检查转文字能力。")
        with tempfile.TemporaryDirectory(prefix="broll-ai-making-") as folder:
            source = Path(folder) / "voice-upload"
            with source.open("wb") as output:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise APIError(400, "语音文件上传中断，请重试。")
                    output.write(chunk)
                    remaining -= len(chunk)
            try:
                result = subprocess.run([str(python), str(store.asr_script), str(source)],
                                        capture_output=True, text=True, timeout=1800)
            except subprocess.TimeoutExpired:
                raise APIError(422, "语音识别超时，请换一段较短的语音重试。") from None
            if result.returncode:
                raise APIError(422, "未能识别这段语音，请确认文件有清晰的说话声。")
            try:
                parsed = json.loads(result.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                raise APIError(422, "语音识别没有返回可用文字。") from None
            segments = parsed.get("segments") if isinstance(parsed, dict) else None
            if not isinstance(segments, list):
                raise APIError(422, "语音识别结果格式不完整。")
            clean = []
            for item in segments:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    continue
                try:
                    start, end = float(item.get("start")), float(item.get("end"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                    continue
                text = item["text"].strip()
                if text:
                    clean.append({"start": max(0, start), "end": end, "text": text[:10000]})
            return {"segments": clean, "engine": str(parsed.get("engine", "local-asr"))[:100]}

    def save_ai_image(self, store):
        size = self.content_length(15 * 1024 * 1024)
        if not size:
            raise APIError(400, "请选择一张图片。")
        content = self.rfile.read(size)
        if len(content) != size:
            raise APIError(400, "图片上传中断，请重试。")
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        elif content.startswith(b"\xff\xd8\xff"):
            extension = "jpg"
        elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            extension = "webp"
        else:
            raise APIError(415, "请使用 PNG、JPEG 或 WebP 图片。")
        folder = store.data_dir / "ai-making-assets"
        folder.mkdir(mode=0o700, exist_ok=True)
        name = f"{uid()}.{extension}"
        with (folder / name).open("xb") as output:
            output.write(content)
        return {"url": f"/ai-making-assets/{name}"}

    def send_json(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def send_security_headers(self, *, document=False):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if document:
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)

    def send_bytes(self, status, content, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def dispatch(self, head):
        storage = self.server.store.storage
        path = urlsplit(self.path).path
        if path.startswith('/api/storage'):
            return self.dispatch_storage()
        if not path.startswith('/api/'):
            return self.dispatch_regular(head)
        # Serialize request admission with the storage freeze. Background jobs are
        # registered before a mutating request leaves this gate.
        with storage.gate:
            generates = path.endswith(('/waveform', '/waveforms', '/previews'))
            if storage.active and (self.command in {'POST', 'PATCH'} or generates):
                self.close_connection = True
                return self.send_json(409, {'error': '资料正在搬运，请完成或取消后再编辑。'})
            if storage.active:
                # Read-only status/project reads remain available, but a storage
                # commit still waits until this short read leaves the gate.
                return self.dispatch_regular(head)
            storage.regular_started()
        try:
            return self.dispatch_regular(head)
        finally:
            storage.regular_finished()

    def dispatch_storage(self):
        storage = self.server.store.storage
        try:
            self.check_host()
            parsed = urlsplit(self.path)
            path, method = parsed.path, self.command
            if method == 'POST': self.check_write_origin()
            if path == '/api/storage' and method == 'GET':
                return self.send_json(200, storage.status())
            if path == '/api/storage/choose-folder' and method == 'POST':
                self.read_json()
                return self.send_json(200, storage.choose_folder())
            if path == '/api/storage/tasks' and method == 'POST':
                return self.send_json(202, storage.start(self.read_json()))
            if path == '/api/storage/uploads' and method == 'POST':
                return self.send_json(202, storage.prepare_upload(self.read_json(64 * 1024**2)))
            match = re.fullmatch(r'/api/storage/tasks/([a-f0-9]{32})/cancel', path)
            if match and method == 'POST':
                self.read_json()
                return self.send_json(200, storage.cancel(match.group(1)))
            match = re.fullmatch(r'/api/storage/uploads/([a-f0-9]{32})(/finish)?', path)
            if match and method == 'POST':
                if match.group(2):
                    self.read_json()
                    return self.send_json(202, storage.finish_upload(match.group(1)))
                self.connection.settimeout(60)
                name = parse_qs(parsed.query).get('path', [''])[0]
                return self.send_json(200, storage.upload_file(match.group(1), name, self.rfile, self.content_length(1024**5)))
            raise APIError(404, '找不到这个存储操作。')
        except Exception as error:
            self.close_connection = True
            try:
                self.send_json(getattr(error, 'status', 400), {'error': getattr(error, 'message', str(error)) or '存储操作未完成。'})
            except (BrokenPipeError, ConnectionResetError):
                pass

    def dispatch_regular(self, head):
        try:
            self.check_host()
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            method = self.command
            store = self.server.store
            if method in {"POST", "PATCH"}:
                self.check_write_origin()
            if path.startswith('/api/production/'):
                from production_bridge import proxy_production
                return proxy_production(self)
            if path == '/api/ai-making/transcribe' and method == 'POST':
                return self.send_json(200, self.transcribe_ai_audio(store))
            if path == '/api/ai-making/assets' and method == 'POST':
                return self.send_json(201, self.save_ai_image(store))
            if path == '/api/tags' and method == 'POST':
                return self.send_json(200,store.rename_tag(self.read_json()))
            if path == '/api/runtime' and method in {'GET','HEAD'}:
                return self.send_json(200,store.runtime_status())
            if path == '/api/system-usage' and method in {'GET','HEAD'}:
                return self.send_json(200, store.system_usage())
            if path == '/api/music':
                if method in {'GET','HEAD'}: return self.send_json(200,store.local_music())
                if method == 'POST': return self.send_json(201,store.import_music(query.get('name',[''])[0],self.rfile,self.content_length()))
                if method == 'PATCH': return self.send_json(200,store.edit_local_music(self.read_json()))
            if path == "/api/projects":
                if method in {"GET", "HEAD"}:
                    return self.send_json(200, {"projects": store.list()})
                if method == "POST":
                    size = self.content_length()
                    self.connection.settimeout(180)
                    project = store.import_stream(query.get("name", [""])[0], self.rfile, size)
                    return self.send_json(201, project)
            playback = re.fullmatch(r'/api/projects/([a-f0-9]{32})/playback', path)
            if playback and method in {'GET', 'HEAD', 'POST'}:
                quality = self.read_json().get('quality') if method == 'POST' else query.get('quality', [''])[0]
                return self.send_json(200, store.playback.status(playback.group(1), quality, start=method == 'POST'))
            playback_media = re.fullmatch(r'/playback-media/([a-f0-9]{32})/([a-f0-9]{24}\.mp4)', path)
            if playback_media and method in {'GET', 'HEAD'}:
                return self.send_file(store.playback.file(*playback_media.groups()), media=True)
            sections = re.fullmatch(r'/api/projects/([a-f0-9]{32})/music_sections', path)
            if sections and method == 'POST':
                return self.send_json(200, store.sections.dispatch(sections.group(1), self.read_json()))
            research_waves = re.fullmatch(r'/api/projects/([a-f0-9]{32})/research/([a-f0-9]{32})/waveforms', path)
            if research_waves and method in {'GET', 'HEAD'}:
                return self.send_json(200, store.research.waveforms(*research_waves.groups()))
            research = re.fullmatch(r'/api/projects/([a-f0-9]{32})/research', path)
            if research and method == 'POST':
                body = self.read_json()
                if body.get('action') == 'reveal':
                    target = store.research.file(research.group(1), body.get('id'), body.get('file_id'))
                    result = store.run(['/usr/bin/open', '-R', str(target)], timeout=10)
                    if result.returncode: raise APIError(422, '访达未能打开文件。')
                    return self.send_json(200, {'ok': True})
                return self.send_json(200, store.research.dispatch(research.group(1), body))
            research_media = re.fullmatch(r'/research-media/([a-f0-9]{32})/([a-f0-9]{32})/([a-f0-9]{32})', path)
            if research_media and method in {'GET', 'HEAD'}:
                return self.send_file(store.research.file(*research_media.groups()), media=True)
            match = re.fullmatch(r"/api/projects/([^/]+)(?:/(analyze|export|capture|waveform|transcribe|metadata|annotation|asset|collect|previews|save_export|reveal|music|study|storyboard|subtitle)|/shots/([^/]+))?", path)
            if match:
                project_id, action, shot_id = match.groups()
                valid_id(project_id)
                if method in {"GET", "HEAD"} and not action and not shot_id:
                    return self.send_json(200, store.read(project_id))
                if method in {'GET','HEAD'} and action == 'previews':
                    return self.send_json(200,store.previews(project_id))
                if method == 'POST' and action in {'metadata','annotation','asset','collect','save_export','reveal','music','study','storyboard','subtitle'}:
                    return self.send_json(200,getattr(store,action)(project_id,self.read_json()))
                if method in {"GET", "HEAD"} and action == "waveform":
                    return self.send_json(200, store.waveform(project_id))
                if method in {"GET", "HEAD"} and action == "export":
                    format_name = query.get("format", ["json"])[0]
                    data, content_type = store.export(project_id, format_name)
                    name = quote(store.read(project_id)["name"] + ".shots." + format_name, safe="")
                    return self.send_bytes(200, data, content_type,
                                           {"Content-Disposition": f"attachment; filename=shots.{format_name}; filename*=UTF-8''{name}"})
                if method == "POST" and action in {"analyze", "capture", "transcribe"}:
                    body = self.read_json()
                    result = getattr(store, action)(project_id, body)
                    return self.send_json(202 if action in {"analyze", "transcribe"} else 200, result)
                if method == "PATCH" and shot_id:
                    return self.send_json(200, store.annotate(project_id, shot_id, self.read_json()))
            if path.startswith("/api/"):
                raise APIError(404 if method in {"GET", "HEAD"} else 405, "没有这个接口或不支持此操作。")
            if method not in {"GET", "HEAD"}:
                raise APIError(405, "此地址不支持修改操作。")
            preset_media = re.fullmatch(r'/ai-preset-media/([A-Za-z0-9._-]+)', path)
            if preset_media:
                filename = preset_media.group(1)
                if filename not in PRESET_MEDIA_FILES:
                    raise APIError(404, "预设素材不存在。")
                return self.send_file(PRESET_MEDIA_ROOT / filename, media=True)
            ai_image = re.fullmatch(r'/ai-making-assets/([a-f0-9]{32}\.(?:png|jpg|webp))', path)
            if ai_image:
                return self.send_file(store.data_dir / 'ai-making-assets' / ai_image.group(1), media=True)
            local_music = re.fullmatch(r'/music-media/([a-f0-9]{32})\.m4a',path)
            if local_music:
                return self.send_file(store.data_dir/'music'/(local_music.group(1)+'.m4a'),media=True)
            media = re.fullmatch(r"/media/([a-f0-9]{32})/(source\.mp4|(?:thumbnails|captures)/[a-f0-9]{32}\.jpg|previews/frame-[0-9]{3}\.jpg|audio/[a-f0-9]{32}\.m4a|exports/[a-f0-9]{32}\.(?:docx|srt|txt|md|csv|json))", path)
            if path.startswith("/media/"):
                if not media:
                    raise APIError(404, "找不到这个媒体文件。")
                project_id, filename = media.groups()
                store.read(project_id)
                return self.send_file(store.directory(project_id) / filename, media=True)
            relative = path.lstrip("/") or "index.html"
            candidate = (self.server.public_dir / relative).resolve()
            if not candidate.is_relative_to(self.server.public_dir) or any(part.startswith(".") for part in Path(relative).parts):
                raise APIError(404, "页面不存在。")
            return self.send_file(candidate, media=False)
        except APIError as error:
            # An early rejected upload may have unread bytes. Never parse them as another request.
            if self.command in {"POST", "PATCH"}:
                self.close_connection = True
            try:
                self.send_json(error.status, {"error": error.message, "message": error.message})
            except (BrokenPipeError, ConnectionResetError):
                pass
        except (BrokenPipeError, ConnectionResetError):
            pass
        except TimeoutError:
            self.close_connection = True
            try:
                self.send_json(408, {"error": "上传连接超时，请重新上传。"})
            except OSError:
                pass
        except Exception as error:
            self.close_connection = True
            print(f"Request failed: {type(error).__name__}: {error}", flush=True)
            try:
                self.send_json(500, {"error": "本地处理暂时失败，请重试。已有项目会保留。"})
            except OSError:
                pass

    def send_file(self, path: Path, media: bool):
        if not path.is_file():
            raise APIError(404, "文件不存在。")
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested_range = self.headers.get("Range")
        if requested_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range.strip())
            if not match or not any(match.groups()) or size == 0:
                return self.send_bytes(416, b"", "application/octet-stream", {"Content-Range": f"bytes */{size}"})
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                if suffix <= 0:
                    return self.send_bytes(416, b"", "application/octet-stream", {"Content-Range": f"bytes */{size}"})
                start = max(0, size - suffix)
            if start >= size or end < start:
                return self.send_bytes(416, b"", "application/octet-stream", {"Content-Range": f"bytes */{size}"})
            status = 206
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.send_security_headers(document=not media)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command != "HEAD":
            with path.open("rb") as file:
                file.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = file.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description="本地拉片工作台")
    parser.add_argument("--port", type=int, default=4182)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--public-dir", type=Path, default=ROOT / "public")
    parser.add_argument("--detector", choices=["transnetv2", "ffmpeg"], default="transnetv2",
                        help="默认使用 TransNetV2；ffmpeg 是需要主动选择的备用算法")
    args = parser.parse_args()
    config_path = Path.home() / '.config' / 'lapian-workbench' / 'storage.json'
    try:
        directory = args.data_dir or configured_directory(ROOT / 'data', config_path)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"无法打开拉片工作台：{error}", file=sys.stderr, flush=True)
        return 2
    try:
        store = ProjectStore(directory, detector=args.detector)
    except (LibraryInUseError, OSError, ValueError, RuntimeError) as error:
        print(f"无法打开拉片工作台：{error}", file=sys.stderr, flush=True)
        return 2
    server = None
    try:
        # Explicit data-dir is useful for isolated QA; changing its location remains local to that run.
        store.storage.config_path = None if args.data_dir else config_path
        server = WorkbenchServer(("127.0.0.1", args.port), store, args.public_dir)
        print(f"本地拉片工作台：http://127.0.0.1:{server.server_address[1]}", flush=True)
        print(f"项目保存位置：{store.data_dir}", flush=True)
        def stop_service(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop_service)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.begin_shutdown()
        if server:
            server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
