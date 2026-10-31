#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/ops_distill_blank_check_probe.py —— 「一组 0 张卡」是模型抖动还是判据缺口？

背景：2026-10-01 加工线对「公众号/获客与成交」7 篇新料跑出 **规则卡 0 张**，
而 `ops_distill.SYSTEM` 里明确写着「不要交白卷：多篇各讲不同对象时，归并成一张清单/分类卡」。
本探针用**同一份 prompt** 连跑两次，看 0 卡是否稳定复现。只读、不落盘、不改水位。

用法：python scripts/_probe/ops_distill_blank_check_probe.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\.hermes\scripts")
import ops_distill as od  # noqa: E402

PREP = Path(r"C:\Users\Administrator\.hermes\scripts\ops-distill-prepare.py")
PLAT, TOPIC = "公众号", "获客与成交"
# 加工日志里那一轮「输入 7 篇」的清单（_原文 下的文件名）
NAMES = [
    "2026-10-01_4个人的教培运营团队，每月干30万业绩，我们是这么分工的_2FC625E2C27871B9AF79CC7A70BE3EC2.md",
    "2026-10-01_从199元上门做获客服务，到年营收1亿+，她如何把代运营做成大生意？_ACD2C09202EF3DD60AA37DC9FA7CEAA7.md",
    "2026-10-01_她做中老年兴趣课私域，续费率从不足30%做到60%+_2ABEAE5D0D3D0372938E56D7B64F37E9.md",
    "2026-10-01_微信小店金秋大促：“小店与卡包”成交增5倍，入口价值凸显_B42B341122AB3B2332F005AAF17A2EBB.md",
    "2026-10-01_抢抓AI新机遇，2026阿里妈妈美妆个护家清行业私享会解锁双11全域增长新路径_AF58F552B23AAFE38C623B88288A9D12.md",
    "2026-10-01_用AI全自动排版公众号，30分钟的活一句话搞定｜运营AI小实训_C25B99364AFD4D0B7D28B0E8F9D2C7DE.md",
    "2026-10-01_行业100策丨最高50%流量反哺！阿里妈妈健康行业AI领航计划，解锁双11增量新机会_F9196DF82B55D44D829CF364EABE20C2.md",
]


def load_items():
    ops = od.load_prepare()
    d = od.OPS / PLAT / "_原文"
    items = []
    for n in NAMES:
        f = d / n
        if not f.is_file():
            print("  ⚠ 文件不在：%s" % n[:40])
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        fm = (re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", t, re.DOTALL) or [None, ""])[1]
        body = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", t, flags=re.DOTALL).strip()
        a = re.search(r"^作者\s*:\s*(.*?)\s*$", fm, re.M) or re.search(r"^author\s*:\s*(.*?)\s*$", fm, re.M)
        items.append({"name": f.name, "sub": "_原文", "author": (a.group(1).strip().strip("\"'") if a else "未知"),
                      "body": re.sub(r"\n{3,}", "\n\n", body)[:12000]})
    return items


def main():
    items = load_items()
    print("组：%s / %s ｜ 喂入 %d 篇" % (PLAT, TOPIC, len(items)))
    user, used = od.build_user(PLAT, TOPIC, items, od.existing_titles(PLAT))
    print("prompt 字符数：%d ｜ 已有卡 %d 张\n" % (len(user), len(od.existing_titles(PLAT))))
    msgs = [{"role": "system", "content": od.SYSTEM}, {"role": "user", "content": user}]
    for i in (1, 2):
        cards, raw, ok, info = od.ask_cards(list(msgs), od.MODEL_DEFAULT)
        print("第 %d 次：ok=%s ｜ 解析出 %d 张卡 ｜ info=%s" % (i, ok, len(cards or []), str(info)[:80]))
        for c in (cards or []):
            print("    - [%s] %s" % (c.get("叶子"), c.get("标题")))
        if not cards:
            print("    模型原文（前 300）：%r" % (raw or "")[:300])
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
