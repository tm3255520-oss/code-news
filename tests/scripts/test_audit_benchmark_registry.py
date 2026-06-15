import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.audit_benchmark_registry import audit_benchmark_registry


class AuditBenchmarkRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_dir = self.root / "config"
        self.data_dir = self.root / "data"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_audit_reports_ok_when_all_phase_tokens_resolve_and_sources_exist(self) -> None:
        source_path = self.data_dir / "records.json"
        source_path.write_text(json.dumps([{"title": "demo"}], ensure_ascii=False), encoding="utf-8")
        (self.config_dir / "content_domains.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "domains": {
                        "ai_tools": {
                            "aliases": ["design-tools", "agent-tools"],
                            "keywords": ["AI工具"],
                        },
                        "efficiency_tools": {
                            "aliases": ["workflow-shift"],
                            "keywords": ["工作流"],
                        },
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.config_dir / "benchmark_source_registry.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "design-tools": {
                            "aliases": ["ai_tools", "agent-tools"],
                            "inputPath": "../data/records.json",
                        },
                        "workflow-shift": {
                            "aliases": ["efficiency_tools"],
                            "inputPath": "../data/records.json",
                        },
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = audit_benchmark_registry(
            registry_path=self.config_dir / "benchmark_source_registry.json",
            domains_path=self.config_dir / "content_domains.json",
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["missingTokens"], [])
        self.assertEqual(result["missingSourcePaths"], [])
        self.assertEqual(result["emptySourcePaths"], [])
        self.assertEqual(result["staleSourcePaths"], [])
        self.assertGreaterEqual(len(result["coverage"]), 4)

    def test_audit_reports_missing_tokens_and_missing_source_paths(self) -> None:
        (self.config_dir / "content_domains.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "domains": {
                        "digital_product_usage": {
                            "aliases": ["digital-products", "product-usage"],
                            "keywords": ["订阅"],
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.config_dir / "benchmark_source_registry.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "ai-subscriptions": {
                            "aliases": ["digital_product_usage"],
                            "inputPath": "../data/missing.json",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = audit_benchmark_registry(
            registry_path=self.config_dir / "benchmark_source_registry.json",
            domains_path=self.config_dir / "content_domains.json",
        )

        self.assertEqual(result["status"], "warning")
        self.assertIn("digital-products", result["missingTokens"])
        self.assertIn("product-usage", result["missingTokens"])
        self.assertEqual(len(result["missingSourcePaths"]), 1)
        self.assertEqual(result["missingSourcePaths"][0]["registryKey"], "ai-subscriptions")

    def test_audit_reports_empty_and_stale_source_paths(self) -> None:
        source_path = self.data_dir / "stale-empty.json"
        source_path.write_text("[]", encoding="utf-8")
        os.utime(source_path, (1, 1))
        (self.config_dir / "content_domains.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "domains": {
                        "ai_tools": {
                            "aliases": ["design-tools"],
                            "keywords": ["AI工具"],
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.config_dir / "benchmark_source_registry.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "design-tools": {
                            "aliases": ["ai_tools"],
                            "inputPath": "../data/stale-empty.json",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = audit_benchmark_registry(
            registry_path=self.config_dir / "benchmark_source_registry.json",
            domains_path=self.config_dir / "content_domains.json",
            max_source_age_days=7,
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(len(result["emptySourcePaths"]), 1)
        self.assertEqual(result["emptySourcePaths"][0]["registryKey"], "design-tools")
        self.assertEqual(len(result["staleSourcePaths"]), 1)
        self.assertEqual(result["staleSourcePaths"][0]["registryKey"], "design-tools")
        self.assertEqual(result["summary"]["emptySourcePathCount"], 1)
        self.assertEqual(result["summary"]["staleSourcePathCount"], 1)
        self.assertEqual(result["coverage"][0]["recordCount"], 0)

    def test_audit_treats_empty_search_envelope_as_empty_source(self) -> None:
        source_path = self.data_dir / "search-envelope.json"
        source_path.write_text(
            json.dumps({"query": "AI", "total": 0, "articles": []}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.config_dir / "content_domains.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "domains": {
                        "light_tech_science": {
                            "aliases": ["google-search-ai"],
                            "keywords": ["Google"],
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (self.config_dir / "benchmark_source_registry.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sources": {
                        "google-search-ai": {
                            "aliases": ["light_tech_science"],
                            "inputPath": "../data/search-envelope.json",
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = audit_benchmark_registry(
            registry_path=self.config_dir / "benchmark_source_registry.json",
            domains_path=self.config_dir / "content_domains.json",
            max_source_age_days=365,
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["summary"]["emptySourcePathCount"], 1)
        self.assertEqual(result["coverage"][0]["recordCount"], 0)
        self.assertTrue(result["coverage"][0]["sourceIsEmpty"])


if __name__ == "__main__":
    unittest.main()
