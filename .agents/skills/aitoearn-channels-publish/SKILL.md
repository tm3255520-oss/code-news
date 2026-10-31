---
name: aitoearn-channels-publish
description: 用 AiToEarn 把视频发到「微信视频号」的实操手册（浏览器插件腿）。当用户说「用 aitoearn 发视频号」「视频号改用 AiToEarn」「插件发视频号」「AiToEarn 发不出去」「视频号视频时长不能少于 3 秒」「AIToEarnPlugin」时使用。核心是三条硬事实：**发视频号只能走浏览器插件/网页端（wxSph 的 publish=false，指 Open API 不直发，不等于不能发）**；**插件必须显式传 platformConfig.wxSph.videoMetadata，否则扩展在 Service Worker 里把时长算成 0、平台报「时长不能少于 3 秒」**；**插件对视频号无草稿能力，发出去即公开**。含 bsk 注入执行、本地素材常驻、后台复核的完整落地步骤。**边界**：视频号「进草稿箱」走 d2v-channels-publish；其他 AiToEarn 平台（抖音/B站/快手/公众号）走 Open API；产线故障定位走 hermes-pipeline-repair。
agent_created: true
version: 1.1.0
tags: [视频号, channels, aitoearn, bsk, 插件, publish, 发布, api-key, 凭据]
---

# AiToEarn 发微信视频号（浏览器插件腿）

> 首次打通：2026-10-13，视频号「数智极客」公开作品一条（workId `e1368636-93fa-8564-45cc-a5ba286341fe`），
> 已在 `channels.weixin.qq.com/platform` 作品列表首位复核到。

## 0. 这个 skill 管什么、不管什么

**管**：手上有一个 mp4 + 一张封面 → 用 AiToEarn 浏览器插件**公开发到视频号** → 到后台复核。

**不管**（别在这里找）：

| 事情 | 去哪 |
|---|---|
| 视频号**进草稿箱**（不公开） | skill `d2v-channels-publish`（`~/.hermes/scripts/publish_channels.py`，走后台 UI + `bsk upload`，已验证） |
| 其他平台走 AiToEarn **Open API** | `docs.aitoearn.cn`（`X-Api-Key` + Flow）；抖音/KWAI/wxGzh/bilibili 才 `publish=true` |
| 微信**公众号**发布 | skill `wechat-channel-ops`（`mp.weixin.qq.com`，与视频号是两套系统） |
| 该不该动手修 | skill `repair-gate`（默认只报告） |
| 蚁小二/矩媒腿 | `publish_via_yxer.py` / `publish_via_matrixmedia.py` |

---

## 1. 三条硬事实（先记住，能省一轮）

1. **发视频号只能走插件/网页端；API Key 仍有用，别劝退用户**。
   `GET /api/v2/channels/platforms`（需 `X-Api-Key`）里 `wxSph` 是 `authType=plugin` 且
   **`publish=False`** → **Open API 不能发视频号**，必须走浏览器插件或 `aitoearn.cn` 网页端。
   ⚠️ 但**别把这说成「key 白费/不能发」**（2026-10-13 我犯过这个错，被用户当场纠正）——
   `publish=false` 只说明 API 不直发 wxSph，不等于不能发。实测证据：
   `GET /api/v2/channels/publish/records` 里有 **2026-10-12 视频号成功记录**
   （`source=web`、`workLink https://weixin.qq.com/sph/ArIRcaX1R`、标题「国庆大厂静默？看懂AI新逻辑」）。
   **API Key 的实际价值**：① 查账号/授权状态（`/channels/accounts`）；② 查发布历史与结果；
   ③ 抖音 / 快手 / 微信公众号 / 哔哩哔哩 4 个平台可 API 直发。
   → 用户贴 key 时，**收下登记 + 用起来**，而不是回绝。
2. **必须传 `platformConfig.wxSph.videoMetadata`**。不传必报「**视频号视频时长不能少于 3 秒**」，
   哪怕视频有 47 秒。原因见 §4。
3. **插件对视频号没有草稿**。`supportsSchedule:true`、无 `supportsDraft`，
   且 `deleteWork` 对 wxSph 直接返回「不支持」→ **发出去就是公开且不能用插件撤回**。
   若用户要的是草稿，**改用 `d2v-channels-publish`**，不要用这条腿。

---

## 2. 30 秒速用

```bash
# 0) 前置：bsk 已连上装了 AiToEarn 扩展的 Chrome、视频号频道已授权
bsk status
bsk session list                      # 拿 session id；没有就 bsk session start

# 1) 起本地素材服务（必须后台常驻！见 §3 坑）
#    cwd = 素材目录；绑定 127.0.0.1
cd "<素材目录>" && "<python>" -m http.server 8777 --bind 127.0.0.1
#    自检（注意 --noproxy '*'，否则被沙箱代理劫持成 502）
curl -s -o /dev/null -w "%{http_code} %{size_download}\n" --noproxy '*' http://127.0.0.1:8777/final.mp4

# 2) 取真实元数据（duration 要用它）
ffprobe -v error -show_entries stream=width,height,duration -show_entries format=size \
        -of json "<素材目录>/final.mp4"

# 3) 导航到已授权域名（插件只在该域名注入），点火发布（不等待，避免阻塞）
bsk navigate --session <sid> "https://aitoearn.cn/zh-CN/publish"
bsk evaluate --session <sid> --await-promise false --timeout 30s "$(cat kickoff.js)"

# 4) 轮询结果
bsk evaluate --session <sid> --timeout 30s "<读 window.__sphPub 的表达式>"
```

**点火 JS 模板**（`kickoff.js`，把所有值填实）：

```js
(() => {
  const p = window.AIToEarnPlugin;
  if (!p) return "NO_PLUGIN";
  const params = {
    platform: "wxSph",
    type: "video",
    title: "<标题>",
    desc:  "<描述，≤2000 字>",
    video: "http://127.0.0.1:8777/final.mp4",
    cover: "http://127.0.0.1:8777/cover.png",
    topics: ["<话题1>", "<话题2>"],           // ≤10 个
    platformConfig: {                          // ★★ 不传就必失败 ★★
      wxSph: {
        videoMetadata: {
          width: 1080, height: 1920,
          duration: 47.166667,                 // ffprobe 的秒数，可带小数
          size: 18432418                       // 字节
        }
      }
    }
  };
  window.__sphPub = { state: "running", events: [], startedAt: Date.now() };
  const onProg = (e) => { try { window.__sphPub.events.push({ stage: e && e.stage, progress: e && e.progress, message: (e && e.message) || "" }); } catch (_) {} };
  p.publish(params, onProg)
    .then(r => { window.__sphPub.state = "done"; window.__sphPub.result = r; window.__sphPub.endedAt = Date.now(); })
    .catch(e => { window.__sphPub.state = "error"; window.__sphPub.err = String((e && e.message) || e); window.__sphPub.endedAt = Date.now(); });
  return "STARTED";
})()
```

**轮询表达式**：

```js
JSON.stringify((function(){var s=window.__sphPub;if(!s)return{none:true};
return{state:s.state,elapsedMs:(s.endedAt||Date.now())-s.startedAt,
lastEvents:(s.events||[]).slice(-10),result:s.result,err:s.err};})())
```

**成功长这样**：`{"success":true,"workId":"e1368636-...","publishTime":1791897344152,"platformData":{"mediaMd5sum":"...","videoClipTaskId":"..."}}`

> 用「先 `--await-promise false` 点火、再轮询全局变量」的写法，**不要**让单次 `evaluate` 等整个上传
> （3 分片上传 + 封面 + 建作品，整段约 8–12 秒，遇到大文件更久；单次等待容易被 --timeout 打断）。

---

## 3. 踩坑集（每条都真的踩过）

| # | 症状 | 真因 | 处置 |
|---|---|---|---|
| 1 | `Failed to fetch`，进度停在 `正在验证参数...`，2 秒就失败 | 本地素材 http server 已死。**用 `nohup … &` 起的话，Bash 调用一结束进程就被回收** | 用**后台常驻**方式起服务；每次发之前 `curl --noproxy '*'` 自检 200 |
| 2 | `curl http://127.0.0.1:8777/...` 返回 **502**（服务其实活着） | Git Bash 里带了 `http_proxy`，请求被沙箱代理劫持 | 自检一律加 `--noproxy '*'`；直连返回 `000` 才是真的没监听 |
| 3 | `发布失败: 视频号视频时长不能少于 3 秒` | §4 的 SW 无 DOM 缺陷 | 传 `platformConfig.wxSph.videoMetadata` |
| 4 | `bsk evaluate` 报 `session not registered` | bsk session 会自动过期 | `bsk session start` 重开，换新 `--session` |
| 5 | `window.AIToEarnPlugin` 只有 4 个搜索方法、没有 `publish` | `publish/login/checkPermission/getVersion` 挂在**原型**上 | 用 `Object.getOwnPropertyNames(Object.getPrototypeOf(obj))` 看，别只看 `Object.keys` |
| 6 | 插件没注入（`NO_PLUGIN`） | 当前 tab 不在授权域名列表里 | `bsk navigate` 到 `aitoearn.cn` / `aitoearn.ai` 等已授权来源 |
| 7 | 想开 `chrome://version` 读 profile path | Agent Window 沙箱**拒绝访问 `chrome://`** 页面 | 改从扩展在页面里打的日志拿扩展 ID，再反查（见 §5） |
| 8 | 在 Bash 里调 `powershell.exe` 被安全策略拒绝 | Bash 调 PowerShell 会绕过其安全检查 | 改用独立的 PowerShell 工具；且**别在 `-match` 里写 `%xxx%`**（会误判成 cmd 的 `%VAR%` 语法而被拦） |

---

## 4. 根因：扩展在 Service Worker 里把时长算成 0（隐藏契约）

`D:\aitoearn-extension\js\background.js` 里：

```js
// 类 H（工具类）
static async getVideoMetadata(e){
  return new Promise(((t,n)=>{
    if ("undefined" == typeof document){                 // ← MV3 SW 里 document 就是 undefined
      const n = "string" == typeof e ? 0 : e.size;
      return void t({duration:0, width:1920, height:1080, rotation:0, size:n})   // ← 直接编造元数据
    }
    ... // 有 DOM 时才真的用 <video> 探测
  }))
}
```

视频号发布链路上，上传器返回的就是这份元数据：

```js
// 类 rn（wxSph 上传器）
return ...,{url:..., fileSize:e.size, duration:Math.ceil(n.duration),   // ← n 就是上面那份
            width:n.width, height:n.height, startUploadTime:c, endUploadTime:d}
```

然后提交剪辑任务时校验：

```js
// 类 nn（WxSphPublisher）
async submitClipTask(e){
  if (e.video.duration < 3) throw new h(t("wxSphVideoDurationTooShort"), d.VALIDATION_ERROR);
  ...
}
```

**救命的旁路**——发布器读元数据时**优先取 payload 里的 `videoMetadata`**：

```js
// 类 sn（WxSphPublisher）
getWxSphConfig(e){ return e.platformConfig?.wxSph || e.platformConfig || {} }
async getVideoMetadata(e, t){
  const n = t.videoMetadata;
  if (n?.width && n.height && n.duration) return {...n, size: n.size || e.size};   // ← 命中就跳过 SW 探测
  return {...await H.getVideoMetadata(e), size: e.size};                          // ← 否则走上面那个 duration:0
}
```

所以：**`platformConfig: { wxSph: { videoMetadata: { width, height, duration, size } } }` 即可绕过。**
（`duration` 会被 `Math.ceil`，传小数秒没关系。）

> ⚠️ **不要改扩展源码**。这是外部软件，按 `repair-gate`：**只报告、只传参绕行**。
> 记为「上游缺陷」即可，改动它会污染用户环境且升级即失效。

**其他参数（顺带记下，都是同一个函数里读的）**：
`validateParams` 只校验 `type==="video"` + `video` + `cover` 必传、`desc.length<=2000`、`topics.length<=10`。
定时发布用**顶层** `scheduledTime`（毫秒时间戳，> now 才生效 → 写入 `effectiveTime`）；
`postFlag`/`poiInfo`/`event`/`extLink` 也从 `platformConfig.wxSph` 里读。

---

## 5. 怎么反查这个扩展（下次报错时用）

1. 让插件在页面上跑一次，然后读控制台，**扩展 ID 会印在资源路径里**：
   ```bash
   bsk console --session <sid> | grep "chrome-extension://"
   # → chrome-extension://hnmocdhmnfgcjnedmdgfefcobideaeja/js/content_script_home.js
   ```
2. 用 ID 到 **`Secure Preferences`**（不是 `Preferences`！未打包扩展的 `extensions.settings` 条目在这里）反查安装路径：
   ```bash
   python -c "
   import json,io
   p=r'C:\Users\Administrator\AppData\Local\Google\Chrome\User Data\Profile 2\Secure Preferences'
   d=json.load(io.open(p,encoding='utf-8'))
   print(json.dumps({k:v for k,v in d['extensions']['settings'].items()
                     if 'aitoearn' in k.lower() or v.get('path','').lower().find('aitoearn')>=0},
                    ensure_ascii=False)[:800])"
   # → {"path": "D:\\aitoearn-extension", "location": 4}   ← location:4 = 未打包
   ```
3. 文案反查比读代码快：先在 `_locales/zh_CN/messages.json` 里按中文报错找到 message key
   （如 `wxSphVideoDurationTooShort`），再拿 key 去 `js/background.js` 里 grep，直接定位抛错点。

> 注意：**先按 ID `grep -rl` 整个 Chrome User Data** 若没命中，别放弃——
> 未打包扩展的详细条目只在 `Secure Preferences`；也可能用的是别的 profile（见 `bsk` 的 "Agent Window"）。

---

## 6. 发完必须复核（不能只信返回码）

```bash
bsk navigate --session <sid> "https://channels.weixin.qq.com/platform"
sleep 8
bsk snapshot --session <sid> | grep -nE "视频|作品"
```

**判据**：作品列表**首位**出现该条，且时间戳与 `publishTime` 对得上、描述与投递文案逐字一致。
（`/platform/post/list` 这个深链在 Agent Window 里会渲染成空白，**别用深链**，用 `/platform` 首页。）

---

## 7. 与本机其他视频号通路的关系

| 通路 | 落点 | 是否公开 | 依赖 |
|---|---|---|---|
| **本 skill**（AiToEarn 插件） | 视频号作品 | **公开** | bsk + Chrome 常开 + 插件授权 |
| `d2v-channels-publish`（`publish_channels.py`） | **草稿箱** | 不公开 | bsk + `bsk upload` + 窗口可见性门禁 |
| 矩媒 `publish_via_matrixmedia.py --mode draft` | 草稿箱 | 不公开 | 矩媒账号（视频号已失效，2026-10-13 弃用） |

**选择判据**：用户要「发」→ 本 skill；用户要「进草稿箱/我自己去后台发」→ `d2v-channels-publish`。

---

## 8. 凭据与「为什么重复配置」（2026-10-13 用户质疑后的定论）

**AiToEarn API Key 的落点**：`各Agent档案/hermes/hermes相关 key汇总.md` → §二·平台 → 「AiToEarn」节。
（备份：`D:\Obsidian Vault\备份\WK-20261013-08-登记AiToEarn-key-20261013-213733`）
登记走 skill `key-registry-maintenance` 的纪律：剔零宽字符 → 查重 → 定点插入 → `od -c`/Python 字节级验证 → **真实探活**。

**为什么「Codex 配过、WorkBuddy 还要配」——因为本机是三个独立 harness，密钥不互通：**

| 事实 | 证据（2026-10-13 全量核查） |
|---|---|
| Codex **没把这个 key 落盘** | `grep -rn "H5wIKfb"` 全 vault **零命中**；`.codex/config.toml` 及其所有备份**均无 AiToEarn** |
| Codex 是在会话里**用完即弃** | 231 个 Codex 会话里仅 1 个碰过 `api/v2/channels`，且是**账号授权回调**、非发布、非持久化 |
| 10-12 那次视频号发布走的是**浏览器腿** | 该会话统计：`bsk` 2369、`plugin` 184、`channels.weixin` 56；而 `assets.aitoearn` **0**、`publish/flows` **0**、无 `X-Api-Key` |

**结论**：工作区/文件可以共享，**运行时密钥不共享**。Codex、Hermes、WorkBuddy 各存各的凭据；
一个 harness 里对话里用过的 key，**不会自动出现在另一个 harness**。→ 需要用的 key，
**必须显式登记到 `hermes相关 key汇总.md`**，这才是跨 harness 的唯一共享面。
