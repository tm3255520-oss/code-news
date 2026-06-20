from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from scripts.generate_peer_content_insights import add_platform_relative_scores, build_markdown as build_peer_report
    from scripts.generate_peer_content_insights import grouped_summary, read_rows as read_peer_rows
    from scripts.run_benchmark_monitor import read_jsonl
    from scripts.web_scraper_contracts import write_jsonl
    from scripts.web_scraper_mcp import DEFAULT_CONFIG_PATH as DEFAULT_WEB_SCRAPER_CONFIG_PATH
    from scripts.web_scraper_mcp import read_json as read_web_scraper_json, run_request as run_web_scraper_request
except ModuleNotFoundError:
    from generate_peer_content_insights import add_platform_relative_scores, build_markdown as build_peer_report
    from generate_peer_content_insights import grouped_summary, read_rows as read_peer_rows
    from run_benchmark_monitor import read_jsonl
    from web_scraper_contracts import write_jsonl
    from web_scraper_mcp import DEFAULT_CONFIG_PATH as DEFAULT_WEB_SCRAPER_CONFIG_PATH
    from web_scraper_mcp import read_json as read_web_scraper_json, run_request as run_web_scraper_request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_REGISTRY_PATH = ROOT / "config" / "benchmark_source_registry.json"

WORKFLOW_KEYWORDS = (
    "workflow",
    "flow",
    "publish",
    "shipping",
    "ship",
    "pipeline",
    "system",
    "automation",
    "rework",
    "multi-platform",
    "distribution",
    "链路",
    "工作流",
    "分发",
    "发布",
    "自动化",
    "系统",
    "返工",
)
MISTAKE_KEYWORDS = (
    "don't",
    "dont",
    "do not",
    "avoid",
    "mistake",
    "wrong",
    "坑",
    "误区",
    "别",
    "不要",
    "买错",
    "避坑",
)
GUIDE_KEYWORDS = (
    "guide",
    "how to",
    "playbook",
    "framework",
    "check",
    "checklist",
    "guide:",
    "指南",
    "攻略",
    "全攻略",
    "判断",
    "清单",
)
COMPARISON_KEYWORDS = (
    "top",
    "vs",
    "compare",
    "comparison",
    "rank",
    "ranking",
    "review",
    "评测",
    "排行",
    "对比",
    "横评",
    "top ",
)
RESULT_KEYWORDS = (
    "faster",
    "without rework",
    "ship",
    "publish",
    "efficiency",
    "result",
    "win",
    "直接发",
    "效率",
    "少返工",
    "能发",
    "结果",
    "无人值守",
)
QUESTION_MARKS = ("?", "？")

PEER_SAMPLE_HEADERS = [
    "platform",
    "account_name",
    "title",
    "views",
    "likes",
    "comments",
    "bookmarks",
    "shares",
    "topic",
    "angle",
    "format",
    "hook_type",
    "cover_type",
    "cta_type",
    "post_date",
    "captured_date",
    "url",
]

PLATFORM_LABELS = {
    "toutiao": "今日头条",
    "zhihu": "知乎",
    "wechat": "公众号",
    "xiaohongshu": "小红书",
}
SIGNAL_ARTIFACT_NAMES = {
    "benchmarkSummaryPath": "benchmark-monitor.md",
    "viralAnalysisPath": "viral-analysis.md",
    "rewritePlanPath": "rewrite-plan.md",
}
BENCHMARK_REQUEST_NAME = "benchmark-request.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build benchmark monitor, viral analysis, and rewrite plan artifacts from normalized records."
    )
    parser.add_argument("records_path", type=Path, help="Normalized JSONL records path.")
    parser.add_argument("output_dir", type=Path, help="Generated slug output directory.")
    parser.add_argument("--slug", required=True, help="Content slug.")
    parser.add_argument("--current-title", required=True, help="Current working article title.")
    parser.add_argument("--min-group-samples", type=int, default=2, help="Minimum group sample size.")
    parser.add_argument("--top-limit", type=int, default=5, help="Top rows or groups to show.")
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PEER_SAMPLE_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def lowercase_joined(*parts: str) -> str:
    return " ".join(part for part in parts if part).lower()


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def title_has_number(title: str) -> bool:
    return any(ch.isdigit() for ch in title)


def detect_hook_type(title: str) -> str:
    lowered = title.lower()
    if contains_any(lowered, MISTAKE_KEYWORDS):
        return "mistake_cost"
    if any(mark in title for mark in QUESTION_MARKS):
        return "question"
    if contains_any(lowered, RESULT_KEYWORDS):
        return "result_first"
    if title_has_number(title) or contains_any(lowered, COMPARISON_KEYWORDS):
        return "list_or_rank"
    if contains_any(lowered, WORKFLOW_KEYWORDS):
        return "workflow"
    if contains_any(lowered, GUIDE_KEYWORDS):
        return "guide"
    return "direct"


def detect_angle(title: str, summary: str, tags: list[str]) -> str:
    lowered = lowercase_joined(title, summary, " ".join(tags))
    if contains_any(lowered, WORKFLOW_KEYWORDS):
        return "workflow"
    if contains_any(lowered, MISTAKE_KEYWORDS):
        return "mistake_avoidance"
    if contains_any(lowered, COMPARISON_KEYWORDS):
        return "comparison"
    if contains_any(lowered, GUIDE_KEYWORDS):
        return "guide"
    if contains_any(lowered, RESULT_KEYWORDS):
        return "result_first"
    return "general"


def detect_format(title: str) -> str:
    lowered = title.lower()
    if contains_any(lowered, GUIDE_KEYWORDS):
        return "guide"
    if contains_any(lowered, COMPARISON_KEYWORDS) or title_has_number(title):
        return "ranking"
    if contains_any(lowered, WORKFLOW_KEYWORDS):
        return "workflow_breakdown"
    if any(mark in title for mark in QUESTION_MARKS):
        return "qa"
    return "article"


def detect_cover_type(hook_type: str, angle: str) -> str:
    if hook_type == "mistake_cost":
        return "myth_vs_fact"
    if angle == "workflow":
        return "workflow_map"
    if hook_type == "list_or_rank":
        return "checklist_cover"
    if hook_type == "result_first":
        return "result_board"
    return "editorial_cover"


def detect_cta_type(title: str, comments: int) -> str:
    if comments >= 10:
        return "discussion_prompt"
    if any(mark in title for mark in QUESTION_MARKS):
        return "question_prompt"
    return "none"


def record_to_peer_sample(row: dict[str, Any]) -> dict[str, Any]:
    title = normalize_space(row.get("title"))
    content = row.get("content") if isinstance(row.get("content"), dict) else {}
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    summary = normalize_space(content.get("summary"))
    tags = [normalize_space(tag) for tag in meta.get("tags", []) if normalize_space(tag)]
    angle = detect_angle(title, summary, tags)
    hook_type = detect_hook_type(title)
    return {
        "platform": normalize_space(row.get("platform")) or "unknown",
        "account_name": normalize_space(row.get("author")) or "unknown",
        "title": title or "untitled",
        "views": int(metrics.get("views", 0) or 0),
        "likes": int(metrics.get("likes", 0) or 0),
        "comments": int(metrics.get("comments", 0) or 0),
        "bookmarks": int(metrics.get("favorites", 0) or 0),
        "shares": int(metrics.get("shares", 0) or 0),
        "topic": normalize_space(meta.get("topic")) or "unclassified",
        "angle": angle,
        "format": detect_format(title),
        "hook_type": hook_type,
        "cover_type": detect_cover_type(hook_type, angle),
        "cta_type": detect_cta_type(title, int(metrics.get("comments", 0) or 0)),
        "post_date": normalize_space(row.get("publishedAt")),
        "captured_date": current_date_label(),
        "url": normalize_space(row.get("url")),
    }


def current_date_label() -> str:
    return datetime.now().astimezone().date().isoformat()


def build_peer_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record_to_peer_sample(row) for row in rows]


def signal_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    ranked = sorted(rows, key=lambda item: item.get("traffic_score", 0.0), reverse=True)
    top_slice = ranked[: max(1, len(ranked) // 2)]
    counts = {
        "workflow": sum(1 for row in top_slice if row.get("angle") == "workflow"),
        "mistake": sum(1 for row in top_slice if row.get("hook_type") == "mistake_cost"),
        "guide": sum(1 for row in top_slice if row.get("format") == "guide"),
        "ranking": sum(1 for row in top_slice if row.get("format") == "ranking"),
        "result": sum(1 for row in top_slice if row.get("hook_type") == "result_first"),
    }
    return counts


def dominant_signal_names(rows: list[dict[str, Any]], limit: int = 3) -> list[str]:
    counts = signal_counts(rows)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, count in ordered if count > 0][:limit]


def platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def benchmark_reason(row: dict[str, Any]) -> str:
    title = str(row.get("title", ""))
    lowered = title.lower()
    if contains_any(lowered, WORKFLOW_KEYWORDS):
        return "标题直接把焦点放到工作流或发布链路。"
    if contains_any(lowered, MISTAKE_KEYWORDS):
        return "标题先放大错误成本，抓手比功能介绍更硬。"
    if contains_any(lowered, COMPARISON_KEYWORDS):
        return "适合观察选型、横评和榜单型标题的点击结构。"
    if contains_any(lowered, GUIDE_KEYWORDS):
        return "更偏指南和判断框架，适合公众号与知乎。"
    return "可作为同主题标题和结构参考。"


def build_benchmark_markdown(
    normalized_rows: list[dict[str, Any]],
    peer_rows: list[dict[str, Any]],
    *,
    slug: str,
    current_title: str,
    top_limit: int,
) -> str:
    ranked = sorted(peer_rows, key=lambda row: row["views"], reverse=True)
    signals = dominant_signal_names(peer_rows)
    evidence_urls = [row.get("url", "").strip() for row in ranked if row.get("url", "").strip()]

    lines = [
        "# 对标监控",
        "",
        f"- 日期：`{current_date_label()}`",
        f"- 当前文章：`{current_title}`",
        f"- 监控任务：`{slug}`",
        f"- 监控结论关键词：`{' / '.join(signals or ['workflow', 'guide'])}`",
        "- 本轮口径：先用公开可检索样本做标题和结构监控，不冒充平台后台热度榜。",
        "",
        "## 核心样本",
        "",
        "| 平台 | 来源/账号 | 时间快照 | 标题 | 为什么盯 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for row in ranked[:top_limit]:
        lines.append(
            "| "
            f"{platform_label(str(row['platform']))} | "
            f"{row['account_name']} | "
            f"{row.get('post_date') or 'unknown'} | "
            f"{row['title']} | "
            f"{benchmark_reason(row)} |"
        )

    lines.extend(
        [
            "",
            "## 今天确认到的监控结论",
            "",
            f"1. 同主题高表现样本里，`{signals[0] if signals else 'workflow'}` 是最稳定的主线，说明读者更关心链路结果，不只是单点功能。",
            "2. 标题抓手最强的不是产品名，而是`少返工`、`别买错`、`能不能发出去`这类错误成本和结果承诺。",
            "3. 适合作为后续仿写输入的，不是某一句标题，而是标题机制、开头机制和结构机制。",
            "",
            "## 这一步给当前稿的直接价值",
            "",
            f"- 当前稿 `{current_title}` 方向没有跑偏，但要继续往“决策和发布结果”靠，不要退回成纯工具盘点。",
            "- 后续生成时，优先放大工作流、发布、返工和适配这些词，而不是堆产品新闻。",
            "",
            "## 证据来源",
            "",
        ]
    )

    if evidence_urls:
        lines.extend([f"- {url}" for url in evidence_urls[:top_limit]])
    else:
        lines.append("- 本轮样本未包含可回溯 URL。")

    return "\n".join(lines).strip() + "\n"


def current_title_gap_lines(rows: list[dict[str, Any]], current_title: str) -> list[str]:
    lowered = current_title.lower()
    counts = signal_counts(rows)
    lines: list[str] = []

    if counts.get("result", 0) > 0 and not contains_any(lowered, RESULT_KEYWORDS):
        lines.append("- 当前标题有判断，但结果承诺还不够硬，可以把“少返工”或“能不能直接发”往前提。")
    if counts.get("mistake", 0) > 0 and not contains_any(lowered, MISTAKE_KEYWORDS):
        lines.append("- 当前标题没有明确错误成本，建议补上“别买错”“别先看模板”这类反常识抓手。")
    if counts.get("workflow", 0) > 0 and not contains_any(lowered, WORKFLOW_KEYWORDS):
        lines.append("- 当前标题需要更明确点出工作流或发布链路，否则会被读成普通工具盘点。")
    if title_has_number(current_title):
        lines.append("- 当前标题自带数字抓手，可以保留“几个判断”这种结构化优势。")
    if not lines:
        lines.append("- 当前标题方向基本对，但还可以继续压缩抽象表达，换成更具体的工作损失。")
    return lines


def platform_strategy_lines(rows: list[dict[str, Any]], platform: str) -> list[str]:
    sample_rows = [row for row in rows if row["platform"] == platform]
    if not sample_rows:
        return ["- 当前样本还薄，先按平台默认风格做一版。"]

    best_angle = grouped_summary(sample_rows, "angle", limit=1, min_group_samples=1)
    best_format = grouped_summary(sample_rows, "format", limit=1, min_group_samples=1)
    best_hook = grouped_summary(sample_rows, "hook_type", limit=1, min_group_samples=1)

    lines = [
        f"- 样本数：`{len(sample_rows)}`",
        f"- 当前平台更强的角度：`{best_angle[0]['name'] if best_angle else 'workflow'}`",
        f"- 当前平台更强的结构：`{best_format[0]['name'] if best_format else 'guide'}`",
        f"- 当前平台更强的标题机制：`{best_hook[0]['name'] if best_hook else 'direct'}`",
    ]

    if platform == "wechat":
        lines.append("- 公众号版更适合写成方法论和判断框架，允许信息密度更高。")
    elif platform == "zhihu":
        lines.append("- 知乎版优先强调选型依据、评测维度和适用对象。")
    elif platform == "toutiao":
        lines.append("- 头条版开头要更快给结论，把结果承诺放到前两段。")
    return lines


def build_viral_analysis(rows: list[dict[str, Any]], *, current_title: str, benchmark_path: Path) -> str:
    signals = dominant_signal_names(rows)
    gap_lines = current_title_gap_lines(rows, current_title)

    lines = [
        "# 爆款分析",
        "",
        f"- 日期：`{current_date_label()}`",
        f"- 样本基础：见 [`benchmark-monitor.md`]({benchmark_path.as_posix()})",
        "- 说明：这里的“爆款”定义为同主题下可重复检索、结构可复用、标题信号稳定的强样本。",
        "",
        "## 一、这批样本为什么能打",
        "",
        "### 1. 它们卖的不是功能，而是结果",
        "",
        "- 高表现样本反复强调的是少返工、能发布、能接住工作流，而不是单点功能介绍。",
        "- 这说明读者点击的不是“工具名”，而是“今天能不能少走回头路”。",
        "",
        "### 2. 它们把主角从工具换成了工作流",
        "",
        f"- 本轮最稳定的信号是：`{' / '.join(signals or ['workflow', 'result'])}`。",
        "- 标题里出现工作流、发布、分发、系统这些词时，更容易把内容抬升成团队决策题。",
        "",
        "### 3. 它们的冲突足够具体",
        "",
        "- 强样本不是讲抽象趋势，而是讲排版太慢、平台适配麻烦、生成完还是发不出去这些真实损失。",
        "",
        "## 二、平台差异",
        "",
        "### 公众号",
        *platform_strategy_lines(rows, "wechat"),
        "",
        "### 知乎",
        *platform_strategy_lines(rows, "zhihu"),
        "",
        "### 今日头条",
        *platform_strategy_lines(rows, "toutiao"),
        "",
        "## 三、当前稿和强样本的差距",
        "",
        f"- 当前标题：`{current_title}`",
        *gap_lines,
        "- 当前稿如果继续堆品牌动态，会稀释判断框架，后续需要把品牌信息压缩成证据，不要让它抢主线。",
        "",
        "## 四、从样本里提炼出的可复用动作",
        "",
        "1. 标题层：优先写错误成本、结果承诺和发布链路，不要只写功能介绍。",
        "2. 开头层：前三段必须出现一个真实工作场景、一个明确损失、一个判断结论。",
        "3. 结构层：保持“判断框架”作为主线，避免写成分散的工具资讯。",
        "4. 平台层：公众号偏方法论，知乎偏指南/评测，头条偏结果和效率承诺。",
        "5. 视觉层：正文至少拆成对比、链路、清单三种信息结构，不能再用单一图版。",
        "",
        "## 一句话结论",
        "",
        "- 这批强样本给出的明确信号是：读者现在更愿意点开“少返工、别买错、能接住发布”的内容，而不是泛泛工具盘点。",
    ]

    return "\n".join(lines).strip() + "\n"


def title_number_hint(current_title: str) -> str:
    match = re.search(r"(\d+)", current_title)
    return match.group(1) if match else "4"


def build_title_variants(current_title: str, rows: list[dict[str, Any]]) -> list[str]:
    count_hint = title_number_hint(current_title)
    counts = signal_counts(rows)
    prefix = "内容团队选工具"
    if counts.get("mistake", 0) > 0:
        return [
            f"{prefix}，先别看模板，先过这{count_hint}个发布前判断",
            f"真正拖慢内容团队的，不是第一稿，而是这{count_hint}个发布前问题",
            f"别再买会做图却发不出去的工具了：内容团队先看这{count_hint}个判断",
        ]
    return [
        f"{prefix}，先看这{count_hint}个工作流判断",
        f"想少返工，先过这{count_hint}个发布前检查",
        f"会生成不等于会发布：内容团队先看这{count_hint}个判断",
    ]


def build_rewrite_plan(rows: list[dict[str, Any]], *, current_title: str) -> str:
    title_variants = build_title_variants(current_title, rows)
    count_hint = title_number_hint(current_title)
    lines = [
        "# 仿写方案",
        "",
        f"- 日期：`{current_date_label()}`",
        f"- 当前文章：`{current_title}`",
        "- 目标：不是抄某一篇，而是把监控样本里的标题机制、开头机制、结构机制和视觉机制落到当前稿上。",
        "",
        "## 一、先定边界",
        "",
        "### 不做的事",
        "",
        "- 不直接复用任何对标标题原句。",
        "- 不照搬别人品牌排序和案例顺序。",
        "- 不把榜单写法硬套到判断框架稿子上。",
        "",
        "### 要学的东西",
        "",
        "- `误区式切口`",
        "- `工作流式结构`",
        "- `决策型表达`",
        "- `多版式配图`",
        "",
        "## 二、这篇稿子最适合采用的仿写组合",
        "",
        "### 主打法：误区式判断",
        "",
        "- 先指出大家最容易看错什么。",
        "- 再指出真正该看的，是发布链路和返工成本。",
        f"- 最后把内容收束到“{count_hint}个发布前判断”这种可执行清单里。",
        "",
        "### 辅打法：工作流式拆解",
        "",
        "- 让研究、生成、协作、发布成为一条线，而不是散开的产品功能点。",
        "- 后续三平台改写都围绕这条主线做轻量适配，不推翻整稿。",
        "",
        "## 三、标题改写动作",
        "",
        "### 当前标题",
        "",
        f"`{current_title}`",
        "",
        "### 可直接测试的三版标题",
        "",
        f"1. `{title_variants[0]}`",
        f"2. `{title_variants[1]}`",
        f"3. `{title_variants[2]}`",
        "",
        "## 四、开头改写动作",
        "",
        "### 改写原则",
        "",
        "1. 第一段先给一个团队日常场景。",
        "2. 第二段立刻给出损失，不要先讲大道理。",
        "3. 第三段再抛出判断：先别看会不会生成，先看能不能把最后一公里接住。",
        "",
        "### 推荐开头节奏",
        "",
        "- 第一段：上午做完，下午还在改尺寸、补封面、填说明，晚上还没发出去。",
        "- 第二段：这种损失不是多花半小时，而是把前面省下来的时间又全部吐回去。",
        "- 第三段：所以今天选内容工具，先看它能不能把发布链路接住。",
        "",
        "## 五、正文结构动作",
        "",
        "### 保留",
        "",
        f"- `{count_hint}个发布前判断` 这条主线。",
        "- 工具或平台对比，但只保留服务于判断的部分。",
        "",
        "### 压缩",
        "",
        "- 与当前判断无关的品牌新闻背景。",
        "- 只增加信息量、不增加决策价值的枝节描述。",
        "",
        "### 放大",
        "",
        "- 每个判断和真实工作动作的对应关系。",
        "- 为什么它会影响返工、协作和正式发布。",
        "",
        "## 六、插图和配图动作",
        "",
        "### 三图分工",
        "",
        "1. `对比图`",
        "   - 说明“第一稿生成快”不等于“团队整体效率高”。",
        "   - 视觉形式：双栏对照。",
        "2. `链路图`",
        "   - 说明研究、生成、协作、发布如何接成一条线。",
        "   - 视觉形式：流程链 / 工具栈地图。",
        "3. `清单图`",
        f"   - 承接“{count_hint}个发布前判断”。",
        "   - 视觉形式：白板式检查清单。",
        "",
        "### 本次执行原则",
        "",
        "- 同一篇稿内不重复同一构图逻辑。",
        "- 后续每篇稿至少保留两种以上信息结构，不再让所有配图都长成同一种卡片。",
        "",
        "## 七、三平台落地动作",
        "",
        "### 公众号",
        "- 用方法论版本，信息密度可以更高。",
        "",
        "### 知乎",
        "- 更适合强调团队为什么容易买错，以及判断框架的适用边界。",
        "",
        "### 今日头条",
        "- 标题更直接，开头更快给结论，把“少返工、能直接发”放到更靠前的位置。",
        "",
        "## 八、这一轮仿写的验收标准",
        "",
        "1. 标题里出现明确的错误成本或决策动作。",
        "2. 开头前三段能让内容团队读者立刻代入。",
        "3. 正文主线始终围绕判断框架，不被品牌信息冲散。",
        "4. 三张图的功能各不相同，不再单一版式。",
        "5. 结尾带出一个明确互动问题，而不是平收。",
        "",
        "## 一句话结论",
        "",
        "- 这篇稿最该学的不是“别人列了多少工具”，而是怎么把工具选型写成团队决策题。",
    ]
    return "\n".join(lines).strip() + "\n"


CHECKLIST_COUNT_HINT_PATTERN = re.compile(r"(\d{1,2})\s*(个|步|条|种|招|项|类|版|问|点)")
VOLUME_COUNT_HINT_PATTERN = re.compile(r"(\d{1,2})\s*(篇|张)")


def explicit_title_count(current_title: str) -> str | None:
    match = CHECKLIST_COUNT_HINT_PATTERN.search(current_title)
    if match:
        return match.group(1)
    match = VOLUME_COUNT_HINT_PATTERN.search(current_title)
    return match.group(1) if match else None


def title_number_hint(current_title: str) -> str:
    return explicit_title_count(current_title) or "4"


def title_subject(current_title: str) -> str:
    first = re.split(r"[：:，,。！？!?]", current_title, maxsplit=1)[0].strip()
    return first or current_title.strip()


def infer_rewrite_theme(current_title: str, rows: list[dict[str, Any]]) -> str:
    lowered = current_title.lower()
    counts = signal_counts(rows)
    if "google" in lowered or "i/o" in lowered or "替你做事" in current_title:
        return "trend"
    if any(keyword in current_title for keyword in ("复盘", "避坑", "踩坑")):
        return "postmortem"
    if any(keyword in current_title for keyword in ("工作流", "流程", "夜班", "自动化")):
        return "workflow"
    if any(keyword in current_title for keyword in ("工具", "怎么选", "判断", "能不能改")):
        return "tool_selection"
    if counts.get("workflow", 0) > 0:
        return "workflow"
    if counts.get("mistake", 0) > 0:
        return "postmortem"
    return "generic"


def rewrite_focus_phrase(theme: str, current_title: str) -> str:
    count_hint = title_number_hint(current_title)
    has_explicit_count = explicit_title_count(current_title) is not None
    if theme == "tool_selection":
        return f"{count_hint}个发布前判断" if has_explicit_count else "发布前判断"
    if theme == "postmortem":
        return f"{count_hint}个避坑方法" if has_explicit_count else "几个避坑方法"
    if theme == "workflow":
        return "AI 能不能自己跑完流程"
    if theme == "trend":
        return "AI 从回答走向执行的关键判断"
    return "核心判断"


def build_title_variants(current_title: str, rows: list[dict[str, Any]]) -> list[str]:
    count_hint = title_number_hint(current_title)
    subject = title_subject(current_title)
    theme = infer_rewrite_theme(current_title, rows)
    has_explicit_count = explicit_title_count(current_title) is not None

    if theme == "workflow":
        return [
            f"{subject}：真正拉开差距的，不是更会答，而是会不会自己跑流程",
            "AI 真正开始接活，不是回答更长了，而是能不能把流程接住",
            "想少返工，重点不是多会写，而是让 AI 把最后一公里跑完",
        ]
    if theme == "postmortem":
        list_phrase = f"这{count_hint}个坑" if has_explicit_count else "这些坑"
        return [
            f"复盘 {count_hint} 篇 AI 内容后，我最后只留这{count_hint}个避坑方法"
            if has_explicit_count
            else f"{subject}：我最后只留下几个真正有用的避坑方法",
            f"AI 内容越写越像垃圾，问题常出在{list_phrase}",
            f"做完一轮 AI 内容复盘后，我更建议先避开{list_phrase}",
        ]
    if theme == "trend":
        return [
            f"{subject} 之后，AI 开始从回答问题走向替你做事",
            "AI 真正的变化，不是更会答，而是开始接住动作",
            f"看完 {subject}，我更关心 AI 什么时候真能替你做事",
        ]
    if theme == "tool_selection":
        if signal_counts(rows).get("mistake", 0) > 0:
            return [
                f"{subject}，先别看模板，先过这{count_hint}个发布前判断",
                f"真正拖慢团队的，不是第一稿，而是这{count_hint}个发布前问题",
                f"会做图不等于能发出去：先看这{count_hint}个判断",
            ]
        return [
            f"{subject}，先看这{count_hint}个工作流判断",
            f"想少返工，先过这{count_hint}个发布前检查",
            f"会生成不等于会发布：先看这{count_hint}个判断",
        ]
    return [
        f"{subject}：先看结果，再看功能",
        f"{subject}，关键不是信息更多，而是动作能不能接住",
        "真正拉开差距的，不是讲了多少，而是有没有把判断写清楚",
    ]


def build_rewrite_context(current_title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    theme = infer_rewrite_theme(current_title, rows)
    focus_phrase = rewrite_focus_phrase(theme, current_title)

    if theme == "workflow":
        return {
            "primaryHeading": "结果式流程判断",
            "primaryLines": [
                "- 先指出大家最容易把“更会答”误当成“能接住工作流”。",
                "- 再把重点拉回流程能不能自己跑完、返工能不能真正减少。",
                f"- 最后把内容收束到“{focus_phrase}”这个判断上。",
            ],
            "secondaryHeading": "工作流式拆解",
            "secondaryLines": [
                "- 把回答、执行、回传结果写成一条线，而不是停在聊天框里的单次问答。",
                "- 三平台改写都围绕“会答”和“会做”的差别展开，不重新发明主题。",
            ],
            "openingRule3": "3. 第三段再抛出判断：先别看回答像不像人，先看它能不能把流程跑完。",
            "openingLines": [
                "- 第一段：白天有人盯提示词，晚上还得有人守着流程交接，一断就得手工补。",
                "- 第二段：真正拖慢团队的，不是第一轮回答，而是关键动作一到交接处就掉回人工。",
                "- 第三段：所以这篇稿子的重点，不是 AI 更会答了，而是它能不能自己把流程跑完。",
            ],
            "retainLines": [
                f"- 保留“{focus_phrase}”这条主线。",
                "- 会答和会做的对比，只保留能支撑判断的部分。",
            ],
            "compressLines": [
                "- 与流程判断无关的工具名堆叠和泛功能介绍。",
                "- 只增加热闹感、不增加执行判断的信息。",
            ],
            "amplifyLines": [
                "- 哪些动作真正从“帮你答”变成“替你做”。",
                "- 为什么这会影响交接、夜班和返工成本。",
            ],
            "zhihuLine": "- 更适合把“会答”和“会做”的边界、反例和适用条件拆清楚。",
            "toutiaoLine": "- 标题更直给，开头更快抛出“AI 是否真能自己跑流程”的结论。",
            "closingLine": "- 这篇稿最该学的，不是“AI 又会了一个新功能”，而是怎么把“会答”写成“会做”的判断题。",
        }
    if theme == "postmortem":
        return {
            "primaryHeading": "复盘式避坑",
            "primaryLines": [
                "- 先把最容易重复踩的坑摆出来，不要先讲宏大道理。",
                "- 再说明每个坑为什么会直接拉低阅读、互动或发布结果。",
                f"- 最后把内容收束到“{focus_phrase}”这种筛选结论里。",
            ],
            "secondaryHeading": "结果式复盘",
            "secondaryLines": [
                "- 复盘不是回忆过程，而是筛出哪些动作以后要彻底删掉。",
                "- 三平台改写都围绕“为什么白写”和“怎么少踩坑”展开。",
            ],
            "openingRule3": "3. 第三段再抛出判断：先别急着讲方法，先把踩坑成本摆出来。",
            "openingLines": [
                "- 第一段：写的时候觉得每段都很完整，发出去才发现读者根本不买单。",
                "- 第二段：真正浪费的不是多写了几百字，而是把错误写法重复了十几次。",
                f"- 第三段：所以这篇稿的重点，不是分享心得，而是先筛掉最该避开的{focus_phrase}。",
            ],
            "retainLines": [
                f"- 保留“{focus_phrase}”这条筛选主线。",
                "- 每个坑和结果之间的对应关系，要写得足够直接。",
            ],
            "compressLines": [
                "- 与坑点判断无关的宏观趋势和空泛总结。",
                "- 只有态度、没有具体后果的泛复盘表述。",
            ],
            "amplifyLines": [
                "- 每个坑是怎么发生的。",
                "- 改掉以后最直接会影响哪一个结果。",
            ],
            "zhihuLine": "- 更适合把每个坑的成因、边界和反例写清楚。",
            "toutiaoLine": "- 标题更直接，把踩坑成本和筛选结果前置。",
            "closingLine": "- 这篇稿最该学的，不是把经验写成大道理，而是把复盘写成可避开的具体坑。",
        }
    if theme == "trend":
        return {
            "primaryHeading": "趋势落地判断",
            "primaryLines": [
                "- 先指出大家最容易把发布会信息看成一串新功能新闻。",
                "- 再把重点拉回“从回答走向替你做事”这个能力迁移。",
                f"- 最后把内容收束到“{focus_phrase}”这种可判断的结论上。",
            ],
            "secondaryHeading": "能力迁移式拆解",
            "secondaryLines": [
                "- 把演示背后的能力迁移拆开：从回答、到调用、再到完成动作。",
                "- 三平台改写都围绕“AI 真正开始替人做什么”展开。",
            ],
            "openingRule3": "3. 第三段再抛出判断：先别停在发布会功能表，先看 AI 有没有越过聊天框去接动作。",
            "openingLines": [
                "- 第一段：台上看起来像是多了几个新功能，台下真正该问的是它到底接走了哪一步动作。",
                "- 第二段：如果只是回答更快，工作方式不会变；只有开始替人做事，流程才会被改写。",
                "- 第三段：所以这篇稿子的重点，不是功能更新，而是 AI 已经从回答走向执行到哪一步。",
            ],
            "retainLines": [
                "- 保留“从回答问题走向替你做事”这条主线。",
                "- 功能变化只保留能支撑趋势判断的那部分。",
            ],
            "compressLines": [
                "- 零散功能清单和会场枝节。",
                "- 只会拉长篇幅、不会增强判断的信息堆砌。",
            ],
            "amplifyLines": [
                "- 哪些信号说明 AI 在接手动作而不是补充说明。",
                "- 这种变化为什么会先影响搜索、助手和工作台。",
            ],
            "zhihuLine": "- 更适合把趋势判断拆成依据、反例和落地边界。",
            "toutiaoLine": "- 标题更聚焦结论，把“替你做事”放到更靠前的位置。",
            "closingLine": "- 这篇稿最该学的，不是逐条复述发布会功能，而是把趋势新闻写成能力迁移的判断题。",
        }
    if theme == "tool_selection":
        return {
            "primaryHeading": "误区式判断",
            "primaryLines": [
                "- 先指出大家最容易看错什么。",
                "- 再指出真正该看的，是发布链路和返工成本。",
                f"- 最后把内容收束到“{focus_phrase}”这种可执行清单里。",
            ],
            "secondaryHeading": "工作流式拆解",
            "secondaryLines": [
                "- 让研究、生成、协作、发布成为一条线，而不是散开的产品功能点。",
                "- 后续三平台改写都围绕这条主线做轻量适配，不推翻整稿。",
            ],
            "openingRule3": "3. 第三段再抛出判断：先别看会不会生成，先看能不能把最后一公里接住。",
            "openingLines": [
                "- 第一段：上午做完，下午还在改尺寸、补封面、填说明，晚上还没发出去。",
                "- 第二段：这种损失不是多花半小时，而是把前面省下来的时间又全部吐回去。",
                "- 第三段：所以今天选工具，先看它能不能把发布链路接住。",
            ],
            "retainLines": [
                f"- 保留“{focus_phrase}”这条主线。",
                "- 工具或平台对比，但只保留服务于判断的部分。",
            ],
            "compressLines": [
                "- 与当前判断无关的品牌新闻背景。",
                "- 只增加信息量、不增加决策价值的枝节描述。",
            ],
            "amplifyLines": [
                "- 每个判断和真实工作动作的对应关系。",
                "- 为什么它会影响返工、协作和正式发布。",
            ],
            "zhihuLine": "- 更适合强调团队为什么容易买错，以及判断框架的适用边界。",
            "toutiaoLine": "- 标题更直接，开头更快给结论，把“少返工、能直接发”放到更靠前的位置。",
            "closingLine": "- 这篇稿最该学的，不是“别人列了多少工具”，而是怎么把工具选型写成团队决策题。",
        }
    return {
        "primaryHeading": "判断式重写",
        "primaryLines": [
            "- 先把最值得读者停下来的判断点拎出来。",
            "- 再把真正的结果差异写清楚，不要堆功能和信息。",
            f"- 最后把内容收束到“{focus_phrase}”这条主线上。",
        ],
        "secondaryHeading": "结构式拆解",
        "secondaryLines": [
            "- 把核心判断、证据和动作安排成一条线。",
            "- 三平台改写都围绕这个判断做轻量适配。",
        ],
        "openingRule3": "3. 第三段再抛出判断：先别急着展开，先把这篇稿最关键的结论立住。",
        "openingLines": [
            "- 第一段：先给出一个真实场景，让读者知道这不是空话。",
            "- 第二段：再把不改会付出的代价说透。",
            "- 第三段：最后抛出这篇稿真正要回答的判断题。",
        ],
        "retainLines": [
            f"- 保留“{focus_phrase}”这条主线。",
            "- 所有例子都服务于主判断，不另起新枝。",
        ],
        "compressLines": [
            "- 与主判断无关的背景补充。",
            "- 会拉长篇幅、不会增强决策价值的泛表述。",
        ],
        "amplifyLines": [
            "- 哪个证据最能支撑当前判断。",
            "- 为什么它会改变读者的具体动作。",
        ],
        "zhihuLine": "- 更适合把判断依据和适用边界写完整。",
        "toutiaoLine": "- 标题更聚焦结果，开头更快给结论。",
        "closingLine": "- 这篇稿最该学的，不是换一层说法，而是把判断真正写实。",
    }


def build_rewrite_plan(rows: list[dict[str, Any]], *, current_title: str) -> str:
    title_variants = build_title_variants(current_title, rows)
    theme = infer_rewrite_theme(current_title, rows)
    focus_phrase = rewrite_focus_phrase(theme, current_title)
    context = build_rewrite_context(current_title, rows)
    lines = [
        "# 仿写方案",
        "",
        f"- 日期：`{current_date_label()}`",
        f"- 当前文章：`{current_title}`",
        "- 目标：不是抄某一篇，而是把监控样本里的标题机制、开头机制、结构机制和视觉机制落到当前稿上。",
        "",
        "## 一、先定边界",
        "",
        "### 不做的事",
        "",
        "- 不直接复用任何对标标题原句。",
        "- 不照搬别人品牌排序和案例顺序。",
        "- 不把榜单写法硬套到判断框架稿子上。",
        "",
        "### 要学的东西",
        "",
        "- `误区式切口`",
        "- `工作流式结构`",
        "- `决策型表达`",
        "- `多版式配图`",
        "",
        "## 二、这篇稿子最适合采用的仿写组合",
        "",
        f"### 主打法：{context['primaryHeading']}",
        "",
        *context["primaryLines"],
        "",
        f"### 辅打法：{context['secondaryHeading']}",
        "",
        *context["secondaryLines"],
        "",
        "## 三、标题改写动作",
        "",
        "### 当前标题",
        "",
        f"`{current_title}`",
        "",
        "### 可直接测试的三版标题",
        "",
        f"1. `{title_variants[0]}`",
        f"2. `{title_variants[1]}`",
        f"3. `{title_variants[2]}`",
        "",
        "## 四、开头改写动作",
        "",
        "### 改写原则",
        "",
        "1. 第一段先给一个真实工作场景。",
        "2. 第二段立刻给出损失，不要先讲大道理。",
        context["openingRule3"],
        "",
        "### 推荐开头节奏",
        "",
        *context["openingLines"],
        "",
        "## 五、正文结构动作",
        "",
        "### 保留",
        "",
        *context["retainLines"],
        "",
        "### 压缩",
        "",
        *context["compressLines"],
        "",
        "### 放大",
        "",
        *context["amplifyLines"],
        "",
        "## 六、插图和配图动作",
        "",
        "### 三图分工",
        "",
        "1. `对比图`",
        "   - 说明核心能力强，不等于整体结果就已经更好。",
        "   - 视觉形式：双栏对照。",
        "2. `链路图`",
        "   - 说明关键动作如何从单点能力接成完整链路。",
        "   - 视觉形式：流程链 / 能力迁移地图。",
        "3. `清单图`",
        f"   - 承接“{focus_phrase}”。",
        "   - 视觉形式：白板式检查清单。",
        "",
        "### 本次执行原则",
        "",
        "- 同一篇稿内不重复同一构图逻辑。",
        "- 后续每篇稿至少保留两种以上信息结构，不再让所有配图都长成同一种卡片。",
        "",
        "## 七、三平台落地动作",
        "",
        "### 公众号",
        "- 用方法论版本，信息密度可以更高。",
        "",
        "### 知乎",
        context["zhihuLine"],
        "",
        "### 今日头条",
        context["toutiaoLine"],
        "",
        "## 八、这一轮仿写的验收标准",
        "",
        "1. 标题里出现明确的错误成本、能力迁移或决策动作。",
        "2. 开头前三段能让目标读者立刻进入具体场景。",
        "3. 正文主线始终围绕当前判断，不被枝节信息冲散。",
        "4. 三张图的功能各不相同，不再单一版式。",
        "5. 结尾带出一个明确互动问题，而不是平收。",
        "",
        "## 一句话结论",
        "",
        context["closingLine"],
    ]
    return "\n".join(lines).strip() + "\n"


def signal_artifact_paths(generated_dir: Path) -> dict[str, Path]:
    return {
        key: generated_dir / filename
        for key, filename in SIGNAL_ARTIFACT_NAMES.items()
    }


def read_json_file(path: Path) -> Any:
    return read_web_scraper_json(path)


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_benchmark_registry(path: Path) -> dict[str, Any]:
    data = read_json_file(path)
    return data if isinstance(data, dict) else {}


def normalize_registry_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def candidate_registry_keys(payload: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for raw in (
        payload.get("benchmarkRegistryKey"),
        payload.get("domain"),
        payload.get("topic"),
    ):
        key = normalize_registry_key(raw)
        if not key or key in keys:
            continue
        keys.append(key)
    return keys


def normalize_registry_request(request: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    normalized = dict(request)
    if "action" not in normalized:
        normalized["action"] = "search_content"
    if "provider" not in normalized:
        normalized["provider"] = "import_json"

    input_path = str(normalized.get("inputPath") or "").strip()
    if input_path:
        candidate = Path(input_path)
        if not candidate.is_absolute():
            candidate = (registry_path.parent / candidate).resolve()
        normalized["inputPath"] = str(candidate)
    return normalized


def resolve_registry_request(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    registry_path = Path(
        str(payload.get("benchmarkRegistryPath") or DEFAULT_BENCHMARK_REGISTRY_PATH).strip()
    )
    if not registry_path.exists():
        return None, None

    registry = load_benchmark_registry(registry_path)
    sources = registry.get("sources", {})
    if not isinstance(sources, dict):
        return None, None

    alias_to_key: dict[str, str] = {}
    for key, raw_request in sources.items():
        if not isinstance(raw_request, dict):
            continue
        alias_to_key[normalize_registry_key(key)] = key
        for alias in raw_request.get("aliases", []) or []:
            normalized_alias = normalize_registry_key(alias)
            if normalized_alias:
                alias_to_key[normalized_alias] = key

    for candidate in candidate_registry_keys(payload):
        resolved_key = alias_to_key.get(candidate)
        if not resolved_key:
            continue
        raw_request = sources.get(resolved_key)
        if isinstance(raw_request, dict):
            return resolved_key, normalize_registry_request(raw_request, registry_path)
    return None, None


def benchmark_request_path(generated_dir: Path) -> Path:
    return generated_dir / BENCHMARK_REQUEST_NAME


def build_benchmark_request_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    explicit_request = payload.get("benchmarkRequest")
    if isinstance(explicit_request, dict):
        return explicit_request, {
            "sourceKind": "payload",
            "registryKey": None,
            "requestResolvedFrom": "payload",
        }

    request_path = str(payload.get("benchmarkRequestPath") or "").strip()
    if request_path:
        candidate = Path(request_path)
        if candidate.exists():
            data = read_json_file(candidate)
            if isinstance(data, dict):
                return data, {
                    "sourceKind": "payload",
                    "registryKey": None,
                    "requestResolvedFrom": "payload",
                }

    source_path = str(payload.get("benchmarkSourcePath") or "").strip()
    if not source_path:
        registry_key, request = resolve_registry_request(payload)
        if isinstance(request, dict):
            return request, {
                "sourceKind": "registry",
                "registryKey": registry_key,
                "requestResolvedFrom": "registry",
            }
        return None, {
            "sourceKind": None,
            "registryKey": None,
            "requestResolvedFrom": None,
        }

    request: dict[str, Any] = {
        "action": str(payload.get("benchmarkAction") or "search_content").strip() or "search_content",
        "provider": str(payload.get("benchmarkProvider") or "import_json").strip() or "import_json",
        "platform": str(payload.get("benchmarkPlatform") or payload.get("platform") or "unknown").strip() or "unknown",
        "inputPath": source_path,
        "recordType": str(payload.get("benchmarkRecordType") or "article").strip() or "article",
    }
    if payload.get("benchmarkLimit") is not None:
        request["limit"] = int(payload.get("benchmarkLimit") or 0)
    if str(payload.get("benchmarkQuery") or "").strip():
        request["query"] = str(payload.get("benchmarkQuery")).strip()
    return request, {
        "sourceKind": "payload",
        "registryKey": None,
        "requestResolvedFrom": "payload",
    }


def resolve_benchmark_request(
    generated_dir: Path,
    payload: dict[str, Any] | None,
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any]]:
    sidecar_path = benchmark_request_path(generated_dir)
    if sidecar_path.exists():
        data = read_json_file(sidecar_path)
        if isinstance(data, dict):
            return sidecar_path.resolve(), data, {
                "sourceKind": "request_sidecar",
                "registryKey": None,
                "requestResolvedFrom": "generated_sidecar",
            }

    if isinstance(payload, dict):
        request, trace = build_benchmark_request_from_payload(payload)
        if isinstance(request, dict):
            generated_dir.mkdir(parents=True, exist_ok=True)
            write_json_file(sidecar_path, request)
            return sidecar_path.resolve(), request, trace

    return None, None, {
        "sourceKind": None,
        "registryKey": None,
        "requestResolvedFrom": None,
    }


def collect_records_from_request(
    *,
    generated_dir: Path,
    request: dict[str, Any],
    config_path: Path = DEFAULT_WEB_SCRAPER_CONFIG_PATH,
) -> Path | None:
    config = read_json_file(config_path)
    response = run_web_scraper_request(request, config)
    if response.get("status") != "ok":
        return None

    rows = response.get("records")
    if not isinstance(rows, list):
        record = response.get("record")
        if isinstance(record, dict):
            rows = [record]
        else:
            rows = []
    if not rows:
        return None

    target_path = generated_dir / "benchmark-records.jsonl"
    write_jsonl(target_path, rows)
    return target_path.resolve()


def resolve_records_path(payload: dict[str, Any] | None, generated_dir: Path) -> tuple[Path | None, str | None]:
    candidates: list[tuple[Path, str]] = []
    if isinstance(payload, dict):
        for key in ("benchmarkRecordsPath", "benchmark_records_path"):
            raw = str(payload.get(key) or "").strip()
            if raw:
                candidates.append((Path(raw), "payload"))
    candidates.append((generated_dir / "benchmark-records.jsonl", "generated_records"))

    for candidate, source in candidates:
        if candidate.exists():
            return candidate.resolve(), source
    return None, None


def resolve_existing_request_path(generated_dir: Path) -> Path | None:
    sidecar_path = benchmark_request_path(generated_dir)
    if sidecar_path.exists():
        return sidecar_path.resolve()
    return None


def ensure_signal_artifacts(
    *,
    generated_dir: Path,
    slug: str,
    current_title: str,
    payload: dict[str, Any] | None = None,
    records_path: Path | None = None,
    min_group_samples: int = 2,
    top_limit: int = 5,
) -> dict[str, Any]:
    artifact_paths = signal_artifact_paths(generated_dir)
    records_resolved_from: str | None = None
    if records_path and records_path.exists():
        resolved_records = records_path.resolve()
        records_resolved_from = "explicit_records"
    else:
        resolved_records, records_resolved_from = resolve_records_path(payload, generated_dir)

    request_path, benchmark_request = (resolve_existing_request_path(generated_dir), None)
    trace: dict[str, Any] = {
        "sourceKind": None,
        "registryKey": None,
        "requestResolvedFrom": "generated_sidecar" if request_path else None,
        "recordsResolvedFrom": records_resolved_from,
    }
    if not resolved_records:
        request_path, benchmark_request, request_trace = resolve_benchmark_request(generated_dir, payload)
        trace.update(request_trace)
        if benchmark_request:
            resolved_records = collect_records_from_request(
                generated_dir=generated_dir,
                request=benchmark_request,
            )
            if resolved_records:
                trace["recordsResolvedFrom"] = "request_fetch"
    elif records_resolved_from in {"generated_records", "explicit_records", "payload"}:
        trace["sourceKind"] = "records_reused" if records_resolved_from in {"generated_records", "explicit_records"} else "payload"
    has_all_artifacts = all(path.exists() for path in artifact_paths.values())

    if resolved_records:
        result = run_content_signal_pipeline(
            resolved_records,
            generated_dir,
            slug=slug,
            current_title=current_title,
            min_group_samples=min_group_samples,
            top_limit=top_limit,
        )
        return {
            "status": "completed",
            "recordsPath": str(resolved_records),
            "requestPath": str(request_path) if request_path else None,
            **trace,
            **result,
        }

    if has_all_artifacts:
        return {
            "status": "reused_existing",
            "recordsPath": None,
            "requestPath": str(request_path) if request_path else None,
            **trace,
            **{key: str(path) for key, path in artifact_paths.items()},
        }

    return {
        "status": "pending_source",
        "recordsPath": None,
        "requestPath": str(request_path) if request_path else None,
        **trace,
        **{key: str(path) for key, path in artifact_paths.items()},
    }


def run_content_signal_pipeline(
    records_path: Path,
    output_dir: Path,
    *,
    slug: str,
    current_title: str,
    min_group_samples: int = 2,
    top_limit: int = 5,
) -> dict[str, Any]:
    normalized_rows = read_jsonl(records_path)
    if not normalized_rows:
        raise ValueError("No normalized rows found.")

    output_dir.mkdir(parents=True, exist_ok=True)

    benchmark_records_path = output_dir / "benchmark-records.jsonl"
    benchmark_path = output_dir / "benchmark-monitor.md"
    peer_csv_path = output_dir / "peer-content-samples.csv"
    peer_report_path = output_dir / "peer-content-traffic-report.md"
    viral_analysis_path = output_dir / "viral-analysis.md"
    rewrite_plan_path = output_dir / "rewrite-plan.md"

    write_jsonl(benchmark_records_path, normalized_rows)

    peer_samples = build_peer_samples(normalized_rows)
    write_csv_rows(peer_csv_path, peer_samples)

    peer_rows = read_peer_rows(peer_csv_path)
    add_platform_relative_scores(peer_rows)

    benchmark_content = build_benchmark_markdown(
        normalized_rows,
        peer_rows,
        slug=slug,
        current_title=current_title,
        top_limit=max(1, top_limit),
    )
    peer_report = build_peer_report(
        peer_rows,
        source_path=peer_csv_path,
        min_group_samples=max(1, min_group_samples),
        top_limit=max(1, top_limit),
    )
    viral_analysis = build_viral_analysis(peer_rows, current_title=current_title, benchmark_path=benchmark_path)
    rewrite_plan = build_rewrite_plan(peer_rows, current_title=current_title)

    write_text(benchmark_path, benchmark_content)
    write_text(peer_report_path, peer_report)
    write_text(viral_analysis_path, viral_analysis)
    write_text(rewrite_plan_path, rewrite_plan)

    return {
        "slug": slug,
        "recordCount": len(normalized_rows),
        "benchmarkSummaryPath": str(benchmark_path),
        "peerSamplesPath": str(peer_csv_path),
        "trafficReportPath": str(peer_report_path),
        "viralAnalysisPath": str(viral_analysis_path),
        "rewritePlanPath": str(rewrite_plan_path),
    }


def main() -> int:
    args = parse_args()
    result = run_content_signal_pipeline(
        args.records_path,
        args.output_dir,
        slug=args.slug,
        current_title=args.current_title,
        min_group_samples=args.min_group_samples,
        top_limit=args.top_limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
