import json
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline_state import (
    build_fingerprint,
    initialize_pipeline_state,
    pipeline_state_path,
    set_platform_state,
    summarize_assets,
)


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.payload_path = self.root / ".tmp" / "toutiao_payload_demo.json"
        self.generated_dir = self.root / ".tmp" / "generated" / "demo-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path.parent.mkdir(parents=True, exist_ok=True)
        self.payload = {
            "slug": "demo-slug",
            "title": "A short title",
            "summary": "Concrete summary",
            "article_blocks": ["first block", "second block"],
            "body_images": [{"file_name": "body-01.png"}],
        }
        self.payload_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_fingerprint_ignores_whitespace_noise(self) -> None:
        altered = {
            **self.payload,
            "summary": "Concrete   summary",
            "article_blocks": ["first block", "second   block"],
        }
        self.assertEqual(build_fingerprint(self.payload), build_fingerprint(altered))

    def test_summarize_assets_reports_missing_body_images(self) -> None:
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        asset_summary = summarize_assets(self.generated_dir, self.payload)
        self.assertEqual(asset_summary["coverExists"], True)
        self.assertEqual(asset_summary["bodyImageCount"], 0)
        self.assertIn("body-01.png", " ".join(asset_summary["missingFiles"]))

    def test_initialize_pipeline_state_contains_all_platforms(self) -> None:
        state = initialize_pipeline_state(self.payload_path, self.payload)
        self.assertEqual(state["slug"], "demo-slug")
        self.assertEqual(state["platforms"]["toutiao"]["status"], "ready")
        self.assertEqual(state["platforms"]["zhihu"]["status"], "ready")
        self.assertEqual(state["platforms"]["wechat"]["status"], "ready")

    def test_set_platform_state_updates_timestamp_and_error(self) -> None:
        state = initialize_pipeline_state(self.payload_path, self.payload)
        updated = set_platform_state(
            state,
            "wechat",
            status="awaiting_verification",
            error="wechat qr required",
        )
        self.assertEqual(updated["platforms"]["wechat"]["status"], "awaiting_verification")
        self.assertEqual(updated["platforms"]["wechat"]["error"], "wechat qr required")
        self.assertIsNotNone(updated["updatedAt"])

    def test_pipeline_state_path_lives_under_generated_slug_dir(self) -> None:
        state_path = pipeline_state_path(self.payload_path, self.payload)
        self.assertEqual(state_path, self.generated_dir / "pipeline-state.json")


if __name__ == "__main__":
    unittest.main()
