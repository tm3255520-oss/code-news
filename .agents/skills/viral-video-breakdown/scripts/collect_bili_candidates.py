#!/usr/bin/env python3
"""
collect_bili_candidates.py - B站 DSH 候选池采集器（确定性 🔵，无 LLM）

流程：
  关键词搜索 -> 收集 bvid -> view API 全指标 -> 质量代理指标(收藏率/赞率/投币率)
  -> 竞品作者空间枚举(补作者中位数=相对基线) -> 阈值筛选 -> 候选清单+指标表

铁律：限速(请求间隔)、412 直接跳过、失败跳过+标记、不重试、不碰登录墙。

用法：
  python collect_bili_candidates.py [--config config.yaml] [--limit N]
  python collect_bili_candidates.py --keywords "dsh 插件,deepseek harness" --limit 20

产物（输出到 out_dir）：
  candidates.json      全字段候选
  candidates.csv       扁平指标表
  candidate_pool.md    人读候选清单（按播放排序）
"""
import sys
import os
import re
import csv
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

DEFAULT_CONFIG = {
    "bili": {
        "keywords": [
            "deepseek harness", "dsh 插件", "dsh-std",
            "DeepSeek Harness 插件", "deepseek harness 教程",
        ],
        "seed_author_mids": [12890453],   # 程序员鱼皮等 DSH 头部作者
        "top_authors_to_scan": 5,          # 自动发现后枚举前 N 个作者空间
        "search_pages": 2,                 # 每关键词抓几页
        "request_interval_s": 2.5,         # 请求间隔（防 412）
        "min_play": 2000,                  # 候选初筛播放下限
        "min_fav_rate": 0.02,              # 收藏率下限（资料价值）
        "max_authors": 30,                 # 自动发现作者数上限
        "max_candidates": 80,              # 最终候选数上限
        "max_stat_candidates": 40,         # 抓全指标的候选数上限（防超时，按播放取 topN）
    }
}


def log(msg, tag="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


def load_config(path=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and os.path.exists(path):
        try:
            import yaml
            user = yaml.safe_load(open(path, encoding="utf-8")) or {}
            b = user.get("bili") or {}
            cfg["bili"].update({k: v for k, v in b.items()})
        except Exception as e:
            log(f"config 加载失败，用默认: {e}", "WARN")
    return cfg


def http_get_json(url, interval_s):
    """带限速的 GET JSON；返回 dict 或 None（跳过）。"""
    time.sleep(interval_s)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://search.bilibili.com/",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            data = resp.read().decode("utf-8", "replace")
        if status == 412:
            return {"_risk": True}
        obj = json.loads(data)
        return obj
    except Exception as e:
        log(f"请求失败 {url[:70]}: {str(e)[:80]}", "WARN")
        return None


def clean_title(t):
    return re.sub(r"</?em[^>]*>", "", t or "").strip()


def parse_duration(s):
    """B站搜索结果 duration 是 'MM:SS'/'H:MM:SS' 字符串，view API 是秒。统一转秒。"""
    if isinstance(s, int):
        return s
    try:
        parts = str(s).split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0


SEARCH_URLS = [
    "https://api.bilibili.com/x/web-interface/wbi/search/type",  # 实测更稳
    "https://api.bilibili.com/x/web-interface/search/type",      # 旧端点兜底
]


def search_bili(keyword, pages, interval):
    """返回 (bvid -> {bvid,title,author,mid,play,comment,fav,duration,pubdate})"""
    out = {}
    for p in range(1, pages + 1):
        q = urllib.parse.quote(keyword)
        obj = None
        for base in SEARCH_URLS:
            obj = http_get_json(f"{base}?search_type=video&keyword={q}&page={p}", interval)
            if obj and not obj.get("_risk") and obj.get("code") == 0:
                break
            obj = None
        if obj is None:
            log(f"  [搜索] '{keyword}' 第 {p} 页失败(风控/异常)，跳过", "WARN")
            break
        if obj is None:
            break
        if obj.get("_risk"):
            log(f"  [412风控] 关键词 '{keyword}' 第 {p} 页跳过", "WARN")
            break
        if obj.get("code") != 0:
            log(f"  搜索失败 code={obj.get('code')} '{keyword}' p{p}", "WARN")
            break
        rs = ((obj.get("data") or {}).get("result")) or []
        if not rs:
            break
        for r in rs:
            bv = r.get("bvid")
            if not bv:
                continue
            out[bv] = {
                "bvid": bv, "title": clean_title(r.get("title")),
                "author": r.get("author", ""), "mid": r.get("mid", 0),
                "play": int(r.get("play") or 0),
                "comment": int(r.get("video_review") or 0),
                "fav": int(r.get("favorites") or 0),
                "duration": parse_duration(r.get("duration")),
                "pubdate": int(r.get("pubdate") or 0),
            }
        if len(rs) < 20:
            break
    return out


def get_stat(bvid, interval):
    obj = http_get_json(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", interval)
    if not obj or obj.get("code") != 0 or not obj.get("data"):
        return None
    d = obj["data"]
    s = d.get("stat", {})
    return {
        "view": int(s.get("view") or 0), "like": int(s.get("like") or 0),
        "reply": int(s.get("reply") or 0), "favorite": int(s.get("favorite") or 0),
        "coin": int(s.get("coin") or 0), "share": int(s.get("share") or 0),
        "danmaku": int(s.get("danmaku") or 0),
        "duration": int(d.get("duration") or 0),
        "pubdate": int(d.get("pubdate") or 0),
    }


def author_videos(mid, interval, max_pages=3):
    """枚举作者空间视频列表（含播放），返回 {bvid: {title, play, pubdate, duration}}"""
    out = {}
    for p in range(1, max_pages + 1):
        obj = http_get_json(
            f"https://api.bilibili.com/x/space/arc/search?mid={mid}&ps=30&pn={p}",
            interval)
        if not obj or obj.get("code") != 0:
            break
        vlist = (((obj.get("data") or {}).get("list")) or {}).get("vlist") or []
        if not vlist:
            break
        for v in vlist:
            out[v.get("bvid")] = {
                "title": clean_title(v.get("title")),
                "play": int(v.get("play") or 0),
                "pubdate": int(v.get("created") or 0),
                "duration": parse_duration(v.get("length")),
            }
        if len(vlist) < 30:
            break
    return out


def author_median_via_search(author, interval, pages=1):
    """降级方案：空间接口被风控时，用搜索接口按作者名聚合播放量，近似中位数。
    注意：搜索返回的是作者热门视频（偏高偏保守）；只算成功页，单页失败不丢数据。"""
    plays = []
    for p in range(1, pages + 1):
        q = urllib.parse.quote(author)
        obj = http_get_json(
            f"https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={q}&page={p}",
            interval)
        if not obj or obj.get("_risk") or obj.get("code") != 0:
            break
        rs = ((obj.get("data") or {}).get("result")) or []
        for r in rs:
            if r.get("author") == author:
                plays.append(int(r.get("play") or 0))
        if len(rs) < 20:
            break
    if not plays:
        return None
    return sorted(plays)[len(plays) // 2]


def is_dsh_title(t):
    t = t.lower()
    pat = re.compile(r"deepseek.?harness|dsh[ -]?std|dsh[ -]?插件|deepseek.?插件|dsh")
    return bool(pat.search(t))


def compute_rates(c):
    v = max(c["view"], 1)
    c["fav_rate"] = round(c["favorite"] / v, 4)
    c["like_rate"] = round(c["like"] / v, 4)
    c["coin_rate"] = round(c["coin"] / v, 4)
    c["reply_rate"] = round(c["reply"] / v, 4)
    c["rel_to_median"] = None
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--keywords", default=None, help="覆盖关键词，逗号分隔")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个候选（测试用）")
    ap.add_argument("--skip-author-scan", action="store_true", help="跳过作者空间枚举")
    args = ap.parse_args()
    cfg = load_config(args.config)["bili"]

    keywords = [k.strip() for k in (args.keywords or "").split(",")] if args.keywords else cfg["keywords"]
    out_dir = args.out_dir or os.path.join(os.getcwd(), "candidate_pool")
    os.makedirs(out_dir, exist_ok=True)
    interval = cfg["request_interval_s"]
    log(f"关键词池: {keywords}")
    log(f"限速 {interval}s/请求 | 播放下限 {cfg['min_play']} | 收藏率下限 {cfg['min_fav_rate']}")

    # ---- 1. 搜索收集 ----
    found = {}
    risk_keywords = []
    for kw in keywords:
        rs = search_bili(kw, cfg["search_pages"], interval)
        if rs:
            log(f"  [搜索] '{kw}' 新增 {len(rs)} 条")
            found.update(rs)
        else:
            risk_keywords.append(kw)
    log(f"搜索去重后共 {len(found)} 条")

    # ---- 2. 自动作者发现（按 DSH 播放量）----
    authors = {}
    for bv in found.values():
        if bv["play"] >= cfg["min_play"]:
            a = authors.setdefault(bv["mid"], {"name": bv["author"], "plays": 0, "count": 0})
            a["plays"] += bv["play"]
            a["count"] += 1
    top_authors = sorted(authors.items(), key=lambda x: -x[1]["plays"])[:cfg["max_authors"]]
    log(f"自动发现候选作者 {len(top_authors)} 个")

    # 种子作者并入
    seed = {m: "seed" for m in cfg["seed_author_mids"]}
    for m in seed:
        if m not in authors:
            top_authors.append((m, {"name": f"mid:{m}", "plays": 0, "count": 0}))

    # ---- 3. 作者空间枚举（补 DSH 视频 + 中位数基线）----
    author_median = {}
    scanned = 0
    if not args.skip_author_scan:
        for mid, info in top_authors[:cfg["top_authors_to_scan"]]:
            vids = author_videos(mid, interval)
            src = "space"
            if not vids:
                # 降级：空间接口被风控，用搜索近似中位数
                med = author_median_via_search(info["name"], interval)
                if med is None:
                    continue
                author_median[mid] = med
                src = "search-approx"
                scanned += 1
                log(f"  [作者] {info['name']} 中位数≈{med}(搜索近似，偏高偏保守)")
                continue
            plays = [v["play"] for v in vids.values() if v["play"] > 0]
            author_median[mid] = sorted(plays)[len(plays) // 2] if plays else None
            # 作者空间里命中的 DSH 视频并入候选
            for bv, v in vids.items():
                if is_dsh_title(v["title"]) and v["play"] >= cfg["min_play"]:
                    found.setdefault(bv, {
                        "bvid": bv, "title": v["title"], "author": info["name"],
                        "mid": mid, "play": v["play"], "comment": 0, "fav": 0,
                        "duration": v["duration"], "pubdate": v["pubdate"],
                    })
            scanned += 1
            log(f"  [作者] {info['name']}(mid={mid}) 中位数={author_median[mid]}({src})")
    log(f"作者空间枚举完成（{scanned} 个），候选总数 {len(found)}")

    # ---- 4. 全指标（按播放取 topN 处理，防超时）----
    cap = cfg.get("max_stat_candidates", 40)
    ordered = sorted(found.values(), key=lambda x: -(x.get("play") or 0))[:cap]
    log(f"按播放取 top {min(cap, len(ordered))} 条抓全指标")
    cands = []
    for c in ordered:
        st = get_stat(c["bvid"], interval)
        if st:
            c.update(st)
        c = compute_rates(c)
        c["author_median"] = author_median.get(c.get("mid"))
        if c.get("author_median"):
            c["rel_to_median"] = round(c["view"] / max(c["author_median"], 1), 2)
        cands.append(c)
        if args.limit and len(cands) >= args.limit:
            break
    log(f"指标抓取完成，共 {len(cands)} 条")

    # ---- 5. 阈值筛选 ----
    keep = [c for c in cands if c["view"] >= cfg["min_play"]]
    keep.sort(key=lambda x: -x["view"])

    # ---- 6. 落盘 ----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"candidates_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": ts, "keywords": keywords,
                   "risk_keywords": risk_keywords, "count": len(keep),
                   "candidates": keep}, f, ensure_ascii=False, indent=1)

    csv_path = os.path.join(out_dir, f"candidates_{ts}.csv")
    cols = ["bvid", "title", "author", "mid", "view", "like", "reply", "favorite",
            "coin", "share", "danmaku", "fav_rate", "like_rate", "coin_rate",
            "reply_rate", "duration", "pubdate", "author_median", "rel_to_median"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in keep:
            w.writerow(c)

    # 人读清单
    md_lines = ["# DSH 候选池（B站自动采集）", "",
                f"> 生成：{ts}｜关键词：{', '.join(keywords)}｜风控跳过：{risk_keywords or '无'}", "",
                "| # | 播放 | 收藏率 | 赞率 | 投币率 | 相对作者中位数 | 时长 | 标题 | 作者 | bvid |", "|---|---:|---:|---:|---:|---:|---:|---|---|---|"]
    for i, c in enumerate(keep[:cfg["max_candidates"]], 1):
        rel = c.get("rel_to_median") if c.get("rel_to_median") is not None else "-"
        dur = f"{c['duration']//60}:{c['duration']%60:02d}"
        md_lines.append(
            f"| {i} | {c['view']:,} | {c.get('fav_rate',0):.1%} | {c.get('like_rate',0):.1%} "
            f"| {c.get('coin_rate',0):.1%} | {rel} | {dur} | {c['title'][:44]} | "
            f"{c.get('author','')} | [{c['bvid']}](https://www.bilibili.com/video/{c['bvid']}) |")
    md_lines.append("")
    if risk_keywords:
        md_lines.append("> ⚠️ 以下关键词被风控(412)跳过，下次自动采集会重试：" + ", ".join(risk_keywords))
    md_path = os.path.join(out_dir, f"candidate_pool_{ts}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    log(f"✅ 候选池 {len(keep)} 条 -> {json_path}")
    log(f"   指标表 -> {csv_path}")
    log(f"   人读清单 -> {md_path}")
    print("\n" + "\n".join(md_lines))


if __name__ == "__main__":
    main()
