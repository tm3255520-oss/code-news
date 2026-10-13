---
name: content-pipeline-audit
description: 审计 Hermes 内容自动化生产线（头条/公众号/知乎/小红书/视频号/贴图任一条）。当用户说「把 XX 生产线搞清楚」「审计 XX 流水线」「看看这条产线有什么问题」「产线体检」时使用。产出分级问题清单 + 改善建议的审计报告。**边界**：只读审计、不动手修 —— 要修产线走 hermes-pipeline-repair（且动手前先过 repair-gate）；体检 WorkBuddy 本机能力走 workbuddy-capability-audit；巡检 Obsidian 中枢链路走 obsidian-vault-health-check。
agent_created: true
version: 1.0.1
tags: [audit, hermes, cron, content-pipeline]
---

# 内容自动化生产线审计

## 触发条件
- 「把 XX 生产线搞清楚」「审计 XX 流水线」「这条产线有什么问题」「产线体检」
- 需要判断某条自动化内容产线是否真的在健康产出

## 核心判据
**不看 cron 状态，看产物是否落地。** `last_status: ok` / `exit 0` 完全不可信——实测头条线发布失败仍返回 success=True。
每一层都要问：「这一步说成功，有没有平台侧/产物侧的独立证据？」

## 审计六步法

### 1. 定位任务
```bash
ls ~/.hermes/cron/jobs.json        # 46 个任务全在这里
```
用 python 解析，按 name 筛目标任务，取 `id / script / schedule_display / enabled / last_status / last_run_at / no_agent`。
- `no_agent: true` + `script: xxx.py` → 逻辑全在脚本里，prompt 是空的，必须读脚本
- 记录 `repeat.completed`（已跑次数）与 `created_at`

### 2. 读主脚本
重点看四处：
- **成败判定**：`return XxxResult(success=...)` 是否真的汇总了各步骤结果（常见坑：发布结果被丢弃，无条件 return True）
- **兜底/降级路径**：主路径失效时走哪条分支？产出质量如何？（头条线就是在兜底路径上持续产垃圾）
- **异常处理**：`except Exception: pass` 静默吞异常的位置
- **硬编码路径**：不属于 vault_paths 体系的绝对路径（如 `D:/OpenClaw/...`），多为已失效的外部目录

### 3. 查执行证据（三层，缺一不可）
```bash
# 调度层
sqlite3 ~/.hermes/cron/executions.db "select status,error from executions where job_id='<ID>'"
# 日志层（逐日输出，最有价值）
ls ~/.hermes/cron/output/<ID>/
# 降级层
ls ~/.hermes/state/fallback_flags/    # 回退标记 = 上游断供次数
```
**逐日输出要抽 `"success"` 字段，而非看 exit code。** 一条命令批量提取：
```bash
grep -o '"success": *[a-z]*' 2026-09-*.md
```

### 4. 查产物质量
直接看输出目录的文件体积与标题：
- 体积断崖（如 6KB → 1KB）= 内容退化
- 标题出现 `...`、以 `,`/`：` 结尾、含半截英文 = 截断残句
- `md5sum *.md | sort` 查重复发布；同题不同 hash 也要警惕（AI 改写会掩盖重复）

### 5. 查闭环
- 台账：`D:\Obsidian Vault\obsidian Vault\内容生产\发布\发布台账.md` — 看有多少条"已发布" vs "待发布"
- 目录语义：草稿是否误存进"已发布"目录
- 死代码：`for f in *.py; do grep -l "$f" *.py; done` 找零引用脚本

### 6. 交叉验证上游
产线质量往往取决于上游（头条线 80% 取决于公众号线）。务必查上游 cron 的成败。
看门狗任务 `f4404627133c` 的每日输出是很好的全局健康快照。

## 报告结构
1. 执行摘要（设计预期 vs 实测现状对照表 + 一句话结论）
2. 生产线全景（链路图 + 组件清单表 + 死代码统计）
3. 运行现状（上游断供次数 / 产物质量抽样表 / 典型失败日实况）
4. 问题清单（P0 阻断 / P1 高 / P2 中，每条附代码位置 + 后果）
5. 改善建议（分「止血 / 闭环 / 清理」三批，按投入产出比排序）
6. 附：取证来源表

## 常见坑（本次审计实证）
- **假成功**：`run()` 不检查 step 结果就 return True → 静默丢稿
- **软约束**：合规检查只拦 Critical/High，字数不足、AI 味超标都只 WARN 放行
- **无去重**：兜底路径恒选 `max(mtime)` 的同一份素材 → 同题反复生产
- **旧资源兜底**：封面/图片兜底目录长期不更新 → 配 25 天前的无关图
- **文档脱节**：SKILL.md 描述的发布器早已替换成别的（老发布器成死代码）
- **编码损坏**：SKILL.md 出现 `��` 乱码（UTF-8 被二次错误编解码）

## 输出
报告写到工作区 `XX生产线-审计报告-YYYY-MM-DD.md`，用 present_files 呈现。
审计只做只读取证，不修改任何产线代码；修复方案作为建议列出，等用户确认后再动手。
