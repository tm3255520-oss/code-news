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
import shlex
import subprocess
import sys
import urllib.request
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
    # 输出截断口径：保留**头部**。头部含 status/count/首条记录，是判定成败的关键；
    # 旧实现保留尾部，会把 JSON 开头砍掉，调用方 json.loads 直接失败
    # （2026-09-27 排查 redfox_search trending 时踩到）。截断时明确标注，便于识别。
    def _clip(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n...[输出过长已截断，仅保留前 %d 字符]..." % limit

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
            "stdout": _clip(proc.stdout or "", 20000),
            "stderr": _clip(proc.stderr or "", 4000),
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._mcp_compat import FastMCP  # noqa: E402  # 兼容 mcp 1.x / 2.x

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
def redfox_search(
    platform: str,
    keyword: str = "",
    limit: int = 20,
    sort: str = "",
    days: int = 7,
) -> str:
    """RedFox 多平台搜索（只读，会话内直接查，不用等 cron、不用翻落盘文件）。

    取的是 RedFox 中转的新媒体数据，返回统一结构（title/author/url/互动数/发布时间）。

    platform 取值：
      xhs            小红书关键词搜索笔记          keyword 必填
      douyin         抖音关键词搜索作品            keyword 必填
      douyin-account 抖音按账号取最新作品          keyword=抖音号(unique_id)
      gzh            公众号关键词搜索文章          keyword 必填
      gzh-account    公众号按账号取最新文章        keyword=公众号名
      gzh-rank       公众号榜单(10W+/原创爆款)     sort 可留空，days 生效
      bilibili       B站关键词搜索                 keyword 必填
      shipinhao      视频号关键词搜索              keyword 必填
      trending       全网热点(公众号榜单跨分类聚合) keyword 留空，days 生效

    limit: 返回条数上限。sort: 平台排序参数，留空用各平台默认。
    days: 仅 gzh-rank / trending 用，回溯天数。
    注意：本工具只读不写——不落库、不转录、不做闸门；要入库请走各平台采集脚本。
    """
    config = load_config()
    args = [platform]
    if platform == "trending":
        args += ["--days", str(days), "--limit-per", str(limit)]
    elif platform == "gzh-rank":
        args += ["--days", str(days), "--limit", str(limit)]
    else:
        args.append(keyword)
        args += ["--limit", str(limit)]
        if sort:
            args += ["--sort", sort]
    return json.dumps(_run_script(config, "redfox_search", args), ensure_ascii=False)


@mcp.tool()
def redfox_skill(skill: str, args: str = "") -> str:
    """执行 RedFox 官方 skill（榜单 / 账号诊断 / 对标）。

    统一走 scripts/redfox_skill.py，解决官方脚本在 Windows 上的三个坑：
    高保真输出被 GBK 控制台打断（扣完积分崩在打印）、只认环境变量不读 .env、
    积分不足的报错混在正文里难识别（wrapper 会映射为退出码 3）。

    skill 取值（也可先用 skill="--list" 查看已登记入口）：
      douyin-daily-hot        抖音每日点赞榜（--limit 3 / --type 美食 / --start 2026-09-25）
      douyin-content-surge    抖音每日点赞飙升榜（同上参数）
      douyin-rise-ranking     抖音涨粉账号榜（--rank_type day|week|month --top_n 3）
      douyin-top-account      抖音影响力账号榜（--period day|week|month --limit 3）
      douyin-account-diagnosis 抖音账号诊断（args 直接给账号名或抖音号）
      douyin-similar-account  抖音对标账号（--account_id <抖音号>）
      xiaohongshu-dailytop    小红书每日爆款（--top_n 3 / --category 时尚穿搭）
      xiaohongshu-weeklytop   小红书七日爆款（同上）
      xiaohongshu-top-account 小红书账号榜（--period day --limit 3）
      xiaohongshu-similar-account 小红书对标（--red_id <小红书号> 或 --track 赛道）
      xiaohongshu-search / xiaohongshu-lowtop / xiaohongshu-account-analyzer
      multi-wordcheck / trending-hub-top10

    args: 透传给 skill 脚本的参数串（按 shell 规则切分，支持引号）。
    注意：榜单类数据是 T+1/T+2 更新，查「今天」通常为空，一般传昨天或前天。
    """
    config = load_config()
    argv = [skill] + (shlex.split(args) if args.strip() else [])
    return json.dumps(_run_script(config, "redfox_skill", argv), ensure_ascii=False)


@mcp.tool()
def publish_wordcheck(
    platform: str,
    content: str = "",
    file: str = "",
    as_json: bool = True,
) -> str:
    """发布前违禁词门禁（官方词库，覆盖公众号/小红书/抖音）。

    补充门禁，不替换各平台既有 checker——那些还查 AI 声明/原创度/标题规范。

    platform: 公众号 / 小红书 / 抖音（也接受 gzh / xhs / douyin）。
    content: 直接给文案；file: 给 Markdown 路径（自动剥 frontmatter）。二者择一。
    as_json: 默认 True 返回 JSON（含 status/count/sensitive_words）。

    退出码：0 通过 / 2 阻断（命中违禁词）/ 1 无法判定（缺 key、网络异常、内容为空）。
    注意 1 不等于通过——查不了时不要当成合格放行。
    """
    config = load_config()
    args = ["--platform", platform]
    if file:
        args += ["--file", file]
    elif content:
        args += ["--content", content]
    else:
        return json.dumps(
            {"status": "error", "message": "需要 content 或 file 二者之一"},
            ensure_ascii=False,
        )
    if as_json:
        args.append("--json")
    return json.dumps(_run_script(config, "publish_wordcheck", args), ensure_ascii=False)


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


@mcp.tool()
def matrixmedia_publish(
    file: str,
    title: str,
    platforms: str = "dy",
    description: str = "",
    phone: str = "",
    short_title: str = "",
    tags: str = "",
    publish_at: str = "",
    creative_statement: str = "",
) -> str:
    """发布视频到多平台（经 MatrixMedia 矩媒 HTTP API，矩媒 GUI 需保持打开）。

    file: 视频本地绝对路径或 http(s) URL。title: 标题。
    platforms: 逗号分隔平台代码（dy=抖音, sph=视频号, ks=快手, blbl=哔哩哔哩,
              bjh=百家号, tt=头条, xhs=小红书, fqsp=番茄视频）。
    phone: 账号手机号（与矩媒 GUI 账号树一致）。tags: 标签（空格或逗号分隔）。
    publish_at: 一次性定时发布 "YYYY-MM-DD HH:mm:ss"（可选）。
    注意：正式发布默认关闭——请先发草稿/定时，人工确认后再公开。
    """
    config = load_config()
    tool = _tool_config(config, "matrixmedia_publish")
    url = tool.get("http_url") or "http://127.0.0.1:30088/publish"
    payload: dict[str, Any] = {"file": file, "title": title}
    if description:
        payload["description"] = description
    if short_title:
        payload["shortTitle"] = short_title
    if tags:
        payload["tags"] = tags
    if phone:
        payload["phone"] = phone
    if publish_at:
        payload["publishAt"] = publish_at
    if creative_statement:
        payload["creativeStatement"] = creative_statement
    platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
    if len(platform_list) == 1:
        payload["platform"] = platform_list[0]
    else:
        payload["platforms"] = platform_list
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {
                "status": "error",
                "message": f"矩媒 HTTP API 不可达（GUI 是否已打开？）: {exc}",
            },
            ensure_ascii=False,
        )


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(run_selftest())
    mcp.run()
