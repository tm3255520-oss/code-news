#!/usr/bin/env python3
"""check_doc_references.py -- 活文档路径引用一致性校验（多 Agent 防漂移）。

背景：多 Agent 协作下，同一份路径知识被复制在多个「指令 / 规范 / 导航」文档里。
目录改名后散落引用不会自动同步，而各 Agent 检查时读的正是这些文档，导致
「引用失效」长期无人发现。本脚本用确定性方式（不靠 LLM 判断）逐个验证：

  扫描「活文档」（指令文件 / 共享认知 / 运行手册 / 索引页 / 工具登记专区）里的硬引用
  （反引号路径、markdown 链接、@import、dataview 的 from），
  逐个验证目标路径是否真实存在，输出 MISSING 清单。

判定为三态:
  ok      -- 目标路径存在
  missing -- 目标路径确定不存在（需要修）
  skip    -- 无法在 Windows 侧确定性解析（路径片段 / 概念名 / WSL 路径），不判错

用法（Windows 与 WSL 均可运行；2026-09-14 起平台自适应）:
  python scripts/check_doc_references.py                 # 文本报告
  python scripts/check_doc_references.py --format json   # JSON 报告
  python scripts/check_doc_references.py --quiet         # 仅汇总 + MISSING 明细
  python scripts/check_doc_references.py --show-skip     # 附 SKIP 明细（排查用）
  python scripts/check_doc_references.py --list-targets  # 只列出将被扫描的文档
  python scripts/check_doc_references.py --root <dir>    # 覆盖 vault 根（测试用）

退出码: 存在 MISSING 引用返回 1，否则 0（可直接用于 cron / 巡检）。

注意: 汇总里的「扫描活文档」必须 > 0。若为 0，说明根路径没解析对，本次运行
      无效 —— 不得当作「通过」（历史上在 WSL 下跑就出现过这种假通过）。

豁免: 某行内写 `<!-- refcheck:ignore -->` 则该行所有引用跳过（用于示例 / 历史路径）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ── 平台自适应（2026-09-14 新增）────────────────────────────────────────
# 本脚本原为 Windows 专用：根路径与分隔符都硬编码。现在同一份脚本也能在
# WSL / Linux 下运行，且 **Windows 行为逐字不变**（os.name == "nt" 时走原逻辑）：
#   非 Windows：盘符路径 D:\x → /mnt/d/x；引用里的 "\\" 归一化为 "/"。
# 验收判据：Windows 与 WSL 两次运行必须给出相同的
#   扫描活文档 / 提取硬引用 / OK / MISSING / SKIP 计数。
IS_WINDOWS = os.name == "nt"
LOCAL_SEP = "\\" if IS_WINDOWS else "/"


def _to_local_sep(value: str) -> str:
    """把引用里的分隔符归一化为当前平台的分隔符。"""
    return value.replace("/", LOCAL_SEP) if IS_WINDOWS else value.replace("\\", "/")


def _platform_root(win_path: str) -> Path:
    """Windows 盘符路径 → 当前平台路径（Windows 原样；其它平台映射到 /mnt/<drive>）。"""
    if IS_WINDOWS:
        return Path(win_path)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", win_path)
    if m:
        return Path("/mnt") / m.group(1).lower() / m.group(2).replace("\\", "/")
    return Path(win_path)


def _localize_abs(raw: str) -> Path:
    r"""绝对路径引用 → 当前平台路径（Windows 原样；非 Windows 把 D:\x 映射为 /mnt/d/x）。"""
    if IS_WINDOWS:
        return Path(raw.replace("/", "\\"))
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if m:
        return Path("/mnt") / m.group(1).lower() / m.group(2).replace("\\", "/")
    return Path(raw.replace("\\", "/"))


VAULT_ROOT = _platform_root(r"D:\Obsidian Vault\obsidian Vault")
CODE_NEWS_ROOT = _platform_root(r"C:\Users\Administrator\Documents\code-news")
AGENT_WORK_ROOT = _platform_root(r"C:\Users\Administrator\Documents\agent-work")
HOME_ROOT = _platform_root(r"C:\Users\Administrator")

IGNORE_MARK = "<!-- refcheck:ignore"
IGNORE_FILE_MARK = "<!-- refcheck:ignore-file"

OK = "ok"
MISSING = "missing"
SKIP = "skip"

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AT_IMPORT_RE = re.compile(r"^\s*@(.+?)\s*$")
DATAVIEW_FROM_RE = re.compile(r'\bfrom\s*:?\s*"([^"]+)"', re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*```(\w*)")
# 模板 / 占位路径（如 YYYY-MM-DD、序号），不参与存在性判定
TEMPLATE_RE = re.compile(r"YYYY|MM-DD|序号|placeholder|\.\.\.", re.IGNORECASE)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass
class Ref:
    line: int
    text: str


@dataclass
class Finding:
    doc: Path
    line: int
    ref: str
    status: str
    detail: str


def candidate_roots(vault_root: Path) -> list[Path]:
    """相对引用的候选解析根（按优先级，vault 优先）。"""
    return [
        vault_root,
        CODE_NEWS_ROOT,
        AGENT_WORK_ROOT,
        HOME_ROOT / ".codex",
        HOME_ROOT / ".claude",
        HOME_ROOT / ".hermes",
        HOME_ROOT / ".workbuddy-ai",
        HOME_ROOT,
    ]


def known_prefix_map(vault_root: Path) -> dict[str, tuple[Path, bool]]:
    """路径首段 → (所属根, 是否保留首段)。

    - 独立根（code-news / agent-work）：首段就是根目录名，拼根时不再保留首段。
    - vault 内顶级目录（raw / 内容生产 / 系统中枢 ...）：根是 vault 根，
      首段是 vault 下的真实目录名，拼接时必须保留。
    """
    return {
        "code-news": (CODE_NEWS_ROOT, False),
        "agent-work": (AGENT_WORK_ROOT, False),
        "raw": (vault_root, True),
        "内容生产": (vault_root, True),
        "知识库": (vault_root, True),
        "系统中枢": (vault_root, True),
        "参考库": (vault_root, True),
        "ai工具": (vault_root, True),
        "wiki": (vault_root, True),  # 历史路径名，保留识别以便抓失效引用
    }


# 工具登记专区（2026-09-27 新增）：自研 skill / MCP 与脚本工具链的登记文档目录。
# 这些文档同样在复制路径知识（「哪个工具写到哪个目录」），必须与运行手册一起纳入校验，
# 否则专区内的引用断链不会有人发现。新增专区只要往元组里加目录名。
REGISTRY_ZONES = ("系统skills以及MCP", "系统脚本工具链")


def default_targets(vault_root: Path) -> list[Path]:
    """需要扫描的「活文档」清单。"""
    targets: list[Path] = [
        # 指令文件
        vault_root / "AGENTS.md",
        vault_root / "index.md",
        CODE_NEWS_ROOT / "AGENTS.md",
        CODE_NEWS_ROOT / "CLAUDE.md",
        AGENT_WORK_ROOT / "AGENTS.md",
        HOME_ROOT / ".codex" / "AGENTS.md",
        HOME_ROOT / ".claude" / "CLAUDE.md",
        HOME_ROOT / ".hermes" / "SOUL.md",
        HOME_ROOT / ".workbuddy-ai" / "SOUL.md",
        HOME_ROOT / ".workbuddy-ai" / "IDENTITY.md",
        HOME_ROOT / ".workbuddy-ai" / "USER.md",
    ]
    # 共享认知
    shared = vault_root / "系统中枢" / "规则与权限" / "智能体共享"
    if shared.exists():
        targets += sorted(shared.glob("*.md"))
    # 运行手册
    manual = vault_root / "系统中枢" / "运行手册"
    if manual.exists():
        targets += sorted(manual.glob("*.md"))
    # 工具登记专区（自研 skill / MCP / 脚本工具链）
    for zone in REGISTRY_ZONES:
        zone_dir = vault_root / "系统中枢" / zone
        if zone_dir.exists():
            targets += sorted(zone_dir.glob("*.md"))
    # 索引 / 导航
    targets += [
        vault_root / "知识库" / "INDEX.md",
        vault_root / "知识库" / "SCHEMA.md",
        vault_root / "系统中枢" / "地图与导航" / "MOC" / "index.md",
    ]

    seen: set[str] = set()
    result: list[Path] = []
    for p in targets:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if p.is_file():
                result.append(p)
        except OSError:
            continue
    return result


def build_name_index(vault_root: Path) -> dict[str, list[str]]:
    """文件名 → 路径列表（用于解析裸文件名引用，如 `SOUL.md` / `CLAUDE.md`）。

    覆盖 vault 与各工作区 / Agent home —— 活文档里的裸文件名可能指向其中任一处。
    """
    index: dict[str, list[str]] = {}
    roots = [
        vault_root,
        CODE_NEWS_ROOT,
        AGENT_WORK_ROOT,
        HOME_ROOT / ".codex",
        HOME_ROOT / ".claude",
        HOME_ROOT / ".hermes",
        HOME_ROOT / ".workbuddy-ai",
    ]
    for root in roots:
        try:
            for p in root.rglob("*.md"):
                if ".obsidian" in p.parts or "node_modules" in p.parts:
                    continue
                index.setdefault(p.name.lower(), []).append(str(p))
        except OSError:
            continue
    return index


def extract_refs(text: str) -> list[Ref]:
    """按行提取硬引用，跳过代码块（dataview 块只取 from）。"""
    refs: list[Ref] = []
    in_fence = False
    in_dataview = False

    for idx, line in enumerate(text.splitlines(), start=1):
        if IGNORE_MARK in line:
            continue

        fence = FENCE_RE.match(line)
        if fence:
            if not in_fence:
                in_fence = True
                in_dataview = fence.group(1).lower() == "dataview"
            else:
                in_fence = False
                in_dataview = False
            continue

        if in_fence:
            if in_dataview:
                for m in DATAVIEW_FROM_RE.finditer(line):
                    refs.append(Ref(idx, m.group(1)))
            continue

        for m in INLINE_CODE_RE.finditer(line):
            refs.append(Ref(idx, m.group(1)))
        for m in MD_LINK_RE.finditer(line):
            refs.append(Ref(idx, m.group(1)))
        at = AT_IMPORT_RE.match(line)
        if at:
            refs.append(Ref(idx, at.group(1)))

    return refs


def looks_like_path(ref: str) -> bool:
    """启发式判断一个引用是否「像路径」（过滤命令、说明、占位符）。"""
    ref = ref.strip().strip("`").strip()
    if not ref:
        return False
    if re.match(r"^(https?|mailto|ftp|file)://", ref, re.IGNORECASE):
        return False
    if any(ch in ref for ch in "*?{}<>|"):
        return False
    if any(ch in ref for ch in " \t"):
        return False
    if "$" in ref or "%" in ref or "=" in ref:
        return False
    if ref.startswith("#"):
        return False
    has_sep = ("/" in ref) or ("\\" in ref)
    is_md = ref.lower().endswith(".md")
    if not (has_sep or is_md):
        return False
    return True


def resolve_ref(
    ref: str,
    doc_dir: Path,
    roots: list[Path],
    prefix_map: dict[str, tuple[Path, bool]],
    name_index: dict[str, list[str]],
) -> tuple[str, str]:
    """解析引用为真实路径并检查存在性。返回 (status, 说明)。"""
    raw = ref.strip().strip("`").strip()
    raw = raw.split("#", 1)[0].strip()
    # 尾部行号不是路径的一部分（如 `file.py:56` / `file.py:56:3`）
    raw = re.sub(r":\d+(?::\d+)?$", "", raw).strip()
    if not raw:
        return SKIP, "empty"

    # 纯扩展名（如 ".md"）或模板占位（YYYY-MM-DD 等）不判错
    if re.fullmatch(r"\.\w+", raw):
        return SKIP, "纯扩展名"
    if TEMPLATE_RE.search(raw):
        return SKIP, "模板 / 占位路径"

    slash = raw.replace("\\", "/")

    # 0. WSL 专属路径（.dsh 在 WSL 内），Windows 侧无法确定性验证
    if slash.startswith("~/.dsh") or "/.dsh/" in slash or slash.endswith("/.dsh"):
        return SKIP, "WSL 路径（~/.dsh），Windows 侧无法验证"

    # 1. 绝对 Windows 路径
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        p = _localize_abs(raw)
        try:
            if p.exists():
                return OK, str(p)
        except OSError:
            pass
        # 盘符根下的 home 简写：C:\.codex -> C:\Users\Administrator\.codex
        m = re.match(r"^([A-Za-z]):[\\/](\.\S+)$", _to_local_sep(raw))
        if m:
            alt = HOME_ROOT / m.group(2)
            try:
                if alt.exists():
                    return OK, str(alt)
            except OSError:
                pass
        return MISSING, str(p)

    # 2. /mnt/ 挂载路径
    if raw.startswith("/mnt/"):
        if not IS_WINDOWS:
            p = Path(raw)
            try:
                return (OK if p.exists() else MISSING), str(p)
            except OSError:
                return MISSING, str(p)
        m = re.match(r"^/mnt/([A-Za-z])/(.*)$", raw)
        if m:
            p = Path(f"{m.group(1).upper()}:\\{m.group(2).replace('/', chr(92))}")
            try:
                return (OK if p.exists() else MISSING), str(p)
            except OSError:
                return MISSING, str(p)
        return SKIP, "无法解析 /mnt 路径"

    # 3. ~ 展开
    if raw.startswith("~"):
        rel = raw.lstrip("~").lstrip("/\\")
        p = HOME_ROOT / _to_local_sep(rel)
        try:
            return (OK if p.exists() else MISSING), str(p)
        except OSError:
            return MISSING, str(p)

    # 4. 已知根名前缀（code-news\... / 内容生产/... / wiki/...）
    first = slash.split("/")[0].lower()
    if first in prefix_map:
        root, keep_first = prefix_map[first]
        if keep_first:
            p = root / _to_local_sep(slash)
        else:
            parts = slash.split("/", 1)
            tail = parts[1] if len(parts) > 1 else ""
            p = root / _to_local_sep(tail)
        try:
            return (OK if p.exists() else MISSING), str(p)
        except OSError:
            return MISSING, str(p)

    # 5. ./ ../ 相对当前文档
    if slash.startswith("./") or slash.startswith("../"):
        p = (doc_dir / _to_local_sep(raw)).resolve()
        try:
            return (OK if p.exists() else MISSING), str(p)
        except OSError:
            return MISSING, str(p)

    # 6. 裸文件名（无分隔符，.md 结尾）→ 全库按文件名查找
    if ("/" not in raw) and ("\\" not in raw) and raw.lower().endswith(".md"):
        hits = name_index.get(raw.lower())
        if hits:
            return OK, hits[0]
        return MISSING, f"vault 内无同名文件: {raw}"

    # 7. 其它含分隔符的相对路径：试各候选根；全失败视为「片段」不判错
    if "/" in raw or "\\" in raw:
        for root in roots:
            p = root / _to_local_sep(raw)
            try:
                if p.exists():
                    return OK, str(p)
            except OSError:
                continue
        return SKIP, f"无法定位（疑似路径片段）: {raw}"

    return SKIP, "not a path"


def scan(
    targets: list[Path],
    roots: list[Path],
    prefix_map: dict[str, tuple[Path, bool]],
    name_index: dict[str, list[str]],
) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    total_refs = 0
    for doc in targets:
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if IGNORE_FILE_MARK in text:
            continue
        doc_dir = doc.parent
        for ref in extract_refs(text):
            if not looks_like_path(ref.text):
                continue
            total_refs += 1
            status, detail = resolve_ref(ref.text, doc_dir, roots, prefix_map, name_index)
            findings.append(
                Finding(doc=doc, line=ref.line, ref=ref.text.strip(), status=status, detail=detail)
            )
    return findings, total_refs


def rel(path: Path) -> str:
    for root in (VAULT_ROOT, CODE_NEWS_ROOT, AGENT_WORK_ROOT, HOME_ROOT):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def render_text(
    targets: list[Path], findings: list[Finding], total_refs: int, quiet: bool, show_skip: bool
) -> str:
    missing = [f for f in findings if f.status == MISSING]
    skipped = [f for f in findings if f.status == SKIP]
    ok_count = sum(1 for f in findings if f.status == OK)

    lines: list[str] = []
    if not quiet:
        lines.append("=== 文档引用一致性校验 (check_doc_references) ===")
        lines.append(f"扫描活文档 : {len(targets)}")
        lines.append(f"提取硬引用 : {total_refs}")
        lines.append(f"  OK       : {ok_count}")
        lines.append(f"  MISSING  : {len(missing)}")
        lines.append(f"  SKIP     : {len(skipped)}")
        lines.append("")

    if missing:
        lines.append(f"MISSING 明细（{len(missing)} 条，需修）:")
        for f in sorted(missing, key=lambda x: (str(x.doc), x.line)):
            lines.append(f"  {rel(f.doc)}:{f.line}  `{f.ref}`")
            if not quiet:
                lines.append(f"      -> {f.detail}")
    else:
        lines.append("无 MISSING 引用 —— 全部活文档路径引用有效。")

    if show_skip and skipped:
        lines.append("")
        lines.append(f"SKIP 明细（{len(skipped)} 条，无法确定性解析，不判错）:")
        for f in sorted(skipped, key=lambda x: (str(x.doc), x.line)):
            lines.append(f"  {rel(f.doc)}:{f.line}  `{f.ref}`  ({f.detail})")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="活文档路径引用一致性校验")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--quiet", action="store_true", help="仅输出汇总与 MISSING 明细")
    parser.add_argument("--show-skip", action="store_true", help="附 SKIP 明细")
    parser.add_argument("--list-targets", action="store_true", help="只列出将被扫描的文档")
    parser.add_argument("--root", default=None, help="覆盖 vault 根目录（测试用）")
    args = parser.parse_args()

    vault_root = Path(args.root) if args.root else VAULT_ROOT
    roots = candidate_roots(vault_root)
    prefix_map = known_prefix_map(vault_root)
    targets = default_targets(vault_root)

    if args.list_targets:
        for t in targets:
            print(rel(t))
        return

    name_index = build_name_index(vault_root)
    findings, total_refs = scan(targets, roots, prefix_map, name_index)
    missing = [f for f in findings if f.status == MISSING]
    skipped = [f for f in findings if f.status == SKIP]

    if args.format == "json":
        payload = {
            "vault_root": str(vault_root),
            "scanned_docs": len(targets),
            "total_refs": total_refs,
            "ok": sum(1 for f in findings if f.status == OK),
            "missing": len(missing),
            "skip": len(skipped),
            "findings": [
                {
                    "doc": str(f.doc),
                    "line": f.line,
                    "ref": f.ref,
                    "status": f.status,
                    "detail": f.detail,
                }
                for f in findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(targets, findings, total_refs, args.quiet, args.show_skip), end="")

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
