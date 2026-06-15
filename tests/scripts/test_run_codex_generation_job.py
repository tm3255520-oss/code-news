import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_codex_generation_job import run_generation_job


class RunCodexGenerationJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        (self.generated_dir / "benchmark-monitor.md").write_text("# Benchmark\n", encoding="utf-8")
        (self.generated_dir / "viral-analysis.md").write_text("# Viral\n", encoding="utf-8")
        (self.generated_dir / "rewrite-plan.md").write_text("# Rewrite\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_generation_job_builds_request_and_writes_request_copy(self) -> None:
        request_path = self.generated_dir / "generation-request.json"
        result = run_generation_job(
            generated_dir=self.generated_dir,
            topic="设计工具怎么选",
            content_domain="AI工具",
            platforms=["toutiao", "zhihu", "wechat"],
            provider="packet",
            config={
                "schemaVersion": 1,
                "defaultProvider": "packet",
                "providers": {"packet": {"type": "packet", "packetDirName": "ai-packets"}},
            },
            request_path=request_path,
        )
        self.assertTrue(request_path.exists())
        self.assertEqual(result["status"], "queued")

    def test_run_generation_job_builds_signal_inputs_from_benchmark_records(self) -> None:
        for name in ("benchmark-monitor.md", "viral-analysis.md", "rewrite-plan.md"):
            (self.generated_dir / name).unlink()

        records_path = self.generated_dir / "benchmark-records.jsonl"
        records = [
            {
                "platform": "zhihu",
                "recordType": "article",
                "author": "Research Crew",
                "title": "Guide: 4 checks before you choose a content tool",
                "url": "https://example.com/zhihu-1",
                "publishedAt": "2026-06-14T10:00:00+08:00",
                "metrics": {"views": 1500, "likes": 48, "comments": 15, "favorites": 14, "shares": 4},
                "content": {"summary": "Selection guide for multi-platform content ops.", "rawTextPath": None},
                "meta": {"topic": "ai_tools", "tags": ["guide", "checklist"], "captureMethod": "fixture"},
            }
        ]
        with records_path.open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        request_path = self.generated_dir / "generation-request.json"
        result = run_generation_job(
            generated_dir=self.generated_dir,
            topic="内容团队选工具，先过这4个发布前判断",
            content_domain="AI工具",
            platforms=["toutiao", "zhihu", "wechat"],
            provider="packet",
            config={
                "schemaVersion": 1,
                "defaultProvider": "packet",
                "providers": {"packet": {"type": "packet", "packetDirName": "ai-packets"}},
            },
            request_path=request_path,
        )

        self.assertEqual(result["status"], "queued")
        self.assertTrue((self.generated_dir / "benchmark-monitor.md").exists())
        self.assertTrue((self.generated_dir / "viral-analysis.md").exists())
        self.assertTrue((self.generated_dir / "rewrite-plan.md").exists())
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(
            request_payload["inputs"]["benchmarkSummaryPath"],
            str(self.generated_dir / "benchmark-monitor.md"),
        )

    def test_run_generation_job_builds_records_from_benchmark_request_sidecar(self) -> None:
        for name in ("benchmark-monitor.md", "viral-analysis.md", "rewrite-plan.md"):
            (self.generated_dir / name).unlink()

        raw_source_path = self.root / "raw-monitor-source.json"
        raw_source_path.write_text(
            json.dumps(
                [
                    {
                        "platform": "zhihu",
                        "title": "Guide: 4 checks before you choose a content tool",
                        "url": "https://example.com/zhihu-1",
                        "summary": "Selection guide for multi-platform content ops.",
                        "views": 1500,
                        "likes": 48,
                        "comments": 15,
                        "favorites": 14,
                        "shares": 4,
                        "author": "Research Crew",
                        "publishedAt": "2026-06-14T10:00:00+08:00",
                        "tags": ["guide", "checklist"],
                        "topic": "ai_tools",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.generated_dir / "benchmark-request.json").write_text(
            json.dumps(
                {
                    "action": "search_content",
                    "provider": "import_json",
                    "platform": "zhihu",
                    "inputPath": str(raw_source_path),
                    "limit": 10,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        request_path = self.generated_dir / "generation-request.json"
        result = run_generation_job(
            generated_dir=self.generated_dir,
            topic="内容团队选工具，先过这4个发布前判断",
            content_domain="AI工具",
            platforms=["toutiao", "zhihu", "wechat"],
            provider="packet",
            config={
                "schemaVersion": 1,
                "defaultProvider": "packet",
                "providers": {"packet": {"type": "packet", "packetDirName": "ai-packets"}},
            },
            request_path=request_path,
        )

        self.assertEqual(result["status"], "queued")
        self.assertTrue((self.generated_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.generated_dir / "benchmark-monitor.md").exists())
        self.assertTrue((self.generated_dir / "viral-analysis.md").exists())
        self.assertTrue((self.generated_dir / "rewrite-plan.md").exists())


if __name__ == "__main__":
    unittest.main()
