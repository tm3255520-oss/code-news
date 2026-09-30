#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""register_xietong_cron.py — 把「协同三件套巡检」与「协同周报」注册进 Hermes cron。

做法（沿用 `cron_ledger_notify.py` / `register_memory_governance_cron.py` 的既有约定）：
    1. 在 `HERMES_HOME/scripts/` 放**薄转发脚本**（cron 调度器只认该目录内的脚本），
       转发到 code-news 里的真实实现（git 管理，不产生副本漂移）。
    2. 用 `cron.jobs.create_job` 注册两个 no_agent job（幂等：同名已存在则跳过）。

用法（在 Windows 侧运行，Hermes 环境）：
    python scripts/register_xietong_cron.py --dry-run
    python scripts/register_xietong_cron.py
    python scripts/register_xietong_cron.py --deliver local      # 不推飞书
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HERMES_HOME = Path(r"C:\Users\Administrator\.hermes")
HERMES_SCRIPTS = HERMES_HOME / "scripts"
JOBS = HERMES_HOME / "cron" / "jobs.json"
DEFAULT_DELIVER = "feishu:oc_28164d05d12f3e0d7a9fef3c3a6b0a65"  # 与「定时任务异常日报」同频道

FORWARDER_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发到 code-news 的 {target}（供 Hermes cron 调用）。

为什么要转发：cron 调度器要求 job 脚本落在 HERMES_HOME/scripts/ 内，
实现放在 code-news（git 管理）。与 cron_ledger_notify.py 同一做法。
"""
import subprocess
import sys

TARGET = r"{target_path}"
CWD = r"{cwd}"

cmd = [sys.executable, TARGET, *{extra_args}, *sys.argv[1:]]
try:
    sys.exit(subprocess.call(cmd, cwd=CWD))
except Exception as e:  # noqa: BLE001
    print("{name} failed:", e)
    sys.exit(1)
'''

JOBS_SPEC = (
    {
        "name": "协同三件套巡检",
        "schedule": "30 1 * * *",
        "script": "xietong_audit_cron.py",
        "forwarder": ("xietong_audit_cron.py", "xietong_audit.py",
                      ["--quiet-when-clean", "--stale-days", "7"]),
        "prompt": "",
    },
    {
        "name": "协同周报",
        "schedule": "0 9 * * 1",
        "script": "xietong_weekly_cron.py",
        "forwarder": ("xietong_weekly_cron.py", "xietong_weekly.py", ["--days", "7"]),
        "prompt": "",
    },
)


def existing_names() -> set[str]:
    if not JOBS.is_file():
        return set()
    data = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    rows = list(jobs.values()) if isinstance(jobs, dict) else list(jobs)
    return {str(j.get("name")) for j in rows if isinstance(j, dict)}


def write_forwarder(name: str, target: str, extra_args: list[str], dry_run: bool) -> Path:
    path = HERMES_SCRIPTS / name
    body = FORWARDER_TEMPLATE.format(
        name=name, target=target, target_path=str(REPO_ROOT / "scripts" / target),
        cwd=str(REPO_ROOT), extra_args=repr(extra_args),
    )
    if dry_run:
        print(f"[dry-run] 写转发脚本 {path}")
    else:
        HERMES_SCRIPTS.mkdir(parents=True, exist_ok=True)
        path.write_text(body.replace("\n", "\r\n"), encoding="utf-8")
        print(f"写转发脚本 {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="注册协同三件套 cron")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--deliver", default=DEFAULT_DELIVER)
    parser.add_argument("--force", action="store_true", help="同名已存在时也重新创建")
    args = parser.parse_args(argv)

    have = existing_names()
    print(f"现有 cron 任务 {len(have)} 个；本次注册 {len(JOBS_SPEC)} 个")

    for spec in JOBS_SPEC:
        fname, target, extra = spec["forwarder"]
        write_forwarder(fname, target, extra, args.dry_run)
        if spec["name"] in have and not args.force:
            print(f"跳过（已存在）：{spec['name']}")
            continue
        if args.dry_run:
            print(f"[dry-run] create_job(name={spec['name']!r}, schedule={spec['schedule']!r}, "
                  f"script={spec['script']!r}, no_agent=True, deliver={args.deliver!r})")
            continue

        sys.path.insert(0, str(HERMES_HOME / "hermes-agent"))
        try:
            from cron.jobs import create_job  # noqa: PLC0415
        except ImportError as exc:
            print(f"Hermes cron API 不可用：{exc}", file=sys.stderr)
            return 1
        job = create_job(prompt=spec["prompt"], schedule=spec["schedule"], name=spec["name"],
                         script=spec["script"], no_agent=True, deliver=args.deliver)
        print(f"已注册：{spec['name']}（id={job.get('id')}，{spec['schedule']}）")

    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
