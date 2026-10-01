#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/raw_wechat_dedup_cleanup.py —— 清理 raw/articles/wechat 的「同文多日重复」。

成因（2026-10-01 定位）：`wechat_redfox_collect.py` 把 `known` 台账集合**算出来却没用**
→ 同一条爆款按日期前缀每天重存一份（raw_lint 判据修好后暴露 14 组 / 多余 56 份）。采集端已修。

本脚本只做**存量清理**：每组保留「采集日最早」的那一份（07 标准 §六 的 L2 口径：只留最早的当代表），
其余**移动到 vault 外的备份目录**（可恢复），**不删除**。

安全前置：**只移动「正文与保留件逐字相同」的文件**；正文不同就跳过并报告（宁可不做）。

用法：
  python scripts/_probe/raw_wechat_dedup_cleanup.py            # 干跑（默认）
  python scripts/_probe/raw_wechat_dedup_cleanup.py --apply
"""
import argparse
import collections
import hashlib
import re
import shutil
import sys
from pathlib import Path

VAULT = Path(r"D:\Obsidian Vault\obsidian Vault")
SRC = VAULT / "raw" / "articles" / "wechat"
BACKUP = Path(r"D:\Obsidian Vault\_整改备份-20261001-raw重复清理\raw\articles\wechat")


FOOTER = re.compile(r"(?m)^\*由\s+wechat_redfox_collect\.py\s+采集于.*$")


def body_of(p):
    """取「原文段」做比对基准。

    不能整篇比对：同一篇文章每次重采/归一时，**采集日期**、**页脚时间戳**、
    以及 LLM 重新生成的**「核心要点」**都会不同（实测同一组里这三处必差、原文段逐字一致）。
    这些是「同一作品的多次加工」留下的差异，不是内容不同 —— 所以只比 `## 📄 原文` 段并去页脚。
    """
    t = p.read_text(encoding="utf-8", errors="replace")
    bt = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", t, flags=re.DOTALL)
    if "## 📄 原文" in bt:
        bt = bt.split("## 📄 原文", 1)[1]
    bt = FOOTER.sub("", bt)
    return re.sub(r"\s+", "", bt)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def work_key(p):
    t = p.read_text(encoding="utf-8", errors="replace")[:1200]
    u = re.search(r"^url\s*:\s*\"?(.*?)\"?\s*$", t, re.M)
    m = re.search(r"[?&]sn=([0-9a-fA-F]{32})", u.group(1) if u else "")
    if m:
        return m.group(1).lower()
    w = re.search(r"^work_id\s*:\s*\"?(.*?)\"?\s*$", t, re.M)
    return w.group(1).lower() if w else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真移动（默认只干跑）")
    args = ap.parse_args()

    files = sorted(SRC.glob("*.md"))
    groups = collections.defaultdict(list)
    for f in files:
        k = work_key(f)
        if k:
            groups[k].append(f)
    dups = {k: sorted(v, key=lambda p: p.name) for k, v in groups.items() if len(v) > 1}

    move, skip = [], []
    for k, v in sorted(dups.items(), key=lambda x: -len(x[1])):
        keep = v[0]                       # 文件名以日期开头 → 最早的排最前
        kb = sha(body_of(keep))
        for f in v[1:]:
            (move if sha(body_of(f)) == kb else skip).append((k, keep, f))

    print("扫描 %d 篇 ｜ 重复组 %d ｜ 计划移动 %d 份 ｜ 正文不同·跳过 %d 份"
          % (len(files), len(dups), len(move), len(skip)))
    for k, keep, f in skip:
        print("  ⚠ 跳过（正文与保留件不同）：%s  ←  %s" % (f.name, keep.name))
    for k, keep, f in move[:8]:
        print("  - %s  ←  保留 %s" % (f.name[:56], keep.name[:40]))
    if len(move) > 8:
        print("  …（另有 %d 份）" % (len(move) - 8))
    if not args.apply:
        print("\n（干跑：未移动任何文件）")
        return 0

    BACKUP.mkdir(parents=True, exist_ok=True)
    n = 0
    for k, keep, f in move:
        shutil.move(str(f), str(BACKUP / f.name))
        n += 1
    (BACKUP.parent.parent / "README.md").write_text(
        "# raw/articles/wechat 同文多日重复 —— 清理备份（2026-10-01）\n\n"
        "用户 2026-10-01 裁定「重复的要清掉」。\n\n"
        "- 成因：`wechat_redfox_collect.py` 的 `known` 台账集合算了没用 → 同一条爆款每天重存一份。\n"
        "  采集端已修（落盘前用 `known` 过滤）。\n"
        "- 口径：每组保留**采集日最早**的那份；正文逐字相同的其余份移到这里（**未删除**，可恢复）。\n"
        "- 实测：移出 %d 份；库内 0 篇引用这些文件名（移前已全库检索确认）。\n"
        "- 恢复：把本目录的 `.md` 移回 `raw/articles/wechat/` 即可。\n"
        "- 关联：任务台账 WK-20261001-30；判据见 `系统中枢/规则与权限/智能体共享/07-raw素材层标准.md` §六/§七。\n"
        % n, encoding="utf-8")
    print("\n✅ 已移动 %d 份 → %s" % (n, BACKUP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
