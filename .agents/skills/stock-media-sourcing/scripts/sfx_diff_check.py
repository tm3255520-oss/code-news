# -*- coding: utf-8 -*-
r"""sfx_diff_check.py — 用 A/B 差分证明「音效真的进了成片」

原理：A（含音效）与 B（--no-sfx）**除音效外完全同源**（同一 BGM/旁白/ducking），
      且比较的是 loudnorm **之前**的原始混音 → A−B 的残差就是音效轨本身。
      因此残差的每窗 RMS 包络，应当精确复现各锚点的起点与时长。

用法：python sfx_diff_check.py <A.wav> <B.wav> 2.5 4.0 ...
      锚点写法两种都接受：裸秒数 `2.5` 或 `anchor=2.5`。
"""
import argparse
import math
import struct
import subprocess
from pathlib import Path

FFMPEG = r"C:/ffmpeg/bin/ffmpeg.exe"
if not Path(FFMPEG).exists():
    FFMPEG = "ffmpeg"          # 与其它脚本一致：依赖 PATH 兜底
SR = 48000


def parse_anchor(x):
    """接受 '2.5' 与 'anchor=2.5' 两种写法。"""
    return float(x.split("=", 1)[1]) if "=" in x else float(x)


def pcm(p):
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(p),
                        "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True, timeout=1800)
    raw = r.stdout or b""
    n = len(raw) // 2
    return struct.unpack("<%dh" % n, raw[:n * 2])


def rms_db(seg):
    if not seg:
        return -200.0
    r = math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768.0
    return 20 * math.log10(r) if r > 0 else -200.0


def main():
    ap = argparse.ArgumentParser(
        description="用 A/B 差分（A−B）证明音效真的进了成片。")
    ap.add_argument("a", help="A.wav（含音效）")
    ap.add_argument("b", help="B.wav（--no-sfx）")
    ap.add_argument("anchors", nargs="*", type=parse_anchor,
                    help="音效锚点秒数，可写 2.5 或 anchor=2.5（可多个）")
    args = ap.parse_args()

    a, b = Path(args.a), Path(args.b)
    anchors = args.anchors
    sa, sb = pcm(a), pcm(b)
    n = min(len(sa), len(sb))
    diff = [sa[i] - sb[i] for i in range(n)]
    print(f"A={a.name}  B={b.name}  共 {n / SR:.4f}s  （两者采样数 {len(sa)} / {len(sb)}）")

    win = 0.25
    k = int(SR * win)
    print()
    print("== 残差（A−B）逐 0.25s 窗 RMS，只列 ≥ -78 dB 的窗 ==")
    rows = []
    for i in range(0, n - k + 1, k):
        db = rms_db(diff[i:i + k])
        if db >= -78.0:
            rows.append((i / SR, i / SR + win, db))

    # 归并连续窗成「事件段」
    events = []
    for t0, t1, db in rows:
        if events and abs(t0 - events[-1][1]) < 1e-6:
            events[-1][1] = t1
            events[-1][2] = max(events[-1][2], db)
        else:
            events.append([t0, t1, db])
    print(f"{'起点':>8}{'终点':>9}{'时长':>8}{'峰值窗dB':>11}")
    for t0, t1, db in events:
        print(f"{t0:>8.2f}{t1:>9.2f}{t1 - t0:>8.2f}{db:>11.1f}")

    print()
    print("== 锚点核对 ==")
    for at in anchors:
        i0 = int(at * SR)
        i1 = min(n, int((at + 0.6) * SR))
        near = rms_db(diff[max(0, i0 - int(0.1 * SR)):i1])
        # 取整段（到下一锚点或 +3.5s）
        i2 = min(n, int((at + 3.5) * SR))
        whole = rms_db(diff[i0:i2])
        print(f"锚点 {at:>7.3f}s ｜ 起点 0.6s 内 {near:>6.1f} dB ｜ 该点后 3.5s {whole:>6.1f} dB")

    print()
    print("== 对照：全片残差总能量 ==")
    print(f"整片残差 RMS = {rms_db(diff):.1f} dB ｜ A 整片 = {rms_db(sa[:n]):.1f} dB "
          f"｜ B 整片 = {rms_db(sb[:n]):.1f} dB")


if __name__ == "__main__":
    main()
