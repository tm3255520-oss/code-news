#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 stream_B_desktop.json / stream_A_mobile.json 里取到的明文 mp4 地址下载视频。
URL 带时间戳会过期，且需要 Referer 防盗链。输出 douyin_raw.mp4
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORK = Path(r"C:\Users\Administrator\WorkBuddy AI\内容工位\_过程稿\2026-09-16-抖音视频拆解")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")

# 从两个探测结果里收集候选 URL
cands = []
for name in ("stream_B_desktop.json", "stream_A_mobile.json"):
    p = WORK / name
    if not p.exists():
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    for v in data.get("videos", []):
        u = (v.get("src") or "").strip()
        if u.startswith("http") and "video_mp4" in u:
            cands.append((name, u))
    for u in data.get("htmlMp4", []) or []:
        if "douyinvod" in u and "media-audio" not in u:
            cands.append((name + ":html", u))

print(f"[i] 候选 {len(cands)} 条", flush=True)
env = {k: v for k, v in os.environ.items()
       if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}

ok = None
for i, (src, u) in enumerate(cands):
    out = WORK / f"raw_{i}.mp4"
    print(f"\n[{i}] ({src}) 尝试下载 {u[:110]}...", flush=True)
    r = subprocess.run(["curl", "-sS", "-L", "--noproxy", "*",
                        "-m", "120",
                        "-o", str(out),
                        "-H", f"Referer: https://www.douyin.com/",
                        "-H", f"User-Agent: {UA}",
                        "-w", "%{http_code} %{size_download}",
                        u], capture_output=True, text=True, env=env)
    print(f"    curl: rc={r.returncode} {r.stdout.strip()} err={r.stderr.strip()[:200]}", flush=True)
    if out.exists() and out.stat().st_size > 100_000:
        # ffprobe 验真
        pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height,duration,codec_name,nb_frames",
                             "-show_entries", "format=duration,bit_rate,format_name",
                             "-of", "default=nw=1", str(out)],
                            capture_output=True, text=True, env=env)
        print("    ffprobe:\n" + "\n".join("      " + x for x in pr.stdout.strip().splitlines()), flush=True)
        if "width" in pr.stdout and ok is None:
            ok = out
    else:
        sz = out.stat().st_size if out.exists() else 0
        print(f"    太小/失败 size={sz}", flush=True)

if ok:
    print(f"\n[OK] 有效视频 -> {ok} ({ok.stat().st_size/1e6:.2f} MB)", flush=True)
else:
    print("\n[FAIL] 没有下载到有效视频", flush=True)
    sys.exit(1)
