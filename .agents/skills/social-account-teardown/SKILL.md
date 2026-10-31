---
name: social-account-teardown
display_name: 社媒账号拆解
display_name_en: Social Account Teardown
description: 逆向拆解国内社交媒体账号（抖音、小红书、B站、Instagram），抓取真实一手数据，产出互动指标体系与可复刻的运营手册。当用户提出「拆解某账号」「分析对标号」「看看XX号为什么火」「复刻这个账号的风格」「抓取抖音/小红书/B站/INS 账号数据」「竞品账号分析」「对标账号数据」「账号诊断」等需求时使用。产出结构化数据 + 互动指标 + 形态拆解 + 差距定位。核心原则：抓取层按平台适配，归一化层与指标层完全复用；严格区分实测数据与推断，抓不到的数据明确标注为不可得，绝不用同类内容脑补。
description_zh: 给它一个账号链接，抓取公开数据，2 分钟输出一份可复刻的运营拆解
description_en: Give it an account link — get a reproducible teardown of engagement metrics, content format and gap analysis in 2 minutes
version: 1.2.0
author: xiao
agent_created: true
---

# 社媒账号拆解（Social Account Teardown）

给它一个账号链接，抓真实公开数据，输出一份**可复刻**的运营拆解。
不是"内容要优质"这种空话，而是把互动结构、更新节奏、内容形态、爆款因子全部量化。

## 它能给你什么

| 能力 | 说明 |
|---|---|
| 账号体检 | 千粉均赞、头部占比、日更频率、互动结构（剔除了粉丝规模的影响） |
| 多账号横比 | 和你的号逐项对比，定位**真实**差距而不是体量差距 |
| 爆款因子 | 用什么特征区分高赞与尾部内容，带统计检验 |
| 形态拆解 | 图文 / 视频占比、发布节奏、爆款依赖度 |
| 选题方法 | 标题结构分析 + 选题公式归纳（见 `references/content-teardown.md`） |
| 趋势追踪 | 连续快照看老内容是否还在涨 |

## 用户会怎么说

- "拆解这个小红书账号 <链接>"
- "我的号和 XXX 到底差在哪"
- "看看这个抖音号为什么火"
- "分析对标账号的发布节奏"

## 需要你提供（缺一就先问）

1. **平台**
2. **账号定位符**：抖音 = `sec_user_id`；B站 = `mid`；小红书 = 主页 URL；INS = username
3. **拆解目的**：复刻风格 / 评估变现 / 找选题 —— 目的决定报告重心

只有昵称没有 ID？抖音用 CDP 打开搜索页看 URL，B站用
`https://api.bilibili.com/x/web-interface/search/type?search_type=bili_user&keyword=<昵称>`。

## 标准流程

```bash
# 1. 启动带调试端口的浏览器（需要登录的平台必须有头模式）
node scripts/launch_chrome.js --port 9337 --profile ./.cdp-profile

# 2. 抓取（按平台选一个）
node scripts/fetch_xhs.js        --url <主页URL>  --port 9337 --out workdir/
node scripts/fetch_douyin.js     --sec <sec_id>   --port 9337 --out workdir/
node scripts/fetch_bilibili.js   --mid <uid>      --out workdir/
node scripts/fetch_instagram.js  --username <name> --port 9337 --out workdir/

# 3. 归一化 + 算指标
node scripts/normalize.js --platform <平台> --raw workdir/raw.json --out workdir/posts.json
node scripts/metrics.js   --posts workdir/posts.json --out workdir/metrics.json
```

进阶命令：

```bash
# 小红书必做：补单条详情（评论/收藏/分享/真实图片数只有详情页有）
node scripts/fetch_xhs_detail.js --posts workdir/posts.json --port 9337 \
     --out workdir/details.json --merge workdir/posts_full.json

# 多账号横比
node scripts/compare.js --set "我的号=a/posts.json" --set "对标=b/posts.json" --out cmp.json --md cmp.md

# 爆款因子
node scripts/virality.js --posts workdir/posts.json --out virality.json --md virality.md

# 趋势追踪（攒够 ≥2 份快照）
node scripts/snapshot.js --posts workdir/posts.json --dir snapshots/
node scripts/trend.js --dir snapshots/ --name 账号名
```

需要登录时，先跑 `scripts/login_helper.js`，用户在弹出的浏览器里自己扫码。

## 平台支持情况

| 平台 | 状态 | 说明 |
|---|---|---|
| 抖音 | ✅ 已实测 | CDP + 网络拦截。未登录只能拿最近 ~18 条 |
| 小红书 | ✅ 已实测 | CDP + SSR 状态树。需补单条详情 |
| 小红书·蒲公英 | ⚠️ 受限 | 多数账号无权限，`fetch_pgy.js` 自动诊断并降级到公开主页 |
| B站 | ✅ 部分 | 账号数据可直连；视频列表接口被风控 |
| Instagram | ❌ 未登录不可行 | `web_profile_info` 返回 429 |

平台适配细节见 `references/platform-adapters.md`。

## 执行时的硬规矩（必须遵守）

1. **抓不到就说抓不到**，绝不用同类账号的语料脑补冒充分析
2. **必须标注样本量**（`n=18` 这种）<20 条只给定性结论，不给百分比级强结论
3. **不做登录态绕过**——需要登录就让用户在弹出的浏览器里扫码
4. **不批量爬取**，只针对用户指定的单个账号；请求间隔 ≥2.5s
5. **只做分析不搬运**——复刻时必须改写文案、更换素材
6. **相关 ≠ 因果**：结构化特征（图片数、标题长度）很可能只是选题的伴随现象
7. **小红书必须补单条详情**：列表接口的图片数是错的（实测 1 张 vs 真实 3.3 张），
   不补就下"单图/视频为主"的结论会全错

## 交付前自查（四条写进报告）

1. 这个判断的证据是实测数据、平台规则，还是我的推测？
2. 样本量够吗？
3. 如果我是反对者，从哪个角度能把这个结论打穿？
4. 用户想做的事如果不成立，我有没有直说？

## 参考文档

| 文件 | 什么时候读 |
|---|---|
| `references/content-teardown.md` | 做选题 / 标题结构分析时 |
| `references/metrics-playbook.md` | 需要指标定义与判读基准时 |
| `references/platform-adapters.md` | 适配新平台或排查抓取失败时 |
| `references/report-template.md` | 产出 HTML 报告时 |
| `references/engineering-notes.md` | 遇到风控、字段缺失、口径疑问时（踩坑记录与实测数据） |
