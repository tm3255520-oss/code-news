#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/gzh_http_page_probe.py —— 看清「纯 HTTP 抓公众号正文」到底被喂了什么页。

只读、不落盘。用法：python scripts/_probe/gzh_http_page_probe.py "<mp 文章 url>"
"""
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def main():
    url = sys.argv[1]
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://mp.weixin.qq.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="ignore")
        print("HTTP %s ｜ %d 字节 ｜ 最终 URL: %s" % (r.status, len(html), r.geturl()))
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    print("title=%r" % (t.group(1).strip() if t else None))
    for pat in ("js_content", "rich_media_content", "weui-msg__title",
                "环境异常", "验证", "该内容已被发布者删除", "参数错误"):
        print("  含 %-24s : %s" % (pat, bool(re.search(pat, html))))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    print("可见文本前 400 字：\n%s" % text[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
