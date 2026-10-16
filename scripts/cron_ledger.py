#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_ledger.py — 定时任务台账（确定性，零 LLM）

产出：
    <vault>/系统中枢/运行小结/系统与配置/Cron定时任务台账-<日期>.md

为什么要它（对应 RedFox「订阅中心」思路，见 2026-09-27 研读报告 Phase 3-3）：
    任务散在 .hermes/cron/jobs.json（数量随时间变化，见文件自身），没人一眼看得全：哪些在跑、跑成没有、
    连续失败几次、有没有「在跑但没在 tool_registry 登记」。本脚本把三份来源并成一张表：
      jobs.json（调度真相）+ tool_registry.json（能力登记）+ cron/output（最近一次输出）

与既有资产的关系：
    `系统中枢/经验沉淀/复盘/Cron定时任务路径审计表-2026-09-06.md` 是**时点快照**（46 任务，
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
BY_DESIGN_REGISTRY = Path(__file__).resolve().parent.parent / "config" / "cron_by_design_nonzero.json"

HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

try:
    from vault_paths import SYSTEM_SUMMARY as _SUMM
    OUT_DIR = _SUMM / "系统与配置"
except Exception:  # noqa: BLE001
    OUT_DIR = Path(r"D:\Obsidian Vault\obsidian Vault\系统中枢\运行小结\系统与配置")


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


def _parse_output_timestamp(name: str) -> str | None:
    """从 cron 输出文件名提取「这次失败发生的时间」（形如 2026-10-16_00-55-21.md）。

    文件名约定 `<日期>_<时间>.md`，返回 `YYYY-MM-DD HH:MM:SS`；不匹配返回 None。
    """
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})", name)
    if not m:
        return None
    return "%s %s" % (m.group(1), m.group(2).replace("-", ":"))


def output_timestamp(path: Path) -> str:
    """取一次 cron 输出发生的**真实时间**：优先文件名，退回文件 mtime。

    硬约束（WK-20261016-36）：严禁用 datetime.now() 或窗口小时数倒推冒充。
    """
    parsed = _parse_output_timestamp(path.name)
    if parsed:
        return parsed
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "（时间未知）"


# 失败标记：提示词型 job 的标题带 "(FAILED)"，脚本型 job 正文带 "**Status:** script failed"。
# 只扫文件头部即可判定（头部含标题与状态）。
FAIL_MARKERS = ("(FAILED)", "script failed")

def load_by_design_nonzero() -> dict[str, str]:
    """从声明式注册表读取「设计性非零退出」任务：{任务名: 原因}。

    这些任务**故意**用非零码报「发现了问题」，不算故障，不要每天报。
    2026-09-27 逐条核对输出确认过语义（见 RedFox 台账 9.3 的 C 类）。
    用注册表而不是硬编码：新增/改名这类任务不用改脚本，且逐条写清「为什么」。
    """
    try:
        data = json.loads(BY_DESIGN_REGISTRY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        print("警告：读取设计性非零退出注册表失败：%s" % BY_DESIGN_REGISTRY, file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[str(k)] = str(v.get("reason", "")).strip()
        else:
            out[str(k)] = str(v).strip()
    return out


# 设计性非零退出：这些任务**故意**用非零码报「发现了问题」，不算故障，不要每天报。
BY_DESIGN_NONZERO = load_by_design_nonzero()


def validate_by_design_registry() -> None:
    """校验注册表里的任务名是否都存在于 jobs.json；缺失则告警到 stderr（不阻断）。"""
    try:
        job_names = {str(j.get("name")) for j in load_jobs()}
    except Exception:  # noqa: BLE001
        return
    for name in sorted(set(BY_DESIGN_NONZERO) - job_names):
        print("警告：设计性非零退出注册表中的任务「%s」在 jobs.json 中不存在（可能已改名），"
              "请更新 config/cron_by_design_nonzero.json。" % name, file=sys.stderr)


_MEMBER_LINE_RE = re.compile(r"^\[\d+/\d+\]\s+(.+?)\s+\.\.\.\s+(OK|FAIL)\b")


def _batch_fail_members(text: str) -> list[str] | None:
    """解析批输出的 FAIL 成员名（成员行在最后一个单独成行的 `stdout:` 之后）。

    返回 FAIL 成员名列表；无任何 `[i/N] ... OK|FAIL` 成员行时返回 None，
    以区分「非批输出」与「批输出但无失败成员」两种 fail-open 语义。
    """
    lines = text.splitlines()
    stdout_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "stdout:":
            stdout_idx = i
    scope = lines[stdout_idx + 1:] if stdout_idx != -1 else lines
    fail_names: list[str] = []
    found_member_line = False
    for line in scope:
        m = _MEMBER_LINE_RE.match(line)
        if not m:
            continue
        found_member_line = True
        if m.group(2) == "FAIL":
            fail_names.append(m.group(1).strip())
    return fail_names if found_member_line else None


def _by_design_match(name: str) -> tuple[str, str] | None:
    """成员名命中 by-design 注册表时返回 (键, 原因)；否则 None。

    命中规则：∃键 k，k == name 或 k.startswith(name + "-")。
    前缀匹配用于容忍批成员短名（如「账号体检总览」）与注册表完整任务名
    （如「账号体检总览-每日」）的后缀差异。
    """
    prefix = name + "-"
    for k, reason in BY_DESIGN_NONZERO.items():
        if k == name or k.startswith(prefix):
            return (k, reason)
    return None


def _name_by_design(name: str) -> bool:
    """成员名是否命中 by-design 注册表（布尔版，同 `_by_design_match`）。"""
    return _by_design_match(name) is not None


def _failure_is_by_design_only(text: str) -> bool:
    """批输出里 FAIL 成员是否**全部**为设计性非零。

    无成员行 / 一个 FAIL 成员都没有 → False（fail-open，照常报告）。
    """
    fail_names = _batch_fail_members(text)
    if not fail_names:
        return False
    return all(_name_by_design(n) for n in fail_names)


def classify_failure(text: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """把一次 FAIL 输出文本拆成「新故障成员」与「已知项成员」。

    返回 (new_members, known_members)：
      - new_members：FAIL 成员里**未命中** by-design 的成员名（保持出现顺序）；
      - known_members：(成员名, 命中的注册表键, 原因) 列表。
    无任何 `[i/N] ... OK|FAIL` 成员行（脚本型任务整条失败）→ 两者均为空列表，
    由调用方按「整条属新故障」处理（有 FAIL 标记但无成员可归因）。
    """
    fail_names = _batch_fail_members(text)
    if not fail_names:
        return [], []
    new_members: list[str] = []
    known_members: list[tuple[str, str, str]] = []
    for name in fail_names:
        m = _by_design_match(name)
        if m is None:
            new_members.append(name)
        else:
            known_members.append((name, m[0], m[1]))
    return new_members, known_members


def recent_failures(
    hours: int,
) -> tuple[list[tuple[dict, list[str] | None, str]], list[tuple[dict, str, str, str]], list[tuple[dict, list[str]]]]:
    """近 N 小时内失败任务，按「新故障 / 已知项 / 已恢复」三分。

    返回 (new_failures, known_items, recovered)：
      - new_failures：窗口内**最后一次新故障**之后没有干净输出 → 计入 🔴 新故障（exit 1）；
        每项 (job, new_members, ts)，new_members=None 表示整条失败（脚本型、无成员行），
        否则为命中新故障的成员名列表；ts 为该次失败输出文件的真实时间（文件名/mtime）。
      - known_items：窗口内**最新一次失败输出**里命中 by-design 的 FAIL 成员 → 计入 ⚪ 已知项
        （exit 1）；每项 (job, 成员名, 命中的注册表键, 原因)。
      - recovered：窗口内最后一次新故障之后有干净输出 → 🟡 已恢复（不触发非零退出）；
        每项 (job, times)，times 为窗口内新故障输出文件名列表。
    已排除：停用任务（enabled 非真，F1）与「任务名整条命中清单」的设计性非零任务（F4）。
    """
    cutoff_ts = (datetime.now() - timedelta(hours=hours)).timestamp()
    new_failures: list[tuple[dict, list[str] | None, str]] = []
    known_items: list[tuple[dict, str, str, str]] = []
    recovered: list[tuple[dict, list[str]]] = []
    for job in load_jobs():
        if not job.get("enabled"):
            continue  # F1：只扫启用中的任务，停用任务的旧输出不再参与 --notify
        if str(job.get("name")) in BY_DESIGN_NONZERO:
            continue  # F4：任务名整条命中清单照旧排除（exit 语义见清单 reason）
        d = CRON_OUT / str(job.get("id") or "")
        if not d.is_dir():
            continue
        recent: list[Path] = []
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            try:
                if f.stat().st_mtime < cutoff_ts:
                    continue
            except OSError:
                continue
            recent.append(f)
        if not recent:
            continue
        # 逐文件分四类（按时间序）：clean / new / known / mixed（new+known）。
        # new＝带 FAIL 标记且含未命中成员（或整条失败、无成员行）；known＝带 FAIL 标记
        # 且含命中 by-design 的成员；clean＝无 FAIL 标记。
        # 最后一次 new 之后有 clean → 已恢复；否则计入 🔴。
        # known 取最新一次失败输出里的命中成员，逐条进 ⚪（带 reason）。
        new_files: list[str] = []
        new_latest: list[str] | None = None
        new_ts: str = "（时间未知）"
        covered = False
        known_latest: list[tuple[str, str, str]] = []
        for f in recent:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not any(m in text[:2000] for m in FAIL_MARKERS):
                if new_files:
                    covered = True
                known_latest = []
                continue
            new_members, known_members = classify_failure(text)
            known_latest = known_members
            if new_members:
                new_files.append(f.name[:16].replace("_", " "))
                new_latest = new_members
                new_ts = output_timestamp(f)
                covered = False
            elif not known_members:
                # 有 FAIL 标记但无任何成员行 → 整条失败，属新故障
                new_files.append(f.name[:16].replace("_", " "))
                new_latest = None
                new_ts = output_timestamp(f)
                covered = False
        if new_files:
            if covered:
                recovered.append((job, new_files))
            else:
                new_failures.append((job, new_latest, new_ts))
        for member, key, reason in known_latest:
            known_items.append((job, member, key, reason))
    return new_failures, known_items, recovered


def scan_history(job: dict, days: int) -> list[str]:
    """回看 cron/output 里近 N 天的输出，返回出现过失败的日期。

    为什么要它：jobs.json 的 last_status / failure_streak 只反映**最近一次**，
    任务一旦恢复就归零，于是几天前的事故会被抹掉。
    2026-09-27 实测教训：每日情报-1/2 在 09-25、09-26 因 Connection error 失败，
    看门狗当天就报了警；09-27 恢复后 streak 归零，只看 last_status 完全看不到，
    直到顺着内容线断链才挖出来（已写入 06-复用守则 第十节 第 5 条）。

    口径与 recent_failures 保持一致（WK-20261009-08）：
      - F1 停用任务跳过；
      - F4 设计性非零退出任务跳过；
      - 成员级传导：命中 FAIL_MARKERS 且 _failure_is_by_design_only(全文) 为真 → 该日不计入。
    """
    if not job.get("enabled"):
        return []  # F1：停用任务的旧输出不再计入历史失败
    if str(job.get("name")) in BY_DESIGN_NONZERO:
        return []  # F4：设计性非零退出任务照旧排除
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
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(m in text[:2000] for m in FAIL_MARKERS):
            if _failure_is_by_design_only(text):
                continue  # 批内失败成员全为设计性非零 → 该日不计入
            hits.append(date)
    return sorted(set(hits))


def build_ledger(date: str, days: int) -> dict:
    """构建台账正文与摘要数据（确定性、零打印、零落盘）。

    无参模式与 --notify 模式共用：--notify 用它静默刷新当日台账。
    返回 dict，含 doc（正文）与 jobs/ok/bad/disabled/unreg/hist_bad（供打印摘要）。
    """
    jobs = load_jobs()
    blob = load_registry_blob()

    history = {str(j.get("id")): scan_history(j, days) for j in jobs}
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
    ap_("| **近 %d 天内出现过失败**（含已恢复的） | **%d** |" % (days, len(hist_bad)))
    ap_("")
    if hist_bad:
        ap_("### 近 %d 天窗口内出现过失败的任务" % days)
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

    return {
        "doc": "\n".join(L),
        "jobs": jobs,
        "ok": ok,
        "bad": bad,
        "disabled": disabled,
        "unreg": unreg,
        "hist_bad": hist_bad,
    }


def write_ledger(doc: str, date: str) -> Path:
    """把台账正文写到当日文件（不打印；--notify 用它静默落盘）。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("Cron定时任务台账-%s.md" % date)
    out.write_text(doc, encoding="utf-8")
    return out


def render_notify_body(
    new_failures: list[tuple[dict, list[str] | None, str]],
    known_items: list[tuple[dict, str, str, str]],
    recovered: list[tuple[dict, list[str]]],
    hours: int,
) -> str:
    """把 --notify 的三栏数据渲染成给人看的日报正文（纯函数，离线可测）。"""
    L: list[str] = []
    ap_ = L.append
    ap_("⏰ 定时任务异常日报（近 %d 小时）" % hours)
    if new_failures:
        ap_("🔴 新故障（%d 个，需处理）：" % len(new_failures))
        for job, members, ts in new_failures:
            if members:
                ap_("- %s（新故障成员：%s）" % (job.get("name"), "、".join(members)))
            else:
                ap_("- %s（整条失败）" % job.get("name"))
            ap_("    失败时间：%s" % ts)
            err = first_error_line(job, 120)
            if err and err != "—":
                ap_("    最后一次：%s" % err)
    if known_items:
        ap_("⚪ 已知项（已登记，非故障）：")
        for job, member, key, reason in known_items:
            ap_("- %s · 成员「%s」命中「%s」：%s" % (job.get("name"), member, key, reason))
    if recovered:
        ap_("🟡 已恢复（%d 个，历史痕迹，可忽略）：" % len(recovered))
        for job, times in recovered:
            ap_("- %s ×%d（%s）"
                % (job.get("name"), len(times), "、".join(t.split(" ")[0] for t in times)))
    ap_("")
    ap_("处置建议：🔴 项先看「最后一次」报错与「失败时间」；🔴 的失败时间早于你最近一次修复 ⇒ 属回响，等该任务下一轮跑完即消失；⚪ 项已登记、非故障可忽略；🟡 项已自愈，无需处理。")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(prog="cron_ledger.py", description="定时任务台账")
    ap.add_argument("--dry-run", action="store_true", help="只打印摘要，不写 vault")
    ap.add_argument("--date", default=None, help="文件名日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--days", type=int, default=7, help="回看窗口天数（默认 7）")
    ap.add_argument("--notify", action="store_true",
                    help="异常日报模式：近 N 小时有未恢复失败则打印并 exit 1（供 cron 推飞书）；已恢复仅打印；无异常静默 exit 0")
    ap.add_argument("--hours", type=int, default=24, help="--notify 的窗口小时数（默认 24）")
    ns = ap.parse_args()

    validate_by_design_registry()

    # —— 异常日报模式：只输出给「人」看的一小段，供 Hermes cron 在失败时推飞书 ——
    # 「谁接到、做什么」的落地：报警集中到一条，且只在有**未恢复**失败时出声；
    # 已退役/已恢复的痕迹降级为 🟡 打印、不触发非零退出（避免天天重播历史）。
    if ns.notify:
        new_failures, known_items, recovered = recent_failures(ns.hours)
        # 静默刷新当日台账（默认今天、窗口 --days 默认 7 天）；不打印、不改 stdout/退出码语义。
        ledger_date = ns.date or datetime.now().strftime("%Y-%m-%d")
        write_ledger(build_ledger(ledger_date, ns.days)["doc"], ledger_date)
        if not new_failures and not known_items and not recovered:
            return 0                      # 静默：无异常不出声
        print(render_notify_body(new_failures, known_items, recovered, ns.hours))
        return 1 if (new_failures or known_items) else 0

    date = ns.date or datetime.now().strftime("%Y-%m-%d")
    ledger = build_ledger(date, ns.days)
    doc = ledger["doc"]
    jobs = ledger["jobs"]
    ok = ledger["ok"]
    bad = ledger["bad"]
    disabled = ledger["disabled"]
    unreg = ledger["unreg"]
    hist_bad = ledger["hist_bad"]

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

    out = write_ledger(doc, date)
    print("已写：%s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
