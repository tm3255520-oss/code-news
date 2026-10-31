#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper-to-transcript.py
把本机 openai-whisper 的输出转成 HyperFrames embedded-captions 所需的
word-level transcript.json（预置式，绕过 whisper-cpp / WhisperX）。

背景：
  embedded-captions/scripts/transcribe.cjs 在开头会读 <project>/transcript.json，
  若其符合 word-level 形状（且有 language_code），**直接 return，不做任何转录**。
  因此只要预置一个合格文件，本机就不需要 whisper-cpp，也不需要 uvx/WhisperX。

用法：
  python whisper-to-transcript.py <whisper输出.json|.srt> <项目目录或输出文件>
         [--mode cue|word] [--lang zh] [--name transcript.json]

模式：
  cue  （默认，中文推荐）每个 segment / SRT cue 一条。字幕按句显示，不闪。
  word （英文推荐）逐词一条。中文会按单字切分，逐字上屏 —— 慎用。

输出（与 transcribe.cjs 写出的格式一致）：
  {
    "text": "<全文>",
    "language_code": "zh",
    "engine": "local-whisper(<model>)",
    "words": [ {"text": "...", "start": 0.0, "end": 1.2, "type": "cue"}, ... ]
  }
"""
import argparse
import json
import os
import re
import sys

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")


def die(msg, code=1):
    print("[whisper-to-transcript] 错误: " + msg, file=sys.stderr)
    sys.exit(code)


def read_text(path):
    """读文本，同时兼容 CRLF / LF / UTF-8 BOM。
    ⚠️ 行尾必须归一成 LF —— hyperframes transcribe 的 SRT 解析器不认 CRLF。"""
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def parse_srt(text):
    """极简 SRT 解析 → [{start,end,text}]（时间归一为秒）。"""
    if "-->" not in text:
        die("不是有效的 SRT（找不到 '-->'）")
    cues = []
    for block in re.split(r"\n{2,}", text.strip()):
        lines = [x for x in block.strip().split("\n") if x.strip() != ""]
        if not lines:
            continue
        ti = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if ti is None:
            continue
        m = re.match(
            r"\s*(\d+):(\d+):([\d.,]+)\s*-->\s*(\d+):(\d+):([\d.,]+)",
            lines[ti],
        )
        if not m:
            continue
        g = m.groups()

        def sec(h, mi, s):
            return int(h) * 3600 + int(mi) * 60 + float(s.replace(",", "."))

        body = " ".join(lines[ti + 1:]).strip()
        if body:
            cues.append({"start": sec(*g[:3]), "end": sec(*g[3:]), "text": body})
    if not cues:
        die("SRT 解析出 0 条 cue")
    return cues


def from_whisper_json(d, mode):
    """whisper --output_format json 的结构：
       {text, language, segments:[{start,end,text,words:[{word,start,end}]}]}
    """
    segs = d.get("segments") or []
    if not segs:
        die("whisper json 里没有 segments")
    lang = d.get("language") or ""
    if mode == "cue":
        words = []
        for s in segs:
            t = (s.get("text") or "").strip()
            if not t:
                continue
            words.append(
                {"text": t, "start": float(s["start"]), "end": float(s["end"]), "type": "cue"}
            )
        return words, lang

    # mode == word：优先用 segments[].words；缺失则退化到整段当一条
    words = []
    for s in segs:
        ws = s.get("words") or []
        if ws:
            for w in ws:
                txt = (w.get("word") or w.get("text") or "").strip()
                if not txt:
                    continue
                words.append(
                    {
                        "text": txt,
                        "start": float(w["start"]),
                        "end": float(w["end"]),
                        "type": "word",
                    }
                )
        else:
            t = (s.get("text") or "").strip()
            if t:
                words.append(
                    {"text": t, "start": float(s["start"]), "end": float(s["end"]), "type": "cue"}
                )
    return words, lang


def build_text(words):
    """拼接全文。CJK 不加空格，拉丁文加空格，标点前不留空格。"""
    if not words:
        return ""
    if CJK.search("".join(w["text"] for w in words)):
        s = "".join(w["text"] for w in words)
    else:
        s = " ".join(w["text"] for w in words)
    return re.sub(r"\s+([,.!?;:，。！？；：、])", r"\1", s).strip()


def validate(words):
    """复刻 transcribe.cjs 第 127-138 行的 word-level 校验。"""
    problems = []
    if not words:
        problems.append("words 为空")
    for i, w in enumerate(words):
        if not isinstance(w.get("text"), str) or not w["text"]:
            problems.append("第 {} 条 text 非法".format(i))
        for k in ("start", "end"):
            if not isinstance(w.get(k), (int, float)):
                problems.append("第 {} 条 {} 不是数字".format(i, k))
            elif w[k] >= 36000:
                problems.append("第 {} 条 {}={} ≥36000（疑似毫秒格式）".format(i, k, w[k]))
    for i in range(1, len(words)):
        if words[i]["start"] < words[i - 1]["start"] - 0.001:
            problems.append("第 {} 条时间早于上一条（未按时间递增）".format(i))
            break
    return problems


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("source", help="whisper 输出的 .json 或 .srt")
    ap.add_argument("target", help="项目目录，或直接给 transcript.json 的路径")
    ap.add_argument("--mode", choices=["cue", "word"], default="cue",
                    help="cue=按句（中文推荐，默认）；word=逐词（英文推荐）")
    ap.add_argument("--lang", default="",
                    help="language_code，如 zh / en。留空则从 whisper json 读，读不到用 zh")
    ap.add_argument("--name", default="transcript.json", help="输出文件名（默认 transcript.json）")
    args = ap.parse_args()

    src = os.path.abspath(args.source)
    if not os.path.isfile(src):
        die("源文件不存在: " + src)

    ext = os.path.splitext(src)[1].lower()
    if ext == ".srt":
        cues = parse_srt(read_text(src))
        mode = "cue"  # SRT 天生是 cue 级
        words, lang = [], ""
        for c in cues:
            words.append({"text": c["text"], "start": c["start"], "end": c["end"], "type": "cue"})
        engine = "local-whisper(srt)"
    elif ext == ".json":
        try:
            d = json.loads(read_text(src))
        except Exception as e:
            die("json 解析失败: {}".format(e))
        if isinstance(d, list):
            die("这是一份 list 格式的 json（hyperframes transcribe 的导入产物），"
                "不是 whisper 的原始输出。请传入 whisper 的 .json（含 segments）。")
        words, lang = from_whisper_json(d, args.mode)
        # 模型名从文件名里尽力提取，仅作记录
        engine = "local-whisper"
    else:
        die("只支持 .json 或 .srt，收到: " + ext)

    language_code = args.lang or lang or "zh"

    if args.mode == "word" and CJK.search("".join(w["text"] for w in words)):
        print("[whisper-to-transcript] ⚠ 检测到 CJK 文本而 mode=word —— 中文会被切成单字，"
              "字幕将逐字上屏。中文请用 --mode cue。", file=sys.stderr)

    problems = validate(words)
    if problems:
        print("[whisper-to-transcript] 校验未通过：", file=sys.stderr)
        for p in problems[:10]:
            print("   - " + p, file=sys.stderr)
        die("共 {} 处问题".format(len(problems)))

    out = args.target
    if os.path.isdir(out) or not os.path.splitext(out)[1]:
        os.makedirs(out, exist_ok=True)
        out = os.path.join(out, args.name)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    payload = {
        "text": build_text(words),
        "language_code": language_code,
        "engine": engine,
        "words": words,
    }
    # 落盘用 LF（与上游 eol=lf 约定一致）
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 回读校验
    back = json.loads(read_text(out))
    ok = (
        isinstance(back, dict)
        and isinstance(back.get("words"), list)
        and len(back["words"]) == len(words)
        and bool(back.get("language_code"))
    )
    span = "{:.2f}s → {:.2f}s".format(words[0]["start"], words[-1]["end"])
    print("[whisper-to-transcript] {} 条 → {}".format(len(words), out))
    print("[whisper-to-transcript] 时间跨度 {}  语言 {}  模式 {}".format(
        span, language_code, "cue" if words[0].get("type") == "cue" else "word"))
    print("[whisper-to-transcript] 全文: {}".format(
        payload["text"][:80] + ("…" if len(payload["text"]) > 80 else "")))
    print("[whisper-to-transcript] 回读校验: " + ("通过 ✓" if ok else "失败 ✗"))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
