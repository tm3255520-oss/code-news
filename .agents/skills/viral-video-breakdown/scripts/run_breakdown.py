#!/usr/bin/env python3
"""
run_breakdown.py - 一键拆解入口（🔵 编排 + 🟡 LLM 生成报告草稿）

输入一个 B站/头条链接（或已有证据包目录），产出完整拆解报告草稿：
  1. 🔵 调 extract_video_evidence.py 产出证据包（或读 --evidence 已有证据包）
  2. 🔵 读 meta.json / transcript.txt / frames_ocr.md
  3. 🟡 调 NVIDIA NIM（minimax-m3）按 breakdown-output-template 生成报告草稿
  4. 🔵 落盘 <out_dir>/爆款拆解报告.md（标注"待人工终审"）

用法:
  python run_breakdown.py <url> [out_dir]
  python run_breakdown.py --evidence <evidence_dir> [out_dir]
"""
import sys
import os
import re
import json
import argparse
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_NEWS_SCRIPTS = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts"))
if CODE_NEWS_SCRIPTS not in sys.path:
    sys.path.insert(0, CODE_NEWS_SCRIPTS)
MODEL = "minimaxai/minimax-m3"

REPORT_TMPL = """你是爆款视频拆解分析师。基于下面的证据，产出一份拆解报告（简体中文）。

【证据】
- 平台/标题/作者/数据：{meta}
- 旁白转写（节选）：{transcript}
- 画面逐帧描述（带时间戳，含屏幕文字/构图/隐喻）：{vision}
- 数据门（硬约束，由代码按 validation-gate 规则计算）：{data_gate}

【要求】
按以下结构输出，每节尽量简洁有据（推断处标【推断】）：
1. 样本判断：平台/形态、目标人群、核心情绪、核心承诺、是否值得复刻（数据门未过标"待数据/不值得"）、主要风险
2. 数据门：播放/点赞/评论/收藏/投币、收藏率/投币率、相对作者中位数（若有）、结论（✅通过/⚠️观察中/❌未通过/❓数据不足）
3. 为什么会火/扑（2-4 条，每条标【推断】+证据）
4. 前3秒钩子（画面/口播/屏幕大字/节奏 + 可迁移机制）
5. 分段结构（时间|功能|重点|留存作用 表格）
6. 爆款DNA（选题/标题/前3秒/结构/留存/金句/画面/转化 可复刻项）
7. 底层公式（对【】用【】说出【】，再用【】给到【】，最后制造【】理由）
8. 能借鉴的 / 不能直接抄的（各 2-3 条）
9. 资讯专属六维（若为图文TTS形态）：选题信息增量/图文TTS特征/资料来源/信任构建/生产可行性/转化路径

【硬约束】第 2 节"数据门结论"和"是否值得复刻"必须严格采用上面给出的数据门结论，不得自行改为"通过/值得"。
输出直接给 Markdown，不要额外解释。"""


def compute_data_gate(meta: dict) -> tuple[str, str]:
    """按 validation-gate.md 硬阈值确定性计算数据门结论（不交给 LLM 判断）。"""
    play = int(meta.get("play_count") or 0)
    digg = int(meta.get("digg_count") or 0)
    comment = int(meta.get("comment_count") or 0)
    repin = int(meta.get("repin_count") or meta.get("favorite_count") or 0)
    like_rate = (digg / play) if play else 0
    collect_rate = (repin / play) if play else 0
    comment_rate = (comment / play) if play else 0
    if play < 50000:
        verdict = (f"❌ 未达爆款绝对值：播放 {play} < 5万(头条阈值)；作者中位数未知→相对倍数无法判定，"
                   f"故数据不足。互动：赞率{like_rate:.2%} 收率{collect_rate:.2%} 评率{comment_rate:.2%}。")
        outcome = "待数据/不值得（L4 未通过，禁止判'值得复刻'）"
    else:
        verdict = (f"✅ 达播放绝对值：{play} ≥5万；互动 赞率{like_rate:.2%} 收率{collect_rate:.2%} 评率{comment_rate:.2%}；"
                   f"但作者中位数未知→相对倍数待定，需再看起量趋势。")
        outcome = "待复验（需作者基线中位数 + 起量趋势，暂不判'值得'）"
    return verdict, outcome


def ensure_vision(ev_dir: str, provider: str = "bailian", model: str = "qwen3-vl-plus") -> str:
    """若无 vision_frames.md 且有 frames，则跑视觉逐帧描述；返回其文本。"""
    vmd = os.path.join(ev_dir, "vision_frames.md")
    if not os.path.exists(vmd) and os.path.isdir(os.path.join(ev_dir, "frames")):
        log("运行视觉逐帧描述（qwen3-vl-plus）...")
        try:
            import video_scene_vision as vsv
            rows = vsv.describe_frames(Path(ev_dir), model, provider, 5)
            vsv.write_md(Path(ev_dir), rows)
        except Exception as e:  # noqa: BLE001
            log(f"视觉步骤失败（{str(e)[:120]}），将仅用文本证据", "WARN")
    return read_or_skip(vmd)


def load_keys():
    import glob
    cand = [os.environ.get("NVIDIA_KEYS_FILE"),
            os.path.join(os.path.expanduser("~"), ".hermes", "config", "nvidia_keys.json")]
    for c in cand:
        if c and os.path.isfile(c):
            break
    else:
        g = glob.glob("/sessions/*/mnt/.hermes/config/nvidia_keys.json")
        c = g[0] if g else None
    if not c:
        return []
    try:
        cfg = json.load(open(c, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for k in cfg.get("nvidia_keys", []):
        if isinstance(k, dict):
            k = k.get("key")
        if isinstance(k, str) and k.strip():
            out.append(k.strip())
    return out


def call_nvidia(prompt, model=MODEL, max_tokens=4000):
    keys = load_keys()
    if not keys:
        return None, "no nvidia keys"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": max_tokens, "stream": False},
        ensure_ascii=False).encode("utf-8")
    last = "all keys failed"
    for key in keys:
        body = payload.decode("utf-8", "replace")
        # 1) urllib
        try:
            req = urllib.request.Request(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if content and content.strip():
                return content.strip(), None
            last = "empty"
        except Exception as e:
            last = str(e)[:120]
        # 2) curl 兜底（python-TLS 握手偶发 EOF）
        try:
            import subprocess
            r = subprocess.run(
                ["curl", "-sS", "-X", "POST", "--max-time", "120",
                 "https://integrate.api.nvidia.com/v1/chat/completions",
                 "-H", f"Authorization: Bearer {key}",
                 "-H", "Content-Type: application/json",
                 "-d", body],
                capture_output=True, text=True, timeout=130)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if content and content.strip():
                    return content.strip(), None
        except Exception as e2:
            last = f"{last}; curl:{str(e2)[:80]}"
    return None, last


def read_or_skip(path, n_lines=None):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    if n_lines:
        lines = lines[:n_lines]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="视频 URL")
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument("--evidence", default=None, help="复用已有证据包目录（跳过下载）")
    args = ap.parse_args()

    if not args.input and not args.evidence:
        ap.error("需要 URL 或 --evidence 目录")
    if args.evidence and args.input and not args.out_dir:
        # --evidence 模式下，位置参数 input 视为 out_dir
        args.out_dir = args.input
        args.input = None
    out_dir = args.out_dir or os.path.join(
        os.getcwd(), "breakdown_out", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)

    # 1. 证据提取（或复用）
    ev_dir = args.evidence
    if not ev_dir:
        log("调用 extract_video_evidence.py ...")
        r = subprocess.run([sys.executable, os.path.join(SKILL_DIR, "scripts",
                                                         "extract_video_evidence.py"),
                            args.input, out_dir], capture_output=True, text=True, timeout=600)
        log(r.stdout[-500:] if r.stdout else "")
        ev_dir = out_dir
    else:
        log(f"复用证据包: {ev_dir}")

    # 2. 读证据
    meta_path = os.path.join(ev_dir, "meta.json")
    if not os.path.exists(meta_path):
        log(f"证据包不完整（缺 meta.json）: {ev_dir}", "ERROR")
        sys.exit(1)
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta_str = json.dumps({k: meta.get(k) for k in
                           ["platform", "title", "author", "play_count", "comment_count",
                            "digg_count", "favorite_count", "coin_count", "duration_s",
                            "bvid", "url"]} | {"repin_count": meta.get("repin_count")},
                          ensure_ascii=False)
    trans = read_or_skip(os.path.join(ev_dir, "transcript.txt"), n_lines=40)
    vision = ensure_vision(ev_dir)
    log(f"证据读取完成: meta / 转写{len(trans)}字 / 视觉{len(vision)}字")

    # 3. LLM 生成报告草稿：标准网关 role=analysis（视觉增强）；失败回退 minimax / 素材包
    gate_str, gate_outcome = compute_data_gate(meta)
    prompt = REPORT_TMPL.format(meta=meta_str, transcript=trans or "(无转写)",
                                vision=vision or "(无视觉逐帧描述)", data_gate=gate_str)
    content, err = None, None
    try:
        from model_gateway import call as gw_call
        log("调用标准网关（role=analysis）生成报告草稿 ...")
        r = gw_call(None, role="analysis", prompt=prompt, max_tokens=4500, temperature=0.3)
        if r.get("error"):
            err = r["error"]
        else:
            content = r["text"]
            log(f"网关完成 model={r.get('model')} wire={r.get('wire')}")
    except Exception as e:  # noqa: BLE001
        err = str(e)
    if not content:
        log(f"网关不可用（{(err or '')[:80]}），回退 NVIDIA minimax-m3 ...", "WARN")
        content, err = call_nvidia(prompt)
    if not content:
        log(f"NVIDIA 也不可用（{(err or '')[:80]}），降级为报告素材包（由 Claude/人工生成报告）", "WARN")
        material = ("# 拆解报告素材包（NVIDIA 不可用，供 Claude/人工生成报告）\n\n"
                    f"> 证据包：`{ev_dir}`｜生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    "## 证据\n"
                    f"- meta：{meta_str}\n"
                    f"- 转写（前40句）：\n```\n{trans}\n```\n"
                    f"- 画面逐帧描述：\n```\n{vision}\n```\n\n"
                    "## 任务\n按 `references/breakdown-output-template.md` 生成完整拆解报告（含数据门/机制/是否值得复刻），"
                    "推断标【推断】，数据门未过则写「待数据/不值得」。")
        out_md = os.path.join(out_dir, "report_input.md")
        with open(out_md, "w", encoding="utf-8") as f:
            f.write(material)
        log(f"✅ 素材包 -> {out_md}")
        sys.exit(2)
    report = ("# 爆款拆解报告（草稿，待人工终审）\n\n"
              f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}｜证据包：`{ev_dir}`\n\n"
              f"{content}\n\n---\n*本报告由 run_breakdown.py 自动生成，机制结论为【推断】，发布前需人工核验数据门与来源。*")

    # 4. 落盘
    out_md = os.path.join(out_dir, "爆款拆解报告.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"✅ 报告草稿 -> {out_md}")


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


if __name__ == "__main__":
    main()
