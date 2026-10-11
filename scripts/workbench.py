#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workbench.py — 工作台「按名调用」入口（确定性路由，零 LLM）

为什么：能力攒到 88 条接口 / 210 个脚本 / 近 100 个技能之后，卡点不是「没有」，
而是「记不住名字与路径」。本脚本把「按名字找 + 按名字跑」变成一条命令。

与邻居的分工（不重复造）：
    - tool_inventory.py  = 开发前**存量盘点**（面向开发者：宁可多列，别漏，用于判断复用）
    - workbench.py       = 日常**按名调用**（面向使用者：给一条最优命中 + 怎么调 + 可直接跑）
    两者共用同一份索引与匹配实现（直接加载 tool_inventory 复用，不重写）。
    调用方式文案与「一键入口」清单复用 workbench_digest.py（面板与入口同一份口径）。

用法：
    python scripts/workbench.py 爆款拆解               # 查：命中哪条、怎么调
    python scripts/workbench.py 对标视频入库 --limit 8  # 查：多列几条
    python scripts/workbench.py --run 对标视频入库 <链接>   # 跑：取最优命中直接执行
    python scripts/workbench.py --pick 2 --run 转录 <链接>  # 跑：命中不是第一条时按序号挑
    python scripts/workbench.py --entries              # 列一键入口（核对路径存在性）
    python scripts/workbench.py --entry 开工三查 工作台   # 跑一键入口（多余参数透传给目标脚本）
    python scripts/workbench.py 转录 --json

退出码：0 = 有命中；1 = 无命中或执行失败；2 = 命中但形态不可执行（技能/会话内工具）。
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent


def _load_module(name: str, path: Path):
    """按绝对路径加载同目录模块（注册进 sys.modules，见 workbench_digest 的注释）。"""
    spec = _ilu.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 %s" % path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ti = _load_module("tool_inventory_impl", SCRIPT_DIR / "tool_inventory.py")   # 索引 + 匹配
_wb = _load_module("workbench_digest_impl", SCRIPT_DIR / "workbench_digest.py")  # 调用方式 + 入口

REGISTRY = REPO / "config" / "tool_registry.json"

# 命中来源的优先级（同分时排序用）：注册表是唯一能力真相，优先展示
SOURCE_ORDER = {"注册表": 0, "仓库技能": 1, "hub 技能": 2, "仓库脚本": 3,
                "技能脚本": 4, "hermes/scripts": 5, "hermes/skills": 6, "toolkit": 7}

# 注册表优先的加成：它是「能力路由的唯一裁决」，同分或接近时分给它。
# 例：口语「爆款拆解」在注册表里写作「爆款视频拆解」，字面只覆盖 2/3 个字窗，
# 若不加成会输给某个正文里恰好出现完整四字的脚本。
REGISTRY_BONUS = 30

# 聚合入口降权：MCP 服务器（toolkit_mcp 等）的用途里会列举所有子能力，容易把
# 具体接口压下去（实测：口语「转录视频」会先命中 toolkit_mcp 而不是 transcribe_skill）。
# 具体能力优先，聚合入口只作兜底展示。
UMBRELLA_PENALTY = 20


def _is_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _pure_cjk(text: str) -> bool:
    """整串都是汉字（口语能力名就长这样：爆款拆解 / 对标视频入库）。"""
    return bool(text) and all("\u4e00" <= ch <= "\u9fff" for ch in text)


# 滑窗退化的适用范围与门槛（2026-10-12 实测校准）：
#   只对纯中文查询生效 —— 混了 ASCII 的口语串走滑窗会被「能力」「存在」这类
#   常见双字刷出假命中；短词（≤6 字）覆盖率 ≥50% 即认，
#   长串要求 ≥75%，否则宁可判无命中，也不给似是而非的答案。
COVERAGE_MAX_LEN = 6
COVERAGE_MIN_SHORT = 0.5
COVERAGE_MIN_LONG = 0.75


def _hit(query: str, fields: list) -> tuple:
    """按字段命中打分：字段= (标签, 文本, 权重)。返回 (分数, 命中依据列表)。

    两级口径与 tool_inventory.match 同源：整词子串为强命中；中文再按**二字滑窗覆盖率**
    给部分分（中文说法不统一：「对标视频入库」vs 注册表里的「对标视频库入库」；
    「爆款拆解」vs「爆款视频拆解」——纯子串会漏，逐字又会过匹配）。
    覆盖率 < 50% 不计分，避免「命中一个字窗就当归类命中」的噪音。
    """
    q = query.lower().strip()
    score = 0
    why: list = []
    for label, text, weight in fields:
        t = str(text or "").lower()
        if q and q in t:
            score += weight
            why.append(label)
    if not why and _pure_cjk(q) and len(q) >= 2:
        windows = [q[i:i + 2] for i in range(len(q) - 1)]
        need = COVERAGE_MIN_SHORT if len(q) <= COVERAGE_MAX_LEN else COVERAGE_MIN_LONG
        for label, text, weight in fields:
            t = str(text or "").lower()
            hit_n = sum(1 for w in windows if w in t)
            cov = hit_n / len(windows)
            if cov >= need:
                score += int(weight * cov)
                why.append("%s·字窗%d/%d" % (label, hit_n, len(windows)))
    return score, why


# 用途字段很长的条目（如整条内容产线）会把深处偶发提到的一个词刷成满分——
# 所以「用途」按位置拆两段：开头是这条能力的自述，后文只作弱证据。
HEAD_CHARS = 80


def registry_hits(query: str) -> list:
    """注册表命中（能力路由的唯一权威）。"""
    data = json.loads(REGISTRY.read_text(encoding="utf-8")).get("interfaces", {})
    out = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        purpose = str(entry.get("purpose") or "")
        fields = [("接口名", key, 110), ("用途·开头", purpose[:HEAD_CHARS], 80),
                  ("用途·后文", purpose[HEAD_CHARS:], 15),
                  ("主实现", entry.get("primary"), 70),
                  ("兜底", " ".join(map(str, entry.get("fallbacks") or [])), 30)]
        score, why = _hit(query, fields)
        if score <= 0:
            continue
        mode = str(entry.get("mode") or "")
        if mode in ("mcp_server", "external_mcp"):
            score -= UMBRELLA_PENALTY
            why = why + ["聚合入口降权"]
        out.append({"kind": "registry", "source": "注册表", "name": key,
                    "mode": mode,
                    "how": _wb.howto(entry),
                    "desc": str(entry.get("purpose") or ""),
                    "score": score + REGISTRY_BONUS,
                    "why": why + ["注册表优先"]})
    return out


def other_hits(query: str, include_hub: bool) -> list:
    """技能 / 脚本 / toolkit 命中（复用 tool_inventory 的索引与匹配）。"""
    out = []
    for item in _ti.collect(include_hub=include_hub):
        src = str(item.get("source") or "")
        # 注册表 / toolkit 由上面的 registry_hits 与调用方式表负责，避免同一条能力出现两次、
        # 且避免整段 JSON / 全文正文把真正的路由压下去（2026-10-12 实测：会造成误命中）。
        if src in ("注册表", "toolkit"):
            continue
        # 很多 hub 技能的 SKILL.md 用 `description: |` 块式 YAML，tool_inventory 的单行
        # 正则抓不到内容（desc 只剩一个「|」）——这里回退用正文开头当描述，否则这些技能
        # 只剩最低权重的正文可匹配，会被长散文条目压过去（2026-10-12 实测）。
        desc = str(item.get("desc") or "").strip()
        if desc in ("", "|"):
            desc = str(item.get("blob") or "")[:300]
        fields = [("名称", item.get("name"), 100), ("描述", desc, 70),
                  ("路径", item.get("target"), 30), ("正文", item.get("blob"), 10)]
        score, why = _hit(query, fields)
        if score <= 0:
            continue
        if src.endswith("技能") or "skills" in src:
            how = "自然语言触发「%s」" % item.get("name")
        else:
            how = "python %s" % item.get("target")
        out.append({"kind": "skill" if "技能" in src or "skills" in src else "script",
                    "source": src, "name": str(item.get("name")),
                    "mode": "", "how": how,
                    "desc": str(item.get("desc") or ""),
                    "score": score, "why": why})
    return out


def search(query: str, limit: int, include_hub: bool) -> list:
    hits = registry_hits(query) + other_hits(query, include_hub)
    # 同名去重：注册表条目优先（它就是唯一路由真相）
    best: dict = {}
    for h in hits:
        prev = best.get(h["name"])
        if prev is None or h["score"] > prev["score"] or \
                (h["score"] == prev["score"] and SOURCE_ORDER.get(h["source"], 99) <
                 SOURCE_ORDER.get(prev["source"], 99)):
            best[h["name"]] = h
    ordered = sorted(best.values(),
                     key=lambda h: (-h["score"], SOURCE_ORDER.get(h["source"], 99), h["name"]))
    return ordered[:limit]


def executable_target(hit: dict):
    """把命中翻成可执行(argv)或不可执行的原因。"""
    how = hit.get("how") or ""
    if hit["kind"] == "registry" and hit.get("mode") == "manual_skill":
        return None, "这是技能（manual_skill），请在会话里用自然语言触发：%s" % how
    if hit["kind"] == "registry" and hit.get("mode") in ("toolkit_tool", "mcp_server", "external_mcp"):
        return None, "这是会话内/外部 MCP 工具，请在会话里调用：%s" % how
    if hit["kind"] == "skill":
        return None, "这是技能，请在会话里用自然语言触发：%s" % how
    if how.startswith("python "):
        return ["python", how.split(" ", 1)[1].strip()], ""
    return None, "这个命中的形态暂不支持命令行直接执行：%s" % how


def run_hit(hit: dict, extra: list, dry_run: bool) -> int:
    argv, why_not = executable_target(hit)
    if argv is None:
        print("不执行：%s" % why_not, file=sys.stderr)
        return 2
    argv[0] = sys.executable
    argv = argv + list(extra or [])
    print("[执行] %s" % " ".join(argv), file=sys.stderr)
    if dry_run:
        return 0
    try:
        return subprocess.run(argv, cwd=str(REPO)).returncode
    except FileNotFoundError as exc:
        print("执行失败：找不到 %s" % exc, file=sys.stderr)
        return 1


def print_hits(query: str, hits: list) -> None:
    if not hits:
        print("无命中：「%s」" % query)
        print("建议：换 2-3 种说法重试（例：取视频 / 视频获取 / 下载视频）；"
              "或跑 python scripts/tool_inventory.py %s 做全量盘点。" % query)
        return
    print("查询：%s（命中 %d 条，按注册表优先）" % (query, len(hits)))
    for i, h in enumerate(hits, 1):
        print("")
        print("%d. [%s] %s" % (i, h["source"], h["name"]))
        if h.get("desc"):
            print("   用途：%s" % h["desc"][:110])
        print("   怎么调：%s" % h["how"])
        print("   依据：%s（分 %d）" % ("、".join(h["why"]) or "—", h["score"]))
    print("")
    print("要直接跑：python scripts/workbench.py --run %s [参数...]" % query)


def list_entries() -> int:
    print("一键入口（路径失效会标 ⚠️）：")
    bad = 0
    for name, cmd, note in _wb.ENTRY_POINTS:
        target = cmd.split(" ", 1)[1] if cmd.startswith("python ") else cmd
        ok = Path(target).is_file()
        bad += 0 if ok else 1
        print("  %s %-22s %s" % ("✅" if ok else "⚠️", name, cmd))
        if not ok:
            print("      （路径失效：%s）" % target)
    print("")
    print("跑某个入口：python scripts/workbench.py --entry <名称> [额外参数...]")
    return 0 if bad == 0 else 1


def run_entry(name: str, extra: list, dry_run: bool) -> int:
    matches = [(n, c, note) for n, c, note in _wb.ENTRY_POINTS if name and name in n]
    if not matches:
        print("没找到入口「%s」；先跑 --entries 看清单。" % name, file=sys.stderr)
        return 1
    nm, cmd, _note = matches[0]
    if len(matches) > 1:
        print("提示：%d 个入口名含「%s」，取第一个「%s」。"
              % (len(matches), name, nm), file=sys.stderr)
    if cmd.startswith("python "):
        argv = [sys.executable, cmd.split(" ", 1)[1].strip()] + list(extra or [])
        print("[执行] %s" % " ".join(argv), file=sys.stderr)
        if dry_run:
            return 0
        return subprocess.run(argv, cwd=str(REPO)).returncode
    target = Path(cmd)
    print("[启动] %s（%s）" % (cmd, nm), file=sys.stderr)
    if dry_run:
        return 0
    if not target.is_file():
        print("路径失效，未启动：%s" % target, file=sys.stderr)
        return 1
    # .cmd/.bat/.lnk 用 shell 打开 = 等价双击（会开新窗口，不阻塞本进程）
    try:
        os.startfile(str(target))  # noqa: S606 - 就是要点开用户的桌面入口
    except OSError as exc:
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="workbench.py",
        description="工作台按名调用入口（确定性路由，零 LLM；复用 tool_inventory 的索引）")
    ap.add_argument("query", nargs="?", help="要查的能力名（一个词；含空格请加引号）")
    ap.add_argument("--run", action="store_true", help="执行命中项（取 --pick 指定序号，默认 1）")
    ap.add_argument("--pick", type=int, default=1, help="配合 --run：取第 N 条命中（从 1 数）")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令")
    ap.add_argument("--limit", type=int, default=5, help="最多展示几条命中（默认 5）")
    ap.add_argument("--no-hub", action="store_true", help="不扫社区技能 hub（更快）")
    ap.add_argument("--registry", default=None, help="tool_registry.json 路径覆盖（测试用）")
    ap.add_argument("--entries", action="store_true", help="列出「一键入口」清单")
    ap.add_argument("--entry", default=None, help="执行某个「一键入口」（按名称子串匹配）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    # query 只吃一个词，其余位置参数一律透传给目标脚本 —— 否则「--run 开工三查 工作台」
    # 会把两段拼成一个查询词（2026-10-12 实测踩到，结果跑错脚本）。
    args, extra = ap.parse_known_args(argv)

    if args.registry:
        global REGISTRY
        REGISTRY = Path(args.registry)

    if args.entries:
        return list_entries()

    if args.entry:
        return run_entry(args.entry, extra, args.dry_run)

    if not args.query:
        ap.error("给一个能力名，或用 --entries / --entry")
    query = args.query.strip()

    hits = search(query, args.limit, include_hub=not args.no_hub)

    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
        return 0 if hits else 1

    if not args.run:
        print_hits(query, hits)
        return 0 if hits else 1

    if not hits:
        print("无命中，未执行：「%s」" % query, file=sys.stderr)
        return 1
    if not 1 <= args.pick <= len(hits):
        print("--pick %d 超出命中条数 %d" % (args.pick, len(hits)), file=sys.stderr)
        return 1
    chosen = hits[args.pick - 1]
    print("[命中] %s（%s，分 %d）→ %s"
          % (chosen["name"], chosen["source"], chosen["score"], chosen["how"]), file=sys.stderr)
    return run_hit(chosen, extra, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
