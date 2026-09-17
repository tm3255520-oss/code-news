#!/usr/bin/env python3
"""
track_predictions.py - 爆款预测回测（🔵）

读 predictions.csv，用 B站 view API 刷新每条最新播放/收藏率，
按规则判定"实际是否成为爆款"，与拆解预测对比，输出准确率。

实际爆款判定（DSH 垂类近似）：play >= 50000 且 收藏率 >= 3%。

用法:
  python track_predictions.py [--csv predictions.csv] [--interval 2]
"""
import sys
import os
import csv
import time
import json
import argparse
import urllib.request
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

PLAY_THRESHOLD = 50000
FAV_RATE_THRESHOLD = 0.03


def get_stat(bvid, interval):
    time.sleep(interval)
    req = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers={"User-Agent": UA, "Referer": f"https://www.bilibili.com/video/{bvid}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if d.get("code") != 0 or not d.get("data"):
            return None
        s = d["data"]["stat"]
        return {"play": int(s.get("view") or 0), "fav": int(s.get("favorite") or 0)}
    except Exception as e:
        return {"_err": str(e)[:60]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "research",
        "dsh-std-video-analysis", "predictions.csv"))
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig")))
    log(f"加载预测 {len(rows)} 条: {args.csv}")

    results = []
    for r in rows:
        st = get_stat(r["bvid"], args.interval)
        if not st or "_err" in st:
            log(f"  {r['bvid']} 刷新失败: {st}", "WARN")
            results.append({**r, "current_play": "", "current_fav_rate": "",
                            "actual_viral": "?", "hit": ""})
            continue
        play = st["play"]
        fav_rate = round(st["fav"] / max(play, 1), 3)
        # 实际成功分三档：爆款 / 优质(高收藏率未爆) / 普通
        actual_viral = play >= PLAY_THRESHOLD and fav_rate >= FAV_RATE_THRESHOLD
        actual_quality = fav_rate >= 0.08  # 资料价值极高（即使播放未到量级）
        pred = r["预测值得复刻"]
        hit = ""
        if pred == "是":
            hit = "是" if (actual_viral or actual_quality) else "否"
        elif pred == "否":
            hit = "是" if not (actual_viral or actual_quality) else "否"
        else:  # 待数据
            hit = "观察"
        results.append({**r, "current_play": play, "current_fav_rate": fav_rate,
                        "actual_viral": "是" if actual_viral else "否", "hit": hit})
        log(f"  {r['bvid']} 播放{play} 收藏率{fav_rate} 实际爆={actual_viral} 命中={hit}")

    # 汇总
    scored = [x for x in results if x["hit"] in ("是", "否")]
    acc = sum(1 for x in scored if x["hit"] == "是") / len(scored) if scored else 0
    watch = [x for x in results if x["hit"] == "观察"]
    viral_now = sum(1 for x in scored if x["actual_viral"] == "是")

    print("\n=== 回测结果 ===")
    print(f"有效样本: {len(scored)}/{len(results)}（排除待数据 {len(watch)}）")
    print(f"当前已成爆款: {viral_now} 条")
    print(f"预测准确率（是/否 判断）: {acc:.0%}")
    print("\n命中明细:")
    for x in results:
        print(f"  [{x['hit']}] {x['bvid']} {x['title'][:24]} 播放{x['current_play']} 收藏率{x['current_fav_rate']} 实际爆={x['actual_viral']}")
    if watch:
        print(f"\n待观察 {len(watch)} 条（若转爆，说明拆解应升级为值得复刻）:")
        for x in watch:
            print(f"  {x['bvid']} {x['title'][:24]} 播放{x['current_play']} 收藏率{x['current_fav_rate']}")

    # 落盘
    ts = datetime.now().strftime("%Y%m%d")
    out = os.path.join(os.path.dirname(args.csv), f"回测_{ts}.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    log(f"回测明细 -> {out}")


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


if __name__ == "__main__":
    main()
