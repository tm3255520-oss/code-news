#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tool_inventory.py — 开发前的能力盘点（把"先扫描再开发"变成一条命令）。

为什么有这个脚本：vault《协作七原则》第 4 条已经写了「能力走注册表，唯一裁决」，
但那条规则一直靠"记得去翻"来执行 —— 结果是同一个能力被开发两三遍
（2026-09-17 实测抓到 4 处重复：redfox 调用、转写、抽帧、响度检测）。
本脚本把"翻"变成"跑"：给关键词，扫五处来源，列出已有实现候选。

扫描来源（全部只读、零网络、零 LLM）：
  1. config/tool_registry.json          能力路由总表（唯一权威）
  2. .agents/skills/*/SKILL.md          仓库自研技能
  3. <hub>/.agents/skills/*/SKILL.md    社区技能 hub（含 junction）
  4. .hermes/scripts + .hermes/skills   Hermes 侧脚本与技能
  5. config/mcp_toolkit.json            toolkit MCP 工具 → 底层实现

用法：
    python scripts/tool_inventory.py 取视频 转写
    python scripts/tool_inventory.py --all            # 全量清单
    python scripts/tool_inventory.py 响度 --json
    python scripts/tool_inventory.py 取视频 --no-hub  # 不扫 hub（更快）

退出码：0 = 有命中；1 = 无命中（无命中意味着"可能是真空白"，可以往下走新建）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "config" / "tool_registry.json"
TOOLKIT = REPO / "config" / "mcp_toolkit.json"
REPO_SKILLS = REPO / ".agents" / "skills"
HUB_SKILLS = Path(r"C:\Users\Administrator\.agents\skills")
HERMES = Path(r"C:\Users\Administrator\.hermes")

CHECKLIST = (
    "处置三选一（不要默认新建）：\n"
    "  ① 直接调用——已有实现能满足，写明调用方式即可\n"
    "  ② 扩展/合并——已有实现差一点，改它；同类功能合并成一个\n"
    "  ③ 新建——前两者都不成立，且必须在提交信息或技能变更日志里写清"
    "「为什么不能复用」"
)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def scan_registry() -> list[dict]:
    out = []
    for key, val in (_read_json(REGISTRY).get("interfaces") or {}).items():
        blob = json.dumps(val, ensure_ascii=False)
        out.append({
            "source": "注册表",
            "name": key,
            "target": str(val.get("primary") or val.get("model") or "?"),
            "desc": str(val.get("purpose") or "")[:90],
            "blob": blob,
        })
    return out


def scan_toolkit() -> list[dict]:
    out = []
    for key, val in (_read_json(TOOLKIT).get("tools") or {}).items():
        blob = json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)
        target = val.get("script", "") if isinstance(val, dict) else ""
        out.append({
            "source": "toolkit",
            "name": key,
            "target": str(target),
            "desc": "",
            "blob": blob,
        })
    return out


def scan_skill_dirs(root: Path, source: str) -> list[dict]:
    out = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir()):
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = ""
        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")[:1200]
        except Exception:
            pass
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        out.append({
            "source": source,
            "name": child.name,
            "target": str(skill_md),
            "desc": (m.group(1).strip() if m else "")[:90],
            "blob": text,
        })
    return out


def scan_py(root: Path, source: str, skip: tuple = ("node_modules", "site-packages",
                                                    "__pycache__", ".venv")) -> list[dict]:
    """扫 Python 实现（仓库脚本 / 技能内脚本 / Hermes 脚本）。

    必须包含仓库自己的 scripts/ —— 最可能的已有实现就在那里
    （第一版漏了它，结果"响度"关键词一条仓库实现都没扫到）。
    """
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*.py")):
        s = str(f)
        if any(k in s for k in skip):
            continue
        try:
            # 读全文而不是前 N 字符：函数与常量往往在后半段
            # （第一版只读 900 字符，"响度"扫不到 analyze_video_production.py 里的实现）
            head = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        doc = re.search(r'"""(.*?)"""', head, re.S)
        out.append({
            "source": source,
            "name": f.stem,
            "target": str(f),
            "desc": (doc.group(1).strip().splitlines()[0][:90] if doc else ""),
            "blob": head,
        })
    return out


def scan_hermes_scripts() -> list[dict]:
    out: list[dict] = []
    for sub in ("scripts", "skills"):
        out += scan_py(HERMES / sub, f"hermes/{sub}")
    return out


def collect(include_hub: bool) -> list[dict]:
    items = scan_registry() + scan_toolkit()
    items += scan_py(REPO / "scripts", "仓库脚本")
    items += scan_skill_dirs(REPO_SKILLS, "仓库技能")
    items += scan_py(REPO_SKILLS, "技能脚本")
    if include_hub:
        items += scan_skill_dirs(HUB_SKILLS, "hub 技能")
    items += scan_hermes_scripts()
    return items


def match(items: list[dict], keywords: list[str]) -> dict[str, list[dict]]:
    """两级匹配：整词子串为强命中；中文关键词退化为"逐字都在"为弱命中。

    为什么要弱命中：中文说法不统一——关键词「取视频」在注册表里写的是「视频获取」，
    纯子串匹配会漏掉真正的实现（实测漏掉了 video_fetch_browser）。
    盘点宁可多列几条，也不要漏。
    """
    hits: dict[str, list[dict]] = {k: [] for k in keywords}
    for it in items:
        hay = f"{it['name']} {it['target']} {it['desc']} {it['blob']}".lower()
        for kw in keywords:
            low = kw.lower()
            if low in hay:
                hits[kw].append({**it, "match": "强"})
                continue
            # 弱命中：只要求关键词的末两字出现。中文说法不统一，但末两字通常是
            #   能力主体（取视频→视频 / 语音转写→转写），比"逐字都在"精确得多。
            #   仅对中文关键词启用：ASCII 关键词（OCR / TTS）没有语序变体，
            #   启用它会退化成匹配末两字符（OCR→"cr"），几乎全库命中。
            is_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in low)
            if is_cjk and len(low) >= 2 and low[-2:] in hay:
                hits[kw].append({**it, "match": "弱"})
    for kw in hits:
        hits[kw].sort(key=lambda v: (v["match"] != "强", v["source"], v["name"]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="开发前的能力盘点（先扫描再开发）")
    ap.add_argument("keywords", nargs="*", help="能力关键词，如 取视频 / 转写 / OCR / 响度")
    ap.add_argument("--all", action="store_true", help="输出全量清单（不筛选）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-hub", action="store_true", help="不扫社区技能 hub（更快）")
    args = ap.parse_args()
    if not args.keywords and not args.all:
        ap.error("至少给一个关键词，或用 --all")

    items = collect(include_hub=not args.no_hub)
    if args.all:
        hits = {"(全部)": items}
    else:
        hits = match(items, args.keywords)

    if args.json:
        print(json.dumps({k: [{kk: v[kk] for kk in ("source", "name", "target", "desc")}
                              for v in vs] for k, vs in hits.items()},
                         ensure_ascii=False, indent=2))
    else:
        STRUCTURED = ("注册表", "toolkit", "仓库技能", "hub 技能")
        print(f"[盘点] 来源条目 {len(items)} 条；关键词 {args.keywords or '(全部)'}")
        total = 0
        for kw, vs in hits.items():
            total += len(vs)
            print(f"\n=== 命中「{kw}」：{len(vs)} 条")
            strong = [v for v in vs if v["match"] == "强"]
            weak_struct = [v for v in vs if v["match"] == "弱" and v["source"] in STRUCTURED]
            weak_script = [v for v in vs if v["match"] == "弱" and v["source"] not in STRUCTURED]
            for v in strong[:20]:
                print(f"  - [{v['source']}·{v['match']}命中] {v['name']}")
                print(f"      {v['target']}")
                if v["desc"]:
                    print(f"      {v['desc']}")
            for v in weak_struct[:10]:
                print(f"  - [{v['source']}·弱命中] {v['name']}")
                print(f"      {v['target']}")
            if len(strong) > 20:
                print(f"  … 强命中另有 {len(strong) - 20} 条")
            if weak_script:
                print(f"  … 脚本类弱命中 {len(weak_script)} 条（多为旁证，"
                      f"要看清单用 --json）")
        print("\n" + CHECKLIST)
        print("\n提示：中文说法不统一，一种说法没命中不等于空白——"
              "换 2–3 个说法再跑（例：取视频 / 视频获取 / 下载视频；转写 / 转录 / ASR）。")
        if total == 0:
            print("\n结论：本次关键词无命中 —— 仍需人工确认是否真空白，再决定新建。")

    if args.all:
        return 0
    return 0 if any(hits.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
