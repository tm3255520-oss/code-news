#!/usr/bin/env python3
"""Audit benchmark registry coverage against configured content domains."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_daily_content_ops import load_benchmark_registry, read_json, resolve_registry_request
except ModuleNotFoundError:
    from run_daily_content_ops import load_benchmark_registry, read_json, resolve_registry_request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "config" / "benchmark_source_registry.json"
DEFAULT_DOMAINS_PATH = ROOT / "config" / "content_domains.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / ".tmp" / "benchmark-registry-audit.md"
DEFAULT_MAX_SOURCE_AGE_DAYS = 14


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit benchmark registry coverage.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH, help="Registry config path.")
    parser.add_argument("--domains", type=Path, default=DEFAULT_DOMAINS_PATH, help="Content domains config path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
        help="Optional markdown audit output path.",
    )
    parser.add_argument(
        "--max-source-age-days",
        type=int,
        default=DEFAULT_MAX_SOURCE_AGE_DAYS,
        help="Warn when a benchmark source snapshot is older than this many days.",
    )
    return parser.parse_args()


def load_domains(path: Path) -> dict[str, Any]:
    data = read_json(path, {})
    return data if isinstance(data, dict) else {}


def iter_domain_tokens(domains: dict[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for domain_id, meta in (domains.get("domains") or {}).items():
        output.append({"domainId": str(domain_id), "token": str(domain_id), "tokenType": "domain"})
        for alias in meta.get("aliases", []) or []:
            alias_text = str(alias).strip()
            if alias_text:
                output.append(
                    {
                        "domainId": str(domain_id),
                        "token": alias_text,
                        "tokenType": "alias",
                    }
                )
    return output


def count_source_records(path: Path) -> int | None:
    data = read_json(path, None)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("items", "records", "data", "results", "articles"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        if any(key in data for key in ("title", "summary", "url")):
            return 1
        return 0

    if path.suffix.lower() == ".jsonl":
        try:
            return sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())
        except OSError:
            return None
    return None


def inspect_source_snapshot(path: str | None, *, now: datetime, max_source_age_days: int) -> dict[str, Any]:
    if not path:
        return {
            "inputPath": None,
            "inputPathExists": False,
            "recordCount": None,
            "sourceLastModifiedAt": None,
            "sourceAgeDays": None,
            "sourceIsEmpty": False,
            "sourceIsStale": False,
        }

    source_path = Path(path)
    exists = source_path.exists()
    if not exists:
        return {
            "inputPath": str(source_path),
            "inputPathExists": False,
            "recordCount": None,
            "sourceLastModifiedAt": None,
            "sourceAgeDays": None,
            "sourceIsEmpty": False,
            "sourceIsStale": False,
        }

    modified_at = datetime.fromtimestamp(source_path.stat().st_mtime)
    age_days = max(0, int((now - modified_at).total_seconds() // 86400))
    record_count = count_source_records(source_path)
    return {
        "inputPath": str(source_path),
        "inputPathExists": True,
        "recordCount": record_count,
        "sourceLastModifiedAt": modified_at.isoformat(timespec="seconds"),
        "sourceAgeDays": age_days,
        "sourceIsEmpty": record_count == 0,
        "sourceIsStale": age_days > max_source_age_days,
    }


def audit_benchmark_registry(
    *,
    registry_path: Path,
    domains_path: Path,
    max_source_age_days: int = DEFAULT_MAX_SOURCE_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    registry = load_benchmark_registry(registry_path)
    domains = load_domains(domains_path)
    current_time = now or datetime.now()
    coverage: list[dict[str, Any]] = []
    missing_tokens: list[str] = []
    missing_source_paths: list[dict[str, Any]] = []
    empty_source_paths: list[dict[str, Any]] = []
    stale_source_paths: list[dict[str, Any]] = []
    seen_missing_keys: set[str] = set()
    seen_empty_keys: set[str] = set()
    seen_stale_keys: set[str] = set()

    for item in iter_domain_tokens(domains):
        key, request = resolve_registry_request(
            {
                "title": "registry audit",
                "summary": "registry audit",
                "article_blocks": [],
                "domain": item["token"],
            },
            registry,
            registry_path,
        )
        source_snapshot = inspect_source_snapshot(
            str((request or {}).get("inputPath") or "").strip() or None,
            now=current_time,
            max_source_age_days=max_source_age_days,
        )
        coverage.append(
            {
                **item,
                "registryKey": key,
                **source_snapshot,
            }
        )
        if not key:
            missing_tokens.append(item["token"])
            continue
        input_path = source_snapshot["inputPath"]
        if input_path and not source_snapshot["inputPathExists"] and key not in seen_missing_keys:
            seen_missing_keys.add(key)
            missing_source_paths.append(
                {
                    "registryKey": key,
                    "inputPath": input_path,
                }
            )
        if source_snapshot["inputPathExists"] and source_snapshot["sourceIsEmpty"] and key not in seen_empty_keys:
            seen_empty_keys.add(key)
            empty_source_paths.append(
                {
                    "registryKey": key,
                    "inputPath": input_path,
                    "recordCount": source_snapshot["recordCount"],
                }
            )
        if source_snapshot["inputPathExists"] and source_snapshot["sourceIsStale"] and key not in seen_stale_keys:
            seen_stale_keys.add(key)
            stale_source_paths.append(
                {
                    "registryKey": key,
                    "inputPath": input_path,
                    "sourceAgeDays": source_snapshot["sourceAgeDays"],
                    "sourceLastModifiedAt": source_snapshot["sourceLastModifiedAt"],
                }
            )

    status = (
        "ok"
        if not missing_tokens and not missing_source_paths and not empty_source_paths and not stale_source_paths
        else "warning"
    )
    return {
        "status": status,
        "registryPath": str(registry_path),
        "domainsPath": str(domains_path),
        "maxSourceAgeDays": max_source_age_days,
        "summary": {
            "domainCount": len((domains.get("domains") or {}).keys()),
            "tokenCount": len(coverage),
            "coveredTokenCount": sum(1 for item in coverage if item.get("registryKey")),
            "missingTokenCount": len(missing_tokens),
            "missingSourcePathCount": len(missing_source_paths),
            "emptySourcePathCount": len(empty_source_paths),
            "staleSourcePathCount": len(stale_source_paths),
        },
        "missingTokens": missing_tokens,
        "missingSourcePaths": missing_source_paths,
        "emptySourcePaths": empty_source_paths,
        "staleSourcePaths": stale_source_paths,
        "coverage": coverage,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    summary = audit.get("summary", {})
    lines = [
        "# Benchmark Registry Audit",
        "",
        f"- Status: `{audit.get('status', 'unknown')}`",
        f"- Domains: `{summary.get('domainCount', 0)}`",
        f"- Tokens: `{summary.get('tokenCount', 0)}`",
        f"- Covered tokens: `{summary.get('coveredTokenCount', 0)}`",
        f"- Missing tokens: `{summary.get('missingTokenCount', 0)}`",
        f"- Missing source paths: `{summary.get('missingSourcePathCount', 0)}`",
        f"- Empty source paths: `{summary.get('emptySourcePathCount', 0)}`",
        f"- Stale source paths: `{summary.get('staleSourcePathCount', 0)}`",
        "",
        "## Missing Tokens",
        "",
    ]

    if audit.get("missingTokens"):
        lines.extend([f"- `{token}`" for token in audit["missingTokens"]])
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Missing Source Paths",
            "",
        ]
    )
    if audit.get("missingSourcePaths"):
        lines.extend(
            [
                f"- `{item['registryKey']}` -> `{item['inputPath']}`"
                for item in audit["missingSourcePaths"]
            ]
        )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Empty Source Paths",
            "",
        ]
    )
    if audit.get("emptySourcePaths"):
        lines.extend(
            [
                f"- `{item['registryKey']}` -> `{item['inputPath']}` (records={item['recordCount']})"
                for item in audit["emptySourcePaths"]
            ]
        )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Stale Source Paths",
            "",
        ]
    )
    if audit.get("staleSourcePaths"):
        lines.extend(
            [
                f"- `{item['registryKey']}` -> `{item['inputPath']}` (age={item['sourceAgeDays']}d)"
                for item in audit["staleSourcePaths"]
            ]
        )
    else:
        lines.append("- none")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    audit = audit_benchmark_registry(
        registry_path=args.registry.resolve(),
        domains_path=args.domains.resolve(),
        max_source_age_days=args.max_source_age_days,
    )
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
