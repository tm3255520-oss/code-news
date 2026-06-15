#!/usr/bin/env python3
"""Flag low-signal article drafts before publish."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

try:
    from sync_recent_metrics_to_log import DEFAULT_OUTPUT as DEFAULT_METRICS_CSV
    from sync_recent_metrics_to_log import infer_topic
except ModuleNotFoundError:
    from scripts.sync_recent_metrics_to_log import DEFAULT_OUTPUT as DEFAULT_METRICS_CSV
    from scripts.sync_recent_metrics_to_log import infer_topic


ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT / ".tmp"
DEFAULT_PAYLOAD_GLOB = "toutiao_payload_*.json"
DEFAULT_REPORT_DIR = TMP_DIR / "quality-gates"

ABSTRACT_PHRASES = [
    "放在一起看",
    "说明同一件事",
    "更值得注意",
    "更重要的变化",
    "过去一个多",
    "真正值钱的",
    "真正值得",
    "这背后的变化",
    "如果你最近还在用",
    "越来越多官方产品更新都在说明",
]

PRACTICAL_WORDS = [
    "省",
    "赚钱",
    "多赚",
    "步骤",
    "方法",
    "模板",
    "清单",
    "案例",
    "实测",
    "避坑",
    "判断",
    "怎么做",
    "适合",
    "流程",
    "效率",
]

OPINION_WORDS = [
    "我判断",
    "我建议",
    "我更建议",
    "我的结论",
    "我踩过",
    "我会",
    "我自己",
    "我不建议",
    "在我看来",
]

COVER_TEMPLATE_MARKERS = [
    "WHY NOW",
    "KEY SIGNAL",
    "SHIFT SIGNAL",
    "DECISION FRAME",
    "WORKFLOW VALUE",
    "MATURITY TEST",
    "WHAT CHANGED",
    "FRAMEWORK",
]

TITLE_SHORT_TARGET = 22
TITLE_HARD_LIMIT = 30

TOPIC_FALLBACKS: list[tuple[str, tuple[str, ...]]] = [
    ("workflow-shift", ("流程", "工作流", "夜班", "schedule", "trigger", "后台", "自动运行")),
    ("approval-first", ("审批", "请示", "approval", "control", "trust")),
    ("shared-agents", ("共享", "workspace agents", "工作台", "agent")),
]


@dataclass
class CheckResult:
    severity: str
    title: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a traffic-first quality check against one generated payload.",
    )
    parser.add_argument(
        "payload_path",
        type=Path,
        help="Path to a generated payload json file.",
    )
    parser.add_argument(
        "--metrics-csv",
        type=Path,
        default=DEFAULT_METRICS_CSV,
        help="Path to the merged performance CSV.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown report output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional json report output path.",
    )
    parser.add_argument(
        "--exit-nonzero-on-block",
        action="store_true",
        help="Return exit code 2 when the quality gate blocks publish.",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def read_metrics_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {key: (value or "").strip() for key, value in raw.items()}
            for field in ["views", "likes", "comments", "bookmarks", "shares"]:
                try:
                    row[field] = float(str(row.get(field, "0")).replace(",", "") or 0)
                except ValueError:
                    row[field] = 0.0
            rows.append(row)
    return rows


def recent_payloads(current_path: Path, limit: int = 8) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(
        TMP_DIR.glob(DEFAULT_PAYLOAD_GLOB),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        if path == current_path:
            continue
        try:
            payload = read_json(path)
        except Exception:
            continue
        title = str(payload.get("title", "")).strip()
        payloads.append(
            {
                "path": str(path),
                "title": title,
                "topic": infer_topic_from_payload(payload),
            }
        )
        if len(payloads) >= limit:
            break
    return payloads


def title_overlap(a: str, b: str) -> float:
    left = set(a.replace("：", "").replace(":", ""))
    right = set(b.replace("：", "").replace(":", ""))
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def top_title_length(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return float(TITLE_SHORT_TARGET)
    ranked = sorted(rows, key=lambda row: float(row.get("views", 0.0)), reverse=True)
    top_slice = ranked[: max(1, len(ranked) // 3)]
    return mean(len(str(row.get("title", "")).strip()) for row in top_slice)


def average_views(rows: list[dict[str, Any]], topic: str | None = None) -> float:
    source = rows
    if topic:
        source = [row for row in rows if str(row.get("topic", "")).strip() == topic]
    if not source:
        return 0.0
    return mean(float(row.get("views", 0.0)) for row in source)


def infer_topic_from_payload(payload: dict[str, Any]) -> str:
    explicit_topic = str(payload.get("topic", "")).strip()
    if explicit_topic:
        return explicit_topic

    title = str(payload.get("title", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    blocks = payload.get("article_blocks", []) or []
    joined = " ".join([title, summary, *[str(block) for block in blocks[:4]]])

    topic = infer_topic(title, joined)
    if topic != "unlabeled":
        return topic

    lowered = joined.lower()
    for label, keywords in TOPIC_FALLBACKS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return label
    return "unlabeled"


def text_contains_any(text: str, phrases: list[str]) -> list[str]:
    normalized = text.strip()
    return [phrase for phrase in phrases if phrase in normalized]


def detect_cover_template(payload: dict[str, Any]) -> bool:
    cover = payload.get("cover", {}) or {}
    footer = str(cover.get("footer", ""))
    if footer.count("/") >= 2:
        return True

    images = payload.get("body_images", []) or []
    marker_hits = 0
    for image in images:
        fields = " ".join(
            str(image.get(key, ""))
            for key in ["kicker", "badge", "signal_label", "signal_value"]
        )
        if any(marker in fields for marker in COVER_TEMPLATE_MARKERS):
            marker_hits += 1
    return marker_hits >= 2


def opinion_density(blocks: list[str]) -> int:
    joined = "\n".join(blocks[:8])
    return len(text_contains_any(joined, OPINION_WORDS))


def build_checks(
    payload: dict[str, Any],
    metrics_rows: list[dict[str, Any]],
    recent: list[dict[str, Any]],
) -> list[CheckResult]:
    title = str(payload.get("title", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    blocks = [str(block).strip() for block in payload.get("article_blocks", []) if str(block).strip()]
    opening = "\n".join([summary, *blocks[:3]]).strip()
    topic = infer_topic_from_payload(payload)

    results: list[CheckResult] = []

    recent_same_topic = [item for item in recent if item.get("topic") == topic]
    topic_avg_views = average_views(metrics_rows, topic)
    overall_avg_views = average_views(metrics_rows)
    if len(recent_same_topic) >= 3 and (
        topic_avg_views == 0 or topic_avg_views < max(overall_avg_views * 0.8, 30)
    ):
        results.append(
            CheckResult(
                "fail",
                "题材疲劳",
                f"`{topic}` 最近已经连续出现 {len(recent_same_topic) + 1} 次，现有平均阅读只有 {topic_avg_views:.0f}，继续复写大概率还是低流量。",
            )
        )
    elif len(recent_same_topic) >= 2:
        results.append(
            CheckResult(
                "warn",
                "题材重复",
                f"`{topic}` 在最近发文里已经很密，除非这次是新案例或新教程，否则容易被读者当成换词重发。",
            )
        )

    similar_titles = [
        item for item in recent if title_overlap(title, str(item.get("title", ""))) >= 0.42
    ]
    if similar_titles:
        results.append(
            CheckResult(
                "warn",
                "标题骨架重复",
                f"最近已有 {len(similar_titles)} 个标题和这篇高度相似，说明我们在复用同一套句式。",
            )
        )

    top_avg_length = top_title_length(metrics_rows)
    title_length = len(title)
    if title_length > TITLE_HARD_LIMIT:
        results.append(
            CheckResult(
                "fail",
                "标题过长",
                f"当前标题长度 {title_length}，已经明显超过近期开得动的短标题区间（样本上限参考 {top_avg_length:.1f}）。",
            )
        )
    elif title_length > max(top_avg_length + 3, 24):
        results.append(
            CheckResult(
                "warn",
                "标题偏长",
                f"当前标题长度 {title_length}，比高表现样本均值 {top_avg_length:.1f} 更长，容易在信息流里显得拖。",
            )
        )

    if "：" in title or ":" in title:
        results.append(
            CheckResult(
                "warn",
                "标题像报告题",
                "冒号标题在我们的低表现样本里占比过高，容易显得像摘要或周报，而不是读者会点开的入口。",
            )
        )

    abstract_hits = text_contains_any(opening, ABSTRACT_PHRASES)
    if len(abstract_hits) >= 2:
        results.append(
            CheckResult(
                "fail",
                "开头套话重",
                f"开头命中了 {len(abstract_hits)} 个抽象套话信号：{', '.join(abstract_hits[:4])}。",
            )
        )
    elif len(abstract_hits) == 1:
        results.append(
            CheckResult(
                "warn",
                "开头偏抽象",
                f"开头已经出现 `{abstract_hits[0]}` 这类空泛连接句，读者很容易在前两段就滑走。",
            )
        )

    practical_hits = text_contains_any(f"{title}\n{opening}", PRACTICAL_WORDS)
    if not practical_hits:
        results.append(
            CheckResult(
                "fail",
                "没有具体收益",
                "标题和开头都没有把读者能得到什么说透，更像行业观察，不像读者要立刻点开的内容。",
            )
        )

    if opinion_density(blocks) == 0:
        results.append(
            CheckResult(
                "warn",
                "缺少作者判断",
                "前半篇几乎看不到明确的个人判断或经历，读起来会像信息搬运，而不是有立场的内容。",
            )
        )

    if detect_cover_template(payload):
        results.append(
            CheckResult(
                "warn",
                "封面和配图模板味重",
                "封面 footer、正文图 badge 和卡片结构高度固定，容易被识别成同一套咨询风模板反复换词。",
            )
        )

    if len(payload.get("sources", []) or []) <= 3 and len(blocks) >= 12:
        results.append(
            CheckResult(
                "warn",
                "论证密度不够",
                "篇幅已经很长，但有效信源和案例不多，容易形成大段抽象分析堆叠。",
            )
        )

    return results


def score_checks(checks: list[CheckResult]) -> int:
    score = 100
    for item in checks:
        if item.severity == "fail":
            score -= 18
        elif item.severity == "warn":
            score -= 8
    return max(score, 0)


def evaluate_gate(
    *,
    score: int,
    checks: list[CheckResult],
    min_score: int = 80,
) -> dict[str, Any]:
    fail_count = sum(1 for item in checks if item.severity == "fail")
    warn_count = sum(1 for item in checks if item.severity == "warn")
    if fail_count:
        return {
            "status": "blocked",
            "reason": "contains_fail_items",
            "score": score,
            "failCount": fail_count,
            "warnCount": warn_count,
        }
    if score < min_score:
        return {
            "status": "blocked",
            "reason": "score_below_minimum",
            "score": score,
            "failCount": fail_count,
            "warnCount": warn_count,
        }
    return {
        "status": "passed",
        "reason": "ready_for_publish",
        "score": score,
        "failCount": fail_count,
        "warnCount": warn_count,
    }


def suggestion_lines(checks: list[CheckResult], topic: str) -> list[str]:
    suggestions: list[str] = []
    if any(item.title in {"题材疲劳", "题材重复"} for item in checks):
        suggestions.append("先停掉同题趋势解读，换成工具实测、案例拆解或明确教程。")
    if any(item.title in {"标题过长", "标题偏长", "标题像报告题"} for item in checks):
        suggestions.append("把标题改成短结论句，优先写结果、损失或明确收益，默认不再用冒号。")
    if any(item.title in {"开头套话重", "开头偏抽象", "没有具体收益"} for item in checks):
        suggestions.append("前两段直接写“谁会踩坑/谁能省时间/具体能拿走什么”，不要先做行业总述。")
    if any(item.title == "缺少作者判断" for item in checks):
        suggestions.append("正文里至少补一段个人判断、真实测试结论或反例，不要只复述平台更新。")
    if any(item.title == "封面和配图模板味重" for item in checks):
        suggestions.append("下一篇封面改成单视觉或单结论，不再复用多卡片咨询风结构。")
    if not suggestions:
        suggestions.append("当前草稿通过度尚可，但仍建议用结果优先标题和更强的读者场景开头。")
    suggestions.append(f"当前题材 `{topic}` 如果继续写，优先换成“教程 / 结果 / 实测”角度，而不是再写趋势判断。")
    return suggestions[:5]


def build_markdown(
    *,
    payload_path: Path,
    payload: dict[str, Any],
    topic: str,
    checks: list[CheckResult],
    recent: list[dict[str, Any]],
    metrics_rows: list[dict[str, Any]],
) -> str:
    score = score_checks(checks)
    severity_order = {"fail": 0, "warn": 1, "pass": 2}
    ordered = sorted(checks, key=lambda item: (severity_order[item.severity], item.title))
    fail_count = sum(1 for item in checks if item.severity == "fail")
    warn_count = sum(1 for item in checks if item.severity == "warn")

    lines = [
        "# 内容质检结果",
        "",
        f"- 稿件：`{payload_path}`",
        f"- 标题：`{payload.get('title', '')}`",
        f"- 题材：`{topic}`",
        f"- 质检分：`{score}`",
        f"- 风险统计：`fail={fail_count}`，`warn={warn_count}`",
        "",
        "## 主要问题",
        "",
    ]

    if ordered:
        for item in ordered:
            lines.append(f"- [{item.severity.upper()}] {item.title}：{item.detail}")
    else:
        lines.append("- 没有发现明显的低质信号。")

    lines.extend(
        [
            "",
            "## 背景参照",
            "",
            f"- 最近可对比草稿数：`{len(recent)}`",
            f"- 已归档表现样本数：`{len(metrics_rows)}`",
            "",
            "## 修改建议",
            "",
        ]
    )
    for suggestion in suggestion_lines(checks, topic):
        lines.append(f"- {suggestion}")

    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- `80+`：可以发，但仍要做平台化改写。",
            "- `60-79`：建议改后再发。",
            "- `59 以下`：默认打回，不应该直接进发布链路。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    payload_path = args.payload_path.resolve()
    payload = read_json(payload_path)
    metrics_rows = read_metrics_rows(args.metrics_csv)
    recent = recent_payloads(payload_path)
    topic = infer_topic_from_payload(payload)
    checks = build_checks(payload, metrics_rows, recent)
    score = score_checks(checks)
    gate = evaluate_gate(score=score, checks=checks, min_score=80)

    report = {
        "payloadPath": str(payload_path),
        "title": str(payload.get("title", "")).strip(),
        "topic": topic,
        "score": score,
        "gate": gate,
        "checks": [
            {"severity": item.severity, "title": item.title, "detail": item.detail}
            for item in checks
        ],
        "suggestions": suggestion_lines(checks, topic),
    }

    markdown = build_markdown(
        payload_path=payload_path,
        payload=payload,
        topic=topic,
        checks=checks,
        recent=recent,
        metrics_rows=metrics_rows,
    )

    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(markdown)
    if args.exit_nonzero_on_block and gate["status"] == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
