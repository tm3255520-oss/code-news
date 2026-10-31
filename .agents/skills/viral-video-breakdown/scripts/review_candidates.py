#!/usr/bin/env python3
"""
review_candidates.py - 候选池每日评审（🔵）

读最新 candidates_*.json，按价值分层挑 Top N，输出"今日拆解队列"建议。

价值分层（来自校准结论）：
- 爆款候选：播放>=50000 且 收藏率>=3%
- 优质候选：收藏率>=6%（资料价值，即使播放中量）
- 观察候选：播放>=20000
输出：值得优先拆解的前 N 条。

用法:
  python review_candidates.py [--dir candidate_pool] [--top 5]
"""
import os
import json
import glob
import argparse


def latest_pool(pool_dir):
    files = sorted(glob.glob(os.path.join(pool_dir, "candidates_*.json")),
                   key=os.path.getmtime)
    return files[-1] if files else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "research",
        "dsh-std-video-analysis", "candidate_pool"))
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()

    f = latest_pool(args.dir)
    if not f:
        print("无候选池文件"); return
    data = json.load(open(f, encoding="utf-8"))
    cands = data.get("candidates", [])
    print(f"最新候选池: {os.path.basename(f)}｜{data.get('count', len(cands))} 条")

    def tier(c):
        play = c.get("view", 0)
        fr = c.get("fav_rate", 0)
        if play >= 50000 and fr >= 0.03:
            return 0, "爆款候选"
        if fr >= 0.06:
            return 1, "优质候选(高收藏率)"
        if play >= 20000:
            return 2, "观察候选"
        return 3, "普通"

    scored = [(tier(c), c) for c in cands]
    scored.sort(key=lambda x: (x[0][0], -x[1].get("view", 0)))
    picked = scored[:args.top]

    print(f"\n=== 今日拆解队列 Top{args.top} ===")
    for (lv, label), c in picked:
        print(f"\n[{label}] {c.get('title','')[:40]}")
        print(f"  播放{c.get('view',0):,} | 收藏率{c.get('fav_rate',0):.1%} | "
              f"投币率{c.get('coin_rate',0):.1%} | 作者{c.get('author','')} | "
              f"https://www.bilibili.com/video/{c.get('bvid')}")
    print("\n建议：优先拆「爆款候选/优质候选」；观察候选择机；普通候选一般跳过。")
    print("拆解：python scripts/run_breakdown.py <url> 或 Claude 处理 breakdown_queue。")


if __name__ == "__main__":
    main()
