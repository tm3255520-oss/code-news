#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_video_link.py — 一条命令跑完"链接/文件 → 视频 → 六组证据 → 报告骨架"。

为什么要有它（2026-09-17 决定）：此前要手工分四步敲命令（取视频 / 取证 / 抽帧 / 写报告），
漏一步就少一组证据，且报告结构靠人记。本脚本只做**编排**，不重复实现任何能力：
  ① 取视频   → fetch_video_with_browser.py（redfox 通用解析优先，失败降级浏览器）
  ② 取证     → analyze_video_production.py（A/B/C/D/E/H/F/F2/G 全部组）
  ③ 抽帧     → ffmpeg（contact sheet + 关键帧，命令与 frame-sampling.md 一致）
  ④ 报告骨架 → video_production_report.py（确定性数字自动填，判断节留空）

用法：
    python scripts/analyze_video_link.py "<链接或本地视频>" --out <目录> [--title T]
    python scripts/analyze_video_link.py --regress [--regress-dir <技能 regression 目录>]
      --regress：跑回归用例并与基线比对（用例见技能 regression/cases.json）
退出码：0 成功；1 回归不通过；2 参数/依赖问题。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
SKILL = REPO / ".agents" / "skills" / "video-production-analysis"
DEFAULT_REGRESSION = SKILL / "regression"

# 回归容差（口径：数字应稳定，但 whisper/OCR/编码器有微小抖动）
TOLERANCE = {
    "scene_tight": 0, "scene_loose": 0, "cut_sample": 1,
    "median_shot_s": 0.15, "cut_coverage": 0.05, "median_deviation_s": 0.05,
    "speed_cps": 0.35, "integrated_lufs": 0.5, "true_peak_dbtp": 0.5,
    "tier1_px": 6.0,
}


def run(cmd: list, label: str) -> int:
    print(f"\n=== {label}\n    $ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-4:]
    for l in tail:
        print(f"    {l}")
    if r.returncode != 0:
        print(f"    [warn] 退出码 {r.returncode}；stderr 末行："
              f"{(r.stderr or '').strip().splitlines()[-1][:120] if r.stderr else '—'}")
    return r.returncode


def fetch_video(target: str, out_dir: Path) -> tuple:
    """"返回 (视频路径, 是否成功)。本地文件直接用；链接走取视频脚本。"""
    p = Path(target)
    if p.exists():
        return p.resolve(), True
    rc = run([sys.executable, str(SCRIPTS / "fetch_video_with_browser.py"),
              target, str(out_dir)], "① 取视频（redfox 优先 → 浏览器降级）")
    vid = out_dir / "video.mp4"
    return vid, rc == 0 and vid.exists()


def make_frames(video: Path, out_dir: Path) -> None:
    """抽帧：contact sheet + 关键帧。命令与 references/frame-sampling.md 一致。"""
    fdir = out_dir / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    if not ff:
        print("    [warn] 无 ffmpeg，跳过抽帧")
        return
    print("\n=== ③ 抽帧（contact sheet + 关键帧）")
    subprocess.run([ff, "-v", "error", "-y", "-i", str(video), "-vf",
                    "fps=1/3,scale=150:-1", str(fdir / "f_%03d.jpg")],
                   capture_output=True)
    subprocess.run([ff, "-v", "error", "-y", "-i", str(fdir / "f_%03d.jpg"),
                    "-vf", "scale=150:-1,tile=6x3", "-frames:v", "1",
                    str(out_dir / "contact_sheet.jpg")], capture_output=True)
    n = len(list(fdir.glob("f_*.jpg")))
    print(f"    frames/ {n} 张 + contact_sheet.jpg")


def one(target: str, out_dir: Path, title: str = None,
        whisper: str = "large-v3-turbo", report: bool = True) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    video, ok = fetch_video(target, out_dir)
    if not ok:
        print("[fail] 取视频失败（输入层失败，如实报告，不要继续）")
        return 2
    rc = run([sys.executable, str(SCRIPTS / "analyze_video_production.py"),
              str(video), "--out", str(out_dir), "--whisper-model", whisper],
             "② 取证（A/B/C/D/E/H/F/F2/G）")
    if rc != 0:
        print("[fail] 取证失败")
        return 2
    make_frames(video, out_dir)
    if report:
        cmd = [sys.executable, str(SCRIPTS / "video_production_report.py"), str(out_dir)]
        if title:
            cmd += ["--title", title]
        cmd += ["--source", target]
        run(cmd, "④ 报告骨架（第六/七/八节待人写）")
    print(f"\n[done] 产物目录：{out_dir}")
    return 0


def regress(reg_dir: Path) -> int:
    cases_file = reg_dir / "cases.json"
    if not cases_file.exists():
        print(f"[fail] 找不到 {cases_file}")
        return 2
    cases = json.loads(cases_file.read_text(encoding="utf-8"))
    results, total, passed = [], 0, 0
    for c in cases:
        src = c.get("local") if Path(c.get("local", "")).exists() else c["link"]
        # 运行产物写仓库 .tmp/（.gitignore 已忽略），不要落在技能目录里——
        # 技能目录是入库的，回归的中间帧/音频会污染 git（第一次实跑就踩到）。
        work = REPO / ".tmp" / "video-analysis-regression" / c["name"]
        work.mkdir(parents=True, exist_ok=True)
        print(f"\n########## 回归用例：{c['name']}（{c['title']}）")
        if one(src, work, title=c["title"], report=False) != 0:
            results.append((c["name"], "运行失败", "", "", ""))
            total += 1
            continue
        got = json.loads((work / "production_analysis.json").read_text(encoding="utf-8"))
        exp = c["expected"]
        B, D, C, Lo, F2 = (got["B_shots"], got["D_coupling"], got["C_transcript"],
                           got.get("H_loudness", {}), got.get("F2_layout", {}))
        dur = got["A_technical"].get("duration_s") or 0
        cjk = sum(1 for ch in (C.get("full_text") or "") if "\u4e00" <= ch <= "\u9fff")
        actual = {
            "video_class": B.get("video_class"),
            "scene_tight": (B.get("scene_count_range") or [None, None])[0],
            "scene_loose": (B.get("scene_count_range") or [None, None])[1],
            "median_shot_s": B.get("median_shot_s"),
            "cut_sample": D.get("cut_sample"),
            "cut_coverage": D.get("cut_coverage"),
            "median_deviation_s": D.get("median_deviation_s"),
            "speed_cps": round(cjk / dur, 2) if dur else None,
            "integrated_lufs": Lo.get("integrated_lufs"),
            "true_peak_dbtp": Lo.get("true_peak_dbtp"),
            "tier1_px": (F2.get("type_tiers_px") or [{}])[0].get("h_px"),
        }
        for k, e in exp.items():
            if k in ("accent_hex",):
                continue
            a = actual.get(k)
            if e is None or a is None:
                results.append((c["name"], k, e, a, "SKIP")); continue
            total += 1
            if isinstance(e, str) or k == "video_class":
                ok = (a == e)
            else:
                ok = abs(float(a) - float(e)) <= TOLERANCE.get(k, 0)
            results.append((c["name"], k, e, a, "PASS" if ok else "FAIL"))
            passed += 1 if ok else 0
    print("\n########## 回归结果")
    print(f"{'用例':<10}{'指标':<20}{'期望':<14}{'实测':<14}结果")
    for r in results:
        print(f"{r[0]:<10}{r[1]:<20}{str(r[2]):<14}{str(r[3]):<14}{r[4]}")
    print(f"\n合计 {passed}/{total} 通过"
          + ("（有 SKIP：基线缺该指标）" if any(r[4] == 'SKIP' for r in results) else ""))
    return 0 if passed == total and total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="链接 → 视频 → 六组证据 → 报告骨架（薄编排）")
    ap.add_argument("target", nargs="?", help="链接或本地视频文件")
    ap.add_argument("--out", default=None, help="产物目录")
    ap.add_argument("--title", default=None)
    ap.add_argument("--whisper-model", default="large-v3-turbo")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--regress", action="store_true", help="跑回归用例（与基线比对）")
    ap.add_argument("--regress-dir", default=str(DEFAULT_REGRESSION))
    args = ap.parse_args()

    if args.regress:
        return regress(Path(args.regress_dir))
    if not args.target:
        ap.error("给链接或本地视频路径，或用 --regress")
    out = Path(args.out) if args.out else (REPO / ".tmp" / "video-analysis-run")
    return one(args.target, out.resolve(), args.title, args.whisper_model,
               not args.no_report)


if __name__ == "__main__":
    raise SystemExit(main())
