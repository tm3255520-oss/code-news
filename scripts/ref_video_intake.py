#!/usr/bin/env python3
"""ref_video_intake.py — 对标视频库「丢链接 → 自动入库命名」。

把一条视频链接（或整段分享文案）变成库里的一条样本：
    <库>/<平台>/YYYY-MM-DD-<标题>-<作品号>.mp4   (+ 同名 .meta.json)

库位置：D:\\Obsidian Vault\\obsidian Vault\\内容生产\\2-调研与素材\\素材与资源\\对标视频库
（定位与纪律见该库 `_说明.md`）

用法：
    python scripts/ref_video_intake.py "<链接或整段分享文案>"
    python scripts/ref_video_intake.py "<链接>" --title "自定义标题"
    python scripts/ref_video_intake.py "<链接>" --dry-run

复用（不新造轮子）：
    - 下载：scripts/fetch_video_with_browser.py（redfox 通用解析优先；浏览器 + yt-dlp 兜底）
    - 平台识别 / 作品号 / 命名口径 沿用 .hermes/scripts/video_collect.py 的同类实现
      （此处内联而非 import：避免为一个轻量入库工具拉进 whisper / bsk / vault_paths 重依赖）

标题解析顺序（逐级降级）：--title > 分享文案里的文案 > yt-dlp > redfox > 仅作品号。
抖音标题三处都取不到（网页端 JS 渲染、yt-dlp 要 fresh cookies、分享页是验证码），
**贴分享文案是最可靠的自动路径**；只贴纯链接时可能只剩下作品号，标题事后可手改文件名。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS = Path(__file__).resolve().parent
FETCH = SCRIPTS / "fetch_video_with_browser.py"
LIB_ROOT = Path(r"D:\Obsidian Vault\obsidian Vault\内容生产\2-调研与素材\素材与资源\对标视频库")

# 平台 slug → (库内中文目录, slug)
PLATFORMS = {
    "douyin": ("抖音", "douyin"),
    "bilibili": ("B站", "bilibili"),
    "xiaohongshu": ("小红书", "xiaohongshu"),
    "shipinhao": ("视频号", "shipinhao"),
    "toutiao": ("头条", "toutiao"),
    "kuaishou": ("快手", "kuaishou"),
    "zhihu": ("知乎", "zhihu"),
}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MEDIA_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4a")


def extract_url(text: str) -> str:
    """从整段分享文案里抠出第一条链接。"""
    m = re.search(r"https?://[^\s，。；、）)】\]]+", text or "")
    return m.group(0).rstrip("/") if m else ""


def detect_platform(url: str) -> str:
    u = (url or "").lower()
    if "douyin.com" in u:
        return "douyin"
    if "bilibili.com" in u or "b23.tv" in u:
        return "bilibili"
    if "xiaohongshu.com" in u or "xhslink.com" in u:
        return "xiaohongshu"
    if ("weixin.qq.com" in u or "channels.weixin" in u
            or "finder.video.qq.com" in u or "sph" in u):
        return "shipinhao"
    if "toutiao.com" in u or "ixigua.com" in u:
        return "toutiao"
    if "kuaishou.com" in u:
        return "kuaishou"
    if "zhihu.com" in u:
        return "zhihu"
    return ""


def resolve_url(url: str) -> str:
    """跟随短链跳转，拿到含作品号的长链。"""
    if not url:
        return url
    try:
        import requests
        s = requests.Session()
        s.trust_env = False
        r = s.get(url, headers={"User-Agent": UA}, allow_redirects=True, timeout=30)
        return r.url or url
    except Exception:
        return url


def extract_work_id(url: str) -> str:
    """作品号（去重主键）：抖音 /video/<19位>、B站 /video/BVxxx、小红书 /explore|<item>/<hex>。"""
    m = (re.search(r"/video/(\d{10,25})", url)
         or re.search(r"/video/(BV[0-9A-Za-z]{8,14})", url)
         or re.search(r"/(?:explore|item|note|discovery/item)/([0-9a-fA-F]{16,32})", url)
         or re.search(r"[?&](?:aweme_id|item_id|vid)=([0-9A-Za-z]{8,32})", url))
    return m.group(1) if m else ""


def caption_from_share(text: str, url: str) -> str:
    """抖音等分享文案：文案在链接之前，且分享码是 ASCII —— 从第一个汉字起截。

    抖音的话题标签（`# 话题`）通常挂在正文尾巴上，会把文件名弄脏；
    正文够长（≥6 字）就切掉第一个 `#` 之后的部分。
    """
    if not text or not url or url not in text:
        return ""
    prefix = re.sub(r"https?://\S+", " ", text.split(url)[0])
    m = re.search(r"[\u4e00-\u9fff].*", prefix)
    if not m:
        return ""
    cap = m.group(0).strip()
    head = cap.split("#")[0].strip()
    if len(head) >= 6:
        cap = head
    return re.sub(r"\s+", " ", cap).strip()


def sanitize(name: str) -> str:
    """文件名 slug：挡掉 Obsidian/Windows 非法字符与双链语法字符，压空格，截 60 字。"""
    name = re.sub(r'[\\/:*?"<>|#\[\]^\s]+', "-", (name or "").strip())
    return name.strip("-")[:60].strip("-")


def media_file(d: Path) -> Path | None:
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in MEDIA_EXT and f.is_file() and f.stat().st_size > 0:
            return f
    return None


def ytdlp_title(url: str) -> str:
    """yt-dlp 拿标题（B站/小红书等有效；抖音会报要 cookies，返回空）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-download", "--no-warnings", "--", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1"}, timeout=60)
        if r.returncode == 0:
            for line in (r.stdout or "").splitlines():
                if line.strip().startswith("{"):
                    return (json.loads(line).get("title") or "").strip()
    except Exception:
        pass
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="对标视频库：丢链接 → 自动入库命名")
    ap.add_argument("input", help="视频链接，或整段分享文案")
    ap.add_argument("--title", default="", help="手动标题（优先级最高）")
    ap.add_argument("--dry-run", action="store_true", help="只解析，不下载不落库")
    ap.add_argument("--force", action="store_true", help="同作品号已存在时仍覆盖")
    a = ap.parse_args()

    url0 = extract_url(a.input) or a.input.strip()
    url = resolve_url(url0)
    plat = detect_platform(url) or detect_platform(url0)
    if not plat:
        print(f"[fail] 认不出平台，支持：{'/'.join(PLATFORMS)}")
        print(f"       输入={url0}")
        return 2
    folder_cn = PLATFORMS[plat][0]
    wid = extract_work_id(url)
    cap = caption_from_share(a.input, url0) or caption_from_share(a.input, url)

    print(f"[1/4] 平台={folder_cn}  作品号={wid or '(未取到)'}")
    print(f"      链接={url}")

    if a.dry_run:
        print(f"[dry-run] 标题={a.title or cap or '(待 yt-dlp/redfox 解析)'}")
        return 0

    target_dir = LIB_ROOT / folder_cn
    target_dir.mkdir(parents=True, exist_ok=True)

    if wid and not a.force:
        dup = [p for p in target_dir.glob(f"*{wid}*") if p.suffix.lower() in MEDIA_EXT]
        if dup:
            print(f"[skip] 已在库：{dup[0].name}（要覆盖加 --force）")
            return 0

    print("[2/4] 下载（复用 fetch_video_with_browser.py）…")
    tmp = Path(tempfile.mkdtemp(prefix="refvid-"))
    try:
        r = subprocess.run([sys.executable, str(FETCH), url, str(tmp)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        print("\n".join("      " + ln for ln in out.splitlines()[-6:]))
        mf = media_file(tmp)
        if r.returncode != 0 or not mf:
            print("[fail] 下载失败")
            print(out[-800:])
            return 3

        meta: dict = {}
        mp = tmp / "meta.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                meta = {}

        title = a.title or cap or ytdlp_title(url) or (meta.get("title") or "").strip()
        date = datetime.now().strftime("%Y-%m-%d")
        parts = [date] + ([sanitize(title)] if title else []) + ([wid] if wid else [])
        stem = "-".join(parts)

        dst = target_dir / f"{stem}{mf.suffix.lower()}"
        if dst.exists() and not a.force:
            print(f"[skip] 目标已存在：{dst.name}")
            return 0
        shutil.move(str(mf), str(dst))

        meta.update({
            "title": title,
            "work_id": wid,
            "platform": plat,
            "source_url": url0,
            "resolved_url": url,
            "in_library": folder_cn,
            "collected": date,
            "file": dst.name,
        })
        (target_dir / f"{stem}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[3/4] 入库：{dst}")
        print(f"[4/4] 标题={'（未解析，仅作品号，可手改文件名）' if not title else title}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
