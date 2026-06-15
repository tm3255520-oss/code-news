#!/usr/bin/env python3
"""Summarize publish readiness across the four current platforms."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = ROOT / ".tmp"


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class PlatformConfig:
    key: str
    label: str
    profile_dir: Path
    records_path: Path | None
    launch_hint: str
    baseline_grade: str


PLATFORMS: list[PlatformConfig] = [
    PlatformConfig(
        key="wechat",
        label="微信公众号",
        profile_dir=TMP_DIR / "browser-profiles" / "wechat-automation",
        records_path=TMP_DIR / "analytics" / "wechat_recent_metrics_structured.json",
        launch_hint="node .tmp/launch_wechat_controlled_chrome.js",
        baseline_grade="B+",
    ),
    PlatformConfig(
        key="zhihu",
        label="知乎",
        profile_dir=TMP_DIR / "browser-profiles" / "zhihu-automation",
        records_path=TMP_DIR / "zhihu-publish-records.json",
        launch_hint="node .tmp/launch_zhihu_controlled_chrome.js",
        baseline_grade="A-",
    ),
    PlatformConfig(
        key="toutiao",
        label="今日头条",
        profile_dir=TMP_DIR / "browser-profiles" / "toutiao",
        records_path=TMP_DIR / "toutiao-publish-records.json",
        launch_hint="Use the dedicated Toutiao browser profile before publish.",
        baseline_grade="B-",
    ),
    PlatformConfig(
        key="xhs",
        label="小红书",
        profile_dir=TMP_DIR / "browser-profiles" / "xhs-controlled",
        records_path=TMP_DIR / "xhs-publish-records.json",
        launch_hint="node .tmp/launch_xhs_bridge_chrome.js",
        baseline_grade="C+",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check current publish readiness for WeChat, Zhihu, Toutiao, and Xiaohongshu."
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return fallback


def safe_iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def latest_file(path: Path, pattern: str) -> Path | None:
    matches = list(path.glob(pattern))
    if not matches:
        return None
    matches.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0]


def latest_xhs_debug_dir() -> Path | None:
    generated_dir = TMP_DIR / "generated"
    if not generated_dir.exists():
        return None
    candidates = [item for item in generated_dir.glob("*/debug/xhs") if item.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def latest_publish_record(config: PlatformConfig) -> dict[str, Any] | None:
    if not config.records_path:
        return None

    if config.key == "wechat":
        rows = read_json(config.records_path, [])
        published_rows = [row for row in rows if row.get("status") == "published"]
        return published_rows[0] if published_rows else (rows[0] if rows else None)

    rows = read_json(config.records_path, [])
    if isinstance(rows, list) and rows:
        return rows[-1] if config.key in {"zhihu", "toutiao", "xhs"} else rows[0]
    return None


def summarize_profile(config: PlatformConfig) -> dict[str, Any]:
    exists = config.profile_dir.exists()
    known_profile_dirs = [
        name
        for name in ("Default", "Profile", "Profile 2")
        if (config.profile_dir / name).exists()
    ]
    return {
        "exists": exists,
        "default_profile_exists": bool(known_profile_dirs),
        "known_profile_dirs": known_profile_dirs,
        "updated_at": safe_iso(config.profile_dir.stat().st_mtime if exists else None),
    }


def status_payload(
    config: PlatformConfig,
    state: str,
    summary: str,
    blockers: list[str],
    next_actions: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "platform": config.label,
        "key": config.key,
        "baseline_grade": config.baseline_grade,
        "state": state,
        "summary": summary,
        "profile": summarize_profile(config),
        "latest_publish_record": latest_publish_record(config),
        "blockers": blockers,
        "next_actions": next_actions,
        "launch_hint": config.launch_hint,
    }
    if extra:
        payload.update(extra)
    return payload


def check_wechat(config: PlatformConfig) -> dict[str, Any]:
    profile = summarize_profile(config)
    blockers: list[str] = []
    next_actions = [
        "Use the dedicated controlled Chrome profile before every publish.",
        "Budget for the final WeChat verification QR step during formal publish.",
    ]

    if not profile["exists"] or not profile["default_profile_exists"]:
        blockers.append("Dedicated WeChat browser profile is missing.")
        next_actions.insert(0, "Launch and log in to the WeChat automation profile.")
        return status_payload(
            config,
            state="blocked",
            summary="Profile is not ready, so WeChat publish is blocked.",
            blockers=blockers,
            next_actions=next_actions,
        )

    return status_payload(
        config,
        state="warning",
        summary="Flow is usable, but final publish still depends on manual WeChat verification.",
        blockers=blockers,
        next_actions=next_actions,
    )


def check_zhihu(config: PlatformConfig) -> dict[str, Any]:
    profile = summarize_profile(config)
    blockers: list[str] = []
    next_actions = [
        "Run a quick draft publish probe before a large batch.",
        "Keep using the dedicated Zhihu profile to avoid login churn.",
    ]
    latest_record = latest_publish_record(config)

    if not profile["exists"] or not profile["default_profile_exists"]:
        blockers.append("Dedicated Zhihu browser profile is missing.")
        next_actions.insert(0, "Launch and log in to the Zhihu automation profile.")
        return status_payload(
            config,
            state="blocked",
            summary="Profile is not ready, so Zhihu publish is blocked.",
            blockers=blockers,
            next_actions=next_actions,
        )

    if not latest_record:
        return status_payload(
            config,
            state="warning",
            summary="No local publish proof was found recently, so Zhihu should be re-probed before publishing.",
            blockers=blockers,
            next_actions=next_actions,
        )

    return status_payload(
        config,
        state="ready",
        summary="Zhihu is the smoothest current channel and looks ready to publish.",
        blockers=blockers,
        next_actions=next_actions,
    )


def check_toutiao(config: PlatformConfig) -> dict[str, Any]:
    profile = summarize_profile(config)
    blockers: list[str] = []
    next_actions = [
        "Accept platform auto-generated cover layouts when possible.",
        "Run post-publish list verification instead of trusting editor success alone.",
    ]
    latest_record = latest_publish_record(config)

    if not profile["exists"] or not profile["default_profile_exists"]:
        blockers.append("Dedicated Toutiao browser profile is missing.")
        next_actions.insert(0, "Open the Toutiao profile and confirm login first.")
        return status_payload(
            config,
            state="blocked",
            summary="Profile is not ready, so Toutiao publish is blocked.",
            blockers=blockers,
            next_actions=next_actions,
        )

    if not latest_record:
        return status_payload(
            config,
            state="warning",
            summary="Flow exists, but there is no recent local publish proof. Re-run a probe before production use.",
            blockers=blockers,
            next_actions=next_actions,
        )

    return status_payload(
        config,
        state="warning",
        summary="Toutiao can publish, but it is still a fragile browser flow with edge-case risk around cover, title, and list verification.",
        blockers=blockers,
        next_actions=next_actions,
    )


def check_xhs(config: PlatformConfig) -> dict[str, Any]:
    profile = summarize_profile(config)
    blockers: list[str] = []
    next_actions = [
        "Open the dedicated XHS browser/bridge profile before publish.",
        "Run a login probe before starting any new long-form post.",
        "Treat missing templates or bridge disconnects as blockers, not soft failures.",
    ]
    latest_record = latest_publish_record(config)
    debug_dir = latest_xhs_debug_dir()
    probe_state = read_json(TMP_DIR / "xhs-publish-probe.json", {})
    login_state = read_json(debug_dir / "login-state.json", {}) if debug_dir else {}
    long_article_state = read_json(debug_dir / "long-article-stage.json", {}) if debug_dir else {}

    extra = {
        "latest_debug_dir": str(debug_dir) if debug_dir else None,
        "latest_probe_state": probe_state or None,
        "latest_login_state": login_state or None,
        "latest_long_article_state": long_article_state or None,
    }

    if not profile["exists"]:
        blockers.append("Dedicated XHS browser profile is missing.")
        next_actions.insert(0, "Launch the XHS bridge browser and log in again.")
        return status_payload(
            config,
            state="blocked",
            summary="Profile is not ready, so Xiaohongshu publish is blocked.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    if login_state and login_state.get("loggedIn") is False:
        blockers.append("Latest XHS debug run fell back to the login page.")
        next_actions.insert(0, "Repair login/session state before the next publish attempt.")
        return status_payload(
            config,
            state="blocked",
            summary="Latest debug signal shows Xiaohongshu is not currently logged in.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    probe_status = probe_state.get("status")

    if probe_status == "cdp_unavailable":
        blockers.append("Latest XHS probe shows the controlled browser/CDP endpoint is unavailable.")
        next_actions.insert(0, "Relaunch the XHS bridge browser before any publish attempt.")
        return status_payload(
            config,
            state="blocked",
            summary="Xiaohongshu is currently blocked because the controlled browser/CDP endpoint is unavailable.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    if probe_status == "logged_out":
        blockers.append("Latest XHS probe landed on the login page.")
        next_actions.insert(0, "Log in to Xiaohongshu in the dedicated controlled browser before publishing.")
        return status_payload(
            config,
            state="blocked",
            summary="Xiaohongshu is currently blocked because the dedicated publish browser is logged out.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    template_count = long_article_state.get("templateCount")
    if template_count == 0:
        blockers.append("Latest XHS long-article stage returned zero templates.")
        return status_payload(
            config,
            state="warning",
            summary="Xiaohongshu is partially available, but the latest publish flow did not complete the long-article template stage.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    if latest_record:
        return status_payload(
            config,
            state="warning",
            summary="Xiaohongshu has local publish proof, but it still depends on fragile browser and bridge state.",
            blockers=blockers,
            next_actions=next_actions,
            extra=extra,
        )

    return status_payload(
        config,
        state="warning",
        summary="Xiaohongshu has no recent proof of a clean publish closeout, so re-probe before production use.",
        blockers=blockers,
        next_actions=next_actions,
        extra=extra,
    )


def evaluate() -> list[dict[str, Any]]:
    checks = {
        "wechat": check_wechat,
        "zhihu": check_zhihu,
        "toutiao": check_toutiao,
        "xhs": check_xhs,
    }
    return [checks[config.key](config) for config in PLATFORMS]


def render_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Publish Readiness",
        "",
        f"- Generated at `{datetime.now().isoformat(timespec='seconds')}`",
        "",
        "| Platform | Baseline | State | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for item in results:
        lines.append(
            f"| {item['platform']} | {item['baseline_grade']} | {item['state']} | {item['summary']} |"
        )

    for item in results:
        lines.extend(
            [
                "",
                f"## {item['platform']}",
                "",
                f"- State: `{item['state']}`",
                f"- Baseline grade: `{item['baseline_grade']}`",
                f"- Launch hint: `{item['launch_hint']}`",
            ]
        )

        profile = item.get("profile", {})
        lines.append(
            f"- Profile ready: `{profile.get('exists') and profile.get('default_profile_exists')}`"
        )
        if profile.get("updated_at"):
            lines.append(f"- Profile updated at: `{profile['updated_at']}`")

        if item.get("latest_publish_record"):
            lines.append(f"- Latest publish record: `{json.dumps(item['latest_publish_record'], ensure_ascii=False)}`")

        if item.get("blockers"):
            lines.append("- Current blockers:")
            for blocker in item["blockers"]:
                lines.append(f"  - {blocker}")

        if item.get("next_actions"):
            lines.append("- Next actions:")
            for action in item["next_actions"]:
                lines.append(f"  - {action}")

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    results = evaluate()
    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(results))


if __name__ == "__main__":
    main()
