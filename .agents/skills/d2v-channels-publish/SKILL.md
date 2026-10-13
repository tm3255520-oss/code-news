---
name: d2v-channels-publish
description: 把视频文件自动推进「视频号草稿箱」、以及**删除草稿箱里的草稿**的实操手册（D2V 产线的发布段）。当用户说「推视频号」「发视频号」「进视频号草稿箱」「推一条到视频号草稿箱」「把这条视频传上去」「跑一下视频号发布」「视频号上传卡住了/传不上去」「删掉视频号草稿」「草稿箱里的测试存档要删掉」时使用。核心是**窗口可见性门禁**——Agent Window 被遮挡时 Chrome 对 hidden 文档不加载任何媒体，页面永远卡在 `<video>` 元数据校验处且**不报错**；本文给出该门禁的判据、症状形态、窗口操作安全约束，以及 bsk upload 交付、短标题 6–16 两端拒绝、ID 差分验证这四条落地判据；§10 给出草稿箱删除的完整 SOP（含「作品管理页的删除 ≠ 草稿箱的删除」这个致命区分）。**边界**：只管**视频号**上传进草稿箱与草稿删除；**公众号**发布与合规走 wechat-channel-ops；视频**转录**走 note-transcription；**产线故障定位**走 hermes-pipeline-repair。
agent_created: true
version: 1.1.1
tags: [视频号, channels, d2v, bsk, publish, 自动化, 草稿箱]
---

# D2V 视频号自动上传（含窗口可见性门禁）

> 落地实现：`C:/Users/Administrator/.hermes/scripts/publish_channels.py`（**v4.5**，2026-09-15 两次端到端通过）
> 窗口助手：`C:/Users/Administrator/.hermes/scripts/_bsk_win.ps1`（随主脚本自动落盘，不用手工维护）
> 草稿删除：`C:/Users/Administrator/.hermes/scripts/del_channels_draft.py`（2026-09-15 新增，干跑默认 / `--go` 实删）—— 见 §10
> 2026-09-15 全链路打通，草稿箱 2 → 3 → 4 条，两次都是「恰好 +1」。

## 0. 这个 skill 管什么、不管什么

**管**：手上有一个 mp4 → 自动传进视频号草稿箱 → 用 API 证明真的进去了；**也管删草稿箱里的草稿**（§10）。

**不管**（别在这里找）：
| 事情 | 去哪 |
|---|---|
| 文章 → 口播稿 → mp4（上游产线） | `D:\OpenClaw\ai_tool_review\`（`scripts/00_run_all.py` 一键） |
| 视频号接口报错、产线静默失败、配置漂移 | skill `hermes-pipeline-repair`（本 skill 只写正常路径与症状辨认） |
| **公众号图文**发布 | skill `wechat-channel-ops` ← **注意：那是公众号，不是视频号，两套完全不同的系统** |
| 该不该动手修 | skill `repair-gate`（默认只报告） |
| 跑得久怕卡死 | skill `execution-timeout-guard` |

**这个词的歧义**：用户说「微信」时，先分清**公众号**（图文，后台 `mp.weixin.qq.com`）还是**视频号**（视频，后台 `channels.weixin.qq.com`）。本 skill 只管后者。

---

## 1. 30 秒速用

```bash
PY="C:/Users/Administrator/.hermes/hermes-agent/.hermes-runtime/python/cpython-3.11-windows-x86_64-none/python.exe"

env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 "C:/Users/Administrator/.hermes/scripts/publish_channels.py" \
  --publish "<视频绝对路径.mp4>" \
  --title "<6–16字标题>" \
  --desc "<描述，可留空>" \
  --topics "#话题1#话题2"
```

> **`env -u ...` 不是可选项**：环境变量里的 `HTTP_PROXY` 是 **IDE 注入的临时代理，端口每次会话都变**
> （见过 55642 / 57154 / 52874），且**不转发外网** —— 不清掉会让所有外网调用超时
> （2026-09-16 实测：edge-tts 因此报 `NoAudioReceived`，清掉即成功）。
> `-u`（无缓冲）+ `-X utf8`（防 Windows GBK 下 ✅ 等字符崩）是标配。**必须用上面这个 Hermes runtime python**，
> 别用 `binaries\python`（缺 Hermes 依赖，实测 `No module named 'yaml'`）。

### 参数表（照 argparse 抄的，别猜）

| 参数 | 说明 |
|---|---|
| `--publish <video.mp4>` | 自动上传 + 填表 + 保存草稿（主路径） |
| `--wait-video` | **人工兜底**：等你手动拖入视频，脚本负责填表 + 保存（需配 `--title`） |
| `--title` | 短标题，**6–16 字硬限**，两端都拒绝（见 §5.3） |
| `--desc` / `--topics` / `--location` | 描述 / 话题（`#a#b`）/ 地理位置 |
| `--save-only` / `--publish-now` | **默认存草稿**；不显式给 `--publish-now` 就绝不发表 |
| `--wait-minutes N` | `--wait-video` 模式的等待分钟数（默认 5） |
| `--no-fallback` | `--publish` 时禁止降级：上传不了就直接失败，不等人工 |
| `--check-login` | **登录态硬判据（首选）**：直接给「正常 / 被重定向到 login.html」的结论（见 §2.3） |
| `--list` | 列草稿箱（登录态失效时报 `errCode=300333`，**只能佐证、不能单独定案**） |
| `--draft-object-id <id> --verify` | 验证指定草稿的完整性 |
| `--check --title <标题>` | 只跑发布前检查清单，不发布 |

### 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功（含「结果不确定、请人工确认」的分支 —— 看日志别只看码） |
| 1 | 视频文件不存在 |
| 2 | bsk session 起不来，或标题校验被拒 |
| 3 | 某个阶段失败（上传 / 填表 / 保存） |
| 4 | **验证失败**：ID 差分无新增，或命中的草稿没有视频 |

---

## 2. 前置条件核查（跑之前 30 秒，能省半小时）

### 2.1 用对数 python

```bash
"$PY" -c "import sys,requests,yaml;print(sys.version)"
```
跑不通 → 用错 python 了，回到 §1。

### 2.2 bsk 版本（**这条最容易被忽略**）

```bash
bsk --version          # 实测 2026-10-08 = bsk 0.3.2
bsk status             # 状态看顶层；`bsk daemon status` 会报 unrecognized subcommand
```

**下限是 0.2.1**（**0.1.6 及更早没有 `upload` 命令** —— 那时「自动上传不可能」是真的，
详情见 `hermes-pipeline-repair` §6.3）。
**当前实测版本 0.3.2**（2026-10-08 本机端到端跑通：`--check-login` / `--list` / `--publish` 均正常）。
> 注：文中其它处出现的「0.2.1」，若是**版本演进史**（如「升到 0.2.1 后 `upload` 可用」）则属历史记录、不改写；
> **本机当前版本一律以本节为准**。
**教训顺序：先核工具版本，再怀疑物理限制。**

### 2.3 登录态在**对的那个** Chrome profile（历史上最大的一次误判）

本机有 3 个 profile：

| profile | 名字 | 账号 |
|---|---|---|
| `Profile` | 您的 Chrome | — |
| `Profile 2` | **M** | tm3255520@gmail.com |
| `Profile 3` | **工作** | — |

**视频号登录态在「工作」(Profile 3)**（2026-09-15 实测）。查法：

```bash
"$PY" -X utf8 -c "
import json,pathlib
p=pathlib.Path.home()/'AppData/Local/Google/Chrome/User Data/Local State'
d=json.loads(p.read_text(encoding='utf-8'))
for k,v in d['profile']['info_cache'].items(): print(k,'|',v.get('name'),'|',v.get('user_name'))
"
```

**首选入口：`--check-login`** —— 一步到位给出硬判据的结论（2026-10-08 实测）：
```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 <publish_channels.py> --check-login
```
- `[OK] 视频号登录态正常（https://channels.weixin.qq.com/platform/post/create）` → 继续。
- `[FAIL] 视频号登录态失效：被重定向到 https://channels.weixin.qq.com/login.html` → 需重新扫码。

> 它把「访问发布页是否被重定向」这一步直接做掉并给出结论 —— **不用自己从 `--list` 的 errCode 去推**。
> 该参数脚本里早已存在（`argparse` 有 `--check-login`），本手册此前只写了 `--list` 这条更绕的路。

**辅助佐证：`--list`**：
```bash
"$PY" -u -X utf8 <publish_channels.py> --list
```
- 能列出草稿 → cookie 有效，继续。
- 报 `errCode=300333/300330` → 佐证身份不对，**但单独不足以定案**。

> ⚠️ `300333`（带 sessionid 但会话无效）**不能单独定案**，它只是佐证；**「被踢到 login.html」才算硬判据**。
> 2026-10-08 实测：`--list` 报 `300333`、`--check-login` 报被重定向到 `login.html` —— 两者一致才定案。
> 曾把 `300333` 误归因为「代理/hosts 劫持」，用三输入对照（真 cookie=300333 / 伪造=300330 / 空=300330）推翻了它。

**重新扫码**（需要时）：
```
顶级页面直接打开：
https://open.weixin.qq.com/connect/qrconnect?appid=wx20d84d087938fd46&scope=snsapi_login&redirect_uri=https%3A%2F%2Fchannels.weixin.qq.com%2Fplatform%2Foauth-callback.html&self_redirect=false
```
扫码 + 微信点「允许」→ 由平台页 JS 自己完成 code→session 交换 → **然后重新导航 `/platform`**，不再被踢到 `login.html` 即成功。
> ❌ **不要手工顶级打开 `oauth-callback.html`**：会黑屏（`state=undefined`），换 session 的 JS 不在那个页面里。

### 2.4 标题与视频

- 短标题**先自己数一遍字数**（6–16）。脚本会拒，但早点发现省一轮。
- 待上传目录：`C:/Users/Administrator/Videos/视频号待上传/`
  ⚠️ 这里**可能残留上一次的旧 mp4**（清理时 `safe-delete` 会失败但不阻断）→ **上传前确认拿的是本次文件**。

---

## 3. 正常输出基线（长这样 = 成功）

```
[INFO] 标题校验: 通过 | 最终: HTML转视频全流程
[INFO] --publish 前置快照: 草稿箱现有 3 条（用于 ID 差分验证）
[INFO] 可见性前置检查: OK — Agent Window 已可见（media=loadedmetadata，title=视频号助手）
[INFO] bsk upload(input) 已交付文件，等待页面接收...
[INFO] ✅ 视频已就位
[INFO] 阶段: draft-saved | 已点击保存草稿（@e35），待 API 复核
[VERIFY] 草稿箱 3 → 4 条，新增 1 条
[VERIFY] 命中草稿（ID 差分）: export/UzFfBgAAxNmHVFBUfV_Mk8zT4DCagBukcnCWvOaIqTe
[VERIFY]   title=HTML转视频全流程 | video=✅ | status=1
✅ 验证通过：保存草稿成功（依据：ID 差分）
[台账] 已登记: HTML转视频全流程 | 待发布
```

**成功 = 下面四条同时成立**（少一条都不算）：

1. `可见性前置检查: OK`（**没有这一行就等于没跑通**，见 §4）
2. `新增 1 条`（不是 0，也不是 2）
3. `video=✅` 且 `status=1`
4. `[台账] 已登记` —— 台账落在 `D:\Obsidian Vault\obsidian Vault\内容生产\5-发布\发布台账.md`（幂等，重复标题不会写第二遍）

---

## 4. ★窗口可见性门禁（本 skill 的核心）

### 4.1 因果链（全部实测，不是推测）

```
Agent Window 被用户自己的 Chrome 窗口完全遮挡
  → Chrome 原生窗口遮挡检测（Windows: CalculateNativeWinOcclusion）判它 occluded
  → document.visibilityState === 'hidden'
  → Chrome 对 hidden 文档一律不加载任何媒体资源
  → 视频号发布页靠 <video> 读元数据校验时长/分辨率，这一步永远不返回
  → beforeUpload 之后零上传请求，页面只造一个坏掉的 blob: 预览
  → bsk upload 交付的文件被「接住但不用」
```

**对照实验**（把窗口抬到最前，同一个 ref、同一个文件）：
```
before: vis=hidden   → <video> TIMEOUT          rs=0
after : vis=visible  → <video> loadedmetadata   rs=4     ← 立刻恢复
```

### 4.2 症状形态（记住这个形状，能省三天）

| 观测量 | 值 |
|---|---|
| `videoEl.readyState` | **永远 0** |
| `videoEl.networkState` | **永远 2**（LOADING） |
| `videoEl.error` | **null —— 不报错！** |
| 表现 | **永久挂住**：无异常、无 console 报错、无网络失败 |

> ⚠️ 它长得像「资源还在加载」，其实是「Chrome 根本不打算加载」。
> **`error === null` 不等于没问题 —— 沉默本身就是症状。**
>
> ⚠️ `bsk upload --mode input` 此时会报 `the upload trigger did not activate a file input`。
> **这个报错是在说谎**：`@eN` 没选错，是 hidden 门禁。修好可见性后同一个 ref 直接成功。

### 4.3 门禁判据

```python
def _media_gate_open(st): return st.get("v") == "visible"     # 只看 visibilityState
```

**为什么不用 `media` 当判据**：因果链上「媒体能不能加载」是**被 visibility 决定**的。
若把 `media` 也写进判据，探针负载自身的任何问题都会反过来卡死主流程
（本机真踩过：探针坏了 → 门禁比真实要求还严）。

**探针负载有讲究**：必须用解码器能真正读出元数据的负载 —— 一个 **844 字节 / 8bit / 8kHz 单声道 WAV** 的
`data:` URL（完全自包含）。第一版塞了个「只有 `ftyp` 盒、没有 `moov`」的 28 字节假 mp4，
任何浏览器都 `error` → 页面前台可见时照样报 `media=error` → **假信号**。

> **规矩：长二进制常量一律用代码生成 + 当场自证，绝不手抄。**
> 更早的一版把 1128 字符的 base64 手工分行抄进源码，拼成 12086 字符、第 1086 位起错位 →
> 浏览器对**任何**负载都报 `error`，形状跟真信号一模一样，差点把整条证据链搅浑。

### 4.4 窗口操作三条安全约束（`_bsk_win.ps1`，Python 调 PowerShell）

```
抬起：EnumWindows → GetClassName == 'Chrome_WidgetWin_1' → 标题匹配 → hwnd
      SetWindowPos(hwnd, HWND_TOPMOST=-1, x,y,w,h, SWP_SHOWWINDOW=0x40) + SetForegroundWindow
还原：SetWindowPos(hwnd, HWND_NOTOPMOST=-2, 原x,原y,原w,原h, 0x50)   # 原位置先落 state.json
```

1. **只接受 `Chrome_WidgetWin_1`** —— 别把标题匹配到的任意窗口都动。
2. **拿不到页面标题就拒绝操作** —— 否则助手会匹配「第一个 Chrome 窗口」，
   那很可能是**用户自己正在用的窗口**，一动就把人家窗口挪走。代码里这是硬 gate。
3. **抬起尺寸别盖满屏**：默认 `900×640`（脚本内嵌值）。第一版用了 `1320×1497`，几乎占满用户屏幕。
4. **只还原自己抬过的那个窗口**（`_RAISED_TITLE` 有记录才动）。
5. **它不该是正确性的硬依赖**：抬不起来就只报告 + 退回原失败路径（「提升成功率」而非「不抬就不干活」）。

工程细节（踩过的）：
- 窗口标题走命令行会被中文/引号弄坏 → **用 base64 传**（`-TitleB64`），PS 里 `[Console]::OutputEncoding = UTF8` 防回显乱码。
- `[System.IntPtr]` 转 int64 用 `[int64]$h`；**`$h.ToInt64()` 会报「找不到重载」**。
- **等待循环里要周期性复抬**（`nudger`）—— 窗口会再次被遮挡而掉回 hidden。

### 4.5 已排除的替代解释（**别再重查一遍**）

| 假设 | 对照实验 | 结论 |
|---|---|---|
| 文件本身坏了 | 23,573,879 B 全量读取、MP4 `ftypisom` 头正确 | ❌ 排除 |
| 路径含中文 | 换纯 ASCII 路径（sha256 与原文件逐位相同） | ❌ 排除 |
| 编解码不支持 | `canPlayType` / MSE / WebCodecs（`VideoDecoder.isConfigSupported('avc1.42E01E')` = supported） | ❌ 排除 |
| CSP 拦截 | console 无任何拦截记录 | ❌ 排除 |
| 资源加载整体坏了 | **同一上下文** `<img>` 的 data URL **225ms 成功** | ❌ 排除（只卡媒体元素这道门） |
| 「网络/文件来源才受影响」 | 干净 `about:blank` + `data:` URL，连 844 B 的 WAV 都加载不了；纯内存 Blob 一样 | ❌ 排除（与来源无关） |
| 「CLI 没把文件送到」 | capture 阶段 drop 监听：`name/size/type` 全对、`types:["Files"]`、页面 `beforeUpload` **被调用** | ❌ 排除（送到了） |
| 「元素 ref 选错了」 | 修好可见性后**同一个 ref** 直接成功 | ❌ 排除 |

---

## 5. 四个阶段的判据

### 5.1 登录态

见 §2.3。硬判据 = **是否被重定向到 `login.html`** / `--list` 能不能列出草稿。

### 5.2 上传：主路径 `bsk upload`

```bash
bsk upload --session "$SID" --file "<视频绝对路径>" --mode input   # 优先
bsk upload --session "$SID" --file "<视频绝对路径>" --mode drop    # 兜底（需明确放置目标）
```
脚本里 `try_auto_upload()` 依次试 `input` → `drop`，两条都失败才降级人工（**绝不伪造成功**）。

**验证「送到了没」别只看退出码**：预埋 capture 阶段的监听（`capture=true`，必须在页面自己的 handler 之前拿到）：
```javascript
document.addEventListener('drop', e => {
  window.__probe = {n: e.dataTransfer.files.length, name: e.dataTransfer.files[0]?.name,
                    size: e.dataTransfer.files[0]?.size, type: e.dataTransfer.files[0]?.type};
}, true);
```
> **「文件送到了吗」和「页面用不用」是两个独立问题，必须分开验证。**
> 实测过：drop 交付的是**真文件**、`beforeUpload` 也被调用了 —— 然后卡在 §4 那道门。

**兜底路径**（页面结构大改时）：
```
① bsk click <上传区 ref>  → 页面懒创建 input[type=file] + 弹出 Windows 原生「打开」对话框（窗口类 #32770）
② Python ctypes EnumWindows 找 #32770 → SetForegroundWindow
③ 剪贴板写入视频绝对路径 → Ctrl+A（清空文件名框）→ Ctrl+V → Enter
④ 轮询 <video>：readyState === 4 且 duration ≈ 预期 → 完成
```
> `reg.exe` / `tasklist` / `wmic` 常被本机安全策略拦 → 进程/窗口枚举一律用 Python `ctypes`。
> ⚠️ **64 位 ctypes 必须显式声明签名**，否则 HANDLE 被截断成 32 位 →
> `OSError: access violation writing 0x...0020`。要声明的是 `GlobalAlloc.restype/.argtypes`、
> `GlobalLock.restype/.argtypes`、`OpenClipboard.argtypes`、`SetClipboardData.restype/.argtypes`。

### 5.3 填表：两个字段的坑完全不同

| 字段 | 结构 | aria 是否暴露 | 填法 |
|---|---|---|---|
| 短标题 | `input[placeholder*="短标题"]` | ✅ 暴露（如 `@e28`） | `bsk fill @e28 "标题"` |
| 描述 | `div.input-editor[contenteditable][placeholder="添加描述"]` | ❌ **不暴露** | JS `focus()` + Range 把光标放末尾 → `bsk press Ctrl+V` |

**短标题 6–16 字：两端都拒绝，绝不静默加工**
- 超 16 字 → 页面报 `error-title`「标题超过16字限制」+ **「保存草稿/发表/手机预览」三按钮同时**
  拿到 `weui-desktop-btn_disabled` → 点击**毫无反应** → 保存静默失败（极易误判成「页面卡住」）。
- 不足 6 字 → 旧版会补成 `短。。。。。`，那是**静默造假**（进草稿箱的标题不是产线给的）→ 现已直接拒绝。
- **判据要问页面，不要问自己的常量**：
  ```javascript
  document.querySelector('.error-title')?.textContent
  [...document.querySelectorAll('button')].map(b => [b.textContent.trim(), b.className])
  ```

**「标题对上了没」别用严格相等** —— 平台会规范化（全角/半角、空格、省略号）。
用 `_title_similar(actual, expected)`：**≥6 字 且 ≥较短串的 80%**。
> 相对占比不是洁癖：`GitHub新星5万星HTML转视` vs `GitHub5万星HTML转视频` 的最长公共子串有 **9 字**
> （占短串 56%），把阈值从 4 提到 6 根本挡不住。**但本质仍不可靠** —— 真判据是 ID 差分。

描述里写 `#话题` 会被平台**自动识别成真话题**（DOM 变成 `<span class="topic">`），不用额外操作。

### 5.4 保存与验证：**ID 差分才是事实**

```python
before = snapshot_draft_ids(cookie)      # 任何写操作之前先拍
# ... 保存 ...
after  = snapshot_draft_ids(cookie)
new_ids = set(after) - set(before)        # 恰好 +1 = 本次存的
```

**为什么必须差分**：草稿箱本来就有历史草稿，「找到一条标题相似的」会把别人的账算成自己的
（假阳性）；平台截断标题又会算不过（假阴性）。差分把判据从「猜」变成「事实」。

```
POST {API_BASE}/post/get_draft_list     # API_BASE=https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin
POST {API_BASE}/post/get_draft_info     {objectId}
```

**通过标准**：`errCode==0` + 条数 +1（差分恰好 1 条，新增条目 `video=="Y"`）
+ `get_draft_info` 里 `media` 有视频且已生成 URL、`status==1` + 台账登记返回 True。

> 差分 > 1 条要警惕**重复提交**（脚本会取最新一条并打 WARN）；差分 = 0 就是**没存进去**，
> 此时脚本会把现场落盘到 `~/.hermes/logs/channels_verify_fail_<时间戳>.json`（草稿列表快照 + 期望标题）——
> 事后一眼看出是「压根没存」还是「存了但字段不对」。

---

## 6. 故障速查表

| 症状 | 先查什么 | 处置 |
|---|---|---|
| **永久挂住，不报错**，`readyState=0` / `error=null` | `document.visibilityState` | **§4 可见性门禁** —— 抬窗口，别改代码 |
| `the upload trigger did not activate a file input` | 同上 | **这个报错在说谎**，先确认可见性再怀疑 ref |
| 三按钮全灰、点保存没反应 | `.error-title` 文案 | 标题超 16 字 → 换 6–16 字 |
| `errCode=300333` | **是否被重定向到 `login.html`** | 被踢 → profile/登录态不对（§2.3） |
| `bsk` 报 `browser rejected the underlying CDP call` | — | **同 session 反复操作的瞬态失败，重试即可**，别当成选择器写错去改代码 |
| `bsk daemon status` 报 `unrecognized subcommand` | — | 用顶层 `bsk status` |
| `bsk session list` 显示 `(no active sessions)` | — | **会话不跨 shell 命令存活**；窗口操作与会话必须在同一进程生命周期内 |
| 跑 python 的命令**一行输出都没有**就 SIGTERM | 是否用了 `capture_output=True` | **bsk 的 `session start` 会留下持有管道句柄的子进程** → `run()` 等不到 EOF → 宿主杀整条命令。改输出走临时文件（`hermes-pipeline-repair` §1.7）。<br>⚠️ **版本注**：该症状在 **0.2.1** 观察到；**0.3.2 实测已不复现**（2026-10-08 探针：`capture_output=True` 下 0.2s 正常返回 rc=0）。但**保守做法照旧**——临时文件方案零成本，不值得为省它去赌 |
| 探针报 `media=error` 但在前台页面也复现 | 探针负载本身 | 负载坏了 → 见 §4.3「长常量代码生成 + 当场自证」 |
| `视频号待上传\` 里有多余旧 mp4 | — | `safe-delete` 失败（`SHFileOperationW 0x2`）**无害不阻断**，但人工拖拽前确认拿的是本次文件 |

---

## 7. 人工兜底（自动上传失效时）

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 "<publish_channels.py>" \
  --wait-video --title "<6–16字>" --desc "<描述>" --wait-minutes 10
```
启动后**人工把 mp4 拖进发布页**，脚本自动接管填表 + 保存 + 验证。

> `--publish` 在自动上传失败时**默认会自己降级**到这条路径（同一个 session 继续用），
> 不想等人工就加 `--no-fallback` 直接失败。

---

## 8. 纪律（红线）

1. **默认只存草稿** —— 不显式给 `--publish-now` 就绝不点「发表」。
2. **绝不伪造成功** —— 上传没成功、验证没过，就如实报失败，宁可退回人工。
   静默补字凑标题、把「找不到」当成「已发布」，都属此类。
3. **只动自己抬起来的那个窗口** —— 拿不到标题就什么都不做（用户可能正在用那个窗口）。
4. **收尾两个固定动作**：`release_agent_window()`（还原置顶与位置）+ `bsk session stop --all`（不留野 session）。
5. **vault 不放密钥** —— cookie / sessionid 只存在内存与 `~/.hermes/`，**绝不写进 vault 任何文件**。
6. **改 `publish_channels.py` 前先备份 + 改后跑真机验证**（脚本无版本控制，只有 `.bak` 习惯）。
   动过之后要重跑 §3 基线，不能只看 diff。

---

## 9. 相关文档与 skill

**vault（`D:\Obsidian Vault\obsidian Vault\系统中枢\`）**
- 运行手册：`运行手册/视频号草稿箱自动上传SOP.md`
- 硬规则：`经验沉淀/工作流/platform-publish-automation.md` **§11 视频号发布专属硬规则**
- 踩坑复盘：`经验沉淀/复盘/2026-09-15-视频号发布自动上传打通-三次误判.md`
- 导航：`地图与导航/MOC/视频号生产线地图.md`

**skill**
- `hermes-pipeline-repair` —— §1.6 工具版本 / §1.7 管道死锁 / §1.8 长常量 / §6 视频号上传的完整取证过程
- `repair-gate` —— 想「顺手修一下」之前先看这个
- `execution-timeout-guard` —— 上传等待是长任务，别傻等
- `wechat-channel-ops` —— **公众号**通道（别和视频号混）

---

## 10. 草稿箱运维：删除草稿（2026-09-15 首用并固化）

**实现**：`C:/Users/Administrator/.hermes/scripts/del_channels_draft.py`（**干跑默认 / `--go` 实删**）

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 "C:/Users/Administrator/.hermes/scripts/del_channels_draft.py"        # 干跑（只定位、不点击）
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 "C:/Users/Administrator/.hermes/scripts/del_channels_draft.py" --go   # 实删（不可逆）
```

目标在脚本顶部 `TARGETS` 里改，以 **(createTime, shortTitle) 双要素**锚定 —— **不要用标题模糊匹配**。

### 10.1 ★★★ 致命区分：两个页面都有「删除」，文案一模一样

| 页面 | 路由 | 那儿的「删除」删的是 |
|---|---|---|
| **草稿箱** | `/platform/post/draftListManager` | 草稿 —— **我们要的那条路** |
| 作品管理 | `/platform/post/list` | **已发布作品** —— 点错就删线上作品 |

两页按钮文案**都叫「删除」**，快照形态也像，唯一区别是路由。
⚠️ **草稿箱路由不是从 href 读出来的**：左侧导航是 SPA（`href="javascript:;"`，读 href 只会拿到
`javascript:;`）。只能 JS 点 `草稿箱` 导航项、再看 `location.href` 变化，才会暴露 `draftListManager`。

### 10.2 ★★ aria 快照的 `ctx:` 会串行污染 —— 定位行绝不能用它

4 行草稿时实测：第 3/4 行按钮的 `ctx` 会**错指第 1 行的日期**
（`@e21/@e22` 的 ctx 写着 `2026年09月15日 16:22`，实际它属于 `08月17日 01:10` 那行）。
删掉一行重取快照后又恢复正常 —— 属「行数多时」的偶发污染。

**正确做法**（脚本 `map_delete_buttons()`）：按文档顺序遍历，
遇 `StaticText "YYYY年MM月DD日 HH:MM"` 记下当前日期，遇 `button "删除"` 与**最近一次的日期**配对。

### 10.3 删除是两步，判据只能是 objectId 差分

```
点「删除」→ 弹独立 layer 的「删除草稿」确认框（@e2 "取消" / @e3 "确定"）→ 点「确定」
不点「确定」 = 没删。
```

删除接口（留档便于将来 API 化；**body 未取证，别凭猜写死**）：
```
POST https://channels.weixin.qq.com/micro/content/cgi-bin/mmfinderassistant-bin/post/del_draft
```
每次删除后页面立即 `get_draft_list` 刷新 —— 这正好给 ID 差分提供了窗口。

### 10.4 硬断言清单（脚本已内建，改脚本时别删）

1. 目标以 **(createTime, shortTitle) 双要素**锚定，两个都对上才认；
2. 点击前断言：API 侧命中恰好 1 条、UI 侧该日期命中恰好 1 个删除按钮；
3. 每删一条用 **ID 差分**证明「恰好少了预期那一条」，不符预期**立即停止**；
4. 每删一条**重取快照**（列表重排，ref 失效）；
5. 窗口必须可见；抬不起来就 abort（hidden 文档不渲染，点不到）；
6. 目标不存在时 **abort（rc=3）而非静默跳过** —— 避免「以为删了其实没删」。

> **首次使用实况（2026-09-15）**：两条测试存档 —— `1789460551`（HTML转视频全流程，09-15 16:22）
> 与 `1789460451`（GitHub5万星HTML转视频，09-15 16:20）—— 已删，草稿箱 **4 → 2**；
> 作品管理**无新增**（这一步同时证明了「是删除，不是被发表」）。
> 现场取证落在 `%TEMP%\draft_del_run\`：`snap_dialog_*.txt` = 确认弹窗快照，
> `snap_pre_*.txt` = 删掉第一条后的 3 条列表（可用于事后复盘「到底删的是哪条」）。

---

## 11. 维护记录与待确认项

**版本 1.1.1**（2026-10-08）：**四处与实际不符的更正**（用户当场确认后执行）。
来源为该轮实测：`card13/final.mp4` 推草稿箱时先卡在登录态失效，靠 `--check-login` 一次定案。
① **§2.2 bsk 版本**：原写「期望 bsk 0.2.1」，实测已是 **0.3.2** →    改为「下限 0.2.1 / 当前实测 0.3.2」。
② **§2.3 登录态判据**：原只教 `--list` 看 `errCode`（而 `300333` 按本文自己的说法「不能单独定案」），
   漏了脚本里早已存在的 **`--check-login`** —— 它直接给「正常 / 被重定向到 login.html」的结论，
   是硬判据的一步到位入口。已把它提为首选、`--list` 降为佐证；**§1 参数表同步补该参数**。
   实测对照：`--list` 报 `300333` + `--check-login` 报被重定向到 `login.html` → 两者一致才定案。
③ **§6 速查表「管道死锁」行**：原把症状绑死在「bsk 0.2.1 的 session start」，改为**不绑版本**，
   并加版本注 —— **0.3.2 实测已不复现**（2026-10-08 探针：`capture_output=True` 下 0.2s 正常返回 rc=0），
   但**保守做法照旧**（临时文件方案零成本，不值得为省它去赌）。
④ **§11 实测环境行**：bsk 0.2.1 → **0.3.2**（保留「首版落地时为 0.2.1」的沿革）。

**版本 1.1.0**（2026-09-15）：新增 **§10 草稿箱删除 SOP**。来源为该轮实测：草稿箱路由
`/platform/post/draftListManager`、与「作品管理页删除」的致命区分、aria `ctx` 串行污染、
`POST /post/del_draft` 端点、「两步确认 + objectId 差分」判据。工具：
`~/.hermes/scripts/del_channels_draft.py`（**新增文件**，未改动任何既有脚本）。
顺带**纯结构调整**：把原本夹在 §9 与 §10 之间的「附录 A」挪到文末（只挪位置，无内容改动）。

**版本 1.0.0**（2026-09-15）：从 `hermes-pipeline-repair` §6 抽出并固化为独立 skill。
内容来源为该轮实测：`publish_channels.py` v4.5、`_bsk_win.ps1`、两次端到端日志、排除表 8 项对照实验。

**实测环境**：bsk **0.3.2**（2026-10-08 复核；本 skill 首版落地时为 0.2.1）/ Hermes runtime python 3.11 / Chrome 三 profile / 视频号后台 `channels.weixin.qq.com`。

### ⚠️ 待确认项（发现但**未擅自改**，按纪律只报告）

1. **`publish_channels.py` 的注释与实测结论矛盾**：
   `find_ref_by_keyword()` 的 docstring 和 `_DEEP_ALL_JS` 的注释仍写着「表单全在 shadowRoot 里」，
   而 2026-09-15 的对照实验证明那是**同源 iframe**（`wujie-app.shadowRoot === null`，
   内容在 `iframe.contentDocument`）。**以实测结论为准**；脚本注释是 v4.3 遗留，未同步。
   → 顺带存疑：`__deepAll` 只递归 `shadowRoot`、**不跨 iframe 边界**，它为何仍能取到元素需要单独确认
   （可能 `bsk evaluate` 的上下文本就在 frame 内）。
2. `hermes-pipeline-repair` §6 与本 skill 内容重叠 —— 建议把 §6 瘦身为「指向本 skill 的短导航 + 只留跨产线通用部分」。
   **未擅自删改**，等用户确认。
3. 本 skill 未覆盖**定时/自动发布**（目前是手动触发）。若要接 cron，需另定失败重试与去重策略。

## 附录 A：函数 ↔ 职责映射（要改代码时先看这张表）

`publish_channels.py` 里与本流程相关的函数（共 51 个函数，下表是这条链路用的）：

| 函数 | 职责 | 出问题先看 |
|---|---|---|
| `page_visibility()` | 读 `visibilityState` + 媒体探针 | §4.3 |
| `_media_gate_open()` | **门禁判据**（只看 `v == visible`） | §4.3 |
| `_wav_probe_data_url()` | 生成 844 B WAV 探针（带 assert 自证） | §4.3 |
| `ensure_agent_window_visible()` | 前置检查 + 最多 3 次抬窗 | §4.1 / §4.4 |
| `release_agent_window()` | 收尾还原（只还原自己抬过的） | §8.4 |
| `_ps()` / `_ensure_ps1()` | 调 PowerShell 窗口助手（标题走 base64） | §4.4 |
| `bsk_cmd()` | **必须走临时文件，不能用管道** | §6 表最后三行 |
| `bsk_session_start()` | 起 session（注意：sid 用 `[a-z]{4}` 正则从输出里抠，**很脆**） | §2.2 |
| `bsk_upload()` | 调 `bsk upload`（`input` / `drop`） | §5.2 |
| `try_auto_upload()` | 上传策略编排 + nudge 复抬 + 失败如实报告 | §5.2 |
| `publish_video()` | 导航 → **可见性门禁** → 上传 → 填表 | §4.1 |
| `wait_for_video()` | 等视频就位（带周期性复抬） | §4.4 |
| `validate_title()` | 6–16 字两端拒绝 | §5.3 |
| `_title_similar()` | 标题相似（**粗筛，非判据**） | §5.3 |
| `fill_short_title()` / `fill_desc()` | 填两个字段（ref / JS 两条路） | §5.3 |
| `find_ref_by_keyword()` | 从 aria 快照按关键词找 `@eN` | §5.3 |
| `_page_validation_hint()` / `_button_states()` | 读**页面自己**的校验提示与按钮状态 | §5.3 |
| `fill_and_save()` | 填表 + 原创 + 保存草稿 | §5.3 / §5.4 |
| `snapshot_draft_ids()` | 发布前拍 objectId 快照 | §5.4 |
| `verify_draft_created()` | **ID 差分验证**（+ 退化到标题相似） | §5.4 |
| `_save_verify_evidence()` | 验证失败时把现场落盘 | §5.4 |
| `record_publish()` | 写发布台账（幂等） | §3.4 |
| `publish_flow()` / `wait_video_flow()` / `_wait_and_fill()` | 三条入口编排（自动 / 人工兜底 / 共用尾段） | §1 / §7 |

> `bsk_session_start()` 用 `re.search(r"[a-z]{4}", out)` 提取 sid —— 只要能匹配到 4 个小写字母就算成功。
> **这是脆弱点**：bsk 输出格式一变就会静默取到错误的「sid」。若出现 `sid` 相关怪问题，第一个查这里。

---
