#!/usr/bin/env python3
"""Normalize recent platform metrics into the shared performance CSV schema."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT / ".tmp" / "analytics"
DEFAULT_OUTPUT = ROOT / ".tmp" / "latest-content-performance-log.csv"


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync recent WeChat, Zhihu, Toutiao, and XHS metrics into one CSV."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path.",
    )
    return parser.parse_args()


def read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_number(value: Any) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0.0
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]

    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        year = digits[0].zfill(4)
        month = digits[1].zfill(2)
        day = digits[2].zfill(2)
        return f"{year}-{month}-{day}"

    return text


TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("ai-subscriptions", ("订阅", "会员", "付费", "花钱", "工具名", "值不值得")),
    ("workflow-shift", ("prompt", "Prompt", "上下文", "工作流", "workflow")),
    ("google-search-ai", ("Google Search", "谷歌搜索", "AI搜索", "搜索")),
    ("google-io-agentic", ("Google I/O", "替你做事")),
    ("video-platform-ai-policy", ("YouTube", "换脸", "平台新规", "平台规则")),
    ("design-tools", ("Canva", "设计工具")),
]


def infer_topic(title: str, notes: str = "") -> str:
    text = f"{title} {notes}".strip()
    lowered = text.lower()
    for topic, keywords in TOPIC_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return topic
    return "unlabeled"


def base_row(
    *,
    date: str,
    platform: str,
    title: str,
    content_type: str,
    url: str = "",
    views: float = 0.0,
    likes: float = 0.0,
    comments: float = 0.0,
    bookmarks: float = 0.0,
    shares: float = 0.0,
    followers_gained: float = 0.0,
    topic: str = "unlabeled",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "date": date,
        "platform": platform,
        "title": title,
        "topic": topic,
        "content_type": content_type,
        "url": url,
        "views": int(views),
        "likes": int(likes),
        "comments": int(comments),
        "bookmarks": int(bookmarks),
        "shares": int(shares),
        "followers_gained": int(followers_gained),
        "notes": notes,
    }


def from_wechat() -> list[dict[str, Any]]:
    rows = read_json(TMP_DIR / "wechat_recent_metrics_structured.json")
    output: list[dict[str, Any]] = []
    for item in rows:
        notes = []
        if item.get("status"):
            notes.append(f"status={item['status']}")
        if normalize_number(item.get("recommend", 0)):
            notes.append(f"recommend={int(normalize_number(item['recommend']))}")

        output.append(
            base_row(
                date=normalize_date(item.get("publishedAt", "")),
                platform="wechat",
                title=str(item.get("title", "")).strip(),
                topic=infer_topic(str(item.get("title", "")).strip(), "; ".join(notes)),
                content_type="long-article",
                url=str(item.get("url", "")).strip(),
                views=normalize_number(item.get("read")),
                likes=normalize_number(item.get("like")),
                comments=normalize_number(item.get("comment")),
                bookmarks=0,
                shares=normalize_number(item.get("share")),
                notes="; ".join(notes),
            )
        )
    return output


def from_zhihu() -> list[dict[str, Any]]:
    rows = read_json(TMP_DIR / "zhihu_recent_metrics_structured.json")
    output: list[dict[str, Any]] = []
    for item in rows:
        output.append(
            base_row(
                date=normalize_date(item.get("date", "")),
                platform="zhihu",
                title=str(item.get("title", "")).strip(),
                topic=infer_topic(str(item.get("title", "")).strip()),
                content_type="long-article",
                url=str(item.get("url", "")).strip(),
                views=normalize_number(item.get("read")),
                likes=normalize_number(item.get("agree")),
                comments=normalize_number(item.get("comment")),
                bookmarks=normalize_number(item.get("collect")),
                shares=normalize_number(item.get("share")) + normalize_number(item.get("repost")),
            )
        )
    return output


def from_toutiao() -> list[dict[str, Any]]:
    rows = read_json(TMP_DIR / "toutiao_recent_metrics_structured.json")
    output: list[dict[str, Any]] = []
    for item in rows:
        impression = normalize_number(item.get("impression"))
        read = normalize_number(item.get("read"))
        notes = f"impression={int(impression)}"
        output.append(
            base_row(
                date=normalize_date(item.get("publishedAt", "")),
                platform="toutiao",
                title=str(item.get("title", "")).strip(),
                topic=infer_topic(str(item.get("title", "")).strip(), notes),
                content_type="article",
                views=read,
                likes=normalize_number(item.get("like")),
                comments=normalize_number(item.get("comment")),
                notes=notes,
            )
        )
    return output


def from_xhs() -> list[dict[str, Any]]:
    rows = read_json(TMP_DIR / "xhs_recent_metrics_structured.json")
    output: list[dict[str, Any]] = []
    for item in rows:
        output.append(
            base_row(
                date=normalize_date(item.get("publishedAt", "")),
                platform="xiaohongshu",
                title=str(item.get("title", "")).strip(),
                topic=infer_topic(str(item.get("title", "")).strip()),
                content_type="note",
                views=normalize_number(item.get("view")),
                likes=normalize_number(item.get("like")),
                comments=normalize_number(item.get("comment")),
                bookmarks=normalize_number(item.get("collect")),
                shares=normalize_number(item.get("share")),
            )
        )
    return output


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = (row["platform"], row["date"], row["title"])
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def collect_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(from_wechat())
    rows.extend(from_zhihu())
    rows.extend(from_toutiao())
    rows.extend(from_xhs())
    rows = dedupe(rows)
    rows.sort(key=lambda item: (item["date"], item["platform"], item["title"]), reverse=True)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "date",
        "platform",
        "title",
        "topic",
        "content_type",
        "url",
        "views",
        "likes",
        "comments",
        "bookmarks",
        "shares",
        "followers_gained",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows = collect_rows()
    write_csv(args.output, rows)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rowCount": len(rows),
                "platforms": sorted({row["platform"] for row in rows}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
