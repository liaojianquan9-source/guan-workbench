"""Keep the user-selected process source auditable across future handoffs."""
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class ProcessBundleTests(unittest.TestCase):
    def test_upstream_files_are_complete_and_unmodified(self):
        bundle = ROOT / 'docs/process/ai-product-starter-kit'
        manifest = json.loads((bundle / 'UPSTREAM.json').read_text())
        self.assertEqual(manifest['commit'], '955871e830e8ec29abfbdee688fff89992fede40')
        self.assertEqual(manifest['license'], 'MIT')
        self.assertIn('AGENTS.md', manifest['files'])
        self.assertIn('LICENSE', manifest['files'])
        for name, expected in manifest['files'].items():
            with self.subTest(file=name):
                path = (bundle / name).resolve()
                self.assertTrue(path.is_relative_to(bundle.resolve()))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_handoff_entrypoints_exist(self):
        for relative in ('docs/项目状态.md', 'docs/阶段文档/2026-09-21-现有工作台修复.md',
                         'docs/evidence/阶段2-现有工作台/README.md'):
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
        self.assertIn('docs/项目状态.md', (ROOT / 'AGENTS.md').read_text())


if __name__ == '__main__':
    unittest.main()
