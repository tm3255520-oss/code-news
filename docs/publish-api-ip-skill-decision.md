# 多平台发布方案决策表：API、固定 IP、发布 Skill

更新时间：2026-05-26

## 先说结论

围绕你这次提出的 3 个问题，我的最终判断是：

1. **API 能用就优先用 API。**
   目前四个平台里，最明确适合改成官方 API 主链路的是微信公众号。
2. **固定 IP 不是四个平台统一都必须，但公众号 API 路线要认真考虑。**
   微信官方文档已明确提到 API IP 白名单；如果我们自己托管服务端发布，最好按“固定出口 IP”来设计。  
   但如果走微信云托管的云调用，官方文档又明确说不需要配置 IP 白名单。
3. **有发布 skill，不代表有官方 API。**
   很多 skill 的本质只是把浏览器自动化封装了一层。  
   对稳定性真正有帮助的是：官方 API、持久会话、登录健康检查、发布后验收。

## 平台决策总表

| 平台 | 官方公开发布 API | 当前是否建议对接 API | 固定 IP 是否要重点考虑 | 专门发布 skill 情况 | 当前最优路线 |
| --- | --- | --- | --- | --- | --- |
| 微信公众号 | 有，已核实草稿和发布接口 | 是，强烈建议 | 是，若自建服务端需重点考虑；走微信云托管可弱化 | 有，而且不少 | 自建官方 API 主链路 |
| 今日头条 | 未核实到公开创作者文章发布 API | 否，暂不建议按“公开 API”立项 | 浏览器路线不是硬要求，但稳定网络有帮助 | 有，但本质多为浏览器自动化 | 继续浏览器自动化 |
| 小红书 | 未核实到桌面创作者后台长文公开发布 API；有分享 SDK/开放平台 | 否，暂不建议重构到 SDK 路线 | 浏览器路线不是硬要求，但稳定网络有帮助 | 有，但多为 CDP/浏览器会话型 | 继续浏览器自动化 |
| 知乎 | 未核实到公开专栏文章发布 API | 否 | 浏览器路线不是硬要求 | 几乎没有成熟发布 skill | 继续浏览器自动化 |

## 1. API 这件事，到底要不要

### 微信公众号

要，而且是当前最值得做的改造。

这次核实到的微信官方能力包括：

- [新增草稿](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)
- [发布草稿](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html)
- [发布状态查询](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html)
- [获取已发布图文信息](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle.html)

这说明公众号可以做成完整的服务端链路：

1. 上传图片/素材
2. 创建草稿
3. 提交发布
4. 查询发布状态
5. 获取正式文章链接

这条线比浏览器自动化更适合做正式生产主链路。

### 今日头条

我这次**没有核实到一个公开可自助申请的“头条号图文文章发布 API”**。  
我核到的官方开放平台公开重点仍然是营销、投放、报表、素材管理，见 [巨量引擎开放平台](https://open.oceanengine.com/)。

所以当前更准确的结论不是“我们应该赶快对接头条 API”，而是：

- **我没有确认到一个现在就能直接接的公开创作者发文 API**
- 如果以后拿到的是企业合作、私有接口、商务接入权限，那是另一条线
- 但在当前信息下，不适合把头条规划成“API-first”

换句话说：

**今日头条现在最现实的主路线，仍然是浏览器自动化，不是公开 API 对接。**

### 小红书

我没有核实到适合我们当前桌面长文后台工作流的公开发文 API。  
当前官方可见的是：

- [小红书开放平台](https://ad-market.xiaohongshu.com/)
- [小红书分享开放平台](https://agora.xiaohongshu.com/)
- [小红书小程序开放平台](https://miniapp.xiaohongshu.com/)

这里要区分清楚：

- 分享开放平台更像“把内容分享到小红书 App”
- 它不等于“桌面创作者后台长文发布 API”

所以短期不建议为小红书单独重构一套 SDK 发布链。

### 知乎

我在当前公开的 [知乎开放平台](https://developer.zhihu.com/) 里，没有核实到“专栏文章发布 API”。  
目前更像是搜索、热榜、直答等数据能力入口。

结论：

- 不适合按“官方发文 API”立项
- 浏览器自动化仍然是现实方案

## 2. 固定 IP 到底要不要

### 微信公众号：要认真考虑

这件事微信官方文档是有明确信号的。

在 [服务端 API 调用说明](https://developers.weixin.qq.com/doc/service/guide/dev/api/) 里，微信官方明确写到：

- 开发者可修改 `API IP 白名单`
- 白名单内 IP 才可以调用获取接口调用凭据的接口
- 否则会提示 `61004` 错误

同一页文档还有两个非常关键的补充：

1. 如果使用**微信云托管**的云调用，**无需配置 IP 白名单**
2. 对于有风险的调用，平台可能返回 `89503`，并要求管理员确认该 IP 可调用

这对我们意味着：

- 如果我们自己在本机或自建服务器上做公众号 API 发布，**最好按固定出口 IP 来设计**
- 如果不想处理白名单和出口 IP，**优先考虑微信云托管**

所以公众号 API 方案有两个子方案：

#### 方案 A：自建服务端 API 发布

条件：

- 有 `AppID`
- 有 `AppSecret`
- 服务端调用
- 能管理 `API IP 白名单`
- 最好有固定出口 IP

#### 方案 B：微信云托管云调用

条件：

- 接受微信云托管体系
- 愿意把发布服务部署到微信云侧

优点：

- 官方文档明确说**无需配置 IP 白名单**
- 更适合稳定长期跑

### 今日头条 / 小红书 / 知乎：没有查到官方“固定 IP”硬要求

这里我分两层说。

#### 已核实部分

截至 `2026-05-26`，我**没有在当前公开官方开发者入口里核实到**：

- 头条创作者发文 API 的固定 IP 要求
- 小红书创作者后台发文 API 的固定 IP 要求
- 知乎专栏发布 API 的固定 IP 要求

#### 工程判断

对当前浏览器自动化路线来说，固定 IP **不是硬门槛**，但它是明显有帮助的。

帮助体现在：

- 登录态更稳定
- 风控更少
- 会话复用更持久
- 异地登录和异常设备提醒更少

所以对这三个平台，我的建议不是“必须固定 IP”，而是：

- **不要频繁切换网络**
- **不要挂来回切换的代理/VPN**
- **最好固定在同一台机器、同一网络、同一浏览器 profile 上发布**

也就是说：

- 公众号 API：固定 IP 是设计重点
- 其余三个浏览器流：固定 IP 不是硬要求，但稳定网络环境很重要

## 3. 有没有专门的发布 Skill

有，但要分成两类看：

1. **官方 API 型**
2. **浏览器自动化型**

真正更稳的，是前者。

### 微信公众号相关

#### `iamzifei/wechat-article-publisher-skill@wechat-article-publisher`

- `npx skills find wechat publish` 结果：`2K installs`
- GitHub：`139 stars`
- 说明：README 明确写的是 **API-based publishing**
- 但它不是我们直接拿公众号官方 `AppID/AppSecret` 去调，而是依赖第三方：
  - `WECHAT_API_KEY`
  - [wx.limyai.com](https://wx.limyai.com)

判断：

- 它说明“公众号 API 化”这条方向是成立的
- 但如果我们追求主链路稳定和可控，**更建议自己直连微信官方 API**
- 不建议把正式生产主链路压在第三方中转 API Key 上

#### `0731coderlee-sudo/wechat-publisher@wechat-publisher`

- `618 installs`
- GitHub：`37 stars`
- README 表明它是基于 `wenyan-cli`
- 本质更像“Markdown -> 微信草稿箱”的现成封装

判断：

- 适合参考
- 但不是我们最优主方案

### 今日头条相关

#### `guanyang/super-publisher@toutiao-publisher`

- `839 installs`
- GitHub：`19 stars`
- 它自己的 README 明确写了：**基于 Playwright，核心理念是模拟真实用户行为，而非简单 API 调用**

这个信息很关键。

说明什么？

- 它不是“官方 API skill”
- 它本质也是浏览器自动化
- 只是把登录、状态复用、发布流程封装得更像产品

判断：

- 有参考价值
- 不能当作“头条官方 API 已经有成熟 skill”的证据

### 小红书相关

#### `iamzifei/red-publisher-skill@xiaohongshu-publisher`

- `208 installs`
- GitHub：`8 stars`
- README 明确写的是：**Uses CDP mode to connect to your existing browser session**

这也说明它本质是浏览器会话自动化，不是官方发文 API。

判断：

- 有
- 但成熟度一般
- 而且和我们当前本地已经打磨过的小红书链路本质接近

### 知乎相关

我这次用 `npx skills find zhihu publish` 和 `npx skills find zhihu article` 继续查了，**没有看到成熟的知乎文章发布 skill**。  
出来的结果更多是搜索、热榜、内容编辑侧能力，不是正式发布器。

判断：

- 知乎这块短期内不要指望外部 publish skill
- 自己维护链路反而更靠谱

## 修正后的平台判断

### 微信公众号

修正后结论：

- **最优路线：自建官方 API 发布器**
- 备选路线：浏览器自动化兜底
- 设计重点：`AppID/AppSecret`、发布素材结构、发布状态轮询、IP 白名单或微信云托管

### 今日头条

修正后结论：

- **不要先假设“公开 API 一定有而且值得接”**
- 目前未核实到公开创作者文章发布 API
- 外部 skill 也主要是浏览器模拟，不是官方 API
- 现阶段最优路线仍是：**强化浏览器自动化 + 持久化登录 + 发布后列表验收**

### 小红书

修正后结论：

- 官方公开能力更偏分享和开放平台，不等于桌面后台发文 API
- 外部 publish skill 也主要是浏览器/会话型
- 最优路线仍是：**继续维护我们自己的浏览器发布链**

### 知乎

修正后结论：

- 当前没有发现成熟 publish skill，也没核实到公开发文 API
- 最优路线仍是：**自己的专用浏览器自动化**

## 现在应该怎么改我们的方案

基于这次补查，方案要这样调整：

### 第一优先级

做 `wechat-api-publisher`，并且从一开始就按两条路选一条：

1. 自建服务端 + 固定出口 IP + 白名单
2. 微信云托管 + 云调用

这一步是唯一一个能同时解决：

- 登录复杂
- 反复扫码
- 浏览器 DOM 脆弱
- 发布状态难确认

### 第二优先级

不要为今日头条盲目立“官方 API 对接”项目。

正确做法是：

- 先把它定义成浏览器自动化平台
- 把标题校验、封面策略、列表验收、登录态复用做稳
- 如果将来真拿到公开可用的创作者 API 或商务接口，再切

### 第三优先级

给其余三个浏览器平台补统一会话层：

- 固定 profile
- 固定端口
- 固定启动器
- 固定登录探针
- 固定发布后验收

## 我的最终判断

如果只用一句话回答你这次的三个问题：

**公众号值得立刻 API 化，且要认真处理 IP 白名单或直接走微信云托管；头条、小红书、知乎目前都还不适合按“公开发文 API”主导设计，外部 publish skill 也大多只是浏览器自动化封装。**

## 参考链接

### 官方

- 微信服务端 API 调用说明：[https://developers.weixin.qq.com/doc/service/guide/dev/api/](https://developers.weixin.qq.com/doc/service/guide/dev/api/)
- 微信新增草稿：[https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)
- 微信发布草稿：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html)
- 微信发布状态查询：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html)
- 微信获取已发布图文信息：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle.html)
- 知乎开放平台：[https://developer.zhihu.com/](https://developer.zhihu.com/)
- 巨量引擎开放平台：[https://open.oceanengine.com/](https://open.oceanengine.com/)
- 小红书开放平台：[https://ad-market.xiaohongshu.com/](https://ad-market.xiaohongshu.com/)
- 小红书分享开放平台：[https://agora.xiaohongshu.com/](https://agora.xiaohongshu.com/)
- 小红书小程序开放平台：[https://miniapp.xiaohongshu.com/](https://miniapp.xiaohongshu.com/)

### Skill / 仓库

- `iamzifei/wechat-article-publisher-skill@wechat-article-publisher`：[https://skills.sh/iamzifei/wechat-article-publisher-skill/wechat-article-publisher](https://skills.sh/iamzifei/wechat-article-publisher-skill/wechat-article-publisher)
- 仓库：[https://github.com/iamzifei/wechat-article-publisher-skill](https://github.com/iamzifei/wechat-article-publisher-skill)
- `0731coderlee-sudo/wechat-publisher@wechat-publisher`：[https://skills.sh/0731coderlee-sudo/wechat-publisher/wechat-publisher](https://skills.sh/0731coderlee-sudo/wechat-publisher/wechat-publisher)
- 仓库：[https://github.com/0731coderlee-sudo/wechat-publisher](https://github.com/0731coderlee-sudo/wechat-publisher)
- `guanyang/super-publisher@toutiao-publisher`：[https://skills.sh/guanyang/super-publisher/toutiao-publisher](https://skills.sh/guanyang/super-publisher/toutiao-publisher)
- 仓库：[https://github.com/guanyang/super-publisher](https://github.com/guanyang/super-publisher)
- `iamzifei/red-publisher-skill@xiaohongshu-publisher`：[https://skills.sh/iamzifei/red-publisher-skill/xiaohongshu-publisher](https://skills.sh/iamzifei/red-publisher-skill/xiaohongshu-publisher)
- 仓库：[https://github.com/iamzifei/red-publisher-skill](https://github.com/iamzifei/red-publisher-skill)
