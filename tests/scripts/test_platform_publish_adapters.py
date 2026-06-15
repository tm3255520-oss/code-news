import unittest

from scripts.platform_publish_adapters import (
    map_toutiao_result,
    map_wechat_result,
    should_skip_platform,
)


class PlatformPublishAdapterTests(unittest.TestCase):
    def test_should_skip_when_platform_already_verified(self) -> None:
        state = {"platforms": {"toutiao": {"status": "published_verified"}}}
        self.assertTrue(should_skip_platform(state, "toutiao"))

    def test_toutiao_submitted_plus_remote_list_hit_becomes_published_verified(self) -> None:
        record = {"status": "submitted", "pageUrl": "https://www.toutiao.com/item/1/"}
        verification = {"hasTitleMatch": True, "checkedAt": "2026-06-09T12:00:00+08:00"}
        mapped = map_toutiao_result(record, verification)
        self.assertEqual(mapped["status"], "published_verified")
        self.assertEqual(mapped["verificationSource"], "article_list_check")

    def test_toutiao_remote_list_miss_becomes_publish_failed(self) -> None:
        verification = {
            "hasTitleMatch": False,
            "checkedAt": "2026-06-12T22:38:00+08:00",
            "pageUrl": "https://mp.toutiao.com/profile_v4/graphic/articles",
        }
        mapped = map_toutiao_result(None, verification)
        self.assertEqual(mapped["status"], "publish_failed")
        self.assertEqual(mapped["verificationSource"], "article_list_check")
        self.assertEqual(mapped["error"], "toutiao publish verification failed")

    def test_wechat_awaiting_verification_does_not_allow_republish(self) -> None:
        record = {"status": "awaiting_wechat_verification", "pageUrl": "https://mp.weixin.qq.com/"}
        mapped = map_wechat_result(record)
        self.assertEqual(mapped["status"], "awaiting_verification")
        self.assertEqual(mapped["verificationSource"], "local_publish_record")


if __name__ == "__main__":
    unittest.main()
