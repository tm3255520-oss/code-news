---
name: obsidian-governance-change
description: 安全修改 Obsidian 多 Agent 治理规范（vault 里的 00~04 号共享认知文档、模型配置母本、vault 根 AGENTS.md、各 Agent 档案）。当用户要求「补登记/改权限/调白名单/修订规范/升版」等改动协作规则时使用。核心是「一处改动必须在 N 处同步登记」+「改完跑引用校验器」，漏改会造成规范自相矛盾或引用失效。**边界**：我改的是**协作规则 / 权限 / 白名单 / 登记**；**日常写内容、把资料归位**走 obsidian-vault-ops；**只读巡检**走 obsidian-vault-health-check。判据：说「整理到系统中枢」时，**改规则**归我、**只归位文件**归 obsidian-vault-ops。
agent_created: true
version: 1.5.1
tags: [obsidian, 治理规范, 多智能体, 登记同步, vault]
---

# Obsidian 多 Agent 治理规范变更

> 对象：`D:\Obsidian Vault\obsidian Vault` 内的治理层文档。
> 主目录：`系统中枢/规则与权限/智能体共享/`（00~04 号 + 模型配置母本）
> 用户身份：自媒体创作者，模型 `deepseek-flash`，我 = `workbuddy`

## 🔴 头号铁律：登记是重复的，必须全批同改

**一条权限/白名单信息同时存在于 6~8 个文档里。只改一处 → 规范内部自相矛盾 → 比不改更糟**，因为其它 Agent 会读到两个版本。

改任何权限/白名单/工作区信息，**必须**按此清单逐处核对（**这是最容易漏、也最致命的环节**）：

| # | 文档 | 位置 |
|---|---|---|
| 1 | vault 根 `AGENTS.md` | 「多 Agent 总览」表 + 表下注 + 「协作五原则」+ 版本号 |
| 2 | `00-多Agent工作区总览.md` | §三 总表 + 更新注 + §五 铁律 + frontmatter status |
| 3 | `01-总则与工作区划分.md` | §一 核心原则 + §二 总表 + 表下注 + §三 同步规则 + §四 待办 |
| 4 | `02-目录与命名规范.md` | §1.2 写者表后注 + §五 禁止与例外 + 修订记录 |
| 5 | `03-工具与调用.md` | §二 各智能体工具速览（表下注）+ §六 接入状态表 |
| 6 | `04-各Agent工作区设定.md` | §2.N 该 Agent 小节 + §三 统一规则 |
| 7 | `各Agent档案/<agent>/_索引.md` | 该 Agent 的权限表 + 待办 |
| 8 | `模型配置母本.md` §五 | 变更记录（续记一条） |

**改完必须 grep 验证**（见下「验证」节），别靠记忆。

### ⚖️ 先判类型：不是所有改动都要跑 8 点全批

8 点全批**只适用「权限 / 白名单 / 工作区规则」三类**（那才是被复制到 6~8 处的信息）。判错类型会导致两种浪费：该全批的只改一处 → 规范打架；不该全批的硬凑 8 处 → 给无关文档灌水。

| 改动类型 | 例子 | 实际同步点 | 要不要升 AGENTS.md 版本 |
|---|---|---|---|
| **权限 / 白名单 / 工作区规则** | 权限升降、白名单增删、「一个文件一个写者」语义 | **8 点全批**（上表） | ✅ 要（vX.Y +0.1，版本行写一句话） |
| **能力清单 / 技能 / 插件 / 接线** | WorkBuddy 技能数、junction 接线、插件启停 | 仅 2 处：`03` §二 表 + §七 状态；`各Agent档案/<agent>/_索引.md` | ❌ 不用（不碰规则） |
| **MCP 接入状态**（⚠️ 别当上面那类！） | 某 Agent 的 MCP 由「未接入」改为「已接入/配置就绪」 | **与规则类同批**：MCP 状态被复制到 `AGENTS.md` + `00` + `01` + `03` §六 + `04` + 母本；本轮实测 **grep 三查抓出 3 处漏改** | ✅ 要 |
| 纯事实纠错 | 目录名写错、路径失效 | 出错文档本身 + 受影响文档 | ❌ 不用 |

> **判定口诀：别看改动叫什么，看「这条信息被复制到了几处」。** 名字像「能力类」但字样散落在多份规则文档里的（MCP 接入状态就是），按规则类走全批 + grep 三查。
> 反例教训：2026-09-12 我按「MCP 属能力类、只需 2 处」推进，结果 `01` 第 43 行「MCP 能力仍未接入」、`00` 第 44/83 行的 `v3.3`、`04` 第 53 行的 `v3.0` 全部漏改，靠 grep 三查才捞回来。

实测（2026-09-12）：能力类（技能数量）全库检索确认 `AGENTS.md` / `00` / `01` / `02` / `04` **均无技能数量表述**，只有 `03` §二 表行写了「Work Buddy | 2 个 skills」→ 故**技能数量**类改动确实只需动 03 + 档案。**但 MCP 状态不在这个结论范围内。**

## 🔌 WorkBuddy 技能接线的专属事实（2026-09-12 实测）

- **WorkBuddy 不在统一分发脚本内**：`code-news\scripts\sync_agent_skills.py` 的 `--agents` 只认 `codex,claude,hermes,dsh,openclaw`，脚本全文无 `workbuddy` 引用 → 别指望跑脚本，也**别去改脚本**（那是产线资产，按 `repair-gate` 只报告）。
- **接线命令用 PowerShell**：`New-Item -ItemType Junction -Path <link> -Target <target>`。**Git Bash 下 `cmd //c mklink /J` 会因路径转义静默失败**（返回 FAIL 但不报错），别用。
- **验证接线必须查 `LinkType`**，只 `Test-Path` 不够（副本也能通过）：
  ```powershell
  Get-ChildItem "<skills 目录>" -Force | Where-Object { $_.LinkType } |
    Select-Object Name, LinkType, Target
  ```
  只有 `LinkType = Junction` 才是真链接。
- **hub 结构**：共享技能 hub = `C:\Users\Administrator\.agents\skills`；hub 技能分发到各 Agent 时表现为**符号链接**（`lrwxrwxrwx`），而放在某 Agent 目录里的**实体目录**（`drwxr-xr-x`）说明它是该 Agent 的原生技能。判断「主实现在哪」靠这个特征。
- **`skillOverrides` 的 `off` 是硬禁用，不是「仅不列出」**：报错原文 `Skill "X" is disabled via skillOverrides. Re-enable it in /skills or remove the override from your settings to run it.` 清除后**热生效**，无需重启 App。改前务必备份 `settings.json`。
- **WorkBuddy 的 MCP 接入（2026-09-12 实测，推翻旧登记）**：WorkBuddy **支持 MCP** —— 配置文件 `~/.workbuddy-ai/mcp.json`，`mcpServers.<name>`。条目**不许自创格式**，须逐字段等同官方定义 `sync_agent_mcp._entry_claude()` = `{"command":"cmd","args":["/c","<绝对路径>\\toolkit-mcp.cmd"]}`（Windows 下 `cmd /c` 包 `.cmd` 是官方推荐写法）。
  - 权威比对别手写 JSON 字符串做比较（反斜杠转义极易踩坑，我因此误报过一次 False）→ **直接 import 官方函数比**：`import sync_agent_mcp as S; S._entry_claude() == mine`
  - 自检：`<hermes venv>/python.exe scripts/mcp_toolkit_server.py --selftest` → 期望 `SELFTEST_RESULT: OK`
  - **旧登记「WorkBuddy 无原生 MCP 客户端」是错的**；不自动注册的真实原因是 `sync_agent_mcp.py` 的 `AGENTS` 只含 `codex,claude,hermes,dsh`，脚本不覆盖 workbuddy —— **不是**没有客户端。→ 登记文件前**先实测**，别照抄旧文档。
- 🔴 **WorkBuddy 的 MCP 生效机制（2026-09-12 实测，最容易误判的一条）**：MCP 配置在**会话启动时**以 `--mcp-config` 参数注入 sidecar（并带 `--strict-mcp-config`），**运行中不能热加载**。
  - 「点信任」= 登记授权 ≠ 激活；**必须新开会话（或重启 App）**才生效
  - **验证是否真加载**（别靠猜）：
    1. 查会话 sidecar 启动参数里 `--mcp-config` 是否含目标 server 名 → 日志 `~/.workbuddy-ai/logs/daemon.log`，搜 `spawn details`
    2. 查 `resolveMcpServers resolved` 的 `hasTrustedRuntimeMcpEnv` / `projectMcpCount`
    3. 直接跟服务器跑标准 stdio MCP 握手（`initialize` + `tools/list`）看能否列出工具 → **服务端可用 ≠ 应用已加载**，两件事要分开验
  - **工具数两个口径别混**：`--selftest` = 9 个业务工具；MCP `tools/list` = **10 个**（多一个 `toolkit_status` 自检工具）。两个数都对。**未生效时看不到任何该 server 的工具是正常的**，别误判为配置错。
  - 其他存储也顺手查过但**都不是**信任落点：`mcp-approvals.json`（长期为空 `{}`）、`workbuddy.db`（无 MCP 表）、审计日志（只有 command-safety 事件）。→ 别在这些地方浪费时间找「信任记录」。
- **`.codex` 不受版本控制（2026-09-12 实测）**：`C:\Users\Administrator\.codex` 下 `git status` 返回 `fatal: not a git repository`。而 6 个共享接口的**主实现只在这里**（hub / `code-news\.agents\skills` / 备份区原本均无副本）→ **真实单点故障，误删即永久丢失**。恢复快照：`D:\Obsidian Vault\备份\技能主实现归档-20260912\`（6 技能 / 52 文件 / SHA256 manifest）。**用户已裁定不迁移（维持 B），别主动重提**；但改 `.codex` 下任何技能前先确认归档是最新的。
- **「描述性指针失效」≠「能力失效」**：`tool_registry.json` 里的 `fallbacks` 是**描述性回落指针**，它指向死路**不代表接口本身坏**。修之前先追**真实调用链**（多半走 `config/mcp_toolkit.json`）确认到底哪一环断了——2026-09-12 我一开始把一条死链定级为「能力失效」，实测发现能力一直好着。

## 执行步骤

### 1. 备份（强制，写 vault 重要文档前）
```bash
cd "D:/Obsidian Vault/obsidian Vault"
BK="D:/Obsidian Vault/备份/<批次名>-$(date +%Y%m%d-%H%M)"
mkdir -p "$BK"
cp AGENTS.md "$BK/"
cp "系统中枢/规则与权限/智能体共享/"{00,01,02,03,04}*.md "$BK/"
cp "系统中枢/各Agent档案/<agent>/_索引.md" "$BK/<agent>-_索引.md"
```
批次名用中文描述性短语，如 `WorkBuddy权限升级-全库可读写-20260912-0100`。

### 2. 先摸清事实，再动笔
改「登记」这类工作，**登记必须等于事实**。先实测：
```bash
ls "系统中枢/各Agent档案/"                    # 实际有哪些 agent 档案
grep -rn "关键词" --include="*.md" . | head -30   # 该信息散落在哪
```
历史教训：`02` 曾把知识库写成 `platforms/`（**该目录根本不存在**）、`entities/`（应为 `实体/`）；
白名单里写了 `wiki/`（实际是 `知识库/`）。**目录名错了会让 Agent 写错位置甚至建错目录。**

### 3. 全批同改（按上表 8 处）
版本号递进：`AGENTS.md` 现在是 **v3.3**，每次实质性改动 +0.1，并在版本行写明「vX.Y 变更：<一句话>」。
`00`/`04` 的 frontmatter status 同步更新（`00` 用 vN 序号，见其现状）。

### 4. 验证（grep 三查）
```bash
cd "D:/Obsidian Vault/obsidian Vault"
# ① 新信息是否已铺开
grep -rc "新表述关键词" AGENTS.md "系统中枢/规则与权限/智能体共享/"{00,01,02,03,04}*.md
# ② 旧登记是否清净（应输出空）
grep -rn "旧表述关键词" --include="*.md" AGENTS.md "系统中枢/规则与权限/智能体共享/"
# ③ 版本号是否统一（只剩历史变更说明=正常）
grep -rn "v3\.[0-9]" AGENTS.md "系统中枢/规则与权限/智能体共享/00-多Agent工作区总览.md"
```

### 4b. 验证引用有效性（2026-09-13 新增）

改动规范后，除了 grep 三查，还要跑**确定性引用校验器**，确认所有活文档里的路径引用有效（改名 / 改路径后尤其必要）：

```bash
cd "C:/Users/Administrator/Documents/code-news"
python scripts/check_doc_references.py          # 文本报告，退出码 0 = 无 MISSING
python scripts/check_doc_references.py --quiet  # 仅汇总 + MISSING 明细
```

- 判定三态：`ok` / `missing`（需修）/ `skip`（路径片段 / 概念名 / WSL 路径 / 模板，不判错）。
- 覆盖：vault 根 `AGENTS.md`、`code-news/AGENTS.md`、`code-news/CLAUDE.md`、`agent-work/AGENTS.md`、各 Agent home 的 SOUL / AGENTS、`智能体共享/` 00~04 与模型配置母本、`运行手册/*.md`、索引页。
- 豁免：行内 `<!-- refcheck:ignore -->`（单行）、文档顶部 `<!-- refcheck:ignore-file -->`（整篇，用于历史记录 / 方案 / 总结类文档）。
- 配套铁律：任何目录改名 / 移动，必须「扫描 → 改引用 → 校验器清零 → 决策留痕」四步（见 `01-总则与工作区划分.md` §一.6、`02-目录与命名规范.md` §五、`00-多Agent工作区总览.md` 铁律 8、vault 根 `AGENTS.md` 协作第 6 条）。

### 5. 写决策记录（例外与变更需留痕，规范自己要求的）
目录：`系统中枢/经验沉淀/决策/`，命名 `YYYY-MM-DD-<标题>.md`
模板：复制 `_模板-决策.md`（frontmatter 用 `类型/标题/一句话定义/来源/创建日期/最后更新/状态/标签`）
必须包含：背景 / 选项对比表 / 选择 / 理由 / **执行清单表** / **影响与残余风险** / 结果（留空待回填）
索引 `决策/index.md` 是 dataview 自动生成，**不用手工加条目**。

#### 5b. 用户就「选项表」裁定后如何收口（2026-09-12 实战）

选项表一旦被用户裁定，**旧记录的「待裁定」字样必须清零**，否则规范会自相矛盾（下次我或别人会把已裁定的项当待办捡起来）。要改 **5 处**：

1. **frontmatter `状态` 字段** → 由「待裁定」改为终局态（如「全部收口（…风险二经用户裁定维持 B…）」）
2. **选项表对应行** → 行内标注「（YYYY-MM-DD 选定；同日经用户确认维持）」
3. **`## 选择` 节** → 追加「**裁定补记**」引用块：写清裁定了什么 + 明确否掉了哪个选项 + 未执行方案的命令留在哪
4. **`## 影响与残余风险`** → 把「待裁定」改成「**已知情接受**」+ 写清**触发条件**（什么情况下需要启用备选方案）
5. **`## 结果`** → 回填「已收口 / 有无回滚 / 仍待用户操作的事项」

同时要同步**下游引用处**（本例 4 处）：同名主题的清单文档、Agent 档案 `_索引.md` 能力表、以及备选方案所在的 README。

**验证**：`grep -rn "待裁定" <改过的目录>` 必须 **0 命中**（除显式写「不再挂待裁定」的说明句外）。本例靠这条查出决策记录小节标题仍停在改前状态。

> **同时守住「不抹历史」**：只改**状态字段与标题**，**别删**「当时为什么先选 B」的推理段——那是决策过程的一部分。裁定结果以「补记」形式叠加，不覆盖原叙述。

### 5c. 用户只发了一个字母/歧义词时：先问，别猜

用户发来孤立单字（如「b」）而你手上**没有**待选 A/B 时 → **停下确认**。判断依据：去翻自己给过的**选项表**，若那个字母只对得上某张表里的选项，就**带着表名去问**（「是决策记录里风险二的 B 选项吗？」），给出 2~4 个具体选项让对方点。

理由：单字母歧义面极广（可能是错手发送、可能指别的表、可能指别的意思），而**猜错的代价不对称**——若猜成「执行 C 方案」这类跨 Agent 变更，误判成本远高于问一句。

### 6. 更新记忆
- 工作区日志：`<workspace>/.workbuddy-ai/memory/YYYY-MM-DD.md`（追加）
- 跨项目长期：`~/.workbuddy-ai/MEMORY.md`（我的权限、协作协议这类要长期记）

## 🔑 两个必须守住的概念区分

### 「权限」≠「内容纪律」
权限（能写哪个文件）和内容规则（内容该怎么写）是**两套东西**。**授权扩大不使纪律失效**：

| 内容纪律 | 是否因权限扩大而变 |
|---|---|
| `raw/` 只进不出 | ❌ 不变 |
| `经验沉淀/决策/` 只追加不覆盖 | ❌ 不变 |
| `log.md` 不删历史 | ❌ 不变 |
| vault 不放密钥 | ❌ 不变 |
| 不在 vault 根随意建文件 | ❌ 不变 |
| 除用户明确要求外不动 `.obsidian/` | ❌ 不变 |

理由：这些约束的是「内容该怎么写」而非「谁可以写」。把授权误读成免责 = 用一次授权换掉整套数据完整性保障。

### 「一个文件一个写者」是协调协议，不是权限墙
原表述「按目录固定写权限，两个 Agent 不写同一文件」——**一旦出现全库权限 Agent 就直接失效**。
若不同步改写，规范自相矛盾。正确改法：**权限照给，用四条纪律对冲覆盖风险**：

1. **不静默覆盖** —— 写非主责目录前先查既定写者与占用
2. **日期前缀分区** —— 共用目录一律 `YYYY-MM-DD-*`，天然免碰撞
3. **写前备份** —— `D:\Obsidian Vault\备份\<批次名>-YYYYMMDD-HHmm\`
4. **跨界先告知** —— 改他人归属文件先告知 + 决策日志留痕

同时把表格里「写者」列的语义说明为「**主责写者**（默认权限），非权限墙」。

## 现状基线（2026-09-12，改前先核对是否已变）

- **Work Buddy（我）= 全库可读写**（用户裁定 B 方案）；读取全库按需
- **持「全库可读写」者共 3 个**（2026-10-01 基线）：Work Buddy（09-12）/ Codex（09-16）/ **piAgent（10-01）**
- 其它 Agent 仍按白名单：Hermes（全库读 + 内容生产/raw/知识库/运行小结写）、
  Claude Code（知识库读 + 草稿与已发布写）、Harness(=DSH，MCP 间接读、不直接写)、
  OpenClaw（只挂共享认知与自身档案）
- Agent slug 小写：`claude-code` / `codex` / `hermes` / `dsh`（**= harness 同一实体**）/ `openclaw` / `workbuddy` / **`piagent`**
- 实际档案目录 **7 个**（2026-10-01 起）；**没有** `harness/` 目录，别建也别引用
- **各 Agent 的「指令文件」落点**（2026-10-01 补）：Codex `agent-work\AGENTS.md`（管线 `code-news\AGENTS.md`）；Claude Code `agent-work\AGENTS.md`（管线 `code-news\CLAUDE.md`）；Hermes `~/.hermes/SOUL.md` + vault 根 `AGENTS.md`；**piAgent `D:\pi-agent\AGENTS.md`**（pi 从 cwd 逐级向上查找 `AGENTS.md`）。行尾基准：**既有指令文件全部纯 LF**
- vault 顶层：`raw/ 知识库/ 内容生产/ 参考库/ AI工具/ 系统中枢/` + `AGENTS.md index.md log.md log_index.md`
- **`知识库/` 子目录**（易错）：`主题/ 实体/ 摘要/ 概念/ 综合判断/ 归档/` + `INDEX.md` + `SCHEMA.md`
  —— 无 `wiki/`、无 `platforms/`
- **WorkBuddy 能力基线**（2026-09-12 用户裁定后）：skills 目录 14 项 = 8 自有 skill + **6 条 junction**（`content-research-writer` / `Humanizer-zh` / `ian-xiaohei-illustrations` / `guizang-social-card-skill` / `dbs-benchmark` / `dbs-content`，指向 `C:\Users\Administrator\.codex\skills\`）；`settings.json` 的 `skillOverrides` **已清空**；`enabledPlugins` 开启 6 个（腾讯系 5 个 + `find-skills`），保持关闭 3 个（`weixinpay` / `agent-browser` / `playwright-cli`）；**MCP**：`~/.workbuddy-ai/mcp.json` → `mcpServers.toolkit`（已登记，⏳ 待用户点「信任」）；vault 权限 **全库可读写**

## 常见坑

- **改权限时只改表格忘了表下注**：表格和注是两处，注里有「权限≠免责」等关键限定，都要改。
- **`03-工具与调用.md` 有同名概念陷阱**：§六「接入状态」表讲的是 **MCP 能力**，
  §二 讲的是 **vault 权限**。两个维度，改一个别顺手把另一个也改了，也别混读。
  📌 该表里 WorkBuddy 的条目 2026-09-12 晚已由「未接入」更正为「已登记（配置就绪、待信任激活）」；
  **同批更正**：`00`/`01`/`04`/`AGENTS.md`(→v3.4) 均有 MCP 字样需同步（见上「先判类型」表）。
  边界：OpenClaw 仍为「无原生 MCP 客户端」——**别顺手把它也改了**。
- **登记必须等于事实，别照抄自己上一轮的登记**：我 2026-09-12 有一次把「MCP 未接入」写进登记，
  根源是信了旧文档而非实测，属于**制造新的不准确**。规则：**任何能力/状态类登记，写下前先跑一次实测命令验证**，
- **⚠️ 别把「配置文件」当成「指令文件」登记（2026-10-01 实战踩中）**：piAgent 接入登记时，`00-多Agent工作区总览.md` §四.2 写「piAgent 读 `.pi\agent\settings.json` + 技能目录 `SKILL.md`（**无 AGENTS.md 自动加载机制**）」—— **两处都错**：`settings.json` 是配置不是指令文件；pi **确有** AGENTS.md 加载机制。**正确姿势 = 读该 Agent 源码，别凭印象**：
  - ① 找加载逻辑：`grep -rn "AGENTS.md" <包>/dist/core/`（pi 的候选名 = `AGENTS.md` / `AGENTS.MD` / `CLAUDE.md` / `CLAUDE.MD`，搜索方式 = **cwd 逐级向上到根** + 始终加载 `agentDir`）
  - ② 定 cwd：查启动脚本里的 `cd`（pi 的 `pi-web-30141.cmd` 有 `cd /d "D:\pi-agent"`）→ 决定文件该放哪
  - ③ 落盘后**用该 Agent 自己的 loader 实测**：pi 可 `import { loadProjectContextFiles }` 传 `{cwd, agentDir}` 看返回清单（比「人肉推断」可靠）
  - ④ 行尾对齐**同族既有指令文件**（本机全为 **LF**），别按「vault 用 CRLF」的习惯写
  - ⑤ 加载**绑定 cwd** 的 Agent，必须在登记里如实写明「换目录启动则不命中」的残余边界
- **决策记录不要抹除历史状态**：`状态: 已执行（待用户终审）` 这类字样在决策记录里属**历史叙事**，
  终审后应改状态字段 + 在修订记录加「终审通过」条目，**但不要删掉叙述当时的句子**，否则决策过程失真。
- **两份决策记录打架**：若新决策推翻了旧决策的结论，**必须回改旧记录的状态字段**为
  「已被覆盖 / 部分被覆盖」，并在文首 + 结果节双处标注哪部分作废、哪部分仍有效。
- **`模型配置母本.md` 是 YAML-in-markdown 混合**：1~1442 行是配置数据，1443+ 是人工正文，
  §五变更记录在文件末尾。改它只动正文，别碰 YAML 区。
- 改 vault 用 Read/Edit/Write 工具，**别用 sed**（中文路径 + 编码易崩）。
- **⚠️ 也别用 Bash heredoc 往文件里写 Windows 反斜杠路径（2026-10-01 实测）**：命令文本经 heredoc 传给解释器时，`D:\pi-agent` 会被**规范成 `D:/pi-agent`**（实测：Python 里 `repr()` 打印的「写入内容」本身已是正斜杠，与写入层无关）。**Edit / Write 工具不受影响**（反斜杠原样落盘）。所以：**含 Windows 路径的登记/文档，一律用 Edit / Write 写**；确要用 heredoc，就接受正斜杠（Windows 可解析），别事后靠复读才发现写歪了。
- 备份目录不要自作主张删除，等用户确认。

## 参照案例
- `2026-09-12-WorkBuddy白名单补登记与目录规范修订.md` —— 白名单补登记 + 按实测目录重写 02
- `2026-09-12-WorkBuddy权限升级为全库可读写.md` —— 权限升级 + 「一个文件一个写者」改协议
- `2026-09-12-WorkBuddy技能接线与插件启用.md` —— 技能接线 + 插件启停（能力类，2 处同步）
- `2026-09-12-WorkBuddy风险处置与MCP接入.md` —— 三类残余风险处置 + MCP 接入 + **grep 三查抓出 3 处漏改**（MCP 状态按规则类走全批的判例）
- `2026-10-01-piAgent接入与vault权限登记.md` —— **新 Agent 接入**（第 7 个）+ 接入当日漏改 5 处的事后补全 + 断链清零；配套：`D:\pi-agent\AGENTS.md` 指令文件补建（含「配置文件≠指令文件」事实订正 + loader 实测）
