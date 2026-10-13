---
domain: mp.weixin.qq.com
aliases: [公众号, 微信公众号, 微信公众平台, mp.weixin]
updated: 2026-10-13
---

## 平台特征
- **CDP 导航实测通过（2026-10-13）**：`/new?url=https://mp.weixin.qq.com/` 可打开，约 3 秒完成渲染。
- **登录态判据（2026-10-13 实测，用户 Chrome 已登录）**：cookie 含 `wxuin`、`mm_lang`、`rewardsn`；
  打开后 URL 为 `https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=<数字>`——**URL 带 `token=` 参数即视为已登录**（token 即当次会话凭证，具有时效）。
- 页面标题固定为「公众号」。公众平台是 CGI 接口型后端（`/cgi-bin/`），大量操作链接都带 `token` 与 `lang` 参数。

## 有效模式
- 登录后首页：`https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=<token>`。
- **从已登录首页点选进入的链接天然携带 token，优先用 `/click` 走菜单导航，不要手拼 token URL**（token 过期后手拼链接会 200 但内容为空或跳登录）。
- `/eval` 直接读 DOM 正常，未触发风控（2026-10-13）。

## 已知陷阱
- 页面为传统多页应用，跳转靠完整 URL；`/eval` 取到的链接若不含 token 属正常现象，**不要在未登录态下解读为故障**。
- `token` 有时效（约数小时），长时间任务中途报" token 失效"式空白页时，引导用户刷新首页重新取链接即可，无需重启 proxy。
- 与 `wechat-article-extractor` 技能分工：读**单篇文章正文**（mp.weixin.qq.com/s?__biz=...）优先用该技能的静态解析（无需浏览器、无反爬压力）；**素材管理/后台操作**才走 CDP。
