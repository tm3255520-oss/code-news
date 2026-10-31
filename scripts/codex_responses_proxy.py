#!/usr/bin/env python3
"""codex_responses_proxy.py - 让 Codex(仅 responses) 调 NVIDIA(仅 chat) 模型的本地翻译代理。

背景：Codex 0.15x 移除了 chat wire，自定义 provider 只支持 OpenAI Responses API；
而 NVIDIA integrate API 的 /v1/responses 是非标准 schema（要求 format 字段），
但其 /v1/chat/completions 是标准 OpenAI chat 补全。本代理在一个本地端口上暴露
标准 /v1/responses，把 Codex 的流式请求翻译成 NVIDIA chat，再把 NVIDIA 的流
式回包翻译成 Responses SSE 事件，从而让 nemotron / deepseek 等模型可在 Codex 里调用。

用法：
  NVIDIA_API_KEY=<key> python scripts/codex_responses_proxy.py --port 8971

配置到 Codex（config.toml）：
  [model_providers.nvidia]
  name = "nvidia"
  base_url = "http://127.0.0.1:8971/v1"
  wire_api = "responses"
  env_key = "NVIDIA_API_KEY"
"""
from __future__ import annotations

import json
import hashlib
import os
import secrets
import subprocess
import sys
import time
import uuid
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _env_or_dotenv(name: str) -> str:
    """进程环境 → ~/.hermes/.env。

    2026-09-26：各家 key 统一收归 ~/.hermes/.env（注册表里的 NVIDIA 副本已清理）。
    本代理由计划任务 codex-nvidia-responses-proxy 直接拉起、没有启动脚本注入 key，
    因此必须自己能读 .env —— 否则下次重启会以空 key 启动，Codex 的 nvidia 系模型全断。
    经 8972/8973/8975/8976 启动脚本拉起时，脚本已显式注入 NVIDIA_API_KEY，此处不会生效。
    """
    v = os.environ.get(name)
    if v:
        return v
    try:
        with open(os.path.expanduser(r"~/.hermes/.env"), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.partition("=")[2].strip()
    except OSError:
        pass
    return ""


NVIDIA_BASE = os.environ.get("NVIDIA_BASE", "https://integrate.api.nvidia.com/v1")
NVIDIA_KEY = _env_or_dotenv("NVIDIA_API_KEY")

try:
    from nvidia_key_events import log_event  # 负载埋点：403/429 写入事件日志（失败不影响主流程）
except Exception:
    def log_event(*_a, **_k):  # type: ignore
        pass
PORT = int(os.environ.get("CODECX_PROXY_PORT", "8971"))

# ---- OpenCode Zen 免费通道档位（CODEX_PROXY_PROFILE=zen）--------------------------------
# 2026-10-04：Codex 只认 Responses，而 Zen 匿名免费通道是 chat/completions；该通道自
# 2026-09-16 起有两道门 —— 关联头必须是 OpenCode 规范的 ses_ 形状，且请求体必须流式
# 并携带名为 bash/read 的 function 工具（与 opencode2dsh 插件同规则，见其 src/adapter/ids.ts
# 与 src/adapter/messages.ts）。本档位只补齐这两件事。
# 默认关闭：8971/8972/8973/8975/8976 五个 provider 的既有行为一字不变。
PROFILE = os.environ.get("CODEX_PROXY_PROFILE", "").strip().lower()
ZEN = PROFILE == "zen"
ZEN_KEY = "public"  # 匿名通道的 key 就是字面量，不涉及任何机密
ZEN_UA = "opencode/1.18.31 (linux x64; node26.7.0)"
ZEN_GATE_TOOLS = ("bash", "read")
_B62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _b62(value: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_B62[value % 62])
        value //= 62
    return "".join(reversed(out))


def _zen_ids(messages) -> dict:
    """派生 Zen 关联 id：会话由首条用户消息 sha256 得稳定 ses_ 形状，请求 id 每次随机。"""
    seed = ""
    for m in messages or []:
        if isinstance(m, dict) and m.get("role") == "user":
            enc = json.dumps(m.get("content"), ensure_ascii=False)
            if enc and enc != "null":
                seed = enc
                break
    if not seed:
        seed = "fallback"
    digest = hashlib.sha256(("ses\u0000" + seed).encode("utf-8")).digest()
    session = "ses_" + digest[:6].hex() + _b62(int.from_bytes(digest[6:16], "big"), 14)
    project = "prj_" + hashlib.sha256(b"prj\x00opencode2dsh:default-project").hexdigest()[:24]
    return {"session": session, "request": "req_" + secrets.token_hex(16), "project": project}


def _zen_headers(payload: dict) -> dict:
    ids = _zen_ids(payload.get("messages"))
    return {
        "User-Agent": ZEN_UA,
        "x-opencode-client": "cli",
        "x-opencode-session": ids["session"],
        "x-session-affinity": ids["session"],
        "X-Session-Id": ids["session"],
        "x-opencode-request": ids["request"],
        "x-opencode-project": ids["project"],
    }


def _zen_gate(payload: dict) -> None:
    """就地补齐免费通道的 agent 形状：只追加缺失的 bash/read 桩工具。"""
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    names = {t.get("function", {}).get("name") for t in tools if isinstance(t, dict)}
    missing = [n for n in ZEN_GATE_TOOLS if n not in names]
    if not missing:
        return
    payload["tools"] = list(tools) + [{
        "type": "function",
        "function": {"name": n, "description": "Reserved for the host runtime; do not call it.",
                     "parameters": {"type": "object", "properties": {}}},
    } for n in missing]
    if not tools:
        payload["tool_choice"] = "none"


def _now() -> int:
    return int(time.time() * 1000)


def _tool_to_chat(tools: list | None) -> list | None:
    if not tools:
        return None
    out = []
    for t in tools:
        if t.get("type") != "function":
            continue
        out.append({
            "type": "function",
            "function": {
                "name": t.get("name"),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        })
    return out or None


def _content_to_chat(content):
    """Responses 的 content -> chat completions 的 content。

    纯文本时返回字符串（与原行为一致）；带图时返回 parts 列表，
    把 input_image 转成 chat 的 image_url，否则图片会被静默丢弃。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts, images = [], []
    for p in content:
        if not isinstance(p, dict):
            continue
        ptype = p.get("type")
        if ptype in ("input_text", "output_text", "text"):
            texts.append(p.get("text", ""))
        elif ptype in ("input_image", "image_url"):
            url = p.get("image_url") or p.get("url") or ""
            if isinstance(url, dict):
                url = url.get("url", "")
            if url:
                images.append({"type": "image_url", "image_url": {"url": url}})
    if not images:
        return "".join(texts)
    parts: list[dict] = []
    if texts:
        parts.append({"type": "text", "text": "".join(texts)})
    parts.extend(images)
    return parts


def _content_to_text(content) -> str:
    """纯文本视图（保留原语义，供只接受文本的调用点使用）。"""
    out = _content_to_chat(content)
    if isinstance(out, str):
        return out
    return "".join(p.get("text", "") for p in out if p.get("type") == "text")


def _input_to_messages(instructions: str | None, inp) -> list[dict]:
    msgs: list[dict] = []
    if instructions:
        msgs.append({"role": "system", "content": instructions})
    if isinstance(inp, str):
        msgs.append({"role": "user", "content": inp})
        return msgs
    if not isinstance(inp, list):
        return msgs

    # collect consecutive function_call items into one assistant tool_calls block
    pending_calls: list[dict] = []

    def flush_calls():
        nonlocal pending_calls
        if pending_calls:
            msgs.append({
                "role": "assistant",
                "content": None,
                "tool_calls": pending_calls,
            })
            pending_calls = []

    for item in inp:
        itype = item.get("type")
        if itype == "message":
            flush_calls()
            role = item.get("role", "user")
            if role == "developer":
                # Codex(Responses) 用 developer 表达系统指令；NVIDIA chat 只认 system
                role = "system"
            c = _content_to_chat(item.get("content"))
            if c:
                msgs.append({"role": role, "content": c})
        elif itype == "function_call":
            pending_calls.append({
                "id": item.get("call_id") or item.get("id"),
                "type": "function",
                "function": {
                    "name": item.get("name"),
                    "arguments": item.get("arguments") or "{}",
                },
            })
        elif itype == "function_call_output":
            flush_calls()
            msgs.append({
                "role": "tool",
                "tool_call_id": item.get("call_id"),
                "content": item.get("output", ""),
            })
        else:
            # reasoning / web_search_call etc: ignore
            pass
    flush_calls()
    return msgs


def _chat_payload(model: str, msgs: list[dict], body: dict) -> dict:
    payload = {
        "model": model,
        "messages": msgs,
        "stream": True,
    }
    tools = _tool_to_chat(body.get("tools"))
    if tools:
        payload["tools"] = tools
        tc = body.get("tool_choice")
        if tc:
            payload["tool_choice"] = tc
    mt = body.get("max_output_tokens")
    if mt:
        payload["max_tokens"] = mt
    r = body.get("reasoning")
    if isinstance(r, dict) and r.get("effort"):
        if ZEN:
            # 2026-10-04 实测：既不接受 reasoning 对象，也不普遍接受 reasoning_effort
            # —— big-pickle 接受 high/none 却不接受 "none"… 具体为：big-pickle/mimo 收
            # high，ling-3.1-flash-free 收 high 直接 "Endpoint is unavailable"，而两者不带
            # 该参数都正常。故一律不透传，交给上游默认值（模型自身照常输出 reasoning）。
            pass
        else:
            payload.setdefault("reasoning", {}).setdefault("effort", r["effort"])
    if ZEN:
        _zen_gate(payload)
    return payload


def _curl_attempt(payload: dict):
    """发起一次 curl 调上游（body 走 stdin，避免临时文件竞态），返回 proc。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if ZEN:
        # 免费通道要求整套 CLI 同形关联头，缺一个就是 403 FreeTierError。
        cmd = ["curl.exe", "-N", "-sS", "-m", "300"]
        for k, v in _zen_headers(payload).items():
            cmd += ["-H", f"{k}: {v}"]
        cmd += ["-H", "Authorization: Bearer " + ZEN_KEY]
    else:
        cmd = ["curl.exe", "-N", "-sS", "-m", "300",
               "-H", "Authorization: Bearer " + NVIDIA_KEY]
    cmd += [
        "-H", "Content-Type: application/json",
        "-H", "Accept: text/event-stream",
        "--data-binary", "@-",
        NVIDIA_BASE + "/chat/completions",
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    proc.stdin.write(data)
    proc.stdin.close()
    return proc


def _retriable(err: dict) -> bool:
    code = str(err.get("code", ""))
    msg = str(err.get("message", ""))
    return any(x in code for x in ("503", "429", "500", "502", "504")) or "overload" in msg.lower()


def _error_from_body(lines: list[str], returncode) -> dict:
    """上游没回 SSE（纯 JSON 错误体 / HTML / 空响应）时，把它整理成 error 对象。"""
    text = " ".join(lines).strip()[:500]
    code = str(returncode) if returncode else "upstream"
    if text:
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            err = obj.get("error")
            if isinstance(err, dict):
                return {"code": str(err.get("code") or code),
                        "message": str(err.get("message") or text)[:500]}
            if isinstance(err, str):
                return {"code": code, "message": err[:500]}
            for key in ("detail", "message"):
                if obj.get(key):
                    return {"code": code, "message": str(obj[key])[:500]}
        return {"code": code, "message": text}
    return {"code": code,
            "message": f"upstream closed the stream without data (curl exit {returncode})"}


def _stream_chat(model: str, payload: dict):
    """生成器：用 curl 调 NVIDIA，逐个产出 SSE 的 JSON 事件。
    首个事件若是可重试的上游错误（503/429/…），自动重试；重试仍失败或上游没回
    SSE 时，产出一个 error 事件，绝不静默返回空结果。"""
    attempts = 0
    last_error: dict | None = None
    while attempts < 4:
        attempts += 1
        proc = _curl_attempt(payload)
        retry = False
        first = None
        noise: list[str] = []
        saw_data = False
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                if len(noise) < 40:
                    noise.append(line)
                continue
            saw_data = True
            datum = line[5:].strip()
            if datum == "[DONE]":
                return
            try:
                obj = json.loads(datum)
            except Exception:
                continue
            if first is None:
                first = obj
                if isinstance(obj, dict) and obj.get("error"):
                    try:
                        log_event(model=model, status=str(obj["error"].get("code", "")),
                                  note=str(obj["error"].get("message", ""))[:200])
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()
                    last_error = obj["error"]
                    if _retriable(obj["error"]):
                        retry = True
                        break
                    yield obj
                    return
            yield obj
        if retry:
            continue
        if not saw_data:
            # 上游回的不是 SSE：纯 JSON 错误体、HTML 或空响应，原样上报
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            last_error = _error_from_body(noise, proc.returncode)
            if _retriable(last_error):
                try:
                    log_event(model=model, status=str(last_error.get("code", "")),
                              note=str(last_error.get("message", ""))[:200])
                except Exception:
                    pass
                continue
            yield {"error": last_error}
            return
        return
    yield {"error": last_error or {"code": "upstream",
                                   "message": f"upstream failed after {attempts} attempts"}}


def _sse_event(item: dict) -> str:
    return "data: " + json.dumps(item) + "\n\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a) -> None:  # quiet
        return

    def do_GET(self):
        # 自检口：确认这个端口真正生效的档位与上游（排查「启动脚本环境没传进去」时用）
        self._json({"profile": PROFILE or "default/nvidia", "target": NVIDIA_BASE,
                    "zen": ZEN, "pid": os.getpid()}, 200)

    def do_POST(self):
        if not self.path.endswith("/responses"):
            self._json({"object": "error", "message": "not found"}, 404)
            return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json({"object": "error", "message": "bad json"}, 400)
            return
        model = body.get("model", "")
        msgs = _input_to_messages(body.get("instructions"), body.get("input"))
        if not msgs:
            msgs = [{"role": "user", "content": "hello"}]
        payload = _chat_payload(model, msgs, body)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        rid = "resp_" + uuid.uuid4().hex
        created = _now()

        def emit(item):
            self.wfile.write(_sse_event(item).encode("utf-8"))
            self.wfile.flush()

        emit({"type": "response.created", "response": {
            "id": rid, "object": "response", "created_at": created, "model": model,
            "status": "in_progress", "output": [], "usage": None}})

        try:
            event_iter = _stream_chat(model, payload)
        except Exception as e:
            emit({"type": "response.failed", "response": {
                "id": rid, "object": "response", "created_at": created, "model": model,
                "status": "failed", "error": {"code": "upstream", "message": str(e)[:500]}}})
            emit({"type": "response.completed", "response": {
                "id": rid, "object": "response", "created_at": created, "model": model,
                "status": "failed", "output": []}})
            return

        item_id = "msg_" + uuid.uuid4().hex
        text_buf: list[str] = []
        calls: dict[int, dict] = {}
        input_tokens = 0
        output_tokens = 0
        finished = False

        try:
            for chunk in event_iter:
                if chunk.get("error"):
                    emit({"type": "response.failed", "response": {
                        "id": rid, "object": "response", "created_at": created, "model": model,
                        "status": "failed", "error": {"code": "upstream", "message": chunk["error"].get("message", "")[:500]}}})
                    emit({"type": "response.completed", "response": {
                        "id": rid, "object": "response", "created_at": created, "model": model,
                        "status": "failed", "output": []}})
                    return
                usage = chunk.get("usage")
                if usage:
                    input_tokens = usage.get("prompt_tokens", input_tokens)
                    output_tokens = usage.get("completion_tokens", output_tokens)
                choices = chunk.get("choices") or []
                for ch in choices:
                    delta = ch.get("delta") or {}
                    finish = ch.get("finish_reason")
                    if finish:
                        finished = True
                    content = delta.get("content")
                    if content:
                        if not text_buf:
                            emit({"type": "response.output_item.added", "output_index": 0, "item": {
                                "id": item_id, "type": "message", "role": "assistant",
                                "status": "in_progress", "content": []}})
                            emit({"type": "response.content_part.added", "item_id": item_id,
                                  "output_index": 0, "content_index": 0, "part": {
                                      "type": "output_text", "text": "", "annotations": []}})
                        text_buf.append(content)
                        emit({"type": "response.output_text.delta", "item_id": item_id,
                              "output_index": 0, "content_index": 0, "delta": content})
                    tcs = delta.get("tool_calls")
                    if tcs:
                        for tc in tcs:
                            if ZEN and (tc.get("function") or {}).get("name") in ZEN_GATE_TOOLS:
                                continue  # 桩工具仅供过门；真被调用也不透传给 Codex
                            idx = tc.get("index", 0)
                            call = calls.setdefault(idx, {"id": tc.get("id"), "name": "", "args": ""})
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                call["name"] += fn["name"]
                            if fn.get("arguments"):
                                call["args"] += fn["arguments"]
                            if not call["id"]:
                                call["id"] = tc.get("id")
                            emit({"type": "response.output_text.delta",
                                  "item_id": "call_" + str(idx), "output_index": 0,
                                  "content_index": 0, "delta": fn.get("arguments", "")})

            # finalize: build output
            output_items = []
            if text_buf:
                text = "".join(text_buf)
                emit({"type": "response.output_text.done", "item_id": item_id,
                      "output_index": 0, "content_index": 0, "text": text})
                emit({"type": "response.content_part.done", "item_id": item_id,
                      "output_index": 0, "content_index": 0, "part": {
                          "type": "output_text", "text": text, "annotations": []}})
                emit({"type": "response.output_item.done", "output_index": 0, "item": {
                    "id": item_id, "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}})
                output_items.append({
                    "id": item_id, "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]})
            for idx in sorted(calls):
                c = calls[idx]
                cid = "call_" + str(idx)
                emit({"type": "response.output_item.added", "output_index": len(output_items), "item": {
                    "id": cid, "type": "function_call", "status": "in_progress",
                    "call_id": c["id"] or cid, "name": c["name"], "arguments": c["args"]}})
                emit({"type": "response.output_item.done", "output_index": len(output_items), "item": {
                    "id": cid, "type": "function_call", "status": "completed",
                    "call_id": c["id"] or cid, "name": c["name"], "arguments": c["args"]}})
                output_items.append({
                    "id": cid, "type": "function_call", "status": "completed",
                    "call_id": c["id"] or cid, "name": c["name"], "arguments": c["args"]})

            status = "completed" if (output_items or finished) else "incomplete"
            final = {
                "id": rid, "object": "response", "created_at": created, "model": model,
                "status": status, "output": output_items,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
            }
            emit({"type": "response.completed", "response": final})
        except Exception as e:
            emit({"type": "response.failed", "response": {
                "id": rid, "object": "response", "created_at": created, "model": model,
                "status": "failed", "error": {"code": "proxy", "message": str(e)[:300]}}})
            emit({"type": "response.completed", "response": {
                "id": rid, "object": "response", "created_at": created, "model": model,
                "status": "failed", "output": []}})
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _json(self, obj, code):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = PORT
    if len(sys.argv) >= 3 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    if not ZEN and not NVIDIA_KEY:
        print("[proxy] WARNING: NVIDIA_API_KEY env not set", file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[proxy] listening on http://127.0.0.1:{port}/v1 (target {NVIDIA_BASE}, profile "
          f"{PROFILE or 'default/nvidia'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
