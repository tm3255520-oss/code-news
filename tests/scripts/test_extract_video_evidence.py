"""extract_video_evidence.py 单元测试（纯函数 + mock 网络解析）。"""
import json
import os
import sys
import unittest
from unittest import mock

_SCRIPTS = os.path.join(
    os.path.dirname(__file__), "..", "..", ".agents", "skills",
    "viral-video-breakdown", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))

import extract_video_evidence as ev  # noqa: E402


class TestPureFunctions(unittest.TestCase):
    def test_detect_platform(self):
        self.assertEqual(ev.detect_platform("https://www.toutiao.com/video/123/"), "toutiao")
        self.assertEqual(ev.detect_platform("https://www.ixigua.com/123"), "toutiao")
        self.assertEqual(ev.detect_platform("https://www.bilibili.com/video/BV1xx/"), "bilibili")
        self.assertEqual(ev.detect_platform("https://www.douyin.com/video/1"), "douyin")
        self.assertEqual(ev.detect_platform("https://foo.com/x"), "unknown")

    def test_load_config_defaults(self):
        cfg = ev.load_config(None)
        self.assertIn("extraction", cfg)
        self.assertIn("whisper", cfg)
        self.assertEqual(cfg["extraction"]["frame_interval"], 3)

    def test_load_config_env_override(self):
        with mock.patch.dict(os.environ, {"TESSDATA_PREFIX": "/custom/tess"}):
            cfg = ev.load_config(None)
            self.assertEqual(cfg["paths"]["tessdata_prefix"], "/custom/tess")


# ---------------- 头条移动页 articleInfo 解析（mock http_get） ----------------
_TOUTIAO_HTML = (
    "<html><body>"
    "<script>%7B%22sessionConfig%22%3A%7B%7D%2C%22articleInfo%22%3A%7B%22title%22%3A%22%E6%B5%8B%E8%AF%95%22%2C"
    "%22videoPlayCount%22%3A78%2C%22commentCount%22%3A0%2C%22diggCount%22%3A0%2C%22publishTime%22%3A%221787600614%22%2C"
    "%22videoId%22%3A%22v01%22%2C%22mediaUser%22%3A%7B%22screenName%22%3A%22%E4%BD%9C%E8%80%85%22%7D%2C"
    "%22videoDuration%22%3A207%2C%22playAuthTokenV2%22%3A%22tok%22%7D%7D</script>"
    "</body></html>")


class TestToutiaoMeta(unittest.TestCase):
    @mock.patch.object(ev, "http_get", return_value=_TOUTIAO_HTML.encode("utf-8"))
    def test_fetch_toutiao_meta(self, mock_get):
        meta = ev.fetch_toutiao_meta("https://www.toutiao.com/video/123456/", ev.UA)
        self.assertEqual(meta["title"], "测试")
        self.assertEqual(meta["author"], "作者")
        self.assertEqual(meta["play_count"], 78)
        self.assertEqual(meta["video_id"], "v01")
        self.assertEqual(meta["duration_s"], 207)
        self.assertEqual(meta["publish_time"], "1787600614")


# ---------------- B站 view API 解析（mock http_get） ----------------
_BILI_VIEW = json.dumps({
    "code": 0,
    "data": {
        "bvid": "BV1TEST", "cid": 100, "title": "测试视频", "desc": "desc",
        "owner": {"name": "作者A", "mid": 123},
        "duration": 281, "pubdate": 1787000000, "pic": "http://pic",
        "stat": {"view": 1000, "reply": 10, "like": 50, "favorite": 20,
                 "coin": 5, "share": 3, "danmaku": 7},
    }}).encode("utf-8")

_BILI_PLAYURL = json.dumps({
    "code": 0,
    "data": {"dash": {
        "video": [{"id": 32, "height": 480, "width": 852, "codecs": "avc1.640033",
                   "baseUrl": "https://cdn/v.m4s"}],
        "audio": [{"id": 30216, "bandwidth": 65731, "baseUrl": "https://cdn/a.m4s"}],
    }}}).encode("utf-8")


class TestBiliMeta(unittest.TestCase):
    @mock.patch.object(ev, "http_get", return_value=_BILI_VIEW)
    def test_fetch_bili_meta(self, mock_get):
        meta = ev.fetch_bili_meta("https://www.bilibili.com/video/BV1TEST", ev.UA)
        self.assertEqual(meta["platform"], "bilibili")
        self.assertEqual(meta["bvid"], "BV1TEST")
        self.assertEqual(meta["cid"], 100)
        self.assertEqual(meta["title"], "测试视频")
        self.assertEqual(meta["play_count"], 1000)
        self.assertEqual(meta["comment_count"], 10)
        self.assertEqual(meta["digg_count"], 50)
        self.assertEqual(meta["coin_count"], 5)

    def test_fetch_bili_meta_no_bvid(self):
        with self.assertRaises(RuntimeError):
            ev.fetch_bili_meta("https://www.bilibili.com/video/notabvid", ev.UA)

    @mock.patch.object(ev, "http_get", return_value=_BILI_PLAYURL)
    def test_get_bili_streams(self, mock_get):
        vurl, aurl = ev.get_bili_streams("BV1TEST", 100, ev.UA)
        self.assertEqual(vurl, "https://cdn/v.m4s")
        self.assertEqual(aurl, "https://cdn/a.m4s")


if __name__ == "__main__":
    unittest.main()
