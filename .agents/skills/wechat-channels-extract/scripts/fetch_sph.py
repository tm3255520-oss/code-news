#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频号链接内容提取 —— 拿元数据 + 封面。

用法:
    python fetch_sph.py https://weixin.qq.com/sph/AtdKRFoOZo
    python fetch_sph.py AtdKRFoOZo --outdir ./sph_out

产出:
    <outdir>/feedinfo.json   原始返回
    <outdir>/cover.jpg       封面（若存在）

注：视频本体拿不到（需微信客户端内播放）。封面通常信息量极大，务必读图。
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

API = "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info"
ORIGIN = "https://channels.weixin.qq.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")


def extract_id(raw: str) -> str:
    """从短链或纯 ID 里取出 shortUri。"""
    raw = raw.strip()
    m = re.search(r"/sph/([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", raw):
        return raw
    raise SystemExit(f"无法从输入中解析出视频号 ID: {raw!r}")


def fetch_feed_info(sid: str) -> dict:
    body = json.dumps({"baseReq": {"generalToken": ""}, "shortUri": sid}).encode()
    req = urllib.request.Request(
        API, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": ORIGIN,                       # 缺这个头会 401
            "Referer": f"{ORIGIN}/finder-preview/pages/sph?id={sid}",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", "replace")
        if "permission verification failed" in payload:
            raise SystemExit("401 权限校验失败 —— 检查是否带了 Origin 头。")
        raise SystemExit(f"HTTP {e.code}: {payload[:400]}")


def download(url: str, path: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": ORIGIN + "/"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="视频号短链或 ID")
    ap.add_argument("--outdir", default=".", help="输出目录（默认当前目录）")
    args = ap.parse_args()

    sid = extract_id(args.url)
    os.makedirs(args.outdir, exist_ok=True)
    print(f"[*] shortUri = {sid}")

    d = fetch_feed_info(sid)
    if d.get("errCode") != 0:
        raise SystemExit(f"接口报错: {json.dumps(d, ensure_ascii=False)[:400]}")

    with open(os.path.join(args.outdir, "feedinfo.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    data = d.get("data", {})
    fi = data.get("feedInfo", {}) or {}
    ai = data.get("authorInfo", {}) or {}

    print("\n===== 元数据 =====")
    print("作者    :", ai.get("nickname"))
    print("文案    :", (fi.get("description") or "").replace("\n", " / "))
    print("点赞/转发/收藏/评论:",
          fi.get("likeCountFmt"), "/", fi.get("forwardCountFmt"), "/",
          fi.get("favCountFmt"), "/", fi.get("commentCountFmt"))
    ct = fi.get("createtime")
    if ct:
        import datetime
        print("发布时间:", datetime.datetime.fromtimestamp(ct).strftime("%Y-%m-%d %H:%M"))

    cover = fi.get("coverUrl")
    if cover:
        p = os.path.join(args.outdir, "cover.jpg")
        n = download(cover, p)
        print(f"\n[+] 封面已下载: {p} ({n} 字节)")
        print("    封面里的界面截图很小，建议裁开放大再读：")
        print(f'    ffmpeg -y -i "{p}" -vf "crop=W:H:X:Y,scale=2000:-1:flags=lanczos" cover_crop.png')
    else:
        print("\n[-] 无 coverUrl")

    print("\n[i] 视频本体无法通过接口获取（需微信客户端内播放）。")
    print("    下一步：读封面图 + 用文案里的关键词去 GitHub/搜索引擎反查工具。")


if __name__ == "__main__":
    main()
