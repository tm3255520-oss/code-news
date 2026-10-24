"""topic_triage 的离线用例：窗口/聚合过滤、同题提示、台账增量、日报渲染。

真调 Jev 的那部分不在这里（会花钱且依赖网络），由 `--dry-run` + 影子台账验证。
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts import topic_triage as TT


def _card(pool: Path, rows: list[str]) -> None:
    pool.mkdir(parents=True, exist_ok=True)
    (pool / "题材卡.md").write_text(
        "# 题材卡\n\n| 标题 | 平台 | 日期 | 摘要 | 原文 |\n|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


class CollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.pool = self.vault / TT.POOL_REL
        self.summ = self.vault / "知识库/1-素材摘要/2026-10"
        self.summ.mkdir(parents=True)
        for name in ("in", "old", "agg", "missing"):
            if name != "missing":
                (self.summ / f"{name}.md").write_text(f"# {name}\n正文", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_filters_window_and_aggregates(self) -> None:
        _card(self.pool, [
            "| 窗口内素材 | 头条 | 2026-10-24 | [[知识库/1-素材摘要/2026-10/in]] | [x](u) |",
            "| 窗口外素材 | 头条 | 2026-10-01 | [[知识库/1-素材摘要/2026-10/old]] | [x](u) |",
            "| 2026-10-24-热榜TOP20 | 热点与情报 | 2026-10-24 | [[知识库/1-素材摘要/2026-10/agg]] | [x](u) |",
        ])
        items = TT.collect(self.vault, "2026-10-22", "2026-10-24")
        self.assertEqual([i["title"] for i in items], ["窗口内素材"])
        self.assertEqual(items[0]["plat"], "头条")

    def test_skips_missing_summary_file(self) -> None:
        _card(self.pool, [
            "| 缺文件的素材 | 头条 | 2026-10-24 | [[知识库/1-素材摘要/2026-10/missing]] | [x](u) |",
        ])
        self.assertEqual(TT.collect(self.vault, "2026-10-22", "2026-10-24"), [])

    def test_dedupes_same_summary_path(self) -> None:
        row = "| 同一条 | 头条 | 2026-10-24 | [[知识库/1-素材摘要/2026-10/in]] | [x](u) |"
        _card(self.pool, [row, row])
        self.assertEqual(len(TT.collect(self.vault, "2026-10-22", "2026-10-24")), 1)


class SimilarityTests(unittest.TestCase):
    def test_same_title_is_a_pair(self) -> None:
        a = {"title": "DeepSeek 开源推理框架解读"}
        b = {"title": "DeepSeek 开源推理框架 解读！"}
        self.assertEqual(len(TT.similarity_pairs([a, b])), 1)

    def test_unrelated_titles_are_not_paired(self) -> None:
        a = {"title": "MiniMax 开源模型"}
        b = {"title": "一家三口去杭州怎么玩"}
        self.assertEqual(TT.similarity_pairs([a, b]), [])

    def test_never_merges_or_drops(self) -> None:
        """同题只提示、不合并 —— 返回值是"对"，不是"簇"，条目数不受影响。"""
        items = [{"title": "同一个标题"}, {"title": "同一个标题"}, {"title": "完全不同的事"}]
        self.assertEqual(len(TT.similarity_pairs(items)), 1)
        self.assertEqual(len(items), 3)


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.temp.name) / "ledger.jsonl"
        self.orig = TT.LEDGER
        TT.LEDGER = self.ledger

    def tearDown(self) -> None:
        TT.LEDGER = self.orig
        self.temp.cleanup()

    def test_missing_ledger_is_empty(self) -> None:
        self.assertEqual(TT.load_seen(), set())

    def test_reads_src_and_ignores_bad_lines(self) -> None:
        self.ledger.write_text(
            json.dumps({"src": "a"}) + "\n不是json\n" + json.dumps({"title": "无 src"}) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(TT.load_seen(), {"a"})


class RenderTests(unittest.TestCase):
    def test_groups_into_three_buckets_with_disclaimer(self) -> None:
        scored = [
            {"title": "A", "plat": "头条", "date": "2026-10-24", "bucket": "now",
             "confidence": 0.8, "new_info": 0.7, "card": "模型与API"},
            {"title": "B", "plat": "知乎", "date": "2026-10-24", "bucket": "skip",
             "confidence": 0.5, "new_info": 0.2, "card": "AI行业趋势"},
        ]
        meta = {"since": "2026-10-22", "until": "2026-10-24", "raw": 3,
                "model": "jev-1.14.0", "tokens": 1000}
        report = TT.render("2026-10-24", scored, meta, [], 1)
        self.assertIn("now（优先看）", report)
        self.assertIn("skip（无新增信息）", report)
        self.assertIn("A", report)
        self.assertIn("B", report)
        self.assertIn("confidence` 不能当筛选器", report)
        self.assertIn("已评过跳过 **1** 条", report)


if __name__ == "__main__":
    unittest.main()
