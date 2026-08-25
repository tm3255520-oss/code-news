"""MCP stdio server: 让沙箱 Claude 通过宿主机写 Obsidian vault。

背景：Claude 跑在 Linux 沙箱，vault 挂载只读；Hermes 跑在宿主机可直接写。
本 MCP server 跑在宿主机（Windows Python），暴露 write_to_vault 等工具，
Claude 通过它把文件写进 D:\\Obsidian Vault 的白名单目录 —— 获得与 Hermes 相同的写入能力。

安全：只允许写白名单目录；禁止路径穿越（..）；禁止写 vault 根/非白名单。
启动：python scripts/mcp_vault_writer_server.py（stdio 传输）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

VAULT_ROOT = Path(r"D:\Obsidian Vault\obsidian Vault")

# 白名单：允许写入的顶层目录（来自 vault AGENTS.md 各 Agent 写白名单，按需增补）
ALLOWED_PREFIXES = [
    "内容生产", "AI工具", "wiki/decisions", "raw",
]

mcp = FastMCP("vault-writer")


def _resolve(relative_path: str) -> Path:
    """解析相对路径到 vault 绝对路径；校验白名单 + 防穿越。"""
    rel = relative_path.replace("\\", "/").strip("/")
    if not rel:
        raise ValueError("relative_path 不能为空")
    if ".." in Path(rel).parts:
        raise ValueError("禁止路径穿越")
    prefix = rel.split("/")[0]
    if not any(rel == p or rel.startswith(p + "/") for p in ALLOWED_PREFIXES):
        raise ValueError(f"目录不在白名单: {prefix}（允许: {', '.join(ALLOWED_PREFIXES)}）")
    target = (VAULT_ROOT / rel).resolve()
    if not str(target).startswith(str(VAULT_ROOT.resolve())):
        raise ValueError("路径超出 vault 根")
    return target


@mcp.tool()
def write_to_vault(relative_path: str, content: str) -> dict[str, Any]:
    """写入/覆盖 vault 白名单目录下的文件（UTF-8）。relative_path 如 '内容生产/热点监控/x.md'。"""
    try:
        target = _resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def append_to_vault(relative_path: str, content: str) -> dict[str, Any]:
    """追加到 vault 白名单目录下的文件（文件不存在则创建）。"""
    try:
        target = _resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        with open(target, "a", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": str(target), "existed": existed}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
def list_vault(relative_dir: str = "内容生产") -> dict[str, Any]:
    """列出 vault 白名单目录下的文件名（只读，方便确认写入结果）。"""
    try:
        target = _resolve(relative_dir)
        if not target.is_dir():
            return {"ok": False, "error": "不是目录"}
        names = sorted(p.name for p in target.iterdir())
        return {"ok": True, "dir": str(target), "files": names[:100]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run()
