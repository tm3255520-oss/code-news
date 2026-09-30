#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff_append.py — 收工三写（台账 + 交接块 + 会话索引），确定性零 LLM。

对应 vault `系统中枢/规则与权限/智能体共享/05-记忆协议.md` §六.2：
    ① 改台账自己那行 ② 追加交接块 ③ 追加会话索引一行。

用法：
    python handoff_append.py --task WK-20260930-01 --agent dsh --status 进行中 \\
        --did "写完第 1 版深度文（3200 字），审查未过" \\
        --evidence "内容生产/4-成品与审查/2026-09-30-review2.md（缺 2 处来源）" \\
        --files "内容生产/3-草稿与创作/2026-09-30-gpt5.md" \\
        --open "Sora 2 时长口径不一致" --next "补 2 处一手来源 → 复审" \\
        --handler "codex（handoff）" --session-id 9f3c --transcript-ref ~/.dsh/sessions/x

    python handoff_append.py ... --create --title "同题短视频改编" --platform 抖音·口播
    python handoff_append.py ... --dry-run          # 只打印将要写入什么
    python handoff_append.py ... --force --force-reason "接手 codex 未完成的稿子"

退出码：
    0  成功（含幂等跳过重复块）
    1  用法 / 数据错误（含疑似密钥、状态非法）
    2  守卫拒绝（台账无此任务且未 --create；或要改他人负责的行且未 --force）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xietong_lib import (  # noqa: E402
    BLOCK_FIELDS, STATUSES, TASK_ID_RE, Block, Task, append_handoff_block, append_index,
    append_ledger_row, contains_secret, handoff_path, index_path, parse_ledger,
    resolve_root, update_ledger_row,
)

PLACEHOLDER = "—"


def one_line(text: str, field: str) -> str:
    cleaned = " ".join((text or "").split())
    if "\n" in (text or ""):
        print(f"[!] {field} 里的换行已压成空格（交接块是一行一字段）", file=sys.stderr)
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="收工三写：台账 / 交接块 / 会话索引")
    p.add_argument("--task", required=True, help="任务ID，如 WK-20260930-01")
    p.add_argument("--agent", required=True, help="写交接的 Agent（claude-code/codex/dsh/hermes/workbuddy/openclaw）")
    p.add_argument("--status", required=True, choices=STATUSES, help="任务状态")
    p.add_argument("--did", required=True, help="本轮做了什么（一句话结果）")
    p.add_argument("--evidence", required=True, help="证据（路径 / 命令+退出码）")
    p.add_argument("--files", default="", help="动了哪些文件（逗号分隔）")
    p.add_argument("--open", dest="open_q", default="无", help="未决问题（默认「无」）")
    p.add_argument("--next", dest="next_step", default="", help="下一步（谁做什么）")
    p.add_argument("--handler", default="", help="建议接手方 + 该调的 skill")
    p.add_argument("--summary", default="", help="会话索引摘要（默认取 --did）")
    p.add_argument("--session-id", default=PLACEHOLDER, help="原生会话 ID")
    p.add_argument("--transcript-ref", default=PLACEHOLDER, help="原生会话文件路径（指针）")
    p.add_argument("--title", default="", help="台账标题（--create 时必填）")
    p.add_argument("--platform", default="", help="平台/形态（--create 时必填）")
    p.add_argument("--create", action="store_true", help="台账无此任务时新建一行（认领）")
    p.add_argument("--force", action="store_true", help="允许改动他人负责的台账行")
    p.add_argument("--force-reason", default="", help="--force 的原因（会写进变更记录）")
    p.add_argument("--root", default=None, help="协同根目录（默认自动解析）")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不写任何文件")
    p.add_argument("--now", default=None, help="覆盖时间戳（ISO，测试用）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not TASK_ID_RE.match(args.task):
        print(f"错误：任务ID 格式应为 WK-YYYYMMDD-NN，收到 {args.task!r}", file=sys.stderr)
        return 1
    payload_text = " ".join([args.did, args.evidence, args.files, args.open_q,
                             args.next_step, args.handler, args.summary])
    if contains_secret(payload_text):
        print("错误：内容疑似含密钥/token，按 05-记忆协议 §二.3 拒绝写入 vault", file=sys.stderr)
        return 1
    if args.force and not args.force_reason:
        print("错误：--force 必须同时给 --force-reason", file=sys.stderr)
        return 1

    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    updated = now.strftime("%Y-%m-%d %H:%M")
    root = resolve_root(args.root)

    ledger_file = root / "任务台账.md"
    led = parse_ledger(ledger_file)
    if not ledger_file.is_file():
        print(f"错误：台账不存在：{ledger_file}", file=sys.stderr)
        return 1

    task = led.by_id(args.task)
    created = False
    if task is None:
        if not args.create:
            print(f"守卫拒绝：台账里没有 {args.task}。先认领再动手——"
                  f"加 --create --title ... --platform ... 建行，或先手工补台账行。", file=sys.stderr)
            return 2
        if not args.title or not args.platform:
            print("错误：--create 需要 --title 与 --platform", file=sys.stderr)
            return 1
        task = Task(task_id=args.task, title=one_line(args.title, "title"),
                    platform=one_line(args.platform, "platform"), owner=args.agent,
                    status=args.status, updated=updated,
                    artifact=one_line(args.files, "files") or PLACEHOLDER,
                    link=f"协同/交接/{args.task}.md")
        created = True
    else:
        owner = task.owner.strip()
        if owner not in ("", PLACEHOLDER, args.agent) and owner != "待认领" and not args.force:
            print(f"守卫拒绝：{args.task} 的负责人是 {owner}，不是 {args.agent}。"
                  f"要接手请加 --force --force-reason \"<原因>\"（会写进台账变更记录）。", file=sys.stderr)
            return 2

    block = Block(ts=stamp, agent=args.agent, task_id=args.task, fields={
        "本轮做了什么": one_line(args.did, "did"),
        "动了哪些文件": one_line(args.files, "files") or PLACEHOLDER,
        "证据": one_line(args.evidence, "evidence"),
        "未决问题": one_line(args.open_q, "open") or "无",
        "下一步": one_line(args.next_step, "next") or "无",
        "建议接手方 + 该调的 skill": one_line(args.handler, "handler") or PLACEHOLDER,
        "状态": args.status,
    }, line_no=0)

    record = {
        "agent": args.agent,
        "session_id": one_line(args.session_id, "session-id") or PLACEHOLDER,
        "ts": stamp,
        "task": args.task,
        "title": one_line(args.title or (task.title if task else ""), "title"),
        "summary": one_line(args.summary or args.did, "summary")[:200],
        "artifacts": [p.strip() for p in re.split(r"[,，]", args.files) if p.strip()],
        "transcript_ref": one_line(args.transcript_ref, "transcript-ref") or PLACEHOLDER,
        "outcome": args.status,
    }

    hpath = handoff_path(root, args.task)
    ipath = index_path(root, args.agent)
    ledger_action = "新建行" if created else f"更新 L{task.line_no} 行"
    if created:
        if args.dry_run:
            print(f"[dry-run] 台账：追加一行 {task.render()}")
        else:
            append_ledger_row(led, task)
    else:
        task.status = args.status
        task.updated = updated
        if args.files:
            task.artifact = one_line(args.files, "files")
        task.link = f"协同/交接/{args.task}.md"
        if args.dry_run:
            print(f"[dry-run] 台账：{ledger_action} -> {task.render()}")
        else:
            update_ledger_row(led, task, force=args.force, force_reason=args.force_reason,
                              change_log=args.agent)

    if args.dry_run:
        print(f"[dry-run] 交接：追加到 {hpath}")
        print(block.render())
        print(f"[dry-run] 会话索引：追加一行到 {ipath}")
        print(json.dumps(record, ensure_ascii=False))
        print("\n[dry-run] 未写入任何文件。")
        return 0

    hpath, h_written = append_handoff_block(root, block, task.title)
    ipath, i_written = append_index(root, record)

    print(f"台账：{ledger_action}（{args.task}，状态={args.status}，更新={updated}）")
    if args.force:
        print(f"台账变更记录：已留痕（{args.force_reason}）")
    print(f"交接：{'已追加' if h_written else '已存在同时间块，跳过'} → {hpath}")
    print(f"会话索引：{'已追加' if i_written else '已存在同 key，跳过'} → {ipath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
