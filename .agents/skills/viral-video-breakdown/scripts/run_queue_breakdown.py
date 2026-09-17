#!/usr/bin/env python3
"""
run_queue_breakdown.py - 按拆解队列逐条拆解（🔵 编排）

读 breakdown_queue.md 的第一条待拆解（`- [ ]`），提取 B站 URL，
调用 run_breakdown.py 产出拆解报告，成功后把该行勾选为 `- [x]`。

用法:
  python run_queue_breakdown.py [--queue breakdown_queue.md] [--out-root <dir>]

输出: <out-root>/<date>_<bvid>/爆款拆解报告.md
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_QUEUE = SCRIPT_DIR.parent.parent.parent.parent / "research" / "dsh-std-video-analysis" / "breakdown_queue.md"
DEFAULT_OUT = SCRIPT_DIR.parent.parent.parent.parent / "research" / "dsh-std-video-analysis" / "breakdowns"

URL_RE = re.compile(r"https?://\S+")


def first_pending(queue: Path):
    lines = queue.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("- [ ]"):
            m = URL_RE.search(line)
            if not m:
                continue
            return i, line.strip(), m.group(0)
    return None, None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=str(DEFAULT_QUEUE))
    ap.add_argument("--out-root", default=str(DEFAULT_OUT))
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    queue = Path(args.queue)
    idx, line, url = first_pending(queue)
    if not line:
        print("拆解队列已清空（无可拆解条目）")
        return 0

    bvid_m = re.search(r"BV[0-9A-Za-z]+", url)
    bvid = bvid_m.group(0) if bvid_m else "unknown"
    out_dir = Path(args.out_root) / f"{datetime.now().strftime('%Y%m%d')}_{bvid}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"正在拆解: {bvid}")
    print(f"  {line}")
    print(f"  输出: {out_dir}")

    cmd = [args.python, str(SCRIPT_DIR / "run_breakdown.py"), url, str(out_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1500)
    print("run_breakdown exit:", proc.returncode)
    if proc.stdout:
        print(proc.stdout[-3000:])
    if proc.stderr:
        print("STDERR:", proc.stderr[-1000:])

    report = out_dir / "爆款拆解报告.md"
    if report.exists():
        # 勾选队列
        lines = queue.read_text(encoding="utf-8").splitlines()
        lines[idx] = lines[idx].replace("- [ ]", "- [x]", 1)
        # 追加到已完成
        done_idx = next((i for i, l in enumerate(lines) if l.strip() == "## 已完成"), len(lines))
        lines.insert(done_idx + 1, f"- [x] {lines[idx].strip()[5:]}  （{datetime.now().strftime('%Y-%m-%d %H:%M')}）")
        queue.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"OK: 拆解完成，队列已更新 → {report}")
        return 0

    print("FAIL: 未生成拆解报告（见上方错误）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
