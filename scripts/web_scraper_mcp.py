from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.web_scraper_contracts import normalize_record
except ModuleNotFoundError:
    from web_scraper_contracts import normalize_record


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "web_scraper_mcp.json"

SUPPORTED_ACTIONS = {
    "search_content",
    "fetch_article",
    "fetch_author_feed",
    "extract_metrics",
    "normalize_record",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the repo-local web_scraper_mcp adapter.")
    parser.add_argument("request_path", type=Path, help="Path to the adapter request JSON file.")
    parser.add_argument("--output", type=Path, default=None, help="Optional response output path.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Config file path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def read_json_maybe(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def error_response(message: str, error_type: str = "validation_error") -> dict[str, Any]:
    return {
        "status": "error",
        "errorType": error_type,
        "message": message,
    }


def fixture_key(request: dict[str, Any]) -> str:
    return f"{request.get('action')}:{request.get('platform', '')}:{request.get('query', '')}"


def load_fixture_rows(provider_config: dict[str, Any], request: dict[str, Any]) -> list[dict[str, Any]]:
    fixtures = provider_config.get("fixtures", {})
    path = fixtures.get(fixture_key(request))
    if not path:
        raise ValueError(f"missing fixture for {fixture_key(request)}")
    payload = read_json_maybe(Path(path))
    if not isinstance(payload, list):
        raise ValueError("fixture payload must be a list")
    return payload


def import_rows_from_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(request.get("record"), dict):
        return [request["record"]]
    input_path = request.get("inputPath")
    if not input_path:
        raise ValueError("import_json provider requires record or inputPath")
    payload = read_json_maybe(Path(input_path))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("records", "articles", "items", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        return [payload]
    raise ValueError("input payload must be a dict or list")


def normalize_rows(rows: list[dict[str, Any]], request: dict[str, Any], provider_type: str) -> list[dict[str, Any]]:
    return [
        normalize_record(
            row,
            platform=request.get("platform"),
            record_type=request.get("recordType", "article"),
            capture_method=provider_type,
        )
        for row in rows
    ]


def run_request(request: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action not in SUPPORTED_ACTIONS:
        return error_response(f"unsupported action: {action}")

    provider_name = request.get("provider") or config.get("defaultProvider") or "import_json"
    provider_config = (config.get("providers") or {}).get(provider_name, {})
    provider_type = provider_config.get("type")
    if provider_type not in {"fixture", "import_json"}:
        return error_response(f"unsupported provider: {provider_name}")

    try:
        rows = (
            load_fixture_rows(provider_config, request)
            if provider_type == "fixture"
            else import_rows_from_request(request)
        )
        normalized = normalize_rows(rows, request, provider_type)
    except ValueError as exc:
        return error_response(str(exc))

    if action == "search_content":
        limit = max(1, int(request.get("limit", len(normalized)) or len(normalized)))
        return {"status": "ok", "records": normalized[:limit]}
    if action == "fetch_author_feed":
        return {"status": "ok", "records": normalized}
    if action == "extract_metrics":
        first = normalized[0]
        return {"status": "ok", "metrics": first["metrics"], "record": first}
    if action == "fetch_article":
        return {"status": "ok", "record": normalized[0]}
    return {"status": "ok", "record": normalized[0]}


def main() -> int:
    args = parse_args()
    request = read_json(args.request_path)
    config = read_json(args.config)
    response = run_request(request, config)
    text = json.dumps(response, ensure_ascii=False, indent=2)
    if args.output:
        write_json(args.output, response)
    print(text)
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
