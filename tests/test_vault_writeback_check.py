#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vault_writeback_check.py 的单元测试

覆盖：
1. 分类器：vault 外改动 → 需要哪几类落点；vault 内改动**不**参与
2. 台账解析：读出产出列 + 时间
3. 落点检测：since 之后该目录有文件才算已落
4. 回链段体检
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import vault_writeback_check as vwc  # noqa: E402


class TestClassify(unittest.TestCase):
    def test_cron_change_needs_decision_and_summary(self):
        hits = vwc.classify([r"C:\Users\Administrator\.hermes\cron\jobs.json"])
        self.assertIn("决策", hits)
        self.assertIn("运行小结", hits)

    def test_code_script_needs_tool_doc(self):
        hits = vwc.classify([r"C:\Users\Administrator\Documents\code-news\scripts\foo.py"])
        self.assertIn("工具档案", hits)

    def test_aivideo_script_needs_tool_doc(self):
        hits = vwc.classify([r"D:\AI-VIDEO\scripts\bar.py"])
        self.assertIn("工具档案", hits)
        self.assertIn("运行小结", hits)

    def test_vault_internal_change_is_not_classified(self):
        """vault 内的改动本身就是落点，不该再要求登记"""
        hits = vwc.classify([r"D:\Obsidian Vault\obsidian Vault\系统中枢\运行手册\x.md"])
        self.assertEqual(hits, {})

    def test_skill_change_needs_skill_changelog(self):
        hits = vwc.classify([r"C:\Users\Administrator\.agents\skills\foo\SKILL.md"])
        self.assertIn("技能变更日志", hits)

    def test_unknown_path_no_hit(self):
        hits = vwc.classify([r"C:\Windows\System32\drivers\etc\hosts"])
        self.assertEqual(hits, {})


class TestInVault(unittest.TestCase):
    def test_normalisation(self):
        self.assertTrue(vwc.in_vault(r"D:\Obsidian Vault\obsidian Vault\a\b.md"))
        self.assertTrue(vwc.in_vault(r"D:/Obsidian Vault/obsidian Vault/a/b.md"))
        self.assertFalse(vwc.in_vault(r"D:\AI-VIDEO\x.md"))


class TestBacklink(unittest.TestCase):
    def test_backlink_detected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write("# T\n\n## 回链\n- [[x]]\n")
        p = fh.name
        try:
            self.assertTrue(vwc.has_backlink(p))
        finally:
            os.remove(p)

    def test_missing_backlink(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write("# T\n\n没有回链段。\n")
        p = fh.name
        try:
            self.assertFalse(vwc.has_backlink(p))
        finally:
            os.remove(p)


class TestLedgerParsing(unittest.TestCase):
    def test_parse_ledger_row(self):
        tmp = tempfile.mkdtemp(prefix="vwc_")
        ledger = os.path.join(tmp, "任务台账.md")
        with open(ledger, "w", encoding="utf-8") as fh:
            fh.write(
                "| 任务ID | 标题 | 平台 | 负责人 | 状态 | 更新时间 | 产出路径 | 交接 |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| WK-20260101-01 | 测试任务 | 参考库 | opencode | 已完成 | 2026-01-01 12:34 | "
                "D:/a/x.md, D:/b/y.py | 协同/交接/WK-20260101-01.md |\n"
            )
        old_led, old_vault = vwc.LEDGER, vwc.VAULT
        vwc.LEDGER = ledger
        try:
            paths, ts = vwc.changed_from_ledger("WK-20260101-01")
            self.assertEqual(paths, ["D:/a/x.md", "D:/b/y.py"])
            self.assertIsNotNone(ts)
            self.assertEqual(ts.year, 2026)
        finally:
            vwc.LEDGER = old_led
            vwc.VAULT = old_vault
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_task_returns_empty(self):
        paths, ts = vwc.changed_from_ledger("WK-NOT-EXIST-XX")
        self.assertEqual(paths, [])
        self.assertIsNone(ts)


class TestLandedFiles(unittest.TestCase):
    def test_landed_files_respects_since(self):
        tmp = tempfile.mkdtemp(prefix="vwc_l_")
        d = os.path.join(tmp, "决策")
        os.makedirs(d)
        f = os.path.join(d, "2026-01-01-x.md")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("# x")
        old_route = vwc.route_dir
        vwc.route_dir = lambda kind: d
        try:
            self.assertEqual(len(vwc.landed_files("决策", None)), 1)
            future = datetime.datetime.now() + datetime.timedelta(days=1)
            self.assertEqual(len(vwc.landed_files("决策", future)), 0)
        finally:
            vwc.route_dir = old_route
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


class TestCheckPaths(unittest.TestCase):
    """产出路径存在性检查（防路径笔误）—— 2026-10-21 同一个笔误一天犯了三次"""

    def test_missing_path_detected(self):
        import tempfile as tf

        tmp = tf.mkdtemp(prefix="vwc_p_")
        real = os.path.join(tmp, "real.md")
        with open(real, "w", encoding="utf-8") as fh:
            fh.write("# x")
        fake = os.path.join(tmp, "typo.md")
        old_led = vwc.LEDGER
        ledger = os.path.join(tmp, "台账.md")
        with open(ledger, "w", encoding="utf-8") as fh:
            fh.write(
                "| 任务ID | 标题 | 平台 | 负责人 | 状态 | 更新时间 | 产出路径 | 交接 |\n"
                "|---|---|---|---|---|---|---|---|\n"
                f"| WK-20260101-02 | t | p | opencode | 已完成 | 2026-01-01 10:00 | "
                f"{real.replace(chr(92), '/')}, {fake.replace(chr(92), '/')} | h.md |\n"
            )
        vwc.LEDGER = ledger
        try:
            rc = vwc.main(["--ledger", "WK-20260101-02", "--check-paths"])
            self.assertEqual(rc, 1)  # 有不存在的路径 → 退出码 1
        finally:
            vwc.LEDGER = old_led
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)

    def test_all_paths_exist_returns_zero(self):
        import tempfile as tf

        tmp = tf.mkdtemp(prefix="vwc_p2_")
        real = os.path.join(tmp, "real.md")
        with open(real, "w", encoding="utf-8") as fh:
            fh.write("# x")
        old_led = vwc.LEDGER
        ledger = os.path.join(tmp, "台账.md")
        with open(ledger, "w", encoding="utf-8") as fh:
            fh.write(
                "| 任务ID | 标题 | 平台 | 负责人 | 状态 | 更新时间 | 产出路径 | 交接 |\n"
                "|---|---|---|---|---|---|---|---|\n"
                f"| WK-20260101-03 | t | p | opencode | 已完成 | 2026-01-01 10:00 | "
                f"{real.replace(chr(92), '/')} | h.md |\n"
            )
        vwc.LEDGER = ledger
        try:
            rc = vwc.main(["--ledger", "WK-20260101-03", "--check-paths"])
            self.assertEqual(rc, 0)
        finally:
            vwc.LEDGER = old_led
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
