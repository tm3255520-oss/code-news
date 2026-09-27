#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""redfox_search.py — RedFox 搜索类能力的会话内入口（toolkit-mcp 接线用）

把已经跑通的各平台采集脚本里**已验证**的搜索接口抽成一条统一 CLI，
让智能体在会话里直接按关键词取结构化数据，不必等 cron、也不用翻落盘文件。

端点与参数全部来自既有采集脚本（不是文档猜测）：
    小红书   /story/api/xhsUser/searchArticle   {keyword, offset, sortType:"_0"}
    抖音     /story/api/dyData/searchArticle    {keyword, offset, sortType:"_4"}
    抖音账号 /story/api/dy/data/listWorkByAccount {uniqueName, pageNum, pageSize, sortType:"_2"}
    公众号   /story/api/gzhData/searchArticle   {keyword, offset, sortType:"_4"}
    公众号账号 /story/api/gzhData/queryWorkList {accountName, offset, sortType:"_2"}
    公众号榜单 /story/api/cozeSkill/getTenWReadingRank | getOriginalRank {type, startDate, endDate}
    B站      /story/api/bili/data/workSearch    {keyword, page, pageSize, order}
    视频号   /story/api/sphAllData/searchWork   {keyword, sort}

定位：**只读**。不做闸门、不写 vault、不转录——那是采集脚本的事。
本脚本只负责「给我关键词，还我结构化列表」，供会话内快速查。

用法:
    python redfox_search.py --selftest
    python redfox_search.py xhs "AI 智能体" --limit 10
    python redfox_search.py douyin "Claude Code" --limit 10
    python redfox_search.py gzh "AI 编程" --limit 10
    python redfox_search.py gzh-rank --category 科技数码 --days 7
    python redfox_search.py bilibili "AI 工具" --limit 10
    python redfox_search.py shipinhao "AI 副业" --limit 10
    python redfox_search.py trending            # 全网热点（多平台榜单聚合）

边界（2026-09-27 Phase 2 明确，避免重复实现）：
    本脚本只管「关键词检索」+ 公众号榜单/全网热点。
    抖音与小红书的**榜单/账号榜/涨粉榜/对标/账号诊断**不在本脚本，走 redfox_skill：
        python redfox_skill.py douyin-daily-hot --limit 3
        python redfox_skill.py xiaohongshu-weeklytop --top_n 20
    那些能力由官方 skill 实现（已逐枚验证），此处**刻意不再复制一份**。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

from redfox_client import RedFox, num, read_count  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- 已验证端点 ----
EP = {
    "xhs": "/story/api/xhsUser/searchArticle",
    "douyin": "/story/api/dyData/searchArticle",
    "douyin_account": "/story/api/dy/data/listWorkByAccount",
    "gzh": "/story/api/gzhData/searchArticle",
    "gzh_account": "/story/api/gzhData/queryWorkList",
    "gzh_rank_10w": "/story/api/cozeSkill/getTenWReadingRank",
    "gzh_rank_orig": "/story/api/cozeSkill/getOriginalRank",
    "bilibili": "/story/api/bili/data/workSearch",
    "shipinhao": "/story/api/sphAllData/searchWork",
}

# 榜单日期窗口：口径抄自 wechat_redfox_collect.py（已验证跑通），
# end 必须是**昨天**——榜单每日 18:30 后才更新昨日数据，传今天会返回空
RANK_END_OFFSET_DAYS = 1


def _rank_dates(days: int) -> tuple[str, str]:
    today = datetime.now()
    end = today - timedelta(days=RANK_END_OFFSET_DAYS)
    start = today - timedelta(days=max(days, RANK_END_OFFSET_DAYS + 1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# 榜单分类（公众号采集脚本里用的口径）
GZH_RANK_CATEGORIES = ("科技数码", "知识百科", "创投商业")


# --------------------------------------------------------------------------- #
# 归一化：各平台字段名不同，统一成同一套键，便于会话内比对
# --------------------------------------------------------------------------- #
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _i(v: Any) -> int:
    try:
        return int(num(v))
    except (TypeError, ValueError):
        return 0


def norm(w: dict, platform: str, keyword: str) -> dict:
    """把任意平台的原始条目归一成统一结构。缺失字段留空，不抛异常。

    字段映射按各平台**实测返回**写死（来源：各个 *_redfox_collect.py 的 normalize）：
        小红书 workId/workTitle/accountNickname/workDesc/workUrl/...Count/workType
        抖音   workId|videoId/title|content/accountName|authorName/authorUniqueId/
               workUrl|opusUrl/likeCount/collectCount/commentCount/shareCount+repostCount/
               duration(毫秒)/publishTime/followerCount
        公众号 workUuid|photoId/title/userName|author/oriUrl|workUrl|sourceUrl/
               clicksCount|readCount(可能为 "10w+")/likeCount/watchCount/shareCount/
               commentCount/publicTime
        B站    bvId/title/author/description/playCount/likeCount/favoriteCount/
               commentCount/shareCount/coinCount/duration/created/tagNames
        视频号 videoId|exportId/description(即标题)/nickname/videoUrl/likeCount/
               favCount/forwardCount/commentCount/videoDuration/publishTime
    """
    desc_raw = _s(w.get("workDesc") or w.get("desc") or w.get("digest")
                  or w.get("description") or w.get("summary"))
    uid = _s(w.get("workId") or w.get("id") or w.get("workUuid") or w.get("uuid")
             or w.get("bvId") or w.get("videoId") or w.get("exportId")
             or w.get("photoId"))
    title = _s(w.get("workTitle") or w.get("title") or w.get("articleTitle"))
    if not title:
        # 抖音用 content 当标题；视频号没有独立标题字段，用描述开头
        title = _s(w.get("content")) or (desc_raw[:60] if platform == "shipinhao" else "")
    author = _s(w.get("accountNickname") or w.get("accountName") or w.get("userName")
                or w.get("authorName") or w.get("nickname") or w.get("author")
                or w.get("originalAuthor"))
    url = _s(w.get("workUrl") or w.get("url") or w.get("articleUrl")
             or w.get("link") or w.get("videoUrl") or w.get("oriUrl")
             or w.get("sourceUrl") or w.get("opusUrl"))
    if not url and w.get("bvId"):
        url = f"https://www.bilibili.com/video/{w['bvId']}"
    tags = w.get("tagNames") or []
    # 时长：抖音返回毫秒（>1000 视为毫秒），其余平台返回秒
    dur = num(w.get("duration") or w.get("videoDuration"))
    duration = int(dur / 1000) if dur > 1000 else int(dur)
    return {
        "author_id": _s(w.get("authorUniqueId") or w.get("authorId")),
        "author_fans": _i(w.get("followerCount") or w.get("authorFansCount")),
        "is_original": bool(w.get("originalFlag") or w.get("isOriginal")),
        "platform": platform,
        "uid": uid,
        "title": title[:120],
        "author": author,
        "url": url,
        "desc": desc_raw[:300],
        "like": _i(w.get("workLikedCount") or w.get("likeCount") or w.get("praiseNum")),
        "collect": _i(w.get("workCollectedCount") or w.get("collectCount")
                      or w.get("favoriteCount") or w.get("favCount")),
        "comment": _i(w.get("workCommentsCount") or w.get("commentCount")),
        "share": _i(w.get("workSharedCount") or w.get("shareCount")
                    or w.get("forwardCount")) + _i(w.get("repostCount")),
        # 公众号阅读数可能是 "10w+" 这类字符串，走 read_count 解析
        "read": read_count(w.get("clicksCount") or w.get("readCount") or w.get("readNum")),
        "watch": _i(w.get("watchCount")),
        "play": _i(w.get("playCount")),
        "duration": duration,
        "tags": " ".join(_s(t) for t in tags) if isinstance(tags, list) else _s(tags),
        "publish_time": _s(w.get("workPublishTime") or w.get("publishTime")
                           or w.get("createTime") or w.get("pubTime")
                           or w.get("created") or w.get("publicTime")),
        "keyword": keyword,
    }


def _unwrap(data: Any) -> list:
    """列表型接口兼容各平台实际键名。

    B站 workSearch 返回 {"workList": [...]}，与其它平台的 list/records/data 不同，
    这是实测踩过的坑（按通用键名取会拿到 0 条）。
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("list", "accountList", "records", "data", "items", "result",
                  "workList"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _emit(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# 单次返回的条数硬上限。工具结果要在会话里当文本传，无限大既撑爆调用方的
# stdout 截断线、也挤占模型上下文，所以在这里封顶并显式标注被截断。
HARD_MAX_ITEMS = 30
# 必留字段（定位一条内容的最小集合）
_KEEP_ALWAYS = ("platform", "uid", "title", "author", "url", "keyword")
# 有值才留的字段（0/空串/False 一律省掉，JSON 体积能小一半以上）
_KEEP_IF_SET = ("like", "collect", "comment", "share", "read", "watch", "play",
                "duration", "author_fans", "publish_time", "author_id", "is_original")


def _slim(row: dict) -> dict:
    """压掉空字段，控制单条体积。"""
    out = {k: row.get(k) for k in _KEEP_ALWAYS}
    for k in _KEEP_IF_SET:
        v = row.get(k)
        if v not in (0, "", None, False):
            out[k] = v
    desc = _s(row.get("desc"))
    if desc:
        out["desc"] = desc[:80]
    tags = _s(row.get("tags"))
    if tags:
        out["tags"] = tags[:60]
    return out


def _finalize(payload: dict) -> dict:
    """统一收口：瘦身 → 封顶 → 标注截断。"""
    rows = payload.get("data") or []
    total = len(rows)
    if total > HARD_MAX_ITEMS:
        rows = rows[:HARD_MAX_ITEMS]
        payload["truncated"] = True
    payload["data"] = [_slim(r) for r in rows]
    payload["count"] = len(payload["data"])
    payload["total_matched"] = total
    return payload


# --------------------------------------------------------------------------- #
# 各平台查询
# --------------------------------------------------------------------------- #
def search_xhs(keyword: str, limit: int, sort: str, rf: RedFox) -> dict:
    lst = rf.listing(EP["xhs"], {"keyword": keyword, "offset": 0, "sortType": sort})
    rows = [norm(x, "xiaohongshu", keyword) for x in lst][:limit]
    return {"status": "ok", "platform": "xiaohongshu", "keyword": keyword,
            "count": len(rows), "data": rows}


def search_douyin(keyword: str, limit: int, sort: str, rf: RedFox) -> dict:
    lst = rf.listing(EP["douyin"], {"keyword": keyword, "offset": 0, "sortType": sort})
    rows = [norm(x, "douyin", keyword) for x in lst][:limit]
    return {"status": "ok", "platform": "douyin", "keyword": keyword,
            "count": len(rows), "data": rows}


def search_douyin_account(unique_name: str, limit: int, rf: RedFox) -> dict:
    lst = rf.listing(EP["douyin_account"],
                     {"uniqueName": unique_name, "pageNum": 1,
                      "pageSize": max(limit, 20), "sortType": "_2"})
    rows = [norm(x, "douyin", f"账号·{unique_name}") for x in lst][:limit]
    return {"status": "ok", "platform": "douyin", "account": unique_name,
            "count": len(rows), "data": rows}


def search_gzh(keyword: str, limit: int, sort: str, rf: RedFox) -> dict:
    lst = rf.listing(EP["gzh"], {"keyword": keyword, "sortType": sort, "offset": 0})
    rows = [norm(x, "gongzhonghao", keyword) for x in lst][:limit]
    return {"status": "ok", "platform": "gongzhonghao", "keyword": keyword,
            "count": len(rows), "data": rows}


def search_gzh_account(account: str, limit: int, rf: RedFox) -> dict:
    lst = rf.listing(EP["gzh_account"],
                     {"accountName": account, "offset": 0, "sortType": "_2"})
    rows = [norm(x, "gongzhonghao", f"账号·{account}") for x in lst][:limit]
    return {"status": "ok", "platform": "gongzhonghao", "account": account,
            "count": len(rows), "data": rows}


def search_gzh_rank(category: str, days: int, limit: int, rf: RedFox) -> dict:
    """公众号榜单：10W+ 阅读榜 + 原创爆款榜。一次调用即带正文/阅读数。"""
    start, end = _rank_dates(days)
    body = {"type": category, "startDate": start, "endDate": end}
    out: list[dict] = []
    used: list[str] = []
    for name, path in (("10W+榜", EP["gzh_rank_10w"]), ("原创爆款榜", EP["gzh_rank_orig"])):
        data = rf.call(path, body)
        items = _unwrap(data)
        if items:
            used.append(f"{name}·{category}({len(items)})")
        out += [norm(x, "gongzhonghao", f"{name}·{category}") for x in items]
    rows = out[:limit]
    return {"status": "ok", "platform": "gongzhonghao", "category": category,
            "days": days, "sources": used, "count": len(rows), "data": rows}


def search_bilibili(keyword: str, limit: int, order: str, rf: RedFox) -> dict:
    data = rf.call(EP["bilibili"],
                   {"keyword": keyword, "page": "1",
                    "pageSize": max(limit, 10), "order": order})
    rows = [norm(x, "bilibili", keyword) for x in _unwrap(data)][:limit]
    return {"status": "ok", "platform": "bilibili", "keyword": keyword,
            "count": len(rows), "data": rows}


def search_shipinhao(keyword: str, limit: int, sort: str, rf: RedFox) -> dict:
    lst = rf.listing(EP["shipinhao"], {"keyword": keyword, "sort": sort})
    rows = [norm(x, "shipinhao", keyword) for x in lst][:limit]
    return {"status": "ok", "platform": "shipinhao", "keyword": keyword,
            "count": len(rows), "data": rows}


def search_trending(categories: tuple = GZH_RANK_CATEGORIES, days: int = 1,
                    limit_per: int = 10, rf: RedFox | None = None) -> dict:
    """全网热点：现阶段用公众号两榜按分类聚合（已验证可用）。

    说明：营销页宣传的跨 7 平台 trending hub 接口在既有代码里**没有出现**，
    未经验证不接线；此处只聚合已跑通的榜单接口，避免给会话喂假能力。
    """
    rf = rf or RedFox()
    start, end = _rank_dates(days)
    body_dates = {"startDate": start, "endDate": end}
    out: list[dict] = []
    sources: list[str] = []
    for cat in categories:
        for name, path in (("10W+榜", EP["gzh_rank_10w"]), ("原创爆款榜", EP["gzh_rank_orig"])):
            data = rf.call(path, {"type": cat, **body_dates})
            items = _unwrap(data)
            if items:
                sources.append(f"{name}·{cat}({len(items)})")
            out += [norm(x, "gongzhonghao", f"{name}·{cat}") for x in items[:limit_per]]
    out.sort(key=lambda r: (-r["read"], -r["like"]))
    return {"status": "ok", "scope": "gzh_ranks", "days": days,
            "sources": sources, "count": len(out), "data": out}


# --------------------------------------------------------------------------- #
# 自检（不联网）
# --------------------------------------------------------------------------- #
def selftest() -> int:
    raw = {"workId": "abc", "workTitle": "AI 工具实测", "accountNickname": "测试博主",
           "workUrl": "https://x/abc", "workLikedCount": "1200", "workCollectedCount": "800",
           "workCommentsCount": "120", "workSharedCount": "300",
           "workPublishTime": "2026-09-18 10:00:00", "workDesc": "简介"}
    r = norm(raw, "xiaohongshu", "kw")
    assert r["uid"] == "abc" and r["like"] == 1200 and r["collect"] == 800, r
    assert r["comment"] == 120 and r["share"] == 300, r
    # 空值不炸
    r2 = norm({}, "douyin", "kw")
    assert r2["uid"] == "" and r2["like"] == 0
    # B站真实字段（bvId / playCount / favoriteCount / created / tagNames）
    bili = norm({"bvId": "BV1xx", "title": "AI 智能体实战", "author": "测试UP",
                 "playCount": "120000", "likeCount": "3000", "favoriteCount": "1200",
                 "commentCount": "220", "shareCount": "500", "coinCount": "100",
                 "duration": 180, "created": "2026-09-18 10:00:00",
                 "tagNames": ["AI", "教程"]}, "bilibili", "kw")
    assert bili["uid"] == "BV1xx", bili
    assert bili["url"].endswith("/BV1xx"), bili
    assert bili["play"] == 120000 and bili["collect"] == 1200, bili
    assert bili["duration"] == 180 and "AI" in bili["tags"], bili
    # 视频号真实字段（description 当标题 / nickname / favCount / forwardCount）
    sph = norm({"videoId": "v1", "description": "AI 副业怎么起步",
                "nickname": "测试号", "videoUrl": "https://finder/x",
                "likeCount": "7072", "favCount": "30", "forwardCount": "12",
                "commentCount": "39", "videoDuration": 60,
                "publishTime": "2026-09-24 12:00:00"}, "shipinhao", "kw")
    assert sph["uid"] == "v1" and sph["author"] == "测试号", sph
    assert sph["title"] == "AI 副业怎么起步", sph
    assert sph["collect"] == 30 and sph["share"] == 12, sph
    assert sph["duration"] == 60 and sph["url"] == "https://finder/x", sph
    # 公众号真实字段（workUuid/userName/oriUrl/clicksCount 可能为 "10w+"/publicTime）
    gzh = norm({"workUuid": "u1", "title": "AI 编程工具排行", "userName": "菜鸟教程",
                "oriUrl": "https://mp.weixin.qq.com/s?x", "clicksCount": "10w+",
                "likeCount": "81", "watchCount": "40", "shareCount": "330",
                "commentCount": "21", "publicTime": "2026-08-31 11:27:00",
                "originalFlag": 1}, "gongzhonghao", "kw")
    assert gzh["uid"] == "u1" and gzh["author"] == "菜鸟教程", gzh
    assert gzh["read"] == 100000 and gzh["watch"] == 40, gzh
    assert gzh["url"].startswith("https://mp.weixin.qq.com"), gzh
    assert gzh["publish_time"] == "2026-08-31 11:27:00", gzh
    assert gzh["is_original"] is True, gzh
    # 抖音真实字段（accountName/含毫秒 duration/collectCount/repostCount 累加）
    dy = norm({"workId": "w1", "title": "6款Agent工具实测", "accountName": "珍妮丁丁说AI",
               "authorUniqueId": "jenny", "workUrl": "https://iesdouyin/x",
               "likeCount": "132113", "collectCount": "81745", "commentCount": "2925",
               "shareCount": "19818", "repostCount": "100", "duration": 56913,
               "followerCount": "500000", "publishTime": "2026-07-14 20:30:00"},
              "douyin", "kw")
    assert dy["uid"] == "w1" and dy["author"] == "珍妮丁丁说AI", dy
    assert dy["author_fans"] == 500000 and dy["duration"] == 56, dy  # 毫秒 → 秒
    assert dy["share"] == 19918, dy  # shareCount + repostCount
    assert dy["collect"] == 81745, dy
    # 抖音毫秒阈值边界：正好 1000 按秒，>1000 按毫秒
    assert norm({"duration": 1000}, "douyin", "k")["duration"] == 1000
    assert norm({"duration": 1001}, "douyin", "k")["duration"] == 1
    # 榜单日期窗口：end 必须是昨天（传今天接口返回空，见 code=3203 实测）
    start, end = _rank_dates(7)
    today = datetime.now()
    assert end == (today - timedelta(days=1)).strftime("%Y-%m-%d"), (start, end)
    assert start == (today - timedelta(days=7)).strftime("%Y-%m-%d"), (start, end)
    # days 小于等于 1 时也要留出「昨天」这一格，不能退化成同日窗口
    s1, e1 = _rank_dates(1)
    assert s1 != e1, (s1, e1)
    # 瘦身：空/零字段被丢掉，非零指标保留
    slim = _slim(norm({"workId": "x", "workTitle": "T", "accountNickname": "A",
                       "workUrl": "u", "workLikedCount": "5"}, "xiaohongshu", "k"))
    assert "like" in slim and slim["like"] == 5, slim
    assert "read" not in slim and "desc" not in slim, slim
    assert "collect" not in slim, slim
    # 封顶：超过硬上限时截断并标注
    big = {"status": "ok", "data": [dict(slim) for _ in range(HARD_MAX_ITEMS + 7)]}
    fin = _finalize(big)
    assert fin["count"] == HARD_MAX_ITEMS and fin["truncated"] is True, fin.keys()
    assert fin["total_matched"] == HARD_MAX_ITEMS + 7, fin["total_matched"]
    # 未超限时不标注 truncated
    fin2 = _finalize({"status": "ok", "data": [{"platform": "x"}]})
    assert "truncated" not in fin2 and fin2["count"] == 1
    # 各种列表键名都能解开（含 B站的 workList）
    assert len(_unwrap({"list": [1, 2]})) == 2
    assert len(_unwrap({"records": [1]})) == 1
    assert len(_unwrap({"data": [1, 2, 3]})) == 3
    assert len(_unwrap({"workList": [1, 2]})) == 2
    assert len(_unwrap([1])) == 1
    assert len(_unwrap({"nope": 1})) == 0
    # 端点常量都在
    for k in ("xhs", "douyin", "gzh", "bilibili", "shipinhao"):
        assert EP[k].startswith("/story/api/"), k
    print("SELFTEST PASS: norm(xhs/dy/gzh/bili/sph 真实字段) / "
          "_unwrap(含 workList) / 毫秒时长阈值 / 端点常量")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="RedFox 搜索（会话内只读入口）")
    ap.add_argument("--selftest", action="store_true", help="离线自检，不联网")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("xhs", help="小红书关键词搜索")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", default="_0", help="sortType，默认 _0")

    p = sub.add_parser("douyin", help="抖音关键词搜索")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", default="_4", help="sortType，默认 _4")

    p = sub.add_parser("douyin-account", help="抖音按账号取作品")
    p.add_argument("unique_name")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("gzh", help="公众号关键词搜索")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", default="_4", help="sortType，默认 _4")

    p = sub.add_parser("gzh-account", help="公众号按账号取文章")
    p.add_argument("account")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("gzh-rank", help="公众号榜单（10W+/原创爆款）")
    p.add_argument("--category", default="科技数码")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("bilibili", help="B站关键词搜索")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--order", default="time", help="time/duration/click")

    p = sub.add_parser("shipinhao", help="视频号关键词搜索")
    p.add_argument("keyword")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", default="最多点赞")

    p = sub.add_parser("trending", help="全网热点（公众号榜单聚合）")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--limit-per", type=int, default=10)

    return ap


def main() -> int:
    args = build_parser().parse_args()
    if args.selftest:
        return selftest()
    if not args.cmd:
        build_parser().print_help()
        return 2

    rf = RedFox()
    # redfox_client 在接口报错时会把诊断打到 stdout，而本脚本是给 MCP 当子进程调的——
    # stdout 必须是纯 JSON，否则调用方 json.loads 直接炸。所以查询期间的输出全部截获，
    # 收尾时作为 warnings 字段塞回结果里（信息不丢，但不再污染 stdout）。
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            if args.cmd == "xhs":
                out = search_xhs(args.keyword, args.limit, args.sort, rf)
            elif args.cmd == "douyin":
                out = search_douyin(args.keyword, args.limit, args.sort, rf)
            elif args.cmd == "douyin-account":
                out = search_douyin_account(args.unique_name, args.limit, rf)
            elif args.cmd == "gzh":
                out = search_gzh(args.keyword, args.limit, args.sort, rf)
            elif args.cmd == "gzh-account":
                out = search_gzh_account(args.account, args.limit, rf)
            elif args.cmd == "gzh-rank":
                out = search_gzh_rank(args.category, args.days, args.limit, rf)
            elif args.cmd == "bilibili":
                out = search_bilibili(args.keyword, args.limit, args.order, rf)
            elif args.cmd == "shipinhao":
                out = search_shipinhao(args.keyword, args.limit, args.sort, rf)
            elif args.cmd == "trending":
                out = search_trending(days=args.days, limit_per=args.limit_per, rf=rf)
            else:  # pragma: no cover
                out = {"status": "error", "message": f"未知命令 {args.cmd}"}
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(_emit({"status": "error", "cmd": args.cmd, "message": str(exc)}))
        return 1
    out["api_calls"] = rf.calls
    warn = buf.getvalue().strip()
    if warn:
        # 诊断行可能很长（接口一次回一大段），只留前若干行
        out["warnings"] = [ln.strip() for ln in warn.splitlines() if ln.strip()][:5]
    out = _finalize(out)
    print(_emit(out))
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
