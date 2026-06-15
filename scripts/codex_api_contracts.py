from __future__ import annotations

from pathlib import Path
from typing import Any


SUPPORTED_ACTIONS = {
    "draft_article",
    "generate_titles",
    "build_rewrite_plan",
    "humanize_article",
    "summarize_quality_issues",
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    action = normalize_text(request.get("action"))
    request_id = normalize_text(request.get("requestId"))
    topic = normalize_text(request.get("topic"))
    output_dir = normalize_text(request.get("outputDir"))

    if action not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported action: {action}")
    if not request_id:
        raise ValueError("requestId is required")
    if not topic:
        raise ValueError("topic is required")
    if not output_dir:
        raise ValueError("outputDir is required")

    platforms = [normalize_text(item) for item in request.get("platforms", []) if normalize_text(item)]
    if not platforms:
        raise ValueError("at least one platform is required")

    return {
        **request,
        "action": action,
        "requestId": request_id,
        "topic": topic,
        "platforms": platforms,
        "contentDomain": normalize_text(request.get("contentDomain")) or "unclassified",
        "outputDir": output_dir,
    }


def build_artifact_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "articlePath": output_dir / "article.md",
        "titleVariantsPath": output_dir / "title-variants.json",
        "summaryPath": output_dir / "ai-summary.json",
    }


def validate_success_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "ok":
        raise ValueError("success payload must have status ok")

    artifacts = payload.get("artifacts") or {}
    required = ("articlePath", "titleVariantsPath", "summaryPath")
    for key in required:
        path = artifacts.get(key)
        if not path:
            raise ValueError(f"missing artifact path: {key}")
        if not Path(path).exists():
            raise ValueError(f"artifact path does not exist: {path}")

    usage = payload.get("usage") or {}
    if "inputTokens" not in usage or "outputTokens" not in usage:
        raise ValueError("usage must contain inputTokens and outputTokens")

    return payload
