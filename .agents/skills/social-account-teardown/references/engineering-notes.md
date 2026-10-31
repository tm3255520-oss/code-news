# 工程笔记（内部参考，不对外展示）

> 本文件保存 v1.1.0 及以前的完整 SKILL.md 内容：踩坑记录、实测数据、
> 平台风控细节、字段映射速查、待办与已否决的需求。
>
> **为什么挪到这里**：SkillHub / WorkBuddy 市场页会直接渲染 SKILL.md 全文，
> 这些内容属于"开发者的思考过程"，当商品介绍展示会严重损害可读性。
> SKILL.md 已瘦身为用户-facing 说明 + AI 必守规则，细节按需读本文件。
>
> 执行任务时若遇到平台风控、字段缺失、口径疑问，读这里。

---

# 社交媒体账号拆解 (Social Account Teardown)

## 核心架构：三层分离

```
L1 抓取层 (平台各异)  →  L2 归一化层 (统一 schema)  →  L3 指标层 + 分析层 (平台无关)
   fetch_douyin.js         normalize.js                  core.js   ← 共享内核（唯一事实来源）
   fetch_bilibili.js       → posts.json                  metrics.js
   fetch_xhs.js                                          compare.js   多账号横向对比
   fetch_xhs_detail.js                                   virality.js  爆款因子分析
   fetch_instagram.js                                    (复用率 100%)
```

**这是本 skill 的设计基石**：换平台只需写一个新的 `fetch_*.js`，L2/L3 完全不动。
不要为每个平台重写分析报告逻辑。

⚠️ **`core.js` 是统计口径的唯一事实来源。** metrics / compare / virality 三个脚本
共用它的 `compute()` 与特征提取。要改口径就改 `core.js`，
不要在任一脚本里另写一份 —— 否则"均值""TopN 占比"会悄悄漂移，
对比出来的差异就是口径差异而不是真实差异。

## 各平台可行性（实测状态，勿混淆）

| 平台 | 路径 | 验证状态 | 备注 |
|---|---|---|---|
| **抖音** | CDP + Network 拦截 | ✅ **已端到端实测** | 2026-09-03 成功抓到 18 条完整数据 |
| **B站** | `card` 接口 curl 直连 | ✅ **已实测** | 粉丝/关注/投稿数，无需登录 |
| **B站** | `wbi` 签名取视频列表 | ⚠️ **签名算法正确但被风控** | 返回 `code:-352`。海外出口 IP 会加剧；国内 IP 可能可过 |
| **小红书** | CDP + SSR `__INITIAL_STATE__` | ✅ **已端到端验证** | 2026-09-04 登录后拿到 29 条，含账号与笔记数据 |
| **小红书·单条详情** | CDP 打开笔记页 + 状态树 | ✅ **已端到端验证** | 2026-09-05 实测 29/29 成功。补上列表接口拿不到的评论/收藏/分享/真实图片数 |
| **小红书·蒲公英** | `/api/solar/user/info` 身份诊断 | ⚠️ **受限** | 2026-09-05 实测：账号权限不足时自动降级到公开主页，不硬抓。详见 §1.6 |
| **Instagram** | CDP + 登录态 | ❌ **未登录不可行** | `web_profile_info` 返回 HTTP 429 |

**🔴 小红书列表接口的 `media_count` 是错的，必须抓详情修正。**
列表接口不返回图片数组，normalize 只能填 1。实测同一个账号：
列表算出「平均 1 张/条」，抓完详情真实值是 **3.3 张/条**。
**拿列表数据直接下"这个号是单图/视频为主"的结论会全错。**

**硬规矩**：对未验证的平台，运行时必须先跑一次探测，把结果如实告诉用户，
**禁止用同类平台语料脑补数据填充报告**。抓不到就说抓不到。

## 工作流

### 0. Preflight — 确定目标与平台

需要用户提供（缺一不可）：
1. **平台**
2. **账号定位符**：抖音 = `sec_user_id`（分享链接里 `MS4wLjABAAAA...` 那段）；
   B站 = `mid`；小红书 = 用户主页 URL；INS = username
3. **拆解目的**：复刻风格 / 评估变现 / 找选题 —— 目的决定报告重心，先问清楚

若用户只有昵称没有 ID：抖音用 CDP 打开搜索页看 URL；B站用
`https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=<昵称>`。

### 1. 抓取（选对应 fetch 脚本）

**先启动带调试端口的浏览器**（跨平台，会自动定位 Chrome）：
```bash
node scripts/launch_chrome.js --port 9337 --profile ./.cdp-profile
```
脚本会：自动找本机 Chrome（Win/macOS/Linux，找不到时兜底 Edge）→ 启动 →
读 `/json/version` 校验 → **明确告诉你是不是 headless**。

> 🔴 **`--user-data-dir` 必须是绝对路径。** 实测传相对路径时 Chrome 静默启动失败、
> 端口毫无响应，且因为错误输出被忽略，排查起来极痛苦。`launch_chrome.js` 内部已
> `path.resolve()` 处理，但如果手敲命令，务必写全路径。
>
> ⚠️ 端口被占或 profile 损坏时，**换一个新目录名**（`.cdp2`、`.cdp3`…）。
> `rm -rf` 大目录常被安全策略拦截，换名比删旧目录省事。
>
> ⚠️ 若沙箱强制 headless（脚本会告警），**没有窗口就无法扫码登录**。
> 需要登录的场景必须先让执行环境允许启动 GUI 进程。

然后：
```bash
node scripts/fetch_douyin.js --sec <sec_user_id> --port 9335 --out workdir/
node scripts/fetch_bilibili.js --mid <uid> --out workdir/
node scripts/fetch_xhs.js --url <主页URL> --port 9335 --out workdir/
node scripts/fetch_instagram.js --username <name> --port 9335 --out workdir/
```

**抖音的关键坑（血泪教训）**：
- ❌ 不要试图在页面里直接 `fetch('/aweme/v1/web/aweme/post/?...')` 调 API。
  实测只返回 93 字节空结果——抖音校验了完整请求头链，页内构造不出来。
- ✅ 正确做法：`Network.enable` 监听 `Network.responseReceived` → 匹配
  `aweme/v1/web/aweme/post` → 记录 requestId → 等 `Network.loadingFinished`
  → `Network.getResponseBody` 取回。让**浏览器自己发请求**，我们只截获响应。
- 分页靠**真实滚动**触发：`scrollTo(0, body.scrollHeight)` → 等 4s
  → 点击文案为「加载更多/查看更多/看更多」的元素 → 等 3.5s，循环 5-8 轮。
- 首次 `Page.navigate` 后**至少等 25 秒**，抖音页面加载慢且永不触发 idle 事件。
- Node 22 的 WebSocket **必须用 `addEventListener`**，`.on()` 不工作。

**⚠️ 未登录态只能拿到最近 ~18 条。** 脚本会自动读主页的「作品」总数并打印覆盖度。
实测某账号主页 85 条作品，未登录只抓到 18 条（21%）。
**不要把 18 条当成"该账号的全部作品"** —— 要算长期趋势、季节性、转型节点时，
必须先登录再重跑。只做近期内容形态拆解时，18 条够用。

**⚠️ 作品数少的新号更狠：连 1 条都不给。** 接口直接返回
`{"aweme_list":[],"not_login_module":{"guide_login_tip_exist":true}}`。
脚本会识别这个字段并明确告诉你「这是登录墙，不是脚本问题」。
实测某 111 粉账号，未登录 0 条，登录后立刻拿到全部 5 条。

### 登录流程（已端到端验证，2026-09-04）

```bash
# 1. 开窗口，停在目标站点，等用户手动登录，检测到登录态自动退出
node scripts/login_helper.js --url "https://www.douyin.com/user/<sec>" --port 9337 --wait 300

# 2. 登录态已存进 user-data-dir，之后直接抓即可（同一 port + user-data-dir）
node scripts/fetch_douyin.js --sec <sec> --port 9337 --out workdir/
```

**🔴 前置条件：Chrome 必须是有头模式，否则用户看不到窗口，根本没法登录。**

沙箱环境会**强制 headless** —— 即使显式传 `--headless=false`，
`/json/version` 的 UA 仍是 `HeadlessChrome`。此时必须跳出沙箱限制启动，
**并验证 UA 中不含 "Headless"** 再继续。`login_helper.js` 会自动做这个检查并报错退出。

登录态保存在 `--user-data-dir` 里，**下次用同一目录启动不需要重新登录**
（实测第二次启动 2 秒就检测到已有 session）。

**判定登录态只认登录后才有的 cookie**：抖音 = `sessionid` / `sessionid_ss`。
绝不能把 `passport_csrf_token`、`sid_tt` 这类**访客态就下发**的 cookie 当作登录凭证
（实测踩过：误报"已登录"，随后抓取仍拿空 —— 误判比检测不到更危险）。

### 1.5 小红书：补单条详情（**必做，不是可选项**）

列表接口只给点赞数。评论/收藏/分享/真实图片数必须打开单条笔记才能拿到。
不补这步，小红书账号**算不出互动结构、也做不了爆款因子分析**。

```bash
node scripts/fetch_xhs_detail.js --posts workdir/posts.json --port 9337 \
     --out workdir/details.json --merge workdir/posts_full.json [--limit 29] [--top 10]
```

`--merge` 会把真实值写回 posts，并自动把已补齐的字段从 `_unavailable` 里移除，
之后 metrics 就能正常计算互动结构了。实测 29/29 成功，只剩 `play` 不可得
（小红书确实不公开播放量，不要想办法估算）。

**单条详情的字段名为实测所得，勿凭印象改**：
```
__INITIAL_STATE__.note.noteDetailMap[noteId].note
  .interactInfo = { likedCount, collectedCount, commentCount, shareCount, liked, collected }
                                                              ^^^^^^^^^^ 是 shareCount 不是 sharedCount
  .imageList    = 图片数组（不是 imagesList）
  .tagList / .desc / .ipLocation / .time / .lastUpdateTime
__INITIAL_STATE__.note.noteDetailMap[noteId].comments.comments  ← 评论直接在这里，比网络拦截可靠
```
`xsec_token` 有时效，过期后详情为空 —— 脚本会识别并提示重跑 `fetch_xhs.js` 拿新 token。

### 1.6 小红书蒲公英：身份诊断 + 自动降级

蒲公英 (`pgy.xiaohongshu.com`) 是小红书的商业版后台，理论上能拿到博主/品牌方的
深度数据（报价档位、近 30 天互动率、粉丝画像、商单数）。**实测结论：这条路对
大多数账号走不通**，必须设计成「诊断 → 降级」而不是「硬抓」。

```bash
node scripts/fetch_pgy.js --url "https://pgy.xiaohongshu.com/creator/home" --port 9337 --out workdir/
# 输出: workdir/pgy_access.json + 退出码 0（可继续抓）/ 2（需降级）
```

**脚本会自动做这三件事**：
1. 调 `/api/solar/user/info` 拿当前 cookie 的身份（role / access / blockBlogger / permissions）
2. 真实导航到 `/creator/home`、`/creator/notes`、`/brand/home`、`/agent/home`，
   检测是否落到"你访问的页面不见了"
3. 出具 verdict：`KOL_OK` / `BLOCKED_BLOGGER` / `NO_ROLE_GRANTED` / `NOT_LOGGED_IN` /
   `BUYER_ONLY` / `UNKNOWN`，并给出降级建议

**为什么必须降级而不是硬抓**：蒲公英 `/api/solar/*` 全部按调用方身份路由，
错误路径返回 `"url not support"` 而不是 404 —— 这是设计上的"假装不存在"。
即使反复重试也不会变成 200，硬抓只会反复触发同样的错误。

**降级目标**：自动切回 `fetch_xhs.js` + `fetch_xhs_detail.js`，抓对方的
`www.xiaohongshu.com` 公开主页。这是**不登录对方账号能拿到的最全数据**：
粉丝、获赞与收藏、每条笔记点赞数，部分账号还能补到评论/收藏/分享。

**蒲公英后台数据要走通的唯一路径**：换用第三方付费工具（新榜、千瓜、灰豚），
或拿到对应账号本人的蒲公英 cookie —— 都不在 skill 覆盖范围。**不要为了凑数据
硬上第三方 API（违反使用限制条款）**。

### 2. 归一化

```bash
node scripts/normalize.js --platform douyin --raw workdir/raw.json --out workdir/posts.json
```

统一 schema（所有平台必须映射到这个结构）：
```json
{
  "platform": "douyin",
  "account": { "id":"", "name":"", "fans":0, "total_likes":0, "post_count":0, "bio":"" },
  "posts": [{
    "id":"", "title":"", "create_time":"2026-08-26", "url":"",
    "media_type":"image_album|video", "media_count":5,
    "play":0, "digg":0, "comment":0, "share":0, "collect":0, "danmaku":0,
    "tags":["",""], "raw": {}
  }]
}
```

**字段映射速查**：
| 统一字段 | 抖音 | B站 |
|---|---|---|
| digg | `statistics.digg_count` | `stat.like` / vlist `video_review`❌(那是评论) → 用 `archive/stat`.like |
| comment | `statistics.comment_count` | `archive/stat`.reply |
| share | `statistics.share_count` | `archive/stat`.share |
| collect | `statistics.collect_count` | `archive/stat`.favorite |
| play | `statistics.play_count` | `archive/stat`.view |
| danmaku | — | `archive/stat`.danmaku |
| media_count | `images.length` / `image_list.length` | 1（视频） |
| media_type | 有 `images` 即 `image_album` | `video` |

### 3. 指标计算

```bash
node scripts/metrics.js --posts workdir/posts.json --out workdir/metrics.json
```

**⚠️ 抖音图文号的 `play_count` 恒为 0**——图文作品接口不返回播放量。
所以抖音图文号**无法计算赞阅比**，只能用 `digg` 当分母做相对指标。
不要假装拿到了播放量，也不要用第三方估算值冒充。

完整指标定义与判读基准见 `references/metrics-playbook.md`。

### 3.5 多账号横向对比（拆解的核心用途）

```bash
node scripts/compare.js \
  --set "我的号=dy_me/posts.json" \
  --set "对标号=dy_target/posts.json" \
  --out cmp.json --md cmp.md
```

输出体量/集中度/节奏/形态/互动结构五个维度的横向表 + 自动判定的差异点。

**脚本内置三道"防假结论"门禁，不要绕过**：
1. **量级归一化**：粉量差 >3 倍时警告绝对赞数不可比，改看「千粉均赞」
2. **缺失字段整列跳过**：某账号该字段为 null 就跳过，**不以 0 参与比较**
3. **比率可靠性门禁**：总赞 <1000 的账号，其百分比指标强制降级、不得进入「强差异」。
   真实案例：某 58 粉账号 18 条共 274 赞，因 2 条「评论数>赞数」算出评论率 34.31%，
   看着像强互动账号，实际只是分母太小
4. **区分账号行为与抓取窗口**：样本跨度只作元信息不进差异排名；
   日更频率在样本被截断时（达接口上限，或"N 天跨度只有个位数条"）直接判为不可用作结论

### 3.6 爆款因子分析（回答"为什么火"）

```bash
node scripts/virality.js --posts workdir/posts.json --out virality.json --md virality.md
```

**小样本下唯一诚实的做法**，三层保护：

1. **置换检验 p 值**（2000 次，固定种子可复现）：不假设正态分布。
   随机划两组，看真实 TOP-vs-尾部差异在随机分布里的位置
2. **BH / FDR 多重比较校正**：判定一律用 `p_adj`，原始 p 值只展示不判定。
   实测救回过一次假阳性：某账号"周日发布" p=0.02 → p_adj=0.09，降为弱信号
3. **混杂变量 `age_days` 单独检验**：老作品有更长时间累积点赞。
   若它显著，说明分组被"发得更早"污染，其他因子结论全部打折

另外两条硬规矩写在脚本里：分组依据是 digg，所以**互动指标先看绝对值**
（`comment/digg` 这类比率的分母就是分组依据，高赞作品的比率会被天然压低）；
**n<8 拒绝出结论**，只给描述性统计。

### 3.7 趋势追踪（看历史变化）

一次抓取只能看到「现在什么样」，连续快照才能回答：涨粉速度、内容有没有长尾、
哪条作品真的在涨。

```bash
# 每次抓完存一份（文件名带完整时间戳，同日多次不覆盖）
node scripts/snapshot.js --posts workdir/posts.json --dir snapshots/

# 攒够 ≥2 份后看趋势
node scripts/trend.js --dir snapshots/ --name 账号名
```

**三个防自欺的设计**：

1. **同批作品对比** —— 两次快照之间「样本总赞」的增加，很可能只是"又发了几条新的"。
   所以总赞增长之外单独算**交集作品**（两次都存在的 id）的赞增量，那才是老内容还在不在涨。
   实测这两个数能差一半以上。
2. **抓取窗口污染检测** —— 有作品从快照里消失、或作品数变化过大时明确警告，
   不把"窗口变化"说成"内容变化"。
3. **只有 1 份快照就直说没趋势** —— 不假装有。同日多次抓取会按日期去重
   （一天内的波动是噪声，不是趋势）。

外推按当前速度算天数，但脚本会写明**「算术外推，不是预测」**——
账号增长通常前期慢、爆发期快、之后放缓，外推只看数量级。

**想自动化**：用定时任务（每天/每周）跑 `抓取 → normalize → snapshot` 即可，
攒够数据随时看趋势。

### 3.8 内容拆解：标题结构与选题公式（回答"差在哪"）

指标只说明结果差距，内容拆解才解释原因。完整方法论、判读规则与实战案例见
`references/content-teardown.md`。

最小动作链：把所有 `title` 提出来 → 统计长度分布 + 2-gram 高频词 + 标点密度 →
归纳选题公式（格式：`锁定人群 + 数字锚点 + 好奇缺口`）→ 判断标题是「筛选器」还是「新闻台」
→ 对照互动密度看差距的内容层原因。

三条纪律：
1. **样本 <20 条不归纳公式**，只给描述性统计
2. **选题是归纳不是检验**，报告里必须标注"推断"，不能和"接口实测"混在一起
3. **相关 ≠ 因果**：高互动密度与某类选题同时出现，只能写"同时出现"

### 4. 产出报告

按 `references/report-template.md` 生成 HTML 手册。必须包含：
- **数据来源声明表**：每条数据标「接口实测 / 页面可见 / 推断」
- **自我纠错章节**：主动写出本报告的局限、可能出错的地方、用户怎么验证
- 不要只给结论不给证据

### 5. 对抗式审查（交付前必做）

自问四条，答案写进报告：
1. 这个判断的证据是实测数据、平台规则，还是我基于同类账号的推测？
2. 样本量够吗？（**<20 条只能当定性参考，不能给百分比级强结论**）
3. 如果我是反对者，从哪个角度能把这个结论打穿？
4. 用户想做的事如果不成立，我有没有直说？

## 硬约束

1. **区分实测与推断**。抓不到就说抓不到。绝不用同品类语料脑补冒充分析。
2. **样本量警告**：抓到 15-20 条是常态（抖音/B站未登录态上限）。
   任何百分比指标都要标注 `n=18` 这样的样本量。
3. **不做登录态绕过**。需要登录才能看的，让用户自己在弹出的浏览器里扫码登录后继续，
   不要尝试破解或伪造身份。
4. **不批量爬取**。只针对用户指定的单个账号做拆解，不做全站遍历。
5. **频率克制**。请求间隔 ≥2.5s，滚动间隔 ≥3.5s。过快会触发风控并可能波及用户 IP。
6. **数据只做分析**。抓到的内容（文案/图片）用于拆解学习，
   复刻时必须改写文案、更换素材，不直接搬运。
7. **相关性 ≠ 因果**。compare / virality 给的都是"这两件事同时出现"。
   结构化特征（图片数、标题长度、tag 数）很可能只是选题的伴随现象，
   复制这些特征不等于能复制爆款。**选题本身才是主因，而选题没法从元数据里统计出来。**

## 待办（按优先级，2026-09-05 排）

**第二梯队 —— 有价值但成本更高：**
- 评论抓取与分析（高赞评论 = 用户共鸣点）。`fetch_xhs_detail.js` 已能拿到小红书评论，
  抖音/B站待补
- 素材下载（形态拆解必须真的看图，`report-template.md` 里写了但没脚本）
- `report.js` 自动生成 HTML 报告（目前只有模板文档，没有生成脚本）

**已判定为伪需求，别做：**
- 更多海外平台（xiao 的场景用不到）
- 自动内容分类（关键词分类容易假精确）
- 涨粉曲线（需要历史快照，当前只有单次快照）
