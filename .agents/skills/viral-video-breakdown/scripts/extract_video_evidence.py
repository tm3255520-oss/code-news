#!/usr/bin/env python3
"""
extract_video_evidence.py - 爆款视频拆解·证据提取（确定性脚本，🔵）

把 URL 或本地视频转成证据包：
  meta.json / video.mp4 / audio.wav / frames/*.jpg / contact_sheet.jpg
  frames_ocr.md / transcript.txt / manifest.json

原则（skill-design 铁律）：
- 全部确定性步骤，无 LLM。
- 幂等：产物已存在则跳过该步。
- 失败跳过 + 标记：单步失败写 manifest failed:true，继续下一步，不重试。

头条/西瓜用已验证链路（移动页取元数据 -> vod token 换播放地址 -> 下载）。
其它平台降级用 yt-dlp；无 yt-dlp 则只做本地文件证据。

用法:
  python extract_video_evidence.py <url|video_path> [out_dir] [--config config.yaml]
"""
import sys
import os
import re
import json
import base64
import subprocess
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 复用仓库 scripts/ 的公共模块（yt-dlp 抗抖动下载）
_CODE_NEWS_SCRIPTS = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts"))
if _CODE_NEWS_SCRIPTS not in sys.path:
    sys.path.insert(0, _CODE_NEWS_SCRIPTS)

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")

DEFAULT_CONFIG = {
    "paths": {"ffmpeg": "ffmpeg", "tesseract": "tesseract", "tessdata_prefix": None},
    "whisper": {"model_name": "large-v3-turbo", "model_dir": None,
                "device": "cpu", "compute_type": "int8"},
    "extraction": {"frame_interval": 3, "frame_width": 640,
                   "transcript_language": "zh", "user_agent": UA,
                   "ocr_max_frames": 80},
}


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


def load_config(path=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and os.path.exists(path):
        try:
            import yaml
            user = yaml.safe_load(open(path, encoding="utf-8")) or {}
            for k, v in user.items():
                if isinstance(v, dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:
            log(f"config 加载失败，用默认: {e}", "WARN")
    # env 覆盖
    if os.getenv("TESSDATA_PREFIX"):
        cfg["paths"]["tessdata_prefix"] = os.getenv("TESSDATA_PREFIX")
    for envkey in ("WHISPER_MODEL_NAME", "WHISPER_MODEL_DIR"):
        val = os.getenv(envkey)
        if val:
            key = envkey.lower().replace("whisper_", "whisper.").split(".")
            cfg["whisper"][key[1]] = val
    return cfg


def detect_platform(url):
    u = url.lower()
    if "toutiao.com" in u or "ixigua.com" in u:
        return "toutiao"
    if "douyin.com" in u:
        return "douyin"
    if "xiaohongshu.com" in u or "xhslink.com" in u:
        return "xiaohongshu"
    if "bilibili.com" in u or "b23.tv" in u:
        return "bilibili"
    if "weixin" in u or "channels.weixin" in u:
        return "weixin_video"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "unknown"


# ================= 头条/西瓜链路（已验证 2026-08-25） =================

def http_get(url, ua=UA, timeout=30, referer=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": ua, "Accept": "*/*",
        "Referer": referer or "https://m.toutiao.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_toutiao_meta(url, ua):
    """移动页取 articleInfo。"""
    m = re.search(r"(?:video|item)/(\d+)", url)
    vid = m.group(1) if m else url.rstrip("/").split("/")[-1]
    page = http_get(f"https://m.toutiao.com/video/{vid}/", ua).decode("utf-8", "replace")
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", page)
    data = None
    for s in scripts:
        t = s.strip()
        if not t.startswith("%7B") and "%22articleInfo%22" not in t:
            continue
        try:
            decoded = urllib.parse.unquote(t)
            obj = json.loads(decoded)
            if "articleInfo" in obj:
                data = obj
                break
        except Exception:
            continue
    if not data:
        raise RuntimeError("头条移动页未解析到 articleInfo")
    ai = data["articleInfo"]
    media = ai.get("mediaUser") or {}
    meta = {
        "platform": "toutiao", "url": url, "group_id": vid,
        "title": ai.get("title", ""), "description": ai.get("content", ""),
        "author": media.get("screenName", ""),
        "author_uid": media.get("id"), "author_followers": media.get("followerCount"),
        "author_video_count": media.get("videoCount"),
        "duration_s": ai.get("videoDuration") or ai.get("videoDurationMap", {}).get(
            ai.get("videoId", "")) or 0,
        "publish_time": ai.get("publishTime", ""),
        "video_id": ai.get("videoId", ""),
        "play_count": ai.get("videoPlayCount") or ai.get("impressionCount"),
        "comment_count": ai.get("commentCount"),
        "digg_count": ai.get("diggCount"),
        "repost_count": ai.get("repostCount"),
        "repin_count": ai.get("repinCount"),
        "is_original": ai.get("isOriginal"), "is_pgc": ai.get("isPgcArticle"),
        "biz_tag": ai.get("bizTag"), "poster_url": ai.get("posterUrl", ""),
        "play_auth_token": ai.get("playAuthTokenV2", ""),
    }
    return meta


def get_toutiao_playurl(meta, ua):
    """playAuthTokenV2 -> vod 播放地址列表 + sprite。"""
    token = meta.get("play_auth_token")
    if not token:
        raise RuntimeError("无 play_auth_token")
    pad = token + "=" * (-len(token) % 4)
    inner = json.loads(base64.b64decode(pad))
    signed = inner["GetPlayInfoToken"]
    resp = http_get("https://vod.bytedanceapi.com/?" + signed, ua).decode("utf-8", "replace")
    obj = json.loads(resp)
    d = obj["Result"]["Data"]
    urls = []
    for p in d.get("PlayInfoList", []):
        if p.get("MainPlayUrl"):
            urls.append({"definition": p.get("Definition"), "url": p["MainPlayUrl"],
                         "width": p.get("Width"), "height": p.get("Height"),
                         "size": p.get("Size")})
    urls.sort(key=lambda x: -(x.get("height") or 0))
    sprite = ""
    if d.get("BigThumbs"):
        sprite = d["BigThumbs"][0].get("ImgUrl", "")
    cover = d.get("CoverUrl", "") or meta.get("poster_url", "")
    return urls, sprite, cover


# ================= B站（Bilibili）链路（免登录，已验证 2026-08-25） =================

def fetch_bili_meta(url, ua):
    """view API -> meta + cid。"""
    m = re.search(r"(BV[0-9A-Za-z]+)", url)
    if not m:
        raise RuntimeError("无法从 URL 提取 bvid")
    bvid = m.group(1)
    ref = f"https://www.bilibili.com/video/{bvid}"
    obj = json.loads(http_get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", ua, referer=ref))
    if obj.get("code") != 0 or not obj.get("data"):
        raise RuntimeError(f"B站 view API 失败: {obj.get('message')}")
    d = obj["data"]
    s = d.get("stat", {})
    return {
        "platform": "bilibili", "url": url, "bvid": bvid, "cid": d.get("cid"),
        "title": d.get("title", ""), "description": d.get("desc", ""),
        "author": (d.get("owner") or {}).get("name", ""),
        "author_uid": (d.get("owner") or {}).get("mid"),
        "duration_s": d.get("duration"), "publish_time": d.get("pubdate"),
        "play_count": s.get("view"), "comment_count": s.get("reply"),
        "digg_count": s.get("like"), "favorite_count": s.get("favorite"),
        "coin_count": s.get("coin"), "share_count": s.get("share"),
        "danmaku_count": s.get("danmaku"), "poster_url": d.get("pic", ""),
    }


def get_bili_streams(bvid, cid, ua):
    """playurl API -> (视频url, 音频url)。取 avc 最高≤720p + 最高带宽音频。"""
    url = (f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}"
           f"&fnval=16&fnver=0&fourk=0")
    obj = json.loads(http_get(url, ua, referer=f"https://www.bilibili.com/video/{bvid}"))
    if obj.get("code") != 0 or not obj.get("data"):
        raise RuntimeError(f"B站 playurl 失败: {obj.get('message')}")
    dash = obj["data"].get("dash") or {}
    vids = [v for v in dash.get("video", []) if "avc" in (v.get("codecs") or "")]
    vids.sort(key=lambda v: -(v.get("height") or 0))
    auds = sorted(dash.get("audio", []), key=lambda a: -(a.get("bandwidth") or 0))
    return (vids[0]["baseUrl"] if vids else None,
            auds[0]["baseUrl"] if auds else None)


def _curl_download(url, out_path, ua, ref, timeout=180):
    """B站 m4s 专用下载：curl 覆盖 + 重试（抗 CDN 瞬时中断）。"""
    try:
        cmd = ["curl", "-sS", "-L", "--max-time", str(timeout), "--retry", "3",
               "--retry-delay", "2", "--retry-all-errors", "-A", ua,
               "-H", f"Referer: {ref}", "-o", out_path, url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 20)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception:
        return False


def download_bili(url, out_dir, ua, ffmpeg, meta):
    """下载 B站视频（m4s 视频+音频 -> ffmpeg 合成 video.mp4）。"""
    bvid, cid = meta.get("bvid"), meta.get("cid")
    if not bvid or not cid:
        return False
    vp = os.path.join(out_dir, "video.mp4")
    if os.path.exists(vp) and os.path.getsize(vp) > 0:  # 幂等：已有成品跳过
        return True
    vurl, aurl = get_bili_streams(bvid, cid, ua)
    if not vurl:
        return False
    vtmp, atmp = os.path.join(out_dir, "_v.m4s"), os.path.join(out_dir, "_a.m4s")
    ref = f"https://www.bilibili.com/video/{bvid}"
    okv = _curl_download(vurl, vtmp, ua, ref)
    oka = _curl_download(aurl, atmp, ua, ref) if aurl else False
    ok = False
    if okv and oka:
        r = run([ffmpeg, "-v", "error", "-y", "-i", vtmp, "-i", atmp,
                 "-c", "copy", "-movflags", "+faststart", vp], timeout=120)
        ok = r.returncode == 0 and os.path.exists(vp)
    for t in (vtmp, atmp):
        try:
            os.path.exists(t) and os.remove(t)
        except Exception:
            pass  # 清理失败不影响结果（只读挂载区/权限）
    return ok


# ================= 通用工具 =================

def run(cmd, timeout=300, env=None):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace",
                          env=env)


def download(url, out_path, ua=UA, referer=None):
    """单 URL 下载：先 urllib（30s），SSL/EOF 类失败再用 curl 兜底。"""
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        log(f"已存在，跳过下载: {os.path.basename(out_path)}")
        return True
    # 1) urllib
    try:
        data = http_get(url, ua, timeout=30, referer=referer)
        with open(out_path, "wb") as f:
            f.write(data)
        if os.path.getsize(out_path) > 0:
            return True
    except Exception as e:
        log(f"urllib 下载失败，转 curl 兜底 {url[:50]}: {str(e)[:80]}", "WARN")
    # 2) curl 兜底（CDN 对部分 python-TLS 握手不友好；加重试+断点续传抗瞬时中断）
    try:
        cmd = ["curl", "-sS", "-L", "--max-time", "180", "--retry", "3",
               "--retry-delay", "2", "--retry-all-errors", "-C", "-",
               "-A", ua, "-o", out_path, url]
        if referer:
            cmd += ["-H", f"Referer: {referer}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True
    except Exception as e:
        log(f"curl 兜底失败 {url[:50]}: {str(e)[:80]}", "WARN")
    return False


def extract_audio(video_path, out_path, ffmpeg):
    if os.path.exists(out_path):
        return True
    r = run([ffmpeg, "-v", "error", "-y", "-i", video_path, "-vn",
             "-ac", "1", "-ar", "16000", out_path], timeout=300)
    return r.returncode == 0 and os.path.exists(out_path)


def extract_frames(video_path, out_dir, ffmpeg, interval, width):
    if os.path.isdir(out_dir) and any(f.endswith(".jpg") for f in os.listdir(out_dir)):
        return True
    os.makedirs(out_dir, exist_ok=True)
    r = run([ffmpeg, "-v", "error", "-y", "-i", video_path,
             "-vf", f"fps=1/{interval},scale={width}:-1", "-q:v", "4",
             os.path.join(out_dir, "f_%03d.jpg")], timeout=300)
    return r.returncode == 0 and any(f.endswith(".jpg") for f in os.listdir(out_dir))


def make_contact_sheet(frames_dir, out_path, ffmpeg):
    if os.path.exists(out_path):
        return True
    frames = sorted(os.listdir(frames_dir))[:100]
    if not frames:
        return False
    first = os.path.join(frames_dir, frames[0])
    r = run([ffmpeg, "-v", "error", "-y", "-i", first,
             "-vf", f"scale=240:-1,tile={min(10,len(frames))}x{max(1,len(frames)//10+1)}",
             out_path], timeout=120)
    return r.returncode == 0


def ocr_frames(frames_dir, out_md, tesseract, tessdata_prefix, max_frames=80):
    if os.path.exists(out_md):
        try:
            prev = open(out_md, encoding="utf-8").read()
            if len(prev.strip()) > 40:  # 有实际 OCR 内容才跳过，空文件重做
                return True
        except Exception:
            pass
    names = sorted(n for n in os.listdir(frames_dir) if re.match(r"f_\d+\.jpg", n))
    if len(names) > max_frames:  # 长视频均匀抽样，防 OCR 超时
        step = len(names) / max_frames
        names = [names[int(i * step)] for i in range(max_frames)]
    lines = ["# 画面文字时间线（OCR）", ""]
    env = os.environ.copy()
    if tessdata_prefix:
        env["TESSDATA_PREFIX"] = tessdata_prefix
    ok = False
    for name in names:
        m = re.match(r"f_(\d+)\.jpg", name)
        if not m:
            continue
        path = os.path.join(frames_dir, name)
        t = (int(m.group(1)) - 1) * 3
        try:
            r = run([tesseract, path, "stdout", "-l", "chi_sim", "--psm", "6",
                     "--dpi", "96"], timeout=60, env=env)
            txt = re.sub(r"\s+", " ", r.stdout or "").strip()
            if r.returncode != 0:
                lines.append(f"- t={t}s | [OCR失败: {(r.stderr or '').strip()[:80]}]")
            else:
                lines.append(f"- t={t}s | {txt}")
            ok = ok or bool(txt)
        except Exception as e:
            lines.append(f"- t={t}s | [OCR失败: {e}]")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return ok


def transcribe(audio_path, out_txt, cfg):
    """faster-whisper 转写（带时间码）。模型可配置；无依赖则标缺失。"""
    if os.path.exists(out_txt) and os.path.getsize(out_txt) > 0:
        return True, ""
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        return False, f"无 faster-whisper: {e}"
    try:
        model_name = cfg["whisper"]["model_name"]
        model_dir = cfg["whisper"].get("model_dir")
        load = model_dir if model_dir and os.path.isdir(model_dir) else model_name
        model = WhisperModel(load, device=cfg["whisper"]["device"],
                             compute_type=cfg["whisper"]["compute_type"])
        segs, info = model.transcribe(
            audio_path, language=cfg["extraction"]["transcript_language"], beam_size=5)
        out = []
        for s in segs:
            out.append(f"[{s.start:6.1f}-{s.end:6.1f}] {s.text.strip()}")
        with open(out_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        return True, ""
    except Exception as e:
        return False, f"转写失败: {e}"


def save_meta(meta, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "meta.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return path


def save_manifest(steps, out_dir):
    path = os.path.join(out_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), "steps": steps},
                  f, ensure_ascii=False, indent=1)
    log(f"manifest -> {path}")


# ================= 主流程 =================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="URL 或本地视频/音频/字幕文件")
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--skip-whisper", action="store_true", help="跳过转写（省时间）")
    args = ap.parse_args()
    cfg = load_config(args.config)
    inp = args.input
    out_dir = args.out_dir or os.path.join(
        os.getcwd(), "evidence", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    steps = {}
    meta = {}

    is_url = inp.startswith("http")
    platform = detect_platform(inp) if is_url else "local"
    log(f"输入: {inp} | 平台: {platform} | 输出: {out_dir}")

    # ---- 1. 元数据 ----
    try:
        if is_url and platform == "toutiao":
            meta = fetch_toutiao_meta(inp, cfg["extraction"]["user_agent"])
            steps["meta"] = {"ok": True, "platform": "toutiao"}
        elif is_url and platform == "bilibili":
            meta = fetch_bili_meta(inp, cfg["extraction"]["user_agent"])
            steps["meta"] = {"ok": True, "platform": "bilibili"}
        elif is_url:
            # yt-dlp 兜底（可选）
            try:
                r = run([sys.executable, "-m", "yt_dlp", "--dump-json",
                         "--no-download", "--", inp], timeout=60)
                if r.returncode == 0 and r.stdout.strip().startswith("{"):
                    o = json.loads(r.stdout.strip())
                    meta = {"platform": platform, "url": inp,
                            "title": o.get("title", ""), "author": o.get("uploader", ""),
                            "duration_s": o.get("duration"), "description": o.get("description", "")}
                    steps["meta"] = {"ok": True, "platform": platform}
                else:
                    raise RuntimeError("yt-dlp 元数据失败")
            except Exception as e:
                steps["meta"] = {"ok": False, "error": str(e)}
                meta = {"platform": platform, "url": inp}
        else:
            meta = {"platform": "local", "url": inp,
                    "title": os.path.basename(inp), "duration_s": 0}
            steps["meta"] = {"ok": True, "platform": "local"}
    except Exception as e:
        steps["meta"] = {"ok": False, "error": str(e)}
        meta = {"platform": platform, "url": inp}
    save_meta(meta, out_dir)

    # ---- 2. 下载视频 ----
    video_path = ""
    if is_url:
        try:
            if platform == "toutiao" and meta.get("video_id"):
                urls, sprite, cover = get_toutiao_playurl(meta, cfg["extraction"]["user_agent"])
                meta["play_urls"] = urls
                meta["sprite_url"] = sprite
                if cover:
                    meta["poster_url"] = cover
                if urls:
                    vp = os.path.join(out_dir, "video.mp4")
                    ok = False
                    for u in urls:
                        if download(u["url"], vp, cfg["extraction"]["user_agent"]):
                            ok = True
                            meta["downloaded_def"] = u["definition"]
                            break
                        os.path.exists(vp) and os.remove(vp)
                    video_path = vp if ok else ""
                    steps["download"] = {"ok": ok, "def": meta.get("downloaded_def", ""),
                                         "error": "" if ok else "所有清晰度下载失败"}
                    if sprite:
                        download(sprite, os.path.join(out_dir, "contact_sheet.jpg"),
                                 cfg["extraction"]["user_agent"])
                else:
                    steps["download"] = {"ok": False, "error": "无播放地址"}
            elif platform == "bilibili" and meta.get("bvid"):
                vp = os.path.join(out_dir, "video.mp4")
                ok = download_bili(inp, out_dir, cfg["extraction"]["user_agent"],
                                   cfg["paths"]["ffmpeg"], meta)
                video_path = vp if ok else ""
                steps["download"] = {"ok": ok,
                                     "error": "" if ok else "B站下载失败"}
            else:
                # yt-dlp 下载（抗抖动：长传输冻结时看门狗杀掉并断点续传，见 scripts/ytdlp_download.py）
                vp = os.path.join(out_dir, "video.mp4")
                ok, err = False, ""
                try:
                    import ytdlp_download
                    rr = ytdlp_download.robust_download(inp, vp, log=log)
                    ok = bool(rr["ok"])
                    if ok:
                        video_path = rr["path"]          # 实际产物（可能为 .webm/.mkv）
                        log(f"yt-dlp 下载完成：{rr['size_MB']}MB，{rr['attempts']} 段")
                    else:
                        err = rr.get("error") or "yt-dlp 下载失败"
                except Exception as e:
                    err = f"yt-dlp 下载异常：{str(e)[:180]}"
                if not ok:
                    video_path = ""
                steps["download"] = {"ok": ok, "error": err}
        except Exception as e:
            steps["download"] = {"ok": False, "error": str(e)[:200]}
    else:
        video_path = inp
        steps["download"] = {"ok": True, "note": "local file"}

    # ---- 3. 音频 ----
    audio_ok = False
    if video_path:
        audio_path = os.path.join(out_dir, "audio.wav")
        audio_ok = extract_audio(video_path, audio_path, cfg["paths"]["ffmpeg"])
        steps["audio"] = {"ok": audio_ok, "error": "" if audio_ok else "ffmpeg 音频提取失败"}

    # ---- 4. 抽帧 + contact sheet ----
    frames_ok = False
    if video_path:
        frames_dir = os.path.join(out_dir, "frames")
        frames_ok = extract_frames(video_path, frames_dir, cfg["paths"]["ffmpeg"],
                                   cfg["extraction"]["frame_interval"],
                                   cfg["extraction"]["frame_width"])
        steps["frames"] = {"ok": frames_ok,
                           "error": "" if frames_ok else "抽帧失败"}
        cs = os.path.join(out_dir, "contact_sheet.jpg")
        if frames_ok and not os.path.exists(cs):
            make_contact_sheet(frames_dir, cs, cfg["paths"]["ffmpeg"])

    # ---- 5. OCR ----
    ocr_ok = False
    if frames_ok:
        try:
            ocr_ok = ocr_frames(os.path.join(out_dir, "frames"),
                                os.path.join(out_dir, "frames_ocr.md"),
                                cfg["paths"]["tesseract"],
                                cfg["paths"].get("tessdata_prefix"),
                                cfg["extraction"].get("ocr_max_frames", 80))
            steps["ocr"] = {"ok": ocr_ok,
                            "error": "" if ocr_ok else "OCR 无可读文字"}
        except Exception as e:
            steps["ocr"] = {"ok": False, "error": str(e)[:200]}

    # ---- 6. 转写 ----
    if audio_ok and not args.skip_whisper:
        ok, err = transcribe(os.path.join(out_dir, "audio.wav"),
                             os.path.join(out_dir, "transcript.txt"), cfg)
        steps["transcript"] = {"ok": ok, "error": err}
    elif args.skip_whisper:
        steps["transcript"] = {"ok": False, "error": "skip 参数跳过"}

    save_manifest(steps, out_dir)
    log("证据提取完成。产物: " + ", ".join(
        n for n in ("meta.json", "video.mp4", "audio.wav", "frames/",
                    "frames_ocr.md", "transcript.txt") if os.path.exists(os.path.join(out_dir, n))))


if __name__ == "__main__":
    main()
