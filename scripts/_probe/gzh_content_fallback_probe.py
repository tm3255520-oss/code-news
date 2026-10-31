#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/gzh_content_fallback_probe.py —— 公众号正文「替代通道」可行性探针。

背景：`gzh_creator_collect.py` 走 RedFox `gzhData/queryWork` 取正文，实测部分文章
`content` 恒为空串（不是网络/参数问题）。本探针验证**替代通道**能否补上：
  通道 A：纯 HTTP GET `mp.weixin.qq.com/s/...`（复用 `gzh_download.fetch_article` 的抽取法）
  通道 B：同上但换更稳的抽取（js_content / rich_media_content / og:description 兜底）

只读：不写 vault、不落盘。用法：
  python scripts/_probe/gzh_content_fallback_probe.py [最多测几篇，默认 4]
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\.hermes\scripts")

TRACKER = Path(r"D:\Obsidian Vault\obsidian Vault\运营中心\.state\collection_tracker.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def strip_tags(h: str) -> str:
    for close in ("</p>", "</h1>", "</h2>", "</h3>", "</h4>", "</li>",
                  "</blockquote>", "</div>", "</figure>", "</pre>"):
        h = h.replace(close, "\n")
    for br in ("<br/>", "<br />", "<br>"):
        h = h.replace(br, "\n")
    h = re.sub(r"<script[^>]*>.*?</script>", "", h, flags=re.S)
    h = re.sub(r"<style[^>]*>.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<[^>]+>", "", h)
    h = (h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
         .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    return re.sub(r"\n{3,}", "\n\n", h).strip()


def extract(html: str):
    """返回 (正文, 用了哪条规则)。"""
    m = re.search(r'id="js_content"[^>]*>(.*?)</div>\s*(?:<script|<div id="js_)', html, re.S)
    if m and len(strip_tags(m.group(1))) > 200:
        return strip_tags(m.group(1)), "js_content"
    m = re.search(r'class="rich_media_content[^"]*"[^>]*>(.*?)</div>\s*<script', html, re.S)
    if m and len(strip_tags(m.group(1))) > 200:
        return strip_tags(m.group(1)), "rich_media_content"
    m = re.search(r'var msg_desc\s*=\s*"(.*?)";', html, re.S)
    if m:
        return m.group(1), "msg_desc(兜底·非全文)"
    return "", "无"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    d = json.loads(TRACKER.read_text(encoding="utf-8"))
    rows = [(k, v) for k, v in (d.get("entries") or {}).items()
            if (v or {}).get("platform") == "wechat"
            and (v or {}).get("status") == "skipped_no_content"]
    print("台账里 skipped_no_content 的公众号条目：%d 条，测前 %d 条\n" % (len(rows), limit))
    ok = 0
    for uid, v in rows[:limit]:
        url = v.get("url") or ""
        print("· %s" % (v.get("title") or "")[:40])
        print("  url=%s" % url)
        if not url.startswith("http"):
            print("  ❌ 无可用链接\n")
            continue
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://mp.weixin.qq.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            print("  ❌ 请求失败：%s\n" % str(exc)[:100])
            continue
        body, how = extract(html)
        n = len(re.sub(r"\s", "", body))
        flag = "✅" if n >= 300 else "⚠️"
        print("  %s HTML %d 字节 → 正文 %d 字（规则=%s）" % (flag, len(html), n, how))
        if n >= 300:
            ok += 1
            print("     开头：%s" % body[:70].replace("\n", " "))
        print()
    print("=== 结论：%d/%d 可用替代通道拿到正文 ===" % (ok, min(limit, len(rows))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
