#!/usr/bin/env python3
"""
make_breakdown_queue.py - 生成"拆解队列"文件（🔵 确定性，无 LLM）

读最新候选池 candidates_*.json，按价值分层挑 TopN，写入 breakdown_queue.md。
队列是 S1→S2 的交接物：S2 拆解时消费该文件，已拆解的打 [x]。

价值分层（来自校准结论）：
- 爆款候选：播放>=50000 且 收藏率>=3%
- 优质候选：收藏率>=6%（资料价值，即使播放中量）
- 观察候选：播放>=20000

用法:
  python make_breakdown_queue.py [--dir candidate_pool] [--top 5] [--queue breakdown_queue.md]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_POOL = SCRIPT_DIR.parent.parent.parent.parent / "research" / "dsh-std-video-analysis" / "candidate_pool"
DEFAULT_QUEUE = SCRIPT_DIR.parent.parent.parent.parent / "research" / "dsh-std-video-analysis" / "breakdown_queue.md"


def latest_pool(pool_dir: Path):
    files = sorted(glob.glob(str(pool_dir / "candidates_*.json")), key=os.path.getmtime)
    return Path(files[-1]) if files else None


def tier(c: dict) -> tuple:
    play = c.get("view", 0)
    fr = c.get("fav_rate", 0)
    if play >= 50000 and fr >= 0.03:
        return 0, "爆款候选"
    if fr >= 0.06:
        return 1, "优质候选(高收藏率)"
    if play >= 20000:
        return 2, "观察候选"
    return 3, "普通"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_POOL))
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--queue", default=str(DEFAULT_QUEUE))
    args = ap.parse_args()

    pool_dir = Path(args.dir)
    f = latest_pool(pool_dir)
    if not f:
        print("无候选池文件")
        return 1
    data = json.loads(f.read_text(encoding="utf-8"))
    cands = data.get("candidates", [])

    scored = [(tier(c), c) for c in cands]
    scored.sort(key=lambda x: (x[0][0], -x[1].get("view", 0)))
    picked = scored[: args.top]

    queue = Path(args.queue)
    queue.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 拆解队列",
        "",
        f"> 生成时间: {now}",
        f"> 数据源: {f.name}（{data.get('count', len(cands))} 条候选）",
        f"> 队列条数: {len(picked)}",
        "",
        "## 待拆解",
        "",
    ]
    for (lv, label), c in picked:
        title = (c.get("title") or "").replace("|", "｜")
        lines.append(
            f"- [ ] **[{label}]** {title}  "
            f"(播放{c.get('view', 0):,} | 收藏率{c.get('fav_rate', 0):.1%} | "
            f"作者{c.get('author', '')})  "
            f"https://www.bilibili.com/video/{c.get('bvid')}"
        )
    lines += [
        "",
        "## 说明",
        "",
        "- 每拆解一条，把该行 `[ ]` 改 `[x]` 并追加到下方「已完成」。",
        "- 优先级：爆款候选/优质候选优先；观察候选择机；普通候选一般跳过。",
        "- 拆解：`python scripts/run_breakdown.py <url>` 或让 Claude 按队列处理。",
        "",
        "## 已完成",
        "",
    ]
    queue.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: 已写入拆解队列 {queue}")
    for (lv, label), c in picked:
        print(f"  [{label}] {c.get('bvid')} {c.get('title','')[:30]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
