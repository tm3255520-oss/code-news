#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_to_channels.py — 视频号发布 wrapper（宿主机运行）

读取 publish_config.json（标题/描述外置，避免 .bat 中文编码问题），
调用 Hermes 现成 publish_channels.py 上传成品视频到视频号草稿箱（--save-only）。

安全：默认只保存到草稿箱，不直接发布；人工确认后在 channels.weixin.qq.com 点击发布。

用法:
    python publish_to_channels.py [--config <publish_config.json>]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERMES_PY = r"C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe"
PUBLISH_CHANNELS = r"C:\Users\Administrator\.hermes\scripts\publish_channels.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=r"C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\dsh-video-prod\publish_config.json")
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    video = cfg["video"]
    title = cfg["title"]
    desc = cfg.get("desc", "")
    topics = cfg.get("topics", "")
    save_only = cfg.get("save_only", True)

    # 标题 6-50 字硬校验（publish_channels v4.1 规则）
    if not (6 <= len(title) <= 50):
        print(f"标题长度 {len(title)} 需在 6-50 字之间，当前: {title}", file=sys.stderr)
        sys.exit(1)

    cmd = [HERMES_PY, PUBLISH_CHANNELS, "--publish", video, "--title", title]
    if desc:
        cmd += ["--desc", desc]
    if topics:
        cmd += ["--topics", topics]
    if save_only:
        cmd.append("--save-only")

    print("执行视频号上传（保存草稿箱）:")
    print("  video:", video)
    print("  title:", title)
    print("  模式:", "保存草稿(人工确认后发布)" if save_only else "直接发布")
    print()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print("STDERR:", (r.stderr or "")[-1000:], file=sys.stderr)
        sys.exit(r.returncode)
    print("✅ 已上传视频号草稿箱。请在 channels.weixin.qq.com 草稿箱确认后点击发布。")


if __name__ == "__main__":
    main()
