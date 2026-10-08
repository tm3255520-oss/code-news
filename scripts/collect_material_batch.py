#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_material_batch.py — 采集批执行器（素材主动采集 6→1 / 收藏采集 3→1 / 情报写入看门狗 3→1 / 账号体检 4→1 / 知识加工 3→1 / 内容产线 4→1 / 日志维护 2→1 / 模型与供应商周检 3→1 / Skills/MCP 清单 2→1 / 热点与榜单 2→1 / cron 自监控 2→1 / 协同留痕 3→1 / 3 天审计 2→1 / 朋友圈素材后置 3→1）

把互相独立的采集脚本按分组合成一条命令顺序执行：每条独立子进程、逐条记录 exit code
与耗时，任一失败不中断整批，最后汇总并以「整体是否全成功」决定退出码。

分组（--group，默认 material）：
  - material（默认）：素材主动采集 6 条（头条 / 公众号 / 抖音 / 知乎 / B站 / 小红书）
  - favorites：收藏采集 3 条（今日头条 / 知乎 / 小红书）
  - watchdogs：情报写入看门狗 3 条（每日情报-1/2/3 写入看门狗）
  - accounts：账号体检 4 条（视频号作品数据采集 / 公众号账号体检 / 公众号数据面采集 / 账号体检总览）
  - knowledge：知识加工 3 条（知识库加工整理 / 视频素材加工 / raw文章体例归一，归一必须最后）
  - pipelines：内容产线 4 条（公众号 / 头条 / 知乎 / 小红书；公众号深度文终稿被后 3 条复用，公众号必须第一、顺序不得重排）
  - logs：日志维护 2 条（Log Index → Log Watchdog）
  - models：模型与供应商周检 3 条（供应商模型巡检 → 模型健康巡检 → 每周更新 Hermes 模型配置汇总）
  - skillsmcp：Skills/MCP 本地清单 2 条（Skills-MCP 清单每日刷新 → 技能与MCP资产盘点）
  - hotrank：热点与榜单落盘 2 条（平台榜单-每日落盘 → 全网社交热点-每日落盘）
  - cronalert：cron 自监控 2 条（cron 健康巡检看门狗 → 定时任务异常日报）
  - xietong：协同留痕 3 条（协同三件套巡检 → HANDOFF 运行小结自动分发 → 定时任务总览再生成）
  - audit3d：3 天审计 2 条（work-audit-3d → 工作卡片关联扫描）
  - moments：朋友圈素材后置 3 条（公众号文章朋友圈文案推送 → 贴图每日生产流水线 → 贴图朋友圈打包推送）

契约（阶段3）：
  - 顺序固定，每条独立子进程执行（视频号发现 shipinhao_redfox_collect.py 已停用，不纳入）；
  - 失败隔离：任一条非零，继续跑下一条，不 set -e 式中断；
  - 子进程超时兜底：每条设 timeout（默认 900 秒，--timeout 覆盖），超时记 FAIL(timeout) 不中断整批；
  - 输出：每条一行 `[i/N] <任务名> ... OK/FAIL(exit=N) <秒>s`，末尾 `summary: 成功 X / 失败 Y`；
  - 退出码：失败数 Y==0 → 0，否则 1。

用法：
  python collect_material_batch.py                     # 默认 material 组，顺序跑 6 条
  python collect_material_batch.py --group favorites   # favorites 组，顺序跑 3 条
  python collect_material_batch.py --group watchdogs   # watchdogs 组，顺序跑 3 条
  python collect_material_batch.py --group accounts    # accounts 组，顺序跑 4 条（总览必须最后）
  python collect_material_batch.py --group knowledge   # knowledge 组，顺序跑 3 条（归一必须最后）
  python collect_material_batch.py --group pipelines   # pipelines 组，顺序跑 4 条（公众号必须第一）
  python collect_material_batch.py --group logs        # logs 组，顺序跑 2 条（索引 → 看门狗）
  python collect_material_batch.py --group models      # models 组，顺序跑 3 条（供应商巡检 → 模型健康巡检 → 配置汇总）
  python collect_material_batch.py --group skillsmcp   # skillsmcp 组，顺序跑 2 条（清单刷新 → 资产盘点）
  python collect_material_batch.py --group hotrank     # hotrank 组，顺序跑 2 条（榜单 → 热点）
  python collect_material_batch.py --group cronalert   # cronalert 组，顺序跑 2 条（看门狗 → 异常日报）
  python collect_material_batch.py --group xietong     # xietong 组，顺序跑 3 条（协同巡检 → HANDOFF 分发 → 总览再生成）
  python collect_material_batch.py --group audit3d     # audit3d 组，顺序跑 2 条（work-audit → 卡片关联扫描）
  python collect_material_batch.py --group moments     # moments 组，顺序跑 3 条（公众号朋友圈文案 → 贴图生产 → 贴图朋友圈打包）
  python collect_material_batch.py --dry-run           # 只打印命令，不实际执行
  python collect_material_batch.py --only <子串>        # 只跑名字/脚本名含子串的条目（便于测试失败隔离）
  python collect_material_batch.py --group cronalert --quiet-ok  # 全部成功静默；任一失败才打印全部条目
  python collect_material_batch.py --group models --pass-stdout  # 成员成功时也透传 stdout 正文（内容型周报）
  python collect_material_batch.py --group pipelines --fail-tail-lines 3  # 失败成员打印其 stdout 末尾 3 行（默认 15）
"""

import argparse
import os
import subprocess
import sys
import time

# 采集脚本落点（Hermes cron 的 script 解析只认 HERMES_HOME/scripts/ 之下）
HERMES_SCRIPTS_DIR = r"C:\Users\Administrator\.hermes\scripts"

# 素材主动采集（顺序固定 1→6，与 cron 任务表一致；视频号发现已停用不纳入）
MATERIAL_ENTRIES = [
    ("素材主动采集-头条", "toutiao_keyword_collect.py"),
    ("素材主动采集-公众号", "wechat_redfox_collect.py"),
    ("素材主动采集-抖音", "douyin_redfox_collect.py"),
    ("素材主动采集-知乎", "zhihu_keyword_collect.py"),
    ("素材主动采集-B站", "bilibili_redfox_collect.py"),
    ("素材主动采集-小红书", "xiaohongshu_redfox_collect.py"),
]

# 收藏采集（顺序固定 1→3，与 cron 任务表一致；均接入 login_gate）
FAVORITES_ENTRIES = [
    ("今日头条收藏采集", "toutiao_collect.py"),
    ("知乎收藏采集", "zhihu_collect.py"),
    ("小红书收藏采集", "xhs_collect.py"),
]

# 情报写入看门狗（顺序固定 1→3，与 cron 任务表一致；no_agent 脚本，无参数）
WATCHDOG_ENTRIES = [
    ("每日情报-1-写入看门狗", "task1_report_writer.py"),
    ("每日情报-2-写入看门狗", "task2_report_writer.py"),
    ("每日情报-3-写入看门狗", "task3_report_writer.py"),
]

# 账号体检（顺序固定 1→4，与 cron 任务表一致；账号体检总览汇总前 3 个采集源，必须最后）
ACCOUNTS_ENTRIES = [
    ("视频号作品数据采集", "channels_metrics_collector.py"),
    ("公众号账号体检", "mp_account_check.py"),
    ("公众号数据面采集", "mp_data_collector.py"),
    ("账号体检总览", "account_dashboard.py"),
]

# 知识加工（顺序固定 1→3，与 cron 任务表一致；文章加工 → 视频加工 → raw 归一，归一必须最后）
KNOWLEDGE_ENTRIES = [
    ("知识库加工整理-每日增量", "wiki_ingest_cron.py"),
    ("视频素材加工-每日增量", "wiki_ingest_videos_cron.py"),
    ("raw文章体例归一-每日", "raw_normalize_articles.py"),
]

# 内容产线（顺序固定 1→4，与 cron 任务表一致；公众号深度文终稿被后 3 条复用，公众号必须第一、顺序不得重排）
PIPELINES_ENTRIES = [
    ("公众号内容生产流水线", "content_production_pipeline.py"),
    ("头条内容生产流水线", "toutiao_pipeline.py"),
    ("知乎内容生产流水线", "zhihu_pipeline.py"),
    ("小红书内容生产流水线", "xhs_pipeline.py"),
]

# 日志维护（顺序固定 1→2，与 cron 任务表一致；索引先生成、看门狗后扫描，顺序不得重排）
LOGS_ENTRIES = [
    ("日志索引生成", "log_index.py"),
    ("日志看门狗", "log_watchdog.py"),
]

# 模型与供应商周检（顺序固定 1→3，与 cron 任务表一致；供应商巡检 → 模型健康巡检 → 配置汇总）
MODELS_ENTRIES = [
    ("供应商模型巡检", "nvidia_model_audit_weekly.py"),
    ("模型健康巡检", "model_health_check.py"),
    ("每周更新 Hermes 模型配置汇总", "update_model_config_doc.py"),
]

# Skills/MCP 本地清单（顺序固定 1→2，与 cron 任务表一致；同输入 ~/.hermes/skills/ + config.yaml，仅落点不同）
SKILLSMCP_ENTRIES = [
    ("Skills-MCP 清单每日刷新", "generate_skills_mcp_inventory.py"),
    ("技能与MCP资产盘点", "skills_mcp_inventory.py"),
]

# 热点 / 榜单落盘（顺序固定 1→2，榜单先于热点；均为 RedFox 日更，产出同区块）
HOTRANK_ENTRIES = [
    ("平台榜单-每日落盘", "rank_redfox_daily.py"),
    ("全网社交热点-每日落盘", "hotspot_redfox_daily.py"),
]

# cron 自监控（顺序固定 1→2，看门狗先于异常日报；均 no_agent 脚本，无参数）
CRONALERT_ENTRIES = [
    ("cron健康巡检看门狗", "cron_watchdog.py"),
    ("定时任务异常日报", "cron_ledger_notify.py"),
]

# 协同留痕（顺序固定 1→3，协同三件套巡检 → HANDOFF 分发 → 定时任务总览再生成；均 no_agent 脚本，无参数）
XIETONG_ENTRIES = [
    ("协同三件套巡检", "xietong_audit_cron.py"),
    ("HANDOFF 运行小结自动分发", "handoff_dispatch.py"),
    ("定时任务总览再生成", "cron_overview_cron.py"),
]

# 3 天审计（顺序固定 1→2，work-audit 先于工作卡片关联扫描；均 no_agent 脚本，无参数）
AUDIT3D_ENTRIES = [
    ("work-audit-3d", "work_audit.py"),
    ("工作卡片关联扫描", "cron_work_scan.py"),
]

# 朋友圈素材后置（顺序固定 1→3，与 cron 任务表一致；③ 读② 产出的贴图 manifest，① 只读同一篇深度文、与②无依赖故放最前，顺序不得重排）
MOMENTS_ENTRIES = [
    ("公众号文章朋友圈文案推送", "video_enhance/after_article_moments.py"),
    ("贴图每日生产流水线", "tie_tu_daily.py"),
    ("贴图朋友圈打包推送", "tie_tu_moments_daily.py"),
]

GROUPS = {
    "material": MATERIAL_ENTRIES,
    "favorites": FAVORITES_ENTRIES,
    "watchdogs": WATCHDOG_ENTRIES,
    "accounts": ACCOUNTS_ENTRIES,
    "knowledge": KNOWLEDGE_ENTRIES,
    "pipelines": PIPELINES_ENTRIES,
    "logs": LOGS_ENTRIES,
    "models": MODELS_ENTRIES,
    "skillsmcp": SKILLSMCP_ENTRIES,
    "hotrank": HOTRANK_ENTRIES,
    "cronalert": CRONALERT_ENTRIES,
    "xietong": XIETONG_ENTRIES,
    "audit3d": AUDIT3D_ENTRIES,
    "moments": MOMENTS_ENTRIES,
}

# 与 GNU timeout 一致：超时用独立退出码区分于普通非零退出
TIMEOUT_EXIT_CODE = 124


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _script_path(name):
    if os.path.isabs(name):
        return name
    return os.path.join(HERMES_SCRIPTS_DIR, name)


def _build_entries(only, group="material"):
    """按 group 选条目集，再按 --only 子串筛选；无匹配时把子串当作裸脚本名（便于测失败隔离）。"""
    entries = [{"name": name, "script": _script_path(script)}
               for name, script in GROUPS[group]]
    if not only:
        return entries
    sub = only.lower()
    matched = [e for e in entries if sub in e["name"].lower() or sub in e["script"].lower()]
    if matched:
        return matched
    return [{"name": only, "script": _script_path(only)}]


def _cmdline(argv):
    return subprocess.list2cmdline(argv)


def _first_line(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:500]
    return ""


def _run_one(entry, timeout):
    """独立子进程跑一条，返回 (exit_code, 耗时秒, stdout, stderr 摘要, 是否超时)。"""
    script = entry["script"]
    if not os.path.isfile(script):
        return 127, 0.0, "", "script not found", False
    cmd = [sys.executable, script]
    t0 = time.time()
    timed_out = False
    try:
        r = subprocess.run(cmd, cwd=HERMES_SCRIPTS_DIR, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        rc = r.returncode
        out = r.stdout or ""
        err = _first_line(r.stderr) if rc != 0 else ""
    except subprocess.TimeoutExpired:
        rc = TIMEOUT_EXIT_CODE
        timed_out = True
        out = ""
        err = f"子进程超时（>{timeout:g}s）被杀"
    except OSError as exc:  # 解释器/脚本不可执行等
        rc = 127
        out = ""
        err = str(exc)
    dt = time.time() - t0
    return rc, dt, out, err, timed_out


def _emit_member_stdout(text):
    """透传成员 stdout（仅成功路径）：原样输出正文，并确保其后跟换行、避免与 summary 粘连。"""
    body = (text or "").rstrip("\n")
    if body:
        print(body)


def _tail_block(name, out, n):
    """失败时生成成员 stdout 尾部的展示块；空 stdout 或 n<=0 返回空列表（不打印空块）。"""
    if n <= 0:
        return []
    text = out or ""
    if not text.strip():
        return []
    lines = text.splitlines()
    total = len(lines)
    if total > n:
        block = [f"  [{name}] stdout 末尾 {n} 行（共 {total} 行）",
                 f"  （省略前 {total - n} 行）"]
        block.extend(lines[-n:])
    else:
        block = [f"  [{name}] stdout（共 {total} 行）"]
        block.extend(lines)
    return block


def _run(entries, timeout, quiet_ok=False, pass_stdout=False, fail_tail_lines=15):
    total = len(entries)
    ok = 0
    fail = 0
    stdout_buf = [] if quiet_ok else None
    stderr_buf = [] if quiet_ok else None

    def _out(line):
        if quiet_ok:
            stdout_buf.append(line)
        else:
            print(line)

    def _err(line):
        if quiet_ok:
            stderr_buf.append(line)
        else:
            print(line, file=sys.stderr)

    for i, entry in enumerate(entries, 1):
        rc, dt, out, err, timed_out = _run_one(entry, timeout)
        if rc == 0:
            ok += 1
            _out(f"[{i}/{total}] {entry['name']} ... OK {dt:.1f}s")
            if pass_stdout:
                _emit_member_stdout(out)
        else:
            fail += 1
            if timed_out:
                _out(f"[{i}/{total}] {entry['name']} ... FAIL(timeout) {dt:.1f}s")
            else:
                _out(f"[{i}/{total}] {entry['name']} ... FAIL(exit={rc}) {dt:.1f}s")
            if err:
                _err(f"  [{entry['name']}] {err}")
            for line in _tail_block(entry['name'], out, fail_tail_lines):
                _err(line)

    if quiet_ok:
        if fail == 0:
            return 0
        for line in stdout_buf:
            print(line)
        for line in stderr_buf:
            print(line, file=sys.stderr)
        print(f"summary: 成功 {ok} / 失败 {fail}")
        return 1

    print(f"summary: 成功 {ok} / 失败 {fail}")
    return 0 if fail == 0 else 1


def main(argv=None):
    _reconfigure_stdio()
    parser = argparse.ArgumentParser(description="采集批执行器（素材主动采集 6→1 / 收藏采集 3→1 / 情报写入看门狗 3→1 / 账号体检 4→1 / 知识加工 3→1 / 内容产线 4→1 / 日志维护 2→1 / 模型与供应商周检 3→1 / Skills/MCP 清单 2→1 / 热点与榜单 2→1 / 朋友圈素材后置 3→1）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印要执行的命令，不实际执行")
    parser.add_argument("--only", metavar="SUBSTR",
                        help="只执行名字/脚本名含该子串的条目；无匹配时当作裸脚本名（便于测失败隔离）")
    parser.add_argument("--timeout", type=float, default=900,
                        help="每条采集子进程的超时秒数（默认 900）")
    parser.add_argument("--quiet-ok", action="store_true",
                        help="全部成功时不输出任何内容（静默）；任一失败才逐条打印全部条目+summary 并 exit 1（告警型任务用）")
    parser.add_argument("--pass-stdout", action="store_true",
                        help="成员成功时也透传其 stdout 正文（内容型周报用）；与 --quiet-ok 互斥，同时给出报错退出码 2")
    parser.add_argument("--fail-tail-lines", type=int, default=15, metavar="N",
                        help="成员失败时额外打印其 stdout 末尾 N 行（默认 15；0=不打印）")
    parser.add_argument("--group", choices=["material", "favorites", "watchdogs", "accounts", "knowledge", "pipelines", "logs", "models", "skillsmcp", "hotrank", "cronalert", "xietong", "audit3d", "moments"], default="material",
                        help="条目组：material=素材主动采集6条（默认），favorites=收藏采集3条，watchdogs=情报写入看门狗3条，accounts=账号体检4条，knowledge=知识加工3条（归一必须最后），pipelines=内容产线4条（公众号必须第一、顺序不得重排），logs=日志维护2条（索引→看门狗），models=模型与供应商周检3条（供应商巡检→模型健康巡检→配置汇总），skillsmcp=Skills/MCP清单2条（清单刷新→资产盘点），hotrank=热点与榜单2条（榜单→热点），cronalert=cron自监控2条（看门狗→异常日报），xietong=协同留痕3条（协同巡检→HANDOFF分发→总览再生成），audit3d=3天审计2条（work-audit→卡片关联扫描），moments=朋友圈素材后置3条（公众号朋友圈文案→贴图生产→贴图朋友圈打包，顺序不得重排）")
    args = parser.parse_args(argv)

    if args.pass_stdout and args.quiet_ok:
        print("错误：--pass-stdout 与 --quiet-ok 互斥，不能同时使用", file=sys.stderr)
        return 2

    entries = _build_entries(args.only, args.group)

    if args.dry_run:
        total = len(entries)
        for i, entry in enumerate(entries, 1):
            cmd = [sys.executable, entry["script"]]
            print(f"[{i}/{total}] {entry['name']} -> {_cmdline(cmd)}")
        return 0

    # 启动校验（仅全量默认跑）：缺任一采集脚本即明确报错并列出缺哪个，拒绝执行
    if not args.only:
        missing = [e for e in entries if not os.path.isfile(e["script"])]
        if missing:
            print("启动校验失败：以下采集脚本不存在，拒绝执行：", file=sys.stderr)
            for e in missing:
                print(f"  - {e['name']}: {e['script']}", file=sys.stderr)
            return 1

    return _run(entries, args.timeout, quiet_ok=args.quiet_ok, pass_stdout=args.pass_stdout,
                fail_tail_lines=args.fail_tail_lines)


if __name__ == "__main__":
    sys.exit(main())
