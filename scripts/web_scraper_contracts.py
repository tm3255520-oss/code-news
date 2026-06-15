from __future__ import annotations

import json
from pathlib import Path
from typing import Any


METRIC_ALIASES = {
    "views": ("views", "view_count", "read_count", "reads"),
    "likes": ("likes", "like_count"),
    "comments": ("comments", "comment_count"),
    "favorites": ("favorites", "bookmarks", "favorite_count", "bookmark_count"),
    "shares": ("shares", "share_count"),
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def normalize_platform(value: Any) -> str:
    text = normalize_text(value).lower()
    aliases = {
        "jinritoutiao": "toutiao",
        "今日头条": "toutiao",
        "头条": "toutiao",
        "公众号": "wechat",
        "微信公众号": "wechat",
        "weixin": "wechat",
        "wechat": "wechat",
        "知乎": "zhihu",
        "zhihu": "zhihu",
        "小红书": "xiaohongshu",
        "xhs": "xiaohongshu",
    }
    return aliases.get(text, text or "unknown")


def to_int(value: Any) -> int:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0
    try:
        return max(0, int(float(text)))
    except ValueError:
        return 0


def normalize_metrics(payload: dict[str, Any]) -> dict[str, int]:
    metrics_source = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
    normalized: dict[str, int] = {}
    for target, aliases in METRIC_ALIASES.items():
        value = 0
        for alias in aliases:
            if alias in metrics_source:
                value = to_int(metrics_source.get(alias))
                break
        normalized[target] = value
    return normalized


def normalize_record(
    payload: dict[str, Any],
    *,
    platform: str | None = None,
    record_type: str = "article",
    capture_method: str = "unknown",
) -> dict[str, Any]:
    title = normalize_text(payload.get("title"))
    summary = normalize_text(payload.get("summary") or payload.get("content") or payload.get("excerpt"))
    url = normalize_text(payload.get("url"))
    author = normalize_text(payload.get("author") or payload.get("account_name") or payload.get("source"))

    if not title and not summary:
        raise ValueError("normalized record requires title or summary")

    tags = [normalize_text(item) for item in payload.get("tags", []) or [] if normalize_text(item)]
    published_at = normalize_text(payload.get("publishedAt") or payload.get("publish_time") or payload.get("post_date"))

    return {
        "platform": normalize_platform(platform or payload.get("platform")),
        "recordType": normalize_text(record_type) or "article",
        "author": author or "unknown",
        "title": title or "untitled",
        "url": url,
        "publishedAt": published_at or None,
        "metrics": normalize_metrics(payload),
        "content": {
            "summary": summary,
            "rawTextPath": normalize_text(payload.get("rawTextPath")) or None,
        },
        "meta": {
            "topic": normalize_text(payload.get("topic")) or "unclassified",
            "tags": tags,
            "captureMethod": capture_method,
            "sourceFields": {
                "author": author,
                "publishedAt": published_at,
            },
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
