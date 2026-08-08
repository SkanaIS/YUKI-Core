"""YUKI Agent 沙箱工具 — 工作空间隔离 + 代码执行（无 QQ 依赖，纯文件/子进程操作）"""

import shutil
import subprocess
import sys
from pathlib import Path

MAX_OUTPUT_CHARS = 8000


class SandboxError(Exception):
    """工作空间越界等安全错误"""


def _clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + f"\n……（输出过长已截断，共 {len(text)} 字符）"
    return text


class WorkspaceSandbox:
    """将一切文件操作限制在指定工作空间内。"""

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def resolve(self, rel: str) -> Path:
        """把相对工作空间的路径解析为绝对路径，越界即抛错。"""
        p = (self.workspace / str(rel)).resolve()
        if p != self.workspace and not p.is_relative_to(self.workspace):
            raise SandboxError(f"路径越界，禁止访问工作空间之外: {rel}")
        return p

    def list_dir(self, rel: str = ".") -> str:
        p = self.resolve(rel)
        if not p.exists():
            return f"错误：路径不存在（相对工作空间）: {rel}"
        if p.is_file():
            return f"{rel} 是一个文件（{p.stat().st_size} 字节），请用 read_file 读取内容"
        entries = []
        for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
            if child.is_dir():
                entries.append(f"[目录] {child.name}")
            else:
                entries.append(f"[文件] {child.name} ({child.stat().st_size}B)")
        return _clip("\n".join(entries)) if entries else "（空目录）"

    def read_file(self, rel: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
        p = self.resolve(rel)
        if not p.is_file():
            return f"错误：文件不存在（相对工作空间）: {rel}"
        data = p.read_text(encoding="utf-8", errors="replace")
        return _clip(data, max_chars)

    def write_file(self, rel: str, content: str) -> str:
        p = self.resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入 {rel}（{len(content)} 字符）"

    def delete_file(self, rel: str) -> str:
        p = self.resolve(rel)
        if not p.exists():
            return f"错误：路径不存在: {rel}"
        if p.is_dir():
            return f"错误：{rel} 是目录，请使用 delete_dir"
        p.unlink()
        return f"已删除文件 {rel}"

    def delete_dir(self, rel: str) -> str:
        p = self.resolve(rel)
        if not p.exists():
            return f"错误：路径不存在: {rel}"
        if not p.is_dir():
            return f"错误：{rel} 是文件，请使用 delete_file"
        if p == self.workspace:
            raise SandboxError("禁止删除工作空间根目录")
        shutil.rmtree(p)
        return f"已删除目录 {rel}"


def run_python(code: str, cwd: Path, timeout: int = 60) -> str:
    """在指定工作目录下执行 Python 代码，返回 stdout/stderr + exit code。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（>{timeout}s）已终止"
    except Exception as exc:
        return f"启动进程失败: {exc}"
    parts = []
    if proc.stdout.strip():
        parts.append(proc.stdout.strip())
    if proc.stderr.strip():
        parts.append(f"[stderr]\n{proc.stderr.strip()}")
    body = "\n".join(parts) or "（无输出）"
    return _clip(f"exit code: {proc.returncode}\n{body}")


def run_shell(command: str, cwd: Path, timeout: int = 60) -> str:
    """在指定工作目录下执行 Shell 命令，返回 stdout/stderr + exit code。"""
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（>{timeout}s）已终止"
    except Exception as exc:
        return f"启动进程失败: {exc}"
    parts = []
    if proc.stdout.strip():
        parts.append(proc.stdout.strip())
    if proc.stderr.strip():
        parts.append(f"[stderr]\n{proc.stderr.strip()}")
    body = "\n".join(parts) or "（无输出）"
    return _clip(f"exit code: {proc.returncode}\n{body}")
