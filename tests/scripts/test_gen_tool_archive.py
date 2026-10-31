"""gen_tool_archive.py 的回归测试。

守的是「档案骨架能不能如实反映工具」这件事，具体四条：
1. frontmatter 的块标量（`description: >`）要能收拢成一行——这是绝大多数 skill
   写描述的写法，解析不出来等于档案没有「干什么」。
2. 触发句要切成完整句子，不能把整段描述或无关正文吞进来。
3. 工具目录在本机读不到时（符号链接指向挂载之外）要能从 ~/.hermes 的 git 仓库兜底，
   否则这类档案只剩一个名字。
4. --write / --check 要与线别映射一一对应，漏一个就要报出来。
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "gen_tool_archive.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("gen_tool_archive", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # 脚本用了 @dataclass，必须先把模块登记进 sys.modules（同 test_check_doc_references）。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FrontmatterTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_script()

    def test_folded_block_scalar_is_joined(self):
        text = (
            "---\n"
            "name: demo\n"
            "description: >\n"
            "  第一段说明。\n"
            "  第二段说明。\n"
            "version: 2.1\n"
            "---\n\n# demo\n"
        )
        fm = self.m._frontmatter(text)
        self.assertEqual(fm["description"], "第一段说明。 第二段说明。")
        self.assertEqual(fm["version"], "2.1")

    def test_literal_block_scalar_and_plain_scalar(self):
        text = "---\ndescription: |\n  a\n  b\nauthor: 老廖\n---\n"
        fm = self.m._frontmatter(text)
        self.assertEqual(fm["description"], "a b")
        self.assertEqual(fm["author"], "老廖")

    def test_missing_frontmatter(self):
        self.assertEqual(self.m._frontmatter("# 没有 frontmatter\n"), {})


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_script()

    def test_trigger_section_wins(self):
        body = "# x\n\n## 触发\n\n- 用户说「拆解这条视频」\n- 用户说「拉片」\n\n## 其它\n\n无关\n"
        got = self.m._find_triggers("描述", body)
        self.assertEqual(got, ["用户说「拆解这条视频」", "用户说「拉片」"])

    def test_english_marker_keeps_whole_clause(self):
        got = self.m._find_triggers("Use when given a video URL to transcribe into Obsidian.", "")
        self.assertEqual(got, ["Use when given a video URL to transcribe into Obsidian."])

    def test_chinese_marker_clause(self):
        got = self.m._find_triggers("公众号文案合规检测。触发词：发稿前检查、违禁词扫描。其它说明。", "")
        self.assertIn("发稿前检查、违禁词扫描", got[0])

    def test_fallback_is_labelled_as_inferred(self):
        got = self.m._find_triggers("Codex桌面端故障诊断运维。502、8971代理死时用。", "")
        self.assertTrue(got[0].startswith("（推断自 description）"))
        self.assertIn("502", got[0])

    def test_nothing_available_returns_empty(self):
        self.assertEqual(self.m._find_triggers("短。", ""), [])


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_script()

    def test_finds_backticked_and_bare_output_dirs(self):
        body = "写到 `D:\\Obsidian Vault\\obsidian Vault\\raw\\videos\\` 下，\n" \
               "候选清单进 内容生产/情报与选题/素材候选/ 目录。\n"
        outs = self.m._extract(body)["outputs"]
        self.assertTrue(any("raw" in o for o in outs), outs)
        self.assertTrue(any("素材候选" in o for o in outs), outs)

    def test_ignores_plain_words_without_a_separator(self):
        # 「抖音」是线索词但没有路径形状，不该被当成落盘目录
        self.assertEqual(self.m._extract("正文提到抖音这个平台。\n")["outputs"], [])

    def test_finds_dependency_files_and_billing(self):
        body = "依赖 `.hermes/scripts/foo.py`，走 NVIDIA NIM，RedFox 中转。\n"
        got = self.m._extract(body)
        self.assertIn(".hermes/scripts/foo.py", got["deps"])
        self.assertTrue(any("NIM" in b for b in got["billing"]), got["billing"])
        self.assertTrue(any("RedFox" in b for b in got["billing"]), got["billing"])

    def test_generic_token_signal_is_marked_weak(self):
        got = self.m._extract("注意 token 用量。\n")
        self.assertTrue(got["billing"], "弱线索也该留痕")
        self.assertIn("弱线索", got["billing"][0])

    def test_fault_heading_carries_first_bullet(self):
        body = "## Pitfalls\n\n- netstat 查不到但 curl 得 502：是代理劫持。\n"
        faults = self.m._extract(body)["faults"]
        self.assertEqual(len(faults), 1)
        self.assertIn("Pitfalls", faults[0])
        self.assertIn("代理劫持", faults[0])


class ArchiveNameTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_script()

    def test_skill_name_uses_leaf_dir(self):
        self.assertEqual(self.m.Tool("devops/codex-desktop-ops", "skill", "系统与运维", "x").archive_name,
                         "codex-desktop-ops.md")

    def test_mcp_name_drops_prefix(self):
        self.assertEqual(self.m.Tool("mcp:toolkit-mcp", "mcp", "MCP", "x").archive_name,
                         "toolkit-mcp.md")


class BuildAndWriteTests(unittest.TestCase):
    """用临时目录装作 vault 与 ~/.hermes，跑一遍写档 + 体检。"""

    def setUp(self):
        self.m = _load_script()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.vault = root / "vault"
        (self.vault / "系统中枢").mkdir(parents=True)
        self.skills = root / "hermes" / "skills"
        self.hermes = root / "hermes"

        # 一个正常可读的 skill
        d = self.skills / "demo-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: >\n  演示用 skill。\n"
            "  触发词：演示、练手。\nversion: 1.0\n---\n\n"
            "## 触发\n\n- 用户说「演示一下」\n\n"
            "写到 `参考库/运营知识/抖音/` 下。依赖 `.hermes/scripts/demo.py`。\n",
            encoding="utf-8",
        )

        # 一个「读不到」的 skill：符号链接指向不存在的目标，靠 git blob 兜底
        git_dir = self.skills / "linked-skill"
        git_dir.mkdir(parents=True)
        (git_dir / "SKILL.md").write_text(
            "---\nname: linked-skill\ndescription: 从 git 兜底读到的描述。\n---\n\n# linked\n",
            encoding="utf-8",
        )
        self._git_init_and_commit()

        broken = self.skills / "linked-skill" / "SKILL.md"
        broken.unlink()
        os.symlink("/nonexistent/nowhere/SKILL.md", broken)

        # 一个装了但映射里没有的 skill → --check 要报出来
        stray = self.skills / "stray-skill"
        stray.mkdir()
        (stray / "SKILL.md").write_text("---\nname: stray\n---\n", encoding="utf-8")

        self.m.VAULT_ROOT = self.vault
        self.m.SKILLS_ROOT = self.skills
        self.m.HERMES_HOME = self.hermes
        self.m.LINES_CONFIG = self._write_lines_config()

    def tearDown(self):
        self._tmp.cleanup()

    def _git_init_and_commit(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
        for argv in (["init", "-q"], ["add", "skills"],
                     ["commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(self.hermes), *argv],
                           capture_output=True, env=env, check=False)

    def _write_lines_config(self):
        cfg = self.vault / "lines.json"
        cfg.write_text(
            '{"演示线": ["demo-skill", "linked-skill"], "MCP": []}',
            encoding="utf-8",
        )
        return cfg

    def test_readable_skill_is_parsed_from_disk(self):
        t = self.m._build_skill("demo-skill", "演示线", {}, None)
        self.assertTrue(t.readable)
        self.assertEqual(t.version, "1.0")
        self.assertIn("演示用 skill", t.description)
        self.assertIn("用户说「演示一下」", t.triggers)
        self.assertTrue(any("参考库" in o for o in t.outputs), t.outputs)
        self.assertIn(".hermes/scripts/demo.py", t.deps)

    def test_unreadable_skill_falls_back_to_git_blob(self):
        t = self.m._build_skill("linked-skill", "演示线", {}, None)
        self.assertEqual(t.description, "从 git 兜底读到的描述。")
        self.assertTrue(t.notes, "兜底要留痕，说明正文取自 git")
        self.assertIn("git", t.notes[0])
        self.assertGreater(t.line_count, 0)

    def test_git_file_count_used_when_os_walk_fails(self):
        t = self.m._build_skill("linked-skill", "演示线", {}, None)
        self.assertEqual(t.file_count, 1)

    def test_write_then_check_passes_for_mapped_tools(self):
        tools = [self.m._build_skill("demo-skill", "演示线", {}, None)]
        created, skipped = self.m.write_archives(tools, force=False)
        self.assertEqual((created, skipped), (1, 0))
        f = self.vault / "系统中枢" / self.m.ZONE_DIRNAME / "演示线" / "demo-skill.md"
        self.assertTrue(f.exists())
        body = f.read_text(encoding="utf-8")
        self.assertIn("## 二、怎么触发", body)
        self.assertIn("演示线", body)
        subprocess.run(["git", "-C", str(self.hermes), "add", "-A"], capture_output=True)
        # 映射齐了就不该报「漏档」；stray-skill 没配仍会被点名
        problems = self.m.check(tools)
        self.assertTrue(any("stray-skill" in p for p in problems), problems)
        self.assertFalse(any("demo-skill" in p for p in problems), problems)

    def test_archives_never_leak_sandbox_paths(self):
        t = self.m._build_skill("demo-skill", "演示线", {}, None)
        rendered = self.m.render(t)
        self.assertNotIn(str(self.skills), rendered, "档案里不该出现本机/沙箱路径")
        self.assertIn("C:\\Users\\Administrator\\.hermes\\skills", rendered)

    def test_manifest_counts(self):
        tools = [self.m._build_skill(k, "演示线", {}, None) for k in ("demo-skill", "linked-skill")]
        data = self.m.manifest(tools)
        self.assertEqual(data["counts"]["total"], 2)
        self.assertEqual(data["counts"]["skill"], 2)
        self.assertEqual(data["counts"]["by_line"]["演示线"], 2)


class IndexTests(unittest.TestCase):
    """专区 _索引.md 的总表段：只替换标记之间，散文不许动。"""

    def setUp(self):
        self.m = _load_script()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.vault = root / "vault"
        self.hermes = root / "hermes"
        (self.hermes / "skills" / ".archive" / "old-skill").mkdir(parents=True)
        (self.hermes / "skills" / ".archive" / "old-skill" / "SKILL.md").write_text(
            "---\nname: old-skill\n---\n", encoding="utf-8"
        )
        zone = self.vault / "系统中枢" / self.m.ZONE_DIRNAME
        for line, name, one in (("演示线", "demo-skill", "把演示做掉。"), ("MCP", "demo-mcp", "演示用的 MCP。")):
            d = zone / line
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.md").write_text(
                f"---\ntitle: {name}\n来源: self\n线别: {line}\n---\n\n# {name}\n\n"
                f"## 一、干什么\n\n{one}后面还有别的说明。\n\n## 二、怎么触发\n\n- 用户说演示\n",
                encoding="utf-8",
            )
        self.m.VAULT_ROOT = self.vault
        self.m.SKILLS_ROOT = self.hermes / "skills"
        self.m.HERMES_HOME = self.hermes

    def tearDown(self):
        self._tmp.cleanup()

    def test_rows_cover_every_line_and_carry_one_liner(self):
        lines, retired = self.m._index_rows()
        self.assertEqual(set(lines), {"演示线", "MCP"})
        self.assertEqual(lines["演示线"], [("demo-skill", "self", "把演示做掉。")])
        self.assertIn("old-skill", retired)

    def test_render_index_counts_and_escapes_the_alias_pipe(self):
        out = self.m.render_index()
        self.assertIn("**当前收录 2 件**", out)
        self.assertIn("skill 1 件 + MCP 1 件", out)
        self.assertIn("### 演示线（1）", out)
        self.assertIn(r"[[系统中枢/系统skills以及MCP/演示线/demo-skill\|demo-skill]]", out)
        self.assertIn("old-skill", out)
        self.assertTrue(out.startswith(self.m.INDEX_BEGIN))

    def test_update_index_leaves_surrounding_prose_untouched(self):
        f = self.vault / "系统中枢" / self.m.ZONE_DIRNAME / "_索引.md"
        f.write_text(
            f"---\ntitle: t\n---\n\n## 一、散文在前\n\n别动我。\n\n"
            f"{self.m.INDEX_BEGIN}\n\n旧的表\n\n{self.m.INDEX_END}\n\n## 三、散文在后\n\n也别动我。\n",
            encoding="utf-8",
        )
        self.assertEqual(self.m.update_index(), 0)
        got = f.read_text(encoding="utf-8")
        self.assertIn("别动我。", got)
        self.assertIn("也别动我。", got)
        self.assertNotIn("旧的表", got)
        self.assertIn("demo-skill", got)

    def test_update_index_without_markers_is_refused(self):
        f = self.vault / "系统中枢" / self.m.ZONE_DIRNAME / "_索引.md"
        f.write_text("---\ntitle: t\n---\n\n没标记\n", encoding="utf-8")
        self.assertEqual(self.m.update_index(), 1)
        self.assertIn("没标记", f.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
