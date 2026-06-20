from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.check_generated_article_quality import infer_topic_from_payload, read_json
    from scripts.image_strategy import build_image_plan
    from scripts.pipeline_state import empty_platform_state, ensure_platform_entries, load_pipeline_state, now_iso, save_pipeline_state
    from scripts.run_content_signal_pipeline import ensure_signal_artifacts
    from scripts.run_three_platform_pipeline import run_preflight
except ModuleNotFoundError:
    from check_generated_article_quality import infer_topic_from_payload, read_json
    from image_strategy import build_image_plan
    from pipeline_state import empty_platform_state, ensure_platform_entries, load_pipeline_state, now_iso, save_pipeline_state
    from run_content_signal_pipeline import ensure_signal_artifacts
    from run_three_platform_pipeline import run_preflight


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = ROOT / "config"
DEFAULT_HISTORY_PATH = ROOT / ".tmp" / "v3" / "image-history.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the v3 prepublish content control chain.")
    parser.add_argument("payload_path", type=Path, help="Path to the base payload JSON file.")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR, help="Config directory.")
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY_PATH, help="Image history path.")
    parser.add_argument("--min-score", type=int, default=80, help="Minimum quality score.")
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


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config(config_dir: Path, name: str) -> dict[str, Any]:
    return read_json_file(config_dir / name, {})


def reset_stale_platform_statuses(state: dict[str, Any]) -> dict[str, Any]:
    for platform in ("toutiao", "zhihu", "wechat"):
        entry = state.get("platforms", {}).get(platform, {})
        if (
            int(entry.get("attemptCount", 0) or 0) == 0
            and not entry.get("publishedAt")
            and not entry.get("url")
            and not entry.get("titleUsed")
            and str(entry.get("status") or "") in {"publish_failed", "awaiting_verification", "submitted", "publishing"}
        ):
            entry["status"] = "ready"
            entry["verificationSource"] = "v3_reset_no_publish_evidence"
            entry["error"] = None
    return state


def evaluate_asset_gate(state: dict[str, Any]) -> dict[str, Any]:
    assets = state.get("assets", {}) or {}
    missing_files = list(assets.get("missingFiles", []) or [])
    cover_exists = bool(assets.get("coverExists"))
    body_image_count = int(assets.get("bodyImageCount", 0) or 0)
    if not cover_exists or missing_files or body_image_count <= 0:
        return {
            "status": "blocked",
            "reason": "missing_required_assets",
            "missingFiles": missing_files,
            "coverExists": cover_exists,
            "bodyImageCount": body_image_count,
        }
    return {
        "status": "passed",
        "reason": "assets_ready",
        "missingFiles": [],
        "coverExists": cover_exists,
        "bodyImageCount": body_image_count,
    }


def resolve_stale_benchmark_block(signal_pipeline: dict[str, Any]) -> dict[str, Any] | None:
    if str(signal_pipeline.get("freshnessStatus") or "") != "stale":
        return None
    return {
        "status": "blocked_by_stale_benchmark_inputs",
        "reason": "benchmark_inputs_stale",
        "freshnessStatus": str(signal_pipeline.get("freshnessStatus") or "unknown"),
        "requestAgeHours": signal_pipeline.get("requestAgeHours"),
        "recordsAgeHours": signal_pipeline.get("recordsAgeHours"),
    }


def resolve_content_domain(payload: dict[str, Any], domains_config: dict[str, Any]) -> str:
    declared = str(payload.get("domain") or "").strip()
    domains = domains_config.get("domains", {})
    if declared in domains:
        return declared

    inferred_topic = infer_topic_from_payload(payload)
    text = " ".join(
        [
            str(payload.get("title") or ""),
            str(payload.get("summary") or ""),
            *[str(item) for item in (payload.get("article_blocks", []) or [])[:6]],
        ]
    ).lower()

    for domain_id, meta in domains.items():
        aliases = [str(item).lower() for item in meta.get("aliases", [])]
        keywords = [str(item).lower() for item in meta.get("keywords", [])]
        if inferred_topic.lower() in aliases:
            return domain_id
        if any(keyword in text for keyword in keywords):
            return domain_id

    return next(iter(domains), "unclassified")


def build_skill_packets(
    *,
    payload: dict[str, Any],
    domain: str,
    registry: dict[str, Any],
    image_plan: dict[str, Any],
    preflight: dict[str, Any],
) -> dict[str, Any]:
    interfaces = registry.get("interfaces", {})
    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or ""),
        "domain": domain,
        "qualityGate": preflight.get("gate", {}),
        "interfaces": {
            name: {
                "status": config.get("status", "unknown"),
                "mode": config.get("mode", "unknown"),
                "primary": config.get("primary"),
                "fallbacks": config.get("fallbacks", []),
                "purpose": config.get("purpose", ""),
            }
            for name, config in interfaces.items()
        },
        "tasks": [
            {
                "interface": "monitor_skill",
                "goal": "补齐同主题对标样本并更新选题池",
            },
            {
                "interface": "writer_skill",
                "goal": "基于当前 payload 继续生成或修订正文草稿",
            },
            {
                "interface": "humanizer_skill",
                "goal": "对正文做人写感收敛，压低模板腔",
            },
            {
                "interface": "illustration_skill",
                "goal": "按 image-plan.json 生成正文配图",
                "details": image_plan.get("bodySlots", []),
            },
            {
                "interface": "cover_skill",
                "goal": "按图片计划生成封面与首图",
                "details": {
                    "coverFamily": image_plan.get("coverFamily"),
                    "coverRenderer": image_plan.get("coverRenderer"),
                    "coverPalette": image_plan.get("coverPalette"),
                },
            },
        ],
    }


def build_publish_preview(
    *,
    payload: dict[str, Any],
    state_path: Path,
    preflight: dict[str, Any],
    registry: dict[str, Any],
    asset_gate: dict[str, Any],
    signal_pipeline: dict[str, Any],
) -> dict[str, Any]:
    interfaces = registry.get("interfaces", {})
    publisher = interfaces.get("publisher_skill", {})
    xhs_placeholder = interfaces.get("xhs_placeholder_publish", {})
    stale_block = resolve_stale_benchmark_block(signal_pipeline)
    gate_status = preflight.get("gate", {}).get("status")
    if stale_block:
        status = str(stale_block["status"])
    elif gate_status != "passed":
        status = "blocked_by_quality_gate"
    elif asset_gate.get("status") != "passed":
        status = "blocked_by_asset_gate"
    else:
        status = "manual_confirmation_required"

    return {
        "schemaVersion": 1,
        "slug": str(payload.get("slug") or ""),
        "formalPublishEnabled": bool(publisher.get("formalPublishEnabled", False)),
        "assetGate": asset_gate,
        "platforms": {
            "toutiao": {
                "status": status,
                "payloadPath": str(preflight["platformPayloads"]["toutiao"]),
                "formalPublishEnabled": False,
                **({"blockContext": stale_block} if stale_block else {}),
            },
            "zhihu": {
                "status": status,
                "payloadPath": str(preflight["platformPayloads"]["zhihu"]),
                "formalPublishEnabled": False,
                **({"blockContext": stale_block} if stale_block else {}),
            },
            "wechat": {
                "status": status,
                "payloadPath": str(preflight["platformPayloads"]["wechat"]),
                "formalPublishEnabled": False,
                **({"blockContext": stale_block} if stale_block else {}),
            },
            "xiaohongshu": {
                "status": (
                    "placeholder_ready"
                    if gate_status == "passed" and asset_gate.get("status") == "passed"
                    else "placeholder_blocked"
                ),
                "formalPublishEnabled": bool(xhs_placeholder.get("formalPublishEnabled", False)),
                "payloadPath": str(state_path.parent / "xhs-placeholder.json"),
            },
        },
    }


def build_operator_checklist(
    *,
    payload: dict[str, Any],
    preflight: dict[str, Any],
    asset_gate: dict[str, Any],
    signal_pipeline: dict[str, Any],
    image_plan_path: Path,
    skill_packets_path: Path,
    publish_preview_path: Path,
    xhs_placeholder_path: Path,
) -> str:
    gate_status = str(preflight.get("gate", {}).get("status") or "unknown")
    signal_status = str(signal_pipeline.get("status") or "unknown")
    signal_source_kind = str(signal_pipeline.get("sourceKind") or "unknown")
    signal_registry_key = str(signal_pipeline.get("registryKey") or "none")
    signal_request_from = str(signal_pipeline.get("requestResolvedFrom") or "unknown")
    signal_records_from = str(signal_pipeline.get("recordsResolvedFrom") or "unknown")
    signal_freshness = str(signal_pipeline.get("freshnessStatus") or "unknown")
    signal_request_age = signal_pipeline.get("requestAgeHours")
    signal_records_age = signal_pipeline.get("recordsAgeHours")
    quality_report_path = preflight.get("reportMarkdownPath")
    required_actions: list[str] = []

    if signal_status == "pending_source":
        required_actions.append("补齐对标来源：提供 `benchmark-records.jsonl`、`benchmark-request.json` 或 payload 中的对标来源路径。")
    else:
        required_actions.append("审阅 `benchmark-monitor.md`、`viral-analysis.md` 和 `rewrite-plan.md`，确认对标、爆款分析和仿写方向无偏差。")

    if gate_status != "passed":
        required_actions.append("先处理质量门禁未通过项，按质量报告逐条修正文案、标题或结构。")
    else:
        required_actions.append("质量门禁已通过，但仍需人工复核三平台标题、摘要和正文开头是否符合当天选题。")

    if asset_gate.get("status") != "passed":
        required_actions.append("补齐封面和正文配图，确保 `cover.png` 和正文图片数量满足最小要求。")
    else:
        required_actions.append("根据 `image-plan.json` 复核封面家族、配色和正文三张图是否真的做出了差异化。")

    required_actions.extend(
        [
            "人工确认 `publish-preview.json` 中今日头条、知乎、公众号仍然处于人工确认或阻塞态，避免误触正式发布。",
            "人工确认小红书仍然只保留占位，不进入正式发布。",
            "正式发布前再次核对是否存在重复发布、重复标题或重复配图风险。",
        ]
    )

    lines = [
        "# 用户配合清单",
        "",
        f"- slug：`{payload.get('slug') or ''}`",
        f"- 标题：`{payload.get('title') or ''}`",
        f"- 更新时间：`{now_iso()}`",
        f"- 质量门禁：`{gate_status}`",
        f"- 资产门禁：`{asset_gate.get('status') or 'unknown'}`",
        f"- 对标信号链：`{signal_status}`",
        f"- 对标输入来源：`{signal_source_kind}` / registry=`{signal_registry_key}` / request=`{signal_request_from}` / records=`{signal_records_from}`",
        f"- 对标输入新鲜度：`{signal_freshness}` / requestAgeHours=`{signal_request_age}` / recordsAgeHours=`{signal_records_age}`",
        "",
        "## 自动产物",
        "",
        f"- 配图计划：`{image_plan_path.name}`",
        f"- 技能调用包：`{skill_packets_path.name}`",
        f"- 发布预览：`{publish_preview_path.name}`",
        f"- 小红书占位：`{xhs_placeholder_path.name}`",
    ]

    if quality_report_path:
        lines.append(f"- 质量报告：`{Path(str(quality_report_path)).name}`")
    if signal_pipeline.get("benchmarkSummaryPath"):
        lines.append(f"- 对标监控：`{Path(str(signal_pipeline['benchmarkSummaryPath'])).name}`")
    if signal_pipeline.get("viralAnalysisPath"):
        lines.append(f"- 爆款分析：`{Path(str(signal_pipeline['viralAnalysisPath'])).name}`")
    if signal_pipeline.get("rewritePlanPath"):
        lines.append(f"- 仿写方案：`{Path(str(signal_pipeline['rewritePlanPath'])).name}`")

    lines.extend(
        [
            "",
            "## 当前边界",
            "",
            "- 这条链路只做到生成、配图规划、预检和发布前占位。",
            "- 今日头条、知乎、公众号默认仍需人工确认后才能正式发布。",
            "- 小红书当前只保留占位，不进入正式发布。",
            "",
            "## 需要你配合的事项",
            "",
        ]
    )
    if signal_freshness == "stale":
        required_actions.insert(0, "对标输入已过期，先刷新 benchmark request / records，再决定是否继续发布。")
    lines.extend([f"{index}. {item}" for index, item in enumerate(required_actions, start=1)])
    lines.append("")
    return "\n".join(lines)


def upsert_history(history: list[dict[str, Any]], entry: dict[str, Any], max_items: int = 50) -> list[dict[str, Any]]:
    output = [item for item in history if item.get("slug") != entry.get("slug")]
    output.append(entry)
    return output[-max_items:]


def run_v3_prepublish(
    payload_path: Path,
    *,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    history_path: Path = DEFAULT_HISTORY_PATH,
    min_score: int = 80,
) -> dict[str, Any]:
    payload_path = payload_path.resolve()
    preflight = run_preflight(payload_path, min_score=min_score)
    payload = read_json(payload_path)
    state_path = Path(preflight["statePath"])
    generated_dir = state_path.parent
    state = ensure_platform_entries(load_pipeline_state(state_path))
    state = reset_stale_platform_statuses(state)

    registry = load_config(config_dir, "tool_registry.json")
    domains_config = load_config(config_dir, "content_domains.json")
    image_strategy = load_config(config_dir, "image_strategy.json")
    history = read_json_file(history_path, [])

    domain = resolve_content_domain(payload, domains_config)
    signal_pipeline = ensure_signal_artifacts(
        generated_dir=generated_dir,
        slug=str(payload.get("slug") or generated_dir.name),
        current_title=str(payload.get("title") or "").strip(),
        payload=payload,
    )
    asset_gate = evaluate_asset_gate(state)
    image_plan = build_image_plan(payload, domain, image_strategy, history if isinstance(history, list) else [])
    skill_packets = build_skill_packets(
        payload=payload,
        domain=domain,
        registry=registry,
        image_plan=image_plan,
        preflight=preflight,
    )
    publish_preview = build_publish_preview(
        payload=payload,
        state_path=state_path,
        preflight=preflight,
        registry=registry,
        asset_gate=asset_gate,
        signal_pipeline=signal_pipeline,
    )

    image_plan_path = state_path.parent / "image-plan.json"
    skill_packets_path = state_path.parent / "skill-packets.json"
    publish_preview_path = state_path.parent / "publish-preview.json"
    xhs_placeholder_path = state_path.parent / "xhs-placeholder.json"
    operator_checklist_path = state_path.parent / "operator-checklist.md"

    write_json_file(image_plan_path, image_plan)
    write_json_file(skill_packets_path, skill_packets)
    write_json_file(publish_preview_path, publish_preview)
    write_json_file(
        xhs_placeholder_path,
        {
            "slug": payload.get("slug"),
            "title": payload.get("title"),
            "status": publish_preview["platforms"]["xiaohongshu"]["status"],
            "note": "第一阶段仅保留预发布占位，不触发正式发布。",
        },
    )
    operator_checklist_path.write_text(
        build_operator_checklist(
            payload=payload,
            preflight=preflight,
            asset_gate=asset_gate,
            signal_pipeline=signal_pipeline,
            image_plan_path=image_plan_path,
            skill_packets_path=skill_packets_path,
            publish_preview_path=publish_preview_path,
            xhs_placeholder_path=xhs_placeholder_path,
        ),
        encoding="utf-8",
    )

    gate_status = preflight.get("gate", {}).get("status")
    ready_for_confirmation = gate_status == "passed" and asset_gate.get("status") == "passed"
    for platform in ("toutiao", "zhihu", "wechat"):
        state["platforms"].setdefault(platform, empty_platform_state())
        state["platforms"][platform]["manualConfirmRequired"] = True
        state["platforms"][platform]["formalPublishEnabled"] = False
        state["platforms"][platform]["prepublishStatus"] = (
            "ready_for_confirmation"
            if ready_for_confirmation
            else ("blocked_by_quality_gate" if gate_status != "passed" else "blocked_by_asset_gate")
        )

    state["platforms"]["xiaohongshu"] = {
        **state["platforms"].get("xiaohongshu", empty_platform_state()),
        "status": "placeholder_ready" if ready_for_confirmation else "placeholder_blocked",
        "attemptCount": 0,
        "manualConfirmRequired": True,
        "formalPublishEnabled": False,
        "verificationSource": "v3_placeholder",
        "error": None,
    }
    state["v3"] = {
        "domain": domain,
        "formalPublishEnabled": False,
        "signalPipeline": signal_pipeline,
        "assetGate": asset_gate,
        "imagePlanPath": str(image_plan_path),
        "skillPacketsPath": str(skill_packets_path),
        "publishPreviewPath": str(publish_preview_path),
        "operatorChecklistPath": str(operator_checklist_path),
        "historyPath": str(history_path),
        "xhsPlaceholderOnly": True,
        "updatedAt": now_iso(),
    }
    state["updatedAt"] = state["v3"]["updatedAt"]
    save_pipeline_state(state_path, state)

    history_entry = {
        "slug": str(payload.get("slug") or ""),
        "domain": domain,
        "coverFamily": image_plan["coverFamily"],
        "coverPalette": image_plan["coverPalette"],
        "bodyFamilies": [slot["family"] for slot in image_plan.get("bodySlots", [])],
        "updatedAt": state["updatedAt"],
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(
        history_path,
        upsert_history(history if isinstance(history, list) else [], history_entry),
    )

    return {
        "mode": "v3-prepublish",
        "payloadPath": str(payload_path),
        "statePath": str(state_path),
        "domain": domain,
        "signalPipeline": signal_pipeline,
        "imagePlanPath": str(image_plan_path),
        "skillPacketsPath": str(skill_packets_path),
        "publishPreviewPath": str(publish_preview_path),
        "operatorChecklistPath": str(operator_checklist_path),
        "formalPublishEnabled": False,
    }


def main() -> int:
    args = parse_args()
    result = run_v3_prepublish(
        args.payload_path,
        config_dir=args.config_dir,
        history_path=args.history_path,
        min_score=args.min_score,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
