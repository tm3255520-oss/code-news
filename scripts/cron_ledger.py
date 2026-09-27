#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_ledger.py — 定时任务台账（确定性，零 LLM）

产出：
    <vault>/系统中枢/运行手册/Cron定时任务台账-<日期>.md

为什么要它（对应 RedFox「订阅中心」思路，见 2026-09-27 研读报告 Phase 3-3）：
    任务散在 .hermes/cron/jobs.json（60 条），没人一眼看得全：哪些在跑、跑成没有、
    连续失败几次、有没有「在跑但没在 tool_registry 登记」。本脚本把三份来源并成一张表：
      jobs.json（调度真相）+ tool_registry.json（能力登记）+ cron/output（最近一次输出）

与既有资产的关系：
    `系统中枢/运行手册/Cron定时任务路径审计表-2026-09-06.md` 是**时点快照**（46 任务，
    逐条人工审计路径）。本脚本不替代它，而是产出**可重复生成**的当前台账（自动跟随）。

用法：
    python cron_ledger.py --dry-run
    python cron_ledger.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

JOBS = Path(r"C:\Users\Administrator\.hermes\cron\jobs.json")
CRON_OUT = Path(r"C:\Users\Administrator\.hermes\cron\output")
REGISTRY = Path(__file__).resolve().parent.parent / "config" / "tool_registry.json"

HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

try:
    from vault_paths import SYSTEM_RUNBOOK as OUT_DIR
except Exception:  # noqa: BLE001
    OUT_DIR = Path(r"D:\Obsidian Vault\obsidian Vault\系统中枢\运行手册")


def load_jobs() -> list[dict]:
    data = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    return list(jobs.values()) if isinstance(jobs, dict) else list(jobs)


def load_registry_blob() -> str:
    try:
        return json.dumps(json.loads(REGISTRY.read_text(encoding="utf-8")).get("interfaces") or {},
                          ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return ""


def entry_of(job: dict) -> str:
    s = job.get("script")
    if not s:
        return "（提示词型 job）" if not job.get("no_agent") else "（无脚本）"
    return re.split(r"[\\/]", str(s).strip())[-1]


def registered(job: dict, blob: str) -> str:
    s = job.get("script")
    if not s:
        return "—"
    base = re.split(r"[\\/]", str(s).strip())[-1]
    name = base[:-3] if base.endswith(".py") else base
    return "是" if (name and name in blob) else "**否**"


def last_output(job: dict) -> str:
    d = CRON_OUT / str(job.get("id") or "")
    if not d.is_dir():
        return "—"
    fs = sorted(p.name for p in d.iterdir() if p.is_file())
    return fs[-1] if fs else "—"


def first_error_line(job: dict, limit: int = 110) -> str:
    raw = str(job.get("last_error") or "").strip().replace("\n", " ")
    raw = re.sub(r"\s+", " ", raw)
    return raw[:limit] if raw else "—"


# 失败标记：提示词型 job 的标题带 "(FAILED)"，脚本型 job 正文带 "**Status:** script failed"。
# 只扫文件头部即可判定（头部含标题与状态）。
FAIL_MARKERS = ("(FAILED)", "script failed")


def scan_history(job: dict, days: int) -> list[str]:
    """回看 cron/output 里近 N 天的输出，返回出现过失败的日期。

    为什么要它：jobs.json 的 last_status / failure_streak 只反映**最近一次**，
    任务一旦恢复就归零，于是几天前的事故会被抹掉。
    2026-09-27 实测教训：每日情报-1/2 在 09-25、09-26 因 Connection error 失败，
    看门狗当天就报了警；09-27 恢复后 streak 归零，只看 last_status 完全看不到，
    直到顺着内容线断链才挖出来（已写入 06-复用守则 第十节 第 5 条）。
    """
    d = CRON_OUT / str(job.get("id") or "")
    if not d.is_dir():
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    hits: list[str] = []
    for f in sorted(d.iterdir()):
        if not f.is_file():
            continue
        date = f.name[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date) or date < cutoff:
            continue
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if any(m in head for m in FAIL_MARKERS):
            hits.append(date)
    return sorted(set(hits))


def main() -> int:
    ap = argparse.ArgumentParser(prog="cron_ledger.py", description="定时任务台账")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写 vault")
    ap.add_argument("--date", default=None, help="文件名日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--days", type=int, default=7, help="回看窗口天数（默认 7）")
    ns = ap.parse_args()

    jobs = load_jobs()
    blob = load_registry_blob()
    date = ns.date or datetime.now().strftime("%Y-%m-%d")

    history = {str(j.get("id")): scan_history(j, ns.days) for j in jobs}
    hist_bad = [(j, history[str(j.get("id"))]) for j in jobs if history[str(j.get("id"))]]
    hist_bad.sort(key=lambda t: (-len(t[1]), str(t[0].get("name"))))

    def sched(j: dict) -> str:
        s = j.get("schedule")
        if isinstance(s, dict):
            return str(s.get("expr") or s.get("display") or "")
        return str(s or "")

    ok = [j for j in jobs if j.get("last_status") == "ok"]
    bad = [j for j in jobs if j.get("last_status") not in (None, "ok")]
    bad.sort(key=lambda j: -(j.get("failure_streak") or 0))
    unreg = [j for j in jobs if registered(j, blob) == "**否**"]
    disabled = [j for j in jobs if not j.get("enabled")]

    L: list[str] = []
    ap_ = L.append
    ap_("# Cron 定时任务台账（%s）" % date)
    ap_("")
    ap_("> 自动生成：`code-news/scripts/cron_ledger.py`（确定性零 LLM，可重复生成）")
    ap_("> 数据源：`.hermes/cron/jobs.json`（调度真相）+ `code-news/config/tool_registry.json`（能力登记）+ `.hermes/cron/output/`（最近输出）")
    ap_("")
    ap_("## 一、概览")
    ap_("")
    ap_("| 指标 | 数量 |")
    ap_("| --- | --- |")
    ap_("| 任务总数 | %d |" % len(jobs))
    ap_("| 最近一次成功（last_status=ok） | %d |" % len(ok))
    ap_("| 最近一次非 ok | **%d** |" % len(bad))
    ap_("| 已停用（enabled=false） | %d |" % len(disabled))
    ap_("| 有脚本但未在 tool_registry 登记 | %d |" % len(unreg))
    ap_("| **近 %d 天内出现过失败**（含已恢复的） | **%d** |" % (ns.days, len(hist_bad)))
    ap_("")
    if hist_bad:
        ap_("### 近 %d 天窗口内出现过失败的任务" % ns.days)
        ap_("")
        ap_("> 这一节**不受 last_status 影响**——任务恢复后 streak 会归零，但历史输出不会。排序按窗口内失败条数。")
        ap_("> 2026-09-25/26 的每日情报-1/2 就是只有在这里才看得见的例子。")
        ap_("")
        ap_("| 失败条数 | 任务 | 调度 | 失败日期 |")
        ap_("| ---: | --- | --- | --- |")
        for j, dates in hist_bad:
            ap_("| %d | %s | `%s` | %s |" % (len(dates), j.get("name"), sched(j), ", ".join(dates)))
        ap_("")
    if bad:
        ap_("## 二、需要关注（最近一次非 ok，按连续失败次数降序）")
        ap_("")
        ap_("> 注意：看门狗/保护类任务**故意**用非零退出码报「发现了问题」（如 cron 巡检、发布台账巡检、数据铁律跳过），")
        ap_("> 它们出现在这里不代表自身坏了。判断时看最后一列的真实报错。")
        ap_("")
        ap_("| 连续失败 | 任务 | 调度 | 最近运行 | 退出/报错摘要 |")
        ap_("| ---: | --- | --- | --- | --- |")
        for j in bad:
            ap_("| %s | %s | `%s` | %s | %s |" % (
                j.get("failure_streak") or 0, j.get("name"), sched(j),
                str(j.get("last_run_at") or "")[:16].replace("T", " "),
                first_error_line(j).replace("|", "/")))
        ap_("")
    ap_("## 三、全量清单（按调度时刻排序）")
    ap_("")
    ap_("| ID | 任务 | 调度 | 类型 | 入口 | 状态 | 登记 | 最近输出 |")
    ap_("| --- | --- | --- | --- | --- | --- | --- | --- |")

    def sort_key(j: dict):
        e = sched(j)
        m = re.match(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$", e)
        if not m:
            return (99, 99, 99)
        mi, ho, dom = m.group(1), m.group(2), m.group(3)
        if not mi.isdigit():
            return (98, 98, 98)
        return (int(ho) if ho.isdigit() else 99, int(mi), int(dom) if dom.isdigit() else 99)

    for j in sorted(jobs, key=sort_key):
        kind = "脚本" if j.get("script") else ("提示词" if not j.get("no_agent") else "无脚本")
        state = "启用" if j.get("enabled") else "**停用**"
        ap_("| `%s` | %s | `%s` | %s | %s | %s | %s | %s |" % (
            str(j.get("id"))[:12], j.get("name"), sched(j), kind,
            entry_of(j), state, registered(j, blob), last_output(j)))
    ap_("")
    if unreg:
        ap_("## 四、在跑但未在 tool_registry 登记")
        ap_("")
        for j in unreg:
            ap_("- %s（`%s`，调度 `%s`）" % (j.get("name"), entry_of(j), sched(j)))
        ap_("")
        ap_("> 说明：registry 收录标准是「可被 Agent 路由的**能力**」，基础设施/运维任务不登记是有意为之（见 registry 顶层 scope 字段）。")
        ap_("")

    doc = "\n".join(L)
    print("概览：总数 %d ｜ ok %d ｜ 非 ok %d ｜ 停用 %d ｜ 未登记 %d"
          % (len(jobs), len(ok), len(bad), len(disabled), len(unreg)))
    print("近 %d 天出现过失败：%d 个任务" % (ns.days, len(hist_bad)))
    for j, dates in hist_bad:
        print("  ↺ %-24s %d 次 %s" % (j.get("name"), len(dates), ",".join(d[-5:] for d in dates)))
    for j in bad:
        print("  ⚠️ streak=%-3s %-24s %s" % (j.get("failure_streak") or 0, j.get("name"),
                                              first_error_line(j, 70)))
    if ns.dry_run:
        print("\n---- dry-run，不写盘。正文预览 ----")
        print(doc[:1500])
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("Cron定时任务台账-%s.md" % date)
    out.write_text(doc, encoding="utf-8")
    print("已写：%s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
