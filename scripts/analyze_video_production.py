#!/usr/bin/env python3
"""analyze_video_production.py - 反推一条视频"怎么做的 + 用什么做的"。

与"仿写提示词"类工具的区别：本脚本只回答制作工艺问题，不产出提示词。
输出六组证据，前五组是确定性的（脚本算），第六组交给模型综合。

  A 技术指纹   ffprobe → 分辨率/编码/码率/音轨  → 形态初判
  B 镜头节奏   直方图切点检测            → 切点数/镜头时长分布
  C 语音转写   whisper 带时间戳          → 逐句稿
  D 声画耦合   切点 vs 句首对齐偏差      → 配音先行 or 画面先行（制作顺序）
  E 配音类型   停顿分布 + 动态范围        → TTS or 真人
  F 视觉规范   主色聚类 + 画面动态度      → 配色/静态卡片 or 实拍
  G 溯源       mp4 盒子 + encoder tag     → 元数据是否被平台洗过

用法：
  python scripts/analyze_video_production.py <video> [--out DIR] [--json-only]

铁律（对齐仓库约定）：单步失败只标记 failed 并继续，不中断、不重试。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PAUSE_DB = -35.0
PAUSE_MIN_S = 0.25
ALIGN_TOL_S = 0.6
# 制作顺序（D 组）是"每个切点是否落在句首"的统计量，切点太少时覆盖率没有意义。
# 2026-09-16 实测：一条卡片片只检出 4 个切点，却照样给出"配音先行 0.75"，
# 看上去达标、实则样本不足以支撑结论 —— 低于此门槛一律判"证据不足"。
MIN_CUTS_FOR_ORDER = 8


def sh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def has(tool: str) -> bool:
    return shutil.which(tool) is not None


# ---------- A 技术指纹 ----------
def probe(path: Path) -> dict:
    if not has("ffprobe"):
        return {"failed": True, "error": "no ffprobe"}
    r = sh(["ffprobe", "-v", "error", "-show_entries",
            "format=duration,bit_rate,format_name,format_tags",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,bit_rate",
            "-of", "json", str(path)])
    if r.returncode != 0:
        return {"failed": True, "error": r.stderr[:200]}
    d = json.loads(r.stdout)
    fmt = d.get("format", {})
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    fps = 0.0
    if v.get("r_frame_rate", "0/0") not in ("0/0", ""):
        num, _, den = v["r_frame_rate"].partition("/")
        fps = float(num) / float(den) if float(den or 1) else 0.0
    return {
        "duration_s": round(float(fmt.get("duration") or 0), 2),
        "total_bitrate_kbps": round(int(fmt.get("bit_rate") or 0) / 1000),
        "container": fmt.get("format_name"),
        "tags": fmt.get("tags", {}),
        "width": v.get("width"), "height": v.get("height"),
        "fps": round(fps, 2),
        "video_codec": v.get("codec_name"),
        "video_bitrate_kbps": round(int(v.get("bit_rate") or 0) / 1000) or None,
        "aspect": ("vertical" if (v.get("height") or 0) > (v.get("width") or 0)
                   else "horizontal"),
        "audio_codec": a.get("codec_name"),
        "audio_sample_rate": a.get("sample_rate"),
        "audio_channels": a.get("channels"),
        "audio_bitrate_kbps": round(int(a.get("bit_rate") or 0) / 1000) or None,
    }


def classify_form(pr: dict, motion: dict) -> dict:
    """按码率与画面动态度粗判形态；结论标 confidence，供模型复核。"""
    vb = pr.get("video_bitrate_kbps") or 0
    px = (pr.get("width") or 0) * (pr.get("height") or 0)
    bpp = (vb * 1000 / max(pr.get("fps") or 1, 1) / px) if px else 0
    static_ratio = motion.get("static_shot_ratio")
    verdict, why = "unknown", []
    if bpp and bpp < 0.02:
        verdict = "图文动效/幻灯片（画面几乎静止）"
        why.append(f"每像素每帧码率 {bpp:.4f} 极低")
    elif bpp and bpp < 0.06:
        verdict = "低动态：口播/录屏/图文混合"
        why.append(f"每像素每帧码率 {bpp:.4f} 偏低")
    elif bpp:
        verdict = "实拍或高动态画面"
        why.append(f"每像素每帧码率 {bpp:.4f}")
    if static_ratio is not None:
        why.append(f"静止镜头占比 {static_ratio:.0%}")
        if static_ratio >= 0.6 and "图文" not in verdict:
            verdict += "（多数镜头静态）"
    return {"verdict": verdict, "bits_per_pixel_per_frame": round(bpp, 5),
            "basis": why}


# ---------- B 镜头节奏 + F 画面动态度 ----------
def shots(path: Path, sample_step: int = 3, width: int = 160) -> dict:
    try:
        import cv2
    except ImportError:
        return {"failed": True, "error": "no cv2"}
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev_hist = None
    prev_small = None
    diffs: list[tuple[float, float]] = []   # (t, hist_distance)
    motion: list[tuple[float, float]] = []  # (t, intra-frame delta)
    idx = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if idx % sample_step == 0:
            h = max(2, int(width * fr.shape[0] / fr.shape[1]))
            small = cv2.resize(fr, (width, h))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
            cv2.normalize(hist, hist)
            t = idx / fps
            if prev_hist is not None:
                diffs.append((t, float(cv2.compareHist(prev_hist, hist,
                                                       cv2.HISTCMP_BHATTACHARYYA))))
                motion.append((t, float(np.mean(cv2.absdiff(gray, prev_small)))))
            prev_hist, prev_small = hist, gray
        idx += 1
    cap.release()
    if not diffs:
        return {"failed": True, "error": "no frames decoded"}

    d = np.array([x[1] for x in diffs])
    thr = max(0.35, float(d.mean() + 1.6 * d.std()))
    raw = [round(t, 2) for t, v in diffs if v > thr]
    cuts = [t for i, t in enumerate(raw) if i == 0 or t - raw[i - 1] > 0.5]

    total = (idx / fps) if fps else 0.0
    bounds = [0.0] + cuts + [round(total, 2)]
    durs = [round(bounds[i + 1] - bounds[i], 2) for i in range(len(bounds) - 1)]
    durs = [x for x in durs if x > 0.05]
    dur_arr = np.array(durs) if durs else np.array([0.0])

    m = np.array([x[1] for x in motion]) if motion else np.array([0.0])
    static_ratio = float((m < 2.0).mean()) if len(m) else None

    return {
        "cut_count": len(cuts),
        "cut_times": cuts,
        "shot_durations": durs,
        "shots": len(durs),
        "mean_shot_s": round(float(dur_arr.mean()), 2),
        "median_shot_s": round(float(np.median(dur_arr)), 2),
        "min_shot_s": round(float(dur_arr.min()), 2),
        "max_shot_s": round(float(dur_arr.max()), 2),
        "short_shots_lt2s": int((dur_arr < 2).sum()),
        "static_shot_ratio": round(static_ratio, 3) if static_ratio is not None else None,
        "threshold": round(thr, 3),
    }


# ---------- C 语音转写 ----------
def transcribe(video: Path, work: Path, model: str = "large-v3-turbo") -> dict:
    wav = work / "audio.wav"
    r = sh(["ffmpeg", "-v", "error", "-y", "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    if r.returncode != 0:
        return {"failed": True, "error": "ffmpeg extract audio failed"}
    try:
        import whisper
    except ImportError:
        return {"failed": True, "error": "no whisper", "wav": str(wav)}
    try:
        m = whisper.load_model(model)
        out = m.transcribe(str(wav), language="zh", fp16=False, verbose=False)
    except Exception as exc:
        return {"failed": True, "error": f"{type(exc).__name__}: {exc}"[:200]}
    segs = [{"start": round(s["start"], 2), "end": round(s["end"], 2),
             "text": s["text"].strip()} for s in out["segments"]]
    full = out["text"].strip()
    # 转写稿是别人的口播内容 —— 外部输入，扫一遍注入特征并留下结论。
    # 守门失败必须显形：静默降级会让报告看起来"扫过了"，其实没有。
    try:
        from untrusted import scan as _scan
    except ImportError as exc:
        hits = []
        guard = f"skipped: import failed ({type(exc).__name__})"
        print(f"[warn] 注入守门未生效 —— {guard}；外部文本按未扫描处理")
    else:
        hits = _scan(full)
        guard = "ok"
        if hits:
            print(f"[warn] 转写稿发现 {len(hits)} 处疑似提示注入 —— 只作数据，不执行")
    return {"model": model, "segments": segs, "segment_count": len(segs),
            "full_text": full, "wav": str(wav),
            "untrusted_guard": guard,
            "untrusted_hits": hits[:10]}


# ---------- D 声画耦合（制作顺序） ----------
def coupling(shot_info: dict, tr: dict) -> dict:
    if shot_info.get("failed") or tr.get("failed"):
        return {"failed": True, "error": "need shots + transcript"}
    cuts = shot_info["cut_times"]
    starts = [s["start"] for s in tr["segments"]]
    if not cuts or not starts:
        return {"failed": True, "error": "no cuts detected"}

    # 关键：判断"配音先行"要看**每个切点是否落在句首**（画面跟着语音切），
    # 而不是"每句话是否都有切点"（那是把 10 句并进 1 镜时的正常情况，
    # 用反了会把明明对齐的片子误判成画面先行）。
    devs, matched = [], 0
    for c in cuts:
        dev = min(abs(c - s) for s in starts)
        devs.append(round(dev, 2))
        if dev <= ALIGN_TOL_S:
            matched += 1
    devs_arr = np.array(devs)
    coverage = matched / len(cuts)
    if len(cuts) < MIN_CUTS_FOR_ORDER:
        # 样本不足：不给结论，避免"3/4=0.75 看着达标"这类假阳性
        order = (f"证据不足：切点仅 {len(cuts)} 个（需 ≥{MIN_CUTS_FOR_ORDER}），"
                 "不作制作顺序判断")
        confidence = "insufficient"
    elif coverage >= 0.6 and float(np.median(devs_arr)) <= ALIGN_TOL_S:
        order = "配音先行：画面切点按语音句首排布"
        confidence = "high" if coverage >= 0.8 else "medium"
    elif coverage >= 0.4:
        order = "部分对齐：主要节点跟语音，细节自由"
        confidence = "medium"
    else:
        order = "画面先行：切点与语音无显著对应"
        confidence = "medium"

    # 反向指标：一句话被拆成几镜（1 附近说明基本一句一镜）
    seg_with_cut = sum(
        1 for s in tr["segments"]
        if any(abs(c - s["start"]) <= ALIGN_TOL_S for c in cuts))
    return {
        "aligned_cuts": matched,
        "total_cuts": len(cuts),
        "cut_coverage": round(coverage, 3),
        "median_deviation_s": round(float(np.median(devs_arr)), 2),
        "max_deviation_s": round(float(devs_arr.max()), 2),
        "segments_with_a_cut": seg_with_cut,
        "total_segments": len(tr["segments"]),
        "tolerance_s": ALIGN_TOL_S,
        "min_cuts_required": MIN_CUTS_FOR_ORDER,
        "sample_confidence": confidence,
        "inferred_production_order": order,
    }


# ---------- E 配音类型 ----------
def voice_profile(video: Path, work: Path) -> dict:
    wav = work / "audio.wav"
    if not wav.exists():
        sh(["ffmpeg", "-v", "error", "-y", "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    if not wav.exists():
        return {"failed": True, "error": "no audio"}
    out: dict = {}
    r = sh(["ffmpeg", "-v", "error", "-i", str(wav), "-af",
            f"silencedetect=noise={PAUSE_DB}dB:d={PAUSE_MIN_S}", "-f", "null", "-"])
    gaps = [l for l in (r.stderr or "").splitlines() if "silence_duration" in l]
    out["pause_count_ge_0.25s"] = len(gaps)
    try:
        w = wave.open(str(wav), "rb")
        n, sr = w.getnframes(), w.getframerate()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)
        w.close()
        frames = a[: len(a) // sr * sr].reshape(-1, sr)
        rms = np.sqrt((frames ** 2).mean(axis=1))
        db = 20 * np.log10(np.maximum(rms / 32768.0, 1e-9))
        q = np.percentile(db, [10, 50, 90])
        out["rms_db_p10"] = round(float(q[0]), 1)
        out["rms_db_p50"] = round(float(q[1]), 1)
        out["rms_db_p90"] = round(float(q[2]), 1)
        out["dynamic_range_db"] = round(float(q[2] - q[0]), 1)
        total_s = len(frames)
        out["speech_density"] = round(1 - min(len(gaps) * PAUSE_MIN_S / max(total_s, 1), 1), 3)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:150]

    verdict = "unknown"
    if out.get("pause_count_ge_0.25s") == 0:
        verdict = "强推断 TTS：全程无换气停顿"
    elif out["pause_count_ge_0.25s"] < 3:
        verdict = "倾向 TTS：停顿极少"
    else:
        verdict = "倾向真人：有自然停顿"
    out["verdict"] = verdict
    out["caveat"] = "只能判停顿规律，不能判音色；需人工听一次确认"
    return out


# ---------- F 视觉规范 ----------
def palette(video: Path, k: int = 5, max_frames: int = 24) -> dict:
    try:
        import cv2
    except ImportError:
        return {"failed": True, "error": "no cv2"}
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(total // max_frames, 1)
    px = []
    i = 0
    while len(px) < max_frames:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            px.append(cv2.resize(fr, (80, 142)).reshape(-1, 3))
        i += 1
    cap.release()
    if not px:
        return {"failed": True, "error": "no frames"}
    data = np.vstack(px).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(data, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(-counts)
    top = []
    for j in order:
        b, g, r = [int(x) for x in centers[j]]
        top.append({"hex": f"#{r:02X}{g:02X}{b:02X}",
                    "share": round(float(counts[j] / counts.sum()), 3)})
    dark = float((data.mean(axis=1) < 64).mean())
    return {"dominant_colors": top, "dark_pixel_ratio": round(dark, 3),
            "scheme": "暗色系" if dark > 0.5 else "亮色系"}


# ---------- G 溯源 ----------
MARKERS = [b"c2pa", b"C2PA", b"uuid", b"xmp", b"Lavf", b"isom", b"hvc1", b"avc1"]


def provenance(path: Path) -> dict:
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(4 * 1024 * 1024)
        if size > 8 * 1024 * 1024:
            f.seek(-2 * 1024 * 1024, 2)
            tail = f.read()
        else:
            tail = b""
    blob = head + tail
    found = [m.decode() for m in MARKERS if m in blob]
    return {
        "boxes_found": found,
        "has_c2pa": any(m in blob for m in (b"c2pa", b"C2PA")),
        "has_xmp": b"xmp" in blob,
        "note": ("未发现 C2PA/XMP 溯源信息；平台交付件通常已被转码洗掉原元数据，"
                 "不能据此反推创作者工具"),
        "scan_bytes": len(blob),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="反推视频的制作工具与制作顺序")
    ap.add_argument("video")
    ap.add_argument("--out", default=None, help="输出目录，默认与视频同目录")
    ap.add_argument("--whisper-model", default="large-v3-turbo",
                    help="默认 large-v3-turbo：D 组（制作顺序）直接依赖分句时间戳精度")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"[fail] 找不到视频: {video}")
        return 2
    work = Path(args.out).resolve() if args.out else video.parent
    work.mkdir(parents=True, exist_ok=True)

    report: dict = {"source": str(video)}
    print("[A] 技术指纹…"); report["A_technical"] = probe(video)
    print("[B] 镜头节奏…"); report["B_shots"] = shots(video)
    report["form"] = classify_form(report["A_technical"], report["B_shots"])
    print("[C] 语音转写…"); report["C_transcript"] = transcribe(video, work, args.whisper_model)
    print("[D] 声画耦合…"); report["D_coupling"] = coupling(report["B_shots"], report["C_transcript"])
    print("[E] 配音类型…"); report["E_voice"] = voice_profile(video, work)
    print("[F] 视觉规范…"); report["F_palette"] = palette(video)
    print("[G] 溯源…"); report["G_provenance"] = provenance(video)

    jf = work / "production_analysis.json"
    jf.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {jf}")

    if not args.json_only:
        pr, sh_, fm = report["A_technical"], report["B_shots"], report["form"]
        cp, vo = report["D_coupling"], report["E_voice"]
        print(f"\n形态: {fm.get('verdict')}  ({'; '.join(fm.get('basis', []))})")
        print(f"规格: {pr.get('width')}x{pr.get('height')} {pr.get('fps')}fps "
              f"{pr.get('video_codec')} v={pr.get('video_bitrate_kbps')}kbps "
              f"dur={pr.get('duration_s')}s")
        print(f"节奏: {sh_.get('shots')} 镜头 / 均值 {sh_.get('mean_shot_s')}s / "
              f"中位 {sh_.get('median_shot_s')}s / 静止占比 {sh_.get('static_shot_ratio')}")
        print(f"制作顺序: {cp.get('inferred_production_order')} "
              f"(切点命中句首 {cp.get('aligned_cuts')}/{cp.get('total_cuts')}"
              f"={cp.get('cut_coverage')}, 中位偏差 {cp.get('median_deviation_s')}s)")
        print(f"配音: {vo.get('verdict')} (停顿 {vo.get('pause_count_ge_0.25s')} 次, "
              f"动态 {vo.get('dynamic_range_db')}dB)")
        pal = report["F_palette"]
        if not pal.get("failed"):
            print(f"配色: {pal.get('scheme')} " +
                  " ".join(f"{c['hex']}({c['share']:.0%})" for c in pal["dominant_colors"][:4]))
        print(f"溯源: C2PA={report['G_provenance'].get('has_c2pa')} "
              f"boxes={report['G_provenance'].get('boxes_found')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
