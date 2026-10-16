#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rank_daily.py — 平台榜单每日落盘（确定性，零 LLM）

产出：
    <vault>/内容生产/1-情报与选题/热点与情报/抖音/<日期>-榜单.md
    <vault>/内容生产/1-情报与选题/热点与情报/小红书/<日期>-榜单.md

数据源：RedFox 官方 skill，统一经 scripts/redfox_skill.py 执行
（强制 UTF-8、注入 REDFOX_API_KEY、积分不足映射退出码 3）。
**不重写端点逻辑**——skill 已逐枚验证，这里只做「调度 + 拼装 + 落盘」。

为什么 cron 排 20:00 而不是跟 04:xx 采集线走：
    抖音日榜 06:00 更新昨日、影响力榜 17:30、涨粉榜 18:00、小红书 19:00。
    凌晨 05 点抓只能拿到 T-2 的旧数据；20:00 抓最新，正好赶上次日 05:30 选题池。

与其他产线的关系（互补，不重复）：
    hotspot_daily.py        全网热搜事件（社交向）
    wechat_redfox_collect   公众号榜单（10W+/原创）
    本脚本                  抖音与小红书的作品榜 / 账号榜 / 涨粉榜

用法：
    python rank_daily.py --dry-run
    python rank_daily.py --limit 20
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
WRAPPER = REPO / "scripts" / "redfox_skill.py"

HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

try:
    from vault_paths import HOTSPOT as HOTSPOT_DIR
except Exception:  # noqa: BLE001
    HOTSPOT_DIR = Path(r"D:\Obsidian Vault\obsidian Vault\内容生产\1-情报与选题\热点与情报")

# 平台 → [(小节标题, skill, 参数)]
PLATFORMS: dict[str, list[tuple[str, str, list[str]]]] = {
    "抖音": [
        ("每日点赞榜", "douyin-daily-hot", ["--limit", "{n}"]),
        ("点赞飙升榜", "douyin-content-surge", ["--limit", "{n}"]),
        ("涨粉榜", "douyin-rise-ranking", ["--top_n", "{n}"]),
        ("影响力账号榜", "douyin-top-account", ["--period", "day", "--limit", "{n}"]),
    ],
    "小红书": [
        ("每日爆款笔记", "xiaohongshu-dailytop", ["--top_n", "{n}"]),
        ("七日爆款笔记", "xiaohongshu-weeklytop", ["--top_n", "{n}"]),
        ("账号榜", "xiaohongshu-top-account", ["--period", "day", "--limit", "{n}"]),
    ],
}

# skill 输出尾部的交互式提示（"是否查看剩余 47 条""是否订阅"）对落盘无意义，去掉。
DROP_PREFIXES = ("⚡", "📬", "1️⃣", "2️⃣", "3️⃣", "•")

# 部分 skill 会先打印一串过程日志再给数据，落盘时是噪音。
NOISE_PREFIXES = (
    "正在获取", "当前时间:", "提醒:", "推荐查询", "榜单类型:", "查询日期:",
    "分类:", "用户指定日期:", "根据关键词", "从缓存读取", "时间范围:", "更新日期:",
)


def clean(text: str) -> str:
    # skill 在 Windows 文本模式下会写出 \r\r\n；str.splitlines() 会把 \r 也当换行，
    # 于是每行之间多出一个空行，markdown 表格就会被拆散。先统一换行符。
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    keep: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if any(s.startswith(p) for p in DROP_PREFIXES):
            continue
        if any(s.startswith(p) for p in NOISE_PREFIXES):
            continue
        if re.fullmatch(r"-{3,}", s):
            continue
        if "本次榜单完整共" in s:
            continue
        keep.append(line.rstrip())
    body = unwrap_ranking_json("\n".join(keep))
    # 折叠连续空行
    out: list[str] = []
    for line in body.splitlines():
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    return "\n".join(out).strip()


def unwrap_ranking_json(text: str) -> str:
    """抖音涨粉榜把整段 JSON 打在一行里（ranking_table/analysis 是其中的 markdown 字段）。
    落盘时把那一行换成它内嵌的表格与分析，避免整页 JSON 噪音。"""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("{") and '"ranking_table"' in s):
            out.append(line)
            continue
        try:
            obj = json.loads(s)
        except Exception:  # noqa: BLE001
            out.append(line)
            continue
        meta = " · ".join(
            x for x in (
                str(obj.get("rank_label") or "").strip(),
                "日期 " + str(obj.get("rank_date") or "").strip(),
                "分类 " + str(obj.get("category") or "").strip(),
            ) if x and not x.endswith(" ")
        )
        if meta:
            out += ["_" + meta + "_", ""]
        desc = str(obj.get("data_description") or "").strip()
        if desc:
            out += [desc, ""]
        table = str(obj.get("ranking_table") or "").strip()
        if table:
            out += [table, ""]
        analysis = str(obj.get("analysis") or "").strip()
        if analysis:
            out += [analysis]
        out.append("")
    return "\n".join(out)


def run_skill(skill: str, args: list[str]) -> tuple[bool, str]:
    """经 wrapper 执行 skill。返回 (是否成功, 文本)。"""
    cmd = [sys.executable, str(WRAPPER), skill, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, cwd=str(REPO), timeout=300)
    except subprocess.TimeoutExpired:
        return False, "取数失败：执行超时（>300s）"
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if proc.returncode == 3:
        return False, "取数失败：红狐积分不足"
    if proc.returncode != 0:
        detail = (err.strip() or out.strip()).splitlines()[:3]
        return False, "取数失败（exit %d）：%s" % (proc.returncode, " / ".join(detail))
    body = clean(out)
    if not body:
        return False, "取数失败：无输出"
    return True, body


def build_platform_block(platform: str, limit: int) -> tuple[str, int, int]:
    """返回 (markdown 正文, 成功数, 失败数)。"""
    lines: list[str] = []
    ok = fail = 0
    for label, skill, tpl in PLATFORMS[platform]:
        args = [str(limit) if a == "{n}" else a for a in tpl]
        success, text = run_skill(skill, args)
        flag = "✅" if success else "⚠️"
        print("  %s %-14s %s" % (flag, label, skill), flush=True)
        lines.append("## %s" % label)
        lines.append("")
        lines.append(text)
        lines.append("")
        ok, fail = (ok + 1, fail) if success else (ok, fail + 1)
    return "\n".join(lines).strip() + "\n", ok, fail


def main() -> int:
    ap = argparse.ArgumentParser(prog="rank_daily.py", description="平台榜单每日落盘")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写 vault")
    ap.add_argument("--limit", type=int, default=20, help="每榜展示条数（默认 20）")
    ap.add_argument("--date", default=None, help="文件名日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--platform", default="all", choices=["all", *PLATFORMS.keys()],
                    help="只跑某个平台（调试用，省积分）")
    ns = ap.parse_args()

    date = ns.date or datetime.now().strftime("%Y-%m-%d")
    total_ok = total_fail = 0

    targets = list(PLATFORMS) if ns.platform == "all" else [ns.platform]
    for platform in targets:
        print("[%s] 取数中…" % platform, flush=True)
        body, ok, fail = build_platform_block(platform, ns.limit)
        total_ok += ok
        total_fail += fail
        header = (
            "---\ntags: [榜单, %s]\ndate: %s\n---\n\n"
            "# %s 平台榜单（%s）\n\n"
            "> 数据来源：RedFox 官方 skill（经 scripts/redfox_skill.py 执行）。\n"
            "> 口径：抖音日榜每日 06:00 更昨日、影响力榜 17:30、涨粉榜 18:00；小红书 19:00 后更新。\n\n"
            % (platform, date, platform, date)
        )
        doc = header + body
        if ns.dry_run:
            print("---- %s（dry-run，不写盘）----" % platform)
            print(doc[:1200])
            continue
        if ok == 0:
            # 该平台一个榜都没取到，写盘只会留下「只有表头的空壳」，下游会误当数据；不落盘并显式报原因。
            print("[%s] %d 个榜单全部取数失败，不落盘" % (platform, fail),
                  file=sys.stderr, flush=True)
            continue
        out_dir = HOTSPOT_DIR / platform
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("%s-榜单.md" % date)
        out_path.write_text(doc, encoding="utf-8")
        print("  已写：%s" % out_path, flush=True)

    print("完成：成功 %d 项，失败 %d 项" % (total_ok, total_fail), flush=True)
    # 全失败才报错（部分失败仍落盘，沿用 account_dashboard「一个坏了其余照常出数」的思路）
    return 1 if total_ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
