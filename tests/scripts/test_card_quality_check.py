# -*- coding: utf-8 -*-
"""test_card_quality_check.py — 质量自检线的回归门

自检线的产出会被当成「改动是否有效」的判据，所以它自己必须可验证。
固化三类真出过问题的地方：

1. 画幅适配：声明（deck.format）与实际（成片分辨率）必须自洽；
   竖屏平台配横屏成片必须判硬失败 —— 这是产线里唯一「不用花钱检测就能确定错」的判据。
2. 读数可信性：motion_check 的内容区裁切只按横屏 1440x1080 标定过，
   换画幅读数失真，必须标记作废，而不是照报一个错数字。
3. 时间轴与文本口径：卡片缝隙/重叠必须被拦住；字数口径（不含标点）、
   Hook 窗口（按字幕起始时间落窗）必须可复现。

跑真实基准（video-line/acceptance/）时走 build_metrics 直调 + 合成探针，
不拉 ffmpeg —— 保持整个测试套件秒级。

用法（仓库根目录）：
    python -m unittest tests.scripts.test_card_quality_check -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import card_quality_check as Q  # noqa: E402

ACCEPT = ROOT / "video-line" / "acceptance"


def probe(w: int, h: int, dur: float = 27.8) -> dict:
    return {"width": w, "height": h, "duration_s": dur}


def cap(text: str, start: float, dur: float = 1.2) -> dict:
    return {"text": text, "start": start, "duration": dur}


def deck_of(cards: list, fmt: str | None = None) -> dict:
    d = {"series": "T", "episode": "S1", "style": "grid-dark", "cards": cards}
    if fmt:
        d["format"] = fmt
    return d


def card(title: str, start: float, dur: float, units=None, caps=None,
         motion: str = "SLAMS 标题") -> dict:
    return {
        "title": title, "start": start, "duration": dur, "step": "01 / 01",
        "motion": motion, "transition_in": "硬切", "transition_out": "硬切",
        "kicker": "01 · 测试", "units": units or [], "captions": caps or [],
    }


class CharCountTests(unittest.TestCase):
    def test_punct_excluded_from_char_count(self):
        no_punct, with_punct = Q.count_chars("很多人，还在比。")
        self.assertEqual(no_punct, 6)
        self.assertEqual(with_punct, 8)

    def test_whitespace_ignored(self):
        no_punct, _ = Q.count_chars("还在比\n哪个 AI")
        self.assertEqual(no_punct, 7)


class TimelineTests(unittest.TestCase):
    def test_gapless_timeline_reports_nothing(self):
        tl = Q.cards_timeline([card("A", 0.0, 2.0), card("B", 2.0, 3.0)])
        self.assertEqual(tl["gaps"], [])
        self.assertEqual(tl["overlaps"], [])
        self.assertEqual(tl["total_s"], 5.0)

    def test_gap_is_detected(self):
        tl = Q.cards_timeline([card("A", 0.0, 2.0), card("B", 2.5, 3.0)])
        self.assertEqual(len(tl["gaps"]), 1)
        self.assertAlmostEqual(tl["gaps"][0]["gap_s"], 0.5, places=3)

    def test_overlap_is_detected(self):
        tl = Q.cards_timeline([card("A", 0.0, 3.0), card("B", 2.5, 2.0)])
        self.assertEqual(len(tl["overlaps"]), 1)
        self.assertAlmostEqual(tl["overlaps"][0]["gap_s"], -0.5, places=3)


class MotionReadoutTests(unittest.TestCase):
    def test_readout_void_when_motion_check_cannot_run(self):
        """motion_check 没认出画幅 → 读数作废，不许照报。"""
        deck = deck_of([card("A", 0.0, 3.0)], fmt="vertical")
        m = Q.build_metrics(deck, None, probe(1080, 1920),
                            {"failed": True, "error": "不支持的分辨率"},
                            None)
        self.assertFalse(m["pacing"]["motion_reliable"])
        self.assertIsNone(m["pacing"]["still_ratio"])
        rows = Q.judge(m)
        self.assertEqual([r[2] for r in rows if r[1] == "静止帧占比"], ["未测"])
        self.assertTrue(any("motion_check 未跑成" in g for g in m["evidence_gaps"]))

    def test_readout_trusted_when_motion_check_names_the_format(self):
        """motion_check 认出画幅 → 读数可用，且把画幅与内容区记进来源。"""
        deck = deck_of([card("A", 0.0, 3.0)], fmt="vertical")
        m = Q.build_metrics(deck, None, probe(1080, 1920),
                            {"format": "vertical", "content_rect": [58, 126, 1022, 1482],
                             "still_ratio": 0.285, "longest_still_s": 2.1},
                            None)
        self.assertTrue(m["pacing"]["motion_reliable"])
        self.assertEqual(m["pacing"]["motion_format"], "vertical")
        rows = Q.judge(m)
        self.assertEqual([r[2] for r in rows if r[1] == "静止帧占比"], [0.285])
        self.assertTrue(any("画幅 vertical" in r[4] for r in rows))


class FormatGateTests(unittest.TestCase):
    def test_landscape_film_on_vertical_platform_is_hard_fail(self):
        deck = deck_of([card("A", 0.0, 3.0)])
        m = Q.build_metrics(deck, None, probe(1440, 1080), None, "视频号")
        self.assertTrue(m["format_consistent"])
        self.assertFalse(m["platform_fit"])
        self.assertTrue(any(r[4] == "硬失败" for r in Q.judge(m)))

    def test_vertical_film_on_vertical_platform_passes(self):
        deck = deck_of([card("A", 0.0, 3.0)], fmt="vertical")
        m = Q.build_metrics(deck, None, probe(1080, 1920), None, "视频号")
        self.assertTrue(m["format_consistent"])
        self.assertTrue(m["platform_fit"])
        self.assertFalse(any(r[4] == "硬失败" for r in Q.judge(m)))

    def test_declared_vs_actual_mismatch_is_hard_fail(self):
        deck = deck_of([card("A", 0.0, 3.0)], fmt="vertical")
        m = Q.build_metrics(deck, None, probe(1440, 1080), None, None)
        self.assertFalse(m["format_consistent"])
        self.assertTrue(any(r[4] == "硬失败" for r in Q.judge(m)))

    def test_platform_unknown_leaves_fit_untested(self):
        deck = deck_of([card("A", 0.0, 3.0)])
        m = Q.build_metrics(deck, None, probe(1440, 1080), None, None)
        self.assertIsNone(m["platform_fit"])


class HookAndCtaTests(unittest.TestCase):
    def test_hook_window_uses_caption_start(self):
        cards = [
            card("A", 0.0, 2.0, caps=[cap("一二三四", 0.0), cap("五六七八", 1.0)]),
            card("B", 2.0, 2.0, caps=[cap("九十", 2.5), cap("窗外不计", 3.5)]),
        ]
        m = Q.build_metrics(deck_of(cards), None, {"failed": True}, None, None)
        self.assertEqual(m["hook"]["caption_count"], 3)
        self.assertEqual(m["hook"]["chars_no_punct"], 10)

    def test_cta_hit_and_miss(self):
        hit = deck_of([card("关注我", 0.0, 2.0, caps=[cap("点赞收藏", 0.0)])])
        miss = deck_of([card("值钱的是流程", 0.0, 2.0, caps=[cap("就是这样", 0.0)])])
        self.assertTrue(Q.build_metrics(hit, None, {"failed": True}, None, None)["cta"]["has_cta"])
        self.assertFalse(Q.build_metrics(miss, None, {"failed": True}, None, None)["cta"]["has_cta"])

    def test_first_role_is_read_from_script(self):
        deck = deck_of([card("A", 0.0, 2.0)])
        m = Q.build_metrics(deck, {"_storyboard_role": ["钩子", "展开"]},
                            {"failed": True}, None, None)
        self.assertEqual(m["hook"]["first_role"], "钩子")


class AcceptanceBaselineTests(unittest.TestCase):
    """真实基准：横竖两条同源成片，必须都量得出、且画幅自洽。"""

    def _measure(self, fmt_dir: str, w: int, h: int) -> dict:
        deck = json.loads((ACCEPT / fmt_dir / "deck.json").read_text(encoding="utf-8"))
        script = json.loads((ACCEPT / fmt_dir / "script.json").read_text(encoding="utf-8"))
        return Q.build_metrics(deck, script, probe(w, h), None, "视频号")

    def test_both_baselines_measure_clean(self):
        for fmt_dir, size in (("landscape", (1440, 1080)), ("vertical", (1080, 1920))):
            with self.subTest(fmt_dir=fmt_dir):
                m = self._measure(fmt_dir, *size)
                self.assertEqual(m["card_count"], 9)
                self.assertEqual(m["pacing"]["timeline_gaps"], [])
                self.assertEqual(m["pacing"]["timeline_overlaps"], [])
                self.assertAlmostEqual(m["total_s"], 32.47, delta=0.05)
                self.assertTrue(m["format_consistent"])
                self.assertEqual(m["hook"]["first_role"], "钩子")

    def test_baselines_carry_the_cta_card(self):
        """2026-09-17 加的末卡 CTA —— 掉了要报出来（这是当时定下的改进项）。"""
        for fmt_dir, size in (("landscape", (1440, 1080)), ("vertical", (1080, 1920))):
            with self.subTest(fmt_dir=fmt_dir):
                m = self._measure(fmt_dir, *size)
                self.assertTrue(m["cta"]["has_cta"])
                self.assertIn("收藏", m["cta"]["hits"])

    def test_landscape_baseline_is_flagged_for_vertical_platform(self):
        m = self._measure("landscape", 1440, 1080)
        self.assertFalse(m["platform_fit"])
        self.assertTrue(any(r[4] == "硬失败" for r in Q.judge(m)))

    def test_vertical_baseline_passes_platform_fit(self):
        m = self._measure("vertical", 1080, 1920)
        self.assertTrue(m["platform_fit"])
        self.assertFalse(any(r[4] == "硬失败" for r in Q.judge(m)))


if __name__ == "__main__":
    unittest.main()
