#!/usr/bin/env python3
"""
script_to_pages.py - 口播脚本 → 图文TTS视频页面定义（🔵 确定性）

读 article_to_script.py 产出的口播脚本 JSON，转成 make_slideshow_video.py 需要的 pages.json：
  [{"text": "页大字", "sub": "副标题", "tts": "该页旁白", "dur": 秒}]

规则：
- 每段口播 = 一页幻灯片；text 取该段前 18 字做大字；tts 用完整内容；dur 按 4 字/秒估算。
- --title-as-first：把 video_title 作为第一页（封面页）。

用法:
  python script_to_pages.py <口播脚本.json> [-o pages.json] [--title-as-first]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def dur_for(text: str) -> float:
    n = len(text)
    return max(3.0, round(n / 4.0, 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script_json", help="article_to_script 产出的口播脚本 JSON")
    ap.add_argument("-o", "--out", default="pages.json")
    ap.add_argument("--title-as-first", action="store_true", help="用 video_title 做第一页封面")
    args = ap.parse_args()

    data = json.loads(Path(args.script_json).read_text(encoding="utf-8"))
    segs = data["script"]["script"]
    pages = []
    for s in segs:
        content = (s.get("content") or "").strip()
        if not content:
            continue
        pages.append({
            "text": content[:18],
            "sub": "",
            "tts": content,
            "dur": dur_for(content),
        })

    if args.title_as_first:
        topic = data.get("topic") or {}
        title = (topic.get("video_title") or "").strip()
        if title:
            hook = (topic.get("hook_sentence") or "").strip()
            pages.insert(0, {
                "text": title[:14],
                "sub": hook[:20],
                "tts": title,
                "dur": 3.5,
            })

    out = Path(args.out)
    out.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(pages)} 页 -> {out}")
    for i, p in enumerate(pages):
        print(f"  [{i}] dur={p['dur']}s text={p['text'][:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
