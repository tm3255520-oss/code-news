"""Smoke test: 用真实 MCP stdio 协议握手验证 toolkit-mcp 服务器可被客户端连接。

用法：python scripts/smoke_toolkit.py
通过标准 = initialize / tools/list / tools/call(toolkit_status) 全部返回预期，退出码 0。
覆盖：协议层握手 + 工具枚举 + status 工具调用（不触发外部宿主机脚本）。
"""
from __future__ import annotations

import json
import subprocess
import sys
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
        "clientInfo": {"name": "smoke-toolkit", "version": "1.0"},
    },
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
CALL = {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": "toolkit_status", "arguments": {}},
}


def run_handshake(server: str) -> dict:
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
    send(CALL)
    r = read_response()
    if r:
        responses[3] = r
    try:
        assert proc.stdin is not None
        proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return responses


def main() -> int:
    responses = run_handshake("mcp_toolkit_server.py")
    init_ok = 1 in responses and "result" in responses[1]
    list_ok = 2 in responses and "tools" in responses[2]["result"]
    tools = responses[2].get("result", {}).get("tools", []) if list_ok else []
    has_status = any(t.get("name") == "toolkit_status" for t in tools)
    call_resp = responses.get(3, {})
    text = ""
    if "result" in call_resp:
        content = call_resp["result"].get("content", [{}])
        text = content[0].get("text", "") if content else ""
    call_ok = bool(text) and ("tools" in text or "status" in text)

    ok = init_ok and list_ok and has_status and call_ok
    print(f"[{'PASS' if ok else 'FAIL'}] toolkit-mcp: init={init_ok} list={list_ok} "
          f"toolkit_status_present={has_status} call={call_ok}")
    if not ok:
        print("responses:", json.dumps(responses, ensure_ascii=False)[:2000])
    print("SMOKE_TOOLKIT_RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
