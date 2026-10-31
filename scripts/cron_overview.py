#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_overview.py — 定时任务总览与资源窗口规划（确定性，零 LLM）

产出：
    <vault>/系统中枢/运行手册/定时任务总览与资源窗口规划.md

为什么：旧版该文档手写，数字（79 条 / 启用 69 / 停用 10）与 jobs.json 脱节、且列了
已合并/删除的任务与时刻。本脚本从 jobs.json 实时再生成，使文档不可能再脱节。
与 cron_ledger.py（逐日台账）、scan_vault_structure.py（架构扫描）同一范式：
纯确定性、只读数据源、只写一份目标文档、不引入 LLM。

数据源（只读）：~/.hermes/cron/jobs.json（调度真相）
批任务成员结构：code-news/scripts/collect_material_batch.py 的 GROUPS（单一事实源）

用法：
    python cron_overview.py                  # 重写目标文档
    python cron_overview.py --dry-run        # 只打印正文，不写盘
    python cron_overview.py --jobs <path>    # 覆盖 jobs.json 路径（测试用）
    python cron_overview.py --out <path>     # 覆盖输出路径（测试用）
"""
from __future__ import annotations

import argparse
import importlib.util as _ilu
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent                 # code-news/scripts
HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")


def _load_module(name: str, path: Path):
    """按绝对路径加载模块（绕开 sys.path 里同名转发器的遮蔽）。"""
    spec = _ilu.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("无法加载 %s" % path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 批任务成员结构的单一事实源（code-news/scripts/collect_material_batch.py 的 GROUPS）。
# 注意：不能用 `import collect_material_batch` —— .hermes/scripts 下有同名转发器
# （无 __main__ 守卫，导入即转发执行真实批），会抢在 code-news 实现之前命中。
# 因此按路径显式加载 code-news 的实现。加载失败置空：成员数/成员脚本降级为「—」。
try:
    _cm = _load_module("collect_material_batch_impl", SCRIPT_DIR / "collect_material_batch.py")
    BATCH_GROUPS = dict(getattr(_cm, "GROUPS", {}))
except Exception:  # noqa: BLE001
    BATCH_GROUPS = {}

# vault 输出路径单一事实源（.hermes/scripts/vault_paths.py）
try:
    _vp = _load_module("vault_paths_impl", HERMES_SCRIPTS / "vault_paths.py")
    OUT_FILE = Path(_vp.SYSTEM_RUNBOOK) / "定时任务总览与资源窗口规划.md"
except Exception:  # noqa: BLE001
    OUT_FILE = Path(r"D:\Obsidian Vault\obsidian Vault\系统中枢\运行手册\定时任务总览与资源窗口规划.md")

JOBS = Path(r"C:\Users\Administrator\.hermes\cron\jobs.json")

# 批任务 job 的 script basename → collect_material_batch.py GROUPS 的 key。
# 成员数/成员脚本以 GROUPS 为准（job 名里的「（N 件/平台）」是历史命名，可能滞后）。
BATCH_SCRIPT_TO_GROUP = {
    "collect_material_batch.py": "material",
    "collect_favorites_batch.py": "favorites",
    "watchdog_batch.py": "watchdogs",
    "account_check_batch.py": "accounts",
    "knowledge_batch.py": "knowledge",
    "pipelines_batch.py": "pipelines",
    "logs_batch.py": "logs",
    "models_batch.py": "models",
    "skillsmcp_batch.py": "skillsmcp",
    "hotrank_batch.py": "hotrank",
    "cron_alert_batch.py": "cronalert",
    "xietong_batch.py": "xietong",
    "audit3d_batch.py": "audit3d",
    "moments_batch.py": "moments",
}

# 深夜窗口：23:00–05:59（含 23 点与 0 点）
DEEP_NIGHT_HOURS = {23, 0, 1, 2, 3, 4, 5}
DEEP_NIGHT_ORDER = [23, 0, 1, 2, 3, 4, 5]


def load_jobs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    return list(jobs.values()) if isinstance(jobs, dict) else list(jobs)


def sched(job: dict) -> str:
    s = job.get("schedule")
    if isinstance(s, dict):
        return str(s.get("expr") or s.get("display") or "")
    return str(s or "")


def cron_fields(expr: str):
    parts = str(expr).split()
    return parts if len(parts) == 5 else None


def single_hour(expr: str):
    """5 段 cron 且小时段是单一整数 → 返回该小时；否则 None。"""
    f = cron_fields(expr)
    if f is None:
        return None
    hour = f[1]
    return int(hour) if hour.isdigit() else None


def interval_minutes(expr: str):
    m = re.match(r"^every\s+(\d+)m$", str(expr).strip())
    return int(m.group(1)) if m else None


def hour_set(expr: str):
    """展开 5 段 cron 的小时段为小时集合；非 cron 返回 None。"""
    f = cron_fields(expr)
    if f is None:
        return None
    vals: set[int] = set()
    for part in f[1].split(","):
        if part == "*":
            return set(range(24))
        if "-" in part:
            lo, hi = part.split("-", 1)
            if lo.isdigit() and hi.isdigit():
                vals.update(range(int(lo), int(hi) + 1))
                continue
        if part.startswith("*/") and part[2:].isdigit():
            vals.update(range(0, 24, int(part[2:])))
            continue
        if part.isdigit():
            vals.add(int(part))
            continue
        return set(range(24))  # 未识别形态，保守按全天
    return vals


def job_name(job: dict) -> str:
    return str(job.get("name") or "")


def script_label(job: dict) -> str:
    s = job.get("script")
    if s:
        return str(s)
    return "（提示词型）" if job.get("no_agent") is False else "—"


def deliver_label(job: dict) -> str:
    d = str(job.get("deliver") or "")
    if d.startswith("feishu:"):
        return "飞书"
    if d == "local":
        return "本地"
    return d or "—"


def moment_label(job: dict) -> str:
    e = sched(job)
    im = interval_minutes(e)
    if im is not None:
        return "每 %d 分钟" % im
    return e


def _dom_key(dom: str) -> int:
    if dom == "*":
        return 0
    if dom.startswith("*/") and dom[2:].isdigit():
        return int(dom[2:])
    if dom.isdigit():
        return int(dom)
    return 99


def _dow_key(dow: str) -> int:
    if dow == "*":
        return 0
    if dow.isdigit():
        return int(dow)
    return 99


def detail_sort_key(job: dict):
    e = sched(job)
    f = cron_fields(e)
    if f and f[0].isdigit() and f[1].isdigit():
        return (0, int(f[1]), int(f[0]), _dom_key(f[2]), _dow_key(f[4]), job_name(job))
    im = interval_minutes(e)
    if im is not None:
        return (1, im, job_name(job))
    return (1, 10 ** 9, e, job_name(job))


def is_batch(job: dict) -> bool:
    return bool(job.get("no_agent")) and str(job.get("script") or "").endswith("_batch.py")


def batch_members(batch_script: str) -> tuple[int, str]:
    """返回 (成员数, 成员脚本串)。成员以 collect_material_batch.py GROUPS 为准。"""
    group = BATCH_SCRIPT_TO_GROUP.get(str(batch_script))
    if group is None or group not in BATCH_GROUPS:
        return 0, "—"
    entries = BATCH_GROUPS[group]
    scripts = "、".join(script for _name, script in entries)
    return len(entries), scripts


def build_document(jobs: list[dict]) -> str:
    total = len(jobs)
    enabled = [j for j in jobs if j.get("enabled")]
    disabled = [j for j in jobs if not j.get("enabled")]
    n_en = len(enabled)
    n_dis = len(disabled)
    batches = [j for j in jobs if is_batch(j)]
    batches_sorted = sorted(batches, key=detail_sort_key)

    L: list[str] = []
    a = L.append

    # —— ① 生成元信息 ——
    a("# 定时任务总览与资源窗口规划")
    a("")
    a("> ⚠️ 本文件由脚本自动生成，请勿手改：`~/.hermes/scripts/cron_overview_cron.py`"
      "（实现 `code-news/scripts/cron_overview.py`，确定性、零 LLM）。")
    a("> 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    a("> 数据来源：`~/.hermes/cron/jobs.json`（只读，Hermes 调度真相）")
    a("> 重跑命令：`python %s`" % (HERMES_SCRIPTS / "cron_overview_cron.py"))
    a("> 权威指针：逐日台账以 `cron_ledger.py` 生成的 "
      "`系统中枢/运行小结/系统与配置/Cron定时任务台账-<日期>.md` 为准；本文件只做常青总览。")
    a("")

    # —— ② 执行载体总览 ——
    a("## 一、执行载体总览（各智能体的调度配置现状）")
    a("")
    a("> 除 **Hermes** 行由 jobs.json 实时生成外，其余行来自 2026-10-06 全机调度调查"
      "（WK-20261006-03），属静态事实，不随本脚本自动刷新。")
    a("")
    a("| 执行载体 | 定时任务 | 说明 |")
    a("|---|---|---|")
    a("| **Hermes** | **%d 条（启用 %d / 停用 %d）** | 事实上的调度中枢（数据源 `~/.hermes/cron/jobs.json`） |"
      % (total, n_en, n_dis))
    a("| **Codex** | 1 条（heartbeat） | 素材入口产线验收 05:45 |")
    a("| **Claude Code** | 0 | 无 hooks、无 cron，只有 settings |")
    a("| **DSH（WSL）** | 0 | crontab 空；systemd 只有系统 timer |")
    a("| **piAgent** | 0 | 无定时任务 |")
    a("| **WorkBuddy** | 0 | 有 extension scheduler 但卡在 `SENTINEL(gate-all)`，每 5 秒刷诊断日志 |")
    a("| **OpenClaw** | 0 | `D:\\OpenClaw` 为素材/技能仓库，无调度 |")
    a("")
    a("> 全机调度配置只集中在 Hermes（jobs.json）与 Codex（automations）；"
      "Claude Code / DSH / piAgent / WorkBuddy / OpenClaw 均无调度配置。")
    a("")

    # —— ③ Hermes 规模与结构 ——
    a("## 二、Hermes 规模与结构")
    a("")
    a("| 指标 | 数量 |")
    a("|---|---|")
    a("| 任务总数 | %d |" % total)
    a("| 启用 | %d |" % n_en)
    a("| 停用 | %d |" % n_dis)
    a("")
    a("### 2.1 批任务一览（%d 个）" % len(batches_sorted))
    a("")
    a("> 成员数/成员脚本以执行器脚本 `collect_material_batch.py` 的 GROUPS 为准"
      "（单一事实源）；job 名里带的「（N 件/平台）」是历史命名，可能滞后。")
    a("")
    a("| 批任务 | 调度 | 执行器 | 成员数 | 成员脚本 |")
    a("|---|---|---|---|---|")
    for b in batches_sorted:
        cnt, members = batch_members(str(b.get("script") or ""))
        a("| %s | `%s` | %s | %d | %s |" % (
            job_name(b), sched(b), str(b.get("script") or ""), cnt, members))
    a("")

    # —— ④ 时段分布 ——
    hour_counts: dict[int, int] = {}
    rhythmic: list[dict] = []
    for j in enabled:
        h = single_hour(sched(j))
        if h is not None:
            hour_counts[h] = hour_counts.get(h, 0) + 1
        else:
            rhythmic.append(j)
    a("### 2.2 时段分布（启用项，按小时）")
    a("")
    a("| 时段 | 任务数 | 深夜窗口 |")
    a("|---|---|---|")
    for h in sorted(hour_counts):
        flag = "⚠️" if h in DEEP_NIGHT_HOURS else ""
        a("| %02d:00–%02d:59 | %d | %s |" % (h, h, hour_counts[h], flag))
    if rhythmic:
        a("| 节奏型 / 多时段 | %d | 见 2.3 |" % len(rhythmic))
    a("")

    # —— ⑤ 深夜窗口占用清单 ——
    single_dn: list[tuple[int, dict]] = []
    interval_dn: list[dict] = []
    multi_dn: list[dict] = []
    for j in enabled:
        e = sched(j)
        h = single_hour(e)
        if h is not None:
            if h in DEEP_NIGHT_HOURS:
                single_dn.append((h, j))
            continue
        if interval_minutes(e) is not None:
            interval_dn.append(j)
            continue
        hs = hour_set(e)
        if hs is not None and (hs & DEEP_NIGHT_HOURS):
            multi_dn.append(j)
    single_dn.sort(key=lambda t: DEEP_NIGHT_ORDER.index(t[0]))
    dn_total = len(single_dn) + len(interval_dn) + len(multi_dn)
    a("### 2.3 深夜窗口（23:00–05:59）占用清单")
    a("")
    a("> 本窗口是「深夜视频制作」想独占的资源窗口。下列任务会在 23:00–05:59 运行，视频制作前需按需让路。")
    a("> 当前共占用 **%d** 个任务（单小时 %d + 节奏型 %d + 多时段 %d）。"
      % (dn_total, len(single_dn), len(interval_dn), len(multi_dn)))
    a("")
    a("| 时刻 | 任务名 | 脚本 |")
    a("|---|---|---|")
    for _h, j in single_dn:
        a("| `%s` | %s | %s |" % (sched(j), job_name(j), script_label(j)))
    for j in interval_dn:
        a("| 每 %d 分钟（全天） | %s | %s |"
          % (interval_minutes(sched(j)), job_name(j), script_label(j)))
    for j in multi_dn:
        a("| `%s`（多时段，01–05 停跳） | %s | %s |"
          % (sched(j), job_name(j), script_label(j)))
    a("")

    # —— ⑥ 全量启用任务明细 ——
    a("### 2.4 全量启用任务明细（%d 条，按时刻排序）" % n_en)
    a("")
    a("| 时刻 | 任务名 | 脚本 | deliver |")
    a("|---|---|---|---|")
    for j in sorted(enabled, key=detail_sort_key):
        a("| `%s` | %s | %s | %s |" % (
            moment_label(j), job_name(j), script_label(j), deliver_label(j)))
    a("")
    a("> deliver 列：`本地` = local 落盘；`飞书` = feishu:* 推送（具体群 id 见 jobs.json）。")
    a("")

    # —— 停用提示（不列全量，指针到台账） ——
    a("## 三、停用任务（%d 条，保留登记）" % n_dis)
    a("")
    a("> 停用任务共 %d 条，其中大部分是被合并进批任务的单脚本成员（改由批执行器统一调度），"
      "少数是刻意停用。全量清单（含 ID / 状态 / 最近输出）以 cron_ledger.py 生成的逐日台账为准。"
      % n_dis)
    a("")

    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="cron_overview.py",
        description="定时任务总览与资源窗口规划（确定性、零 LLM，从 jobs.json 再生成）")
    ap.add_argument("--dry-run", action="store_true", help="只打印正文，不写盘")
    ap.add_argument("--jobs", default=None, help="jobs.json 路径覆盖（默认 ~/.hermes/cron/jobs.json）")
    ap.add_argument("--out", default=None, help="输出路径覆盖（默认 vault 运行手册目标文档）")
    ns = ap.parse_args(argv)

    jobs_path = Path(ns.jobs) if ns.jobs else JOBS
    out_path = Path(ns.out) if ns.out else OUT_FILE

    if not jobs_path.is_file():
        print("错误：读不到 jobs.json：%s" % jobs_path, file=sys.stderr)
        return 1

    try:
        jobs = load_jobs(jobs_path)
    except Exception as exc:  # noqa: BLE001
        print("错误：解析 jobs.json 失败：%s" % exc, file=sys.stderr)
        return 1

    doc = build_document(jobs)

    if ns.dry_run:
        print(doc)
        return 0

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(doc)
    except Exception as exc:  # noqa: BLE001
        print("错误：写目标文档失败：%s" % exc, file=sys.stderr)
        return 1

    print("已写：%s（总数 %d / 启用 %d / 停用 %d）"
          % (out_path, len(jobs), sum(1 for j in jobs if j.get("enabled")),
             sum(1 for j in jobs if not j.get("enabled"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
