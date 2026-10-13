#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 vault 内「.md 路径引用」是否存在（判据收紧，排除已知假失败源）。

用法:
    python verify-vault-refs.py [vault根目录]
    默认 vault: D:\\Obsidian Vault\\obsidian Vault

抽取对象:
    A. 行内代码 `...` 中的 .md 路径
    B. 带路径的双链 [[a/b/xxx.md|alias]]

判据要点（见 SKILL.md §十）:
    - 基准双基准解析: vault 根 + 系统中枢/（引用惯用基准是后者）
    - 只认以 vault 顶层目录或中枢子目录开头的路径
    - 明确排除假失败源:
        通配符 * ? {} / 占位 < > / 省略号 ... / ./ ../ ~/ / 绝对盘符 / URL
        点开头的外部工程目录（.claude/ .agents/ 等）/ 裸文件名

⚠️ 输出的 MISSING 必须逐个定性，不要直接当断链:
    模板占位（YYYY-MM-DD / 序号 / <id>）、历史路径描述（旧目录结构）、
    已删文件的叙述 —— 全是假失败。
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else r"D:\Obsidian Vault\obsidian Vault"
SKIP = {".obsidian", ".trash", ".git"}

TOP = ("系统中枢", "知识库", "内容生产", "参考库", "raw", "AI工具")
SYS_SUB = ("经验沉淀", "运行手册", "规则与权限", "各Agent档案", "地图与导航",
           "运行小结", "规范", "情报与选题")

CODE = re.compile(r"`([^`\n]+)`")
WLINK = re.compile(r"\[\[([^\]\|#]+)(?:#[^\]\|]+)?(?:\|[^\]]+)?\]\]")
BAD = ("*", "?", "{", "}", "<", ">", "...")


def norm(s):
    s = s.strip().replace("\\", "/")
    if not s.lower().endswith(".md"):
        return None
    if any(b in s for b in BAD):
        return None
    if s.startswith(("./", "../", "~/")) or re.match(r"^[A-Za-z]:", s) or "://" in s:
        return None
    if s.startswith("."):          # .claude/ .agents/ 等外部工程目录
        return None
    if s.count("/") == 0:          # 裸文件名，交 basename 兜底，此处不查
        return None
    head = s.split("/")[0]
    if head not in TOP and head not in SYS_SUB:
        return None
    return s


def main():
    files = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP]
        for n in fn:
            if n.lower().endswith(".md"):
                files.append((os.path.relpath(os.path.join(dp, n), ROOT), os.path.join(dp, n)))

    from collections import defaultdict
    refs = defaultdict(list)
    for rel, ap in files:
        try:
            t = open(ap, encoding="utf-8").read()
        except Exception:
            continue
        for m in CODE.finditer(t):
            s = norm(m.group(1))
            if s:
                refs[s].append((rel, m.group(0)))
        if "[[" in t:
            for m in WLINK.finditer(t):
                s = norm(m.group(1))
                if s:
                    refs[s].append((rel, m.group(0)))

    def exists(s):
        for base in (ROOT, os.path.join(ROOT, "系统中枢")):
            if os.path.exists(os.path.join(base, s.replace("/", os.sep))):
                return True
        return False

    missing = {s: v for s, v in refs.items() if not exists(s)}
    print("vault 内 .md 路径引用: %d 个目标 / %d 次引用" % (len(refs), sum(len(v) for v in refs.values())))
    print("MISSING: %d" % len(missing))
    for s, v in sorted(missing.items()):
        print("\n  ✗ %s   (%d 处)" % (s, len(v)))
        for rel, _ in v[:3]:
            print("       ← %s" % rel)
    print()
    print("✅ 全部存在，无断链" if not missing else "⚠️ 上列 MISSING 需逐个定性（模板占位/历史路径/已删叙述 = 假失败）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
