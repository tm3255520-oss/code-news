# 公众号方向有用 Skills 短名单

更新时间：2026-05-24

## 这份文档解决什么问题

这不是对外部文章的全文复述，而是把其中**对我们当前阶段真正有用**的部分筛出来。

当前阶段的核心目标已经确定：

**用更高的内容质量，换更稳定的流量结果。**

所以筛选标准只有 3 条：

1. 能不能帮助我们提高公众号内容质量。
2. 能不能帮助我们做竞品研究、爆款拆解和选题判断。
3. 能不能作为我们现有公众号发布链路的备份或增强。

不满足这 3 条的 skill，就算功能多，也不列为当前重点。

## 一、先给结论

从这篇文章提到的大量微信相关 skill 里，**当前对我们最有用的，不是“再装一个发布器”，而是下面 4 组能力**：

1. 公众号发布备份与参考实现
2. 公众号文章写作与内容优化
3. 公众号竞品抓取、搜索与转存
4. 发布前质量闸门与发布后复盘

其中最值得我们重点关注的 skill 短名单如下：

- `jimliu/baoyu-skills@baoyu-post-to-wechat`
- `iamzhihuix/happy-claude-skills@wechat-article-writer`
- `freestylefly/wechat-article-extractor-skill@wechat-article-extractor`
- `wuchubuzai2018/expert-skills-hub@wechat-article-search`
- `steelan9199/wechat-publisher@wechat-content-optimizer`
- `jackwener/wechat-article-to-markdown`

## 二、对我们最有价值的 6 个 skill

## 1. baoyu-post-to-wechat

定位：

- 公众号发布方向里，当前最值得重点参考的公开方案

为什么对我们有用：

- 它同时支持 API 草稿发布和浏览器模拟发布
- 支持多账号管理
- 支持 Markdown 转微信友好 HTML
- 支持主题化输出和小绿书图文模式

截至 `2026-05-24` 我用 `npx skills find` 复核到的当前公开热度：

- `25.6K installs`

安装命令：

```bash
npx skills add https://github.com/jimliu/baoyu-skills --skill baoyu-post-to-wechat
```

我们该怎么用：

- **不急着安装进主流程**
- 先把它作为公众号发布链路的对标样本和备份参考实现

判断：

- **高优先级参考**

## 2. wechat-article-writer

定位：

- 公众号写作辅助里最值得关注的公开 skill 之一

为什么对我们有用：

- 它覆盖资料搜索、正文写作、标题生成和排版优化
- 比起单纯“生成一篇稿”，它更接近完整写作流程
- 适合我们后面补“研究支持 + 标题变体 + 开头优化”

安装命令：

```bash
npx skills add https://github.com/iamzhihuix/happy-claude-skills --skill wechat-article-writer
```

我们该怎么用：

- 把它作为“写作工作流参考”
- 优先借它的流程设计，不直接把生成结果视为可发终稿

判断：

- **高优先级观察对象**

## 3. wechat-article-extractor

定位：

- 公众号内容研究和竞品拆解的基础设施

为什么对我们有用：

- 能从公众号文章 URL 或 HTML 中提取完整元数据
- 适合保存对标文章信息
- 适合做后续竞品库、爆款样本库和文章结构研究

截至 `2026-05-24` 我复核到的当前公开热度：

- `3.1K installs`

安装命令：

```bash
npx skills add https://github.com/freestylefly/wechat-article-extractor-skill --skill wechat-article-extractor
```

我们该怎么用：

- 这是当前**最值得进入研究链路**的 skill 之一
- 后面如果要搭公众号同行监控，优先考虑它

判断：

- **高优先级可试用**

## 4. wechat-article-search

定位：

- 公众号文章搜索与竞品发现工具

为什么对我们有用：

- 能按关键词搜索公众号文章
- 适合快速摸赛道内容分布
- 适合配合 `wechat-article-extractor` 做“发现 + 提取”的两段式研究流程

截至 `2026-05-24` 我复核到的当前公开热度：

- `1.2K installs`

安装命令：

```bash
npx skills add https://github.com/wuchubuzai2018/expert-skills-hub --skill wechat-article-search
```

注意：

- 真实链接解析会受反爬影响，不稳定是正常现象

判断：

- **高优先级可试用**

## 5. wechat-content-optimizer

定位：

- 已有文章的二次质量优化器

为什么对我们有用：

- 它不负责发布，反而更符合我们当前阶段的重点
- 优化点集中在开头吸引力、段落节奏、标题小节、口语化表达、结尾互动设计
- 这些都和“提升阅读表现、收藏表现、评论表现”直接相关

截至 `2026-05-24` 我复核到的当前公开热度：

- `93 installs`

安装命令：

```bash
npx skills add https://github.com/steelan9199/wechat-publisher --skill wechat-content-optimizer
```

判断：

- **中优先级观察对象**

原因：

- 功能方向很对
- 但公开热度还不够高，先观察，不直接依赖

## 6. wechat-article-to-markdown

定位：

- 公众号竞品保存、拆稿和知识沉淀工具

为什么对我们有用：

- 能把公众号文章转成干净 Markdown
- 自动下载并本地化图片
- 特别适合做“拆结构、拆标题、拆段落、拆配图”的素材归档

安装方式：

```bash
uv tool install wechat-article-to-markdown
```

我们该怎么用：

- 作为竞品研究资料整理工具使用
- 不参与发布链路，专心做研究输入

判断：

- **高优先级可试用**

## 三、哪些 skill 现在不该排前面

## 1. 再装一个“纯发布器”

例如：

- `wechat-article-publisher`
- `wechat-publisher`
- `wechat-draft-publisher`

原因：

- 我们自己的公众号发布链路已经打通了
- 当前真正的瓶颈不是“能不能发”，而是“发出去的内容是否够强”

结论：

- 可以记录
- 不作为当前优先安装目标

## 2. 全自动热点到发布链路

例如：

- `wechat-ai-publisher`

原因：

- 这类 skill 很诱人，但通常外部依赖重
- 很容易把重点带回“自动化程度”而不是“内容质量”
- 当前阶段更适合把它当未来探索方向，而不是主生产方式

结论：

- 只做远期观察

## 3. 小程序开发与桌面微信自动化

例如：

- `auth-wechat-miniprogram`
- `cloudbase-document-database-in-wechat-miniprogram`
- `wechat-miniprogram-skill`
- `wechat-automation`

原因：

- 这些不属于我们当前的公众号内容增长主线

结论：

- 暂不纳入当前工具建设重点

## 四、对我们最有意义的组合方式

如果只从这篇文章里挑最适合我们的组合，推荐按下面这套来理解：

## 组合 A：竞品研究组合

- `wechat-article-search`
- `wechat-article-extractor`
- `wechat-article-to-markdown`

适用目标：

- 找到同行文章
- 把文章抓下来
- 转成可读、可拆、可归档的研究资料

这是当前最贴近“质量和流量优先”目标的一组。

## 组合 B：写作改进组合

- `wechat-article-writer`
- `wechat-content-optimizer`

适用目标：

- 补资料搜索与写作流程
- 优化标题、开头、结构、结尾互动

这组的价值不是“代写”，而是帮我们形成更稳定的高质量写作流程。

## 组合 C：发布备份组合

- `baoyu-post-to-wechat`

适用目标：

- 作为我们现有公众号发布链路的参考实现或备份方案

这组不需要立刻装，但值得长期关注。

## 五、建议的执行顺序

如果后面真的要动手引入外部 skill，顺序建议固定成这样：

1. 先试 `wechat-article-search`
2. 再试 `wechat-article-extractor`
3. 再试 `wechat-article-to-markdown`
4. 再评估 `wechat-article-writer`
5. 最后才考虑 `baoyu-post-to-wechat`

原因：

- 前三者直接增强研究和竞品拆解
- 写作辅助放在第二阶段更合理
- 发布类 skill 当前不是第一痛点

## 六、和我们现有体系怎么衔接

这篇文章最值得我们吸收的，不是“收集了很多微信 skill”，而是它提醒了我们公众号工具链应该覆盖这些环节：

1. 找题材
2. 找样本
3. 抓内容
4. 做拆解
5. 改自己的稿
6. 再发布

这和我们已经确定的路线是吻合的：

- [quality-traffic-tooling-roadmap.md](C:/Users/Administrator/Documents/code-news/docs/quality-traffic-tooling-roadmap.md)
- [peer-monitoring-workflow.md](C:/Users/Administrator/Documents/code-news/docs/peer-monitoring-workflow.md)
- [wechat-publish-runbook.md](C:/Users/Administrator/Documents/code-news/docs/wechat-publish-runbook.md)
- [pre-publish-quality-gate-template.md](C:/Users/Administrator/Documents/code-news/docs/templates/pre-publish-quality-gate-template.md)

## 七、一句话版结论

这篇文章里对我们最有价值的，不是“再找一个公众号发布器”，而是这 3 类能力：

1. **竞品研究**
2. **写作优化**
3. **发布备份**

按当前优先级看，最值得先动的是：

**研究类 skill 先行，写作类 skill 次之，发布类 skill 最后。**
