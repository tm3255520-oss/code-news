#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watch_nvidia_keys.py — NVIDIA Key 探活：把「限流」和「别的故障」分开

背景（NVIDIA NIM 免费通道）：同样是失败，处理方式相反，必须先分清是哪一种：
  • 403 账号级权限回收 —— 等 1-7 天自愈，不要改配置
  • 429 模型级限流 —— 换模型即可，免费额度的正常现象
  • 404/410 —— 该模型已下架（换模型，不是 key 的问题）
  • 探活失败（超时/连不上）—— 拿不到响应，无法判断；这一类最危险，
    因为旧版脚本把「测不出来」和「一切正常」都表现为静默输出。

输出约定（适配 cron no_agent 模式）：
  - 首次运行 / 状态有变化 / 出现需处置状态（429、探活失败、401）→ 输出报告
  - 全 200，或仅稳定在 403（等自愈中）→ 空输出，静默
状态文件：~/.hermes/cache/nvidia_key_watch.json（供周报「Key 健康」表读取）

用法：
  python scripts/watch_nvidia_keys.py            # 正常探活并写状态（cron 用）
  python scripts/watch_nvidia_keys.py --dry-run  # 只探活并打印，不写状态
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
STATE_FILE = HERMES_HOME / "cache" / "nvidia_key_watch.json"
BASE_URL = "https://integrate.api.nvidia.com/v1"

# 监控范围：新 4 账号（acct-a/b/c/d，各 1 主 1 备）+ 旧槽位。
# 旧槽位是过渡期保留的：代码已切到新账号，但 config.yaml/Codex 代理还引用旧名，
# 观察一天确认无误后再随 legacy 组一起退役（届时删掉下面 legacy 这一段即可）。
KEY_VARS = [
    # 新：acct-a/b/c/d
    "NVIDIA_API_KEY_A", "NVIDIA_API_KEY_A_SPARE",
    "NVIDIA_API_KEY_B", "NVIDIA_API_KEY_B_SPARE",
    "NVIDIA_API_KEY_C", "NVIDIA_API_KEY_C_SPARE",
    "NVIDIA_API_KEY_D", "NVIDIA_API_KEY_D_SPARE",
    # 旧（legacy-2026-09，过渡期）
    "NVIDIA_API_KEY_A1", "NVIDIA_API_KEY_B1", "NVIDIA_API_KEY_C1", "NVIDIA_API_KEY_D1",
    "NVIDIA_API_KEY",
]

# 探活模型按序取第一个在架的：稳定优先，且不会因为自己下架而让所有 key 误判。
# 2026-09-26 换：nvidia/nemotron-3-super-120b-a12b 实测带 Deprecation: 2026-10-03 头
# （7 天后弃用），降到 ultra-550b 打头；gpt-oss-20b 当天 8 把 key 全超时，只留作最后兜底。
PROBE_MODEL_PREFERENCE = [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "moonshotai/kimi-k3",
    "z-ai/glm-5.3",
    "openai/gpt-oss-20b",
]

# 需要处置的状态：静默策略只对 200 与稳定 403 生效
ATTENTION = {"429", "timeout", "conn-error", "error", "no-key", "401", "5xx"}

LABEL = {
    "200": "可用",
    "401": "key 无效/被吊销（要换 key）",
    "403": "账号级权限回收（等 1-7 天自愈，勿动配置）",
    "404": "探活模型不存在",
    "410": "探活模型已下架",
    "429": "模型级限流（免费额度，换模型即可）",
    "5xx": "上游 5xx（服务端问题，重试/换模型）",
    "timeout": "探活超时（拿不到响应，不能判断是否限流）",
    "conn-error": "连不上（网络/DNS/代理问题）",
    "no-key": "未配置该 key",
    "error": "探活异常",
}

ICON = {"200": "✅", "403": "⏳", "429": "🔁", "401": "❌", "404": "❓", "410": "❓"}


def classify(code: int) -> str:
    if code == 200:
        return "200"
    if code >= 500:
        return "5xx"
    return str(code)


def load_env() -> dict:
    env: dict = {}
    path = HERMES_HOME / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def resolve_key(var: str, env: dict) -> str:
    return env.get(var) or os.environ.get(var, "")


def probe_key(key: str, model: str, timeout: int = 30) -> str:
    """对一把 key 发一次最小对话请求，返回状态标签（绝不抛异常）。"""
    if not key:
        return "no-key"
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "好"}],
                       "max_tokens": 5}).encode("utf-8")
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return classify(int(getattr(resp, "status", 200)))
    except urllib.error.HTTPError as e:
        return classify(int(e.code))
    except (socket.timeout, TimeoutError):
        return "timeout"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        return "timeout" if isinstance(reason, (socket.timeout, TimeoutError)) else "conn-error"
    except Exception:
        return "error"


def fetch_catalog(key: str, timeout: int = 60) -> list[str]:
    """拉在架模型目录；失败返回空列表（探活模型退化为偏好列表首个）。"""
    if not key:
        return []
    req = urllib.request.Request(BASE_URL + "/models",
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return [it["id"] for it in (data.get("data") or []) if it.get("id")]
    except Exception:
        return []


def pick_probe_model(catalog: list[str]) -> str:
    for m in PROBE_MODEL_PREFERENCE:
        if m in catalog:
            return m
    for m in catalog:
        if "/" in m and not re.search(r"guard|safety|embed|retriev|parse|reward", m, re.I):
            return m
    return PROBE_MODEL_PREFERENCE[0]


def needs_attention(status: str) -> bool:
    return status in ATTENTION


def should_emit(current: dict, last: dict) -> bool:
    if not last:
        return True
    if any(current.get(v) != last.get(v) for v in current):
        return True
    return any(needs_attention(s) for s in current.values())


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def write_state(current: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def render_report(current: dict, last: dict, model: str, catalog_count: int) -> str:
    first_run = not last
    recovered = [v for v, s in current.items() if s == "200" and last.get(v) == "403"]
    newly_down = [v for v, s in current.items() if s == "403" and last.get(v) == "200"]
    still_down = [v for v, s in current.items() if s == "403" and last.get(v) == "403"]
    limited = [v for v, s in current.items() if s == "429"]
    unmeasured = [v for v, s in current.items()
                  if s in ("timeout", "conn-error", "error", "no-key")]
    other = [v for v, s in current.items()
             if needs_attention(s) and s not in ("429",) and v not in unmeasured]
    covered = set(recovered) | set(newly_down) | set(limited) | set(unmeasured) | set(other)
    changed = [(v, last[v], current[v]) for v, s in current.items()
               if last.get(v) is not None and last.get(v) != s and v not in covered]

    lines = ["🔍 NVIDIA Key 健康监控", f"时间：{time.strftime('%Y-%m-%d %H:%M')}",
             f"探活模型：{model}" + (f"　（目录在架 {catalog_count}）" if catalog_count else ""), ""]
    if first_run:
        lines += ["📋 首次快照，建立基线。", ""]
    if changed:
        lines.append("🔀 状态变化（其他）：")
        lines += [f"  • {v}：{LABEL.get(old, old)} → {LABEL.get(new, new)}" for v, old, new in changed]
        lines.append("")
    if recovered:
        lines.append("✅ 自愈恢复（403→200）：")
        lines += [f"  • {v}" for v in recovered]
        lines.append("")
    if newly_down:
        lines.append("⚠️ 新回收（200→403，账号级，等 1-7 天自愈，勿动配置）：")
        lines += [f"  • {v}" for v in newly_down]
        lines.append("")
    if limited:
        lines.append("🔁 限流（429，免费额度，换模型即可，不是 key 坏了）：")
        lines += [f"  • {v}" for v in limited]
        lines.append("")
    if unmeasured:
        lines.append("❗ 探活失败（拿不到 HTTP 响应，无法判断是否限流）：")
        lines += [f"  • {v} —— {LABEL.get(current[v], current[v])}" for v in unmeasured]
        lines.append("")
    if other:
        lines.append("❗ 其他异常：")
        lines += [f"  • {v} —— {LABEL.get(current[v], current[v])}" for v in other]
        lines.append("")
    if still_down:
        lines.append(f"⏳ 持续 403（等自愈）：{len(still_down)} 把 —— " + "、".join(still_down))
        lines.append("")
    lines.append("各 key 当前状态：")
    for v in KEY_VARS:
        s = current.get(v, "?")
        lines.append(f"  {ICON.get(s, '•')} {v:<22} {s:<11}{LABEL.get(s, s)}")
    lines.append("")
    ok = sum(1 for s in current.values() if s == "200")
    lines.append(f"当前可用：{ok}/{len(current)}")
    lines.append("")
    lines.append("判定口径：403=账号回收等自愈，勿动配置；429=限流换模型；"
                 "404/410=该模型下架；探活失败=连不上/超时，与限流无关，需查网络或代理。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NVIDIA Key 探活")
    ap.add_argument("--dry-run", action="store_true", help="只探活并打印，不写状态文件")
    args = ap.parse_args(argv)

    env = load_env()
    keys = {v: resolve_key(v, env) for v in KEY_VARS}
    catalog = fetch_catalog(next((k for k in keys.values() if k), ""))
    model = pick_probe_model(catalog)
    current = {v: probe_key(k, model) for v, k in keys.items()}
    last = read_state()

    if not args.dry_run:
        write_state(current)
    if args.dry_run or should_emit(current, last):
        print(render_report(current, last, model, len(catalog)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
