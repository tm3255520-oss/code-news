#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""两条新路径尝试拿到抖音视频明文流地址：
   A) 移动端分享页 iesdouyin.com/share/video/<id>  —— 历史上该页给明文 <video src>
   B) 桌面页 performance.getEntriesByType('resource') —— MSE 分片 / aweme detail 接口
只读探测，不下载。输出 grab_stream.log
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WORK = Path(r"C:\Users\Administrator\WorkBuddy AI\内容工位\_过程稿\2026-09-16-抖音视频拆解")
VID = "7676834838926890405"


def bsk(args, timeout=90):
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        r = subprocess.run(["bsk"] + args, stdout=fo, stderr=fe,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        fo.seek(0)
        fe.seek(0)
        out = fo.read().decode("utf-8", "replace")
        err = fe.read().decode("utf-8", "replace")
    return out.strip(), err.strip(), r.returncode


L = []
def log(m):
    print(m, flush=True)
    L.append(str(m))


# 探测 JS：拿 video src + 资源条目里所有可疑地址 + SSR 全局键名
PROBE_JS = r"""
(() => {
  const vs = Array.from(document.querySelectorAll('video')).map(v => ({
    src: v.currentSrc || v.src || '', dur: v.duration || null,
    w: v.videoWidth || null, h: v.videoHeight || null
  }));
  const res = performance.getEntriesByType('resource').map(e => e.name);
  const hit = res.filter(u => /\.mp4|douyinvod|bytevod|aweme\/v1\/web\/aweme\/detail|play_addr|mime_type/i.test(u));
  const globals = Object.keys(window).filter(k => /_ROUTER_DATA|_SSR_DATA|__INITIAL|RENDER_DATA|_DATA/i.test(k));
  let ssrLen = 0, ssrKeys = [];
  try {
    const R = window._ROUTER_DATA || window._SSR_DATA;
    if (R) { ssrLen = JSON.stringify(R).length; ssrKeys = Object.keys(R); }
  } catch(e){}
  return JSON.stringify({
    href: location.href, title: document.title,
    videos: vs,
    resTotal: res.length,
    resHit: hit.slice(0, 40),
    globals: globals,
    ssrLen: ssrLen, ssrKeys: ssrKeys,
    // 全 HTML 里搜 mp4 / play_addr 关键字
    htmlMp4: (document.documentElement.outerHTML.match(/https?:[^"'\\\s]{0,180}(?:\.mp4|douyinvod|bytevod)[^"'\\\s]{0,120}/g) || []).slice(0, 20)
  }, null, 1);
})()
"""


def probe(tag, url):
    log(f"\n========== [{tag}] {url} ==========")
    out, err, rc = bsk(["session", "start"])
    m = re.search(r"\b([a-z]{4})\b", out)
    sid = m.group(1) if m else None
    log(f"[session] rc={rc} sid={sid} out={out[:120]!r}")
    if not sid:
        return
    try:
        o, e, r = bsk(["navigate", url, "--session", sid,
                       "--wait-until", "domcontentloaded", "--timeout", "40s"], timeout=120)
        log(f"[navigate] rc={r} err={e[:200]!r}")
        bsk(["wait-ms", "6000ms"], timeout=30)
        # 触发播放，逼 MSE 起流
        bsk(["evaluate",
             "(()=>{const vs=document.querySelectorAll('video');vs.forEach(v=>{try{v.muted=true;v.play();}catch(e){}});return vs.length;})()",
             "--session", sid], timeout=60)
        bsk(["wait-ms", "4000ms"], timeout=30)
        o, e, r = bsk(["evaluate", PROBE_JS, "--session", sid], timeout=90)
        log(f"[evaluate] rc={r} err={e[:200]!r}")
        log(o[:6000])
        (WORK / f"stream_{tag}.json").write_text(o, encoding="utf-8")
        p = WORK / f"stream_{tag}.png"
        try:
            bsk(["screenshot", "--session", sid, "--out", str(p)], timeout=90)
            log(f"[screenshot] exists={p.exists()}")
        except Exception as ex:
            log(f"[screenshot] fail {ex}")
    except Exception as ex:
        log(f"[!] {tag} 异常: {ex}")
    finally:
        bsk(["session", "stop", sid], timeout=30)
        log("[session stop]")


if __name__ == "__main__":
    probe("A_mobile", f"https://www.iesdouyin.com/share/video/{VID}/")
    probe("B_desktop", f"https://www.douyin.com/video/{VID}")
    (WORK / "grab_stream.log").write_text("\n".join(L), encoding="utf-8")
    print("\n[ok] log -> grab_stream.log", flush=True)
