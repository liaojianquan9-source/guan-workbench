#!/usr/bin/env python3
"""Repair or create the project's pinned Python 3.12 media runtimes.

This script is safe to run on every launch.  Healthy environments use a small
validated marker and an executable check; missing or stale environments are
probed, repaired in place where possible, and populated from the lock files.
Project data is never read or changed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_env import (  # noqa: E402
    RUNTIMES,
    check_python_runtime,
    clear_runtime_cache,
    environment_uses_ephemeral_python,
    is_ephemeral_path,
)


MARKER = ".broll-runtime.json"
MARKER_VERSION = 1


def run(command: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def python_312(path: Path) -> bool:
    if not path.is_file() or not os.access(path, os.X_OK) or is_ephemeral_path(path):
        return False
    try:
        result = run([str(path), "-I", "-c", "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))"], 15)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def find_base_python() -> Path | None:
    candidates = [
        os.environ.get("BROLL_PYTHON_312"),
        shutil.which("python3.12"),
        "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.12",
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv-separation" / "bin" / "python",
        ROOT / ".venv-music" / "bin" / "python",
        sys.executable,
    ]
    seen: set[str] = set()
    for value in candidates:
        if not value:
            continue
        path = Path(value).expanduser()
        key = str(path)
        if key not in seen and python_312(path):
            return path
        seen.add(key)
    return None


def requirements_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def marker_is_current(key: str) -> bool:
    spec = RUNTIMES[key]
    environment = ROOT / spec.directory
    python = environment / "bin" / "python"
    marker = environment / MARKER
    if environment_uses_ephemeral_python(ROOT, key) or not python_312(python):
        return False
    try:
        saved = json.loads(marker.read_text(encoding="utf-8"))
        return (
            saved.get("version") == MARKER_VERSION
            and saved.get("key") == key
            and saved.get("requirements_sha256") == requirements_digest(ROOT / spec.requirements)
        )
    except (OSError, ValueError, TypeError):
        return False


def write_marker(key: str) -> None:
    spec = RUNTIMES[key]
    environment = ROOT / spec.directory
    marker = environment / MARKER
    temporary = marker.with_name(f".{MARKER}.{uuid.uuid4().hex}.tmp")
    payload = {
        "version": MARKER_VERSION,
        "key": key,
        "python": "3.12",
        "requirements_sha256": requirements_digest(ROOT / spec.requirements),
    }
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, marker)


def repair_interpreter(key: str, base: Path) -> bool:
    """Retarget a populated venv while retaining its already installed wheels."""
    spec = RUNTIMES[key]
    environment = ROOT / spec.directory
    site_packages = environment / "lib" / "python3.12" / "site-packages"
    if not environment.is_dir() or not site_packages.is_dir():
        return False

    saved_links: dict[Path, str] = {}
    for name in ("python", "python3", "python3.12"):
        path = environment / "bin" / name
        if path.is_symlink():
            saved_links[path] = os.readlink(path)
            path.unlink()
    try:
        result = run([str(base), "-m", "venv", "--upgrade", str(environment)], 120)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0 and python_312(environment / "bin" / "python"):
        return True

    for path, target in saved_links.items():
        if not path.exists() and not path.is_symlink():
            path.symlink_to(target)
    return False


def install_requirements(key: str) -> bool:
    spec = RUNTIMES[key]
    python = ROOT / spec.directory / "bin" / "python"
    print(f"· 正在安装{spec.label}的锁定依赖（首次可能较慢）…", flush=True)
    try:
        result = run([
            str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
            "--requirement", str(ROOT / spec.requirements),
        ], 3600)
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode:
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["未知错误"]
        print(f"  {spec.label}依赖安装失败：{tail[0]}", file=sys.stderr, flush=True)
        return False
    return True


def probe_environment(key: str, environment: Path) -> bool:
    spec = RUNTIMES[key]
    try:
        result = run([str(environment / "bin" / "python"), "-I", "-c", spec.probe], 180)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def create_environment(key: str, base: Path) -> bool:
    spec = RUNTIMES[key]
    environment = ROOT / spec.directory
    backup = ROOT / f".{spec.directory.lstrip('.')}.replaced-{uuid.uuid4().hex}"
    published_backup = False
    completed = False
    try:
        if environment.exists() or environment.is_symlink():
            os.replace(environment, backup)
            published_backup = True
        result = run([str(base), "-m", "venv", str(environment)], 120)
        if result.returncode:
            return False
        result = run([
            str(environment / "bin" / "python"), "-m", "pip", "install",
            "--disable-pip-version-check", "--no-input", "--requirement",
            str(ROOT / spec.requirements),
        ], 3600)
        if result.returncode:
            tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["未知错误"]
            print(f"  {spec.label}依赖安装失败：{tail[0]}", file=sys.stderr, flush=True)
            return False
        if not probe_environment(key, environment):
            print(f"  {spec.label}依赖已安装，但真实导入验证失败。", file=sys.stderr, flush=True)
            return False
        completed = True
        if published_backup:
            try:
                shutil.rmtree(backup)
            except OSError:
                pass
            published_backup = False
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if not completed and environment.exists():
            shutil.rmtree(environment)
        if published_backup:
            os.replace(backup, environment)


def ensure_runtime(key: str, base: Path, check_only: bool = False) -> bool:
    spec = RUNTIMES[key]
    marker_current = marker_is_current(key)
    clear_runtime_cache()
    check = check_python_runtime(ROOT, key)
    if check.available and not environment_uses_ephemeral_python(ROOT, key):
        if not marker_current:
            write_marker(key)
        print(f"✓ {spec.label}运行环境已验证", flush=True)
        return True
    if check_only:
        print(f"✗ {check.message}", file=sys.stderr, flush=True)
        return False

    print(f"· 正在修复{spec.label}运行环境…", flush=True)
    repaired = repair_interpreter(key, base)
    if not repaired:
        repaired = create_environment(key, base)
    else:
        clear_runtime_cache()
        if not check_python_runtime(ROOT, key).available:
            repaired = install_requirements(key)

    clear_runtime_cache()
    check = check_python_runtime(ROOT, key)
    if repaired and check.available:
        write_marker(key)
        print(f"✓ {spec.label}运行环境修复完成", flush=True)
        return True
    print(f"✗ {check.message} 原视频和已有分析结果不受影响。", file=sys.stderr, flush=True)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="验证并修复拉片工作台的本地模型环境")
    parser.add_argument("--check", action="store_true", help="只检查，不修复")
    parser.add_argument("--runtime", action="append", choices=sorted(RUNTIMES), help="只处理指定环境")
    args = parser.parse_args()
    keys = args.runtime or list(RUNTIMES)
    base = find_base_python()
    if base is None:
        print("找不到稳定的 Python 3.12。请先安装 Python 3.12（macOS 可用 brew install python@3.12）。",
              file=sys.stderr, flush=True)
        return 1
    print(f"使用本机 Python 3.12：{base}", flush=True)
    results = [ensure_runtime(key, base, args.check) for key in keys]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
