# 平台适配详解

## 总览

| 平台 | 主路径 | 备用路径 | 状态 |
|---|---|---|---|
| 抖音 | CDP + Network 拦截 `aweme/v1/web/aweme/post` | 无（页内 fetch 已证明失败） | ✅ 实测通过 |
| B站 | `card` 接口（profile）+ `wbi` 签名（列表） | CDP + 登录态 | ⚠️ 半可用 |
| 小红书 | CDP 读 `__INITIAL_STATE__` | CDP 拦截 `api/sns/web/v1/user_posted` | ❓ 未实测 |
| Instagram | CDP + 登录态拦截 GraphQL | 无（匿名已被 429 封死） | ❌ 需登录 |

---

## 抖音（唯一完整验证过的）

### 入口定位
用户主页 URL：`https://www.douyin.com/user/<sec_user_id>`
`sec_user_id` 从分享链接里取，形如 `MS4wLjABAAAAlLZoiptB5Qat-...`（以 `MS4wLjABAAAA` 开头）。

### 数据接口
```
/aweme/v1/web/aweme/post/?device_platform=webapp&aid=6383&channel=channel_pc_web
  &sec_user_id=<sec>&max_cursor=<cursor>&count=18&...
```
响应体顶层：`{ aweme_list: [...], has_more: 0|1, max_cursor: <next> }`

### 关键字段
| 用途 | 字段路径 |
|---|---|
| 作品 ID | `aweme_id` |
| 文案 | `desc`（含 `#话题`） |
| 发布时间 | `create_time`（Unix 秒） |
| 赞/评论/分享/收藏 | `statistics.digg_count` / `comment_count` / `share_count` / `collect_count` |
| 播放 | `statistics.play_count` —— **图文作品恒为 0** |
| 推荐量 | `statistics.recommend_count` |
| 图片列表 | `images[]`（图文）或 `image_list[]` |
| 话题 | `text_extra[]` |
| 音乐 | `music` |

### 已验证的失败路径（别再试）
```javascript
// ❌ 在页面上下文里直接 fetch API
fetch('/aweme/v1/web/aweme/post/?...&msToken=&X-Bogus=&_signature=')
// 结果：返回 93 字节空响应。抖音校验完整请求头链（含 X-Bogus 签名），
// 页内构造不出来。让浏览器自己发请求，我们只截获响应，才是唯一可行路径。
```

### 已验证的成功路径
1. `Network.enable`（buffer 放大到 80MB / 400MB）
2. 监听 `Network.responseReceived`，正则匹配 `aweme\/v1\/web\/aweme\/post`
3. `Network.loadingFinished` 后 `Network.getResponseBody` 取回
4. 分页靠**真实交互**触发：
   - `scrollTo(0, body.scrollHeight)` → 等 4s
   - 点击 innerText 为「加载更多 / 查看更多 / 看更多」的元素 → 等 3.5s
   - 循环 5-8 轮
5. `Page.navigate` 后**至少等 25s**（抖音页面永不 idle，`waitForNavigation` 会卡死）

### 常见故障
| 现象 | 原因 | 处理 |
|---|---|---|
| 只拿到 0 条 | 等太久 / 还没滚 | 首屏等待加到 25-30s，滚动轮次加到 8 |
| 登录墙挡住 | 未登录态限制 | 在 Chrome 里扫码登录后重跑（复用同一 profile 目录） |
| `getResponseBody` 报 "not found" | buffer 太小或响应已释放 | 调大 `maxResourceBufferSize` |

---

## B站

### 已实测可用
```
GET https://api.bilibili.com/x/web-interface/card?mid=<uid>&photo=false
```
返回：`data.card.{mid,name,fans,attention,sign}`、`data.archive`（投稿数）、`data.like_num`（获赞）
**无需登录，curl 直连即可。**（2026-09-04 实测 mid=1 返回粉丝 229,706）

### 已实测失败
```
GET https://api.bilibili.com/x/space/wbi/arc/search?mid=<uid>&...&w_rid=<sign>
→ {"code":-352,"message":"风控校验失败","data":{"v_voucher":"voucher_..."}}
```
- wbi 签名算法**实现是正确的**（MIXIN_KEY_ENC_TAB 重排 + 参数排序 + md5）
- 卡在 `-352`，附加 `v_voucher` 票据 —— B站 2024 底上线的风控挑战
- 测试环境出口 IP 在新加坡（`ip_region: SG`），海外 IP 会显著加剧风控
- **国内 IP 可能直接通过**，值得先试

### wbi 签名要点（若需自己实现）
1. `GET /x/web-interface/nav` → `data.wbi_img.{img_url,sub_url}`（未登录也返回）
2. 取文件名去扩展名 → `imgKey` / `subKey`
3. `mixinKey = MIXIN_KEY_ENC_TAB.map(i => (imgKey+subKey)[i]).join('').slice(0,32)`
4. 参数加 `wts`（秒级时间戳）→ 按 key 排序 → 过滤 `!'()*` → encodeURIComponent → `&` 连接
5. `w_rid = md5(query + mixinKey)`

### 单条视频互动数据
```
GET https://api.bilibili.com/x/web-interface/archive/stat?bvid=<bvid>
→ data.{view, danmaku, reply, favorite, coin, share, like}
```

---

## 小红书（✅ 已端到端验证，2026-09-04）

实测账号 `5fa954de000000000101e92b`：登录后拿到 **29 条笔记 + 完整账号数据**。

### 唯一可行路径：读 SSR 状态
网络拦截（`api/sns/web/v1/*`）实测**命中 0 次**，接口名可能已改版。别指望它。
真正的数据全在 `window.__INITIAL_STATE__` 里。

### 结构（四个坑，都是实测踩出来的）

**坑 1｜Vue 3 ref 包装**
```javascript
window.__INITIAL_STATE__.user.userInfo
// → {dep,__v_isRef,__v_isShallow,_rawValue,_value}   ← 不是真实数据
window.__INITIAL_STATE__.user.userInfo._value
// → {desc,gender,images,imageb,guest,redId,userId,nickname}  ← 真实数据在这
```
所有值都要 unref：`(o)=> o&&o.__v_isRef ? (o._value??o._rawValue) : o`

**坑 2｜循环引用**
整块 `JSON.stringify(state)` 抛 `Uncaught`（报错栈指向小红书自己的 library-polyfill）。
**必须每次查询包成自包含 IIFE、只返回一个短字符串**，helper 用单行无注释写法。

**坑 3｜notes 是分页数组**
```javascript
user.notes._value   // 长度 5（这是"页"数！）
  [0] → [笔记1, 笔记2, ...]   // 每页又是一个数组
```
必须判断首元素是否为数组、摊平一层，才能得到真正的 29 条笔记对象。
**别把 5 当成笔记总数**——实测第一版就只拿到 5 条。

**坑 4｜笔记字段在 noteCard 里**
```
笔记对象 = { id, noteCard:{ type, displayTitle, interactInfo, cover, noteId,
                            user, time, xsecToken }, index, exposed, ... }
```
标题 = `noteCard.displayTitle`，ID = `noteCard.noteId`，时间 = `noteCard.time`。

### 字段提取位置

| 数据 | 路径 |
|---|---|
| 昵称 / 简介 / redId | `user.userInfo._value.{nickname,desc,redId}` |
| **粉丝数** | `user.userPageData._value.interactions[]` 中 `type==='fans'` 的 `count` |
| **获赞与收藏** | 同上，`name` 含「赞」或 `type==='interaction'` 的 `count` |
| IP 属地 | `user.userPageData._value.basicInfo.ipLocation` |
| 笔记列表 | `user.notes._value`（摊平一层） |

⚠️ **粉丝数不在 userInfo 里**（userInfo 只有 8 个字段，没有 fans）——
必须从 `userPageData.interactions` 数组取。

### 登录墙 + cookie 陷阱（重要）

未登录态页面直接显示「登录即可查看 Ta 的笔记」，**一条都不给**（比抖音更狠）。

⚠️ **`web_session` 是访客就会下发的 cookie，不能作为登录凭证。**
实测：cookie 里有 `web_session`（有效期到 2027），但页面
`__INITIAL_STATE__.user.loggedIn._value = false`，页面仍显示登录墙。

cookie 里还会出现 `sec_poison_id`、`acw_tc`、`websectiga` 等反爬标记。

**判定只能靠页面**：用 `login_helper.js`，它读 `loggedIn._value` 而不是 cookie。

### 数据可得性（诚实标注）

`interactInfo` 只有 `{liked, likedCount, sticky}` ——
**列表接口只返回点赞数，评论/收藏/分享必须打开单条笔记才能拿到。**
normalize 会把这三项置 `null`（不是 0），metrics 显示 `N/A（接口不提供）`。
不要拿 0 冒充——那会让人误以为"互动极差"，实际是"这个接口拿不到"。

---

## Instagram（未登录不可行，已实测）

### 实测结论
```
GET https://www.instagram.com/api/v1/users/web_profile_info/?username=xxx
Header: x-ig-app-id: 936619743392459
→ HTTP 429（限流）
```

### 唯一现实路径
登录态 + CDP：
1. 独立 `user-data-dir` 启动 Chrome
2. 手动登录一次
3. 复用同一 profile 目录重跑脚本

### 拦截目标
- `/api/v1/feed/user/<user_id>/`
- `/graphql/query`
- `/api/v1/users/web_profile_info/`

### 数据可得性
- 赞、评论可得
- **分享数、收藏数 INS 不公开** —— 指标层会自动跳过这两项
- 播放量只有视频有（`video_view_count`）

---

## 通用：启动调试 Chrome

```bash
"<CHROME>" --remote-debugging-port=9335 \
  --user-data-dir="<工作区>/.cdp-prof" \
  --no-first-run --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  about:blank
```

Chrome 常见位置（Windows）：
```
C:\Program Files\Google\Chrome\Application\chrome.exe
C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
C:\Users\<user>\AppData\Local\Google\Chrome\Application\chrome.exe
```

**注意**：
- 端口冲突或 profile 损坏时，**换目录名**（`.cdp2`、`.cdp3`…），
  不要 `rm -rf` 旧目录（大目录删除会被安全策略拦截）
- 需要登录的平台（小红书/INS/B站列表），登录后**保持 Chrome 不关**，
  后续脚本复用同一端口即可保持会话

## 频率控制（避免连累用户 IP）

| 操作 | 最小间隔 |
|---|---|
| 滚动 | 3.5–4s |
| 接口直连请求 | 2.5s |
| 逐条取详情 | 1.2s |

只针对用户指定的**单个账号**做拆解，不做全站遍历、不做批量爬取。
