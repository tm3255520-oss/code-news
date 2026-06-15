import unittest

from scripts.check_generated_article_quality import (
    CheckResult,
    evaluate_gate,
    infer_topic_from_payload,
)
from scripts.sync_recent_metrics_to_log import infer_topic


class QualityGateTests(unittest.TestCase):
    def test_score_below_80_blocks_even_without_fail_items(self) -> None:
        decision = evaluate_gate(
            score=79,
            checks=[CheckResult("warn", "title weak", "too long")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "blocked")
        self.assertEqual(decision["reason"], "score_below_minimum")

    def test_any_fail_item_blocks_even_with_high_score(self) -> None:
        decision = evaluate_gate(
            score=92,
            checks=[CheckResult("fail", "opening weak", "too abstract")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "blocked")
        self.assertEqual(decision["reason"], "contains_fail_items")

    def test_high_score_without_fail_items_passes(self) -> None:
        decision = evaluate_gate(
            score=84,
            checks=[CheckResult("warn", "title weak", "too long")],
            min_score=80,
        )
        self.assertEqual(decision["status"], "passed")
        self.assertEqual(decision["reason"], "ready_for_publish")

    def test_infer_topic_prefers_design_tools_over_generic_agent_mentions(self) -> None:
        topic = infer_topic(
            "设计工具这轮先看4个判断",
            "Canva AI 2.0、Figma 设计 agent、Adobe Firefly AI Assistant 最近的动作都很直接。",
        )
        self.assertEqual(topic, "design-tools")

    def test_infer_topic_keeps_google_io_when_explicit_keywords_exist(self) -> None:
        topic = infer_topic(
            "Google I/O 2026：AI 开始从回答问题走向替你做事",
            "这是 Google I/O 之后最直接的信号。",
        )
        self.assertEqual(topic, "google-io-agentic")

    def test_infer_topic_from_payload_prefers_explicit_topic_over_keyword_collision(self) -> None:
        payload = {
            "topic": "workflow-shift",
            "title": "别再只比谁更会答 现在判断AI先看4步流程能力",
            "summary": "判断一款 AI 该不该长期留，不妨先看它能不能稳定接住一条重复流程。",
            "article_blocks": [
                "我的结论是，判断一款 AI 值不值得长期留，先看它能不能自己跑完一条流程。",
                "只要它还要每次等你重新开口，它就更像聊天入口，不像后台流程能力。",
            ],
        }

        self.assertEqual(infer_topic_from_payload(payload), "workflow-shift")


if __name__ == "__main__":
    unittest.main()
