# CLAUDE.md — code-news 工作区（Claude Code）

本文件是 Claude Code 在 code-news 的入口。总规范以仓库根 `AGENTS.md` 为准（两者内容一致）：Obsidian vault 是知识中枢，本仓库是共享代码工作区，能力路由查 `config/tool_registry.json`。

## 关键约定

- 本仓库是**管线/生产代码库**；日常调研/实验/草稿到 `C:\Users\Administrator\Documents\agent-work`（通用工作区，入口见其 AGENTS.md）。
- 工作区分层（四层）：知识 → `D:\Obsidian Vault\obsidian Vault`（读写白名单见 vault 根 AGENTS.md 与 `智能体共享/01-总则与工作区划分.md`）；生产代码 → 本仓库；通用工作区 → `agent-work`；配置/技能/密钥 → `C:\.claude`。
- 内容生产类任务先查 `config/tool_registry.json`；正式发布能力默认关闭（publisher/xhs 为占位）。
- 开发前必读 vault `wiki/workflows/` 与 `wiki/postmortems/`（铁律：确定性流程禁用 LLM）。
- vault 不做 git；代码改动只在本仓库做 git。
