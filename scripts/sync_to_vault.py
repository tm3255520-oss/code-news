#!/usr/bin/env python3
"""
sync_to_vault.py - 宿主机一键同步到 Obsidian vault

把 code-news/research/dsh-std-video-analysis/待同步vault/ 下的文件，
按相对路径复制到 D:\\Obsidian Vault 的白名单目录。
（沙箱 Claude 写不了 vault，本脚本在宿主机跑，达到同等效果。）

待同步vault/ 目录组织 = vault 相对路径，如：
  待同步vault/内容生产/热点监控/DSH候选池.md  →  vault/内容生产/热点监控/DSH候选池.md

用法:
  python scripts/sync_to_vault.py [--dry-run]   # 宿主机 Python 运行
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

VAULT_ROOT = Path(r"D:\Obsidian Vault\obsidian Vault")
SRC_ROOT = Path(r"C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\待同步vault")
ALLOWED_PREFIXES = ["内容生产", "AI工具", "wiki/decisions", "raw"]


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not SRC_ROOT.is_dir():
        print(f"源目录不存在: {SRC_ROOT}")
        return 1
    copied = skipped = blocked = 0
    for src in sorted(SRC_ROOT.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SRC_ROOT).as_posix()
        if ".." in Path(rel).parts:
            print(f"  跳过(穿越): {rel}")
            blocked += 1
            continue
        prefix = rel.split("/")[0]
        if not any(rel == p or rel.startswith(p + "/") for p in ALLOWED_PREFIXES):
            print(f"  跳过(白名单外): {rel}")
            blocked += 1
            continue
        dst = VAULT_ROOT / rel
        if dry:
            print(f"  [dry] {rel} -> {dst}")
            copied += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✅ {rel}")
        except Exception as e:
            print(f"  ❌ {rel}: {e}")
            skipped += 1
    print(f"\n完成: 复制 {copied} | 跳过 {skipped} | 拦截 {blocked}{'（dry-run）' if dry else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
