# MatrixMedia 矩媒接入说明（唯一新装 · 8 平台视频矩阵分发）

> 日期：2026-08-26 | 依据《多智能体共享工具接入方案》P0「唯一新装」环节
> 背景：库内比对后，唯一明显缺口 = 视频批量分发。现有 `publish_douyin.py` / `publish_channels.py` / `publish_multi_platform.py` 只是雏形；MatrixMedia 提供 **GUI + CLI + HTTP API + 原生 MCP Server**，把抖音/小红书/头条/视频号/快手/B站 的网页发布流程统一封装。

## 一、安装（宿主机，双击）

1. 双击 `code-news\scripts\install-matrixmedia.bat`
2. 脚本自动：查 GitHub 最新 release → 下载 Windows 包 → 解压到 `D:\OpenClaw\MatrixMedia`
3. 运行 `D:\OpenClaw\MatrixMedia\MatrixMedia.exe`，按界面登录各目标平台（复用浏览器登录态）

> 若 `.bat` 下载失败（网络/代理），手动到 [GitHub releases](https://github.com/hanliang97/MatrixMedia/releases) 下载 Windows 包解压到同目录即可。

## 二、开启 MCP Server

1. 在矩媒「设置」里找到 **MCP Server** 开关并开启（默认开一个本地端口，如 `http://127.0.0.1:xxxx`）
2. 记下 endpoint（端口号以安装后的界面为准）

## 三、接入统一 MCP 工具箱（toolkit）

在 `code-news\config\mcp_toolkit.json` 的 `tools` 段新增/启用：

```json
"matrixmedia_publish": {
  "enabled": true,
  "group": "publish_video",
  "label": "8平台视频矩阵分发（MatrixMedia 矩媒）",
  "script": "",
  "mcp_url": "http://127.0.0.1:XXXX",
  "notes": "调用矩媒内置 MCP Server 批量分发视频；正式发布保留人工确认。"
}
```

> 具体调用方式（stdio 包装 或 HTTP SSE）以安装版本 README 为准；如矩媒 MCP 走 HTTP，则在各 Agent 的 MCP 配置里加 `"type": "http", "url": "..."`。

## 四、接入各智能体

- Codex：`C:\.codex\config.toml` 加 `[mcp_servers.matrixmedia]`（命令指向矩媒 MCP）
- Claude Code：`C:\Users\Administrator\.claude.json` 的 `mcpServers` 加 `matrixmedia` 条目
- Hermes：`C:\Users\Administrator\.hermes\config.yaml` 的 `mcp_servers` 段加 `matrixmedia`
- DSH：`~/.dsh/profiles/web/cordis.patch.yml`（WSL）
- OpenClaw：待 mcporter 启用后接入

## 五、验证

- 矩媒界面能看到各平台已登录
- 从任一智能体调用 `matrixmedia_publish`（或矩媒自带 MCP 工具），先把一个测试视频发到「草稿/定时」而非直接发布
- 确认 `smoke_mcp_servers.py` / `smoke_toolkit.py` 输出 OK

## 六、注意事项

1. **正式发布默认关闭**：首轮一律发「草稿」或「定时」，人工确认后再公开。
2. **登录态红线**：矩媒依赖各平台网页登录态，登录态失效需重新扫码；勿在无人值守时长时间批量发布。
3. **风控**：抖音/小红书/视频号批量发布有风控风险，控制频率（间隔 ≥ 数分钟）、避开同一 IP 短时高频。
4. **密钥**：矩媒登录态存在其自身配置目录，不进 vault；登记到 `安装清单/hermes/hermes相关 key汇总.md` 即可。
