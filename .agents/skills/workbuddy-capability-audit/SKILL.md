---
name: workbuddy-capability-audit
description: WorkBuddy 本机能力体检——清点已装 skill / 插件 / MCP / 连接器，并实测关键链路（浏览器操作、搜索、发布）是否真的可用。当用户说「排查一下要装什么 skill」「体检 WorkBuddy」「哪些能力没装」「浏览器/搜索能不能用」「换个新环境配一遍」时使用。**边界**：对象是 **WorkBuddy 本机能力**（skill / 插件 / MCP / 连接器 + 关键链路实测）；**Obsidian 中枢链路**走 obsidian-vault-health-check；**某条内容产线**走 content-pipeline-audit。
agent_created: true
version: 1.4.1
---

# WorkBuddy 能力体检

> 核心判据：**不要看"装没装"，要看"跑不跑得通"**。
> 插件装了 ≠ skill 已注册 ≠ CLI 已安装 ≠ 通道能连上。这四层要逐层验。

---

## 一、四层家底清点（只读）

| 层 | 路径 | 查什么 |
|---|---|---|
| 用户级 skill | `~/.workbuddy-ai/skills/<name>/SKILL.md` | 目录列表 + frontmatter 的 name/version |
| 已装插件 | `~/.workbuddy-ai/plugins/installed_plugins.json` | `plugins` 对象的所有 key + installPath + version |
| **插件启用开关** | `~/.workbuddy-ai/settings.json` → `enabledPlugins` | **每个插件 true/false。false = 不加载** |
| MCP 配置 | `~/.workbuddy-ai/mcp.json`（**不是** `.mcp.json`） | mcpServers 各项 |
| 连接器 | `~/.workbuddy-ai/connectors/default/mcp.json` | 每项是否 `"disabled": true` |
| **skill 可见性开关** | `~/.workbuddy-ai/settings.json` → `skillOverrides` | **哪些 skill 被降级/隐藏** —— 见下方专条 |

> ⚠️ **「安装」≠「启用」**。`installed_plugins.json` 有记录、cache 目录文件齐全、`plugin.json` 版本正确
> —— 这些**都不能证明插件被加载**。真正的开关是 `settings.json` 的 `enabledPlugins`。
> 排查「插件 skill 找不到」时，**第一步就看这里**，别先去翻文件结构。

**skill 可见性四态（`skillOverrides`）—— 清点 skill 时「必须」查这一层**

`skillOverrides` 是官方支持的覆盖机制，**不改 SKILL.md 就能控制单个 skill 的可见性**
（官方定位原文：「适用于**你不方便改动的 Skill**」）。
所以 **skills 目录里数出 50 个（2026-09-16 实测）≠ 50 个都能被模型自动调用** —— 少查这层，"家底"就是虚的。

| 值 | 对模型可见 | 在 `/` 菜单 | 含义 |
|---|---|---|---|
| `on` | 名称 + 描述 | 是 | **未列出的 skill 默认此态** |
| `name-only` | 仅名称 | 是 | 折叠描述，省 context 预算 |
| `user-invocable-only` | **隐藏** | 是 | 不进模型清单；**按名调用仍放行** |
| `off` | 隐藏 | 隐藏 | 硬禁用 → 按名调用报 `Skill "X" is disabled via skillOverrides...` |

```bash
# 看当前被覆盖了哪些（空 {} = 全部 on）
python -c "import json;print(json.load(open(r'C:/Users/Administrator/.workbuddy-ai/settings.json'))['skillOverrides'])"
```

- **生效层级**：`PROJECT_LOCAL(.codebuddy/settings.local.json) > PROJECT > USER`；高优先级按 skill 名覆盖低优先级。
- **plugin 类 skill 不受此机制影响**（走 `/plugin` 管理，`/skills` 里显示 `locked by plugin`）；
  **接线（软链/junction）进来的属于普通用户级 skill，受控** ✓
- **用途（2026-09-15 实战）**：处理「**接线/第三方 skill 描述重叠**」的正路 ——
  把抢触发词的那条设为 `user-invocable-only`，**降优先级但不丢能力**，且不碰别人的资产。
  详见 `技能体系地图` §2.3 与案例 10。
- ⚠️ **`settings.json` 含明文凭据**（`claw.users.*.channels` 下 `botToken` / `appSecret`）→
  **它的备份不能放 vault**（违反「vault 不放密钥」），放 `%TEMP%` 之类非 vault 位置。
- ⚠️ **数入口先过滤「非目录项」**（2026-09-15 踩到）：`skills/` 顶层混着 3 个**隐藏的迁移标记文件**，
  枚举时会被一起数进来 —— 2026-09-15 实测机器枚举 = **34**、真入口 **31**（= 12 实体目录 + 19 接线 + **3 文件**）；
  **2026-09-16 实测枚举 = 53、真入口 50**（= **13 实体目录 + 37 接线** + **3 文件**）：
  `.disable_to_model_invocation_migration.json`、`.model_invocation_to_override_migration.json`、`_bm_skillid_migration.json`。
  **判据**：先按 `os.path.isdir()` / `LinkType` 分类，**再**计数；直接 `listdir` 计数必然虚高。
- 📌 **这 3 个文件本身是 `skillOverrides` 的「官方血统」证据**：产品自己做过两步迁移
  「SKILL.md frontmatter `disable-model-invocation` → `model_invocation` → settings `skillOverrides`」
  （本机标记：2026-09-02 23:04 两步迁移，`scanned:0` = 本机无历史遗留；BuiltinMarket skillId 迁移 2026-09-10 17:08）。
  → 说明「**别改别人的 SKILL.md，用 settings 覆盖**」**不是野路子，是产品设计的方向**。

**唯一硬证据：CLI host 日志。** 判断插件到底有没有被加载，只看这一个文件：

```bash
L=$(ls -t ~/.workbuddy-ai/logs/$(date +%Y-%m-%d)/__workbuddy_cli_host__-*.log | head -1)
grep -n "Loading plugin components for\|PluginsProductProvider.provide\|active plugins refreshed" "$L"
```

- `[PluginsProductProvider.provide] active=N, ids=[…]` —— **当前实际生效的插件全集**，拿它跟 `enabledPlugins` 对表
- 有 `Loading plugin components for <插件>` 才算进了加载流程；**一条都没有 = 压根没纳入范围**（多半是 `enabledPlugins: false`）
- 有 `Loading` 但没有对应的 `Loaded plugin components for … : … skill(s)` = 加载了但没解析出 skill（结构/`SKILL.md` 问题）

可用市场（看能补装什么）：

```bash
ls -1 ~/.workbuddy-ai/plugins/marketplaces/codebuddy-plugins-official/plugins/
ls -1 ~/.workbuddy-ai/connectors-marketplace/connectors/
```

**第五层：共享 skill 池（最容易漏，价值最高）**

本机有多个 Agent 共用一套 skill 池，WorkBuddy 只挂了其中一部分。**做体检必须比对，否则会漏掉一堆现成能力。**

```bash
# WorkBuddy 实际挂了什么（含软链）
ls -la ~/.workbuddy-ai/skills
# 上游池子各有多少
for d in ~/.codex/skills ~/.agents/skills ~/Documents/code-news/.agents/skills; do
  echo "$d: $(ls -1 "$d" 2>/dev/null | grep -v '^\.system$' | wc -l)"
done
```

判据：**`ls -la ~/.workbuddy-ai/skills` 里 `->` 指向别处的就是共享进来的**。
差集 = 「别的 Agent 有、WorkBuddy 没有」的候选。
注意 `~/.codex/skills` 本身常是**软链枢纽**（指向 `.agents/skills` 等），所以 `find` 不穿透、要用 `ls -la` 看链接目标。

**建链与验真方法见案例 9**（`MSYS=winsymlinks:nativestrict` + `fsutil` 取 tag 值）。

**本机已完成（2026-09-14 首批 13 条）**：已挂 13 条真软链 ——
`guizang-ppt-skill` / `note-transcription` / `tavily-search` / `tavily-research` / `firecrawl-search`
（以上来自 `~/.codex/skills`）、
`wechat-article-search` / `wechat-article-extractor` / `wechat-article-writer` / `wechat-content-optimizer` / `youtube-transcript`
（以上来自 `~/.agents/skills`）、
`xiaohongshu-skills` / `viral-video-breakdown` / `viral-video-replicate`
（以上来自 `Documents/code-news/.agents/skills`）。

**2026-09-16 第二批 19 条：视频链整族补齐**（用户批准后逐项挂、逐项验，全部通过）——
`hyperframes` / `hyperframes-cli` / `hyperframes-core` / `hyperframes-registry`（基础设施）、
`hyperframes-animation` / `hyperframes-keyframes` / `hyperframes-creative` / `hyperframes-media` / `media-use`（领域原子）、
`faceless-explainer` / `embedded-captions` / `motion-graphics` / `talking-head-recut` / `slideshow` /
`general-video` / `music-to-video` / `website-to-video` / `product-launch-video` / `pr-to-video`（工作流）。
→ 技能总数 31 → 50。**整族一起挂**是关键：这些技能互相用 `../兄弟技能/` 相对路径引用，缺一个就断链。
→ 工具留在工位：`_脚本/mount-skill-link.js`（`--link` / `--check` / `--unlink` / `--list`），
  比手工 `ln -s` 稳，且天生带回滚。


排除项（别推荐）：
- **AI 文生视频 / 图生视频** —— 本产品不支持，别去找这类 skill
- **⚠️ 但「HTML 渲染成片」类要挂（2026-09-16 更正）**：HyperFrames 系
  （`hyperframes*` / `faceless-explainer` / `embedded-captions` / `motion-graphics` / `talking-head-recut` /
  `slideshow` / `general-video` / `music-to-video` / `website-to-video` / `product-launch-video` / `pr-to-video` / `media-use`）
  是**代码型渲染**（HTML→MP4），不经过生成模型，**不在限制范围内**，已全部挂载。
  原登记写「视频类一律不挂」是**把两类混为一谈的错判**。
  判别口径：**靠模型凭空生成画面 → 不挂；靠 HTML/CSS/ffmpeg 把已有内容渲染成片 → 挂。**
- 给别的 Agent 专用机制（如 `vault-sync` 是 Claude 沙箱只读时的等效方案，WorkBuddy 对 vault 有直写权限，用不上）
- 与内置/现有重复的（`find-skills` / `find-mcps`；`obsidian-health-check` 与现有 `obsidian-vault-health-check` 重复）
- 需外部授权但用不到的（`figma` 要 Figma 账号；`remotion-to-hyperframes` 只做 Remotion 迁移）


---

## 二、关键链路实测（重点）

### 搜索链路

| 工具 | 怎么验 |
|---|---|
| WebSearch（内置） | 直接发一次真实查询，看是否返回结果 |
| WebFetch（内置） | 已知 URL 抓一次 |
| web-access 的 Jina | `r.jina.ai/<url>`（不带 http 前缀） |

### 浏览器链路（三通道，逐个验）

**通道 1：agent-browser CLI**

```bash
which agent-browser            # 常见位置 D:\pi-agent（npm prefix）
agent-browser --version
timeout 130 agent-browser open https://example.com
```

判据：`--version` 通过 **不等于** 可用。`open` 静默卡死 = daemon 起不来。

**通道 2：web-access CDP**

```bash
cat "$LOCALAPPDATA/Google/Chrome/User Data/DevToolsActivePort"   # 取端口
node -e "fetch('http://127.0.0.1:<port>/json/version').then(r=>r.text()).then(t=>console.log(r.status,t.slice(0,200)))"
```

判据：
- TCP 通 + `/json/version` 返回 JSON → 可用
- TCP 通 + **404** → Chrome 安全限制，需用户在 `chrome://inspect/#remote-debugging` 勾选 Allow remote debugging
- 无响应 → Chrome 未开调试

**通道 3：playwright-cli** —— 与通道 1 同源，验法相同

---

## 三、已踩过的坑（照抄即可，别重复踩）

| 坑 | 真相 |
|---|---|
| `check-deps.mjs` 报 `chrome: ok` | **只做 TCP connect**，端口通就判 ok，CDP 可能实际是 404。不可信 |
| `agent-browser open` 卡死 | 先查 `~/.agent-browser/default.pid` 里的 PID 是否还活着；死了就清 pid/port/stream（**先备份**）。若清理后仍卡死 → 是 daemon 启动本身失败 |
| 插件装了但 skill 不在可用列表 | 插件 skill 名 ≠ 插件名。如 `agent-browser` 插件 v1.0.0 的 skill 名是 `Browser Automation`（路径 `skills/browser-automation/SKILL.md`） |
| `setup.sh` 不装东西 | agent-browser 插件 v1.0.0 的 setup.sh 在 Windows（msys/cygwin/WINDIR）**直接 exit 0**，SessionStart hook 空跑 |
| npm 全局包查不到 | 先 `npm config get prefix`。本机是 `D:\pi-agent`，不是默认的 `AppData\Roaming\npm` |
| 连接器"配了"≠"能用" | `connectors/default/mcp.json` 里默认全是 `"disabled": true` |

---

## 四、纪律（必须遵守）

1. **默认只报告，不动手**（见 `repair-gate`）。发现故障 → 出报告：现象 / 位置 / 证据 / 根因判断 / 影响面 / 建议。
2. 只读探测随便做；**任何写操作（删状态文件、装包、改配置）先报告等确认**。
3. 备份先行：动 `~/.agent-browser/`、`~/.workbuddy-ai/` 下任何状态文件前，先 `cp -r` 到工位。
4. 长命令用 `timeout` 包住（见 `execution-timeout-guard`）。**慢 ≠ 死，沉默 = 死**；超 10 分钟无新进展必须停。

---

## 五、产出模板

报告落工位：`_过程稿/YYYY-MM-DD-<任务简称>/能力体检报告-YYYY-MM-DD.md`

必含：
- 结论摘要表（能力 / 满足与否 / 一句话）
- 每条链路的**实测命令 + 原始输出**
- 根因判断（**明确标注是判断**）
- 缺口清单（分优先级）
- 建议动作（标注哪些需用户手动、哪些需专用会话）

---

## 六、实战案例（2026-09-14，本机 Chrome 150.0.7871.187）

### 案例 1：`/json/*` 全 404 —— 这是设计行为，不是故障

**现象**：Chrome 在跑、`DevToolsActivePort` 存在、端口 LISTENING，但 `/json/version`、`/json/list` 全部 **HTTP 404 body 长度 0**。

**真相**：**Chrome 144+ 起，`chrome://inspect` 的远程调试不再提供传统 HTTP 端点**。端口只接受带 UUID 路径的 WebSocket。

**推论**：不要拿 `/json/version` 当连通性判据。**看 `DevToolsActivePort` 第二行有没有 UUID 路径**才是。

**web-access 已适配**：`cdp-proxy.mjs` 第 73-77 行读第二行拿 `wsPath`，第 107-110 行拼 `ws://127.0.0.1:PORT/devtools/browser/UUID`，绕过 `/json`。

### 案例 2：真正的杀手是「连接槽竞争」

**现象**：proxy 起得来（`/health` 返回 `status:ok`），但 `connected:false`，`/targets` 挂起；日志报 `Received network error or non-101 status code`。

**根因**：`check-deps.mjs` 用 `startProxyDetached()` 启动的 proxy（`detached:true` + `unref()`）**不会随父进程退出**。若再手工启动一个 proxy，两个实例抢同一条 browser-level 连接槽，后到者被拒。

**处置顺序**：
1. `netstat -ano | grep :3456` 找 PID，`netstat -ano | grep :<chromePort>` 看有无多余 ESTABLISHED
2. **杀掉全部 proxy**，等 40 秒让 Chrome 释放
3. 只启动**唯一一个** proxy
4. 发一次 `/targets` 触发连接 —— **Chrome 可能弹授权框，必须让用户点 Allow**

**关键教训**：`check-deps.mjs` 报 `proxy: ready` 后就别再手工启 proxy 了。

### 案例 3：agent-browser 卡死 —— 版本错配

**现象**：`agent-browser close` 正常，但 `open` 静默卡死（无 stdout/stderr），`--debug` 也无输出。

**根因**：**CLI 版本与 Chromium 运行时版本错配**。

**修复**：
```bash
npm install -g agent-browser@latest    # 0.32.3 → 0.37.1
agent-browser install                  # 下载匹配的 Chrome（147 → 153）
```

**注意**：
- `agent-browser --version` 通过 **不代表**可用，`close` 能用也不代表 `open` 能用
- 0.37.1 声明 `node >= 24`，npm 会报 `EBADENGINE`；但**实测 Node 22 可用，Node 25 反而卡死** → 别急着按警告换 Node
- 排查时把输出**重定向到文件**再读，别用 `| head`（可能触发 SIGPIPE 造成假故障）

### 案例 4：npm 全局包找不到

`which agent-browser` 可能指向非默认位置。本机 npm prefix = `D:\pi-agent`（不是 `AppData\Roaming\npm`）。**先 `npm config get prefix`**。

### 案例 5：「插件装了、升级了、重启了，skill 还是找不到」（2026-09-14 21:26 定案）

**现象**：`agent-browser` 插件 cache 文件齐全、`installed_plugins.json` 指向 1.3.0、`plugin.json` 版本对、重启过——`Skill(agent-browser)` 依然 `Can not find skill`。

**走过的弯路（都白费）**：对比 `1.0.0` vs `1.3.0` 目录结构、怀疑根目录 `SKILL.md` 不合规范、查 `.in_use` 标记、查 `orphaned_at`、查市场源包结构、查插件注册表。
—— **全部无关**。实测证明**根目录放 `SKILL.md` 完全合法**（26 个已注册插件都这么干）。

**真因（一行）**：`~/.workbuddy-ai/settings.json` → `enabledPlugins["agent-browser@codebuddy-plugins-official"] = false`。
禁用状态下插件**根本不进加载流程**，日志里连一条 `Loading plugin components for agent-browser` 都没有。

**定位手法（照抄）**：

```bash
# 1. 看实际生效的插件全集
grep "PluginsProductProvider.provide" <cli-host.log> | tail -1     # → active=6, ids=[…]
# 2. 看启用开关
node -e "console.log(JSON.parse(require('fs').readFileSync(process.env.USERPROFILE+'/.workbuddy-ai/settings.json','utf8')).enabledPlugins)"
# 3. 对表 —— 两边差集就是「装了但没启用」的
```

**教训**：
1. **先查启用开关，再查文件结构**。开关是 5 秒钟的事，结构对比是半小时的事。
2. **`active=N` 是唯一事实来源**，别用 `installed_plugins.json` 的记录数（本机 43 条记录 vs 实际 active 6）。
3. 产品配置 `~/.workbuddy-ai/cache/acc-product-config-v3.json` 的 `builtInMarketPlugins`（含 `autoEnable`）
   只是**期望值**，不是**实际值**。声明里若有一个插件在实际市场包里不存在，整个
   `install-builtin-market-plugins` 阶段会 `failed` → `reconcile-configured-plugins` 标 `degraded`。
   ⚠️ **注意：此时改 `enabledPlugins` 兜底是无效的** —— 反编译确认 `installBuiltInMarketPlugins()`
   的执行顺序是「**先 `marketplace.getPlugin(name)` 查找并抛错，后判断是否启用**」，禁用状态压根没参与查找。
   详见案例 8。**这种情况本地无解，只能报告厂商**（`runRecoverableStage` 会收集错误后继续，功能影响为零）。

### 案例 6：验证浏览器能力时**踩坏了产线**（2026-09-14 21:01 / 21:13）

**现象**：Hermes 的「知乎收藏采集」「今日头条收藏采集」各失败一次：
`⚠️ bsk: error: multiple browsers are online` / `❌ session 启动失败`。

**根因**：采集脚本依赖「**唯一浏览器在线**」。为验证 `agent-browser` 而启动它自带的 Chrome（v153）
→ 同时有两个浏览器在线 → 采集脚本无法确定连哪个 → 失败。
时间点与验证操作吻合。

**规则**：
1. 跑 `agent-browser` / CDP 相关验证**之前**，先想一下会不会撞上本机定时采集（本机采集每 2 小时一次，整点前后）。
2. 验证完**必须** `agent-browser close`，并确认 `~/.agent-browser/default.pid` 已消失。
3. 排查「采集失败」时，`multiple browsers are online` 优先怀疑**有别的自动化留下的浏览器实例**，而不是脚本本身。

### 案例 7：判断「产线哑没哑」不能只看产出目录（2026-09-14 21:55）

**反面教训**：我看到 `raw/articles/zhihu` 最新文件是 2026-08-02，就判断「摄入链路哑了」——**错的**。

**正确判据**（三步，缺一不可）：

```bash
# ① cron 活着吗 —— 看心跳，不看目录
ls -la ~/.hermes/cron/ticker_heartbeat ~/.hermes/cron/ticker_last_success   # mtime 是当下 = 活着

# ② 任务还在吗、启没启用
node -e "const j=require('C:/Users/Administrator/.hermes/cron/jobs.json');(j.jobs||j).forEach(t=>console.log((t.enabled!==false?'[on] ':'[off] ')+(t.name||'')))"

# ③ 逐次看实际结果 —— 关键！output/<jobId>/ 下每个文件是一次执行
ls -1t ~/.hermes/cron/output/<jobId> | head -12
grep -o "❌.*\|✅.*" ~/.hermes/cron/output/<jobId>/<file> | tail -1
```

**本机实测结论**：头条/知乎采集最近 10~12 次里 **9~11 次是成功的**，结果全是「✅ 无新文章，跳过」。
→ `raw/` 停更的真因是**收藏夹没新增**（增量采集无货可采），不是链路断。

**一句话**：产出目录空 ≠ 链路哑。**要看链路最近有没有「跑」，而不是目录里有没有「货」。**

### 案例 8：判断「插件/市场里有没有某个东西」——**三层模型，禁止以清单 JSON 为据**（2026-09-14 22:45 定案）

**这是本 skill 最重要的一条方法论。** 同一个问题我前后给了三个不同答案，前两个都错在**只看清单、没看实物**。

**三层必须分清，三者可以不一致：**

| 层 | 载体 | 作用 |
|---|---|---|
| **声明层** | 产品配置 `builtInMarketPlugins`（CDN 下发，缓存在 `~/.workbuddy-ai/cache/acc-product-config-v3.json`） | 客户端**会去装**哪些插件 |
| **货架层** | 市场 listing JSON（`builtInMarketplaces.<name>.metaUrl`，如 `…/cb_teams_marketplace.json`） | UI **展示**什么、插件元数据 |
| **货箱层** | 市场内容包 zip（`builtInMarketplaces.<name>.url`） | **实际投递**的插件实现文件 |

**本机实例**：`finance-data` 在**声明层有**（`autoEnable:true`）、在**货架层有**（v1.5.0），
但**货箱层没有** —— 已装版 `de338e37` 与最新版 `6a7a8beb` 两版 zip 的 `marketplace.json` **字节级完全相同**
（sha256 一致，29 插件），`plugins/` 下 30 个子目录里**没有 finance-data**。
→ 每次启动必然报 `Plugin finance-data@cb_teams_marketplace is not found in its declared marketplace`。

**正确验证方法（照抄，别省）**：

```bash
# ① 拿下载 URL（来自产品配置，不是 listing！）
node -e "const c=require('C:/Users/Administrator/.workbuddy-ai/cache/acc-product-config-v3.json');console.log(JSON.stringify(c.builtInMarketplaces,null,1))"
# ② 拿远端版本号
curl -s https://download.codebuddy.cn/plugin-marketplace/version/cb_teams_marketplace.txt
# ③ 下载「已装版」与「最新版」两个 zip，解压，逐文件 diff
curl -s -o old.zip "<已装版url>"; curl -s -o new.zip "…-<版本号>.zip"
unzip -q -o old.zip -d old; unzip -q -o new.zip -d new
diff -rq old new | wc -l
node -e "const m=require('./new/.codebuddy-plugin/marketplace.json');console.log(m.plugins.length, m.plugins.some(p=>p.name==='目标名'))"
```

**⚠️ 三条硬规矩**：

1. **禁止以 listing JSON 为依据**下「有没有」的结论。**看清单不算验证，要看实物。**
2. **HTTP HEAD 可能全返 `000`（被拦）**，判断 URL 存在性要用 `curl -s -o /dev/null -w "%{http_code}"`（GET），
   或直接下载后看文件头是不是 `PK`。
3. **`metaUrl` 在 CLI bundle 里零引用** —— 改它/看它都不影响客户端行为。客户端只认 `builtInMarketplaces.<name>.url`。

**顺带发现的第二个产品缺陷**：`version/*.txt` 已推进到新版本号，但产品配置里 `url` 字段**仍钉在旧包** →
客户端会认为「需要更新」却每次都下载回同一旧货箱 → **市场内容永远停在旧版**（本机两版共 104 个差异文件，
涉及 18 个插件，含在用的 `sheetagent`）。

**报错时先看日志原文**：`~/.workbuddy-ai/logs/<date>/` 下搜插件名，**报错时间点直接给出复现频率**
（本机 14:14:48 / 14:14:55 / 14:15:15 / 14:23:15 / 14:58:28 = 每次启动都报）。

### 案例 9：把别的 Agent 的 skill 软链挂进来（Windows 特有坑）

**建链（两条路，优先用 Node）**：

```bash
# 路 A（推荐）：Node 原生 symlink，绕开 MSYS，天然带回滚与验证
node "<工位>/_脚本/mount-skill-link.js" --link <skill名>

# 路 B：Git Bash（必须带 MSYS，否则 ln -s 会退化成复制）
export MSYS=winsymlinks:nativestrict
ln -s "/c/Users/Administrator/.codex/skills/xxx" ~/.workbuddy-ai/skills/xxx
# ⚠️ Git Bash 会假报 "No such file or directory"，退出码非 0 —— 其实建成功了，别信
```

⚠️ **源侧若本身是软链，要取真身再指**（`.codex/skills/hyperframes` 就是指向 `.agents/skills/hyperframes` 的软链）
→ 用 `fs.realpathSync()` 解出真身，避免链套链。

**验真判据 —— 不能用中文关键词**（`fsutil` 输出是 GBK，`grep "符号链接"` 必然失配），要取 tag 值：

```bash
for n in ~/.workbuddy-ai/skills/*; do
  [ -L "$n" ] || continue
  tag=$(fsutil reparsepoint query "$n" 2>/dev/null | grep -oE '0xa[0-9a-f]{7}' | head -1)
  echo "$tag  $(basename "$n")  -> $(readlink "$n")"
done
#  0xa000000c = IO_REPARSE_TAG_SYMLINK     → 真符号链接 ✅
#  0xa0000003 = IO_REPARSE_TAG_MOUNT_POINT → junction（不是我们要的）
```

**验收四项**：tag=`0xa000000c`、size=0、`SKILL.md` 可读、frontmatter `name` 与目录名一致。

**不要挂的**：`find-skills`/`find-mcps`（与内置重复）、给别的 Agent 专用的机制（如 `vault-sync`）、
**AI 文生视频/图生视频类**（本产品不支持）。
⚠️ **但 HTML 渲染成片类要挂** —— 见上方「排除项」的更正说明，别把两类混为一谈。

---

### 案例 10：处理「触发词重叠」别去改别人的 skill —— 用 `skillOverrides`（2026-09-15 定案）

**场景**：MOC 列出 7 组「同一句话会被 2 个以上 skill 抢」的重叠。其中联网簇 4 个
（`web-access` 属第三方 + `firecrawl-search` / `tavily-search` / `tavily-research` 属接线）**全部不可改** ——
改描述等于改别人的主实现。

**走过的弯路**：一开始把 `skillOverrides` 当成「**禁用**」的同义词，觉得代价太大（禁用 = 丢能力），
只敢把它列为"下一步"，结果 7 组**悬了很久没结论**。

**正解**：去**产品内置文档**取证（`resources/app.asar.unpacked/cli/dist/web-ui/docs/cn/cli/skills.md`），
发现它是**四态** —— `on` / `name-only` / **`user-invocable-only`** / `off`。
`user-invocable-only` = 「对模型隐藏、按名调用仍放行」→ **降优先级而不丢能力**，且**只改本机配置**。
→「不可改侧」的重叠从此有了正路。

**判据（关键：别按状态字面下结论）**：

| skill | 实测 | 结论 |
|---|---|---|
| `tavily-search` / `tavily-research` | `which tvly` **找不到**；无 `TAVILY_API_KEY` | **不可用** → 自动触发必失败 → 设 `user-invocable-only` |
| `firecrawl-search` | CLI 在（v1.23.1）。⚠️ `firecrawl --status` 报 `● Not authenticated`，**但实跑 `firecrawl search "obsidian"` 返回了真实结果** | **可用** → 保持 `on` |
| `web-access` | CDP 直连本机 Chrome | **可用** → 保持 `on` |

> ⚠️ **本案例最大的坑**：`firecrawl --status` 说 `Not authenticated`，差点据此判它不可用并降级 ——
> 那会把**唯一能用的轻量搜索入口**也一起关掉。**状态字面 ≠ 实际可用，必须实跑一次。**

**改法（最小替换 + 逐项校验）**：

1. 备份 `settings.json` 到 **`%TEMP%`**（⚠️ **不能进 vault** —— 该文件含明文凭据）；
2. 只替换 `"skillOverrides": {}` 这一处锚点，**不重序列化**（重排会动全文件）；
3. 校验 12 项：JSON 可解析 / **差异键仅 `skillOverrides`** / 值属四态 /
   **明文凭据（botToken、appSecret）逐项未变** / 行尾保持 / 锚点前逐字节相同。

**回滚**：删掉那几行（或改回 `"on"`）即可 —— 未列出的 skill 视为 `on`。

**顺带一条**：做这类「更正登记」时，**校验断言别用裸子串**。断言「旧表述已清除」会误报 ——
因为**你刚写的更正说明里会故意引用旧表述**（如「原登记写『保持关闭（3）』…」）。
断言要**限定结构位置**（如表格单元格 `| 保持关闭（3） |`）。

---

### 案例 11：批量挂技能软链的「逐项验证」纪律（2026-09-16 定案，19 项零失败）

**场景**：用户批准挂 19 个视频类技能，并明确要求「**逐项进行，每项改后都要测，通过才往下走，避免错误累积难排查**」。
这条要求直接决定了两件事：**验证必须自动化且判据统一**，**必须能回滚**。

**三类判据（缺一不可，光看第一条会被骗）**：

| 层 | 判据 | 为什么必须 |
|---|---|---|
| 文件系统 | `lstatSync().isSymbolicLink()` 为真、`readlinkSync` 指向预期真身、reparse tag `0xa000000c` | 防 `ln -s` 退化成复制；防 junction（`0xa0000003`）冒充 |
| **内容** | `SKILL.md` 可读 + 字节一致 + **整棵目录树递归一致**（文件/目录/子链接逐个比对） | 链接对了不代表目标对；`embedded-captions` 有 144 个文件，只测 SKILL.md 会漏 |
| **识别** | frontmatter `name` 与目录名一致；**与全部已挂技能无重名** | name 不一致 → 模型调不到；重名 → 两个技能抢同一触发词 |

**关键结论：软链新增技能「不需要重启会话」，当场生效。**
本机无任何 skills 索引/manifest 文件（全盘找过），识别是**目录扫描 + 按需解析**。
`hyperframes` 建链后立刻 `Skill(hyperframes)` 就命中，base dir 指向新链接。
→ 所以不需要"先挂完再重启验证"，**可以边挂边验**，这正是逐项推进可行的前提。

**「整族一起挂」不是偷懒，是必须**：
这批技能互相用 `../hyperframes-animation/rules/`、`../hyperframes-creative/frame-presets/` 这类**兄弟目录相对路径**引用。
挂一半 → 另一半路径解析失败且**不一定报错**。
验收时要专门跑一次兄弟路径可达性检查（本机 5 条全过）。

**逐项验证不要用 Skill 工具测全部项** —— `talking-head-recut` 的 SKILL.md 有 64KB、`embedded-captions` 32KB，
20 项全用 Skill 工具测会把上下文撑爆。
**正解：Tier A 用脚本测全部（文件系统+内容+识别），Tier B 只对旗舰项抽查 Skill 工具**（本机抽 3 项）。

**四个 Windows 坑（本次实测）**：

| 坑 | 真相 |
|---|---|
| `ln -s` 报 `No such file or directory` | **假报**。链其实建成了（`ls -ld` 能看到 `->`）。退出码 1 不可信 |
| **Node 不认 MSYS 的 `/c/` 路径** | Node 是原生 Windows 进程。传路径给 node 必须 `C:\...` 或 `C:/...`；传 `/c/...` 会变成 `C:\c\...` 找不到 |
| **`tar` 把 `C:` 当远程主机** | `tar: Cannot connect to C: resolve failed` → 必须加 `--force-local`。备份 skills 目录时必踩 |
| **Windows 原生 `Get-ChildItem` 解析软链** | 比 MSYS 更权威（WorkBuddy 是 Windows 程序）。可用 Node 的 `fs.realpathSync` 等效验证 |

**备份要点**：`cp -a` **不能保真软链**（MSYS 未开 nativestrict 时报错、链丢失）。
正解用 `tar --force-local -czf`（本机 32 条目零缺失、19 条软链保真、仅 131KB）。
验归档要数**四项**：顶层条目数、软链条数（`tar -tvzf | grep -c '^l'`）、隐藏文件在不在、抽样命中。

**别忘外部依赖**：技能挂上 ≠ 能用。`pr-to-video` 依赖 `gh` CLI（本机未装）；
hyperframes 视频链依赖 `whisper-cpp`（转录）、TTS Kokoro（配音）、MusicGen（配乐）——**本机三项全缺**。
挂完必须跑一次 `hyperframes doctor --json`（gate 看 `.ok`，命令**永远 exit 0** 不可信）把缺口一次列全。

**中文视频的隐形杀手**：HyperFrames 里中文字体**必须显式写 `@font-face`**，否则 `lint` 直接报
`font_family_without_font_face`，且渲染掉字体。系统字体用 `src: local("字体名")` 即可通过，不需要字体文件。

---

### 案例 12：升级全局 npm 包前，必须先查「共享依赖树」（2026-09-16，hyperframes 0.7.31→0.8.40）

**场景**：用户批准升级 hyperframes。它装在全局根 `D:\pi-agent`（`npm root -g` = `D:\pi-agent\node_modules`），
该根下**并排住着 13 个工具**。直接 `npm install -g hyperframes@latest` 的结果：

```
npm install -g hyperframes@0.8.40 --dry-run
→ 117 packages changed, 52 packages removed
```

**如果没有 `--dry-run`，这会静默打断另外 12 个工具。**

**第一步永远是 `--dry-run` + 逐个查依赖归属**（判据不是"看名字像不像"，是 `npm ls -g <包名>`）：

| 会被误删/降级的包 | 真正的主人 | 后果 |
|---|---|---|
| `sharp@0.34.5` | `@agegr/pi-web` 的 `next@16.2.1` | pi-web 图像处理直接废 |
| `color-convert` / `ansi-styles@4` | `pi-coding-agent` | 终端着色库被升到 6.x，旧调用可能崩 |
| `basic-ftp` / `buffer-crc32` | `pi-coding-agent` | 传输链断 |

**踩坑：`--install-strategy=nested` 对全局安装无效。** 加了它照样报 117 变更 —— 别指望这个开关救人。

**正解：隔离安装 + 手建嵌套依赖树**（四步，顶层零改动）

```bash
# 1. 隔离安装到独立目录（不碰全局根）
npm install hyperframes@0.8.40 --prefix D:\pi-agent\hf-080

# 2. 把新依赖树整个复制进包自己的 node_modules/
#    D:\pi-agent\hf-080\node_modules\* → D:\pi-agent\node_modules\hyperframes\node_modules\
#    （本机 340MB / 125 条目）

# 3. 只替换 hyperframes 本体（dist/、package.json 等），不碰任何同级包

# 4. 顶层 13 个包一个未动 —— 这才是验收判据
```

**为什么这样能行**：本机 npm 全局根**本来就是嵌套布局**（每个包的依赖躺在自己目录下，非扁平提升）。
所以 `hyperframes/node_modules/sharp@0.35.4` 与 `@agegr/pi-web/node_modules/sharp@0.34.5` **天然隔离，互不可见**。
→ 遇到全局包版本冲突，**优先想"能不能塞进包自己的 node_modules"，而不是"能不能升全局依赖"**。

**验收必须跑四项**（缺一项就可能"看起来成功了"）：

| 项 | 怎么测 | 本机结果 |
|---|---|---|
| 顶层包未动 | `ls D:\pi-agent\node_modules` 逐个数 | 13 个，零变更 |
| **shim 字节未变** | 升级前后对 `hyperframes.cmd` / `hyperframes` / `hyperframes.ps1` 取 **md5** | 三者 md5 逐字节相同 |
| 真实 PATH 调用 | 直接敲 `hyperframes --version`（**不能用绝对路径调 dist/cli.js**，那绕过了 shim，测不出 PATH 层问题） | 0.8.40 |
| 产线端到端 | 跑产线真实入口脚本 | 见下 |

**最关键的一项测试：拿产线源码当验收标准，不是拿 CLI 自己当标准。**
本机产线 `06_hyperframes_video.py` 第 25 行硬编码 `HF_CLI = r"D:\pi-agent\hyperframes.cmd"`，
第 233 行调用契约是：

```python
cmd = [HF_CLI, "render", str(scene_dir), "-o", str(output_path), "-f", "30", "-q", "standard"]
subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(scene_dir))
#                                                                  ↑ 60 秒硬限时
```

→ **`timeout=60` 就是升级的硬兼容判据。** 本机仿真出片 **17 秒**（余量 3.5 倍），退出码 0。
**升级前必须先读产线源码的调用行**，把它的参数、限时、cwd、退出码判断全部抄成测试用例。

**画质不能用"看起来没变"验收。** 用**全片逐帧 PSNR** 对比升级前后的同项目渲染：
> 40dB 以上＝视觉无差别，50dB 以上＝几乎完全一致。

本机 0.8.40 对 0.7.31 全片 **48.30 dB**（最差帧 47.49）、显著差异像素仅 **0.32%**（集中在文字边缘抗锯齿）→ 判零退化。
体积 +27.6% 的原因也查清了：编码码率 200→255 kbps（**默认 `-q` 档位变了，不是画质变好**）。

**⚠️ `-q/--quality` 的语义会漂移**：0.7.31 `draft/standard/high`（默认 `standard`）
→ 0.8.40 `draft/looks/delivery/standard/high`（默认 **`looks` = CRF 16**）。
`standard` 降级为兼容别名。→ **升级后若文件体积/耗时突变，先查参数档位的语义，别急着当 bug 修。**

**命令契约也要 diff**：升级前后各存一份 `<cli> --help > cli-help-旧.txt / cli-help-新.txt` 再做比对。
本机结果：**31 命令保留、5 新增（`check`/`compare`/`grade-compare`/`media-treatment`/`normalize-audio`）、0 删除**。
其中 `validate` 与 `inspect` **被废弃并统一进 `check`**（旧命令仍可跑，只打提示）——
所以**看到 deprecation warning 不要当失败**，先看替代命令是不是更强。

**备份与回滚（`tar` 必加 `--force-local`，见案例 11 的 Windows 坑）**：
```bash
tar --force-local -czf hyperframes-0.7.31-backup.tar.gz -C D:/pi-agent/node_modules hyperframes
# 本机 130MB / 7962 条目。验归档数四项：条目数、软链条数、隐藏文件、抽样命中
```
**回滚 = 解包覆盖本体 + 保留原嵌套树**，不需要重装。回滚方案要**在升级成功当天就验一遍**，不能等到出事才试。

**一个会浪费半小时的假警报：首次运行报 `spawn UNKNOWN`。**
新版需要下载新 Chrome（本机 131.0.6778.85 → **152.0.7977.30**），**首次解包未完成**时所有渲染类命令报 `spawn UNKNOWN`。
判据：**同一 composition、同一时刻，若旧版能跑而新版不能 → 先等浏览器落地**；
本机等新 Chrome 到位后**连跑 3 次全通过** → 冷启动一次性成本，非缺陷。

**升级完别忘下游**：`hyperframes skills check` 本机报 **19 过时 / 2 已被上游移除 / 1 新增核心**。
⚠️ 且技能池 `~/.agents/skills` 是 **WorkBuddy / Codex / Claude Code 三 Agent 共用**（`~/.claude/skills/*` 全是指向它的软链）——
`skills update` **会删除上游已移除的目录**，导致其他 Agent 的软链悬空。
→ **涉及共用池的改动，单独走一轮「逐个验证」，不要顺手做。**

> 📌 下游那一步已于同日单独执行完毕（20 技能池全部对齐、2 个废弃零残留）——
> 完整方法见 **案例 13**。本条的教训不变：**共用池的改动必须单开一轮**。

---

### 案例 13：共享技能池的升级与同步 —— **`skills update` 会「假报成功」**（2026-09-16 定案，20 技能池零残留）

**先认清池子的三层结构，否则必然漏同步：**

| 层 | 路径 | 性质 |
|---|---|---|
| canonical 真身 | `~/.agents/skills` | 唯一写入点 |
| 软链 / junction 镜像 | `~/.claude/skills`、`~/.codex/skills`、`~/.workbuddy-ai/skills` | **自动跟随 canonical**，改真身即生效 |
| **实体副本** | `~/.hermes/skills`、`~/.iflow/skills`、`~/.config/opencode/skills`、`~/.pi/agent/skills` | ⚠️ **改了 canonical 不会跟，必须单独同步** |

判形态一行搞定：`os.path.islink(p)` → 软链；`os.path.isjunction(p)` → junction；否则实体。

**为什么不能顺手跑 `npx skills update`：**

- **写入范围不止 canonical。** `hyperframes` 的 wrapper 硬编码了
  `GLOBAL_INSTALL_ARGS_TAIL = ["--global","--agent","claude-code","universal","--copy","--full-depth","--yes"]`，
  其中 `--copy` 会向源码里 **70 个 `AGENT_GLOBAL_DIRS`** 逐个写。**是否命中的判据是
  `existsSync(dirname(targetDir))`** —— 父目录存在才动。本机实命中 5 个目录
  （含**新建** `.codebuddy/skills`、往 `.hermes/skills` 写 109 项），另 54 个安全跳过。
  → **动之前先按这份映射表空跑一遍，算出影响面。**
- **非交互模式下它会跳过删除**（上游已移除的技能不会自动删）；但 `hyperframes skills update`
  子命令**会删**，导致别的 Agent 软链悬空。
- 🚨 **最坑的一条：它会对部分技能报 `✓ Updated`，而实际写入的是错误内容。**

**「假更新」的两种真实形态（本机实测）：**

1. **目录串位** —— `hyperframes-core` 里混进了 `hyperframes` 主技能的 9 个文件
   （`references/brief-contract.md`、`scripts/lib/frame-packets-core.mjs` 等），
   且跨技能引用被**改写成指向自己**（`../hyperframes/references/...` → `../hyperframes-core/references/...`）。
   本地 20 文件 vs 官方 manifest **11** 文件。
2. **上游中间版本** —— 跨技能路径写法不同：本地 `../../transitions/overview.md`
   vs 上游 `../transitions/overview.md`，**每个文件差 3~6 字节**。肉眼极易放过。

→ **结论：CLI 的 `✓` 一个字都不能信，必须用上游权威哈希逐文件独立比。**

**权威校验法（本案例的核心武器）**

```python
def git_blob_sha(content):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()
```

- **权威清单**：`raw.githubusercontent.com/<owner>/<repo>/main/skills-manifest.json`
  —— 每个技能给 `hash` + `files`（文件数）。**这是判据，不是 README 也不是对比表。**
- **逐文件哈希源**：GitHub tree API `.../git/trees/main?recursive=1`（本机 2.77MB / 1.12s）
- 一次比对同时得到「**哪个文件错了**」+「**错在第几字节**」，比整目录哈希有用得多。

**抓上游源码的两个硬坑：**

```bash
git clone --depth 1 <url> hfx        # ❌ 全量克隆会超时（SIGTERM）

git clone --depth 1 --filter=blob:none --sparse <url> hfx   # ✅ 本机 21 秒
cd hfx && git sparse-checkout set skills/<要的几个>
git config core.autocrlf false && git config core.eol lf    # ⚠️ 关键，漏了必然对不上
```

上游 `.gitattributes` 是 `* text=auto eol=lf`；Windows 默认 `core.autocrlf=true`
会把检出文件**全转 CRLF**，于是 blob sha 必然不符，**会被误判成「上游内容有问题」**——
先去查自己的 autocrlf，再怀疑上游。

**重建 + 验证四步（缺一不可）：**

1. **normalize**：原样 → `\r\n`→`\n` → 去 BOM，**三级回退**，任一级命中即采用（本机三级全命中「原样」）
2. 校验读到的文件数 **== manifest 的 `files`**
3. 备份旧目录 → 写入
4. 🔁 **回读逐文件 blob sha 再比一遍** —— **写成功 ≠ 写对**

**实体副本同步：** 只动「上游发布的技能集」，用目录树 sha1 判等；
**先 `DRY=1` 空跑**出「更新 N + 新增 M」清单，人确认后再实跑，跑完回读校验。
（本机预演暴露了 OpenCode 需更新 19 个，而另外三个只各需 1~2 个 —— 不空跑就会盲打。）

**废弃技能清理：** canonical **归档不删**（保留可恢复），各 Agent 目录移除引用，最后全盘扫残留。

> 🩸 **血泪点：清理完必须重跑 `check`。**
> 本机为此白查了一整轮 —— 我读的是自己早先存的 `check-after-step2.json`，
> 里面还写着「2 removed upstream」，但那是**清理动作之前**的时间点。
> **存档快照会骗人，只有当下实跑的输出算数。**

**收尾验证清单（逐项都要有输出）：**

- `hyperframes skills check` → `✓ N current` + `Installed skills are up to date`，
  **退出码 0**（有 outdated 时它返回 **1** —— 脚本里拿退出码判成败会被坑）
- canonical vs 上游 manifest **差集 == 空**
- 每个 Agent 目录**逐文件 sha1 零差异**（本机 6 个目录各 914 文件）
- 「**故意不挂**」的项要能当场说出理由（本机 WorkBuddy 有意不挂 `figma` /
  `remotion-to-hyperframes`）—— 否则会把设计决策误报成缺陷
- 新增技能**当场可加载**：直接用 Skill 工具调一次即验证，**不需要重启会话**

**别忘 lock。** `check` 判定「removed upstream」读的是
`~/.agents/.skill-lock.json`（`$XDG_STATE_HOME/skills/.skill-lock.json` 优先，project scope 则读
`cwd/skills-lock.json`）。判定链是：`source` 归属 → `skillPath` 以 `skills/` 开头 → 不在当前上游清单。
**先确认读的是哪个 lock，再谈「为什么还报 removed」。**

#### ⚠️ 反向纪律：**往共享目录里加东西之后，必须验证它不会被同步动作清掉**

同步是双向风险 —— 不只「漏同步」，还有「**被冲掉**」。新建一个 skill 放进任何被托管的目录后，
按这三连判据验一遍（本机 `hyperframes-local-transcribe` 实测通过）：

| 判据 | 怎么查 | 为什么 |
|---|---|---|
| ① 在不在 lock | 读 `.skill-lock.json` 的 `skills` 键 | prune **只删 lock 里登记的**；不在 lock → 不会被删 |
| ② 在不在上游清单 | 比对 `skills-manifest.json` | 不在 → 不参与 hash 比对，不会被判 outdated |
| ③ **目标目录在不在工具的目标矩阵** | 解析 cli.js 的 `AGENT_GLOBAL_DIRS` | 不在矩阵 → 同步动作**根本不会写这个目录** |

> 🧨 **本机最容易想当然的一处：`codebuddy` ≠ `workbuddy`。**
> `AGENT_GLOBAL_DIRS` 70 项里只有 `codebuddy`（`.codebuddy/skills`），
> **全文搜 `workbuddy` 出现 0 次** —— 也就是说 `~/.workbuddy-ai/skills` **完全在同步矩阵之外**。
> 别看到 "buddy" 就以为是同一个东西。

---

### 案例 14：**外部技能选型** —— 按「生产环节」归位，不按热度排（2026-10-05 定案，编导环节盘点）

**场景**：用户要求「用 find-skills 查视频编导相关技能，列表汇总分析，结合我们做自媒体的需求来挑」。
这类需求（**选型**，不是**体检**）比体检多两步：**外部检索** + **归位判断**。本节记录这两步的方法。

#### 第一步：外部检索（SkillHub 是主源，但要批量跑）

```bash
curl -s "https://lightmake.site/api/v1/search?q=<URL编码>&limit=12"
```

- **必须批量跑关键词**（本次 52 组），单次搜索覆盖极差。中文说法不统一 → 每个环节换 2~3 种说法
  （编导 / 分镜 / 镜头语言 / 运镜 / 完播 / 钩子 …）。
- **`score` 阈值不能用来筛**：本机实测全部落在 **0.05~0.13**，最高的也只有 0.126。
  按「<0.05 忽略」的官方建议筛，会把真正相关的全滤掉。
  → **判据是内容，不是分数。分数只用来做同组内排序。**
- 检索结果里 **`downloads` 与 `stars` 常常背离**（本机实例：`short-video-script` 31403 下载 / 63 星，
  而内容密度最高的 `kunlun-wanbolv` 只有 13 下载 / 0 星）。**冷门 ≠ 没用。**
- 写脚本做**去重 + 多关键词命中数**统计，比人肉翻 JSON 快一个数量级。

#### 第二步：先清点本地，再谈「候选」（复用守则的硬应用）

⚠️ **不做这一步，报告必然是错的。** 本机实测：外部检索出 300+ 条去重结果，
但**真正有价值的候选只有 7 个** —— 因为：
1. **大量结果本地早已装上**（本次 56 个 skill 里有 13 个属该环节）；
2. **更多结果本地已有等价能力**（`knowledge-video-storyboard` 已覆盖「口播稿→分镜」，
   外部再多的分镜技能都是重复）；
3. **大部分结果根本不属于该环节**（搜「视频」出来 80% 是图生视频/数字人/漫剧 —— 那是**制作段**，
   不是**编导段**）。

→ 顺序必须是 **① 提取本地 frontmatter 描述 → ② 外部检索 → ③ 相减**，反过来做会推荐一堆已装的东西。
→ 可复用脚本套路：遍历 `~/.workbuddy-ai/skills/*/SKILL.md`，正则抓 frontmatter 的 `name` / `description`。
   注意 **YAML 多行描述（`>` / `|`）抓不到内容** → 要回退到正文首段。

#### 第三步：归位 + 分档（这才是「挑选」）

- **按生产环节切，不按平台或热度切。** 本次把「编导」切成
  选题策划 / 脚本创作 / 分镜设计 / 镜头语言 / 节奏完播 五段，逐段标「已覆盖 / 部分 / 空白」。
  → 缺口自然浮现，推荐也自然有依据。
- **分档要给出「不装」的理由**，不能只列推荐。本次专设第三档「不建议装」，
  把漫剧系、数字人系、带货系、横屏编剧系逐一排除并写明原因 ——
  这样用户下次不用重新纠结同一批东西。
- **最高人气的那条往往是坑。** 本次 `short-video-script`（31403 下载 / 63 星）功能与本地已有的
  `content-research-writer` + `viral-video-replicate` + `knowledge-video-storyboard` 链条高度重叠
  → 装了大半闲置。**人气是平台的指标，不是你的指标。**

#### 附：断链的「查」与「修」（2026-10-05 实战闭环）

**查**（一条命令扫全量）：

```bash
cd ~/.workbuddy-ai/skills && for n in *; do
  [ -L "$n" ] && [ ! -e "$n" ] && echo "DANGLING: $n -> $(readlink "$n")"
done
```
判据：**「软链存在」≠「目标存在」** —— `-L` 为真、`-e` 为假 = 空壳。清点家底必须验这一层。

**修之前先分清两种断链 —— 修法完全不同：**

| 形态 | 判据 | 修法 |
|---|---|---|
| **技能真的没了** | 遍历所有 Agent 目录都找不到实体 | 补回文件，或从引用里摘掉 |
| **接线接错地址**（更常见） | 别的 Agent 目录 `-e` 能过、且都指向同一个真身 | **只改软链目标**，一行 `ln -s` |

本机实测属**第二种**：`video-production-analysis` 的 WorkBuddy 接线指着 `~/.agents/skills/`（旧 hub 路径），
而 `.codex` / `.claude` / `.hermes` 都已改指仓库 `code-news\.agents\skills\` —— **唯独 WorkBuddy 漏改**。
根因：2026-09-16「技能搬家到 git 管理」时 hub 原位内容被移进 `~/.agents/_archive/`，
指向旧路径的接线**静默断掉**（不报错、不提示）。

**修法**：

```bash
cd ~/.workbuddy-ai/skills
export MSYS=winsymlinks:nativestrict
rm -f <name>
ln -s "/c/Users/Administrator/Documents/code-news/.agents/skills/<name>" <name>
```

⚠️ `rm` / `ln` 的返回码在本机**都不可信**（见删除铁律与案例 11），**必须看实际结果**（`ls -la` + `-e` 判定）。

**验收四类判据**（与案例 11 一致）：reparse tag `0xa000000c` / 与真身 `diff -r` 逐文件一致 /
frontmatter `name` == 目录名 / **实测 Skill 工具调用成功**。

> ⚠️ **风险模式（值得记住）**：`~/.agents/skills` 里被「归档 / 搬家 / 上游移除」的技能，
> 会让**仍指向旧 hub 路径**的接线静默断掉。→ **批量同步动作（`skills update` /
> `sync_agent_skills.py`）之后，值得跑一次全量断链扫描。**

#### 反查：推荐市场的关键词覆盖很差

`workbuddy_marketplace_skill`（BuiltinMarket）用 `编导` / `短视频` 搜**均返回 0 条**，
`视频` 只有 3 条。→ **不能只靠它做选型**，它是补充源，SkillHub 才是主源。
