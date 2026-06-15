# 发布稳定性、文本质量与流量执行方案

更新时间：2026-05-27

## 目标

接下来 7 天，我们不再把重点放在“能不能多发几个平台”，而是同时解决 3 件事：

1. 把 4 平台发布链路从“能用”推进到“可控、可预检、少返工”
2. 把文本质量从“写得完整”推进到“更有竞争力、更适合平台”
3. 把流量工作从“发完再看”推进到“发布前就知道为什么值得发，发布后能快速复盘”

核心原则：

- 发布优先解决稳定性，不追求华丽自动化。
- 文本优先解决竞争力，不追求写得面面俱到。
- 流量优先解决反馈闭环，不追求一次猜中爆款。

## 当前判断

### 发布现状

| 平台 | 当前判断 | 主要问题 | 当前结论 |
| --- | --- | --- | --- |
| 微信公众号 | 可用，但最后一步要人工扫码验证 | 无法真正一键到底 | 保留现链路，同时推进 API-first |
| 知乎 | 当前最顺 | 仍依赖浏览器登录态 | 作为当前最稳主链路 |
| 今日头条 | 能发，但边角问题多 | 标题、封面、发布后回查容易出问题 | 先保稳发，不强控所有细节 |
| 小红书 | 有发布记录，但稳定性最弱 | 登录态、桥接、模板阶段不稳定 | 先做 login/editor readiness，再谈放量 |

### 质量与流量现状

- 仓库里已经有表现周报脚本、同行样本分析脚本、质量闸门模板和改进模板。
- 现在缺的不是“理论”，而是一个固定执行回路。
- 也就是说：工具有雏形，但没有被串成每天都能跑的流程。

## 这次我补上的执行抓手

### 1. 发布 readiness 脚本

新增脚本：

- [check_publish_readiness.py](/C:/Users/Administrator/Documents/code-news/scripts/check_publish_readiness.py)
- [probe_xhs_publish_state.py](/C:/Users/Administrator/Documents/code-news/scripts/probe_xhs_publish_state.py)
- [run_daily_content_ops.py](/C:/Users/Administrator/Documents/code-news/scripts/run_daily_content_ops.py)

作用：

- 每天先判断 4 平台当前是否适合正式发布
- 把问题分成 `ready / warning / blocked`
- 直接提示下一步动作，而不是等到写完才发现发不出去

建议命令：

```bash
python scripts/check_publish_readiness.py --format markdown
python scripts/probe_xhs_publish_state.py
python scripts/run_daily_content_ops.py
```

### 2. 统一流量台账同步脚本

新增脚本：

- [sync_recent_metrics_to_log.py](/C:/Users/Administrator/Documents/code-news/scripts/sync_recent_metrics_to_log.py)

作用：

- 把微信、知乎、头条、小红书最近表现统一同步成同一份 CSV
- 直接喂给现有周报脚本
- 从今天开始，把“质量”和“流量”放到同一张表里看

建议命令：

```bash
python scripts/sync_recent_metrics_to_log.py --output .tmp/latest-content-performance-log.csv
python scripts/generate_content_performance_report.py .tmp/latest-content-performance-log.csv --output .tmp/content-performance-report.md
```

## 接下来 7 天怎么做

## P0：先把发布变成“可预检”

这一步目标不是继续写更复杂的发布器，而是做到：

- 发布前 3 分钟就知道哪个平台今天能发，哪个平台今天不该碰
- 不再在写完文之后才暴露登录态、桥接态、模板态问题

执行动作：

1. 每天开始工作先跑一次 `check_publish_readiness.py`
2. 如果平台状态是 `blocked`，当天先不把它放进正式发布计划
3. 如果平台状态是 `warning`，只发 1 篇，不做批量
4. 只有 `ready` 平台进入当天主发布链路

对应判断：

- 知乎：当前主发布平台
- 微信：可发，但发布时要留出人工验证时间
- 头条：保留，但以“稳发成功”为第一目标
- 小红书：先保账号健康和链路稳定，不做激进放量

## P1：把每篇内容拆成 3 个版本，而不是一稿四发

从现在开始，每篇内容最少准备 3 个版本：

- 深度版：给微信公众号、知乎
- 冲突短标题版：给小红书、头条
- 复盘版：给后续表现分析和改稿

固定规则：

- 微信 / 知乎：允许更完整的论证、更长标题、更清楚的结构
- 小红书 / 头条：优先短标题、强冲突、强结论、首屏快进入价值
- 不能再把同一标题直接平移到 4 个平台

## P2：发布前加一道质量闸门

直接使用现有模板：

- [pre-publish-quality-gate-template.md](/C:/Users/Administrator/Documents/code-news/docs/templates/pre-publish-quality-gate-template.md)

以后每篇发布前都要过这 7 个问题：

1. 标题是否足够具体、清楚、可感知收益
2. 开头前三段是否快速给出冲突、判断或结论
3. 正文是否有可以被收藏的结构化信息
4. 是否有清晰观点，而不只是信息搬运
5. 封面是否与标题承诺一致
6. 是否适配当前平台阅读习惯
7. 是否与最近已发内容过度重复

执行要求：

- 少于 6 项通过，不发
- 被打回必须写明原因
- 每篇至少留一个“为什么这篇值得发”的一句话判断

## P3：把流量数据变成下篇选题输入

现有模板和脚本：

- [content-performance-log.csv](/C:/Users/Administrator/Documents/code-news/docs/templates/content-performance-log.csv)
- [generate_content_performance_report.py](/C:/Users/Administrator/Documents/code-news/scripts/generate_content_performance_report.py)

执行方式：

1. 每天同步一次最近表现到 `.tmp/latest-content-performance-log.csv`
2. 每周至少生成一次表现周报
3. 周报不只看“谁阅读高”，还要看：
   - 谁的点赞率高
   - 谁的评论率高
   - 谁更有收藏价值
4. 每周固定输出 3 条可执行调整：
   - 哪种标题继续放大
   - 哪种开头需要减少
   - 哪种话题值得继续做

## P4：把同行样本变成改稿输入

现有脚本和模板：

- [generate_peer_content_insights.py](/C:/Users/Administrator/Documents/code-news/scripts/generate_peer_content_insights.py)
- [viral-post-review-template.md](/C:/Users/Administrator/Documents/code-news/docs/templates/viral-post-review-template.md)
- [weekly-improvement-board-template.md](/C:/Users/Administrator/Documents/code-news/docs/templates/weekly-improvement-board-template.md)

以后不是“看到爆文觉得不错”，而是固定做：

1. 收集同行样本
2. 拆标题承诺、开头结构、信息密度、互动设计
3. 提炼成“下篇就能改”的动作
4. 写进每周改进板

最低要求：

- 每周深拆至少 6 篇高表现内容
- 每篇拆解至少产出 3 条可执行动作

## 每天的固定操作

### 上午

1. 跑发布 readiness
2. 确定今天哪些平台进入正式计划
3. 选题时先看上周高表现结构，不再纯凭感觉选题

### 写稿阶段

1. 先写深度主版本
2. 再拆平台化标题和开头
3. 发布前跑质量闸门

### 下午或发后

1. 同步最近表现数据
2. 记录当天发布结果
3. 对早期表现异常的内容做快复盘

## 每周的固定产出

1. 一份发布稳定性状态表
2. 一份表现周报
3. 一份同行拆解报告
4. 一份下周改进板

## 成功标准

### 发布

- 4 平台不再“写完后才发现发不出去”
- 发布失败主要集中在可预见问题，而不是随机问题
- 小红书和头条的失败率下降

### 文本质量

- 被质量闸门打回的内容有明确共性
- 同一类低竞争力标题不再重复出现
- 平台化改稿变成固定动作

### 流量

- 每周都能明确说出哪类标题在涨，哪类在掉
- 每周至少有 1 到 2 个结构被确认值得继续放大
- 改稿动作能在下一周数据里看到反馈

## 建议的直接执行顺序

今天开始就按这个顺序跑：

1. `python scripts/run_daily_content_ops.py`
2. 如需额外查看原始预检明细，再跑 `python scripts/check_publish_readiness.py --format markdown`
3. 每篇发前过 [pre-publish-quality-gate-template.md](/C:/Users/Administrator/Documents/code-news/docs/templates/pre-publish-quality-gate-template.md)
4. 每周用 [weekly-improvement-board-template.md](/C:/Users/Administrator/Documents/code-news/docs/templates/weekly-improvement-board-template.md) 固定沉淀改进动作

新增产出物：

- [daily-content-ops-brief.md](/C:/Users/Administrator/Documents/code-news/.tmp/daily-content-ops-brief.md)
- [daily-content-ops-state.json](/C:/Users/Administrator/Documents/code-news/.tmp/daily-content-ops-state.json)

固定节奏参考：

- [four-platform-posting-schedule.md](/C:/Users/Administrator/Documents/code-news/docs/four-platform-posting-schedule.md)

## 最后的取舍

接下来一周，最重要的不是把 4 平台都打磨成全自动，而是：

- 先让发布变得更可控
- 再让文本更有竞争力
- 再让流量反馈进入固定闭环

顺序不能反。
