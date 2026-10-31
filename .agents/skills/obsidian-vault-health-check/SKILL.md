---
name: obsidian-vault-health-check
description: 对 Obsidian 自媒体中枢（vault + Hermes cron + MCP）做只读健康巡检。当用户说「体检一次系统」「巡检 Obsidian」「检查中枢运行状态」「看看哪条链路断了」时使用。判据是「每条链路最近有没有新产出」，不是「目录里有没有文件」。**边界**：对象是 **Obsidian 中枢链路**（vault 产出 + Hermes cron + MCP）；**WorkBuddy 本机能力**（skill / 插件 / MCP / 连接器是否真的可用）走 workbuddy-capability-audit；**某条内容产线的问题**走 content-pipeline-audit。
agent_created: true
version: 1.1.0
tags: [obsidian, 巡检, 健康检查, 只读, 多智能体]
---

# Obsidian 中枢健康巡检

> 对象：`D:\Obsidian Vault\obsidian Vault` + Hermes（`C:\Users\Administrator\.hermes`）+ code-news。
> 铁律：**全程只读**。不改 vault、不改脚本、不重跑生产任务。发现故障只定位根因并报告，等用户决策后再动。
>
> **📌 路径基准（2026-10-14 全量重订）**：vault 已改为**序号前缀目录**（`内容生产/1-情报与选题`…`6-归档`、
> `知识库/0-收件箱`…`9-归档`）。本技能所有路径以 **`~/.hermes/scripts/vault_paths.py` 为唯一事实源**
> （各产线脚本都 import 它）。**改本技能路径前先读那个文件**，别凭记忆。
> 旧路径 → 新路径速查：`内容生产/情报与选题`→`1-情报与选题`｜`创作与调研/深度调研`→`2-调研与素材/深度调研`｜
> `创作与调研/素材与资源`→`2-调研与素材/素材与资源`｜`创作与调研/文章`→`3-草稿与创作/文章`｜
> `成品`/`成品与素材`→`4-成品与审查`｜`发布`→`5-发布`｜`归档`→`6-归档`｜`DSH专线`→`9-DSH专线`｜
> `知识库/摘要`→`1-素材摘要`｜`知识库/{2-概念,3-实体,4-主题}`→**层已移除**（`5-方法`/`6-案例`/`7-判断` 代之）｜
> `参考库/平台内容规则`→**顶层模块 `运营中心/<平台>/`**（`_规则原文` + `规则与合规` 双层）。

## 核心判据

看**每条链路最近产出时间**，不看文件数。一个 40 天没更新的目录，即使文件很多，链路也已经死了。

分级：🟢 ≤3 天 · 🟡 3~14 天 · 🔴 >14 天或核心产线失败。

## 执行步骤

### 0. 前置（最容易漏、也最致命）
```bash
timeout 25 bsk status          # 期望 browsers connected 1；超时/无响应 = Chrome Profile 2 未附着
```
Profile 2（显示名 M / tm3255520@gmail.com）不开 → 采集脚本静默 exit(0)、发布无落点。**采集/发布异常先查它。**

### 1. 全库体检 + 各链路最近产出
用 Git Bash（PowerShell 工具在本机可能不回显输出）：
```bash
cd "D:/Obsidian Vault/obsidian Vault"
echo "TOTAL=$(find . -name '*.md' -type f | wc -l) EMPTY=$(find . -name '*.md' -type f -empty | wc -l)"
for d in "内容生产/1-情报与选题/AI日报" "内容生产/2-调研与素材/深度调研" \
  "内容生产/5-发布/已发布/公众号" "内容生产/5-发布/已发布/头条" "内容生产/5-发布/已发布/知乎" \
  "内容生产/5-发布/已发布/视频号" "内容生产/4-成品与审查" \
  "内容生产/1-情报与选题/热点与情报" "内容生产/1-情报与选题/选题与题材" \
  "知识库/1-素材摘要" "知识库/5-方法" "知识库/6-案例" "知识库/7-判断" \
  "系统中枢/经验沉淀/工作流" "系统中枢/经验沉淀/复盘" "系统中枢/经验沉淀/决策" \
  "raw/articles/toutiao" "raw/articles/wechat" "raw/articles/xiaohongshu" \
  "raw/articles/zhihu" "raw/videos"; do
  f=$(find "$d" -name '*.md' -printf '%T@ %TY-%Tm-%Td %TH:%TM|%p\n' 2>/dev/null | sort -rn | head -1)
  echo "[$d] $(echo "$f" | cut -d'|' -f1 | cut -d' ' -f2-) $(basename "$(echo "$f" | cut -d'|' -f2)")"
done
```

### 2. cron 全景（关键，别跳过）

**⚠️ 2026-09-10 定案（根因已查明，别再当玄学）：`hermes cron list` 返回 "No scheduled jobs" 不是 bug，
是 `HERMES_HOME` 没被继承。**

- Windows 上 `hermes_constants._get_platform_default_hermes_home()` 返回 **`%LOCALAPPDATA%\hermes`**
  （= `C:\Users\Administrator\AppData\Local\hermes`），**不是** `~/.hermes`。
- 本机真实 home 是 `C:\Users\Administrator\.hermes`，证据：`.hermes\gateway.pid` 里
  `"hermes_home": "C:\\Users\\Administrator\\.hermes"`，且 `\.hermes\cron\jobs.json` 才是 ticker 认的文件。
- 用户级环境变量 `HERMES_HOME` **已经设对**（= `C:\Users\Administrator\.hermes`），但**父进程没带这个变量时
  （AI 助手 shell / 任务计划 / 被清洗过的环境）就会掉进影子目录** `AppData\Local\hermes\cron\`，
  那里没有 jobs.json → 打印 "No scheduled jobs"。
- **危险的不只是显示错**：在这种环境里 `hermes cron create` 会把任务写进影子目录，**永不触发、静默失败**。

**正确做法（二选一）**：
```bash
# Bash：
export HERMES_HOME='C:\Users\Administrator\.hermes'   # 或用工作区里的 ./hcron.sh
/c/Users/Administrator/.hermes/bin/hermes.exe cron list
# CMD：
C:\Users\Administrator\.hermes\bin\hcron.cmd cron list
```
两个 wrapper 已建好（`hcron.cmd` / 工作区 `hcron.sh`），内部固定 HERMES_HOME，
在不带该变量的环境里实测能正确列出任务。有事直接用 wrapper。

**哨兵检查**（每轮巡检做一次）：
```bash
ls "C:/Users/Administrator/AppData/Local/hermes/cron/"   # 只应有 output/ 和哨兵 txt
```
若出现 **`jobs.json` → 立即报警**：有人在无 HERMES_HOME 的环境建了任务，那些任务永远不会跑。

**但仍然建议直接读文件做主判据**（CLI 只是辅助），因为 jobs.json 是唯一真相源：
```bash
ls -la "C:/Users/Administrator/.hermes/cron/"     # jobs.json / executions.db / ticker_heartbeat
```
- `jobs.json` → `{"jobs":[...], "updated_at":...}`，任务全量定义
  关键字段：`id, name, enabled, state(scheduled|paused), schedule{kind,expr|minutes,display},
  last_run_at, next_run_at, last_status, failure_streak, last_error, last_delivery_error, script, workdir`
- `executions.db`（SQLite，只读打开）→ 表 `executions`(job_id,status,started_at,finished_at,error)
  和 **`cron_incidents`**(job_id,state,failure_type,first_seen_at,last_seen_at,error) —— 后者是故障聚合，必看
- 只读连接：`sqlite3.connect("file:C:/Users/Administrator/.hermes/cron/executions.db?mode=ro", uri=True)`

解析脚本模板见本文末。重点：按 `failure_streak` 排序追连续失败，并读每个失败任务 error 里的真实 traceback。

**判定红绿时注意**：
- `state` 正常值是 `scheduled`（不是 `active`）；`paused` 的任务 next_run_at 会停在过去，恢复前不再唤起。
- 周/月任务天龄 7~30 天属正常周期，**别按"天龄>3天"误判**。
- `interval` 类看 `schedule.minutes`（单位分钟）；`cron` 类看 `expr`。
- `last_status` 可能是 `ok/completed/error/failed/delivery_failed`。

### 3. MCP 与基础设施
```bash
# 今日错误日志
python -c "p=r'C:\Users\Administrator\.hermes\logs\errors.log';\
[print(l[:200]) for l in open(p,encoding='utf-8',errors='replace').read().splitlines() if '<今天日期>' in l][-40:]"
```
典型致命信号：
- `MCP server 'xxx' failed initial connection ... Connection closed` → 直接手工跑 `.cmd` 看 Python 报错
- `failed to connect to docker API at npipe:////./pipe/dockerDesktopLinuxEngine` → Docker 未开，OpenClaw 不可用

**MCP 挂了怎么定位**（2026-09-09 实测路径）：
```bash
cat "C:/Users/Administrator/Documents/code-news/scripts/codex-api-mcp.cmd"   # 看它用哪个 python
"<那个python>" -c "import mcp.server.fastmcp"                                 # 看是否 ModuleNotFoundError
"<那个python>" -m pip list | grep -i mcp                                      # 看版本；2.0.0 会破坏 1.x API
```

### 4. 数据完整性
```bash
grep -rl --include='*.md' -e '{{' . | wc -l                       # 占位符
grep -rl --include='*.md' '暂无数据' 内容生产/1-情报与选题/热点与情报/ | wc -l
find . -name '*.md' -type f -empty
cat .obsidian/community-plugins.json                              # 必须含 dataview，否则索引页全是灰色代码块
```

### 5. dataview 索引健康（D6）
对每个含 ` ```dataview ` 的文件，取 `from "..."`，确认目录存在且非空、且活索引排除了 `_模板`。

**⚠️ 别只靠 `check_doc_references.py`**：它只扫「活文档」（指令文件 / 共享认知 / 运行手册 / 工具登记专区 /
`知识库/INDEX.md`·`SCHEMA.md` / MOC index），**不扫各目录自己的 `index.md`/`_索引.md`**，
也不扫带 `<>` 占位符的引用（会判 SKIP）。所以 dataview 源失效可能 MISSING=0 却真实存在。
补一行确定性扫描（本机实测口径：全库 dataview 源 23 个）：
```bash
cd "C:/Users/Administrator/Documents/code-news" && python - <<'PY'
import os,re
V=r"D:\Obsidian Vault\obsidian Vault"; os.chdir(V)
bad=[]
for r,d,f in os.walk("."):
    d[:]=[x for x in d if x not in (".git",".obsidian",".trash")]
    for n in f:
        if not n.endswith(".md"): continue
        p=os.path.join(r,n)
        s=open(p,encoding="utf-8",errors="replace").read()
        for blk in re.findall(r"```dataview\s*\n(.*?)```",s,re.S):
            for src in re.findall(r'^\s*from\s+"([^"]+)"',blk,re.M):
                if not (os.path.isdir(src) or os.path.exists(src+".md")):
                    bad.append((p,src))
print(f"dataview 源失效 {len(bad)} 处")
[print("  MISS",s,"<-",p) for p,s in bad]
PY
```

### 6. 路径引用漂移自检（每轮必跑，零成本）
```bash
cd "C:/Users/Administrator/Documents/code-news" && python scripts/check_doc_references.py --quiet
```
判据：`扫描活文档 > 0`（为 0 = 根路径没解析对，**本次运行无效，不得当通过**）+ `MISSING == 0`。

## 必查的关键目录（对应五项业务链路）
- 公众号产线 → `内容生产/5-发布/已发布/公众号`（**最常断，且会连锁拖垮知乎/头条**）；真正判据是 `内容生产/5-发布/发布台账.md` 的登记行
- 头条产线 → `内容生产/5-发布/已发布/头条`
- 采集 → `raw/articles/*`、`raw/videos/*`
- 知识加工 → `知识库/1-素材摘要/<年月>/`（L1）；`知识库/{5-方法,6-案例,7-判断}/`（L2/L3，由 kb-distill 产出）
- 沉淀 → `系统中枢/经验沉淀/{工作流,复盘,决策}`（决策目录常年 0 条实际内容）

## 常见坑
- **PowerShell 工具不回显输出** → 改用 Bash 工具（Git Bash）。
- **Git Bash 的 `/tmp` 与 Windows Python 的 `/tmp` 不是同一个** → 中间文件写进工作区绝对路径。
- **`hermes cron list` 显示 0 任务**（见第 2 节）→ 99% 是 HERMES_HOME 没继承，用 `hcron.cmd` / `hcron.sh` 重试；
  看到任务后再读 jobs.json 交叉验证。
- **`hermes` 启动时警告 "A previous `hermes update` pulled new code but did not restart running gateways"**
  → gateway 仍在跑旧代码。用 `gateway.pid` 的 `start_time` 判断它跑了多久（2026-09-10 实测：自 09-09 05:42
  起连跑 31 小时）。`hermes gateway restart` 是**会影响线上**的动作，先问用户，别在巡检里自作主张。
- **Windows 平台默认 home 陷阱**：任何"用 CLI 读不到/写不进"的诡异现象，先查是不是掉进了
  `%LOCALAPPDATA%\hermes`。这一条适用于所有 Hermes 子命令，不只对 cron。
- 看门狗任务 `f4404627133c`（cron健康巡检看门狗）报 failed 往往只是"它检出了严重问题"，不是它自己坏了；
  但它连失 10+ 天说明**报警没人处理**（报警疲劳），要单独提示用户。
- 飞书 `delivery_failed` 与产出成功可以并存 —— 产出已落盘，只是通知没发出去（错误：`Feishu dependencies
  not installed. Run 'hermes setup'`）。**别误判成产线失败**，但也别当没发生：用户会以为"日报没生成"。
- **`interval` 的 `minutes` 单位易写错**：2026-09-10 实测 3 个采集任务是 `7200m`（=5 天），本意"每 2 小时"
  应为 `120m`。对照 `skills-git-留痕看门`=120m 才是对的。**这是 raw/ 长期不涨的隐藏根因，务必核对。**
- 采集脚本 `bsk status` 超时阈值 30s 偏紧（bsk 有 protocol drift 警告时响应变慢）→ 会伪装成"采集失败"。

## 已知故障模式速查（2026-09-10 Phase 5 后更新）

> ⚠️ **下表「根因」列里的路径是「事发当时」的路径，不是现行路径**——保留原样以免篡改故障史。
> 现行落点一律看上方「各线真实落点速查」+ `~/.hermes/scripts/vault_paths.py`。

| 任务 | 症状 | 根因 |
|---|---|---|
| **（头号模式）任意任务** | 每天报 `completed`/`ok`，连续多日，**但产出物从不更新** | **路径漂移**：写方落点 ≠ 读方路径。**排查新故障时先核对这两者字面是否一致**，别假设一致 |
| 公众号DSH内容自动化 | 报 completed 累计 16 次，`成品与素材/` 从无 `*-DSH-*.md` | ① generator 读 repos 在 `DSH专线/` 顶层找，实际在 `DSH专线/content产品/`；② pipeline 找文章看 `成品与素材/公众号文章/`（不存在）、找封面看 `成品与素材/封面/`（空）。**已修（Phase 4），4 篇推送成功** |
| 公众号内容生产流水线 | 终稿 08:23 正常生成；`内容生产/成品` 停 08-30 | 断点在「终稿 → 成品归档」。⚠️ **Phase 4 修正**：`发布台账.md` 显示 09-05/06/09/10 均有「公众号草稿已推送」→ **推送一直在工作**，「停 27 天」是 `media_id.txt` 收据停写造成的误判。Pillow 缺失实际导致的是**封面不更新** |
| 知乎内容生产流水线 | Step 6 报 `创建草稿失败: 未能获取文章ID，URL=zhuanlan.zhihu.com/write` | ⚠️ **Phase 3 修正**：**不是 Cookie 失效**，是 bsk 页面加载时序（4s 不够，编辑器 `no_ed`）。已加 `networkidle` + 6s 等待 + 重试 |
| 小红书内容生产流水线 | 停产 26 天，logs 报 `x-mcp 不可用/未登录` | **三个独立根因**：① 任务 08-15 16:56 被 `pause`（`enabled=false`）没人 resume；② `x-mcp`(mcp.aredink.com) 查不到登录态 → **必须用户本人打开小红书页面确认**；③ 该链路**从未列入巡检清单**，所以没人发现。已 resume |
| 头条内容生产流水线 | title 是英文 repo 名（`MadsLorentzen/ai-job-search`），内容取自过期报告 | **Phase 5 修复**：`_generate_article` 读 `GZH_ARTICLES`=`发布/已发布/公众号`（**人工归档**，顶层 0 md）→ 恒空 → 走「从调研报告生成简化版」兜底。改读 `CONTENT_PRODUCT`（`成品与素材`）。该文件另有 30 行 U+FFFD 乱码，已修 |
| 视频号每日生产流水线 | `⚠️ 未找到 _data.json` + exit 1 | **两个问题**：① `VAULT_RESEARCH=CONTENT_PRODUCT` 漂移（`_data.json` 全在 `素材与资源/源码调研`）→ 口播稿退化成 `repos.json` 兜底，产出 `forks 0` 错数。**已修**；② **真凶**：`Fish 调用失败: SSL UNEXPECTED_EOF_WHILE_READING`（逐段 TTS，**无重试**，一次抖动即整条失败，09-09 成功/09-08、09-10 失败）→ 属网络/服务问题，建议加重试 |
| 原生线（公众号）调研 vs 写文 | 当天文章无 `_data.json` 快照 | **Phase 5 修复**：调研用 `repos[:5]`（不过滤），写文用「跳过已写过/今日已写」后取第一个未写过的 → **口径不一致**。前 5 个若都已写过，写文落到第 6 个未调研仓库。修法 = 调研前套用 `article_generator.get_existing_repos() \| get_today_generated_repos()` |
| 技能与MCP资产盘点 | NameError | `skills_mcp_inventory.py` L22 引用未定义的 `OBSIDIAN_AI_DAILY` |
| Skills-MCP 清单每日刷新 | PermissionError | 输出路径拼成了**目录** `.../各Agent档案/hermes` 却当文件写 |
| 发布台账闭环巡检 | exit 1 | 真实数据不一致：成品/台账数对不上，有台账孤儿 |

### 判据与巡检清单的坑（Phase 5 已修，务必记住）

1. **`内容生产/5-发布/已发布/公众号` 是人工发布归档，不是自动线产物** —— 按用户边界「推草稿箱=完成」，
   它停更**不算故障**。别拿它当健康判据（曾造成恒红误报）。
2. **`内容生产/成品` 与 `内容生产/成品与素材` 两个旧名均已废弃** —— 2026-09-28 合并为
   **`内容生产/4-成品与审查`**（常量 `PRODUCT_UNIT` 与 `CONTENT_PRODUCT` 现指向同一目录）。
   写盘单元是 `<日期>-<项目>/`（见 `vault_paths.article_unit()`）。**别再按「成品/」去找产物**。
3. **巡检清单必须覆盖所有 enabled 的产线任务**。血泪教训：`小红书内容生产流水线`
   没列进清单 → 停产 **26 天**无人发现。
4. **产出稀疏的任务要用 `sparse=True` 豁免「静默失败」判据**（收藏采集无新增就不落文件）。
5. `assert_artifacts.py`（工作区）已支持 `pattern` / 绝对路径 / `sparse`，并内置
   **第 ⑤ 项路径漂移自检**（监控「废弃目录近期是否又出现新文件」）。

### 各线真实落点速查

| 链路 | 落点 | 匹配 |
|------|------|------|
| 公众号①终稿生成 | `内容生产/2-调研与素材/深度调研/<日期>/` | `*.md` |
| 公众号②推草稿箱 | `内容生产/5-发布/发布台账.md` | 台账 |
| 头条 / 知乎 / 小红书 / 抖音 / 快手 / 视频号 / B站 | `内容生产/5-发布/已发布/{平台}` | `*.md` |
| 成品单元（一篇文章一套） | `内容生产/4-成品与审查/<日期>-<项目>/` | `*.md` |
| DSH | `内容生产/9-DSH专线/` | `*-DSH-*.md` |
| 贴图 | `C:\Users\Administrator\.hermes\tie_tu_output`（**vault 之外**） | `*.md` |
| 视频号口播稿 | `内容生产/4-成品与审查/` | `*口播脚本*.json` |
| 源码数据快照 | `内容生产/2-调研与素材/素材与资源/源码调研` | `*_data.json` |
| 平台规则（运营知识） | `运营中心/<平台>/` → `_规则原文/` + `规则与合规/` | `*.md` |

### 路径漂移排查法（3 步）

1. **找写方**：`grep -n "OUTPUT_DIR\|OUTPUT_PATH\|write_text\|mkdir" <写脚本>`，确认文件实际落到哪
2. **找读方**：`grep -n "glob\|DIR\|_JSON\|Path(" <读脚本>`，逐条比对是否同一个字面路径
3. **立刻验证**：`import` 那个 pipeline 模块，直接 `print(模块.ARTICLES_DIR)` + 调 `find_*()` 看返回条数 —— 别靠推理

### 排查执行器报错时必做

`executions.db` 的 `error` 字段**会被截断**（默认只存前若干百字符），且 `stdout` 会混在 `error` 里。
定位真凶必须拉**更长片段**：

```python
c.execute("SELECT error FROM executions WHERE job_id=? AND started_at LIKE ? ORDER BY started_at DESC LIMIT 1", (jid, "2026-09-10%"))
print((c.fetchone()[0] or "")[:2500])   # 给足长度，别只取 300
```

实例：视频号第一次看只到「⚠️ 未找到 _data.json」就以为是它挂了；拉全后才看到
真正的 `[ERROR] Fish 调用失败: SSL EOF`（前者只是 stderr 警告）。

### 排查编码损坏（乱码）

```python
s = open(p, encoding="utf-8").read(); s.count("\ufffd")   # >0 即有损坏
```
全量扫描确认是否系统性：逐个文件统计 U+FFFD。本仓库实测仅 `toutiao_pipeline.py` 中招（68 个/30 行）。
修复方式：按行号 + **保留原缩进**整行替换，替换前 assert 该行确实含 `\ufffd` 以防行号错位。

## 输出
生成结构化报告：红黄绿总览 → P0/P1 分级（含证据与根因）→ A~E 五维明细 → cron 失败清单 → 处置优先级 → 与上次巡检对比。
报告写到**工作区**而非 vault。理由：巡检报告是**一次性诊断产物**，不是知识或决策，按 vault 的「新产出先落草稿箱、不随意建文件」惯例不该直接进库。
（2026-09-12 更正：原此处写「vault 有白名单约束」——该理由已过期，Work Buddy 现为**全库可读写**，见 `vault/AGENTS.md` v3.3。写入 vault 不再受目录限制，但仍须守内容纪律与协调协议。）
如需把巡检结论留痕进 vault，先问用户，且应落到 `系统中枢/运行小结/错误复盘/` 或写成决策记录，而非散落根目录。

## parse_cron.py 模板（直接读 jobs.json + executions.db，替代 CLI）
```python
# -*- coding: utf-8 -*-
import json, sqlite3, datetime, collections
J  = r"C:\Users\Administrator\.hermes\cron\jobs.json"
DB = r"C:\Users\Administrator\.hermes\cron\executions.db"
NOW = datetime.datetime.now().astimezone()

jobs = json.load(open(J, encoding="utf-8"))["jobs"]      # list
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); cur = con.cursor()

ex = collections.defaultdict(list)      # 执行历史
for r in cur.execute("SELECT job_id,status,started_at,finished_at,error "
                     "FROM executions ORDER BY rowid DESC"):
    ex[r[0]].append({"status": r[1], "started": r[2], "error": (r[4] or "")[:400]})

inc = collections.defaultdict(list)     # 故障聚合（关键，别漏）
for r in cur.execute("SELECT job_id,state,failure_type,first_seen_at,last_seen_at,error "
                     "FROM cron_incidents ORDER BY rowid DESC"):
    inc[r[0]].append({"state": r[1], "ftype": r[2], "first": r[3], "last": r[4],
                      "err": (r[5] or "")[:200]})

def age_days(ts):
    if not ts: return None
    t = datetime.datetime.fromisoformat(ts)
    if t.tzinfo is None: t = t.replace(tzinfo=NOW.tzinfo)
    return (NOW - t).total_seconds() / 86400.0

for j in jobs:
    jid = str(j["id"]); e = ex.get(jid, [])
    sched = j.get("schedule", {})
    recent = e[:10]; ok = sum(1 for x in recent if x["status"] == "completed")
    print(f'{j["name"]:36} streak={j.get("failure_streak",0):3} '
          f'近10={ok}/{len(recent)}  天龄={age_days(j.get("last_run_at"))}  '
          f'status={j.get("last_status")}  sched={sched.get("display")}')
    if j.get("last_error"): print("   ", j["last_error"][:300])
    for i in inc.get(jid, [])[:2]: print("   !", i["ftype"], i["last"][:16], i["err"][:120])
```
排序建议：先按 `failure_streak` 倒序（连续失败最刺眼），再按天龄倒序。
报告里务必区分「脚本自身崩了」vs「脚本检出了业务问题才 exit 1」（后者如看门狗、台账巡检）。
