#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: render-video.sh <layout.json> <output.mp4>" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
renderer_dir="$(cd "$script_dir/../assets/remotion-renderer" && pwd)"
layout_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
output_dir="$(cd "$(dirname "$2")" && pwd)"
output_path="$output_dir/$(basename "$2")"

if [ ! -f "$layout_path" ]; then
  echo "Layout not found: $layout_path" >&2
  exit 2
fi

if [ ! -d "$renderer_dir/node_modules" ]; then
  npm install --prefix "$renderer_dir"
fi

cd "$renderer_dir"
browser_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ -x "$browser_path" ]; then
  npx remotion render src/index.ts BrollLayout "$output_path" --props="$layout_path" --codec=h264 --browser-executable="$browser_path" --concurrency=1
else
  npx remotion render src/index.ts BrollLayout "$output_path" --props="$layout_path" --codec=h264 --concurrency=1
fi
