import unittest

from scripts.check_provider_consistency import check_fallback_chains


class CheckFallbackChainsTests(unittest.TestCase):
    """第五面对账（fallback_chains 落地校验）的离线单测——全部用受控 dict，不碰真配置。"""

    @staticmethod
    def _providers() -> dict:
        return {
            "agnes": {"models": {"agnes-3.0-flash": {}, "agnes-2.5-flash": {}}},
            "nvidia": {"models": {"nvidia/nemotron-3-ultra-550b-a55b": {}, "openai/gpt-oss-20b": {}}},
            "deepseek": {"models": {"deepseek-flash": {}}},
        }

    def test_all_valid_no_errors(self) -> None:
        errors, warnings = check_fallback_chains(self._providers(), {
            "general": ["agnes/agnes-3.0-flash",
                        "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
                        "deepseek/deepseek-flash"],
            "premium": ["nvidia/nvidia/nemotron-3-ultra-550b-a55b"],
        })
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_provider_is_error(self) -> None:
        errors, warnings = check_fallback_chains(self._providers(), {
            "general": ["nosuch/whatever"],
        })
        self.assertEqual(len(errors), 1)
        self.assertIn("nosuch/whatever", errors[0])
        self.assertEqual(warnings, [])

    def test_undeclared_model_is_error(self) -> None:
        errors, warnings = check_fallback_chains(self._providers(), {
            "general": ["agnes/no-such-model"],
        })
        self.assertEqual(len(errors), 1)
        self.assertIn("agnes/no-such-model", errors[0])
        self.assertEqual(warnings, [])

    def test_empty_chain_is_warning_not_error(self) -> None:
        errors, warnings = check_fallback_chains(self._providers(), {
            "code_premium": [],
            "general": ["agnes/agnes-3.0-flash"],
        })
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("code_premium", warnings[0])

    def test_model_name_with_slash_resolves(self) -> None:
        # 模型名本身含 `/`（nvidia 家）：必须落在正确切点，不误判 provider 或 model
        errors, warnings = check_fallback_chains(self._providers(), {
            "fast": ["nvidia/openai/gpt-oss-20b"],
        })
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
