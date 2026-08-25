# 给 Claude 开启 vault 写入权限（vault-writer MCP）

## 为什么需要这个

- **Hermes 能写 vault**：因为它跑在宿主机（Windows），直接写 `D:\Obsidian Vault\...`。
- **Claude 跑在 Linux 沙箱**：vault 挂载进来是**只读**的（Read-only file system），普通权限设置改不了——这是沙箱隔离设计。
- **解决办法**：架一个跑在宿主机上的 **MCP server**，Claude 通过它把文件写进 vault（和 Hermes 相同的效果，但走受控通道 + 白名单）。

## 已备好的文件

| 文件 | 作用 |
|---|---|
| `code-news/scripts/mcp_vault_writer_server.py` | MCP 服务本体（写/追加/列目录，白名单限 `内容生产`、`AI工具`、`wiki/decisions`、`raw`，防路径穿越） |
| `code-news/scripts/vault-writer-mcp.cmd` | 启动脚本（用 .hermes 的 venv python 跑） |

## 最后一步（需要你在桌面端操作，1 分钟）

在 **Claude 桌面端设置 → MCP / 连接器（Connectors）** 里添加一个 **stdio** MCP server：

- **名称**：`vault-writer`
- **命令**（Command）：`C:\Users\Administrator\Documents\code-news\scripts\vault-writer-mcp.cmd`

添加后重启会话（或刷新连接器）。之后 Claude 就能通过 `write_to_vault` 工具写 Obsidian vault 的白名单目录了。

> 若你的桌面端版本没有 MCP 管理界面，参考官方文档：https://claude.com/docs/third-party/claude-desktop/overview
> 若桌面端 MCP 是从 `.hermes/config.yaml` 的 `mcp_servers` 读取的，则在其中加一项：
> ```yaml
> vault-writer-mcp:
>   command: C:\Users\Administrator\Documents\code-news\scripts\vault-writer-mcp.cmd
>   enabled: true
>   timeout: 120
> ```

## 接入后验证（告诉我一声即可）

我调用 `write_to_vault("内容生产/热点监控/DSH候选池-20260825.md", ...)` 写入一条，你在 Obsidian 里能看到文件即成功。

## 安全说明

- 只开放白名单目录，不会写 vault 根、不会覆盖非白名单内容。
- 符合你们"vault 写入只走白名单、一个文件一个写者"的规范——只是把"写者"从 Hermes 扩展到 Claude（经 MCP）。
- 此 MCP 只在本机运行，无网络外发。
