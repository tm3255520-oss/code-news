# -*- coding: utf-8 -*-
"""test_card_video_line.py — 知识卡片视频「生成环节」的回归门

这一段是确定性机器（人只喂 script.json，它只负责出片），改一次就要重渲一次。
所以把三类**真出过问题**的地方固化成断言，让「改坏了」能被一条命令发现，
而不是靠肉眼看片子。

1. 分镜适配（scripts/storyboard_to_cards.py）
   - 正例必须 0 错误；反例 fixture 必须被拦下
   - 动效目标必须在那一镜真有对应画面元素
     （历史事故：单元类卡片写「FLOATS 卡片」→ 渲染器找 .blocks .block 找不到 → GSAP 静默失效）
2. 模板生成器（scripts/build_card_deck.py）
   - 产出的 HTML 里**每一条 GSAP 选择器都要能在 DOM 里找到目标**
     （历史事故：正常路径漏渲染 .blocks 外壳 → GSAP target not found）
   - `ease` 必须带引号（历史事故：序列化剥掉引号 → `ease: power2.out` → JS 未定义变量）
   - 每个定时元素都必须有 data-start + data-duration
   - 同一输入必须产出逐字节相同的 HTML（渲染器要求确定性）
3. 时间轴分组（scripts/build_card_video.py）
   - 卡片必须无空洞覆盖全部口播行；字幕必须归属到正确的卡片

用法（在仓库根目录）：
    python -m unittest tests.scripts.test_card_video_line -v
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_card_deck as B  # noqa: E402
from scripts import build_card_video as V  # noqa: E402
from scripts import storyboard_to_cards as S  # noqa: E402

FIXTURES = ROOT / "video-line"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_storyboard(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── 小工具：从生成的 HTML 里找问题（正例必须为空，反例必须命中）──────────

SEL_RE = re.compile(r'tl\.(?:fromTo|to)\(\s*"([^"]*?)"')
QSEL_RE = re.compile(r"querySelector\('([^']+)'\)")
CLIP_RE = re.compile(r'<div class="([^"]*\bclip\b[^"]*)"([^>]*)>')
EASE_RE = re.compile(r'ease:\s*[^"\s]')


def gsap_selectors(html: str) -> list[str]:
    return SEL_RE.findall(html) + QSEL_RE.findall(html)


def has_class(html: str, cls: str) -> bool:
    return re.search(r'class="[^"]*(?<![\w-])' + re.escape(cls) + r'(?![\w-])', html) is not None


def selector_problems(html: str) -> list[str]:
    """每一条 GSAP 选择器里的 class / id 都必须真的出现在 DOM 里。"""
    problems = []
    for sel in gsap_selectors(html):
        for cls in re.findall(r"\.([A-Za-z][\w-]*)", sel):
            if not has_class(html, cls):
                problems.append(f"选择器 {sel!r} 要的 .{cls} 在 DOM 里不存在")
        for eid in re.findall(r"#([A-Za-z][\w-]*)", sel):
            if f'id="{eid}"' not in html:
                problems.append(f"选择器 {sel!r} 要的 #{eid} 在 DOM 里不存在")
    return problems


def timing_problems(html: str) -> list[str]:
    """定时元素（class 带 clip）必须同时有 data-start 与 data-duration。"""
    problems = []
    for m in CLIP_RE.finditer(html):
        cls, attrs = m.group(1), m.group(2)
        if "data-start=" not in attrs or "data-duration=" not in attrs:
            problems.append(f"class={cls!r} 的定时元素缺 data-start/data-duration")
    return problems


def js_literal_problems(html: str) -> list[str]:
    """ease 被剥引号会变成 JS 未定义变量（历史事故），必须带引号。"""
    return [f"ease 未加引号：{m.group(0)!r}" for m in EASE_RE.finditer(html)]


def synthetic_deck() -> dict:
    """覆盖全部分支的小样：blocks / big / 四类单元 / DRAWS / TYPES / 末镜淡黑。"""
    return {
        "series": "REGRESSION", "episode": "TEST", "breadcrumb": "回归", "style": "grid-dark",
        "audio": "assets/voice_segmented.mp3",
        "cards": [
            {"title": "带 blocks 的卡", "kicker": "01",
             "blocks": [{"label": "L", "text": "T"}],
             "start": 0.0, "duration": 3.0,
             "motion": "DRAWS 标题 → FLOATS 卡片",
             "transition_in": "硬切", "transition_out": "硬切",
             "captions": [{"text": "字幕一", "start": 0.1, "duration": 1.2}]},
            {"title": "带大字的卡", "subtitle": "副标题", "big": ["3 小时", "5 分钟"],
             "start": 3.0, "duration": 4.0, "motion": "TYPES 标题",
             "transition_in": "FADES", "transition_out": "硬切",
             "captions": [{"text": "字幕二", "start": 3.1, "duration": 1.0}]},
            {"title": "带四类单元的卡", "kicker": "03",
             "units": [
                 {"type": "list", "numbered": True, "drift": True,
                  "items": ["甲", "乙", "丙"], "note": "列表小结"},
                 {"type": "stat",
                  "items": [{"label": "密度", "value": "3.2%"}, {"label": "对标", "value": "2.66%"}]},
                 {"type": "compare",
                  "items": [{"label": "前", "text": "第一行\n第二行"}, {"label": "后", "text": "第三行\n第四行"}]},
                 {"type": "steps", "items": ["第一步", "第二步", "第三步"]},
             ],
             "start": 7.0, "duration": 5.0, "motion": "FLOATS 标题",
             "transition_in": "硬切", "transition_out": "FADES 到黑",
             "captions": [{"text": "字幕三", "start": 7.1, "duration": 1.5}]},
        ],
    }


class StoryboardAdapterTests(unittest.TestCase):
    """分镜适配层：正例要过，反例要拦，动效目标要与画面内容对得上。"""

    def test_positive_fixture_passes(self) -> None:
        errs, warns = S.check(load_storyboard("storyboard.pipeline.json"))
        self.assertEqual(errs, [], f"正例不该有错误：{errs}")
        self.assertEqual(warns, [], f"正例不该有告警：{warns}")

    def test_negative_fixture_is_rejected(self) -> None:
        errs, _ = S.check(load_storyboard("storyboard.bad.json"))
        self.assertGreaterEqual(len(errs), 10, "反例 fixture 应该被大量拦下")
        joined = "\n".join(errs)
        for expect in ("未登记的目标", "写了参数", "缺 transition_out"):
            self.assertIn(expect, joined, f"反例里该类错误没被拦下：{expect}")

    def test_motion_target_requires_matching_content(self) -> None:
        """单元类卡片去动「卡片」= 渲染器找不到目标（历史事故，必须拦下）。"""
        sb = copy.deepcopy(load_storyboard("storyboard.pipeline.json"))
        sb["scenes"][2]["motion"] = "FLOATS 标题 → FLOATS 卡片"  # 这一镜只有 units，没有 blocks
        errs, _ = S.check(sb)
        self.assertTrue(any("卡片" in e and "screen.blocks" in e for e in errs),
                        f"没拦住「动不存在的卡片」：{errs}")

    def test_motion_target_missing_subtitle_is_rejected(self) -> None:
        sb = copy.deepcopy(load_storyboard("storyboard.pipeline.json"))
        sb["scenes"][3]["motion"] = "FLOATS 副标题"  # 这一镜没有 subtitle
        errs, _ = S.check(sb)
        self.assertTrue(any("screen.subtitle" in e for e in errs),
                        f"没拦住「动不存在的副标题」：{errs}")

    def test_adapter_output_contract(self) -> None:
        sb = load_storyboard("storyboard.pipeline.json")
        script = S.to_script(sb)
        self.assertEqual(script["lines"], sb["lines"])
        covered: list[int] = []
        for card in script["cards"]:
            covered.extend(range(card["from"], card["to"] + 1))
        self.assertEqual(sorted(covered), list(range(1, len(sb["lines"]) + 1)),
                         "script.json 的卡片必须恰好覆盖每一行口播")


class DeckBuilderTests(unittest.TestCase):
    """模板生成器：产出的 HTML 必须自洽，否则渲染时才炸。"""

    def setUp(self) -> None:
        self.deck = synthetic_deck()
        self.html = B.build(self.deck)

    def test_every_gsap_selector_resolves_in_dom(self) -> None:
        self.assertEqual(selector_problems(self.html), [],
                         "有 GSAP 选择器在 DOM 里找不到目标，动效会静默失效")

    def test_selector_checker_has_teeth(self) -> None:
        """反例：把 .blocks 外壳抹掉（历史事故现场），检查器必须报出来。"""
        broken = self.html.replace('class="blocks', 'class="')
        problems = selector_problems(broken)
        self.assertTrue(any(".blocks" in p for p in problems),
                        "检查器抓不到「.blocks 外壳缺失」，等于没有回归保护")

    def test_ease_values_are_quoted(self) -> None:
        self.assertEqual(js_literal_problems(self.html), [], "ease 被剥引号会变成 JS 未定义变量")

    def test_ease_checker_has_teeth(self) -> None:
        broken = self.html.replace('ease: "power2.out"', "ease: power2.out", 1)
        self.assertTrue(js_literal_problems(broken), "检查器抓不到未加引号的 ease")

    def test_timed_elements_have_start_and_duration(self) -> None:
        self.assertEqual(timing_problems(self.html), [])
        self.assertTrue(CLIP_RE.search(self.html), "样本里应该有定时元素，检查本身要有效")

    def test_draws_emits_rule(self) -> None:
        self.assertTrue(has_class(self.html, "rule"), "DRAWS 目标要有 .rule 可画")

    def test_types_emits_char_spans(self) -> None:
        self.assertTrue(has_class(self.html, "ch"), "TYPES 需要逐字 span")

    def test_fadeout_only_when_last_card_asks_for_it(self) -> None:
        self.assertIn('id="fadeout"', self.html, "末镜写了 FADES 到黑 就该有黑幕")
        plain = copy.deepcopy(self.deck)
        plain["cards"][-1]["transition_out"] = "硬切"
        self.assertNotIn('id="fadeout"', B.build(plain), "没写淡黑就不该有黑幕")

    def test_build_is_deterministic(self) -> None:
        self.assertEqual(self.html, B.build(synthetic_deck()))
        for bad in ("Math.random", "Date.now"):
            self.assertNotIn(bad, self.html, f"渲染要求确定性，不允许 {bad}")

    def test_committed_fixture_builds(self) -> None:
        deck = load_fixture("cards.sample.json")
        html = B.build(deck)
        self.assertEqual(html.count('class="clip card"'), len(deck["cards"]),
                         "每张卡片应恰好一个定时元素")
        self.assertEqual(selector_problems(html), [])
        self.assertEqual(timing_problems(html), [])


class TimingTests(unittest.TestCase):
    """时间轴分组：配音先行推出来的卡片时间轴必须无空洞、字幕归属正确。"""

    def _script(self) -> dict:
        return {"lines": ["甲。", "乙。", "丙。", "丁。"],
                "cards": [{"title": "一", "from": 1, "to": 2},
                          {"title": "二", "from": 3, "to": 4}]}

    def _timeline(self) -> dict:
        starts = [0.0, 1.0, 2.5, 3.5]
        return {"segments": [{"index": i + 1, "start": s, "end": s + 1.0, "duration": 1.0}
                             for i, s in enumerate(starts)],
                "total_duration": 4.5}

    def test_cards_are_gapless_and_captions_land_right(self) -> None:
        cues = [{"start": 0.2, "end": 0.8, "text": "第一条"},
                {"start": 3.0, "end": 3.4, "text": "第二条"}]
        cards, total = V.step_timing(self._script(), self._timeline(), cues)
        self.assertEqual([c["start"] for c in cards], [0.0, 2.5])
        self.assertEqual([c["duration"] for c in cards], [2.5, 2.0])
        self.assertAlmostEqual(sum(c["duration"] for c in cards), total, places=6)
        self.assertEqual([c["text"] for c in cards[0]["captions"]], ["第一条"])
        self.assertEqual([c["text"] for c in cards[1]["captions"]], ["第二条"])

    def test_incomplete_coverage_is_rejected(self) -> None:
        script = {"lines": ["甲。", "乙。", "丙。"],
                  "cards": [{"from": 1, "to": 1}, {"from": 3, "to": 3}]}
        tl = {"segments": [{"index": i + 1, "start": float(i), "end": float(i + 1),
                            "duration": 1.0} for i in range(3)],
              "total_duration": 3.0}
        with self.assertRaises(RuntimeError):
            V.step_timing(script, tl, [])

    def test_segment_count_must_match_lines(self) -> None:
        tl = self._timeline()
        tl["segments"] = tl["segments"][:2]
        with self.assertRaises(RuntimeError):
            V.step_timing(self._script(), tl, [])


if __name__ == "__main__":
    unittest.main()
