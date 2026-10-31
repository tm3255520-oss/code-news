#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 Obsidian vault 的「双链同名歧义」，用三连判据避免假失败。

用法:
    python scan-wikilink-ambiguity.py [vault根目录]
    默认 vault: D:\\Obsidian Vault\\obsidian Vault

判据（缺一即产生假失败 —— 见 SKILL.md §十/§十·补）:
    ① 双链目标含 "/"  → 带路径，Obsidian 明确解析 → 跳过
    ② 裸 basename 且引用方同目录存在同名文件 → 同目录优先 → 跳过
    ③ 裸 basename + 同目录无 + 全库同名 >= 2 → ★真歧义

输出:
    - 全库 .md 数 / 同名 basename 组数
    - 三类计数（带路径跳过 / 同目录消解 / 真歧义）
    - 真歧义按引用次数降序，附候选路径与引用方
"""
import os
import re
import sys
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\Obsidian Vault\obsidian Vault"
SKIP = {".obsidian", ".trash", ".git"}
LINK = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]")


def main():
    files, groups = [], defaultdict(list)
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP]
        for n in fn:
            if n.lower().endswith(".md"):
                ap = os.path.join(dp, n)
                files.append((os.path.relpath(ap, ROOT), ap))
                groups[os.path.splitext(n)[0]].append(os.path.relpath(ap, ROOT))

    multi = {n: p for n, p in groups.items() if len(p) > 1}

    withpath = samedir = 0
    real = defaultdict(list)
    for rel, ap in files:
        try:
            t = open(ap, encoding="utf-8").read()
        except Exception:
            continue
        if "[[" not in t:
            continue
        d = os.path.dirname(ap)
        for m in LINK.finditer(t):
            tgt = m.group(1).strip().replace("\\", "/")
            if "/" in tgt:                                   # 判据 1
                withpath += 1
                continue
            base = os.path.splitext(tgt)[0]
            if base not in multi:
                continue
            if os.path.exists(os.path.join(d, base + ".md")):  # 判据 2
                samedir += 1
                continue
            real[base].append((rel, m.group(0)))             # 判据 3

    print("全库 .md=%d   同名 basename=%d 组" % (len(files), len(multi)))
    print("① 带路径双链（跳过）: %d" % withpath)
    print("② 同目录优先消解: %d" % samedir)
    print("★③ 真歧义: %d 组 / %d 次引用" % (len(real), sum(len(v) for v in real.values())))
    print()
    for base, lst in sorted(real.items(), key=lambda x: -len(x[1])):
        print("### [[%s]]  %d 次引用；候选 %d 份:" % (base, len(lst), len(multi[base])))
        for c in multi[base]:
            print("      " + c)
        seen = set()
        for rel, _ in lst:
            if rel in seen:
                continue
            seen.add(rel)
            print("      ← %s" % rel)
            if len(seen) >= 5:
                rest = len(set(r for r, _ in lst)) - 5
                if rest > 0:
                    print("      ...（还有 %d 个引用方）" % rest)
                break
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
