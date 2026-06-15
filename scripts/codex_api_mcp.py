from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.codex_api_contracts import build_artifact_paths, validate_request, validate_success_payload
except ModuleNotFoundError:
    from codex_api_contracts import build_artifact_paths, validate_request, validate_success_payload


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "codex_api_mcp.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the repo-local codex_api_mcp adapter.")
    parser.add_argument("request_path", type=Path, help="Path to adapter request JSON.")
    parser.add_argument("--output", type=Path, default=None, help="Optional adapter response path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Provider config path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def error_response(message: str, error_type: str = "validation_error") -> dict[str, Any]:
    return {
        "status": "error",
        "errorType": error_type,
        "message": message,
        "retryable": False,
    }


def write_generation_artifacts(output_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = build_artifact_paths(output_dir)
    paths["articlePath"].write_text(payload["article_markdown"], encoding="utf-8")
    paths["titleVariantsPath"].write_text(
        json.dumps(payload["title_variants"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["summaryPath"].write_text(
        json.dumps(payload["summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {key: str(value) for key, value in paths.items()}


def run_fixture_provider(request: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    fixture_path = (provider_config.get("fixtures") or {}).get(request["action"])
    if not fixture_path:
        raise ValueError(f"missing fixture for action {request['action']}")
    payload = read_json(Path(fixture_path))
    artifacts = write_generation_artifacts(Path(request["outputDir"]), payload)
    response = {
        "requestId": request["requestId"],
        "status": "ok",
        "provider": "fixture",
        "artifacts": artifacts,
        "usage": payload.get("usage", {"inputTokens": 0, "outputTokens": 0}),
        "warnings": payload.get("summary", {}).get("warnings", []),
    }
    return validate_success_payload(response)


def run_packet_provider(request: dict[str, Any], provider_config: dict[str, Any]) -> dict[str, Any]:
    output_dir = Path(request["outputDir"])
    packet_dir = output_dir / str(provider_config.get("packetDirName") or "ai-packets")
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / f"{request['requestId']}.json"
    packet_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "requestId": request["requestId"],
        "status": "queued",
        "provider": "packet",
        "packetPath": str(packet_path),
        "message": "request packet written for later fulfillment",
    }


def run_request(request_payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    try:
        request = validate_request(request_payload)
    except ValueError as exc:
        return error_response(str(exc))

    provider_name = request_payload.get("provider") or config.get("defaultProvider") or "packet"
    provider_config = (config.get("providers") or {}).get(provider_name, {})
    provider_type = provider_config.get("type")

    try:
        if provider_type == "fixture":
            return run_fixture_provider(request, provider_config)
        if provider_type == "packet":
            return run_packet_provider(request, provider_config)
    except ValueError as exc:
        return error_response(str(exc))

    return error_response(f"unsupported provider: {provider_name}")


def main() -> int:
    args = parse_args()
    request = read_json(args.request_path)
    config = read_json(args.config)
    response = run_request(request, config)
    if args.output:
        write_json(args.output, response)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("status") in {"ok", "queued"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
