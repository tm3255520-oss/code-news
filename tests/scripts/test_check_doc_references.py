"""check_doc_references.py 的回归测试。

重点守两条：
1. 「工具登记专区」（自研 skill / MCP 与脚本工具链的登记目录）必须被纳入扫描；
   这些文档同样在复制路径知识，不扫就等于专区内的断链无人发现。
2. 专区目录不存在时不得报错，也不得往 targets 里塞不存在的路径。
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_references.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_doc_references", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 必须先登记进 sys.modules：脚本用了 @dataclass，dataclasses 在解析注解时
    # 会回查 cls.__module__ 对应的模块对象，未登记会报 NoneType.__dict__。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RegistryZoneTargetTests(unittest.TestCase):
    def setUp(self):
        self.cr = _load_script()
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        manual = self.vault / "系统中枢" / "运行手册"
        manual.mkdir(parents=True)
        (manual / "a.md").write_text("# a\n", encoding="utf-8")
        self.manual_doc = manual / "a.md"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_zone_doc(self, zone, body="# x\n"):
        zone_dir = self.vault / "系统中枢" / zone
        zone_dir.mkdir(parents=True, exist_ok=True)
        doc = zone_dir / "x.md"
        doc.write_text(body, encoding="utf-8")
        return doc

    def _scan(self):
        return self.cr.scan(
            self.cr.default_targets(self.vault),
            [self.vault],
            self.cr.known_prefix_map(self.vault),
            {},
        )

    def test_registry_zone_names_are_declared(self):
        self.assertEqual(
            tuple(self.cr.REGISTRY_ZONES),
            ("系统skills以及MCP", "系统脚本工具链"),
        )

    def test_zone_docs_are_scanned_when_present(self):
        targets = {str(p) for p in self.cr.default_targets(self.vault)}
        for zone in self.cr.REGISTRY_ZONES:
            doc = self._make_zone_doc(zone)
            targets = {str(p) for p in self.cr.default_targets(self.vault)}
            self.assertIn(str(doc), targets, f"{zone} 的文档未被纳入扫描")

    def test_absent_zones_do_not_break_or_ghost(self):
        targets = self.cr.default_targets(self.vault)
        self.assertIn(self.manual_doc, targets)
        for p in targets:
            self.assertTrue(p.is_file(), f"targets 里出现了不存在的路径: {p}")

    def test_no_duplicate_targets(self):
        for zone in self.cr.REGISTRY_ZONES:
            self._make_zone_doc(zone)
        lowered = [str(p).lower() for p in self.cr.default_targets(self.vault)]
        self.assertEqual(len(lowered), len(set(lowered)))

    def test_broken_ref_inside_zone_doc_is_reported_missing(self):
        doc = self._make_zone_doc(
            "系统脚本工具链", "见 `系统中枢/运行手册/根本没有这份.md`\n"
        )
        findings, _ = self._scan()
        missing = [
            f
            for f in findings
            if f.status == self.cr.MISSING and str(f.doc) == str(doc)
        ]
        self.assertEqual(len(missing), 1, "专区文档里的断链未被校验出来")
        self.assertIn("根本没有这份", missing[0].ref)

    def test_valid_ref_inside_zone_doc_is_ok(self):
        (self.vault / "系统中枢" / "运行手册" / "真手册.md").write_text(
            "# 真\n", encoding="utf-8"
        )
        doc = self._make_zone_doc(
            "系统skills以及MCP", "见 `系统中枢/运行手册/真手册.md`\n"
        )
        findings, _ = self._scan()
        statuses = {f.status for f in findings if str(f.doc) == str(doc)}
        self.assertEqual(statuses, {self.cr.OK})


if __name__ == "__main__":
    unittest.main()
