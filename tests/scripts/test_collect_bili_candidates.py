"""collect_bili_candidates.py 单元测试（纯函数 + config）。"""
import os
import sys
import unittest

_SCRIPTS = os.path.join(
    os.path.dirname(__file__), "..", "..", ".agents", "skills",
    "viral-video-breakdown", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))

import collect_bili_candidates as cbc  # noqa: E402


class TestCollectPureFunctions(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(cbc.parse_duration("04:41"), 281)
        self.assertEqual(cbc.parse_duration("1:00:00"), 3600)
        self.assertEqual(cbc.parse_duration(160), 160)
        self.assertEqual(cbc.parse_duration("x"), 0)

    def test_clean_title(self):
        self.assertEqual(cbc.clean_title("Deep<em class=\"keyword\">Seek</em>"), "DeepSeek")

    def test_is_dsh_title(self):
        self.assertTrue(cbc.is_dsh_title("DeepSeek Harness 首发实测"))
        self.assertTrue(cbc.is_dsh_title("dsh 插件教程"))
        self.assertTrue(cbc.is_dsh_title("DSH插件圈大地震"))
        self.assertTrue(cbc.is_dsh_title("deepseek-harness 入门"))
        self.assertFalse(cbc.is_dsh_title("Python 教程"))

    def test_compute_rates(self):
        c = {"view": 1000, "like": 100, "reply": 10, "favorite": 50, "coin": 5}
        out = cbc.compute_rates(dict(c))
        self.assertEqual(out["fav_rate"], 0.05)
        self.assertEqual(out["like_rate"], 0.10)
        self.assertEqual(out["coin_rate"], 0.005)
        self.assertEqual(out["reply_rate"], 0.01)
        self.assertIsNone(out["rel_to_median"])

    def test_compute_rates_zero_view(self):
        c = {"view": 0, "like": 0, "reply": 0, "favorite": 0, "coin": 0}
        out = cbc.compute_rates(c)
        self.assertEqual(out["fav_rate"], 0.0)

    def test_load_config_defaults(self):
        cfg = cbc.load_config(None)["bili"]
        self.assertIn("keywords", cfg)
        self.assertGreaterEqual(cfg["request_interval_s"], 0)
        self.assertGreaterEqual(cfg["max_stat_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
