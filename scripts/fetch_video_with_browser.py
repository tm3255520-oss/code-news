#!/usr/bin/env python3
"""fetch_video_with_browser.py - 用本机浏览器会话取视频（抖音等需登录态的平台）。

为什么需要这个脚本：
  yt-dlp 的 `--cookies-from-browser` 在新版 Chrome/Edge 上会报
  `Failed to decrypt with DPAPI`。原因是浏览器把 cookie 升级为 v20
  App-Bound Encryption，密钥只有浏览器进程自己能解。

  本脚本不破解加密：自己起一个持久化浏览器，打开目标页，
  再通过 Playwright 从浏览器进程内读**明文** cookie，落成
  Netscape cookies.txt 交给 yt-dlp。登录态存在私有 profile 里，
  第一次可能需要手动过验证码，之后长期复用。

用法：
  python scripts/fetch_video_with_browser.py <url> <out_dir> [--headless] [--profile DIR]

产物：
  <out_dir>/video.<ext>   下载的视频
  <out_dir>/meta.json     平台/标题/时长/互动数

私有目录（不进仓库）：
  %USERPROFILE%\\.codex\\video-fetch\\             默认 profile 与 cookies.txt
  可用环境变量 VIDEO_FETCH_HOME 覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

READY_COOKIES = ("ttwid", "s_v_web_id", "odin_tt")

# ---------- redfox 通用解析路由（2026-09-17 加） ----------
# 为什么加：yt-dlp 对视频号没有 extractor、浏览器嗅探又撞登录墙（实测 0 条媒体流），
# 而 redfox 的通用解析接口一次调用就给 videoUrl，覆盖抖音/视频号/B站，且不需要登录态。
# 复用而非自建：鉴权与调用走 hermes 的共享客户端 redfox_client（同一套密钥/错误码处理），
# 避免出现第三份 redfox 调用代码。
HERMES_SCRIPTS = r"C:\Users\Administrator\.hermes\scripts"
UA_FALLBACK = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PLATFORM_REFERER = (
    ("douyin", "https://www.douyin.com/"),
    ("weixin", "https://channels.weixin.qq.com/"),
    ("bilibili", "https://www.bilibili.com/"),
    ("xiaohongshu", "https://www.xiaohongshu.com/"),
)


def referer_for(url: str) -> str:
    low = url.lower()
    for key, ref in PLATFORM_REFERER:
        if key in low or (key == "weixin" and "sph" in low):
            return ref
    return ""


def redfox_parse(url: str) -> dict | None:
    """调 redfox 通用解析接口取 videoUrl；不可用或未解析出地址时返回 None。"""
    if HERMES_SCRIPTS not in sys.path:
        sys.path.insert(0, HERMES_SCRIPTS)
    try:
        from redfox_client import RedFox
    except ImportError as exc:
        print(f"[warn] redfox 共享客户端不可用，跳过该路由（{type(exc).__name__}: {exc}）")
        return None
    try:
        # 注意：RedFox.call() 返回的是 data 本体，不是 {"code","msg","data"} 信封
        data = RedFox().call("/story/api/parseWork/parse", {"url": url})
    except Exception as exc:
        print(f"[warn] redfox 解析异常，跳过该路由（{type(exc).__name__}: {exc}）")
        return None
    if not isinstance(data, dict):
        print("[info] redfox 未返回可用结果，跳过该路由")
        return None
    if not (data.get("videoUrl") or "").strip():
        print(f"[info] redfox 未解析出视频地址（awemeType={data.get('awemeType')}）")
        return None
    return data


def download_stream(url: str, target: Path, referer: str = "") -> bool:
    """下载媒体流。用 requests 而不是 urllib：实测抖音 365yg CDN 对 urllib 会
    TLS 握手失败（UNEXPECTED_EOF），requests 正常。"""
    try:
        import requests
    except ImportError:
        print("[warn] 无 requests，跳过下载")
        return False
    headers = {"User-Agent": UA_FALLBACK}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=180)
    except Exception as exc:
        print(f"[warn] 下载失败: {type(exc).__name__}: {str(exc)[:100]}")
        return False
    if r.status_code != 200 or len(r.content) < 10000:
        print(f"[warn] 下载异常: HTTP {r.status_code} / {len(r.content)} 字节")
        return False
    target.write_bytes(r.content)
    return True


def _redfox_path(url: str, out_dir: Path) -> int:
    """redfox 路由：解析 → 下载 → 落 meta.json。失败返回非 0 让上层继续降级。"""
    data = redfox_parse(url)
    if not data:
        return 7
    target = out_dir / "video.mp4"
    if not download_stream(data["videoUrl"], target, referer_for(url)):
        return 7
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    meta = {
        "platform": "redfox-parse",
        "title": data.get("title") or "",
        "duration": int(float((probe.stdout or "0").strip() or 0)),
        "cover": data.get("cover"),
        "aweme_type": data.get("awemeType"),
        "webpage_url": url,
        "method": "redfox-parse",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(scan_untrusted(meta), ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] " + str(target))
    print("       " + json.dumps({k: meta[k] for k in ("title", "duration", "method")},
                                 ensure_ascii=False)[:200])
    return 0


def scan_untrusted(meta: dict) -> dict:
    """平台元数据（标题/简介/作者）是用户生成内容，属外部输入，扫一遍再落盘。

    守门失败必须显形（与 analyze_video_production.py 同一约定）：
    静默跳过会让 meta.json 看起来"扫过了"，其实没有。
    """
    try:
        from untrusted import scan
    except ImportError as exc:
        guard = f"skipped: import failed ({type(exc).__name__})"
        meta["_untrusted_guard"] = guard
        print(f"[warn] 注入守门未生效 —— {guard}；平台元数据按未扫描处理")
        return meta
    hits = []
    for k in ("title", "description", "uploader"):
        for h in scan(str(meta.get(k) or "")):
            h["field"] = k
            hits.append(h)
    if hits:
        meta["_untrusted_warning"] = hits[:10]
        print(f"[warn] 平台元数据发现 {len(hits)} 处疑似提示注入 —— "
              f"已标注 _untrusted_warning，内容一律只作数据")
    meta["_untrusted_guard"] = "ok"
    return meta

# 抖音的媒体流走 douyinvod.com；byteeffecttos.com 是特效/贴纸素材，必须排除，
# 否则会把贴纸 mp4 当成视频下下来。
MEDIA_HOST_ALLOW = re.compile(r"douyinvod\.com|/video/tos/", re.I)
MEDIA_HOST_DENY = re.compile(r"byteeffecttos\.com|effectcdn|/ies\.fe\.effect/", re.I)
MEDIA_EXT = re.compile(r"\.(mp4|m4s)(\?|$)", re.I)


def private_home() -> Path:
    root = os.environ.get("VIDEO_FETCH_HOME")
    base = Path(root) if root else Path.home() / ".codex" / "video-fetch"
    base.mkdir(parents=True, exist_ok=True)
    return base


def to_netscape(cookies: list[dict], path: Path) -> int:
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            dom = c.get("domain") or ""
            if not dom:
                continue
            if not dom.startswith(".") and dom.count(".") >= 1:
                dom = "." + dom
            exp = int(c.get("expires") or 0)
            if exp <= 0:
                exp = 2147483647
            f.write("\t".join([
                dom, "TRUE", c.get("path", "/"),
                "TRUE" if c.get("secure") else "FALSE",
                str(exp), c["name"], c["value"],
            ]) + "\n")
            n += 1
    return n


def harvest_cookies(url: str, profile: Path, headless: bool, wait_s: float,
                    settle_s: float = 6.0) -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            channel="msedge",
            args=["--disable-blink-features=AutomationControlled"],
            viewport=None if not headless else {"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:  # 超时不致命，cookie 可能已经写入
            print(f"[warn] goto: {type(exc).__name__}: {str(exc)[:120]}")

        # 短链会 302 到真实视频页；必须等它落地并驻留，平台才会铸造本次会话的新鲜 cookie。
        for _ in range(12):
            if not page.url.startswith("https://v.douyin.com"):
                break
            page.wait_for_timeout(2500)
        print(f"[..] 落地页: {page.url[:110]}")
        page.wait_for_timeout(int(settle_s * 1000))

        steps = max(int(wait_s / 2.5), 1)
        cookies: list[dict] = []
        for i in range(steps):
            cookies = ctx.cookies()
            names = {c["name"] for c in cookies}
            if all(k in names for k in READY_COOKIES):
                print(f"[ok] cookie 就绪 @ {i * 2.5:.1f}s，共 {len(cookies)} 条")
                break
            print(f"[..] {i * 2.5:.1f}s 已有 {len(cookies)} 条，等待关键 cookie")
            page.wait_for_timeout(2500)
        else:
            print(f"[warn] 等待超时，只有 {len(cookies)} 条 cookie（可能需要过验证码）")

        ctx.close()
        return cookies


def ytdlp(args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "yt_dlp", *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def sh_ffprobe(path: Path) -> set[str]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {k.strip() for k in (r.stdout or "").splitlines() if k.strip()}


def sniff_download(url: str, profile: Path, headless: bool, out_dir: Path,
                   wait_s: float = 15.0, max_tracks: int = 6):
    """让浏览器自己加载页面，从网络层截获真实媒体流再下载。

    抖音的 aweme/detail 接口现在要 msToken + a_bogus 签名，yt-dlp 拿不到；
    但浏览器自己播放时一定会请求真实媒体流，截获它即可绕开签名问题。
    """
    from playwright.sync_api import sync_playwright

    raw: list[str] = []
    saved: list[Path] = []
    meta: dict = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile), headless=headless, channel="msedge",
            args=["--disable-blink-features=AutomationControlled"],
            viewport=None if not headless else {"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_resp(resp):
            u = resp.url
            if MEDIA_HOST_DENY.search(u):
                return
            if not (MEDIA_HOST_ALLOW.search(u) or MEDIA_EXT.search(u)):
                return
            ct = (resp.headers or {}).get("content-type", "")
            if ct and not ct.startswith(("video/", "audio/", "application/octet-stream")):
                return
            raw.append(u)

        page.on("response", on_resp)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"[warn] goto: {type(exc).__name__}: {str(exc)[:100]}")
        page.wait_for_timeout(int(wait_s * 1000))
        meta["title"] = (page.title() or "").replace(" - 抖音", "").strip()
        meta["webpage_url"] = page.url

        seen, urls = set(), []
        for u in raw:
            key = u.split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            urls.append(u)
        print(f"[sniff] 截获 {len(urls)} 条候选媒体流")

        for i, u in enumerate(urls[:max_tracks]):
            try:
                resp = ctx.request.get(
                    u, headers={"Referer": "https://www.douyin.com/"},
                    timeout=180000, fail_on_status_code=False)
                if not resp.ok:
                    print(f"  [skip] HTTP {resp.status}")
                    continue
                body = resp.body()
            except Exception as exc:
                print(f"  [skip] {type(exc).__name__}")
                continue
            suffix = ".mp4" if ".mp4" in u.lower() else ".m4s"
            f = out_dir / f"track_{i}{suffix}"
            f.write_bytes(body)
            saved.append(f)
            print(f"  [got] {f.name} {len(body) / 1024:.0f} KB")
        ctx.close()
    return meta, saved


def assemble(tracks: list[Path], out_dir: Path) -> Path | None:
    """把截获的轨道拼成一个可用的 video.mp4。"""
    target = out_dir / "video.mp4"
    vids, auds, muxed = [], [], []
    for f in tracks:
        kinds = sh_ffprobe(f)
        if "video" in kinds and "audio" in kinds:
            muxed.append(f)
        elif "video" in kinds:
            vids.append(f)
        elif "audio" in kinds:
            auds.append(f)
    if muxed:
        best = max(muxed, key=lambda f: _height(f))
        shutil.copy2(best, target)
        return target
    if vids:
        best = max(vids, key=lambda f: _height(f))
        if auds:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(best), "-i", str(auds[0]),
                 "-c", "copy", "-movflags", "+faststart", str(target)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and target.exists():
                return target
            print(f"[warn] 合并失败：{(r.stderr or '')[:150]}")
        shutil.copy2(best, target)
        return target
    return None


def _height(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return int((r.stdout or "0").strip() or 0)
    except ValueError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="用本机浏览器会话取视频（抖音等）")
    ap.add_argument("url")
    ap.add_argument("out_dir")
    ap.add_argument("--headless", action="store_true", help="无头模式（抖音大概率触发验证，不推荐）")
    ap.add_argument("--profile", default=None, help="浏览器 profile 目录，默认在私有目录下")
    ap.add_argument("--wait", type=float, default=40.0, help="等待关键 cookie 的秒数")
    ap.add_argument("--wait-sniff", type=float, default=15.0,
                    help="嗅探兜底时等待页面拉流加载的秒数")
    ap.add_argument("--no-redfox", action="store_true",
                    help="跳过 redfox 通用解析路由（默认先走它，失败再降级到浏览器）")
    args = ap.parse_args()

    home = private_home()
    profile = Path(args.profile) if args.profile else home / "browser-profile"
    cookie_file = home / "cookies.txt"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_redfox:
        print("[0/3] redfox 通用解析（无需登录态，覆盖抖音/视频号/B站）")
        if _redfox_path(args.url, out_dir) == 0:
            return 0
        print("[info] redfox 路由未成功，降级到浏览器路由")

    print(f"[1/3] 启动浏览器取 cookie (profile={profile})")
    cookies = harvest_cookies(args.url, profile, args.headless, args.wait)
    if not cookies:
        print("[fail] 没拿到任何 cookie")
        return 2
    n = to_netscape(cookies, cookie_file)
    print(f"[2/3] 写入 {n} 条 cookie -> {cookie_file}")

    print("[3/3] yt-dlp 下载")
    meta = ytdlp([
        "--cookies", str(cookie_file), "--no-warnings", "--skip-download",
        "--dump-json", "--", args.url,
    ])
    if meta.returncode != 0:
        print("[info] yt-dlp 取接口失败，转浏览器嗅探兜底")
        print("       " + (meta.stderr or meta.stdout).strip().splitlines()[-1][:160])
        return _sniff_path(args, home, profile, out_dir)

    info = json.loads(meta.stdout.strip().splitlines()[0])
    summary = {
        "platform": info.get("extractor_key"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url"),
        "method": "yt-dlp",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(scan_untrusted(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    print("       " + json.dumps(summary, ensure_ascii=False)[:200])

    dl = ytdlp([
        "--cookies", str(cookie_file), "--no-warnings",
        "-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4",
        "-o", str(out_dir / "video.%(ext)s"), "--", args.url,
    ])
    if dl.returncode != 0:
        print("[info] yt-dlp 下载失败，转浏览器嗅探兜底")
        return _sniff_path(args, home, profile, out_dir)
    print("[done] " + str(out_dir))
    return 0


def _sniff_path(args, home: Path, profile: Path, out_dir: Path) -> int:
    meta, tracks = sniff_download(args.url, profile, args.headless, out_dir,
                                  wait_s=args.wait_sniff)
    if not tracks:
        print("[fail] 没截获到媒体流：页面可能未自动播放，或该视频需要登录")
        return 5
    target = assemble(tracks, out_dir)
    if not target:
        print("[fail] 截获的流里没有可用的视频轨")
        return 6
    for f in tracks:
        if f != target:
            f.unlink(missing_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    meta["duration"] = int(float((probe.stdout or "0").strip() or 0))
    meta["method"] = "browser-sniff"
    meta["extractor_key"] = "Douyin"
    (out_dir / "meta.json").write_text(
        json.dumps(scan_untrusted(meta), ensure_ascii=False, indent=2), encoding="utf-8")
    print("[done] " + str(target))
    print("       " + json.dumps(meta, ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
