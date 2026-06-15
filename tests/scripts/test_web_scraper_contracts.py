import json
import tempfile
import unittest
from pathlib import Path

from scripts.web_scraper_contracts import normalize_record, write_jsonl


class WebScraperContractsTests(unittest.TestCase):
    def test_normalize_record_maps_alias_metrics_and_preserves_source_fields(self) -> None:
        raw = {
            "platform": "Zhihu",
            "title": "设计工具怎么选，先看4个判断",
            "url": "https://example.com/post",
            "author": "示例作者",
            "publishedAt": "2026-06-14T08:30:00+08:00",
            "summary": "先看结果能不能继续改，再看工具值不值得长期用。",
            "metrics": {
                "read_count": "1200",
                "likes": "23",
                "comment_count": "4",
                "favorites": "5",
            },
            "tags": ["AI工具", "效率"],
        }

        record = normalize_record(raw, capture_method="import_json")

        self.assertEqual(record["platform"], "zhihu")
        self.assertEqual(record["recordType"], "article")
        self.assertEqual(record["metrics"]["views"], 1200)
        self.assertEqual(record["metrics"]["likes"], 23)
        self.assertEqual(record["metrics"]["comments"], 4)
        self.assertEqual(record["metrics"]["favorites"], 5)
        self.assertEqual(record["meta"]["captureMethod"], "import_json")
        self.assertEqual(record["meta"]["sourceFields"]["author"], "示例作者")

    def test_normalize_record_requires_title_or_summary(self) -> None:
        raw = {
            "platform": "toutiao",
            "url": "https://example.com/post",
            "metrics": {"views": 12},
        }

        with self.assertRaises(ValueError):
            normalize_record(raw, capture_method="fixture")

    def test_write_jsonl_writes_utf8_lines(self) -> None:
        rows = [
            normalize_record(
                {
                    "platform": "wechat",
                    "title": "AI图片越真实，越要先做4步避坑",
                    "url": "https://example.com/a",
                    "summary": "正文摘要",
                },
                capture_method="fixture",
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            write_jsonl(path, rows)
            content = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(content), 1)
            parsed = json.loads(content[0])
            self.assertEqual(parsed["platform"], "wechat")


if __name__ == "__main__":
    unittest.main()
