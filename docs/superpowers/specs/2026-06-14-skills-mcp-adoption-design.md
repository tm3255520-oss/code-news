# v3 内容运营 Skills / MCP 采用设计

日期：2026-06-14  
适用仓库：`C:\Users\Administrator\Documents\code-news`

## 1. 目标

这份设计只解决三个问题：

1. 把 `对标监控 -> 爆款分析 -> 仿写方案 -> 批量生成 -> 配图 -> 评分 -> 定时发布 -> 数据追踪 -> 质量复盘 -> 评分规则修正 -> 工具评估` 这 11 个环节需要的能力映射清楚。
2. 把“会话里可调用的 skill / MCP / 插件工具”和“仓库里可被脚本稳定调度的能力”严格分开。
3. 给出当前缺口的开发顺序，避免后续继续把占位能力误写成已落地能力。

这份设计不做正式发布实现，不改现有发布脚本行为，不假装 `codex_api_mcp` 和 `web_scraper_mcp` 已经存在。

## 2. 判定标准

每个流程环节都按三层能力评估：

1. `会话能力`：当前 Codex 会话里能直接调用的 skill、MCP、插件工具。
2. `仓库能力`：当前仓库内已有脚本、配置、状态文件，且可在本机重复执行。
3. `调度能力`：未来能否被 Windows 任务计划或统一总控脚本稳定调用。

只有同时满足第 2 层和第 3 层，才能算“已纳入 v3 主链”。  
只有第 1 层可用时，只能算“研究辅助能力”，不能算自动化主链能力。

## 3. 流程映射总表

| 环节 | 目标 | 推荐 Skills | 推荐 MCP / 插件工具 | 当前仓库实现 | 当前结论 |
|---|---|---|---|---|---|
| 对标监控 | 抓平台对标、沉淀结构化样本 | `dbs-benchmark`、`wechat-article-search`、`wechat-article-extractor`、`xhs-explore`、`xhs-content-ops` | `web.run`、`mcp__node_repl.js` | 缺统一采集器；仅有零散样本与分析脚本 | `需适配` |
| 爆款分析 | 从样本中抽取高流量结构和信号 | `dbs-content`、`content-research-writer` | `web.run` | `scripts/generate_peer_content_insights.py` | `可用但输入不统一` |
| 仿写方案 | 生成差异化仿写 brief | `dbs-content`、`content-research-writer`、`humanizer-zh` | 无硬依赖 | 已能产出 markdown，但没有标准接口 | `需适配` |
| 批量生成 | 按主题批量生成草稿、标题、摘要 | `content-research-writer`、`wechat-content-optimizer`、`humanizer-zh` | 未来应统一到 `codex_api_mcp` | `scripts/run_v3_content_ops.py` 只做预检主链，不做真实批量生成 | `暂缺主干` |
| 配图 | 正文插图、封面、平台图卡 | `ian-xiaohei-illustrations`、`guizang-social-card-skill` | `image_gen`、Figma 工具可选 | `scripts/image_strategy.py` | `基础可用` |
| 评分 | 发布前质量打分和拦截 | `humanizer-zh` 只负责文本修正 | 无硬依赖 | `scripts/check_generated_article_quality.py` | `可直接用` |
| 定时发布 | 统一调度发布或预发布占位 | `xhs-publish` 仅保留候选 | `codex_app.automation_update`、`mcp__node_repl.js` | `scripts/run_three_platform_pipeline.py`，但 `formalPublishEnabled=false` | `当前不能算正式自动发布` |
| 数据追踪 | 采 24h / 72h 表现数据 | 无专用核心 skill | `mcp__node_repl.js` 未来可做浏览器采集 | `scripts/sync_recent_metrics_to_log.py`、`scripts/collect_xhs_recent_metrics.py` | `部分可用` |
| 质量复盘 | 从结果反推标题、结构、配图问题 | `dbs-content`、`content-research-writer` | 无硬依赖 | `scripts/generate_content_performance_report.py`、`scripts/run_daily_content_ops.py` | `可用但偏报表` |
| 评分规则修正 | 根据表现回调质检规则 | 无现成专用 skill | 无 | 只能手改脚本 | `缺闭环` |
| 工具评估 | 比较 skill / MCP / 脚本稳定性和成本 | 无现成专用 skill | `web.run` | 无统一台账 | `缺台账` |

## 4. 当前采用结论

### 4.1 P0：立即纳入 v3 主链

这些能力已经足够稳定，应该直接写入 v3 主链设计，不再反复讨论是否采用：

- `dbs-benchmark`
- `dbs-content`
- `content-research-writer`
- `humanizer-zh`
- `ian-xiaohei-illustrations`
- `guizang-social-card-skill`
- `wechat-article-search`
- `wechat-article-extractor`
- `wechat-content-optimizer`
- `scripts/check_generated_article_quality.py`
- `scripts/image_strategy.py`
- `scripts/run_v3_content_ops.py`
- `scripts/run_three_platform_pipeline.py`
- `scripts/sync_recent_metrics_to_log.py`
- `scripts/generate_content_performance_report.py`
- `scripts/run_daily_content_ops.py`

这些能力的角色应当固定为：

- `monitor_skill`：对标监控与样本收集
- `analyzer_skill`：爆款分析与仿写拆解
- `writer_skill`：草稿生成与中文优化
- `illustration_skill`：正文插图生成
- `cover_skill`：封面、首图、传播图生成
- `quality_gate`：发布前质检与拦截

### 4.2 P1：允许使用，但不计入“仓库已落地能力”

这些工具在当前会话可用，但还不能写成“仓库自动化已落地”：

- `web.run`
  用于对标搜索、查外部资料、核实平台公开信息。适合研究，不适合直接当任务计划主链。
- `mcp__node_repl.js`
  未来浏览器采集、自动化验证、受控发布的首选执行器。优先级高于桌面乱点。
- `codex_app.automation_update`
  适合 Codex 应用层的周期任务，但不是仓库级计划任务的替代品。
- Figma 工具
  适合高控制视觉资产生成，不适合当前 P0 内容流水线主链。
- `xhs-explore` / `xhs-content-ops` / `xhs-publish`
  当前只保留为研究、预发布、风险排查能力，不纳入正式自动发布主链。

### 4.3 P2：必须补齐的适配层

如果不开发下面这几个适配层，项目会长期停留在“会话里能做、调度时失效”的状态：

- `codex_api_mcp`
- `web_scraper_mcp`
- `scheduler_adapter`
- `metrics_tracker`
- `quality_calibration`
- `tool_evaluation_registry`

## 5. 不采用或降级采用的结论

下面几类能力不应该被写成当前主链核心：

### 5.1 小红书自动发布

结论：当前阶段只保留 `预发布占位`，不进入正式发布主链。

原因：

1. 当前项目目标已明确小红书暂不正式发布。
2. 小红书 skills 文档自身限制执行方式，且 metadata 标记偏 `darwin / linux`，对当前 Windows 主链存在环境不确定性。
3. 小红书是风控最敏感平台，不应在“接口层未统一、去重发布未闭环”的情况下继续自动推进。

### 5.2 Figma 作为配图主干

结论：保留为高质量视觉分支，不纳入当前 P0 主链。

原因：

1. 当前主链目标是稳定批量出图和去重，而不是高精度人工设计。
2. Figma 更适合做大图卡、模板化资产、专题封面，不适合替代正文插图流水线。

### 5.3 Computer Use / 桌面点击型自动化

结论：只作为最后兜底，不作为主执行器。

原因：

1. 当前环境已经有 `mcp__node_repl.js`，浏览器控制能力优先级更高。
2. 桌面点击重放更脆弱，更难调试，也更难沉淀成仓库级总控。

## 6. `codex_api_mcp` 接口设计

### 6.1 设计目标

`codex_api_mcp` 不是某个具体模型的名字，而是 v3 总控调用 AI 能力的统一协议层。

它负责把以下能力标准化：

- 选题延展
- 爆款角度拆解
- 仿写 brief
- 标题生成
- 正文草稿生成
- 人味化重写
- 评分解释文案

### 6.2 最小能力集

第一版只做 5 个动作：

1. `draft_article`
2. `generate_titles`
3. `build_rewrite_plan`
4. `humanize_article`
5. `summarize_quality_issues`

### 6.3 请求结构

```json
{
  "action": "draft_article",
  "requestId": "2026-06-14-ai-tools-night-shift-001",
  "topic": "设计工具怎么选，我现在先看能不能继续改",
  "platforms": ["toutiao", "zhihu", "wechat"],
  "contentDomain": "AI工具",
  "inputs": {
    "benchmarkSummaryPath": ".tmp/generated/<slug>/benchmark-monitor.md",
    "viralAnalysisPath": ".tmp/generated/<slug>/viral-analysis.md",
    "rewritePlanPath": ".tmp/generated/<slug>/rewrite-plan.md"
  },
  "constraints": {
    "tone": "中文、自然、少套话、能落地",
    "avoid": ["重复标题", "平台规则冲突", "空泛结论"],
    "wordCount": {
      "toutiao": 1200,
      "zhihu": 1400,
      "wechat": 1500
    }
  }
}
```

### 6.4 响应结构

```json
{
  "requestId": "2026-06-14-ai-tools-night-shift-001",
  "status": "ok",
  "provider": "configured_provider",
  "artifacts": {
    "articlePath": ".tmp/generated/<slug>/article.md",
    "titleVariantsPath": ".tmp/generated/<slug>/title-variants.json",
    "summaryPath": ".tmp/generated/<slug>/ai-summary.json"
  },
  "usage": {
    "inputTokens": 0,
    "outputTokens": 0
  },
  "warnings": []
}
```

### 6.5 失败模型

统一只允许三类失败：

- `retryable_error`
- `validation_error`
- `provider_error`

失败响应必须包含：

```json
{
  "requestId": "2026-06-14-ai-tools-night-shift-001",
  "status": "error",
  "errorType": "provider_error",
  "message": "provider timeout",
  "retryable": true
}
```

### 6.6 落地原则

实现时必须遵守：

1. 业务脚本不能直接知道具体模型名。
2. 业务脚本不能直接依赖 skill 名称。
3. 统一由本地适配脚本负责鉴权、重试、日志、落盘。
4. 所有生成物必须落本地文件，不能只存在会话里。

## 7. `web_scraper_mcp` 接口设计

### 7.1 设计目标

`web_scraper_mcp` 负责统一“搜什么、抓什么、怎么标准化”，不负责内容分析。

它的工作对象包括：

- 对标账号列表
- 文章或帖子详情
- 平台公开列表页
- 最近表现数据

### 7.2 最小能力集

第一版只做 5 个动作：

1. `search_content`
2. `fetch_article`
3. `fetch_author_feed`
4. `extract_metrics`
5. `normalize_record`

### 7.3 请求结构

```json
{
  "action": "search_content",
  "requestId": "2026-06-14-monitor-ai-tools-001",
  "platform": "zhihu",
  "query": "AI工具 效率 提示词 工作流",
  "limit": 10,
  "sortBy": "recent",
  "timeWindow": "7d"
}
```

### 7.4 统一记录结构

所有平台抓回来的记录，必须先映射到统一结构再进入分析脚本：

```json
{
  "platform": "zhihu",
  "recordType": "article",
  "author": "示例作者",
  "title": "示例标题",
  "url": "https://example.com/post",
  "publishedAt": "2026-06-14T08:30:00+08:00",
  "metrics": {
    "views": 0,
    "likes": 0,
    "comments": 0,
    "favorites": 0,
    "shares": 0
  },
  "content": {
    "summary": "正文摘要",
    "rawTextPath": ".tmp/scrape/<id>/raw.md"
  },
  "meta": {
    "topic": "AI工具",
    "tags": ["效率", "AI工具"],
    "captureMethod": "browser"
  }
}
```

### 7.5 落地原则

实现时必须遵守：

1. 抓取层只负责采集与标准化，不做“是否爆款”的判断。
2. 平台适配器必须按平台拆开，不能写一个巨型混合脚本。
3. 所有抓取结果必须可重放、可落盘、可追溯来源 URL。
4. 必须记录抓取方式、抓取时间、抓取平台、限流或失败状态。

## 8. 配图链的特殊结论

当前配图问题不是“没有工具”，而是“没有分流规则”。

所以 v3 必须保留并继续加强下面这套约束：

1. 同一篇文章的 3 张正文图不能来自同一图像家族。
2. 连续两篇文章不能复用同一封面家族。
3. 最近两篇文章不能复用主配色。
4. 正文图和封面图要分开选渲染器，不允许长期只走一个 renderer。
5. 配图历史必须写回状态文件，供下一次避让。

换句话说，配图主问题已经从“选哪一个 skill”转成“如何把多样性规则固化到代码和状态文件”。

## 9. 开发顺序

后续实现按下面顺序推进：

1. 开发 `web_scraper_mcp` 接口层
2. 开发 `codex_api_mcp` 接口层
3. 把对标监控、爆款分析、仿写方案三步改成统一输入输出
4. 把批量生成接入统一 AI 适配层
5. 补 `metrics_tracker`，统一 24h / 72h 数据追踪
6. 补 `scheduler_adapter`，先跑监控、分析、预检，不直接放开正式发布
7. 补 `quality_calibration`，把评分规则修正做成可回放流程
8. 补 `tool_evaluation_registry`，沉淀每个 skill / MCP / 脚本的稳定性和替代策略

## 10. 下一阶段验收标准

进入下一阶段之前，至少要满足：

1. `codex_api_mcp` 和 `web_scraper_mcp` 都有明确输入输出契约。
2. 仓库里能区分“会话能力”“仓库能力”“调度能力”。
3. 对标监控、爆款分析、仿写方案三步不再依赖临时人工拼接。
4. 预发布链输出的每个产物都有固定路径和固定字段。
5. 正式发布仍保持关闭，直到重复发布拦截、平台验证、失败回滚都补齐。
