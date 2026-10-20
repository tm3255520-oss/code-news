#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""find_duplicate_models.py 的单元测试

覆盖 2026-10-20 实战踩出的四条纪律：
1. 同体积不同内容 → 不算重复
2. 符号链接 → 跳过，不算重复
3. 硬链接化 → 两条路径都在、哈希不变、inode 相同、可回滚
4. 默认 dry-run，不动文件系统
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import find_duplicate_models as fdm  # noqa: E402


class TestCollectAndDetect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fdm_test_")
        self.a_dir = os.path.join(self.tmp, "a")
        self.b_dir = os.path.join(self.tmp, "b")
        os.makedirs(self.a_dir)
        os.makedirs(self.b_dir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, path, size, filler=b"x"):
        with open(path, "wb") as fh:
            fh.write(filler * size)

    def test_same_content_different_path_is_duplicate(self):
        """同内容不同路径 → 判为重复"""
        p1 = os.path.join(self.a_dir, "m1.safetensors")
        p2 = os.path.join(self.b_dir, "m1.safetensors")
        self._write(p1, 1024, b"a")
        self._write(p2, 1024, b"a")
        files, _ = fdm.collect_files([self.a_dir, self.b_dir], 512)
        groups = fdm.find_duplicate_groups(files, progress=False)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["reclaimable"], 1024)

    def test_same_size_different_content_not_duplicate(self):
        """同体积不同内容 → 不算重复（15 个 0.67GB controlnet 的教训）"""
        p1 = os.path.join(self.a_dir, "cn1.safetensors")
        p2 = os.path.join(self.b_dir, "cn2.safetensors")
        self._write(p1, 1024, b"a")
        self._write(p2, 1024, b"b")
        files, _ = fdm.collect_files([self.a_dir, self.b_dir], 512)
        groups = fdm.find_duplicate_groups(files, progress=False)
        self.assertEqual(groups, [])

    def test_symlink_skipped(self):
        """符号链接 → 跳过，不算第二份拷贝"""
        target = os.path.join(self.a_dir, "real.bin")
        self._write(target, 1024, b"a")
        link = os.path.join(self.b_dir, "link.bin")
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            self.skipTest("本机无法创建符号链接")
        files, skipped = fdm.collect_files([self.a_dir, self.b_dir], 512)
        self.assertEqual(len(files), 1)
        self.assertTrue(any("link.bin" in s or "b" in s for s in skipped))
        groups = fdm.find_duplicate_groups(files, progress=False)
        self.assertEqual(groups, [])

    def test_min_size_filter(self):
        p1 = os.path.join(self.a_dir, "small.bin")
        p2 = os.path.join(self.b_dir, "small.bin")
        self._write(p1, 10, b"a")
        self._write(p2, 10, b"a")
        files, _ = fdm.collect_files([self.a_dir, self.b_dir], 1024)
        self.assertEqual(files, [])

    def test_already_hardlinked_group_is_not_reclaimable(self):
        """已硬链接化的一组 → 仍算重复组，但**可回收记 0**（不能重复统计）"""
        p1 = os.path.join(self.a_dir, "m1.safetensors")
        p2 = os.path.join(self.b_dir, "m1.safetensors")
        self._write(p1, 1024, b"a")
        os.link(p1, p2)
        files, _ = fdm.collect_files([self.a_dir, self.b_dir], 512)
        groups = fdm.find_duplicate_groups(files, progress=False)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["already_linked"])
        self.assertEqual(groups[0]["reclaimable"], 0)


class TestHardlinkify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fdm_hl_")
        self.keep = os.path.join(self.tmp, "keep.bin")
        self.dup = os.path.join(self.tmp, "dup.bin")
        with open(self.keep, "wb") as fh:
            fh.write(b"A" * 4096)
        with open(self.dup, "wb") as fh:
            fh.write(b"A" * 4096)
        self.group = {
            "size": 4096,
            "sha256": fdm.sha256_of(self.keep),
            "paths": sorted([self.keep, self.dup]),
            "reclaimable": 4096,
        }

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_does_not_touch_filesystem(self):
        before = os.stat(self.dup).st_ino
        fdm.hardlink_ify(self.group, self.keep, dry_run=True)
        self.assertTrue(os.path.exists(self.dup))
        self.assertEqual(os.stat(self.dup).st_ino, before)

    def test_apply_keeps_both_paths_and_same_inode(self):
        fdm.hardlink_ify(self.group, self.keep, dry_run=False)
        self.assertTrue(os.path.exists(self.keep))
        self.assertTrue(os.path.exists(self.dup))          # 路径没丢
        self.assertEqual(os.stat(self.keep).st_ino, os.stat(self.dup).st_ino)
        self.assertEqual(fdm.sha256_of(self.dup), self.group["sha256"])
        self.assertEqual(os.path.getsize(self.dup), 4096)

    def test_rollback_restores_independent_copy(self):
        fdm.hardlink_ify(self.group, self.keep, dry_run=False)
        self.assertEqual(os.stat(self.keep).st_ino, os.stat(self.dup).st_ino)
        record = os.path.join(self.tmp, "rec.json")
        import json

        json.dump(
            {"groups": [{"keep": self.keep, "sha256": self.group["sha256"], "size": 4096,
                         "results": [{"dup": self.dup, "status": "ok", "size": 4096}]}]},
            open(record, "w", encoding="utf-8"),
        )
        fdm.rollback(record)
        self.assertTrue(os.path.exists(self.dup))
        self.assertNotEqual(os.stat(self.keep).st_ino, os.stat(self.dup).st_ino)
        self.assertEqual(fdm.sha256_of(self.dup), self.group["sha256"])


class TestPickKeep(unittest.TestCase):
    def test_prefer_prefix_wins(self):
        g = {"paths": [r"C:\z\a.bin", r"D:\models\a.bin"], "size": 1, "sha256": "x", "reclaimable": 1}
        self.assertEqual(fdm.pick_keep(g, [r"D:\models"]), r"D:\models\a.bin")

    def test_fallback_to_sorted_first(self):
        g = {"paths": [r"C:\b\a.bin", r"C:\a\a.bin"], "size": 1, "sha256": "x", "reclaimable": 1}
        self.assertEqual(fdm.pick_keep(g, []), r"C:\a\a.bin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
