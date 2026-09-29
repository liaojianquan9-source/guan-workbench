#!/bin/zsh
set -u
cd "${0:A:h}"

bootstrap_python="${BROLL_PYTHON_312:-}"
if [[ -z "$bootstrap_python" ]]; then
  bootstrap_python="$(command -v python3.12 2>/dev/null || command -v python3)"
fi

if [[ "${BROLL_SKIP_RUNTIME_BOOTSTRAP:-0}" != "1" ]]; then
  if ! "$bootstrap_python" tools/bootstrap_runtime.py; then
    print -u2 "本地 AI 环境未全部就绪；工作台仍会打开，原视频和已有资料不会被改动。"
  fi
fi

server_python="$bootstrap_python"
if [[ -x .venv/bin/python ]]; then
  server_python="${BROLL_SERVER_PYTHON:-.venv/bin/python}"
fi
if [[ -f ../../apps/broll-agent/launch.py ]]; then
  exec "$server_python" ../../apps/broll-agent/launch.py
fi
exec "$server_python" server.py
