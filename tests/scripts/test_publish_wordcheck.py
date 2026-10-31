"""退役守卫测试：scripts/_deprecated/publish_wordcheck.py

2026-10-16 发布线统一归口后，publish_wordcheck.py 已退役并移入
scripts/_deprecated/，文件头插入执行守卫（运行即打印停用提示、退出码非 0）。
见 2026-10-16-P0发布线脚本收口清单.md。

原 14 条离线断言（平台归一 / frontmatter 剥离 / 命中提取 / 退出码口径 / 自检）
随被测对象退役不再有意义。本文件改为**退役守卫测试**，把「退役本身」纳入回归网：
断言脚本仍在 _deprecated/、被跑时退出码非 0 且打印停用提示——若有人误把脚本移回
scripts/ 或删掉守卫，此测试会立刻变红。

Run: python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPRECATED = REPO_ROOT / "scripts" / "_deprecated" / "publish_wordcheck.py"


class TestRetiredGuard(unittest.TestCase):
    def test_script_stays_in_deprecated(self) -> None:
        self.assertTrue(DEPRECATED.is_file(),
                        "退役脚本必须留在 scripts/_deprecated/，不许移回 scripts/")

    def test_running_prints_deprecation_notice_and_exits_nonzero(self) -> None:
        # 用字节模式抓取，再按 UTF-8 容错解码——守卫经 sys.exit 把提示写到 stderr，
        # 本机 locale 是 GBK，直接 text=True 会在读取管道时 UnicodeDecodeError。
        proc = subprocess.run(
            [sys.executable, str(DEPRECATED), "--selftest"],
            capture_output=True,
        )
        combined = (proc.stdout or b"").decode("utf-8", "replace") + \
            (proc.stderr or b"").decode("utf-8", "replace")
        self.assertNotEqual(proc.returncode, 0, "退役脚本运行退出码必须非 0")
        self.assertIn("已停用", combined, "退役脚本运行必须打印停用提示")


if __name__ == "__main__":
    unittest.main()
