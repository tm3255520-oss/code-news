#!/usr/bin/env python3
"""Generate the daily content-ops brief for publish, quality, and traffic decisions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.check_generated_article_quality import infer_topic_from_payload
    from scripts.check_publish_readiness import TMP_DIR, evaluate, render_markdown
    from scripts.generate_content_performance_report import build_markdown as build_performance_markdown
    from scripts.generate_content_performance_report import read_rows as read_performance_rows
    from scripts.probe_xhs_publish_state import OUTPUT_PATH as XHS_PROBE_PATH
    from scripts.probe_xhs_publish_state import run_probe
    from scripts.run_content_signal_pipeline import ensure_signal_artifacts
    from scripts.sync_recent_metrics_to_log import collect_rows, infer_topic, write_csv
except ModuleNotFoundError:
    from check_generated_article_quality import infer_topic_from_payload
    from check_publish_readiness import TMP_DIR, evaluate, render_markdown
    from generate_content_performance_report import build_markdown as build_performance_markdown
    from generate_content_performance_report import read_rows as read_performance_rows
    from probe_xhs_publish_state import OUTPUT_PATH as XHS_PROBE_PATH
    from probe_xhs_publish_state import run_probe
    from run_content_signal_pipeline import ensure_signal_artifacts
    from sync_recent_metrics_to_log import collect_rows, infer_topic, write_csv


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEF_PATH = TMP_DIR / "daily-content-ops-brief.md"
DEFAULT_STATE_PATH = TMP_DIR / "daily-content-ops-state.json"
DEFAULT_METRICS_PATH = TMP_DIR / "latest-content-performance-log.csv"
DEFAULT_REPORT_PATH = TMP_DIR / "content-performance-report-latest.md"
DEFAULT_READINESS_PATH = TMP_DIR / "publish-readiness-latest.md"
DEFAULT_BENCHMARK_REGISTRY_PATH = ROOT / "config" / "benchmark_source_registry.json"
DEFAULT_CONTENT_DOMAINS_PATH = ROOT / "config" / "content_domains.json"
GENERATED_DIR = TMP_DIR / "generated"
XHS_CLI = ROOT / ".agents" / "skills" / "xiaohongshu-skills" / "scripts" / "cli.py"
PLATFORM_SCHEDULE = {
    "wechat": {
        "platform": "微信公众号",
        "standard_volume": "1篇/天",
        "max_volume": "1篇/天",
        "primary_time": "20:00-21:00",
        "backup_time": "12:15-13:00",
    },
    "zhihu": {
        "platform": "知乎",
        "standard_volume": "1篇/天",
        "max_volume": "2篇/天",
        "primary_time": "19:30-21:30",
        "backup_time": "12:00-13:30",
    },
    "toutiao": {
        "platform": "今日头条",
        "standard_volume": "1篇/天",
        "max_volume": "2篇/天",
        "primary_time": "12:30-13:30",
        "backup_time": "20:30-21:30",
    },
    "xhs": {
        "platform": "小红书",
        "standard_volume": "1篇/天",
        "max_volume": "2篇/天",
        "primary_time": "20:00-21:00",
        "backup_time": "12:30-13:30",
    },
}
DEFAULT_DAILY_SEQUENCE = [
    ("toutiao", "12:30"),
    ("zhihu", "19:30"),
    ("wechat", "20:15"),
    ("xhs", "20:45"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the daily content-ops loop and produce one operating brief."
    )
    parser.add_argument(
        "--brief-path",
        type=Path,
        default=DEFAULT_BRIEF_PATH,
        help="Output markdown brief path.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="Output JSON state path.",
    )
    parser.add_argument(
        "--metrics-path",
        type=Path,
        default=DEFAULT_METRICS_PATH,
        help="Output CSV path for merged metrics.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Output markdown path for the traffic report.",
    )
    parser.add_argument(
        "--readiness-path",
        type=Path,
        default=DEFAULT_READINESS_PATH,
        help="Output markdown path for publish readiness.",
    )
    parser.add_argument(
        "--skip-xhs-probe",
        action="store_true",
        help="Skip refreshing the XHS probe before evaluating readiness.",
    )
    parser.add_argument(
        "--prepare-xhs-login",
        action="store_true",
        help="If XHS is logged out, prepare a fresh QR login payload via the XHS auth CLI.",
    )
    parser.add_argument(
        "--benchmark-registry",
        type=Path,
        default=DEFAULT_BENCHMARK_REGISTRY_PATH,
        help="Optional local registry for benchmark source requests.",
    )
    parser.add_argument(
        "--skip-benchmark-refresh",
        action="store_true",
        help="Skip refreshing stale, missing, or empty benchmark source snapshots.",
    )
    return parser.parse_args()


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def latest_generated_article_dir(
    generated_root: Path = GENERATED_DIR,
    payload_root: Path = TMP_DIR,
) -> Path | None:
    if not generated_root.exists():
        return None
    dirs = [item for item in generated_root.iterdir() if item.is_dir()]
    if not dirs:
        return None

    ranked = sorted(dirs, key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in ranked:
        if find_payload_for_generated_dir(candidate, payload_root=payload_root):
            return candidate
    return ranked[0]


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return fallback


def normalize_registry_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def find_payload_for_generated_dir(generated_dir: Path, payload_root: Path = TMP_DIR) -> Path | None:
    slug = generated_dir.name
    candidates: list[tuple[int, float, Path]] = []
    for path in payload_root.glob("*payload*.json"):
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("slug") or "").strip() != slug:
            continue
        priority = 0 if path.name.startswith("toutiao_payload") else 1
        candidates.append((priority, -path.stat().st_mtime, path))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def load_benchmark_registry(path: Path) -> dict[str, Any]:
    data = read_json(path, {})
    return data if isinstance(data, dict) else {}


def build_benchmark_registry_audit(
    registry_path: Path = DEFAULT_BENCHMARK_REGISTRY_PATH,
    domains_path: Path = DEFAULT_CONTENT_DOMAINS_PATH,
    max_source_age_days: int = 14,
) -> dict[str, Any]:
    try:
        from scripts.audit_benchmark_registry import audit_benchmark_registry
    except ModuleNotFoundError:
        from audit_benchmark_registry import audit_benchmark_registry

    return audit_benchmark_registry(
        registry_path=registry_path,
        domains_path=domains_path,
        max_source_age_days=max_source_age_days,
    )


def refresh_benchmark_registry_if_needed(
    audit: dict[str, Any] | None,
    *,
    registry_path: Path = DEFAULT_BENCHMARK_REGISTRY_PATH,
    refresher: Any = None,
) -> dict[str, Any] | None:
    if not isinstance(audit, dict):
        return None
    has_targets = any(audit.get(key) for key in ("missingSourcePaths", "emptySourcePaths", "staleSourcePaths"))
    if not has_targets:
        return None

    if refresher is None:
        try:
            from scripts.refresh_benchmark_sources import refresh_benchmark_sources
        except ModuleNotFoundError:
            from refresh_benchmark_sources import refresh_benchmark_sources

        refresher = refresh_benchmark_sources
    return refresher(registry_path=registry_path, audit=audit)


def candidate_registry_keys(payload: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    raw_candidates = [
        payload.get("benchmarkRegistryKey"),
        payload.get("domain"),
        payload.get("topic"),
        infer_topic_from_payload(payload),
        infer_topic(
            str(payload.get("title") or "").strip(),
            " ".join(
                [
                    str(payload.get("summary") or "").strip(),
                    *[str(item) for item in (payload.get("article_blocks") or [])[:6]],
                ]
            ),
        ),
    ]
    for raw in raw_candidates:
        key = normalize_registry_key(raw)
        if not key or key == "unlabeled" or key in keys:
            continue
        keys.append(key)
    return keys


def normalize_registry_request(request: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    normalized = dict(request)
    if "action" not in normalized:
        normalized["action"] = "search_content"
    if "provider" not in normalized:
        normalized["provider"] = "import_json"
    input_path = str(normalized.get("inputPath") or "").strip()
    if input_path:
        candidate = Path(input_path)
        if not candidate.is_absolute():
            candidate = (registry_path.parent / candidate).resolve()
        normalized["inputPath"] = str(candidate)
    return normalized


def resolve_registry_request(
    payload: dict[str, Any],
    registry: dict[str, Any],
    registry_path: Path,
) -> tuple[str | None, dict[str, Any] | None]:
    sources = registry.get("sources", {})
    if not isinstance(sources, dict):
        return None, None

    alias_to_key: dict[str, str] = {}
    for key, raw_request in sources.items():
        if not isinstance(raw_request, dict):
            continue
        alias_to_key[normalize_registry_key(key)] = key
        for alias in raw_request.get("aliases", []) or []:
            normalized_alias = normalize_registry_key(alias)
            if normalized_alias:
                alias_to_key[normalized_alias] = key

    for candidate in candidate_registry_keys(payload):
        resolved_key = alias_to_key.get(candidate)
        if not resolved_key:
            continue
        raw_request = sources.get(resolved_key)
        if not isinstance(raw_request, dict):
            continue
        return resolved_key, normalize_registry_request(raw_request, registry_path)

    return None, None


def prepare_benchmark_source_for_generated_dir(
    generated_dir: Path,
    *,
    payload_root: Path = TMP_DIR,
    registry_path: Path = DEFAULT_BENCHMARK_REGISTRY_PATH,
) -> dict[str, Any]:
    payload_path = find_payload_for_generated_dir(generated_dir, payload_root=payload_root)
    if not payload_path:
        return {
            "status": "missing_payload",
            "sourceKind": None,
            "payloadPath": None,
            "generatedDir": str(generated_dir),
        }

    payload = read_json(payload_path, {})
    if not isinstance(payload, dict):
        return {
            "status": "invalid_payload",
            "sourceKind": None,
            "payloadPath": str(payload_path),
            "generatedDir": str(generated_dir),
        }

    payload_with_request = dict(payload)
    source_kind = "payload"
    registry_key: str | None = None

    has_payload_source = any(
        str(payload.get(field) or "").strip()
        for field in ("benchmarkSourcePath", "benchmarkRequestPath")
    ) or isinstance(payload.get("benchmarkRequest"), dict)

    if not has_payload_source:
        registry = load_benchmark_registry(registry_path)
        registry_key, request = resolve_registry_request(payload, registry, registry_path)
        if not request:
            return {
                "status": "pending_registry",
                "sourceKind": "registry",
                "registryKey": None,
                "payloadPath": str(payload_path),
                "generatedDir": str(generated_dir),
            }
        payload_with_request["benchmarkRequest"] = request
        source_kind = "registry"

    result = ensure_signal_artifacts(
        generated_dir=generated_dir,
        slug=str(payload.get("slug") or generated_dir.name),
        current_title=str(payload.get("title") or "").strip(),
        payload=payload_with_request,
    )
    summary = {
        **result,
        "sourceKind": source_kind,
        "registryKey": registry_key,
        "payloadPath": str(payload_path),
        "generatedDir": str(generated_dir),
    }
    return summary


def parse_title_variants(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    variants: dict[str, list[str]] = defaultdict(list)
    current_platform: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_platform = normalize_platform_heading(line[3:].strip())
            continue
        if line.startswith("### "):
            continue
        if current_platform and not line.startswith("#"):
            variants[current_platform].append(line)

    return dict(variants)


def normalize_platform_heading(text: str) -> str:
    lowered = text.lower()
    if "头条" in text or "toutiao" in lowered:
        return "toutiao"
    if "微信" in text or "wechat" in lowered:
        return "wechat"
    if "知乎" in text or "zhihu" in lowered:
        return "zhihu"
    if "小红书" in text or "xhs" in lowered:
        return "xhs"
    return lowered


def choose_platform_title(platform: str, variants: dict[str, list[str]], fallback: str) -> str:
    options = [item.strip() for item in variants.get(platform, []) if item.strip()]
    if not options:
        return fallback

    if platform in {"toutiao", "xhs"}:
        return min(options, key=len)
    if platform == "wechat":
        return max(options, key=len)
    return options[0]


def summarize_platform_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("platform", "unknown"))].append(row)

    summary: dict[str, dict[str, float]] = {}
    for platform, items in grouped.items():
        summary[platform] = {
            "count": float(len(items)),
            "avg_views": safe_mean([float(item.get("views", 0.0)) for item in items]),
            "avg_like_rate": safe_mean([float(item.get("like_rate", 0.0)) for item in items]),
            "avg_comment_rate": safe_mean([float(item.get("comment_rate", 0.0)) for item in items]),
            "avg_composite_score": safe_mean(
                [float(item.get("composite_score", 0.0)) for item in items]
            ),
        }
    return summary


def pick_top_posts(rows: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: float(row.get("composite_score", 0.0)), reverse=True)
    return ranked[:limit]


def title_signal_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- 近期样本还太少，先继续累计发文和表现数据。"]

    ranked = sorted(rows, key=lambda row: float(row.get("composite_score", 0.0)), reverse=True)
    top_slice = ranked[: max(1, len(ranked) // 3)]

    avg_all = safe_mean([float(row.get("title_length", 0.0)) for row in rows])
    avg_top = safe_mean([float(row.get("title_length", 0.0)) for row in top_slice])
    all_numbers = safe_mean([1.0 if row.get("title_has_number") else 0.0 for row in rows])
    top_numbers = safe_mean([1.0 if row.get("title_has_number") else 0.0 for row in top_slice])
    all_colons = safe_mean([1.0 if row.get("title_has_colon") else 0.0 for row in rows])
    top_colons = safe_mean([1.0 if row.get("title_has_colon") else 0.0 for row in top_slice])

    lines = []
    if avg_top and avg_top < avg_all:
        lines.append(
            f"- 高表现标题更短，近期胜出样本平均长度 `{avg_top:.1f}`，明显低于整体的 `{avg_all:.1f}`。"
        )
    if top_numbers < all_numbers:
        lines.append("- 数字并不是当前最强信号，别默认把每篇内容都包装成清单题。")
    if top_colons < all_colons:
        lines.append("- 冒号型标题近期不占优，短结论式标题更值得优先测试。")
    if not lines:
        lines.append("- 近期标题信号还不够分化，先继续按平台差异化出题并积累样本。")
    return lines


def quality_focus_lines(rows: list[dict[str, Any]], readiness: list[dict[str, Any]]) -> list[str]:
    lines = title_signal_lines(rows)[:2]

    blocked = [item for item in readiness if item.get("state") == "blocked"]
    if blocked:
        lines.append("- 被判定为 `blocked` 的平台今天不进正式发布链路，先保住可发布平台的节奏。")
    else:
        lines.append("- 今天可以把重心放在平台化改稿，而不是额外处理发布故障。")

    lines.append("- 所有正文发布前都先过一次质量闸门，重点检查开头前三段、收藏价值和评论引导。")
    lines.append("- Publish gate: run `python scripts/check_generated_article_quality.py <payload.json>` and block drafts below score 60.")
    return lines[:4]


def topic_focus_lines(rows: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        topic = str(row.get("topic", "unlabeled")).strip() or "unlabeled"
        grouped[topic].append(row)

    ranked = sorted(
        grouped.items(),
        key=lambda item: safe_mean([float(row.get("composite_score", 0.0)) for row in item[1]]),
        reverse=True,
    )
    lines: list[str] = []
    for topic, items in ranked[:3]:
        lines.append(
            f"- `{topic}` 最近样本 `{len(items)}` 篇，平均综合分 `{safe_mean([float(row.get('composite_score', 0.0)) for row in items]):.1f}`。"
        )
    return lines or ["- 题材标签还不够丰富，先继续累计可归类样本。"]


def platform_dispatch(
    readiness: list[dict[str, Any]],
    metrics_summary: dict[str, dict[str, float]],
    manifest: dict[str, Any] | None,
    title_variants: dict[str, list[str]],
) -> list[dict[str, Any]]:
    fallback_title = str((manifest or {}).get("title", "")).strip()
    state_priority = {"ready": 0, "warning": 1, "blocked": 2}

    def sort_key(item: dict[str, Any]) -> tuple[float, float]:
        platform_key = "xiaohongshu" if item["key"] == "xhs" else item["key"]
        metric = metrics_summary.get(platform_key, {})
        return (float(metric.get("avg_views", 0.0)), float(metric.get("avg_composite_score", 0.0)))

    ranked = sorted(
        readiness,
        key=lambda item: (
            state_priority.get(str(item.get("state", "")), 9),
            -sort_key(item)[0],
            -sort_key(item)[1],
        ),
    )
    dispatch: list[dict[str, Any]] = []
    for item in ranked:
        dispatch.append(
            {
                "platform": item["platform"],
                "key": item["key"],
                "state": item["state"],
                "summary": item["summary"],
                "recommended_title": choose_platform_title(item["key"], title_variants, fallback_title),
                "avg_recent_views": sort_key(item)[0],
                "next_actions": item.get("next_actions", [])[:2],
            }
        )
    return dispatch


def top_post_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for row in pick_top_posts(rows):
        lines.append(
            "- "
            f"{row.get('date', '')} | {row.get('platform', '')} | {row.get('title', '')} | "
            f"阅读 `{float(row.get('views', 0.0)):.0f}` | 综合分 `{float(row.get('composite_score', 0.0)):.1f}`"
        )
    return lines or ["- 近期还没有足够多的表现样本。"]


def extract_today_actions(dispatch: list[dict[str, Any]]) -> list[str]:
    primary = [item for item in dispatch if item["state"] == "ready"]
    warning = [item for item in dispatch if item["state"] == "warning"]
    blocked = [item for item in dispatch if item["state"] == "blocked"]

    lines: list[str] = []
    if primary:
        ordered = " -> ".join(item["platform"] for item in primary)
        lines.append(f"- 今天优先正式发布的平台：`{ordered}`。")
    if warning:
        ordered = " -> ".join(item["platform"] for item in warning)
        lines.append(f"- 处于 `warning` 的平台只做单篇发布和人工复核：`{ordered}`。")
    if blocked:
        ordered = " -> ".join(item["platform"] for item in blocked)
        lines.append(f"- 处于 `blocked` 的平台今天先不进正式链路：`{ordered}`。")
    return lines or ["- 今天所有平台都需要先补预检，再安排发布。"]


def schedule_snapshot(dispatch: list[dict[str, Any]]) -> list[dict[str, str]]:
    snapshot: list[dict[str, str]] = []
    dispatch_by_key = {str(item.get("key", "")): item for item in dispatch}
    for key, suggested_time in DEFAULT_DAILY_SEQUENCE:
        config = PLATFORM_SCHEDULE.get(key)
        if not config:
            continue
        dispatch_item = dispatch_by_key.get(key, {})
        snapshot.append(
            {
                "key": key,
                "platform": str(config["platform"]),
                "standardVolume": str(config["standard_volume"]),
                "maxVolume": str(config["max_volume"]),
                "primaryTime": str(config["primary_time"]),
                "backupTime": str(config["backup_time"]),
                "suggestedTodayTime": suggested_time,
                "state": str(dispatch_item.get("state", "unknown")),
            }
        )
    return snapshot


def schedule_lines(snapshot: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for item in snapshot:
        lines.append(
            "- "
            f"{item['platform']}：标准 `{item['standardVolume']}`，上限 `{item['maxVolume']}`，"
            f"主时段 `{item['primaryTime']}`，备选 `{item['backupTime']}`，"
            f"今日建议落点 `{item['suggestedTodayTime']}`，当前状态 `{item['state']}`。"
        )
    return lines or ["- 今天还没有可用的固定节奏快照。"]


def generate_xhs_login_payload() -> dict[str, Any] | None:
    if not XHS_CLI.exists():
        return None

    result = subprocess.run(
        [sys.executable, str(XHS_CLI), "--cdp-port", "9226", "check-login"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    start = result.stdout.find("{")
    if start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
        return payload
    except json.JSONDecodeError:
        return None


def build_brief(
    *,
    readiness: list[dict[str, Any]],
    metrics_rows: list[dict[str, Any]],
    manifest: dict[str, Any] | None,
    latest_article_dir: Path | None,
    title_variants: dict[str, list[str]],
    xhs_login_payload: dict[str, Any] | None,
    benchmark_source: dict[str, Any] | None,
    benchmark_refresh: dict[str, Any] | None,
    benchmark_registry_audit: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    metrics_summary = summarize_platform_metrics(metrics_rows)
    dispatch = platform_dispatch(readiness, metrics_summary, manifest, title_variants)
    daily_schedule = schedule_snapshot(dispatch)

    state = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "latestArticleDir": str(latest_article_dir) if latest_article_dir else None,
        "latestArticleManifest": manifest,
        "dispatch": dispatch,
        "dailySchedule": daily_schedule,
        "readiness": readiness,
        "xhsLogin": xhs_login_payload,
        "benchmarkSource": benchmark_source,
        "benchmarkRefresh": benchmark_refresh,
        "benchmarkRegistryAudit": benchmark_registry_audit,
    }

    audit_summary = (benchmark_registry_audit or {}).get("summary", {})
    audit_status = (benchmark_registry_audit or {}).get("status", "not_checked")
    audit_total = int(audit_summary.get("tokenCount", 0) or 0)
    audit_covered = int(audit_summary.get("coveredTokenCount", 0) or 0)
    audit_empty = int(audit_summary.get("emptySourcePathCount", 0) or 0)
    audit_stale = int(audit_summary.get("staleSourcePathCount", 0) or 0)
    refresh_status = (benchmark_refresh or {}).get("status", "not_run")
    refresh_refreshed = int((benchmark_refresh or {}).get("refreshedCount", 0) or 0)
    refresh_failed = int((benchmark_refresh or {}).get("failedCount", 0) or 0)

    lines = [
        "# 今日内容运营简报",
        "",
        f"- 生成时间：`{state['generatedAt']}`",
        f"- 最新选题目录：`{state['latestArticleDir'] or '未找到'}`",
        f"- 对标输入状态：`{(benchmark_source or {}).get('status', 'not_checked')}`",
        f"- Benchmark refresh: `{refresh_status}` (refreshed={refresh_refreshed}, failed={refresh_failed})",
        f"- Benchmark registry audit: `{audit_status}` ({audit_covered}/{audit_total}, empty={audit_empty}, stale={audit_stale})",
    ]

    if manifest:
        lines.extend(
            [
                f"- 当前主标题：`{manifest.get('title', '')}`",
                f"- 素材来源数：`{manifest.get('sourceCount', 0)}`",
                "",
                "## 今天先发什么",
                "",
                *extract_today_actions(dispatch),
                "",
                "## 平台发布建议",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## 今天先发什么",
                "",
                *extract_today_actions(dispatch),
                "",
                "## 平台发布建议",
                "",
            ]
        )

    lines.extend(
        [
            "### 固定节奏",
            "",
            *schedule_lines(daily_schedule),
            "",
        ]
    )

    for item in dispatch:
        lines.extend(
            [
                f"### {item['platform']}",
                f"- 状态：`{item['state']}`",
                f"- 建议标题：`{item['recommended_title']}`",
                f"- 近期平均阅读：`{item['avg_recent_views']:.0f}`",
                f"- 判断：{item['summary']}",
            ]
        )
        if item["next_actions"]:
            lines.append(f"- 下一步：{'；'.join(item['next_actions'])}")
        lines.append("")

    lines.extend(
        [
            "## 近期流量信号",
            "",
            *top_post_lines(metrics_rows),
            "",
            "## 标题与质量重点",
            "",
            *quality_focus_lines(metrics_rows, readiness),
            "",
            "## 题材复盘",
            "",
            *topic_focus_lines(metrics_rows),
        ]
    )

    if xhs_login_payload and xhs_login_payload.get("logged_in") is False:
        lines.extend(
            [
                "",
                "## 小红书恢复路径",
                "",
                f"- 当前状态：`{xhs_login_payload.get('login_method', 'unknown')}`",
                f"- 二维码文件：`{xhs_login_payload.get('qrcode_path', '')}`",
            ]
        )
        if xhs_login_payload.get("qr_login_url"):
            lines.append(f"- 手机直达登录链接：`{xhs_login_payload['qr_login_url']}`")

    return "\n".join(lines).strip() + "\n", state


def build_run_summary(
    *,
    brief_path: Path,
    state_path: Path,
    readiness_path: Path,
    report_path: Path,
    metrics_path: Path,
    xhs_probe_path: Path,
    latest_article_dir: Path | None,
    benchmark_source: dict[str, Any] | None,
    benchmark_refresh: dict[str, Any] | None,
    benchmark_registry_audit: dict[str, Any] | None,
    xhs_login_prepared: bool,
) -> dict[str, Any]:
    return {
        "briefPath": str(brief_path),
        "statePath": str(state_path),
        "readinessPath": str(readiness_path),
        "reportPath": str(report_path),
        "metricsPath": str(metrics_path),
        "xhsProbePath": str(xhs_probe_path),
        "latestArticleDir": str(latest_article_dir) if latest_article_dir else None,
        "benchmarkSource": benchmark_source,
        "benchmarkRefresh": benchmark_refresh,
        "benchmarkRegistryAudit": benchmark_registry_audit,
        "xhsLoginPrepared": xhs_login_prepared,
    }


def main() -> int:
    args = parse_args()

    if not args.skip_xhs_probe:
        probe_state = run_probe()
        XHS_PROBE_PATH.write_text(json.dumps(probe_state, ensure_ascii=False, indent=2), encoding="utf-8")

    readiness = evaluate()
    args.readiness_path.write_text(render_markdown(readiness), encoding="utf-8")

    merged_rows = collect_rows()
    write_csv(args.metrics_path, merged_rows)
    performance_rows = read_performance_rows(args.metrics_path)
    performance_report = build_performance_markdown(performance_rows, args.metrics_path)
    args.report_path.write_text(performance_report, encoding="utf-8")

    latest_article_dir = latest_generated_article_dir()
    manifest = read_json(latest_article_dir / "manifest.json", None) if latest_article_dir else None
    title_variants = (
        parse_title_variants(latest_article_dir / "title-variants.md")
        if latest_article_dir
        else {}
    )
    benchmark_registry_audit = build_benchmark_registry_audit(
        registry_path=args.benchmark_registry,
        domains_path=DEFAULT_CONTENT_DOMAINS_PATH,
    )
    benchmark_refresh = None if args.skip_benchmark_refresh else refresh_benchmark_registry_if_needed(
        benchmark_registry_audit,
        registry_path=args.benchmark_registry,
    )
    if benchmark_refresh:
        benchmark_registry_audit = build_benchmark_registry_audit(
            registry_path=args.benchmark_registry,
            domains_path=DEFAULT_CONTENT_DOMAINS_PATH,
        )
    benchmark_source = (
        prepare_benchmark_source_for_generated_dir(
            latest_article_dir,
            payload_root=TMP_DIR,
            registry_path=args.benchmark_registry,
        )
        if latest_article_dir
        else None
    )

    xhs_login_payload = None
    xhs_state = next((item for item in readiness if item.get("key") == "xhs"), None)
    if args.prepare_xhs_login and xhs_state and xhs_state.get("state") == "blocked":
        probe_state = read_json(XHS_PROBE_PATH, {})
        if probe_state.get("status") == "logged_out":
            xhs_login_payload = generate_xhs_login_payload()

    brief_markdown, state = build_brief(
        readiness=readiness,
        metrics_rows=performance_rows,
        manifest=manifest,
        latest_article_dir=latest_article_dir,
        title_variants=title_variants,
        xhs_login_payload=xhs_login_payload,
        benchmark_source=benchmark_source,
        benchmark_refresh=benchmark_refresh,
        benchmark_registry_audit=benchmark_registry_audit,
    )

    args.brief_path.write_text(brief_markdown, encoding="utf-8")
    args.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = build_run_summary(
        brief_path=args.brief_path,
        state_path=args.state_path,
        readiness_path=args.readiness_path,
        report_path=args.report_path,
        metrics_path=args.metrics_path,
        xhs_probe_path=XHS_PROBE_PATH,
        latest_article_dir=latest_article_dir,
        benchmark_source=benchmark_source,
        benchmark_refresh=benchmark_refresh,
        benchmark_registry_audit=benchmark_registry_audit,
        xhs_login_prepared=bool(xhs_login_payload),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
