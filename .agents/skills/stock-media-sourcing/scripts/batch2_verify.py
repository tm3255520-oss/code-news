# -*- coding: utf-8 -*-
r"""batch2_verify.py — 第二批素材验收（解码 / 尾部性质 / 可闻长度 / 电平 / 格式）

判据（与 ACE-Step「只填 70%」缺陷区分开）：
  - 尾部静音是**淡出**（逐窗单调下降）→ 正常，属音乐结构
  - 尾部静音是**数字静音**（直接掉到 —120 / 精确 0）→ 缺陷，该文件只可用前段
  - **可闻长度 M ≥ 3× 成片目标**（默认 28.25s → 阈值 84.75s），否则会被循环拼接、接缝听得见

用法：python batch2_verify.py [--root <music 根>] [--target <成片时长秒>]
      根目录默认 D:\AI-VIDEO\music，可用环境变量 MUSIC_ROOT 覆盖
"""
import argparse
import json
import math
import os
import struct
import subprocess
import sys
from pathlib import Path

FFMPEG = r"C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"

NEW_BGM = [
    r"A_intro\cyberpunk_city.mp3",
    r"B_background\deep_techno_ambience.mp3",
    r"C_transition\tech_house_vibes.mp3",
    r"D_climax\uplifting_bass.mp3",
    r"E_outro\a_new_life.mp3",
]
OLD_BGM = [
    r"A_intro\close_up.mp3", r"B_background\your_breath.mp3",
    r"C_transition\digital_clouds.mp3", r"D_climax\house_fest.mp3",
    r"E_outro\discover.mp3",
]
NEW_SFX = ["transition_whoosh_3s_01.wav", "transition_sweep_3s_01.wav",
           "riser_build_3s_01.wav", "impact_trailer_01.wav"]
OLD_SFX = ["transition_whoosh_01.wav", "transition_swipe_01.wav",
           "emphasis_ding_01.wav", "ui_click_01.wav", "riser_build_01.wav",
           "impact_boom_01.wav", "brand_logo_sting_01.wav"]

sys.stdout.reconfigure(encoding="utf-8")


def probe(p):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=sample_rate,channels,codec_name",
                        "-show_entries", "format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    return (float(d.get("format", {}).get("duration", 0) or 0),
            int(st.get("sample_rate", 0) or 0), int(st.get("channels", 0) or 0),
            st.get("codec_name", ""))


def pcm(p, sr=16000, mono=True):
    cmd = [FFMPEG, "-v", "error", "-i", str(p)]
    if mono:
        cmd += ["-ac", "1"]
    cmd += ["-ar", str(sr), "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=1800)
    raw = r.stdout or b""
    n = len(raw) // 2
    return struct.unpack("<%dh" % n, raw[:n * 2]), sr


def all_windows(p, win=1.0, sr=16000):
    """返回 (整片逐 1s 窗 RMS(dBFS) 列表, 文件时长s)。"""
    s, sr = pcm(p, sr)
    k = int(sr * win)
    out = []
    for i in range(0, len(s) - k + 1, k):
        seg = s[i:i + k]
        rms = math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768.0
        out.append(round(20 * math.log10(rms), 1) if rms > 0 else -200.0)
    return out, len(s) / sr


def audible_length(windows, win=1.0, thr=-55.0):
    """可闻长度 M：最后一个 ≥ thr 的窗的结束时间（秒）。"""
    last = 0.0
    for i, v in enumerate(windows):
        if v >= thr:
            last = (i + 1) * win
    return last


def max_volume(p):
    r = subprocess.run([FFMPEG, "-i", str(p), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    out = (r.stderr or "") + (r.stdout or "")
    mv = [l.split("max_volume:")[1].strip() for l in out.splitlines() if "max_volume:" in l]
    return mv[0] if mv else "?"


def lufs(p):
    r = subprocess.run([FFMPEG, "-i", str(p), "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    out = (r.stderr or "") + (r.stdout or "")
    lines = out.splitlines()
    for i, l in enumerate(lines):
        if "Integrated loudness" in l:
            for j in range(i, min(i + 4, len(lines))):
                if "I:" in lines[j]:
                    return lines[j].split("I:")[1].strip().split()[0]
    return "?"


def main():
    ap = argparse.ArgumentParser(description="第二批素材验收（格式 / 尾部 / 可闻长度 / 电平）")
    ap.add_argument("--root", default=os.environ.get("MUSIC_ROOT", r"D:\AI-VIDEO\music"),
                    help="music 根目录（默认 D:\\AI-VIDEO\\music，或环境变量 MUSIC_ROOT）")
    ap.add_argument("--target", type=float, default=28.25,
                    help="成片目标时长（秒），判据 M ≥ 3×target（默认 28.25）")
    args = ap.parse_args()
    LIB = Path(args.root) / "library"
    SFX = Path(args.root) / "sfx"
    need = 3 * args.target

    print(f"根目录：{args.root} ｜ 成片目标 {args.target}s → 可闻长度 M 须 ≥ {need:.2f}s")
    print("=" * 108)
    print("BGM 验收（新 5 首 + 旧 5 首）")
    print("=" * 108)
    print(f"{'文件':<40}{'时长':>9}{'采样':>7}{'声道':>5}{'LUFS':>8}{'峰值dB':>8}{'可闻M':>9}  尾部性质")
    m_bad = []
    for rel in OLD_BGM + NEW_BGM:
        p = LIB / rel
        if not p.exists():
            print(f"{rel:<40}  [MISS]")
            continue
        d, sr, ch, codec = probe(p)
        allw, _ = all_windows(p, win=1.0)
        tw = allw[-14:]
        M = audible_length(allw, win=1.0)
        # 尾部性质：从尾部往回找第一个 ≥ -55 的窗，再看其后是逐步下降还是直接腰斩
        tail_sil = 0
        for v in reversed(tw):
            if v < -55.0:
                tail_sil += 1
            else:
                break
        # 紧邻静音之前的 3 个窗是否单调下降
        idx = len(tw) - tail_sil - 1
        pre = tw[max(0, idx - 2):idx + 1]
        monotone = all(pre[i] >= pre[i + 1] - 1.0 for i in range(len(pre) - 1)) if len(pre) > 1 else False
        if tail_sil <= 0:
            kind = "无静音"
        elif monotone and pre and pre[-1] > -60:
            kind = f"淡出（前 {len(pre)} 窗 {pre[0]:.0f}→{pre[-1]:.0f} dB）"
        else:
            kind = f"🔴 疑似数字静音（末尾 {tail_sil}s，前窗 {pre}）"
        if M < need:
            kind += f"  🔴 可闻长度不足（M={M:.2f}s < {need:.2f}s）"
            m_bad.append(rel)
        tag = "旧" if rel in OLD_BGM else "新"
        print(f"[{tag}] {rel:<36}{d:>9.3f}{sr:>7}{ch:>5}{lufs(p):>8}{max_volume(p):>8}{M:>9.2f}  {kind}")

    print()
    print("=" * 108)
    print("音效验收（新 4 个 + 旧 7 个）")
    print("=" * 108)
    print(f"{'文件':<34}{'时长':>9}{'采样':>7}{'声道':>5}{'格式':>7}{'峰值dB':>8}")
    bad = []
    for name in OLD_SFX + NEW_SFX:
        p = SFX / name
        if not p.exists():
            print(f"{name:<34}  [MISS]")
            bad.append(name)
            continue
        d, sr, ch, codec = probe(p)
        tag = "旧" if name in OLD_SFX else "新"
        okfmt = (sr == 48000 and ch == 2 and codec == "pcm_s16le")
        if not okfmt:
            bad.append(name)
        print(f"[{tag}] {name:<29}{d:>9.3f}{sr:>7}{ch:>5}{codec:>7}{max_volume(p):>8}"
              + ("" if okfmt else "  🔴 格式不符（需 48000/2/pcm_s16le）"))
    print()
    print(f"格式不合格：{len(bad)} 个 {bad if bad else ''}")
    print(f"可闻长度不足（M < {need:.2f}s）：{len(m_bad)} 个 {m_bad if m_bad else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
