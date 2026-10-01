#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_slideshow_video.py — 图文TTS横版视频合成（宿主机运行）

把 slides.json（页大字）+ voice_segmenter 生成的配音 mp3/srt 合成为 1280x720 横版视频：
  1. PIL 生成白底大字幻灯片 PNG（微软雅黑）
  2. 读 SRT 每段时长（voice_segmenter 实测，零误差）
  3. ffmpeg 每页 clip = PNG + 对应音频段 → concat 成品

用法:
    python compose_slideshow_video.py --slides slides.json \
        --voice-mp3 voice/voice_segmented.mp3 --voice-srt voice/voice_segmented.srt \
        --out 成品.mp4
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720


def ts_to_sec(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: str):
    """解析 SRT → [(start, end), ...]"""
    segs = []
    content = Path(path).read_text(encoding="utf-8")
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        m = re.search(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
        if m:
            segs.append((ts_to_sec(m.group(1)), ts_to_sec(m.group(2))))
    return segs


def load_font(size: int):
    for cand in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc",
                 "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"]:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_slide(text: str, sub: str, path: Path, font_size=64):
    img = Image.new("RGB", (W, H), (244, 246, 246))
    d = ImageDraw.Draw(img)
    font = load_font(font_size)
    # 自动换行，每行最多 12 字
    lines, cur = [], ""
    for ch in text:
        if len(cur) >= 12:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    total = len(lines) * (font_size + 14)
    y = (H - total) // 2
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=font)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=font, fill=(30, 30, 30))
        y += font_size + 14
    if sub:
        d.text((W // 2, H - 90), sub, anchor="mm", fill=(120, 120, 120))
    img.save(path)


def run(cmd, timeout=180):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  CMD FAIL:", " ".join(cmd)[:120], "|", (r.stderr or "")[:200])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", required=True)
    ap.add_argument("--voice-mp3", required=True)
    ap.add_argument("--voice-srt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args()

    slides = json.load(open(args.slides, encoding="utf-8"))
    segs = parse_srt(args.voice_srt)
    out = Path(args.out)
    work = Path(args.workdir) if args.workdir else out.parent
    work.mkdir(parents=True, exist_ok=True)

    n = min(len(slides), len(segs))
    print(f"幻灯片 {len(slides)} 页 / SRT {len(segs)} 段 → 合成 {n} 段")
    if n == 0:
        print("无匹配段，退出", file=sys.stderr); sys.exit(1)

    clips = []
    for i in range(n):
        png = work / f"s{i+1:02d}.png"
        make_slide(slides[i].get("text", ""), slides[i].get("sub", ""), png)
        start, end = segs[i]
        dur = max(end - start, 1.0)
        clip = work / f"clip{i+1:02d}.mp4"
        ok = run(["ffmpeg", "-y", "-loop", "1", "-i", str(png),
                  "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", args.voice_mp3,
                  "-map", "0:v", "-map", "1:a",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                  "-r", "30", "-c:a", "aac", "-b:a", "128k", "-shortest", str(clip)])
        if not ok:
            sys.exit(1)
        clips.append(clip)
        print(f"  [{i+1}/{n}] {slides[i].get('text','')[:18]} | {dur:.1f}s")

    # concat
    listf = work / "concat.txt"
    listf.write_text("\n".join(f"file '{c.resolve()}'" for c in clips), encoding="utf-8")
    ok = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
              "-c", "copy", str(out)])
    if ok:
        print(f"\n✅ 成品视频 -> {out}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
