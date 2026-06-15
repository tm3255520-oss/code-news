import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from scripts.run_three_platform_pipeline import (
    choose_platform_title,
    load_title_variants,
    main,
    run_pipeline,
    run_preflight,
)


class PipelinePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_dir = self.root / ".tmp"
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path = self.payload_dir / "toutiao_payload_demo.json"
        self.payload = {
            "slug": "demo-slug",
            "title": "三步搭好内容发布流程",
            "summary": "这套方法能减少重复发布，适合先做三平台同步。",
            "article_blocks": ["先把状态写清楚。", "再按步骤做发布验证。"],
            "body_images": [{"file_name": "body-01.png"}],
        }
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        (self.generated_dir / "body-01.png").write_bytes(b"body")
        (self.generated_dir / "title-variants.md").write_text(
            "# 平台标题方案\n\n## 今日头条\n\n短标题\n\n## 微信公众号\n\n长标题版本\n\n## 知乎\n\n问句标题版本\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_title_variants_parses_platform_sections(self) -> None:
        variants = load_title_variants(self.generated_dir / "title-variants.md")
        self.assertEqual(variants["toutiao"][0], "短标题")
        self.assertEqual(variants["wechat"][0], "长标题版本")
        self.assertEqual(variants["zhihu"][0], "问句标题版本")

    def test_choose_platform_title_uses_platform_specific_variant(self) -> None:
        variants = {
            "toutiao": ["短标题"],
            "wechat": ["长标题版本"],
            "zhihu": ["问句标题版本"],
        }
        self.assertEqual(choose_platform_title("toutiao", variants, "Base title"), "短标题")
        self.assertEqual(choose_platform_title("wechat", variants, "Base title"), "长标题版本")
        self.assertEqual(choose_platform_title("zhihu", variants, "Base title"), "问句标题版本")

    def test_run_preflight_writes_pipeline_state_and_platform_payloads(self) -> None:
        result = run_preflight(self.payload_path, min_score=0)
        self.assertEqual(result["gate"]["status"], "passed")
        self.assertTrue(result["statePath"].exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "toutiao.json").exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "zhihu.json").exists())
        self.assertTrue((self.generated_dir / "platform-payloads" / "wechat.json").exists())

    def test_run_preflight_applies_platform_summary_and_opening_overrides(self) -> None:
        payload = dict(self.payload)
        payload["article_blocks"] = [
            "旧开头一。",
            "旧开头二。",
            "一、正文标题",
            "正文内容。",
        ]
        self.payload_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.generated_dir / "platform-copy.json").write_text(
            json.dumps(
                {
                    "toutiao": {
                        "summary": "早上打开电脑前，AI 已经先把日报和待跟进整理好了。",
                        "opening_blocks": [
                            "你早上打开电脑前，日报、分类和待跟进已经先跑完一轮了。",
                            "这才是这轮 AI 最该比的能力：不是更会答，而是能不能稳定接住一条流程。",
                        ],
                    },
                    "zhihu": {
                        "summary": "为什么说现在更有价值的 AI，不是更会回答，而是会自己跑流程？",
                        "opening_blocks": [
                            "如果一个 AI 每次都要等你开口，它更像一个高级搜索框。",
                            "如果它能按节奏自己整理、归类、提醒和回传，它才开始接近真正的工作伙伴。",
                        ],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        run_preflight(self.payload_path, min_score=0)

        toutiao_payload = json.loads(
            (self.generated_dir / "platform-payloads" / "toutiao.json").read_text(encoding="utf-8")
        )
        zhihu_payload = json.loads(
            (self.generated_dir / "platform-payloads" / "zhihu.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            toutiao_payload["summary"],
            "早上打开电脑前，AI 已经先把日报和待跟进整理好了。",
        )
        self.assertEqual(
            toutiao_payload["article_blocks"][:4],
            [
                "你早上打开电脑前，日报、分类和待跟进已经先跑完一轮了。",
                "这才是这轮 AI 最该比的能力：不是更会答，而是能不能稳定接住一条流程。",
                "一、正文标题",
                "正文内容。",
            ],
        )
        self.assertEqual(
            zhihu_payload["summary"],
            "为什么说现在更有价值的 AI，不是更会回答，而是会自己跑流程？",
        )
        self.assertEqual(
            zhihu_payload["article_blocks"][:2],
            [
                "如果一个 AI 每次都要等你开口，它更像一个高级搜索框。",
                "如果它能按节奏自己整理、归类、提醒和回传，它才开始接近真正的工作伙伴。",
            ],
        )

    @patch("scripts.run_three_platform_pipeline.subprocess.run")
    def test_run_pipeline_skips_verified_platform_and_runs_remaining_two(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '{"status":"published","pageUrl":"https://example.com"}'
        run_mock.return_value.stderr = ""

        state_path = self.generated_dir / "pipeline-state.json"
        state_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "slug": "demo-slug",
                    "fingerprint": "x",
                    "title": "Base title",
                    "createdAt": "2026-06-09T12:00:00+08:00",
                    "updatedAt": "2026-06-09T12:00:00+08:00",
                    "qualityGate": {"status": "passed", "score": 90, "failCount": 0, "warnCount": 0},
                    "assets": {"coverExists": True, "bodyImageCount": 1, "missingFiles": []},
                    "platforms": {
                        "toutiao": {"status": "published_verified"},
                        "zhihu": {"status": "ready"},
                        "wechat": {"status": "ready"},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = run_pipeline(self.payload_path, min_score=0)
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(result["platforms"]["toutiao"]["status"], "published_verified")

    @patch("scripts.run_three_platform_pipeline.run_pipeline")
    @patch("scripts.run_three_platform_pipeline.load_pipeline_state")
    @patch("scripts.run_three_platform_pipeline.run_preflight")
    def test_main_preflight_only_avoids_publish(
        self,
        run_preflight_mock: MagicMock,
        load_pipeline_state_mock: MagicMock,
        run_pipeline_mock: MagicMock,
    ) -> None:
        run_preflight_mock.return_value = {
            "topic": "design-tools",
            "gate": {"status": "passed", "score": 92, "failCount": 0, "warnCount": 1},
            "statePath": self.generated_dir / "pipeline-state.json",
            "platformPayloads": {
                "toutiao": self.generated_dir / "platform-payloads" / "toutiao.json",
                "zhihu": self.generated_dir / "platform-payloads" / "zhihu.json",
                "wechat": self.generated_dir / "platform-payloads" / "wechat.json",
            },
        }
        load_pipeline_state_mock.return_value = {
            "assets": {"coverExists": True, "bodyImageCount": 1, "missingFiles": []},
            "qualityGate": {"status": "passed"},
        }

        with patch(
            "sys.argv",
            ["run_three_platform_pipeline.py", str(self.payload_path), "--preflight-only"],
        ):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        run_preflight_mock.assert_called_once()
        run_pipeline_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
