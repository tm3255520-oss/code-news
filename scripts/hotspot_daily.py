#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hotspot_daily.py — 全网社交热点每日落盘（确定性，零 LLM）

产出：<vault>/内容生产/情报与选题/热点与情报/热点监控/<日期>-全网社交热点.md

与既有「AI内容工厂-热点监控」（hot_trend_cron.py → OpenClaw hot_scanner）**互补而非重复**：
那个扫 B站/GitHub/HackerNews/MCP生态（技术向），本脚本扫
抖音/微博/B站/快手/知乎/头条/百度 的热搜事件（社交向）。

数据源：RedFox /story/api/hotKeyword/list，经 redfox_client 调用（复用鉴权），
与已装技能 trending-hub-top10 同源，结果可互相对照。
本脚本只做「取数 → 归一去重 → 排序 → 落 Markdown」等确定性动作，不引入 LLM。

用法：
    python hotspot_daily.py --selftest
    python hotspot_daily.py --dry-run --top 15
    python hotspot_daily.py --top 20 --hours 24
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

HOTSPOT_PATH = "/story/api/hotKeyword/list"
SOURCE_TAG = "热点与情报-每日热点-GitHub"

try:
    from vault_paths import HOTSPOT as HOTSPOT_DIR

    OUT_DIR = HOTSPOT_DIR / "热点监控"
except Exception:  # noqa: BLE001
    OUT_DIR = Path(r"D:\Obsidian Vault\obsidian Vault\内容生产\情报与选题\热点与情报\热点监控")

# 去重时忽略的噪声字符。同一事件在不同平台标题里常只差这些符号，
# 用字符集过滤而不是正则，避免大量转义与边界坑。
_NOISE_CHARS = set(
    " \t\r\n#*【】[]（）()「」《》\"'“”‘’!！?？,，.。、:：;；~～-—_|·…‥・"
)


def norm_title(text: str) -> str:
    """标题归一化，用于跨平台合并同一事件。"""
    return "".join(ch for ch in (text or "").strip() if ch not in _NOISE_CHARS)


def _num(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def merge(items: list[dict]) -> list[dict]:
    """按归一化标题合并同一事件：热度取最大、平台收集齐、首次上榜取更早。"""
    merged: dict[str, dict] = {}
    for it in items:
        title = (it.get("title") or "").strip()
        key = norm_title(title)
        if not title or not key:
            continue
        score = _num(it.get("maxHotScore"))
        plat = (it.get("platName") or "").strip()
        rec = merged.get(key)
        if rec is None:
            merged[key] = {
                "title": title,
                "score": score,
                "plats": [plat] if plat else [],
                "first_rank": (it.get("firstRankTime") or "").strip(),
                "latest_rank": (it.get("latestRankDate") or "").strip(),
                "url": (it.get("url") or "").strip(),
                "keyword": (it.get("source_keyword") or "").strip(),
            }
            continue
        rec["score"] = max(rec["score"], score)
        if plat and plat not in rec["plats"]:
            rec["plats"].append(plat)
        if not rec["url"] and it.get("url"):
            rec["url"] = str(it["url"]).strip()
        fr = (it.get("firstRankTime") or "").strip()
        if fr and (not rec["first_rank"] or fr < rec["first_rank"]):
            rec["first_rank"] = fr
    return sorted(merged.values(), key=lambda r: (-r["score"], r["title"]))


def render(rows: list[dict], top: int, hours: int, now: datetime | None = None) -> str:
    now = now or datetime.now()
    shown = rows[: max(top, 1)]
    lines = [
        f"# 全网社交热点 · {now.strftime('%Y-%m-%d')}",
        "",
        f"> 窗口：近 {hours} 小时 ｜ 原始事件 {len(rows)} 个 ｜ 本表 Top {len(shown)}",
        "> 来源：RedFox 全网热搜（抖音/微博/B站/快手/知乎/头条/百度）",
        "> 用途：选题池参考；链接指向各平台搜索页，非内容转载。",
        "",
        "| # | 热度 | 事件 | 平台 | 首次上榜 |",
        "| ---: | ---: | --- | --- | --- |",
    ]
    for i, r in enumerate(shown, 1):
        title = r["title"].replace("|", "丨")
        link = f"[{title}]({r['url']})" if r["url"] else title
        plats = "、".join(r["plats"]) or "—"
        first = (r["first_rank"] or "")[:16] or "—"
        lines.append(f"| {i} | {r['score']} | {link} | {plats} | {first} |")
    lines += ["", f"*由 hotspot_daily.py 生成于 {now.strftime('%Y-%m-%d %H:%M')}*"]
    return "\n".join(lines)


def write_digest(md: str, date: str, out_dir: Path | None = None) -> Path:
    target = out_dir or OUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    fp = target / f"{date}-全网社交热点.md"
    fp.write_text(md, encoding="utf-8")
    return fp


def flatten(data: Any) -> list[dict]:
    """把接口返回摊平成热点条目列表。

    实测返回形状（2026-09-27）：data 是**按关键词分组的列表**
        [{"keyword": "中美", "plats": ["快手", ...], "hotSpotList": [ {...}, ... ]}, ...]
    每组自带 keyword / plats，条目里可能没有 platName，所以要在这里补上。
    同时兼容 {"hotspots": [...]} 这种扁平形状，免得接口换版就整个静默取空。
    """
    if isinstance(data, dict):
        items = data.get("hotspots")
        return items if isinstance(items, list) else []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for group in data:
        if not isinstance(group, dict):
            continue
        keyword = (group.get("keyword") or "").strip()
        plats = group.get("plats") or []
        group_plat = plats[0] if isinstance(plats, list) and plats else ""
        for h in (group.get("hotSpotList") or []):
            if not isinstance(h, dict):
                continue
            item = dict(h)
            if keyword and not item.get("source_keyword"):
                item["source_keyword"] = keyword
            if group_plat and not item.get("platName"):
                item["platName"] = group_plat
            out.append(item)
    return out


def fetch(hours: int = 24, rf: Any = None) -> list[dict]:
    """取热点原始列表（已摊平）。失败抛异常，由 main 转成退出码 1。"""
    if rf is None:
        from redfox_client import RedFox

        rf = RedFox(sleep=0)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=max(hours, 1))
    data = rf.call(
        HOTSPOT_PATH,
        {
            "source": SOURCE_TAG,
            "startDate": start.strftime("%Y-%m-%d %H:%M:%S"),
            "endDate": now.strftime("%Y-%m-%d %H:%M:%S"),
        },
        quiet=True,
    )
    if data is None:
        raise RuntimeError("热点接口未返回数据（key 无效/配额不足/网络异常）")
    items = flatten(data)
    if not items:
        raise RuntimeError(
            f"热点接口返回结构无法解析: type={type(data).__name__} "
            f"keys={list(data)[:6] if isinstance(data, dict) else len(data)}")
    return items


def selftest() -> int:
    # 摊平：分组形状（实测形状）与扁平形状都要认
    grouped = [
        {"keyword": "中美", "plats": ["快手"],
         "hotSpotList": [{"title": "甲", "maxHotScore": 10, "platName": "快手"}]},
        {"keyword": "AI", "plats": ["微博"],
         "hotSpotList": [{"title": "乙", "maxHotScore": 20}]},   # 条目缺 platName 要补
    ]
    flat = flatten(grouped)
    assert len(flat) == 2, flat
    assert flat[0]["platName"] == "快手" and flat[1]["platName"] == "微博", flat
    assert flat[1]["source_keyword"] == "AI", flat[1]
    assert len(flatten({"hotspots": [{"title": "丙"}]})) == 1
    assert flatten(None) == [] and flatten("x") == []
    assert flatten([{"hotSpotList": []}]) == []
    # 标题归一：符号差异不影响合并
    assert norm_title("中方回应# 美方言论！") == norm_title("中方回应 美方言论")
    assert norm_title("") == ""
    # 跨平台同一事件：热度取最大、平台收集齐、首次上榜取更早、空标题丢弃
    rows = merge([
        {"title": "事件A", "platName": "抖音", "maxHotScore": 100,
         "firstRankTime": "2026-09-26 10:00:00", "url": "u1"},
        {"title": "事件A", "platName": "微博", "maxHotScore": 900,
         "firstRankTime": "2026-09-26 09:00:00"},
        {"title": "事件B", "platName": "快手", "maxHotScore": 500},
        {"title": "", "platName": "百度", "maxHotScore": 999},
    ])
    assert len(rows) == 2, rows
    assert rows[0]["title"] == "事件A" and rows[0]["score"] == 900, rows[0]
    assert rows[0]["plats"] == ["抖音", "微博"], rows[0]
    assert rows[0]["first_rank"] == "2026-09-26 09:00:00", rows[0]["first_rank"]
    assert rows[0]["url"] == "u1"
    assert rows[1]["title"] == "事件B"  # 热度降序
    # 渲染：Top 截断 + 标题里的竖线必须转义（否则表格列错位）
    md = render(
        [{"title": "带|竖线", "score": 1, "plats": ["抖音"], "first_rank": "", "url": ""},
         {"title": "第二个", "score": 0, "plats": [], "first_rank": "", "url": ""}],
        top=1, hours=24, now=datetime(2026, 9, 27, 6, 0))
    assert "| 第二个 |" not in md, "Top=1 时第二行不该出现"
    assert "丨" in md, "标题里的竖线要转义"
    assert "近 24 小时" in md
    # 数值解析容错
    assert _num("9505397") == 9505397 and _num(None) == 0 and _num("x") == 0
    print("SELFTEST PASS: 分组摊平 / 标题归一 / 跨平台合并 / 热度排序 / Top截断 / 表格转义")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="全网社交热点每日落盘（确定性）")
    ap.add_argument("--top", type=int, default=20, help="表格展示条数（默认 20）")
    ap.add_argument("--hours", type=int, default=24, help="回溯小时数（默认 24）")
    ap.add_argument("--out-dir", default="", help="覆盖输出目录（测试用）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不落盘")
    ap.add_argument("--selftest", action="store_true", help="离线自检，不联网")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    try:
        items = fetch(hours=args.hours)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "stage": "fetch", "message": str(exc)},
                         ensure_ascii=False))
        return 1

    rows = merge(items)
    md = render(rows, top=args.top, hours=args.hours)

    if args.dry_run:
        print(md)
        print(json.dumps({"status": "ok", "raw": len(items), "events": len(rows),
                          "dry_run": True}, ensure_ascii=False))
        return 0

    date = datetime.now().strftime("%Y-%m-%d")
    fp = write_digest(md, date, Path(args.out_dir) if args.out_dir else None)
    print(json.dumps({"status": "ok", "raw": len(items), "events": len(rows),
                      "top": min(args.top, len(rows)), "file": str(fp)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
