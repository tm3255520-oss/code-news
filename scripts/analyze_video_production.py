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
import re
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
# 2026-09-16 实测：一条卡片片只检出 4 个切点，却照样给出"配音先行 0.75"。
# 2026-09-17 调整：门槛保留但分两级 ——
#   n < MIN_CUTS_FOR_WEAK(5)          → 证据不足，不给结论
#   5 ≤ n < MIN_CUTS_FOR_ORDER(8)     → 给结论但标"低置信"（7 卡结构天然只有 6–7 个切点，
#                                        一味沉默会让整类片子无法作答）
#   n ≥ MIN_CUTS_FOR_ORDER            → 正常结论
MIN_CUTS_FOR_ORDER = 8
MIN_CUTS_FOR_WEAK = 5


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


# ---------- B 镜头/卡片节奏 + F 画面动态度 ----------
# 度量选择（2026-09-17 第二次更换）：原先用 HSV 直方图距离 + 自适应阈值，在"高静止 +
# 少突变"的卡片片上失效（一条 7 卡视频只报 4 个切点，2 真 2 假、漏 5；另一条报 0）。
# 先改成"逐帧灰度帧间差 + 单帧尖峰"，在两条卡片片上对了，但**过检**（元素进场被当事件）。
# 最终方案基于三点实测校准（三条留档样本，见 reading-guide 的口径表）：
#   ① 幅度单指标无法区分"换卡"与"元素进场"（幅度重叠）；
#   ② 加"变化像素面积占比"后可以区分——换卡是整屏/整块换，元素只动一小块；
#      但三种片型的面积尺度不同（全屏式卡片 / 只动中央文字的卡片 / 动态素材），
#      单一阈值必然对某一种失效（实测：面积≥5% 时抖音 7 个正确、视频号只剩 4 个；
#      面积≥2% 时视频号 9 个正确、抖音涨到 16 个）；
#   ③ 动态素材片（B站样本）用面积判据会爆炸（180+），必须回到自适应阈值法。
# 因此本函数**不输出单一"卡片数"**，而是输出区间 + 口径：
#   严口径 = 幅度≥1.5 且 面积≥5%（全屏式换卡）→ 抖音 7（对上 7 张卡）
#   宽口径 = 幅度≥1.5 且 面积≥2%（含只动中央文字的换卡）→ 视频号 9（对上 9–11 卡）
#   D 组（声画耦合）用宽口径的事件，因为"跟着语音切"的换卡两种形态都算。
CUT_MIN_DIFF = 1.5       # 事件最小幅度（灰阶，160px 宽降采样）
AREA_TIGHT = 0.05        # 严口径：变化像素占比
AREA_LOOSE = 0.02        # 宽口径：变化像素占比
PIXEL_CHANGE_THR = 25    # 单像素判为"变了"的灰阶差
DENSE_MEAN_DIFF = 1.0    # 帧间差均值 ≥ 该值 → 动态素材型，改用自适应阈值法
CUT_SPIKE_RATIO = 2.5    # 单帧尖峰判定：峰值 > 相邻较高帧 × 该比例
PREV_ADAPTIVE_THR = 0.35  # 动态素材型沿用原自适应阈值下限（B站样本 49 镜）


def _events_by_criteria(m: list, r: list, fps: float,
                        mthr: float, rthr: float) -> list:
    """联合判据取事件：局部峰值 且 幅度≥mthr 且 变化面积≥rthr。

    宽度（≥峰值一半的连续帧数）用来自动区分：1 帧=硬切，2–4 帧=淡变。
    """
    out: list = []
    k = 1
    while k < len(m) - 1:
        v = float(m[k])
        if (v >= mthr and float(r[k]) >= rthr
                and v >= float(m[k - 1]) and v > float(m[k + 1])):
            half = v / 2.0
            lo = k
            while lo - 1 >= 0 and float(m[lo - 1]) >= half:
                lo -= 1
            hi = k
            while hi + 1 < len(m) and float(m[hi + 1]) >= half:
                hi += 1
            width = hi - lo + 1
            out.append({
                "t": round(k / fps, 2),
                "peak": round(v, 2),
                "area_ratio": round(float(r[k]), 3),
                "width_frames": width,
                "kind": "硬切" if width <= 1 else "淡变",
            })
            k = hi + 1
        else:
            k += 1
    return out


def _events_adaptive(m: list, fps: float) -> list:
    """动态素材型：沿用原自适应阈值法（实拍/录屏/混剪，B站样本给出 49 镜）。"""
    d = np.array(m)
    thr = max(PREV_ADAPTIVE_THR, float(d.mean() + 1.6 * d.std()))
    out: list = []
    last = -10 ** 9
    gap = int(0.5 * fps)
    for i, v in enumerate(d):
        if v <= thr or i - last < gap:
            continue
        out.append({"t": round(i / fps, 2), "peak": round(float(v), 2),
                    "area_ratio": None, "width_frames": None, "kind": "变点"})
        last = i
    return out


def shots(path: Path, width: int = 160) -> dict:
    try:
        import cv2
    except ImportError:
        return {"failed": True, "error": "no cv2"}
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    prev = None
    m: list = []          # 帧间差均值（幅度）
    r: list = []          # 变化像素占比（面积）
    frames = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        h = max(2, int(width * fr.shape[0] / fr.shape[1]))
        gray = cv2.cvtColor(cv2.resize(fr, (width, h)), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            df = cv2.absdiff(gray, prev)
            m.append(float(df.mean()))
            r.append(float((df > PIXEL_CHANGE_THR).mean()))
        prev = gray
        frames += 1
    cap.release()
    if not m:
        return {"failed": True, "error": "no frames decoded"}

    arr = np.array(m)
    mean_diff = float(arr.mean())
    tight = loose = None
    if mean_diff >= DENSE_MEAN_DIFF:
        video_class = "动态素材型"
        events = _events_adaptive(m, fps)
        criteria = ("自适应阈值法（动态素材型：实拍/录屏/混剪；"
                    f"阈值下限 {PREV_ADAPTIVE_THR}）")
        counts = {"adaptive": len(events)}
    else:
        video_class = "静态卡片型"
        tight = _events_by_criteria(m, r, fps, CUT_MIN_DIFF, AREA_TIGHT)
        loose = _events_by_criteria(m, r, fps, CUT_MIN_DIFF, AREA_LOOSE)
        events = loose            # D 组用宽口径：两种换卡形态都算"跟着语音切"
        criteria = (f"联合判据 幅度≥{CUT_MIN_DIFF} 且 变化面积≥{AREA_LOOSE}"
                    f"（宽口径=D组主口径）；严口径面积≥{AREA_TIGHT}")
        counts = {"tight": len(tight), "loose": len(loose)}

    cuts = [e["t"] for e in events]
    total = (frames / fps) if fps else 0.0
    bounds = [0.0] + cuts + [round(total, 2)]
    durs = [round(bounds[i + 1] - bounds[i], 2) for i in range(len(bounds) - 1)]
    durs = [x for x in durs if x > 0.05]
    dur_arr = np.array(durs) if durs else np.array([0.0])
    rng = ([len(tight), len(loose)] if tight is not None else [len(events), len(events)])
    return {
        "video_class": video_class,
        "scene_metric": criteria,
        "counts_by_criteria": counts,
        "scene_count_range": rng,
        "cut_count": len(cuts),
        "cut_times": cuts,
        "hard_cut_count": len([e for e in events if e["kind"] == "硬切"]),
        "fade_count": len([e for e in events if e["kind"] == "淡变"]),
        "event_detail": events,
        "card_count": len(events) + 1,
        "shot_durations": durs,
        "shots": len(durs),
        "mean_shot_s": round(float(dur_arr.mean()), 2),
        "median_shot_s": round(float(np.median(dur_arr)), 2),
        "min_shot_s": round(float(dur_arr.min()), 2),
        "max_shot_s": round(float(dur_arr.max()), 2),
        "short_shots_lt2s": int((dur_arr < 2).sum()),
        "static_shot_ratio": round(float((arr < 2.0).mean()), 3),
        "mean_frame_diff": round(mean_diff, 3),
        "threshold": round(CUT_MIN_DIFF, 2),
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
    n = len(cuts)
    if coverage >= 0.6 and float(np.median(devs_arr)) <= ALIGN_TOL_S:
        order = "配音先行：画面切点按语音句首排布"
        confidence = "high" if (coverage >= 0.8 and n >= MIN_CUTS_FOR_ORDER) else "low"
    elif coverage >= 0.4:
        order = "部分对齐：主要节点跟语音，细节自由"
        confidence = "medium" if n >= MIN_CUTS_FOR_ORDER else "low"
    else:
        order = "画面先行：切点与语音无显著对应"
        confidence = "medium" if n >= MIN_CUTS_FOR_ORDER else "low"
    if n < MIN_CUTS_FOR_WEAK:
        # 样本不足：不给结论，避免"3/4=0.75 看着达标"这类假阳性
        order = (f"证据不足：切点仅 {n} 个（需 ≥{MIN_CUTS_FOR_WEAK}），"
                 "不作制作顺序判断")
        confidence = "insufficient"
    elif n < MIN_CUTS_FOR_ORDER:
        order += f"（低置信：切点仅 {n} 个，<{MIN_CUTS_FOR_ORDER}）"

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
        "cut_sample": n,
        "min_cuts_required": MIN_CUTS_FOR_ORDER,
        "min_cuts_weak": MIN_CUTS_FOR_WEAK,
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


# ---------- H 响度/母带 ----------
def loudness(video: Path, work: Path) -> dict:
    """EBU R128 三值：整体响度 / 真峰值 / 动态范围。

    为什么单列一组：母带是否合规、有没有削波，只有这一步能看出来。
    2026-09-17 实测三条留档样本真峰值全部越线（−1.09 / +0.25 / +1.77 dBTP，
    标准 ≤ −1.0），其中一条比 −14 LUFS 标准响约 5 dB —— 靠听是听不出来的。
    注意：必须在**原视频**上测。实测先把音频降到 16k 单声道 wav 再测，抖音那条
    从 −13.25 变成 −16.28 LUFS，差 3 dB —— 采样率与声道合并会改变测量结果。
    """
    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
            "-map", "0:a:0", "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "")
    if not m:
        return {"failed": True, "error": "loudnorm 输出解析失败（可能无音轨）"}
    j = json.loads(m.group(0))
    i, tp, lra = float(j["input_i"]), float(j["input_tp"]), float(j["input_lra"])
    return {
        "integrated_lufs": i,
        "true_peak_dbtp": tp,
        "lra_lu": lra,
        "true_peak_ok": tp <= -1.0,
        "verdict": ("真峰值越界（标准 ≤ -1.0 dBTP），导出前需过限幅"
                    if tp > -1.0 else "真峰值合规"),
        "measured_on": "原视频音轨（非转码后的 wav）",
        "note": "参考基准：整体响度约 -14 LUFS、真峰值 ≤ -1.0 dBTP",
    }


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


# ---------- F2 版式/字号/强调色（2026-09-17 新增） ----------
# 为什么要 F2：F 组原来只有"5 色 k-means 占比"，而"能直接抄"的视觉信息是
# 版式槽位、字号层级、强调色占比。做法参考 Work Buddy 的 layout 方法
# （OCR 逐帧 → 词框 → 槽位聚类 + 字号分档），但抽帧与 OCR 自己实现而不是复制脚本：
#   - OCR 用 Windows 自带能力（scripts/win_ocr.ps1，WinRT，零安装零依赖）
#   - 本机实测 zh-CN OCR 包已 Installed；无引擎时本组按 failed 返回、不中断
# 颜色"语义"（红=工具 / 绿=收益）是**判断**不是测量，脚本只给强调色清单与占比，
# 语义标注留给报告作者 —— 与铁律 1「确定性 vs 推断分栏」一致。
OCR_PS1 = Path(__file__).resolve().parent / "win_ocr.ps1"
OCR_FILTER = re.compile(r"[\u4e00-\u9fff]")   # 含汉字才留


def _ocr_image(img: Path, lang: str = "zh-CN") -> list:
    """调 win_ocr.ps1 取词框。返回 [{text,x,y,w,h}]；失败返回 []。"""
    if not OCR_PS1.exists():
        return []
    exe = shutil.which("powershell.exe") or shutil.which("powershell")
    if not exe:
        return []
    r = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(OCR_PS1),
         "-Path", str(img), "-Lang", lang],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _slots(values: list, bin_w: float, min_seed: int) -> list:
    """一维分箱找"槽位"：分箱 → count ≥ min_seed 的箱作种子 → **仅紧邻**种子合并。

    为什么不用链式聚类（相邻差 ≤ gap 就并）：实测 83 个块被一路并成 1 个槽位
    （y 从 37.1% 到 63.7%），因为同页相邻文字的间隙都小于阈值。
    分箱 + 紧邻合并不会跨空箱传播，槽位边界因此稳定可解释。
    """
    if not values:
        return []
    lo = min(values)
    bins: dict = {}
    for v in values:
        b = int((v - lo) / bin_w)
        bins.setdefault(b, []).append(v)
    seeds = sorted(b for b, vs in bins.items() if len(vs) >= min_seed)
    groups, cur = [], []
    for b in seeds:
        if cur and b - cur[-1] <= 1:
            cur.append(b)
        else:
            if cur:
                groups.append(cur)
            cur = [b]
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        vals = [v for b in g for v in bins[b]]
        out.append((round(sum(vals) / len(vals), 1), len(vals),
                    round(min(vals), 1), round(max(vals), 1)))
    # 未落入任何槽位的块（散点）单独报数，不伪造槽位
    covered = sum(len(bins[b]) for g in groups for b in g)
    return out + ([] if covered == len(values) else [(None, len(values) - covered, None, None)])


def _blocks_from_words(words: list, w: int, h: int) -> list:
    """把词框并成行级文字块：同 y 带内的相邻词合并。丢掉纯单字符数字（emoji 误识）。"""
    kept = []
    for wo in words:
        t = str(wo.get("text") or "").strip()
        if not t:
            continue
        if not OCR_FILTER.search(t) and (len(t) < 2 or t.isdigit() and len(t) < 2):
            continue          # 纯符号/单字符数字 = emoji 或装饰，忽略
        kept.append(wo)
    if not kept:
        return []
    kept.sort(key=lambda x: (x["y"], x["x"]))
    lines: list = []
    for wo in kept:
        placed = False
        for ln in lines:
            if abs(ln[0]["y"] - wo["y"]) <= 0.6 * max(ln[0]["h"], wo["h"], 1):
                ln.append(wo)
                placed = True
                break
        if not placed:
            lines.append([wo])
    blocks = []
    for ln in lines:
        ln.sort(key=lambda x: x["x"])
        merged = [ln[0]]
        for wo in ln[1:]:
            prev = merged[-1]
            if wo["x"] - (prev["x"] + prev["w"]) <= 1.2 * max(prev["h"], 8):
                merged[-1] = {**prev, "w": wo["x"] + wo["w"] - prev["x"],
                              "text": prev["text"] + wo["text"],
                              "h": max(prev["h"], wo["h"])}
            else:
                merged.append(wo)
        for b in merged:
            blocks.append({
                "text": b["text"][:40],
                "y_pct": round(100.0 * (b["y"] + b["h"] / 2) / h, 1),
                "h_px": int(b["h"]),
                "x_mid_pct": round(100.0 * (b["x"] + b["w"] / 2) / w, 1),
            })
    return blocks


def layout_and_type(video: Path, work: Path, every_s: float = 2.5,
                    max_frames: int = 30) -> dict:
    """F2：OCR 逐帧 → 版式槽位 / 字号层级 / 居中判定 / 强调色占比。"""
    try:
        import cv2
    except ImportError:
        return {"failed": True, "error": "no cv2"}
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = (total / fps) if fps else 0.0
    fdir = work / "frames_ocr"
    fdir.mkdir(parents=True, exist_ok=True)
    times = []
    t = 0.0
    while t < dur and len(times) < max_frames:
        times.append(round(t, 2))
        t += every_s
    frames, blocks_all, accent = [], [], []
    for i, ts in enumerate(times):
        img = fdir / f"o_{i:03d}.jpg"
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
        ok, fr = cap.read()
        if not ok:
            continue
        cv2.imwrite(str(img), fr)
        hsv = cv2.cvtColor(cv2.resize(fr, (200, int(200 * H / max(W, 1)))),
                           cv2.COLOR_BGR2HSV)
        sat = (hsv[:, :, 1] > 90) & (hsv[:, :, 2] > 90)
        if sat.mean() > 0.0005:      # 有可辨识的强调色像素
            px = cv2.cvtColor(cv2.resize(fr, (200, int(200 * H / max(W, 1)))),
                              cv2.COLOR_BGR2RGB)[sat]
            accent.append((ts, float(sat.mean()), np.median(px, axis=0)))
        words = _ocr_image(img)
        if words:
            bl = _blocks_from_words(words, W, H)
            frames.append({"t": ts, "blocks": bl})
            blocks_all.extend(bl)
    cap.release()
    if not frames:
        return {"failed": True,
                "error": "OCR 无输出（检查 scripts/win_ocr.ps1 与 zh-CN 语言包）"}

    # 纵向占用带：5% 分箱的直方图。**不做聚类**——实测各卡片版式不同（标签/大标题/
    # 批注位置各异），y 分布是准连续的，全局"槽位"并不存在，硬聚会把 82 个块并成一簇。
    # 密集带 = 计数 ≥ 2× 中位数的箱，等价于"文字主要落在这几段"。
    bands: dict = {}
    for b in blocks_all:
        lo = int(b["y_pct"] // 5) * 5
        bands[lo] = bands.get(lo, 0) + 1
    med_band = float(np.median(list(bands.values()))) if bands else 0.0
    y_bands = [{"band": f"{k}–{k + 5}%", "blocks": v} for k, v in sorted(bands.items())]
    dense = [b for b in y_bands if med_band and b["blocks"] >= 2 * med_band]
    tiers = _slots([b["h_px"] for b in blocks_all], 8, 2)
    # 居中判定按"行"做：同一 y 带内的块合成一行（并排胶囊算一行），再看行中心。
    # 按块判定会把左右并排的两个胶囊都算成"不居中"，实测把居中率压到 0.5。
    lines_centered = lines_total = 0
    for fr in frames:
        rows: dict = {}
        for b in fr["blocks"]:
            if b["h_px"] < 20 or len(b["text"]) < 2:
                continue
            # 只算内容区（y 20–80%）：顶部装饰（左对齐系列名 + 右对齐页码）与
            # 底部角标天然不居中，会把居中率拉低（实测抖音因它掉到 0.40）
            if not (20 <= b["y_pct"] <= 80):
                continue
            key = int(b["y_pct"] // 2)
            rows.setdefault(key, []).append(b)
        for key, bs in rows.items():
            left = min(b["x_mid_pct"] for b in bs)
            right = max(b["x_mid_pct"] for b in bs)
            lines_total += 1
            if abs((left + right) / 2 - 50) <= 3:
                lines_centered += 1
    centered_ratio = round(lines_centered / max(lines_total, 1), 3)
    out = {
        "ocr_frames": len(frames),
        "sampled_every_s": every_s,
        "block_count": len(blocks_all),
        "text_lines": lines_total,
        "y_bands": y_bands,
        "y_dense_bands": dense,
        "y_bands_note": ("各卡版式不同时 y 分布准连续，全局槽位不存在；"
                         "这里给占用直方图与密集带，不做聚类"),
        "type_tiers_px": [{"h_px": c[0], "blocks": c[1],
                           "range": [c[2], c[3]]}
                          for c in sorted([t for t in tiers if t[0] is not None],
                                          key=lambda x: -x[0])],
        "type_tiers_ungrouped": sum(t[1] for t in tiers if t[0] is None),
        "centered_ratio": centered_ratio,
        "centered_scope": "内容区（y 20–80%）按行判定；并排块算一行",
        # 分档依据（2026-09-17 两条样本）：视频号单栏居中 0.911；
        # 抖音是"顶部标题 + 并排框 + 底部字幕"的多框版式，只剩 0.373 —— 这不是噪声，
        # 是版式差异，所以三档描述而不是一刀切"是否居中"。
        "layout_verdict": ("居中单栏纵向堆叠" if centered_ratio >= 0.85 else
                           "以居中为主，存在并排/分栏行" if centered_ratio >= 0.6 else
                           "多框/多栏版式（非单栏居中）"),
        "note": ("槽位=文字块中心的 y 百分比聚类（间隔 2.5%）；字号档=块高像素聚类（间隔 12px）。"
                 "颜色『语义』（工具/系统/收益）属判断，脚本只给强调色清单，标注留给报告作者。"),
    }
    if accent:
        shares = np.array([a[1] for a in accent])
        med = np.median(np.stack([a[2] for a in accent]), axis=0)
        out["accent_color"] = {
            "hex": "#{:02X}{:02X}{:02X}".format(int(med[0]), int(med[1]), int(med[2])),
            "frames_with_accent": len(accent),
            "accent_pixel_ratio_median": round(float(np.median(shares)), 4),
            # 阈值口径：对标样本的强调色占比落在 1–3%（抖音那条荧光绿 1.2%），
            # 所以 3% 以内属正常，超过才提示"是否铺面积"。
            "verdict": ("极简（<0.5%）：几乎不用强调色"
                        if float(np.median(shares)) < 0.005 else
                        "正常（0.5–3%）：对标区间 1–3%"
                        if float(np.median(shares)) <= 0.03 else
                        "偏高（>3%）：颜色可能铺面积，注意是否失去强调作用"),
        }
    else:
        out["accent_color"] = {"hex": None, "note": "未检出高饱和像素（可能纯灰阶/低饱和设计）"}
    return out


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
    print("[H] 响度/母带…"); report["H_loudness"] = loudness(video, work)
    print("[F] 视觉规范…"); report["F_palette"] = palette(video)
    print("[F2] 版式/字号/强调色（OCR 逐帧）…")
    report["F2_layout"] = layout_and_type(video, work)
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
        rng = sh_.get("scene_count_range") or [0, 0]
        print(f"节奏: {sh_.get('video_class')} / 场景数 {rng[0]}–{rng[1]}（严–宽口径）/ "
              f"硬切 {sh_.get('hard_cut_count')} / 淡变 {sh_.get('fade_count')} / "
              f"中位 {sh_.get('median_shot_s')}s / 静止 {sh_.get('static_shot_ratio')}")
        print(f"制作顺序: {cp.get('inferred_production_order')} "
              f"(切点命中句首 {cp.get('aligned_cuts')}/{cp.get('total_cuts')}"
              f"={cp.get('cut_coverage')}, 中位偏差 {cp.get('median_deviation_s')}s, "
              f"置信 {cp.get('sample_confidence')})")
        print(f"配音: {vo.get('verdict')} (停顿 {vo.get('pause_count_ge_0.25s')} 次, "
              f"动态 {vo.get('dynamic_range_db')}dB)")
        lo = report["H_loudness"]
        if not lo.get("failed"):
            print(f"响度: {lo.get('integrated_lufs')} LUFS / 真峰值 "
                  f"{lo.get('true_peak_dbtp')} dBTP / LRA {lo.get('lra_lu')} LU — "
                  f"{lo.get('verdict')}")
        pal = report["F_palette"]
        if not pal.get("failed"):
            print(f"配色: {pal.get('scheme')} " +
                  " ".join(f"{c['hex']}({c['share']:.0%})" for c in pal["dominant_colors"][:4]))
        lt = report.get("F2_layout") or {}
        if lt.get("failed"):
            print(f"版式: 未产出（{lt.get('error')}）")
        else:
            tiers = " / ".join(f"{t['h_px']}px×{t['blocks']}" for t in lt["type_tiers_px"][:5])
            ac = lt.get("accent_color") or {}
            dense = ", ".join(f"{b['band']}({b['blocks']})" for b in lt.get("y_dense_bands", [])[:5])
            print(f"版式: 文字行 {lt.get('text_lines')} / 纵向密集带 {dense or '无'} / "
                  f"字号档 {tiers}")
            print(f"     居中行占比 {lt['centered_ratio']} → {lt['layout_verdict']}")
            print(f"强调色: {ac.get('hex')}（占比中位 {ac.get('accent_pixel_ratio_median')}）"
                  f" {ac.get('verdict', '')}")
        print(f"溯源: C2PA={report['G_provenance'].get('has_c2pa')} "
              f"boxes={report['G_provenance'].get('boxes_found')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
