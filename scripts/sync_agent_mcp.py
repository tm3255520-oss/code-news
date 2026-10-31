"""sync_agent_mcp.py — 把 toolkit-mcp 注册到各智能体的 MCP 配置（幂等）。

单一来源：code-news\\scripts\\toolkit-mcp.cmd
目标：Codex (config.toml) / Claude Code (.claude.json) / Hermes (config.yaml)
DSH：WSL 内文件，脚本只输出待执行的 wsl 命令（不自动改）。
OpenClaw：无原生 MCP 客户端，标记待 mcporter 启用。

用法：
  python scripts/sync_agent_mcp.py            # 幂等写入（缺的加，已存在跳过）
  python scripts/sync_agent_mcp.py --dry-run  # 预览将要执行的动作
  python scripts/sync_agent_mcp.py --verify   # 只校验并输出状态表
  python scripts/sync_agent_mcp.py --agents codex,claude,hermes

退出码：verify 模式任一缺失/不一致返回 1；写入失败返回 1。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

TOOLKIT_CMD = Path(r"C:\Users\Administrator\Documents\code-news\scripts\toolkit-mcp.cmd")

# 每个 Agent 的配置描述
AGENTS = [
    {
        "name": "codex",
        "path": Path(r"C:\.codex\config.toml"),
        "fmt": "toml",
        "root": "mcp_servers",
    },
    {
        "name": "claude",
        "path": Path(r"C:\Users\Administrator\.claude.json"),
        "fmt": "json",
        "root": "mcpServers",
    },
    {
        "name": "hermes",
        "path": Path(r"C:\Users\Administrator\.hermes\config.yaml"),
        "fmt": "yaml",
        "root": "mcp_servers",
    },
    {
        "name": "dsh",
        "path": Path(r"C:\Users\Administrator\.dsh\profiles\web\cordis.patch.yml"),
        "fmt": "yaml-wsl",
        "root": "mcp_servers",
    },
]

OPENCLAW_NOTE = (
    "OpenClaw 无原生 MCP 客户端，需启用 mcporter 插件或上游支持后再接入；"
    "届时在 D:\\OpenClaw 容器内把 toolkit-mcp.cmd 挂载并注册。"
)


def _entry_claude() -> dict:
    """Claude Code 用 cmd /c 包装 .cmd（官方推荐 Windows 写法）。"""
    return {"command": "cmd", "args": ["/c", str(TOOLKIT_CMD)]}


def _entry_direct() -> dict:
    """Hermes / Codex 直接指向 .cmd（与现有 codex-api-mcp 写法一致）。"""
    return {"command": str(TOOLKIT_CMD)}


def _backup(path: Path) -> str | None:
    """写前备份，返回备份路径；文件不存在返回 None。"""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    return str(backup)


# --------------------------------------------------------------------------- #
# JSON（Claude .claude.json）
# --------------------------------------------------------------------------- #
def _json_entry_present(data: dict, entry: dict) -> bool:
    servers = data.get("mcpServers") or {}
    return servers.get("toolkit") == entry


def ensure_json(path: Path, dry_run: bool, verify: bool) -> str:
    if not path.exists():
        return "missing"
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.setdefault("mcpServers", {})
    entry = _entry_claude()
    if servers.get("toolkit") == entry:
        return "ok"
    if verify:
        return "missing"
    if dry_run:
        return "would-add"
    backup = _backup(path)
    servers["toolkit"] = entry
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"added(backup={backup})"


# --------------------------------------------------------------------------- #
# YAML（Hermes config.yaml）
# --------------------------------------------------------------------------- #
def _yaml_block(entry: dict, indent: int) -> list[str]:
    lines = [f"{' ' * indent}toolkit:"]
    for key, value in entry.items():
        if isinstance(value, list):
            lines.append(f"{' ' * (indent + 4)}{key}:")
            for item in value:
                lines.append(f"{' ' * (indent + 6)}- {item}")
        else:
            lines.append(f"{' ' * (indent + 4)}{key}: {value}")
    return lines


def _find_root_idx(lines: list[str], root: str) -> int | None:
    for i, line in enumerate(lines):
        if re.match(rf"^{root}\s*:", line):
            return i
    return None


def _yaml_has_toolkit(lines: list[str], root_idx: int) -> bool:
    for line in lines[root_idx + 1:]:
        if line and not line[0].isspace():
            break  # 遇到下一个顶层 key
        if line.strip().startswith("toolkit:"):
            return True
    return False


def ensure_yaml(path: Path, dry_run: bool, verify: bool) -> str:
    if not path.exists():
        return "missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    root_idx = _find_root_idx(lines, "mcp_servers")
    if root_idx is None:
        return "no-root"  # 配置里没有 mcp_servers 段，需人工处理
    if _yaml_has_toolkit(lines, root_idx):
        return "ok"
    if verify:
        return "missing"
    if dry_run:
        return "would-add"
    backup = _backup(path)
    entry = _entry_direct()
    # 子项缩进：取现有子项缩进（默认 2）
    child_indent = 2
    for line in lines[root_idx + 1:]:
        if line.strip():
            child_indent = len(line) - len(line.lstrip())
            break
    block = _yaml_block(entry, child_indent)
    new_lines = lines[: root_idx + 1] + block + lines[root_idx + 1:]
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return f"added(backup={backup})"


# --------------------------------------------------------------------------- #
# TOML（Codex config.toml）—— 追加独立 section，不破坏已有内容
# --------------------------------------------------------------------------- #
def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ensure_toml(path: Path, dry_run: bool, verify: bool) -> str:
    if not path.exists():
        return "missing"
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^\[mcp_servers\.toolkit\]\s*$", text):
        return "ok"
    if verify:
        return "missing"
    if dry_run:
        return "would-add"
    backup = _backup(path)
    cmd_escaped = _toml_escape(str(TOOLKIT_CMD))
    block = (
        "\n# toolkit-mcp: 统一 MCP 工具箱（由 sync_agent_mcp.py 管理）\n"
        "[mcp_servers.toolkit]\n"
        f'command = "{cmd_escaped}"\n'
    )
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    return f"added(backup={backup})"


# --------------------------------------------------------------------------- #
# DSH（WSL）—— 输出待执行命令，不自动修改
# --------------------------------------------------------------------------- #
def dsh_instruction() -> str:
    return (
        "DSH 配置在 WSL 内：~/.dsh/profiles/web/cordis.patch.yml\n"
        "请在你的 WSL 会话执行（或由宿主机脚本 wsl -e sh -lc 执行）：\n"
        "  python3 - <<'PY'\n"
        "import yaml, pathlib\n"
        "p = pathlib.Path.home() / '.dsh' / 'profiles' / 'web' / 'cordis.patch.yml'\n"
        "d = yaml.safe_load(p.read_text() or '{}')\n"
        "d.setdefault('mcp_servers', {})['toolkit'] = {'command': '"
        "C:\\\\Users\\\\Administrator\\\\Documents\\\\code-news\\\\scripts\\\\toolkit-mcp.cmd'}\n"
        "p.write_text(yaml.safe_dump(d))\n"
        "PY"
    )


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run_for_agent(agent: dict, dry_run: bool, verify: bool) -> str:
    fmt = agent["fmt"]
    path = agent["path"]
    if fmt == "json":
        return ensure_json(path, dry_run, verify)
    if fmt == "yaml":
        return ensure_yaml(path, dry_run, verify)
    if fmt == "toml":
        return ensure_toml(path, dry_run, verify)
    if fmt == "yaml-wsl":
        return "needs-wsl"
    return "unknown-fmt"


def main() -> int:
    parser = argparse.ArgumentParser(description="把 toolkit-mcp 注册到各智能体 MCP 配置")
    parser.add_argument("--dry-run", action="store_true", help="预览，不写文件")
    parser.add_argument("--verify", action="store_true", help="只校验")
    parser.add_argument(
        "--agents",
        default="codex,claude,hermes,dsh",
        help="逗号分隔，可选 codex,claude,hermes,dsh",
    )
    args = parser.parse_args()

    wanted = {a.strip() for a in args.agents.split(",") if a.strip()}
    ok = True
    for agent in AGENTS:
        if agent["name"] not in wanted:
            continue
        if agent["name"] == "dsh":
            print(f"[INFO] dsh: {dsh_instruction()}")
            continue
        status = run_for_agent(agent, args.dry_run, args.verify)
        flag = "OK " if status == "ok" else "CHG"
        if status in ("missing", "no-root", "unknown-fmt"):
            flag = "FAIL"
            ok = False
        print(f"[{flag}] {agent['name']:<8} {agent['path']}  ->  {status}")

    if "openclaw" in wanted:
        print(f"[INFO] openclaw: {OPENCLAW_NOTE}")

    print("SYNC_MCP_RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
