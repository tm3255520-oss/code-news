# 质量与流量优先的第一批工具栈

更新时间：2026-05-24

## 核心判断

既然当前阶段最重要的是把`阅读量、点赞量、评论量`做起来，那第一批工具就不能围着“更快发布”转，而要围着这 3 个问题转：

1. 什么题材更容易拿到阅读量。
2. 什么结构更容易拿到点赞量。
3. 什么表达更容易拿到评论量。

所以我已经替我们定了第一批工具方向：

- 先上研究类工具
- 再上改稿类工具
- 发布类工具先放到第二阶段

## 一、已经安装的第一批 Skill

这次我已经实际装了 4 个公众号方向工具：

1. `wuchubuzai2018/expert-skills-hub@wechat-article-search`
   - 用途：按关键词找公众号相关文章
   - 价值：强化选题发现和竞品发现

2. `freestylefly/wechat-article-extractor-skill@wechat-article-extractor`
   - 用途：从公众号文章 URL 或 HTML 提取元数据
   - 价值：沉淀竞品文章样本，支持后续拆解

3. `steelan9199/wechat-publisher@wechat-content-optimizer`
   - 用途：优化开头、结构、段落节奏、标题和结尾互动
   - 价值：直接服务点赞率和评论率提升

4. `iamzhihuix/happy-claude-skills@wechat-article-writer`
   - 用途：资料搜索、写作、标题变体与排版优化
   - 价值：帮助我们补强写作工作流，而不是直接替代判断

说明：

- 这些技能安装后通常需要重启 Codex 才会在新会话里完整生效。

## 二、暂缓安装的工具

这次我刻意没有把发布类 skill 放到第一优先级。

暂缓对象：

- `baoyu-post-to-wechat`
- `wechat-article-publisher`
- 其他纯发布或纯草稿箱工具

原因：

- 我们自己的公众号发布链路已经打通了
- 当前更稀缺的是高质量研究、改稿和复盘能力

另外有一个工具这次先记为待定：

- `wechat-article-to-markdown`

原因：

- 安装过程比普通 skill 慢很多，这次实际安装超时了
- 它仍然值得后续补装，但不影响第一批研究链路启动

## 三、这批工具分别服务哪些指标

## 阅读量

主要靠这两件事：

- 选题是否打中平台兴趣
- 标题和开头是否足够强

对应工具：

- `wechat-article-search`
- `wechat-article-writer`

## 点赞量

主要靠这两件事：

- 信息密度是否足够高
- 读者是否产生明确认同和收藏冲动

对应工具：

- `wechat-content-optimizer`
- `wechat-article-writer`

## 评论量

主要靠这两件事：

- 内容里是否有值得讨论的判断
- 结尾是否留出了互动空间

对应工具：

- `wechat-content-optimizer`
- `wechat-article-search`

## 四、我补上的本地工具

除了装 skill，我还补了两个本地产物，确保数据能沉淀下来。

## 1. 表现记录模板

- [content-performance-log.csv](C:/Users/Administrator/Documents/code-news/docs/templates/content-performance-log.csv)

用途：

- 记录每篇内容的阅读、点赞、评论、收藏、分享、涨粉

## 2. 表现周报生成脚本

- [generate_content_performance_report.py](C:/Users/Administrator/Documents/code-news/scripts/generate_content_performance_report.py)

用途：

- 从 CSV 自动生成 Markdown 周报
- 自动输出阅读 Top 5、点赞率 Top 5、评论率 Top 5 和综合分 Top 5
- 帮我们更快发现什么题材和标题结构更强

示例命令：

```bash
python scripts/generate_content_performance_report.py docs/templates/content-performance-log.csv --output .tmp/content-performance-report.md
```

## 五、这批工具怎么串起来用

标准流程应该固定成这样：

1. 用 `wechat-article-search` 找公众号相关高表现内容。
2. 用 `wechat-article-extractor` 把重点文章变成结构化样本。
3. 按 [peer-monitoring-workflow.md](C:/Users/Administrator/Documents/code-news/docs/peer-monitoring-workflow.md) 做单篇爆款复盘。
4. 用 `wechat-content-optimizer` 优化我们自己的文章开头、结构和结尾互动。
5. 发布前走 [pre-publish-quality-gate-template.md](C:/Users/Administrator/Documents/code-news/docs/templates/pre-publish-quality-gate-template.md)。
6. 发布后把数据记入 [content-performance-log.csv](C:/Users/Administrator/Documents/code-news/docs/templates/content-performance-log.csv)。
7. 用脚本生成周报，决定下周继续放大什么、停止什么。

## 六、接下来最重要的两步

1. 用这 4 个已安装工具，跑出第一批公众号竞品样本。
2. 开始记录我们自己的内容表现数据，形成第一份真实周报。

现在我们缺的已经不是“能不能发”，而是“能不能稳定看懂什么内容会爆、为什么爆、下一篇该怎么改”。

## 七、一句话结论

第一批工具已经按“质量和流量优先”原则定好了：

**先强化研究、拆解、改稿和复盘，再考虑是否继续加自动发布能力。**
