import json
import tempfile
import unittest
from pathlib import Path

from scripts.refresh_benchmark_sources import refresh_benchmark_sources


class RefreshBenchmarkSourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_dir = self.root / "config"
        self.tmp_dir = self.root / ".tmp"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.config_dir / "benchmark_source_registry.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "design-tools": {
                            "platform": "wechat",
                            "query": "AI 工具",
                            "inputPath": "../.tmp/wechat-search-ai-tools.json",
                        },
                        "workflow-shift": {
                            "platform": "wechat",
                            "query": "AI 编程",
                            "inputPath": "../.tmp/wechat-search-ai-coding.json",
                        },
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_refresh_benchmark_sources_refreshes_stale_and_missing_jobs(self) -> None:
        audit = {
            "staleSourcePaths": [{"registryKey": "design-tools"}],
            "missingSourcePaths": [{"registryKey": "workflow-shift"}],
            "emptySourcePaths": [],
        }
        seen_jobs: list[dict[str, str]] = []

        def runner(job: dict[str, object]) -> dict[str, object]:
            seen_jobs.append(
                {
                    "registryKey": str(job["registryKey"]),
                    "query": str(job["query"]),
                    "outputPath": str(job["outputPath"]),
                }
            )
            Path(str(job["outputPath"])).write_text(
                json.dumps({"query": job["query"], "total": 1, "articles": [{"title": "demo"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            return {"status": "ok", "recordCount": 1}

        result = refresh_benchmark_sources(
            registry_path=self.registry_path,
            audit=audit,
            runner=runner,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["refreshedCount"], 2)
        self.assertEqual(result["failedCount"], 0)
        self.assertEqual(len(seen_jobs), 2)
        self.assertEqual({job["registryKey"] for job in seen_jobs}, {"design-tools", "workflow-shift"})
        self.assertTrue((self.tmp_dir / "wechat-search-ai-tools.json").exists())
        self.assertTrue((self.tmp_dir / "wechat-search-ai-coding.json").exists())

    def test_refresh_benchmark_sources_reports_missing_query_as_failure(self) -> None:
        self.registry_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "design-tools": {
                            "platform": "wechat",
                            "inputPath": "../.tmp/wechat-search-ai-tools.json",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = refresh_benchmark_sources(
            registry_path=self.registry_path,
            audit={"staleSourcePaths": [{"registryKey": "design-tools"}]},
            runner=lambda job: {"status": "ok"},
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["refreshedCount"], 0)
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["results"][0]["status"], "missing_query")


if __name__ == "__main__":
    unittest.main()
