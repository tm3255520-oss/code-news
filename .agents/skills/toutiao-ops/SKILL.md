---
name: toutiao-ops
description: 今日头条（头条号）创作者后台的数据查询与内容运营，基于本机已安装并已登录的 toutiao-ops CLI。当用户要求查看头条号的粉丝画像、作品数据、收益数据、单篇作品详情、评论列表，或要求发布文章/视频/微头条、回复或点赞评论、获取创作灵感与热点推荐时使用。也适用于「查下我头条数据」「头条粉丝画像」「头条收益」「发条微头条」「头条评论」等表述。**边界**：只管**头条号**；**公众号**走 wechat-channel-ops、**视频号**发布走 d2v-channels-publish、**小红书**走 xiaohongshu-skills。
agent_created: true
version: 1.1.0
---

# 头条号运营与数据查询（toutiao-ops）

## 这是什么

`toutiao-ops` 是本机已安装的**今日头条创作者平台运营自动化 CLI**，覆盖数据查询、内容发布、评论互动、创作灵感全链路。

- **包位置**：`D:\pi-agent\node_modules\@openclaw-cn\toutiao-ops`（v1.1.4）
- **调用方式**：`toutiao-ops` 已在 PATH 中，可直接调用；兜底可用 `node "D:/pi-agent/node_modules/@openclaw-cn/toutiao-ops/index.js"`
- **技术路线**：Playwright + stealth 浏览器自动化。发布走浏览器模拟真人；数据走浏览器内 `fetch()` 复用已登录 Cookie 调平台 API
- **认证方式**：**扫码登录 + 会话持久化，不需要任何 token**。会话存 `~/.toutiao-ops/accounts/<name>/browser-data/`
- **输出**：成功时输出结构化 **JSON 到 stdout**，错误输出 JSON 到 **stderr**

## 前置检查（每次使用前必做）

先确认登录态，再执行任何操作：

```bash
timeout 180 toutiao-ops auth check
```

- 返回 `"logged_in": true` → 继续操作
- 返回 `false` 或报错 → **必须让用户手动扫码**，不要尝试自动化登录：

  ```bash
  toutiao-ops auth login    # 打开浏览器窗口，需用户手机扫码
  ```

  > 登录必须由用户本人完成（涉及账号安全）。执行后告知用户：「浏览器已打开，请用今日头条 App 扫码登录，完成后告诉我继续。」

查看所有已保存账号：`toutiao-ops auth list`

## 全局约定

- `--account <name>` 是**全局参数，必须放在子命令之前**：`toutiao-ops --account work analytics fans`
- 省略时使用 `default` 账号
- 所有命令支持 `--headless`（无头模式，不弹浏览器窗口）
- 每个账号的浏览器会话相互隔离
- Playwright 启动较慢，**所有调用都用 `timeout 180` 包住**

## 核心工作流

### A. 查数据（只读，最常用）

```bash
timeout 180 toutiao-ops analytics fans                          # 粉丝画像（性别/年龄/地域/机型）
timeout 180 toutiao-ops analytics works --period 7d --type all  # 作品数据（7d/30d；all/article/video/weitoutiao）
timeout 180 toutiao-ops analytics income --period 30d           # 收益数据（all/article/video）
timeout 180 toutiao-ops analytics content-detail --content-id <ID> --content-type 2
timeout 180 toutiao-ops content list --type all --status published --limit 20
timeout 180 toutiao-ops inspiration --type hotspot              # 热点推荐
timeout 180 toutiao-ops inspiration --type activity             # 创作活动
```

- `content-detail` 的 `--content-type`：`2` = 图文/微头条，`3` = 视频
- `content list` 的 `--status`：`published` / `reviewing` / `rejected`

### B. 发布内容（⚠️ 外部动作，必须先经用户确认）

**发布是不可逆的对外动作。** 执行前必须：

1. **先向用户确认**：标题、正文要点、封面、发布时间
2. **默认加 `--draft`**：先存草稿，让用户在头条后台确认后再正式发布
3. 只有用户**明确说「直接发布」**时才去掉 `--draft`

```bash
# 文章（--cover 在 single 模式下必填）
timeout 300 toutiao-ops publish article \
  --title "标题" --content-file "/path/body.md" --format markdown \
  --cover "/path/cover.jpg" --cover-mode single --declaration "个人观点" --draft

# 微头条
timeout 300 toutiao-ops publish weitoutiao \
  --content "内容" --images "a.jpg,b.jpg" --topic "话题" --draft

# 视频
timeout 300 toutiao-ops publish video \
  --file "/path/video.mp4" --title "标题" --cover "/path/cover.jpg" \
  --topic "话题" --visibility public --draft
```

注意：
- `publish article` **默认会同时发布微头条**，用 `--no-weitoutiao` 关闭
- `--declaration` 可选值按内容类型不同（图文与视频的选项不同），详见 `references/commands.md`
- 封面/配图/视频必须是**本地绝对路径**

### C. 评论互动（⚠️ 外部动作，回复前先给用户看）

```bash
timeout 180 toutiao-ops comment list --with-replies      # 评论列表（含子评论）
timeout 180 toutiao-ops comment list --article-id <ID>
timeout 180 toutiao-ops comment reply --comment-id "<评论ID或内容片段>" --content "回复内容"
timeout 180 toutiao-ops comment like --comment-id "<评论ID或内容片段>"
```

**回复评论前，必须把拟回复内容给用户过目**，确认后再执行。`--comment-id` 可传 ID 或内容片段。

## 安全与纪律

1. **发布类与回复类命令属外部动作** —— 未经用户明确确认不得执行。宁可多问一句。
2. **`~/.toutiao-ops/` 存有账号登录会话** —— 禁止同步到云盘、git 仓库或任何外部位置。
3. **登录必须由用户本人扫码** —— 不要尝试自动化或绕过。
4. **不要把任何 token / Cookie 内容写进对话、vault 或记忆文件**。
5. **批量发布前先在草稿模式验证** —— 头条对违规内容有处罚，发布前检查敏感词与事实。
6. 用户账号为「**老廖聊ai**」（`default`，userId `2562312010738074`）—— 操作前可先 `auth check` 核对，避免发错账号。

## 故障处理

| 现象 | 处置 |
|---|---|
| `logged_in: false` | 让用户手动 `toutiao-ops auth login` 扫码 |
| stderr 报「未登录，请执行 auth login」 | 同上 |
| 命令长时间无输出 | Playwright 启动慢属正常；超过 3 分钟无输出则中止（见 `execution-timeout-guard`） |
| 命令找不到 | 用兜底调用：`node "D:/pi-agent/node_modules/@openclaw-cn/toutiao-ops/index.js" ...` |
| 发布失败 / 页面元素找不到 | 头条前端可能改版。**只报告现象，不要擅自改包内代码**（见 `repair-gate`） |

## 参考

- 完整命令参数表：`references/commands.md`
- 上游仓库：https://github.com/jiulingyun/toutiao-ops
- 包内 README：`D:\pi-agent\node_modules\@openclaw-cn\toutiao-ops\README.md`
