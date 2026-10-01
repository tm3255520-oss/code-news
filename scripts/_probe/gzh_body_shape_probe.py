#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/gzh_body_shape_probe.py —— 判定「正文为空」是**通道问题**还是**文章本身无文字**。

上一支探针发现：浏览器能正常打开文章页（标题/公众号/日期都对、无风控），
但 `#js_content` 的 innerText 只有十几字 —— 高度怀疑这批文章是**纯图片/海报型**（正文只有 <img>）。
本探针读 `#js_content` 的 innerHTML：数图片数、看标签构成。只读、不落盘。

用法：python scripts/_probe/gzh_body_shape_probe.py "<url>" ["<url>" ...]
"""
import json
import subprocess
import sys
import time


def bsk(args, timeout=120):
    r = subprocess.run(["bsk"] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return ((r.stdout or "") + (r.stderr or "")).strip()


JS = ("(()=>{const e=document.querySelector('#js_content');"
      "const h=e?e.innerHTML:'';"
      "return JSON.stringify({title:document.title,htmlLen:h.length,"
      "imgs:(h.match(/<img/g)||[]).length,textLen:(e?e.innerText:'').length,"
      "tags:(h.match(/<([a-zA-Z0-9]+)/g)||[]).slice(0,25)})})()")


def main():
    urls = sys.argv[1:]
    sid = bsk(["session", "start"])
    try:
        for url in urls:
            bsk(["navigate", url, "--session", sid,
                 "--wait-until", "domcontentloaded", "--timeout", "45s"])
            time.sleep(3)
            raw = bsk(["evaluate", "--session", sid, JS])
            i, j = raw.find("{"), raw.rfind("}")
            if i < 0 or j <= i:
                print("· %s\n  ❌ evaluate 失败：%s\n" % (url[:60], raw[:150]))
                continue
            d = json.loads(raw[i:j + 1])
            verdict = ("纯图片/海报型（正文无文字）" if int(d.get("imgs") or 0) > 0
                       and int(d.get("textLen") or 0) < 300
                       else ("有文字正文" if int(d.get("textLen") or 0) >= 300 else "既无文字也无图？"))
            print("· %s" % (d.get("title") or "")[:44])
            print("  html=%d 字节 ｜ <img> %d 张 ｜ 文字 %s 字 → **%s**"
                  % (d.get("htmlLen"), d.get("imgs"), d.get("textLen"), verdict))
            print("  标签构成：%s\n" % ",".join(t for t in (d.get("tags") or [])[:18]))
    finally:
        bsk(["session", "stop", sid])
    return 0


if __name__ == "__main__":
    sys.exit(main())
