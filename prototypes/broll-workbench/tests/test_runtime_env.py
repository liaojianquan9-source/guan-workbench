"""Runtime health checks and repair never rely on disposable Codex Python paths."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from runtime_env import (
    check_python_runtime,
    clear_runtime_cache,
    environment_uses_ephemeral_python,
)


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SPEC = importlib.util.spec_from_file_location(
    "broll_runtime_bootstrap", ROOT / "tools" / "bootstrap_runtime.py"
)
bootstrap = importlib.util.module_from_spec(BOOTSTRAP_SPEC)
BOOTSTRAP_SPEC.loader.exec_module(bootstrap)


class RuntimeHealthTest(unittest.TestCase):
    def test_dangling_interpreter_is_not_reported_as_available(self):
        with tempfile.TemporaryDirectory(prefix="broll-runtime-health-") as temporary:
            root = Path(temporary)
            binary = root / ".venv" / "bin"
            binary.mkdir(parents=True)
            (binary / "python").symlink_to(root / "deleted-codex-runtime" / "python")
            clear_runtime_cache()
            check = check_python_runtime(root, "scenes", timeout=2)
            self.assertFalse(check.available)
            self.assertIn("失效", check.message)

    def test_pyvenv_config_rejects_codex_runtime_even_if_link_changes(self):
        with tempfile.TemporaryDirectory(prefix="broll-runtime-origin-") as temporary:
            root = Path(temporary)
            environment = root / ".venv"
            (environment / "bin").mkdir(parents=True)
            (environment / "pyvenv.cfg").write_text(
                "home = /Users/example/.cache/codex-runtimes/codex-primary-runtime/python\n",
                encoding="utf-8",
            )
            self.assertTrue(environment_uses_ephemeral_python(root, "scenes"))

    @unittest.skipUnless(shutil.which("python3.12"), "Python 3.12 is required for repair regression")
    def test_repair_retargets_populated_environment_to_stable_python(self):
        base = Path(shutil.which("python3.12"))
        with tempfile.TemporaryDirectory(prefix="broll-runtime-repair-") as temporary:
            root = Path(temporary)
            environment = root / ".venv"
            subprocess.run([str(base), "-m", "venv", str(environment)], check=True, timeout=60)
            for name in ("python", "python3", "python3.12"):
                path = environment / "bin" / name
                if path.is_symlink():
                    path.unlink()
                path.symlink_to("/deleted/.cache/codex-runtimes/codex-primary-runtime/python3.12")
            (environment / "pyvenv.cfg").write_text(
                "home = /deleted/.cache/codex-runtimes/codex-primary-runtime/bin\n",
                encoding="utf-8",
            )
            with patch.object(bootstrap, "ROOT", root):
                self.assertTrue(bootstrap.repair_interpreter("scenes", base))
            result = subprocess.run(
                [str(environment / "bin" / "python"), "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("(3, 12)", result.stdout)
            self.assertFalse(environment_uses_ephemeral_python(root, "scenes"))


if __name__ == "__main__":
    unittest.main()
