#!/usr/bin/env python3
"""Generate a markdown report from article performance metrics."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable


NUMERIC_FIELDS = [
    "views",
    "likes",
    "comments",
    "bookmarks",
    "shares",
    "followers_gained",
]


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a markdown traffic report from content metrics CSV."
    )
    parser.add_argument("csv_path", type=Path, help="Path to the metrics CSV file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for the markdown report. Defaults to stdout only.",
    )
    return parser.parse_args()


def to_float(value: str) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items()}
            for field in NUMERIC_FIELDS:
                row[field] = to_float(row.get(field, "0"))

            row["views"] = max(row["views"], 0.0)
            row["likes"] = max(row["likes"], 0.0)
            row["comments"] = max(row["comments"], 0.0)
            row["bookmarks"] = max(row["bookmarks"], 0.0)
            row["shares"] = max(row["shares"], 0.0)
            row["followers_gained"] = max(row["followers_gained"], 0.0)

            row["like_rate"] = safe_div(row["likes"], row["views"])
            row["comment_rate"] = safe_div(row["comments"], row["views"])
            row["bookmark_rate"] = safe_div(row["bookmarks"], row["views"])
            row["share_rate"] = safe_div(row["shares"], row["views"])
            row["engagement_rate"] = safe_div(
                row["likes"] + row["comments"] + row["bookmarks"] + row["shares"],
                row["views"],
            )
            row["title_length"] = len(row.get("title", ""))
            row["title_has_number"] = any(ch.isdigit() for ch in row.get("title", ""))
            row["title_has_question"] = any(ch in row.get("title", "") for ch in "?？")
            row["title_has_colon"] = any(ch in row.get("title", "") for ch in ":：")
            rows.append(row)

    return rows


def assign_rank_scores(rows: list[dict], key: str) -> None:
    if not rows:
        return

    ordered = sorted(range(len(rows)), key=lambda idx: rows[idx][key], reverse=True)
    total = len(rows)
    for position, idx in enumerate(ordered):
        if total == 1:
            rows[idx][f"{key}_rank_score"] = 1.0
        else:
            rows[idx][f"{key}_rank_score"] = 1.0 - (position / (total - 1))


def add_composite_scores(rows: list[dict]) -> None:
    for metric in ["views", "like_rate", "comment_rate", "engagement_rate"]:
        assign_rank_scores(rows, metric)

    for row in rows:
        row["composite_score"] = round(
            (
                0.50 * row.get("views_rank_score", 0.0)
                + 0.20 * row.get("like_rate_rank_score", 0.0)
                + 0.20 * row.get("comment_rate_rank_score", 0.0)
                + 0.10 * row.get("engagement_rate_rank_score", 0.0)
            )
            * 100,
            2,
        )


def top_rows(rows: list[dict], key: str, limit: int = 5) -> list[dict]:
    return sorted(rows, key=lambda row: row[key], reverse=True)[:limit]


def average(items: Iterable[float]) -> float:
    values = list(items)
    return mean(values) if values else 0.0


def title_feature_summary(rows: list[dict], top_slice: list[dict]) -> list[str]:
    def ratio(source: list[dict], key: str) -> float:
        if not source:
            return 0.0
        return sum(1 for row in source if row[key]) / len(source)

    lines = [
        f"- 平均标题长度：全部 `{average(row['title_length'] for row in rows):.1f}`，高表现 `{average(row['title_length'] for row in top_slice):.1f}`",
        f"- 含数字标题占比：全部 `{percent(ratio(rows, 'title_has_number'))}`，高表现 `{percent(ratio(top_slice, 'title_has_number'))}`",
        f"- 含问句标题占比：全部 `{percent(ratio(rows, 'title_has_question'))}`，高表现 `{percent(ratio(top_slice, 'title_has_question'))}`",
        f"- 含冒号标题占比：全部 `{percent(ratio(rows, 'title_has_colon'))}`，高表现 `{percent(ratio(top_slice, 'title_has_colon'))}`",
    ]
    return lines


def platform_summary(rows: list[dict]) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row.get("platform", "未填写") or "未填写"].append(row)

    lines = []
    for platform, items in sorted(grouped.items(), key=lambda item: item[0]):
        lines.append(
            f"- {platform}：`{len(items)}` 篇，平均阅读 `{average(row['views'] for row in items):.0f}`，平均点赞率 `{percent(average(row['like_rate'] for row in items))}`，平均评论率 `{percent(average(row['comment_rate'] for row in items))}`"
        )
    return lines


def topic_summary(rows: list[dict], limit: int = 5) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        topic = row.get("topic", "").strip() or "未标注"
        grouped[topic].append(row)

    ranked = sorted(
        grouped.items(),
        key=lambda item: average(row["composite_score"] for row in item[1]),
        reverse=True,
    )
    lines = []
    for topic, items in ranked[:limit]:
        lines.append(
            f"- {topic}：`{len(items)}` 篇，平均综合分 `{average(row['composite_score'] for row in items):.1f}`，平均阅读 `{average(row['views'] for row in items):.0f}`"
        )
    return lines


def row_label(row: dict) -> str:
    date = row.get("date", "")
    platform = row.get("platform", "未填平台")
    title = row.get("title", "未命名文章")
    return f"{date} | {platform} | {title}"


def metric_lines(rows: list[dict], key: str, label: str, formatter) -> list[str]:
    lines = []
    for row in top_rows(rows, key):
        lines.append(f"- {row_label(row)}：{label} `{formatter(row[key])}`")
    return lines


def build_markdown(rows: list[dict], source_path: Path) -> str:
    add_composite_scores(rows)
    ranked = sorted(rows, key=lambda row: row["composite_score"], reverse=True)
    top_slice = ranked[: max(1, len(ranked) // 3)]

    total_views = sum(row["views"] for row in rows)
    total_likes = sum(row["likes"] for row in rows)
    total_comments = sum(row["comments"] for row in rows)

    recurring_topics = Counter(
        row.get("topic", "").strip() or "未标注" for row in rows
    ).most_common(5)

    lines = [
        "# 内容表现周报",
        "",
        f"- 数据源：`{source_path}`",
        f"- 样本数量：`{len(rows)}` 篇",
        f"- 总阅读：`{total_views:.0f}`",
        f"- 总点赞：`{total_likes:.0f}`",
        f"- 总评论：`{total_comments:.0f}`",
        f"- 平均点赞率：`{percent(average(row['like_rate'] for row in rows))}`",
        f"- 平均评论率：`{percent(average(row['comment_rate'] for row in rows))}`",
        "",
        "## 平台概览",
        "",
        *platform_summary(rows),
        "",
        "## 综合表现 Top 5",
        "",
        *metric_lines(ranked, "composite_score", "综合分", lambda value: f"{value:.1f}"),
        "",
        "## 阅读量 Top 5",
        "",
        *metric_lines(rows, "views", "阅读", lambda value: f"{value:.0f}"),
        "",
        "## 点赞率 Top 5",
        "",
        *metric_lines(rows, "like_rate", "点赞率", percent),
        "",
        "## 评论率 Top 5",
        "",
        *metric_lines(rows, "comment_rate", "评论率", percent),
        "",
        "## 标题特征观察",
        "",
        *title_feature_summary(rows, top_slice),
        "",
        "## 题材方向观察",
        "",
        *topic_summary(rows),
        "",
        "## 高频题材",
        "",
        *[
            f"- {topic}：出现 `{count}` 次"
            for topic, count in recurring_topics
        ],
        "",
        "## 建议动作",
        "",
        "- 保留综合分和阅读量同时靠前的选题结构，作为下周重点复用对象。",
        "- 单独复盘评论率靠前的内容，提炼更能激发讨论的观点表达方式。",
        "- 单独复盘点赞率靠前的内容，提炼更容易形成认同感和收藏感的结构。",
        "- 对综合分靠后但阅读高的内容，重点检查正文价值密度和结尾互动设计。",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    rows = read_rows(args.csv_path)
    if not rows:
        raise SystemExit("No rows found in CSV file.")

    report = build_markdown(rows, args.csv_path)
    print(report)

    if args.output:
        args.output.write_text(report, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
