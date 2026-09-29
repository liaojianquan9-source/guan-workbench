import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('broll_launch', ROOT / 'apps/broll-agent/launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class LaunchTests(unittest.TestCase):
    def test_existing_service_is_not_owned_or_restarted(self):
        children = []
        with patch.object(launch, 'reachable', return_value=True), patch.object(launch.subprocess, 'Popen') as start:
            launch.start_service('http://127.0.0.1/health', ['python'], children, 'service')
        start.assert_not_called()
        self.assertEqual(children, [])

    def test_start_waits_for_actual_readiness(self):
        child = Mock(); child.poll.return_value = None
        children = []
        with patch.object(launch, 'reachable', side_effect=[False, False, True]), \
             patch.object(launch.subprocess, 'Popen', return_value=child), patch.object(launch.time, 'sleep') as sleep:
            launch.start_service('http://127.0.0.1/health', ['python'], children, 'service')
        self.assertEqual(children, [child])
        sleep.assert_called_once_with(.1)

    def test_dead_process_is_failure_and_still_owned_for_cleanup(self):
        child = Mock(); child.poll.return_value = 1
        children = []
        with patch.object(launch, 'reachable', return_value=False), \
             patch.object(launch.subprocess, 'Popen', return_value=child):
            with self.assertRaisesRegex(RuntimeError, '启动失败'):
                launch.start_service('http://127.0.0.1/health', ['python'], children, 'service')
        self.assertEqual(children, [child])

    def test_original_start_entry_runs_integrated_launcher(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); workbench = root / 'prototypes/broll-workbench'
            (workbench / '.venv/bin').mkdir(parents=True)
            launcher = root / 'apps/broll-agent/launch.py'
            launcher.parent.mkdir(parents=True); launcher.write_text('# fixture')
            start = workbench / 'start.command'
            start.write_bytes((ROOT / 'prototypes/broll-workbench/start.command').read_bytes())
            fake = workbench / '.venv/bin/python'
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); fake.chmod(0o755)
            import os
            result = subprocess.run(['zsh', str(start)], capture_output=True, text=True,
                env={**os.environ, 'BROLL_SKIP_RUNTIME_BOOTSTRAP': '1', 'BROLL_SERVER_PYTHON': str(fake)}, check=True)
            self.assertEqual(result.stdout.strip(), '../../apps/broll-agent/launch.py')
