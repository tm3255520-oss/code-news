# 同行监控与质量改进方案

更新时间：2026-05-24

## 结论先行

“监控同行”和“怎么改进”这两件事，确实是下一阶段最关键的增长杠杆。

我查完现有 skills 和资料后的结论是：

1. `监控同行` 这件事，小红书已经有比较合适的 skill 可以直接承接。
2. `怎么改进` 这件事，有通用分析 skill 可以辅助，但还不能完全替代我们自己的内容判断。
3. 今日头条这边，目前没有找到一个足够成熟、足够可信、能直接替代我们自建监控链路的“同行监控 skill”。
4. 所以最合理的做法不是“完全交给 skill”，而是：
   - 小红书：优先用现成 skill 做数据采集和竞品分析
   - 头条：保留我们自己的采集/观察链路
   - 改进方法论：用高质量通用 skill 做分析框架辅助，但最终形成我们自己的固定复盘模板

## 一、我查到的 skill 现状

### 1. 已经在本地可直接用的 skill

当前工作区已经有一套小红书技能：

- `xhs-content-ops`
- `xhs-explore`
- `xhs-publish`
- `xhs-interact`

其中最关键的是 `xhs-content-ops`。

它的说明里明确写了支持：

- 竞品分析
- 热点追踪
- 内容创作
- 互动管理

并且它组合了：

- 搜索笔记
- 查看详情
- 看用户主页
- 获取互动数据

这意味着：

- 对“小红书同行监控”这件事，它已经不是“能不能凑合用”，而是“就是为这个场景设计的”

### 2. 用 `find-skills` 搜到的候选 skill

我按“同行监控 / 内容分析 / 社媒运营”搜了一轮，比较值得看的有这些：

#### 小红书方向

1. `autoclaw-cc/xiaohongshu-mcp-skills@xiaohongshu`
   - 安装量：2.2K
   - GitHub 仓库：`autoclaw-cc/xiaohongshu-skills`
   - GitHub Stars：1.1k
   - 适合：搜索、详情、用户主页、发布、互动、复合运营
   - 判断：成熟度高，和我们本地已有 skill 家族非常接近，可信度高

2. `softbread/xiaohongshu-doctor@xiaohongshu-note-analyzer`
   - 安装量：2.5K
   - GitHub 仓库：`softbread/xiaohongshu-doctor`
   - GitHub Stars：1
   - 判断：安装量和仓库体量严重不匹配，可信度不足，不建议作为主方案

#### 通用竞品 / 内容分析方向

1. `aaron-he-zhu/seo-geo-claude-skills@competitor-analysis`
   - 安装量：4.3K
   - GitHub Stars：1.8k
   - 适合：竞品分析、内容差距分析、结构化研究
   - 判断：成熟度高，但它是通用分析框架，不是小红书或头条原生采集器

2. `apify/agent-skills@apify-content-analytics`
   - 安装量：2.5K
   - GitHub Stars：2.1k
   - 适合：抓 engagement 数据、做跨平台内容表现分析
   - 限制：需要 `APIFY_TOKEN`，而且强项是国外平台和 Apify Actor 生态，不是天然适配头条/小红书

3. `coreyhaines31/marketingskills@content-strategy`
   - 安装量：74.5K
   - 适合：内容策略思考
   - 限制：更偏方法论，不解决中国平台的一手数据采集问题

#### 今日头条方向

1. `guanyang/super-publisher@toutiao-publisher`
   - 安装量：830
   - GitHub Stars：19
   - 能力：自动发布头条
   - 判断：能做发布，不解决“监控同行”和“质量改进”

2. `wuchubuzai2018/expert-skills-hub@toutiao-news-trends`
   - 安装量：243
   - 判断：更像热点趋势，不像账号级竞品监控

### 3. 最终判断

如果只看“能不能替代我们自己写规则”，答案是：

- 小红书：`可以替代一大半`
- 今日头条：`只能替代很少一部分`
- 质量改进：`可以辅助，但不能完全替代`

## 二、这两个核心问题分别怎么解

## 1. 第一件事：监控同行

这件事本质上不是“看几个爆款”，而是做一个稳定的监控面板。

### 小红书

小红书可以直接基于现有 skill 来做：

- 关键词搜索
- 同类账号主页跟踪
- 爆款笔记详情抓取
- 点赞 / 收藏 / 评论量观察
- 标题、封面、正文结构复盘

最适合的 skill 组合：

- 主技能：`xhs-content-ops`
- 补充技能：`xhs-explore`

我认为这已经足够承担：

- 同行爆款监控
- 热点话题追踪
- 爆文结构拆解

### 今日头条

今日头条目前没有找到一个像小红书那样成熟的“竞品分析 skill”。

所以头条这边更现实的做法是：

- 继续保留我们自己的页面采集或人工核查链路
- 重点抓：
  - 同类账号标题
  - 发布时间
  - 封面形式
  - 阅读量
  - 评论量
  - 点赞量
  - 选题方向

也就是说：

- 小红书可以优先用 skill
- 头条还需要我们自建流程

## 2. 第二件事：怎么改进

这件事不能只停在“哪个标题好看”，而要形成固定诊断维度。

我建议每篇同行爆款都从下面 7 个维度拆：

1. 选题
   - 它讲的是热点、教程、观点、踩坑、新闻解释，还是工具清单

2. 标题
   - 是结果导向、冲突导向、身份代入、提问式，还是清单式

3. 封面
   - 是单图、三图、信息卡、情绪图，还是对比图

4. 开头
   - 前 2 到 4 句是否快速给结论

5. 正文结构
   - 是“结论先行”，还是“背景 - 细节 - 结论”

6. 互动设计
   - 有没有天然引评论的问题、立场冲突、可讨论点

7. 平台适配
   - 小红书偏“个人体验感 + 可收藏”
   - 头条偏“观点明确 + 信息密度高 + 可讨论”

这部分最适合用通用分析 skill 做“第二层总结”，不适合直接让 skill 代替结论。

推荐辅助 skill：

- `aaron-he-zhu/seo-geo-claude-skills@competitor-analysis`
- `coreyhaines31/marketingskills@content-strategy`

但它们的角色应是：

- 帮我们把爆款拆得更结构化
- 帮我们找内容差距和改进点

而不是：

- 直接替我们决定下一篇写什么

## 三、我建议的最终策略

不要试图用一个 skill 一把梭。

最优解是“三层结构”：

### 第一层：采集层

目标：把同行内容和数据稳定抓回来。

建议：

- 小红书：用 `xhs-content-ops` / `xhs-explore`
- 头条：用我们自己的链路

### 第二层：分析层

目标：解释“为什么它做得好”。

建议：

- 用 `competitor-analysis` 这类通用 skill 做结构化分析
- 固定按 7 维模板复盘

### 第三层：改进层

目标：把分析结果真正改到我们的内容生产里。

改进动作至少要落到：

- 选题方向
- 标题模板
- 封面样式
- 正文结构
- 评论引导设计

## 四、我不建议走的路

### 1. 不建议完全依赖“通用社媒分析 skill”

原因：

- 大多数这类 skill 更偏 Instagram / TikTok / YouTube
- 它们对小红书和头条的原生理解不够深

### 2. 不建议把“安装量高”直接等同于“适合我们”

比如：

- `softbread/xiaohongshu-doctor@xiaohongshu-note-analyzer` 安装量看起来不低
- 但仓库只有 1 star
- 这种信号不一致，不能作为主力依赖

### 3. 不建议今天就去重装很多新 skill

原因：

- 我们本地已经有足够强的小红书 skill
- 真正缺的是“监控模板”和“复盘机制”，不是 skill 数量

## 五、我给你的明确建议

如果按“先用现成 skill，避免自己重新编规则”的原则来做，我的建议是：

1. 小红书同行监控：
   - 直接用我们现有的 `xhs-content-ops`
   - 这部分不需要另起炉灶

2. 头条同行监控：
   - 不要期待现成 skill 能完全接住
   - 这部分保留我们自己的观察和采集流程

3. 质量改进方法：
   - 可以借助 `competitor-analysis` / `content-strategy`
   - 但最终要沉淀成我们自己的复盘模板

## 六、下一步最值得做的不是继续找 skill

下一步最值得做的是把这个系统真正落成固定工作流：

1. 建一个“同行池”
   - 头条 10 个账号
   - 小红书 10 个账号

2. 建一个“爆款采样规则”
   - 阅读高
   - 点赞高
   - 评论高
   - 最近 7 天内

3. 建一个“固定复盘模板”
   - 标题
   - 封面
   - 开头
   - 结构
   - 互动点
   - 可复用动作

4. 建一个“改稿动作清单”
   - 我们下一篇要改哪些点

## 七、最终结论

你的判断是对的：

- 平台规则和发布链路只是起点
- 质量和流量才是决定成败的核心

而在这一步上，最佳路线不是“继续写更多发布规则”，而是：

- 用 skill 帮我们抓同行和拆同行
- 再把拆出来的规律，变成我们自己的内容改进系统

截至 2026-05-24，我的明确结论是：

- 小红书：现成 skill 足够强，可以直接进入“监控同行”阶段
- 头条：没有找到足够成熟的竞品监控 skill，仍应保留自建链路
- 改进质量：有辅助 skill，但真正的护城河会是我们自己的复盘体系

## 参考来源

- 本地 skill：`xhs-content-ops`、`xhs-explore` 的 SKILL.md 与 README
- skills.sh 搜索结果：
  - `autoclaw-cc/xiaohongshu-mcp-skills@xiaohongshu`
  - `aaron-he-zhu/seo-geo-claude-skills@competitor-analysis`
  - `apify/agent-skills@apify-content-analytics`
  - `guanyang/super-publisher@toutiao-publisher`
- GitHub 仓库成熟度：
  - `autoclaw-cc/xiaohongshu-skills`
  - `aaron-he-zhu/seo-geo-claude-skills`
  - `apify/agent-skills`
  - `guanyang/super-publisher`
