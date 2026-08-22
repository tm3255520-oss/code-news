# code-news — 共享代码工作区（AGENTS.md）

> 面向所有接入 Agent（Codex / Claude Code / Harness / Hermes / DSH / OpenClaw）。知识中枢是 Obsidian vault，本仓库是共享代码/脚本/工具工作区。

## 本仓库是什么

- 多 Agent 共用的代码与工具仓：内容生产管线、MCP 服务器、工具注册表、测试。
- 本仓库是**管线/生产代码库，不是通用工作区**；日常调研/实验/草稿请到 `C:\Users\Administrator\Documents\agent-work`（通用工作区，入口见其 AGENTS.md）。
- 知识正文不长期存放于此；知识/产出回写 vault 白名单目录。

## 工作区分层（四层）

- 知识 → `D:\Obsidian Vault\obsidian Vault`（读写白名单见 vault 根 AGENTS.md 与 `智能体共享/01-总则与工作区划分.md`）
- 生产代码 → 本仓库（code-news）：管线工程、MCP、注册表、测试
- 通用工作区 → `C:\Users\Administrator\Documents\agent-work`：日常调研/实验/草稿/临时脚本
- 配置/技能/密钥 → 各 Agent 私有 home（`C:\.codex`、`C:\.claude`、`C:\.hermes`、`~/.dsh`、OpenClaw 容器）

## 启动须知

1. 能力路由先查 `config/tool_registry.json`（接口 → primary → fallback）。
2. 内容生产类任务入口：registry 的 monitor/analyzer/writer/humanizer/illustration/cover 等接口。
3. 正式发布能力默认关闭（publisher/xhs 为占位），绝不自动公开发布。
4. 开发前必读 vault `wiki/workflows/` 与 `wiki/postmortems/`（含铁律：确定性流程禁用 LLM）。
5. 测试入口：`python -m unittest discover -s tests -t .`。

## 约束

- 密钥/token 不放本仓库；登录态与凭据留在各 Agent 私有区。
- vault 不做 git；代码改动只在本仓库做 git。
- 进入规则：管线任务在本仓库做；日常杂活（调研/实验/草稿）去 `agent-work`，不混用。
- 新 Agent 接入：建 vault `安装清单/<agent>/_索引.md` → 登记 `智能体共享/03` → 更新总表 → registry 接入。
