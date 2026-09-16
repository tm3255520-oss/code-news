#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_card_deck.py — 知识卡片视频模板（HyperFrames 合成生成器）

把一份卡片 JSON 渲染成 HyperFrames 合成 index.html。
视觉规范照抄对标样本 C（抖音 7676834838926890405）：
  米色外框 + 深色网格面板 + 荧光绿强调 + 页码/进度点 + 底部字幕条，画布 1440x1080 (4:3)。

模板与数据的边界：
  【模板管】版面、配色、字号、网格、页眉页脚、进度点、字幕条样式
  【数据管】每张卡片的标题/标签/内容块、每张卡片与每条字幕的时间轴

用法:
    python scripts/build_card_deck.py --cards cards.json --out video-line/index.html

cards.json 结构（时间由上游 TTS 的 SRT 实测时长填入）:
{
  "series": "AI KNOWLEDGE", "episode": "SERIES 001", "breadcrumb": "AI工作流",
  "audio": "assets/voice_segmented.mp3",
  "cards": [
    {"title": "做一条视频：3小时→5分钟", "kicker": "VIDEO TASK",
     "blocks": [{"label": "VIDEO TASK", "text": "做一条视频"}],
     "start": 0.0, "duration": 10.8,
     "captions": [{"text": "给Codex装上这四个技能", "start": 0.0, "duration": 2.0}]}
  ]
}
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W, H = 1440, 1080

# ── 画幅 ─────────────────────────────────────────────────────────────
# landscape 是历史归档画幅，geom 故意留空（沿用样式自带几何），保证历史输出逐字节不变。
# vertical 只覆盖「与画幅强相关」的几何；配色/字号仍归样式管。
FORMATS: dict[str, dict] = {
    "landscape": {"size": (W, H), "geom": {}},
    "vertical": {
        "size": (1080, 1920),
        "geom": {
            # 上下留出外框装饰文字的位置（左上 stamp-l / 右下 stamp-b 是常驻层，
            # 面板一旦压上去就会 text_occluded —— 竖屏首渲实测踩到）
            "inset": (26, 100, 26, 96),
            "card_inset": (58, 126, 58, 438),
            "band_h": 208, "hud_b": 232, "pbar_b": 214, "frame_b": 296,
            "list_w": 872, "compare_w": 900,
            "blocks_w": 900, "title_max": 900, "cap_size": 46,
            "center_rule": "display:flex; flex-direction:column; justify-content:center; ",
            # 字号档位：竖屏画幅高，沿用横屏字号会显得内容小而画面空
            "title_size": 112, "bl_size": 16, "bl_n1": 17,
            "bt_size": 40, "bt_n1": 56, "bt_n2": 48,
            "li_size": 34, "note_size": 26, "sv_size": 104,
            "su_size": 32, "ct_size": 34, "sub_size": 30,
            # steps 的行高、标记条位移、字号是一组联动值（位移 = 行高 + 行距，在 JS 里算），
            # 必须一起改，否则标记条会与文字错位
            "sp_h": 74, "stx_size": 33,
        },
    },
}

# ── 动效词表：分镜写动词，渲染器翻译成 GSAP ──────────────────────────
# 分镜技能（knowledge-video-storyboard）只允许用这张表里的动词与目标。
# 新增动词必须同时改这里和技能里的 references/动效词表.md，否则分镜会被判不合格。
VERBS: dict[str, dict] = {
    "FADES":   {"from": {"opacity": 0},
                "to": {"opacity": 1, "duration": 0.5, "ease": "power1.out"}},
    "FLOATS":  {"from": {"opacity": 0, "y": 26},
                "to": {"opacity": 1, "y": 0, "duration": 0.6, "ease": "power2.out"}},
    "SLIDES":  {"from": {"opacity": 0, "x": -46},
                "to": {"opacity": 1, "x": 0, "duration": 0.6, "ease": "power3.out"}},
    "RISES":   {"from": {"opacity": 0, "y": 72},
                "to": {"opacity": 1, "y": 0, "duration": 0.7, "ease": "power3.out"}},
    "SLAMS":   {"from": {"opacity": 0, "scale": 1.26},
                "to": {"opacity": 1, "scale": 1, "duration": 0.45, "ease": "back.out(1.7)"}},
    # 子项错开淡入（用于「卡片」这类多元素目标）
    "STAGGER": {"from": {"opacity": 0, "y": 14},
                "to": {"opacity": 1, "y": 0, "duration": 0.45, "stagger": 0.14,
                       "ease": "power2.out"}},
    # 子项从左侧错开滑入
    "CASCADE": {"from": {"opacity": 0, "x": -60},
                "to": {"opacity": 1, "x": 0, "duration": 0.5, "stagger": 0.12,
                       "ease": "power3.out"}},
    # 逐字出现（需要渲染端把文字拆成 span.ch）
    "TYPES":   {"special": "types"},
    # 线条从左画出（需要渲染端提供 .rule）
    "DRAWS":   {"special": "draws"},
}

# 分镜里的目标名 → 模板内的选择器
TARGET_SEL: dict[str, str] = {
    "标题": ".title",
    "副标题": ".subtitle",
    "标签": ".kicker-wrap",
    "卡片": ".blocks .block",
    "大字": ".blocks .row",
}

# ── 信息单元类型（借鉴 video-shotcraft 的「镜头配方卡」） ─────────────
# 来源：Vincentwei1021/video-shotcraft（Apache-2.0，8742★）gallery/source/*.md
# 适配说明：卡片用归一化时间 ft(0-1) 描述自己的 3.6s 窗口；我们按它能落到的
# **绝对节奏**取值（stagger ≈10f@30fps=0.32s、单项行程 ≈26f=0.85s），
# 因为我们的卡片时长由配音实测决定、不是固定 3.6s。
# density_measured：同一把尺子（字形覆盖）实测值，对标 C 2.66% / 对标 D 2.05%。
UNITS: dict[str, dict] = {
    # list-reveal：垂直列表逐项「scale 找位」+ 容器**线性漂移**（两层运动解耦）
    "list": {
        "density_measured": 0.0264,
        "min_items": 2,
        "max_items": 8,
        "stagger_s": 0.32,
        "item_dur_s": 0.85,
        "start_scale": 0.78,
        "start_y": 14,
        "drift_px": 16,          # 容器从 +16 漂到 -16（贯穿该卡）
        "ease": "back.out(1.2)",  # 小过冲，把落位那一帧从「停」变成「扣住」
    },
    # gauge-readout-moves（式 B tape-scroll-fixed-pointer）：大数字 + 刻度带滚动
    # 机制要点：「世界动、针不动」——刻度带整体滚过，窗内的数字自己数上去
    "stat": {
        "density_measured": 0.0320,
        "min_items": 1,
        "max_items": 3,
        "count_dur_s": 1.1,      # 数值爬升时长
        "stagger_s": 0.22,       # 多指标错峰（原卡：齐甩读作复制粘贴）
        "tape_speed_px": 45,     # 原卡冲刺速度 45px/f @30fps ≈ 1.5px/ms
        "ease": "power2.out",
    },
    # quad-split-parallel-scenes：并列面板，**错拍是灵魂**
    "compare": {
        "density_measured": 0.0114,   # 偏低：面板大而文字薄；已在 CSS 收紧并加中轴
        "min_items": 2,
        "max_items": 4,
        "stagger_s": 0.15,       # 原卡错拍 3–6 帧 ≈ 0.10–0.20s
        "item_dur_s": 0.6,
        "start_y": 22,
        "ease": "power3.out",
    },
    # beat-step-list-theme-cycle：纵向步骤 + 当前项高亮逐拍推进
    # 机制要点：跳变只占拍头（「跳」不要「滑」），其余时间静置
    "steps": {
        "density_measured": 0.0367,
        "min_items": 2,
        "max_items": 5,
        "beat_s": 0.6,           # 原卡拍长 18f ≈ 0.6s
        "snap_s": 0.2,           # 跳变窗仅占拍头 6f；拉长就「跳」变「滑」
        "step_px": 70,           # 每拍步进 = 行高 58 + 行距 12
        "ease": "power3.out",
    },
}

# ── 风格 DNA：两套风格共用同一份骨架，只换下面这组变量 ────────────────
STYLES: dict[str, dict] = {
    # 技术感：深色网格 + 荧光绿（对标样本 C）
    "grid-dark": {
        "page": "#E3DCC9", "panel": "#101818", "grid": "rgba(255,255,255,.055)",
        "stamp": "#3F3B2E", "title": "#F4F4EF", "body": "#EDEDE6", "muted": "#9AA79B",
        "accent": "#B3E553", "accent_ink": "#8FB845",
        "grid_alpha": "0.085", "bracket_w": 2, "bracket_a": "0.42",
        "block_bg": "rgba(179,229,83,.045)", "block_border": "2px solid #B3E553",
        "band": "#0D0D0D", "band_ink": "#EFEFE4",
        "bracket": "rgba(255,255,255,.22)", "divider": "rgba(255,255,255,.09)",
        "dock": "#2E3A33", "crumb_ink": "#C9D2C6", "crumb_border": "#2B3630",
        "dimmer": "#3E4A42", "pbar_off": "rgba(255,255,255,.14)",
        "title_size": 84, "grid_size": 34, "radius": 22, "block_radius": 18,
        "inset": (38, 86, 38, 66), "panel_shadow": "0 18px 44px rgba(0,0,0,.22)",
        "card_inset": (72, 150, 72, 262),
    },
    # 杂志感：米白全幅 + 橙红强调 + 深色内容卡（对标样本 D）
    "paper-light": {
        "page": "#F8F6F2", "panel": "#F8F6F2", "grid": "rgba(0,0,0,0)",
        "stamp": "#8A8377", "title": "#0F0D0E", "body": "#25211F", "muted": "#6B655C",
        "accent": "#E4572E", "accent_ink": "#C8431F",
        "grid_alpha": "0", "bracket_w": 2, "bracket_a": "0.30",
        "block_bg": "#141210", "block_border": "0", "block_ink": "#F2F0EA",
        "band": "#111111", "band_ink": "#F5F3EE",
        "bracket": "rgba(0,0,0,.18)", "divider": "rgba(0,0,0,.12)",
        "dock": "#DED9CF", "crumb_ink": "#5A554C", "crumb_border": "#DDD8CE",
        "dimmer": "#C9C3B6", "pbar_off": "rgba(0,0,0,.14)",
        "title_size": 88, "grid_size": 0, "radius": 2, "block_radius": 10,
        "inset": (56, 84, 56, 92), "panel_shadow": "none",
        "card_inset": (84, 146, 84, 268),
    },
}


def css_for(s: dict) -> str:
    """用占位符替换而不用 str.format —— CSS 里全是花括号，format 会被它们搞崩。"""
    left, top, right, bottom = s["inset"]
    cl, ct, cr, cb = s["card_inset"]
    grid_rules = ""
    if s["grid_size"]:
        grid_rules = (
            "background-image:"
            "linear-gradient(to right,rgba(255,255,255,"
            + s.get("grid_alpha", "0.055") + ") 1px,transparent 1px),"
            "linear-gradient(to bottom,rgba(255,255,255,"
            + s.get("grid_alpha", "0.055") + ") 1px,transparent 1px);"
            f"background-size:{s['grid_size']}px {s['grid_size']}px;"
        )
    def rgba(hexcolor: str, alpha: str) -> str:
        h = hexcolor.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},{alpha})"

    out = CSS_TMPL
    for k, v in {
        "page": s["page"], "panel": s["panel"], "stamp": s["stamp"],
        "title": s["title"], "body": s["body"], "muted": s["muted"],
        "accent": s["accent"], "accent_ink": s["accent_ink"],
        "block_bg": s["block_bg"], "block_border": s["block_border"],
        "block_ink": s.get("block_ink", s["body"]),
        "band": s["band"], "band_ink": s["band_ink"], "bracket": s["bracket"],
        "divider": s["divider"], "dock": s["dock"],
        "crumb_ink": s["crumb_ink"], "crumb_border": s["crumb_border"],
        "dimmer": s["dimmer"], "pbar_off": s["pbar_off"],
        "title_size": s["title_size"], "radius": s["radius"],
        "block_radius": s["block_radius"], "panel_shadow": s["panel_shadow"],
        "pl": left, "pt": top, "pr": right, "pb": bottom,
        "cl": cl, "ct": ct, "cr": cr, "cb": cb,
        "bracket_w": s.get("bracket_w", 1),
        "bracket_color": rgba(s["accent"], s.get("bracket_a", "0.25")),
        "readout_label": rgba(s["accent"], "0.55"),
        "grid_rules": grid_rules,
        # 画幅相关几何：这些默认值 = 历史横屏版式，纵向画幅由 FORMATS 覆盖
        "frame_b": s.get("frame_b", 222), "hud_b": s.get("hud_b", 168),
        "pbar_b": s.get("pbar_b", 150), "band_h": s.get("band_h", 148),
        "cap_size": s.get("cap_size", 34), "list_w": s.get("list_w", 640),
        "steps_w": s.get("steps_w", 780), "compare_w": s.get("compare_w", 860),
        "blocks_w": s.get("blocks_w", 1080), "title_max": s.get("title_max", 1180),
        "center_rule": s.get("center_rule", ""),
        "sp_h": s.get("sp_h", 58), "stx_size": s.get("stx_size", 26),
        # 字号档位：横屏默认值 = 历史字面量（保证输出不变）；竖屏放大以填空、齐手机可读性
        "bl_size": s.get("bl_size", 12), "bl_n1": s.get("bl_n1", 13),
        "bt_size": s.get("bt_size", 27), "bt_n1": s.get("bt_n1", 38),
        "bt_n2": s.get("bt_n2", 32), "li_size": s.get("li_size", 24),
        "note_size": s.get("note_size", 19), "sv_size": s.get("sv_size", 76),
        "su_size": s.get("su_size", 26), "ct_size": s.get("ct_size", 25),
        "sub_size": s.get("sub_size", 22),
    }.items():
        out = out.replace("@@%s@@" % k, str(v))
    return out


CSS_TMPL = """
* { margin:0; padding:0; box-sizing:border-box; }
html, body { margin:0; width:100%; height:100%; overflow:hidden; background:#0a0a0a; }

#root {
  width:100%; height:100%;
  font-family: sans-serif;
  -webkit-font-smoothing:antialiased;
}

.bgclip, .card, .cap { position:absolute; inset:0; }

/* ── 外框 ───────────────────────────────── */
.stage { position:absolute; inset:0; background:@@page@@; }
.corner { position:absolute; width:26px; height:26px; }
.corner::before, .corner::after { content:""; position:absolute; background:@@bracket@@; }
.corner::before { left:12px; top:0; width:1px; height:26px; }
.corner::after  { top:12px; left:0; height:1px; width:26px; }
.c-tl { left:16px;  top:16px; }
.c-tr { right:16px; top:16px; }
.c-bl { left:16px;  bottom:16px; }
.c-br { right:16px; bottom:16px; }

.stamp-l { position:absolute; left:56px; top:22px; display:flex; flex-direction:column;
  gap:1px; font-size:11px; line-height:1.45; letter-spacing:.14em;
  color:@@stamp@@; font-weight:800; }
.stamp-b { position:absolute; right:56px; bottom:26px; text-align:right;
  display:flex; flex-direction:column; gap:1px; font-size:10px; line-height:1.5;
  letter-spacing:.14em; color:@@stamp@@; font-weight:800; }
.mono { font-family:ui-monospace, Consolas, "Courier New", monospace; }

/* ── 主面板 ─────────────────────────────── */
.panel {
  position:absolute; left:@@pl@@px; right:@@pr@@px; top:@@pt@@px; bottom:@@pb@@px;
  background:@@panel@@; border-radius:@@radius@@px; overflow:hidden;
  @@grid_rules@@
  box-shadow:@@panel_shadow@@;
}
.dots { position:absolute; left:30px; top:24px; display:flex; gap:9px; }
.dots i { width:11px; height:11px; border-radius:50%; background:@@dock@@; display:block; }
.crumb { position:absolute; left:50%; top:20px; transform:translateX(-50%);
  border:1px solid @@crumb_border@@; border-radius:14px; padding:5px 18px;
  font-size:13px; letter-spacing:.08em; color:@@crumb_ink@@; font-weight:700; }

/* ── 四角括号（借 telemetry-hud 的框景语言，用强调色才看得见） ─ */
.frame { position:absolute; left:52px; right:52px; top:58px; bottom:@@frame_b@@px; }
.bracket { position:absolute; width:40px; height:40px; border:0 solid @@bracket_color@@; }
.b-tl { left:0; top:0; border-left-width:@@bracket_w@@px; border-top-width:@@bracket_w@@px; }
.b-tr { right:0; top:0; border-right-width:@@bracket_w@@px; border-top-width:@@bracket_w@@px; }
.b-bl { left:0; bottom:0; border-left-width:@@bracket_w@@px; border-bottom-width:@@bracket_w@@px; }
.b-br { right:0; bottom:0; border-right-width:@@bracket_w@@px; border-bottom-width:@@bracket_w@@px; }

/* ── 面板右上：大字读数（对标 C 的 SCAN RATE 风格） ─ */
.readout { position:absolute; right:calc(@@pr@@px + 30px); top:calc(@@pt@@px + 26px);
  display:flex; gap:22px; text-align:right; }
.readout .ro { display:flex; flex-direction:column; align-items:flex-end; }
.readout .rl { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:10px; letter-spacing:.16em; color:@@readout_label@@; font-weight:700; }
.readout .rv { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:30px; line-height:1.05; font-weight:800; color:@@accent@@; }
.readout .rv small { font-size:14px; margin-left:2px; }

/* ── 卡片内容 ───────────────────────────── */
.card-inner { position:absolute; left:@@cl@@px; right:@@cr@@px; top:@@ct@@px; bottom:@@cb@@px; @@center_rule@@}
/* 纵向画幅下 .card-inner 是 flex 列：kicker 是 inline-block，不限定就会横向拉伸成整条 */
.card-inner > .kicker { align-self:flex-start; }
.kicker { display:inline-block; border:1px solid @@accent@@; border-radius:14px;
  padding:6px 16px; font-size:13px; letter-spacing:.16em; font-weight:800; color:@@accent@@;
  font-family:ui-monospace, Consolas, "Courier New", monospace; }
.title { margin-top:24px; font-size:@@title_size@@px; line-height:1.10; font-weight:900;
  color:@@title@@; letter-spacing:-.02em; max-width:@@title_max@@px; white-space:pre-line; }
.title .ln { display:block; }
.title .ch { display:inline; }
.rule { height:5px; width:240px; margin-top:18px; background:@@accent@@; border-radius:2px; }
.blocks { margin-top:40px; display:flex; flex-direction:column; gap:18px; max-width:@@blocks_w@@px; }
.block { border:@@block_border@@; border-radius:@@block_radius@@px; padding:20px 28px;
  background:@@block_bg@@; }
.block .bl { font-size:@@bl_size@@px; letter-spacing:.18em; font-weight:800; color:@@accent_ink@@; }
.block .bt { margin-top:7px; font-size:@@bt_size@@px; line-height:1.35; font-weight:800;
  color:@@block_ink@@; white-space:pre-line; }
/* 内容单元少时按块数放大，避免画面出现大片空白 */
.blocks.n1 { gap:0; }
.blocks.n1 .block { padding:40px 36px; }
.blocks.n1 .block .bl { font-size:@@bl_n1@@px; }
.blocks.n1 .block .bt { font-size:@@bt_n1@@px; line-height:1.25; }
.blocks.n2 { gap:26px; }
.blocks.n2 .block { padding:32px 34px; }
.blocks.n2 .block .bt { font-size:@@bt_n2@@px; }

/* ── 信息单元：list（逐项找位 + 容器线性漂移，借 list-reveal） ── */
.unit-list { display:flex; flex-direction:column; gap:9px; width:@@list_w@@px; margin-top:40px; }
.unit-list .li { display:flex; align-items:center; gap:16px;
  padding:15px 20px; background:@@block_bg@@;
  border:@@block_border@@; border-radius:@@block_radius@@px; }
.unit-list .li .lic { width:26px; height:26px; border-radius:7px; flex:0 0 auto;
  background:@@accent@@; opacity:.85; }
.unit-list .li .lit { font-size:@@li_size@@px; font-weight:700; color:@@block_ink@@;
  white-space:nowrap; }
.unit-list .li .lin { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:15px; color:@@accent_ink@@; font-weight:700; margin-right:2px; }
.unit-note { margin-top:18px; font-size:@@note_size@@px; color:@@muted@@; font-weight:600; }
/* blocks 与 units 同现时收紧间距：两者各自的 margin-top 叠加会把内容压进 HUD 区
   （实测过一次真实重叠：末卡「标题两行 + 卡片 + 对照 + 说明」超出内容区） */
.blocks + .unit-list, .blocks + .unit-stat,
.blocks + .unit-compare, .blocks + .unit-steps { margin-top:24px; }
.unit-list + .unit-note, .unit-stat + .unit-note,
.unit-compare + .unit-note, .unit-steps + .unit-note { margin-top:12px; }

/* ── 信息单元：stat（大数字 + 刻度带，借 gauge-readout-moves 式 B） ── */
.unit-stat { display:flex; gap:52px; margin-top:46px; }
.unit-stat .si { display:flex; flex-direction:column; gap:14px; }
.unit-stat .sl { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:12px; letter-spacing:.16em; color:@@accent_ink@@; font-weight:700; }
.unit-stat .srow { display:flex; align-items:baseline; gap:5px; }
.unit-stat .sv { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:@@sv_size@@px; line-height:1.14; font-weight:800; color:@@accent@@;
  letter-spacing:-.02em; display:block; }
.unit-stat .su { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:@@su_size@@px; font-weight:700; color:@@accent@@; opacity:.7; }
.unit-stat .stape { position:relative; height:11px; margin-top:8px; overflow:hidden; }
.unit-stat .stape i { position:absolute; top:0; width:1px; height:11px;
  background:@@divider@@; display:block; }

/* ── 信息单元：compare（并列面板，借 quad-split-parallel-scenes 的错拍） ── */
.unit-compare { display:grid; grid-template-columns:repeat(2, 1fr); gap:18px;
  margin-top:40px; max-width:@@compare_w@@px; position:relative; }
.unit-compare.n4 { grid-template-columns:repeat(2, 1fr); max-width:900px; }
/* 两格对照时加一条中轴分隔，让两侧留白读作刻意而非空 */
.unit-compare.n2::before { content:""; position:absolute; left:50%; top:8px; bottom:8px;
  width:1px; background:@@divider@@; }
.unit-compare .ci { border:@@block_border@@; border-radius:@@block_radius@@px;
  background:@@block_bg@@; padding:24px 26px; }
.unit-compare .cl { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:12px; letter-spacing:.18em; color:@@accent_ink@@; font-weight:700; }
.unit-compare .ct { margin-top:9px; font-size:@@ct_size@@px; line-height:1.38;
  font-weight:700; color:@@block_ink@@; white-space:pre-line; }

/* ── 信息单元：steps（纵向步骤 + 高亮逐拍推进，借 beat-step-list-theme-cycle） ── */
.unit-steps { position:relative; margin-top:38px; width:@@steps_w@@px;
  display:flex; flex-direction:column; gap:12px; padding-left:16px; }
.unit-steps .marker { position:absolute; left:0; top:0; width:4px; height:@@sp_h@@px;
  background:@@accent@@; border-radius:2px; }
.unit-steps .sp { display:flex; align-items:center; gap:20px; height:@@sp_h@@px;
  padding:0 22px; border-radius:@@block_radius@@px; opacity:.42; }
.unit-steps .sp .sn { font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:16px; font-weight:800; color:@@accent_ink@@; }
.unit-steps .sp .stx { font-size:@@stx_size@@px; font-weight:700; color:@@block_ink@@; }
.bignum { font-size:132px; font-weight:900; color:@@accent@@; line-height:1; }
.row { display:flex; align-items:center; gap:34px; }
.arrow { font-size:70px; color:@@muted@@; font-weight:900; }
.subtitle { margin-top:26px; font-size:@@sub_size@@px; line-height:1.5; color:@@muted@@; font-weight:600; }

/* ── 页眉页码 / 进度点（右上，随卡片切换） ── */
.pagebar { position:absolute; right:56px; top:0; height:86px;
  display:flex; align-items:center; gap:16px; }
.pageno { font-size:15px; letter-spacing:.12em; font-weight:800; color:@@stamp@@; }
.progress { display:flex; align-items:center; gap:11px; }
.progress i { width:15px; height:15px; border-radius:50%; background:@@dimmer@@; display:block; }
.progress i.on { background:@@accent@@; }

/* ── 面板下部：HUD 读数 / 步骤标号 / 分段进度条 ── */
.hud { position:absolute; left:52px; bottom:@@hud_b@@px;
  display:flex; flex-direction:column;
  font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:12px; line-height:1.75; letter-spacing:.06em; color:@@muted@@; }
.hud b { color:@@accent@@; font-weight:700; }
.steplabel { position:absolute; right:52px; bottom:calc(@@pb@@px + @@hud_b@@px); text-align:right;
  display:flex; flex-direction:column;
  font-family:ui-monospace, Consolas, "Courier New", monospace;
  font-size:12px; line-height:1.75; letter-spacing:.10em; color:@@muted@@; }
.steplabel b { color:@@accent@@; font-weight:700; }
.pbar { position:absolute; left:52px; right:52px; bottom:calc(@@pb@@px + @@pbar_b@@px); height:3px;
  display:flex; gap:5px; }
.pbar i { flex:1; background:@@pbar_off@@; display:block; }
.pbar i.on { background:@@accent@@; }

/* ── 字幕条（底板常驻，仅文字随句切换） ──── */
.cap-band { position:absolute; left:@@pl@@px; right:@@pr@@px; bottom:@@pb@@px; height:@@band_h@@px;
  background:@@band@@; border-top:3px solid @@accent@@; }
.cap-layer { position:absolute; left:@@pl@@px; right:@@pr@@px; bottom:@@pb@@px; height:@@band_h@@px;
  display:flex; align-items:center; justify-content:center; padding-bottom:8px; }
.cap-layer span { font-size:@@cap_size@@px; font-weight:900; color:@@band_ink@@; letter-spacing:.01em; }

/* ── 结尾淡出黑幕 ───────────────────────── */
.fadeclip { pointer-events:none; }
#fadeout { position:absolute; inset:0; background:#000; opacity:0; }
"""


def esc(s: str) -> str:
    return html.escape(str(s or ""))


def parse_motion(motion: str) -> list[tuple[str, str]]:
    """解析分镜里写的动效串，如 "TYPES 标题 → FLOATS 卡片"。

    返回 [(动词, 目标), ...]；目标为空表示作用于整张卡片的直接子元素。
    未登记的动词会被忽略（分镜侧已由 storyboard_to_cards.py 拦截）。
    """
    out: list[tuple[str, str]] = []
    if not motion:
        return out
    for seg in re.split(r"→|->|\u2192", str(motion)):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"^([A-Za-z]+)\s*(.*)$", seg)
        if not m:
            continue
        verb, target = m.group(1).upper(), m.group(2).strip()
        if verb in VERBS:
            out.append((verb, target))
    return out


def typewriter(text: str) -> str:
    """把文字拆成逐字 span，供 TYPES 动效使用。换行用 .ln 分块，不用 <br>。"""
    lines = str(text or "").split("\n")
    return "".join(
        '<span class="ln">' + "".join(f'<span class="ch">{esc(c)}</span>' for c in ln) + "</span>"
        for ln in lines
    )


def js_obj(d: dict) -> str:
    """Python dict → JS 对象字面量：字符串带引号，数字裸写。

    不能直接用 json.dumps 再剥引号——那会把 ease: "power2.out" 变成
    ease: power2.out，在 JS 里是未定义变量，动效整段失效（已实测踩过）。
    """
    parts = []
    for k, v in d.items():
        parts.append(f'{k}: "{v}"' if isinstance(v, str) else f"{k}: {v}")
    return "{ " + ", ".join(parts) + " }"


def _item_text(it) -> str:
    if isinstance(it, str):
        return it
    return str(it.get("text") or it.get("value") or "")


def _item_field(it, key: str) -> str:
    if isinstance(it, str):
        return it if key == "text" else ""
    return str(it.get(key) or "")


def parse_stat(v: str):
    """把 "3.16%" / "100000+" / "48" 拆成 (数值, 小数位, 前缀, 后缀)。拆不出返回 None。"""
    m = re.match(r"^([^\d\-+.]*)([-+]?\d+(?:\.\d+)?)(.*)$", str(v).strip())
    if not m:
        return None, 0, "", ""
    pre, num, suf = m.group(1), m.group(2), m.group(3)
    dec = len(num.split(".")[1]) if "." in num else 0
    return float(num), dec, pre, suf


def render_card(card: dict, idx: int, total: int) -> str:
    beats = parse_motion(card.get("motion", ""))
    title_verbs = [v for v, t in beats if t == "标题" or t == ""]
    need_rule = any(v == "DRAWS" for v, _ in beats)

    blocks = ""
    n_blocks = len(card.get("blocks", []) or [])
    for b in card.get("blocks", []):
        label = f'<div class="bl">{esc(b.get("label", ""))}</div>' if b.get("label") else ""
        blocks += f'<div class="block">{label}<div class="bt">{esc(b.get("text", ""))}</div></div>'
    if blocks:
        # 必须包一层 .blocks —— TARGET_SEL「卡片」选择器依赖它，
        # 且 .blocks 的 gap / margin-top 也只对它生效（不加会贴死，已实测）
        cls = f"blocks n{min(n_blocks, 3)}" if n_blocks else "blocks"
        blocks = f'<div class="{cls}">{blocks}</div>'
    if card.get("big"):  # 大字对比式（3小时 → 5分钟）
        blocks = (
            f'<div class="blocks"><div class="row">'
            f'<span class="bignum">{esc(card["big"][0])}</span>'
            f'<span class="arrow">→</span>'
            f'<span class="bignum">{esc(card["big"][1])}</span>'
            f'</div></div>'
        )
    kicker = f'<div class="kicker">{esc(card.get("kicker", ""))}</div>' if card.get("kicker") else ""
    subtitle = f'<div class="subtitle">{esc(card["subtitle"])}</div>' if card.get("subtitle") else ""

    # 信息单元（可选，与 blocks 并存）
    units_html = ""
    for u in (card.get("units") or []):
        items = u.get("items") or []
        note = f'<div class="unit-note">{esc(u["note"])}</div>' if u.get("note") else ""
        ut = u.get("type")
        if ut == "list":
            rows = ""
            for i, it in enumerate(items, 1):
                txt = _item_text(it)
                mark = (f'<span class="lin">{i:02d}</span>' if u.get("numbered", True)
                        else '<span class="lic"></span>')
                rows += f'<div class="li">{mark}<span class="lit">{esc(txt)}</span></div>'
            units_html += (f'<div class="unit-list" data-drift="'
                           f'{1 if u.get("drift", True) else 0}">{rows}</div>{note}')
        elif ut == "stat":
            cells = ""
            for i, it in enumerate(items):
                lab = esc(_item_field(it, "label"))
                val = _item_field(it, "value")
                num, dec, pre, suf = parse_stat(val)
                if num is None:
                    shown, data = esc(val), ""
                else:
                    shown = f'{esc(pre)}{num:.{dec}f}'
                    data = (f' data-num="{num}" data-dec="{dec}" data-pre="{esc(pre)}"'
                            f' data-suf="{esc(suf)}"')
                unit = f'<span class="su">{esc(suf)}</span>' if suf else ""
                ticks = "".join(f'<i style="left:{k * 7.2:.1f}%"></i>' for k in range(14))
                cells += (f'<div class="si" data-i="{i}"><div class="sl">{lab}</div>'
                          f'<div class="srow"><span class="sv"{data}>{shown}</span>{unit}</div>'
                          f'<div class="stape">{ticks}</div></div>')
            units_html += f'<div class="unit-stat">{cells}</div>{note}'
        elif ut == "compare":
            cls = "unit-compare n4" if len(items) >= 4 else "unit-compare n2"
            cells = ""
            for it in items:
                cells += (f'<div class="ci"><div class="cl">'
                          f'{esc(_item_field(it, "label"))}</div>'
                          f'<div class="ct">{esc(_item_field(it, "text"))}</div></div>')
            units_html += f'<div class="{cls}">{cells}</div>{note}'
        elif ut == "steps":
            rows = ""
            for i, it in enumerate(items, 1):
                rows += (f'<div class="sp" data-i="{i}"><span class="sn">{i:02d}</span>'
                         f'<span class="stx">{esc(_item_text(it))}</span></div>')
            units_html += (f'<div class="unit-steps"><div class="marker"></div>'
                           f'{rows}</div>{note}')

    dots = "".join(f'<i class="{"on" if i == idx else ""}"></i>' for i in range(total))
    pbar = "".join(f'<i class="{"on" if i == idx else ""}"></i>' for i in range(total))
    step = card.get("step") or f"{idx + 1:02d} / {total:02d}"
    n_chars = sum(len(c.get("text", "")) for c in card.get("captions", []))
    sec = card.get("duration", 0)

    title_raw = card.get("title", "")
    title_html = typewriter(title_raw) if "TYPES" in title_verbs else esc(title_raw)
    rule = '<div class="rule"></div>' if need_rule else ""
    return f"""
  <div class="clip card" data-start="{card['start']:.3f}" data-duration="{card['duration']:.3f}" data-track-index="1" id="card{idx}">
    <div class="card-inner" data-motion="{esc(card.get('motion', ''))}">
      <div class="kicker-wrap">{kicker}</div>
      <div class="title">{title_html}</div>
      {rule}
      {blocks}
      {units_html}
      {subtitle}
    </div>
    <div class="pagebar">
      <div class="pageno">{idx + 1:02d} / {total:02d}</div>
      <div class="progress">{dots}</div>
    </div>
    <div class="readout">
      <div class="ro"><span class="rl">SEC</span><span class="rv">{sec:.1f}</span></div>
      <div class="ro"><span class="rl">CHAR</span><span class="rv">{n_chars}</span></div>
    </div>
    <div class="steplabel">STEP <b>{esc(step)}</b></div>
    <div class="pbar">{pbar}</div>
  </div>"""


def render_caption(cap: dict, idx: int) -> str:
    # 末尾收 0.04s：避免相邻字幕在句界处同时为可见态而互相遮挡
    dur = max(cap["duration"] - 0.04, 0.12)
    return (f'\n  <div class="clip cap" data-start="{cap["start"]:.3f}" '
            f'data-duration="{dur:.3f}" data-track-index="2" id="cap{idx}">'
            f'<div class="cap-layer"><span>{esc(cap.get("text", ""))}</span></div></div>')


def build(deck: dict) -> str:
    cards = deck["cards"]
    total = len(cards)
    end = max(c["start"] + c["duration"] for c in cards)
    # 画幅在样式之上叠加（局部遮蔽模块级 W/H：本函数后半段的骨架按它渲染画布尺寸）
    fmt = FORMATS.get(str(deck.get("format", "landscape")), FORMATS["landscape"])
    W, H = fmt["size"]
    st = {**STYLES.get(str(deck.get("style", "grid-dark")), STYLES["grid-dark"]),
          **fmt["geom"]}
    # steps 标记条每拍位移 = 行高 + 行距（随画幅一起变，否则标记条与文字错位）
    steps_pitch = int(st.get("sp_h", 58)) + 12
    avg = sum(c["duration"] for c in cards) / max(total, 1)
    hud = (
        f'<span>CARDS:<b>{total:02d}</b></span>'
        f'<span>DUR:<b>{end:.1f}s</b></span>'
        f'<span>AVG:{avg:.1f}s</span>'
    )

    card_html = "".join(render_card(c, i, total) for i, c in enumerate(cards))

    caps, ci = [], 0
    for c in cards:
        for cap in c.get("captions", []):
            caps.append(render_caption(cap, ci))
            ci += 1
    cap_html = "".join(caps)

    audio = ""
    if deck.get("audio"):
        audio = (f'\n  <audio id="vo" src="{esc(deck["audio"])}" data-start="0" '
                 f'data-duration="{end:.3f}" data-volume="{deck.get("volume", 1.0)}"></audio>')

    # 入场动画：只动子元素，不动 .clip；用 fromTo 避免与 CSS transform 冲突
    anim = []
    BEAT_STEP = 0.32      # 各动效节拍之间的间隔
    for i, c in enumerate(cards):
        s = c["start"]
        beats = parse_motion(c.get("motion", ""))
        if beats:
            # 分镜驱动：按分镜写的动词逐个节拍执行
            for k, (verb, target) in enumerate(beats):
                t = s + k * BEAT_STEP
                base = f"#card{i} .card-inner"
                sel = f"{base} {TARGET_SEL[target]}" if target in TARGET_SEL else f"{base} > *"
                spec = VERBS[verb]
                if spec.get("special") == "types":
                    anim.append(
                        f'  tl.fromTo("{sel} .ch", {{ opacity: 0 }}, '
                        f'{{ opacity: 1, duration: .28, stagger: .045, ease: "none" }}, {t:.3f});')
                elif spec.get("special") == "draws":
                    anim.append(
                        f'  tl.fromTo("#card{i} .rule", {{ scaleX: 0, transformOrigin: "left center" }}, '
                        f'{{ scaleX: 1, duration: .55, ease: "power2.inOut" }}, {t:.3f});')
                else:
                    anim.append(f'  tl.fromTo("{sel}", {js_obj(spec["from"])}, '
                                f'{js_obj(spec["to"])}, {t:.3f});')
        else:
            # 未写分镜动效：回退到默认入场
            anim.append(
                f'  tl.fromTo("#card{i} .card-inner > *", '
                f'{{ y: 26, opacity: 0 }}, {{ y: 0, opacity: 1, duration: .55, stagger: .09, ease: "power2.out" }}, {s:.3f});')
        # 相机推进：无论是否分镜驱动都保留（对标样本的推镜）
        if c["duration"] > 3:
            anim.append(
                f'  tl.fromTo("#card{i} .card-inner", {{ scale: 1 }}, '
                f'{{ scale: 1.045, duration: {c["duration"]:.3f}, ease: "none" }}, {s:.3f});')
        t_in = str(c.get("transition_in", "") or "")
        if "FADE" in t_in.upper() or "淡入" in t_in:
            anim.append(f'  tl.fromTo("#card{i} .card-inner", {{ opacity: 0 }}, '
                        f'{{ opacity: 1, duration: .35, ease: "power1.out" }}, {s:.3f});')

        # ── list 单元：逐项「scale 找位」+ 容器**线性漂移**（两层运动解耦） ──
        if any(u.get("type") == "list" for u in (c.get("units") or [])):
            spec = UNITS["list"]
            if c["duration"] > 2.0:
                anim.append(
                    f'  tl.fromTo("#card{i} .unit-list", {{ y: {spec["drift_px"]} }}, '
                    f'{{ y: -{spec["drift_px"]}, duration: {c["duration"]:.3f}, ease: "none" }}, {s:.3f});')
            anim.append(
                f'  tl.fromTo("#card{i} .unit-list .li", '
                f'{{ opacity: 0, scale: {spec["start_scale"]}, y: {spec["start_y"]} }}, '
                f'{{ opacity: 1, scale: 1, y: 0, duration: {spec["item_dur_s"]}, '
                f'stagger: {spec["stagger_s"]}, ease: "{spec["ease"]}" }}, {s + 0.35:.3f});')

        # ── stat 单元：数值爬升 + 刻度带滑入（借 gauge-readout-moves 式 B） ──
        if any(u.get("type") == "stat" for u in (c.get("units") or [])):
            spec = UNITS["stat"]
            for k in range(spec["max_items"]):
                t = s + 0.30 + k * spec["stagger_s"]
                js = (
                    "(function(){var e=document.querySelector('#card%d .unit-stat .si[data-i=\"%d\"] "
                    ".sv[data-num]');if(!e)return;var o={v:0},dec=parseInt(e.dataset.dec,10);"
                    "tl.to(o,{v:parseFloat(e.dataset.num),duration:%s,ease:\"%s\","
                    "onUpdate:function(){e.textContent=(e.dataset.pre||'')+o.v.toFixed(dec);}},%s);})()"
                    % (i, k, spec["count_dur_s"], spec["ease"], "%.3f" % t)
                )
                anim.append("  " + js + ";")
            anim.append(
                f'  tl.fromTo("#card{i} .unit-stat .stape", {{ opacity: 0, x: -34 }}, '
                f'{{ opacity: 1, x: 0, duration: .6, stagger: .18, ease: "power2.out" }}, '
                f'{s + 0.30:.3f});')

        # ── compare 单元：并列面板**错拍**入场（借 quad-split-parallel-scenes） ──
        if any(u.get("type") == "compare" for u in (c.get("units") or [])):
            spec = UNITS["compare"]
            anim.append(
                f'  tl.fromTo("#card{i} .unit-compare .ci", '
                f'{{ opacity: 0, y: {spec["start_y"]} }}, '
                f'{{ opacity: 1, y: 0, duration: {spec["item_dur_s"]}, '
                f'stagger: {spec["stagger_s"]}, ease: "{spec["ease"]}" }}, {s + 0.30:.3f});')

        # ── steps 单元：高亮**逐拍推进**（借 beat-step-list-theme-cycle） ──
        for u in (c.get("units") or []):
            if u.get("type") != "steps":
                continue
            spec = UNITS["steps"]
            n = len(u.get("items") or [])
            base = s + 0.35
            if n == 0:
                continue
            anim.append(
                f'  tl.to("#card{i} .unit-steps .sp[data-i=\\"1\\"]", '
                f'{{ opacity: 1, duration: {spec["snap_s"]}, ease: "{spec["ease"]}" }}, {base:.3f});')
            for k in range(2, n + 1):
                t = base + (k - 1) * spec["beat_s"]
                anim.append(
                    f'  tl.to("#card{i} .unit-steps .marker", '
                    f'{{ y: {(k - 1) * steps_pitch}, duration: {spec["snap_s"]}, '
                    f'ease: "{spec["ease"]}" }}, {t:.3f});')
                anim.append(
                    f'  tl.to("#card{i} .unit-steps .sp[data-i=\\"{k}\\"]", '
                    f'{{ opacity: 1, duration: {spec["snap_s"]}, ease: "{spec["ease"]}" }}, {t:.3f});')

    # 结尾淡出到黑：末镜写了「到黑/FADE」就加一层黑幕
    last = cards[-1]
    t_out = str(last.get("transition_out", "") or "")
    need_fadeout = "黑" in t_out or "FADE" in t_out.upper()
    if need_fadeout:
        fade_at = max(end - 0.9, 0)
        anim.append(f'  tl.fromTo("#fadeout", {{ opacity: 0 }}, '
                    f'{{ opacity: 1, duration: .85, ease: "power2.in" }}, {fade_at:.3f});')

    # 字幕各自按自己的 start 淡入
    j = 0
    for c in cards:
        for cap in c.get("captions", []):
            anim.append(f'  tl.fromTo("#cap{j} .cap-layer", {{ opacity: 0 }}, '
                        f'{{ opacity: 1, duration: .18 }}, {cap["start"]:.3f});')
            j += 1

    anim_js = "\n".join(anim)
    fadeout_html = (
        f'\n  <div class="clip fadeclip" id="fadeclip" data-start="0" data-duration="{end:.3f}" data-track-index="3">'
        f'<div id="fadeout"></div></div>' if need_fadeout else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>{css_for(st)}</style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0"
         data-duration="{end:.3f}" data-width="{W}" data-height="{H}">

      <div class="clip bgclip" id="stage-bg" data-start="0" data-duration="{end:.3f}" data-track-index="0">
        <div class="stage">
          <div class="corner c-tl"></div><div class="corner c-tr"></div>
          <div class="corner c-bl"></div><div class="corner c-br"></div>
          <div class="stamp-l">
            <span>RESEARCH CARD</span>
            <span>{esc(deck.get('series', ''))}</span>
            <span>{esc(deck.get('episode', ''))}</span>
          </div>
          <div class="stamp-b">
            <span>VERSION.</span>
            <span>CARD 4:3 / AUTO 2.0</span>
          </div>
          <div class="panel">
            <div class="dots"><i></i><i></i><i></i></div>
            <div class="crumb">‹ {esc(deck.get('breadcrumb', ''))} ›</div>
            <div class="frame">
              <div class="bracket b-tl"></div><div class="bracket b-tr"></div>
              <div class="bracket b-bl"></div><div class="bracket b-br"></div>
            </div>
            <div class="hud">{hud}</div>
          </div>
          <div class="cap-band"></div>
        </div>
      </div>
{card_html}
{cap_html}
{audio}{fadeout_html}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
{anim_js}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    deck = json.loads(Path(args.cards).read_text(encoding="utf-8"))
    if not deck.get("cards"):
        print("[fail] cards 为空", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(deck), encoding="utf-8")
    total = sum(len(c.get("captions", [])) for c in deck["cards"])
    end = max(c["start"] + c["duration"] for c in deck["cards"])
    print(f"[ok] {out} | 卡片 {len(deck['cards'])} 张 / 字幕 {total} 条 / 总时长 {end:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
