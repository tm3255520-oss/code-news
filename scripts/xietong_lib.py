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

import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:  # POSIX 跨进程文件锁
    import fcntl  # type: ignore
except ImportError:  # Windows
    fcntl = None  # type: ignore

try:  # Windows 跨进程文件锁
    import msvcrt  # type: ignore
except ImportError:  # POSIX
    msvcrt = None  # type: ignore

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

# 协同文件的行尾约定：**固定 CRLF**，与运行平台无关。
# 背景：本模块原先的写入点都不传 newline，行尾随平台走 —— Windows 产出 CRLF、Linux/WSL 产出 LF；
# 同一份协同文件被不同平台的 Agent 写过就会变 MIXED（2026-10-01 实测：codex.jsonl 的 P0 手工追加
# 行是 LF、P1 脚本行是 CRLF，整份文件呈 MIXED）。口径见 vault `系统中枢/协同/会话索引/_README.md`。
FILE_NEWLINE = "\r\n"


# ---------------------------------------------------------------- 并发安全：锁 + 原子写
# 背景（WK-20261017-21）：四处落盘都是裸 read-modify-write，多 Agent 并行收工会后写覆盖
# 先写（丢块）。补两层：① 进程内按路径 RLock + 跨进程 OS 文件锁（fail-open）；② 写盘改原子替换。
# 锁文件放 `%TEMP%/xietong-locks/`，不在 vault 里留 `.lock` 文件。

_LOCK_DIR = Path(tempfile.gettempdir()) / "xietong-locks"

# 进程内按「归一化路径」注册的 RLock：不同路径互不阻塞，同路径同进程内串行、同线程可重入。
_INPROC_LOCKS: dict[str, "threading.RLock"] = {}
_INPROC_LOCKS_GUARD = threading.Lock()
# 线程本地的重入深度计数：key -> 当前线程在该路径上的嵌套层数。
_THREAD_DEPTHS = threading.local()


def _lock_key(path: "str | os.PathLike[str]") -> str:
    """把路径归一化成锁键：resolve 后小写（Windows 大小写不敏感；POSIX 无害）。"""
    return str(Path(path).resolve()).lower()


def _inproc_lock(key: str) -> "threading.RLock":
    with _INPROC_LOCKS_GUARD:
        lock = _INPROC_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _INPROC_LOCKS[key] = lock
        return lock


def _depth_map() -> "dict[str, int]":
    depths = getattr(_THREAD_DEPTHS, "map", None)
    if depths is None:
        depths = {}
        _THREAD_DEPTHS.map = depths
    return depths


def _lock_file(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return _LOCK_DIR / f"{digest}.lock"


@contextmanager
def locked(path: "str | os.PathLike[str]", timeout: float = 15.0):
    """跨进程/跨线程的「同路径互斥」护栏（fail-open）。

    - 进程内：按归一化路径取 RLock（同线程可重入、异线程阻塞）。
    - 跨进程：仅在深度 0→1 时取 OS 独占锁（Windows `msvcrt` / POSIX `fcntl`），1→0 时释放；
      拿不到就 `sleep(0.05)` 重试，到 `timeout` 仍拿不到则打印警告并**继续**（锁是护栏，
      不是单点故障源：不许无限等、不许抛异常）。
    - 嵌套调用同一路径（如 `append_handoff_block` 内部调 `sync_handoff_status`）不会死锁。
    """
    key = _lock_key(path)
    rl = _inproc_lock(key)
    rl.acquire()
    depths = _depth_map()
    depth = depths.get(key, 0)
    depths[key] = depth + 1

    os_fd: "int | None" = None
    os_locked = False
    try:
        if depth == 0:  # 仅最外层负责跨进程锁
            _LOCK_DIR.mkdir(parents=True, exist_ok=True)
            lock_path = _lock_file(key)
            try:
                os_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            except OSError as exc:
                print(f"[xietong_lib] 警告：无法打开锁文件 {lock_path}（{exc}），"
                      f"降级为无锁写入（fail-open）", file=sys.stderr)
                os_fd = None
            if os_fd is not None:
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        if msvcrt is not None:
                            os.lseek(os_fd, 0, os.SEEK_SET)
                            msvcrt.locking(os_fd, msvcrt.LK_NBLCK, 1)
                        elif fcntl is not None:
                            fcntl.flock(os_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        else:
                            raise OSError("无可用跨进程锁原语（msvcrt/fcntl 均不可用）")
                        os_locked = True
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            break
                        time.sleep(0.05)
                if not os_locked:
                    print(f"[xietong_lib] 警告：{timeout:.0f}s 内未能获得文件锁 "
                          f"{lock_path}，降级为无锁写入（fail-open）", file=sys.stderr)
        yield
    finally:
        depths[key] -= 1
        if depths[key] <= 0:
            depths.pop(key, None)
        if os_fd is not None:
            try:
                if os_locked:
                    if msvcrt is not None:
                        os.lseek(os_fd, 0, os.SEEK_SET)
                        msvcrt.locking(os_fd, msvcrt.LK_UNLCK, 1)
                    elif fcntl is not None:
                        fcntl.flock(os_fd, fcntl.LOCK_UN)
            finally:
                try:
                    os.close(os_fd)
                except OSError:
                    pass
        rl.release()


def _tmp_sibling(path: Path) -> Path:
    return path.parent / f".{path.name}.tmp-{os.getpid()}-{os.urandom(4).hex()}"


_REPLACE_RETRIES = 10
_REPLACE_DELAY = 0.02


def _replace(tmp: Path, path: Path) -> None:
    """`os.replace` 的 Windows 加固：目标文件被 Defender/索引器短暂占用时会瞬时报
    `PermissionError`（WinError 5），重试几次；仍失败则抛原异常（由调用方清理 tmp）。
    """
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(_REPLACE_DELAY)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """写同目录临时文件后 `os.replace` 原子替换；失败清理 tmp 并抛原异常。"""
    path = Path(path)
    tmp = _tmp_sibling(path)
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_text_file(path: Path, text: str) -> None:
    """按协同约定写文本：行尾固定 CRLF（与运行平台无关）。

    用 `open(newline=...)` 而非 `Path.write_text(newline=...)` —— 后者需 Python ≥3.10，
    而本脚本会被 Windows 与 WSL 两侧调用，解释器版本不保证。写盘改「临时文件 + 原子替换」，
    避免写一半崩/被杀留下半截文件。
    """
    path = Path(path)
    tmp = _tmp_sibling(path)
    try:
        with tmp.open("w", encoding="utf-8", newline=FILE_NEWLINE) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


TASK_ID_RE = re.compile(r"^WK-\d{8}-\d{2}$")
TASK_ID_PREFIX_RE = re.compile(r"^WK-")


def is_noncompliant_task_id(text: str) -> bool:
    """判断标识是否「形如 WK-… 但不满足 WK-<YYYYMMDD>-<两位序号>」的不合规任务ID。

    巡检用：凡 WK- 开头却不匹配 TASK_ID_RE 的标识（如 WK-20261014-skillrep）单独
    指名成一条「任务ID 不合规」，而非让它派生「没有对应任务行 / 引用了不存在的任务」等噪声。
    """
    text = (text or "").strip()
    return bool(TASK_ID_PREFIX_RE.match(text)) and not bool(TASK_ID_RE.match(text))


BLOCK_HEAD_RE = re.compile(r"^##\s+(\S+)\s*\|\s*([A-Za-z0-9_\-]+)\s*\|\s*(WK-\d{8}-\d{2})\s*$")
BLOCK_FIELDS = ("本轮做了什么", "动了哪些文件", "证据", "未决问题", "下一步",
                "建议接手方 + 该调的 skill", "状态")
# 字段行允许三种常见写法（2026-09-30 实测 codex 真实交接文件后放宽，属校验器修正而非改文件）：
#   - 本轮做了什么：xxx        /  **本轮做了什么**：xxx  /  - **证据（可复核）**：xxx
FIELD_RE = re.compile(
    r"^[-*]?\s*\**\s*(" + "|".join(re.escape(f) for f in BLOCK_FIELDS) +
    r")(?:\s*（[^）]*）)?\s*\**\s*[:：]\s*(.*)$"
)
# 产出路径单元格可能是多路径拼接（`a.md` ／ `b.md`、c.md）
PATH_SEP_RE = re.compile(r"[／、；;]|\s/\s|[,，]")
# frontmatter 的 `status:` 行（前导空白 + status 冒号 + 值 + 尾随空白，逐字节只改值部分）
FM_STATUS_RE = re.compile(r"^(\s*status\s*:\s*)(.*?)(\s*)$")

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


# ---------------------------------------------------------------- 迭代链识别
# 2026-10-13：原重复判据（同 platform + 标题词元交集）把「同一工作的多轮迭代」
# 误报为重复（巡检 29 条经逐对核实 0 条真撞题）。以下三层豁免用于区分迭代链与
# 真重复；命中豁免的对不计 findings，但由调用方以 [迭代链提示] 形式打印可复查。
VERSION_RE = re.compile(r'[vV](\d+(?:\.\d+)?)')
STAGE_RE = re.compile(r'阶段\s*(\d+)')
TASKID_RE = re.compile(r'WK-(\d{8})-(\d+)')
ITERATION_SEQ_WINDOW = 20  # 同负责人同日连续登记的序号差窗口


def iteration_reason(a, b) -> str | None:
    """判断两个活跃任务是否同一工作的多轮迭代/连续登记。

    返回原因串（人类可读）表示应豁免；返回 None 表示仍按重复上报。
    三层判定，任一命中即豁免：
      1) 版本序列：两标题都带版本号且版本不同（v2↔v3、V2.0↔无版本不适用本条）
      2) 阶段序列：两标题都带「阶段N」且 N 不同
      3) 同负责人同日连续登记：owner 相同、任务号日期段相同、序号差 ≤ 窗口
    不在豁免范围的组合（不同负责人同题、跨日无版本、序号差过大、版本相同且跨日）
    一律返回 None——真重复照报。
    """
    va = VERSION_RE.findall(a.title or '')
    vb = VERSION_RE.findall(b.title or '')
    if va and vb and va != vb:
        return f'同作品版本迭代（{"→".join(va)} vs {"→".join(vb)}）'
    sa = STAGE_RE.findall(a.title or '')
    sb = STAGE_RE.findall(b.title or '')
    if sa and sb and sa != sb:
        return f'阶段序列推进（阶段{sa[0]}→阶段{sb[0]}）'
    if a.owner and a.owner == b.owner:
        ma = TASKID_RE.match(a.task_id or '')
        mb = TASKID_RE.match(b.task_id or '')
        if (ma and mb and ma.group(1) == mb.group(1)
                and abs(int(ma.group(2)) - int(mb.group(2))) <= ITERATION_SEQ_WINDOW):
            return f'同负责人（{a.owner}）同日连续登记（{a.task_id} 与 {b.task_id}）'
    return None


def contains_secret(text: str) -> bool:
    return bool(SECRET_RE.search(text or ""))


def split_paths(cell: str) -> list[str]:
    """把一个单元格里的多个产出路径拆开（`a.md` ／ `b.md`、c.md → [a.md, b.md, c.md]）。"""
    text = (cell or "").replace("`", " ").replace("\n", " ")
    out: list[str] = []
    for part in PATH_SEP_RE.split(text):
        cand = part.strip().strip("｜|").strip()
        if not cand or cand == PLACEHOLDER:
            continue
        if "/" not in cand and "\\" not in cand:
            continue
        if cand not in out:
            out.append(cand)
    return out


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
    noncompliant_ids: list[str] = field(default_factory=list)

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
            # 形如 WK-… 但不合规的任务ID：收集起来交巡检统一指名，而非静默丢弃。
            # 取舍：该行整体不合规，其它字段（负责人/状态/时间/产出路径）不再检查，
            # 先让人把 ID 改对（WK-<YYYYMMDD>-<两位序号>），避免在同一行上叠噪声。
            if is_noncompliant_task_id(first):
                led.noncompliant_ids.append(first)
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
    """只替换目标任务那一行；force 时在「变更记录」表追加一行留痕。

    在 `locked(led.path)` 内**重读**台账再按 task_id 定位目标行，避免多 Agent 并行收工时
    后写覆盖先写（丢行/丢变更记录）。
    """
    if task.line_no <= 0:
        raise ValueError(f"任务 {task.task_id} 没有可定位的行号")
    with locked(led.path):
        fresh = parse_ledger(led.path)
        target = fresh.by_id(task.task_id)
        if target is None:
            raise ValueError(f"任务 {task.task_id} 在台账中不存在（重读后）")
        fresh.lines[target.line_no - 1] = task.render()
        if force:
            if not force_reason:
                raise ValueError("force 必须带 force_reason")
            entry = f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {change_log or task.owner} | 改 {task.task_id} | {force_reason} |"
            insert_at = None
            for i, line in enumerate(fresh.lines):
                if line.strip().startswith("## 变更记录"):
                    for j in range(i + 1, len(fresh.lines)):
                        if fresh.lines[j].strip().startswith("|"):
                            insert_at = j + 1
                    break
            if insert_at is None:
                fresh.lines.extend(["", "## 变更记录（跨 Agent 改动他人行时必写）", "",
                                    "| 时间 | 谁 | 改了哪行 | 原因 |", "|---|---|---|---|"])
                insert_at = len(fresh.lines)
            fresh.lines.insert(insert_at, entry)
        write_text_file(fresh.path, "\n".join(fresh.lines) + "\n")


def append_ledger_row(led: Ledger, task: Task) -> None:
    """在台账最后一条任务行之后插入新行。

    在 `locked(led.path)` 内重读台账再定位插入点，避免并发建行时互相覆盖。
    """
    with locked(led.path):
        fresh = parse_ledger(led.path)
        last = max((t.line_no for t in fresh.tasks), default=0)
        if last <= 0:
            anchor = None
            for i, line in enumerate(fresh.lines):
                if line.strip().startswith(f"| {COLUMNS[0]}"):
                    anchor = i + 2  # 表头 + 分隔行
                    break
            if anchor is None:
                raise ValueError("台账结构异常：找不到表头，无法追加行")
            fresh.lines.insert(anchor, task.render())
        else:
            fresh.lines.insert(last, task.render())
        write_text_file(fresh.path, "\n".join(fresh.lines) + "\n")


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
    current_field: str | None = None
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = BLOCK_HEAD_RE.match(line.strip())
        if m:
            if current:
                blocks.append(current)
            current = Block(ts=m.group(1), agent=m.group(2), task_id=m.group(3),
                            fields={}, line_no=no)
            current_field = None
            continue
        if current is None:
            continue
        fm = FIELD_RE.match(line.strip())
        if fm:
            current_field = fm.group(1)
            current.fields[current_field] = fm.group(2).strip()
            continue
        stripped = line.strip()
        # 续行：字段值可以有多行（含无缩进的续行），直到下一个字段/块标题/引用行
        if current_field and stripped and not stripped.startswith(("#", ">", "---")):
            current.fields[current_field] = (current.fields[current_field] + " " + stripped).strip()
    if current:
        blocks.append(current)
    problems: list[str] = []
    for b in blocks:
        missing = [f for f in BLOCK_FIELDS if not b.field(f)]
        if missing:
            problems.append(f"L{b.line_no} 交接块 {b.task_id} 缺字段: {'、'.join(missing)}")
    return blocks, problems


def handoff_header(task_id: str, date: str, status: str = "进行中") -> str:
    return "\n".join([
        "---",
        f"title: 交接 {task_id}",
        f"date: {date}",
        "tags: [协同, 交接]",
        f"status: {status}",
        "agent: shared",
        "---",
        "",
        f"# 交接 {task_id}",
        "",
        f"> 本文件只追加、不覆盖历史块；字段与写法见 `{HANDOFF_DIR}/{TEMPLATE_NAME}`。",
        "",
    ])


def sync_handoff_status(path: str | os.PathLike[str], *, write: bool = True) -> tuple[bool, str, str]:
    """把交接文件 frontmatter 的 `status:` 与最后一个交接块的 `- 状态：` 对齐。

    返回 `(是否改写, 旧值, 新值)`：
      - `(True, 旧 frontmatter 值, 最后一块状态)`：两者不一致；`write=True` 时已只改 frontmatter 那一行；
      - `(False, "", "")`：一致 / 没有 frontmatter / 没有 `status:` 行 / 没有交接块（不插入任何字段）。

    只允许动 frontmatter 的 `status:` 那一行；逐字节保留该文件原有行尾（LF/CRLF）与 UTF-8 BOM。
    `write=False` 只做判定不落盘，供一次性对齐脚本的 dry-run 复用同一套判定（不产生第二份逻辑）。
    整段读→改→写在 `locked(path)` 内，且落盘用原子替换。
    """
    path = Path(path)
    with locked(path):
        if not path.is_file():
            return (False, "", "")

        raw = path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")  # 去 BOM 再处理，写回时按 has_bom 补回

        if "\r\n" in text:
            nl = "\r\n"
        elif "\n" in text:
            nl = "\n"
        elif "\r" in text:
            nl = "\r"
        else:
            nl = "\n"

        lines = text.split(nl)
        # 定位 frontmatter：第一个 `---` 到下一个 `---` 之间（不碰块体里的内容）。
        start = end = None
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if start is None:
                    start = i
                else:
                    end = i
                    break
        if start is None or end is None:
            return (False, "", "")

        status_idx: int | None = None
        fm_status = ""
        for i in range(start + 1, end):
            m = FM_STATUS_RE.match(lines[i])
            if m:
                status_idx = i
                fm_status = m.group(2).strip()
                break
        if status_idx is None or not fm_status:
            return (False, "", "")

        # 最后一个交接块的 `- 状态：` 字段（复用 FIELD_RE，不依赖 read_handoff 的块分组——
        # 这样即便任务ID不合规、块头不规则的文件，也能取到「最后一次 append」的状态）。
        block_status = ""
        for i in range(end, len(lines)):
            fm = FIELD_RE.match(lines[i].strip())
            if fm and fm.group(1) == "状态":
                block_status = fm.group(2).strip()
        if not block_status:
            return (False, "", "")

        if fm_status == block_status:
            return (False, "", "")
        if not write:
            return (True, fm_status, block_status)

        m = FM_STATUS_RE.match(lines[status_idx])
        lines[status_idx] = m.group(1) + block_status + m.group(3)
        out = nl.join(lines).encode("utf-8")
        if has_bom:
            out = b"\xef\xbb\xbf" + out
        _atomic_write_bytes(path, out)
        return (True, fm_status, block_status)


def append_handoff_block(root: Path, block: Block, task_title: str = "") -> tuple[Path, bool]:
    """追加交接块；同 (ts, agent, task) 已存在则跳过。返回 (路径, 是否写入)。

    成功追加后把 frontmatter 的 `status:` 同步为最后一个块的 `状态`（sync_handoff_status），
    使「文件头 status」与「最后一块状态」不再自相矛盾。历史语义不变：仍只追加块。
    整段读→改→写在 `locked(path)` 内（内部调 sync_handoff_status 属同路径重入，不死锁）。
    """
    path = handoff_path(root, block.task_id)
    with locked(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            write_text_file(path, handoff_header(block.task_id, block.ts[:10],
                                                block.fields.get("状态", "进行中")) + "\n")
        blocks, _ = read_handoff(path)
        if any(b.ts == block.ts and b.agent == block.agent and b.task_id == block.task_id
               for b in blocks):
            return path, False
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        write_text_file(path, text + block.render() + "\n")
        sync_handoff_status(path)
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
    with locked(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        rows, _ = read_index(root, agent)
        key = (record.get("ts"), record.get("task"), record.get("agent"))
        for r in rows:
            if (r.get("ts"), r.get("task"), r.get("agent")) == key:
                return path, False
        # 末字节非 LF 时先补换行，避免新条目粘到上一条尾巴（同 append_handoff_block 的守卫）。
        if path.is_file() and path.stat().st_size > 0:
            with path.open("rb") as rb:
                rb.seek(-1, 2)
                last = rb.read(1)
            if last != b"\n":
                with path.open("a", encoding="utf-8", newline=FILE_NEWLINE) as fh:
                    fh.write("\n")
        with path.open("a", encoding="utf-8", newline=FILE_NEWLINE) as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path, True
