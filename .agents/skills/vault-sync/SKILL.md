---
name: vault-sync
description: 把产出内容自动同步进 Obsidian vault——Claude 把该进 vault 的文件放进"待同步vault"目录（按 vault 相对路径组织），Hermes cron 每 10 分钟自动同步。触发词：存进 vault、同步到 Obsidian、写进知识库、归档到 vault。Do NOT use for：临时草稿、不需要进知识库的中间文件。
---

# vault 自动同步（Vault Sync）

把 Claude 的产出自动送进 Obsidian vault。沙箱对 vault 只读（架构限制），通过"待同步目录 + 宿主机 cron 自动同步"达成等效效果，**全自动、无需人工**。

## 机制

```
Claude 产出 → 写入 待同步vault/<vault相对路径>/xxx.md
            → Hermes cron 每 10 分钟跑 sync_to_vault.py（宿主机，确定性）
            → 文件自动出现在 D:\Obsidian Vault\obsidian Vault\<相对路径>
```

## 步骤

1. **判断**：这个产出是否"该进 vault"？
   - 是：数据表、决策文档、沉淀规则、监控报告、知识整理 → 继续。
   - 否：临时草稿、中间文件、仅供 code-news 用 → 放 code-news 即可，不碰 vault。
2. **定位目标目录**：按 vault 白名单选择相对路径：
   - `内容生产/`（选题/热点监控/草稿箱）、`AI工具/`（内容产品）、`raw/`
   - `系统中枢/经验沉淀/决策/`（跨 Agent 决策记录）
   - `系统中枢/经验沉淀/工作流/`（可复用硬规则）
   - 其他目录一律不放（sync 脚本会拦截）。
3. **写入**：写到 `C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\待同步vault\<相对路径>\<文件名>`。
   - 相对路径 = vault 里的路径，例如 `内容生产/热点监控/DSH候选池.md`。
   - 文件用 UTF-8；Markdown 表格优先（Obsidian 原生渲染）。
4. **确认**：自动同步已由 cron 处理（每 10 分钟），无需再让用户双击。若需即时同步，提示用户可手动双击 `sync-to-vault.bat`。

## 硬规则

- 只写白名单目录（`内容生产`、`AI工具`、`raw`、`系统中枢/经验沉淀/决策`、`系统中枢/经验沉淀/工作流`），禁止写 vault 根/其他。
- 文件名避免空格与特殊字符；目录名用 vault 现有结构。
- 与现有写者分工不冲突：此目录是"Claude 产出 → vault 白名单"的专用通道。

## 相关资源

- 同步脚本：`code-news/scripts/sync_to_vault.py`（也复制到 `.hermes/scripts/`）
- 手动触发：`code-news/sync-to-vault.bat`
- 自动注册：`register_vault_sync_cron.py`（Hermes cron，每 10 分钟）
- 说明：`research/dsh-std-video-analysis/同步到vault-使用说明.md`
