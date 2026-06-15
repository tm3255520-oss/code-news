#!/usr/bin/env python3
"""Generate a traffic-first report from peer content samples."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable


NUMERIC_FIELDS = ["views", "likes", "comments", "bookmarks", "shares"]
GROUP_FIELDS = ["topic", "angle", "format", "hook_type", "cover_type", "cta_type"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a markdown insight report from peer content samples."
    )
    parser.add_argument("csv_path", type=Path, help="Path to the peer sample CSV file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output markdown file path.",
    )
    parser.add_argument(
        "--min-group-samples",
        type=int,
        default=2,
        help="Minimum sample count for grouped pattern analysis.",
    )
    parser.add_argument(
        "--top-limit",
        type=int,
        default=5,
        help="How many rows or groups to show in leaderboard sections.",
    )
    return parser.parse_args()


def to_float(value: str) -> float:
    text = str(value or "").strip().replace(",", "")
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


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def average(values: Iterable[float]) -> float:
    items = list(values)
    return mean(items) if items else 0.0


def normalize_text(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items()}

            row["platform"] = normalize_text(row.get("platform", ""), "unknown")
            row["account_name"] = normalize_text(row.get("account_name", ""), "unknown")
            row["title"] = normalize_text(row.get("title", ""), "untitled")

            for field in GROUP_FIELDS:
                row[field] = normalize_text(row.get(field, ""), "unknown")

            for field in NUMERIC_FIELDS:
                row[field] = max(0.0, to_float(row.get(field, "0")))

            row["like_rate"] = safe_div(row["likes"], row["views"])
            row["comment_rate"] = safe_div(row["comments"], row["views"])
            row["bookmark_rate"] = safe_div(row["bookmarks"], row["views"])
            row["share_rate"] = safe_div(row["shares"], row["views"])
            row["engagement_rate"] = safe_div(
                row["likes"] + row["comments"] + row["bookmarks"] + row["shares"],
                row["views"],
            )
            title = row["title"]
            row["title_length"] = len(title)
            row["title_has_number"] = any(ch.isdigit() for ch in title)
            row["title_has_question"] = any(ch in title for ch in "?？")
            row["title_has_colon"] = any(ch in title for ch in ":：")
            rows.append(row)
    return rows


def assign_rank_scores(rows: list[dict], metric: str) -> None:
    if not rows:
        return
    ordered = sorted(range(len(rows)), key=lambda idx: rows[idx][metric], reverse=True)
    total = len(rows)
    for position, idx in enumerate(ordered):
        rank_score = 1.0 if total == 1 else 1.0 - (position / (total - 1))
        rows[idx][f"{metric}_rank_score"] = rank_score


def add_platform_relative_scores(rows: list[dict]) -> None:
    by_platform: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_platform[row["platform"]].append(row)

    for platform_rows in by_platform.values():
        for metric in [
            "views",
            "like_rate",
            "comment_rate",
            "bookmark_rate",
            "share_rate",
            "engagement_rate",
        ]:
            assign_rank_scores(platform_rows, metric)

        for row in platform_rows:
            row["traffic_score"] = round(
                (
                    0.40 * row.get("views_rank_score", 0.0)
                    + 0.25 * row.get("like_rate_rank_score", 0.0)
                    + 0.25 * row.get("comment_rate_rank_score", 0.0)
                    + 0.05 * row.get("bookmark_rate_rank_score", 0.0)
                    + 0.05 * row.get("share_rate_rank_score", 0.0)
                )
                * 100,
                2,
            )
            row["discussion_score"] = round(
                (
                    0.60 * row.get("comment_rate_rank_score", 0.0)
                    + 0.25 * row.get("views_rank_score", 0.0)
                    + 0.15 * row.get("share_rate_rank_score", 0.0)
                )
                * 100,
                2,
            )


def top_rows(rows: list[dict], metric: str, limit: int) -> list[dict]:
    return sorted(rows, key=lambda row: row[metric], reverse=True)[:limit]


def row_label(row: dict) -> str:
    parts = [
        row.get("platform", "unknown"),
        row.get("account_name", "unknown"),
        row.get("post_date", "") or row.get("captured_date", ""),
        row.get("title", "untitled"),
    ]
    return " | ".join(part for part in parts if part)


def metric_lines(rows: list[dict], metric: str, label: str, limit: int, formatter) -> list[str]:
    return [
        f"- {row_label(row)}: {label} `{formatter(row[metric])}`"
        for row in top_rows(rows, metric, limit)
    ]


def platform_summary(rows: list[dict]) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["platform"]].append(row)

    lines: list[str] = []
    for platform, items in sorted(grouped.items()):
        lines.append(
            "- "
            f"{platform}: `{len(items)}` samples, avg views `{average(row['views'] for row in items):.0f}`, "
            f"avg like rate `{pct(average(row['like_rate'] for row in items))}`, "
            f"avg comment rate `{pct(average(row['comment_rate'] for row in items))}`"
        )
    return lines


def grouped_summary(
    rows: list[dict],
    group_key: str,
    limit: int,
    min_group_samples: int,
    score_key: str = "traffic_score",
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row[group_key]].append(row)

    results: list[dict] = []
    for name, items in grouped.items():
        if len(items) < min_group_samples:
            continue
        results.append(
            {
                "name": name,
                "count": len(items),
                "avg_score": average(row[score_key] for row in items),
                "avg_views": average(row["views"] for row in items),
                "avg_like_rate": average(row["like_rate"] for row in items),
                "avg_comment_rate": average(row["comment_rate"] for row in items),
            }
        )

    return sorted(results, key=lambda item: item["avg_score"], reverse=True)[:limit]


def grouped_lines(items: list[dict]) -> list[str]:
    return [
        "- "
        f"{item['name']}: `{item['count']}` samples, avg traffic score `{item['avg_score']:.1f}`, "
        f"avg views `{item['avg_views']:.0f}`, avg like rate `{pct(item['avg_like_rate'])}`, "
        f"avg comment rate `{pct(item['avg_comment_rate'])}`"
        for item in items
    ]


def account_leaderboard(rows: list[dict], limit: int, min_group_samples: int) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = f"{row['platform']} | {row['account_name']}"
        grouped[key].append(row)

    ranked = []
    for key, items in grouped.items():
        if len(items) < min_group_samples:
            continue
        ranked.append(
            {
                "name": key,
                "count": len(items),
                "avg_score": average(row["traffic_score"] for row in items),
                "avg_views": average(row["views"] for row in items),
                "avg_comment_rate": average(row["comment_rate"] for row in items),
            }
        )

    ranked.sort(key=lambda item: item["avg_score"], reverse=True)
    return [
        "- "
        f"{item['name']}: `{item['count']}` samples, avg traffic score `{item['avg_score']:.1f}`, "
        f"avg views `{item['avg_views']:.0f}`, avg comment rate `{pct(item['avg_comment_rate'])}`"
        for item in ranked[:limit]
    ]


def title_feature_summary(rows: list[dict], top_slice: list[dict]) -> list[str]:
    def ratio(source: list[dict], key: str) -> float:
        return safe_div(sum(1 for row in source if row[key]), len(source))

    return [
        f"- Avg title length: all `{average(row['title_length'] for row in rows):.1f}`, top slice `{average(row['title_length'] for row in top_slice):.1f}`",
        f"- Number in title: all `{pct(ratio(rows, 'title_has_number'))}`, top slice `{pct(ratio(top_slice, 'title_has_number'))}`",
        f"- Question in title: all `{pct(ratio(rows, 'title_has_question'))}`, top slice `{pct(ratio(top_slice, 'title_has_question'))}`",
        f"- Colon in title: all `{pct(ratio(rows, 'title_has_colon'))}`, top slice `{pct(ratio(top_slice, 'title_has_colon'))}`",
    ]


def pick_best_group(
    rows: list[dict],
    group_key: str,
    min_group_samples: int,
    score_key: str = "traffic_score",
) -> dict | None:
    options = grouped_summary(
        rows,
        group_key=group_key,
        limit=1,
        min_group_samples=min_group_samples,
        score_key=score_key,
    )
    return options[0] if options else None


def build_action_lines(rows: list[dict], min_group_samples: int) -> list[str]:
    by_score = sorted(rows, key=lambda row: row["traffic_score"], reverse=True)
    top_slice = by_score[: max(1, len(by_score) // 3)]

    best_topic = pick_best_group(rows, "topic", min_group_samples)
    best_angle = pick_best_group(rows, "angle", min_group_samples)
    best_hook = pick_best_group(rows, "hook_type", min_group_samples)
    best_cover = pick_best_group(rows, "cover_type", min_group_samples)
    best_cta = pick_best_group(rows, "cta_type", min_group_samples, score_key="discussion_score")

    actions: list[str] = []
    if best_topic:
        actions.append(
            f"- Next-post focus: keep leaning into `{best_topic['name']}` because it leads the sample pool with avg traffic score `{best_topic['avg_score']:.1f}`."
        )
    if best_angle:
        actions.append(
            f"- Angle upgrade: prioritize `{best_angle['name']}` framing; it is outperforming other angles in both traffic and interaction."
        )
    if best_hook:
        actions.append(
            f"- Opening hook: test more `{best_hook['name']}` intros, because that hook pattern is showing the strongest average score."
        )
    if best_cover:
        actions.append(
            f"- Cover direction: reuse `{best_cover['name']}` style more often; it is the strongest current cover pattern in the sample set."
        )
    if best_cta and best_cta["name"] != "none":
        actions.append(
            f"- Comment strategy: end posts with `{best_cta['name']}` prompts, because that CTA style is leading discussion score."
        )

    number_gap = safe_div(
        sum(1 for row in top_slice if row["title_has_number"]),
        len(top_slice),
    ) - safe_div(sum(1 for row in rows if row["title_has_number"]), len(rows))
    question_gap = safe_div(
        sum(1 for row in top_slice if row["title_has_question"]),
        len(top_slice),
    ) - safe_div(sum(1 for row in rows if row["title_has_question"]), len(rows))
    colon_gap = safe_div(
        sum(1 for row in top_slice if row["title_has_colon"]),
        len(top_slice),
    ) - safe_div(sum(1 for row in rows if row["title_has_colon"]), len(rows))

    if number_gap >= 0.15:
        actions.append("- Title test: numeric titles are over-indexing in the top slice, so add more concrete numbers to title variants.")
    if question_gap >= 0.15:
        actions.append("- Title test: question-led titles are over-indexing in the top slice, so test more curiosity or stance-driven questions.")
    if colon_gap >= 0.15:
        actions.append("- Title test: colon-based titles are over-indexing in the top slice, so test more `topic: takeaway` structures.")

    if not actions:
        actions.append("- The sample size is still thin. Keep logging peer posts daily before making strong content bets.")

    return actions[:6]


def build_markdown(rows: list[dict], source_path: Path, min_group_samples: int, top_limit: int) -> str:
    add_platform_relative_scores(rows)
    ranked = sorted(rows, key=lambda row: row["traffic_score"], reverse=True)
    top_slice = ranked[: max(1, len(ranked) // 3)]

    total_views = sum(row["views"] for row in rows)
    total_likes = sum(row["likes"] for row in rows)
    total_comments = sum(row["comments"] for row in rows)
    accounts = {f"{row['platform']}|{row['account_name']}" for row in rows}
    recurring_topics = Counter(row["topic"] for row in rows).most_common(top_limit)

    lines = [
        "# Peer Content Traffic Report",
        "",
        f"- Source: `{source_path}`",
        f"- Sample count: `{len(rows)}`",
        f"- Platforms: `{len({row['platform'] for row in rows})}`",
        f"- Accounts tracked in sample: `{len(accounts)}`",
        f"- Total views captured: `{total_views:.0f}`",
        f"- Total likes captured: `{total_likes:.0f}`",
        f"- Total comments captured: `{total_comments:.0f}`",
        f"- Average like rate: `{pct(average(row['like_rate'] for row in rows))}`",
        f"- Average comment rate: `{pct(average(row['comment_rate'] for row in rows))}`",
        "",
        "## Platform Snapshot",
        "",
        *platform_summary(rows),
        "",
        "## Strongest Samples by Traffic Score",
        "",
        *metric_lines(ranked, "traffic_score", "traffic score", top_limit, lambda value: f"{value:.1f}"),
        "",
        "## Strongest Samples by Comment Rate",
        "",
        *metric_lines(rows, "comment_rate", "comment rate", top_limit, pct),
        "",
        "## Strongest Samples by Views",
        "",
        *metric_lines(rows, "views", "views", top_limit, lambda value: f"{value:.0f}"),
        "",
        "## Title Pattern Signals",
        "",
        *title_feature_summary(rows, top_slice),
        "",
        "## Topic Leaders",
        "",
        *grouped_lines(grouped_summary(rows, "topic", top_limit, min_group_samples)),
        "",
        "## Angle Leaders",
        "",
        *grouped_lines(grouped_summary(rows, "angle", top_limit, min_group_samples)),
        "",
        "## Hook Leaders",
        "",
        *grouped_lines(grouped_summary(rows, "hook_type", top_limit, min_group_samples)),
        "",
        "## Cover Leaders",
        "",
        *grouped_lines(grouped_summary(rows, "cover_type", top_limit, min_group_samples)),
        "",
        "## CTA Leaders",
        "",
        *grouped_lines(
            grouped_summary(
                rows,
                "cta_type",
                top_limit,
                min_group_samples,
                score_key="discussion_score",
            )
        ),
        "",
        "## Account Leaderboard",
        "",
        *account_leaderboard(rows, top_limit, min_group_samples),
        "",
        "## Frequent Topics",
        "",
        *[f"- {topic}: `{count}` samples" for topic, count in recurring_topics],
        "",
        "## Next Moves",
        "",
        *build_action_lines(rows, min_group_samples),
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = parse_args()
    rows = read_rows(args.csv_path)
    if not rows:
        raise SystemExit("No rows found in CSV file.")

    report = build_markdown(
        rows,
        source_path=args.csv_path,
        min_group_samples=max(1, args.min_group_samples),
        top_limit=max(1, args.top_limit),
    )
    print(report)

    if args.output:
        args.output.write_text(report, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
