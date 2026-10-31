#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xietong_weekly.py — 协同周报（周一 09:00，确定性零 LLM，无 Agent）。

内容：状态分布 / 负责人分布 / 本周新增 / 本周完成 / 停滞清单 / 交接与会话索引活动 /
巡检 findings 摘要。输出 Markdown 到 stdout（cron no_agent=True 时逐字投递）。

用法：
    python xietong_weekly.py                 # 打印周报
    python xietong_weekly.py --days 14
    python xietong_weekly.py --out <path>    # 同时落盘
    python xietong_weekly.py --soft          # 有 findings 也 exit 0（默认即 0）

退出码：0 = 正常（含 findings 存在，周报不是门禁）；2 = 环境错误。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xietong_lib import (  # noqa: E402
    HANDOFF_DIR, PLACEHOLDER, STATUSES, parse_ledger, read_all_index, read_handoff,
    resolve_root,
)
from xietong_audit import audit  # noqa: E402  （同一套判据，避免两处漂移）

STATUS_ORDER = list(STATUSES)


def task_date(task_id: str) -> datetime | None:
    try:
        return datetime.strptime(task_id.split("-")[1], "%Y%m%d")
    except (IndexError, ValueError):
        return None


def build_report(root: Path, days: int, now: datetime | None = None) -> str:
    now = now or datetime.now()
    since = now - timedelta(days=days)
    led = parse_ledger(root / "任务台账.md")
    rows, _ = read_all_index(root)
    findings = audit(root, stale_days=days, now=now)

    total = len(led.tasks)
    by_status = Counter(t.status or "?" for t in led.tasks)
    by_owner = Counter(t.owner or "?" for t in led.tasks)

    new_tasks = [t for t in led.tasks if (d := task_date(t.task_id)) and d >= since]
    done_tasks = [t for t in led.tasks if t.status in ("已完成", "归档")
                  and (ts := t.updated_at) and ts >= since]
    stalled = [t for t in led.tasks if t.status in ("进行中", "待审")
               and (ts := t.updated_at) and (now - ts).days > days]

    block_count: Counter[str] = Counter()
    hdir = root / HANDOFF_DIR
    if hdir.is_dir():
        for path in sorted(hdir.glob("WK-*.md")):
            blocks, _ = read_handoff(path)
            for b in blocks:
                ts = b.ts.replace("T", " ")
                dt = None
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(ts, fmt)
                        break
                    except ValueError:
                        continue
                if dt and dt >= since:
                    block_count[b.agent] += 1

    index_recent = Counter(agent for agent, r in rows
                           if (ts := str(r.get("ts", "")).replace("T", " ")[:16])
                           and _parse(ts) and _parse(ts) >= since)

    out: list[str] = []
    out.append(f"# 协同周报（{since.strftime('%Y-%m-%d')} ~ {now.strftime('%Y-%m-%d')}）")
    out.append("")
    out.append(f"> 生成：{now.strftime('%Y-%m-%d %H:%M')} ｜ 三件套根：`{root}` ｜ 窗口：{days} 天")
    out.append("")
    out.append("## 一、台账总览")
    out.append("")
    out.append(f"- 任务总数：**{total}**")
    out.append(f"- 本周新增：**{len(new_tasks)}** ｜ 本周完成/归档：**{len(done_tasks)}** ｜ 停滞：**{len(stalled)}**")
    out.append("")
    out.append("| 状态 | 数量 |")
    out.append("|---|---|")
    for s in STATUS_ORDER:
        if by_status.get(s):
            out.append(f"| {s} | {by_status[s]} |")
    out.append("")
    out.append("| 负责人 | 任务数 | 本周交接块 | 本周会话索引 |")
    out.append("|---|---|---|---|")
    owners = sorted(set(by_owner) | set(block_count) | set(index_recent))
    for owner in owners:
        out.append(f"| {owner} | {by_owner.get(owner, 0)} | {block_count.get(owner, 0)} "
                   f"| {index_recent.get(owner, 0)} |")
    out.append("")

    out.append("## 二、本周新增任务")
    out.append("")
    if new_tasks:
        for t in new_tasks:
            out.append(f"- `{t.task_id}` {t.title}（{t.platform}）— 负责人 {t.owner} / {t.status}")
    else:
        out.append("（无）")
    out.append("")

    out.append("## 三、本周完成 / 归档")
    out.append("")
    if done_tasks:
        for t in done_tasks:
            out.append(f"- `{t.task_id}` {t.title} — {t.status}（{t.updated}）产出：{t.artifact}")
    else:
        out.append("（无）")
    out.append("")

    out.append(f"## 四、停滞清单（>{days} 天未更新且状态为进行中/待审）")
    out.append("")
    if stalled:
        for t in stalled:
            age = (now - t.updated_at).days if t.updated_at else "?"
            out.append(f"- `{t.task_id}` {t.title} — {t.status}，已 {age} 天未更新，负责人 {t.owner}")
    else:
        out.append("（无）")
    out.append("")

    out.append("## 五、巡检摘要")
    out.append("")
    if findings:
        for f in findings[:20]:
            out.append(f"- [{f['check']}] {f['detail']}")
        if len(findings) > 20:
            out.append(f"- …另有 {len(findings) - 20} 条，见每日巡检输出")
    else:
        out.append("findings=0")
    out.append("")
    return "\n".join(out)


def _parse(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="协同周报")
    p.add_argument("--root", default=None)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--out", default=None, help="同时写入的 Markdown 路径")
    p.add_argument("--soft", action="store_true", help="兼容用；周报默认 exit 0")
    p.add_argument("--now", default=None, help="覆盖当前时间（ISO，测试用）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = resolve_root(args.root)
    if not (root / "任务台账.md").is_file():
        print(f"环境错误：找不到台账 {root / '任务台账.md'}", file=sys.stderr)
        return 2
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    report = build_report(root, args.days, now)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
