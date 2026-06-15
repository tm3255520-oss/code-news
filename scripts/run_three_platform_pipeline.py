from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from scripts.check_generated_article_quality import (
        build_checks,
        build_markdown,
        evaluate_gate,
        infer_topic_from_payload,
        read_json,
        read_metrics_rows,
        score_checks,
    )
    from scripts.pipeline_state import (
        initialize_pipeline_state,
        load_pipeline_state,
        now_iso,
        pipeline_state_path,
        save_pipeline_state,
        set_platform_state,
    )
    from scripts.platform_publish_adapters import (
        map_toutiao_result,
        map_wechat_result,
        map_zhihu_result,
        should_skip_platform,
    )
except ModuleNotFoundError:
    from check_generated_article_quality import (
        build_checks,
        build_markdown,
        evaluate_gate,
        infer_topic_from_payload,
        read_json,
        read_metrics_rows,
        score_checks,
    )
    from pipeline_state import (
        initialize_pipeline_state,
        load_pipeline_state,
        now_iso,
        pipeline_state_path,
        save_pipeline_state,
        set_platform_state,
    )
    from platform_publish_adapters import (
        map_toutiao_result,
        map_wechat_result,
        map_zhihu_result,
        should_skip_platform,
    )


ROOT = Path(__file__).resolve().parents[1]
PLATFORM_SEQUENCE = ("toutiao", "zhihu", "wechat")
PLATFORM_COMMANDS = {
    "toutiao": ["node", str(ROOT / ".tmp" / "publish_toutiao_article.js")],
    "zhihu": ["node", str(ROOT / ".tmp" / "publish_zhihu_article_controlled.js")],
    "wechat": ["node", str(ROOT / ".tmp" / "publish_wechat_article_controlled.js")],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the three-platform content pipeline for Toutiao, Zhihu, and WeChat."
    )
    parser.add_argument("payload_path", type=Path, help="Path to the base payload JSON file.")
    parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Minimum quality score required to continue the pipeline.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only run generation checks and platform payload preparation without publishing.",
    )
    return parser.parse_args()


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


def load_title_variants(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}

    variants: dict[str, list[str]] = {}
    current_platform: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_platform = normalize_platform_heading(line[3:].strip())
            variants.setdefault(current_platform, [])
            continue
        if line.startswith("#"):
            continue
        if current_platform:
            variants[current_platform].append(line)

    return variants


def load_platform_copy_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}

    data = read_json(path)
    return data if isinstance(data, dict) else {}


def is_section_heading(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return bool(re.match(r"^([一二三四五六七八九十]+、|\d+[\.、])", value))


def split_lead_blocks(article_blocks: list[str]) -> tuple[list[str], list[str]]:
    lead: list[str] = []
    rest: list[str] = []
    hit_heading = False

    for block in article_blocks:
        if not hit_heading and is_section_heading(block):
            hit_heading = True
        if hit_heading:
            rest.append(block)
        else:
            lead.append(block)

    return lead, rest


def choose_platform_title(platform: str, variants: dict[str, list[str]], fallback: str) -> str:
    options = [item.strip() for item in variants.get(platform, []) if item.strip()]
    return options[0] if options else fallback


def apply_platform_copy(
    payload: dict[str, Any],
    platform: str,
    variants: dict[str, list[str]],
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    next_payload = dict(payload)
    next_payload["title"] = choose_platform_title(
        platform,
        variants,
        str(payload.get("title", "")).strip(),
    )

    platform_override = overrides.get(platform, {})
    summary = str(platform_override.get("summary", "")).strip()
    if summary:
        next_payload["summary"] = summary

    opening_blocks = [
        str(item).strip()
        for item in (platform_override.get("opening_blocks") or [])
        if str(item).strip()
    ]
    if opening_blocks:
        _, rest = split_lead_blocks(
            [str(block).strip() for block in payload.get("article_blocks", []) or [] if str(block).strip()]
        )
        next_payload["article_blocks"] = [*opening_blocks, *rest]

    return next_payload


def local_recent_payloads(payload_path: Path, limit: int = 8) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(
        payload_path.parent.glob("toutiao_payload_*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        if path.resolve() == payload_path.resolve():
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        payloads.append(
            {
                "path": str(path),
                "title": str(payload.get("title", "")).strip(),
                "topic": infer_topic_from_payload(payload),
            }
        )
        if len(payloads) >= limit:
            break
    return payloads


def write_platform_payloads(
    generated_dir: Path,
    payload: dict[str, Any],
    variants: dict[str, list[str]],
) -> dict[str, Path]:
    payload_dir = generated_dir / "platform-payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    overrides = load_platform_copy_overrides(generated_dir / "platform-copy.json")

    result: dict[str, Path] = {}
    for platform in ("toutiao", "zhihu", "wechat"):
        next_payload = apply_platform_copy(payload, platform, variants, overrides)
        target = payload_dir / f"{platform}.json"
        target.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result[platform] = target

    return result


def run_preflight(payload_path: Path, min_score: int = 80) -> dict[str, Any]:
    payload_path = payload_path.resolve()
    payload = read_json(payload_path)
    generated_dir = payload_path.parent / "generated" / str(payload.get("slug") or payload_path.stem)
    generated_dir.mkdir(parents=True, exist_ok=True)

    metrics_csv = payload_path.parent / "latest-content-performance-log.csv"
    metrics_rows = read_metrics_rows(metrics_csv)
    recent = local_recent_payloads(payload_path)
    topic = infer_topic_from_payload(payload)
    checks = build_checks(payload, metrics_rows, recent)
    score = score_checks(checks)
    gate = evaluate_gate(score=score, checks=checks, min_score=min_score)

    report = {
        "payloadPath": str(payload_path),
        "title": str(payload.get("title", "")).strip(),
        "topic": topic,
        "score": score,
        "gate": gate,
        "checks": [
            {"severity": item.severity, "title": item.title, "detail": item.detail}
            for item in checks
        ],
    }
    report_dir = payload_path.parent / "quality-gates"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = report_dir / f"{payload.get('slug') or payload_path.stem}.json"
    report_md_path = report_dir / f"{payload.get('slug') or payload_path.stem}.md"
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md_path.write_text(
        build_markdown(
            payload_path=payload_path,
            payload=payload,
            topic=topic,
            checks=checks,
            recent=recent,
            metrics_rows=metrics_rows,
        ),
        encoding="utf-8",
    )

    state_path = pipeline_state_path(payload_path, payload)
    state = (
        load_pipeline_state(state_path)
        if state_path.exists()
        else initialize_pipeline_state(payload_path, payload)
    )
    state["fingerprint"] = state.get("fingerprint") or initialize_pipeline_state(payload_path, payload)["fingerprint"]
    state["title"] = str(payload.get("title", "")).strip()
    state["assets"] = initialize_pipeline_state(payload_path, payload)["assets"]
    state["updatedAt"] = now_iso()
    state["qualityGate"] = {
        **gate,
        "checkedAt": state["updatedAt"],
        "reportMarkdownPath": str(report_md_path),
        "reportJsonPath": str(report_json_path),
    }
    save_pipeline_state(state_path, state)

    variants = load_title_variants(generated_dir / "title-variants.md")
    platform_payloads = write_platform_payloads(generated_dir, payload, variants)

    return {
        "payload": payload,
        "topic": topic,
        "checks": checks,
        "gate": gate,
        "statePath": state_path,
        "platformPayloads": platform_payloads,
    }


def read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return fallback


def find_matching_record(records: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any] | None:
    slug = payload.get("slug")
    title = str(payload.get("title", "")).strip()
    for record in records:
        if slug and record.get("slug") == slug:
            return record
        if title and str(record.get("title", "")).strip() == title:
            return record
    return None


def reconcile_platform_state(
    state: dict[str, Any],
    platform: str,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    payload = preflight["payload"]
    root_tmp = Path(preflight["statePath"]).parent.parent.parent
    generated_dir = Path(preflight["statePath"]).parent

    if platform == "toutiao":
        records = read_json_file(root_tmp / "toutiao-publish-records.json", [])
        record = find_matching_record(records if isinstance(records, list) else [], payload)
        verification = read_json_file(generated_dir / "debug" / "after-publish-list-check.json", None)
        mapped = map_toutiao_result(record, verification)
        return set_platform_state(state, "toutiao", **mapped)

    if platform == "zhihu":
        records = read_json_file(root_tmp / "zhihu-publish-records.json", [])
        record = find_matching_record(records if isinstance(records, list) else [], payload)
        mapped = map_zhihu_result(record)
        return set_platform_state(state, "zhihu", **mapped)

    records = read_json_file(root_tmp / "wechat-publish-records.json", [])
    record = find_matching_record(records if isinstance(records, list) else [], payload)
    mapped = map_wechat_result(record)
    return set_platform_state(state, "wechat", **mapped)


def run_platform_command(platform: str, payload_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*PLATFORM_COMMANDS[platform], str(payload_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run_pipeline(payload_path: Path, min_score: int = 80) -> dict[str, Any]:
    preflight = run_preflight(payload_path, min_score=min_score)
    state_path = preflight["statePath"]
    state = load_pipeline_state(state_path)

    if preflight["gate"]["status"] != "passed":
        return state

    for platform in PLATFORM_SEQUENCE:
        if should_skip_platform(state, platform):
            continue

        title_used = json.loads(
            preflight["platformPayloads"][platform].read_text(encoding="utf-8")
        ).get("title")
        state = set_platform_state(
            state,
            platform,
            status="publishing",
            attemptCount=int(state["platforms"][platform].get("attemptCount", 0)) + 1,
            lastAttemptAt=now_iso(),
            titleUsed=title_used,
            error=None,
        )
        save_pipeline_state(state_path, state)

        result = run_platform_command(platform, preflight["platformPayloads"][platform])
        state = reconcile_platform_state(state, platform, preflight)

        if result.returncode != 0 and state["platforms"][platform]["status"] not in {
            "published_verified",
            "awaiting_verification",
        }:
            state = set_platform_state(
                state,
                platform,
                status="publish_failed",
                error=(result.stderr or result.stdout).strip()[:500] or "publish command failed",
            )

        save_pipeline_state(state_path, state)

    return state


def main() -> int:
    args = parse_args()
    payload_path = args.payload_path.resolve()
    payload = read_json(payload_path)

    if args.preflight_only:
        preflight = run_preflight(payload_path, min_score=args.min_score)
        state = load_pipeline_state(preflight["statePath"])
        print(
            json.dumps(
                {
                    "mode": "preflight",
                    "payloadPath": str(payload_path),
                    "statePath": str(preflight["statePath"]),
                    "topic": preflight["topic"],
                    "gate": preflight["gate"],
                    "assets": state.get("assets", {}),
                    "qualityGate": state.get("qualityGate", {}),
                    "platformPayloads": {
                        platform: str(path)
                        for platform, path in preflight["platformPayloads"].items()
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    result = run_pipeline(payload_path, min_score=args.min_score)
    print(
        json.dumps(
            {
                "mode": "publish",
                "payloadPath": str(payload_path),
                "statePath": str(pipeline_state_path(payload_path, payload)),
                "platforms": result.get("platforms", {}),
                "qualityGate": result.get("qualityGate", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
