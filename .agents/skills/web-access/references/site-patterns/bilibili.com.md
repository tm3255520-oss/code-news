---
domain: bilibili.com
aliases: [B站, 哔哩哔哩, bilibili, 小破站]
updated: 2026-09-12
---
## 平台特征
- 国内主流视频平台，用户日常 Chrome 通常已保持登录态（`DedeUserID` cookie 存在即视为已登录）。
- 首页 `https://www.bilibili.com/`，顶部导航含：首页/番剧/直播/游戏中心/会员购/漫画/赛事，右侧含头像、大会员、消息、动态、收藏、历史、创作中心、投稿。
- 登录态判断（2026-09-12 验证）：首页顶部存在 `a.header-entry-mini[href^="//space.bilibili.com/"]`，
  其内 `picture.v-img > source[srcset]` 即头像；该 `href` 中的数字即用户 UID。
  **注意**：`.bili-avatar` 的 `alt` 与 `[class*=nickname]` 在首页不返回昵称，用户名改用 UID 或跳个人空间页获取。
- 未登录时会渲染 `.header-login-entry` / `.go-login-btn`（"登录"按钮）。

## 有效模式
- 直接 `/new?url=https://www.bilibili.com/` 即可打开，无需登录墙拦截（2026-09-12）。
- 页面为 Vue 动态渲染，需等 `document.readyState === 'complete'` 后再取 DOM，否则顶部导航为空。
- 个人空间收藏夹 URL 形态：`https://space.bilibili.com/{UID}/favlist?fid={fid}&ftype=create`
- 创作中心投稿页：`https://member.bilibili.com/platform/upload/video/frame/`

## 已知陷阱
- CORS/风控对 CDP 操作不敏感，常规 DOM 读取未触发验证码（2026-09-12）。
- 首页会加载大量视频封面，`Page.captureScreenshot` 在**后台标签页**上可能长时间不返回并拖断 CDP 连接 ——
  需要截图时先把标签页切到前台，或直接跳过截图改用 DOM 提取（见 web-access skill 的 CDP 经验）。
- **无法用 JS 把 B 站标签页切到前台**（`window.focus()` 无效，`document.visibilityState` 仍为 hidden）；
  `Target.activateTarget` 需新建 WebSocket 连接、会再次触发 Chrome 授权弹窗，代价高。
  → 打开页面后如需用户看见，直接告知用户在 Chrome 里点那个后台标签页即可（2026-09-12 实测）。
- 首页顶部导航懒渲染：`document.readyState` 为 complete 后仍可能取不到 `.bili-header__channel`，
  稳妥做法是同时兜底 `.nav-link` 选择器，或等 1–2 秒再取。
