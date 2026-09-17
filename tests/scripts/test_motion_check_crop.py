# -*- coding: utf-8 -*-
"""test_motion_check_crop.py — 动效密度校验的「内容区裁切」回归门

历史事故（2026-09-16 修正）：旧实现把内容区原图像素除以缩略图比例后
去切**原图数组**，等于只采样原图左上角一条窄带（横屏实测 x13-306 / y25-143）。
后果不是小偏差，而是结论反转：同一条横屏基准
    旧实现 静止率 0.888 ｜ 修正后 0.303
且竖屏成片读数与横屏差出一倍（96.8% vs 88.8%），实际两者同源、本该一致。

本文件把三件事钉住：
1. 裁切框**必须**等于生成器的几何定义（STYLES.card_inset / FORMATS.geom.card_inset），
   版面一改就报错，防止两边漂移。
2. load() 采样的确实是内容区：在内容区**外**（旧 bug 的那条窄带）画黑块，
   读数必须几乎不受影响。
3. 未知分辨率必须拒绝出结论，而不是拿错框硬算。

用法（仓库根目录）：
    python -m unittest tests.scripts.test_motion_check_crop -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_card_deck as B  # noqa: E402
from scripts import motion_check as M  # noqa: E402


def rect_of(inset: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = inset
    w, h = size
    return (left, top, w - right, h - bottom)


class GeometryDriftTests(unittest.TestCase):
    """裁切框的唯一来源是生成器；两边漂移必须被拦下。"""

    def test_landscape_rect_matches_generator_style(self):
        style = B.STYLES["grid-dark"]
        size = tuple(B.FORMATS["landscape"]["size"])
        self.assertEqual(
            tuple(M.CONTENT_RECTS["landscape"]["rect"]),
            rect_of(tuple(style["card_inset"]), size),
        )
        self.assertEqual(tuple(M.CONTENT_RECTS["landscape"]["canvas"]), size)

    def test_vertical_rect_matches_generator_format_geom(self):
        geom = B.FORMATS["vertical"]["geom"]
        size = tuple(B.FORMATS["vertical"]["size"])
        self.assertEqual(
            tuple(M.CONTENT_RECTS["vertical"]["rect"]),
            rect_of(tuple(geom["card_inset"]), size),
        )
        self.assertEqual(tuple(M.CONTENT_RECTS["vertical"]["canvas"]), size)


class FormatDetectTests(unittest.TestCase):
    def test_known_canvases(self):
        self.assertEqual(M.detect_format((1440, 1080)), "landscape")
        self.assertEqual(M.detect_format((1080, 1920)), "vertical")

    def test_unknown_canvas_is_not_guessed(self):
        for size in ((1280, 720), (1920, 1080), (1080, 1080)):
            with self.subTest(size=size):
                self.assertIsNone(M.detect_format(size))


class CropSamplingTests(unittest.TestCase):
    """把旧事故固化成反面：内容区外的东西不许影响读数。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="mc_crop_test_")
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _frame(self, name: str, canvas: tuple[int, int],
               black_at: tuple[int, int, int, int]) -> Path:
        a = np.full((canvas[1], canvas[0]), 255, dtype=np.uint8)
        l, t, r, b = black_at
        a[t:b, l:r] = 0
        p = self.tmp / name
        Image.fromarray(a).save(p)
        return p

    def test_content_box_is_what_gets_sampled(self):
        canvas = tuple(M.CONTENT_RECTS["landscape"]["canvas"])
        rect = tuple(M.CONTENT_RECTS["landscape"]["rect"])
        inside = self._frame("inside.png", canvas, rect)
        # 旧 bug 采样的那条窄带（原图左上角）——放在内容区之外
        outside = self._frame("outside.png", canvas, (13, 25, 306, 143))
        self.assertLess(M.load(inside, rect).mean(), 200,
                        "内容区里的黑块应当被采到")
        self.assertGreater(M.load(outside, rect).mean(), 250,
                           "内容区外的黑块不该影响读数（这正是旧实现出错的地方）")

    def test_vertical_crop_stays_inside_canvas(self):
        canvas = tuple(M.CONTENT_RECTS["vertical"]["canvas"])
        rect = tuple(M.CONTENT_RECTS["vertical"]["rect"])
        p = self._frame("v.png", canvas, rect)
        out = M.load(p, rect)
        self.assertEqual(out.shape[0] > 0 and out.shape[1], M.SAMPLE_W)
        self.assertLess(out.mean(), 200)

    def test_rect_is_inside_canvas_for_every_format(self):
        for name, spec in M.CONTENT_RECTS.items():
            with self.subTest(fmt=name):
                w, h = spec["canvas"]
                l, t, r, b = spec["rect"]
                self.assertTrue(0 <= l < r <= w, "左右越界：%s" % name)
                self.assertTrue(0 <= t < b <= h, "上下越界：%s" % name)


if __name__ == "__main__":
    unittest.main()
