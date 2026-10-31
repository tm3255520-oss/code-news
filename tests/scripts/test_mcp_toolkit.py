"""测试 mcp_toolkit_server 与 sync_agent_mcp 的接线逻辑。

运行：python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import mcp_toolkit_server as toolkit  # noqa: E402
from scripts import sync_agent_mcp  # noqa: E402


def _write_toolkit_config(tmp: Path, scripts: dict) -> Path:
    """构造临时 mcp_toolkit.json；scripts 为 {name: {script, ...}}。"""
    tools = {}
    for name, spec in scripts.items():
        tool = {
            "enabled": True,
            "group": spec.get("group", "test"),
            "label": spec.get("label", name),
            "script": str(spec.get("script", "")),
            "python": sys.executable,
            "timeoutSec": spec.get("timeoutSec", 60),
        }
        if spec.get("data_dir"):
            tool["data_dir"] = str(spec["data_dir"])
        tools[name] = tool
    cfg = {
        "schemaVersion": 1,
        "defaults": {"python": sys.executable, "timeoutSec": 60},
        "tools": tools,
    }
    path = tmp / "mcp_toolkit.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class TestConfigAndStatus(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # 假脚本
        self.fake_script = self.tmp / "fake_script.py"
        self.fake_script.write_text(
            "import sys, json\n"
            "print(json.dumps({'argc': len(sys.argv), 'args': sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        self.cfg_path = _write_toolkit_config(
            self.tmp, {"demo": {"script": self.fake_script, "group": "test"}}
        )
        self._old_env = os.environ.get("MCP_TOOLKIT_CONFIG")
        os.environ["MCP_TOOLKIT_CONFIG"] = str(self.cfg_path)

    def tearDown(self) -> None:
        if self._old_env is None:
            os.environ.pop("MCP_TOOLKIT_CONFIG", None)
        else:
            os.environ["MCP_TOOLKIT_CONFIG"] = self._old_env
        self._tmp.cleanup()

    def test_load_config(self) -> None:
        cfg = toolkit.load_config()
        self.assertEqual(cfg["schemaVersion"], 1)
        self.assertIn("demo", cfg["tools"])

    def test_build_status(self) -> None:
        cfg = toolkit.load_config()
        rows = toolkit.build_status(cfg)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["script_exists"])  # 临时脚本存在
        self.assertTrue(rows[0]["python_exists"])

    def test_run_script_ok(self) -> None:
        cfg = toolkit.load_config()
        result = toolkit._run_script(cfg, "demo", ["a", "b"])
        self.assertEqual(result["status"], "ok")
        payload = json.loads(result["stdout"])
        self.assertEqual(payload["args"], ["a", "b"])

    def test_run_script_missing_python(self) -> None:
        cfg = toolkit.load_config()
        # 手动改工具 python 为不存在路径
        cfg["tools"]["demo"]["python"] = str(self.tmp / "no_such_python.exe")
        result = toolkit._run_script(cfg, "demo", [])
        self.assertEqual(result["status"], "error")
        self.assertIn("解释器或脚本不存在", result["message"])


class TestToolFunctions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fake_script = self.tmp / "fake.py"
        self.fake_script.write_text("print('ok')\n", encoding="utf-8")
        self.cfg_path = _write_toolkit_config(
            self.tmp,
            {
                "transcribe_video": {"script": self.fake_script, "group": "transcribe"},
                "make_slideshow_video": {"script": self.fake_script, "group": "video"},
                "make_voiceover": {"script": self.fake_script, "group": "video"},
                "collect_bili_candidates": {"script": self.fake_script, "group": "collect"},
                "web_scrape": {"script": self.fake_script, "group": "research"},
                "collect_xhs": {"script": self.fake_script, "group": "collect"},
                "collect_toutiao": {"script": self.fake_script, "group": "collect"},
                "douyin_data_summary": {"group": "collect", "data_dir": str(self.tmp)},
            },
        )
        self._old_env = os.environ.get("MCP_TOOLKIT_CONFIG")
        os.environ["MCP_TOOLKIT_CONFIG"] = str(self.cfg_path)
        self._captured_args: list[list[str]] = []

        def fake_run(config, name, args):
            self._captured_args.append(args)
            return {"status": "ok", "tool": name, "args": args}

        self._patcher_args = fake_run
        self._orig_run = toolkit._run_script
        toolkit._run_script = fake_run  # type: ignore[assignment]

    def tearDown(self) -> None:
        toolkit._run_script = self._orig_run  # type: ignore[assignment]
        if self._old_env is None:
            os.environ.pop("MCP_TOOLKIT_CONFIG", None)
        else:
            os.environ["MCP_TOOLKIT_CONFIG"] = self._old_env
        self._tmp.cleanup()

    def test_transcribe_video_args(self) -> None:
        toolkit.transcribe_video("https://bilibili.com/video/BV1")
        self.assertEqual(self._captured_args, [["https://bilibili.com/video/BV1"]])

    def test_make_slideshow_args(self) -> None:
        toolkit.make_slideshow_video("s.json", "o.mp4")
        self.assertEqual(self._captured_args, [["s.json", "-o", "o.mp4"]])

    def test_make_slideshow_args_with_voice(self) -> None:
        toolkit.make_slideshow_video("s.json", "o.mp4", "zh-CN-YunjianNeural")
        self.assertEqual(
            self._captured_args, [["s.json", "-o", "o.mp4", "--voice", "zh-CN-YunjianNeural"]]
        )

    def test_make_voiceover_args(self) -> None:
        toolkit.make_voiceover("script.json", "out")
        self.assertEqual(self._captured_args, [["--script", "script.json", "--out-dir", "out"]])

    def test_collect_bili_args(self) -> None:
        toolkit.collect_bili_candidates(keywords="dsh 插件,deepseek", limit=20)
        self.assertEqual(
            self._captured_args,
            [["--keywords", "dsh 插件,deepseek", "--limit", "20"]],
        )

    def test_collect_bili_no_args(self) -> None:
        toolkit.collect_bili_candidates()
        self.assertEqual(self._captured_args, [[]])

    def test_web_scrape_args(self) -> None:
        toolkit.web_scrape("req.json")
        args = self._captured_args[0]
        self.assertEqual(args[0], "req.json")
        self.assertEqual(args[1], "--config")

    def test_collect_xhs_args(self) -> None:
        toolkit.collect_xhs()
        self.assertEqual(self._captured_args, [[]])

    def test_collect_toutiao_args(self) -> None:
        toolkit.collect_toutiao()
        self.assertEqual(self._captured_args, [[]])

    def test_douyin_data_summary(self) -> None:
        data = {
            "sec_user_id": "S1",
            "total": 2,
            "videos": [
                {"desc": "第一条", "duration": 100},
                {"desc": "第二条", "duration": 200},
            ],
        }
        (self.tmp / "douyin_user_data_target.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        out = json.loads(toolkit.douyin_data_summary())
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["accounts"][0]["total_videos"], 2)
        self.assertEqual(out["accounts"][0]["latest_desc"], "第一条")


class TestSyncAgentMcp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_json_add_and_idempotent(self) -> None:
        path = self.tmp / "claude.json"
        path.write_text(json.dumps({"mcpServers": {"codex-api-mcp": {"command": "x"}}}), encoding="utf-8")
        entry = sync_agent_mcp._entry_claude()
        result = sync_agent_mcp.ensure_json(path, False, False)
        self.assertTrue(result.startswith("added"), result)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["mcpServers"]["toolkit"], entry)
        # 幂等
        self.assertEqual(sync_agent_mcp.ensure_json(path, False, False), "ok")
        self.assertEqual(sync_agent_mcp.ensure_json(path, False, True), "ok")
        # verify 缺时为 missing
        path2 = self.tmp / "claude2.json"
        path2.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        self.assertEqual(sync_agent_mcp.ensure_json(path2, False, True), "missing")

    def test_yaml_add_and_idempotent(self) -> None:
        path = self.tmp / "config.yaml"
        path.write_text(
            "mcp_servers:\n"
            "  codex-api-mcp:\n"
            "    command: x\n"
            "sessions:\n"
            "  auto_archive: true\n",
            encoding="utf-8",
        )
        result = sync_agent_mcp.ensure_yaml(path, False, False)
        self.assertTrue(result.startswith("added"), result)
        text = path.read_text(encoding="utf-8")
        self.assertIn("  toolkit:", text)
        self.assertIn("sessions:", text)  # 不破坏后续内容
        self.assertEqual(sync_agent_mcp.ensure_yaml(path, False, False), "ok")
        self.assertEqual(sync_agent_mcp.ensure_yaml(path, False, True), "ok")

    def test_yaml_no_root(self) -> None:
        path = self.tmp / "config2.yaml"
        path.write_text("sessions:\n  auto_archive: true\n", encoding="utf-8")
        self.assertEqual(sync_agent_mcp.ensure_yaml(path, False, False), "no-root")

    def test_toml_add_and_idempotent(self) -> None:
        path = self.tmp / "config.toml"
        path.write_text('[model]\nname = "x"\n', encoding="utf-8")
        result = sync_agent_mcp.ensure_toml(path, False, False)
        self.assertTrue(result.startswith("added"), result)
        text = path.read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.toolkit]", text)
        self.assertIn("[model]", text)  # 不破坏已有 section
        self.assertEqual(sync_agent_mcp.ensure_toml(path, False, False), "ok")


if __name__ == "__main__":
    unittest.main()
