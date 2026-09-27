#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redfox_skill.py — RedFox 官方 skill 的统一执行入口（wrapper）

为什么需要它（2026-09-27 Phase 1 实测教训）：
1. 官方 skill 脚本直接 print emoji，却没有 sys.stdout.reconfigure(encoding="utf-8")。
   Windows GBK 控制台下抛 UnicodeEncodeError —— 而且是在**已经调用完 API 之后**才崩，
   结果是「积分扣了、数据没拿到」。本脚本给子进程强制 UTF-8。
2. 官方 skill 只认环境变量 REDFOX_API_KEY，不读 .hermes/.env；
   本脚本统一注入（复用 redfox_client.load_key，不重复实现 .env 解析）。
3. 积分耗尽是高频故障，报错混在正文里不易识别；本脚本统一识别并映射退出码 3。

用法:
    python redfox_skill.py --list
    python redfox_skill.py --print-cmd douyin-daily-hot --limit 3
    python redfox_skill.py douyin-daily-hot --limit 3
    python redfox_skill.py douyin-account-diagnosis geng970616
    python redfox_skill.py xiaohongshu-weeklytop --category 时尚穿搭 --top_n 20

退出码:
    0 成功 ｜ 2 skill 或入口脚本不存在 ｜ 3 积分不足 ｜ 4 缺 API Key
    其它 = 子进程原始退出码
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SKILLS_ROOT = Path(r"C:\Users\Administrator\.codex\skills")
HERMES_ENV = Path(r"C:\Users\Administrator\.hermes\.env")
HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")

# skill → 入口脚本（相对 skill 目录）。
# 为什么要显式映射：多数 skill 目录里同时有 fetch / generate / helper 多个 .py，
# 自动挑「第一个」会挑错（例如 douyin-top-account 的 fetch_rank.py vs generate_report.py）。
# 新增 skill 时在此登记；未登记但目录存在时会提示，不会静默乱猜。
ENTRY: dict[str, str] = {
    # —— Phase 1 安装的 10 枚 ——
    "douyin-daily-hot": "scripts/douyin_daily_hot.py",
    "douyin-content-surge": "scripts/douyin_daily_increment.py",
    "douyin-rise-ranking": "scripts/gzh_growth_fetcher.py",
    "douyin-top-account": "scripts/fetch_rank.py",
    "douyin-account-diagnosis": "scripts/douyin_diagnosis.py",
    "douyin-similar-account": "scripts/douyin_similar_account.py",
    "xiaohongshu-dailytop": "scripts/xhs_daily_fetcher.py",
    "xiaohongshu-weeklytop": "scripts/xhs_weekly_fetcher.py",
    "xiaohongshu-top-account": "scripts/fetch_rank.py",
    "xiaohongshu-similar-account": "scripts/xiaohongshu_account_recommender.py",
    # —— 既有 5 枚（与 redfox-community 官方版一致）——
    "xiaohongshu-search": "scripts/fetch_xhs_hot_articles.py",
    "xiaohongshu-lowtop": "scripts/fetch_explosive_articles.py",
    "xiaohongshu-account-analyzer": "scripts/xiaohongshu_analyzer.py",
    "multi-wordcheck": "scripts/check_sensitive_words.py",
    "trending-hub-top10": "scripts/fetch_hotspot.py",
}

CREDIT_MARKERS = ("积分余额不足", "剩余积分", "code=3201", "\"code\": 3201", "\"code\":3201")


def _redfox_key() -> str:
    """复用 redfox_client 的 .env 解析，避免两处实现漂移。"""
    key = os.environ.get("REDFOX_API_KEY")
    if key:
        return key.strip()
    if HERMES_SCRIPTS.exists():
        sys.path.insert(0, str(HERMES_SCRIPTS))
        try:
            from redfox_client import load_key  # type: ignore
            return str(load_key()).strip()
        except SystemExit:
            return ""
        except Exception:
            return ""
    return ""


def _child_env(key: str) -> dict[str, str]:
    env = dict(os.environ)
    # 强制 UTF-8：官方 skill 会 print emoji，GBK 控制台下会崩溃且发生在 API 调用之后
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if key:
        env["REDFOX_API_KEY"] = key
    return env


def _resolve(skill: str, override: str | None) -> Path | None:
    rel = override or ENTRY.get(skill)
    if not rel:
        return None
    path = SKILLS_ROOT / skill / rel
    return path if path.is_file() else None


def cmd_list() -> int:
    print("已登记入口的 skill（%d）：" % len(ENTRY))
    for skill in sorted(ENTRY):
        path = SKILLS_ROOT / skill / ENTRY[skill]
        mark = "OK " if path.is_file() else "缺失"
        print("  [%s] %-30s %s" % (mark, skill, ENTRY[skill]))
    # 只提示「像 RedFox skill」的未登记项：判定依据是 SKILL.md 里出现 REDFOX_API_KEY / 红狐。
    # 不这样做会把 hyperframes、content-research-writer 等全部非 RedFox 技能也列出来，纯噪音。
    unregistered = []
    for p in sorted(SKILLS_ROOT.iterdir()) if SKILLS_ROOT.exists() else []:
        if not p.is_dir() or p.name.startswith(".") or p.name in ENTRY:
            continue
        skill_md = p / "SKILL.md"
        try:
            head = skill_md.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        if "REDFOX_API_KEY" in head or "redfox.hk" in head:
            unregistered.append(p.name)
    if unregistered:
        print("\n目录存在、且看着是 RedFox skill、但未登记入口（如需调用请补 ENTRY）：")
        for n in unregistered:
            print("  - %s" % n)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="redfox_skill.py", add_help=True,
        description="RedFox 官方 skill 统一执行入口（强制 UTF-8 + 注入 API Key + 识别积分不足）")
    ap.add_argument("--list", action="store_true", help="列出已登记的 skill 与入口脚本")
    ap.add_argument("--print-cmd", action="store_true", help="只打印将要执行的命令，不执行")
    ap.add_argument("--script", default=None, help="覆盖入口脚本（相对 skill 目录）")
    ap.add_argument("--timeout", type=int, default=600, help="超时秒数（默认 600）")
    ap.add_argument("skill", nargs="?", help="skill 目录名，如 douyin-daily-hot")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="透传给 skill 脚本的参数")

    if len(sys.argv) == 1 or (len(sys.argv) >= 2 and sys.argv[1] == "--list"):
        return cmd_list()
    ns = ap.parse_args()
    if ns.list:
        return cmd_list()
    if not ns.skill:
        ap.print_help()
        return 2

    script = _resolve(ns.skill, ns.script)
    if script is None:
        known = ", ".join(sorted(ENTRY))
        print("找不到 skill 或入口脚本：%s" % ns.skill, file=sys.stderr)
        if ns.skill in ENTRY:
            print("  期望路径：%s" % (SKILLS_ROOT / ns.skill / ENTRY[ns.skill]), file=sys.stderr)
        else:
            print("  已登记：%s" % known, file=sys.stderr)
        return 2

    key = _redfox_key()
    cmd = [sys.executable, str(script), *ns.args]
    if ns.print_cmd:
        print(" ".join(cmd))
        print("(REDFOX_API_KEY %s；PYTHONUTF8=1)" % ("已注入" if key else "未取到"), file=sys.stderr)
        return 0
    if not key:
        print("[wrapper] 未取到 REDFOX_API_KEY（应在 %s），继续执行但接口大概率会失败。" % HERMES_ENV,
              file=sys.stderr)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=ns.timeout,
                              env=_child_env(key))
    except subprocess.TimeoutExpired:
        print("[wrapper] 执行超时（>%ds）：%s" % (ns.timeout, ns.skill), file=sys.stderr)
        return 124
    except FileNotFoundError as exc:
        print("[wrapper] 解释器或脚本不存在：%s" % exc, file=sys.stderr)
        return 2

    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)

    combined = out + err
    if any(m in combined for m in CREDIT_MARKERS):
        print("[wrapper] 判定为红狐积分不足（exit 3）。请充值后重试。", file=sys.stderr)
        return 3
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
