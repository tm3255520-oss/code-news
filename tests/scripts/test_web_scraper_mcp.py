import json
import tempfile
import unittest
from pathlib import Path

from scripts.web_scraper_mcp import read_json, run_request


class WebScraperMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture_dir = self.root / "fixtures"
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        (self.fixture_dir / "zhihu-search.json").write_text(
            json.dumps(
                [
                    {
                        "platform": "zhihu",
                        "title": "AI工具怎么选，先看4个判断",
                        "url": "https://example.com/1",
                        "summary": "摘要1",
                        "views": 100,
                    },
                    {
                        "platform": "zhihu",
                        "title": "别急着换工具，先看结果能不能继续改",
                        "url": "https://example.com/2",
                        "summary": "摘要2",
                        "views": 80,
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.config = {
            "schemaVersion": 1,
            "defaultProvider": "fixture",
            "providers": {
                "fixture": {
                    "type": "fixture",
                    "fixtures": {
                        "search_content:zhihu:AI工具": str(self.fixture_dir / "zhihu-search.json")
                    },
                },
                "import_json": {"type": "import_json"},
            },
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_fixture_provider_returns_normalized_search_rows(self) -> None:
        response = run_request(
            {
                "action": "search_content",
                "platform": "zhihu",
                "query": "AI工具",
                "limit": 1,
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(response["records"]), 1)
        self.assertEqual(response["records"][0]["platform"], "zhihu")

    def test_import_json_provider_normalizes_inline_record(self) -> None:
        response = run_request(
            {
                "action": "normalize_record",
                "provider": "import_json",
                "record": {
                    "platform": "wechat",
                    "title": "AI图片越真实，越要先做4步避坑",
                    "summary": "摘要",
                    "url": "https://example.com/wx",
                },
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["record"]["platform"], "wechat")

    def test_import_json_provider_extracts_articles_from_search_envelope(self) -> None:
        envelope_path = self.root / "wechat-search-envelope.json"
        envelope_path.write_text(
            json.dumps(
                {
                    "query": "AI 工具",
                    "total": 2,
                    "articles": [
                        {
                            "title": "普通人买 AI，不该为工具名付费",
                            "url": "https://example.com/wechat-1",
                            "summary": "真正该看的，是能不能接住发布链路。",
                            "datetime": "2026-05-26 18:15:17",
                            "source": "样本账号"
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        response = run_request(
            {
                "action": "search_content",
                "provider": "import_json",
                "platform": "wechat",
                "inputPath": str(envelope_path),
            },
            self.config,
        )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(response["records"]), 1)
        self.assertEqual(response["records"][0]["platform"], "wechat")
        self.assertEqual(response["records"][0]["title"], "普通人买 AI，不该为工具名付费")

    def test_unsupported_action_returns_validation_error(self) -> None:
        response = run_request({"action": "unknown_action"}, self.config)
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["errorType"], "validation_error")

    def test_read_json_accepts_utf8_bom_request_file(self) -> None:
        request_path = self.root / "request.json"
        request_path.write_text(
            json.dumps({"action": "normalize_record", "record": {"title": "demo"}}, ensure_ascii=False),
            encoding="utf-8-sig",
        )

        payload = read_json(request_path)
        self.assertEqual(payload["action"], "normalize_record")


if __name__ == "__main__":
    unittest.main()
