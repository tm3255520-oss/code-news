import unittest

from scripts.check_provider_consistency import check_role_resolution


def _providers() -> dict:
    return {
        "agnes": {"models": {"agnes-3.0-flash": {}, "agnes-2.5-flash": {}}},
        "nvidia": {"models": {"nvidia/nemotron-3-ultra-550b-a55b": {}}},
        "deepseek": {"models": {"deepseek-flash": {}}},
    }


class CheckRoleResolutionTests(unittest.TestCase):
    """第六面（E11）的离线单测——全部用受控 dict，不碰真配置。"""

    def test_all_roles_land_no_errors(self) -> None:
        roles = {"review_quality": "nvidia/nemotron-3-ultra-550b-a55b"}
        defaults = {"general": "agnes-3.0-flash", "script": "agnes-3.0-flash"}
        errors, warnings = check_role_resolution(_providers(), roles, defaults, {})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_dangling_role_is_error(self) -> None:
        defaults = {"script": "deepseek-v3.2"}  # 不在任何 provider 的 models 里
        errors, warnings = check_role_resolution(_providers(), {}, defaults, {})
        self.assertEqual(len(errors), 1)
        self.assertIn("script", errors[0])
        self.assertIn("deepseek-v3.2", errors[0])
        self.assertEqual(warnings, [])

    def test_known_unconnected_is_warning_not_error(self) -> None:
        defaults = {"code_premium": "qwen3-coder-plus"}  # 悬空
        known = {"code_premium": "无降级链，留待另开卡"}
        errors, warnings = check_role_resolution(_providers(), {}, defaults, known)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("code_premium", warnings[0])
        self.assertIn("留待另开卡", warnings[0])

    def test_unknown_role_is_not_checked(self) -> None:
        # role 既不在 roles 也不在 role_defaults（如只存在于 fallback_chains）→ 不被遍历，
        # 即便它的模型悬空也不报错。
        defaults = {"general": "agnes-3.0-flash"}
        errors, warnings = check_role_resolution(_providers(), {}, defaults, {})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_roles_overrides_role_defaults(self) -> None:
        # 取值顺序与 resolve() 同构：roles（单一真源）优先于 role_defaults；
        # 即便 defaults 悬空，只要 roles 里落地了就不报错。
        roles = {"script": "agnes-3.0-flash"}
        defaults = {"script": "deepseek-v3.2"}
        errors, warnings = check_role_resolution(_providers(), roles, defaults, {})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
