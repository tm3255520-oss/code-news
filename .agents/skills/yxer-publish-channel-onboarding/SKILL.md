---
name: yxer-publish-channel-onboarding
description: 给蚁小二（yxer CLI）**接入一条新的发布线/平台/内容类型**的标准流程 —— 先零风险证明「这条路真通」，再落代码改路由。含「验证三步」（**核实平台名** → 读 schema → `validate` 正反两向 → 端到端 `--dry-run`）、**6 平台 declaration/createType 枚举对照表**、视频线与图文线的字段契约差异、字段表维护纪律、前置闸要求与测试基线。当用户说「把某平台/某内容类型接到蚁小二」「这条线怎么接」「发布通道换后端」「小红书图文能不能走蚁小二」「新接一个发布平台」时使用。含「接的是一条新**线**时，另起**独立体检件**但判定靠 **import 复用**」的姿势（§六）。**边界**：只讲**发布通道接入**；已接通通道的**封面/文案/必填项内容完整性门禁**归 `publish-content-completeness-gate`；采集线接入归 `platform-line-onboarding`；发布分工的口径文档在 vault `经验沉淀/工作流/platform-publish-automation.md` §12/§13。
agent_created: true
version: 1.3.2
tags: [发布, 蚁小二, yxer, 通道接入, dry-run, schema, 验证, declaration, createType, 平台名]
---

# 给蚁小二（yxer）接一条新发布线

> 权威口径文档：`D:/Obsidian Vault/obsidian Vault/系统中枢/经验沉淀/工作流/platform-publish-automation.md`
> （§12.1 通道矩阵 / §13.5 验证三步 / §13.6 图文线与视频线差异）。**本 skill 是它的可执行版。**
> yxer CLI 版本基线：3.2.26（2026-10-09）。
> 路径：schema `D:/pi-agent/node_modules/@yixiaoermail/cli/schemas/platforms/`，
> 文档 `.../references/platforms/<video|imageText|article>/`，工作流 `.../references/workflows/`。

## 〇、先记住这一条：判据必须有区分度

**恒真的值不是判据。** 本仓库被这条坑过多次，都是同一天内反复踩：

| ❌ 无区分度（别用） | ✅ 有区分度（用这个） |
|---|---|
| `accounts list <平台>` 里有这个平台 | `status == 1`（`2` = 失效**严禁发布**） |
| `x-mcp` 的 `check_login_status` 报已登录 / `success=true` | 返回体**有实质内容**（`nickname`/`user_id` 非空） |
| 矩媒 `/platforms` 的 `hasConfig=true` | 该值**恒真** → 只能证明"支持过"，不能证明"已登录" |
| "代码里有这个平台的分支" / "文档说走这条" | **发布记录**里该平台 `taskSetStatus=allsuccessful` |
| schema 文件**存在**（能力具备） | `--dry-run` **真的跑到完成** |
| yxer 有 B站/头条 schema（能力具备） | 蚁小二**账号配额耗尽**（2026-10-12 用户裁定）→ 这条路**不可用**，改走**矩媒** |

**"能力具备 ≠ 可用"** —— 这是本 skill 存在的理由。

## 一、验证三步（**跑通才准动代码/路由**）

### 第 0 步：确认账号可用

```bash
yxer accounts list <平台> --json          # data:null = 未绑定；status:1=可发；status:2=失效
```
⚠️ 若返 `data: null` 而用户说"已经绑了"：**先怀疑同步延迟**（CLI 走云端 API
`https://www.yixiaomail.cn/api`，客户端本地登录 ≠ CLI 立即可见），**隔几分钟复测**，不要直接判"用户没操作成功"。

### 第 0.5 步：核实**平台名**（2026-10-11 补，最省事的坑）

**别用中文习惯名猜平台名。** 实测（yxer 3.2.26）：

| ❌ 想当然 | ✅ yxer 真正认的 | 后果 |
|---|---|---|
| `B站` | `哔哩哔哩` 或 slug `bilibili` | `schema get B站 video` → `{"message":"schema not found"}` |
| `头条` | `头条号` 或 slug `toutiaohao` | 同上 |
| 抖音/视频号/小红书/快手 | 中文名直接可用 | — |

- 权威来源：`yxer schema list --json`（`data.items[].platform` 是**英文 slug**）；
  官方中文名在 `references/platforms/video/index.md` 的平台表（`头条号 / 哔哩哔哩`）。
- 🔴 **别用 `accounts list <平台>` 判平台名对不对** —— 它对任何字符串都返 `{ok:true, data:null}`，
  错名看起来跟"没绑账号"一模一样，会把人带偏。**要判名字用 `schema get` 或 `schema list`。**

### 第 1 步：读 schema / form contract 定字段（零副作用）

```bash
cat D:/pi-agent/node_modules/@yixiaoermail/cli/schemas/platforms/<平台slug>.<类型>.schema.json
yxer schema fields <平台> <类型>            # 字段视图
yxer publish form start <平台> <类型> --output <session>.json   # 拿 contract（含 required/enum）
```
看**五件事**：`required` / `additionalProperties` / **有没有 `pubType`** / **`declaration` 枚举** / 各 `maxLength`·`minLength`·`minItems`。
- **有 `pubType`** → 有平台草稿箱（视频号 / 公众号 / 头条 / B站）。
- **无 `pubType` 且 `additionalProperties:false`** → **无草稿箱**，`--mode draft` 必然失败（抖音/快手/小红书）。
- ⚠️ **`required` ≠ "你必须自己写"** —— `publish form start` + `form account` **会自动补一部分 required 默认值**
  （实测视频号补出 `{createType:2, declaration:0, formType:task, pubType:1}`）。
  但**账号相关的动态字段不会补**（如 B站 `category` 级联分类，仍须自己取）。判据：
  跑一遍 `form start` + `form account`，看导出的默认值里有没有 —— 别靠猜。
- **`declaration` = 创作声明（含 AI 声明）** —— **各平台枚举值不同，且 `schema` 只给数字、不给标签**。标签要到 **reference** 里查：
  `D:/pi-agent/node_modules/@yixiaoermail/cli/references/platforms/<类型>/<平台>.md`
  已知（2026-10-11 逐个核实 reference，`<类型>=video`）：

  | 平台 | `declaration` 枚举 | 标签 | 本产线取值 |
  |---|---|---|---|
  | 小红书 | `[0,1,2]` | 1-虚构演绎；**2-笔记含 AI 合成内容** | **2** |
  | 视频号 | `[0,1,2,3,7,8]` | 0-无需标注；**1-含 AI 生成内容**；2-含营销广告；3-虚构剧情仅供娱乐；7-内容为转载；8-个人观点 | **1** |
  | 抖音 | `[0,3,4,5,6,7,8]` | **3-内容从 AI 生成**；4-可能引人不适；5-虚构演绎；6-危险行为 | **3** |
  | 快手 | `[0,1,2,3]` | 0-不申明；**1-内容为 AI 生成**；2-演绎情节仅供娱乐；3-个人观点 | **1** |
  | B站 | `[0,1,2,3,4,5,6]` | 0-不申明；**1-AI 合成**；2-危险行为；3-仅供娱乐；4-引人不适；5-理性适度消费；6-个人观点 | **1** |
  | 头条 | `[0,2,1,3,6,7,8,9,10]` | **3-AI 生成**；1-自行拍摄；2-取自站外；6-虚构演绎；7-投资观点；8-健康医疗；9-独家精选；10-首发精选 | **3** |

  🔴 **绝不可跨平台照抄枚举值** —— 小红书 AI 声明是 `2`，头条/抖音是 `3`。照抄会把「取自站外」当成「AI 生成」（或反之），比不声明更糟。
  ⚠️ 头条 `9`(独家精选) / `10`(首发精选) **需要账号权益**，CLI 会查 `/account-info` 并在无权益时拒绝；不要默认写。

- **`createType`（创作类型）各平台语义/默认都不同，别混**（2026-10-11 实测）：

  | 平台 | 枚举 | 默认 | 语义 | 本产线 |
  |---|---|---|---|---|
  | 视频号 | `[1,2]` **required** | **2** | 1-声明原创；2-非原创或转载 | **不写**（官方口径「未提及原创保持 2」；声明原创涉账号权益，误声明更糟） |
  | B站 | `[1,2]` **required** | 1 | 1-自制；2-转载 | **写 1**（卡片视频为自制） |
  | 小红书 | `[0,1]` 选填 | 0 | 1-原创；0-不申明 | 不写 |
  | 抖音/快手/头条 | — | — | 无此字段 | — |

  🔴 **视频号默认 `2`（非原创或转载）** —— 不显式写 `1` 就会被标成"转载"；这是表单默认值，不是你说错了什么。


### 第 2 步：`validate` 正反两向（**零副作用 · 且完全离线**：不发布、不上传、不联网）

```bash
yxer validate <平台> <类型> payload_pos.json     # 正向：期望 ok:true / prepared:true
yxer validate <平台> <类型> payload_neg.json     # 反向：故意多写一个不该有的字段
```
- 正向：写你**准备实际使用的**字段值（如 `visibleType=0`）。
- **反向是铁证**：在正向 payload 里**多加一个 `pubType`**，期望
  `/: unexpected field "pubType" (not in schema)`。
  它证明「schema 分支判断真的生效」，比只看正向强得多。
- **反向再来一条：删掉一个 required**（如 B站删 `category`），期望
  `error.details: ["accountForms[0].contentPublishForm: /: missing required field \"category\""]`。
  ⚠️ 笼统的 `Schema validation failed` **只有看 `error.details` 才知道缺哪个字段**。
- ✅ **`validate` 返回体里有 `remoteChecks: false`** → 它只查本地 schema，**纯离线、零副作用**
  （2026-10-11 实测：断网/无账号也能 `ok:true` 跑过）。**所以体检件可以放心放 `validate`** ——
  这跟 `--dry-run`（会上传素材）**不是一回事**，别一起排除掉。

### 第 3 步：端到端 `--dry-run`（会**上传素材**到云端，但**不投递**）

```bash
yxer upload <本地图或视频> --auto-meta          # 拿 key（官方禁止用外部 URL 直发）
yxer publish <类型> <平台> payload.json --publish-channel local --client-id <本机clientId> --dry-run
```
期望：`ok:true / action:publish.dry-run / schemaChecked:true / effectivePublishChannel:local`。
**跑通这一步才允许改代码或改体检件的通道表** —— 视频线是 `publish_preflight.py` 的 `CHANNELS`；图文线是 `publish_preflight_image.py` 的 `IMAGE_CHANNELS`（见 §四 / §六）。

> ✅ **零投递自检（必做）**：跑完用 `yxer query records --limit 100 --json` 比对记录条数**前后不变**。
> 这是"没真发出去"的唯一可信证据。

## 二、落地脚本：字段表**按线分开维护**，绝不复用

**同一平台、同一字段名，视频线与图文线的枚举可以不同**（2026-10-09 实测）：

| | 视频线 `<平台>.video.schema.json` | 图文线 `<平台>.imageText.schema.json` |
|---|---|---|
| 小红书 `visibleType` | **`[0,1,2]`** ⚠️ 与官方文档**不符** | **`[0,1,3]`**（与文档一致：0-公开/1-私密/3-好友可见） |
| `required`（**小红书**） | `[formType, visibleType]` | `[formType, description, images, visibleType]`（**`description` 必填、`title` 选填**）⚠️ **只对小红书成立**，四平台各不同 → 见 §二·补 |
| 素材 | `video` + `cover` + `coverKey` | `images[]`（1~18 张，每项 `key/size/width/height/format`） |
| 封面 | **必须单独上传**（禁自动截帧） | **自动取第一张图**（`meta.inferredFields.cover` 指向 `accountForms[0].cover`）→ **顺序即封面** |

→ 视频线用 `PUBLIC_FIELDS`/`PRIVATE_FIELDS`，图文线用独立的 `IMAGE_TEXT_SPEC`。**混用必写错值**，
且撞上的是笼统的 `Schema validation failed`，很难查。

### 二·补、图文线**四平台**契约各不相同（2026-10-10 实测，别拿小红书一套套全平台）

范围判据 = `yxer accounts list --all` 里**已绑定**的那几个（本机 = 小红书/视频号/抖音/快手）。
**有 schema ≠ 已绑定** —— `schemas/platforms/` 下有 10 个 `*.imageText.schema.json`，只有绑定的才能发。

| 平台 | `required` | title | description | images | visibleType | 草稿箱 | cover |
|---|---|---|---|---|---|---|---|
| 小红书 | description, formType, images, visibleType | 选填 ≤20 | **必填** 1–1000 | 1–18 | **必填** `[0,1,3]` | 无 | 不可写（写了 unexpected field） |
| 视频号 | formType, images | 选填 ≤22 | 选填 ≤1000 | 1–18 | **无此字段** | **有**（`pubType`） | 不可写 |
| 抖音 | description, formType, images, **title** | **必填** ≤20 | **必填** ≤1000 | 1–20 | 选填 `[0,1,2]` | 无 | **必须写** `cover`+`coverKey` |
| 快手 | formType, images, visibleType | 选填 1–50 | 选填 **0–495** | 1–20 | **必填** `[0,1,2]` | 无 | **必须写** `cover`+`coverKey` |

**三条必踩的坑**：

1. **preflight 比 schema 严** —— 抖音/快手图文即使 schema 的 `required` **没列** `cover`，
   CLI 的 preflight 仍要求 `accountForms[].cover` + `coverKey`（缺则报 `missing coverKey`）；
   反过来小红书/视频号**塞 cover 会报 `unexpected field`**（`additionalProperties:false`）。
   → **"封面自动取第一张"只对小红书/视频号成立**，抖音/快手要**显式写**。
2. **`validate` / `publish` 都要 `--publish-channel local --client-id <id>`**；
   视频号走**云通道**缺代理会被直接拒（实测 `以下账号未设置代理：数智极客`）。
3. **`yxer` 把 JSON 错误写在 `stderr`**，stdout 为空 → 解析**两路都收**，
   否则失败被静默当成 `{}`（本人据此白排查过一轮）。

### 脚本必备

- **`--dry-run`**（必须）。没有 dry-run 的通道脚本 = 调用即产生副作用。
- **前置校验**：按 schema 的 `maxLength`/`minLength`/`minItems` 拦下并**说清数值**
  （例："快手标题上限 50 字，当前 51 字"），别让用户自己猜 `Schema validation failed`。
- **前置闸**（发布前必过），与体检**同源**，别另写一套：
  `from publish_via_xmcp import preflight_ready` → 返回 `(bool, str)`，不过就 **`return 1` 且不提交**。
- **无草稿箱的平台不要塞进 `DRAFT_FIELDS`**（否则 `--mode draft` 会走到 validate 才炸）。

## 三、测试基线（"通过测试才往下走"）

写一个自测脚本，至少覆盖：

1. **边界值两侧**：`title` 恰好等于上限 → 放行；上限 +1 → 拦。⚠️ **中文标题先 `assert len()` 再断言** ——
   本人已两次因手数中文字符数错而误判（把 22 字当成 23 字）。测试用例里用
   `"一二三四五六七八九十"*2 + "一二三"` 这种**可数**构造，并 `assert len(x)==23`。
2. **必填为空** → 拦（`description` 空 / `images` 0 张）。
3. **超限** → 拦（正文 1001 字、图片 19 张）。
4. **未接入的平台** → 拦（并提示走本三步）。
5. **正向 `--dry-run`** → 通。
6. 跑完复查 `yxer query records` 条数不变 —— ⚠️ **记录数组在 `data.data`**：直接取 `data` 拿到的是外层对象，
   照它数会得 0 或报错（正确取法：`d["data"]["data"]`，或先判 `isinstance(rows, dict)` 再 `rows.get("data", [])`）。
7. ⚠️ **断言别拿「含自身字样」的 token 计数** —— 登记行 / 输出里技能名常常出现 **2 次**（名字列 + 路径列），
   断言 `count(技能名) == 1` 会**假失败**；应断言**整行** `count(ROW) == 1`。
8. **mock 装配测试**（2026-10-11 用，免网络、免素材）—— 把适配器的 `run()` 换成假实现，
   只在 `form export` 那一步**真写一个 payload 文件**出去，再拿这个 payload 跑 **真实 `yxer validate`**。
   一次覆盖「字段装配 → schema 合法性」全链路，**零副作用**（不上传、不投递）。
   配合第 2 步的正反两向，是不碰网络的最高性价比验证。
   ⚠️ 假 `export` 的默认值要**按平台给**（别用一个通用 form），否则会把 schema 里不存在的字段（如给头条塞 `createType`）
   带进 payload，得到本不存在的 `unexpected field`。

## 四、改完要同步的地方（缺一不可）

| 落点 | 改什么 |
|---|---|
| `code-news/scripts/publish_via_yxer*.py` | 脚本本身 + 文件头 docstring（写清实测结论） |
| `D:/AI-VIDEO/config/平台适配矩阵.json` | `_发布侧`（接了什么 / 平台名映射 / 已知阻塞；**只记事实不复刻数值**，数值以脚本为准） |
| `~/.hermes/scripts/publish_preflight.py` | `CHANNELS` / `CHANNEL_META`（**视频线**四平台） |
| `~/.hermes/scripts/publish_preflight_image.py` | `IMAGE_CHANNELS` / `IMAGE_CHANNEL_META`（**图文线**四平台；**独立件**，见 §六） |
| vault `协同/发布层模块契约卡.md` | §二 边界 / §三 通道清单 / 判据小节 / §十一 未决 |
| vault `经验沉淀/工作流/platform-publish-automation.md` | §12.1 通道矩阵 / §13.5 / §13.6 |
| vault `经验沉淀/决策/<日期>-<平台>主通道由X切到Y.md` | **换路由必须写决策记录** |
| vault `协同/任务台账.md` / `交接/WK-*.md` / `会话索引/workbuddy.jsonl` | 登记（**CRLF**，按字节改） |

⚠️ vault 文件行尾**不统一**：`协同/*.md`、契约卡、工作流文档、v2 稿是 **LF**；
`任务台账.md` / `交接/WK-*.md` / `会话索引/workbuddy.jsonl` 是 **CRLF**。
**逐文件按字节判**（`open(p,'rb')` 后 `raw.count(b'\r\n')` 与 `raw.count(b'\n')` 比较），
**不要用文本模式 `open(p, encoding='utf-8')` 计数** —— 它会把 CRLF 吞掉。

## 五、踩坑集

- `yxer accounts list` 返 `null` **先想同步延迟**，别判"没绑成"。
- **小红书 `visibleType` 视频线枚举 `[0,1,2]` 与官方文档（0/1/3）不符** —— 只用 0/1；要"好友可见"须先实测。
- `publish_via_xmcp.py` **同名不同能力**（`code-news/` = 视频；`~/.hermes/publish_via_xmcp_image.py` = 图文）—— **认路径**。
- **"小红书"是双线重叠点**：说"小红书通道"必须指明**视频**还是**图文**。
- 写入 vault 前先算好**行尾**并加断言（锚点唯一 + 尾部锚点保留），否则容易把 CRLF 文件写成混合行尾。
- 本机 `yxer` 是 **`.cmd` 垫片**：**`shutil.which("yxer")` 能找到**（`D:\pi-agent\yxer.CMD`），
  但 **`subprocess.run(["yxer", ...])` 直接报 `FileNotFoundError`** —— CLI 侧能跑、Python 侧却不能。
  写探测脚本时必须走 `which`（适配器里的 `yxer_path()` 就是这么做的），否则误判「命令不存在」。
- **preflight 比 schema 严**（图文线）：抖音/快手必须写 `cover`+`coverKey`，小红书/视频号**不能**写 —— 见 §二·补。
- **`yxer` 的 JSON 错误在 `stderr`**、stdout 为空 → 解析**两路都收**，否则失败被静默当成 `{}`。
- **`--dry-run` 会上传素材到云端** → 「不投递」≠「零副作用」。体检件因此**不做** dry-run 冒烟（要验契约请显式手动跑）。
  ⚠️ 但 **`validate` 不一样**：它 `remoteChecks:false`、**纯离线**，可以放心放进体检件（见 §一 第 2 步）。
- **🔴 平台名 ≠ 中文习惯名**（2026-10-11 踩）：`B站`/`头条` 在 yxer 里**不存在**（`schema not found`），
  必须是 `哔哩哔哩`/`bilibili`、`头条号`/`toutiaohao`。**先用 `schema list` 核实**，别猜。
  且 **`accounts list <任意字符串>` 都返 `{ok:true, data:null}`** → 拿它判平台名会被误导成"没绑账号"。
- **`form start` 会补 required 默认值**（2026-10-11 踩）：视频号 `createType` 被默认成 `2`（非原创或转载）、
  `pubType` 默认 `1`。**别假设"脚本没写就是空"** —— 先看导出的默认值。
- **B站 `category` 是账号相关级联分类**（`CascadingPlatformDataItem[]`，须传根→末级完整路径 + 每个节点的 `raw`），
  schema required 且**表单不补**；用 `yxer query categories <account_id> --type video --paths --json` 现取。
- **行尾别用 `grep -c $'\r'` 判** —— 本机实测会**把纯 LF 文件误报成 CRLF**（本人本轮差点据此改错）。
  一律按字节：`raw.count(b"\r\n")` 与 `raw.count(b"\n")` 比较。
- **两组「图文线四平台」别混** —— 见 §六 末段。
- **`isDraft` ≠ 草稿箱**（2026-10-12 实测踩坑）：抖音/快手 的 `video` schema 里**确实有 `isDraft`（boolean）字段**，容易误判成"有草稿箱"。但 `publish_via_yxer.py` 的 `DRAFT_FIELDS` 判据是 **`pubType`**——抖音/快手/小红书**没有** `pubType`，`--mode draft` 必然报「没有平台草稿箱字段」。**判草稿箱只认 `pubType`，别被 `isDraft` 骗**。
- **`publish_via_yxer.py --schedule` 只吃 `YYYY-MM-DD HH:MM`**，**不能带秒**；写成 `YYYY-MM-DD HH:MM:SS` 会在走完 ⑧ AI 声明后才报格式错，白跑一轮（2026-10-12 实测）。
- **蚁小二有「每日发布次数上限」**：超限时 `yxer publish` 返 `{"statusCode":403,"message":"今日发布次数已达上限","code":1001}`（`remote_error`）。**这是配额不是故障**，次日恢复即可重跑（2026-10-12 抖音实测）。
- **矩媒队列会被其他内容堵住**：`Documents/MatrixMedia/data/pushData/<日期>.json` 可查每条任务的 `publishAttemptCount / republishCount / publishStatus / lastPublishMessage`。若里面有**别的作品**处于 `重新发布中`，同平台的投递会排队甚至超时（`[ERR] timed out`）。**多会话并发用矩媒前先看这个文件**（2026-10-12 实测）。
- **🔴 蚁小二账号配额已耗尽（2026-10-12 用户裁定）**：蚁小二已无账号数量，无法在蚁小二新增账号。
  `B站`/`头条` 从未在蚁小二登录过 → 永久改走**矩媒**（`publish_via_matrixmedia.py`）；`视频号` 2026-10-10 已裁定迁矩媒。
  **yxer 现在只服务 抖音/快手/小红书**。yxer 脚本里残留的 B站/头条 分支（declaration/category/createType）保留以备配额恢复，但已不被调用。
  → 本 skill 的「验证三步」「declaration/createType 对照表」对 B站/头条/视频号 **不再适用**（走矩媒），只对 抖音/快手/小红书 有效。
- **头条「首发加权」→ 头条先发、其余错峰后发（2026-10-12 裁定）**：头条原创保护判定标准是「未在其他平台发布」。
  指定头条为**首发平台**，先发（矩媒，无草稿箱→定时/公开），其余平台（抖音/快手/小红书 via yxer、视频号/哔哩哔哩 via 矩媒）错峰后发；
  幂等模块按通道+平台分命名空间，先发后发都不重复投。

## 六、接的是「一条新**线**」（不是新平台）时：另起**独立体检件**，但判定靠 **import 复用**

2026-10-10 接蚁小二**图文线**时定型。当新线的**平台名与旧线重叠**（图文线与视频线都含小红书），
**不要**把它并进现有 `publish_preflight.py` 的 `CHANNELS`：

① **平台名相同 ≠ 同一件事**（小红书图文 `visibleType=[0,1,3]` vs 视频 `[0,1,2]`）——
   混进一张表必然写错值，而错值撞上的是笼统的 `Schema validation failed`，极难查；
② **判定维度不同** —— 图文线多"逐平台字段契约"一维（标题必填否 / 正文上限 / 图片张数 / 可见枚举 / 有无草稿箱）；
③ **不动已验证资产** —— 视频线 `publish_preflight.py` 已有 45 项自测全绿、且被契约卡登记为"唯一可执行契约"。

**正确姿势 = 独立件 + import 复用**（目的同样是"**单一来源、不许两套判定**"）：

```python
from publish_preflight import Probe, probe_yxer, _exit_code, _verdict, _pad, _w   # 判定原语同源
from publish_via_yxer_image import IMAGE_TEXT_SPEC                               # 契约表同源
```

→ **有数值的只有一处**，两条线不会漂移。落地件：`~/.hermes/scripts/publish_preflight_image.py`
（**自测 44 项全绿**；`--json` 用 `line: "image-line"` 与视频线的 `video-line` 区分；
只读实跑 `✅ 可发 4 ｜ ◐ 0 ｜ 🟡 0 ｜ ❌ 0 → 退出码 0`）。

体检件设计要点（照抄即可）：

- **无备用腿要显式**：用哨兵 `NO_FALLBACK = "-"` 表达"确无第二条腿"，**不要**让它显示成"没探"，
  也别让聚合逻辑把它当成有腿。实测图文线只有小红书有备用腿（x-mcp，当前 `⛔ 失效`）。
- **只读到底**：`--deep` 只准调只读工具（如 `publish_via_xmcp_image.py --check-only`，四查不提交任务）；
  **不做** `--dry-run` 冒烟（会上传素材 = 有副作用）。**但 `yxer validate` 是纯离线的，可以放**（见 §一 第 2 步）。
- **自测要验"同源"**：断言 `_exit_code([OK, EXPIRED]) == 7` 之类，证明判定原语确实复用了视频线的，
  而不是本文件另写了一套。

⚠️ **别把它和「渠道既有图文线」搞混**：`check_publish_readiness.py` 覆盖的**另一组**图文线
= 微信/知乎/头条/小红书（走各平台浏览器/扩展）。而**蚁小二图文线** = 小红书/视频号/抖音/快手
（**恰与视频线同一组平台**，属巧合，不是同一条线）。两组**只在"小红书"上重叠** ——
说"图文线四平台"**必须指明是哪一组**。

> 🔵 **是否将来把图文线合并进 `publish_preflight.py`（如 `--line image`），留待用户裁定** ——
> 本轮刻意**不合并**：先保住"不动已验证资产"，再把选择权交回用户。
