# -*- coding: utf-8 -*-
"""分析音效能量包络，输出起止点建议。
按 20ms 窗口算 RMS 能量，再转成「相对峰值」dB（20*log10(r/peak)，本文件峰值=0 dB），
找首个/末个超过阈值的窗口。

用法：python sfx_envelope.py <含 *.wav 的目录>
"""
import argparse
import subprocess
import array
import math
from pathlib import Path

WIN = 0.02          # 20 ms
THRESH = -50.0      # 静音阈值（相对峰值 dB，非绝对 dBFS）
TAIL = -35.0        # 拖尾阈值（相对峰值 dB，非绝对 dBFS）


def rms_envelope(path, sr=48000):
    """解码为 48k mono float32 PCM，返回 [(t_center, db)]"""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode('utf-8', 'replace')[:300])
    a = array.array('f')
    a.frombytes(p.stdout)
    n = int(WIN * sr)
    out = []
    peak = 1e-12
    for i in range(0, len(a) - n + 1, n):
        s = 0.0
        for v in a[i:i + n]:
            s += v * v
        r = (s / n) ** 0.5
        peak = max(peak, r)
        out.append((i / sr + WIN / 2, r))
    res = []
    for t, r in out:
        db = 20 * math.log10(r / peak + 1e-12) if r > 0 else -120.0
        res.append((t, db))
    return res, len(a) / sr, peak


def main():
    ap = argparse.ArgumentParser(
        description="按 20ms 窗 RMS 分析目录内音效的能量包络，输出起止点建议。")
    ap.add_argument("directory", help="含 *.wav 的目录")
    args = ap.parse_args()
    for f in sorted(Path(args.directory).glob('*.wav')):
        try:
            env, dur, peak = rms_envelope(f)
        except Exception as e:
            print(f"{f.name}: 解码失败 {e}")
            continue
        loud = [(t, d) for t, d in env if d > THRESH]
        loud2 = [(t, d) for t, d in env if d > TAIL]
        first = loud[0][0] if loud else 0
        last = loud[-1][0] if loud else dur
        l2 = loud2[-1][0] if loud2 else dur
        pk = max(env, key=lambda x: x[1])
        print(f"{f.name}")
        print(f"   总时长 {dur:.3f}s | 能量起点 {first:.2f}s | "
              f">-50dB 终点 {last:.2f}s | >-35dB 终点 {l2:.2f}s | 峰值 @ {pk[0]:.2f}s")
        # 稀疏打印包络（每约 0.3s 一个点）
        step = max(1, int(0.3 / WIN))
        line = ' '.join(f"{env[i][1]:.0f}" for i in range(0, len(env), step))
        print(f"   相对峰值 dB 包络(*0.3s): {line}")
        print()


if __name__ == '__main__':
    main()
