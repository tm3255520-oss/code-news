#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
register_vault_sync_cron.py — 注册 vault 自动同步 cron（每 10 分钟）
把 code-news/research/dsh-std-video-analysis/待同步vault/ 内容按白名单同步进 Obsidian vault。
确定性脚本（no_agent=True，不走 LLM），幂等，无文件时秒退。

用法（宿主机）：python register_vault_sync_cron.py
"""
import sys, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, r"C:\Users\Administrator\.hermes\hermes-agent")
from cron.jobs import create_job as cron_add  # noqa: E402


def main():
    job = cron_add(
        prompt="自动同步：把 code-news/research/dsh-std-video-analysis/待同步vault/ 内容按白名单(内容生产/AI工具/wiki/decisions/raw)复制进 Obsidian vault。",
        schedule="*/10 * * * *",
        name="vault 自动同步",
        script="sync_to_vault.py",
        no_agent=True,
        deliver="local",
    )
    print("✅ vault 自动同步 cron 注册成功:")
    print(json.dumps(job, ensure_ascii=False, indent=2)[:600])


if __name__ == "__main__":
    main()
