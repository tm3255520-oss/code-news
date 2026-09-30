"""协同三件套（work_lookup / handoff_append / xietong_audit / xietong_weekly）单元测试。

全部在临时目录里跑（`--root` 指过去），不触碰真实 vault。
"""
from __future__ import annotations

import io
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()
