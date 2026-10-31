# 一键同步到 Obsidian vault（Plan B）使用说明

## 背景

Claude 跑在沙箱，对 vault 是只读的（架构限制）；经过排查，当前环境的"插件/MCP"入口是 Hermes 桌面端的 UI 插件系统，无法给 Claude 挂 MCP。因此采用**宿主机一键同步**方案，效果等同、省事可靠。

## 原理

- Claude 把要进 Obsidian 的内容放到：
  `code-news/research/dsh-std-video-analysis/待同步vault/`
  里面的目录结构 = vault 相对路径（如 `内容生产/热点监控/xxx.md`）。
- 你**双击** `code-news\sync-to-vault.bat`，宿主机脚本 `sync_to_vault.py` 就把这些文件复制进 `D:\Obsidian Vault\obsidian Vault` 对应白名单目录。

## 用法

1. 打开文件夹 `C:\Users\Administrator\Documents\code-news`
2. 双击 **`sync-to-vault.bat`**
3. 看到 "Done" 即完成，去 Obsidian 刷新就能看到文件

## 白名单（脚本只允许这 4 个目录）

- `内容生产`、`AI工具`、`wiki/decisions`、`raw`
- 其他路径会被拦截，防止误写知识库。

## 当前已放好的内容

`待同步vault/内容生产/热点监控/` 下已有：
- DSH候选池.md / .csv（B站 爆款候选 Top15）
- DSH预测回测.md / .csv（15 条样本预测 vs 实际）

双击 .bat 后，这些就会出现在 Obsidian 的「内容生产/热点监控」里。

## 以后怎么用

Claude 每次产出"要进 vault"的内容，都会放进 `待同步vault/` 并告诉你"双击同步即可"。你随时双击一下就行；也可以让 Hermes 定时跑 `sync_to_vault.py` 实现全自动。
