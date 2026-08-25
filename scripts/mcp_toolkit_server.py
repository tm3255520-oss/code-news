"""mcp_toolkit_server.py — 统一 MCP 工具箱（stdio）。

把 code-news/.hermes 里已有的脚本能力接线成会话内可调用的 MCP 工具，
5 个智能体（Codex / Claude Code / Hermes / DSH / OpenClaw）共用同一个入口。

原则：只调用不修改——本文件是包装层，真实逻辑仍在各脚本里。

启动（宿主机）：
    toolkit-mcp.cmd
或  python scripts/mcp_toolkit_server.py

自检（不启动 MCP，输出各工具组状态表，供接线验收）：
    python scripts/mcp_toolkit_server.py --selftest

配置覆盖（测试/多环境用）：
    环境变量 MCP_TOOLKIT_CONFIG=<路径>  指向自定义 mcp_toolkit.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "mcp_toolkit.json"

# Windows 控制台 GBK → UTF-8（防中文/emoji 打印崩）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
def load_config() -> dict[str, Any]:
    """读取 mcp_toolkit.json；可用环境变量 MCP_TOOLKIT_CONFIG 覆盖。"""
    path = Path(os.environ.get("MCP_TOOLKIT_CONFIG", DEFAULT_CONFIG_PATH))
    if not path.exists():
        raise FileNotFoundError(f"toolkit config 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _tool_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    tool = (config.get("tools") or {}).get(name)
    if not tool:
        raise ValueError(f"toolkit 配置中未定义工具: {name}")
    return tool


def _resolve_python(config: dict[str, Any], tool: dict[str, Any]) -> str:
    return tool.get("python") or config.get("defaults", {}).get("python") or sys.executable


def _resolve_timeout(config: dict[str, Any], tool: dict[str, Any]) -> int:
    return int(tool.get("timeoutSec") or config.get("defaults", {}).get("timeoutSec") or 300)


def _run_script(config: dict[str, Any], name: str, args: list[str]) -> dict[str, Any]:
    """执行工具对应的宿主机脚本，返回结构化结果。"""
    tool = _tool_config(config, name)
    script = tool.get("script")
    if not script:
        return {
            "status": "error",
            "tool": name,
            "message": "该工具无外部脚本（逻辑在服务器内），不支持 subprocess 调用",
        }
    python = _resolve_python(config, tool)
    timeout = _resolve_timeout(config, tool)
    cmd = [python, script, *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
        )
        return {
            "status": "ok" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "tool": name,
            "stdout": (proc.stdout or "")[-8000:],
            "stderr": (proc.stderr or "")[-4000:],
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "tool": name,
            "message": f"解释器或脚本不存在: python={python} script={tool['script']}",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "tool": name, "message": f"执行超时（>{timeout}s）"}


# --------------------------------------------------------------------------- #
# 自检
# --------------------------------------------------------------------------- #
def build_status(config: dict[str, Any]) -> list[dict[str, Any]]:
    """生成各工具组的启用/脚本存在/解释器存在状态（供 status 工具与 --selftest 用）。"""
    defaults = config.get("defaults", {})
    rows: list[dict[str, Any]] = []
    for name, tool in (config.get("tools") or {}).items():
        python = tool.get("python") or defaults.get("python")
        script = tool.get("script") or ""
        if script:
            script_exists = Path(script).exists()
        else:
            # 无外部脚本的工具（逻辑在服务器内），检查其 data_dir
            script_exists = Path(tool.get("data_dir") or ".").exists()
        rows.append(
            {
                "tool": name,
                "group": tool.get("group"),
                "label": tool.get("label", ""),
                "enabled": bool(tool.get("enabled", True)),
                "script_exists": script_exists,
                "python_exists": Path(python).exists() if python else False,
            }
        )
    return rows


def run_selftest() -> int:
    """--selftest：不启动 MCP，输出状态表；用于接线验收与 CI。"""
    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001
        print(f"SELFTEST_ERROR: {exc}")
        return 1
    rows = build_status(config)
    for row in rows:
        flag = "OK " if (row["enabled"] and row["script_exists"]) else "MISS"
        print(
            f"[{flag}] {row['tool']:<26} group={row.get('group',''):<10} "
            f"script={row['script_exists']} python={row['python_exists']}"
        )
    missing = [r["tool"] for r in rows if not r["script_exists"]]
    ok = not missing
    print("SELFTEST_RESULT:", "OK" if ok else f"MISSING={missing}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# MCP 工具
# --------------------------------------------------------------------------- #
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("toolkit")


@mcp.tool()
def toolkit_status() -> str:
    """返回统一 MCP 工具箱自检状态：各组工具是否启用、脚本是否存在、解释器是否可用。"""
    try:
        config = load_config()
        rows = build_status(config)
        return json.dumps(
            {"schemaVersion": config.get("schemaVersion"), "tools": rows},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)


@mcp.tool()
def transcribe_video(url: str) -> str:
    """转录一个视频到 Obsidian 笔记（接线 video_collect.py，6 平台自动检测：B站/知乎/头条/小红书/抖音/YouTube）。

    url: 视频链接（如 bilibili.com/...、douyin.com/...）。
    输出写入 vault raw/videos/<平台>/，返回转录摘要与笔记路径。
    """
    config = load_config()
    return json.dumps(_run_script(config, "transcribe_video", [url]), ensure_ascii=False)


@mcp.tool()
def make_slideshow_video(slides_json: str, output: str, voice: str = "") -> str:
    """图文TTS视频合成：幻灯片 PNG +（可选）edge-tts 配音 + ffmpeg 合成 720p。

    slides_json: 页面定义 JSON 文件路径，结构为 [{"text","sub","tts","dur"}, ...]。
    output: 输出 mp4 路径。voice: 可选，如 zh-CN-YunjianNeural；留空则跳过配音。
    """
    config = load_config()
    args = [slides_json, "-o", output]
    if voice:
        args += ["--voice", voice]
    return json.dumps(_run_script(config, "make_slideshow_video", args), ensure_ascii=False)


@mcp.tool()
def make_voiceover(script_json: str, out_dir: str, voice: str = "") -> str:
    """逐段 TTS 配音 + 精确字幕（接线 voice_segmenter.py，edge-tts 云健男声）。

    script_json: 口播 JSON 文件路径（script 数组）。out_dir: 输出目录（写 voice_segmented.mp3/.srt）。
    voice: 可选 yunjian/yunxi/xiaoxiao/yunyang。
    """
    config = load_config()
    args = ["--script", script_json, "--out-dir", out_dir]
    if voice:
        args += ["--voice", voice]
    return json.dumps(_run_script(config, "make_voiceover", args), ensure_ascii=False)


@mcp.tool()
def collect_bili_candidates(keywords: str = "", limit: int = 0) -> str:
    """B站候选池采集（接线 collect_bili_candidates.py，确定性无 LLM）。

    keywords: 逗号分隔关键词（如 "dsh 插件,deepseek harness"）。limit: 采集条数上限（0=默认）。
    输出候选清单+指标表到其 out_dir。
    """
    config = load_config()
    args: list[str] = []
    if keywords.strip():
        args += ["--keywords", keywords]
    if limit and limit > 0:
        args += ["--limit", str(limit)]
    return json.dumps(_run_script(config, "collect_bili_candidates", args), ensure_ascii=False)


@mcp.tool()
def web_scrape(request_path: str) -> str:
    """统一网页采集（接线 web-scraper-mcp 适配器）。

    request_path: 采集请求 JSON 文件路径。action 支持 search_content/fetch_article/
    fetch_author_feed/extract_metrics/normalize_record。输出规范化记录 JSON。
    """
    config = load_config()
    ws_cfg = ROOT / "config" / "web_scraper_mcp.json"
    return json.dumps(
        _run_script(config, "web_scrape", [request_path, "--config", str(ws_cfg)]),
        ensure_ascii=False,
    )


@mcp.tool()
def collect_xhs() -> str:
    """小红书收藏增量采集（接线 xhs_collect.py，no_agent cron 脚本，无参）。

    依赖 bsk 登录态；只处理新增笔记，写入 vault raw/articles/xiaohongshu/。
    """
    config = load_config()
    return json.dumps(_run_script(config, "collect_xhs", []), ensure_ascii=False)


@mcp.tool()
def collect_toutiao() -> str:
    """今日头条收藏增量采集（接线 toutiao_collect.py，no_agent cron 脚本，无参）。

    依赖 bsk 登录态；只提取正文，写入 vault raw/articles/toutiao/。
    """
    config = load_config()
    return json.dumps(_run_script(config, "collect_toutiao", []), ensure_ascii=False)


@mcp.tool()
def douyin_data_summary() -> str:
    """抖音博主数据汇总：读本地已采集的 douyin_user_data_*.json，返回各博主视频总数与最近视频描述。

    无外部脚本依赖，逻辑在服务器内。
    """
    config = load_config()
    tool = _tool_config(config, "douyin_data_summary")
    data_dir = Path(tool.get("data_dir") or ROOT)
    rows: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("douyin_user_data_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        videos = data.get("videos") or []
        rows.append(
            {
                "file": path.name,
                "sec_user_id": data.get("sec_user_id", ""),
                "total_videos": data.get("total", len(videos)),
                "latest_desc": (videos[0].get("desc", "") if videos else ""),
            }
        )
    return json.dumps({"count": len(rows), "accounts": rows}, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(run_selftest())
    mcp.run()
