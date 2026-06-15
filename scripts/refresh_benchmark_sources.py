#!/usr/bin/env python3
"""Refresh local benchmark source snapshots from configured search queries."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT / "config" / "benchmark_source_registry.json"
DEFAULT_WECHAT_SEARCH_SCRIPT = (
    Path.home()
    / ".agents"
    / "skills"
    / "wechat-article-search"
    / "scripts"
    / "search_wechat.js"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh benchmark source snapshots.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH, help="Registry config path.")
    parser.add_argument(
        "--source-key",
        dest="source_keys",
        action="append",
        default=[],
        help="Optional registry key to refresh. Repeat for multiple keys.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Refresh every registry source instead of only stale, missing, or empty ones.",
    )
    return parser.parse_args()


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return fallback


def load_registry(path: Path) -> dict[str, Any]:
    data = read_json(path, {})
    return data if isinstance(data, dict) else {}


def resolve_input_path(registry_path: Path, input_path: str) -> Path:
    candidate = Path(input_path)
    if candidate.is_absolute():
        return candidate
    return (registry_path.parent / candidate).resolve()


def unique_registry_keys(audit: dict[str, Any] | None, source_keys: list[str] | None) -> list[str]:
    if source_keys:
        ordered: list[str] = []
        for key in source_keys:
            normalized = str(key or "").strip()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered

    ordered = []
    for bucket in ("missingSourcePaths", "emptySourcePaths", "staleSourcePaths"):
        for item in audit.get(bucket, []) if isinstance(audit, dict) else []:
            key = str((item or {}).get("registryKey") or "").strip()
            if key and key not in ordered:
                ordered.append(key)
    return ordered


def build_refresh_jobs(
    *,
    registry_path: Path,
    audit: dict[str, Any] | None = None,
    source_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    keys = unique_registry_keys(audit, source_keys)
    jobs: list[dict[str, Any]] = []
    seen_output_queries: dict[str, str] = {}

    for key in keys:
        source = ((registry.get("sources") or {}).get(key) or {})
        if not isinstance(source, dict):
            jobs.append({"registryKey": key, "status": "missing_registry_key"})
            continue

        raw_path = str(source.get("inputPath") or "").strip()
        query = str(source.get("query") or "").strip()
        platform = str(source.get("platform") or "").strip() or "unknown"
        if not raw_path:
            jobs.append({"registryKey": key, "status": "missing_input_path"})
            continue

        output_path = resolve_input_path(registry_path, raw_path)
        output_path_key = str(output_path)
        prior_query = seen_output_queries.get(output_path_key)
        if prior_query and prior_query != query:
            jobs.append(
                {
                    "registryKey": key,
                    "status": "conflicting_output_path",
                    "outputPath": output_path_key,
                    "query": query,
                    "conflictQuery": prior_query,
                }
            )
            continue
        seen_output_queries[output_path_key] = query

        jobs.append(
            {
                "registryKey": key,
                "status": "pending",
                "platform": platform,
                "query": query,
                "outputPath": output_path_key,
                "limit": int(source.get("limit") or 10),
            }
        )
    return jobs


def run_wechat_search_job(
    job: dict[str, Any],
    *,
    search_script_path: Path = DEFAULT_WECHAT_SEARCH_SCRIPT,
) -> dict[str, Any]:
    output_path = Path(str(job["outputPath"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "node",
        str(search_script_path),
        str(job["query"]),
        "-n",
        str(job.get("limit", 10)),
        "-o",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        return {
            "status": "runner_error",
            "stderr": completed.stderr.strip(),
            "stdout": completed.stdout.strip(),
            "returncode": completed.returncode,
        }

    payload = read_json(output_path, {})
    records = []
    if isinstance(payload, dict):
        articles = payload.get("articles")
        if isinstance(articles, list):
            records = articles
    return {
        "status": "ok",
        "recordCount": len(records),
        "outputPath": str(output_path),
    }


def refresh_benchmark_sources(
    *,
    registry_path: Path,
    audit: dict[str, Any] | None = None,
    source_keys: list[str] | None = None,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    jobs = build_refresh_jobs(registry_path=registry_path, audit=audit, source_keys=source_keys)
    if not jobs:
        return {
            "status": "noop",
            "registryPath": str(registry_path),
            "refreshedCount": 0,
            "failedCount": 0,
            "results": [],
        }

    execute = runner or run_wechat_search_job
    results: list[dict[str, Any]] = []
    refreshed_count = 0
    failed_count = 0

    for job in jobs:
        job_status = str(job.get("status") or "")
        if job_status != "pending":
            failed_count += 1
            results.append(job)
            continue

        platform = str(job.get("platform") or "").strip().lower()
        if platform != "wechat":
            failed_count += 1
            results.append({**job, "status": "unsupported_platform"})
            continue
        if not str(job.get("query") or "").strip():
            failed_count += 1
            results.append({**job, "status": "missing_query"})
            continue

        outcome = execute(job)
        if str(outcome.get("status") or "") == "ok":
            refreshed_count += 1
            results.append({**job, **outcome, "status": "refreshed"})
            continue

        failed_count += 1
        results.append({**job, **outcome})

    return {
        "status": "ok" if failed_count == 0 else "warning",
        "registryPath": str(registry_path),
        "refreshedCount": refreshed_count,
        "failedCount": failed_count,
        "results": results,
    }


def main() -> int:
    args = parse_args()
    audit = None
    if not args.all and not args.source_keys:
        try:
            from scripts.audit_benchmark_registry import audit_benchmark_registry
        except ModuleNotFoundError:
            from audit_benchmark_registry import audit_benchmark_registry

        audit = audit_benchmark_registry(
            registry_path=args.registry.resolve(),
            domains_path=ROOT / "config" / "content_domains.json",
        )

    result = refresh_benchmark_sources(
        registry_path=args.registry.resolve(),
        audit=None if args.all else audit,
        source_keys=args.source_keys or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"ok", "noop"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
