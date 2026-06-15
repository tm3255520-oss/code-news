from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.codex_api_mcp import run_request
    from scripts.run_content_signal_pipeline import ensure_signal_artifacts
except ModuleNotFoundError:
    from codex_api_mcp import run_request
    from run_content_signal_pipeline import ensure_signal_artifacts


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "codex_api_mcp.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one codex_api_mcp generation job for a slug directory.")
    parser.add_argument("generated_dir", type=Path, help="Generated slug directory.")
    parser.add_argument("--topic", required=True, help="Article topic.")
    parser.add_argument("--content-domain", required=True, help="Content domain id.")
    parser.add_argument("--provider", default=None, help="Optional provider override.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Provider config file.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_request(
    *,
    generated_dir: Path,
    topic: str,
    content_domain: str,
    platforms: list[str],
    provider: str | None,
) -> dict[str, Any]:
    slug = generated_dir.name
    request = {
        "action": "draft_article",
        "requestId": f"{slug}-draft-article",
        "topic": topic,
        "platforms": platforms,
        "contentDomain": content_domain,
        "outputDir": str(generated_dir),
        "inputs": {
            "benchmarkSummaryPath": str(generated_dir / "benchmark-monitor.md"),
            "viralAnalysisPath": str(generated_dir / "viral-analysis.md"),
            "rewritePlanPath": str(generated_dir / "rewrite-plan.md"),
        },
    }
    if provider:
        request["provider"] = provider
    return request


def run_generation_job(
    *,
    generated_dir: Path,
    topic: str,
    content_domain: str,
    platforms: list[str],
    provider: str | None,
    config: dict[str, Any],
    request_path: Path,
) -> dict[str, Any]:
    signal_pipeline = ensure_signal_artifacts(
        generated_dir=generated_dir,
        slug=generated_dir.name,
        current_title=topic,
    )
    request = build_request(
        generated_dir=generated_dir,
        topic=topic,
        content_domain=content_domain,
        platforms=platforms,
        provider=provider,
    )
    write_json(request_path, request)
    response = run_request(request, config)
    response["signalPipeline"] = signal_pipeline
    return response


def main() -> int:
    args = parse_args()
    generated_dir = args.generated_dir.resolve()
    config = read_json(args.config)
    request_path = generated_dir / "generation-request.json"
    response = run_generation_job(
        generated_dir=generated_dir,
        topic=args.topic,
        content_domain=args.content_domain,
        platforms=["toutiao", "zhihu", "wechat"],
        provider=args.provider,
        config=config,
        request_path=request_path,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") in {"ok", "queued"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
