#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""motion_check.py — 动效密度校验（产线第四道门）。

借自 anything2explainer（Vincentwei1021，1458 star）的 motion_check.py 判据，
按我们的模板重写：它的口径是 Remotion 1280x720、内容区 y110-630。

判据（可调）：静止帧占比 <= 40% 且 最长静止 <= 1.0s。
「静止帧」= 相邻采样帧在**内容区**的灰度平均绝对差 < THR。
内容区 = `.card-inner`（kicker/标题/信息块所在的那一盒），刻意排除
页眉/页码/HUD/进度条/字幕带——那些是常驻层，它们的变化不算镜头在动。

【内容区随画幅变化，裁切框必须跟着走】
    landscape 1440x1080  x 72-1368  y 150- 818
    vertical  1080x1920  x 58-1022  y 126-1482
数值来源（改版面必须同步这里，不要手改像素）：
    build_card_deck.STYLES["grid-dark"]["card_inset"]         → 横屏
    build_card_deck.FORMATS["vertical"]["geom"]["card_inset"] → 竖屏
    card_inset = (left, top, right, bottom)
tests/scripts/test_motion_check_crop.py 会在两者漂移时报错。
成片分辨率不在表内时**不出结论**（退出码 2），而不是拿错框硬算一个数。

【2026-09-16 修正：此前采样实现有错，旧标定全部作废】
旧实现把「内容区原图像素」先除以缩略图比例，再拿去切**原图数组**，
等价于只采样了原图左上角一条窄带（横屏实测 x13-306 / y25-143），
根本不是文档写的内容区。修正前后同一条横屏基准：
        旧实现  静止率 0.888   帧间均值 0.559
        修正后  静止率 0.303   帧间均值 1.163
→ 旧标定（「我们新版静止率 75.1%」「对标 C 98.7% / D 99.2%」）**不可比、已作废**，
  需要按新实现重测。特别地：「卡片形态静止率高是正常的」这个结论是旧裁切的产物，
  修正后我们的卡片片只有 30.3% 静止，反而落在 MG 判据（<=40%）之内。
  2026-09-17 对照（video-line/quality/对照-2026-09-17-裁切修正.md）后定调：
  修后三条片子**各违反不同的一项**（基准：静止率合格、最长静止超标；demo 反过来），
  说明 MG 那对阈值（借自 Remotion 动效项目）在形状上不适配卡片形态。
  故 --style card 继续只报告，但依据改为「卡片形态尚无自有判据」——
  门槛要从自检线积累的分布里标定，不再借 MG 的数。

用法:
    python scripts/motion_check.py <video> [--fps 10] [--thr 0.35] [--json]
                                   [--format landscape|vertical]
退出码: 0 通过 / 2 输入或画幅不受支持 / 3 未通过
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

# 内容区（.card-inner）矩形 + 它所属的画布尺寸。见模块头「数值来源」。
CONTENT_RECTS: dict[str, dict] = {
    "landscape": {"canvas": (1440, 1080), "rect": (72, 150, 1368, 818)},
    "vertical": {"canvas": (1080, 1920), "rect": (58, 126, 1022, 1482)},
}
SAMPLE_W = 320


def detect_format(size: tuple[int, int]) -> str | None:
    for name, spec in CONTENT_RECTS.items():
        if tuple(spec["canvas"]) == tuple(size):
            return name
    return None


def extract(video: Path, fps: float, out_dir: Path) -> list[Path]:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-vf", f"fps={fps}", "-q:v", "3", str(out_dir / "f_%05d.jpg")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("抽帧失败：" + (r.stderr or "")[:200])
    return sorted(out_dir.glob("f_*.jpg"))


def load(path: Path, rect: tuple[int, int, int, int]) -> np.ndarray:
    """按内容区矩形**在原图像素上**裁，再等比缩到 SAMPLE_W 宽。

    旧实现在这里用缩略图坐标去切原图，只采到左上角一条窄带（见模块头）。
    """
    im = Image.open(path).convert("L")
    a = np.asarray(im)
    left, top, right, bottom = rect
    crop = a[top:bottom, left:right]
    if crop.size == 0:
        raise RuntimeError("内容区裁切为空：%s" % (rect,))
    h = max(1, round(SAMPLE_W * (bottom - top) / float(right - left)))
    return np.asarray(Image.fromarray(crop).resize((SAMPLE_W, h))).astype(np.int16)


def still_runs(diffs, fps: float, thr: float) -> list[list[float]]:
    """把「静止」帧段并成 [[起, 止], ...]（秒）。消费方据此把死区映射到具体卡片。"""
    step = 1.0 / fps
    runs: list[list[float]] = []
    start = None
    for i, v in enumerate(diffs):
        if v < thr:
            if start is None:
                start = i
        elif start is not None:
            runs.append([round(start * step, 2), round(i * step, 2)])
            start = None
    if start is not None:
        runs.append([round(start * step, 2), round(len(diffs) * step, 2)])
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description="动效密度校验")
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=10.0, help="采样帧率")
    ap.add_argument("--thr", type=float, default=0.35, help="静止判定阈值")
    ap.add_argument("--still-max", type=float, default=0.40, help="静止帧占比上限")
    ap.add_argument("--longest-max", type=float, default=1.0, help="最长静止秒数上限")
    ap.add_argument("--format", choices=sorted(CONTENT_RECTS), default=None,
                    help="画幅；默认按成片分辨率自动识别")
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

        size = Image.open(frames[0]).size
        fmt = args.format or detect_format(size)
        if fmt is None or fmt not in CONTENT_RECTS:
            known = "、".join("%s %dx%d" % (k, v["canvas"][0], v["canvas"][1])
                              for k, v in CONTENT_RECTS.items())
            print("[fail] 不支持的分辨率 %dx%d —— 内容区裁切框未知，不能硬算。" % size)
            print("       已知画幅：%s" % known)
            print("       新画幅要先在 build_card_deck 定几何，再把内容区补进 CONTENT_RECTS。")
            return 2
        if args.format and tuple(CONTENT_RECTS[fmt]["canvas"]) != tuple(size):
            print("[fail] --format %s 声明画布 %s，与实测 %dx%d 不符 —— 用错框算出的数没有意义。"
                  % (fmt, CONTENT_RECTS[fmt]["canvas"], size[0], size[1]))
            print("       要么去掉 --format 让它按分辨率自动识别，要么确认成片分辨率。")
            return 2

        rect = tuple(CONTENT_RECTS[fmt]["rect"])
        prev = load(frames[0], rect)
        diffs = []
        for f in frames[1:]:
            cur = load(f, rect)
            diffs.append(float(np.abs(cur - prev).mean()))
            prev = cur

    d = np.array(diffs)
    still = d < args.thr
    step = 1.0 / args.fps
    longest = 0.0
    run = 0.0
    run_start = 0.0
    longest_span = (0.0, 0.0)
    for i, s in enumerate(still):
        if s:
            if run == 0.0:
                run_start = i * step
            run += step
            if run > longest:
                longest = run
                longest_span = (round(run_start, 2), round((i + 1) * step, 2))
        else:
            run = 0.0
    ratio = float(still.mean())
    runs = still_runs(diffs, args.fps, args.thr)
    within = ratio <= args.still_max and longest <= args.longest_max
    ok = within or args.style == "card"

    res = {
        "video": str(video),
        "format": fmt,
        "canvas": list(size),
        "content_rect": list(rect),
        "seconds": round(len(frames) / args.fps, 2),
        "sampled_frames": len(frames),
        "threshold": args.thr,
        "still_ratio": round(ratio, 3),
        "longest_still_s": round(longest, 2),
        "longest_still_from_s": longest_span[0],
        "longest_still_to_s": longest_span[1],
        "still_runs": runs,
        "diff_mean": round(float(d.mean()), 3),
        "diff_p10": round(float(np.percentile(d, 10)), 3),
        "style": args.style,
        "within_mg_limits": within,
        "verdict": ("pass" if within else ("advisory" if args.style == "card" else "fail")),
    }
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("画幅 %s %dx%d｜内容区裁切 x%d-%d y%d-%d（已排除页眉/HUD/进度条/字幕带）"
              % (fmt, size[0], size[1], rect[0], rect[2], rect[1], rect[3]))
        print("采样 %d 帧 / %ss @ %sfps" % (res["sampled_frames"], res["seconds"], args.fps))
        print("帧间变化 均值 %.3f  P10 %.3f  静止阈值 %.2f"
              % (res["diff_mean"], res["diff_p10"], args.thr))
        print("静止帧占比 %.1f%%  (上限 %.0f%%)" % (ratio * 100, args.still_max * 100))
        print("最长静止   %.2fs  (上限 %ss)" % (longest, args.longest_max))
        if longest > 0:
            print("           位置 %.2f–%.2fs（这一段帧间变化恒低于阈值）"
                  % longest_span)
        if within:
            print("在 MG 判据内（静止帧与最长静止都达标）")
        elif args.style == "mg":
            print("未通过：镜头存在「入场即停」")
        else:
            print("超出 MG 判据，但当前是卡片形态 —— 仅作报告，不拦截")
            print("（卡片形态尚无自有判据：MG 的 40%/1.0s 借自动效项目，与本形态不同形；")
            print("  门槛需从自检线积累的分布里标定 —— 见 video-line/quality/README.md）")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
