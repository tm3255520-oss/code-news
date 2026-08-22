"""MCP stdio server wrapping the repo-local web_scraper_mcp adapter.

原则：只调用不修改——本文件是包装层，真实逻辑仍在 scripts/web_scraper_mcp.py。
启动：python scripts/mcp_web_scraper_server.py（stdio 传输，供各智能体 MCP 客户端连接）
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

from scripts.web_scraper_mcp import DEFAULT_CONFIG_PATH, read_json, run_request  # noqa: E402

mcp = FastMCP("web-scraper")


def handle_request(
    action: str,
    platform: str = "",
    query: str = "",
    limit: int = 10,
    record_json: str = "{}",
    input_path: str = "",
    provider: str = "",
) -> dict[str, Any]:
    """核心处理：构造请求 JSON 并交给既有适配器（只调用不修改）。"""
    config = read_json(DEFAULT_CONFIG_PATH)
    request: dict[str, Any] = {"action": action}
    if platform:
        request["platform"] = platform
    if query:
        request["query"] = query
    request["limit"] = max(1, int(limit))
    try:
        record = json.loads(record_json)
    except json.JSONDecodeError:
        record = {}
    if isinstance(record, dict) and record:
        request["record"] = record
    if input_path:
        request["inputPath"] = input_path
    if provider:
        request["provider"] = provider
    return run_request(request, config)


@mcp.tool()
def web_scraper_run(
    action: str,
    platform: str = "",
    query: str = "",
    limit: int = 10,
    record_json: str = "{}",
    input_path: str = "",
    provider: str = "",
) -> str:
    """提交一次网页采集/规范化请求（经 web_scraper_mcp 适配器）。

    action 取值（SUPPORTED_ACTIONS）：
      search_content / fetch_article / fetch_author_feed / extract_metrics / normalize_record
    provider 取值（config/web_scraper_mcp.json）：
      import_json（默认，从 record/inputPath 导入）/ fixture（读预置样例）
    record_json：import_json 模式下传入单条记录，或 {"records": [...]} / {"articles": [...]}。
    """
    response = handle_request(action, platform, query, limit, record_json, input_path, provider)
    return json.dumps(response, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
