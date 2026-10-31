#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""card_quality_check.py — 卡片视频质量自检（产线质量层）。

把一条已成片的卡片视频，用**我们自己的证据**算成一张「质量自检卡」。
不渲片、不改模板、不调用任何付费服务。

设计口径（重要，别把它当成完整评分）
------------------------------------
外部付费拆解服务的六维里，只有两维必须靠「外面的眼睛」：
    产品展示 / 情绪曲线     → 我们算不了，标记 external_pending，不假装能算
其余四维 + 画幅适配，都用产物自带的证据本地算：
    Hook / 信息密度 / 节奏控制 / 转化引导 / 画幅适配
门槛分三档，来源写在每一行里：
    实测锚点  = 有实测数字可对（如对标片 C 的静止率 98.7%）
    建议区间  = 我们的判断，不是实测，会随基线积累被替换
    待标定    = 还没有任何依据，只报数不判

证据来源（都是产物自带，零额外依赖）
------------------------------------
    <目录>/deck.json          卡片 + 字幕时间轴（渲染输入，必需）
    <目录>/script.json        可选：_storyboard_role 叙事角色
    <目录>/final.mp4          可选：画面侧指标，转交 motion_check.py 算

用法
----
    python scripts/card_quality_check.py <产物目录> [--video PATH]
                                        [--platform 视频号] [--json]
                                        [--no-record] [--history PATH]

退出码
------
    0  测量完成，无硬失败（区间提示不算失败）
    2  输入缺失 / 不可读（找不到 deck.json 等）
    3  硬失败：画幅声明与实际不符、或卡片时间轴有缝/重叠
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOOK_WINDOW_S = 3.0
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_HISTORY = REPO_ROOT / "video-line" / "quality" / "history.jsonl"

# 竖屏优先的平台（视频号/抖音/小红书/快手都是一进就满屏竖屏）
VERTICAL_PLATFORMS = {"视频号", "抖音", "小红书", "快手"}

# 生成器的画幅表（只用来判「声明 vs 实际」是否自洽，不参与版面）
FORMAT_PIXELS = {"landscape": (1440, 1080), "vertical": (1080, 1920)}

# CTA 词表：命中即认为末卡承担了转化引导。可扩展，但别往里塞泛词。
CTA_KEYWORDS = (
    "关注", "点赞", "收藏", "转发", "分享", "评论", "私信", "订阅",
    "链接", "评论区", "置顶", "领取", "下单", "购买", "加群", "回复",
)

PUNCT = set("，。、；：？！“”‘’（）《》〈〉【】—…·,.!?;:\"'()[]{}<>-—/\\|~`@#$%^&*+=_")


def count_chars(text: str) -> tuple[int, int]:
    """返回 (不含标点字数, 含标点字数)。字 = 汉字 + 字母数字。"""
    t = "".join(text.split())
    no_punct = sum(1 for ch in t if ch not in PUNCT)
    return no_punct, len(t)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def probe_video(video: Path) -> dict:
    """ffprobe 取分辨率与时长；失败只标记，不中断。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-show_entries", "format=duration",
             "-of", "json", str(video)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return {"failed": True, "error": (r.stderr or "")[:200]}
        d = json.loads(r.stdout)
        st = (d.get("streams") or [{}])[0]
        return {
            "width": st.get("width"),
            "height": st.get("height"),
            "duration_s": round(float(d.get("format", {}).get("duration") or 0), 2),
        }
    except Exception as e:  # noqa: BLE001 - 单步失败只标记，按仓库铁律不中断
        return {"failed": True, "error": str(e)[:200]}


def run_motion_check(video: Path) -> dict:
    """复用产线第四道门（motion_check.py）算画面侧指标。"""
    script = SCRIPT_DIR / "motion_check.py"
    if not script.exists():
        return {"failed": True, "error": "找不到 motion_check.py"}
    try:
        r = subprocess.run(
            [sys.executable, str(script), str(video), "--style", "card", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode not in (0, 3):
            return {"failed": True, "error": (r.stderr or r.stdout or "")[:200]}
        return json.loads(r.stdout)
    except Exception as e:  # noqa: BLE001
        return {"failed": True, "error": str(e)[:200]}


def cards_timeline(cards: list) -> dict:
    """卡片时间轴完整性：缝隙、重叠、首卡起点、总时长。"""
    gaps, overlaps = [], []
    prev_end = None
    for i, c in enumerate(cards):
        start = float(c.get("start", 0.0))
        dur = float(c.get("duration", 0.0))
        if prev_end is not None:
            delta = round(start - prev_end, 3)
            if delta < -0.001:
                overlaps.append({"gap_s": delta, "after_card": i})
            elif delta > 0.001:
                gaps.append({"gap_s": delta, "after_card": i})
        start = max(start, 0.0)
        dur = max(dur, 0.0)
        prev_end = start + dur
    total = round(prev_end or 0.0, 2)
    return {
        "gaps": gaps,
        "overlaps": overlaps,
        "first_start_s": round(float(cards[0].get("start", 0.0)), 3) if cards else None,
        "total_s": total,
    }


def collect_captions(cards: list) -> list:
    out = []
    for c in cards:
        for cap in c.get("captions") or []:
            out.append({
                "text": str(cap.get("text") or ""),
                "start": float(cap.get("start", 0.0)),
                "duration": float(cap.get("duration", 0.0)),
            })
    return out


def unit_stats(card: dict) -> tuple[int, int]:
    """返回 (单元数, 信息点条数)。items 不是列表时该单元记 1 点。"""
    units = card.get("units") or []
    points = 0
    for u in units:
        items = u.get("items")
        points += len(items) if isinstance(items, list) else 1
    return len(units), points


def card_text(card: dict) -> str:
    """把一张卡上会被观众读到的文字拼起来（用于 CTA 与密度判断）。"""
    parts = [str(card.get("title") or ""), str(card.get("kicker") or "")]
    for u in card.get("units") or []:
        for k in ("items", "left", "right", "value", "label", "note", "body"):
            v = u.get(k)
            if isinstance(v, list):
                parts += [str(x) for x in v]
            elif v is not None:
                parts.append(str(v))
    parts += [c["text"] for c in card.get("captions") or []]
    return " ".join(parts)


def card_at(cards: list, t: float) -> int | None:
    """t 落在第几张卡（1 基）。用于把画面侧的「死区」定位到具体哪一镜。"""
    for i, c in enumerate(cards):
        start = float(c.get("start", 0.0))
        end = start + float(c.get("duration", 0.0))
        if start <= t < end:
            return i + 1
    return None


def per_card_dead_zone(cards: list, runs: list) -> list[dict]:
    """把画面侧「静止段」映射到每张卡，得到每卡死区（秒）。

    这是把「最长静止 2.10s」变成一个能动手的信息：是哪一卡、多久、动效用了几个目标。
    """
    out = []
    for i, c in enumerate(cards):
        cs = float(c.get("start", 0.0))
        ce = cs + float(c.get("duration", 0.0))
        total = longest = 0.0
        for a, b in runs or []:
            ov = max(0.0, min(float(b), ce) - max(float(a), cs))
            total += ov
            longest = max(longest, ov)
        motion = str(c.get("motion") or "")
        out.append({
            "card": i + 1,
            "duration_s": round(ce - cs, 2),
            "still_s": round(total, 2),
            "longest_still_s": round(longest, 2),
            "motion_targets": motion.count("→") + (1 if motion else 0),
        })
    return out


def build_metrics(deck: dict, script: dict | None, video_probe: dict,
                  motion: dict | None, platform: str | None) -> dict:
    cards = deck.get("cards") or []
    caps = collect_captions(cards)
    tl = cards_timeline(cards)
    total_s = tl["total_s"] or 1.0

    # ── Hook：固定前 3 秒窗口 ──────────────────────────────────────
    hook_caps = [c for c in caps if c["start"] < HOOK_WINDOW_S]
    hook_no_punct, hook_all = 0, 0
    for c in hook_caps:
        a, b = count_chars(c["text"])
        hook_no_punct += a
        hook_all += b
    hook_cps = round(hook_no_punct / HOOK_WINDOW_S, 2)

    # ── 信息密度 ───────────────────────────────────────────────────
    all_no_punct = sum(count_chars(c["text"])[0] for c in caps)
    chars_per_s = round(all_no_punct / total_s, 2)
    total_units = sum(unit_stats(c)[0] for c in cards)
    total_points = sum(unit_stats(c)[1] for c in cards)
    points_per_s = round(total_points / total_s, 3)

    # ── 节奏控制 ───────────────────────────────────────────────────
    durs = [float(c.get("duration", 0.0)) for c in cards]
    mean_d = round(sum(durs) / len(durs), 2) if durs else 0.0
    var = sum((d - mean_d) ** 2 for d in durs) / len(durs) if durs else 0.0
    trans = [str(c.get("transition_out") or "") for c in cards]
    trans_kinds = sorted({t for t in trans if t})
    hard_cut_ratio = round(sum(1 for t in trans if t == "硬切") / len(trans), 2) if trans else 0.0
    verbs = sorted({str(c.get("motion") or "").split()[0] for c in cards if c.get("motion")})

    # ── 转化引导 ───────────────────────────────────────────────────
    last = cards[-1] if cards else {}
    last_text = card_text(last)
    cta_hits = [k for k in CTA_KEYWORDS if k in last_text]
    last_s = float(last.get("duration", 0.0))

    # ── 画幅适配 ───────────────────────────────────────────────────
    declared = str(deck.get("format") or "landscape")
    expect = FORMAT_PIXELS.get(declared)
    actual = (video_probe.get("width"), video_probe.get("height"))
    format_consistent = None
    if expect and not video_probe.get("failed"):
        format_consistent = actual == expect
    platform_fit = None
    if platform and not video_probe.get("failed"):
        want_vertical = platform in VERTICAL_PLATFORMS
        is_vertical = (video_probe.get("height") or 0) > (video_probe.get("width") or 0)
        platform_fit = (is_vertical == want_vertical)

    roles = (script or {}).get("_storyboard_role") or []

    # 画面侧读数是否可信：motion_check 自带两套画幅的内容区，它会回传认出的画幅；
    # 只有它没跑成（分辨率不在它的内容区表内、或读取失败）才算读数作废。
    motion_reliable = (
        not video_probe.get("failed")
        and bool(motion)
        and not (motion or {}).get("failed")
        and bool((motion or {}).get("format"))
    )

    return {
        "total_s": total_s,
        "card_count": len(cards),
        "format_declared": declared,
        "format_actual": list(actual),
        "format_consistent": format_consistent,
        "platform": platform,
        "platform_fit": platform_fit,
        "hook": {
            "window_s": HOOK_WINDOW_S,
            "caption_count": len(hook_caps),
            "chars_no_punct": hook_no_punct,
            "chars_with_punct": hook_all,
            "chars_per_s": hook_cps,
            "first_role": roles[0] if roles else None,
        },
        "density": {
            "chars_no_punct": all_no_punct,
            "chars_per_s": chars_per_s,
            "unit_count": total_units,
            "info_points": total_points,
            "points_per_s": points_per_s,
        },
        "pacing": {
            "card_min_s": round(min(durs), 2) if durs else 0.0,
            "card_max_s": round(max(durs), 2) if durs else 0.0,
            "card_mean_s": mean_d,
            "card_std_s": round(var ** 0.5, 2) if durs else 0.0,
            "transitions": trans_kinds,
            "hard_cut_ratio": hard_cut_ratio,
            "motion_verbs": verbs,
            "timeline_gaps": tl["gaps"],
            "timeline_overlaps": tl["overlaps"],
            "still_ratio": (motion or {}).get("still_ratio"),
            "longest_still_s": (motion or {}).get("longest_still_s"),
            "diff_mean": (motion or {}).get("diff_mean"),
            "motion_reliable": motion_reliable,
            "motion_format": (motion or {}).get("format"),
            "motion_content_rect": (motion or {}).get("content_rect"),
            "longest_still_from_s": (motion or {}).get("longest_still_from_s"),
            "longest_still_to_s": (motion or {}).get("longest_still_to_s"),
            "longest_still_card": (
                card_at(cards,
                        ((motion or {}).get("longest_still_from_s") or 0.0)
                        + ((motion or {}).get("longest_still_s") or 0.0) / 2.0)
                if motion_reliable and (motion or {}).get("longest_still_s") else None
            ),
            "per_card_dead_zone": (
                per_card_dead_zone(cards, (motion or {}).get("still_runs"))
                if motion_reliable else []
            ),
        },
        "cta": {
            "hits": cta_hits,
            "has_cta": bool(cta_hits),
            "last_card_s": round(last_s, 2),
            "last_card_share": round(last_s / total_s, 2) if total_s else 0.0,
        },
        "external_pending": {
            "产品展示": "只能由外部检测出分（本地无对应可验证证据）",
            "情绪曲线": "只能由外部检测出分（本地无对应可验证证据）",
        },
        "evidence_gaps": (
            (["无 final.mp4：画面侧指标（静止率/最长静止）未测"] if video_probe.get("failed") else [])
            + (["motion_check 未跑成：画面侧指标缺失（%s）" % (motion or {}).get("error", "未知原因")]
               if (motion and motion.get("failed")) else [])
            + (["无 script.json：叙事角色未取到"] if not roles else [])
        ),
    }


def judge(m: dict) -> list[tuple[str, str, str, str, str]]:
    """返回 (维度, 指标, 实测, 门槛, 门槛来源/判定) 行。"""
    rows: list[tuple[str, str, str, str, str]] = []

    # 画幅：声明 vs 实际 —— 硬判据，不需要任何外部知识
    if m["format_consistent"] is False:
        rows.append(("画幅适配", "声明 vs 实际", f"{m['format_declared']} → {tuple(m['format_actual'])}",
                     "两者必须一致", "硬失败"))
    elif m["format_consistent"] is True:
        rows.append(("画幅适配", "声明 vs 实际", f"{m['format_declared']} → {tuple(m['format_actual'])}",
                     "两者必须一致", "通过"))
    else:
        rows.append(("画幅适配", "声明 vs 实际", "未测（无 final.mp4）", "两者必须一致", "证据缺失"))

    if m["platform_fit"] is True:
        rows.append(("画幅适配", f"适配 {m['platform']}", "匹配", "竖屏平台要竖屏成片", "通过"))
    elif m["platform_fit"] is False:
        rows.append(("画幅适配", f"适配 {m['platform']}", "不匹配", "竖屏平台要竖屏成片", "硬失败"))
    elif m["platform"] is None:
        rows.append(("画幅适配", "适配目标平台", "未指定 --platform", "竖屏平台要竖屏成片", "待标定"))

    # 时间轴：硬判据
    gaps, ov = m["pacing"]["timeline_gaps"], m["pacing"]["timeline_overlaps"]
    rows.append(("节奏控制", "卡片时间轴",
                 f"缝隙 {len(gaps)} 处 / 重叠 {len(ov)} 处",
                 "0 / 0", "硬失败" if (gaps or ov) else "通过"))

    h = m["hook"]
    rows.append(("Hook", "前3秒语速（字/秒）", h["chars_per_s"], "5.0 – 7.0",
                 "参考（同全片锚点 C 6.03 / 本线 6.07；跨窗字幕整条计入，会略高估）"))
    rows.append(("Hook", "前3秒字幕条数", h["caption_count"], "2 – 4 条",
                 "推导值（3s × 5–7 字/秒 ÷ 每条约 6–8 字）"))
    if h["first_role"]:
        rows.append(("Hook", "首镜叙事角色", h["first_role"], "应为「钩子」",
                     "实测锚点（storyboard 声明）"))

    d = m["density"]
    rows.append(("信息密度", "全片语速（字/秒）", d["chars_per_s"], "5.0 – 7.0",
                 "建议区间（锚点同上）"))
    rows.append(("信息密度", "信息点/秒", d["points_per_s"], "—", "待标定"))
    rows.append(("信息密度", "总信息点", d["info_points"], "—", "待标定"))

    p = m["pacing"]
    rows.append(("节奏控制", "卡片时长 min/mean/max(s)",
                 f"{p['card_min_s']} / {p['card_mean_s']} / {p['card_max_s']}", "—", "待标定"))
    if p["still_ratio"] is not None and not p["motion_reliable"]:
        rows.append(("节奏控制", "静止帧占比", "不可信（见下）", "—",
                     "读数作废：motion_check 未认出画幅"))
        rows.append(("节奏控制", "最长静止(s)", "不可信（见下）", "—",
                     "读数作废：同上"))
    else:
        src = ("motion_check（画幅 %s，内容区 %s）"
               % (p.get("motion_format") or "?", p.get("motion_content_rect") or "?"))
        rows.append(("节奏控制", "静止帧占比", p["still_ratio"] if p["still_ratio"] is not None else "未测",
                     "≤ 40%（借自 MG；卡片形态尚无自有门槛，只报告）", src))
        still_txt = p["longest_still_s"] if p["longest_still_s"] is not None else "未测"
        where = ""
        if p.get("longest_still_card") and p.get("longest_still_from_s") is not None:
            where = "｜死区在第 %d 张卡 %.2f–%.2fs（该段像素不变）" % (
                p["longest_still_card"],
                p.get("longest_still_from_s") or 0.0,
                p.get("longest_still_to_s") or 0.0,
            )
        rows.append(("节奏控制", "最长静止(s)", still_txt,
                     "≤ 1.0s 借自 MG；卡片形态待标定", ("同上" + where)))
        dz = p.get("per_card_dead_zone") or []
        if dz:
            spell = " / ".join("%.1f" % d["longest_still_s"] for d in dz)
            worst = max(dz, key=lambda d: d["longest_still_s"])
            spread = max(d["longest_still_s"] for d in dz) - min(d["longest_still_s"] for d in dz)
            rows.append(("节奏控制", "每卡死区(秒,按序)", spell,
                         "卡片形态待标定",
                         "最长为第 %d 张 %.2fs（动效目标 %d 个）；极差 %.2fs —— "
                         "极差比绝对值更该盯：同一片内忽长忽短＝节奏不匀"
                         % (worst["card"], worst["longest_still_s"],
                            worst["motion_targets"], spread)))
    rows.append(("节奏控制", "转场种类", "、".join(p["transitions"]) or "无",
                 "—", "待标定"))
    rows.append(("节奏控制", "硬切占比", p["hard_cut_ratio"], "—", "待标定"))

    c = m["cta"]
    rows.append(("转化引导", "末卡是否含 CTA", "是" if c["has_cta"] else "否",
                 "建议为是", "建议值（命中词：%s）" % ("、".join(c["hits"]) if c["hits"] else "无")))
    rows.append(("转化引导", "末卡占比", c["last_card_share"], "—", "待标定"))
    return rows


def render(m: dict, rows: list, deck_path: Path) -> str:
    L = []
    L.append("质量自检卡")
    L.append("=" * 46)
    L.append("输入：%s" % deck_path)
    L.append("规格：%s → %sx%s ｜ %.2fs ｜ %d 张卡"
             % (m["format_declared"], m["format_actual"][0] or "?",
                m["format_actual"][1] or "?", m["total_s"], m["card_count"]))
    L.append("")
    cell = [[str(c) for c in r] for r in rows]
    width = [max(len(r[i]) for r in cell) for i in range(4)]
    for dim, name, val, gate, src in rows:
        L.append("%-6s %-22s %-26s %-22s %s"
                 % (dim, str(name).ljust(width[1]), str(val).ljust(width[2]),
                    str(gate).ljust(width[3]), src))
    L.append("")
    for k, v in m["external_pending"].items():
        L.append("外部待测（本线算不了，需外部检测出分）：%s —— %s" % (k, v))
    if m["evidence_gaps"]:
        for g in m["evidence_gaps"]:
            L.append("证据缺失：%s" % g)
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="卡片视频质量自检（本地四维 + 画幅适配）")
    ap.add_argument("out_dir", help="产物目录（含 deck.json）")
    ap.add_argument("--video", default=None, help="成片路径，默认找 <目录>/final.mp4")
    ap.add_argument("--platform", default=None, help="目标平台，如 视频号/抖音/小红书")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-record", action="store_true", help="不追加进历史")
    ap.add_argument("--history", default=str(DEFAULT_HISTORY))
    args = ap.parse_args()

    d = Path(args.out_dir).resolve()
    deck_path = d / "deck.json"
    if not deck_path.exists():
        deck_path = d / "cards.json"
    if not deck_path.exists():
        print("[fail] 找不到 deck.json（也找不到 cards.json）：%s" % d)
        return 2
    try:
        deck = load_json(deck_path)
    except Exception as e:  # noqa: BLE001
        print("[fail] deck.json 读不动：%s" % e)
        return 2

    script = None
    sp = d / "script.json"
    if sp.exists():
        try:
            script = load_json(sp)
        except Exception:  # noqa: BLE001
            script = None

    video = Path(args.video).resolve() if args.video else d / "final.mp4"
    probe = {"failed": True, "error": "无 final.mp4"}
    motion = None
    if video.exists():
        probe = probe_video(video)
        motion = run_motion_check(video)

    m = build_metrics(deck, script, probe, motion, args.platform)
    m["deck"] = str(deck_path)
    m["video"] = str(video) if video.exists() else None
    rows = judge(m)

    hard_fail = any(r[4] == "硬失败" for r in rows)
    m["hard_fail"] = hard_fail

    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=1))
    else:
        print(render(m, rows, deck_path))

    if not args.no_record:
        try:
            hp = Path(args.history)
            hp.parent.mkdir(parents=True, exist_ok=True)
            with open(hp, "a", encoding="utf-8") as f:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
            if not args.json:
                print("\n已记入历史：%s" % hp)
        except Exception as e:  # noqa: BLE001 - 记录失败不影响测量结论
            print("[warn] 历史写入失败：%s" % e, file=sys.stderr)

    return 3 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
