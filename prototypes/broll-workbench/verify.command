#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"

test_python="${BROLL_TEST_PYTHON:-.venv/bin/python}"
if [[ ! -x "$test_python" ]]; then
  test_python="$(command -v python3.12 2>/dev/null || command -v python3 2>/dev/null || true)"
fi
if [[ -z "$test_python" ]]; then
  print -u2 "找不到可用的 Python。"
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  print -u2 "找不到 Node.js，无法运行前端回归测试。"
  exit 1
fi

"$test_python" -m compileall -q server.py storage.py research_clips.py runtime_env.py \
  music_sections.py playback_proxies.py tools tests
"$test_python" -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.cjs
"$test_python" tools/bootstrap_runtime.py --check

print "验证完成：语法、后端、前端与本地 AI 环境全部通过。"
