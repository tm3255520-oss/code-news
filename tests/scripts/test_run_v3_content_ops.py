import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_v3_content_ops import run_v3_prepublish


class RunV3ContentOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_dir = self.root / ".tmp"
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.config_dir = self.root / "config"
        self.history_path = self.root / ".tmp" / "v3" / "image-history.json"

        self.payload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "slug": "demo-slug",
            "title": "AI工具怎么选，先看结果能不能继续改",
            "summary": "这篇内容聚焦 AI 工具选择，核心是用更少步骤减少返工，提升发布效率。",
            "article_blocks": [
                "一、为什么先看结果能不能继续改",
                "第一张图好看，不代表整条链高效，关键是后面能不能少返工。",
                "二、研究到发布之间最容易卡住哪里",
                "通常卡在改稿、换尺寸和发出去，这些步骤最吃时间。",
                "三、怎么判断工具值不值得长期用",
                "先看上下文、再看资产、再看发布流程，这样更适合团队长期使用。",
            ],
            "body_images": [
                {"file_name": "body-01.png"},
                {"file_name": "body-02.png"},
                {"file_name": "body-03.png"},
            ],
        }
        self.payload_path = self.payload_dir / "toutiao_payload_demo.json"
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        (self.generated_dir / "body-01.png").write_bytes(b"body-1")
        (self.generated_dir / "body-02.png").write_bytes(b"body-2")
        (self.generated_dir / "body-03.png").write_bytes(b"body-3")
        (self.generated_dir / "title-variants.md").write_text(
            "# 平台标题\n\n## 今日头条\n短标题\n\n## 微信公众号\n长标题\n\n## 知乎\n问题标题\n",
            encoding="utf-8",
        )

        tool_registry = {
            "schemaVersion": 1,
            "interfaces": {
                "monitor_skill": {"primary": "dbs-benchmark", "status": "active"},
                "writer_skill": {"primary": "content-research-writer", "status": "active"},
                "humanizer_skill": {"primary": "humanizer-zh", "status": "active"},
                "illustration_skill": {"primary": "ian-xiaohei-illustrations", "status": "active"},
                "cover_skill": {"primary": "guizang-social-card-skill", "status": "active"},
                "publisher_skill": {
                    "primary": "scripts/run_three_platform_pipeline.py",
                    "status": "active",
                    "formalPublishEnabled": False,
                },
                "codex_api_mcp": {"status": "planned"},
                "web_scraper_mcp": {"status": "planned"},
                "xhs_placeholder_publish": {
                    "primary": "xhs-publish",
                    "status": "active",
                    "formalPublishEnabled": False,
                },
            }
        }
        domains = {
            "schemaVersion": 1,
            "domains": {
                "ai_tools": {
                    "displayName": "AI工具",
                    "aliases": ["design-tools"],
                    "keywords": ["AI工具", "Canva", "Figma", "ChatGPT"],
                }
            },
        }
        strategy = {
            "schemaVersion": 1,
            "historyWindow": 6,
            "avoidRepeatWindow": 2,
            "coverFamilies": {
                "question_lead": {"renderer": "imagegen"},
                "data_brief": {"renderer": "guizang-social-card-skill"},
            },
            "bodyFamilies": {
                "comparison_board": {"renderer": "imagegen"},
                "tool_stack_map": {"renderer": "imagegen"},
                "workflow_whiteboard": {"renderer": "ian-xiaohei-illustrations"},
                "myth_vs_fact": {"renderer": "imagegen"},
            },
            "palettes": {
                "copper_teal": {},
                "coral_slate": {},
                "amber_ink": {},
            },
            "domainPreferences": {
                "ai_tools": {
                    "coverFamilies": ["question_lead", "data_brief"],
                    "bodyFamilies": [
                        "comparison_board",
                        "tool_stack_map",
                        "workflow_whiteboard",
                        "myth_vs_fact",
                    ],
                    "palettes": ["copper_teal", "coral_slate", "amber_ink"],
                }
            },
        }
        (self.config_dir / "tool_registry.json").write_text(
            json.dumps(tool_registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.config_dir / "content_domains.json").write_text(
            json.dumps(domains, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.config_dir / "image_strategy.json").write_text(
            json.dumps(strategy, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_v3_prepublish_writes_required_artifacts(self) -> None:
        summary = run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )
        self.assertEqual(summary["mode"], "v3-prepublish")
        self.assertTrue((self.generated_dir / "image-plan.json").exists())
        self.assertTrue((self.generated_dir / "skill-packets.json").exists())
        self.assertTrue((self.generated_dir / "publish-preview.json").exists())
        self.assertFalse(summary["formalPublishEnabled"])

    def test_run_v3_prepublish_updates_pipeline_state_with_v3_and_xhs_placeholder(self) -> None:
        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )
        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertIn("v3", state)
        self.assertIn("xiaohongshu", state["platforms"])
        self.assertEqual(state["platforms"]["xiaohongshu"]["status"], "placeholder_ready")
        self.assertFalse(state["v3"]["formalPublishEnabled"])

    def test_run_v3_prepublish_writes_operator_checklist_for_manual_handoff(self) -> None:
        summary = run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )

        checklist_path = self.generated_dir / "operator-checklist.md"
        self.assertTrue(checklist_path.exists())
        checklist = checklist_path.read_text(encoding="utf-8")
        self.assertIn("# 用户配合清单", checklist)
        self.assertIn("image-plan.json", checklist)
        self.assertIn("publish-preview.json", checklist)
        self.assertIn("skill-packets.json", checklist)
        self.assertEqual(Path(summary["operatorChecklistPath"]).resolve(), checklist_path.resolve())

        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(state["v3"]["operatorChecklistPath"]).resolve(), checklist_path.resolve())

    def test_run_v3_prepublish_persists_image_history(self) -> None:
        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )
        history = json.loads(self.history_path.read_text(encoding="utf-8"))
        self.assertEqual(history[0]["slug"], "demo-slug")
        self.assertIn("coverFamily", history[0])
        self.assertEqual(len(history[0]["bodyFamilies"]), 3)

    def test_run_v3_prepublish_blocks_when_assets_are_missing(self) -> None:
        (self.generated_dir / "cover.png").unlink()
        result = run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )
        preview = json.loads((self.generated_dir / "publish-preview.json").read_text(encoding="utf-8"))
        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(preview["platforms"]["toutiao"]["status"], "blocked_by_asset_gate")
        self.assertEqual(preview["platforms"]["xiaohongshu"]["status"], "placeholder_blocked")
        self.assertEqual(state["v3"]["assetGate"]["status"], "blocked")
        self.assertFalse(result["formalPublishEnabled"])

    def test_run_v3_prepublish_resets_stale_platform_failures_without_publish_evidence(self) -> None:
        stale_state = {
            "schemaVersion": 1,
            "slug": "demo-slug",
            "fingerprint": "x",
            "title": "old",
            "createdAt": "2026-06-14T09:00:00+08:00",
            "updatedAt": "2026-06-14T09:00:00+08:00",
            "qualityGate": {},
            "assets": {"coverExists": True, "bodyImageCount": 3, "missingFiles": []},
            "platforms": {
                "toutiao": {"status": "awaiting_verification", "attemptCount": 0, "publishedAt": None, "url": None, "titleUsed": None, "verificationSource": "legacy", "error": None},
                "zhihu": {"status": "publish_failed", "attemptCount": 0, "publishedAt": None, "url": None, "titleUsed": None, "verificationSource": "legacy", "error": "missing"},
                "wechat": {"status": "publish_failed", "attemptCount": 0, "publishedAt": None, "url": None, "titleUsed": None, "verificationSource": "legacy", "error": "missing"},
                "xiaohongshu": {"status": "ready", "attemptCount": 0, "publishedAt": None, "url": None, "titleUsed": None, "verificationSource": "legacy", "error": None},
            },
        }
        (self.generated_dir / "pipeline-state.json").write_text(
            json.dumps(stale_state, ensure_ascii=False),
            encoding="utf-8",
        )

        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )
        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["platforms"]["toutiao"]["status"], "ready")
        self.assertEqual(state["platforms"]["zhihu"]["status"], "ready")
        self.assertEqual(state["platforms"]["wechat"]["status"], "ready")

    def test_run_v3_prepublish_runs_signal_pipeline_when_benchmark_records_exist(self) -> None:
        records_path = self.generated_dir / "benchmark-records.jsonl"
        records = [
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
            }
        ]
        with records_path.open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )

        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertTrue((self.generated_dir / "benchmark-monitor.md").exists())
        self.assertTrue((self.generated_dir / "viral-analysis.md").exists())
        self.assertTrue((self.generated_dir / "rewrite-plan.md").exists())
        self.assertEqual(state["v3"]["signalPipeline"]["status"], "completed")
        self.assertEqual(Path(state["v3"]["signalPipeline"]["recordsPath"]).resolve(), records_path.resolve())

    def test_run_v3_prepublish_marks_signal_pipeline_pending_when_records_are_missing(self) -> None:
        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )

        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["v3"]["signalPipeline"]["status"], "pending_source")
        self.assertFalse((self.generated_dir / "viral-analysis.md").exists())
        self.assertFalse((self.generated_dir / "rewrite-plan.md").exists())

    def test_run_v3_prepublish_builds_records_from_payload_benchmark_source_path(self) -> None:
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
        payload = json.loads(self.payload_path.read_text(encoding="utf-8"))
        payload["benchmarkSourcePath"] = str(raw_source_path)
        payload["benchmarkPlatform"] = "zhihu"
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        run_v3_prepublish(
            self.payload_path,
            config_dir=self.config_dir,
            history_path=self.history_path,
            min_score=0,
        )

        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertTrue((self.generated_dir / "benchmark-records.jsonl").exists())
        self.assertTrue((self.generated_dir / "benchmark-request.json").exists())
        self.assertEqual(state["v3"]["signalPipeline"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
