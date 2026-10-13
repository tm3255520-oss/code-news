---
domain: zhihu.com
aliases: [知乎, www.zhihu.com, zhihu]
updated: 2026-10-13
---

## 平台特征
- **CDP 导航实测通过（2026-10-13）**：`/new?url=https://www.zhihu.com/` 可打开，约 3 秒完成渲染。
- **登录态判据（2026-10-13 实测，用户 Chrome 已登录）**：cookie 含 `SESSIONID`、`_zap`、`d_c0`、`__snaker__id`、`z_c0`（z_c0 为核心登录凭证，未登录时不存在）。
  未登录访问同样能打开首页（内容为推荐登录态），**不能以"能否打开"判断登录，必须查 cookie 名**。
- 页面标题「首页 - 知乎」。推荐流/热榜等内容可直接从 DOM 提取。

## 有效模式
- 首页：`https://www.zhihu.com/`；热榜：`https://www.zhihu.com/hot`；问题页：`https://www.zhihu.com/question/<id>`。
- `/eval` 读 DOM 正常，未触发验证码（2026-10-13）。
- 查登录态一行 JS：`document.cookie.includes('z_c0=')`（只判断存在性，不读值）。

## 已知陷阱
- 首屏需约 2–3 秒渲染，`/new` 后立即 eval 可能拿到空串——sleep 2–3 秒再取。
- 首页为信息流 SPA，滚动（`/scroll?direction=bottom`）才触发懒加载更多条目；只取首屏就够用时不必滚。
- 知乎内容页对 curl/静态抓取有反爬（`zse_ck` 校验），**文章/回答正文提取优先走 CDP 而非 WebFetch/firecrawl**；
  本机 `document.cookie` 可见 `zse_ck` 说明静态层会被挡（2026-10-13 观察）。
