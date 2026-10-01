#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/gzh_gate_tighten_probe.py —— 量化「入口收紧」前后的信噪比。

对比同一批号、同一时间窗下，作品级闸门的两种口径：
  放宽：命中**强词或弱词**就算相关（旧默认，--allow-weak）
  收紧：**只认强词**（新默认）
只读、不落盘。会花 RedFox 积分（每号 1 次 queryWorkList）。

用法：python scripts/_probe/gzh_gate_tighten_probe.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Administrator\.hermes\scripts")
import gzh_creator_collect as g  # noqa: E402
import raw_creator_filter as rcf  # noqa: E402
from redfox_client import RedFox  # noqa: E402

RANK = Path(r"D:\Obsidian Vault\obsidian Vault\运营中心\.state\号分级-wechat.json")


def main():
    d = json.loads(RANK.read_text(encoding="utf-8"))
    nicks = [n for n, v in d["账号"].items()
             if str(v.get("级") or "").strip()[:1].upper() in ("A", "B")]
    rcf.CUR["strong"], rcf.CUR["weak"], rcf.CUR["no"] = rcf.PROFILES["ops"]
    rf = RedFox()
    tot_w = tot_s = 0
    print("%-22s %6s %8s %8s" % ("号", "30天篇", "放宽", "收紧"))
    print("-" * 50)
    for nick in sorted(nicks):
        ws = g.fetch_works(rf, nick, 30)
        wide = strict = 0
        for w in ws:
            txt = w["title"] + " " + (w["summary"] or "")
            if rcf._hit(txt, rcf.CUR["strong"]) or rcf._hit(txt, rcf.CUR["weak"]):
                wide += 1
            if rcf._hit(txt, rcf.CUR["strong"]):
                strict += 1
        tot_w += wide
        tot_s += strict
        print("%-22s %6d %8d %8d" % (nick[:22], len(ws), wide, strict))
    print("-" * 50)
    print("合计：放宽 %d 篇 → 收紧 %d 篇（砍掉 %d 篇，%.0f%%）"
          % (tot_w, tot_s, tot_w - tot_s,
             (100.0 * (tot_w - tot_s) / tot_w) if tot_w else 0))
    print("API 调用 %d 次（约 %.2f 积分）" % (rf.calls, rf.calls * 0.04))
    return 0


if __name__ == "__main__":
    sys.exit(main())
