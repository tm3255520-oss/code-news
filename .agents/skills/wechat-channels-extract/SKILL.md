---
name: wechat-channels-extract
description: 从微信视频号分享链接提取视频的元数据与封面（作者、文案/话题标签、互动数、封面图），据此反查视频里讲的工具/方法/步骤。当用户丢来 weixin.qq.com/sph/... 短链并说"看完这个视频""这条视频讲了什么""视频里那个工具是什么""照着视频配置"时使用。含可用的 get_feed_info 接口调用方式、401 排查、封面读图反查法。
agent_created: true
---

# 视频号链接内容提取

## 判据：能拿到什么、拿不到什么

| 目标 | 能不能拿到 | 怎么拿 |
|---|---|---|
| 视频标题 / 文案 / 话题标签 | ✅ | `get_feed_info` 的 `feedInfo.description` |
| 作者昵称 | ✅ | `data.authorInfo.nickname` |
| 互动数（赞/转发/收藏/评论） | ✅ | `feedInfo.likeCountFmt` 等 |
| **封面图** | ✅ | `feedInfo.coverUrl`（finder.video.qq.com 直链） |
| 视频本体 / 逐帧 / 字幕 | ❌ | 需微信客户端内播放，外部无接口 |

**核心判断：拿不到视频本体，但封面信息量通常极大。** 教程类视频的封面往往就是"标题卡 + 软件界面截图"，读图能直接读出工具名、按钮、步骤。**先拿封面再读图，比死磕视频本体高效得多。**

## 步骤

### 1. 解析短链
`https://weixin.qq.com/sph/<ID>` → `https://channels.weixin.qq.com/finder-preview/pages/sph?id=<ID>`
（短链 302 到 channels.weixin.qq.com，`<ID>` 就是 `shortUri`）

页面本身是 JS 渲染的空壳（约 2.6KB），`curl` 拿不到内容；数据走下面的 HTTP 接口。

### 2. 调 get_feed_info

```bash
curl -s -X POST "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info" \
  -H "Content-Type: application/json" \
  -H "Origin: https://channels.weixin.qq.com" \
  -H "Referer: https://channels.weixin.qq.com/finder-preview/pages/sph?id=<ID>" \
  -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148" \
  --data '{"baseReq":{"generalToken":""},"shortUri":"<ID>"}'
```

返回：`data.feedInfo`（description / coverUrl / 各互动数 / createtime）、`data.authorInfo`、`data.sceneInfo.dynamicExportId`。

**正常返回 HTTP 201，不是 200。**

### 3. 下载封面并读图

`coverUrl` 是 `finder.video.qq.com/251/2030x/stodownload?...` 直链，直接下载（带 `Referer: https://channels.weixin.qq.com/`）。然后用视觉能力读图。

> 封面尺寸固定（约 540×720），把 `picformat` / `wxampicformat` 参数改大**无效**。封面里的界面截图很小，**必须裁剪+放大**才能读清：
> ```bash
> ffmpeg -y -i cover.jpg -vf "crop=W:H:X:Y,scale=2000:-1:flags=lanczos" cover_crop.png
> ```
> （Windows 本机 ffmpeg 在 `C:\ffmpeg\bin\ffmpeg.exe`；无 PIL 时用 ffmpeg 裁图）

### 4. 顺线索反查

从封面/文案里抓关键词（工具名、平台名、话题标签），去 GitHub / 搜索引擎反查：
- GitHub 仓库搜索用 API：`https://api.github.com/search/repositories?q=<关键词>`
- 再读仓库 README，拿到完整安装/使用步骤

## 踩过的坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `{"errCode":-1,"errMsg":"permission verification failed"}` HTTP 401 | **缺 `Origin` 头** | 补 `Origin: https://channels.weixin.qq.com` |
| 用 `exportId` 调 → `{"errMsg":{"type":2,"title":"此内容暂时无法播放"}}` | exportId 路径要真 token | 用 `shortUri` 那条路 |
| `/cgi-bin/finder-preview/...`、`/web/api/...` 返回 SPA HTML 或 Cannot POST | 路径猜错 | 正确路径是 `/finder-preview/api/feed/...` |
| 想用浏览器渲染 | 沙箱内 agent-browser 守护进程起不来（SIGTERM） | 不用浏览器，直接走 HTTP 接口 |
| 视频地址怎么都拿不到 | 设计如此 | 放弃视频本体，走封面+README |

## 接口是怎么找到的（方法可复用）

页面 JS 里搜 `WeixinJSBridge.invoke` / `getFeedInfo` / `shortUri`：

```bash
curl -s "https://res.wx.qq.com/t/wx_fed/finder/web/finder-preview/res/assets/feed.<hash>.js"
# hash 从页面 HTML 的 <script src> 里取
grep -oE '.{200}getFeedInfo.{200}' <js文件>
```

`merlin.<hash>.js` 里有接口定义：
```js
class ie extends ae { getFeedInfo(t){ return this.post({url:"feed/get_feed_info", data:{...t}}) } }
// ae 的 baseURL = `${C}/api`，其中 C = "/finder-preview"
```
→ 拼出 `https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info`

## 相关文件

- `scripts/fetch_sph.py` — 一条命令：给短链/ID，输出元数据 JSON + 下载封面
