"""Local deterministic media tools; no model-generated executable arguments."""
from pathlib import Path
import json
import math
import re
import sys
from provider import run_process

REPO = Path(__file__).resolve().parents[2]
WORKBENCH = REPO / "prototypes/broll-workbench"


def probe(path):
    info = json.loads(run_process(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path], timeout=40))
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    duration = float(info.get("format", {}).get("duration", 0))
    return {"duration": duration, "width": video.get("width", 0) if video else 0,
            "height": video.get("height", 0) if video else 0, "has_audio": bool(audio),
            "has_video": bool(video), "format": info.get("format", {}).get("format_name", ""),
            "fps": video.get("avg_frame_rate", "0/1") if video else "0/1"}


def extract_frame(path, seconds, output):
    if not math.isfinite(float(seconds)) or seconds < 0: raise ValueError("抽帧时间无效。")
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    run_process(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds), "-i", path,
                 "-frames:v", "1", "-vf", "scale=960:-2", output], timeout=45)
    if not output.is_file(): raise ValueError("该时间点没有可解码的视频帧。")
    return output


def workbench_projects():
    result = []
    for file in sorted((WORKBENCH / "data").glob("*/project.json")):
        try:
            p = json.loads(file.read_text())
            if not (file.parent / "source.mp4").is_file(): continue
            result.append({"id": p["id"], "name": p["name"], "duration": p["duration"],
                           "segments": len(p.get("transcript", {}).get("segments", [])), "has_transcript": bool(p.get("transcript", {}).get("segments"))})
        except (OSError, ValueError, KeyError): continue
    return result


def read_workbench(identity):
    if not re.fullmatch(r"[a-f0-9]{32}", str(identity)): raise ValueError("工作台项目ID无效。")
    directory = WORKBENCH / "data" / identity
    p = json.loads((directory / "project.json").read_text())
    return p, directory / "source.mp4"


def transcribe(path, cancel=None):
    script = WORKBENCH / "tools/transcribe.py"
    # Reuse the verified adapter: it owns Metal -> CPU fallback and timed Whisper output.
    python = WORKBENCH / ".venv/bin/python"
    if not script.is_file(): raise ValueError("本地转录适配器不可用。可导入带时间码字幕。")
    raw = run_process([python if python.exists() else sys.executable, script, str(path)], timeout=1200, cancel=cancel)
    try:
        data = json.loads(raw)
        return data["segments"]
    except (ValueError, KeyError): raise ValueError("转录未返回有效字幕，可导入带时间码字幕。") from None
