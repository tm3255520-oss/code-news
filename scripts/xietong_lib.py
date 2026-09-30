#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xietong_lib.py — 协同三件套的共享读写库（确定性、零 LLM）。

三件套（见 vault `系统中枢/协同/_使用说明.md`）：
    任务台账.md            一行一任务（任务ID/标题/平台/负责人/状态/最后更新/产出路径/关联会话）
    交接/<任务ID>.md       追加式交接块（8 字段）
    会话索引/<agent>.jsonl 一行一条（结论 + 指针，不搬对话原文）

为什么要这个库：`work_lookup.py`（开工三查）/ `handoff_append.py`（收工三写）/
`xietong_audit.py`（巡检）/ `xietong_weekly.py`（周报）四个入口必须用**同一套解析**，
否则「查到的」和「写进去的」会漂移。

设计纪律：
    - 只读解析不修改任何文件；写操作只在显式调用 append_*/update_ledger_row 时发生。
    - 台账只改自己那一行（协调协议），跨 Agent 改动需显式 force + 留痕。
    - 拒绝写入疑似密钥（与 `memory_governance_audit.py` 同一类判据）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------- 常量

STATUSES = ("待认领", "进行中", "待审", "已完成", "暂停", "归档")
ACTIVE_STATUSES = ("进行中", "待审")
LEDGER_NAME = "任务台账.md"
HANDOFF_DIR = "交接"
INDEX_DIR = "会话索引"
TEMPLATE_NAME = "_模板.md"

COLUMNS = ("任务ID", "标题", "平台/形态", "负责人", "状态", "最后更新", "产出路径", "关联会话/交接")
PLACEHOLDER = "—"

TASK_ID_RE = re.compile(r"^WK-\d{8}-\d{2}$")
BLOCK_HEAD_RE = re.compile(r"^##\s+(\S+)\s*\|\s*([A-Za-z0-9_\-]+)\s*\|\s*(WK-\d{8}-\d{2})\s*$")
BLOCK_FIELDS = ("本轮做了什么", "动了哪些文件", "证据", "未决问题", "下一步",
                "建议接手方 + 该调的 skill", "状态")
FIELD_RE = re.compile(r"^-\s*(" + "|".join(re.escape(f) for f in BLOCK_FIELDS) + r")\s*[:：]\s*(.*)$")

_WIN_ROOT = Path(r"D:\Obsidian Vault\obsidian Vault\系统中枢\协同")
_WSL_ROOT = Path("/mnt/d/Obsidian Vault/obsidian Vault/系统中枢/协同")

SECRET_RE = re.compile(
    r"(?i)(appsecret|secret|token|api[_-]?key|password|passwd)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{12,}"
)

STOPWORDS = {
    "科普", "视频", "文章", "内容", "平台", "深度", "改编", "同题", "第", "版", "篇",
    "the", "and", "for", "with", "from", "http", "https",
}


# ---------------------------------------------------------------- 根目录

def resolve_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """解析协同根目录：显式参数 > 环境变量 XIETONG_ROOT > vault_paths > 平台默认。

    同时支持 Windows 口径（D:\\...）与 WSL 口径（/mnt/d/...），按存在性择一。
    """
    if explicit:
        return Path(explicit)
    env = os.environ.get("XIETONG_ROOT")
    if env:
        return Path(env)
    try:  # 与 Hermes 侧脚本共用路径事实源（不存在时不强依赖）
        hermes_scripts = Path(r"C:\Users\Administrator\.hermes\scripts")
        if hermes_scripts.is_dir():
            sys.path.insert(0, str(hermes_scripts))
        from vault_paths import VAULT  # type: ignore  # noqa: PLC0415

        candidate = Path(VAULT) / "系统中枢" / "协同"
        if candidate.is_dir():
            return candidate
    except Exception:  # noqa: BLE001
        pass
    for candidate in (_WIN_ROOT, _WSL_ROOT):
        if candidate.is_dir():
            return candidate
    return _WIN_ROOT


def ledger_path(root: Path) -> Path:
    return Path(root) / LEDGER_NAME


def handoff_path(root: Path, task_id: str) -> Path:
    return Path(root) / HANDOFF_DIR / f"{task_id}.md"


def index_path(root: Path, agent: str) -> Path:
    return Path(root) / INDEX_DIR / f"{agent}.jsonl"


# ---------------------------------------------------------------- 基础解析

def parse_ts(text: str) -> datetime | None:
    """接受 `YYYY-MM-DD HH:MM` / `YYYY-MM-DDTHH:MM(:SS)?` / `YYYY-MM-DD`。"""
    raw = (text or "").strip().strip("`")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def split_row(line: str) -> list[str]:
    """按未转义竖线切分 Markdown 表格行（转义 `\\|` 不算分隔符）。"""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells, buf, i = [], [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def clean_cell(text: str) -> str:
    return (text or "").strip().strip("`").strip()


def tokens(text: str) -> set[str]:
    """用于重复检测的粗粒度词元：连续中文 ≥2 字，或 ≥3 位字母数字。"""
    raw = re.findall(r"[A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}", text or "")
    out = set()
    for tok in raw:
        low = tok.lower()
        if low in STOPWORDS or tok in STOPWORDS:
            continue
        out.add(low)
    return out


def contains_secret(text: str) -> bool:
    return bool(SECRET_RE.search(text or ""))


# ---------------------------------------------------------------- 台账

@dataclass
class Task:
    task_id: str
    title: str = ""
    platform: str = ""
    owner: str = ""
    status: str = ""
    updated: str = ""
    artifact: str = ""
    link: str = ""
    line_no: int = 0

    @property
    def updated_at(self) -> datetime | None:
        return parse_ts(self.updated)

    def cells(self) -> list[str]:
        return [self.task_id, self.title, self.platform, self.owner, self.status,
                self.updated, self.artifact, self.link]

    def render(self) -> str:
        return "| " + " | ".join(self.cells()) + " |"


@dataclass
class Ledger:
    path: Path
    tasks: list[Task] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def by_id(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None


def parse_ledger(path: Path) -> Ledger:
    path = Path(path)
    led = Ledger(path=path)
    if not path.is_file():
        led.problems.append(f"台账不存在: {path}")
        return led
    text = path.read_text(encoding="utf-8")
    led.lines = text.splitlines()
    header_seen = False
    for no, line in enumerate(led.lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_row(stripped)
        if len(cells) < 2:
            continue
        first = clean_cell(cells[0])
        if first == COLUMNS[0]:
            header_seen = True
            if len(cells) != len(COLUMNS):
                led.problems.append(f"L{no} 表头列数 {len(cells)} != {len(COLUMNS)}")
            continue
        if set(first) <= set("-: "):  # 分隔行
            continue
        if not TASK_ID_RE.match(first):
            continue
        if len(cells) != len(COLUMNS):
            led.problems.append(f"L{no} 任务行 {first} 列数 {len(cells)} != {len(COLUMNS)}")
            continue
        task = Task(
            task_id=first,
            title=clean_cell(cells[1]),
            platform=clean_cell(cells[2]),
            owner=clean_cell(cells[3]),
            status=clean_cell(cells[4]),
            updated=clean_cell(cells[5]),
            artifact=clean_cell(cells[6]),
            link=clean_cell(cells[7]),
            line_no=no,
        )
        led.tasks.append(task)
    if not header_seen:
        led.problems.append("台账缺少表头行（| 任务ID | ... |）")
    seen: dict[str, int] = {}
    for t in led.tasks:
        if t.task_id in seen:
            led.problems.append(f"任务ID 重复: {t.task_id}（L{seen[t.task_id]} / L{t.line_no}）")
        seen[t.task_id] = t.line_no
    return led


def update_ledger_row(led: Ledger, task: Task, *, force: bool = False,
                      force_reason: str = "", change_log: str = "") -> None:
    """只替换目标任务那一行；force 时在「变更记录」表追加一行留痕。"""
    if task.line_no <= 0:
        raise ValueError(f"任务 {task.task_id} 没有可定位的行号")
    led.lines[task.line_no - 1] = task.render()
    if force:
        if not force_reason:
            raise ValueError("force 必须带 force_reason")
        entry = f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {change_log or task.owner} | 改 {task.task_id} | {force_reason} |"
        insert_at = None
        for i, line in enumerate(led.lines):
            if line.strip().startswith("## 变更记录"):
                for j in range(i + 1, len(led.lines)):
                    if led.lines[j].strip().startswith("|"):
                        insert_at = j + 1
                break
        if insert_at is None:
            led.lines.extend(["", "## 变更记录（跨 Agent 改动他人行时必写）", "",
                              "| 时间 | 谁 | 改了哪行 | 原因 |", "|---|---|---|---|"])
            insert_at = len(led.lines)
        led.lines.insert(insert_at, entry)
    led.path.write_text("\n".join(led.lines) + "\n", encoding="utf-8")


def append_ledger_row(led: Ledger, task: Task) -> None:
    """在台账最后一条任务行之后插入新行。"""
    last = max((t.line_no for t in led.tasks), default=0)
    if last <= 0:
        anchor = None
        for i, line in enumerate(led.lines):
            if line.strip().startswith(f"| {COLUMNS[0]}"):
                anchor = i + 2  # 表头 + 分隔行
                break
        if anchor is None:
            raise ValueError("台账结构异常：找不到表头，无法追加行")
        led.lines.insert(anchor, task.render())
    else:
        led.lines.insert(last, task.render())
    led.path.write_text("\n".join(led.lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 交接文件

@dataclass
class Block:
    ts: str
    agent: str
    task_id: str
    fields: dict[str, str]
    line_no: int

    def field(self, name: str) -> str:
        return self.fields.get(name, "")

    def render(self) -> str:
        head = f"## {self.ts} | {self.agent} | {self.task_id}"
        lines = [head] + [f"- {name}：{self.fields.get(name, '')}" for name in BLOCK_FIELDS]
        return "\n".join(lines)


def read_handoff(path: Path) -> tuple[list[Block], list[str]]:
    path = Path(path)
    blocks: list[Block] = []
    if not path.is_file():
        return blocks, []
    current: Block | None = None
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = BLOCK_HEAD_RE.match(line.strip())
        if m:
            if current:
                blocks.append(current)
            current = Block(ts=m.group(1), agent=m.group(2), task_id=m.group(3),
                            fields={}, line_no=no)
            continue
        if current is not None:
            fm = FIELD_RE.match(line.strip())
            if fm:
                current.fields[fm.group(1)] = fm.group(2).strip()
    if current:
        blocks.append(current)
    problems: list[str] = []
    for b in blocks:
        missing = [f for f in BLOCK_FIELDS if not b.field(f)]
        if missing:
            problems.append(f"L{b.line_no} 交接块 {b.task_id} 缺字段: {'、'.join(missing)}")
    return blocks, problems


def handoff_header(task_id: str, date: str) -> str:
    return "\n".join([
        "---",
        f"title: 交接 {task_id}",
        f"date: {date}",
        "tags: [协同, 交接]",
        "status: 进行中",
        "agent: shared",
        "---",
        "",
        f"# 交接 {task_id}",
        "",
        f"> 本文件只追加、不覆盖历史块；字段与写法见 `{HANDOFF_DIR}/{TEMPLATE_NAME}`。",
        "",
    ])


def append_handoff_block(root: Path, block: Block, task_title: str = "") -> tuple[Path, bool]:
    """追加交接块；同 (ts, agent, task) 已存在则跳过。返回 (路径, 是否写入)。"""
    path = handoff_path(root, block.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(handoff_header(block.task_id, block.ts[:10]) + "\n", encoding="utf-8")
    blocks, _ = read_handoff(path)
    if any(b.ts == block.ts and b.agent == block.agent and b.task_id == block.task_id
           for b in blocks):
        return path, False
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block.render() + "\n", encoding="utf-8")
    return path, True


# ---------------------------------------------------------------- 会话索引

def read_index(root: Path, agent: str) -> tuple[list[dict], list[str]]:
    path = index_path(root, agent)
    rows: list[dict] = []
    problems: list[str] = []
    if not path.is_file():
        return rows, problems
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name} L{no} JSON 解析失败: {exc}")
            continue
        if not isinstance(obj, dict):
            problems.append(f"{path.name} L{no} 不是 JSON 对象")
            continue
        rows.append(obj)
    return rows, problems


def read_all_index(root: Path) -> tuple[list[tuple[str, dict]], list[str]]:
    rows: list[tuple[str, dict]] = []
    problems: list[str] = []
    idx_dir = Path(root) / INDEX_DIR
    if not idx_dir.is_dir():
        return rows, problems
    for path in sorted(idx_dir.glob("*.jsonl")):
        got, probs = read_index(root, path.stem)
        rows.extend((path.stem, r) for r in got)
        problems.extend(probs)
    return rows, problems


def append_index(root: Path, record: dict) -> tuple[Path, bool]:
    agent = str(record.get("agent", "")).strip()
    if not agent:
        raise ValueError("record.agent 不能为空")
    path = index_path(root, agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows, _ = read_index(root, agent)
    key = (record.get("ts"), record.get("task"), record.get("agent"))
    for r in rows:
        if (r.get("ts"), r.get("task"), r.get("agent")) == key:
            return path, False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path, True
