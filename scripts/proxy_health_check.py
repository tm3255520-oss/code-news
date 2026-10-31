#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proxy_health_check.py — 出网体检：区分"目标挂了"和"代理挂了"。

为什么需要它（2026-09-17 实战教训）：
  本机装了本地代理（HTTP(S)_PROXY=127.0.0.1:7897）。当天该代理上游故障时，
  走代理的域名（redfox.hk / google / github）在 **TLS 层被 RST**，而不走代理的
  国内站全部正常 —— 表面看像"redfox 挂了"，实际是代理挂了。
  两件事同时发生（redfox 被 RST + Edge 起不来），让取视频两条路径一起断，
  排查成本很高。本脚本把这件事变成一条命令：对每个目标分别测**直连**与**走代理**，
  一眼看出问题在目标还是在代理。

用法：
    python scripts/proxy_health_check.py                 # 默认目标集
    python scripts/proxy_health_check.py example.com https://redfox.hk
退出码：0 = 关键目标（redfox）至少有一条路径可用；1 = 全不可用。
"""
from __future__ import annotations

import os
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_TARGETS = [
    "https://redfox.hk/story/web/api/doc/platforms",   # 取视频路由依赖（关键）
    "https://www.douyin.com",
    "https://mp.weixin.qq.com",
    "https://www.bilibili.com",
    "https://example.com",                              # 典型"走代理"的境外站
    "https://github.com",
]


def probe(url: str, use_proxy: bool, timeout: int = 12) -> str:
    s = requests.Session()
    s.trust_env = use_proxy          # False = 完全忽略环境代理
    try:
        r = s.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        return f"HTTP {r.status_code}"
    except Exception as exc:
        name = type(exc).__name__
        detail = str(exc)
        for key in ("ConnectionResetError", "SSLError", "ConnectionError", "Timeout"):
            if key in detail or key == name:
                return f"{key}"
        return name


def main() -> int:
    targets = sys.argv[1:] or DEFAULT_TARGETS
    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "（未设置）"
    print(f"[出网体检] 环境代理 HTTPS_PROXY = {env_proxy}")
    print(f"{'目标':<46}{'直连':<22}{'走代理':<22}判定")
    redfox_ok = False
    for t in targets:
        direct, proxied = probe(t, False), probe(t, True)
        if "redfox" in t:
            redfox_ok = not direct.startswith(("ConnectionReset", "SSLError", "Connection"))
        if direct == proxied:
            verdict = "两条路径一致"
        elif direct.startswith("HTTP") and not proxied.startswith("HTTP"):
            verdict = "⚠️ 代理坏了（直连正常）"
        elif proxied.startswith("HTTP") and not direct.startswith("HTTP"):
            verdict = "直连被墙，需走代理"
        else:
            verdict = "两条都不通 → 目标侧问题"
        print(f"{t:<46}{direct:<22}{proxied:<22}{verdict}")
    print()
    if redfox_ok:
        print("结论：redfox 至少有一条可用路径 → 取视频的解析路由可用。")
    else:
        print("结论：redfox 两条路径都不通 → 取视频会降级到浏览器路由；"
              "若同时浏览器通道也不可用，则输入层全断。")
    return 0 if redfox_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
