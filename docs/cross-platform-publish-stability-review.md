# 多平台发布链路复盘与降复杂度建议

更新时间：2026-05-26

## 结论先行

这四个平台里，当前最应该换方案的是微信公众号，最应该继续工程化加固的是知乎、今日头条和小红书。

一句话判断：

- 微信公众号：有更稳的官方 API 路线，应该从“浏览器优先”切到“API 优先，浏览器兜底”。
- 知乎：当前浏览器链路已经够用，短期内没有更强的官方公开发文 API 可替代。
- 今日头条：当前链路可用，但平台约束多、编辑器规则细，仍然属于高脆弱链路。
- 小红书：当前链路可用，但 DOM 漂移风险明显；官方公开能力更偏“分享到 App”，不等于桌面端后台发文 API。

## 当前链路复盘

| 平台 | 当前方式 | 已验证状态 | 人工介入点 | 当前主要脆弱点 |
| --- | --- | --- | --- | --- |
| 微信公众号 | 专用可控 Chrome + CDP/Playwright | 可发文、可插图、可选封面、可发表 | 最后一步微信验证扫码 | 最终安全校验不是脚本可绕过；封面流程有独立校验 |
| 知乎 | 专用可控 Chrome + CDP/Playwright | 可写标题、正文、配图、封面、正式发布 | 基本无固定人工门槛 | 仍依赖页面结构和登录态 |
| 今日头条 | 专用可控 Chrome + CDP/Playwright | 可写标题、正文、配图、发布并回列表验收 | 通常无固定人工门槛 | 标题计数、封面行为、列表验收都容易出边角问题 |
| 小红书 | 专用浏览器端口 + 自动化脚本 | 可写长文、配图、发布 | 登录态失效时需人工登录 | 编辑器结构变化快，发布页状态切换复杂 |

## 复杂度与稳定性判断

如果看“当前已经跑通的浏览器链路”，复杂度从低到高大致是：

1. 知乎
2. 微信公众号
3. 小红书
4. 今日头条

如果看“长期最值得投入的稳定方案”，排序会变成：

1. 微信公众号 API 化
2. 知乎浏览器链路加固
3. 小红书浏览器链路加固
4. 今日头条浏览器链路加固

原因很简单：

- 微信公众号是四个平台里唯一一个我已经核实到存在官方草稿和发布 API 的平台，最有机会把“扫码登录 + DOM 脆弱”一起降下去。
- 知乎当前链路最顺，页面反馈也最清晰，适合继续用浏览器自动化。
- 小红书和今日头条都能做，但更像“工程上把不稳定因素一层层包住”，不是“天然简单”。

## 官方替代方案复核结果

### 1. 微信公众号

官方文档已明确提供：

- 草稿箱新增接口 `draft_add`
- 草稿发布接口 `freepublish_submit`
- 发布状态查询接口 `freepublish_get`
- 已发布图文查询接口 `freepublishGetarticle`

这意味着公众号完全可以改成：

1. 服务端上传图片和素材
2. 服务端创建草稿
3. 服务端提交发布
4. 服务端轮询发布状态
5. 仅在必要时人工做最终运营确认

这个方案的价值最大：

- 不再依赖浏览器 DOM
- 不再要求每次走网页登录
- 不再要求每次由你手工扫码登录后台
- 发布后可以直接用 API 查状态，而不是盯着页面猜

需要注意：

- 前提是账号具备对应接口能力，且我们能拿到 `appid/appsecret` 或可用的授权调用凭证
- 需要把正文 HTML、图片上传、封面素材、摘要等都改成 API 兼容格式
- “平台最终风控”仍可能存在，但它和“后台扫码登录”已经不是一回事

结论：**公众号应该优先改成 API-first。**

### 2. 知乎

我这次复核到的知乎官方开发者站，当前公开重点是：

- 知乎搜索 API
- 全网搜索 API
- 直答 API
- 热榜 API

我没有在当前公开开发者入口里核实到“专栏文章发布 API”。

这意味着：

- 目前公开可验证的知乎官方能力，更偏数据和检索，不是创作者文章发布
- 我们现有的浏览器自动化，短期内仍然是最现实的发文路径

结论：**知乎继续用浏览器自动化，但把登录态、草稿、发布后校验做得更工程化。**

### 3. 今日头条

我这次复核到的巨量/头条官方开放能力，公开重点仍是：

- Marketing API
- 营销投放
- 数据报表
- 素材管理

我没有核实到公开的“头条号图文文章发布 API”。

这意味着：

- 当前官方公开开放平台，核心是广告和营销，不是创作者文章发布
- 对我们来说，能稳定发文的现实路径仍然是浏览器自动化

结论：**今日头条暂时没有明显更好的公开替代方案，只能继续加固浏览器链路。**

### 4. 小红书

我这次复核到的小红书官方公开能力，分成两类：

- 开放平台：偏营销、商家、数据、消息、小程序
- 分享开放平台：偏“把内容分享到小红书 App”，基于小红书 App 内置发布能力

我没有核实到适合我们当前桌面工作流的“创作者后台文章/长文发布 API”。

但有一个值得注意的方向：

- 官方分享 SDK 明确支持把图文/视频内容分享到小红书
- 它更像“第三方 App 调起小红书发笔记”
- 它不是我们现在这种“桌面浏览器后台发布”的直接替代品

所以短期结论是：

- 桌面自动化继续保留浏览器路线
- 如果以后愿意做一个手机端或桌面 App 中转器，再评估分享 SDK

结论：**小红书当前最现实的仍是浏览器自动化，不建议现在为它重构整套移动分享链。**

## 为什么你会感觉“又复杂又不够稳”

你的感觉是对的。根因不是我们代码太差，而是现在混用了两类完全不同的机制：

- 一类是“官方支持的接口能力”
- 一类是“登录后网页编辑器自动化”

网页自动化天然会遇到这几类问题：

1. 页面结构会改
2. 按钮文案会变
3. 发布前校验经常是隐式的
4. 登录态会过期
5. 平台风控会额外插入人工确认

所以现在这套链路的真实评价应该是：

- 已经可用
- 但还不够优雅
- 也还没有到“完全不打扰你”的程度

## 重复扫码登录的根因

重复扫码，实际上有三种不同来源，不能混为一谈：

### 1. 后台登录态失效

这类扫码，本质是浏览器 cookie 过期或专用 profile 没复用好。

### 2. 平台发布安全验证

这类扫码最典型的是公众号正式发表前的微信验证。

它不是“没登录”，而是“平台要求你在关键动作上二次确认”。

### 3. 自动化实例没有固定复用

如果每个平台都不是固定 `user-data-dir + 端口 + 专用入口`，就会更容易反复要求登录。

## 接下来最该做的改造

### 第一优先级：把公众号切到 API-first

建议目标：

1. 新建 `wechat-api-publisher`
2. 用官方接口完成素材上传、草稿创建、发布提交、状态轮询
3. 浏览器链路只保留为调试、兜底或人工复核

这是唯一一个能明显减少扫码、明显减少 DOM 风险的平台。

### 第二优先级：做统一的“会话管理层”

建议给四个平台都加一个固定规则：

1. 固定专用 profile 目录
2. 固定远程调试端口
3. 固定启动脚本
4. 固定登录健康检查命令
5. 发布前先跑健康检查，不健康就先提醒登录，不直接跑发布

推荐落地目标：

- `browser-profiles/wechat-automation`
- `browser-profiles/zhihu-automation`
- `browser-profiles/toutiao`
- `browser-profiles/xhs-automation`

以及统一命令：

- `check-login --platform wechat`
- `check-login --platform zhihu`
- `check-login --platform toutiao`
- `check-login --platform xhs`

### 第三优先级：把发布流程拆成三段

不要再让“内容生成”和“真正点击发布”混成一步。

建议固定为：

1. `prepare`：生成文章、配图、平台改写稿
2. `draft`：写入编辑器或写入草稿/API
3. `publish`：只负责最终提交和发布后验收

这样做的好处是：

- 失败范围更小
- 调试成本更低
- 不容易误发
- 你只在最后一步介入

### 第四优先级：给小红书补专用 Launcher

小红书现在能发，但“专用实例管理”还不如公众号、知乎规范。

建议补：

- `launch_xhs_controlled_chrome`
- `probe_xhs_login`
- `probe_xhs_editor`

这样至少先把“重复登录”和“进错页”的概率降下来。

### 第五优先级：降低今日头条目标复杂度

头条最容易把时间耗在边角问题上，所以建议主动做取舍：

- 默认接受平台自动三图封面
- 强制单封面不作为主链路
- 标题长度在本地先预检
- 发布成功只以作品列表出现为准

也就是说，头条要追求“稳定可发”，不要追求“每个视觉细节都完全掌控”。

## 我给出的最终方案

后面这四个平台建议这样分层：

- 微信公众号：改成官方 API 主链路
- 知乎：继续浏览器自动化主链路
- 今日头条：继续浏览器自动化，但降低封面控制欲、加强标题和列表校验
- 小红书：继续浏览器自动化，同时评估官方分享 SDK 的中长期可能

如果只问一句“现阶段最值当做的改造是什么”，答案就是：

**先把公众号从网页发布改成 API 发布，再把四个平台统一成固定专用会话管理。**

## 本地参考

- [今日头条发布手册](C:\Users\Administrator\Documents\code-news\docs\toutiao-publish-runbook.md)
- [公众号发布手册](C:\Users\Administrator\Documents\code-news\docs\wechat-publish-runbook.md)
- [知乎发布手册](C:\Users\Administrator\Documents\code-news\docs\zhihu-publish-runbook.md)
- [小红书发布脚本](C:\Users\Administrator\Documents\code-news\.tmp\publish_xhs_article_controlled.py)

## 官方参考链接

- 微信公众号新增草稿：[https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)
- 微信公众号发布草稿：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html)
- 微信公众号发布状态查询：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html)
- 微信公众号获取已发布图文信息：[https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle.html](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle.html)
- 知乎开放平台首页：[https://developer.zhihu.com/](https://developer.zhihu.com/)
- 巨量引擎商业开放平台首页：[https://open.oceanengine.com/](https://open.oceanengine.com/)
- 小红书开放平台首页：[https://ad-market.xiaohongshu.com/](https://ad-market.xiaohongshu.com/)
- 小红书分享开放平台首页：[https://agora.xiaohongshu.com/](https://agora.xiaohongshu.com/)
- 小红书分享 SDK 文档示例页：[https://agora.xiaohongshu.com/doc/harmony](https://agora.xiaohongshu.com/doc/harmony)
- 小红书小程序开放平台首页：[https://miniapp.xiaohongshu.com/](https://miniapp.xiaohongshu.com/)
