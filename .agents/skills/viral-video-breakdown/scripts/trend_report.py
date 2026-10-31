#!/usr/bin/env python3
"""
trend_report.py - DSH 候选池趋势周报（🔵）

读 candidate_pool 目录下的历史快照（candidates_YYYYMMDD_HHMMSS.json，每天一个），
按日期聚合输出：候选数/总播放/高频作者/热点关键词，生成周报。

数据需积累（每日定时采集自动落盘），1-2 周后跑出趋势。

用法:
  python trend_report.py [--dir candidate_pool]
"""
import os
import re
import json
import glob
import argparse
import collections
from datetime import datetime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "research",
        "dsh-std-video-analysis", "candidate_pool"))
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "candidates_*.json")))
    if not files:
        print("无候选池快照"); return

    by_day = collections.OrderedDict()
    for f in files:
        m = re.search(r"candidates_(\d{8})_", os.path.basename(f))
        day = m.group(1) if m else "unknown"
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        day_entry = by_day.setdefault(day, {"count": 0, "total_play": 0, "authors": collections.Counter(),
                                             "kw": collections.Counter()})
        for c in data.get("candidates", []):
            day_entry["count"] += 1
            day_entry["total_play"] += c.get("view", 0)
            if c.get("author"):
                day_entry["authors"][c["author"]] += 1
            title = c.get("title", "")
            for kw in ["插件", "教程", "实测", "开源", "配置", "安装", "满血", "性能", "TUI", "Agent"]:
                if kw in title:
                    day_entry["kw"][kw] += 1

    print(f"=== DSH 候选池趋势（{len(by_day)} 天快照）===")
    for day, e in by_day.items():
        top_auth = ", ".join(a for a, _ in e["authors"].most_common(3))
        top_kw = ", ".join(k for k, _ in e["kw"].most_common(5))
        print(f"\n{day[:4]}-{day[4:6]}-{day[6:]}｜候选 {e['count']}｜总播放 {e['total_play']:,}")
        print(f"  高频作者: {top_auth or '无'}")
        print(f"  热点词: {top_kw or '无'}")

    # 首末对比（趋势）
    if len(by_day) >= 2:
        days = list(by_day)
        first, last = by_day[days[0]], by_day[days[-1]]
        print(f"\n=== 首末对比（{days[0]} vs {days[-1]}）===")
        print(f"候选数: {first['count']} -> {last['count']}")
        print(f"总播放: {first['total_play']:,} -> {last['total_play']:,}")
    else:
        print("\n数据不足（仅 1 天），继续每日定时采集积累后出趋势。")
    print("\n生成: 每日 09:34 定时采集自动落盘到 candidate_pool/。")


if __name__ == "__main__":
    main()
