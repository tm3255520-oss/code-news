#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/gzh_bsk_content_probe.py —— 公众号正文「浏览器通道」可行性探针。

上一支探针证明：纯 HTTP GET 会被微信风控跳到 `wappoc_appmsgcaptcha` 验证码页。
本探针验证 **bsk ＋ Chrome Profile 2 登录态** 能否拿到渲染后的正文。
只读、不落盘。

用法：python scripts/_probe/gzh_bsk_content_probe.py "<mp 文章 url>"
"""
import json
import re
import subprocess
import sys
import time

BSK_TIMEOUT = 120


def bsk(args, timeout=BSK_TIMEOUT):
    r = subprocess.run(["bsk"] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def main():
    url = sys.argv[1]
    st = bsk(["status"])
    print("bsk status: %s" % st[:200])
    if "browsers connected  0" in st:
        print("❌ 没有可用浏览器（Chrome Profile 2 未开）")
        return 2
    sid = bsk(["session", "start"])
    print("session=%s" % sid)
    try:
        out = bsk(["navigate", url, "--session", sid,
                   "--wait-until", "domcontentloaded", "--timeout", "45s"])
        print("navigate: %s" % out[:200])
        time.sleep(3)
        js = ("(()=>{const e=document.querySelector('#js_content')"
              "||document.querySelector('.rich_media_content');"
              "const t=(e?e.innerText:document.body.innerText)||'';"
              "return JSON.stringify({title:document.title,url:location.href,"
              "hasJs:!!document.querySelector('#js_content'),len:t.length,head:t.slice(0,120)})})()")
        raw = bsk(["evaluate", "--session", sid, js])
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            d = json.loads(raw[i:j + 1])
            print("title=%r" % d.get("title"))
            print("最终 URL=%s" % d.get("url"))
            print("#js_content 存在=%s ｜ 正文字数=%s" % (d.get("hasJs"), d.get("len")))
            print("开头：%s" % (d.get("head") or "").replace("\n", " ")[:110])
            n = int(d.get("len") or 0)
            print("=== %s ===" % ("✅ 浏览器通道可用" if n >= 300 else "⚠️ 仍拿不到正文"))
            if n < 300:
                # 深挖：等一等再读，并把「整页可见文本 + 风控特征」打出来
                for wait in (5, 12):
                    time.sleep(wait)
                    js2 = ("(()=>{const e=document.querySelector('#js_content');"
                           "const t=(e?e.innerText:document.body.innerText)||'';"
                           "return JSON.stringify({url:location.href,len:t.length,"
                           "bodyLen:(document.body.innerText||'').length,"
                           "captcha:/滑块|拖动|验证|环境异常|wappoc/.test(document.documentElement.outerHTML),"
                           "txt:(document.body.innerText||'').replace(/\\s+/g,' ').slice(0,300)})})()")
                    r2 = bsk(["evaluate", "--session", sid, js2])
                    a, b2 = r2.find("{"), r2.rfind("}")
                    if a >= 0 and b2 > a:
                        dd = json.loads(r2[a:b2 + 1])
                        print("  [+%ds] 正文=%s 整页可见=%s 风控特征=%s url=%s"
                              % (wait, dd.get("len"), dd.get("bodyLen"),
                                 dd.get("captcha"), (dd.get("url") or "")[:60]))
                        print("      页面文字：%s" % dd.get("txt"))
        else:
            print("evaluate 原始输出：%s" % raw[:400])
    finally:
        bsk(["session", "stop", sid])
    return 0


if __name__ == "__main__":
    sys.exit(main())
