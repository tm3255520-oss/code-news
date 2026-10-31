"""Smoke test: 用真实 MCP stdio 协议握手验证两个服务器可被客户端连接。

用法：python scripts/smoke_mcp_servers.py
通过标准 = 两个服务器 initialize / tools/list / tools/call 全部返回预期结果，退出码 0。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "smoke", "version": "1.0"},
    },
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


def run_handshake(server: str, call: dict) -> dict:
    proc = subprocess.Popen(
        [PYTHON, str(ROOT / "scripts" / server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        bufsize=1,
    )

    def send(msg: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def read_response() -> dict:
        assert proc.stdout is not None
        line = proc.stdout.readline()
        if not line:
            return {}
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {}

    responses: dict[int, dict] = {}
    send(INIT)
    r = read_response()
    if r:
        responses[1] = r
    send(INITIALIZED)
    send(LIST)
    r = read_response()
    if r:
        responses[2] = r
    send(call)
    r = read_response()
    if r:
        responses[3] = r
    try:
        assert proc.stdin is not None
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return responses


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        codex_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "codex_api_run",
                "arguments": {
                    "action": "draft_article",
                    "topic": "smoke test",
                    "request_id": "smoke-001",
                    "output_dir": tmp,
                    "platforms": "toutiao",
                    "provider": "packet",
                },
            },
        }
        scraper_call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "web_scraper_run",
                "arguments": {
                    "action": "normalize_record",
                    "platform": "toutiao",
                    "record_json": json.dumps(
                        {"title": "smoke", "url": "https://example.com"}, ensure_ascii=False
                    ),
                },
            },
        }

        for name, server, call, expect_status in (
            ("codex-api", "mcp_codex_api_server.py", codex_call, "queued"),
            ("web-scraper", "mcp_web_scraper_server.py", scraper_call, "ok"),
        ):
            responses = run_handshake(server, call)
            init_ok = 1 in responses and "result" in responses[1]
            list_ok = 2 in responses and "tools" in responses[2]["result"]
            call_resp = responses.get(3, {})
            text = (
                call_resp.get("result", {})
                .get("content", [{}])[0]
                .get("text", "")
                if "result" in call_resp
                else ""
            )
            call_ok = expect_status in text
            status = "PASS" if (init_ok and list_ok and call_ok) else "FAIL"
            if status == "FAIL":
                ok = False
            print(f"[{status}] {name}: init={init_ok} list={list_ok} call({expect_status})={call_ok}")

    print("SMOKE_RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
