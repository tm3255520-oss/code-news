#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""work_lookup.py — 开工三查（查重 / 接得上吗 / 可不可以新建），确定性零 LLM。

对应 vault `系统中枢/规则与权限/智能体共享/05-记忆协议.md` §六.1：
    ① 查台账 ② 读交接 ③ 都没有才新建。

用法：
    python work_lookup.py "GPT-5 视频生成"                 # 人工看：命中清单 + 判定
    python work_lookup.py 分镜 --status 进行中              # 只看进行中
    python work_lookup.py 小红书 --json                    # 给别的脚本/Agent 消费
    python work_lookup.py 视频号 --fail-on-active           # 门禁用法：有进行中任务则 exit 3
    python work_lookup.py --list-active                    # 列出全部活跃任务（不开工也能看）

退出码：
    0  正常（无论是否命中）
    1  用法 / 数据错误
    3  --fail-on-active 且命中活跃任务（进行中 / 待审）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xietong_lib import (  # noqa: E402
    ACTIVE_STATUSES, STATUSES, parse_ledger, read_all_index, read_handoff, resolve_root,
    handoff_path, tokens,
)


def match_task(task, words: list[str]) -> bool:
    haystack = " ".join([task.task_id, task.title, task.platform, task.artifact, task.link]).lower()
    return any(w.lower() in haystack for w in words)


def block_text(block) -> str:
    return " ".join([block.ts, block.agent, block.task_id] + list(block.fields.values())).lower()


def collect(args) -> dict:
    root = resolve_root(args.root)
    led = parse_ledger(root / "任务台账.md")
    words = args.keywords or []

    tasks = [t for t in led.tasks if not words or match_task(t, words)]
    if args.status:
        tasks = [t for t in tasks if t.status in args.status]
    if args.owner:
        tasks = [t for t in tasks if t.owner in args.owner]
    if args.list_active:
        tasks = [t for t in led.tasks if t.status in ACTIVE_STATUSES]

    hits = []
    for t in tasks[: max(args.limit, 1)]:
        path = handoff_path(root, t.task_id)
        blocks, problems = read_handoff(path)
        last = blocks[-1] if blocks else None
        hits.append({
            "task_id": t.task_id,
            "title": t.title,
            "platform": t.platform,
            "owner": t.owner,
            "status": t.status,
            "updated": t.updated,
            "artifact": t.artifact,
            "link": t.link,
            "handoff_exists": path.is_file(),
            "handoff_problems": problems,
            "last_block": None if last is None else {
                "ts": last.ts, "agent": last.agent,
                "did": last.field("本轮做了什么"), "next": last.field("下一步"),
                "evidence": last.field("证据"), "open": last.field("未决问题"),
            },
        })

    index_hits = []
    if words:
        rows, problems = read_all_index(root)
        for agent, row in rows:
            blob = json.dumps(row, ensure_ascii=False).lower()
            if any(w.lower() in blob for w in words):
                index_hits.append({"file": agent, **row})
        index_problems = problems
    else:
        index_problems = []

    active = [h for h in hits if h["status"] in ACTIVE_STATUSES]
    done = [h for h in hits if h["status"] in ("已完成", "归档")]
    return {
        "root": str(root),
        "keywords": words,
        "ledger_problems": led.problems,
        "tasks": hits,
        "active": active,
        "done": done,
        "handoffs": [h for h in hits if h["handoff_exists"]],
        "index": index_hits,
        "index_problems": index_problems,
    }


def verdict(payload: dict) -> tuple[str, list[str]]:
    if payload["active"]:
        owners = "、".join(sorted({h["owner"] or "?" for h in payload["active"]}))
        lines = [f"⚠️ 命中 {len(payload['active'])} 个活跃任务（负责人：{owners}）→ **不要重复开工**",
                 "   先读交接文件的最后一块；要补料就直接给负责人，要接手就改台账负责人。"]
        return "active", lines
    if payload["done"]:
        lines = [f"✅ 命中 {len(payload['done'])} 个已完成/归档任务 → 复用产出，不重做",
                 "   产出路径见下方【台账】列。"]
        return "done", lines
    if payload["tasks"]:
        return "other", ["ℹ️ 只命中暂停/待认领类任务：暂停的先看阻塞原因；待认领的可直接认领。"]
    return "none", ["✅ 无命中 → 可新建台账行（状态=进行中、负责人=自己）再动手。"]


def render(payload: dict) -> str:
    out: list[str] = []
    kw = " ".join(payload["keywords"]) or "(全部)"
    out.append(f"=== 开工三查：{kw} ===")
    out.append(f"根目录：{payload['root']}")
    if payload["ledger_problems"]:
        out.append("[!] 台账问题：" + "；".join(payload["ledger_problems"]))

    out.append(f"\n[1/3 台账] 命中 {len(payload['tasks'])} 行")
    for h in payload["tasks"]:
        out.append(f"  {h['task_id']} | {h['title']} | {h['platform']} | 负责人={h['owner']} "
                   f"| 状态={h['status']} | 更新={h['updated']}")
        out.append(f"        产出：{h['artifact']}")

    out.append(f"\n[2/3 交接] 有交接文件 {len(payload['handoffs'])} 个")
    for h in payload["handoffs"]:
        blk = h["last_block"]
        out.append(f"  {h['task_id']} → {h['link'] or '(未登记链接)'}")
        if blk:
            out.append(f"        最后一块 {blk['ts']}（{blk['agent']}）：{blk['did']}")
            out.append(f"        下一步：{blk['next']} ｜ 证据：{blk['evidence']}")
        for p in h["handoff_problems"]:
            out.append(f"        [!] {p}")

    out.append(f"\n[3/3 会话索引] 命中 {len(payload['index'])} 行")
    for r in payload["index"][:10]:
        out.append(f"  {r.get('ts')} | {r.get('agent')} | {r.get('task')} | {r.get('summary')}")

    kind, lines = verdict(payload)
    out.append("\n判定：" + lines[0])
    for extra in lines[1:]:
        out.append(extra)
    return "\n".join(out) + f"\n\nverdict={kind}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="开工三查：台账 / 交接 / 会话索引")
    p.add_argument("keywords", nargs="*", help="检索关键词（可多个）")
    p.add_argument("--root", default=None, help="协同根目录（默认自动解析）")
    p.add_argument("--status", action="append", choices=STATUSES, help="按状态过滤（可重复）")
    p.add_argument("--owner", action="append", help="按负责人过滤（可重复）")
    p.add_argument("--limit", type=int, default=20, help="台账最多显示多少行")
    p.add_argument("--list-active", action="store_true", help="忽略关键词，列出全部活跃任务")
    p.add_argument("--json", action="store_true", help="输出 JSON（供脚本/Agent 消费）")
    p.add_argument("--fail-on-active", action="store_true",
                   help="门禁模式：命中活跃任务时 exit 3")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.keywords and not args.list_active and not args.status and not args.owner:
        print("用法错误：至少要给关键词，或用 --list-active / --status / --owner 之一",
              file=sys.stderr)
        return 1
    payload = collect(args)
    kind, _ = verdict(payload)
    if args.json:
        print(json.dumps({**payload, "verdict": kind}, ensure_ascii=False, indent=2))
    else:
        print(render(payload))
    if args.fail_on_active and kind == "active":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
