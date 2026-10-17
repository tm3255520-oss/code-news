"""协同三件套（work_lookup / handoff_append / xietong_audit / xietong_weekly）单元测试。

全部在临时目录里跑（`--root` 指过去），不触碰真实 vault。
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

from scripts import handoff_append, work_lookup, xietong_audit, xietong_weekly
from scripts import xietong_lib as lib

HEADER = ("| 任务ID | 标题 | 平台/形态 | 负责人 | 状态 | 最后更新 | 产出路径 | 关联会话/交接 |\n"
          "|---|---|---|---|---|---|---|---|\n")


def make_root(tmp: Path, rows: str = "", *, artifacts: tuple[str, ...] = ()) -> Path:
    vault = tmp / "vault"
    root = vault / "系统中枢" / "协同"
    (root / "交接").mkdir(parents=True)
    (root / "会话索引").mkdir(parents=True)
    (root / "任务台账.md").write_text(
        "---\ntitle: 任务台账\n---\n\n# 任务台账\n\n## 台账\n\n" + HEADER + rows, encoding="utf-8")
    for rel in artifacts:
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return root


def row(task_id: str, title: str, platform: str, owner: str, status: str, updated: str,
        artifact: str = "—", link: str = "—") -> str:
    return f"| {task_id} | {title} | {platform} | {owner} | {status} | {updated} | {artifact} | {link} |\n"


def make_block(ts: str, agent: str, task_id: str, status: str = "进行中") -> lib.Block:
    """构造一个 7 字段齐全的交接块（read_handoff 校验 problems 为空的前提）。"""
    return lib.Block(
        ts=ts, agent=agent, task_id=task_id,
        fields={"本轮做了什么": "x", "动了哪些文件": "y", "证据": "z",
                "未决问题": "无", "下一步": "无",
                "建议接手方 + 该调的 skill": "无", "状态": status},
        line_no=0)


class ParseLedgerTests(unittest.TestCase):
    def test_parses_rows_and_flags_column_count(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-01", "标题", "公众号", "codex",
                                           "进行中", "2026-09-30 10:00")
                             + "| WK-20260930-02 | 坏行 |\n")
            led = lib.parse_ledger(root / "任务台账.md")
        self.assertEqual([t.task_id for t in led.tasks], ["WK-20260930-01"])
        self.assertTrue(any("列数" in p for p in led.problems))

    def test_duplicate_ids_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-01", "A", "抖音", "dsh", "进行中",
                                           "2026-09-30 10:00")
                             + row("WK-20260930-01", "B", "抖音", "dsh", "进行中",
                                   "2026-09-30 11:00"))
            led = lib.parse_ledger(root / "任务台账.md")
        self.assertTrue(any("重复" in p for p in led.problems))

    def test_escaped_pipe_is_not_a_separator(self) -> None:
        cells = lib.split_row(r"| WK-20260930-01 | a\|b | 抖音 | dsh | 进行中 | x | — | — |")
        self.assertEqual(len(cells), 8)
        self.assertEqual(cells[1], "a|b")


class WorkLookupTests(unittest.TestCase):
    def test_active_hit_blocks_duplicate_work(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-01", "GPT-5 视频生成科普", "公众号",
                                           "codex", "进行中", "2026-09-30 10:00"))
            args = work_lookup.build_parser().parse_args(["视频生成", "--root", str(root)])
            payload = work_lookup.collect(args)
            kind, _ = work_lookup.verdict(payload)
        self.assertEqual(kind, "active")
        self.assertEqual(payload["active"][0]["owner"], "codex")

    def test_done_hit_says_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260929-01", "视频生成科普", "公众号", "codex",
                                           "已完成", "2026-09-29 10:00"))
            args = work_lookup.build_parser().parse_args(["视频生成", "--root", str(root)])
            payload = work_lookup.collect(args)
            kind, _ = work_lookup.verdict(payload)
        self.assertEqual(kind, "done")

    def test_no_hit_allows_new_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            args = work_lookup.build_parser().parse_args(["量子计算", "--root", str(root)])
            payload = work_lookup.collect(args)
            kind, _ = work_lookup.verdict(payload)
        self.assertEqual(kind, "none")

    def test_fail_on_active_returns_three(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-01", "视频生成", "公众号", "codex",
                                           "进行中", "2026-09-30 10:00"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = work_lookup.main(["视频生成", "--root", str(root), "--fail-on-active"])
        self.assertEqual(code, 3)

    def test_list_active_ignores_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td),
                             row("WK-20260930-01", "A", "抖音", "dsh", "进行中", "2026-09-30 10:00")
                             + row("WK-20260930-02", "B", "抖音", "dsh", "已完成", "2026-09-30 10:00"))
            args = work_lookup.build_parser().parse_args(["--list-active", "--root", str(root)])
            payload = work_lookup.collect(args)
        self.assertEqual([t["task_id"] for t in payload["tasks"]], ["WK-20260930-01"])


class HandoffAppendTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = handoff_append.main(argv)
        return code, buf.getvalue()

    def test_refuses_when_task_missing_and_not_create(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            code, out = self._run(["--task", "WK-20260930-09", "--agent", "dsh",
                                   "--status", "进行中", "--did", "x", "--evidence", "y",
                                   "--root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("先认领再动手", out)

    def test_create_writes_all_three(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            code, out = self._run(["--task", "WK-20260930-09", "--agent", "dsh",
                                   "--status", "进行中", "--did", "开工",
                                   "--evidence", "exit 0", "--create",
                                   "--title", "AI 视频生成科普", "--platform", "公众号·深度文",
                                   "--session-id", "s-1", "--now", "2026-09-30T15:00",
                                   "--root", str(root)])
            self.assertEqual(code, 0)
            led = lib.parse_ledger(root / "任务台账.md")
            blocks, problems = lib.read_handoff(root / "交接" / "WK-20260930-09.md")
            rows, _ = lib.read_index(root, "dsh")
        self.assertEqual(led.by_id("WK-20260930-09").owner, "dsh")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(problems, [])
        self.assertEqual(rows[0]["task"], "WK-20260930-09")
        self.assertEqual(rows[0]["outcome"], "进行中")
        self.assertIn("已追加", out)

    def test_idempotent_on_same_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            argv = ["--task", "WK-20260930-09", "--agent", "dsh", "--status", "待审",
                    "--did", "写完", "--evidence", "review.md", "--create",
                    "--title", "T", "--platform", "抖音", "--now", "2026-09-30T15:00",
                    "--root", str(root)]
            self._run(argv)
            code, out = self._run(argv)
            blocks, _ = lib.read_handoff(root / "交接" / "WK-20260930-09.md")
            rows, _ = lib.read_index(root, "dsh")
        self.assertEqual(code, 0)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(len(rows), 1)
        self.assertIn("跳过", out)

    def test_create_on_occupied_id_from_other_task_is_refused(self) -> None:
        """撞号=危险：另一个任务占了同一个 WK 号时必须拒（实测发生过两次静默覆盖）。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20261002-03", "ai 词表调优", "采集线/B站", "workbuddy",
                                           "待审", "2026-10-02 01:28",
                                           artifact="C:/Users/Administrator/.hermes/scripts/a.py"))
            before = (root / "任务台账.md").read_bytes()
            code, out = self._run(["--task", "WK-20261002-03", "--agent", "workbuddy",
                                   "--status", "已完成", "--did", "另一批活儿",
                                   "--evidence", "x.md", "--create",
                                   "--title", "B站首采第二轮", "--platform", "B站",
                                   "--root", str(root)])
            after = (root / "任务台账.md").read_bytes()
            handoffs = sorted(p.name for p in (root / "交接").iterdir())
        self.assertEqual(code, 2)
        self.assertIn("已被占用", out)
        self.assertEqual(before, after)
        self.assertEqual(handoffs, [])

    def test_repeat_call_merges_artifact_paths(self) -> None:
        """第二次收工的 --files 必须与台账已有路径取并集（原先整列覆盖）。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20261003-01", "T", "抖音", "dsh", "进行中",
                                           "2026-10-03 09:00", artifact="a/one.py,b/two.py"))
            code, _ = self._run(["--task", "WK-20261003-01", "--agent", "dsh",
                                 "--status", "进行中", "--did", "补产出", "--evidence", "x",
                                 "--files", "c/three.py", "--root", str(root)])
            led = lib.parse_ledger(root / "任务台账.md")
        self.assertEqual(code, 0)
        artifact = led.by_id("WK-20261003-01").artifact
        for p in ("a/one.py", "b/two.py", "c/three.py"):
            self.assertIn(p, artifact)
        self.assertNotIn("a/one.py, a/one.py", artifact)  # 去重

    def test_repeat_call_dedupes_slashes_and_case(self) -> None:
        """同一文件写成 `A\\B.py` / `a/b.py` 两种形态时不得重复登记。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20261003-01", "T", "抖音", "dsh", "进行中",
                                           "2026-10-03 09:00", artifact=r"C:\X\One.py"))
            self._run(["--task", "WK-20261003-01", "--agent", "dsh", "--status", "进行中",
                       "--did", "重复登记", "--evidence", "x",
                       "--files", "c:/x/one.py,d/two.py", "--root", str(root)])
            led = lib.parse_ledger(root / "任务台账.md")
        artifact = led.by_id("WK-20261003-01").artifact
        self.assertEqual(artifact.lower().count("one.py"), 1)
        self.assertIn("d/two.py", artifact)

    def test_owner_guard_and_force(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-01", "T", "抖音", "codex", "进行中",
                                           "2026-09-30 10:00"))
            base = ["--task", "WK-20260930-01", "--agent", "dsh", "--status", "进行中",
                    "--did", "接手", "--evidence", "log", "--root", str(root),
                    "--now", "2026-09-30T16:00"]
            code, _ = self._run(base)
            self.assertEqual(code, 2)
            code, out = self._run(base + ["--force", "--force-reason", "codex 已停手"])
            text = (root / "任务台账.md").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("codex 已停手", text)
        self.assertIn("变更记录", text)

    def test_rejects_secret(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            code, out = self._run(["--task", "WK-20260930-01", "--agent", "dsh",
                                   "--status", "进行中", "--did", "x",
                                   "--evidence", 'api_key: "0123456789abcdef"',
                                   "--create", "--title", "T", "--platform", "抖音",
                                   "--root", str(root)])
        self.assertEqual(code, 1)
        self.assertIn("疑似含密钥", out)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            code, out = self._run(["--task", "WK-20260930-01", "--agent", "dsh",
                                   "--status", "进行中", "--did", "x", "--evidence", "y",
                                   "--create", "--title", "T", "--platform", "抖音",
                                   "--dry-run", "--root", str(root)])
            ledger_text = (root / "任务台账.md").read_text(encoding="utf-8")
            handoff_exists = (root / "交接" / "WK-20260930-01.md").exists()
        self.assertEqual(code, 0)
        self.assertNotIn("WK-20260930-01", ledger_text)
        self.assertFalse(handoff_exists)
        self.assertIn("[dry-run]", out)


class AuditTests(unittest.TestCase):
    def _root(self, td: str, rows: str, artifacts: tuple[str, ...] = ()) -> Path:
        root = make_root(Path(td), rows, artifacts=artifacts)
        (root / "交接" / "WK-20260930-01.md").write_text(
            "# 交接 WK-20260930-01\n\n## 2026-09-30T10:00 | codex | WK-20260930-01\n"
            "- 本轮做了什么：x\n", encoding="utf-8")
        return root

    def test_clean_root_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = self._root(td, row("WK-20260930-01", "T", "抖音", "codex", "进行中",
                                      "2026-09-30 10:00"),
                              artifacts=("内容生产/a.md",))
            led = root / "任务台账.md"
            led.write_text(led.read_text(encoding="utf-8").replace("| — | — |",
                                                                   "| 内容生产/a.md | — |"),
                           encoding="utf-8")
            (root / "交接" / "WK-20260930-01.md").write_text(
                "# 交接\n\n## 2026-09-30T10:00 | codex | WK-20260930-01\n"
                + "".join(f"- {f}：x\n" for f in lib.BLOCK_FIELDS), encoding="utf-8")
            (root / "会话索引" / "codex.jsonl").write_text(
                json.dumps({"agent": "codex", "ts": "2026-09-30T10:00",
                            "task": "WK-20260930-01", "outcome": "进行中"},
                           ensure_ascii=False) + "\n", encoding="utf-8")
            findings = xietong_audit.audit(root, 7, datetime(2026, 9, 30, 12, 0))
        self.assertEqual(findings, [], findings)

    def test_stale_and_duplicate_and_format(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            now = datetime(2026, 9, 30, 12, 0)
            old = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
            root = self._root(td,
                              row("WK-20260930-01", "GPT-5 视频生成", "公众号", "codex", "进行中", old)
                              + row("WK-20260930-02", "GPT-5 视频生成 二创", "公众号", "dsh", "进行中", old)
                              + row("WK-20260930-03", "无主任务", "抖音", "", "外星状态", "not-a-time"))
            for tid in ("WK-20260930-01", "WK-20260930-02"):
                (root / "交接" / f"{tid}.md").write_text(
                    "# 交接\n\n## 2026-09-30T10:00 | codex | " + tid + "\n- 本轮做了什么：x\n",
                    encoding="utf-8")
            findings = xietong_audit.audit(root, 7, now)
        checks = {f["check"] for f in findings}
        self.assertIn("停滞", checks)
        self.assertIn("重复", checks)
        self.assertIn("格式", checks)
        self.assertTrue(any("缺负责人" in f["detail"] for f in findings))
        self.assertTrue(any("状态非法" in f["detail"] for f in findings))

    def test_missing_handoff_for_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-05", "T", "抖音", "dsh", "进行中",
                                           "2026-09-30 10:00"))
            findings = xietong_audit.audit(root, 7, datetime(2026, 9, 30, 12, 0))
        self.assertTrue(any("没有交接文件" in f["detail"] for f in findings))

    def test_missing_index_row_for_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-05", "T", "抖音", "dsh", "进行中",
                                           "2026-09-30 10:00"))
            (root / "交接" / "WK-20260930-05.md").write_text(
                "# 交接\n\n## 2026-09-30T10:00 | dsh | WK-20260930-05\n"
                + "".join(f"- {f}：x\n" for f in lib.BLOCK_FIELDS), encoding="utf-8")
            findings = xietong_audit.audit(root, 7, datetime(2026, 9, 30, 12, 0))
        self.assertTrue(any("会话索引没有对应行" in f["detail"] for f in findings))

    def test_multi_path_artifact_is_checked_per_path(self) -> None:
        """实测 codex 真实台账：产出路径列写成 `a.md` ／ `b.md`，不应整体误报断链。"""
        with tempfile.TemporaryDirectory() as td:
            cell = "`内容生产/a.md` ／ `内容生产/b.md`"
            root = make_root(Path(td), row("WK-20260930-06", "T", "抖音", "codex", "已完成",
                                           "2026-09-30 10:00", artifact=cell),
                             artifacts=("内容生产/a.md", "内容生产/b.md"))
            findings = xietong_audit.audit(root, 7, datetime(2026, 9, 30, 12, 0))
            self.assertEqual(lib.split_paths(cell), ["内容生产/a.md", "内容生产/b.md"])
        self.assertFalse([f for f in findings if f["check"] == "断链"], findings)

    def test_real_world_bold_fields_and_continuation_lines(self) -> None:
        """实测 codex 写法：`- **本轮做了什么**：` + 续行 + `- **证据（可复核）**：`。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            path = root / "交接" / "WK-20260930-07.md"
            path.write_text(
                "# 交接\n\n## 2026-09-30T15:10 | codex | WK-20260930-07\n\n"
                "- **本轮做了什么**：整改收官 ——（a）音源取错定位并修；\n"
                "- **动了哪些文件**：\n"
                "  vault：`系统中枢/x.md`、`raw/videos/**`；\n"
                "  代码：`raw_lint.py`。\n"
                "- **证据（可复核）**：\n"
                "  ① `python raw_lint.py` → 不合规 38；\n"
                "  ② 负向测试 exit 1。\n"
                "- **未决问题**：20 篇作者补不了。\n"
                "- **下一步**：等用户表态。\n"
                "- **建议接手方 + 该调的 skill**：无。\n"
                "- **状态**：待审\n", encoding="utf-8")
            blocks, problems = lib.read_handoff(path)
        self.assertEqual(problems, [])
        self.assertEqual(len(blocks), 1)
        self.assertIn("音源取错", blocks[0].field("本轮做了什么"))
        self.assertIn("raw_lint.py", blocks[0].field("动了哪些文件"))
        self.assertIn("负向测试 exit 1", blocks[0].field("证据"))
        self.assertEqual(blocks[0].field("状态"), "待审")

    def test_orphan_handoff_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            (root / "交接" / "WK-20260930-99.md").write_text("# 孤儿\n", encoding="utf-8")
            findings = xietong_audit.audit(root, 7, datetime(2026, 9, 30, 12, 0))
        self.assertTrue(any("没有对应任务行" in f["detail"] for f in findings))

    def test_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), row("WK-20260930-05", "T", "抖音", "dsh", "进行中",
                                           "2026-09-30 10:00"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = xietong_audit.main(["--root", str(root),
                                           "--now", "2026-09-30T12:00"])
                soft = xietong_audit.main(["--root", str(root), "--soft",
                                           "--now", "2026-09-30T12:00"])
            self.assertEqual(code, 1)
            self.assertEqual(soft, 0)

    def test_quiet_when_clean_prints_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td), artifacts=("内容生产/a.md",))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = xietong_audit.main(["--root", str(root), "--quiet-when-clean",
                                           "--now", "2026-09-30T12:00"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue(), "")


class WeeklyTests(unittest.TestCase):
    def test_report_contains_sections_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            now = datetime(2026, 9, 30, 12, 0)
            root = make_root(Path(td),
                             row("WK-20260930-01", "本周新任务", "公众号", "codex", "进行中",
                                 "2026-09-30 10:00")
                             + row("WK-20260920-01", "上周完成", "抖音", "dsh", "已完成",
                                   "2026-09-29 10:00"))
            (root / "交接" / "WK-20260930-01.md").write_text(
                "# 交接\n\n## 2026-09-30T10:00 | codex | WK-20260930-01\n"
                + "".join(f"- {f}：x\n" for f in lib.BLOCK_FIELDS), encoding="utf-8")
            report = xietong_weekly.build_report(root, 7, now)
        self.assertIn("# 协同周报", report)
        self.assertIn("本周新增：**1**", report)
        self.assertIn("本周完成/归档：**1**", report)
        self.assertIn("WK-20260930-01", report)
        self.assertIn("| codex | 1 | 1 |", report)

    def test_main_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = xietong_weekly.main(["--root", str(root), "--now", "2026-09-30T12:00"])
        self.assertEqual(code, 0)
        self.assertIn("findings=0", buf.getvalue())


class TaskIdAndTokensTests(unittest.TestCase):
    def test_task_date_and_tokens(self) -> None:
        self.assertEqual(xietong_weekly.task_date("WK-20260930-01"), datetime(2026, 9, 30))
        self.assertIsNone(xietong_weekly.task_date("bad"))
        self.assertIn("gpt", lib.tokens("GPT-5 视频生成"))
        self.assertEqual(lib.tokens("视频 内容"), set())


class AppendIndexTests(unittest.TestCase):
    def test_append_index_no_trailing_newline_does_not_glue(self) -> None:
        """反例：末行无换行时追加，守卫先补换行，不粘连且 problems 为空。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            idx = root / "会话索引" / "codex.jsonl"
            first = {"agent": "codex", "ts": "t1", "task": "T1"}
            idx.write_bytes(json.dumps(first, ensure_ascii=False).encode("utf-8"))
            rec = {"agent": "codex", "ts": "t2", "task": "T2", "outcome": "进行中"}
            path, wrote = lib.append_index(root, rec)
            rows, problems = lib.read_index(root, "codex")
            raw = idx.read_bytes()
            lines = raw.splitlines()
        self.assertTrue(wrote)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), first)
        self.assertEqual(json.loads(lines[1]), rec)
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))

    def test_append_index_crlf_trailing_newline_no_regression(self) -> None:
        """正例：末行以 CRLF 结尾时行为与旧实现一致，新条目独占一行。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            idx = root / "会话索引" / "codex.jsonl"
            first = {"agent": "codex", "ts": "t1", "task": "T1"}
            idx.write_bytes(json.dumps(first, ensure_ascii=False).encode("utf-8") + b"\r\n")
            rec = {"agent": "codex", "ts": "t2", "task": "T2", "outcome": "进行中"}
            path, wrote = lib.append_index(root, rec)
            rows, problems = lib.read_index(root, "codex")
            raw = idx.read_bytes()
            lines = raw.splitlines()
        self.assertTrue(wrote)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), first)
        self.assertEqual(json.loads(lines[1]), rec)
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))

    def test_append_index_dedup_no_write(self) -> None:
        """同一条 record 第二次调用返回 (path, False)，且文件字节完全不变。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            rec = {"agent": "codex", "ts": "t1", "task": "T1", "outcome": "进行中"}
            path1, wrote1 = lib.append_index(root, rec)
            before = (root / "会话索引" / "codex.jsonl").read_bytes()
            path2, wrote2 = lib.append_index(root, rec)
            after = (root / "会话索引" / "codex.jsonl").read_bytes()
        self.assertTrue(wrote1)
        self.assertFalse(wrote2)
        self.assertEqual(path1, path2)
        self.assertEqual(before, after)


class SyncHandoffStatusTests(unittest.TestCase):
    """WK-20261017-19：sync_handoff_status / handoff_header(status=…) 的回归测试。

    全部跑在临时目录，不触碰真实 vault；不覆盖生产代码（xietong_lib.py 一个字节不动）。
    """

    def _handoff(self, fm_status: str, block_status: str, *, nl: str = "\n",
                 bom: bool = False) -> bytes:
        """构造一份最小交接文件：frontmatter 带 status + 一个完整交接块（状态=block_status）。"""
        content = (
            "---" + nl
            + "title: 交接 WK-20260101-01" + nl
            + "date: 2026-01-01" + nl
            + "tags: [协同, 交接]" + nl
            + f"status: {fm_status}" + nl
            + "agent: shared" + nl
            + "---" + nl
            + nl
            + "# 交接 WK-20260101-01" + nl
            + nl
            + "## 2026-01-01T10:00 | codex | WK-20260101-01" + nl
            + "- 本轮做了什么：x" + nl
            + "- 动了哪些文件：y" + nl
            + "- 证据：z" + nl
            + "- 未决问题：无" + nl
            + "- 下一步：无" + nl
            + "- 建议接手方 + 该调的 skill：无" + nl
            + f"- 状态：{block_status}" + nl
        )
        data = content.encode("utf-8")
        return (b"\xef\xbb\xbf" + data) if bom else data

    def test_status_mismatch_updates_only_status_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.md"
            p.write_bytes(self._handoff("进行中", "已完成"))
            before = p.read_text(encoding="utf-8").splitlines()
            result = lib.sync_handoff_status(p)
            after = p.read_text(encoding="utf-8").splitlines()
        self.assertEqual(result, (True, "进行中", "已完成"))
        self.assertEqual(len(before), len(after))
        diffs = [(i, b, a) for i, (b, a) in enumerate(zip(before, after)) if b != a]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0][1], "status: 进行中")
        self.assertEqual(diffs[0][2], "status: 已完成")

    def test_status_already_consistent_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.md"
            p.write_bytes(self._handoff("已完成", "已完成"))
            before = p.read_bytes()
            result = lib.sync_handoff_status(p)
            after = p.read_bytes()
        self.assertEqual(result, (False, "", ""))
        self.assertEqual(before, after)

    def test_boundary_cases_no_insertion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # 无 frontmatter
            p1 = Path(td) / "no_fm.md"
            p1.write_bytes(
                ("# 无 frontmatter\n\n"
                 "## 2026-01-01T10:00 | codex | WK-20260101-01\n- 状态：已完成\n").encode("utf-8"))
            before1 = p1.read_bytes()
            r1 = lib.sync_handoff_status(p1)
            self.assertEqual(r1, (False, "", ""))
            self.assertEqual(before1, p1.read_bytes())

            # frontmatter 无 status: 行
            p2 = Path(td) / "no_status.md"
            p2.write_bytes(
                ("---\ntitle: x\n---\n\n"
                 "## 2026-01-01T10:00 | codex | WK-20260101-01\n- 状态：已完成\n").encode("utf-8"))
            before2 = p2.read_bytes()
            r2 = lib.sync_handoff_status(p2)
            self.assertEqual(r2, (False, "", ""))
            self.assertEqual(before2, p2.read_bytes())

            # 文件不存在 → 不抛异常
            p3 = Path(td) / "missing.md"
            r3 = lib.sync_handoff_status(p3)
            self.assertEqual(r3, (False, "", ""))

    def test_crlf_and_bom_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # ① 全 CRLF：改后仍全 CRLF，无孤立 \n
            p1 = Path(td) / "crlf.md"
            p1.write_bytes(self._handoff("进行中", "已完成", nl="\r\n"))
            r1 = lib.sync_handoff_status(p1)
            raw1 = p1.read_bytes()
            self.assertEqual(r1, (True, "进行中", "已完成"))
            self.assertNotIn(b"\n", raw1.replace(b"\r\n", b""))
            self.assertIn("status: 已完成", raw1.decode("utf-8-sig"))

            # ② 带 UTF-8 BOM：改后仍有 BOM，且状态已更新
            p2 = Path(td) / "bom.md"
            p2.write_bytes(self._handoff("进行中", "已完成", bom=True))
            r2 = lib.sync_handoff_status(p2)
            raw2 = p2.read_bytes()
            self.assertEqual(r2, (True, "进行中", "已完成"))
            self.assertTrue(raw2.startswith(b"\xef\xbb\xbf"))
            self.assertIn("status: 已完成", raw2.decode("utf-8-sig"))

    def test_append_handoff_block_syncs_status_end_to_end(self) -> None:
        def block(ts: str, status: str) -> lib.Block:
            return lib.Block(
                ts=ts, agent="codex", task_id="WK-20260101-01",
                fields={"本轮做了什么": "x", "动了哪些文件": "y", "证据": "z",
                        "未决问题": "无", "下一步": "无",
                        "建议接手方 + 该调的 skill": "无", "状态": status},
                line_no=0)

        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            path1, wrote1 = lib.append_handoff_block(root, block("2026-01-01T10:00", "进行中"))
            text1 = path1.read_text(encoding="utf-8")
            path2, wrote2 = lib.append_handoff_block(root, block("2026-01-01T11:00", "待审"))
            blocks, problems = lib.read_handoff(path2)
            text2 = path2.read_text(encoding="utf-8")

        self.assertTrue(wrote1)
        self.assertTrue(wrote2)
        self.assertEqual(path1, path2)
        self.assertIn("status: 进行中", text1)
        self.assertIn("status: 待审", text2)
        self.assertEqual(problems, [])
        self.assertEqual(len(blocks), 2)

        header = lib.handoff_header("WK-20260101-01", "2026-01-01", status="待审")
        self.assertIn("status: 待审", header)

    def test_write_false_returns_mismatch_without_writing(self) -> None:
        """WK-20261017-20 N1：write=False 只判定不落盘——frontmatter 与最后一块不一致时返回 (True,旧,新) 且字节不变。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.md"
            p.write_bytes(self._handoff("进行中", "已完成"))
            before = p.read_bytes()
            result = lib.sync_handoff_status(p, write=False)
            after = p.read_bytes()
        self.assertEqual(result, (True, "进行中", "已完成"))
        self.assertEqual(before, after)

    def test_cli_full_chain_syncs_frontmatter(self) -> None:
        """WK-20261017-20 N2：CLI 整链——create 建行写交接块并把 frontmatter status 对齐；二次收工改状态再追加一块。"""
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(buf):
                code1 = handoff_append.main([
                    "--task", "WK-20260101-01", "--agent", "codex",
                    "--status", "待审", "--create",
                    "--title", "t", "--platform", "p",
                    "--did", "d", "--evidence", "e",
                    "--root", str(root), "--now", "2026-01-01T10:00"])
            hpath = root / "交接" / "WK-20260101-01.md"
            blocks1, _ = lib.read_handoff(hpath)
            text1 = hpath.read_text(encoding="utf-8")

            with redirect_stdout(buf), redirect_stderr(buf):
                code2 = handoff_append.main([
                    "--task", "WK-20260101-01", "--agent", "codex",
                    "--status", "已完成",
                    "--did", "d2", "--evidence", "e2",
                    "--root", str(root), "--now", "2026-01-01T11:00"])
            blocks2, _ = lib.read_handoff(hpath)
            text2 = hpath.read_text(encoding="utf-8")

        self.assertEqual(code1, 0)
        self.assertEqual(len(blocks1), 1)
        self.assertIn("status: 待审", text1)

        self.assertEqual(code2, 0)
        self.assertEqual(len(blocks2), 2)
        self.assertIn("status: 已完成", text2)

    def test_parenthesized_status_preserved_verbatim(self) -> None:
        """WK-20261017-20 N3：块状态带括号标注时，同步后 frontmatter 的 status 逐字等于该串（记录当前行为）。"""
        annot = "待审（首轮实跑完成；4 张卡待复核）"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.md"
            p.write_bytes(self._handoff("进行中", annot))
            result = lib.sync_handoff_status(p)
            text = p.read_text(encoding="utf-8")
        self.assertEqual(result, (True, "进行中", annot))
        self.assertIn(f"status: {annot}", text)

    def test_second_sync_is_idempotent(self) -> None:
        """WK-20261017-20 N4：一次成功同步后紧接着再调一次 → (False,"","") 且字节不变。"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.md"
            p.write_bytes(self._handoff("进行中", "已完成"))
            first = lib.sync_handoff_status(p)
            after_first = p.read_bytes()
            second = lib.sync_handoff_status(p)
            after_second = p.read_bytes()
        self.assertEqual(first, (True, "进行中", "已完成"))
        self.assertEqual(second, (False, "", ""))
        self.assertEqual(after_first, after_second)


class ConcurrencyTests(unittest.TestCase):
    """WK-20261017-21：并发安全（进程锁 + 原子替换）自测 T1–T5。

    全部跑在临时目录，不触碰真实 vault；只验证锁/原子写带来的行为不变式。
    """

    def test_thread_concurrent_append_handoff_blocks(self) -> None:
        """T1：同一交接文件 8 线程 × 各追加 5 个不同块 → 恰好 40 块、无重复无丢失。"""
        n_threads, per_thread = 8, 5
        task_id = "WK-20260101-01"
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))

            def worker(i: int) -> None:
                for j in range(per_thread):
                    ts = f"2026-01-01T{i:02d}:{j:02d}"
                    lib.append_handoff_block(root, make_block(ts, "codex", task_id), "t")

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            blocks, problems = lib.read_handoff(root / "交接" / f"{task_id}.md")

        self.assertEqual(len(blocks), n_threads * per_thread)
        self.assertEqual(problems, [])
        self.assertEqual(len({b.ts for b in blocks}), n_threads * per_thread)  # 无重复

    def test_process_concurrent_append_handoff_blocks(self) -> None:
        """T2：4 个子进程各追加 5 块到同一文件 → 恰好 20 块。"""
        n_proc, per_proc = 4, 5
        task_id = "WK-20260101-02"
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            scripts_dir = str(Path(lib.__file__).resolve().parent)
            worker = Path(td) / "_xietong_worker.py"
            worker.write_text(
                "import sys\n"
                "sys.path.insert(0, sys.argv[1])\n"
                "from xietong_lib import Block, append_handoff_block\n"
                "root, i = sys.argv[2], int(sys.argv[3])\n"
                "tid = 'WK-20260101-02'\n"
                "fields = {'本轮做了什么':'x','动了哪些文件':'y','证据':'z',"
                "'未决问题':'无','下一步':'无','建议接手方 + 该调的 skill':'无','状态':'进行中'}\n"
                "for j in range(5):\n"
                "    ts = '2026-01-02T%02d:%02d' % (i, j)\n"
                "    append_handoff_block(root, "
                "Block(ts=ts, agent='codex', task_id=tid, fields=fields, line_no=0), 't')\n",
                encoding="utf-8",
            )
            procs = [
                subprocess.Popen(
                    [sys.executable, str(worker), scripts_dir, str(root), str(i)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                for i in range(n_proc)
            ]
            for p in procs:
                _, err = p.communicate()
                self.assertEqual(p.returncode, 0, msg=err.decode("utf-8", "replace"))

            blocks, problems = lib.read_handoff(root / "交接" / f"{task_id}.md")

        self.assertEqual(len(blocks), n_proc * per_proc)
        self.assertEqual(problems, [])
        self.assertEqual(len({b.ts for b in blocks}), n_proc * per_proc)

    def test_ledger_concurrent_update_different_rows(self) -> None:
        """T3：3 线程各更新不同任务行的状态 → 3 行都改到（无互相覆盖）。"""
        targets = {
            "WK-20260101-01": "已完成",
            "WK-20260101-02": "待审",
            "WK-20260101-03": "暂停",
        }
        with tempfile.TemporaryDirectory() as td:
            root = make_root(
                Path(td),
                row("WK-20260101-01", "A", "抖音", "codex", "进行中", "2026-01-01 10:00")
                + row("WK-20260101-02", "B", "抖音", "codex", "进行中", "2026-01-01 10:00")
                + row("WK-20260101-03", "C", "抖音", "codex", "进行中", "2026-01-01 10:00"))
            ledger_path = root / "任务台账.md"

            def worker(tid: str, status: str) -> None:
                led = lib.parse_ledger(ledger_path)
                task = led.by_id(tid)
                task.status = status
                task.updated = "2026-01-01 11:00"
                lib.update_ledger_row(led, task)

            threads = [threading.Thread(target=worker, args=(tid, st))
                       for tid, st in targets.items()]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            led = lib.parse_ledger(ledger_path)

        for tid, st in targets.items():
            self.assertEqual(led.by_id(tid).status, st, f"{tid} 状态被覆盖")

    def test_nested_lock_and_append_no_deadlock(self) -> None:
        """T4：append_handoff_block（内部调 sync_handoff_status）5s 内返回；locked 同路径嵌套两层不卡。"""
        task_id = "WK-20260101-01"
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            start = time.monotonic()
            path, wrote = lib.append_handoff_block(
                root, make_block("2026-01-01T10:00", "codex", task_id), "t")
            elapsed = time.monotonic() - start
            self.assertTrue(wrote)
            self.assertLess(elapsed, 5.0)

            p = root / "任务台账.md"
            with lib.locked(p):
                with lib.locked(p):
                    pass

    def test_no_residue_and_write_text_crlf(self) -> None:
        """T5：一次追加后目标目录无 .tmp-* / .lock；write_text_file 仍产出 CRLF。"""
        task_id = "WK-20260101-01"
        with tempfile.TemporaryDirectory() as td:
            root = make_root(Path(td))
            lib.append_handoff_block(root, make_block("2026-01-01T10:00", "codex", task_id), "t")

            for d in (root, root / "交接"):
                leftovers = [p.name for p in d.iterdir()
                             if p.name.endswith(".lock") or ".tmp-" in p.name]
                self.assertEqual(leftovers, [], f"{d} 残留: {leftovers}")

            p = root / "任务台账.md"
            lib.write_text_file(p, "a\nb\n")
            raw = p.read_bytes()

        self.assertEqual(raw, b"a\r\nb\r\n")


if __name__ == "__main__":
    unittest.main()
