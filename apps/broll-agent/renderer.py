"""Audited Remotion adapters and frame-accurate local composition.

Only IDs in ADAPTERS may execute code. Asset metadata and uploaded files never
select a shell command or an arbitrary source module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from functools import wraps

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME = HERE / "renderer"
FPS = 30
# These are reviewed release identities, not hashes computed from mutable input.
AUDITED_MANIFEST_SHA256 = "3e1d1de36f5df5853c049d2c16d70a503c9a4dc7a8bf1430f92c3b395e8ae36e"
AUDITED_DEPENDENCIES = {
    "package.json": "f9112e4a4d7505c120ca528a1e2a8fb6b82b1cbd26f62a5b439f5f740a6a2b97",
    "package-lock.json": "a0a31012c253d6bb3b8d72a7a69223d57848b026e7e9b6e4b09f50355a410fcc",
}
RENDER_GATE = threading.RLock()


def serialized(function):
    @wraps(function)
    def call(*args, **kwargs):
        with RENDER_GATE:
            return function(*args, **kwargs)
    return call

ADAPTERS = {
    "kimi-moon-v1": {"folder": "kimi", "frames": (172, 299), "poster": 247,
        "fields": {"title": ("text", "B-ROLL", 14), "subtitle": ("text", "复刻", 8),
                   "texture_text": ("text", "可复用", 12), "image": ("image", None, None)}},
    "kimi-number-v1": {"folder": "kimi", "frames": (99, 171), "poster": 164,
        "fields": {"number": ("text", "28000", 8), "unit": ("text", "亿", 6),
                   "label": ("text", "个参数", 14), "annotation": ("text", "参数规模", 38)}},
    "problem-photo-v1": {"folder": "problem", "frames": (4, 79), "poster": 50,
        "fields": {"kicker": ("text", "本期实践", 14), "title": ("text", "复刻镜头", 10),
                   "subtitle": ("text", "REUSABLE B-ROLL", 34), "image": ("image", None, None)}},
}


def run_command(argv, *, cwd=None, timeout=600, log=None):
    """Kill all descendants on failure, including children ignoring SIGTERM."""
    argv = [str(a) for a in argv]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        failure = None
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            failure = error
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            # Parent exit is not proof that its whole process group exited.
            time.sleep(.15)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        stdout.seek(0); stderr.seek(0)
        out, err = stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")
        if log:
            Path(log).write_text(json.dumps({"argv": argv, "returncode": process.returncode,
                "stdout": out, "stderr": err, "timed_out": isinstance(failure, subprocess.TimeoutExpired),
                "error": str(failure) if failure else None}, ensure_ascii=False, indent=2))
        if isinstance(failure, subprocess.TimeoutExpired):
            raise ValueError(f"{Path(argv[0]).name} 超时（{timeout} 秒），进程组已终止，诊断已保存") from failure
        if failure:
            raise failure
        if process.returncode:
            raise ValueError(f"{Path(argv[0]).name} failed: {(err or out)[-1800:]}")
        return out


def probe(path):
    result = json.loads(run_command(["ffprobe", "-v", "error", "-show_streams",
        "-show_format", "-of", "json", path], timeout=45))
    videos = [s for s in result["streams"] if s["codec_type"] == "video"]
    if not videos:
        raise ValueError("媒体没有可读取的视频轨道")
    video = videos[0]
    a, b = video.get("avg_frame_rate", "0/1").split("/")
    return {"width": video["width"], "height": video["height"],
        "fps": float(a) / max(float(b), 1),
        "duration": float(video.get("duration", result["format"].get("duration", 0))),
        "frames": int(video["nb_frames"]) if video.get("nb_frames", "N/A") != "N/A" else None,
        "has_audio": any(s["codec_type"] == "audio" for s in result["streams"])}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def adapter_signature(renderer_id):
    value = {"adapter": ADAPTERS[renderer_id], "props_mapping_version": 1,
             "number_weights_label": "", "font_policy": "explicit-browser-audit-v1"}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _manifest(path):
    if not path.is_file() or sha256(path) != AUDITED_MANIFEST_SHA256:
        raise ValueError("源码清单不属于已审查版本；请恢复原包或发布新样式版本")
    records = json.loads(path.read_text())
    if not isinstance(records, list):
        raise ValueError("无效源码清单")
    return records


def verify_source(root, folder, *, packaged=False):
    """Validate all selected files and reject added code, paths, and symlinks."""
    root = Path(root)
    records = _manifest(root / "SOURCE-MANIFEST.json")
    expected = {}
    for record in records:
        name = record["file"]
        if not name.startswith(folder + "/"):
            continue
        relative = Path(name[len(folder)+1:] if packaged else name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("源码清单包含越界路径")
        file = root / relative
        if file.is_symlink() or not file.is_file() or sha256(file) != record["sha256"]:
            raise ValueError(f"固定版本源码或素材被修改: {relative}")
        expected[str(relative)] = record["sha256"]
    if not expected:
        raise ValueError("源码清单缺少当前执行器")
    selected = root if packaged else root / folder
    allowed_root = {"SOURCE-MANIFEST.json", *AUDITED_DEPENDENCIES}
    for file in selected.rglob("*"):
        if file.is_dir() and not file.is_symlink():
            continue
        relative = str(file.relative_to(root))
        if packaged and relative in allowed_root:
            continue
        if relative not in expected:
            raise ValueError(f"固定版本包含未审查文件: {relative}")
    for name, expected_hash in AUDITED_DEPENDENCIES.items():
        if not (root / name).is_file() or sha256(root / name) != expected_hash:
            raise ValueError(f"依赖锁与审查版本不一致: {name}")
    return expected


FONT_PROBE_SCRIPT = r"""
const fs = require('fs');
const path = require('path');
const {openBrowser} = require(path.join(process.argv[1], 'node_modules/@remotion/renderer'));
const input = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await openBrowser('chrome', {browserExecutable: process.argv[2], logLevel: 'error'});
  try {
    const page = await browser.newPage({context: () => null, logLevel:'error', indent:false,
      pageIndex:0, onBrowserLog:null, onLog:() => {}});
    await page.evaluate(async data => {
      for (const f of data.custom) {
        const face = new FontFace(f.family, f.source);
        await face.load(); document.fonts.add(face);
      }
      for (const [i, f] of data.fields.entries()) {
        const div = document.createElement('div'); div.id='font-'+i;
        div.style.fontFamily=f.family; div.style.fontSize='60px';
        div.style.fontWeight=String(f.weight || 400); div.textContent=f.text;
        document.body.appendChild(div); await document.fonts.load(`${f.weight || 400} 60px "${f.family}"`, f.text);
      }
      await document.fonts.ready;
    }, input);
    const client=page._client(); await client.send('DOM.enable'); await client.send('CSS.enable');
    const {root}=(await client.send('DOM.getDocument')).value; const result=[];
    for (const [i, f] of input.fields.entries()) {
      const {nodeId}=(await client.send('DOM.querySelector',{nodeId:root.nodeId,selector:'#font-'+i})).value;
      const {fonts}=(await client.send('CSS.getPlatformFontsForNode',{nodeId})).value;
      result.push({...f,fonts});
    }
    process.stdout.write(JSON.stringify(result));
  } finally {await browser.close({silent:true});}
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});
"""


def validate_fields(renderer_id, fields):
    if renderer_id not in ADAPTERS:
        raise ValueError("未知或未审查的样式执行器")
    if not isinstance(fields, dict):
        raise ValueError("fields 必须为对象")
    schema = ADAPTERS[renderer_id]["fields"]
    unknown = set(fields) - set(schema)
    if unknown:
        raise ValueError(f"样式不支持字段: {', '.join(sorted(unknown))}")
    normalized = {}
    for key, (kind, default, maximum) in schema.items():
        value = fields.get(key, default)
        if kind == "text":
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{key} 需要 1–{maximum} 字符；请缩短或换用别的样式")
            normalized[key] = value
        elif value is not None:
            if (not isinstance(value, dict) or set(value) != {"asset_id", "revision"}
                    or not isinstance(value["asset_id"], str)
                    or type(value["revision"]) is not int or value["revision"] < 1):
                raise ValueError(f"{key} 必须引用固定版本的图片资产")
            normalized[key] = value
    return normalized


def layout_check(renderer_id, fields):
    """Guard known fixed-ink boxes; this is narrower than full visual QA."""
    issues = []
    if renderer_id == "kimi-moon-v1":
        for name, box, mixed_limit, latin_limit in [("subtitle", [163, 119], 4, 5),
                                                   ("title", [306, 117], 4, 9)]:
            text = fields[name]
            mixed = any(ord(char) > 127 for char in text)
            limit = mixed_limit if mixed else latin_limit
            if len(text) > limit:
                issues.append({"field": name, "code": "fixed_box_text_compression",
                    "severity": "needs_revision", "box": box, "characters": len(text),
                    "recommended_max_characters": limit,
                    "message": f"{name} 的 {box[0]}×{box[1]} 固定字面框会将 {len(text)} 字符横向压窄；缩短到 {limit} 字符内或换样式。"})
    return {"status": "needs_revision" if issues else "passed", "issues": issues,
        "scope": "已知固定框的保守可读性门；通过不代替用户视觉审看。"}


class Renderer:
    def __init__(self, asset_client, work_root):
        self.assets = asset_client
        self.work_root = Path(work_root).resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)

    def _runtime(self):
        modules = RUNTIME / "node_modules"
        if not modules.exists():
            candidates = [REPO / "outputs/talking-head-260907/replacement-demo/node_modules",
                REPO / "publications/ljq-broll-video-generator/skills/ljq-broll-replica/assets/remotion-renderer/node_modules",
                REPO / "skills/broll-layout-video/assets/remotion-renderer/node_modules"]
            for candidate in candidates:
                if (candidate / "@remotion/cli/remotion-cli.js").exists():
                    try:
                        modules.symlink_to(candidate.resolve(), target_is_directory=True)
                    except FileExistsError:
                        pass
                    break
        cli = modules / "@remotion/cli/remotion-cli.js"
        if not cli.exists():
            raise ValueError(f"Remotion 依赖缺失；在 {RUNTIME} 运行 npm ci")
        for package, version in {"remotion": "4.0.518", "@remotion/cli": "4.0.518",
                "@remotion/renderer": "4.0.518", "react": "19.2.8", "react-dom": "19.2.8", "zod": "4.4.3"}.items():
            installed = json.loads((modules / package / "package.json").read_text()).get("version")
            if installed != version:
                raise ValueError(f"{package} 运行版本 {installed} 与样式锁定版本 {version} 不一致")
        node = shutil.which("node")
        if not node:
            raise ValueError("需要 Node.js 才能运行 Remotion")
        browser = os.environ.get("BROLL_CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if not Path(browser).is_file():
            browser = shutil.which("chromium") or shutil.which("google-chrome")
        if not browser:
            raise ValueError("未找到 Chrome；请设置 BROLL_CHROME_PATH")
        return [node, str(cli)], str(browser)

    def source_snapshot(self, style_asset, destination):
        metadata = style_asset.get("metadata", {})
        renderer_id = metadata.get("renderer_id")
        if renderer_id not in ADAPTERS:
            raise ValueError("未知执行器")
        expected = metadata.get("source_manifest_sha256")
        if expected != AUDITED_MANIFEST_SHA256:
            raise ValueError("样式固定版本的源码清单不匹配；不能用当前代码替代旧版本")
        signature = metadata.get("adapter_contract_sha256")
        if signature is not None and signature != adapter_signature(renderer_id):
            raise ValueError("样式参数适配合同版本已变化，需要原执行器或新样式版本")
        folder = ADAPTERS[renderer_id]["folder"]
        destination = Path(destination)
        package_hash = metadata.get("package_hash") or style_asset.get("blob_hash")
        # Prefer the immutable shared package. A mutable checkout is only a
        # bootstrap source before first publication, and is copied and verified.
        if package_hash:
            package = Path(self.assets.blob_path(package_hash))
            if sha256(package) != package_hash:
                raise ValueError("样式包 SHA-256 与固定版本不符")
            destination.mkdir(parents=True, exist_ok=False)
            with zipfile.ZipFile(package) as archive:
                members = archive.infolist()
                if len(members) > 100 or sum(m.file_size for m in members) > 128*1024*1024:
                    raise ValueError("样式包超过已审查大小限制")
                names = set()
                for member in members:
                    name = Path(member.filename)
                    if (member.filename in names or name.is_absolute() or ".." in name.parts
                            or "\\" in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000):
                        raise ValueError("样式包包含重复、符号链接或越界文件")
                    names.add(member.filename)
                    if member.is_dir():
                        continue
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
            verify_source(destination, folder, packaged=True)
            origin = "immutable_asset_package"
        else:
            verify_source(RUNTIME, folder)
            shutil.copytree(RUNTIME / folder, destination)
            for name in ["SOURCE-MANIFEST.json", *AUDITED_DEPENDENCIES]:
                shutil.copyfile(RUNTIME / name, destination / name)
            verify_source(destination, folder, packaged=True)
            origin = "verified_builtin_snapshot"
        return destination, {"source_manifest_sha256": expected, "source_origin": origin,
            "package_hash": package_hash, "adapter_contract_sha256": adapter_signature(renderer_id)}

    def font_report(self, renderer_id, fields, source, output, cli, browser):
        import base64
        if renderer_id == "problem-photo-v1":
            font = source / "remotion/public/assets/fonts/YouSheBiaoTiHei.ttf"
            custom = [{"family": "BrollDisplay", "source": "url(data:font/ttf;base64," + base64.b64encode(font.read_bytes()).decode() + ")"},
                {"family": "BrollSubtitle", "source": 'local("STHeitiSC-Light")'},
                {"family": "BrollTech", "source": 'local("Monaco")'}]
            requests = [{"field": "title", "family": "BrollDisplay", "text": fields["title"], "expected": ["YouSheBiaoTiHei", "优设标题黑"]},
                {"field": "kicker", "family": "BrollSubtitle", "text": fields["kicker"], "expected": ["Heiti SC", "黑体-简"]},
                {"field": "subtitle", "family": "BrollTech", "text": fields["subtitle"], "expected": ["Monaco"]}]
        elif renderer_id == "kimi-moon-v1":
            custom = []
            requests = [{"field": "title", "family": "Helvetica Neue", "text": fields["title"], "weight": 700, "expected": ["Helvetica Neue"]},
                {"field": "subtitle", "family": "Helvetica Neue", "text": fields["subtitle"], "weight": 700, "expected": ["Helvetica Neue"]},
                {"field": "texture_text", "family": "Songti SC", "text": fields["texture_text"], "weight": 900, "expected": ["Songti SC", "宋体-简"]}]
        else:
            custom = []
            requests = [{"field": "number", "family": "Impact", "text": fields["number"], "expected": ["Impact"]}]
            requests += [{"field": name, "family": "Songti SC", "text": fields[name],
                          "weight": 700 if name == "annotation" else 900, "expected": ["Songti SC", "宋体-简"]}
                         for name in ["unit", "label", "annotation"]]
        request = output / "font-request.json"
        request.write_text(json.dumps({"custom": custom, "fields": requests}, ensure_ascii=False))
        result = json.loads(run_command([cli[0], "-e", FONT_PROBE_SCRIPT, str(RUNTIME), browser, request],
            timeout=60, log=output / "font-command.json"))
        warnings = []
        for record in result:
            fonts = record["fonts"]
            if not fonts or any("lastresort" in (f.get("familyName", "") + f.get("postScriptName", "")).lower() for f in fonts):
                raise ValueError(f"{record['field']} 含当前字体无法显示的字符；请换字或安装受支持字体")
            fallback = [font for font in fonts if font["familyName"] not in record["expected"]]
            record["fallback_detected"] = bool(fallback)
            if fallback:
                warnings.append({"field": record["field"], "requested": record["family"],
                    "actual": [font["familyName"] for font in fonts],
                    "message": "浏览器实际使用了回退字体；字形与参考可能不同，需要查看当前预览"})
        report = {"status": "loaded", "method": "Chrome CSS.getPlatformFontsForNode，实际文字逐字段检查",
            "fields": result, "warnings": warnings, "visual_review_required": bool(warnings),
            "subset_note": "问题页 BrollDisplay 仅包含原案例有限汉字，不承诺任意中文仍使用优设字形。"}
        (output / "fonts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    def _props(self, renderer_id, fields, public):
        image_path = None
        if fields.get("image"):
            reference = fields["image"]
            asset = self.assets.get_asset(reference["asset_id"], reference["revision"])
            if asset["kind"] != "image" or not asset.get("blob_hash"):
                raise ValueError("替换槽位需要已入库的图片")
            source = Path(self.assets.blob_path(asset["blob_hash"]))
            # Browser image decoding identifies type from bytes; no untrusted suffix.
            image_path = f"replacement/{asset['blob_hash']}.image"
            target = public / image_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if renderer_id == "kimi-moon-v1":
            props = {"motionEnabled": True, "kimiTitle": fields["title"],
                "k3Title": fields["subtitle"], "moonTitle": fields["texture_text"]}
            if image_path:
                props.update(moonTopImage=image_path, moonBottomImage=image_path)
            return props
        if renderer_id == "kimi-number-v1":
            return {"motionEnabled": True, "mainNumber": fields["number"],
                "billionUnit": fields["unit"], "parameterUnit": fields["label"],
                "annotationCopy": fields["annotation"], "weightsLabel": ""}
        props = {"motionEnabled": True, "content": {"problem-kicker": fields["kicker"],
            "problem-title": fields["title"], "problem-english": fields["subtitle"]}}
        if image_path:
            props["assets"] = {"problem-background": image_path}
        return props

    @serialized
    def render(self, style_asset, fields, output_dir, *, duration=None):
        renderer_id = style_asset.get("metadata", {}).get("renderer_id")
        actual = validate_fields(renderer_id, fields)
        layout = layout_check(renderer_id, actual)
        adapter = ADAPTERS[renderer_id]
        start, end = adapter["frames"]
        native_frames = end - start + 1
        requested = native_frames / FPS if duration is None else duration
        if (isinstance(requested, bool) or not isinstance(requested, (int, float))
                or not math.isfinite(requested) or requested < .4 or requested > 15):
            raise ValueError("样式时长须为 0.4–15 秒")
        frames = round(requested * FPS)
        target_duration = frames / FPS
        out = Path(output_dir).resolve() / f"render-{uuid.uuid4().hex[:12]}"
        out.mkdir(parents=True, exist_ok=False)
        source, version_evidence = self.source_snapshot(style_asset, out / "runtime")
        public = out / "public"
        shutil.copytree(source / "remotion/public", public)
        props = self._props(renderer_id, actual, public)
        props_file = out / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False, indent=2))
        cli, browser = self._runtime()
        fonts = self.font_report(renderer_id, actual, source, out, cli, browser)
        (source / "node_modules").symlink_to((RUNTIME / "node_modules").resolve(), target_is_directory=True)
        common = [str(source / "remotion/composition.tsx"), "LjqBrollCase"]
        flags = [f"--public-dir={public}", f"--props={props_file}", f"--browser-executable={browser}", "--concurrency=2"]
        native = out / "native.mp4"
        run_command(cli + ["render"] + common + [str(native), f"--frames={start}-{end}",
            "--codec=h264", "--crf=20", "--muted"] + flags,
            cwd=RUNTIME, log=out / "render-command.json")
        video = out / "preview.mp4"
        if frames == native_frames:
            shutil.copyfile(native, video)
        else:
            ratio = frames / native_frames
            run_command(["ffmpeg", "-v", "error", "-i", native, "-vf",
                f"setpts={ratio:.12f}*PTS,fps={FPS},tpad=stop_mode=clone:stop_duration=1",
                "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "fast",
                "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
                log=out / "retime-command.json")
        metadata = probe(video)
        checks = {"dimensions": metadata["width"] == 1280 and metadata["height"] == 720,
            "fps": abs(metadata["fps"] - FPS) < .001, "frames": metadata["frames"] == frames,
            "audio": not metadata["has_audio"], "duration": abs(metadata["duration"] - target_duration) < 1/FPS}
        if not all(checks.values()):
            raise ValueError(f"样式媒体核验失败: {checks}")
        run_command(["ffmpeg", "-v", "error", "-i", video, "-f", "null", "-"], timeout=90)
        poster = out / "poster.jpg"
        poster_time = min(target_duration - 1/FPS, (adapter["poster"]-start) / native_frames * target_duration)
        run_command(["ffmpeg", "-v", "error", "-ss", str(poster_time), "-i", video,
            "-frames:v", "1", "-q:v", "2", poster], timeout=45)
        report = {"status": "passed", "renderer_id": renderer_id, "style": {
            "asset_id": style_asset.get("id"), "revision": style_asset.get("revision")},
            "fields": actual, "props": props, "native_frames": [start, end],
            "media": metadata, "checks": checks, "full_decode": True,
            "video_sha256": sha256(video), **version_evidence, "fonts": fonts, "layout": layout,
            "adapter_sha256": sha256(Path(__file__)),
            "fidelity_status": style_asset.get("metadata", {}).get("fidelity_status", "needs_review"),
            "note": "技术通过表示参数真实进入 Remotion 且媒体可解码；不等于参考保真或任意文案视觉验收。"}
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return {"video": str(video), "poster": str(poster), "report": report}

    @serialized
    def compose(self, source_path, approved_cards, output_path):
        source = Path(source_path).resolve()
        metadata = probe(source)
        cards = sorted(approved_cards, key=lambda c: c["start"])
        previous_end = -1
        for card in cards:
            start, end = card["start"], card["end"]
            if (not isinstance(start, (float, int)) or not isinstance(end, (float, int))
                    or not math.isfinite(start + end) or start < 0 or end <= start
                    or end > metadata["duration"] + 1/metadata["fps"] or start < previous_end):
                raise ValueError("批准片段须在原视频范围内且不能互相重叠")
            path = Path(card["render_path"])
            rendered = probe(path)
            if abs(rendered["duration"] - (end-start)) > 2 / metadata["fps"]:
                raise ValueError("预览时长与批准片段不一致，请重新渲染当前版本")
            previous_end = end
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            raise ValueError("输出已存在，请使用新的成片版本")
        args = ["ffmpeg", "-v", "error", "-i", source]
        for card in cards:
            args += ["-i", card["render_path"]]
        width, height = metadata["width"], metadata["height"]
        graph, base = [], "0:v"
        for index, card in enumerate(cards, 1):
            layer, result = f"layer{index}", f"out{index}"
            crop = card.get("crop_mode", "contain")
            transition = card.get("transition", "cut")
            if crop not in ("contain", "cover") or transition not in ("cut", "dissolve"):
                raise ValueError("未知画幅或转场参数。")
            fit = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101010") if crop == "contain" else (
                   f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                   f"crop={width}:{height}")
            fade = ""
            if transition == "dissolve":
                fade_duration = min(.25, (card["end"]-card["start"])/3)
                fade = (f",format=yuva420p,fade=t=in:st=0:d={fade_duration:.6f}:alpha=1,"
                        f"fade=t=out:st={card['end']-card['start']-fade_duration:.6f}:d={fade_duration:.6f}:alpha=1")
            graph.append(f"[{index}:v]{fit},setsar=1{fade},"
                f"setpts=PTS-STARTPTS+{card['start']:.9f}/TB[{layer}]")
            graph.append(f"[{base}][{layer}]overlay=0:0:eof_action=pass:repeatlast=0:"
                f"enable='gte(t,{card['start']:.9f})*lt(t,{card['end']:.9f})'[{result}]")
            base = result
        if graph:
            args += ["-filter_complex", ";".join(graph), "-map", f"[{base}]"]
        else:
            args += ["-map", "0:v:0"]
        args += ["-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)]
        run_command(args, timeout=1800, log=out.with_suffix(".command.json"))
        final = probe(out)
        checks = {"dimensions": (final["width"], final["height"]) == (width, height),
            "duration": abs(final["duration"]-metadata["duration"]) <= 1/metadata["fps"]+.002,
            "audio": final["has_audio"] == metadata["has_audio"],
            "fps": abs(final["fps"]-metadata["fps"]) < .001}
        if not all(checks.values()):
            raise ValueError(f"成片核验失败: {checks}")
        run_command(["ffmpeg", "-v", "error", "-i", out, "-f", "null", "-"], timeout=600)
        report = {"status": "passed", "checks": checks, "source": metadata, "media": final,
            "full_decode": True, "audio_method": "原口播音轨直接复制", "card_ids": [c["id"] for c in cards],
            "video_sha256": sha256(out), "layout": "逐片段按画幅选项合成", "effects": [
                {"card_id": c["id"], "crop_mode": c.get("crop_mode", "contain"),
                 "transition": c.get("transition", "cut")} for c in cards]}
        out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return {"video": str(out), "report": report}
