#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_check.py — 全套单元测试回归薄件（供 collect_material_batch.py 的 audit3d 组调用）。

跑 `python -m unittest discover -s tests -t .`（cwd=仓库根）。
成功：静默 exit 0（巡检类成功即静默，配合批任务 --quiet-ok 不外发）。
失败：打印 unittest 输出末尾若干行并 exit 1（由批任务放大为飞书告警）。

仅供自检：`--tests-dir <目录>`（默认 tests）可把 -s 指向临时目录，并把该目录同时作为
-t（自包含、可导入），用于验证失败分支。**批任务不传此参数。**
"""
import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAIL_LINES = 60


def _reconfigure_stdio():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None):
    _reconfigure_stdio()
    parser = argparse.ArgumentParser(description="全套单元测试回归薄件（audit3d 组成员）")
    parser.add_argument(
        "--tests-dir",
        default="tests",
        help="仅供自检：指定 -s 起始目录（默认 tests）。自检时指向临时目录并同时作为 -t；批任务不传此参数。",
    )
    args = parser.parse_args(argv)

    if args.tests_dir == "tests":
        # 正式路径：-s tests -t .（仓库根）。
        start, top = "tests", "."
    else:
        # 自检路径：临时目录自包含（同时作为 -s 与 -t），避免「Start directory is not importable」。
        start = top = args.tests_dir

    cmd = [sys.executable, "-m", "unittest", "discover", "-s", start, "-t", top]
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode == 0:
        return 0

    # 失败：合并 stdout/stderr（跳过空流，避免多余空行），打印末尾若干行
    #（unittest 的 traceback 与 FAILED 摘要落在 stderr）。
    body = "\n".join(x for x in ((r.stdout or ""), (r.stderr or "")) if x.strip()).rstrip("\n")
    lines = body.splitlines() if body.strip() else []
    tail = lines[-TAIL_LINES:] if len(lines) > TAIL_LINES else lines
    for line in tail:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
