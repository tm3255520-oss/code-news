#!/usr/bin/env python3
"""
make_slideshow_video.py - 图文TTS视频生产管线（🔵 确定性）

输入页面定义 JSON -> 生成白底大字幻灯片 PNG -> (可选)edge-tts 中文配音
-> ffmpeg 合成 720p30 视频。

页面定义 JSON 结构:
[
  {"text": "页大字", "sub": "副标题(可选)", "tts": "这句的旁白(可选)", "dur": 4.0},
  ...
]

用法:
  python make_slideshow_video.py slides.json -o out.mp4 [--voice zh-CN-XiaoxiaoNeural]
  # 无 edge-tts 时跳过配音（合成静音版，标注待配音）

依赖: pillow, ffmpeg；配音需 edge-tts（宿主机安装）。
"""
import sys
import os
import json
import argparse
import subprocess
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W, H = 1280, 720


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


def make_slide(text, sub, path, font_size=64, bg=(244, 246, 246), fg=(30, 30, 30)):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # 找中文字体
    font = None
    for cand in ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                 "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
                 "C:/Windows/Fonts/msyh.ttc",
                 "C:/Windows/Fonts/msyhbd.ttc",
                 "/System/Library/Fonts/PingFang.ttc"]:
        if os.path.exists(cand):
            try:
                font = ImageFont.truetype(cand, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    # 自动换行（按每行最多 12 字）
    lines = []
    cur = ""
    for ch in text:
        if len(cur) >= 12:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    total_h = len(lines) * (font_size + 12)
    y = (H - total_h) // 2
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=font, fill=fg)
        y += font_size + 12
    if sub:
        d.text((W // 2, H - 90), sub, anchor="mm", fill=(120, 120, 120))
    img.save(path)


def make_audio(page_idx, tts_text, voice, out_dir):
    """edge-tts 生成单页音频；失败返回 None。"""
    out = os.path.join(out_dir, f"a{page_idx:02d}.mp3")
    if os.path.exists(out):
        return out
    try:
        import asyncio
        import edge_tts
        async def gen():
            c = edge_tts.Communicate(tts_text, voice)
            await c.save(out)
        asyncio.run(gen())
        return out if os.path.exists(out) else None
    except Exception as e:
        log(f"  TTS 失败(页{page_idx}): {e}", "WARN")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages_json")
    ap.add_argument("-o", "--out", default="out.mp4")
    ap.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args()

    pages = json.load(open(args.pages_json, encoding="utf-8"))
    workdir = args.workdir or os.path.dirname(os.path.abspath(args.out))
    os.makedirs(workdir, exist_ok=True)
    log(f"页面数: {len(pages)}")

    # 1. 生成幻灯片 + 音频
    for i, p in enumerate(pages, 1):
        slide = os.path.join(workdir, f"s{i:02d}.png")
        make_slide(p.get("text", ""), p.get("sub", ""), slide)
        log(f"  幻灯片 s{i:02d}.png")
        if p.get("tts"):
            p["_audio"] = make_audio(i, p["tts"], args.voice, workdir)
            if p["_audio"]:
                log(f"    配音 a{i:02d}.mp3")

    # 2. ffmpeg 合成：每页图片 + 对应音频（或静音）按 dur 拼接
    have_tts = all(p.get("_audio") for p in pages if p.get("tts"))
    if not have_tts:
        log("部分/全部无配音，用静音占位（宿主机装 edge-tts 后可补）", "WARN")

    # 生成每页 clip
    segs = []
    for i, p in enumerate(pages, 1):
        slide = os.path.join(workdir, f"s{i:02d}.png")
        seg = os.path.join(workdir, f"seg{i:02d}.mp4")
        dur = p.get("dur", 4.0)
        if p.get("_audio"):
            adur = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", p["_audio"]],
                capture_output=True, text=True).stdout.strip()
            try:
                adur = float(adur)
            except Exception:
                adur = dur
            dur = max(dur, adur)
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", slide,
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-shortest",
             seg], capture_output=True, text=True, timeout=60)
        if p.get("_audio"):
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", seg, "-i", p["_audio"],
                 "-c:v", "copy", "-c:a", "aac", "-shortest", seg.replace(".mp4", "_a.mp4")],
                capture_output=True, text=True, timeout=60)
            seg = seg.replace(".mp4", "_a.mp4")
        segs.append(seg)

    # 3. concat
    concat_file = os.path.join(workdir, "concat.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{os.path.abspath(s)}'\n")
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_file, "-c", "copy", args.out], capture_output=True, text=True, timeout=120)
    if r.returncode == 0 and os.path.exists(args.out):
        log(f"✅ 视频 -> {args.out}")
    else:
        log(f"合成失败: {r.stderr[:200]}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
