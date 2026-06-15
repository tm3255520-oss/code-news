from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PLATFORM_KEYS = ("toutiao", "zhihu", "wechat", "xiaohongshu")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def build_fingerprint(payload: dict[str, Any]) -> str:
    basis = {
        "title": normalize_text(payload.get("title")),
        "summary": normalize_text(payload.get("summary")),
        "article_blocks": [
            normalize_text(block) for block in payload.get("article_blocks", []) or []
        ],
    }
    return hashlib.sha256(
        json.dumps(basis, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def generated_dir_from_payload_path(payload_path: Path, payload: dict[str, Any]) -> Path:
    return payload_path.parent / "generated" / str(payload.get("slug") or payload_path.stem)


def pipeline_state_path(payload_path: Path, payload: dict[str, Any]) -> Path:
    return generated_dir_from_payload_path(payload_path, payload) / "pipeline-state.json"


def summarize_assets(generated_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    cover_exists = any(
        (generated_dir / name).exists() for name in ("cover.png", "cover.jpg", "cover.jpeg")
    )
    if not cover_exists:
        missing.append("cover.png|cover.jpg|cover.jpeg")

    image_count = 0
    for index, item in enumerate(payload.get("body_images", []) or [], start=1):
        file_name = item.get("file_name") or f"body-{index:02d}.png"
        if (generated_dir / file_name).exists():
            image_count += 1
        else:
            missing.append(file_name)

    return {
        "coverExists": cover_exists,
        "bodyImageCount": image_count,
        "missingFiles": missing,
    }


def empty_platform_state() -> dict[str, Any]:
    return {
        "status": "ready",
        "attemptCount": 0,
        "lastAttemptAt": None,
        "publishedAt": None,
        "url": None,
        "titleUsed": None,
        "verificationSource": None,
        "error": None,
    }


def initialize_pipeline_state(payload_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    generated_dir = generated_dir_from_payload_path(payload_path, payload)
    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or payload_path.stem),
        "fingerprint": build_fingerprint(payload),
        "title": normalize_text(payload.get("title")),
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "qualityGate": {},
        "assets": summarize_assets(generated_dir, payload),
        "platforms": {key: empty_platform_state() for key in PLATFORM_KEYS},
    }


def load_pipeline_state(state_path: Path) -> dict[str, Any]:
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_pipeline_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_platform_state(state: dict[str, Any], platform: str, **changes: Any) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state.setdefault("platforms", {})
    next_state["platforms"].setdefault(platform, empty_platform_state())
    next_state["platforms"][platform].update(changes)
    next_state["updatedAt"] = now_iso()
    return next_state


def ensure_platform_entries(state: dict[str, Any]) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state.setdefault("platforms", {})
    for platform in PLATFORM_KEYS:
        next_state["platforms"].setdefault(platform, empty_platform_state())
    next_state["updatedAt"] = now_iso()
    return next_state
