# v3 内容运营总控设计

日期：2026-06-14  
范围：头条 / 知乎 / 公众号 / 小红书  
阶段边界：第一阶段只做 `对标监控 + 选题分析 + 草稿生成 + 封面/配图 + 质检预检 + 发布占位`，不做正式发布，不做发布后 72 小时追踪。

## 1. 背景

当前仓库已经有三类资产：

1. 历史内容产物：`.tmp/generated/<slug>/`
2. 三平台浏览器发布脚本：`.tmp/publish_*.js`
3. 质检与状态脚本：`scripts/check_generated_article_quality.py`、`scripts/run_three_platform_pipeline.py`

但当前系统仍有四个核心缺口：

1. 没有一个统一的 v3 总控入口，把“监控、分析、生成、配图、预检、发布占位”串成一条链。
2. 没有把“Skills/MCP 的方案名接口层”和“当前真实可调用能力”分开，容易把未来能力误写成当前能力。
3. 历史数据没有系统迁移，旧内容产物与发布记录分散，难以统一判断。
4. 插图长期呈现单一版本复用，缺少风格分流、变体约束和反重复机制，这会直接伤害点击和停留。

## 2. 目标

本轮 v3 落地只追四件事：

1. 在现有 `code-news` 仓库内建立 v3 主控结构，而不是新开一套平行工程。
2. 为四个平台建立统一的“生成前到发布前”链路，其中小红书只保留预发布占位，不走正式发布。
3. 落地一套真实可执行的 Skills/MCP 采用方案，明确哪些已经能用，哪些只是接口预留。
4. 把插图/配图多样性纳入配置、状态和预检，不再允许长期单一模板重复。

## 3. 非目标

本轮明确不做：

1. 不重写现有头条 / 知乎 / 公众号浏览器发布脚本。
2. 不把小红书强行接进正式发布链。
3. 不假装仓库已经具备脚本级的 `codex_api_mcp` 或 `web_scraper_mcp` 自动调用能力。
4. 不做视频平台、快手、视频号。
5. 不做正式发布按钮自动点击后的 72 小时追踪闭环。

## 4. 总体结构

v3 采用双层结构：

### 4.1 方案接口层

保留方案里的命名，作为稳定接口名：

- `monitor_skill`
- `analyzer_skill`
- `writer_skill`
- `humanizer_skill`
- `illustration_skill`
- `cover_skill`
- `publisher_skill`
- `codex_api_mcp`
- `web_scraper_mcp`

### 4.2 真实调用层

当前仓库里真正存在、并且本机会话可确认的能力：

- `dbs-benchmark`
- `dbs-content`
- `content-research-writer`
- `humanizer-zh`
- `ian-xiaohei-illustrations`
- `guizang-social-card-skill`
- `xhs-auth / xhs-explore / xhs-publish`
- `wechat-article-search / wechat-article-extractor / wechat-content-optimizer`
- `scripts/check_generated_article_quality.py`
- `scripts/run_three_platform_pipeline.py`
- `node_repl / browser automation / 本地 Playwright 脚本`

结论：

1. 接口层保留方案命名，避免后续方案继续漂移。
2. 调用层直接映射到当前真实能力，避免“纸面可用”和“当前可用”混淆。
3. `codex_api_mcp` 与 `web_scraper_mcp` 本轮先落成接口占位和调用协议，不谎称已自动化接通。

## 5. 目录与配置

新增三类固定资产：

1. `config/tool_registry.json`
   - 记录接口层到真实能力的映射。
2. `config/content_domains.json`
   - 锁定第一阶段内容域：`AI工具 / 效率工具 / 数字产品使用 / 轻科技科普`。
3. `config/image_strategy.json`
   - 定义插图风格族、封面风格族、配色池、重复约束和平台偏好。

## 6. 第一阶段主链路

v3 第一阶段总控顺序固定为：

1. 读取 payload / 生成目录
2. 运行质量预检
3. 解析内容域
4. 生成插图与封面计划
5. 生成 Skills 调用包
6. 生成四平台发布占位预览
7. 写回统一状态文件

本阶段输出的不是“直接正式发布”，而是“可审阅、可确认、可追溯”的预发布产物。

## 7. 统一状态

继续沿用每篇内容一个状态文件的原则，主状态文件保留在：

- `.tmp/generated/<slug>/pipeline-state.json`

在状态文件中新增 `v3` 区块，用来记录：

- 当前所属内容域
- 图片计划文件路径
- Skills 调用包路径
- 发布预览路径
- 是否允许正式发布
- 小红书是否只处于占位模式

## 8. 历史迁移

历史迁移分两层：

### 8.1 状态补齐

对已有 `manifest.json`、payload、发布记录进行扫描：

1. 已有 `pipeline-state.json` 的目录直接保留。
2. 缺失 `pipeline-state.json` 的目录尝试自动补写。
3. 补写时只使用已有文件与已有发布记录，不虚构不存在的发布结果。

### 8.2 索引沉淀

额外生成一份迁移索引，用来给后续运营和图像反重复使用：

- 文章 slug
- 标题
- 文件齐全度
- 各平台历史状态
- 历史插图线索

## 9. 插图与配图多样性方案

这是本轮设计重点，不再把插图当成“最后顺手补一张图”。

### 9.1 问题定义

当前历史产物暴露出明显风险：

1. 正文插图结构过于一致。
2. 配色和信息层级重复出现。
3. 多篇内容的视觉语言没有按主题和平台分流。

结果是：

1. 读者一眼识别为同一批模板。
2. 平台侧容易把内容识别为低差异批量产物。
3. 内容主题变化没有被视觉层放大。

### 9.2 设计原则

新策略不是“随机换皮”，而是“按主题分流 + 按历史去重”：

1. 同一篇文章内，三张正文图必须来自不同的图像家族。
2. 连续两篇内容，封面家族不能重复。
3. 最近两篇内容，主配色不能重复。
4. 同一内容域只允许从偏好家族中优先选，但不能死锁在单一家族。
5. 生成计划必须把使用的家族、渲染器、配色写入历史，供下一次选择避让。

### 9.3 图像家族

正文图至少区分为以下家族：

1. `workflow_whiteboard`
2. `comparison_board`
3. `risk_checklist`
4. `decision_tree`
5. `tool_stack_map`
6. `myth_vs_fact`

封面至少区分为以下家族：

1. `warm_editorial`
2. `contrast_signal`
3. `data_brief`
4. `question_lead`

### 9.4 渲染器策略

不再默认所有图都走同一种渲染器：

1. 正文图优先在 `ian-xiaohei-illustrations` 与 `imagegen` 两类渲染器之间按家族切换。
2. 封面优先在 `guizang-social-card-skill` 与 `imagegen` 两类方案之间切换。
3. 只有当某一类渲染器当前不可用时，才允许回退到单一渲染器。

### 9.5 平台适配

第一阶段平台上的视觉策略如下：

1. 头条：优先“快判断、强对比、短标题导向”。
2. 知乎：优先“结构图、比较图、问题导向”。
3. 公众号：优先“封面完成度、正文节奏、留白感”。
4. 小红书：只做预发布卡片占位，不进入正式发布。

## 10. Skills / MCP 采用结论

### 10.1 已采用

- `monitor_skill` -> `dbs-benchmark` + `wechat-article-search` + `xhs-explore`
- `analyzer_skill` -> `dbs-content`
- `writer_skill` -> `content-research-writer`
- `humanizer_skill` -> `humanizer-zh`
- `illustration_skill` -> `ian-xiaohei-illustrations` / `imagegen`
- `cover_skill` -> `guizang-social-card-skill` / `imagegen`
- `publisher_skill` -> 现有本地脚本与 `run_three_platform_pipeline.py`

### 10.2 占位但未自动化接通

- `codex_api_mcp`
- `web_scraper_mcp`

这两个接口在本轮只做：

1. 注册表声明
2. 输入输出协议
3. 后续开发计划落点

## 11. 成功标准

本轮完成标准不是“已经自动发出去”，而是：

1. 仓库内有正式的 v3 规格与实施计划。
2. 仓库内有可执行的工具注册表和图片策略配置。
3. 历史数据可被迁移到统一状态。
4. 新的 v3 预发布主链可以输出：
   - 质量预检结果
   - 图片计划
   - Skills 调用包
   - 四平台发布占位预览
5. 小红书仍保持预发布占位，不触碰正式发布。

## 12. 后续阶段

本轮之后再做：

1. `codex_api_mcp` 真正脚本化接入
2. `web_scraper_mcp` 真正脚本化接入
3. 正式发布确认闸门
4. 发布后 72 小时追踪
5. Windows 任务计划调度
