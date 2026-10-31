---
domain: toutiao.com
aliases: [今日头条, 头条, toutiao, 头条号]
updated: 2026-09-14
---
## 平台特征
- 国内资讯聚合平台。首页 `https://www.toutiao.com/`，**无需登录即可读热榜**（2026-09-14 实测）。
- 首页右侧/中部有「**头条热榜**」模块，含排名 + 标题，容器带 `换一换` 字样。
- 热榜条目链接形态：`/trending/`、`hot-event`、`/article/`。
- 登录态判断：用户日常 Chrome 通常已登录头条号；未登录时不影响热榜读取。

## 有效模式
- `/new?url=https%3A%2F%2Fwww.toutiao.com%2F` 直接打开，**无登录墙**（2026-09-14）。
- 等 `document.readyState === 'complete'` 后再取 DOM（实测 complete 后数据即齐全）。
- **热榜提取（已验证，返回 hotCount=55）**：
  ```js
  [...document.querySelectorAll('a')]
    .filter(a => /\/trending\/|hot-event|\/article\//.test(a.getAttribute('href') || ''))
    .map(a => a.innerText.trim()).filter(t => t.length > 1)
  ```
- **兜底提取**：`document.querySelectorAll('[class*="hot"], [class*="rank"], [class*="trend"]')`
  → 实测命中 4 个容器，第一个 innerText 即"标题\n标题\n…"纯列表；
  含"头条热榜"字样的容器 innerText 为 `头条热榜\n换一换\n\n标题\n\n1\n\n标题\n\n2\n…`，可直接按行解析出「排名+标题」。

## 已知陷阱
- 首页 URL 会带会话参数 `?wid=<数字>`（如 `?wid=1789393721405`）；提取页面内链接时应保留完整参数。
- **eval 返回体是二次转义的**：形如 `{"value":"{\"title\":\"今日头条\",...}"}`，
  需对 `value` 字段再做一次 `JSON.parse` 才能拿到结构化对象。
- 热榜里夹杂互动数条目（如 `"1评论"`、`"83评论"`），解析时需过滤非标题项。
- 页面为动态渲染，热榜可能有"换一换"导致内容随时间变化；同一时刻多次读取结果可能不同。
