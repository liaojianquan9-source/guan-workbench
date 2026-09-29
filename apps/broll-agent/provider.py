"""Model decisions only. Product tools and persistence live outside the model process."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

ACTIONS = ["inspect_video", "search_assets", "inspect_style", "read_history", "propose_draft", "check_draft", "revise_draft", "finish"]
ACTION_SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ACTIONS},
    "rationale": {"type": "string"},
    "arguments_json": {"type": "string"}},
    "required": ["action", "rationale", "arguments_json"], "additionalProperties": False}


class ModelError(RuntimeError):
    pass


def run_process(argv, *, cwd=None, stdin=None, timeout=180, cancel=None):
    """No shell. Kill the whole process group on timeout/cancel, including browser children."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as inp:
        if stdin is not None:
            inp.write(stdin.encode()); inp.seek(0)
        p = subprocess.Popen([str(x) for x in argv], cwd=cwd, stdin=inp, stdout=out, stderr=err, start_new_session=True)
        started = time.monotonic()
        try:
            while p.poll() is None:
                if cancel and cancel.is_set():
                    raise InterruptedError("任务已取消，已保存中间结果。")
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"工具超时（{timeout} 秒），中间结果已保留。")
                time.sleep(.15)
        except BaseException:
            try: os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: p.wait(3)
            except subprocess.TimeoutExpired:
                try: os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                p.wait()
            raise
        out.seek(0); err.seek(0)
        stdout, stderr = out.read().decode(errors="replace"), err.read().decode(errors="replace")
        if p.returncode:
            # CLI messages may contain environment data; do not persist raw stderr to the public trace.
            raise ModelError(f"{Path(str(argv[0])).name} 退出码 {p.returncode}。请检查本机登录、模型权限或工具环境。")
        return stdout


class CodexProvider:
    def __init__(self, model=None, timeout=180):
        self.model = model or os.environ.get("BROLL_MODEL", "gpt-6-astra")
        self.timeout = timeout
        self.executable = os.environ.get("BROLL_CODEX", shutil.which("codex") or "codex")

    def status(self):
        available = bool(shutil.which(self.executable))
        return {"provider": "codex-cli", "model": self.model, "available": available,
                "message": "使用本机 Codex 登录；运行时会发送字幕和选定抽帧，并使用账户额度。" if available else "未找到 Codex，请安装并登录；手动编辑仍可用。"}

    def decide(self, prompt, images=(), cancel=None):
        with tempfile.TemporaryDirectory(prefix="broll-decision-") as directory:
            root = Path(directory)
            schema, output = root / "schema.json", root / "decision.json"
            schema.write_text(json.dumps(ACTION_SCHEMA), encoding="utf-8")
            args = [self.executable, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                    "--sandbox", "read-only", "--color", "never", "--json", "--model", self.model,
                    "-c", 'model_reasoning_effort="low"', "-c", 'web_search="disabled"',
                    "--disable", "shell_tool", "--disable", "apps", "--disable", "multi_agent",
                    "--disable", "browser_use", "--disable", "computer_use",
                    "--output-schema", schema, "--output-last-message", output, "-C", root]
            for path in list(images)[-6:]: args.extend(["--image", str(path)])
            args.append("-")
            run_process(args, cwd=root, stdin=prompt, timeout=self.timeout, cancel=cancel)
            if not output.is_file():
                raise ModelError("模型没有返回结构化决策，草稿未被覆盖。")
            try:
                result = json.loads(output.read_text())
                if result["action"] not in ACTIONS or not isinstance(result["rationale"], str): raise ValueError()
                args = json.loads(result.pop("arguments_json"))
                if not isinstance(args, dict): raise ValueError()
                result["arguments"] = args
                return result
            except (ValueError, KeyError, TypeError):
                raise ModelError("模型返回了无效决策，已保存失败状态，可重试。") from None

