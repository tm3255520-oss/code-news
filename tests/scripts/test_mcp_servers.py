"""Tests for the MCP stdio server wrappers (scripts/mcp_*_server.py)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.mcp_codex_api_server import handle_request as codex_handle
from scripts.mcp_web_scraper_server import handle_request as scraper_handle


class TestCodexApiMcpServer(unittest.TestCase):
    def test_packet_provider_queues_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = codex_handle(
                action="draft_article",
                topic="AI 工具测评",
                request_id="test-mcp-001",
                output_dir=tmp,
                platforms="toutiao",
                provider="packet",
            )
            self.assertEqual(response["status"], "queued")
            self.assertIn("packetPath", response)
            packet = Path(response["packetPath"])
            self.assertTrue(packet.exists())
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(payload["action"], "draft_article")
            self.assertEqual(payload["requestId"], "test-mcp-001")

    def test_default_provider_is_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = codex_handle(
                action="generate_titles",
                topic="标题生成测试",
                request_id="test-mcp-002",
                output_dir=tmp,
                platforms="zhihu",
            )
            self.assertEqual(response["status"], "queued")

    def test_invalid_action_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = codex_handle(
                action="not_a_real_action",
                topic="x",
                request_id="test-mcp-003",
                output_dir=tmp,
                platforms="toutiao",
            )
            self.assertEqual(response["status"], "error")


class TestWebScraperMcpServer(unittest.TestCase):
    def test_import_json_single_record(self) -> None:
        response = scraper_handle(
            action="normalize_record",
            platform="toutiao",
            record_json=json.dumps(
                {"title": "测试标题", "content": "测试摘要", "url": "https://example.com/1"},
                ensure_ascii=False,
            ),
            provider="import_json",
        )
        self.assertEqual(response["status"], "ok")
        record = response["record"]
        self.assertEqual(record["title"], "测试标题")
        self.assertEqual(record["url"], "https://example.com/1")

    def test_search_content_with_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "records.json"
            src.write_text(
                json.dumps(
                    {
                        "records": [
                            {"title": "A", "url": "https://example.com/a"},
                            {"title": "B", "url": "https://example.com/b"},
                            {"title": "C", "url": "https://example.com/c"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            response = scraper_handle(
                action="search_content",
                platform="zhihu",
                limit=2,
                input_path=str(src),
                provider="import_json",
            )
            self.assertEqual(response["status"], "ok")
            self.assertEqual(len(response["records"]), 2)

    def test_unsupported_action(self) -> None:
        response = scraper_handle(action="fly_to_moon", provider="import_json")
        self.assertEqual(response["status"], "error")


if __name__ == "__main__":
    unittest.main()
