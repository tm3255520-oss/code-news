from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.web_scraper_contracts import write_jsonl
except ModuleNotFoundError:
    from web_scraper_contracts import write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build benchmark monitor artifacts from normalized records.")
    parser.add_argument("records_path", type=Path, help="Normalized JSONL records path.")
    parser.add_argument("output_dir", type=Path, help="Generated output directory.")
    parser.add_argument("--slug", required=True, help="Content slug.")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def build_markdown(rows: list[dict[str, Any]], slug: str) -> str:
    lines = [
        "# Benchmark Monitor",
        "",
        f"- Slug: `{slug}`",
        f"- Record count: `{len(rows)}`",
        "",
        "## Platform Summary",
        "",
    ]

    by_platform: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_platform.setdefault(row["platform"], []).append(row)

    for platform, items in sorted(by_platform.items()):
        avg_views = sum(item["metrics"]["views"] for item in items) / max(len(items), 1)
        lines.append(f"- {platform}: `{len(items)}` records, avg views `{avg_views:.0f}`")

    lines.extend(["", "## Sample Records", ""])
    ranked = sorted(rows, key=lambda item: item["metrics"]["views"], reverse=True)
    for row in ranked[:10]:
        lines.append(
            "- "
            f"{row['platform']} | {row['author']} | `{row['metrics']['views']}` views | "
            f"{row['title']}"
        )
    return "\n".join(lines).strip() + "\n"


def run_benchmark_monitor(records_path: Path, output_dir: Path, *, slug: str) -> dict[str, Any]:
    rows = read_jsonl(records_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_copy = output_dir / "benchmark-records.jsonl"
    markdown_path = output_dir / "benchmark-monitor.md"

    write_jsonl(normalized_copy, rows)
    markdown_path.write_text(build_markdown(rows, slug), encoding="utf-8")

    return {
        "slug": slug,
        "recordCount": len(rows),
        "recordsPath": str(normalized_copy),
        "markdownPath": str(markdown_path),
    }


def main() -> int:
    args = parse_args()
    result = run_benchmark_monitor(args.records_path, args.output_dir, slug=args.slug)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
