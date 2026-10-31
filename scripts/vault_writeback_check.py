#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault_writeback_check.py —— 收工落盘自检：系统运行环节的资料有没有全反写进 vault

为什么需要这个（2026-10-20 用户明示 + 实战）：

> 用户的**全部工作以 Obsidian 为系统中枢**。凡**系统运行环节**（跑产线/脚本、排障、改配置权限、
> 接新工具技能、搭改链路、做运维巡检、验收验证 —— 任何让系统「动起来」或「变了」的动作），
> **必须按 `05-记忆协议.md` §四·4.1 落点路由表把资料反写进 vault 对应子目录**。

2026-10-20 那轮治理就漏了 5 处（复盘 / 工作流硬规则 / 运行小结 / 工具档案 / MOC 导航）——
**漏不是因为忘了写，而是因为没有"收工时对着路由表点一遍"这个动作**。
本脚本把这个动作变成一条命令。

用法：

    # ① 从协同台账取某个任务的产出列当"本轮改动清单"（最常用）
    python scripts/vault_writeback_check.py --ledger WK-20261020-21

    # ② 手工给改动清单
    python scripts/vault_writeback_check.py --changed "D:/AI-VIDEO/产线现状总览.md" "C:/.../x.py"

    # ③ 从 code-news 的 git 工作区取（未提交 + 已提交）
    python scripts/vault_writeback_check.py --git-status

    # ④ 顺带体检：vault 里今天新增的文档有没有漏写 ## 回链
    python scripts/vault_writeback_check.py --scan-vault --since 2026-10-20

输出：每类资料 → 需要哪个落点 / 实际落没落 / 缺什么；退出码 0 = 无缺口，1 = 有缺口
（便于直接接进收工门禁或巡检）。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

VAULT = r"D:\Obsidian Vault\obsidian Vault"
COLLAB = os.path.join(VAULT, "系统中枢", "协同")
LEDGER = os.path.join(COLLAB, "任务台账.md")

# ── 05-记忆协议 §四·4.1 落点路由表（资料性质 → 落点）────────────────────────
ROUTES: List[Tuple[str, str, str]] = [
    ("决策", "系统中枢/经验沉淀/决策/", "YYYY-MM-DD-<标题>.md"),
    ("复盘", "系统中枢/经验沉淀/复盘/", "YYYY-MM-DD-<系统>-<问题>.md"),
    ("工作流硬规则", "系统中枢/经验沉淀/工作流/", "<领域>-工作流.md"),
    ("运行小结", "系统中枢/运行小结/", "按该目录既有惯例"),
    ("SOP/运行手册", "系统中枢/运行手册/", "<主题>SOP.md"),
    ("工具档案", "系统中枢/系统脚本工具链/", "<工具>-工具说明.md"),
    ("导航/MOC", "系统中枢/地图与导航/MOC/", "<板块>地图.md"),
    ("技能变更日志", "系统中枢/规则与权限/智能体共享/技能变更日志.md", "追加表格行"),
    ("对话归档", "系统中枢/经验沉淀/对话归档/", "按该目录惯例"),
    ("协同三件套", "系统中枢/协同/", "台账 + 交接/<任务ID>.md + 会话索引/<agent>.jsonl"),
]

# ── 改动特征 → 需要哪几类落点 ───────────────────────────────────────────────
# 顺序有意义：先判具体类型，再判通用兜底
CHANGE_RULES: List[Tuple[str, List[str], str]] = [
    # (正则, 需要的落点类型, 说明)
    (r"\.hermes[\\/]cron[\\/]jobs\.json$", ["决策", "运行小结"], "改了调度任务（cron）"),
    (r"\.hermes[\\/].+\.(py|json|yaml|yml)$", ["决策", "运行小结"], "改了 Agent 私有区配置/脚本"),
    (r"code-news[\\/].+\.(py|bat|ps1|json)$", ["工具档案", "运行小结"], "改了生产代码/脚本/注册表"),
    (r"^D:[\\/]AI-VIDEO[\\/].+\.(py|md|json|bat)$", ["工具档案", "运行小结"], "改了产线脚本/文档"),
    (r"^D:[\\/]AI-VIDEO[\\/]config[\\/]", ["运行小结"], "改了产线配置"),
    (r"^D:[\\/].+\.(md|json|ya?ml)$", ["运行小结"], "改了 vault 外的数据/配置"),
    (r"[\\/]scripts[\\/].+\.py$", ["工具档案", "运行小结"], "动了脚本"),
    (r"[\\/]skills[\\/].+[\\/]SKILL\.md$", ["技能变更日志", "决策"], "改了 skill 主实现"),
    (r"[\\/]MCP[\\/]|[\\/]mcp[\\/]", ["技能变更日志", "决策"], "动了 MCP"),
]

# vault 自身路径 → 已经就是落点，不需要再登记
# ⚠️ 前缀必须与 norm() 同一形态（正斜杠），否则 startswith 永远为假 —— 2026-10-21 单测抓到的真 bug
VAULT_PREFIX = VAULT.replace("\\", "/").lower().rstrip("/")


def norm(p: str) -> str:
    return p.replace("\\", "/")


def in_vault(p: str) -> bool:
    return norm(p).lower().startswith(VAULT_PREFIX.lower())


# ── 改动清单来源 ────────────────────────────────────────────────────────────
def changed_from_ledger(task_id: str) -> Tuple[List[str], Optional[datetime.datetime]]:
    """从协同台账读该任务的产出列（改动清单）+ 最后更新时间。"""
    if not os.path.isfile(LEDGER):
        return [], None
    with open(LEDGER, encoding="utf-8") as fh:
        text = fh.read()
    for line in text.splitlines():
        if task_id in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")]
            # | ID | 标题 | 平台 | 负责人 | 状态 | 更新时间 | 产出路径 | 交接 |
            paths: List[str] = []
            if len(cells) >= 8:
                paths = [p.strip() for p in cells[7].split(",") if p.strip()]
            ts = None
            if len(cells) >= 7:
                try:
                    ts = datetime.datetime.strptime(cells[6].strip(), "%Y-%m-%d %H:%M")
                except ValueError:
                    ts = None
            return paths, ts
    return [], None


def changed_from_git(repo: str) -> List[str]:
    out = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    paths = []
    for line in out.splitlines():
        if len(line) > 3:
            paths.append(os.path.join(repo, line[3:].strip().strip('"')))
    return paths


# ── 分类 ────────────────────────────────────────────────────────────────────
def classify(paths: List[str]) -> Dict[str, List[str]]:
    """返回 {落点类型: [触发的改动文件]}。vault 内改动不参与（它本身就是落点）。"""
    hits: Dict[str, List[str]] = {}
    for p in paths:
        if in_vault(p):
            continue
        n = norm(p)
        for pattern, kinds, why in CHANGE_RULES:
            if re.search(pattern, n, re.IGNORECASE):
                for k in kinds:
                    hits.setdefault(k, []).append(p)
                break
    return hits


# ── 落点是否已落实 ──────────────────────────────────────────────────────────
def route_dir(kind: str) -> str:
    for name, path, _ in ROUTES:
        if name == kind:
            return os.path.join(VAULT, path.replace("/", os.sep))
    return VAULT


def landed_files(kind: str, since: Optional[datetime.datetime]) -> List[str]:
    """该落点目录里，since 之后被新建/修改的文件。"""
    d = route_dir(kind)
    if not os.path.isdir(d):
        return []
    out = []
    for dp, dn, fn in os.walk(d):
        for f in fn:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            try:
                m = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
            if since is None or m >= since:
                out.append(p)
    return out


def has_backlink(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            t = fh.read()
    except OSError:
        return True
    return ("## 回链" in t) or ("回链" in t and "##" in t)


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="收工落盘自检（对照 05-记忆协议 §四·4.1 路由表）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ledger", help="协同台账任务号（从该行产出列取改动清单）")
    src.add_argument("--changed", nargs="+", help="手工给改动清单")
    src.add_argument("--git-status", action="store_true", help="从 code-news 的 git 工作区取")
    src.add_argument("--scan-vault", action="store_true", help="只体检 vault 内文档的回链段")
    ap.add_argument("--check-paths", action="store_true",
                    help="检查产出路径是否真实存在（防路径笔误）；可与 --ledger 同用")
    ap.add_argument("--repo", default=r"C:\Users\Administrator\Documents\code-news", help="--git-status 的仓库路径")
    ap.add_argument("--since", help="起始时间（YYYY-MM-DD 或 YYYY-MM-DD HH:MM），默认取台账行时间")
    ap.add_argument("--json", help="结果 JSON 落盘路径")
    args = ap.parse_args(argv)

    since: Optional[datetime.datetime] = None
    if args.since:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                since = datetime.datetime.strptime(args.since, fmt)
                break
            except ValueError:
                continue

    paths: List[str] = []
    if args.ledger:
        paths, ts = changed_from_ledger(args.ledger)
        if since is None and ts:
            since = ts
        if not paths:
            print(f"[!] 台账里没找到 {args.ledger} 的产出列", file=sys.stderr)
    elif args.changed:
        paths = list(args.changed)
    elif args.git_status:
        paths = changed_from_git(args.repo)
    elif args.scan_vault:
        paths = []

    # ── 0. 产出路径存在性检查（防路径笔误）──────────────────────────────
    # 2026-10-21 实战：同一个路径笔误（`系统中枢` 打成 `系统中中枢`）一天内犯了三次，
    # 每次都要等巡检才发现 → 这里把它变成一道机械闸。
    missing_paths: List[str] = []
    if paths:
        missing_paths = [p for p in paths if not os.path.exists(p)]
        if args.check_paths or args.ledger:
            print(f"══ 收工落盘自检 ══  产出路径存在性：{len(paths) - len(missing_paths)}/{len(paths)} 存在")
            for p in missing_paths:
                print(f"   ❌ 路径不存在（笔误？）：{p}")
            if not missing_paths:
                print("   ✅ 产出路径全部存在")
            print()

    report: Dict[str, object] = {"since": since.isoformat() if since else None, "changed": len(paths)}

    # ── 0.5 落盘判据的时间口径修正 ────────────────────────────────────────
    # 台账行的"最后更新"是**收工时刻**，而落盘往往发生在动作过程中（更早）→
    # 拿收工时刻当 since 会把"本轮落的盘"判成"没落"。
    # 正确口径：**最早的那个改动文件的时间**（改动必然不晚于它自己的落盘动作），
    # 取二者较小值作为"已落"的时间下界。
    since_effective = since
    if paths:
        mtimes = []
        for p in paths:
            # 只算**文件**的 mtime：目录（尤其备份目录）的 mtime 会把时间下界拉得很宽，
            # 让"缺落点"判不出来。目录不是改动。
            if not os.path.isfile(p):
                continue
            try:
                mtimes.append(datetime.datetime.fromtimestamp(os.path.getmtime(p)))
            except OSError:
                pass
        if mtimes:
            earliest = min(mtimes)
            if since_effective is None or earliest < since_effective:
                since_effective = earliest
    if since_effective != since:
        print(f"（落盘判定时间下界取 {since_effective} —— 台账时间是收工时刻，"
              f"本轮落盘发生在动作过程中，不能用收工时刻卡）")

    # ── 1. vault 外改动 → 该落哪几类 ──────────────────────────────────────
    needs = classify(paths)
    report["needs"] = {k: v for k, v in needs.items()}
    print(f"══ 收工落盘自检 ══  起始时间: {since if since else '(未指定)'}")
    outside_files = sorted({p for v in needs.values() for p in v})
    print(f"改动文件: {len(paths)} 个（vault 外 {len(outside_files)} 个 → 归出 {len(needs)} 类落点要求）\n")

    gaps: List[str] = []
    if needs:
        print("按 05-记忆协议 §四·4.1 路由表逐类核对：\n")
        for kind, _route_path, _naming in ROUTES:
            if kind not in needs:
                continue
            d = route_dir(kind)
            landed = landed_files(kind, since_effective)
            ok = bool(landed)
            mark = "✅" if ok else "❌"
            print(f"  {mark} {kind:<12} 落点: {norm(d).replace(VAULT.replace(chr(92), '/'), '')}")
            print(f"      触发: {len(needs[kind])} 个改动 → {', '.join(os.path.basename(p) for p in needs[kind][:4])}"
                  + (" …" if len(needs[kind]) > 4 else ""))
            if ok:
                print(f"      已落: {', '.join(os.path.basename(p) for p in landed[:3])}"
                      + (" …" if len(landed) > 3 else ""))
            else:
                gaps.append(kind)
                print(f"      ❌ 缺落点：{kind}（该目录下 {since} 之后无新增/修改）")
            print()
    else:
        print("（本轮没有 vault 外的改动 → 无需额外落点登记）\n")

    # ── 2. vault 内新增文档 → 回链段体检 ──────────────────────────────────
    # 范围**只限"文档型"落点**（决策/复盘/工作流/运行小结/运行手册/工具档案/MOC/对话归档）+ 参考库。
    # 排除：① raw/ 素材、log.md、.workbuddy-ai/ 记忆 —— 那些不是"文档"；
    #       ② 协同三件套（台账/交接/会话索引）—— 那是**状态记录**，不适用回链段要求。
    backlink_gaps: List[str] = []
    if args.scan_vault or since:
        doc_kinds = ["决策", "复盘", "工作流硬规则", "运行小结", "SOP/运行手册",
                     "工具档案", "导航/MOC", "对话归档"]
        scope_dirs = [route_dir(k) for k in doc_kinds] + [os.path.join(VAULT, "参考库")]
        scanned = 0
        seen = set()
        for base in scope_dirs:
            if not os.path.isdir(base) or base in seen:
                continue
            seen.add(base)
            for dp, dn, fn in os.walk(base):
                if "\\.obsidian" in dp or "\\.git" in dp:
                    continue
                for f in fn:
                    if not f.endswith(".md"):
                        continue
                    p = os.path.join(dp, f)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    # 「是否新增」用**创建时间**，不用 mtime ——
                    # 老文件被人改过 mtime 也会更新，用 mtime 会把老文档全算成"新增"（噪音）。
                    created = datetime.datetime.fromtimestamp(st.st_ctime)
                    if since and created < since:
                        continue
                    scanned += 1
                    if not has_backlink(p):
                        backlink_gaps.append(p)
        print(f"回链段体检: 扫 {scanned} 篇（范围 = 文档型落点 + 参考库；已排除协同状态记录；since "
              f"{since.isoformat() if since else '全量'}）")
        if backlink_gaps:
            print(f"  ⚠️ {len(backlink_gaps)} 篇缺 `## 回链` 段（新增文档建议补，方便三向可达）")
            for p in backlink_gaps[:8]:
                print(f"     - {norm(p).replace(VAULT.replace(chr(92), '/'), '')}")
            if len(backlink_gaps) > 8:
                print(f"     … 另 {len(backlink_gaps) - 8} 篇")
        else:
            print("  ✅ 全部有回链段")
        print()

    report["gaps"] = gaps
    report["backlink_gaps"] = backlink_gaps
    report["missing_paths"] = missing_paths
    if args.json:
        json.dump(report, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[记录] → {args.json}")

    if missing_paths:
        print(f"结论: ❌ 产出路径 {len(missing_paths)} 条不存在（笔误或文件已被删）")
        print("      → 改台账那一行的产出路径列；别让巡检再报一次断链")
        return 1
    if gaps:
        print(f"结论: ❌ 缺 {len(gaps)} 类落盘 → {', '.join(gaps)}")
        print("      （05-记忆协议 §四·4.2：同步整理，不是「以后再说」）")
        return 1
    print("结论: ✅ 落点齐全")
    return 0


if __name__ == "__main__":
    sys.exit(main())
