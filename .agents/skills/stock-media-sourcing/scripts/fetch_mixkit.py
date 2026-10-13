# -*- coding: utf-8 -*-
r"""从 Mixkit 批量下载选定的音乐 / 音效。带 Referer 绕防盗链。

用法：
    python fetch_mixkit.py <manifest.json 输出路径>
    # manifest 路径**必填**：无参数时只打印用法，不下载、不写盘（防误跑污染生产目录）
    # 落盘根目录默认 D:\AI-VIDEO\music，可用环境变量 MUSIC_ROOT 覆盖
    # 改 MUSIC / SFX 两个清单即可适配别的选曲

注意：部分音效 id 的 .wav 会返回 403（如 1143 / 788）→ 换同分类备选 id。
"""
import argparse
import os
import subprocess
import json
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

MUSIC = [
    # (id, 标题, 目标相对路径)
    # —— 批次 1（2026-10-06）——
    ("1167", "Close Up",       r"library\A_intro\close_up.mp3"),
    ("634",  "Your Breath",    r"library\B_background\your_breath.mp3"),
    ("175",  "Digital Clouds", r"library\C_transition\digital_clouds.mp3"),
    ("113",  "House Fest",     r"library\D_climax\house_fest.mp3"),
    ("587",  "Discover",       r"library\E_outro\discover.mp3"),
    # —— 批次 2（2026-10-06 扩库，5 档各 1 首备选；数据源 = 授权台账.md）——
    ("140",  "Cyberpunk City",       r"library\A_intro\cyberpunk_city.mp3"),
    ("134",  "Deep Techno Ambience", r"library\B_background\deep_techno_ambience.mp3"),
    ("130",  "Tech House vibes",     r"library\C_transition\tech_house_vibes.mp3"),
    ("726",  "Uplifting Bass",       r"library\D_climax\uplifting_bass.mp3"),
    ("543",  "A New Life",           r"library\E_outro\a_new_life.mp3"),
]

SFX = [
    # —— 批次 1（2026-10-06）——
    ("1490", "Fast whoosh transition",           r"sfx\transition_whoosh_01.wav"),
    ("175",  "Short transition sweep",           r"sfx\transition_swipe_01.wav"),
    ("3116", "Cybernetic technology affirmation", r"sfx\emphasis_ding_01.wav"),
    ("3124", "Modern technology select",          r"sfx\ui_click_01.wav"),
    ("2600", "Electricity static power up",       r"sfx\riser_build_01.wav"),
    ("498",  "Deep heartbeat impact",             r"sfx\impact_boom_01.wav"),
    ("2861", "Clear announce tones",              r"sfx\brand_logo_sting_01.wav"),
    # —— 批次 2（2026-10-06 专为 3s 级转场而补；数据源 = 授权台账.md）——
    ("1486", "Cinematic tunnel reverb woosh",    r"sfx\transition_whoosh_3s_01.wav"),
    ("2630", "Terror sweep of darkness",         r"sfx\transition_sweep_3s_01.wav"),
    ("1576", "Landing jet flying whoosh",        r"sfx\riser_build_3s_01.wav"),
    ("2909", "Cool impact movie trailer",        r"sfx\impact_trailer_01.wav"),
]
# 🔴 ID 说明（2026-10-06 带 Referer + 正常 UA 逐个实测，纠正旧说法）：
#   2719 → HTTP 200，3.55MB / 13.434s，结构是「渐强 0–7s」→ 裁了就废，**弃用**
#   2900 → HTTP 200，1.58MB / 8.973s，峰值在 4.33s → 裁了就废，**弃用**
#   1143 → HTTP 403（三个里**唯一**真 403）→ **弃用**
#   实际采用：2600（riser 替换源）/ 498（impact 替换源）/ 2861（sting 替换源）
#   ⚠️ 旧说法「2719/1143/2900 三个当初都 403」有误：2719/2900 是**下载成功但结构不符**。

ROOT = Path(os.environ.get("MUSIC_ROOT", r"D:\AI-VIDEO\music"))
REF_MUSIC = "https://mixkit.co/free-stock-music/"
REF_SFX = "https://mixkit.co/free-sound-effects/"


def dl(url, dest, referer):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 2048:
        return "skip", dest.stat().st_size, 0
    r = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", "180", "-A", UA, "-e", referer,
         "-o", str(dest), "-w", "%{http_code}", url],
        capture_output=True, text=True)
    code = r.stdout.strip()
    size = dest.stat().st_size if dest.exists() else 0
    ok = code in ("200", "206") and size > 2048
    return ("ok" if ok else "FAIL"), size, code


def main():
    # 🔴 参数解析必须放在任何副作用（下载 / 写盘）之前。
    ap = argparse.ArgumentParser(
        description="从 Mixkit 批量下载选定的音乐 / 音效（清单内置）。")
    ap.add_argument("manifest",
                    help="manifest JSON 输出路径（必填；无参数只打印用法，不下载、不写盘）")
    args = ap.parse_args()
    manifest_path = Path(args.manifest)

    manifest = []
    jobs = []
    for iid, title, rel in MUSIC:
        jobs.append(("music", iid, title, rel,
                     f"https://assets.mixkit.co/music/{iid}/{iid}.mp3", REF_MUSIC))
    for iid, title, rel in SFX:
        jobs.append(("sfx", iid, title, rel,
                     f"https://assets.mixkit.co/active_storage/sfx/{iid}/{iid}.wav", REF_SFX))

    print(f"落盘根目录：{ROOT}")
    print(f"清单：{len(MUSIC)} 音乐 + {len(SFX)} 音效 = {len(jobs)} 个；"
          f"manifest 将写入：{manifest_path}")
    for kind, iid, title, rel, url, ref in jobs:
        dest = ROOT / rel
        status, size, code = dl(url, dest, ref)
        print(f"[{status:>4}] {kind:>5} {iid:>5} {size:>10,}B http={code}  {rel}")
        manifest.append({"kind": kind, "id": iid, "title": title,
                         "rel": rel, "url": url, "status": status, "size": size})

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    bad = [m for m in manifest if m["status"] == "FAIL"]
    print(f"\n共 {len(manifest)} 个，失败 {len(bad)} 个")
    for b in bad:
        print("  FAIL:", b["rel"], b["url"])


if __name__ == "__main__":
    main()
