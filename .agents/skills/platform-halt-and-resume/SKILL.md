---
name: platform-halt-and-resume
description: 把一个平台（小红书/抖音/视频号/快手/B站/头条…）在产线上**整体停线或恢复**的标准动作与踩坑集 —— 停采/停生成/停发布三层一起收口，且恢复不按日期自动。当用户说「XX 平台不做了/停一段时间」「这条线停下来」「账号被处罚了先别发」「XX 恢复后怎么接回来」「停线期内不要再生成他的作品」时使用。**边界**：新接一条采集线归 `platform-line-onboarding`；发布前置体检查什么归 `publish-line-preflight-entry`；发布字段完整性归 `publish-content-completeness-gate`。
agent_created: true
version: 1.0.0
tags: [停线, 恢复, 风控, 平台开关, 单一事实源, 协同, 踩坑集]
---

# 平台级停线与恢复（platform-halt-and-resume）

> 为什么有这份：2026-10-13 小红书账号「Yq」因 **AI 工具代发 + 高频发布 + 抓取数据** 触发平台风控（一个月处罚期）。
> 停这条线时暴露了三类问题：① 生成层**没有开关**（只靠人工记得传参）② **两个 Agent 会话在并行推同一件事** ③ 备份目录**撞号** + 协同登记被守卫拦。
> 这份把动作和坑一次固化。**原则：停线是一条横切的产线状态，不是改某一个脚本。**

## 〇、核心模型：一处登记，三层收口

**单一事实源** = `D:/AI-VIDEO/config/平台适配矩阵.json` → 顶层 `_停线登记.<平台>`：

```json
"_停线登记": {
  "<平台>": {
    "状态": "停线中",            // 判据键：停线中 / 停线 / 停用 → 视为停线
    "起始": "2026-10-13",
    "计划解除": "2026-11-08",
    "原因": "…（写清平台原话/后台文案）",
    "范围": ["采集（…）", "内容生成（…）", "发布（全部通道：…）"],
    "判据": "到期前不采集/不生成/不发布；到期后先人工登录确认异常消失，再解除本登记",
    "执行落点": ["…（每停一处就补一条，路径要能复核）"]
  }
}
```

**说明书**（人读）：`D:/AI-VIDEO/config/<平台>停线与恢复登记-<日期>.md` —— 为什么停 / 停什么 / 落了哪些开关 / 怎么恢复 / 残留缺口。

**三层开关落点**（改前先读 `_停线登记`，别把状态写死在代码里）：

| 层 | 落点 | 收口方式 |
|---|---|---|
| 采集 | `code-news/scripts/collect_material_batch.py` 的 `MATERIAL_ENTRIES` / `FAVORITES_ENTRIES` | 注释掉该平台条目 + 同步文档串/help 里的条数（如 6→5、3→2） |
| 生成 | `code-news/scripts/adapt_for_platforms.py` | **已有 `halted_platforms()` 读 `_停线登记`**：默认目标自动排除；显式 `--platforms` 点名停线平台 → 硬拦 `rc=2`（拦在 `mkdir` 之前，零产出） |
| 发布 | `publish_rate_limit.py` 的 `precheck(平台, mode)` + `~/.hermes/state/publish_rate_limit.json` 的 `official_only.<平台>=true` | 闸门在被调用的发布脚本内部（`publish_via_{yxer,yxer_image,xmcp}.py`）；**矩媒腿无频控 precheck**，靠摘 `MATRIXMEDIA_PLATFORMS` 条目 |

> ⚠️ `publish_rate_limit.py` 里的 `OFFICIAL_ONLY` 是**代码常量**，状态文件里没这个键时拦截是**隐式**的（只看状态文件会误判"没拦"）。停线时**显式写进状态文件**，让拦截可见可审可解除。

## 一、动手前（不许跳）

```bash
# 1) 开工三查 —— 本机常有多会话并行，跳了就会两个会话改同一文件
python C:\Users\Administrator\Documents\code-news\scripts\work_lookup.py "<平台关键词>"
#    命中「进行中」且非自己 → 不重复开工，读交接最后一块
#    命中「已完成」→ 复用产出（停线可能已被别人做过，先看 §六·①）

# 2) 复用盘点（新建脚本/新能力前必须）
python C:\Users\Administrator\Documents\code-news\scripts\tool_inventory.py "停线"

# 3) 备份号避让 —— 台账号与备份目录号是【两个独立体系】
ls -d "D:/Obsidian Vault/备份/WK-$(date +%Y%m%d)-"*
#    备份号当日可能已被别的改动占满，撞号会被并行会话点名
mkdir -p "D:/Obsidian Vault/备份/WK-<日期>-<下一个未用号>-<简述>-<日期>"
```

## 二、停线标准动作（六步）

1. **写 `_停线登记`**（矩阵 JSON，顶层首键；纯 CRLF，`platforms` 六键不动）。
2. **摘采集条目**：注释 `MATERIAL_ENTRIES` / `FAVORITES_ENTRIES` 里该平台两条 + 同步文案条数。
3. **生成层**：确认 `adapt_for_platforms.py` 的 `halted_platforms()` 能读到（跑 `--list`，应标 `⛔ 停线中`）。
4. **发布层**：写 `official_only.<平台>=true` 进状态文件；跑 `precheck` 实测 `allow=False`。
5. **清 cron**：该平台专属 job 置 `enabled=False`（`hermes cron pause <id>`）；**批量 job 只看批清单里的条目**（批 job 本身仍启用是正确的，别停整个批）。
6. **登记三处**：① 说明书 md ② 协同三件套（台账行 + 交接块 + 会话索引）③ 引用本文档的说明书回链。

## 三、验证（四向实测，缺一不算闭合）

```bash
# 模块级：读登记是否命中
python -c "import sys;sys.path.insert(0,r'C:/Users/Administrator/Documents/code-news/scripts');import adapt_for_platforms as A;m=A.load_matrix();print(A.halted_platforms(m))"
#   期望 ['<平台>']

# 向①：默认目标自动排除（6→5）
# 向②：显式点名停线平台 → 硬拦 rc=2，且【不产生输出目录】
# 向③：对照非停线平台 → rc=0 正常
# 向④：py_compile rc=0 + 行尾按原基准（adapt_for_platforms.py 是纯 LF）
```

> 跑 `--dry-run` 记得加 `--no-rewrite-copy`：否则会调 LLM 改写文案，慢到被进程组管理杀掉（表现为空输出 + SIGTERM）。

## 四、恢复（⚠️ 不按日期自动）

**处罚期满 ≠ 账号恢复。** 必须：

1. 人工登录平台后台，确认处罚/异常提示**已消失**（截图留证）。
2. 改 `_停线登记.<平台>.状态 = 已恢复` + 补「实际恢复日」。
3. 撤三层开关：取消采集条目注释（条数改回）、`official_only` 置 `false`、`recovery_mode` 重新裁定。
4. **重新裁定发布节奏**（别直接沿用停线前参数）：处罚刚过仍在观察期，建议先更保守（如首周 ≤1 条/天）+ 保留人工复核，由用户点头再定。
5. 说明书顶部状态改「已恢复」+ 回填恢复证据。

> 生成层**不需要回改代码**——它读登记，改登记即自动恢复。这正是选"读登记"而非"硬编码删平台"的理由。

## 五、踩坑集（都是实测踩过的）

1. **本机常有多会话并行推同一件事**：我第一次改完 `adapt_for_platforms.py`，另一会话已独立复验并同步文档，还指出我的备份撞号。→ **动手前必跑开工三查**；产出后**查一眼台账是否有同主题行**。
2. **台账号 ≠ 备份目录号**：台账只到 `WK-…-04`，但备份目录 `WK-…-01~08` 当天已被占满。按备份号建目录会撞。→ 建目录前先 `ls`。
3. **`handoff_append.py` 有交付物占用守卫**：目标文件被别的活跃任务（哪怕"待审"）持有时会被拒。→ 确属新增改动、不冲突时用 `--force --force-reason "<原因>"`，原因会写进台账变更记录。
4. **MSYS 管道阻塞**：原生 exe 的 stdout 直连 Git Bash 管道会永久挂起（空输出 + SIGTERM）。→ 输出重定向到文件（`> /tmp/x.log 2>&1`）。
5. **删除闸**：`rm -rf` 在本机可能触发安全闸（`SAFE_DELETE_FAIL_CLOSED`），**连带的后续命令一起被杀**。→ 测试用新目录名，别先删。
6. **矩媒腿没有频控 precheck**：`publish_via_matrixmedia.py` 只有幂等 precheck。停线靠摘 `MATRIXMEDIA_PLATFORMS` 条目，别指望它自己拦。
7. **`--force-rate-limit` 逃生门仍在**：属既有人工背书设计，停线期内**不得使用**，要在交接里点名。

## 六、查"还有没有活着的路径"（停线后必做）

```bash
# ① 专属 cron 是否真停
python -c "import json,io;d=json.load(io.open(r'C:/Users/Administrator/.hermes/cron/jobs.json',encoding='utf-8'));[print(j['id'],j['name'],j['enabled']) for j in d['jobs'] if '<平台>' in json.dumps(j,ensure_ascii=False)]"
# ② 活跃批任务脚本里的引用
grep -c -i "<平台>|xhs" ~/.hermes/scripts/{pipelines_batch,collect_material_batch,collect_favorites_batch,daily_video_production}.py
#   注意：只用 grep【实际调用】——文档串里的平台名不算（如 pipelines_batch.py 第 10 行注释）
# ③ 该平台的编排脚本挂在哪个 cron 上？不在任何 cron 上的（如 daily_video_production.py）不构成自动路径
```

> 三层都收口后仍会残留"手动可调用"的脚本本体（`xhs_pipeline.py` 等）——**有意保留**（可回滚），但要在交接里写明"停线期内不要手工单独跑"。
