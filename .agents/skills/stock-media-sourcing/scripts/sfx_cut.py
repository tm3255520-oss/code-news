# -*- coding: utf-8 -*-
r"""按能量包络数据裁剪音效，统一为 48kHz / stereo / pcm_s16le。

用法：
    python sfx_cut.py                        # 🔴 默认 dry-run：只打印计划，不落盘
    python sfx_cut.py --apply                # 真正落盘（跑完 JOBS）
    python sfx_cut.py --apply --replace SRC NAME   # 覆盖某条替换源（可重复）
    # 目标根目录默认 D:\AI-VIDEO\music\sfx，可用环境变量 SFX_ROOT 覆盖
    # 替换源默认在 <SFX_ROOT>\..\_staging\（相对路径），也可给绝对路径

原始完整版保存在 <SFX_ROOT>\_raw\，成品落在 <SFX_ROOT>\。
改 JOBS / REPLACE 即可适配别的音效清单。

🔴 防呆：无 --apply 时**不写任何文件**（含不写 _raw）。
   历史上「无参数直接静默覆写 _raw」是 fail-open 设计，已改为 fail-safe。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SFX_ROOT", r"D:\AI-VIDEO\music\sfx"))
RAW = ROOT / "_raw"
STAGE = ROOT.parent / "_staging"

# 备选替换源：下载到但「结构不符」的原始档，用同分类候选替换后再裁。
# (候选源文件, _raw 目标名)。源文件默认在 STAGE；不存在则跳过
# （_raw 里通常已是可用原始档，无需替换）。
# 🔴 实测（2026-10-06）：2600/498/2861 = 第一批实际采用的替换源；
#    2719(13.43s 渐强型)/2900(8.97s 峰值在 4.33s) 可下载但结构不符、已弃用，
#    1143 实测 403。原 argv 版漏了 impact_boom_01（498），故补进常量。
REPLACE = [
    ("2600_electricity_static_power_up.wav", "riser_build_01"),
    ("498_deep_heartbeat_impact.wav",        "impact_boom_01"),
    ("2861_clear_announce_tones.wav",        "brand_logo_sting_01"),
]

# (文件名, 起点, 总长, 淡入, 淡出)
# 批次 1（7 条）+ 批次 2（4 条，2026-10-06 专为 3s 级转场而补）。
# 批次 2 的起点/淡入/淡出均由 _raw 能量包络实测推导，并用 md5 对照生产成品验证。
JOBS = [
    ("transition_whoosh_01", 0.00, 0.80, 0.01, 0.15),
    ("transition_swipe_01",  0.13, 0.47, 0.01, 0.10),
    ("emphasis_ding_01",     0.00, 0.70, 0.00, 0.25),
    ("ui_click_01",          0.00, 0.15, 0.00, 0.05),
    ("riser_build_01",       0.00, 1.70, 0.02, 0.30),
    ("impact_boom_01",       0.00, 1.40, 0.00, 0.35),
    ("brand_logo_sting_01",  0.07, 1.95, 0.01, 0.35),
    # —— 批次 2（3s 级转场，2026-10-06）——
    ("transition_whoosh_3s_01", 0.00, 3.00, 0.00, 0.60),
    ("transition_sweep_3s_01",  0.00, 3.00, 0.05, 0.50),
    ("riser_build_3s_01",       0.15, 3.00, 0.05, 0.15),
    ("impact_trailer_01",       0.00, 1.50, 0.00, 0.30),
]


def cut(name, ss, dur, fi, fo):
    src = RAW / f"{name}.wav"
    dst = ROOT / f"{name}.wav"
    if not src.exists():
        print(f"  [MISS] {src}")
        return False
    chain = [f"atrim=start={ss}:duration={dur}", "asetpts=N/SR/TB"]
    if fi > 0:
        chain.append(f"afade=t=in:st=0:d={fi}")
    if fo > 0:
        chain.append(f"afade=t=out:st={dur - fo}:d={fo}")
    chain.append("aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src),
           "-af", ",".join(chain), "-c:a", "pcm_s16le", str(dst)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  [FAIL] {name}: {r.stderr.decode('utf-8','replace')[:200]}")
        return False
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", str(dst)],
                       capture_output=True, text=True).stdout.strip()
    print(f"  [ok] {name}.wav  {float(d):.3f}s  {dst.stat().st_size:,}B")
    return True


def resolve(item):
    """(候选源, _raw 目标名) → (源 Path, 目标 Path)。"""
    src, name = item
    s = Path(src)
    if not s.is_absolute():
        s = STAGE / src
    return s, RAW / f"{name}.wav"


def apply_replace(items):
    """把替换源拷进 _raw（源不存在则跳过，不报错）。"""
    for item in items:
        s, d = resolve(item)
        if s.exists():
            d.write_bytes(s.read_bytes())
            print(f"  [raw] {d.name} <- {s.name} ({d.stat().st_size:,}B)")
        else:
            print(f"  [skip] 无替换源 {s} —— 沿用 _raw 现有 {d.name}")


def dry_run(items):
    """只打印计划，绝不落盘。"""
    print("--- 替换源 ---")
    for item in items:
        s, d = resolve(item)
        if s.exists():
            print(f"  [raw] 将写 {d}  <- {s}")
        else:
            print(f"  [skip] 无替换源 {s} —— 沿用 _raw 现有 {d.name}")
    print(f"--- 裁剪（{len(JOBS)} 个）---")
    miss = 0
    for name, ss, dur, fi, fo in JOBS:
        src = RAW / f"{name}.wav"
        dst = ROOT / f"{name}.wav"
        tag = "" if src.exists() else "  [MISS 源]"
        if not src.exists():
            miss += 1
        print(f"  将写 {dst}  (ss={ss} dur={dur} fi={fi} fo={fo}){tag}")
    print(f"\nDRY-RUN 结束：以上 {len(JOBS)} 个成品**未**写入"
          + (f"（其中 {miss} 个缺源）" if miss else "")
          + "。真写请加 --apply。")


def main():
    ap = argparse.ArgumentParser(
        description="按能量包络裁剪音效（默认 dry-run，--apply 才落盘）。")
    ap.add_argument("--apply", action="store_true",
                    help="真正落盘；不加此开关 = dry-run（只打印计划，不写盘）")
    ap.add_argument("--replace", nargs=2, action="append", metavar=("SRC", "NAME"),
                    help="覆盖替换源（可重复）：SRC 为候选文件，NAME 为 _raw 目标名")
    args = ap.parse_args()

    items = args.replace if args.replace else REPLACE
    print(f"输出根目录：{ROOT}")
    print(f"原始档目录：{RAW}")
    print(f"替换源目录：{STAGE}")

    if not args.apply:
        print("\n=== DRY-RUN（未加 --apply，不会写任何文件）===")
        dry_run(items)
        return 0

    print("\n=== APPLY：开始落盘 ===")
    print("--- 替换结构不符的原始档 ---")
    apply_replace(items)
    print("--- 裁剪 ---")
    ok = sum(cut(*j) for j in JOBS)
    print(f"\n完成 {ok}/{len(JOBS)}")
    return 0 if ok == len(JOBS) else 1


if __name__ == "__main__":
    sys.exit(main())
