# toolkit-mcp 实施验收报告

> 日期：2026-08-26 | 依据《多智能体共享工具接入方案》P0 全环节
> 原则：每一环节先测试、测试通过才进下一环节。

## 一、实施环节与测试结果

| 环节 | 内容 | 沙箱内测试 | 结果 |
|---|---|---|---|
| 阶段 0 | toolkit-mcp 骨架：配置 + 服务器 + .cmd + 分发脚本 + 单测 | py_compile / 18 单测 / selftest / 真实 stdio smoke | ✅ 全绿 |
| P0 接线 1 | 转录 → `transcribe_video`（video_collect.py） | 单测 + mnt 路径 selftest | ✅ |
| P0 接线 2 | 视频/TTS → `make_slideshow_video` + `make_voiceover` | 单测 + mnt 路径 selftest | ✅ |
| P0 接线 3 | 采集/监控 → B站 / 小红书 / 头条 / 抖音 / 素材 | 单测 + mnt 路径 selftest + 真实读抖音 JSON | ✅ |
| P0 新装 | MatrixMedia 矩媒（8 平台视频分发） | 安装脚本 + 接入文档（宿主机安装） | 📦 待宿主机 |
| 分发 | toolkit 注册到 Codex/Claude/Hermes/DSH | 真实 config.yaml 副本预演（插入正确/保留原有/幂等） | ✅ |

## 二、测试证据（沙箱）

```
# 单元测试：18 项全绿（配置/状态/执行/工具参数/JSON·YAML·TOML 幂等插入）
python3 -m unittest tests.scripts.test_mcp_toolkit -v   → Ran 18 tests ... OK

# stdio 真实握手（mcp<2 SDK）
python3 scripts/smoke_toolkit.py                        → [PASS] init/list/call OK

# 接线路径（mnt 模拟宿主机视角，8 工具全存在）
MCP_TOOLKIT_CONFIG=... python3 scripts/mcp_toolkit_server.py --selftest  → SELFTEST_RESULT: OK

# 抖音数据真实读取：10 个博主账号聚合成功
douyin_data_summary → accounts: 10

# 真实 config.yaml 副本分发预演
ensure_yaml → added(backup=...)；sessions/wenyan/toutiao 保留；幂等 ok；verify ok

# 全量回归：130 测试中 2 个沙箱 import 路径错误（与本次改动无关，宿主机 CI 无此问题）
```

## 三、交付物清单

| 文件 | 说明 |
|---|---|
| `config/mcp_toolkit.json` | 统一工具箱配置（8 工具：转录/视频/TTS/B站/素材/小红书/头条/抖音） |
| `scripts/mcp_toolkit_server.py` | stdio MCP 服务器（FastMCP），接线上述脚本为会话内工具 |
| `scripts/toolkit-mcp.cmd` | 统一入口启动器（各 Agent 共用） |
| `scripts/sync_agent_mcp.py` | 把 toolkit 注册到各 Agent 配置（幂等 + 备份 + verify + dry-run） |
| `scripts/smoke_toolkit.py` | stdio 握手 smoke |
| `scripts/install-matrixmedia.bat` | MatrixMedia 下载安装（宿主机双击） |
| `scripts/register-toolkit.bat` | 一键注册 toolkit 到 Codex/Claude/Hermes/DSH（宿主机双击） |
| `tests/scripts/test_mcp_toolkit.py` | 18 项单元测试 |
| `config/tool_registry.json` | 新增接口：toolkit_mcp / transcribe_skill / video_maker / video_publisher(占位) |
| `docs/MatrixMedia矩媒接入说明-2026-08-26.md` | 矩媒安装 + MCP 开启 + 接入步骤 |

## 四、宿主机待办（沙箱无法访问 Windows 环境，需你双击）

1. **注册 toolkit**：双击 `code-news\scripts\register-toolkit.bat`
   → 把 toolkit 写进 Codex / Claude Code / Hermes / DSH 的 MCP 配置（自动备份）→ 自检
   → 完全重启 Claude 桌面端 / Hermes / DSH
2. **安装 MatrixMedia**：双击 `code-news\scripts\install-matrixmedia.bat`
   → 运行矩媒 → 设置里开启 MCP Server → 记端口 → 按接入文档接入
3. **端到端验证**：`python scripts/smoke_toolkit.py` + `python scripts/smoke_mcp_servers.py`
   → 在任一智能体里调用 `toolkit_status`，应返回 8 工具可用状态

## 五、边界说明（诚实标注）

- **沙箱内已验证**：代码逻辑、协议握手、命令构造、配置幂等插入、接线路径存在性、抖音数据真实读取。
- **必须宿主机验证**：真实执行 `video_collect.py`（需 whisper/yt-dlp/NVIDIA key）、`edge-tts` 配音（需宿主机）、`xhs/toutiao_collect.py`（需 bsk 登录态）、MatrixMedia GUI + 平台登录态。
- 全量回归的 2 个 import 错误为沙箱 discover 路径问题（`run_daily_content_ops` 等脚本从 scripts/ 目录绝对导入），与本次改动无关。

## 六、后续维护（新增一个工具的标准流程）

1. 脚本进 `.hermes/scripts` 或 `code-news/.agents/skills/**/scripts`（git）；
2. `config/mcp_toolkit.json` 加条目（script / python / timeoutSec / notes）；
3. `scripts/mcp_toolkit_server.py` 加 `@mcp.tool()` 函数；
4. `tests/scripts/test_mcp_toolkit.py` 加参数/幂等用例 → 跑单测；
5. `config/tool_registry.json` 登记接口（如需）；
6. 各 Agent 无需改配置（toolkit 入口已固定）——`sync_agent_mcp.py --verify` 确认。
