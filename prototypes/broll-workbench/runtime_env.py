"""Runtime discovery and health checks for optional local media models.

The environments live inside the project, but their base interpreter must not
come from Codex's disposable runtime cache.  Callers get a real import probe,
not a mere path-exists check, so a dangling or half-installed environment is
reported as unavailable before any project job is queued.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import threading


EPHEMERAL_RUNTIME_PARTS = ("/.cache/codex-runtimes/", "/codex-primary-runtime/")


@dataclass(frozen=True)
class PythonRuntimeSpec:
    key: str
    label: str
    directory: str
    requirements: str
    probe: str
    override: str
    assets: tuple[str, ...] = ()


RUNTIMES = {
    "scenes": PythonRuntimeSpec(
        key="scenes",
        label="镜头识别",
        directory=".venv",
        requirements="requirements.lock.txt",
        probe="import torch; from transnetv2_pytorch import TransNetV2",
        override="BROLL_SCENE_PYTHON",
    ),
    "separation": PythonRuntimeSpec(
        key="separation",
        label="声音分离",
        directory=".venv-separation",
        requirements="requirements-separation.lock.txt",
        probe="import numpy, soundfile, torch; from audio_separator.separator import Separator",
        override="BROLL_SEPARATION_PYTHON",
        assets=("runtime/models/separation/UVR-MDX-NET-Inst_HQ_3.onnx",),
    ),
    "music": PythonRuntimeSpec(
        key="music",
        label="歌曲识别",
        directory=".venv-music",
        requirements="requirements-music.lock.txt",
        probe="from shazamio import Shazam",
        override="BROLL_MUSIC_PYTHON",
    ),
}


@dataclass(frozen=True)
class RuntimeCheck:
    available: bool
    executable: Path
    message: str = ""


_cache: dict[tuple[object, ...], RuntimeCheck] = {}
_cache_lock = threading.Lock()


def is_ephemeral_path(value: str | os.PathLike[str]) -> bool:
    """Return whether a path is tied to a disposable Codex runtime."""
    normalized = str(value).replace("\\", "/")
    return any(part in normalized for part in EPHEMERAL_RUNTIME_PARTS)


def configured_python(root: Path, key: str, executable: Path | None = None) -> Path:
    spec = RUNTIMES[key]
    if executable is not None:
        return Path(executable)
    override = os.environ.get(spec.override)
    return Path(override).expanduser() if override else root / spec.directory / "bin" / "python"


def environment_uses_ephemeral_python(root: Path, key: str) -> bool:
    """Inspect links and pyvenv.cfg without following a possibly dead link."""
    spec = RUNTIMES[key]
    environment = root / spec.directory
    config = environment / "pyvenv.cfg"
    try:
        if config.is_file() and is_ephemeral_path(config.read_text(encoding="utf-8", errors="replace")):
            return True
    except OSError:
        return True
    for name in ("python", "python3", "python3.12"):
        path = environment / "bin" / name
        try:
            if path.is_symlink() and is_ephemeral_path(os.readlink(path)):
                return True
        except OSError:
            return True
    return False


def _fingerprint(root: Path, spec: PythonRuntimeSpec, python: Path) -> tuple[object, ...]:
    values: list[object] = [str(python)]
    for path in (python, root / spec.directory / "pyvenv.cfg", root / spec.requirements,
                 *(root / asset for asset in spec.assets)):
        try:
            stat = path.stat()
            values.extend((stat.st_mtime_ns, stat.st_size))
        except OSError:
            values.extend((None, None))
    return tuple(values)


def clear_runtime_cache() -> None:
    with _cache_lock:
        _cache.clear()


def check_python_runtime(root: Path, key: str, executable: Path | None = None,
                         timeout: float = 90) -> RuntimeCheck:
    """Execute the environment and import its required libraries once per state."""
    root = Path(root).resolve()
    spec = RUNTIMES[key]
    python = configured_python(root, key, executable)
    managed_python = root / spec.directory / "bin" / "python"
    inspect_managed_environment = executable is None or python.absolute() == managed_python.absolute()
    fingerprint = (key, *_fingerprint(root, spec, python))
    with _cache_lock:
        cached = _cache.get(fingerprint)
    if cached is not None:
        return cached

    if not python.is_file() or not os.access(python, os.X_OK):
        result = RuntimeCheck(False, python, f"{spec.label}运行环境未安装或解释器已失效。")
    elif inspect_managed_environment and environment_uses_ephemeral_python(root, key):
        result = RuntimeCheck(False, python, f"{spec.label}运行环境仍指向临时 Codex 路径。")
    else:
        missing_asset = next((root / asset for asset in spec.assets if not (root / asset).is_file()), None)
        if missing_asset:
            result = RuntimeCheck(False, python, f"{spec.label}的本地模型文件缺失。")
        else:
            try:
                process = subprocess.run(
                    [str(python), "-I", "-c", spec.probe],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                if process.returncode == 0:
                    result = RuntimeCheck(True, python)
                else:
                    result = RuntimeCheck(False, python, f"{spec.label}依赖不完整或无法导入。")
            except (OSError, subprocess.SubprocessError):
                result = RuntimeCheck(False, python, f"{spec.label}解释器无法执行。")

    with _cache_lock:
        _cache[fingerprint] = result
    return result


def check_whisper_runtime(root: Path) -> RuntimeCheck:
    """Check the native Whisper adapter's executable and model assets."""
    root = Path(root).resolve()
    executable = root / "runtime" / "whisper.cpp" / "build" / "bin" / "whisper-cli"
    model = root / "runtime" / "models" / "ggml-large-v3-turbo-q5_0.bin"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return RuntimeCheck(False, executable, "本地字幕引擎未编译或不可执行。")
    if not model.is_file() or not model.stat().st_size:
        return RuntimeCheck(False, executable, "本地字幕模型文件缺失。")
    return RuntimeCheck(True, executable)
