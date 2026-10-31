"""MCP stdio server wrapping the repo-local codex_api_mcp adapter.

原则：只调用不修改——本文件是包装层，真实逻辑仍在 scripts/codex_api_mcp.py。
启动：python scripts/mcp_codex_api_server.py（stdio 传输，供各智能体 MCP 客户端连接）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from scripts.codex_api_contracts import SUPPORTED_ACTIONS  # noqa: E402
from scripts.codex_api_mcp import DEFAULT_CONFIG_PATH, read_json, run_request  # noqa: E402

mcp = FastMCP("codex-api")


def handle_request(
    action: str,
    topic: str,
    request_id: str,
    output_dir: str,
    platforms: str = "",
    provider: str = "",
) -> dict[str, Any]:
    """核心处理：构造请求 JSON 并交给既有适配器（只调用不修改）。"""
    config = read_json(DEFAULT_CONFIG_PATH)
    request: dict[str, Any] = {
        "action": action,
        "requestId": request_id,
        "topic": topic,
        "outputDir": output_dir,
        "platforms": [p.strip() for p in platforms.split(",") if p.strip()],
    }
    if provider:
        request["provider"] = provider
    return run_request(request, config)


@mcp.tool()
def codex_api_run(
    action: str,
    topic: str,
    request_id: str,
    output_dir: str,
    platforms: str = "",
    provider: str = "",
) -> str:
    """提交一次 AI 生成请求（经 codex_api_mcp 适配器）。

    action 取值（codex_api_contracts.SUPPORTED_ACTIONS）：
      draft_article / generate_titles / build_rewrite_plan / humanize_article / summarize_quality_issues
    platforms：目标平台，逗号分隔（如 "toutiao,zhihu,wechat"），至少一个。
    provider 取值（config/codex_api_mcp.json）：
      packet（默认，写 ai-packets 队列待消费）/ fixture（读预置样例）
    """
    response = handle_request(action, topic, request_id, output_dir, platforms, provider)
    return json.dumps(response, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
