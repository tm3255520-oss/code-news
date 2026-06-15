import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_daily_content_ops import (
    build_brief,
    build_run_summary,
    latest_generated_article_dir,
    load_benchmark_registry,
    prepare_benchmark_source_for_generated_dir,
    refresh_benchmark_registry_if_needed,
    resolve_registry_request,
)


class RunDailyContentOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_root = self.root / ".tmp"
        self.generated_dir = self.payload_root / "generated" / "demo-slug"
        self.config_dir = self.root / "config"
        self.payload_root.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "slug": "demo-slug",
            "title": "内容团队选工具，先过这4个发布前判断",
            "summary": "Canva 和 Figma 都在前面，但真正决定效率的是后面的发布链路。",
            "article_blocks": [
                "上午做完，下午还在改尺寸、补封面、填说明，晚上还没发出去。",
                "真正拖慢团队的，不是第一稿，而是后面的返工和分发。",
                "所以今天选工具，先看它能不能把最后一公里接住。",
            ],
        }
        self.payload_path = self.payload_root / "toutiao_payload_demo.json"
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prepare_benchmark_source_for_generated_dir_uses_registry_when_payload_has_no_source(self) -> None:
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
        registry_path = self.config_dir / "benchmark_source_registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "design-tools": {
                            "action": "search_content",
                            "provider": "import_json",
                            "platform": "zhihu",
                            "inputPath": str(raw_source_path),
                            "query": "设计工具 工作流 发布",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = prepare_benchmark_source_for_generated_dir(
            self.generated_dir,
            payload_root=self.payload_root,
            registry_path=registry_path,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["registryKey"], "design-tools")
        self.assertTrue((self.generated_dir / "benchmark-request.json").exists())
        self.assertTrue((self.generated_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.generated_dir / "viral-analysis.md").exists())

    def test_prepare_benchmark_source_for_generated_dir_prefers_payload_source_path(self) -> None:
        raw_source_path = self.root / "payload-source.json"
        raw_source_path.write_text(
            json.dumps(
                [
                    {
                        "platform": "wechat",
                        "title": "Do not buy tools that cannot ship",
                        "url": "https://example.com/wechat-1",
                        "summary": "A method guide for reducing publish friction.",
                        "views": 1200,
                        "likes": 42,
                        "comments": 8,
                        "favorites": 11,
                        "shares": 2,
                        "author": "Editor Board",
                        "publishedAt": "2026-06-14T09:00:00+08:00",
                        "tags": ["mistake", "guide"],
                        "topic": "ai_tools",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = json.loads(self.payload_path.read_text(encoding="utf-8"))
        payload["benchmarkSourcePath"] = str(raw_source_path)
        payload["benchmarkPlatform"] = "wechat"
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        registry_path = self.config_dir / "benchmark_source_registry.json"
        registry_path.write_text(
            json.dumps({"schemaVersion": 1, "sources": {}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result = prepare_benchmark_source_for_generated_dir(
            self.generated_dir,
            payload_root=self.payload_root,
            registry_path=registry_path,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["sourceKind"], "payload")
        self.assertTrue((self.generated_dir / "benchmark-request.json").exists())
        self.assertTrue((self.generated_dir / "benchmark-records.jsonl").exists())

    def test_latest_generated_article_dir_prefers_directory_with_matching_payload(self) -> None:
        newer_demo_dir = self.payload_root / "generated" / "demo-only"
        newer_demo_dir.mkdir(parents=True, exist_ok=True)

        selected = latest_generated_article_dir(
            generated_root=self.payload_root / "generated",
            payload_root=self.payload_root,
        )

        self.assertEqual(selected, self.generated_dir)

    def test_repo_registry_covers_phase_one_domain_ids_and_aliases(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        registry_path = repo_root / "config" / "benchmark_source_registry.json"
        domains_path = repo_root / "config" / "content_domains.json"
        registry = load_benchmark_registry(registry_path)
        domains = json.loads(domains_path.read_text(encoding="utf-8"))

        expected_tokens = [
            "ai_tools",
            "ai-tool",
            "ai-tools",
            "design-tools",
            "agent-tools",
            "efficiency_tools",
            "workflow-shift",
            "approval-first",
            "shared-agents",
            "digital_product_usage",
            "digital-products",
            "product-usage",
            "light_tech_science",
            "google-io-agentic",
            "google-search-ai",
            "video-platform-ai-policy",
        ]
        self.assertEqual(set(domains["domains"].keys()), {
            "ai_tools",
            "efficiency_tools",
            "digital_product_usage",
            "light_tech_science",
        })

        for token in expected_tokens:
            with self.subTest(token=token):
                key, request = resolve_registry_request(
                    {
                        "title": "demo",
                        "summary": "demo",
                        "article_blocks": [],
                        "domain": token,
                    },
                    registry,
                    registry_path,
                )
                self.assertIsNotNone(key)
                self.assertIsInstance(request, dict)

    def test_repo_registry_does_not_share_one_input_path_across_different_queries(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        registry_path = repo_root / "config" / "benchmark_source_registry.json"
        registry = load_benchmark_registry(registry_path)

        by_path: dict[str, set[str]] = {}
        for meta in registry.get("sources", {}).values():
            input_path = str(meta.get("inputPath") or "").strip()
            query = str(meta.get("query") or "").strip()
            by_path.setdefault(input_path, set()).add(query)

        conflicting = {path: queries for path, queries in by_path.items() if len(queries) > 1}
        self.assertEqual(conflicting, {})

    def test_build_brief_persists_registry_audit_in_state(self) -> None:
        brief, state = build_brief(
            readiness=[],
            metrics_rows=[],
            manifest={"title": "demo", "sourceCount": 1},
            latest_article_dir=self.generated_dir,
            title_variants={},
            xhs_login_payload=None,
            benchmark_source={"status": "completed"},
            benchmark_refresh={"status": "ok", "refreshedCount": 2, "failedCount": 0},
            benchmark_registry_audit={
                "status": "ok",
                "summary": {
                    "tokenCount": 16,
                    "coveredTokenCount": 16,
                    "missingTokenCount": 0,
                    "missingSourcePathCount": 0,
                },
            },
        )

        self.assertIn("benchmarkRegistryAudit", state)
        self.assertEqual(state["benchmarkRegistryAudit"]["status"], "ok")
        self.assertIn("benchmarkRefresh", state)
        self.assertEqual(state["benchmarkRefresh"]["refreshedCount"], 2)
        self.assertIn("registry", brief.lower())

    def test_build_brief_includes_registry_health_counts(self) -> None:
        brief, _ = build_brief(
            readiness=[],
            metrics_rows=[],
            manifest={"title": "demo", "sourceCount": 1},
            latest_article_dir=self.generated_dir,
            title_variants={},
            xhs_login_payload=None,
            benchmark_source={"status": "completed"},
            benchmark_refresh={"status": "ok", "refreshedCount": 2, "failedCount": 1},
            benchmark_registry_audit={
                "status": "warning",
                "summary": {
                    "tokenCount": 16,
                    "coveredTokenCount": 16,
                    "missingTokenCount": 0,
                    "missingSourcePathCount": 0,
                    "emptySourcePathCount": 2,
                    "staleSourcePathCount": 3,
                },
            },
        )

        self.assertIn("empty=2", brief)
        self.assertIn("stale=3", brief)
        self.assertIn("refreshed=2", brief)
        self.assertIn("failed=1", brief)

    def test_build_run_summary_includes_registry_audit(self) -> None:
        summary = build_run_summary(
            brief_path=self.root / "brief.md",
            state_path=self.root / "state.json",
            readiness_path=self.root / "readiness.md",
            report_path=self.root / "report.md",
            metrics_path=self.root / "metrics.csv",
            xhs_probe_path=self.root / "xhs.json",
            latest_article_dir=self.generated_dir,
            benchmark_source={"status": "completed"},
            benchmark_refresh={"status": "ok", "refreshedCount": 2},
            benchmark_registry_audit={"status": "ok"},
            xhs_login_prepared=False,
        )

        self.assertIn("benchmarkRegistryAudit", summary)
        self.assertEqual(summary["benchmarkRegistryAudit"]["status"], "ok")
        self.assertIn("benchmarkRefresh", summary)
        self.assertEqual(summary["benchmarkRefresh"]["refreshedCount"], 2)

    def test_refresh_benchmark_registry_if_needed_calls_refresher_for_stale_sources(self) -> None:
        seen: dict[str, object] = {}

        def refresher(*, registry_path: Path, audit: dict[str, object]) -> dict[str, object]:
            seen["registry_path"] = registry_path
            seen["audit"] = audit
            return {"status": "ok", "refreshedCount": 1}

        result = refresh_benchmark_registry_if_needed(
            {"status": "warning", "staleSourcePaths": [{"registryKey": "design-tools"}]},
            registry_path=self.config_dir / "benchmark_source_registry.json",
            refresher=refresher,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["refreshedCount"], 1)
        self.assertEqual(seen["registry_path"], self.config_dir / "benchmark_source_registry.json")

    def test_refresh_benchmark_registry_if_needed_skips_ok_audit(self) -> None:
        result = refresh_benchmark_registry_if_needed(
            {"status": "ok", "staleSourcePaths": [], "missingSourcePaths": [], "emptySourcePaths": []},
            registry_path=self.config_dir / "benchmark_source_registry.json",
            refresher=lambda **_: {"status": "ok", "refreshedCount": 99},
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
