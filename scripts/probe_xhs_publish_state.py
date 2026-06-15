#!/usr/bin/env python3
"""Probe the current Xiaohongshu publish state through the controlled browser."""

from __future__ import annotations

import json
import sys
from pathlib import Path


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS_DIR = ROOT / ".agents" / "skills" / "xiaohongshu-skills" / "scripts"
if str(SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from xhs.cdp import Browser  # type: ignore  # noqa: E402
from xhs.urls import PUBLISH_URL  # type: ignore  # noqa: E402


PORT = 9226
OUTPUT_PATH = ROOT / ".tmp" / "xhs-publish-probe.json"


def evaluate_state(page) -> dict:
    return page.evaluate(
        """
        (() => {
          const bodyText = (document.body ? document.body.innerText : "").slice(0, 4000);
          const editorNodes = Array.from(document.querySelectorAll(".tiptap.ProseMirror, [contenteditable='true']"));
          const uploadButtons = Array.from(document.querySelectorAll("button, div, span"))
            .map(node => (node.innerText || "").trim())
            .filter(Boolean)
            .filter(text => ["写长文", "上传图文", "上传视频", "发布笔记", "发布"].includes(text));
          return {
            url: window.location.href,
            title: document.title,
            bodyText,
            hasEditor: editorNodes.length > 0,
            editorCount: editorNodes.length,
            uploadButtons,
          };
        })()
        """
    )


def classify(state: dict) -> str:
    url = state.get("url", "")
    body_text = state.get("bodyText", "")

    if "login" in url or "短信登录" in body_text or "发送验证码" in body_text:
        return "logged_out"

    if state.get("hasEditor"):
        return "editor_ready"

    if "publish/publish" in url:
        return "publish_home"

    return "unknown"


def run_probe() -> dict:
    browser = Browser(port=PORT)
    page = None
    try:
        try:
            page = browser.get_existing_page() or browser.get_or_create_page()
            page.navigate(PUBLISH_URL)
            page.wait_for_load(timeout=120)
            page.wait_dom_stable()

            state = evaluate_state(page)
            state["status"] = classify(state)
            state["port"] = PORT
            state["publishUrl"] = PUBLISH_URL
        except Exception as exc:
            state = {
                "status": "cdp_unavailable",
                "port": PORT,
                "publishUrl": PUBLISH_URL,
                "error": str(exc),
            }
        return state
    finally:
        browser.close()


def main() -> None:
    state = run_probe()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
