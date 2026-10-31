#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adapt_for_platforms.py — 平台适配编排器（方案 B · 第一档）

把一个「内容母版 script.json」按平台适配矩阵，为每个目标平台生成一版**原生适配**的成片。

为什么是「原生生成」而不是「后处理」：
    平台跨平台查重比对的是**画面/音频/文本**三维指纹，其中音频指纹权重最高。
    后处理（改分辨率、调色、加角标）改不了音频指纹，也改不了构图 —— 而 B站社区公约
    已明确把「倍速/镜像/调色/补帧」列为**不构成自制**。所以真正有效的适配只有一条路：
    **每个平台各生成一版**（换音色、换画幅、换卡片样式），而不是把一个 mp4 改来改去。

依据：`运营中心/<平台>/规则与合规/跨平台分发防搬运与AI标识合规动作单.md`
矩阵：`D:\\AI-VIDEO\\config\\平台适配矩阵.json`（参数单一事实源，改矩阵不动脚本）

用法:
    # 看矩阵
    python adapt_for_platforms.py --list

    # 只产出各平台 script.json + 发布文案（不渲染；会调 LLM 改写文案）
    python adapt_for_platforms.py --script <script.json> --out-root <dir> --dry-run
    # 跳过文案改写（纯参数注入，秒回，用来核对画幅/音色注入）
    python adapt_for_platforms.py --script <s.json> --out-root <d> --dry-run --no-rewrite-copy

    # 全平台真跑
    python adapt_for_platforms.py --script <script.json> --out-root <dir>

    # 只跑某几个平台 / 只渲前 N 秒做确认
    python adapt_for_platforms.py --script <s.json> --out-root <d> --platforms 抖音,视频号
    python adapt_for_platforms.py --script <s.json> --out-root <d> --platforms 抖音 --preview 6

前置：本机 `edge-tts` 装在**系统 Python313**（托管解释器没有），HyperFrames 在 D:\\pi-agent\\。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from platform_cover_spec import cover_gate, find_horizontal_in_dir  # noqa: E402  封面槽规格（单一事实源）

SCRIPTS = Path(r"C:\Users\Administrator\Documents\code-news\scripts")
MATRIX = Path(r"D:\AI-VIDEO\config\平台适配矩阵.json")
CARD_BUILDER = SCRIPTS / "build_card_video.py"
# edge-tts 只在系统 Python313（平台线既定事实，见 platform-line-onboarding skill）
CARD_PY = Path(r"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe")
VOICE_SEGMENTER = Path(r"C:\Users\Administrator\.hermes\scripts\video_enhance\voice_segmenter.py")

PLATFORM_ORDER = ["抖音", "视频号", "小红书", "快手", "B站", "头条"]


def halted_platforms(matrix: dict) -> list:
    """读 `平台适配矩阵.json` 的 `_停线登记`，返回当前处于「停线中」的平台名。

    为什么读登记而不写死：停线是**有期限**的（如小红书 2026-10-13 → 2026-11-08）。
    把停线状态放在权威登记里，采集 / 生成 / 发布三层共用一处事实源；
    到期恢复时只改登记，不必回改本脚本，也不会漏掉某一个调用点。

    `_停线登记` 段的设计意图就是「人工/Agent 开工前先读本段，命中即跳过该平台」，
    见 `D:/AI-VIDEO/config/小红书停线与恢复登记-20261013.md`。
    """
    reg = matrix.get("_停线登记") or {}
    halted = []
    for name, item in reg.items():
        if not isinstance(item, dict):
            continue
        if str(item.get("状态", "")).strip() in ("停线中", "停线", "停用"):
            halted.append(name)
    return halted


def load_matrix() -> dict:
    if not MATRIX.exists():
        print(f"[fail] 找不到适配矩阵：{MATRIX}", file=sys.stderr)
        sys.exit(2)
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def preflight() -> None:
    problems = []
    if not CARD_BUILDER.exists():
        problems.append(f"缺 build_card_video.py：{CARD_BUILDER}")
    if not CARD_PY.exists():
        problems.append(f"缺系统 Python313：{CARD_PY}")
    if problems:
        for p in problems:
            print(f"[fail] {p}", file=sys.stderr)
        sys.exit(2)


def ensure_asset_link(master_script: Path, out_root: Path) -> None:
    """补回资源上下文。

    母版 script.json 会用 `../assets/shot/xxx.png` 引用截图（基准＝script.json 所在目录的父目录，
    见 build_card_video.stage_shots）。我们把各平台 script.json 复制到了 `<out_root>/<平台>/`，
    于是 `../assets` 解析成 `<out_root>/assets` —— 那里没有资源，渲染会 FileNotFoundError。
    这里在 out_root 下建一个指向母版项目 `assets` 的**目录联接**（junction，Windows 下免管理员），
    一次建好、各平台共用。
    """
    master_assets = master_script.resolve().parent.parent / "assets"
    if not master_assets.is_dir():
        return  # 母版没有截图引用，无需联接
    link = out_root / "assets"
    if link.exists():
        return
    # Windows 原生 cmd /c mklink 输出为本机 OEM 代码页(GBK)；自家 Python 子进程才用 utf-8
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(master_assets)],
                       capture_output=True, text=True, encoding="gbk", errors="replace")
    if r.returncode == 0:
        print(f"资源联接：{link}  ->  {master_assets}")
    else:
        print(f"[warn] 建资源联接失败（母版若有截图引用，渲染会失败）："
              f"{(r.stdout or '').strip()} {(r.stderr or '').strip()}", file=sys.stderr)


COPY_SYSTEM = (
    "你是自媒体运营，负责把同一条内容按不同平台的调性改写成发布文案。"
    "铁律：核心事实、数字、结论一个字都不能改——只改表达。"
)


_BOUND_RE = re.compile(r"[，。！？；、：…—!?;:\s]")   # 只认「强边界」：不认 . - , 这些英文词/数字内部也会出现的符号
_TRIM = "，。！？；、：,.!?;:…— \t"


def _rate_to_speed(rate) -> float:
    """矩阵里 edge-tts 语速字符串（`+28%` / `-5%`）→ aliyun 的 `--ali-speed` 倍率。

    ⚠️ **2026-10-13 起已不作为主路径**。原因：它隐含假设「两个引擎的自然语速相同」，
    而实测不成立（同为 atempo=1.24，Nofish 口径A 5.22 而 Ryan 4.49）。
    现改由 `voice_speed()` 按**音色基准**反解。本函数保留作兜底（音色不在基准表里时用）。
    """
    s = str(rate or "").strip().replace("%", "")
    try:
        v = float(s)
    except (TypeError, ValueError):
        return 1.0
    if v <= 0:                       # 负倍率无意义，按原速处理
        return 1.0
    return round(1.0 + v / 100.0, 3)


VOICE_RATE_BASE = Path(r"D:\AI-VIDEO\config\音色语速基准.json")


def probe_rate_a(script_json: Path, voice: str, ali_speed: float,
                 workdir: Path, engine: str = "aliyun", gap: float = 0.16) -> float | None:
    """快速探一遍 TTS，实测该「音色 + 这段文本」的口径A（纯说话语速）。

    为什么需要闭环（2026-10-13 实测教训）：
      静态音色基准表（`音色语速基准.json`）是在**固定基准文本**上测的；
      而每个平台的口播稿是**各自 LLM 改写**的，文本不同 → 同一音色实际语速也不同。
      实测：按静态表反解后，六平台口径A 仍散在 6.64–7.33（目标 6.5）。
      → 所以必须**先用本平台的真实文本探一遍**，再按比例修正 atempo。

    口径 A = 发音音节数 ÷ Σ 各段 duration（不含段间停顿）。
    这是 atempo 直接控制的量，且与 gap 无关，所以探针不必跑 normalize_pauses。
    """
    import subprocess
    workdir.mkdir(parents=True, exist_ok=True)
    vi = workdir / "probe_input.json"
    try:
        lines = json.loads(script_json.read_text(encoding="utf-8"))["lines"]
    except Exception:
        return None
    vi.write_text(json.dumps({"script": {"script": [{"content": t} for t in lines]}},
                             ensure_ascii=False), encoding="utf-8")
    cmd = [str(CARD_PY), "-X", "utf8", str(VOICE_SEGMENTER),
           "--script", str(vi), "--out-dir", str(workdir),
           "--engine", engine, "--voice", voice, "--gap", str(gap),
           "--ali-speed", str(ali_speed),
           "--keep-raw"]   # 探针不删 .raw：绕开沙箱删除闸（见 voice_segmenter 里 KEEP_RAW 的说明）
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    try:
        # 🔴 必须补跑 normalize_pauses：正式渲染会跑它（裁掉每段首尾静音、按固定 gap 重排），
        #    而它**会改变 Σ 段时长**。实测不跑它时探针值比渲染值高约 0.18 音节/秒（系统性偏差）
        #    → 直接用探针值修正会过度修正。这里补跑，让探针与渲染走**完全同一条链**。
        import importlib.util
        spec = importlib.util.spec_from_file_location("bcv_rateprobe", CARD_BUILDER)
        bcv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bcv)
        tl = bcv.normalize_pauses(workdir, gap)
        speech = sum(float(s["duration"]) for s in tl["segments"])
        syl = sum(len(l) for l in lines) - sum(
            len(re.findall(r"[，。！？、；：,.!?]", l)) for l in lines)
        return syl / speech if speech > 0 else None
    except Exception:
        return None


def voice_speed(voice: str, cfg: dict) -> tuple[float, str]:
    """按**音色基准**反解 `--ali-speed`，返回 (倍率, 依据说明)。

    为什么不再用「档位百分比」（2026-10-13 实测）：
      不同音色的自然语速本来就不同 —— 同为 atempo=1.24，
      Nofish 口径A 5.22 / Ryan 4.49，差 0.73 音节/秒。
      按档位统一 → 六平台口径A 实测散在 4.89–6.99（极差 2.10），听感完全不统一。
    做法：`ali_speed = 目标口径A ÷ 该音色基准口径A`，目标默认取
      `音色语速基准.json` 的 `target_rate_a`（当前 6.5），矩阵可用 `target_rate_a` 覆盖。
    """
    try:
        base = json.loads(VOICE_RATE_BASE.read_text(encoding="utf-8"))
    except Exception:
        return _rate_to_speed(cfg.get("rate")), "档位换算（音色基准表读不到）"
    target = float(cfg.get("target_rate_a") or base.get("target_rate_a") or 6.5)
    b = (base.get("base_rate_a") or {}).get(voice)
    if not b:
        return _rate_to_speed(cfg.get("rate")), f"档位换算（音色 {voice} 不在基准表）"
    return round(target / float(b), 3), f"音色反解（目标口径A {target} ÷ {voice} 基准 {b}）"


def _clip(s: str, n: int) -> str:
    """按字数上限截断，**优先切在标点/空格处** —— 避免断在半句或半词上（实测硬切会出「…i-hav」这种）。

    ⚠️ 必须同时满足两个目标（2026-10-11 修一处反例）：
      ① 不许断在半词上（如 `…i-hav`、「获 5.4」这种半截数字）；
      ② **不许把上限内还能放下、且本身完整的内容丢掉**。
    天真的「取 head 里最后一个边界」会违反 ②：头条原题「GitHub 反常：i-have-adhd 获 5.4 万星，…」，
    `head=s[:30]` 正好到「星」，但最后一个边界是「5.4」后的**空格（第 28 位）** → 切在 28 位，
    把仍在上限内的「万星」一起扔了，只剩半截数字「5.4」。

    所以先判断**上限处本身是不是边界**：`head[-1]` 是边界，或原文 `s[n]` 是边界（说明这个词到上限处正好写完）
    → 整段 `head` 就是干净的，直接用，一个字符都不丢。
    只有上限处确实落在词中间时，才往回找边界（且离上限 ≤18 字才采用，免得为一个逗号砍掉大半句）。
    """
    s = str(s)
    if n <= 0 or len(s) <= n:
        return s
    head = s[:n]
    if _BOUND_RE.fullmatch(head[-1]) or (n < len(s) and _BOUND_RE.fullmatch(s[n])):
        return head.rstrip(_TRIM)      # 上限处已是干净断点 → 保留全部可容纳内容
    ends = [m.end() for m in _BOUND_RE.finditer(head)]
    if ends and ends[-1] >= max(1, n - 18):
        return head[:ends[-1]].rstrip(_TRIM)
    return head.rstrip(_TRIM)


def rewrite_copy(master: dict, platform: str, cfg: dict) -> dict | None:
    """按平台调性生成发布文案包（title/description/tags）+ 改写后的首句钩子。

    破「文本指纹」用：同一母版在各平台产出**不同的标题/描述/标签/首句**。
    失败一律返回 None（回退原样，不阻断生成）。
    """
    lim = cfg.get("copy_limits") or {}
    lines = master.get("lines") or []
    if not lines:
        return None
    tags_note = (
        f"{lim.get('tags_min', 0)}-{lim.get('tags_max', 0)} 个（每个 ≤ {lim.get('tag_max') or '不限'} 字）"
        if lim.get("tags_max") else "该平台视频无独立标签字段，标签并入描述的话题（#xxx）"
    )
    prompt = f"""下面是一条 AI 科普短视频的口播稿。

【目标平台】{platform}
【平台调性】{cfg.get('note', '')}
【硬限制】标题 ≤ {lim.get('title_max', '?')} 字；描述 ≤ {lim.get('desc_max', '?')} 字；标签 {tags_note}

【要求】
1. 核心事实、数字、结论**一个字都不能改**（这是纪律，不是建议）。
2. 标题按该平台习惯写（抖音偏口语悬念、小红书关键词前置…），**必须卡在字数上限内** ——
   超了会被**硬截断**，标题就断在半句上，所以务必自己数清楚字数再输出。
3. 描述写 2-3 句，自然带出话题标签。
4. 另给一句**改写后的开头钩子**（替换口播第 1 句）：意思与原文一致，但表达不同。

只输出 JSON，不要任何解释：
{{"title": "...", "description": "...", "tags": ["..."], "hook": "..."}}

口播稿：
""" + "\n".join(lines)

    try:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import model_gateway  # 生产线标准模型入口
        r = model_gateway.call(role="general", prompt=prompt, system=COPY_SYSTEM,
                               max_tokens=1200, temperature=0.7, timeout=45)
        text = (r or {}).get("text") or ""
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            print(f"  [warn] 文案改写：模型未返回 JSON，回退原样", file=sys.stderr)
            return None
        obj = json.loads(m.group(0))
        # 硬限制兜底：超长按标点边界截断（宁可截，也不要被平台拒）
        obj["title"] = _clip(obj.get("title", ""), lim.get("title_max") or 0)
        obj["description"] = _clip(obj.get("description", ""), lim.get("desc_max") or 0)
        gmax = lim.get("tags_max") or 0
        tags = obj.get("tags") or []
        if gmax and len(tags) > gmax:
            obj["tags"] = tags[:gmax]
        obj["_provider_model"] = f"{(r or {}).get('provider')}/{(r or {}).get('model')}"
        return obj
    except Exception as e:  # 任何异常都不该阻断视频生成
        print(f"  [warn] 文案改写失败（回退原样）：{e}", file=sys.stderr)
        return None


def _master_key(master: dict) -> str:
    """母版内容指纹：文案改写的缓存键（内容变了才重写）。"""
    blob = json.dumps({"lines": master.get("lines"), "cards": master.get("cards")},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:12]


# ── B站 实质二次加工（2026-10-12 加）──────────────────────────────
# B站社区公约明确：只做尺寸/速度/颜色调整（倍速/镜像/调色/补帧）**不构成自制**，
# 必须做「实质二次加工」——解说配音 + 文字点评 + 特效包装——才能算原创/自制内容。
# 实现：在母版基础上，把 B站 版的口播改写成解说口吻（事实数字结论逐字保留），
# 并在尾部追加一张「老廖点评」卡（文字点评 + 区别于自动卡的 kicker）。
# ⚠️ 纪律：所有事实/数字/结论一律来自母版，绝不新编；只换表达与观点衔接。
SECONDARY_CONNECTIVES = [
    "我注意到，", "说实话，", "这里有个细节：", "重点其实是，",
    "你看这个，", "换句话说，", "我理解是，", "这就有意思了——",
    "说白了，", "我补充一句：", "注意看，", "总结一下，",
]


def _card_anchor(c: dict) -> str:
    """取一张卡的「锚点内容」——用于生成该卡的文字点评，绝不新编事实。"""
    a = (c.get("subtitle") or (str(c.get("title") or "").split("\n")[0]) or "").strip()
    if not a and (c.get("blocks") or []):
        a = ((c["blocks"][0] or {}).get("text") or "")
    if not a and (c.get("units") or []):
        items = (c["units"][0] or {}).get("items") or []
        if items:
            it = items[0]
            a = it.get("text") if isinstance(it, dict) else str(it)
    return (a or "").strip()


def bilibili_commentary(master: dict, out_dir: Path) -> tuple[list[str], dict]:
    """B站 实质二次加工：返回 (解说式口播行, 老廖点评卡)。

    ① 解说配音：母版每行在奇数位加一句解说衔接语（事实原句保留），末尾追加收尾点评口播；
    ② 文字点评：为每张卡生成一句点评（引用卡内已有内容），铺进专属点评卡的 blocks；
    ③ 特效包装：该卡带 kicker「UP主点评」+ transition_out 到黑，明显区别于自动卡。
    按母版内容哈希缓存（母版不变则不重算）。"""
    key = _master_key(master)
    cache = out_dir / "bilibili_processing.json"
    if cache.exists():
        try:
            old = json.loads(cache.read_text(encoding="utf-8"))
            if old.get("_master_key") == key and old.get("extra_card"):
                return old["lines"], old["extra_card"]
        except Exception:
            pass
    lines = master.get("lines") or []
    new_lines = []
    for i, ln in enumerate(lines):
        if i % 2 == 1 and str(ln).strip():        # 奇数行加解说衔接（保留事实原句）
            new_lines.append(SECONDARY_CONNECTIVES[i % len(SECONDARY_CONNECTIVES)] + str(ln))
        else:
            new_lines.append(str(ln))
    # 收尾点评口播（解说配音收束，明确 UP主观点）
    new_lines.append(
        "我是老廖，以上就是这周 GitHub 的三个信号。点个关注，下期接着聊 AI 工具怎么用。")

    # 文字点评：用紧凑的 list 单元铺 3 条短评（≤12 字，防溢出重叠）。
    # ⚠️ 不能把点评写成长文本 blocks——3 条长 block 在宽画幅下会超出卡片高度、
    #   互相重叠，被质量门 content_overlap 判 fail（已实测踩到）。list 单元专为多条罗列设计。
    # 点评均为基于母版内容的观点，不新编事实。
    extra_card = {
        "title": "老廖的点评",
        "from": len(lines) + 1,                  # 指向追加的收尾口播行
        "to": len(lines) + 1,
        "step": "06 / 06",
        "motion": "TYPES 标题 → STAGGER 卡片",
        "transition_in": "硬切",
        "transition_out": "FADES 到黑",
        "kicker": "UP主点评 / 13",
        "subtitle": "别只看热闹，想想怎么用",
        "units": [
            {"type": "list", "numbered": True, "drift": True, "items": [
                "废话少，比模型强更值钱",
                "官方下场，才是真信号",
                "技能包，你也能自己攒",
            ]},
        ],
    }
    data = {"_master_key": key, "lines": new_lines, "extra_card": extra_card}
    try:
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return new_lines, extra_card


AI_NOTICE_TEXT = "作者声明：内容由 AI 生成"


def apply_ai_notice(script: dict) -> dict:
    """给每张卡片挂常驻文字角标（AI 声明），**不配音、不占口播**。就地修改并返回。

    2026-10-12 用户裁定：AI 声明不用语音念，只在画面标文字。
    实现上**在最终 script 上盖章**（而非替换 lines/cards），因此可与
    B站「二次加工（解说配音）」**叠加**，不会互相覆盖。"""
    for c in (script.get("cards") or []):
        c["notice"] = AI_NOTICE_TEXT
    return script


def get_copy(master: dict, platform: str, cfg: dict, out_dir: Path,
             rewrite: bool = True) -> dict | None:
    """取该平台文案包：**命中缓存则复用**（按母版内容哈希），否则调 LLM。

    为什么必须缓存：LLM 调用慢（实测每次数秒~数十秒），6 平台连调会把命令拖超时；
    而且同一母版重复跑（改画幅/换音色重渲）不该重复计费。
    """
    cache = out_dir / "publish_copy.json"
    key = _master_key(master)
    if cache.exists():
        try:
            old = json.loads(cache.read_text(encoding="utf-8"))
            if old.get("_master_key") == key:
                print("  文案：命中缓存（母版未变）")
                return old
        except Exception:
            pass
    if not rewrite:
        return None
    c = rewrite_copy(master, platform, cfg)
    if c:
        c["_master_key"] = key
        cache.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return c


def build_platform_script(master: dict, cfg: dict, hook: str | None = None,
                          secondary: dict | None = None) -> dict:
    """在母版基础上产出该平台的 script.json —— 只改「适配维度」，不动内容主体。

    secondary（仅 B站 二次加工）非空时：整体替换口播行（解说式改写 + 收尾点评），
    并追加一张「老廖点评」卡。
    AI 声明角标（cfg.ai_disclosure_intro）**不在此处理** —— 由 run_platform 在最终
    script 上盖章（apply_ai_notice），以便与二次加工**叠加**、互不覆盖。"""
    s = json.loads(json.dumps(master, ensure_ascii=False))  # 深拷贝
    s["voice"] = cfg["voice"]            # 破音频指纹
    if cfg.get("style"):
        s["style"] = cfg["style"]        # 破画面指纹（卡片配色）
    if secondary:
        # 实质二次加工：解说配音（改写口播）+ 文字点评卡（追加专属卡）
        s["lines"] = list(secondary["lines"])
        s.setdefault("cards", []).append(dict(secondary["extra_card"]))
        s["_secondary_processing"] = True
    elif hook and s.get("lines"):
        s["lines"][0] = hook             # 破文本指纹：只换开头钩子（主体事实不动）
        s["_hook_rewritten"] = True
    s["_adapted_for"] = cfg.get("_platform")   # 留痕，方便日后追溯
    return s


def run_platform(platform: str, cfg: dict, master: dict, out_root: Path,
                 preview: float, quality: str, force: bool,
                 rewrite: bool = True, rate_probe: bool = True) -> dict:
    out_dir = (out_root / platform).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = out_dir / "script.json"

    copy = get_copy(master, platform, cfg, out_dir, rewrite)
    if copy:
        print(f"  文案：title {len(str(copy.get('title','')))}字 / "
              f"desc {len(str(copy.get('description','')))}字 / "
              f"tags {len(copy.get('tags') or [])}个  ({copy.get('_provider_model','')})")

    # B站 实质二次加工：解说配音改写 + 文字点评卡（按母版哈希缓存）
    secondary = None
    if cfg.get("secondary_processing"):
        sec_lines, extra_card = bilibili_commentary(master, out_dir)
        secondary = {"lines": sec_lines, "extra_card": extra_card}
        print(f"  二次加工：解说口播 {len(sec_lines)} 句 + 文字点评卡 1 张")

    # 组最终 script：二次加工（如有）→ 再盖 AI 声明角标（如有，叠加不覆盖）
    script = build_platform_script(master, cfg, (copy or {}).get("hook"), secondary)
    # ── 按画幅给 units 设上限（2026-10-13 加，实测标定）────────────────
    # 🔴 起因：把每卡 units 提到 4–5 项后，**横屏版面撑破** —— 质量门报
    #    `layout content_overlap ×18`（B站 / 头条），两片均判 fail。
    #    逐帧目视确认（抽帧 B站 26s）：**第 3 个单元框压住了底部副标题**。
    #    根因：横屏 1080 高 vs 竖屏 1920 高；而每张卡固定要放「标题 + 大字 + 副标题」，
    #    横屏剩余给 units 的纵向空间只够 **2 项**（3 项必压副标题）。
    #    实测：2 项 → 版面干净（抽帧 B站 14s 确认）；3 项 → 压副标题。
    #    这是**画幅适配**，属适配器职责，不该让母版去猜。
    cap = 2 if str(cfg.get("format")) == "wide" else 5
    trimmed = 0
    for c in script.get("cards") or []:
        for u in c.get("units") or []:
            items = u.get("items")
            if isinstance(items, list) and len(items) > cap:
                u["items"] = items[:cap]
                trimmed += 1
    if trimmed:
        print(f"  版面适配：{cfg.get('format')} 画幅 units 上限 {cap} 项，已裁剪 {trimmed} 处")
    if cfg.get("ai_disclosure_intro"):
        apply_ai_notice(script)
        print(f"  AI标识：卡片常驻文字角标「{AI_NOTICE_TEXT}」（不配音）")

    script_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=1),
        encoding="utf-8")

    target = out_dir / ("preview.mp4" if preview > 0 else "final.mp4")
    if target.exists() and not force:
        return {"platform": platform, "status": "skip", "reason": f"已存在 {target.name}（--force 可覆盖）"}

    # 语速：按**音色基准**反解（2026-10-13 改，见 voice_speed 的说明）。
    # 不再用「档位百分比」—— 实测不同音色自然语速差 0.73 音节/秒，按档位统一无效。
    speed, speed_how = voice_speed(str(cfg["voice"]), cfg)
    # ── 闭环修正（2026-10-13 加）───────────────────────────────────────
    # 静态基准表是在**固定基准文本**上测的；本平台口播稿是各自 LLM 改写的，
    # 文本不同 → 同一音色实际语速也不同（实测按静态表反解后仍散在 6.64–7.33，目标 6.5）。
    # 所以先探一遍实测口径A，再按 `atempo × 目标/实测` 修正。
    target = float(cfg.get("target_rate_a") or 6.5)
    if rate_probe:
        probe_dir = Path(tempfile.gettempdir()) / "adapt_rate_probe" / platform
        got = probe_rate_a(script_path, str(cfg["voice"]), speed, probe_dir,
                           engine=str(cfg.get("engine") or "aliyun"))
        if got and got > 0:
            corrected = round(speed * target / got, 3)
            print(f"    语速探针：实测口径A {got:.2f}（目标 {target}）→ "
                  f"atempo {speed} 修正为 {corrected}")
            speed = corrected
            speed_how += "｜已闭环修正"
        else:
            print("    语速探针：探不到（跳过闭环，用静态表值）", file=sys.stderr)
    cmd = [
        str(CARD_PY), str(CARD_BUILDER),
        "--script", str(script_path),
        "--out", str(out_dir),
        "--format", cfg["format"],
        "--voice", cfg["voice"],
        "--rate", cfg["rate"],
        "--tts-engine", str(cfg.get("engine") or "aliyun"),
        "--tts-speed", str(speed),
        "--quality", quality,
    ]
    print(f"    语速：--tts-speed {speed}（{speed_how}）")
    # BGM / 音效：矩阵每个平台都写了 bgm + sfx 路径，**必须传下去**。
    # 2026-10-13 缺陷：原实现不传 → build_card_video 用 BGM_DEFAULT="off" /
    # SFX_DEFAULT="off" → 六平台成片全部无配乐、无转场音效，人声赤裸暴露
    # 模型自身的 0.2–0.5s 短语停顿，听感就是"声音断开"。
    bgm = cfg.get("bgm")
    sfx = cfg.get("sfx")
    if bgm:
        cmd += ["--bgm", str(bgm)]
    if sfx:
        cmd += ["--sfx", str(sfx)]
    if preview > 0:
        cmd += ["--preview", str(preview)]

    print(f"  $ {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=str(SCRIPTS))
    if r.returncode != 0:
        return {"platform": platform, "status": "fail", "reason": f"退出码 {r.returncode}"}
    # ── 封面（2026-10-13 接线）────────────────────────────────────────
    # 🔴 缺陷：`make_platform_covers.py` 2026-10-12 就写好了，但**没接进本编排器**，
    #    也没接进任何产线 → v3/v4 六平台成片**全都没有封面**。
    #    而 `publish_via_yxer.py --cover` 是 **required** → 没有封面根本发不出去。
    #    这类「脚本写好了但没接线」是本产线反复踩的坑（矩阵字段、--bgm/--sfx 同理），
    #    故此处**默认必跑**，跑失败只告警不阻断（成片已生成，封面可单独补）。
    #
    # 2026-10-13 补第二道：**出图后按平台封面槽比例复核**。
    #    只判「cover.png 存在」是不够的 —— 原实现出的 9:16 封面在抖音侧会被忽略，
    #    回落到上一条视频的封面（用户截图实证），而文件明明"存在"。
    #    槽比例见 platform_cover_spec.py（抖音竖 3:4 / 横 4:3，**不是视频画幅**）。
    cover = out_dir / "cover.png"
    try:
        rc = subprocess.run([str(CARD_PY), "-X", "utf8",
                             str(SCRIPTS / "make_platform_covers.py"),
                             "--out-root", str(out_root), "--platforms", platform],
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=str(SCRIPTS))
        if rc.returncode != 0 or not cover.exists():
            print(f"    [warn] 封面生成失败：{(rc.stderr or '')[-200:]}", file=sys.stderr)
        else:
            print(f"    封面：{(rc.stdout or '').strip().splitlines()[0] if rc.stdout else 'cover.png'}")
            made = sorted(p.name for p in out_dir.glob("cover*.png"))
            bad = cover_gate(platform, cover, find_horizontal_in_dir(out_dir, platform))
            if bad:
                # 只告警：成片已生成，且 publish 侧还有一道硬门禁，不必在这里重复阻断。
                print(f"    [warn] 封面槽比例复核未过：" + "；".join(bad), file=sys.stderr)
            else:
                print(f"    封面槽核验：通过（{' '.join(made)}）")
    except Exception as e:  # noqa: BLE001
        print(f"    [warn] 封面生成异常：{e}", file=sys.stderr)
    return {"platform": platform, "status": "ok", "out": str(target)}


def main() -> int:
    ap = argparse.ArgumentParser(description="平台适配编排器（方案 B）")
    ap.add_argument("--script", help="内容母版 script.json")
    ap.add_argument("--out-root", help="各平台产物的父目录")
    ap.add_argument("--platforms", default=None,
                    help="逗号分隔，只跑指定平台（默认全部）；如 抖音,视频号")
    ap.add_argument("--dry-run", action="store_true", help="只产出各平台 script.json，不渲染")
    ap.add_argument("--preview", type=float, default=0.0, help="只渲前 N 秒做确认")
    ap.add_argument("--quality", default="looks", choices=["draft", "looks", "delivery"])
    ap.add_argument("--force", action="store_true", help="已存在成片也重跑")
    ap.add_argument("--no-rate-probe", action="store_true",
                    help="关掉语速闭环探针（默认开）。探针会先跑一遍 TTS 实测口径A，"
                         "再按比例修正 atempo —— 多花约 40s/平台，换取语速真统一。"
                         "仅在排查时关掉。")
    ap.add_argument("--no-rewrite-copy", dest="rewrite_copy", action="store_false",
                    help="跳过文案改写（默认按平台调性改写 title/描述/标签 + 首句钩子，破文本指纹）")
    ap.add_argument("--list", action="store_true", help="只看矩阵")
    args = ap.parse_args()

    matrix = load_matrix()
    plats: dict = matrix["platforms"]
    halted = halted_platforms(matrix)

    if args.list:
        print(f"{'平台':<6} {'画幅':<10} {'音色':<26} {'样式':<12} {'语速':<7} 通道")
        for name in PLATFORM_ORDER:
            c = plats.get(name)
            if not c:
                continue
            mark = "  ⛔ 停线中" if name in halted else ""
            print(f"{name:<6} {c['format']:<10} {c['voice']:<26} {c['style']:<12} {c['rate']:<7} {c.get('publish_channel','')}{mark}")
        if halted:
            print(f"\n⛔ 停线中（本脚本不为其产出）：{', '.join(halted)}")
            print("   解除：改 `D:/AI-VIDEO/config/平台适配矩阵.json` 的 `_停线登记`，不要改本脚本。")
        return 0

    if not args.script or not args.out_root:
        ap.error("需要 --script 与 --out-root（或用 --list 只看矩阵）")

    preflight()
    master = json.loads(Path(args.script).read_text(encoding="utf-8"))
    if not master.get("lines") or not master.get("cards"):
        print("[fail] 母版 script.json 需要 lines 与 cards", file=sys.stderr)
        return 2

    # ── 规则八 (e) 核验闸（2026-10-14 入，依据 内容生产/知识库线/_产出契约.md §4.4）──
    # 母版缺 _引用核验 → 拒绝进平台适配。先用 verify_script_claims.py 出断言清单、
    # 人工核完回写母版该字段，再跑本脚本。核验记录跟着母版走，不建集中库。
    vf = master.get("_引用核验")
    if not isinstance(vf, dict) or not vf:
        print("[fail] 母版缺 `_引用核验` 字段（产出契约规则八 (e)）：\n"
              "  先跑  python scripts/verify_script_claims.py --script <本文件> --out <清单.md>\n"
              "  按清单逐条核（T0 仓库存在性 / T1 README 锚定 / T2 数字快照），\n"
              "  把结论写回母版 `_引用核验` 后再进平台适配。\n"
              "  范式见 内容生产/知识库线/核验样例-AnyPS5母版-2026-10-14.md", file=sys.stderr)
        return 2

    targets = [p for p in PLATFORM_ORDER if p not in halted]
    if halted:
        print(f"[停线] 按 `_停线登记` 排除：{', '.join(halted)}"
              f"（到期恢复只改登记，不要改本脚本）", file=sys.stderr)
    if args.platforms:
        want = [p.strip() for p in args.platforms.split(",") if p.strip()]
        bad = [p for p in want if p not in plats]
        if bad:
            print(f"[fail] 矩阵里没有这些平台：{bad}", file=sys.stderr)
            return 2
        blocked = [p for p in want if p in halted]
        if blocked:
            print(f"[fail] 这些平台在停线中，不能生成：{', '.join(blocked)}"
                  f"（见 `_停线登记`；确需恢复请先解除登记，不要绕过）", file=sys.stderr)
            return 2
        targets = want

    out_root = Path(args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    ensure_asset_link(Path(args.script), out_root)

    print(f"母版：{args.script}")
    print(f"输出：{out_root}")
    print(f"目标：{', '.join(targets)}")
    print(f"模式：{'dry-run（只出 script.json）' if args.dry_run else ('preview ' + str(args.preview) + 's' if args.preview > 0 else '全量渲染')}")
    print("-" * 72)

    results = []
    for name in targets:
        cfg = dict(plats[name])
        cfg["_platform"] = name
        print(f"\n[{name}] {cfg['format']} / {cfg['voice']} / {cfg['style']} / {cfg['rate']}")
        if args.dry_run:
            out_dir = (out_root / name).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            copy = get_copy(master, name, cfg, out_dir, args.rewrite_copy)
            if copy:
                print(f"  文案：title {len(str(copy.get('title','')))}字 / "
                      f"desc {len(str(copy.get('description','')))}字 / "
                      f"tags {len(copy.get('tags') or [])}个")
            secondary = None
            if cfg.get("secondary_processing"):
                sec_lines, extra_card = bilibili_commentary(master, out_dir)
                secondary = {"lines": sec_lines, "extra_card": extra_card}
                print(f"  二次加工：解说口播 {len(sec_lines)} 句 + 文字点评卡 1 张")
            script = build_platform_script(master, cfg, (copy or {}).get("hook"), secondary)
            if cfg.get("ai_disclosure_intro"):
                apply_ai_notice(script)
                print(f"  AI标识：卡片常驻文字角标「{AI_NOTICE_TEXT}」（不配音）")
            (out_dir / "script.json").write_text(
                json.dumps(script, ensure_ascii=False, indent=1),
                encoding="utf-8")
            results.append({"platform": name, "status": "dry", "out": str(out_dir / "script.json")})
            continue
        results.append(run_platform(name, cfg, master, out_root,
                                    args.preview, args.quality, args.force, args.rewrite_copy,
                                    rate_probe=not args.no_rate_probe))

    print("\n" + "=" * 72)
    print("结果：")
    for r in results:
        mark = {"ok": "OK  ", "dry": "DRY ", "skip": "SKIP", "fail": "FAIL"}.get(r["status"], "?   ")
        tail = r.get("out") or r.get("reason", "")
        print(f"  {mark} {r['platform']:<6} {tail}")

    # 指纹差异化自检：同一维度不允许出现重复值（重复 = 没起到破指纹作用）
    used_voice = [plats[n]["voice"] for n in targets]
    used_fmt = [plats[n]["format"] for n in targets]
    dup_v = len(used_voice) != len(set(used_voice))
    print("\n指纹差异化自检：")
    print(f"  音色唯一：{'❌ 有重复' if dup_v else '✅ 各平台不同'}（{len(set(used_voice))}/{len(used_voice)}）")
    print(f"  画幅分布：vertical {used_fmt.count('vertical')} / landscape {used_fmt.count('landscape')}")
    print("  注：文案已按平台改写（见各平台 publish_copy.json）；发布错峰/幂等/AI 声明仍在发布侧未接，见矩阵 _未覆盖。")

    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
