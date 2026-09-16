#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_check.py — 动效密度校验（产线第四道门）。

借自 anything2explainer（Vincentwei1021，1458 star）的 motion_check.py 判据，
按我们的模板重写：它的口径是 Remotion 1280x720、内容区 y110-630；
我们的是 1440x1080，内容区在 chrome 与字幕带之间，故裁切不同。

判据（可调）：静止帧占比 <= 40% 且 最长静止 <= 1.0s。
「静止帧」= 相邻采样帧在内容区的灰度平均绝对差 < THR。
裁切刻意排除页眉/页码/HUD/进度条/字幕带——那些是常驻层，它们的变化不算镜头在动。

【重要：判据只适用于 MG 形态，不要套到卡片形态】
实测标定（2026-09-16，10fps / THR 0.35 / 我们 1440x1080 的同一裁切）：
    我们旧版(卡片)     帧间均值 1.993  静止 0.0%   最长 0.00s
    我们新版(卡片)     帧间均值 0.545  静止 75.1%  最长 4.30s
    对标C(1.7万赞)     帧间均值 0.018  静止 98.7%  最长 6.90s
    对标D(3分半长片)   帧间均值 0.050  静止 99.2%  最长 104.60s
→ 两条高流量对标片的 99% 帧都判「静止」，却各有几万赞。卡片/幻灯片形态
  本来就是「入场后定住」，这条判据会误杀。故默认 --style card = 只报告不拦截；
  只有 MG 形态（每个字幕块都要有持续动作）才用 --style mg 真正当门。

用法:
    python scripts/motion_check.py <video> [--fps 10] [--thr 0.35] [--json]
退出码: 0 通过 / 3 未通过
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 内容区裁切（1440x1080 模板）：避开顶部 chrome 与底部字幕带/进度条
CROP_TOP = 150
CROP_BOTTOM = 860
CROP_LEFT = 60
CROP_RIGHT = 1380
SAMPLE_W = 320
SAMPLE_H = 180


def extract(video: Path, fps: float, out_dir: Path) -> list[Path]:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-vf", f"fps={fps}", "-q:v", "3", str(out_dir / "f_%05d.jpg")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("抽帧失败：" + (r.stderr or "")[:200])
    return sorted(out_dir.glob("f_*.jpg"))


def load(p: Path) -> np.ndarray:
    im = Image.open(p).convert("L")
    w, h = im.size
    a = np.asarray(im)
    sx, sy = w / float(SAMPLE_W), h / float(SAMPLE_H)
    y0, y1 = int(CROP_TOP / sy), int(CROP_BOTTOM / sy)
    x0, x1 = int(CROP_LEFT / sx), int(CROP_RIGHT / sx)
    crop = a[y0:y1, x0:x1]
    return np.asarray(Image.fromarray(crop).resize((SAMPLE_W, y1 - y0))).astype(np.int16)


def main() -> int:
    ap = argparse.ArgumentParser(description="动效密度校验")
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=10.0, help="采样帧率")
    ap.add_argument("--thr", type=float, default=0.35, help="静止判定阈值")
    ap.add_argument("--still-max", type=float, default=0.40, help="静止帧占比上限")
    ap.add_argument("--longest-max", type=float, default=1.0, help="最长静止秒数上限")
    ap.add_argument("--style", choices=["card", "mg"], default="card",
                    help="card=卡片/幻灯片形态：只报告不拦截；mg=持续动效形态：按判据拦截")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print("[fail] 找不到视频：" + str(video))
        return 2
    with tempfile.TemporaryDirectory(prefix="motion_check_") as td:
        frames = extract(video, args.fps, Path(td))
        if len(frames) < 6:
            print("[fail] 采样帧不足")
            return 2
        prev = load(frames[0])
        diffs = []
        for f in frames[1:]:
            cur = load(f)
            diffs.append(float(np.abs(cur - prev).mean()))
            prev = cur

    d = np.array(diffs)
    still = d < args.thr
    step = 1.0 / args.fps
    longest = 0.0
    run = 0.0
    for s in still:
        run = run + step if s else 0.0
        longest = max(longest, run)
    ratio = float(still.mean())
    within = ratio <= args.still_max and longest <= args.longest_max
    ok = within or args.style == "card"

    res = {
        "video": str(video),
        "seconds": round(len(frames) / args.fps, 2),
        "sampled_frames": len(frames),
        "threshold": args.thr,
        "still_ratio": round(ratio, 3),
        "longest_still_s": round(longest, 2),
        "diff_mean": round(float(d.mean()), 3),
        "diff_p10": round(float(np.percentile(d, 10)), 3),
        "style": args.style,
        "within_mg_limits": within,
        "verdict": ("pass" if within else ("advisory" if args.style == "card" else "fail")),
    }
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("内容区裁切 y%d-%d x%d-%d（已排除页眉/HUD/进度条/字幕带）"
              % (CROP_TOP, CROP_BOTTOM, CROP_LEFT, CROP_RIGHT))
        print("采样 %d 帧 / %ss @ %sfps" % (res["sampled_frames"], res["seconds"], args.fps))
        print("帧间变化 均值 %.3f  P10 %.3f  静止阈值 %.2f"
              % (res["diff_mean"], res["diff_p10"], args.thr))
        print("静止帧占比 %.1f%%  (上限 %.0f%%)" % (ratio * 100, args.still_max * 100))
        print("最长静止   %.2fs  (上限 %ss)" % (longest, args.longest_max))
        if within:
            print("在 MG 判据内（静止帧与最长静止都达标）")
        elif args.style == "mg":
            print("未通过：镜头存在「入场即停」")
        else:
            print("超出 MG 判据，但当前是卡片形态 —— 仅作报告，不拦截")
            print("（卡片形态「入场后定住」是正常的；对标 C/D 的静止率是 98.7% / 99.2%）")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
