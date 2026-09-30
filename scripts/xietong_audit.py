#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xietong_audit.py — 协同三件套每日巡检（确定性零 LLM，无 Agent）。

查四类问题（对应 05-记忆协议 §六.4）：
    1. 停滞：进行中 / 待审 超过 --stale-days 天没更新
    2. 重复：同平台 + 标题有共同词元的两个活跃任务（重复劳动预警）
    3. 格式：台账行缺负责人 / 状态非法 / 时间戳不可解析；交接块缺字段
    4. 断链：活跃任务没有交接文件；交接文件在台账里没有对应行

用法：
    python xietong_audit.py                 # 有 findings 则 exit 1（cron 失败即告警）
    python xietong_audit.py --soft           # 只报告不失败（exit 0）
    python xietong_audit.py --json
    python xietong_audit.py --stale-days 3

退出码：0 = findings=0（或 --soft）；1 = 有 findings；2 = 用法/环境错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xietong_lib import (  # noqa: E402
    ACTIVE_STATUSES, HANDOFF_DIR, PLACEHOLDER, STATUSES, parse_ledger, read_all_index,
    read_handoff, resolve_root, tokens,
)


def vault_root_of(root: Path) -> Path:
    """协同根 = <vault>/系统中枢/协同 → vault 根。"""
    return Path(root).parent.parent


def audit(root: Path, stale_days: int, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    findings: list[dict] = []

    def add(check: str, detail: str) -> None:
        findings.append({"check": check, "detail": detail})

    led = parse_ledger(root / "任务台账.md")
    for problem in led.problems:
        add("格式", problem)

    vault = vault_root_of(root)
    for t in led.tasks:
        if not t.owner or t.owner == PLACEHOLDER:
            add("格式", f"{t.task_id} 缺负责人（L{t.line_no}）")
        if t.status not in STATUSES:
            add("格式", f"{t.task_id} 状态非法：{t.status!r}（L{t.line_no}）")
        ts = t.updated_at
        if ts is None:
            add("格式", f"{t.task_id} 最后更新时间不可解析：{t.updated!r}")
        elif t.status in ACTIVE_STATUSES:
            age = (now - ts).days
            if age > stale_days:
                add("停滞", f"{t.task_id} 状态={t.status} 已 {age} 天未更新（阈值 {stale_days} 天）")
        if t.artifact and t.artifact != PLACEHOLDER and "/" in t.artifact:
            if not (vault / t.artifact.strip("`")).exists():
                add("断链", f"{t.task_id} 产出路径不存在：{t.artifact}")

    # 重复：同平台 + 共同词元
    active = [t for t in led.tasks if t.status in ACTIVE_STATUSES]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.platform and a.platform == b.platform and (tokens(a.title) & tokens(b.title)):
                add("重复", f"{a.task_id} 与 {b.task_id} 同平台（{a.platform}）且标题重叠，"
                            f"两者都在做：{sorted(tokens(a.title) & tokens(b.title))}")

    # 交接文件
    hdir = root / HANDOFF_DIR
    known = {t.task_id for t in led.tasks}
    seen_files: set[str] = set()
    for t in led.tasks:
        path = hdir / f"{t.task_id}.md"
        if not path.is_file():
            if t.status in ACTIVE_STATUSES:
                add("断链", f"{t.task_id} 是活跃任务但没有交接文件")
            continue
        seen_files.add(t.task_id)
        _, problems = read_handoff(path)
        for p in problems:
            add("格式", f"{t.task_id}: {p}")
    if hdir.is_dir():
        for path in sorted(hdir.glob("WK-*.md")):
            if path.stem not in known:
                add("断链", f"交接文件 {path.name} 在台账里没有对应任务行")

    rows, index_problems = read_all_index(root)
    for p in index_problems:
        add("格式", f"会话索引：{p}")
    for agent, row in rows:
        if row.get("outcome") not in STATUSES:
            add("格式", f"会话索引 {agent}.jsonl：outcome 非法 {row.get('outcome')!r}")
        if row.get("task") not in known and row.get("task") != PLACEHOLDER:
            add("断链", f"会话索引 {agent}.jsonl 引用了不存在的任务 {row.get('task')}")
    return findings


def render(root: Path, findings: list[dict], stale_days: int) -> str:
    out = [f"=== 协同三件套巡检（{datetime.now().strftime('%Y-%m-%d %H:%M')}）===",
           f"根目录：{root} ｜ 停滞阈值：{stale_days} 天"]
    if not findings:
        out.append("无问题。")
    for f in findings:
        out.append(f"[{f['check']}] {f['detail']}")
    out.append(f"\nxietong_audit: findings={len(findings)}")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="协同三件套每日巡检")
    p.add_argument("--root", default=None)
    p.add_argument("--stale-days", type=int, default=7)
    p.add_argument("--soft", action="store_true", help="有 findings 也 exit 0")
    p.add_argument("--quiet-when-clean", action="store_true",
                   help="findings=0 时不打印任何内容（cron 静默成功用）")
    p.add_argument("--json", action="store_true")
    p.add_argument("--now", default=None, help="覆盖当前时间（ISO，测试用）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = resolve_root(args.root)
    if not (root / "任务台账.md").is_file():
        print(f"环境错误：找不到台账 {root / '任务台账.md'}", file=sys.stderr)
        return 2
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    findings = audit(root, args.stale_days, now)
    if args.json:
        print(json.dumps({"root": str(root), "findings": findings,
                          "stale_days": args.stale_days}, ensure_ascii=False, indent=2))
    elif not (args.quiet_when_clean and not findings):
        print(render(root, findings, args.stale_days))
    if findings and not args.soft:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
