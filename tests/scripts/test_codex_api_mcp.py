import json
import tempfile
import unittest
from pathlib import Path

from scripts.codex_api_mcp import run_request


class CodexApiMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture_dir = self.root / "fixtures"
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        (self.fixture_dir / "draft-article.json").write_text(
            json.dumps(
                {
                    "article_markdown": "# 设计工具怎么选\n\n先看结果能不能继续改。",
                    "title_variants": {
                        "toutiao": ["设计工具怎么选，先看4个判断"],
                        "zhihu": ["设计工具怎么选，哪些判断最值钱"],
                        "wechat": ["设计工具怎么选，我现在先看能不能继续改"],
                    },
                    "summary": {
                        "hook": "先看结果，再谈工具。",
                        "angle": "减少返工",
                        "warnings": [],
                    },
                    "usage": {"inputTokens": 1200, "outputTokens": 800},
                },
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
                        "draft_article": str(self.fixture_dir / "draft-article.json")
                    },
                },
                "packet": {
                    "type": "packet",
                    "packetDirName": "ai-packets",
                },
            },
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_fixture_provider_writes_generation_artifacts(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "requestId": "req-001",
                "topic": "设计工具怎么选",
                "platforms": ["toutiao", "zhihu", "wechat"],
                "contentDomain": "AI工具",
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "ok")
        self.assertTrue((output_dir / "article.md").exists())
        self.assertTrue((output_dir / "title-variants.json").exists())
        self.assertTrue((output_dir / "ai-summary.json").exists())

    def test_packet_provider_writes_request_packet_and_returns_packet_status(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "provider": "packet",
                "requestId": "req-002",
                "topic": "设计工具怎么选",
                "platforms": ["toutiao"],
                "contentDomain": "AI工具",
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "queued")
        self.assertTrue((output_dir / "ai-packets" / "req-002.json").exists())

    def test_unsupported_provider_returns_validation_error(self) -> None:
        output_dir = self.root / "generated" / "demo-slug"
        response = run_request(
            {
                "action": "draft_article",
                "provider": "missing",
                "requestId": "req-003",
                "topic": "设计工具怎么选",
                "platforms": ["wechat"],
                "outputDir": str(output_dir),
            },
            self.config,
        )
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["errorType"], "validation_error")

    def test_fixture_provider_accepts_utf8_bom_fixture_file(self) -> None:
        bom_fixture = self.fixture_dir / "draft-article-bom.json"
        bom_fixture.write_text(
            json.dumps(
                {
                    "article_markdown": "# 设计工具怎么选\n\n先看结果能不能继续改。",
                    "title_variants": {"toutiao": ["设计工具怎么选，先看4个判断"]},
                    "summary": {"hook": "先看结果，再谈工具。", "angle": "减少返工", "warnings": []},
                    "usage": {"inputTokens": 10, "outputTokens": 20},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8-sig",
        )
        config = {
            "schemaVersion": 1,
            "defaultProvider": "fixture",
            "providers": {
                "fixture": {
                    "type": "fixture",
                    "fixtures": {
                        "draft_article": str(bom_fixture)
                    },
                }
            },
        }
        output_dir = self.root / "generated" / "demo-bom"
        response = run_request(
            {
                "action": "draft_article",
                "requestId": "req-bom",
                "topic": "设计工具怎么选",
                "platforms": ["toutiao"],
                "contentDomain": "AI工具",
                "outputDir": str(output_dir),
            },
            config,
        )
        self.assertEqual(response["status"], "ok")


if __name__ == "__main__":
    unittest.main()
