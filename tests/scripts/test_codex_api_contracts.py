import tempfile
import unittest
from pathlib import Path

from scripts.codex_api_contracts import (
    build_artifact_paths,
    validate_request,
    validate_success_payload,
)


class CodexApiContractsTests(unittest.TestCase):
    def test_validate_request_accepts_required_generation_fields(self) -> None:
        request = {
            "action": "draft_article",
            "requestId": "req-001",
            "topic": "设计工具怎么选",
            "platforms": ["toutiao", "zhihu", "wechat"],
            "contentDomain": "AI工具",
            "outputDir": "C:/tmp/generated/demo-slug",
        }
        validated = validate_request(request)
        self.assertEqual(validated["action"], "draft_article")
        self.assertEqual(validated["platforms"], ["toutiao", "zhihu", "wechat"])

    def test_validate_request_rejects_missing_output_dir(self) -> None:
        request = {
            "action": "draft_article",
            "requestId": "req-002",
            "topic": "设计工具怎么选",
        }
        with self.assertRaises(ValueError):
            validate_request(request)

    def test_build_artifact_paths_uses_generated_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = build_artifact_paths(Path(temp_dir))
            self.assertEqual(paths["articlePath"].name, "article.md")
            self.assertEqual(paths["titleVariantsPath"].name, "title-variants.json")
            self.assertEqual(paths["summaryPath"].name, "ai-summary.json")

    def test_validate_success_payload_requires_written_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            article = output_dir / "article.md"
            titles = output_dir / "title-variants.json"
            summary = output_dir / "ai-summary.json"
            article.write_text("# Demo\n", encoding="utf-8")
            titles.write_text("{}", encoding="utf-8")
            summary.write_text("{}", encoding="utf-8")

            payload = {
                "requestId": "req-003",
                "status": "ok",
                "provider": "fixture",
                "artifacts": {
                    "articlePath": str(article),
                    "titleVariantsPath": str(titles),
                    "summaryPath": str(summary),
                },
                "usage": {"inputTokens": 0, "outputTokens": 0},
                "warnings": [],
            }
            validated = validate_success_payload(payload)
            self.assertEqual(validated["status"], "ok")


if __name__ == "__main__":
    unittest.main()
