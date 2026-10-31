#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""_probe/ops_distill_format_guard_test.py —— 验证「格式失败不再被当成无卡」。

确定性测试：把 `call_nvidia_with_rotation` 换成假实现，喂三种输出，看 `ask_cards` 的判定。
不调 LLM、不写 vault。

用法：python scripts/_probe/ops_distill_format_guard_test.py
"""
import sys

sys.path.insert(0, r"C:\Users\Administrator\.hermes\scripts")
import ops_distill as od  # noqa: E402

REASONING = ("The user wants me to create 规则卡 from the provided source materials. "
             "The constraints are strict: 1. Cross-document synthesis ...")
NO_CARDS = "无卡片"
ONE_CARD = """=== 卡片 1 ===
叶子: 打法与爆款
标题: 教培本地获客：产品拆分加分层投放
验证状态: 信号
触发:
- 任务型：给本地教培做获客方案时
动作:
- 1. 把课程拆成引流品与利润品
边界:
- 只适合有线下交付能力的团队
自检:
- [ ] 是否区分了引流品与利润品
来源:
- _原文/某文件.md"""


def run(name, returns):
    seq = list(returns)

    def fake(messages, **kw):
        r = seq.pop(0) if seq else returns[-1]
        return r, True, ""

    od.call_nvidia_with_rotation = fake
    cards, raw, ok, info = od.ask_cards([{"role": "user", "content": "x"}], "fake-model")
    print("%-28s → ok=%-5s 卡片=%d ｜ info=%s" % (name, ok, len(cards or []), str(info)[:60]))
    return ok, len(cards or [])


def main():
    print("=== 判据自检（假模型输出，不调 LLM）===")
    bad = 0
    # ① 只输出英文思考（没版式）→ 连试两次都这样：必须判为**失败**，不能是"无卡"
    ok, n = run("纯思考·无可卡片式", [REASONING, REASONING])
    if ok or n:
        print("   ❌ 期望 ok=False（格式失败），实际 ok=%s cards=%d" % (ok, n)); bad += 1
    # ② 明确说无卡片 → 正常，ok=True、0 张
    ok, n = run("明确「无卡片」", [NO_CARDS, NO_CARDS])
    if not ok or n:
        print("   ❌ 期望 ok=True cards=0，实际 ok=%s cards=%d" % (ok, n)); bad += 1
    # ③ 首次无版式、重试给了卡片 → ok=True、1 张
    ok, n = run("首次失败·重试给卡", [REASONING, ONE_CARD])
    if not ok or n != 1:
        print("   ❌ 期望 ok=True cards=1，实际 ok=%s cards=%d" % (ok, n)); bad += 1
    # ④ 直接给卡片 → ok=True、1 张
    ok, n = run("直接给卡片", [ONE_CARD])
    if not ok or n != 1:
        print("   ❌ 期望 ok=True cards=1，实际 ok=%s cards=%d" % (ok, n)); bad += 1
    print("\n%s" % ("✅ 四例全部符合预期" if not bad else "❌ %d 例不符合预期" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
