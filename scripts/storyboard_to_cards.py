#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""storyboard_to_cards.py — 分镜表 → 卡片产线输入（确定性适配 + 强校验）

把 knowledge-video-storyboard 技能产出的 storyboard.json 转成
build_card_video.py 能直接消费的 script.json，并在转换前做硬校验。

校验不通过就报错退出，不出片 —— 分镜的质量门在渲染之前，不在渲染之后。

用法:
    python scripts/storyboard_to_cards.py --storyboard sb.json --out <out_dir>
    python scripts/storyboard_to_cards.py --storyboard sb.json --out <dir> --no-strict

产出:
    <out_dir>/script.json    可直接喂给 build_card_video.py
    <out_dir>/storyboard.check.md   校验报告（人读）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_card_deck  # noqa: E402  只取动效词表，单一事实源

VERB_NAMES = set(build_card_deck.VERBS)
TARGET_NAMES = set(build_card_deck.TARGET_SEL)
STYLE_NAMES = set(build_card_deck.STYLES)
UNIT_NAMES = set(build_card_deck.UNITS)

# 空话黑名单：content_expect / effect_expect 里出现即判不合格
EMPTY_WORDS = ("好看", "高级", "大气", "有质感", "讲一下", "介绍一下背景",
               "铺垫一下", "过渡一下", "简单说说", "随便聊聊", "科技感")
# 动效字段禁止出现的参数痕迹
PARAM_PAT = re.compile(r"\d+(\.\d+)?\s*(ms|毫秒|s\b|秒)|ease|缓动|cubic-bezier|power\d")
CORE_MAX = 12
BRIDGE_MAX_RATIO = 0.15


def fail(errs: list[str], msg: str) -> None:
    errs.append(msg)


def check(sb: dict) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errs: list[str] = []
    warns: list[str] = []

    video = sb.get("video") or {}
    lines = sb.get("lines") or []
    scenes = sb.get("scenes") or []
    beats = sb.get("beats") or []

    if not lines:
        fail(errs, "lines 为空")
    if not scenes:
        fail(errs, "scenes 为空")
    if errs:
        return errs, warns

    # ── §1 基本盘 ────────────────────────────────
    core = (video.get("core_message") or "").strip()
    if not core:
        fail(errs, "video.core_message 缺失")
    elif len(core) > CORE_MAX:
        fail(errs, f"video.core_message 超过 {CORE_MAX} 字（现 {len(core)}）")
    for k in ("title", "platform", "density", "tone"):
        if not (video.get(k) or "").strip():
            fail(errs, f"video.{k} 缺失")
    for k in ("density", "tone"):
        v = (video.get(k) or "")
        for w in EMPTY_WORDS:
            if w in v:
                fail(errs, f"video.{k} 含空话「{w}」：{v}")
    style = video.get("style")
    if style is not None and style not in STYLE_NAMES:
        fail(errs, f"video.style 未登记：{style!r}（可用：{'/'.join(sorted(STYLE_NAMES))}）")

    # ── 行号覆盖：连续、不重叠、全覆盖 ──────────
    expect = 1
    for i, sc in enumerate(scenes):
        f, t = sc.get("from"), sc.get("to")
        if not isinstance(f, int) or not isinstance(t, int):
            fail(errs, f"Scene {i+1} 的 from/to 必须是整数")
            continue
        if f != expect:
            fail(errs, f"Scene {i+1} 行号不连续：期望从 {expect} 起，实际 {f}")
        if t < f:
            fail(errs, f"Scene {i+1} 的 to({t}) 小于 from({f})")
        expect = t + 1
    if expect - 1 != len(lines):
        fail(errs, f"scenes 覆盖行数 {expect-1} ≠ 口播稿行数 {len(lines)}")

    # ── 逐镜校验 ────────────────────────────────
    bridge = 0
    for i, sc in enumerate(scenes):
        n = i + 1
        f, t = sc.get("from"), sc.get("to")
        if not (isinstance(f, int) and isinstance(t, int) and 1 <= f <= t <= len(lines)):
            continue
        want = "".join(lines[f - 1:t])
        got = (sc.get("narration") or "").strip()
        if got != want:
            fail(errs, f"Scene {n} 旁白与口播稿不符\n"
                       f"        期望：{want}\n        实际：{got}")
        if sc.get("type") == "bridge":
            bridge += 1
        elif sc.get("type") not in ("A", "B"):
            fail(errs, f"Scene {n} 的 type 必须是 A / B / bridge（现 {sc.get('type')!r}）")
        for field in ("content_expect", "effect_expect"):
            v = (sc.get(field) or "").strip()
            if not v:
                fail(errs, f"Scene {n} 缺 {field}")
                continue
            for w in EMPTY_WORDS:
                if w in v:
                    fail(errs, f"Scene {n} 的 {field} 含空话「{w}」：{v}")
        if not (sc.get("role") or "").strip():
            fail(errs, f"Scene {n} 缺 role（这一镜在叙事里的角色）")
        screen = sc.get("screen") or {}
        if not (screen.get("title") or "").strip():
            fail(errs, f"Scene {n} 的 screen.title 缺失（每镜必须有屏显主文案）")
        for b in (screen.get("blocks") or []):
            if not (b.get("label") or "").strip() or not (b.get("text") or "").strip():
                fail(errs, f"Scene {n} 的 blocks 项缺 label 或 text")
        for u in (screen.get("units") or []):
            ut = u.get("type")
            if ut not in UNIT_NAMES:
                fail(errs, f"Scene {n} 用了未登记的信息单元类型 {ut!r}"
                           f"（可用：{'/'.join(sorted(UNIT_NAMES))}）")
                continue
            spec = build_card_deck.UNITS[ut]
            items = u.get("items") or []
            if not (spec["min_items"] <= len(items) <= spec["max_items"]):
                fail(errs, f"Scene {n} 的 {ut} 单元有 {len(items)} 项，"
                           f"需在 {spec['min_items']}–{spec['max_items']} 之间"
                           f"（配方卡实测边界，超出会失控）")
            for it in items:
                if ut == "stat":
                    if not (isinstance(it, dict) and str(it.get("value", "")).strip()):
                        fail(errs, f"Scene {n} 的 stat 项缺 value")
                    elif not str(it.get("label", "")).strip():
                        fail(errs, f"Scene {n} 的 stat 项缺 label")
                elif ut == "compare":
                    if not (isinstance(it, dict) and str(it.get("label", "")).strip()
                            and str(it.get("text", "")).strip()):
                        fail(errs, f"Scene {n} 的 compare 项需同时有 label 与 text")
                else:
                    t = it if isinstance(it, str) else (it.get("text") or "")
                    if not t.strip():
                        fail(errs, f"Scene {n} 的 {ut} 单元有空项")
        motion = (sc.get("motion") or "").strip()
        if not motion:
            fail(errs, f"Scene {n} 缺 motion（动效要点）")
        elif PARAM_PAT.search(motion):
            fail(errs, f"Scene {n} 的 motion 写了参数（只许写动词）：{motion}")
        else:
            for seg in re.split(r"→|->|\u2192", motion):
                seg = seg.strip()
                if not seg:
                    continue
                m = re.match(r"^([A-Za-z]+)\s*(.*)$", seg)
                if not m:
                    fail(errs, f"Scene {n} 的 motion 片段无法解析：{seg!r}"
                               f"（格式：动词 目标，如「FLOATS 标题」）")
                    continue
                v, tg = m.group(1).upper(), m.group(2).strip()
                if v not in VERB_NAMES:
                    fail(errs, f"Scene {n} 用了未登记的动词 {v}"
                               f"（可用：{'/'.join(sorted(VERB_NAMES))}）")
                if tg and tg not in TARGET_NAMES:
                    fail(errs, f"Scene {n} 用了未登记的目标「{tg}」"
                               f"（可用：{'/'.join(sorted(TARGET_NAMES))}）")
        t_in = (sc.get("transition_in") or "").strip()
        t_out = (sc.get("transition_out") or "").strip()
        for lbl, tv in (("transition_in", t_in), ("transition_out", t_out)):
            if tv and not ("硬切" in tv or "FADE" in tv.upper() or "淡入" in tv or "黑" in tv):
                fail(errs, f"Scene {n} 的 {lbl} 不支持：{tv}"
                           f"（可用：硬切 / FADES / FADES 到黑）")
        for k in ("transition_in", "transition_out"):
            if not (sc.get(k) or "").strip():
                fail(errs, f"Scene {n} 缺 {k}（「硬切」也要明写）")

    # ── 节拍覆盖 ────────────────────────────────
    if not beats:
        warns.append("beats 为空——建议补叙事节拍，便于自检节奏")
    else:
        seen: list[int] = []
        for b in beats:
            a, z = b.get("scene_from"), b.get("scene_to")
            if not (isinstance(a, int) and isinstance(z, int)):
                fail(errs, f"beat「{b.get('name')}」的 scene_from/to 必须是整数")
                continue
            seen.extend(range(a, z + 1))
        if sorted(seen) != list(range(1, len(scenes) + 1)):
            fail(errs, f"beats 未无缝隙覆盖全部 scenes：覆盖 {sorted(set(seen))} / 共 {len(scenes)}")

    # ── 节奏/占比 ───────────────────────────────
    if bridge > len(scenes) * BRIDGE_MAX_RATIO:
        fail(errs, f"过场镜头 {bridge} 个，超过 {BRIDGE_MAX_RATIO:.0%} 上限"
                   f"（共 {len(scenes)} 镜，上限 {int(len(scenes)*BRIDGE_MAX_RATIO)}）")
    if scenes and scenes[0].get("from") != 1:
        fail(errs, "第一镜必须从第 1 行口播开始（hook 要落在开头 3 秒内）")
    for i, sc in enumerate(scenes):
        if not (sc.get("visual") or "").strip():
            warns.append(f"Scene {i+1} 缺 visual（画面描述），本轮不驱动渲染，建议补")
        if not (sc.get("sfx") or "").strip():
            warns.append(f"Scene {i+1} 缺 sfx（无音效也要写「无」）")
        # 信息单元数 → 画面密度。实测：1 块 1.33% / 2 块 2.03% / 列表 3 项 3.16%
        # （字形覆盖；对标 C 2.66%）。钩子镜可以只有 0–1 个，其余镜头不该。
        screen = sc.get("screen") or {}
        n_units = len(screen.get("blocks") or [])
        for u in (screen.get("units") or []):
            n_units += len(u.get("items") or []) or 1
        if i > 0 and n_units < 3:
            warns.append(f"Scene {i+1} 只有 {n_units} 个信息单元 —— 画面会空"
                         f"（实测单元数与密度近乎线性：1 项≈1.3%、2 项≈2.0%、3 项≈3.2%）；"
                         f"建议补到 ≥3，或改用 list 单元")
    return errs, warns


def to_script(sb: dict) -> dict:
    video = sb.get("video") or {}
    # 每镜归属到哪个叙事节拍 → 生成 STEP k / N 标号
    step_of: dict[int, str] = {}
    beats = sb.get("beats") or []
    for k, b in enumerate(beats, 1):
        for sid in range(int(b.get("scene_from", 0)), int(b.get("scene_to", -1)) + 1):
            step_of[sid] = f"{k:02d} / {len(beats):02d}"
    cards = []
    for i, sc in enumerate(sb["scenes"], 1):
        screen = sc.get("screen") or {}
        card = {
            "title": screen.get("title", ""),
            "from": sc["from"],
            "to": sc["to"],
            "step": step_of.get(i, f"{i:02d} / {len(sb['scenes']):02d}"),
            # 动效与转场：build_card_deck 会读这三个字段驱动渲染
            "motion": sc.get("motion", ""),
            "transition_in": sc.get("transition_in", ""),
            "transition_out": sc.get("transition_out", ""),
        }
        for k in ("kicker", "subtitle", "big"):
            if screen.get(k):
                card[k] = screen[k]
        if screen.get("blocks"):
            card["blocks"] = screen["blocks"]
        if screen.get("units"):
            card["units"] = screen["units"]
        cards.append(card)
    return {
        "series": video.get("series", ""),
        "episode": video.get("episode", ""),
        "breadcrumb": video.get("breadcrumb", ""),
        "style": video.get("style", "grid-dark"),
        "voice": sb.get("voice", "yunjian"),
        "lines": sb["lines"],
        "cards": cards,
        # 留档字段，build_card_video 会忽略
        "_storyboard_role": [sc.get("role") for sc in sb["scenes"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="分镜表 → 卡片产线输入")
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-strict", action="store_true", help="只出报告不拦截")
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    errs, warns = check(sb)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = ["# 分镜校验报告", ""]
    report.append(f"- 镜头数：{len(sb.get('scenes') or [])}")
    report.append(f"- 口播行数：{len(sb.get('lines') or [])}")
    report.append(f"- 错误：{len(errs)}　警告：{len(warns)}")
    report.append("")
    if errs:
        report.append("## ✗ 错误（必须修，否则不出片）")
        report += [f"- {e}" for e in errs]
        report.append("")
    if warns:
        report.append("## ⚠ 警告（不拦，但建议修）")
        report += [f"- {w}" for w in warns]
        report.append("")
    if not errs and not warns:
        report.append("全部通过。")
    (out / "storyboard.check.md").write_text("\n".join(report), encoding="utf-8")

    for w in warns:
        print(f"[warn] {w}")
    if errs:
        for e in errs:
            print(f"[error] {e}")
        print(f"\n校验未通过：{len(errs)} 个错误 → 报告见 {out / 'storyboard.check.md'}")
        if args.no_strict:
            print("(--no-strict：仍写出 script.json)")
        else:
            return 3

    (out / "script.json").write_text(
        json.dumps(to_script(sb), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] {out / 'script.json'}  （{len(sb['scenes'])} 镜 / {len(sb['lines'])} 行口播）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
