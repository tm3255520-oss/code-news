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
# 平台目录下只留卡片（.md）；视频本体与 meta 收进这个子目录，避免刷屏
MEDIA_DIRNAME = "_媒体"

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
# 注意：Obsidian **不支持** `![[video.mp4|宽度]]` 这种尺寸语法（那只对图片有效）——
# 实测其渲染代码只创建 <video controls preload=metadata>，从不设宽度。
# 所以卡片缩放走 CSS 片段：.obsidian/snippets/refvid.css + frontmatter `cssclasses`。


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


# ---------- 互动数（BSK 浏览器会话通道） ----------
# 为什么走 BSK 而不是 redfox：redfox 的 parseWork 只回视频地址与封面，没有互动数；
# 它的关键词搜索虽带 赞/藏/评/转，但按标题搜到的是"同名话题"的别人的视频，无法定位到指定作品。
# 已知作品号时，唯一能精确取数的是本机浏览器的抖音登录态 + 官方 detail 接口。

def bsk_session() -> str:
    """取一个活跃的 bsk 会话 id（没有则返回空串）。"""
    try:
        r = subprocess.run(["bsk", "session", "list", "--json"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        if r.returncode == 0:
            arr = json.loads(r.stdout or "[]")
            if isinstance(arr, list) and arr:
                return str(arr[0].get("session_id") or "")
    except Exception:
        pass
    return ""


def douyin_metrics(aweme_id: str, session: str) -> dict | None:
    """经 BSK 会话取抖音单条作品的互动数（点赞/收藏/评论/转发）。取不到返回 None。"""
    if not (session and aweme_id):
        return None
    try:
        subprocess.run(["bsk", "navigate", "--session", session,
                        f"https://www.douyin.com/video/{aweme_id}",
                        "--wait-until", "domcontentloaded", "--timeout", "60s"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=90)
        js = ("(async()=>{const r=await fetch('/aweme/v1/web/aweme/detail/?aweme_id="
              + aweme_id + "&aid=6383',{credentials:'include'});const t=await r.text();"
              "let j=null;try{j=JSON.parse(t)}catch(e){};const d=(j&&j.aweme_detail)||{};"
              "const s=d.statistics||{};return JSON.stringify({http:r.status,"
              "digg:s.digg_count,comment:s.comment_count,collect:s.collect_count,"
              "share:s.share_count,play:s.play_count});})()")
        r = subprocess.run(["bsk", "evaluate", "--session", session, "--json", js],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
        if r.returncode != 0:
            return None
        val = json.loads(json.loads(r.stdout or "{}").get("value") or "{}")
        if val.get("http") != 200:
            return None
        return {"like": val.get("digg"), "collect": val.get("collect"),
                "comment": val.get("comment"), "share": val.get("share"),
                "play": val.get("play")}
    except Exception:
        return None


def attach_metrics(meta: dict) -> dict:
    """把互动数写进 meta（同时留一份带时间戳的历史，便于看增长）。"""
    wid = meta.get("work_id")
    sid = bsk_session() if wid else ""
    m = douyin_metrics(wid, sid) if sid else None
    if not m:
        meta["metrics_status"] = ("无活跃 bsk 会话（浏览器自动化通道不可用）" if not sid
                                  else "取数失败（接口非 200 或解析失败）")
        return meta
    at = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta["metrics"] = m
    meta["metrics_at"] = at
    meta.pop("metrics_status", None)
    hist = [h for h in (meta.get("metrics_history") or []) if h.get("at") != at]
    hist.append({"at": at, **m})
    meta["metrics_history"] = hist[-20:]
    return meta


# 4 项参数的中文名与含义（卡片里逐条列出，打开就知道每个数字是什么）
MEANING = {
    "like": ("👍 点赞", "点「赞」的次数 —— 内容认可度，最直观的量级指标"),
    "collect": ("⭐ 收藏", "被收藏的次数 —— 觉得值得留存 / 复用"),
    "comment": ("💬 评论", "评论条数 —— 引发讨论的强度"),
    "share": ("🔁 转发", "被分享 / 转发的次数 —— 传播意愿"),
}


def media_size(path: Path) -> tuple[int, int] | None:
    """ffprobe 取视频宽高（失败返回 None）。"""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        w, h = (r.stdout or "").strip().split("x")[:2]
        return int(w), int(h)
    except Exception:
        return None


def find_media(target_dir: Path, file_name: str) -> Path | None:
    """定位视频本体（与卡片同目录）；兼容早前挪进 _媒体/ 的旧布局。"""
    for cand in (target_dir / MEDIA_DIRNAME / file_name, target_dir / file_name):
        if cand.is_file():
            return cand
    return None


def normalize_audio(path: Path) -> str:
    """把 Chromium 不支持的音轨转成 AAC-LC（视频轨原样复制、零画质损失）。

    为什么必须做：Obsidian 的播放内核是 Chromium，只解 **AAC-LC**；
    而抖音下回来的片子音轨常是 **HE-AACv2** —— 表现就是「第一帧能看到、
    一按播放就卡住/没反应」（2026-10-04 实测两条都中招）。
    """
    if path.suffix.lower() not in (".mp4", ".mov", ".m4a"):
        return "skip(非 mp4 容器)"
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                            "-show_entries", "stream=profile",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        prof = (r.stdout or "").strip()
    except Exception:
        return "probe 失败"
    if not prof or prof == "LC":
        return "ok"
    tmp = path.with_name(path.name + ".aaclc.tmp.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart", str(tmp)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return f"转码失败 {(r.stderr or '')[:100]}"
    os.replace(tmp, path)
    return f"已归一 {prof} -> AAC-LC"


def write_note(meta: dict, target_dir: Path) -> Path | None:
    """写同名 .md 卡片：内嵌视频 + 4 项互动数（带含义）。打开笔记即等于「打开这个视频」。"""
    file_name = meta.get("file") or ""
    if not file_name:
        return None
    note = target_dir / (Path(file_name).stem + ".md")
    title = meta.get("title") or Path(file_name).stem
    m = meta.get("metrics") or {}
    at = meta.get("metrics_at") or "（未采集）"
    # 竖屏视频用 CSS 片段缩窄（见 NOTE_PORTRAIT_WIDTH 处的说明）；
    # 横屏不给 refvid-portrait 类，保持默认宽度。
    media = find_media(target_dir, file_name)
    dims = media_size(media) if media else None
    css = ("[refvid, refvid-portrait]" if dims and dims[1] > dims[0] else "[refvid]")
    fm = ["---", "类型: 对标视频", f"cssclasses: {css}",
          f"平台: {meta.get('in_library') or meta.get('platform') or ''}",
          f'标题: "{title}"',
          f'作品号: "{meta.get("work_id") or ""}"',
          f'来源: "{meta.get("source_url") or ""}"',
          f"入库日: {meta.get('collected') or ''}",
          f"时长秒: {meta.get('duration') or ''}"]
    fm += [f"{k}: {m.get(k, '')}" for k in MEANING]
    fm += [f'互动采集: "{at}"', "---", ""]
    body = [f"# {title}", "", f"![[{file_name}]]", "", f"## 互动数（截至 {at}）", "",
            "| 参数 | 数值 | 含义 |", "|---|---:|---|"]
    body += [f"| {MEANING[k][0]} | {m.get(k, '—')} | {MEANING[k][1]} |" for k in MEANING]
    body += ["", "> 数据取自抖音官方接口（本机登录态），是**时间点快照**，会随时间增长；"
             "重跑 `ref_video_intake.py --refresh-metrics` 可刷新。", "",
             "## 来源", "", f"- 原链接：{meta.get('source_url') or ''}",
             f"- 作品号：`{meta.get('work_id') or ''}`", ""]
    note.write_text("\n".join(fm + body), encoding="utf-8")
    return note


def refresh_metrics(platform_filter: str) -> int:
    """回填 / 刷新库里已有条目的互动数（只处理有作品号的抖音条目）。"""

    def platform_of(meta_path: Path) -> str:
        # meta 收在 <平台>/_媒体/ 下；兼容旧的 <平台>/ 平铺写法
        return (meta_path.parent.parent if meta_path.parent.name == MEDIA_DIRNAME
                else meta_path.parent).name

    if not bsk_session():
        print("[fail] 没有活跃的 bsk 会话，取不到互动数（需要本机浏览器在连）")
        return 4
    metas = sorted(LIB_ROOT.rglob("*.meta.json"))
    if platform_filter:
        metas = [p for p in metas if platform_of(p) == platform_filter]
    if not metas:
        print("[info] 库里没有 .meta.json 条目")
        return 0
    ok = skip = 0
    for mp in metas:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            print(f"[skip] {mp.name}（meta 读不出）")
            skip += 1
            continue
        if meta.get("platform") != "douyin" or not meta.get("work_id"):
            print(f"[skip] {platform_of(mp)}/{mp.name}（非抖音或无作品号）")
            skip += 1
            continue
        before = meta.get("metrics") or {}
        meta = attach_metrics(meta)
        if not meta.get("metrics"):
            print(f"[fail] {mp.name} —— {meta.get('metrics_status')}")
            skip += 1
            continue
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        write_note(meta, LIB_ROOT / platform_of(mp))
        m = meta["metrics"]
        delta = "".join(f" {k}{m[k] - before[k]:+d}" if isinstance(before.get(k), int) else ""
                        for k in ("like", "collect", "comment", "share"))
        print(f"[ok] {meta.get('file') or mp.name}\n     赞{m['like']} 藏{m['collect']} "
              f"评{m['comment']} 转{m['share']}{('  变化:' + delta) if delta else ''}")
        ok += 1
    print(f"[done] 更新 {ok} 条，跳过 {skip} 条")
    return 0


def rebuild_notes(platform_filter: str) -> int:
    """只用现有 meta.json 重生成卡片（不联网、不重新取数）——换模板或迁移后跑。"""
    metas = sorted((LIB_ROOT / platform_filter if platform_filter else LIB_ROOT)
                   .rglob("*.meta.json"))
    n = 0
    for mp in metas:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            print(f"[skip] {mp.name}（meta 读不出）")
            continue
        pdir = mp.parent.parent if mp.parent.name == MEDIA_DIRNAME else mp.parent
        note = write_note(meta, pdir)
        if note:
            print(f"[ok] {note.relative_to(LIB_ROOT)}")
            n += 1
    print(f"[done] 重生成 {n} 张卡片")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="对标视频库：丢链接 → 自动入库命名")
    ap.add_argument("input", nargs="?", default="", help="视频链接，或整段分享文案")
    ap.add_argument("--title", default="", help="手动标题（优先级最高）")
    ap.add_argument("--dry-run", action="store_true", help="只解析，不下载不落库")
    ap.add_argument("--force", action="store_true", help="同作品号已存在时仍覆盖")
    ap.add_argument("--refresh-metrics", action="store_true",
                    help="不下载，只刷新库里已有条目的互动数（赞/藏/评/转）")
    ap.add_argument("--rebuild-notes", action="store_true",
                    help="只用现有 meta.json 重生成卡片（不联网）")
    ap.add_argument("--platform", default="", help="配合 --refresh-metrics：只刷某个平台目录")
    a = ap.parse_args()

    if a.rebuild_notes:
        return rebuild_notes(a.platform)
    if a.refresh_metrics:
        return refresh_metrics(a.platform)
    if not a.input:
        ap.error("需要给一个视频链接 / 分享文案，或用 --refresh-metrics 刷新互动数")

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

    dup = ([p for p in target_dir.glob(f"*{wid}*") if p.suffix.lower() in MEDIA_EXT]
           if wid else [])
    if dup and not a.force:
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
        norm = normalize_audio(mf)
        if norm != "ok":
            print(f"      音频归一：{norm}")

        meta: dict = {}
        mp = tmp / "meta.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        if dup:
            # 覆盖已有条目时，把旧 meta 垫在下面 —— 否则重下会把已采到的互动数与历史冲掉
            old = target_dir / f"{dup[0].stem}.meta.json"
            if old.is_file():
                try:
                    meta = {**json.loads(old.read_text(encoding="utf-8")), **meta}
                except Exception:
                    pass

        title = a.title or cap or ytdlp_title(url) or (meta.get("title") or "").strip()
        date = datetime.now().strftime("%Y-%m-%d")
        if dup:
            # 覆盖已有条目时沿用原文件名 —— 否则"这次没解析出标题"会另起一个名字，产出重复副本
            stem = dup[0].stem
        else:
            parts = [date] + ([sanitize(title)] if title else []) + ([wid] if wid else [])
            stem = "-".join(parts)

        # 视频与 meta 放在卡片**同目录**：Obsidian 同目录解析最稳（挪进子目录曾导致嵌入失效）
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
        meta_path = target_dir / f"{stem}.meta.json"
        if plat == "douyin" and wid:
            meta = attach_metrics(meta)
            meta.pop("metrics_history", None)  # 入库首抓只记当前值，历史留给 --refresh-metrics
            if meta.get("metrics"):
                m = meta["metrics"]
                print(f"      互动：赞{m['like']} 藏{m['collect']} 评{m['comment']} 转{m['share']}")
            else:
                print(f"      互动：未取到 —— {meta.get('metrics_status')}")
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        note = write_note(meta, target_dir)

        print(f"[3/4] 入库：{dst}")
        if note:
            print(f"      卡片：{note.name}（内嵌视频 + 4 项互动数）")
        print(f"[4/4] 标题={'（未解析，仅作品号，可手改文件名）' if not title else title}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
