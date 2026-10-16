"""cron_ledger.py 异常日报分栏判定（classify_failure / _batch_fail_members / _by_design_match）离线单元测试。

只针对「给定一次 FAIL 文本 → 归到哪一栏」的纯函数，不读真实 cron 数据、不联网。
by-design 注册表用 monkeypatch 固定为受控字典，避免依赖 config 文件内容漂移。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from scripts import cron_ledger


def _batch(*rows: str) -> str:
    """构造一段批输出文本；rows 形如 "账号体检总览 ... FAIL(exit=2) 0.1s"。"""
    n = len(rows)
    lines = ["stdout:"]
    for i, r in enumerate(rows, 1):
        lines.append("[%d/%d] %s" % (i, n, r))
    return "\n".join(lines)


class ClassifyFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = cron_ledger.BY_DESIGN_NONZERO
        cron_ledger.BY_DESIGN_NONZERO = {
            "账号体检总览-每日": "有告警即 exit 2",
            "协同三件套巡检": "巡检发现停滞/重复/格式/断链即 exit 1（设计性）",
        }

    def tearDown(self) -> None:
        cron_ledger.BY_DESIGN_NONZERO = self._orig

    def test_pure_by_design_member(self) -> None:
        text = _batch("账号体检总览 ... FAIL(exit=2) 0.1s")
        new, known = cron_ledger.classify_failure(text)
        self.assertEqual(new, [])
        self.assertEqual([m for m, _k, _r in known], ["账号体检总览"])

    def test_pure_unknown_member(self) -> None:
        text = _batch("定时任务总览再生成 ... FAIL(exit=1) 0.1s")
        new, known = cron_ledger.classify_failure(text)
        self.assertEqual(new, ["定时任务总览再生成"])
        self.assertEqual(known, [])

    def test_mixed_members_split(self) -> None:
        text = _batch(
            "账号体检总览 ... FAIL(exit=2) 0.1s",
            "定时任务总览再生成 ... FAIL(exit=1) 0.1s",
            "公众号账号体检 ... OK 34.7s",
        )
        new, known = cron_ledger.classify_failure(text)
        self.assertEqual(new, ["定时任务总览再生成"])
        self.assertEqual([m for m, _k, _r in known], ["账号体检总览"])

    def test_known_item_reason_passthrough(self) -> None:
        text = _batch("账号体检总览 ... FAIL(exit=2) 0.1s")
        _new, known = cron_ledger.classify_failure(text)
        self.assertEqual(known[0], ("账号体检总览", "账号体检总览-每日", "有告警即 exit 2"))

    def test_job_level_failure_no_member_lines(self) -> None:
        text = "**Status:** script failed\nScript exited with code 1"
        new, known = cron_ledger.classify_failure(text)
        self.assertEqual(new, [])
        self.assertEqual(known, [])

    def test_batch_fail_members_ignores_stderr(self) -> None:
        text = (
            "stderr:\n[账号体检总览] stdout（共 5 行）\n"
            + _batch("账号体检总览 ... FAIL(exit=2) 0.1s")
        )
        self.assertEqual(cron_ledger._batch_fail_members(text), ["账号体检总览"])

    def test_by_design_match_prefix(self) -> None:
        self.assertEqual(
            cron_ledger._by_design_match("账号体检总览"),
            ("账号体检总览-每日", "有告警即 exit 2"),
        )
        self.assertIsNone(cron_ledger._by_design_match("定时任务总览再生成"))


class OutputTimestampTests(unittest.TestCase):
    def test_parse_output_timestamp_matches(self) -> None:
        self.assertEqual(
            cron_ledger._parse_output_timestamp("2026-10-16_00-55-21.md"),
            "2026-10-16 00:55:21",
        )

    def test_parse_output_timestamp_no_match(self) -> None:
        self.assertIsNone(cron_ledger._parse_output_timestamp("无时间戳的输出.md"))

    def test_output_timestamp_prefers_filename(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "2026-10-16_09-44-15.md"
            p.write_text("x", encoding="utf-8")
            os.utime(p, (1700000000, 1700000000))  # mtime 与文件名故意不同
            self.assertEqual(cron_ledger.output_timestamp(p), "2026-10-16 09:44:15")

    def test_output_timestamp_mtime_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "no-timestamp.md"
            p.write_text("x", encoding="utf-8")
            target = 1700000000
            os.utime(p, (target, target))
            expected = datetime.fromtimestamp(target).strftime("%Y-%m-%d %H:%M:%S")
            self.assertEqual(cron_ledger.output_timestamp(p), expected)


class NotifyTimestampTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_load = cron_ledger.load_jobs
        self._orig_out = cron_ledger.CRON_OUT
        self._orig_by_design = cron_ledger.BY_DESIGN_NONZERO

    def tearDown(self) -> None:
        cron_ledger.load_jobs = self._orig_load
        cron_ledger.CRON_OUT = self._orig_out
        cron_ledger.BY_DESIGN_NONZERO = self._orig_by_design

    def test_recent_failures_passes_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            job_dir = Path(d) / "job1"
            job_dir.mkdir()
            f = job_dir / "2026-10-16_00-55-21.md"
            f.write_text("**Status:** script failed\nScript exited with code 1", encoding="utf-8")
            cron_ledger.CRON_OUT = Path(d)
            cron_ledger.BY_DESIGN_NONZERO = {}
            cron_ledger.load_jobs = lambda: [
                {"id": "job1", "name": "测试任务", "enabled": True, "last_status": "error"}
            ]
            new_failures, _known, _recovered = cron_ledger.recent_failures(hours=24)
            self.assertEqual(len(new_failures), 1)
            _job, members, ts = new_failures[0]
            self.assertIsNone(members)
            self.assertEqual(ts, "2026-10-16 00:55:21")

    def test_render_notify_includes_failure_time(self) -> None:
        job = {"name": "协同留痕批（3 件）", "last_error": "Script exited with code 1"}
        new_failures = [(job, ["定时任务总览再生成"], "2026-10-16 00:55:21")]
        out = cron_ledger.render_notify_body(new_failures, [], [], 24)
        self.assertIn("失败时间：2026-10-16 00:55:21", out)
        self.assertIn("定时任务总览再生成", out)
        self.assertIn("回响", out)


if __name__ == "__main__":
    unittest.main()
