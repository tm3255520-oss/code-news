import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_benchmark_monitor import read_jsonl, run_benchmark_monitor


class RunBenchmarkMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.records_path = self.root / "records.jsonl"
        self.output_dir = self.root / "generated" / "demo-slug"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        rows = [
            {
                "platform": "zhihu",
                "recordType": "article",
                "author": "A",
                "title": "AI工具怎么选，先看4个判断",
                "url": "https://example.com/1",
                "publishedAt": "2026-06-14T08:30:00+08:00",
                "metrics": {"views": 1200, "likes": 23, "comments": 4, "favorites": 5, "shares": 0},
                "content": {"summary": "摘要1", "rawTextPath": None},
                "meta": {"topic": "AI工具", "tags": ["AI工具"], "captureMethod": "fixture"},
            },
            {
                "platform": "wechat",
                "recordType": "article",
                "author": "B",
                "title": "AI图片越真实，越要先做4步避坑",
                "url": "https://example.com/2",
                "publishedAt": "2026-06-14T09:30:00+08:00",
                "metrics": {"views": 600, "likes": 16, "comments": 2, "favorites": 3, "shares": 0},
                "content": {"summary": "摘要2", "rawTextPath": None},
                "meta": {"topic": "AI工具", "tags": ["AI图片"], "captureMethod": "fixture"},
            },
        ]
        with self.records_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_benchmark_monitor_writes_jsonl_and_markdown(self) -> None:
        result = run_benchmark_monitor(self.records_path, self.output_dir, slug="demo-slug")
        self.assertTrue((self.output_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.output_dir / "benchmark-monitor.md").exists())
        self.assertEqual(result["recordCount"], 2)

    def test_run_benchmark_monitor_markdown_mentions_platforms_and_titles(self) -> None:
        run_benchmark_monitor(self.records_path, self.output_dir, slug="demo-slug")
        content = (self.output_dir / "benchmark-monitor.md").read_text(encoding="utf-8")
        self.assertIn("zhihu", content)
        self.assertIn("wechat", content)
        self.assertIn("AI工具怎么选", content)

    def test_read_jsonl_accepts_utf8_bom_file(self) -> None:
        bom_path = self.root / "records-bom.jsonl"
        bom_path.write_text(
            json.dumps(
                {
                    "platform": "zhihu",
                    "recordType": "article",
                    "author": "A",
                    "title": "AI工具怎么选，先看4个判断",
                    "url": "https://example.com/1",
                    "publishedAt": "2026-06-14T08:30:00+08:00",
                    "metrics": {"views": 1200, "likes": 23, "comments": 4, "favorites": 5, "shares": 0},
                    "content": {"summary": "摘要1", "rawTextPath": None},
                    "meta": {"topic": "AI工具", "tags": ["AI工具"], "captureMethod": "fixture"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8-sig",
        )

        rows = read_jsonl(bom_path)
        self.assertEqual(rows[0]["platform"], "zhihu")


if __name__ == "__main__":
    unittest.main()
