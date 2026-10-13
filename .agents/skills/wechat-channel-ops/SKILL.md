---
name: wechat-channel-ops
description: 微信公众号通道作业——检查通道健康、内容合规预检、发布前把关、通道故障排查。当用户说「微信通道」「公众号发一下」「检查公众号状态」「这条内容能发公众号吗」时使用。微信通道是 WorkBuddy 相对其它 Agent 的唯一差异化能力（6 个 Agent 中只有本机启用了 wechatmp）。**边界**：只管**通道**（账号健康 / 合规预检 / 发布执行 / 故障排查）；**写文章**走 wechat-article-writer、**改文案**走 wechat-content-optimizer、**搜文章**走 wechat-article-search、**提文章正文**走 wechat-article-extractor。判据：要「发出去 / 能不能发」归我，要「写 / 改 / 找文章」归上面几个。
agent_created: true
version: 1.0.1
tags: [wechat, 公众号, channel, compliance, 发布]
---

# 微信公众号通道作业

> 定位：本机 `settings.json` 的 `claw.channels.wechatmp` 已启用（webhook 模式），**6 个 Agent 里只有 WorkBuddy 接了这个通道**。
> 这是我最不可替代的能力——但也要清楚：**通道是接收/触达能力，内容生产主责在 Hermes**。

## 一、通道健康检查

### 配置真源
```
C:\Users\Administrator\.workbuddy-ai\settings.json  →  claw.channels.wechatmp
```
期望：`{"enabled": true, "connectionMode": "webhook"}`

### 运行态快照（实测可用）
```bash
grep -h "WECHATMP" "C:/Users/Administrator/.workbuddy/logs/$(date +%Y-%m-%d)/edge-sync.log"
```
期望输出：`[WECHATMP_SNAPSHOT_OK] enabled=true`
—— 这是**通道已起**的直接证据（2026-09-11 实测命中）。

### 同日志里的其它可用信号
```bash
grep -hE "INIT|WARN|ERROR" "C:/Users/Administrator/.workbuddy/logs/$(date +%Y-%m-%d)/edge-sync.log" | head -20
```
- `[INIT] configDir=... dbReady=true initFail=(none)` → 初始化正常
- `[WARN] startListeningCommands: no sdk, skip` → **已知且正常**，不是故障（Edge 扩展无 sdk 属预期）

### 排查顺序
1. `settings.json` 里 `enabled` 是不是 `true`
2. 当天日志有没有 `WECHATMP_SNAPSHOT_OK`
3. 日志日期目录是否存在（不存在 = 程序当天没起或日志轮转）
4. **仍不通 → 报告，别自己改配置**（见 `repair-gate`）

## 二、内容合规预检（发布前必做）

### 硬指标（据 `参考库/平台内容规则/公众号/2026新规/AI声明与原创度要求.md`）

| 项 | 要求 |
|---|---|
| 原创度 | **≥60%** |
| AI 声明 | **禁止纯 AI 生成不标注** → 必须声明 |
| 字数·短文 | ≥500 字（建议 800–1500） |
| 字数·中长文 | ≥1000 字（建议 1500–3000） |
| 字数·长文 | ≥2000 字（建议 3000–5000） |
| 搬运抄袭 | 禁止 |

### 规则依据位置（发之前对照，别凭记忆）
```
D:\Obsidian Vault\obsidian Vault\参考库\平台内容规则\公众号\
├── 规则规范/发布规则.md
├── 算法机制/推荐算法与流量池.md
├── 爆款要素/{标题高点击公式,内容结构公式}.md
├── 避坑指南/{违禁词清单,限流原因排查}.md
└── 2026新规/AI声明与原创度要求.md
```
**违禁词扫描**必须查 `避坑指南/违禁词清单.md`——这是硬红线。

### 预检清单
- [ ] 字数达标（按类型对照上表）
- [ ] 违禁词扫描通过（对照 `违禁词清单.md`）
- [ ] AI 声明已加（2026 新规要求）
- [ ] 原创度自评 ≥60%（非搬运、非纯 AI）
- [ ] 标题符合 `爆款要素/标题高点击公式.md`，且不越标题党红线
- [ ] 封面图就绪
- [ ] **正式发布前必须问用户**（见下方红线）

## 三、🔴 发布红线

`tool_registry.json` 明确：`publisher_skill` 的 **`formalPublishEnabled: false`**，xhs 同为占位。

**绝不自动公开发布**（治理规范铁律 7）。我的职责边界：
- ✅ 可以做：通道健康检查、内容合规预检、草稿准备、发布前把关、把结果报告给用户
- ❌ 不可做：自动点发布、绕过确认推送

## 四、内容生产 skill 在哪（别自己写一套）

公众号写作不是我的主责。需要写/优化内容时，**接线共享主实现**（junction 指向 `C:\.codex\skills`）：

| 需求 | 主实现 |
|---|---|
| 公众号写作 | `wechat-article-writer`（共享 hub） |
| 内容优化 | `wechat-content-optimizer`（共享 hub） |
| 文章提取 | `wechat-article-extractor`（共享 hub） |
| 去 AI 味 | `Humanizer-zh`（`C:\.codex\skills`，humanizer_skill 接口主实现） |

> 用 `mklink /J`，**不拷副本**——技能只有一份主实现。

## 五、待核实项（诚实标注，别当已知用）

以下**未实测**，需要时先验证再写进结论：
1. **webhook 回调地址与签名机制**——`connectionMode: webhook` 说明是回调式，但回调 URL、token 校验方式未在本地找到配置
2. **入站消息如何进入会话**——用户从公众号发来的消息如何转成任务，机制未确认
3. **出站发送能力**——是否有主动推送 API（非仅回复），未确认

> 需要这些能力时：**先报告，请用户确认机制或指定专用会话测试**（`repair-gate`），不要靠猜去调 API。

## 相关
- 治理规范：`vault/系统中枢/规则与权限/智能体共享/03-工具与调用.md`
- 我的档案：`vault/系统中枢/各Agent档案/workbuddy/_索引.md`
- 纪律：`repair-gate`（不自己修）、`execution-timeout-guard`（不傻等）
