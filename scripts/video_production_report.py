#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video_production_report.py — 把 production_analysis.json 生成人读版报告骨架。

为什么要有它（2026-09-17 决定）：
  1. 报告此前全靠手写，结构会漂移，同一批数字两次写出来可能不一样；
  2. 确定性数字（六组 + H + F2）已经全在 JSON 里，不该再由模型抄一遍（会抄错）；
  3. 报告最容易缺的是"收口"——写完就停，不落成产线改动项。本生成器把
     「差距对照 + 单一推荐」设为**必填尾节**，并在 `--check` 模式下拒收缺尾节的报告。

标签口径借用产线 `card_quality_check.py` 的三档（术语统一，避免两套说法）：
  【实测】  = 有确定性测量支撑（脚本算出来的）
  【判断】  = 模型的解读/推断，不是测量
  【待标定】= 还没有依据，只报数不判

用法：
    python scripts/video_production_report.py <工作目录> [--title T] [--source S]
    python scripts/video_production_report.py --check <报告.md>      # 校验必填节
退出码：0 正常；1 校验不通过；2 输入缺失。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_SECTIONS = ("## 八、差距对照与单一推荐", "## 六、工具推断", "## 七、可迁移工艺")


def _fmt(v, unit: str = "", nd: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{round(v, nd)}{unit}"
    return f"{v}{unit}"


def _load(work: Path) -> tuple:
    j = work / "production_analysis.json"
    if not j.exists():
        print(f"[fail] 找不到 {j}")
        raise SystemExit(2)
    data = json.loads(j.read_text(encoding="utf-8"))
    meta = {}
    m = work / "meta.json"
    if m.exists():
        try:
            meta = json.loads(m.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    return data, meta


def build_report(data: dict, meta: dict, work: Path, title: str, source: str) -> str:
    A = data.get("A_technical") or {}
    B = data.get("B_shots") or {}
    C = data.get("C_transcript") or {}
    D = data.get("D_coupling") or {}
    E = data.get("E_voice") or {}
    Lo = data.get("H_loudness") or {}
    F = data.get("F_palette") or {}
    F2 = data.get("F2_layout") or {}
    G = data.get("G_provenance") or {}
    form = data.get("form") or {}

    cjk = sum(1 for ch in (C.get("full_text") or "") if "\u4e00" <= ch <= "\u9fff")
    dur = A.get("duration_s") or 0
    speed = round(cjk / dur, 2) if dur else None

    L = []
    L.append(f"# 制作分析报告：{title}")
    L.append("")
    L.append(f"> 分析时间：{__import__('datetime').date.today().isoformat()}　来源：{source or '—'}"
             f"　时长：{_fmt(dur, 's')}")
    L.append(f"> 取证：`scripts/analyze_video_production.py`（whisper `{C.get('model', '—')}`）"
             f"　证据级别标注：见文末说明")
    L.append("")
    L.append("## 一行结论")
    L.append("")
    L.append(f"【判断·待复核】{form.get('verdict', '—')} ＋ "
             f"{D.get('inferred_production_order', '（制作顺序未判）')}。"
             f"（这一行由脚本按确定性结论拼出，仍需作者复核措辞）")
    L.append("")
    L.append("## 一、技术指纹【实测】")
    L.append("")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append(f"| 分辨率 / 帧率 | {A.get('width')}×{A.get('height')} / {_fmt(A.get('fps'))} fps |")
    L.append(f"| 视频编码 / 码率 | {A.get('video_codec')} / {_fmt(A.get('video_bitrate_kbps'), ' kbps', 0)} |")
    L.append(f"| 音频编码 / 码率 | {A.get('audio_codec')} / {_fmt(A.get('audio_bitrate_kbps'), ' kbps', 0)} |")
    L.append(f"| 每像素每帧码率 | {_fmt(form.get('bits_per_pixel_per_frame'), '', 5)} |")
    L.append(f"| 形态判据 | {'；'.join(form.get('basis') or []) or '—'} |")
    L.append("")
    L.append("## 二、场景节奏【实测】")
    L.append("")
    rng = B.get("scene_count_range") or [None, None]
    L.append(f"- 片型：**{B.get('video_class', '—')}**（判据：{B.get('scene_metric', '—')}）")
    L.append(f"- 场景数：**{rng[0]}–{rng[1]}**（严–宽口径）｜口径分布：{B.get('counts_by_criteria')}")
    L.append(f"- 硬切 {B.get('hard_cut_count')} / 淡变 {B.get('fade_count')}｜"
             f"中位镜头 {_fmt(B.get('median_shot_s'), 's')}｜静止占比 {B.get('static_shot_ratio')}")
    L.append(f"- ⚠️ 场景数是**口径依赖量**，引用必须带口径（见 reading-guide 的 B 组口径表）")
    L.append("")
    L.append("## 三、制作顺序【实测】")
    L.append("")
    L.append(f"- 切点命中句首：{D.get('aligned_cuts')}/{D.get('total_cuts')}"
             f" = {D.get('cut_coverage')}，中位偏差 {_fmt(D.get('median_deviation_s'), 's')}")
    L.append(f"- 样本量 `cut_sample` = {D.get('cut_sample')}｜置信 `{D.get('sample_confidence')}`"
             f"（门槛：<{D.get('min_cuts_weak')} 证据不足 / <{D.get('min_cuts_required')} 低置信）")
    L.append(f"- **结论**：{D.get('inferred_production_order', '—')}")
    L.append("")
    L.append("## 四、配音与母带【实测】")
    L.append("")
    L.append(f"- 配音类型：{E.get('verdict', '—')}（停顿 ≥0.25s 共 {E.get('pause_count_ge_0.25s')} 次，"
             f"动态范围 {_fmt(E.get('dynamic_range_db'), ' dB', 1)}）｜{E.get('caveat', '')}")
    L.append(f"- 语速：**{_fmt(speed, ' 字/秒')}**（{cjk} 字 / {_fmt(dur, 's')}）"
             f"｜对标锚点：5.24（清单型）/ 6.07（讲解型）")
    if Lo.get("failed"):
        L.append(f"- 响度：【待标定】未产出（{Lo.get('error')}）")
    else:
        L.append(f"- 响度：**{_fmt(Lo.get('integrated_lufs'), ' LUFS')}** / 真峰值 "
                 f"**{_fmt(Lo.get('true_peak_dbtp'), ' dBTP')}** / LRA {_fmt(Lo.get('lra_lu'), ' LU')}"
                 f"｜{Lo.get('verdict')}（基准 −14 LUFS / ≤ −1.0 dBTP）")
    L.append("")
    L.append("## 五、视觉规范【实测】")
    L.append("")
    if not F.get("failed"):
        cols = " ".join(f"{c['hex']}({c['share']:.0%})" for c in (F.get("dominant_colors") or [])[:4])
        L.append(f"- 主色：{F.get('scheme')} {cols}｜暗色像素占比 {F.get('dark_pixel_ratio')}")
    else:
        L.append(f"- 主色：【待标定】未产出（{F.get('error')}）")
    if F2.get("failed"):
        L.append(f"- 版式/字号：【待标定】未产出（{F2.get('error')}）")
    else:
        tiers = " / ".join(f"{t['h_px']}px×{t['blocks']}" for t in (F2.get("type_tiers_px") or [])[:5])
        bands = ", ".join(f"{b['band']}({b['blocks']})" for b in (F2.get("y_dense_bands") or [])[:5])
        ac = F2.get("accent_color") or {}
        L.append(f"- 字号档：{tiers}（OCR 帧数 {F2.get('ocr_frames')}，散点 {F2.get('type_tiers_ungrouped')}）")
        L.append(f"- 纵向密集带：{bands or '无（y 分布准连续）'}")
        L.append(f"- 版式：居中行占比 {F2.get('centered_ratio')} → {F2.get('layout_verdict')}")
        L.append(f"- 强调色：{ac.get('hex')}（占比中位 {ac.get('accent_pixel_ratio_median')}）"
                 f"｜{ac.get('verdict', '')}")
    L.append("")
    L.append("## 六、工具推断（待填）")
    L.append("")
    L.append("> 规则：每一行必须引用具体证据（溯源标签 / 画面特征 / 音频特征）。"
             "判不了就写「无法确定」，**禁止编造工具名**（SKILL.md 铁律 2）。")
    L.append("")
    L.append("| 环节 | 推断 | 证据 | 级别 |")
    L.append("|---|---|---|---|")
    L.append(f"| 画面制作 |  |  | 【判断】 |")
    L.append(f"| 配音 |  | 停顿 {E.get('pause_count_ge_0.25s')} 次 / LRA {_fmt(Lo.get('lra_lu'), ' LU', 1)} | 【判断】 |")
    L.append(f"| 字幕 |  | 字号档见第五节 | 【判断】 |")
    L.append(f"| 剪辑合成 |  | 溯源：{'；'.join(G.get('boxes_found') or []) or '—'} | 【判断】 |")
    L.append("")
    L.append("## 七、可迁移工艺（待填）")
    L.append("")
    L.append("> 写「能直接搬进我们产线的做法」，每条要能落到具体文件或参数。")
    L.append("")
    L.append("1. ")
    L.append("2. ")
    L.append("")
    L.append("## 八、差距对照与单一推荐（必填）")
    L.append("")
    L.append("| 这条片子要求的环节 | 我们现状 | 判定 | 改动项（指名到文件） |")
    L.append("|---|---|---|---|")
    for env in ("配音先行的对齐", "字幕层（样式/字号）", "强调色与配色语义", "场景切换与节奏", "母带响度"):
        L.append(f"| {env} |  |  |  |")
    L.append("")
    L.append("**单一推荐下一步**：（只写一项，并说明理由）")
    L.append("")
    L.append("## 九、无法确定项【自动汇总】")
    L.append("")
    uncertain = []
    for key, label in (("A_technical", "A 技术指纹"), ("B_shots", "B 场景节奏"),
                       ("C_transcript", "C 语音转写"), ("D_coupling", "D 声画耦合"),
                       ("E_voice", "E 配音类型"), ("H_loudness", "H 响度"),
                       ("F_palette", "F 视觉规范"), ("F2_layout", "F2 版式字号"),
                       ("G_provenance", "G 溯源")):
        blk = data.get(key) or {}
        if blk.get("failed"):
            uncertain.append(f"- {label}：未产出（{blk.get('error')}）")
    if C.get("untrusted_guard") not in (None, "ok"):
        uncertain.append(f"- 注入守门：{C.get('untrusted_guard')}（外部文本按未扫描处理）")
    if (D.get("sample_confidence") or "") != "high":
        uncertain.append(f"- 制作顺序：置信 {D.get('sample_confidence')}（样本 {D.get('cut_sample')} 个切点）")
    L += uncertain or ["- （无）"]
    L.append("- 平台转码会覆盖元数据，工具链无法从元数据确证（见 SKILL.md 已知边界）")
    L.append("")
    L.append("## 十、证据包")
    L.append("")
    L.append(f"- 原始视频：`video.mp4`（{_fmt(dur, 's')}）")
    L.append(f"- 取证 JSON：`production_analysis.json`")
    if (work / "meta.json").exists():
        L.append(f"- 平台元数据：`meta.json`"
                 + (f"（{meta.get('title', '')[:60]}｜{meta.get('method', '')}）" if meta else ""))
    L.append(f"- OCR 抽帧：`frames_ocr/`（{F2.get('ocr_frames', 0)} 帧）")
    L.append("- 接触表/关键帧：见 `frames/`、`contact_sheet.jpg`（如已抽帧）")
    L.append("")
    L.append("---")
    L.append("")
    L.append("> 证据级别说明（术语与产线 `card_quality_check.py` 统一）："
             "【实测】= 脚本确定性测量；【判断】= 解读或推断；【待标定】= 无依据、只报数。")
    return "\n".join(L) + "\n"


def check_report(path: Path) -> int:
    """校验必填节是否**真的写了内容**，而不是只有骨架。

    为什么按节定制判据：生成的骨架里第六节表格已预填"证据/级别"两列，
    用"有没有非空单元格"判会把骨架误判为完成（第一版就是这么放过的）。
    所以每节都查它**该由人填的那一列**。
    """
    text = path.read_text(encoding="utf-8")
    problems = []
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    if missing:
        problems.append(f"缺必填节：{missing}")

    def rows(header: str) -> list:
        if header not in text:
            return []
        body = re.split(r"\n## ", text.split(header, 1)[1], maxsplit=1)[0]
        out = []
        for line in body.splitlines():
            s = line.strip()
            if not s.startswith("|"):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not cells or all(c in ("", "—", "---", ":---") for c in cells):
                continue
            if cells[0] in ("环节", "这条片子要求的环节"):
                continue
            out.append(cells)
        return out

    # 六、工具推断：第 2 列（推断）必须有人写
    infer_rows = rows("## 六、工具推断")
    if not any(len(r) >= 2 and r[1] not in ("", "—", "待填") for r in infer_rows):
        problems.append("第六节「工具推断」的推断列全空")

    # 七、可迁移工艺：至少一条编号项写了内容
    if "## 七、可迁移工艺" in text:
        body7 = re.split(r"\n## ", text.split("## 七、可迁移工艺", 1)[1], maxsplit=1)[0]
        if not any(re.match(r"^\d+\.\s*\S", ln.strip()) for ln in body7.splitlines()):
            problems.append("第七节「可迁移工艺」没有实质条目")
    else:
        problems.append("缺第七节")

    # 八、差距对照：判定列与改动项列都要有人写，且有单一推荐
    gap_rows = rows("## 八、差距对照")
    if not any(len(r) >= 4 and r[2] not in ("", "—") and r[3] not in ("", "—")
               for r in gap_rows):
        problems.append("第八节「差距对照」的判定/改动项列为空")
    rec = text.split("**单一推荐下一步**", 1)[-1].split("\n## ")[0]
    # 先丢掉括号里的填写提示（如"（只写一项，并说明理由）"），再看还剩什么
    rec_txt = re.sub(r"[（(][^）)]*[）)]", "", rec).strip(" ：:\n\t")
    if len(rec_txt) < 8:
        problems.append("第八节「单一推荐下一步」为空")

    for p in problems:
        print(f"[FAIL] {p}")
    if problems:
        print("      按 SKILL.md 第 4 步：必须含工具推断 + 可迁移工艺 + 差距对照 + 单一推荐")
        return 1
    print("[PASS] 必填节齐全且都有实质内容")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成/校验制作分析报告骨架")
    ap.add_argument("work", nargs="?", help="工作目录（含 production_analysis.json）")
    ap.add_argument("--title", default=None, help="视频标题")
    ap.add_argument("--source", default=None, help="来源平台 + 链接")
    ap.add_argument("--out", default=None, help="输出路径，默认 <工作目录>/制作分析报告.md")
    ap.add_argument("--check", default=None, help="只校验已有报告的必填节")
    args = ap.parse_args()

    if args.check:
        return check_report(Path(args.check))
    if not args.work:
        ap.error("要么给工作目录，要么用 --check <报告.md>")

    work = Path(args.work).resolve()
    data, meta = _load(work)
    title = args.title or meta.get("title") or work.name
    source = args.source or meta.get("webpage_url") or ""
    text = build_report(data, meta, work, title, source)
    out = Path(args.out) if args.out else work / "制作分析报告.md"
    out.write_text(text, encoding="utf-8")
    print(f"[done] {out}")
    print(f"       确定性数字已填；第六/七/八节待人写（第八节为必填尾节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
