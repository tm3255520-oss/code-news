#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workbench_digest.py — 工作台只读面板（确定性，零 LLM）

产出（两份渲染，同一份数据）：
    <vault>/系统中枢/运行手册/工作台总览.md      # Obsidian 里直接看
    <code-news>/_reports/工作台.html            # 双击浏览器打开

为什么：能力已经攒到 88 条接口 / 210 个脚本 / 86 个定时任务，入口散落在桌面 .bat、
仓库脚本、各 Agent 配置、vault 手册之间。缺的不是能力，是一面能一眼看全
「在等我什么 / 系统在跑什么 / 今天产出了什么 / 我能调什么」的门面。

设计纪律（对齐 cron_overview.py / cron_ledger.py 的责任边界）：
    - 只读四个事实源，不写任何上游文件、不改生产目录、不执行任何能力；
    - 零 LLM：面板上每个数字都能从来源文件现算复查，算不出来就写「—」，不猜；
    - 不新建真相：调度以 jobs.json 为准、任务态以协同台账为准、能力以注册表为准；
    - 路径常量复用单一事实源（vault_paths.py / xietong_lib.py），不重复硬编码。

数据源（全部只读）：
    ① code-news/config/tool_registry.json      能力路由（接口 → primary → fallback）
    ② ~/.hermes/cron/jobs.json                 调度真相（含 last_run_at / last_status）
    ③ <协同>/任务台账.md                        任务态真相（进行中 / 待审 …）
    ④ vault 内容生产 / 知识库 / raw 目录 mtime   产出真相（判据是最近产出时间）

用法：
    python workbench_digest.py                           # 写两份产物
    python workbench_digest.py --dry-run                 # 只打印正文，不写盘
    python workbench_digest.py --now 2026-10-12 01:00    # 固定时间戳（幂等自测用）
    python workbench_digest.py --out-md <p> --out-html <p> --jobs <p> --registry <p>
"""
from __future__ import annotations

import argparse
import html as _html
import importlib.util as _ilu
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent            # code-news/scripts
REPO_ROOT = SCRIPT_DIR.parent                           # code-news
HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
DEFAULT_JOBS = Path(r"C:\Users\Administrator\.hermes\cron\jobs.json")
DEFAULT_REGISTRY = REPO_ROOT / "config" / "tool_registry.json"
DEFAULT_HTML = REPO_ROOT / "_reports" / "工作台.html"


def _load_module(name: str, path: Path):
    """按绝对路径加载模块（绕开 sys.path 上同名转发器的遮蔽，同 cron_overview.py）。

    必须先注册进 sys.modules：被加载的模块里可能有 dataclass，而 dataclasses 会
    去 sys.modules[cls.__module__] 找命名空间 —— 不注册就会报
    `'NoneType' object has no attribute '__dict__'`（2026-10-12 实测 xietong_lib.py）。
    """
    spec = _ilu.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 %s" % path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# —— 复用既有库：vault 路径单一事实源 ——
try:
    _vp = _load_module("vault_paths_impl", HERMES_SCRIPTS / "vault_paths.py")
    VAULT = Path(_vp.VAULT)
    OUT_MD_DEFAULT = Path(_vp.SYSTEM_RUNBOOK) / "工作台总览.md"
except Exception as _exc:  # noqa: BLE001
    print("警告：加载 vault_paths.py 失败，回退硬编码路径：%s" % _exc, file=sys.stderr)
    _vp = None
    VAULT = Path(r"D:\Obsidian Vault\obsidian Vault")
    OUT_MD_DEFAULT = VAULT / "系统中枢" / "运行手册" / "工作台总览.md"

# —— 复用既有实现：调度语义解析（不重写 cron 解析）——
try:
    _co = _load_module("cron_overview_impl", SCRIPT_DIR / "cron_overview.py")
except Exception as _exc:  # noqa: BLE001
    print("错误：加载 cron_overview.py 失败：%s" % _exc, file=sys.stderr)
    raise SystemExit(1)

# —— 复用既有库：协同台账解析（不重写表格解析）——
try:
    _xt = _load_module("xietong_lib_impl", SCRIPT_DIR / "xietong_lib.py")
    XT_ROOT = _xt.resolve_root()
    ACTIVE_STATUSES = tuple(getattr(_xt, "ACTIVE_STATUSES", ("进行中", "待审")))
except Exception as _exc:  # noqa: BLE001
    print("警告：加载 xietong_lib.py 失败，任务态区块降级：%s" % _exc, file=sys.stderr)
    _xt = None
    XT_ROOT = VAULT / "系统中枢" / "协同"
    ACTIVE_STATUSES = ("进行中", "待审")

# 「在等我」= 需要人动手/拍板的四类状态（认领与卡住同样要人看见）。
WAITING_STATUSES = ACTIVE_STATUSES + ("待认领", "暂停")


def _vp_path(name: str, fallback: Path) -> Path:
    """优先取 vault_paths 的常量，取不到用兜底字面量。"""
    if _vp is not None and hasattr(_vp, name):
        return Path(getattr(_vp, name))
    return fallback


# 产出区块（口径：最近产出时间，不是文件数）
OUTPUT_AREAS: list[tuple[str, Path]] = [
    ("采集·文章（raw）", _vp_path("RAW_ARTICLES", VAULT / "raw" / "articles")),
    ("采集·视频（raw）", _vp_path("RAW_VIDEOS", VAULT / "raw" / "videos")),
    ("情报·热点与情报", _vp_path("HOTSPOT", VAULT / "内容生产" / "1-情报与选题" / "热点与情报")),
    ("情报·AI日报", _vp_path("AI_DAILY", VAULT / "内容生产" / "1-情报与选题" / "AI日报")),
    ("情报·素材候选", _vp_path("MATERIAL_CANDIDATE", VAULT / "内容生产" / "1-情报与选题" / "素材候选")),
    ("调研与素材", VAULT / "内容生产" / "2-调研与素材"),
    ("草稿与创作", _vp_path("DRAFT", VAULT / "内容生产" / "3-草稿与创作")),
    ("成品与审查", _vp_path("PRODUCT_UNIT", VAULT / "内容生产" / "4-成品与审查")),
    ("发布·待发布", _vp_path("PUBLISH_PENDING", VAULT / "内容生产" / "5-发布" / "待发布")),
    ("发布·已发布", _vp_path("PUBLISH_DONE", VAULT / "内容生产" / "5-发布" / "已发布")),
    ("知识库·素材摘要", _vp_path("WIKI_SUMMARIES", VAULT / "知识库" / "1-素材摘要")),
    ("运营中心·收件箱", _vp_path("OPS_CENTER_INBOX", VAULT / "运营中心" / "_收件箱")),
]

# 能力分组规则：确定性关键词分类。**只用于面板展示分组**；路由真相仍是注册表。
# 顺序即优先级，先命中先归组；命中不了的进「其他」——宁可暴露未归类，也不硬塞。
GROUP_RULES: list[tuple[str, str]] = [
    ("采集与情报", r"collect|monitor|hotspot|rank|trend|material|discover|redfox|search|"
                   r"creator|topic_planner|wiki_ingest|videos_ingest|account_finder"),
    ("拆解与分析", r"analy|breakdown|production_analyzer|quality|check|compliance|wordcheck|"
                   r"storyboard|motion|ocr|vision|benchmark|audit|review|report"),
    ("创作与文案", r"writer|humanizer|illustration|cover|adapt|article"),
    ("视频与音频", r"video|transcrib|tts|lyric|audio|render|card|music|bgm|compose|upscale|"
                   r"slideshow|slides"),
    ("发布与分发", r"publish|publisher|xhs|zhihu|toutiao|wechat|channels|moments|tie_tu|"
                   r"matrixmedia|yxer|xmcp|vault|sync"),
    ("协同与工具", r"work_lookup|handoff|xietong|ledger|cron|inventory|toolkit|mcp|tool|"
                   r"proxy|key|guard|selftest|smoke|contract|router|provider|state|hygiene|"
                   r"archive|memory"),
]

# 一键入口：面板只列 + 核对存在性，不代执行。
ENTRY_POINTS: list[tuple[str, str, str]] = [
    ("启动模型代理栈", str(SCRIPT_DIR / "start-codex-stack.cmd"),
     "开机后需要 Codex/Claude 模型路由时双击"),
    ("注册 toolkit 到各 Agent", str(SCRIPT_DIR / "register-toolkit.bat"),
     "MCP 配置丢失或换机后重跑"),
    ("开工三查", "python %s" % (SCRIPT_DIR / "work_lookup.py"),
     "接手任何任务前先查台账 / 交接 / 会话索引"),
    ("收工三写", "python %s" % (SCRIPT_DIR / "handoff_append.py"),
     "台账 / 交接块 / 会话索引，用法见 --help"),
    ("定时任务总览再生", "python %s" % (SCRIPT_DIR / "cron_overview.py"),
     "刷新运行手册里的调度常青总览"),
    ("工作台面板再生", "python %s" % (SCRIPT_DIR / "workbench_digest.py"),
     "就是本文件"),
    ("打开工作台应用（交互壳）", str(REPO_ROOT / "_reports" / "workbench-app" / "index.html"),
     "可搜索/筛选的本地应用；再生：python scripts/workbench_app.py"),
    ("工作台应用再生", "python %s" % (SCRIPT_DIR / "workbench_app.py"),
     "刷新交互壳（数据同源，仍由 workbench_digest.build_panel 取数）"),
    ("按名调用（查能力/跑入口）", "python %s" % (SCRIPT_DIR / "workbench.py"),
     "给口语名 → 命中清单与怎么调；--entries 列入口；--entry <名称> 跑入口"),
    ("能力盘点（新建前置）", "python %s" % (SCRIPT_DIR / "tool_inventory.py"),
     "新建脚本 / 技能前必跑（复用守则）"),
    ("内容日跑", "python %s" % (SCRIPT_DIR / "run_daily_content_ops.py"),
     "内容链日常编排入口"),
    ("热榜日更", "python %s" % (SCRIPT_DIR / "hotspot_daily.py"), "热点情报"),
    ("打开 vault（Obsidian）", str(Path.home() / "Desktop" / "Obsidian.lnk"), "知识中枢"),
    ("打开 WorkBuddy AI", str(Path.home() / "Desktop" / "WorkBuddy AI.lnk"),
     "桌面工作台（可选前端壳）"),
]


# ------------------------------------------------------------------ 取数

def classify(key: str, purpose: str) -> str:
    blob = ("%s %s" % (key, purpose)).lower()
    for name, pat in GROUP_RULES:
        if re.search(pat, blob):
            return name
    return "其他（待归类）"


def one_line(text) -> str:
    """把多行错误信息压成单行 —— 面板列表项里换行会撑破排版。"""
    return re.sub(r"\s+", " ", str(text)).strip()


def moment_text(job: dict) -> str:
    """人读时刻：单点 cron 渲染成 HH:MM，其余原样给表达式（不猜语义）。"""
    f = _co.cron_fields(_co.sched(job))
    if f and f[0].isdigit() and f[1].isdigit():
        return "%02d:%02d" % (int(f[1]), int(f[0]))
    return _co.moment_label(job)


def brief_paths(cell: str) -> str:
    """产出路径单元格可能塞十几条：只显示第一条 + 总数，避免面板被一条任务撑爆。"""
    cell = str(cell or "").strip()
    if not cell or cell == "—":
        return "—"
    parts = _xt.split_paths(cell) if _xt is not None and hasattr(_xt, "split_paths") else \
        [x for x in re.split(r"[／、；;]|\s/\s|[,，]", cell) if x.strip()]
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else "—"
    return "%s ……（共 %d 项）" % (parts[0], len(parts))


def title_for_display(text: str) -> str:
    """渲染台账标题前去掉行内代码反引号（保留文字）。

    台账标题是历史记录，里面可能写有当时路径（如 `~/.hermes/scripts/xx.py`）。
    它一旦被复制进活文档（工作台总览.md）的表格，check_doc_references.py 就会把
    反引号里的路径当成活引用去校验，把「记录里的当时路径」误判成失效引用（传染）。
    只去反引号、不动文字：路径退化为纯文本，校验器不再提取，也不丢信息。
    """
    return str(text or "").replace("`", "")


def howto(entry: dict) -> str:
    """把一条注册表条目翻成「怎么调用」；认不出的原样给 primary，不编。"""
    primary = str(entry.get("primary") or "—")
    mode = str(entry.get("mode") or "")
    if mode == "manual_skill":
        return "自然语言触发「%s」" % primary
    if mode == "toolkit_tool":
        return "会话内 MCP：%s" % primary
    if mode == "mcp_server":
        return "MCP 服务：%s" % primary
    if mode == "external_mcp":
        return "外部 MCP：%s" % primary
    if primary.endswith(".py"):
        if primary.startswith("scripts"):
            return "python %s" % primary
        return "python %s" % primary
    if mode == "cron_script":
        return "cron 自动；手动 python %s" % primary
    return primary


def check_primary(entry: dict, cron_names: set, toolkit_tools: set) -> str:
    """核对 primary 是否在位（技能目录 / 脚本文件 / cron 任务 / toolkit 工具）。

    只做存在性核对，不执行、不判好坏；核不到写「⚠️ 未核对到」，由人决定。
    """
    primary = str(entry.get("primary") or "")
    mode = str(entry.get("mode") or "")
    if not primary:
        return "—"
    if mode == "manual_skill":
        for base in (Path(r"C:\Users\Administrator\.agents\skills"),
                     Path(r"C:\Users\Administrator\.codex\skills"),
                     Path(r"C:\Users\Administrator\.hermes\skills"),
                     REPO_ROOT / ".agents" / "skills"):
            if (base / primary / "SKILL.md").is_file():
                return "✅ 技能"
        return "⚠️ 未核对到"
    if mode == "toolkit_tool":
        return "✅ toolkit" if primary.split(":", 1)[-1] in toolkit_tools else "⚠️ 未核对到"
    if mode == "cron_script":
        # 两种在位形态都算通过：①同名脚本挂在某个 cron 任务上；②脚本文件本身在。
        if Path(primary).name in cron_names:
            return "✅ cron"
        cands = [Path(primary)] if os.path.isabs(primary) else [
            REPO_ROOT / primary, HERMES_SCRIPTS / Path(primary).name]
        for c in cands:
            if Path(c).is_file():
                return "✅ 脚本"
        return "⚠️ 未核对到"
    if primary.endswith(".py"):
        cands = [Path(primary)] if os.path.isabs(primary) else [
            REPO_ROOT / primary, HERMES_SCRIPTS / Path(primary).name]
        for c in cands:
            if Path(c).is_file():
                return "✅ 脚本"
        return "⚠️ 未核对到"
    return "（%s）" % (mode or "未标注形态")


def dir_scan(path: Path, today: str) -> dict:
    """扫一个产出区块：最新文件时间 / 最新文件名 / 今日新增数（本机日期口径）。"""
    out = {"path": path, "exists": path.is_dir(), "latest": None,
           "latest_name": "", "today": 0, "files": 0}
    if not out["exists"]:
        return out
    latest = 0.0
    n = 0
    for root, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            fp = Path(root) / fn
            try:
                st = fp.stat()
            except OSError:
                continue
            n += 1
            if st.st_mtime > latest:
                latest = st.st_mtime
                out["latest_name"] = fn
            if datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d") == today:
                out["today"] += 1
    out["files"] = n
    out["latest"] = datetime.fromtimestamp(latest) if latest else None
    return out


def file_brief(p: Path) -> dict:
    ok = p.is_file()
    rows = 0
    if ok:
        try:
            rows = sum(1 for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
                       if ln.strip().startswith("|") and "---" not in ln)
        except OSError:
            rows = 0
    return {"path": p, "exists": ok,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime) if ok else None,
            "rows": rows}


def build_panel(jobs_path: Path, registry_path: Path, now: datetime) -> dict:
    panel: dict = {"generated_at": now.strftime("%Y-%m-%d %H:%M"), "alerts": []}

    # —— ② 调度 ——
    try:
        jobs = _co.load_jobs(jobs_path)
    except Exception as exc:  # noqa: BLE001
        panel["alerts"].append("读不到 jobs.json：%s" % exc)
        jobs = []
    enabled = [j for j in jobs if j.get("enabled")]
    disabled = [j for j in jobs if not j.get("enabled")]
    cron_names = {Path(str(j.get("script") or "")).name for j in jobs if j.get("script")}
    ok_states = {"ok", "success", "succeeded", "none", None, ""}
    failing = [j for j in enabled if str(j.get("last_status") or "") not in ok_states]
    cron_rows = [{
        "name": _co.job_name(j),
        "moment": moment_text(j),
        "script": _co.script_label(j),
        "deliver": _co.deliver_label(j),
        "last_run": str(j.get("last_run_at") or "—")[:16].replace("T", " "),
        "last_status": str(j.get("last_status") or "—"),
        "streak": j.get("failure_streak") or 0,
        "next_run": str(j.get("next_run_at") or "—")[:16].replace("T", " "),
    } for j in sorted(enabled, key=_co.detail_sort_key)]
    panel["cron"] = {"total": len(jobs), "enabled": len(enabled),
                     "disabled": len(disabled), "failing": failing, "rows": cron_rows}
    for j in failing[:5]:
        panel["alerts"].append(
            "启用任务上次运行异常：%s（%s，连续失败 %s 次）%s"
            % (_co.job_name(j), j.get("last_status"), j.get("failure_streak") or 0,
               one_line(j.get("last_error") or "")[:70]))
    if len(failing) > 5:
        panel["alerts"].append("另有 %d 个启用任务上次运行异常，未逐条列出（见 jobs.json）"
                               % (len(failing) - 5))

    # —— ① 在等我 ——
    waiting: list = []
    ledger_path = None
    if _xt is not None:
        try:
            ledger_path = _xt.ledger_path(XT_ROOT)
            led = _xt.parse_ledger(ledger_path)
            for t in led.tasks:
                if t.status in WAITING_STATUSES:
                    waiting.append({"id": t.task_id, "title": title_for_display(t.title),
                                    "platform": t.platform, "owner": t.owner, "status": t.status,
                                    "updated": t.updated, "artifact": t.artifact})
            for p in led.problems:
                panel["alerts"].append("台账解析告警：%s" % p)
        except Exception as exc:  # noqa: BLE001
            panel["alerts"].append("读台账失败：%s" % exc)
    else:
        panel["alerts"].append("协同库未加载，任务态区块已降级")
    # 先按状态分组（进行中 → 待审 → 待认领 → 暂停），组内按最后更新倒序（最新在前）
    order = {s: i for i, s in enumerate(WAITING_STATUSES)}
    waiting.sort(key=lambda r: r["updated"], reverse=True)
    waiting.sort(key=lambda r: order.get(r["status"], 99))
    counts: dict = {}
    for r in waiting:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    panel["waiting"] = {"rows": waiting, "counts": counts, "ledger": ledger_path}

    # —— ③ 今天产出了什么 ——
    today = now.strftime("%Y-%m-%d")
    panel["output"] = [dict(label=label, **dir_scan(path, today)) for label, path in OUTPUT_AREAS]

    # —— ④ 我能调什么 ——
    reg = json.loads(registry_path.read_text(encoding="utf-8"))
    interfaces = reg.get("interfaces", {})
    toolkit_tools: set = set()
    try:
        tk = json.loads((REPO_ROOT / "config" / "mcp_toolkit.json").read_text(encoding="utf-8"))
        toolkit_tools = {m for m in re.findall(r'"([A-Za-z0-9_]+)"\s*:', json.dumps(tk))}
    except Exception:  # noqa: BLE001
        toolkit_tools = set()
    groups: dict = {}
    for key, entry in interfaces.items():
        if not isinstance(entry, dict):
            continue
        purpose = str(entry.get("purpose") or "")
        groups.setdefault(classify(key, purpose), []).append({
            "key": key,
            "mode": str(entry.get("mode") or "—"),
            "status": str(entry.get("status") or "—"),
            "primary": str(entry.get("primary") or "—"),
            "fallbacks": "、".join(map(str, entry.get("fallbacks") or [])) or "—",
            "howto": howto(entry),
            "check": check_primary(entry, cron_names, toolkit_tools),
            "purpose": purpose,
        })
    for g in groups.values():
        g.sort(key=lambda r: r["key"])
    unmatched = len(groups.get("其他（待归类）", []))
    panel["caps"] = {"total": len(interfaces), "groups": groups, "unmatched": unmatched}
    if unmatched:
        panel["alerts"].append("有 %d 条接口未能归入用途分组（显示在「其他（待归类）」）" % unmatched)
    missing = [r["key"] for g in groups.values() for r in g if r["check"].startswith("⚠️")]
    if missing:
        panel["alerts"].append("有 %d 条接口的 primary 未核对到（可能路径漂移或技能未同步）：%s"
                               % (len(missing), "、".join(missing[:6])))

    # —— ⑤ 账号与发布 ——
    pub_ledger = _vp_path("PUBLISH_LEDGER", VAULT / "内容生产" / "5-发布" / "发布台账.md")
    checkup = VAULT / "内容生产" / "5-发布" / "账号体检总览.md"
    panel["publish"] = {"ledger": file_brief(pub_ledger), "checkup": file_brief(checkup)}

    # —— ⑥ 一键入口（只核对存在性）——
    entries = []
    for name, cmd, note in ENTRY_POINTS:
        target = cmd.split(" ", 1)[1] if cmd.startswith("python ") else cmd
        entries.append({"name": name, "cmd": cmd, "note": note,
                        "exists": Path(target).is_file()})
    panel["entries"] = entries
    broken = [e["name"] for e in entries if not e["exists"]]
    if broken:
        panel["alerts"].append("一键入口核对到 %d 个失效项：%s" % (len(broken), "、".join(broken)))

    # 告警：文档引用校验最近一次报告（沿用既有输出，本脚本不代跑校验器）
    zone = VAULT / "系统中枢" / "运行小结" / "系统与配置"
    reps = sorted(zone.glob("文档引用校验-*.md"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if zone.is_dir() else []
    panel["doc_check"] = {"path": reps[0] if reps else None,
                          "mtime": datetime.fromtimestamp(reps[0].stat().st_mtime) if reps else None}
    return panel


# ------------------------------------------------------------------ 渲染

def _md_table(rows: list) -> list:
    if not rows:
        return []
    L = ["| " + " | ".join(rows[0]) + " |",
         "|" + "|".join(["---"] * len(rows[0])) + "|"]
    for r in rows[1:]:
        L.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return L


def render_md(panel: dict) -> str:
    L: list = []
    a = L.append
    a("# 工作台总览")
    a("")
    a("> ⚠️ 本文件由脚本自动生成，请勿手改：`python code-news/scripts/workbench_digest.py`（确定性、零 LLM）。")
    a("> 生成时间：%s" % panel["generated_at"])
    a("> 数据源（全部只读）：`config/tool_registry.json`（能力路由）｜`~/.hermes/cron/jobs.json`（调度真相）｜"
      "`系统中枢/协同/任务台账.md`（任务态）｜vault 内容生产目录 mtime（产出）")
    a("")
    if panel["alerts"]:
        a("## ⚠️ 告警与自检")
        a("")
        for s in panel["alerts"]:
            a("- %s" % s)
        a("")

    w = panel["waiting"]
    cnt = "、".join("%s %d" % (k, v) for k, v in w["counts"].items()) or "无"
    a("## 一、在等我（%d 件：%s）" % (len(w["rows"]), cnt))
    a("")
    a("> 口径：任务台账里状态为「进行中 / 待审 / 待认领 / 暂停」的行；改状态走收工三写"
      "（`handoff_append.py`），本面板只读。")
    a("")
    if w["rows"]:
        L.extend(_md_table([["任务ID", "标题", "平台/形态", "负责人", "状态", "最后更新", "产出路径"]] +
                           [[r["id"], r["title"], r["platform"], r["owner"], r["status"],
                             r["updated"], brief_paths(r["artifact"])] for r in w["rows"]]))
    else:
        a("（无）")
    a("")

    c = panel["cron"]
    a("## 二、系统在跑什么（启用 %d / 停用 %d，共 %d）"
      % (c["enabled"], c["disabled"], c["total"]))
    a("")
    a("> 调度真相是 `~/.hermes/cron/jobs.json`；资源窗口与停用任务登记见运行手册"
      "《定时任务总览与资源窗口规划》（`cron_overview.py` 生成）。")
    a("")
    L.extend(_md_table([["时刻", "任务名", "脚本", "deliver", "上次运行", "上次状态", "下次"]] +
                       [[r["moment"], r["name"], r["script"], r["deliver"], r["last_run"],
                         r["last_status"], r["next_run"]] for r in c["rows"]]))
    a("")

    a("## 三、今天产出了什么")
    a("")
    a("> 判据是**最近产出时间**而不是文件数（同 vault 巡检口径）；「今日新增」按本机日期统计。")
    a("")
    L.extend(_md_table([["区块", "最新产出", "时间", "今日新增", "区块文件数", "路径"]] +
                       [[o["label"], (o["latest_name"] or "（空）")[:60],
                         o["latest"].strftime("%m-%d %H:%M") if o["latest"] else "—",
                         str(o["today"]) if o["exists"] else "—",
                         str(o["files"]) if o["exists"] else "—",
                         "—" if o["exists"] else "（目录不存在）"] for o in panel["output"]]))
    a("")

    caps = panel["caps"]
    a("## 四、我能调什么（%d 条接口，按用途分组）" % caps["total"])
    a("")
    a("> 路由真相是 `config/tool_registry.json`（接口 → primary → fallback）；分组只是面板展示用的"
      "确定性归类，不改路由。「核对」列只判 primary 是否在位（技能目录 / 脚本文件 / cron 任务 / "
      "toolkit 工具），不执行、不判好坏。")
    a("")
    for gname, items in caps["groups"].items():
        a("### %s（%d）" % (gname, len(items)))
        a("")
        L.extend(_md_table([["接口", "形态", "调用方式", "核对", "用途"]] +
                           [[r["key"], r["mode"], r["howto"], r["check"], r["purpose"][:80]]
                            for r in items]))
        a("")

    pub = panel["publish"]
    a("## 五、账号与发布")
    a("")
    L.extend(_md_table([["产物", "最后更新", "表格行数", "路径"]] +
                       [[k, (v["mtime"].strftime("%Y-%m-%d %H:%M") if v["mtime"] else "（不存在）"),
                         str(v["rows"]) if v["exists"] else "—", str(v["path"])]
                        for k, v in (("发布台账", pub["ledger"]), ("账号体检总览", pub["checkup"]))]))
    a("")
    if panel["doc_check"]["path"]:
        a("- 最近一次文档引用校验报告：%s（%s）"
          % (panel["doc_check"]["path"].name,
             panel["doc_check"]["mtime"].strftime("%Y-%m-%d %H:%M")))
    else:
        a("- 最近一次文档引用校验报告：（未找到）")
    a("")

    a("## 六、一键入口")
    a("")
    a("> 本区块只列命令并核对存在性，**不代执行**；路径失效标 ⚠️。")
    a("> 这些入口可以直接跑：`python scripts/workbench.py --entry <名称>`"
      "（多余参数会透传给目标脚本）；网页版每行有「复制」按钮。")
    a("")
    L.extend(_md_table([["入口", "命令", "核对", "说明"]] +
                       [[e["name"], "`%s`" % e["cmd"], "✅" if e["exists"] else "⚠️ 路径失效",
                         e["note"]] for e in panel["entries"]]))
    a("")
    return "\n".join(L) + "\n"


def render_html(panel: dict) -> str:
    esc = _html.escape

    def table(header: list, rows: list) -> str:
        h = "".join("<th>%s</th>" % esc(x) for x in header)
        body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(str(x)) for x in r)
                       for r in rows)
        return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (h, body)

    P: list = ["<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">",
               "<title>工作台总览</title><style>"]
    P.append("""
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f6f6f3;color:#18181b;margin:0;padding:24px;}
.wrap{max-width:1180px;margin:0 auto;}
h1{font-size:20px;margin:0 0 6px;}
h2{font-size:16px;margin:26px 0 8px;padding-bottom:6px;border-bottom:1px solid #e4e4dd;}
h3{font-size:14px;margin:16px 0 6px;color:#3f3f46;}
.meta{font-size:12px;color:#71717a;line-height:1.7;margin-bottom:12px;}
.alert{background:#fff8e6;border:1px solid #f3d99b;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0;}
.alert li{margin:2px 0;}
table{border-collapse:collapse;width:100%;background:#fff;font-size:12.5px;margin:6px 0 12px;}
th,td{border:1px solid #ecece6;padding:5px 8px;text-align:left;vertical-align:top;}
th{background:#fafaf7;font-weight:500;color:#52525b;white-space:nowrap;}
code{background:#f2f2ee;padding:1px 4px;border-radius:3px;font-size:12px;}
details{margin:6px 0 14px;}summary{cursor:pointer;font-size:14px;font-weight:500;padding:4px 0;}
button.cp{border:1px solid #d8d8d0;background:#fff;border-radius:5px;font-size:11px;
  padding:1px 7px;cursor:pointer;color:#52525b;margin-left:4px;}
button.cp:hover{background:#f2f2ee;}
""")
    P.append("</style></head><body><div class=\"wrap\">")
    P.append("<h1>工作台总览</h1>")
    P.append("<div class=\"meta\">生成时间 %s ｜ 本页由 <code>scripts/workbench_digest.py</code> "
             "确定性生成（零 LLM），请勿手改<br>数据源（只读）："
             "<code>config/tool_registry.json</code>、<code>~/.hermes/cron/jobs.json</code>、"
             "<code>系统中枢/协同/任务台账.md</code>、vault 内容生产目录 mtime</div>"
             % esc(panel["generated_at"]))
    if panel["alerts"]:
        P.append("<div class=\"alert\"><b>⚠️ 告警与自检</b><ul>%s</ul></div>"
                 % "".join("<li>%s</li>" % esc(s) for s in panel["alerts"]))

    w = panel["waiting"]
    cnt = "、".join("%s %d" % (k, v) for k, v in w["counts"].items()) or "无"
    P.append("<h2>一、在等我（%d 件：%s）</h2>" % (len(w["rows"]), esc(cnt)))
    P.append(table(["任务ID", "标题", "平台/形态", "负责人", "状态", "最后更新", "产出路径"],
                   [[r["id"], r["title"], r["platform"], r["owner"], r["status"],
                     r["updated"], brief_paths(r["artifact"])] for r in w["rows"]])
             if w["rows"] else "<p>（无）</p>")

    c = panel["cron"]
    P.append("<h2>二、系统在跑什么（启用 %d / 停用 %d）</h2>" % (c["enabled"], c["disabled"]))
    P.append(table(["时刻", "任务名", "脚本", "deliver", "上次运行", "上次状态", "下次"],
                   [[r["moment"], r["name"], r["script"], r["deliver"], r["last_run"],
                     r["last_status"], r["next_run"]] for r in c["rows"]]))

    P.append("<h2>三、今天产出了什么</h2>")
    P.append(table(["区块", "最新产出", "时间", "今日新增", "文件数", "路径"],
                   [[o["label"], (o["latest_name"] or "（空）")[:60],
                     o["latest"].strftime("%m-%d %H:%M") if o["latest"] else "—",
                     o["today"] if o["exists"] else "—",
                     o["files"] if o["exists"] else "—",
                     str(o["path"]) if o["exists"] else "（目录不存在）"]
                    for o in panel["output"]]))

    caps = panel["caps"]
    P.append("<h2>四、我能调什么（%d 条接口）</h2>" % caps["total"])
    for gname, items in caps["groups"].items():
        P.append("<details><summary>%s（%d）</summary>" % (esc(gname), len(items)))
        P.append(table(["接口", "形态", "调用方式", "核对", "用途"],
                       [[r["key"], r["mode"], r["howto"], r["check"], r["purpose"][:150]]
                        for r in items]))
        P.append("</details>")

    pub = panel["publish"]
    P.append("<h2>五、账号与发布</h2>")
    P.append(table(["产物", "最后更新", "表格行数", "路径"],
                   [[k, (v["mtime"].strftime("%Y-%m-%d %H:%M") if v["mtime"] else "（不存在）"),
                     v["rows"] if v["exists"] else "—", str(v["path"])]
                    for k, v in (("发布台账", pub["ledger"]), ("账号体检总览", pub["checkup"]))]))

    P.append("<h2>六、一键入口</h2>")
    # 入口表单独渲染：命令列带「复制」按钮（本地 HTML 不能直接执行命令，复制是诚实上限）
    P.append("<p class=\"meta\">也可在命令行跑同一个入口："
             "<code>python scripts/workbench.py --entry &lt;名称&gt;</code>（多余参数透传）</p>")
    rows = []
    for e in panel["entries"]:
        rows.append(
            "<tr><td>%s</td><td><code>%s</code> "
            "<button class=\"cp\" data-cmd=\"%s\">复制</button></td><td>%s</td><td>%s</td></tr>"
            % (esc(e["name"]), esc(e["cmd"]), esc(e["cmd"], quote=True),
               "✅" if e["exists"] else "⚠️ 路径失效", esc(e["note"])))
    P.append("<table><thead><tr><th>入口</th><th>命令</th><th>核对</th><th>说明</th></tr>"
             "</thead><tbody>%s</tbody></table>" % "".join(rows))
    P.append("""<script>
document.addEventListener('click', function (ev) {
  var t = ev.target;
  if (!t || !t.classList || !t.classList.contains('cp')) { return; }
  var cmd = t.getAttribute('data-cmd') || '';
  var flash = function (msg) {
    var old = t.textContent; t.textContent = msg;
    setTimeout(function () { t.textContent = old; }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cmd).then(function () { flash('已复制'); },
                                            function () { flash('复制失败'); });
  } else { flash('请手动选中'); }
});
</script>""")
    P.append("</div></body></html>")
    return "\n".join(P) + "\n"


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="workbench_digest.py",
        description="工作台只读面板（确定性、零 LLM；只读四个事实源，写两份渲染）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 md 正文，不写盘")
    ap.add_argument("--now", default=None, help="覆盖生成时间（YYYY-MM-DD HH:MM，幂等自测用）")
    ap.add_argument("--jobs", default=None, help="jobs.json 路径覆盖（测试用）")
    ap.add_argument("--registry", default=None, help="tool_registry.json 路径覆盖（测试用）")
    ap.add_argument("--out-md", default=None, help="md 输出路径覆盖")
    ap.add_argument("--out-html", default=None, help="html 输出路径覆盖")
    ns = ap.parse_args(argv)

    started = time.monotonic()
    now = datetime.strptime(ns.now, "%Y-%m-%d %H:%M") if ns.now else datetime.now()

    try:
        panel = build_panel(Path(ns.jobs) if ns.jobs else DEFAULT_JOBS,
                            Path(ns.registry) if ns.registry else DEFAULT_REGISTRY,
                            now)
    except Exception as exc:  # noqa: BLE001
        print("错误：取数失败：%s" % exc, file=sys.stderr)
        return 1
    md = render_md(panel)
    htm = render_html(panel)

    if ns.dry_run:
        print(md)
        print("（dry-run：用时 %.2fs）" % (time.monotonic() - started), file=sys.stderr)
        return 0

    out_md = Path(ns.out_md) if ns.out_md else OUT_MD_DEFAULT
    out_html = Path(ns.out_html) if ns.out_html else DEFAULT_HTML
    try:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        with out_md.open("w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        with out_html.open("w", encoding="utf-8", newline="\n") as f:
            f.write(htm)
    except Exception as exc:  # noqa: BLE001
        print("错误：写产物失败：%s" % exc, file=sys.stderr)
        return 1

    print("已写：%s（%d 字节）" % (out_md, len(md.encode("utf-8"))))
    print("已写：%s（%d 字节）" % (out_html, len(htm.encode("utf-8"))))
    print("在等我 %d 件 ｜ 启用任务 %d ｜ 接口 %d ｜ 告警 %d ｜ 用时 %.2fs"
          % (len(panel["waiting"]["rows"]), panel["cron"]["enabled"],
             panel["caps"]["total"], len(panel["alerts"]), time.monotonic() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
