from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.pipeline_state import (
        PLATFORM_KEYS,
        build_fingerprint,
        empty_platform_state,
        ensure_platform_entries,
        initialize_pipeline_state,
        now_iso,
        save_pipeline_state,
        summarize_assets,
    )
    from scripts.platform_publish_adapters import map_toutiao_result, map_wechat_result, map_zhihu_result
except ModuleNotFoundError:
    from pipeline_state import (
        PLATFORM_KEYS,
        build_fingerprint,
        empty_platform_state,
        ensure_platform_entries,
        initialize_pipeline_state,
        now_iso,
        save_pipeline_state,
        summarize_assets,
    )
    from platform_publish_adapters import map_toutiao_result, map_wechat_result, map_zhihu_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill v3 pipeline states from legacy artifacts.")
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".tmp",
        help="Path to the legacy .tmp directory.",
    )
    return parser.parse_args()


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


def build_payload_index(tmp_dir: Path) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for path in tmp_dir.glob("*payload*.json"):
        data = read_json_file(path, None)
        if not isinstance(data, dict):
            continue
        slug = str(data.get("slug") or "").strip()
        if not slug:
            continue
        output[slug] = {
            "payloadPath": path,
            "payload": data,
        }
    return output


def payload_from_manifest(generated_dir: Path) -> dict[str, Any] | None:
    manifest = read_json_file(generated_dir / "manifest.json", None)
    if not isinstance(manifest, dict):
        return None

    body_images = []
    for item in manifest.get("bodyImages", []) or []:
        png_path = str(item.get("pngPath") or "").strip()
        if png_path:
            body_images.append({"file_name": Path(png_path).name})

    return {
        "slug": generated_dir.name,
        "title": str(manifest.get("title") or "").strip(),
        "summary": str(manifest.get("summary") or "").strip(),
        "article_blocks": [],
        "body_images": body_images,
    }


def initialize_state_without_payload_path(generated_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or generated_dir.name),
        "fingerprint": build_fingerprint(payload),
        "title": str(payload.get("title") or "").strip(),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "qualityGate": {},
        "assets": summarize_assets(generated_dir, payload),
        "platforms": {key: empty_platform_state() for key in PLATFORM_KEYS},
    }


def find_record(records: list[dict[str, Any]], slug: str, title: str) -> dict[str, Any] | None:
    for record in records:
        if slug and record.get("slug") == slug:
            return record
        if title and str(record.get("title") or "").strip() == title:
            return record
    return None


def xhs_mapping(record: dict[str, Any] | None) -> dict[str, Any]:
    if record and (record.get("publishedAt") or record.get("url")):
        return {
            "status": "published_verified",
            "publishedAt": record.get("publishedAt"),
            "url": record.get("url"),
            "verificationSource": "local_publish_record",
            "error": None,
        }
    return {
        "status": "ready",
        "publishedAt": None,
        "url": None,
        "verificationSource": "legacy_migration",
        "error": None,
    }


def build_index_item(generated_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": generated_dir.name,
        "statePath": str(generated_dir / "pipeline-state.json"),
        "hasManifest": (generated_dir / "manifest.json").exists(),
        "hasArticle": (generated_dir / "article.md").exists(),
        "coverExists": bool(state.get("assets", {}).get("coverExists")),
        "bodyImageCount": int(state.get("assets", {}).get("bodyImageCount", 0)),
        "platformStatuses": {
            key: value.get("status")
            for key, value in (state.get("platforms", {}) or {}).items()
        },
    }


def migrate_legacy_data(tmp_dir: Path) -> dict[str, Any]:
    tmp_dir = Path(tmp_dir)
    generated_root = tmp_dir / "generated"
    payload_index = build_payload_index(tmp_dir)
    toutiao_records = read_json_file(tmp_dir / "toutiao-publish-records.json", [])
    zhihu_records = read_json_file(tmp_dir / "zhihu-publish-records.json", [])
    wechat_records = read_json_file(tmp_dir / "wechat-publish-records.json", [])
    xhs_records = read_json_file(tmp_dir / "xhs-publish-records.json", [])

    created_count = 0
    indexed_items: list[dict[str, Any]] = []

    for generated_dir in sorted(path for path in generated_root.iterdir() if path.is_dir()):
        state_path = generated_dir / "pipeline-state.json"
        if state_path.exists():
            state = ensure_platform_entries(read_json_file(state_path, {}))
            save_pipeline_state(state_path, state)
            indexed_items.append(build_index_item(generated_dir, state))
            continue

        slug = generated_dir.name
        payload_entry = payload_index.get(slug)
        payload_path = payload_entry.get("payloadPath") if payload_entry else None
        payload = payload_entry.get("payload") if payload_entry else payload_from_manifest(generated_dir)
        if not payload:
            continue

        if payload_path:
            state = initialize_pipeline_state(payload_path, payload)
        else:
            state = initialize_state_without_payload_path(generated_dir, payload)
        state = ensure_platform_entries(state)

        title = str(payload.get("title") or "").strip()
        toutiao_record = find_record(toutiao_records if isinstance(toutiao_records, list) else [], slug, title)
        zhihu_record = find_record(zhihu_records if isinstance(zhihu_records, list) else [], slug, title)
        wechat_record = find_record(wechat_records if isinstance(wechat_records, list) else [], slug, title)
        xhs_record = find_record(xhs_records if isinstance(xhs_records, list) else [], slug, title)

        if toutiao_record:
            state["platforms"]["toutiao"].update(map_toutiao_result(toutiao_record, None))
        if zhihu_record:
            state["platforms"]["zhihu"].update(map_zhihu_result(zhihu_record))
        if wechat_record:
            state["platforms"]["wechat"].update(map_wechat_result(wechat_record))
        if xhs_record:
            state["platforms"]["xiaohongshu"].update(xhs_mapping(xhs_record))
        state["updatedAt"] = now_iso()

        save_pipeline_state(state_path, state)
        created_count += 1
        indexed_items.append(build_index_item(generated_dir, state))

    index_path = tmp_dir / "v3" / "legacy-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_payload = {
        "schemaVersion": 1,
        "generatedRoot": str(generated_root),
        "createdAt": now_iso(),
        "items": indexed_items,
    }
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "createdStateCount": created_count,
        "indexedCount": len(indexed_items),
        "indexPath": str(index_path),
    }


def main() -> int:
    args = parse_args()
    result = migrate_legacy_data(args.tmp_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
