import json
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_legacy_data import migrate_legacy_data


class MigrateLegacyDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.tmp_dir = self.root / ".tmp"
        self.generated_dir = self.tmp_dir / "generated" / "legacy-slug"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "slug": "legacy-slug",
            "title": "老内容标题",
            "summary": "历史内容摘要",
            "article_blocks": ["一、旧内容", "二、旧内容延展"],
            "body_images": [{"file_name": "body-01.png"}],
        }
        (self.tmp_dir / "toutiao_payload_legacy.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.generated_dir / "cover.png").write_bytes(b"cover")
        (self.generated_dir / "body-01.png").write_bytes(b"body")
        (self.generated_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "title": "老内容标题",
                    "summary": "历史内容摘要",
                    "coverPngPath": str(self.generated_dir / "cover.png"),
                    "bodyImages": [
                        {"pngPath": str(self.generated_dir / "body-01.png")}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp_dir / "toutiao-publish-records.json").write_text(
            json.dumps(
                [
                    {
                        "slug": "legacy-slug",
                        "title": "老内容标题",
                        "status": "submitted",
                        "submittedAt": "2026-06-10T20:00:00+08:00",
                        "pageUrl": "https://toutiao.example/item/1",
                        "verificationSource": "article_list_check",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp_dir / "zhihu-publish-records.json").write_text(
            json.dumps(
                [
                    {
                        "slug": "legacy-slug",
                        "title": "老内容标题",
                        "publishedAt": "2026-06-10T21:00:00+08:00",
                        "url": "https://zhihu.example/p/1",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp_dir / "wechat-publish-records.json").write_text(
            json.dumps(
                [
                    {
                        "slug": "legacy-slug",
                        "title": "老内容标题",
                        "status": "published",
                        "publishedAt": "2026-06-10T22:00:00+08:00",
                        "pageUrl": "https://mp.weixin.qq.com/s/example",
                        "source": "local_publish_record",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.tmp_dir / "xhs-publish-records.json").write_text(
            json.dumps(
                [
                    {
                        "slug": "legacy-slug",
                        "title": "老内容标题",
                        "publishedAt": "2026-06-11T09:00:00+08:00",
                        "url": "https://xhslink.com/example",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.empty_generated_dir = self.tmp_dir / "generated" / "fresh-slug"
        self.empty_generated_dir.mkdir(parents=True, exist_ok=True)
        (self.empty_generated_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "title": "未发过的新稿",
                    "summary": "还没有任何平台发布记录",
                    "coverPngPath": "",
                    "bodyImages": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_migrate_legacy_data_backfills_missing_pipeline_state(self) -> None:
        result = migrate_legacy_data(self.tmp_dir)
        state_path = self.generated_dir / "pipeline-state.json"
        self.assertTrue(state_path.exists())
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["slug"], "legacy-slug")
        self.assertEqual(result["createdStateCount"], 2)

    def test_migrate_legacy_data_reconciles_platform_statuses(self) -> None:
        migrate_legacy_data(self.tmp_dir)
        state = json.loads((self.generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["platforms"]["toutiao"]["status"], "awaiting_verification")
        self.assertEqual(state["platforms"]["zhihu"]["status"], "published_verified")
        self.assertEqual(state["platforms"]["wechat"]["status"], "published_verified")
        self.assertEqual(state["platforms"]["xiaohongshu"]["status"], "published_verified")

    def test_migrate_legacy_data_writes_index_summary(self) -> None:
        result = migrate_legacy_data(self.tmp_dir)
        index_path = self.tmp_dir / "v3" / "legacy-index.json"
        self.assertTrue(index_path.exists())
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual({item["slug"] for item in index["items"]}, {"legacy-slug", "fresh-slug"})
        self.assertEqual(result["indexPath"], str(index_path))

    def test_migrate_legacy_data_keeps_unpublished_content_as_ready(self) -> None:
        migrate_legacy_data(self.tmp_dir)
        state = json.loads((self.empty_generated_dir / "pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["platforms"]["toutiao"]["status"], "ready")
        self.assertEqual(state["platforms"]["zhihu"]["status"], "ready")
        self.assertEqual(state["platforms"]["wechat"]["status"], "ready")
        self.assertEqual(state["platforms"]["xiaohongshu"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
