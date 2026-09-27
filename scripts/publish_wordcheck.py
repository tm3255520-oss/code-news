#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_wordcheck.py — 发布前统一违禁词门禁（官方词库，多平台）

为什么需要它（2026-09-27 实测）：
  我们已有 4 个平台专属合规检查器（头条/知乎/小红书/公众号），但它们的词库都是
  **各自本地手工维护**的，且小红书那个用 `\\b{词}\\b` 做匹配——中文里 `\\b` 边界
  不成立，实测「最顶级/包治百病/百分百」三个典型违禁词**全部漏检**
  （同一段文案里它报「未检测到违禁词」）。本脚本改用官方词库接口，
  公众号/小红书/抖音三平台一套标准。

定位：**补充门禁**，不替换既有 checker。既有 checker 还查 AI 声明、原创度、
      标题规范、封面比例等，那些本脚本不管。

退出码（沿用既有 rule_checker 约定，便于插进流水线）：
    0 = 通过（无违禁词）
    2 = 阻断（存在违禁词）
    1 = 无法判定（缺 key / 网络异常 / 内容为空）——**不静默放过**

用法：
    python publish_wordcheck.py --selftest
    python publish_wordcheck.py --content "文案..." --platform 小红书
    python publish_wordcheck.py --file 终稿.md --platform 公众号 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERMES_SCRIPTS = Path(r"C:\Users\Administrator\.hermes\scripts")
if HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(HERMES_SCRIPTS))

# 官方违禁词接口（经 redfox_client 调用，path 不含域名）
WORDCHECK_PATH = "/story/api/cozeSkill/sensitiveWordSearch"

# 平台口径：接口只认这三个中文名，其余别名先归一
PLATFORM_ALIASES = {
    "公众号": "公众号", "gzh": "公众号", "wechat": "公众号", "微信": "公众号",
    "小红书": "小红书", "xhs": "小红书", "rednote": "小红书",
    "抖音": "抖音", "douyin": "抖音", "dy": "抖音",
}

EXIT_PASS, EXIT_UNDETERMINED, EXIT_BLOCK = 0, 1, 2


def normalize_platform(value: str) -> str | None:
    """把平台别名归一成接口认的写法；不认识返回 None。"""
    return PLATFORM_ALIASES.get((value or "").strip().lower()) or \
        PLATFORM_ALIASES.get((value or "").strip())


def strip_frontmatter(text: str) -> str:
    """去掉 YAML frontmatter。终稿一般带头信息，查违禁词只该看正文。"""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


# 接口把命中词标在 HTML 里（<span class="banned-word">词</span>），
# 没有单独的「命中词数组」字段，只能从标记里抽。两种类名都要认。
_HIT_PAT = re.compile(r'<span class="(?:banned-word|sensitive-word)">(.*?)</span>')


def extract_hits(marked_html: str) -> list[str]:
    """从带标记的 HTML 里抽出命中词（去重保序）。"""
    return list(dict.fromkeys(_HIT_PAT.findall(marked_html or "")))


def check(content: str, platform: str) -> dict:
    """调官方词库接口。返回统一结构，不抛异常。

    复用 .hermes/scripts/redfox_client：它已经把 {code:2000,data:...} 信封拆好，
    鉴权/重试/超时也都现成，不另写一套 HTTP。
    """
    if not content.strip():
        return {"ok": False, "reason": "待检测内容为空"}
    try:
        from redfox_client import RedFox
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "无法导入 redfox_client（检查 .hermes/scripts）"}
    try:
        data = RedFox(sleep=0).call(
            WORDCHECK_PATH,
            {"content": content, "platform": platform,
             "source": "code-news-publish-gate"},
            quiet=True,
        )
    except SystemExit:
        return {"ok": False, "reason": "未找到 REDFOX_API_KEY（环境变量或 .env）"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"请求异常: {str(exc)[:120]}"}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "接口未返回 data（key 无效或配额不足）"}
    marked = data.get("content") or ""
    hits = extract_hits(marked)
    return {
        "ok": True,
        "platform": platform,
        "hits": hits,
        "types": data.get("prohibitedWordsType") or [],
        "count": len(hits),
    }


def _emit(result: dict, as_json: bool) -> int:
    """输出并返回退出码。"""
    if not result.get("ok"):
        payload = {"status": "undetermined", "reason": result.get("reason")}
        if as_json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"⚠️ 违禁词门禁无法判定：{result.get('reason')}")
        return EXIT_UNDETERMINED
    hits = result["hits"]
    payload = {
        "status": "block" if hits else "pass",
        "platform": result["platform"],
        "count": result["count"],
        "sensitive_words": hits,
        "prohibited_words_type": result["types"],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if hits:
            print(f"🛑 [{result['platform']}] 命中 {result['count']} 个违禁词：")
            for w in hits:
                print(f"   - {w}")
            if result["types"]:
                print(f"   类型：{'、'.join(result['types'])}")
        else:
            print(f"✅ [{result['platform']}] 未命中违禁词")
    return EXIT_BLOCK if hits else EXIT_PASS


def selftest() -> int:
    # 别名归一
    assert normalize_platform("xhs") == "小红书"
    assert normalize_platform("小红书") == "小红书"
    assert normalize_platform("gzh") == "公众号"
    assert normalize_platform("douyin") == "抖音"
    assert normalize_platform("weibo") is None
    assert normalize_platform("") is None
    # frontmatter 剥离：头部不该参与违禁词判定
    md = '---\ntitle: "x"\ntags: [a]\n---\n\n正文内容'
    assert strip_frontmatter(md).strip() == "正文内容"
    assert strip_frontmatter("没有头信息").strip() == "没有头信息"
    # 只有一对 --- 时不误剥
    assert "---" in strip_frontmatter("---\n只有开头")
    # 空内容不放行
    assert check("", "小红书")["ok"] is False
    # 退出码口径
    assert (EXIT_PASS, EXIT_UNDETERMINED, EXIT_BLOCK) == (0, 1, 2)
    print("SELFTEST PASS: 平台归一 / frontmatter 剥离 / 空内容拦截 / 退出码口径")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="发布前违禁词门禁（官方词库）")
    ap.add_argument("--file", "-f", default="", help="待检测文件（Markdown，自动剥 frontmatter）")
    ap.add_argument("--content", "-c", default="", help="直接给文案")
    ap.add_argument("--platform", "-p", default="公众号",
                    help="公众号/小红书/抖音（也接受 gzh/xhs/douyin）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给流水线用）")
    ap.add_argument("--selftest", action="store_true", help="离线自检，不联网")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    platform = normalize_platform(args.platform)
    if not platform:
        print(json.dumps({"status": "undetermined",
                          "reason": f"不支持的平台: {args.platform}"}, ensure_ascii=False))
        return EXIT_UNDETERMINED

    if args.file:
        fp = Path(args.file)
        if not fp.is_file():
            print(json.dumps({"status": "undetermined",
                              "reason": f"文件不存在: {fp}"}, ensure_ascii=False))
            return EXIT_UNDETERMINED
        content = strip_frontmatter(fp.read_text(encoding="utf-8", errors="replace"))
    elif args.content:
        content = args.content
    else:
        print(json.dumps({"status": "undetermined",
                          "reason": "需要 --file 或 --content"}, ensure_ascii=False))
        return EXIT_UNDETERMINED

    return _emit(check(content, platform), args.json)


if __name__ == "__main__":
    sys.exit(main())
