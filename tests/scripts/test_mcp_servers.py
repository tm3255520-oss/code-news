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


class TestVaultWriterMcpServer(unittest.TestCase):
    """vault-writer 的白名单 + 防穿越（2026-09-27：改用 _mcp_compat 取 FastMCP）。"""

    def setUp(self) -> None:
        from scripts import mcp_vault_writer_server as vw

        self.vw = vw

    def test_resolve_accepts_whitelisted_prefix(self) -> None:
        p = self.vw._resolve("内容生产/成品/x.md")
        self.assertEqual(p.name, "x.md")

    def test_resolve_accepts_zhongshu_central(self) -> None:
        # 2026-09-27 增补「系统中枢」：工具档案专区落在该目录下
        p = self.vw._resolve("系统中枢/系统skills以及MCP/内容生产/a.md")
        self.assertIn("系统skills以及MCP", str(p))

    def test_resolve_rejects_non_whitelisted(self) -> None:
        with self.assertRaises(ValueError):
            self.vw._resolve("不存在的目录/x.md")

    def test_resolve_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            self.vw._resolve("../escape.md")

    def test_resolve_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            self.vw._resolve("")

    def test_write_and_append_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = self.vw.VAULT_ROOT
            self.vw.VAULT_ROOT = Path(tmp)
            try:
                r1 = self.vw.write_to_vault("内容生产/a.md", "hello")
                self.assertTrue(r1["ok"], r1)
                r2 = self.vw.append_to_vault("内容生产/a.md", " world")
                self.assertTrue(r2["ok"], r2)
                self.assertTrue(r2["existed"])
                self.assertEqual(
                    (Path(tmp) / "内容生产" / "a.md").read_text(encoding="utf-8"),
                    "hello world",
                )
                r3 = self.vw.write_to_vault("系统中枢/x.md", "y")
                self.assertTrue(r3["ok"], r3)
                self.assertFalse(self.vw.write_to_vault("越界/x.md", "z")["ok"])
            finally:
                self.vw.VAULT_ROOT = old

    def test_list_vault_reports_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = self.vw.VAULT_ROOT
            self.vw.VAULT_ROOT = Path(tmp)
            try:
                (Path(tmp) / "内容生产").mkdir(parents=True, exist_ok=True)
                (Path(tmp) / "内容生产" / "b.md").write_text("x", encoding="utf-8")
                out = self.vw.list_vault("内容生产")
                self.assertTrue(out["ok"])
                self.assertIn("b.md", out["files"])
            finally:
                self.vw.VAULT_ROOT = old


if __name__ == "__main__":
    unittest.main()
