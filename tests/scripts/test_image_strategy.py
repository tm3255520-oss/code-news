import unittest

from scripts.image_strategy import build_image_plan


class ImageStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = {
            "schemaVersion": 1,
            "historyWindow": 6,
            "avoidRepeatWindow": 2,
            "coverFamilies": {
                "warm_editorial": {"renderer": "guizang-social-card-skill"},
                "contrast_signal": {"renderer": "imagegen"},
                "data_brief": {"renderer": "guizang-social-card-skill"},
                "question_lead": {"renderer": "imagegen"},
            },
            "bodyFamilies": {
                "workflow_whiteboard": {"renderer": "ian-xiaohei-illustrations"},
                "comparison_board": {"renderer": "imagegen"},
                "risk_checklist": {"renderer": "ian-xiaohei-illustrations"},
                "decision_tree": {"renderer": "ian-xiaohei-illustrations"},
            },
            "palettes": {
                "amber_ink": {},
                "olive_blue": {},
                "graphite_green": {},
            },
            "domainPreferences": {
                "efficiency_tools": {
                    "coverFamilies": [
                        "warm_editorial",
                        "data_brief",
                        "contrast_signal",
                    ],
                    "bodyFamilies": [
                        "workflow_whiteboard",
                        "decision_tree",
                        "risk_checklist",
                        "comparison_board",
                    ],
                    "palettes": [
                        "amber_ink",
                        "olive_blue",
                        "graphite_green",
                    ],
                }
            },
        }
        self.payload = {
            "slug": "demo-slug",
            "title": "效率工具怎么选，先看流程是不是接得住",
            "summary": "把生成、修改、发布接成一条线，比单点功能更重要。",
            "article_blocks": [
                "一、先看流程",
                "如果流程接不住，再强的单点能力也会卡住。",
                "二、再看协作",
                "团队协作和审批会直接影响返工。",
                "三、最后看发布",
                "能不能少搬运，决定最终效率。",
            ],
        }

    def test_cover_family_avoids_recent_repeat_window(self) -> None:
        history = [
            {
                "slug": "older-1",
                "coverFamily": "warm_editorial",
                "coverPalette": "amber_ink",
                "bodyFamilies": ["workflow_whiteboard", "decision_tree", "risk_checklist"],
            },
            {
                "slug": "older-2",
                "coverFamily": "data_brief",
                "coverPalette": "olive_blue",
                "bodyFamilies": ["comparison_board", "workflow_whiteboard", "decision_tree"],
            },
        ]
        plan = build_image_plan(self.payload, "efficiency_tools", self.strategy, history)
        self.assertEqual(plan["coverFamily"], "contrast_signal")

    def test_body_families_are_unique_within_one_article(self) -> None:
        plan = build_image_plan(self.payload, "efficiency_tools", self.strategy, history=[])
        families = [slot["family"] for slot in plan["bodySlots"]]
        self.assertEqual(len(families), len(set(families)))
        self.assertEqual(len(families), 3)

    def test_recent_palette_is_avoided_when_possible(self) -> None:
        history = [
            {
                "slug": "older-1",
                "coverFamily": "warm_editorial",
                "coverPalette": "amber_ink",
                "bodyFamilies": ["workflow_whiteboard", "decision_tree", "risk_checklist"],
            },
            {
                "slug": "older-2",
                "coverFamily": "data_brief",
                "coverPalette": "olive_blue",
                "bodyFamilies": ["comparison_board", "workflow_whiteboard", "decision_tree"],
            },
        ]
        plan = build_image_plan(self.payload, "efficiency_tools", self.strategy, history)
        self.assertEqual(plan["coverPalette"], "graphite_green")


if __name__ == "__main__":
    unittest.main()
