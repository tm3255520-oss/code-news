import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_content_signal_pipeline import (
    build_rewrite_plan,
    build_title_variants,
    ensure_signal_artifacts,
    run_content_signal_pipeline,
    title_number_hint,
)


class RunContentSignalPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.records_path = self.root / "records.jsonl"
        self.output_dir = self.root / "generated" / "demo-slug"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        rows = [
            {
                "platform": "toutiao",
                "recordType": "article",
                "author": "Flow Lab",
                "title": "Ultimate workflow: publish without rework",
                "url": "https://example.com/toutiao-1",
                "publishedAt": "2026-06-14T08:30:00+08:00",
                "metrics": {"views": 1800, "likes": 55, "comments": 12, "favorites": 9, "shares": 5},
                "content": {"summary": "Auto publishing workflow for content teams.", "rawTextPath": None},
                "meta": {"topic": "ai_tools", "tags": ["workflow", "publish"], "captureMethod": "fixture"},
            },
            {
                "platform": "wechat",
                "recordType": "article",
                "author": "Editor Board",
                "title": "Do not buy tools that cannot ship",
                "url": "https://example.com/wechat-1",
                "publishedAt": "2026-06-14T09:00:00+08:00",
                "metrics": {"views": 1200, "likes": 42, "comments": 8, "favorites": 11, "shares": 2},
                "content": {"summary": "A method guide for reducing publish friction.", "rawTextPath": None},
                "meta": {"topic": "ai_tools", "tags": ["mistake", "guide"], "captureMethod": "fixture"},
            },
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
            },
            {
                "platform": "zhihu",
                "recordType": "article",
                "author": "Design Ops",
                "title": "Top 5 design tools for faster content teams",
                "url": "https://example.com/zhihu-2",
                "publishedAt": "2026-06-13T19:30:00+08:00",
                "metrics": {"views": 900, "likes": 21, "comments": 4, "favorites": 6, "shares": 1},
                "content": {"summary": "Comparison list for design workflows.", "rawTextPath": None},
                "meta": {"topic": "ai_tools", "tags": ["top", "comparison"], "captureMethod": "fixture"},
            },
        ]
        with self.records_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_content_signal_pipeline_writes_required_artifacts(self) -> None:
        result = run_content_signal_pipeline(
            self.records_path,
            self.output_dir,
            slug="demo-slug",
            current_title="Content teams should check 4 publish steps before buying tools",
        )

        self.assertEqual(result["recordCount"], 4)
        self.assertTrue((self.output_dir / "benchmark-monitor.md").exists())
        self.assertTrue((self.output_dir / "peer-content-samples.csv").exists())
        self.assertTrue((self.output_dir / "peer-content-traffic-report.md").exists())
        self.assertTrue((self.output_dir / "viral-analysis.md").exists())
        self.assertTrue((self.output_dir / "rewrite-plan.md").exists())

    def test_run_content_signal_pipeline_builds_peer_sample_rows_from_normalized_records(self) -> None:
        run_content_signal_pipeline(
            self.records_path,
            self.output_dir,
            slug="demo-slug",
            current_title="Content teams should check 4 publish steps before buying tools",
        )

        with (self.output_dir / "peer-content-samples.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["platform"], "toutiao")
        self.assertEqual(rows[0]["bookmarks"], "9")
        self.assertEqual(rows[0]["angle"], "workflow")
        self.assertEqual(rows[0]["hook_type"], "result_first")
        self.assertEqual(rows[2]["format"], "guide")

    def test_run_content_signal_pipeline_markdown_references_current_title_and_visual_variation(self) -> None:
        current_title = "Content teams should check 4 publish steps before buying tools"
        run_content_signal_pipeline(
            self.records_path,
            self.output_dir,
            slug="demo-slug",
            current_title=current_title,
        )

        viral_analysis = (self.output_dir / "viral-analysis.md").read_text(encoding="utf-8")
        rewrite_plan = (self.output_dir / "rewrite-plan.md").read_text(encoding="utf-8")

        self.assertIn("# 爆款分析", viral_analysis)
        self.assertIn("工作流", viral_analysis)
        self.assertIn(current_title, rewrite_plan)
        self.assertIn("对比图", rewrite_plan)
        self.assertIn("链路图", rewrite_plan)
        self.assertIn("清单图", rewrite_plan)

    def test_title_number_hint_ignores_year_only_titles(self) -> None:
        self.assertEqual(
            title_number_hint("Google I/O 2026：AI 开始从回答问题走向替你做事"),
            "4",
        )

    def test_title_number_hint_prefers_checklist_count_over_article_volume(self) -> None:
        self.assertEqual(
            title_number_hint("13篇AI文章复盘后，我只留这5个避坑方法"),
            "5",
        )

    def test_build_title_variants_respects_workflow_titles(self) -> None:
        workflow_rows = [
            {
                "platform": "wechat",
                "title": "6分钟用AI搭好一个工作流",
                "views": 1000,
                "comments": 0,
                "angle": "workflow",
                "format": "workflow_breakdown",
                "hook_type": "workflow",
                "traffic_score": 10.0,
            }
        ]

        variants = build_title_variants(
            "AI 开始接夜班了：真正有用的，不是更会答，而是会自己跑流程",
            workflow_rows,
        )

        self.assertEqual(len(variants), 3)
        self.assertTrue(any("AI" in title for title in variants))
        self.assertTrue(any("流程" in title or "工作流" in title for title in variants))
        self.assertFalse(any("内容团队选工具" in title for title in variants))

    def test_build_rewrite_plan_does_not_hardcode_tool_selection_copy(self) -> None:
        workflow_rows = [
            {
                "platform": "wechat",
                "title": "6分钟用AI搭好一个工作流",
                "views": 1000,
                "comments": 0,
                "angle": "workflow",
                "format": "workflow_breakdown",
                "hook_type": "workflow",
                "traffic_score": 10.0,
            }
        ]

        rewrite_plan = build_rewrite_plan(
            workflow_rows,
            current_title="AI 开始接夜班了：真正有用的，不是更会答，而是会自己跑流程",
        )

        self.assertIn("AI 开始接夜班了", rewrite_plan)
        self.assertIn("工作流", rewrite_plan)
        self.assertNotIn("今天选内容工具", rewrite_plan)

    def test_ensure_signal_artifacts_builds_records_from_benchmark_request_file(self) -> None:
        raw_source_path = self.root / "raw-search.json"
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
        request_path = self.output_dir / "benchmark-request.json"
        request_path.write_text(
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

        result = ensure_signal_artifacts(
            generated_dir=self.output_dir,
            slug="demo-slug",
            current_title="Content teams should check 4 publish steps before buying tools",
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue((self.output_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.output_dir / "benchmark-monitor.md").exists())
        self.assertTrue((self.output_dir / "viral-analysis.md").exists())
        self.assertTrue((self.output_dir / "rewrite-plan.md").exists())
        self.assertTrue(Path(result["requestPath"]).samefile(request_path))
        self.assertEqual(result["sourceKind"], "request_sidecar")
        self.assertIsNone(result["registryKey"])
        self.assertEqual(result["requestResolvedFrom"], "generated_sidecar")
        self.assertEqual(result["recordsResolvedFrom"], "request_fetch")

    def test_ensure_signal_artifacts_keeps_request_path_when_records_already_exist(self) -> None:
        request_path = self.output_dir / "benchmark-request.json"
        request_path.write_text(
            json.dumps(
                {
                    "action": "search_content",
                    "provider": "import_json",
                    "platform": "wechat",
                    "inputPath": str(self.root / "unused-source.json"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        benchmark_records_path = self.output_dir / "benchmark-records.jsonl"
        benchmark_records_path.write_text(self.records_path.read_text(encoding="utf-8"), encoding="utf-8")

        result = ensure_signal_artifacts(
            generated_dir=self.output_dir,
            slug="demo-slug",
            current_title="Content teams should check 4 publish steps before buying tools",
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(Path(result["recordsPath"]), benchmark_records_path.resolve())
        self.assertTrue(Path(result["requestPath"]).samefile(request_path))
        self.assertEqual(result["sourceKind"], "records_reused")
        self.assertIsNone(result["registryKey"])
        self.assertEqual(result["requestResolvedFrom"], "generated_sidecar")
        self.assertEqual(result["recordsResolvedFrom"], "generated_records")

    def test_ensure_signal_artifacts_uses_registry_fallback_when_payload_has_topic_only(self) -> None:
        raw_source_path = self.root / "registry-source.json"
        raw_source_path.write_text(
            json.dumps(
                [
                    {
                        "platform": "wechat",
                        "title": "Workflow guide for AI night shift ops",
                        "url": "https://example.com/wechat-workflow",
                        "summary": "A workflow benchmark sample for AI approval-first content ops.",
                        "views": 2100,
                        "likes": 61,
                        "comments": 18,
                        "favorites": 16,
                        "shares": 7,
                        "author": "Workflow Desk",
                        "publishedAt": "2026-06-15T20:00:00+08:00",
                        "tags": ["workflow", "approval"],
                        "topic": "workflow-shift",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        registry_path = self.root / "benchmark_source_registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "workflow-shift": {
                            "aliases": ["efficiency_tools", "approval-first"],
                            "action": "search_content",
                            "provider": "import_json",
                            "platform": "wechat",
                            "inputPath": str(raw_source_path),
                            "query": "AI workflow",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = ensure_signal_artifacts(
            generated_dir=self.output_dir,
            slug="demo-slug",
            current_title="AI night shift workflow value",
            payload={
                "topic": "workflow-shift",
                "benchmarkRegistryPath": str(registry_path),
            },
        )

        self.assertEqual(result["status"], "completed")
        self.assertTrue((self.output_dir / "benchmark-request.json").exists())
        self.assertTrue((self.output_dir / "benchmark-records.jsonl").exists())
        request = json.loads((self.output_dir / "benchmark-request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["provider"], "import_json")
        self.assertEqual(request["platform"], "wechat")
        self.assertTrue(Path(request["inputPath"]).samefile(raw_source_path))
        self.assertEqual(result["sourceKind"], "registry")
        self.assertEqual(result["registryKey"], "workflow-shift")
        self.assertEqual(result["requestResolvedFrom"], "registry")
        self.assertEqual(result["recordsResolvedFrom"], "request_fetch")


if __name__ == "__main__":
    unittest.main()
