---
domain: xiaohongshu.com
aliases: [小红书, 红薯, 红书, www.xiaohongshu.com, creator.xiaohongshu.com, 小红书创作服务平台]
updated: 2026-10-13
---

## 平台特征
- **C 端主站 `www.xiaohongshu.com` CDP 完全可用（2026-10-13 复测实锤）**：`/new?url=https://www.xiaohongshu.com/explore`
  正常返回 targetId，`/info` 三要素齐全（title「小红书 - 你的生活兴趣社区」、url 落到目标站、ready=complete）。
- **本文件旧版结论作废（2026-10-13 修正）**：旧版写的「CDP 导航不通 / 同机代理对小红书选择性断流」为**错误归因**，
  已被复测推翻，勿再引用。当时的失败样本（`/info` 显示 about:blank）疑似发生在 CDP 连接未就绪/加载时序窗口，
  未最终定论根因；连用户侧截图都证明该域名浏览器可正常打开。
- **创作服务平台 `creator.xiaohongshu.com` 本机网络层不可达（2026-10-13 多次实测）**：直连 curl 返回 `000`
  （连接直接失败，非超时、非拒绝、非证书问题）。属本机网络/代理（Clash 分流/DNS）问题，与 CDP 无关；
  **发布链路在修好该域名连通性前无法进行**，需用户侧排查。
- **登录态不能靠 cookie 名判断**：`document.cookie` 在**已登录**状态下也看不到 `web_session`（session cookie
  对 JS 不可见，大概率 HttpOnly，未直接验证）。2026-10-13 实测当前用户 Chrome **已登录小红书**
  （own profile id `6648c86f000000001e007904`）；此前仅按 document.cookie 判出「未登录」属假阴性。

## 有效模式
- 打开链路：`/new?url=https://www.xiaohongshu.com/explore` → `/info?target=ID` 校验三要素 → `/eval` 操作。
- **登录态判断（2026-10-13 实测，满足任一即已登录）**：
  1. DOM 存在 `a[href*="/user/profile/<自己的id>"]`（侧栏「我」/头像入口）；
  2. 页面含「发布」「创作服务」入口；
  3. 无登录弹窗。
  未登录特征：登录弹窗 + 「登录/注册」按钮 + 无 own profile 链接。
- 宿主状态：`window.__INITIAL_STATE__.user` 存在，含 `loggedIn`（**observable 对象**，别直接 JSON.stringify
  整个 state——循环引用抛 `Converting circular structure to JSON`）、`userInfo`（SSR 初传可能为空，别依赖）、
  `userPageData`/`notes`/`follow` 等。

## 已知陷阱
- **切忌把 `__INITIAL_STATE__` 整体 stringify**：mobx observable 循环引用，`/eval` 返回 `Uncaught`；
  需要哪个字段取哪个，拼普通字符串返回。
- **切忌用 `document.cookie` 判断小红书登录态**：session cookie 对 JS 不可见，必假阴性，走 UI 标记。
- 失败特征识别（通用）：`/info` 的 `url` 仍是 `about:blank` → 导航没开始（非加载慢）；
  `url` 是目标站但 title 空 → 加载中，等待后重取。`/eval` 返回 `Uncaught` = 页面 JS 抛异常，先包 try/catch 再定位。
- creator 子域不可达期间不要反复 `/new` 重试该域名，先修本机网络；修好后回来复测并更新本文件。
- 短时间密集 `/new` 大量页面可能触发反爬风控。
