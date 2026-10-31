#!/usr/bin/env python3
"""Inventory Markdown, wiki, and external links in an Obsidian-style vault."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

try:
    from .safe_io import InputRootError, safe_write_text, validate_input_root
    from .markdown_links import MARKDOWN_IMAGE_RE, split_destination_suffix
    from .check_obsidian_links import (
        MARKDOWN_LINK_RE,
        is_external as is_external_target,
        text_without_code,
        unescape_markdown_destination,
    )
    from .check_vault_quality import markdown_files as safe_markdown_files
except ImportError:
    from safe_io import InputRootError, safe_write_text, validate_input_root
    from markdown_links import MARKDOWN_IMAGE_RE, split_destination_suffix
    from check_obsidian_links import (
        MARKDOWN_LINK_RE,
        is_external as is_external_target,
        text_without_code,
        unescape_markdown_destination,
    )
    from check_vault_quality import markdown_files as safe_markdown_files


WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
EXTERNAL_URL_RE = re.compile(r"\b(?:https?://|mailto:)[^\s<>\]]+")
@dataclass(frozen=True)
class FileInventory:
    file: str
    directory: str
    markdown_links: list[str]
    wiki_links: list[str]
    external_links: list[str]
    unique_targets: list[str]
    counts: dict[str, int]


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def markdown_files(root: Path, excluded_paths: set[Path] | None = None) -> list[Path]:
    root = validate_input_root(root)
    excluded = {path.expanduser().absolute() for path in (excluded_paths or set())}
    return [path for path in safe_markdown_files(root) if path.absolute() not in excluded]


def is_external(target: str) -> bool:
    return is_external_target(unwrap_angle_destination(target))


def unwrap_angle_destination(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        return target[1:-1]
    return target


def clean_target(target: str) -> str:
    target = unwrap_angle_destination(target)
    target = split_destination_suffix(target)
    return unquote(unescape_markdown_destination(target)).strip()


def clean_external_target(target: str) -> str:
    return unescape_markdown_destination(unwrap_angle_destination(target)).strip()


def trim_external_url(target: str) -> str:
    target = target.rstrip(".,;")
    while target.endswith(")") and target.count(")") > target.count("("):
        target = target[:-1]
    return target


def inventory_file(root: Path, path: Path) -> FileInventory:
    text = text_without_code(path.read_text(encoding="utf-8", errors="replace"))
    markdown_links: list[str] = []
    wiki_links: list[str] = []
    external_links: list[str] = []
    markdown_source_spans = sorted(
        (match.start(), match.end())
        for pattern in (MARKDOWN_LINK_RE, MARKDOWN_IMAGE_RE)
        for match in pattern.finditer(text)
    )

    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if is_external(target):
            external_links.append(clean_external_target(target))
            continue
        cleaned = clean_target(target)
        if cleaned:
            markdown_links.append(cleaned)

    for match in WIKI_LINK_RE.finditer(text):
        target = clean_target(match.group(1))
        if target:
            wiki_links.append(target)

    for match in EXTERNAL_URL_RE.finditer(text):
        if any(
            match.start() < source_end and source_start < match.end()
            for source_start, source_end in markdown_source_spans
        ):
            continue
        target = trim_external_url(match.group(0))
        if target not in external_links:
            external_links.append(target)

    unique_targets = sorted(set(markdown_links + wiki_links + external_links))
    relative = path.relative_to(root)
    counts = {
        "markdown_links": len(markdown_links),
        "wiki_links": len(wiki_links),
        "external_links": len(external_links),
        "unique_targets": len(unique_targets),
        "total_links": len(markdown_links) + len(wiki_links) + len(external_links),
    }
    return FileInventory(
        file=str(relative),
        directory=str(relative.parent) if str(relative.parent) != "." else ".",
        markdown_links=markdown_links,
        wiki_links=wiki_links,
        external_links=external_links,
        unique_targets=unique_targets,
        counts=counts,
    )


def build_inventory(root: Path, excluded_paths: set[Path] | None = None) -> dict:
    root = validate_input_root(root)
    files = [inventory_file(root, path) for path in markdown_files(root, excluded_paths)]
    totals = {
        "files": len(files),
        "markdown_links": sum(item.counts["markdown_links"] for item in files),
        "wiki_links": sum(item.counts["wiki_links"] for item in files),
        "external_links": sum(item.counts["external_links"] for item in files),
        "unique_targets": len({target for item in files for target in item.unique_targets}),
        "total_links": sum(item.counts["total_links"] for item in files),
    }
    directories: dict[str, dict[str, int]] = {}
    for item in files:
        counts = directories.setdefault(
            item.directory,
            {"files": 0, "markdown_links": 0, "wiki_links": 0, "external_links": 0, "unique_targets": 0, "total_links": 0},
        )
        counts["files"] += 1
        counts["markdown_links"] += item.counts["markdown_links"]
        counts["wiki_links"] += item.counts["wiki_links"]
        counts["external_links"] += item.counts["external_links"]
        counts["total_links"] += item.counts["total_links"]

    for directory, counts in directories.items():
        targets = {target for item in files if item.directory == directory for target in item.unique_targets}
        counts["unique_targets"] = len(targets)

    return {
        "root": str(root),
        "totals": totals,
        "directories": dict(sorted(directories.items())),
        "files": [asdict(item) for item in files],
    }


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: dict) -> str:
    lines = [
        "# Link Inventory",
        "",
        f"- Root: `{inventory['root']}`",
        f"- Files: {inventory['totals']['files']}",
        f"- Total links: {inventory['totals']['total_links']}",
        f"- Markdown links: {inventory['totals']['markdown_links']}",
        f"- Wiki links: {inventory['totals']['wiki_links']}",
        f"- External links: {inventory['totals']['external_links']}",
        f"- Unique targets: {inventory['totals']['unique_targets']}",
        "",
        "## Directory Counts",
        "",
        "| Directory | Files | Markdown | Wiki | External | Unique Targets | Total |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for directory, counts in inventory["directories"].items():
        lines.append(
            f"| {markdown_escape(directory)} | {counts['files']} | {counts['markdown_links']} | {counts['wiki_links']} | "
            f"{counts['external_links']} | {counts['unique_targets']} | {counts['total_links']} |"
        )

    lines.extend(
        [
            "",
            "## File Counts",
            "",
            "| File | Markdown | Wiki | External | Unique Targets | Total |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in inventory["files"]:
        counts = item["counts"]
        lines.append(
            f"| {markdown_escape(item['file'])} | {counts['markdown_links']} | {counts['wiki_links']} | "
            f"{counts['external_links']} | {counts['unique_targets']} | {counts['total_links']} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    configure_output_encoding()
    parser = argparse.ArgumentParser(description="Inventory Markdown, wiki, and external links in a vault.")
    parser.add_argument("root", type=Path, help="Vault or notes directory")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--out", type=Path, help="Output path. Defaults to stdout.")
    args = parser.parse_args()

    excluded_paths = {args.out} if args.out else set()
    try:
        inventory = build_inventory(args.root, excluded_paths)
    except InputRootError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        output = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    else:
        output = render_markdown(inventory)

    if args.out:
        try:
            safe_write_text(args.out, output)
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(args.out)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
