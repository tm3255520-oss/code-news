#!/usr/bin/env python3
"""gen_tool_archive.py -- 工具档案骨架生成器（skill / MCP 逐个建档）。

背景：本系统自研 + 装了不少 skill 与 MCP，工具一多就「分不清哪个是哪个」。
vault 侧 `系统中枢/系统skills以及MCP/` 是工具档案专区，约定每件工具一份档案，
写清四件事：干什么 / 怎么触发 / 结果落在哪里 / 花不花钱（再加依赖与故障）。

本脚本做机械部分，人工只补判读部分：
  - 从 SKILL.md 抽：名称、版本、作者、来源（复用每日清单的来源判定口径）、
    触发词、正文里出现的落盘路径、计费线索、被引用的依赖文件、故障小标题。
  - 从线别映射（config/tool_archive_lines.json）决定档案落到哪个子目录。
  - 写出档案骨架；已存在的档案默认不动（避免覆盖人工核验过的内容）。
  - 实体不可读的条目（符号链接等）退化为「仅登记」档案，元数据取自每日清单。

用法:
  python scripts/gen_tool_archive.py --manifest            # 打印清单 JSON
  python scripts/gen_tool_archive.py --manifest --out x.json
  python scripts/gen_tool_archive.py --write               # 缺失的档案补骨架
  python scripts/gen_tool_archive.py --write --force       # 连已有的也重写
  python scripts/gen_tool_archive.py --check               # 索引一致性体检

--check 的判定（任一不满足即退出码 1）：
  1. 线别映射里配了、但磁盘上找不到条目、也没能取到正文；
  2. 装了（含 `.archive/` 以外的全部在用 skill）、但线别映射没配的条目 → 会静默漏档；
  3. 配了却没生成档案文件的条目。

路径定位：与 check_doc_references.py 同一套平台自适应写法。**在 Linux 沙箱里
必须显式指定** `--vault-root` / `--skills-root`（或设 HERMES_VAULT_ROOT /
HERMES_SKILLS_ROOT 环境变量），否则默认的 Windows 盘符路径不可达，会扫出 0 条。

数据来源优先级：
  1. 工作区的 `SKILL.md` 直读；
  2. 读不到（符号链接指向挂载之外）→ `~/.hermes` git 仓库的 blob（`git show`）；
  3. 仍取不到 → `各Agent档案/hermes/Hermes Skills 与 MCP 清单.md`（该清单已知滞后，标注未核验）。
  4. 来源（自研/社区/内置/未知）默认调用 `generate_skills_mcp_inventory.py` 的
     `classify_source()`（单一事实来源，避免口径漂移），不可用时退化为轻量判定。

注意：`~/.hermes/skills/.archive/` 下的已退役 skill 不建档，只在专区 `_索引.md` 列名。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── 平台自适应（与 check_doc_references.py 同一套写法）──────────────────
IS_WINDOWS = os.name == "nt"


def _platform_root(win_path: str) -> Path:
    if IS_WINDOWS:
        return Path(win_path)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", win_path)
    if m:
        return Path("/mnt") / m.group(1).lower() / m.group(2).replace("\\", "/")
    return Path(win_path)


def _resolve(win_path: str, env_var: str) -> Path:
    """环境变量优先，其次平台映射。沙箱 / 非默认装机位置走环境变量覆盖。"""
    env = os.environ.get(env_var)
    return Path(env) if env else _platform_root(win_path)


CODE_NEWS_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = _resolve(r"D:\Obsidian Vault\obsidian Vault", "HERMES_VAULT_ROOT")
SKILLS_ROOT = _resolve(r"C:\Users\Administrator\.hermes\skills", "HERMES_SKILLS_ROOT")
HERMES_HOME = _resolve(r"C:\Users\Administrator\.hermes", "HERMES_HOME")
# 写进档案给人看的路径永远是 Windows 形式——档案不该出现沙箱/挂载路径
WIN_SKILLS_ROOT = r"C:\Users\Administrator\.hermes\skills"

ZONE_DIRNAME = "系统skills以及MCP"
LINES_CONFIG = CODE_NEWS_ROOT / "config" / "tool_archive_lines.json"
INVENTORY_DOC_REL = "系统中枢/各Agent档案/hermes/Hermes Skills 与 MCP 清单.md"

SOURCE_LABEL = {
    "builtin": "🏠 内置",
    "community": "📥 社区",
    "self": "🔧 自研",
    "unknown": "❓ 未知",
}
# 每日清单「来源」列 → 内部枚举
ICON_TO_KEY = {"内置": "builtin", "社区": "community", "自研": "self", "未知": "unknown"}

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ── 来源判定 ──────────────────────────────────────────────────────────
# 与 .hermes 脚本口径保持一致；拷一份降级实现只为在该脚本不可用时仍能跑。
HERMES_BUILTIN_PREFIXES = [
    "autonomous-ai-agents/", "hyperframes", "hermes-desktop-plugins", "hermes-themes",
    "embedded-captions", "faceless-explainer", "figma", "general-video", "media-use",
    "motion-graphics", "music-to-video", "pr-to-video", "product-launch-video",
    "remotion-to-hyperframes", "slideshow", "talking-head-recut", "website-to-video",
    "software-development/", "gaming/", "creative/baoyu", "creative/pixel-art",
    "mlops/research/dspy", "productivity/docx", "productivity/pdf", "productivity/xlsx",
    "productivity/tui-widgets", "productivity/response-style",
    "productivity/skill-reuse-policy",
]


def _load_classifier():
    """加载 ~/.hermes/scripts 的来源判定函数；失败返回 None（调用方走降级判定）。

    该脚本 `import vault_paths`（同目录），所以要把 scripts 目录临时挂上 sys.path。
    """
    scripts_dir = HERMES_HOME / "scripts"
    path = scripts_dir / "generate_skills_mcp_inventory.py"
    if not path.exists():
        return None
    import importlib.util

    added = False
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
        added = True
    try:
        spec = importlib.util.spec_from_file_location("_hermes_inventory", path)
        mod = importlib.util.module_from_spec(spec)
        # 注解解析需要模块已在 sys.modules 里
        sys.modules["_hermes_inventory"] = mod
        spec.loader.exec_module(mod)
        return getattr(mod, "classify_source", None)
    except Exception:
        return None
    finally:
        if added and sys.path and sys.path[0] == str(scripts_dir):
            sys.path.pop(0)


def classify(name: str, content: str, fn) -> str:
    if fn is not None:
        try:
            return fn(name, content)
        except Exception:
            pass
    # 降级：author 线索 → 内置前缀 → 用户专属路径 → unknown
    m = re.search(r"^author:\s*(.+)$", content, re.M)
    author = m.group(1) if m else ""
    if "老廖" in author:
        return "self"
    for p in HERMES_BUILTIN_PREFIXES:
        if name.startswith(p):
            return "builtin"
    if re.search(r"(Obsidian Vault|Users\\\\Administrator|老廖聊AI|bsk|Profile 2)", content):
        return "self"
    if author:
        return "community"
    return "unknown"


# ── 每日清单（不可读条目的元数据来源）──────────────────────────────────
INV_ROW = re.compile(
    r"^\|\s*\*\*(?P<name>[^|*]+?)\*\*\s*\|\s*(?P<src>[^|]+?)\s*\|\s*(?P<ver>[^|]*?)\s*"
    r"\|\s*(?P<inst>[^|]*?)\s*\|\s*(?P<upd>[^|]*?)\s*\|[^|]*\|\s*(?P<desc>.*?)\s*\|\s*$",
    re.M,
)


def load_inventory() -> dict[str, dict]:
    """解析每日清单的 Skills 表：名称 → 来源/版本/安装/更新/功能节录。"""
    doc = VAULT_ROOT / INVENTORY_DOC_REL
    rows: dict[str, dict] = {}
    try:
        text = doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for m in INV_ROW.finditer(text):
        name = m.group("name").strip()
        if name in ("Skill 名称", "服务名称") or name.startswith("-"):
            continue
        icon = m.group("src").strip()
        src = "unknown"
        for k, v in ICON_TO_KEY.items():
            if k in icon:
                src = v
                break
        rows[name] = {
            "source": src,
            "version": m.group("ver").strip(),
            "installed": m.group("inst").strip(),
            "updated": m.group("upd").strip(),
            "description": re.sub(r"\s+", " ", m.group("desc")).strip(),
        }
    return rows


# ── git 兜底：符号链接的 skill 目录在部分环境下不可读 ────────────────────
# ~/.hermes 自带 git 仓库（cron 自动提交），blob 里存着这些 SKILL.md 的正文，
# 即使工作区的符号链接指到挂载之外也能取回，避免档案只剩一个名字。
def _git(*argv: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(HERMES_HOME), *argv],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def git_show_skill(key: str) -> str:
    return _git("show", f"HEAD:skills/{key}/SKILL.md")


def git_file_count(key: str) -> int:
    out = _git("ls-tree", "-r", "--name-only", f"HEAD:skills/{key}")
    return len([ln for ln in out.splitlines() if ln.strip()]) if out else 0


# ── MCP 注册表（活配置，比清单更新）──────────────────────────────────
def load_mcp_servers() -> dict[str, dict]:
    """解析 ~/.hermes/config.yaml 的 mcp_servers 段（只取 command/enabled）。"""
    cfg = HERMES_HOME / "config.yaml"
    out: dict[str, dict] = {}
    try:
        lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    in_block = False
    cur: str | None = None
    for line in lines:
        if not in_block:
            if re.match(r"^mcp_servers:\s*$", line):
                in_block = True
            continue
        if line and not line[0].isspace():
            break
        m2 = re.match(r"^  (\S+):\s*$", line)
        if m2:
            cur = m2.group(1)
            out[cur] = {"command": "", "enabled": ""}
            continue
        m3 = re.match(r"^    (command|enabled):\s*(.*)$", line)
        if m3 and cur:
            out[cur][m3.group(1)] = m3.group(2).strip()
    return out


# ── 抽取 ──────────────────────────────────────────────────────────────
BACKTICK_PATH = re.compile(r"`([^`\n]+)`")
# 落盘类路径线索（只认"结果目录"特征，避免把源码路径算成产出）
OUT_HINT_WORDS = (
    "知识库", "内容生产", "情报与选题", "素材候选", "参考库", "选题与题材", "配图",
    "产出库", "运营知识", "待同步vault", "抖音", "小红书", "头条",
)
OUT_HINTS = re.compile("|".join(OUT_HINT_WORDS) + r"|raw[/\\]|\.hermes[/\\](?:output|tmp)|agent-work[/\\]")
# 非反引号包裹的裸路径也要认（含 / 或 \ 且带目录特征）
BARE_PATH = re.compile(
    r"[A-Za-z0-9_一-鿿.\\/-]*(?:" + "|".join(OUT_HINT_WORDS) + r")[A-Za-z0-9_一-鿿.\\/-]*"
)
DEP_FILE = re.compile(
    r"((?:~|/mnt/c/Users/Administrator)?"
    r"\.hermes[/\\][\w./\\-]*\.(?:py|json|yaml|bat|cmd|md)|"
    r"scripts[/\\][\w./\\-]*\.(?:py|bat|cmd)|"
    r"\.env)"
)
# 前四条是强证据，最后一条 token/额度 太容易误报 → 标为弱线索
BILLING = [
    (r"RedFox|红狐|积分", "按次计费（RedFox 通道）"),
    (r"NVIDIA|NIM|英伟达", "消耗外部模型额度（NVIDIA NIM）"),
    (r"Agnes|智谱|火山|OpenAI|Gemini|Claude API", "消耗外部模型额度（API Key）"),
    (r"whisper|ffmpeg|本地模型|本地引擎|edge-tts", "本地可跑，不额外计费"),
    (r"token|额度|限流|计费", "（弱线索）正文出现过 token/额度 字样，是否计费待人工确认"),
]
# 触发线索：先看正文的小节，再看 description 里的触发句
TRIGGER_HEAD = re.compile(
    r"(?:^|\n)#{1,4}\s*[^\n]*(?:触发|何时用|何时触发|使用时机|When to use|Triggers?)\s*\n"
    r"((?:\s*(?:[-*+]|\d+[.、)])\s*[^\n]+\n?)+)",
    re.I,
)
DESC_MARKERS = ("触发词：", "触发词:", "触发：", "触发:", "Load when", "Load for",
                "Use when", "When to use", "Triggers:")
FAULT_HEAD = re.compile(
    r"^\s*#{2,4}\s*(.*?(?:故障|排查|常见错误|常见问题|常见坑|坑|Troubleshoot|"
    r"Common (?:failure|issue)|Pitfall)[^\n]*)$",
    re.I | re.M,
)
FAULT_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s*([^\n]{4,120})$", re.M)


def _find_triggers(desc: str, text: str) -> list[str]:
    m = TRIGGER_HEAD.search(text)
    if m:
        items = [
            re.sub(r"\s+", " ", ln.lstrip("-*+ ").strip())
            for ln in m.group(1).splitlines()
            if ln.strip()
        ]
        items = [i for i in items if i]
        if items:
            return items[:4]
    # description 里的触发句：从某个标记切到句末，避免把整段描述吞进来
    hay = desc or text[:800]
    for marker in DESC_MARKERS:
        idx = hay.find(marker)
        if idx < 0:
            continue
        frag = hay[idx:]  # 连标记一起留，读起来才是完整句子（Use when given a URL…）
        frag = re.split(r"(?<=[。；;．!?！？])|\n|(?:Do not|不要)", frag, maxsplit=1)[0]
        frag = frag.strip(" ：:，,、-*")
        if len(frag) >= 4:
            return [frag[:180]]
    # 兜底：description 本身常就是「什么时候用」。短描述整条留用（触发条件常在后半句，
    # 只截首句会把「…时用」这类关键条件切掉），长的才截。
    flat = re.sub(r"\s+", " ", hay.strip())
    if len(flat) >= 8:
        return [f"（推断自 description）{flat[:180]}"]
    return []


def _extract(text: str, desc: str = "") -> dict:
    """从 SKILL.md 正文抽触发词 / 落盘路径 / 依赖 / 计费 / 故障。"""
    outs: list[str] = []
    for rx in (BACKTICK_PATH.finditer(text), BARE_PATH.finditer(text)):
        for m in rx:
            ref = (m.group(1) if m.re is BACKTICK_PATH else m.group(0)).strip()
            if not ref or not OUT_HINTS.search(ref):
                continue
            if not re.search(r"[/\\]", ref):  # 必须像路径，不是光一个词
                continue
            if len(ref) > 120 or ref in outs:
                continue
            outs.append(ref)

    deps: list[str] = []
    for m in DEP_FILE.finditer(text):
        d = m.group(1).strip()
        if d not in deps:
            deps.append(d)

    billing = [label for pat, label in BILLING if re.search(pat, text)]

    faults: list[str] = []
    for m in FAULT_HEAD.finditer(text):
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        tail = text[m.end():m.end() + 400]
        bullet = FAULT_BULLET.search(tail)
        entry = title if not bullet else f"{title} → {bullet.group(1).strip()}"
        if entry not in faults:
            faults.append(entry)

    return dict(
        triggers=_find_triggers(desc, text),
        outputs=outs[:6],
        deps=deps[:10],
        billing=billing,
        faults=faults[:6],
    )


@dataclass
class Tool:
    key: str            # 映射表里的键（skill 相对路径 / mcp:<名>）
    kind: str           # skill | mcp
    line: str           # 线别
    name: str           # 展示名
    source: str = "unknown"
    version: str = ""
    author: str = ""
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    deps: list[str] = field(default_factory=list)
    billing: list[str] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    path: str = ""      # 真实路径（读盘用）
    display: str = ""   # 写进档案给人看的路径（Windows 形式）
    readable: bool = False
    installed: str = ""
    updated: str = ""
    line_count: int = 0
    file_count: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def archive_name(self) -> str:
        return self.key.removeprefix("mcp:").split("/")[-1].replace(":", "-") + ".md"


def _frontmatter(text: str) -> dict:
    """极简 frontmatter 解析；`description: >` / `|` 这类块标量按缩进收拢成一行。"""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    fm: dict[str, str] = {}
    if not m:
        return fm
    lines = m.group(1).split("\n")
    i = 0
    while i < len(lines):
        mm = re.match(r"^([\w-]+):\s*(.*)$", lines[i])
        if mm:
            key, val = mm.group(1), mm.group(2).strip()
            if val in (">", "|", ">-", "|-", ">+", "|+", ""):
                buf, j = [], i + 1
                while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t")):
                    buf.append(lines[j].strip())
                    j += 1
                val = " ".join(x for x in buf if x)
                fm[key] = val.strip().strip('"').strip("'")
                i = j  # 直接跳到块结束处，别再多加一行（会吃掉紧邻的普通键）
                continue
            fm[key] = val.strip().strip('"').strip("'")
        i += 1
    return fm


def _clean_desc(raw: str) -> str:
    if raw in (">", "|", ">-", "|-", ">+", "|+"):
        return ""
    return re.sub(r"\s+", " ", raw).strip(" \"'")


def _build_skill(key: str, line: str, inv: dict[str, dict], classify_fn) -> Tool:
    t = Tool(key=key, kind="skill", line=line, name=key.split("/")[-1])
    skill_md = SKILLS_ROOT / key / "SKILL.md"
    t.path = str(skill_md)
    t.display = WIN_SKILLS_ROOT + "\\" + key.replace("/", "\\") + "\\SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        t.readable = True
    except OSError:
        text = ""
        t.readable = False

    if not text:
        # 工作区里读不到（符号链接指向挂载之外等）→ 回落到 .hermes 自带 git 的 blob
        text = git_show_skill(key)
        if text:
            t.notes.append(
                "该目录在本机工作区里是符号链接，直读不到；正文取自 `~/.hermes` git 仓库，内容一致。"
            )

    if text:
        fm = _frontmatter(text)
        t.version = fm.get("version", "")
        t.author = fm.get("author", "")
        t.description = _clean_desc(fm.get("description", ""))
        t.source = classify(key, text, classify_fn)
        t.line_count = len(text.splitlines())
        for k, v in _extract(text, t.description).items():
            setattr(t, k, v)
        if t.readable:
            try:
                st = skill_md.stat()
                t.installed = datetime.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d")
                t.updated = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            except OSError:
                pass
        else:
            last = _git("log", "-1", "--format=%cs", "--", f"skills/{key}").strip()
            if last:
                t.updated = last
    if not t.description:
        # 兜底：元数据取每日清单（该清单已知滞后，标注未核验）
        row = inv.get(key, {})
        t.source = t.source if t.source != "unknown" else row.get("source", "unknown")
        t.version = t.version or row.get("version", "")
        t.installed = t.installed or row.get("installed", "")
        t.updated = t.updated or row.get("updated", "")
        t.description = row.get("description", "")
        if t.description:
            t.notes.append("本档元数据取自每日清单，未逐字核验。")

    try:
        t.file_count = sum(1 for p in (SKILLS_ROOT / key).rglob("*") if p.is_file())
    except OSError:
        t.file_count = 0
    if t.file_count == 0:
        t.file_count = git_file_count(key)
    return t


# config.yaml 里注册名与 skill 目录名不完全一致（如 toolkit ↔ toolkit-mcp）
MCP_NAME_ALIASES = {"toolkit-mcp": "toolkit"}


def _build_mcp(key: str, line: str, servers: dict[str, dict]) -> Tool:
    name = key[4:]
    t = Tool(key=key, kind="mcp", line=line, name=name)
    reg = servers.get(name) or servers.get(MCP_NAME_ALIASES.get(name, ""))
    if reg:
        t.readable = True
        t.path = reg.get("command", "")
        t.description = (
            f"本地 MCP 服务器，注册在 `~/.hermes/config.yaml` 的 `mcp_servers` 段，"
            f"启动命令 `{t.path}`，enabled={reg.get('enabled', '?')}。"
        )
    else:
        t.readable = False
        t.path = "（未在 config.yaml 注册）"
        t.description = (
            "MCP 服务器源码存在，但**未注册**到 `~/.hermes/config.yaml` 的 `mcp_servers` 段，"
            "当前不会被任何会话加载。"
        )
        t.notes.append(
            "源码与 .cmd 启动脚本在 `code-news/scripts/` 下，但 config.yaml 里没有此条目 → 尚未启用。"
        )
    return t


def build_tools() -> list[Tool]:
    cfg = json.loads(LINES_CONFIG.read_text(encoding="utf-8"))
    classify_fn = _load_classifier()
    inv = load_inventory()
    servers = load_mcp_servers()
    tools: list[Tool] = []
    for line, keys in cfg.items():
        if line.startswith("_"):
            continue
        for key in keys:
            if key.startswith("mcp:"):
                tools.append(_build_mcp(key, line, servers))
            else:
                tools.append(_build_skill(key, line, inv, classify_fn))
    return tools


# ── 渲染 ──────────────────────────────────────────────────────────────
def render(t: Tool) -> str:
    kind_label = "MCP 服务器" if t.kind == "mcp" else "skill"
    src = SOURCE_LABEL.get(t.source, t.source)

    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items)

    trig = t.triggers or ["（正文未写触发条件，待补：手动调用 / 自动触发 / 由谁调用）"]
    outs = t.outputs or ["（正文未声明落盘路径，待补；若无产出写「无文件产出」）"]
    bill = t.billing or ["（正文未提及计费，默认不额外计费；如走按次通道请补）"]
    dep = t.deps or ["（未扫到显式依赖文件）"]
    fault = t.faults or ["（正文未写故障小节）"]

    if t.kind == "skill":
        loc_label = "主文件"
        meta_line = f"（{t.line_count} 行，目录内 {t.file_count} 个文件）"
        status = "自动生成（待人工核验）"
    else:
        loc_label = "注册状态"
        if t.readable:
            meta_line = ""
            status = "自动生成（待人工核验）"
        else:
            meta_line = ""
            status = "未启用（源码在，未注册）"
    desc_suffix = " *（节录自每日清单，待核）*" if any("每日清单" in n for n in t.notes) else ""

    note_block = ""
    if t.notes:
        note_block = "\n## 附注\n\n" + bullets(t.notes) + "\n"

    shown = t.display or t.path
    return f"""---
title: {t.name}
类型: 工具档案
kind: {kind_label}
来源: {t.source}
线别: {t.line}
路径: {shown}
status: {status}
date: 2026-09-27
tags: [工具档案, {kind_label}, {t.line}]
---

# {t.name}

> {src} · {kind_label} · 线别「{t.line}」 · 版本 {t.version or "—"} · 作者 {t.author or "—"}
> {loc_label}：`{shown}`{meta_line}
> 登记：{t.installed or "—"} · 更新：{t.updated or "—"}

## 一、干什么

{t.description or "（正文未提供一句话描述，待补）"}{desc_suffix}

## 二、怎么触发

{bullets(trig)}

## 三、结果落在哪里

{bullets(outs)}

## 四、花不花钱

{bullets(bill)}

## 五、依赖了什么

{bullets(dep)}

## 六、故障与排查

{bullets(fault)}

## 七、与同类工具的区别（别用错）

- （待补：同线别里最容易混的是哪个？各自适用场景怎么分？）

{note_block}
---
*骨架由 `code-news/scripts/gen_tool_archive.py` 生成；判读部分是否已人工核验，以文首 `status` 为准。
生成依据：`{shown}`。*
"""


def manifest(tools: list[Tool]) -> dict:
    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "vault_root": str(VAULT_ROOT),
        "zone": str(VAULT_ROOT / "系统中枢" / ZONE_DIRNAME),
        "skills_root": str(SKILLS_ROOT),
        "counts": {
            "total": len(tools),
            "skill": sum(1 for t in tools if t.kind == "skill"),
            "mcp": sum(1 for t in tools if t.kind == "mcp"),
            "readable": sum(1 for t in tools if t.readable),
            "by_line": {line: sum(1 for t in tools if t.line == line) for line in dict.fromkeys(t.line for t in tools)},
            "by_source": {
                s: sum(1 for t in tools if t.source == s)
                for s in ("self", "community", "builtin", "unknown")
            },
        },
        "tools": [
            {
                "key": t.key, "name": t.name, "kind": t.kind, "line": t.line,
                "source": t.source, "version": t.version, "author": t.author,
                "path": t.path, "display": t.display or t.path,
                "readable": t.readable, "archive": t.archive_name,
                "description": t.description, "triggers": t.triggers,
                "outputs": t.outputs, "billing": t.billing, "deps": t.deps,
                "faults": t.faults, "line_count": t.line_count,
                "file_count": t.file_count, "notes": t.notes,
            }
            for t in tools
        ],
    }


def write_archives(tools: list[Tool], force: bool) -> tuple[int, int]:
    zone = VAULT_ROOT / "系统中枢" / ZONE_DIRNAME
    created = skipped = 0
    for t in tools:
        d = zone / t.line
        d.mkdir(parents=True, exist_ok=True)
        f = d / t.archive_name
        if f.exists() and not force:
            skipped += 1
            continue
        f.write_text(render(t), encoding="utf-8")
        created += 1
    return created, skipped


INDEX_BEGIN = "<!-- index:begin（本段由 gen_tool_archive.py --index 生成，勿手改）-->"
INDEX_END = "<!-- index:end -->"


def _one_liner(body: str) -> str:
    """从档案的「一、干什么」里取一句话，供索引表用。"""
    m = re.search(r"^##\s*一、干什么\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    if not m:
        return "—"
    text = " ".join(x.strip() for x in m.group(1).splitlines() if x.strip())
    text = re.sub(r"[*`>]", "", text)
    if not text:
        return "—"
    cut = text.find("。")
    if 0 < cut < 90:
        return text[: cut + 1]
    return text[:88] + ("…" if len(text) > 88 else "")


def _index_rows() -> tuple[dict[str, list[tuple[str, str, str]]], list[str]]:
    """扫专区内已生成的档案，按线别收成索引行；另收 `~/.hermes/skills/.archive/` 的退役清单。"""
    zone = VAULT_ROOT / "系统中枢" / ZONE_DIRNAME
    lines: dict[str, list[tuple[str, str, str]]] = {}
    for d in sorted(p for p in zone.iterdir() if p.is_dir()) if zone.exists() else []:
        rows = []
        for f in sorted(d.glob("*.md")):
            body = f.read_text(encoding="utf-8")
            name = f.stem
            src = (re.search(r"^来源:\s*(\S+)", body, re.M) or [None, "unknown"])[1]
            rows.append((name, src, _one_liner(body)))
        if rows:
            lines[d.name] = rows

    retired: set[str] = set()
    arch = SKILLS_ROOT / ".archive"
    if arch.exists():
        try:
            retired = {p.parent.name for p in arch.rglob("SKILL.md")}
        except OSError:
            pass
    for ln in _git("ls-files", "skills/.archive/*SKILL.md").splitlines():
        parts = ln.split("/")
        if len(parts) >= 4:
            retired.add(parts[2])
    return lines, sorted(retired)


def render_index() -> str:
    lines, retired = _index_rows()
    total = sum(len(v) for v in lines.values())
    out = [INDEX_BEGIN, ""]
    out.append(f"**当前收录 {total} 件**——skill {total - len(lines.get('MCP', []))} 件 + MCP {len(lines.get('MCP', []))} 件，"
               f"分 {len(lines)} 条线别。完整字段（怎么触发 / 结果落在哪里 / 花不花钱 / 依赖 / 故障 / 与同类工具的区别）见各档案正文。")
    out.append("")
    for line, rows in lines.items():
        out.append(f"### {line}（{len(rows)}）")
        out.append("")
        out.append("| 工具 | 来源 | 一句话 |")
        out.append("|---|---|---|")
        for name, src, one in rows:
            link = f"[[系统中枢/{ZONE_DIRNAME}/{line}/{name}\\|{name}]]"
            out.append(f"| {link} | {src} | {one} |")
        out.append("")
    out.append(f"### 已退役、不单独建档（{len(retired)}）")
    out.append("")
    out.append("下列 skill 已移入 `~/.hermes/skills/.archive/`，仍能触发但不再是主实现；"
               "其中 `key-registry-maintenance` 是密钥登记的**唯一主实现**（由 4 个旧入口桩合并而来）。")
    out.append("")
    out.append("　".join(retired) if retired else "（无）")
    out.append("")
    out.append(INDEX_END)
    return "\n".join(out)


def update_index() -> int:
    f = VAULT_ROOT / "系统中枢" / ZONE_DIRNAME / "_索引.md"
    if not f.exists():
        print(f"找不到 {f}，请先建索引页并放入 {INDEX_BEGIN} / {INDEX_END} 两个标记。")
        return 1
    text = f.read_text(encoding="utf-8")
    i, j = text.find(INDEX_BEGIN), text.find(INDEX_END)
    if i < 0 or j < 0:
        print(f"{f.name} 里没有 index:begin / index:end 标记，无法只替换表格段。")
        return 1
    new = text[:i] + render_index() + text[j + len(INDEX_END):]
    f.write_text(new, encoding="utf-8")
    lines, retired = _index_rows()
    print(f"索引已更新：{sum(len(v) for v in lines.values())} 件工具、{len(lines)} 条线别、{len(retired)} 件退役。")
    return 0


def check(tools: list[Tool]) -> list[str]:
    zone = VAULT_ROOT / "系统中枢" / ZONE_DIRNAME
    problems: list[str] = []
    for t in tools:
        if t.kind == "skill" and not t.readable and not t.description:
            problems.append(f"映射配了但磁盘上找不到，也没取到正文：{t.key}")
        if not (zone / t.line / t.archive_name).exists():
            problems.append(f"未生成档案：{t.line}/{t.archive_name}")
    # 装了但映射没配 → 会静默漏档。排除 .archive/（已退役，不建档）。
    known = {t.key for t in tools}
    if SKILLS_ROOT.exists():
        found: set[str] = set()
        try:
            for p in SKILLS_ROOT.rglob("SKILL.md"):
                if p.parent == SKILLS_ROOT:
                    continue
                rel = p.parent.relative_to(SKILLS_ROOT).as_posix()
                if not rel.startswith(".archive/"):
                    found.add(rel)
        except OSError:
            pass
        # 符号链接目录 os.walk / rglob 不跟随，用 git 索引补齐
        for ln in _git("ls-files", "skills/*SKILL.md").splitlines():
            if ln.endswith("/SKILL.md"):
                rel = ln[len("skills/"):-len("/SKILL.md")]
                if not rel.startswith(".archive/"):
                    found.add(rel)
        for name in sorted(found - known):
            problems.append(f"装了但线别映射没配（会静默漏档）：{name}")
    return problems


def main() -> None:
    global VAULT_ROOT, SKILLS_ROOT, HERMES_HOME
    ap = argparse.ArgumentParser(description="工具档案骨架生成器")
    ap.add_argument("--manifest", action="store_true", help="输出清单 JSON")
    ap.add_argument("--out", default=None, help="--manifest 的输出文件")
    ap.add_argument("--write", action="store_true", help="生成缺失的档案骨架")
    ap.add_argument("--force", action="store_true", help="连已存在的档案也重写")
    ap.add_argument("--check", action="store_true", help="索引一致性体检")
    ap.add_argument("--index", action="store_true", help="只重建 _索引.md 的表格段（保留散文）")
    ap.add_argument("--vault-root", default=None, help="vault 根（沙箱内必须显式传）")
    ap.add_argument("--skills-root", default=None, help="~/.hermes/skills 路径")
    args = ap.parse_args()

    if args.vault_root:
        VAULT_ROOT = Path(args.vault_root)
    if args.skills_root:
        HERMES_HOME = Path(args.skills_root).parent
        SKILLS_ROOT = Path(args.skills_root)

    if args.index:
        # 索引只扫已生成的档案，不需要重读 skill 源文件
        sys.exit(update_index())

    tools = build_tools()

    if args.manifest:
        payload = json.dumps(manifest(tools), ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(payload, encoding="utf-8")
            print(f"清单已写入 {args.out}（{len(tools)} 条）")
        else:
            print(payload)
        return

    if args.write:
        created, skipped = write_archives(tools, args.force)
        print(f"新增档案 {created} 份，跳过已存在 {skipped} 份，共 {len(tools)} 条")

    if args.check:
        problems = check(tools)
        if problems:
            print(f"体检不通过：{len(problems)} 项")
            for p in problems:
                print("  - " + p)
            sys.exit(1)
        print(f"体检通过：{len(tools)} 条工具，档案与映射一一对应。")

    if not (args.manifest or args.write or args.check):
        ap.print_help()


if __name__ == "__main__":
    main()
