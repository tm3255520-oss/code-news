# code-news — 共享代码工作区（AGENTS.md）

> 面向所有接入 Agent（Codex / Claude Code / Harness / Hermes / DSH / OpenClaw）。知识中枢是 Obsidian vault，本仓库是共享代码/脚本/工具工作区。

## 本仓库是什么

- 多 Agent 共用的代码与工具仓：内容生产管线、MCP 服务器、工具注册表、测试。
- 本仓库是**管线/生产代码库，不是通用工作区**；日常调研/实验/草稿请到 `C:\Users\Administrator\Documents\agent-work`（通用工作区，入口见其 AGENTS.md）。
- 知识正文不长期存放于此；知识/产出回写 vault 白名单目录。

## 工作区分层（四层）

- 知识 → `D:\Obsidian Vault\obsidian Vault`（读写白名单见 vault 根 AGENTS.md 与 `系统中枢/规则与权限/智能体共享/01-总则与工作区划分.md`）
- 生产代码 → 本仓库（code-news）：管线工程、MCP、注册表、测试
- 通用工作区 → `C:\Users\Administrator\Documents\agent-work`：日常调研/实验/草稿/临时脚本
- 配置/技能/密钥 → 各 Agent 私有 home（`C:\.codex`、`C:\.claude`、`C:\.hermes`、`~/.dsh`、OpenClaw 容器）

## 启动须知

1. 能力路由先查 `config/tool_registry.json`（接口 → primary → fallback）。**新建能力 / 新建脚本 /
   新接平台前，先跑 `python scripts/tool_inventory.py <关键词>` 盘点已有实现，按
   「直接调用 / 扩展合并 / 新建」三选一处置，并在提交信息里写明盘点结论**（复用守则 · 协作原则 4，
   规则全文：vault `系统中枢/规则与权限/智能体共享/06-复用守则.md`）。
2. 内容生产类任务入口：registry 的 monitor/analyzer/writer/humanizer/illustration/cover 等接口。
3. 正式发布能力默认关闭（publisher/xhs 为占位），绝不自动公开发布。
4. 开发前必读 vault `系统中枢/经验沉淀/工作流/` 与 `系统中枢/经验沉淀/复盘/`（含铁律：确定性流程禁用 LLM）。
5. 测试入口：`python -m unittest discover -s tests -t .`。

## 约束

- 密钥/token 不放本仓库；登录态与凭据留在各 Agent 私有区。
- vault 不做 git；代码改动只在本仓库做 git。
- 进入规则：管线任务在本仓库做；日常杂活（调研/实验/草稿）去 `agent-work`，不混用。
- 新 Agent 接入：建 vault `系统中枢/各Agent档案/<agent>/_索引.md` → 登记 `系统中枢/规则与权限/智能体共享/03-工具与调用.md` → 更新总表 → registry 接入。（2026-09-11 更正：旧前缀 `安装清单/` 已于 2026-09-06 按决策退役并入 `各Agent档案/`，不再新建）

## 协同协议：开工三查 / 收工三写（2026-09-30 起强制）

> 目的：多 Agent 共用一份任务态，止血「别人做了我不知道 / 重复做」。规则权威：vault `系统中枢/规则与权限/智能体共享/05-记忆协议.md` §六；用法：vault `系统中枢/协同/_使用说明.md`。

**开工三查**：① 查 `系统中枢/协同/任务台账.md` 有无同主题的 `进行中` / `已完成` 行（`进行中` 且非自己 → 不重复开工）② 命中就读 `系统中枢/协同/交接/<任务ID>.md` 最后一块 ③ 都没有就新建一行（状态=进行中、负责人=自己）再动手。
**收工三写**：① 台账自己那行改「状态 / 最后更新 / 产出路径」② `协同/交接/<任务ID>.md` 追加交接块（8 字段，模板 `协同/交接/_模板.md`，证据要可复核：路径 / 命令+退出码）③ `协同/会话索引/<agent>.jsonl` 追加一行（只存结论与指针，不搬对话原文、不写密钥）。
