# CLAUDE.md — code-news 工作区（Claude Code）

本文件是 Claude Code 在 code-news 的入口。总规范以仓库根 `AGENTS.md` 为准（两者内容一致）：Obsidian vault 是知识中枢，本仓库是共享代码工作区，能力路由查 `config/tool_registry.json`。

## 关键约定

- 本仓库是**管线/生产代码库**；日常调研/实验/草稿到 `C:\Users\Administrator\Documents\agent-work`（通用工作区，入口见其 AGENTS.md）。
- 工作区分层（四层）：知识 → `D:\Obsidian Vault\obsidian Vault`（读写白名单见 vault 根 AGENTS.md 与 `系统中枢/规则与权限/智能体共享/01-总则与工作区划分.md`）；生产代码 → 本仓库；通用工作区 → `agent-work`；配置/技能/密钥 → `C:\.claude`。
- 内容生产类任务先查 `config/tool_registry.json`；正式发布能力默认关闭（publisher/xhs 为占位）。
- **新建能力 / 新建脚本 / 新接平台前**先跑 `python scripts/tool_inventory.py <关键词>` 盘点已有实现，
  按「直接调用 / 扩展合并 / 新建」三选一处置并在提交信息里写明结论（复用守则 · 协作原则 4，
  规则全文：vault `系统中枢/规则与权限/智能体共享/06-复用守则.md`）。
- 开发前必读 vault `系统中枢/经验沉淀/工作流/` 与 `系统中枢/经验沉淀/复盘/`（铁律：确定性流程禁用 LLM）。
- vault 不做 git；代码改动只在本仓库做 git。

## Obsidian 关键文档（快速进入状态）

> 知识中枢在 `D:\Obsidian Vault\obsidian Vault`（下称 vault）。每次开工先按下面顺序进入状态；具体任务再按需精读。

@D:/Obsidian Vault/obsidian Vault/系统中枢/规则与权限/智能体共享/00-多Agent工作区总览.md

### 必读（每次开工前）

| 文档 | 用途 |
|---|---|
| `系统中枢/规则与权限/智能体共享/00-多Agent工作区总览.md`（上方已导入） | 四层工作区、Agent×vault 白名单、铁律、技能入口——最快进入状态 |
| vault 根 `AGENTS.md` | v3.4 多 Agent 总规范：读写白名单、禁止行为、开发前必读 |
| `系统中枢/规则与权限/智能体共享/03-工具与调用.md` | 能力路由：tool_registry.json、内容生产统一入口、MCP、密钥登记处 |
| `系统中枢/各Agent档案/claude-code/_索引.md` | Claude Code 资产地图（含桌面端 3P/DeepSeek 配置） |

### 按任务类型按需精读

| 任务 | 先读 |
|---|---|
| 内容生产（对标/选题/写作/配图/封面） | `code-news/config/tool_registry.json` + `内容生产/1-情报与选题/选题与题材/` |
| 开发新 Skill/MCP/工作流/cron | `系统中枢/经验沉淀/工作流/index.md` → 对应领域篇 + `系统中枢/经验沉淀/复盘/`（铁律：确定性流程禁用 LLM） |
| 写 vault 文档/产出 | `系统中枢/规则与权限/智能体共享/02-目录与命名规范.md`（命名 + frontmatter + 白名单） |
| 桌面端/DeepSeek 配置 | `系统中枢/各Agent档案/claude-code/Claude桌面端接入DeepSeek指南.md` |

### 进入状态流程（每次开工）

1. 读上方已导入的 00 总览，确认当前任务属于哪一层（code-news 管线 / agent-work 日常）。
2. 内容生产类任务 → 先查 `config/tool_registry.json` 路由；发布类默认关闭，绝不自动公开发布。
3. 涉及新工作流/Skill → 先读 `系统中枢/经验沉淀/工作流/` 对应领域篇，再动手。
4. vault 写入只走白名单（先落草稿箱再整理），禁止写 vault 根目录；vault 不做 git。

### 协同协议：开工三查 / 收工三写（2026-09-30 起强制）

> 目的：多 Agent 共用一份任务态，止血「别人做了我不知道 / 重复做」。规则权威：vault `系统中枢/规则与权限/智能体共享/05-记忆协议.md` §六；用法：vault `系统中枢/协同/_使用说明.md`。

**开工三查**：① 查 `系统中枢/协同/任务台账.md` 有无同主题的 `进行中` / `已完成` 行（`进行中` 且非自己 → 不重复开工）② 命中就读 `系统中枢/协同/交接/<任务ID>.md` 最后一块 ③ 都没有就新建一行（状态=进行中、负责人=自己）再动手。
**收工三写**：① 台账自己那行改「状态 / 最后更新 / 产出路径」② `协同/交接/<任务ID>.md` 追加交接块（8 字段，模板 `协同/交接/_模板.md`，证据要可复核：路径 / 命令+退出码）③ `协同/会话索引/<agent>.jsonl` 追加一行（只存结论与指针，不搬对话原文、不写密钥）。
