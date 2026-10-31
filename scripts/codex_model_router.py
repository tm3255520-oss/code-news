#!/usr/bin/env python3
"""codex_model_router.py — 单一 Codex 供应商端点，按模型名分流到各上游。

背景：Codex 桌面端的 model_provider 是全局单值，模型选择器只换模型名、不换供应商。
因此把 Codex 指向本路由（一个端点），由路由按模型名决定真正打哪家上游：
选择器里选哪个模型都能直接跑，永远不用切 provider，对话列表也不会因换 provider 而隐藏。

分流规则（按前缀匹配，先长后短）：
  glm-*                       -> 智谱 BigModel        （本地 8975 翻译代理）
  doubao-*                    -> 火山方舟 Ark         （本地 8976 翻译代理）
  qwen*, kimi-*               -> 阿里百炼 DashScope   （本地 8972 翻译代理）
  agnes-*                     -> Agnes apihub         （本地 8973 翻译代理）
  moonshotai/*, nvidia/*, minimaxai/*, ibm/*, meta/*, mistralai/*  -> NVIDIA（本地 8971 翻译代理）
  MiniMax-*                   -> MiniMax 官方         （原生 responses，直连）
  deepseek-*                  -> DeepSeek 官方        （原生 responses，直连）

用法：
  python scripts/codex_model_router.py --port 8970

配置到 Codex（config.toml，沿用现有 provider id 以免旧对话列表被隐藏）：
  [model_providers.deepseek]
  base_url = "http://127.0.0.1:8970/v1"
  wire_api = "responses"
  env_key = "DEEPSEEK_API_KEY"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path(os.path.expanduser("~")) / ".codex" / "models.json"


def _local(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1/responses"


# 上游路由：前缀 -> (目标 responses 地址, 密钥环境变量)
ROUTES: list[tuple[str, str, str]] = [
    ("glm-", _local(8975), "ZHIPU_API_KEY"),
    ("doubao-", _local(8976), "ARK_API_KEY"),
    ("qwen", _local(8972), "BAILIAN_API_KEY"),
    ("kimi-", _local(8972), "BAILIAN_API_KEY"),
    ("agnes-", _local(8973), "AGNES_API_KEY_4"),
    # 必须排在 "deepseek-" 之前：deepseek-ai/* 是 NVIDIA 路由上的模型，不是 DeepSeek 官方
    ("deepseek-ai/", _local(8971), "NVIDIA_API_KEY"),
    ("moonshotai/", _local(8971), "NVIDIA_API_KEY"),
    ("nvidia/", _local(8971), "NVIDIA_API_KEY"),
    ("minimaxai/", _local(8971), "NVIDIA_API_KEY"),
    ("ibm/", _local(8971), "NVIDIA_API_KEY"),
    ("meta/", _local(8971), "NVIDIA_API_KEY"),
    ("mistralai/", _local(8971), "NVIDIA_API_KEY"),
    ("MiniMax-", "https://api.minimaxi.com/v1/responses", "MINIMAX_API_KEY"),
    ("deepseek-", "https://api.deepseek.com/v1/responses", "DEEPSEEK_API_KEY"),
]

# OpenCode Zen 匿名免费通道（本地 8977 翻译代理）。
# 2026-10-04：Zen 的免费 id 没有统一前缀，且部分与既有前缀撞车（如 xxx-flash-free 会
# 被 qwen/deepseek 前缀抢走），所以按精确名单判定，并必须排在前缀匹配之前。key_env
# 留空 —— 匿名通道不需要密钥。名单经 2026-10-04 逐个实测，只收上游确实可用的 9 个。
ZEN_URL = _local(8977)
ZEN_FREE_MODELS = frozenset({
    "big-pickle",
    "mimo-v2.6-flash-free",
    "space-bunny-free",
    "longcat-2.5-preview-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free",
    "fledge-alpha-free",
    "ling-3.1-flash-free",
})


def _lookup_key(name: str) -> str:
    """进程环境 → Windows 用户环境 → ~/.hermes/.env。

    2026-09-26：NVIDIA 等 key 已统一收归 ~/.hermes/.env 一处（注册表副本已清理），
    故追加 .env 回退；否则路由取不到 key 会直接 400「环境变量 X 为空」。
    agnes-3.0-flash 报的正是这个 —— AGNES_API_KEY_4 从来只存在于 .env 里，
    而本路由此前只读进程环境/注册表，所以 Codex 走 agnes 模型一直是断的。
    """
    v = os.environ.get(name)
    if v:
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            v, _ = winreg.QueryValueEx(k, name)
            if str(v):
                return str(v)
    except OSError:
        pass
    env_file = os.path.expanduser(r"~\.hermes\.env")
    try:
        with open(env_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.partition("=")[2].strip()
    except OSError:
        pass
    return ""


def route_for(model: str) -> tuple[str, str, str] | None:
    """返回 (prefix, url, key_env)；无匹配返回 None。"""
    if model in ZEN_FREE_MODELS:
        return "", ZEN_URL, ""
    for prefix, url, key_env in ROUTES:
        if model.startswith(prefix):
            return prefix, url, key_env
    return None


def routable_models() -> list[str]:
    """Codex 模型目录里能路由出去的模型（供 GET /v1/models）。"""
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []
    return sorted(m["slug"] for m in data.get("models", [])
                  if route_for(str(m.get("slug", ""))) is not None
                  and not m.get("hidden"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a) -> None:  # quiet
        return

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/v1/models") or self.path.rstrip("/").endswith("/models"):
            self._send_json({"object": "list",
                             "data": [{"id": s, "object": "model"} for s in routable_models()]})
            return
        self._send_json({"object": "error", "message": "not found"}, 404)

    def do_POST(self):
        if not self.path.endswith("/responses"):
            self._send_json({"object": "error", "message": "not found"}, 404)
            return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"object": "error", "message": "bad json"}, 400)
            return

        model = str(body.get("model", ""))
        route = route_for(model)
        if route is None:
            self._send_json({
                "error": {"code": "no_route",
                          "message": f"模型路由未登记 {model!r}；请在 "
                                     f"scripts/codex_model_router.py 的 ROUTES 里加一条前缀规则"}},
                400)
            return

        _prefix, url, key_env = route
        key = _lookup_key(key_env)
        if key_env and not key:
            self._send_json({"error": {"code": "no_key",
                                       "message": f"环境变量 {key_env} 为空，无法调用 {model}"}}, 400)
            return

        headers = {"Content-Type": "application/json",
                   "Accept": "text/event-stream"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(url, data=raw, method="POST", headers=headers)
        try:
            upstream = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:2000]
            self._send_json({"error": {"code": str(e.code), "message": detail}}, e.code)
            return
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": {"code": "upstream", "message": str(e)[:500]}}, 502)
            return

        self.send_response(200)
        self.send_header("Content-Type", upstream.headers.get("Content-Type", "text/event-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            while True:
                chunk = upstream.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8970)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[router] listening on http://127.0.0.1:{args.port}/v1 "
          f"({len(ROUTES)} prefix routes, {len(routable_models())} catalog models routable)",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
