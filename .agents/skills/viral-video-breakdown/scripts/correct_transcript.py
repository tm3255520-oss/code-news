#!/usr/bin/env python3
"""
correct_transcript.py - 转录 LLM 校稿（🟡 LLM 辅助；框架遵循 video-pipeline 铁律）

输入 transcript.txt（带时间码逐句）→ 调用 NVIDIA NIM（minimax-m3 等）→ 输出 corrected_transcript.txt。
只纠错（专名/错别字/繁转简），不改写。术语表见 references/video-asr-correction.md。

用法:
  python correct_transcript.py <transcript.txt> [out.txt] [--model minimaxai/minimax-m3]
  # 无 NVIDIA key 时：--dry-run 仅输出待校稿行 + 术语替换建议（人工/Claude 校稿）

失败处理：某批调用失败 → 该批保留原文并标记，不中断。
"""
import sys
import os
import re
import json
import time
import argparse
import urllib.request
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_MODEL = "minimaxai/minimax-m3"
BATCH = 25


def _find_keys_file():
    """探测 nvidia_keys.json：env 显式 > 宿主机 home > 沙箱挂载。"""
    cand = [os.environ.get("NVIDIA_KEYS_FILE")]
    cand.append(os.path.join(os.path.expanduser("~"), ".hermes", "config", "nvidia_keys.json"))
    cand.append(os.path.join("/", "sessions"))  # /sessions/*/mnt/.hermes/...
    for c in cand:
        if c and os.path.isfile(c):
            return c
    import glob
    for c in glob.glob("/sessions/*/mnt/.hermes/config/nvidia_keys.json"):
        if os.path.isfile(c):
            return c
    return None

TERM_TABLE = (
    "DeepSeek Harness=DeepSeek Harness；STD/STD规范=dsh-std（小写）；"
    "dsh-ecosystem-spec=dsh-ecosystem-spec；dsh-TUI=dsh-TUI；adapter=adapter；harmony=harmony；"
    "T-Auto=T-Auto；Yan-Zero=Yan-Zero；兼容=兼容；适配=适配；实现=实现；插件=插件"
)

PROMPT_TPL = """你是中文视频转录校稿助手。只纠错，不改写。
硬规则：
- 输出必须全部简体中文：繁体词（規範/倉庫/團隊/視線/解決/已經/為 等）一律转简体（规范/仓库/团队/实现/解决/已经/为）。
- 只纠正：专名/术语误识、错别字、繁转简。
- 原样保留每行开头的 [时间码] 前缀，只改其后的文字。
- 行数/时间码不变；不增删内容；不润色。
- 术语规范（按表强制统一）：
  {terms}
  特别注意：提到 dsh-std 协定/标准时统一写小写 "dsh-std"，不要写 "STD"。
- 不确定的保留原文。

输入（每行 [时间] 文本）：
{batch}

输出（简体、保持同样格式，逐行对应）："""


def load_keys():
    kf = _find_keys_file()
    if not kf:
        return []
    try:
        with open(kf, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return []
    out = []
    for k in cfg.get("nvidia_keys", []):
        if isinstance(k, dict):
            k = k.get("key")
        if isinstance(k, str) and k.strip():
            out.append(k.strip())
    return out


def call_nvidia(messages, model, temperature=0.2, max_tokens=2048, timeout=90):
    keys = load_keys()
    if not keys:
        return None, "no nvidia keys"
    payload = json.dumps({
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
        "stream": False}, ensure_ascii=False).encode("utf-8")
    last = "all keys failed"
    for key in keys:
        req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if content and content.strip():
                return content.strip(), None
            last = "empty content"
        except Exception as e:
            last = str(e)
    return None, last


TERM_FIXUPS = [  # 确定性兜底替换（🔵），保证 LLM 漏改的术语也归位；顺序=长词优先
    (r"Dipsycannus|Dip\s*Cicannus|Dipsix|deep\s*sets|Deep\s*Sets|dpc哈尼斯|dsa是", "DeepSeek Harness"),
    (r"(?<![A-Za-z])STD(?![A-Za-z])", "dsh-std"),
    (r"NZRO", "Yan-Zero"),
    (r"TOTO", "T-Auto"),
    (r"堅榮|監榮", "兼容"),
    (r"失配|登配", "适配"),
    (r"視線", "实现"),
    (r"揪件", "插件"),
    (r"規範", "规范"), (r"倉庫", "仓库"), (r"團隊", "团队"),
    (r"解決", "解决"), (r"已經", "已经"), (r"為", "为"),
]


def apply_term_fixups(text):
    """确定性术语兜底替换：LLM 漏改的专名/繁体残留由脚本强制归位。"""
    for pat, repl in TERM_FIXUPS:
        text = re.sub(pat, repl, text)
    return text


def correct_batch(lines, model):
    batch_text = "\n".join(lines)
    prompt = PROMPT_TPL.format(terms=TERM_TABLE, batch=batch_text)
    content, err = call_nvidia(
        [{"role": "user", "content": prompt}], model)
    if err:
        return None, err
    out = [apply_term_fixups(l) for l in content.splitlines()]
    if len(out) != len(lines):
        return None, f"行数不匹配({len(out)} vs {len(lines)})"
    return out, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="transcript.txt 路径")
    ap.add_argument("output", nargs="?", default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", help="不调用 LLM，输出待校稿行")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    out_path = args.output or os.path.join(os.path.dirname(args.input), "corrected_transcript.txt")

    if args.dry_run:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        log(f"dry-run：写入 {out_path}（未校稿）")
        return

    log(f"校稿 {len(lines)} 行，模型 {args.model}")
    result = []
    fails = []
    for i in range(0, len(lines), BATCH):
        batch = lines[i:i + BATCH]
        fixed, err = correct_batch(batch, args.model)
        if err:
            fails.append((i // BATCH + 1, err))
            result.extend(batch)  # 失败保留原文
            log(f"  批次 {i // BATCH + 1} 失败，保留原文: {err[:80]}", "WARN")
        else:
            result.extend(fixed)
        time.sleep(0.5)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(result) + "\n")
    log(f"✅ 校稿完成 -> {out_path} | 失败批次 {len(fails)}/{len(range(0, len(lines), BATCH))}")
    if fails:
        for b, e in fails:
            log(f"  批次{b} 错误: {e[:120]}", "WARN")


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


if __name__ == "__main__":
    main()
