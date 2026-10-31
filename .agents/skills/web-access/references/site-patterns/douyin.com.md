---
domain: douyin.com
aliases: [抖音, creator.douyin.com, www.douyin.com, 抖音创作者中心]
updated: 2026-10-13
---

## 平台特征
- **CDP 导航实测通过（2026-10-13）**：`/new?url=https://creator.douyin.com/` 可打开，约 3 秒完成渲染。
- **登录态判据（2026-10-13 实测，用户 Chrome 已登录）**：cookie 含 `login_time`、`UIFID`、`passport_assist_user`、`passport_csrf_token` 等 passport 系痕迹。
  打开 `creator.douyin.com/` 会 302 到 `https://creator.douyin.com/creator-micro/home`（创作者工作台）——**URL 落到 `/creator-micro/` 即视为已登录**；未登录会被弹到 passport 登录页。
- 页面标题固定为「抖音创作者中心」。创作者平台主体是 `creator.douyin.com/creator-micro/` 下的 SPA。

## 有效模式
- 创作平台入口：`https://creator.douyin.com/` → 自动跳 `creator-micro/home`。
- 后台标签页 `/new` 打开 + `/eval` 读取 DOM 均正常，未触发验证码（2026-10-13）。
- `/eval` 建议先用 `document.title` + `location.href` 做存活与跳转确认，再做业务 DOM 提取。

## 已知陷阱
- 首屏渲染约需 2–3 秒，`/new` 返回后立即 `/eval` 可能拿到空 title——稳妥做法是 `/new` 后 sleep 2–3 秒再 eval。
- passport 系 cookie 名会随登录态刷新变化，判据以「URL 是否含 `/creator-micro/`」为主、cookie 名为辅。
- 本机 Clash 代理环境下 `www.douyin.com` 主站（C 端推荐流）偶发加载慢，平台后台（creator）不受影响（2026-10-13 观察，非必现）。
