#!/usr/bin/env python3
"""topic_triage.py — 选题池取舍打分：确定性去重 → Jev 三档 → 日报 + 影子台账。

为什么长这样（2026-10-24 用 30 条真实素材实测得出的两条结论）：
  ① **问法决定成败**：同一批素材、同一个 state，朴素问法精确率 35%，把「编辑标准」
     写进 criteria 后升到 78%。所以 prompt 固化在下面，不要随手改。
  ② **它看不见池内重复**：30 条里有 11 条同题，Jev 一次只看一条。所以去重必须由
     我们的确定性代码先做，再把「代表项」交给它 —— 本脚本就是这两段。
实测全文：vault `系统中枢/运行小结/系统与配置/2026-10-24-Jev选题池批量实测.md`

用法：
    python scripts/topic_triage.py                    # 最近 3 天
    python scripts/topic_triage.py --days 7 --dry-run # 只看统计，不调模型
    python scripts/topic_triage.py --date 2026-10-24 --quiet   # cron 用：成功即静默

产物：
    vault `内容生产/1-情报与选题/选题与题材/_Jev取舍-<date>.md`   # 人读的日报
    `agent-work/jev-shadow/ledger.jsonl`                          # 影子比对台账（逐条追加）

退出码：0 成功（含"窗口内无新素材"）/ 2 缺 key / 3 上游错误 / 4 用法错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import typesafe_decision as T  # noqa: E402

DEFAULT_VAULT = Path(r"D:\Obsidian Vault\obsidian Vault")
POOL_REL = Path("内容生产/1-情报与选题/选题与题材")
LEDGER = Path(r"C:\Users\Administrator\Documents\agent-work\jev-shadow\ledger.jsonl")
MODEL = "jev-1.14.0"          # 钉死版本：jev-latest 会漂（2026-10-22→10-24 已从 1.13 漂到 1.14）
MAX_ITEMS = 60

# 聚合行不是"选题素材"，一律排除
AGG_TITLES = ("热榜TOP20", "垂类热力", "全网社交热点", "榜单")
AGG_PLATFORMS = ("热点与情报",)

ROW_RE = re.compile(
    r"^\|\s*(?P<title>[^|]+?)\s*\|\s*(?P<plat>[^|]*?)\s*\|\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*(?P<summary>.*?)\s*\|"
)
LINK_RE = re.compile(r"\[\[([^\]|#]+)")

# 固化的问题单（改它就等于改产品，改完必须重跑实测）
QUESTIONS = {
    "publish_decision": {
        "type": "choice",
        "instructions": (
            "我们的编辑标准是：只做有新增信息的选题 —— 已被覆盖过的话题、纯工具介绍、"
            "二手体验都不算主线；有硬事实、一手细节或反常识结论的才算。"
            "就这一条素材本身，它该进哪一档"
        ),
        "criteria": {
            "now": "含可核实的新事实/一手细节/反常识，值得优先排一篇",
            "later": "信息成立但不新，或只是工具介绍/二手体验，只能当辅料或等更好的角度",
            "skip": "只有情绪或泛泛观点，没有可核实的新信息",
        },
    },
    "new_information": {
        "type": "noul",
        "instructions": "相对市面上已有的同题内容，这条能提供**新增**信息（而不是把已知的事再说一遍）",
    },
}


def _norm(text: str) -> str:
    """标题归一：去 hashtag / 标点 / 空白，只留 CJK + 字母数字。"""
    t = re.sub(r"#\S+", "", text).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", t)


def _grams(s: str, n: int = 2) -> set[str]:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _entities(title: str) -> set[str]:
    """标题里的 ASCII 实体（DeepInfer / Workbuddy / V4.1 这类），长度≥4。"""
    return {m.group(0).lower() for m in re.finditer(r"[A-Za-z][A-Za-z0-9.\-_]{3,}", title)}


def collect(vault: Path, since: str, until: str) -> list[dict]:
    """从题材卡证据链里捞窗口内的真实素材（去聚合、去重、文件必须存在）。"""
    cards = vault / POOL_REL
    items: dict[str, dict] = {}
    for card in sorted(cards.glob("*.md")):
        try:
            text = card.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = ROW_RE.match(line)
            if not m:
                continue
            title, plat, d = m.group("title").strip(), m.group("plat").strip(), m.group("date")
            if not (since <= d <= until):
                continue
            if plat in AGG_PLATFORMS or any(a in title for a in AGG_TITLES):
                continue
            lm = LINK_RE.search(m.group("summary"))
            if not lm:
                continue
            src = vault / (lm.group(1).strip() + ".md")
            if not src.is_file():
                continue
            key = str(src)
            items.setdefault(key, {
                "date": d, "plat": plat, "title": title,
                "card": card.stem, "src": key,
            })
    return list(items.values())


def similarity_pairs(items: list[dict]) -> list[tuple[dict, dict]]:
    """**只做提示，不合并**：找出标题高度相似的成对条目，供人工看同题。

    2026-10-24 实测教训：用「标题 2-gram + 共享 ASCII 实体」去**自动合并**是不可靠的
    —— 它把「工作台」「155 万亿 Token」「MiniMax」并成了一簇（都含 token），
    却漏掉了真正同系列的工作台 6 条。**静默并错比不并更危险**，
    所以这里只输出提示，绝不替人丢弃任何一条。
    """
    out: list[tuple[dict, dict]] = []
    norm = [_norm(i["title"]) for i in items]
    grams = [_grams(s) for s in norm]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _jaccard(grams[i], grams[j]) >= 0.5:
                out.append((items[i], items[j]))
    return out


def load_seen() -> set[str]:
    """读影子台账，返回已评过的素材路径（增量依据，避免每天重复打标同一条）。"""
    if not LEDGER.is_file():
        return set()
    seen: set[str] = set()
    try:
        for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("src"):
                seen.add(rec["src"])
    except OSError:
        pass
    return seen


def ask(items: list[dict], model: str, retries: int = 3) -> tuple[list[dict], dict]:
    key = T.lookup_key()
    done, tokens = [], 0
    for it in items:
        src = Path(it["src"])
        try:
            body = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        state = f"【标题】{it['title']}\n【平台】{it['plat']}　【日期】{it['date']}\n\n{body[:6000]}"
        payload = {"model": model, "state": state, "questions": QUESTIONS}
        for attempt in range(retries):
            try:
                resp = T._request(T.SYSTEMONE_URL, key, payload, 150)
                a = resp["answers"]
                it2 = dict(it)
                it2.update({
                    "bucket": a["publish_decision"]["choice"],
                    "confidence": a["publish_decision"]["confidence"],
                    "new_info": a["new_information"]["noul"],
                    "model": resp.get("model"),
                })
                tokens += int((resp.get("usage") or {}).get("input_tokens", 0))
                done.append(it2)
                break
            except SystemExit:
                if attempt == retries - 1:
                    print(f"[warn] 放弃：{it['title'][:40]}", file=sys.stderr)
                else:
                    time.sleep(2 * (attempt + 1))
    return done, {"input_tokens": tokens}


def render(day: str, scored: list[dict], meta: dict, pairs: list[tuple[dict, dict]],
           skipped: int) -> str:
    by_bucket: dict[str, list[dict]] = {"now": [], "later": [], "skip": []}
    for it in scored:
        by_bucket.setdefault(it["bucket"], []).append(it)
    for v in by_bucket.values():
        v.sort(key=lambda x: (-x["confidence"], x["date"]), reverse=False)

    lines = [
        "---",
        f"title: Jev 选题取舍 {day}",
        f"date: {day}",
        "tags: [选题池, Jev, 取舍, 影子比对]",
        f"status: 自动生成（{meta['model']}）",
        "agent: topic_triage.py",
        "---",
        "",
        f"# Jev 选题取舍 · {day}",
        "",
        f"> 窗口 {meta['since']} ~ {meta['until']}｜题材卡命中 **{meta['raw']}** 条真实素材｜"
        f"台账已评过跳过 **{skipped}** 条 → 本次打标 **{len(scored)}** 条。",
        f"> 模型 `{meta['model']}`｜输入 token {meta['tokens']}｜成本 ≈ ${meta['tokens'] * 0.042 / 1e6:.6f}",
        "",
        "> ⚠️ 判读纪律：**`confidence` 不能当筛选器**（实测反向）。只看档位与 `new_info`。",
        "> 它是「优先看」的排序器，不是「自动砍」的筛选器 —— `skip` 也不要自动丢。",
        "",
    ]
    label = {"now": "🟢 now（优先看）", "later": "🟡 later（可当辅料/等角度）", "skip": "⚪ skip（无新增信息）"}
    for bucket in ("now", "later", "skip"):
        rows = by_bucket.get(bucket, [])
        lines += [f"## {label[bucket]} — {len(rows)} 条", ""]
        if not rows:
            lines += ["（无）", ""]
            continue
        for it in rows:
            lines.append(
                f"- **{it['title'][:64]}**｜{it['plat']} {it['date']}"
                f"｜conf {it['confidence']:.2f}｜new_info {it['new_info']:.2f}｜`{it['card']}`"
            )
        lines.append("")

    if pairs:
        lines += ["## 同题提示（只提示、不合并；供人工复核）", ""]
        for a, b in pairs[:20]:
            lines.append(f"- {a['title'][:34]}　／　{b['title'][:34]}")
        lines.append("")

    lines += [
        "## 影子比对（周后复盘用）",
        "",
        "本次逐条结果已追加到 `agent-work/jev-shadow/ledger.jsonl`。",
        "一周后按 `now` 档命中率复盘：Jev 标 now 的条目里，实际被做成内容的占比；"
        "以及我们实际做了、但 Jev 标 later/skip 的漏判项。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="选题池取舍打分（去重 → Jev 三档 → 日报）")
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--days", type=int, default=3, help="回看天数（默认 3）")
    ap.add_argument("--date", default=None, help="以哪天为'今天'（YYYY-MM-DD，默认系统今天）")
    ap.add_argument("--limit", type=int, default=MAX_ITEMS, help=f"最多打标条数（默认 {MAX_ITEMS}）")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--no-seen", action="store_true", help="忽略台账，强制重评（默认跳过已评过的）")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不调模型")
    ap.add_argument("--quiet", action="store_true", help="cron 用：成功不输出")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    since = (today - timedelta(days=args.days)).isoformat()
    until = today.isoformat()
    day = until

    raw = collect(args.vault, since, until)
    if not raw:
        if not args.quiet:
            print(f"[{day}] 窗口 {since}~{until} 内无新素材，跳过。")
        return 0

    pairs = similarity_pairs(raw)
    seen = set() if args.no_seen else load_seen()
    todo = [i for i in raw if i["src"] not in seen]
    skipped = len(raw) - len(todo)
    todo.sort(key=lambda x: x["date"], reverse=True)
    todo = todo[: args.limit]

    if args.dry_run:
        print(f"[dry-run] {since}~{until}：真实素材 {len(raw)} 条｜已评过 {skipped} 条｜"
              f"本次将打标 {len(todo)} 条")
        for a, b in pairs[:10]:
            print(f"  同题提示: {a['title'][:30]} ／ {b['title'][:30]}")
        return 0

    if not todo:
        # 没有新素材时**不重写日报**（否则会用空报告覆盖当天已有内容）
        if not args.quiet:
            print(f"[{day}] 无新素材（窗口内 {len(raw)} 条均已评过），跳过。")
        return 0

    scored, usage = ask(todo, args.model)
    meta = {"since": since, "until": until, "raw": len(raw), "model": args.model,
            "tokens": usage["input_tokens"]}
    report = args.vault / POOL_REL / f"_Jev取舍-{day}.md"
    report.write_text(render(day, scored, meta, pairs, skipped), encoding="utf-8", newline="\n")

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as fh:
        for it in scored:
            fh.write(json.dumps({
                "run_date": day, "title": it["title"], "platform": it["plat"],
                "material_date": it["date"], "card": it["card"], "src": it["src"],
                "bucket": it["bucket"], "confidence": round(it["confidence"], 4),
                "new_info": round(it["new_info"], 4), "model": it["model"],
            }, ensure_ascii=False) + "\n")

    if not args.quiet:
        counts = {b: sum(1 for x in scored if x["bucket"] == b) for b in ("now", "later", "skip")}
        print(f"[{day}] 素材 {len(raw)}｜跳过已评 {skipped}｜打标 {len(scored)}｜"
              f"now {counts['now']} / later {counts['later']} / skip {counts['skip']}｜"
              f"token {usage['input_tokens']} ≈ ${usage['input_tokens']*0.042/1e6:.6f}")
        print(f"  日报：{report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
