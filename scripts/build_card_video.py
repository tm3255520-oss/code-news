#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_card_video.py — 知识卡片视频编排层（一条命令出成片）

把「口播稿 + 卡片结构」变成一条带配音和字幕的 MP4：

    script.json
      → ① voice_segmenter.py（edge-tts 逐段配音）
          → voice_segmented.mp3 / .srt / voice_timeline.json
      → ② 段级时间轴按卡片分组 → 卡片起止时长 + 字幕时间轴
      → ③ build_card_deck.py → HyperFrames 合成 index.html
      → ④ hyperframes render → MP4

关键约束（对齐对标样本的工艺）：**配音先行**。卡片时长与字幕轴全部由配音实测时长推出，
不写死任何页时长。

用法:
    python scripts/build_card_video.py --script script.json --out <工作目录>
        [--project video-line] [--voice yunjian] [--gap 0.4] [--rate +28%]
        [--voice-root <voice_segmenter.py 所在目录>] [--skip-render] [--quality looks]

语速校准（2026-09-16 实测，对标抖音样本 C：365 字 / 60.5s = 6.03 字/秒）
    带标点的真实稿件下，edge-tts 逐段配音的实测语速：
        +21% → 5.74 字/秒 (0.952x)   +25% → 5.93 (0.983x)
        +28% → 6.07 字/秒 (1.006x) ← 默认值，与对标基线基本一致
        +32% → 6.26 (1.038x)         +36% → 6.45 (1.069x)
    注意：标点会带来微停顿，会拉低语速；改稿件标点后需要重新校准。
    速率只保证节奏对齐，**音色自然度无法由脚本判定，必须人工听一次**。

稿件标点要求（决定字幕质量）
    voice_segmenter 按标点断句（句末 `。！？!?` 优先，句中 `，、；：` 次选），
    只有超长且无标点的片段才会按字数硬切 —— 硬切会断在词中间。
    所以口播稿必须带标点，且标点写在自然停顿处。本脚本会校验并告警。

script.json 结构:
{
  "series": "AI KNOWLEDGE", "episode": "SERIES 001", "breadcrumb": "AI工作流",
  "voice": "yunjian",
  "lines": ["第一句口播。", "第二句口播。", ...],      // 顺序即配音顺序
  "cards": [
    {"title": "...", "kicker": "...", "subtitle": "...",
     "blocks": [{"label": "INPUT", "text": "..."}],
     "big": ["3 小时", "5 分钟"],                      // 可选，替代 blocks
     "from": 1, "to": 3}                               // 1-based，含两端
  ]
}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_card_deck  # noqa: E402

DEFAULT_VOICE_DIR = Path(r"C:\Users\Administrator\.hermes\scripts\video_enhance")
HF_CMD_CANDIDATES = (
    r"D:\pi-agent\hyperframes.cmd",
    r"D:\pi-agent\hyperframes.ps1",
)


def hf_prefix() -> list[str]:
    """把 hyperframes 解析成可被 subprocess 直接执行的形式。

    Windows 上 hyperframes 是 .cmd/.ps1 包装脚本，CreateProcess 不能直接跑，
    必须过 cmd /c 或 powershell -File。
    """
    for name in ("hyperframes.cmd", "hyperframes.exe", "hyperframes"):
        p = shutil.which(name)
        if p:
            return _wrap(p)
    for c in HF_CMD_CANDIDATES:
        if Path(c).exists():
            return _wrap(c)
    return ["npx", "--yes", "hyperframes@0.8.40"]


def _wrap(path: str) -> list[str]:
    low = path.lower()
    if low.endswith((".cmd", ".bat")):
        return ["cmd", "/c", path]
    if low.endswith(".ps1"):
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
    return [path]



def run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def parse_srt(path: Path) -> list[dict]:
    def sec(t: str) -> float:
        h, m, rest = t.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = [x for x in block.splitlines() if x.strip()]
        if len(lines) < 3:
            continue
        m = re.search(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
        if not m:
            continue
        cues.append({"start": sec(m.group(1)), "end": sec(m.group(2)),
                     "text": "".join(lines[2:]).strip()})
    return cues


PUNCT = "。！？!?，、,；;：:"
MAX_UNBROKEN = 14  # 超过这个长度且无标点 → 会被按字数硬切，可能断在词中间


def check_lines(lines: list[str]) -> list[str]:
    """口播稿标点自检：字幕断句质量取决于它。"""
    warns = []
    for i, t in enumerate(lines, 1):
        t = t.strip()
        if not t:
            warns.append(f"第 {i} 行是空的")
            continue
        if t[-1] not in "。！？!?":
            warns.append(f"第 {i} 行结尾没有句末标点（建议补 。）")
        longest = max((len(x) for x in re.split("[" + re.escape(PUNCT) + "]", t)), default=0)
        if longest > MAX_UNBROKEN:
            warns.append(f"第 {i} 行有 {longest} 字连续无标点，会被硬切（建议在自然停顿处补 ，）")
    return warns


def step_tts(script: dict, out_dir: Path, voice_dir: Path,
             voice: str, gap: float, rate: str) -> tuple[Path, Path, dict]:
    """① 逐段配音。返回 (mp3, srt, timeline)。"""
    lines = script["lines"]
    vi = out_dir / "voice_input.json"
    vi.write_text(json.dumps({"script": {"script": [{"content": t} for t in lines]}},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    vdir = out_dir / "voice"
    vs = voice_dir / "voice_segmenter.py"
    if not vs.exists():
        raise FileNotFoundError(f"找不到 voice_segmenter.py: {vs}")
    r = run([sys.executable, str(vs), "--script", str(vi),
             "--out-dir", str(vdir), "--engine", "edge",
             "--voice", voice, "--gap", str(gap), "--rate", rate])
    if r.returncode != 0:
        raise RuntimeError("TTS 失败:\n" + (r.stdout or "")[-800:] + (r.stderr or "")[-800:])
    mp3 = vdir / "voice_segmented.mp3"
    srt = vdir / "voice_segmented.srt"
    tl = vdir / "voice_timeline.json"
    for f in (mp3, srt, tl):
        if not f.exists():
            raise RuntimeError(f"TTS 产物缺失: {f}")
    return mp3, srt, json.loads(tl.read_text(encoding="utf-8"))


def media_duration(path: Path) -> float:
    """ffprobe 实测媒体时长（权威值，优于时间轴的取整值）。"""
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    try:
        return round(float((r.stdout or "0").strip() or 0), 3)
    except ValueError:
        return 0.0


def make_preview(deck: dict, audio: Path, cut: float, project: Path) -> dict:
    """把整片截成「前 cut 秒」的确认版：只留该区间内的卡片与字幕，音频同长截断。

    借自 anything2explainer 的「前 30 秒样片」确认点：
    「在这里改一次是 1 个组的成本，等整片渲完再改是全部组」。
    """
    cards = [dict(c) for c in deck["cards"] if c["start"] < cut - 0.05]
    if not cards:
        cards = [dict(deck["cards"][0])]
    last = cards[-1]
    last["duration"] = round(max(cut - last["start"], 0.5), 3)
    for c in cards:
        c["captions"] = [x for x in c.get("captions", []) if x["start"] < cut - 0.04]
    assets = project / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    out_audio = assets / "preview_audio.mp3"
    r = run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-t", f"{cut:.3f}",
             "-c:a", "libmp3lame", "-q:a", "2", str(out_audio)])
    if r.returncode != 0:
        raise RuntimeError("截断预览音频失败：" + (r.stderr or "")[:200])
    d = dict(deck)
    d["cards"] = cards
    d["audio"] = "assets/preview_audio.mp3"
    return d


def run_check(project: Path, retries: int = 1) -> tuple[bool, str]:
    """跑 hyperframes check 当质量门。

    实测有一次瞬时失败：Runtime 报 `Navigation timeout of 10000 ms exceeded`，
    直接重跑就过（Lint 当时是 0 error）。所以这里对**导航超时**做一次重试，
    其余错误不重试 —— 避免把真缺陷当成抖动放过。
    """
    for attempt in range(retries + 1):
        r = run([*hf_prefix(), "check", str(project)], timeout=900)
        out = (r.stdout or "") + (r.stderr or "")
        passed = "Check passed" in out
        transient = "Navigation timeout" in out
        if passed:
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            tail = next((l for l in lines if "text checks" in l), "")
            return True, "Check passed" + ("　" + tail if tail else "")
        if transient and attempt < retries:
            print("     [retry] 命中瞬时导航超时，重试一次")
            continue
        return False, "Check 未通过：\n" + "\n".join(
            l for l in out.splitlines() if l.strip().startswith(("✗", "⚠")))[:900]
    return False, "Check 重试耗尽"


HEAD_KEEP = 0.03     # 段首保留的静音（秒）
TAIL_KEEP = 0.06     # 段尾保留的静音（秒）
SIL_DB = -42.0       # 判定静音的相对门限（dB，相对该段语音电平）


def _speech_bounds(wav: Path) -> tuple[float, float, float]:
    """返回 (语音起点, 语音终点, 段总长)，单位秒。用相对门限，抗不同录音电平。"""
    import wave as _w
    import numpy as _np
    w = _w.open(str(wav), "rb")
    sr = w.getframerate()
    a = _np.frombuffer(w.readframes(w.getnframes()), dtype=_np.int16).astype(_np.float32)
    w.close()
    win = max(int(sr * 0.01), 1)
    n = len(a) // win
    if n < 4:
        return 0.0, len(a) / sr, len(a) / sr
    rms = _np.sqrt((a[:n * win].reshape(n, win) ** 2).mean(axis=1))
    db = 20 * _np.log10(_np.maximum(rms / 32768.0, 1e-9))
    thr = _np.percentile(db, 90) + SIL_DB
    loud = _np.where(db > thr)[0]
    if len(loud) == 0:
        return 0.0, len(a) / sr, len(a) / sr
    return loud[0] * 0.01, (loud[-1] + 1) * 0.01, len(a) / sr


def normalize_pauses(voice_dir: Path, gap: float, compress: bool = False) -> dict:
    """用自己生成的合法静音片重建配音拼接，并按新时间轴重写 SRT 与 timeline。

    为什么不让 voice_segmenter 直接做：实测 `--gap 0` 时它生成的 silence.mp3 是坏的
    （0.20 KB，ffmpeg 报 "Failed to find two consecutive MPEG audio frames"），
    拼接在第一段之后就断了 —— 而只要 gap>0 又会凭空多出约 0.8s 静音。
    所以这里绕开它：用已经生成好的 seg_*.mp3，按我们要的 gap 重新拼一遍。

    返回新的 timeline（同时回写 voice_segmented.mp3 / .srt / voice_timeline.json）。
    """
    seg_dir = voice_dir / "_segments"
    segs = sorted(seg_dir.glob("seg_*.mp3"))
    if len(segs) < 2:
        return json.loads((voice_dir / "voice_timeline.json").read_text(encoding="utf-8"))

    durs = [media_duration(p) for p in segs]
    if any(d <= 0 for d in durs):
        raise RuntimeError("分段音频时长读取失败，无法重建拼接")

    # ── 裁掉每段头尾的静音：edge-tts 句末自带约 0.84s 停顿，不裁就压不下来 ──
    trim_dir = seg_dir / "_trim"
    trim_dir.mkdir(exist_ok=True)
    trimmed: list[Path] = []
    heads: list[float] = []
    for p in segs:
        wav = trim_dir / (p.stem + ".wav")
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ac", "1", "-ar", "24000", str(wav)])
        if r.returncode != 0:
            raise RuntimeError(f"解码分段失败：{p.name}")
        a, z, total = _speech_bounds(wav)
        start = max(a - HEAD_KEEP, 0.0)
        end = min(z + TAIL_KEEP, total)
        if end - start < 0.3:
            start, end = 0.0, total
        out = trim_dir / (p.stem + "_t.mp3")
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ss", f"{start:.3f}",
                 "-t", f"{end - start:.3f}", "-c:a", "libmp3lame", "-q:a", "2", str(out)])
        if r.returncode != 0:
            raise RuntimeError(f"裁剪分段失败：{p.name}")
        trimmed.append(out)
        heads.append(start)
    durs = [media_duration(p) for p in trimmed]

    sil = None
    if gap > 0:
        sil = seg_dir / "_gap_silence.mp3"
        r = run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "anullsrc=r=24000:cl=mono", "-t", f"{gap:.3f}",
                 "-c:a", "libmp3lame", "-q:a", "9", str(sil)])
        if r.returncode != 0 or not sil.exists():
            raise RuntimeError("生成静音片失败")
    parts = [str(trimmed[0])]
    for p in trimmed[1:]:
        if sil is not None:
            parts.append(str(sil))
        parts.append(str(p))

    lst = seg_dir / "_reconcat.txt"
    lst.write_text("\n".join(f"file '{p}'" for p in parts), encoding="utf-8")
    mp3 = voice_dir / "voice_segmented.mp3"
    # 必须重编码：`-c copy` 拼出来的 MP3 头里没有正确时长，ffprobe 会读成第一段长度
    r = run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c:a", "libmp3lame", "-q:a", "2", str(mp3)])
    if r.returncode != 0:
        raise RuntimeError("重建配音拼接失败：" + (r.stderr or "")[:200])

    tl = json.loads((voice_dir / "voice_timeline.json").read_text(encoding="utf-8"))
    orig = {s["index"]: (float(s["start"]), float(s["end"])) for s in tl["segments"]}
    cur = 0.0
    for i, (seg, d) in enumerate(zip(tl["segments"], durs), 1):
        seg["start"] = round(cur, 3)
        seg["end"] = round(cur + d, 3)
        seg["duration"] = round(d, 3)
        cur += d + (gap if i < len(segs) else 0.0)
    tl["gap"] = gap
    tl["head_trim"] = [round(h, 3) for h in heads]
    tl["total_duration"] = round(cur, 3)
    (voice_dir / "voice_timeline.json").write_text(
        json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")

    # SRT：按「旧时间」定位每条字幕所属的段，再整体平移
    srt = voice_dir / "voice_segmented.srt"
    if srt.exists():
        def fmt(t: float) -> str:
            ms = int(round(t * 1000))
            h, ms = divmod(ms, 3600000)
            m, ms = divmod(ms, 60000)
            s, ms = divmod(ms, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        rows = []
        blocks = [b for b in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8").strip()) if b.strip()]
        for b in blocks:
            lines = b.splitlines()
            m = re.search(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
            if not m:
                continue
            a, z = _srt_sec(m.group(1)), _srt_sec(m.group(2))
            seg_i = next((i for i, (s0, s1) in orig.items()
                          if s0 - 0.01 <= a < s1 + 0.01), len(orig))
            tgt = tl["segments"][seg_i - 1]["start"]
            off = tgt - orig[seg_i][0] - heads[seg_i - 1]
            na = max(a + off, tgt)
            nz = max(z + off, na + 0.2)
            rows.append([na, nz, "\n".join(lines[2:])])
        # 去重叠：每条字幕不得越过下一条的起点（否则会触发 content_overlap）
        for i in range(len(rows) - 1):
            if rows[i][1] > rows[i + 1][0] - 0.04:
                rows[i][1] = max(rows[i + 1][0] - 0.04, rows[i][0] + 0.12)
        out = [f"{i}\n{fmt(r[0])} --> {fmt(r[1])}\n{r[2]}" for i, r in enumerate(rows, 1)]
        srt.write_text("\n\n".join(out) + "\n", encoding="utf-8")

    # 母带响度：在音轨定稿处做（此后音轨不再改动）——两遍式 loudnorm 到 −14 LUFS / TP −1.5
    ln = apply_loudnorm(mp3, compress=compress)
    if ln.get("failed"):
        print(f"      [warn] 响度归一失败（{ln.get('error')}），音轨保持原样")
    else:
        print(f"      响度: {ln['before_lufs']:.2f} → {ln['after_lufs']:.2f} LUFS | "
              f"TP {ln['before_tp']:.2f} → {ln['after_tp']:.2f} dBTP "
              f"({'合规' if ln['ok'] else '仍越界'})")
    return tl


# ── 母带响度（2026-09-17 加）─────────────────────────────
# 为什么加：用同一套分析工具测我方验收成片，得到 −21.54 LUFS / −4.1 dBTP，
# 而平台标准是约 −14 LUFS / TP ≤ −1.0 —— 我们比标准**低 7.5 dB**，播放时会被平台
# 归一化提升、动态被压，听感发闷。同批测的 4 条对标片里 3 条响度都比我们更接近标准。
# TP 取 −1.5 而不是 −1.0：hermes video_enhancer 的标定记录显示编码后会带来约
# 0.16 dB overshoot（loudnorm 标 −1.0 实测解码后 −0.84），所以留 0.5 dB 余量。
LOUDNORM_TARGET = {"I": -14.0, "TP": -1.5, "LRA": 8.0}
# 可选：先压缩再归一。实测能把响度从 −16.08 推到 −15.06 LUFS（更接近平台标准 −14），
# 但 LRA 会从 ~2 掉到 1.40（对标片 TTS 是 2.0 左右）→ 过度压平的听感风险，故默认不开。
LOUDNORM_COMPRESSOR = "acompressor=threshold=-20dB:ratio=4:attack=5:release=150,"
# 语速档位（edge-tts 速率字符串 → 实测语速，来自文件头标定表）
SPEED_PROFILES = {"talk": "+28%", "list": "+16%"}


def measure_loudness(path: Path) -> dict:
    """测整合响度/真峰值/LRA（EBU R128）。"""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "")
    return json.loads(m.group(0)) if m else {}


def apply_loudnorm(path: Path, target: dict = None, compress: bool = False) -> dict:
    """两遍式 loudnorm：先测量再应用（一遍式会因实时动态处理而漂移）。

    就地替换 path；返回 before/after 三值用于写进运行日志。
    """
    tgt = dict(LOUDNORM_TARGET if target is None else target)
    before = measure_loudness(path)
    if not before:
        return {"failed": True, "error": "测量失败"}
    # 为什么要挂一级限幅：我们的 TTS 音轨峰均比很高（实测 −24.56 LUFS 配 −4.11 dBTP
    # ≈ 20 dB crest），只做线性 loudnorm 会为了不超峰而限制增益 → 只能到 −16.08 LUFS / −0.99 dBTP。
    # 先 loudnorm 归一到目标响度，再用 alimiter 把越界的峰压回 TP 以内。
    # ⚠️ alimiter 必须显式 `level=disabled`：默认 level=true 会做自动电平归一，抵消 loudnorm 的结果
    #    （hermes video_enhancer 的标定记录里踩过这个坑）。
    pre = LOUDNORM_COMPRESSOR if compress else ""
    filt = (pre + f"loudnorm=I={tgt['I']}:TP={tgt['TP']}:LRA={tgt['LRA']}"
            f":measured_I={before['input_i']}:measured_TP={before['input_tp']}"
            f":measured_LRA={before['input_lra']}:measured_thresh={before['input_thresh']}"
            f":offset={before['target_offset']}:linear=true:print_format=summary,"
            # 注意：alimiter 的 limit 是**线性幅度**（范围 0.0625–1），不是 dB。
            # 传 dB 会被当成比值 → 报 "Value 1.18 out of range"（2026-09-17 实测踩到）。
            f"alimiter=limit={10 ** (tgt['TP'] / 20):.4f}:level=disabled")
    tmp = path.with_name(path.stem + ".norm" + path.suffix)
    r = run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af", filt,
             "-c:a", "libmp3lame", "-q:a", "2", str(tmp)])
    if r.returncode != 0 or not tmp.exists():
        return {"failed": True, "error": (r.stderr or "")[:200]}
    tmp.replace(path)
    after = measure_loudness(path)
    return {
        "before_lufs": float(before["input_i"]), "before_tp": float(before["input_tp"]),
        "after_lufs": float(after["input_i"]) if after else None,
        "after_tp": float(after["input_tp"]) if after else None,
        "target": tgt,
        "ok": bool(after) and float(after["input_tp"]) <= -1.0,
    }


def _srt_sec(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def step_timing(script: dict, timeline: dict, cues: list[dict],
                total_override: float | None = None) -> tuple[list[dict], float]:
    """② 段级时间轴按卡片分组 → 卡片时间轴 + 字幕归属。"""
    segs = timeline["segments"]
    total = float(total_override or timeline["total_duration"])
    n_lines = len(script["lines"])
    if len(segs) != n_lines:
        raise RuntimeError(f"时间轴段数 {len(segs)} ≠ 口播行数 {n_lines}")

    cards = []
    for i, c in enumerate(script["cards"]):
        f, t = int(c["from"]), int(c["to"])
        if not (1 <= f <= t <= n_lines):
            raise RuntimeError(f"卡片 {i+1} 的 from/to 越界: {f}..{t}")
        cards.append({**c, "_start": float(segs[f - 1]["start"]),
                      "_end": float(segs[t - 1]["end"]),
                      "_lines": list(range(f, t + 1))})

    # 覆盖检查：每行口播必须恰好被一张卡片覆盖
    covered: list[int] = []
    for c in cards:
        covered.extend(c["_lines"])
    if sorted(covered) != list(range(1, n_lines + 1)):
        raise RuntimeError(f"卡片未完整覆盖口播行：覆盖 {sorted(covered)} / 共 {n_lines} 行")

    # 配音先行：卡片时长由语音推出；卡片之间不留空洞，末卡收在音频末尾
    for i, c in enumerate(cards):
        c["start"] = c["_start"]
        c["duration"] = round((cards[i + 1]["_start"] if i + 1 < len(cards) else total)
                              - c["_start"], 3)
        if c["duration"] <= 0:
            raise RuntimeError(f"卡片 {i+1} 时长为负，检查 from/to 是否递增")

    # 字幕按时间归属到卡片（SRT 是口语粒度，比口播行更细）
    for c in cards:
        c["captions"] = []
    for cue in cues:
        host = next((c for c in cards
                     if c["start"] - 0.01 <= cue["start"] < c["start"] + c["duration"] - 0.01),
                    cards[-1])
        host["captions"].append({"text": cue["text"], "start": round(cue["start"], 3),
                                 "duration": round(cue["end"] - cue["start"], 3)})
    return cards, total


def main() -> int:
    ap = argparse.ArgumentParser(description="知识卡片视频编排层")
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--project", default=str(ROOT / "video-line"),
                    help="HyperFrames 项目目录（默认 code-news/video-line）")
    ap.add_argument("--voice", default=None, help="覆盖 script.json 里的 voice")
    # 段间停顿 = TAIL_KEEP(0.06s) + gap；对标样本 C 实测为 0.18–0.32s
    # （edge-tts 句末自带约 0.84s 停顿，已由 normalize_pauses 裁掉）
    ap.add_argument("--gap", type=float, default=0.16,
                    help="段间额外静音秒数；最终停顿 ≈ 0.06 + gap，默认 0.16 ≈ 0.22s")
    ap.add_argument("--rate", default=None,
                    help="TTS 语速，如 +28%%；不给则由 --speed-profile 决定（见文件头校准表）")
    # 语速档位（2026-09-17 加）：对标《只用了 Claude Code 30%能力》实测 4.84 字/秒、
    # 抖音卡片样本 5.24 —— 清单型内容比讲解型慢一档，观众需要时间读清单。
    ap.add_argument("--speed-profile", default=None, choices=("talk", "list"),
                    help="语速档位：talk=讲解型 +28%%（6.07 字/秒）；"
                         "list=清单型 +16%%（实测约 5.2 字/秒）。给了 --rate 则以 --rate 为准")
    ap.add_argument("--loudnorm-compress", action="store_true",
                    help="母带响度归一前先压缩（更接近 −14 LUFS，但 LRA 会降到约 1.4）")
    ap.add_argument("--voice-root", default=str(DEFAULT_VOICE_DIR),
                    help="voice_segmenter.py 所在目录")
    ap.add_argument("--quality", default="looks", help="draft/looks/delivery")
    ap.add_argument("--format", default="landscape",
                    choices=("landscape", "vertical"),
                    help="画幅：landscape=1440x1080（默认，历史归档画幅）；"
                         "vertical=1080x1920（视频号/抖音/小红书竖屏投放）")
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--no-check", action="store_true",
                    help="跳过渲染后的 hyperframes check 质量门")
    ap.add_argument("--skip-tts", action="store_true", help="复用 <out>/voice 下已有配音")
    ap.add_argument("--preview", type=float, default=0.0,
                    help="确认点：只渲前 N 秒（片头+第 1 章开头），看完再决定是否整片渲染")
    ap.add_argument("--preview-name", default="preview.mp4")
    args = ap.parse_args()

    if args.rate is None:                     # 未显式给 --rate → 按语速档位取
        args.rate = SPEED_PROFILES[args.speed_profile or "talk"]
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    if not script.get("lines") or not script.get("cards"):
        print("[fail] script.json 需要 lines 与 cards", file=sys.stderr)
        return 2

    for w in check_lines(script["lines"]):
        print(f"[warn] 稿件标点: {w}")
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    project = Path(args.project).resolve()

    voice = args.voice or script.get("voice", "yunjian")
    print(f"[1/4] 配音（{voice} @ {args.rate}，配音先行）")
    if args.skip_tts:
        vdir = out_dir / "voice"
        mp3, srt, timeline = (vdir / "voice_segmented.mp3", vdir / "voice_segmented.srt",
                              json.loads((vdir / "voice_timeline.json").read_text(encoding="utf-8")))
        print("      复用已有配音")
    else:
        mp3, srt, timeline = step_tts(script, out_dir, Path(args.voice_root),
                                      voice, args.gap, args.rate)
        before = timeline["total_duration"]
        timeline = normalize_pauses(out_dir / "voice", args.gap,
                                    compress=args.loudnorm_compress)
        print(f"      段间停顿重建为 {args.gap}s（拼接受损前的总长 {before}s → {timeline['total_duration']}s）")
        print(f"      {len(timeline['segments'])} 段 / 总时长 {timeline['total_duration']}s")

    total_media = media_duration(mp3)
    print("[2/4] 按语音时间轴分组卡片与字幕")
    cards, total = step_timing(script, timeline, parse_srt(srt), total_media or None)
    print(f"      音频实测总长 {total_media:.3f}s（用作合成总长，避免槽位与媒体不等长）")
    for i, c in enumerate(cards):
        print(f"      {i+1}. {c['start']:6.2f}-{c['start']+c['duration']:6.2f}s "
              f"| {len(c['captions']):2d} 条字幕 | {c.get('title','')[:20]}")

    print("[3/4] 生成 HyperFrames 合成")
    deck = {k: script[k] for k in ("series", "episode", "breadcrumb", "style") if k in script}
    deck["audio"] = "assets/voice_segmented.mp3"
    deck["format"] = args.format
    deck["cards"] = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]
    (out_dir / "cards.json").write_text(
        json.dumps(deck, ensure_ascii=False, indent=1), encoding="utf-8")
    assets = project / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mp3, assets / "voice_segmented.mp3")
    render_deck = deck
    if args.preview > 0:
        cut = min(args.preview, total)
        render_deck = make_preview(deck, mp3, cut, project)
        print(f"      [确认点] 截取前 {cut:.1f}s / {len(render_deck['cards'])} 张卡做样片")
    (project / "index.html").write_text(build_card_deck.build(render_deck), encoding="utf-8")
    print(f"      {project / 'index.html'}")

    if args.skip_render:
        print("[4/4] 跳过渲染（--skip-render）")
        return 0

    print("[4/4] HyperFrames 渲染")
    mp4 = out_dir / (args.preview_name if args.preview > 0 else "final.mp4")
    r = run([*hf_prefix(), "render", str(project), "-o", str(mp4),
             "-q", args.quality], timeout=3600)
    if r.returncode != 0 or not mp4.exists():
        print("[fail] 渲染失败：")
        print(((r.stdout or "") + (r.stderr or ""))[-1200:])
        return 5
    print(f"[done] {mp4}")

    if not args.no_check:
        print("[+1] 质量门 hyperframes check")
        ok, detail = run_check(project)
        if ok:
            print("     " + detail)
        else:
            print("     " + detail)
            print("[fail] 质量门未通过 —— 成片已生成但不合格，见上方明细")
            return 6
    if args.preview > 0:
        print("\n—— 确认点 ——")
        print("看完这段样片先定三件事：风格 / 字号 / 配音语速与节奏。")
        print("这里改一次的成本是「重渲这几十秒」；等整片渲完再改是全部重来。")
        print("确认没问题就去掉 --preview 重跑整片。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
