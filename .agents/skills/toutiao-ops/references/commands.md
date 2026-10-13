# toutiao-ops 完整命令参考

> 来源：本机实测 `--help` 输出（2026-09-14，v1.1.4 / CLI 自报 1.0.0）
> 上游：https://github.com/jiulingyun/toutiao-ops

---

## 全局参数

| 参数 | 说明 |
|---|---|
| `--account <name>` | 指定操作账号，**必须置于子命令之前**（默认 `default`） |
| `-V, --version` | 显示版本号 |
| `-h, --help` | 显示帮助 |

> 子命令级通用参数：`--headless`（无头模式运行，不弹浏览器窗口）

---

## 顶层命令

```
auth          账号管理
publish       内容发布
content       作品管理
comment       评论管理
analytics     数据分析
inspiration   创作灵感
```

---

## 1. auth — 账号管理

| 命令 | 说明 | 参数 |
|---|---|---|
| `auth check` | 检测登录状态 | `--headless` |
| `auth login` | 打开浏览器手动扫码登录 | 无 |
| `auth logout` | 清除登录缓存（退出登录，用于切换账号） | 无 |
| `auth list` | 列出所有已保存的账号 | 无 |

**`auth check` 成功输出示例**：

```json
{
  "logged_in": true,
  "account": "default",
  "username": "老廖聊ai",
  "userId": "2562312010738074",
  "profileUrl": "https://www.toutiao.com/c/user/2562312010738074/",
  "url": "https://mp.toutiao.com/profile_v4/index"
}
```

---

## 2. analytics — 数据分析

### 2.1 `analytics works` — 作品数据

| 参数 | 说明 | 默认 |
|---|---|---|
| `--period <period>` | 时间范围：`7d` / `30d` | `7d` |
| `--type <type>` | 类型：`all` / `article` / `video` / `weitoutiao` | `all` |
| `--headless` | 无头模式 | — |

### 2.2 `analytics fans` — 粉丝数据

| 参数 | 说明 |
|---|---|
| `--headless` | 无头模式 |

返回内容含**性别 / 年龄 / 地域 / 机型 / 机型价格**等画像分布（每项为 `{label, percent}` 数组）。

### 2.3 `analytics income` — 收益数据

| 参数 | 说明 | 默认 |
|---|---|---|
| `--period <period>` | 时间范围：`7d` / `30d` | `7d` |
| `--type <type>` | 类型：`all` / `article` / `video` | `all` |
| `--headless` | 无头模式 | — |

### 2.4 `analytics content-detail` — 单个作品详细数据

| 参数 | 说明 | 默认 |
|---|---|---|
| `--content-id <id>` | 作品 ID（`item_id` / `gidStr`） | — |
| `--content-type <type>` | 内容类型编号：`2`=图文/微头条，`3`=视频 | `2` |
| `--headless` | 无头模式 | — |

---

## 3. content — 作品管理

### `content list` — 作品列表

| 参数 | 说明 | 默认 |
|---|---|---|
| `--type <type>` | 类型：`article` / `video` / `weitoutiao` / `all` | `all` |
| `--status <status>` | 状态：`published` / `reviewing` / `rejected` | `published` |
| `--page <n>` | 页码 | `1` |
| `--limit <n>` | 每页数量 | `20` |
| `--headless` | 无头模式 | — |

---

## 4. comment — 评论管理

### 4.1 `comment list` — 评论列表

| 参数 | 说明 | 默认 |
|---|---|---|
| `--article-id <id>` | 指定文章 ID | — |
| `--page <n>` | 页码 | `1` |
| `--with-replies` | 同时获取每条评论的子评论/回复 | 关闭 |
| `--headless` | 无头模式 | — |

### 4.2 `comment reply` — 回复评论 ⚠️ 外部动作

| 参数 | 说明 |
|---|---|
| `--comment-id <id>` | 评论 ID **或内容片段** |
| `--content <content>` | 回复内容 |
| `--headless` | 无头模式 |

### 4.3 `comment like` — 点赞评论 ⚠️ 外部动作

| 参数 | 说明 |
|---|---|
| `--comment-id <id>` | 评论 ID **或内容片段** |
| `--headless` | 无头模式 |

---

## 5. publish — 内容发布 ⚠️ 全部为外部动作

### 5.1 `publish article` — 发布图文文章

| 参数 | 说明 | 默认 |
|---|---|---|
| `--title <title>` | 文章标题 | — |
| `--content <content>` | 文章正文 | — |
| `--content-file <path>` | 从文件读取正文（`.md` 自动识别为 Markdown） | — |
| `--format <format>` | 正文格式：`text`（纯文本）/ `markdown`（富文本排版） | `markdown` |
| `--cover <path>` | 封面图片路径（**single 模式下必填**） | — |
| `--content-images <paths>` | 正文配图路径，逗号分隔（上传进编辑器） | — |
| `--cover-mode <mode>` | 封面模式：`single` / `triple` / `none` | `single` |
| `--first-publish` | 勾选「头条首发」 | 关闭 |
| `--collection <name>` | 添加至合集名称 | — |
| `--no-weitoutiao` | 取消「同时发布微头条」（**默认开启**） | — |
| `--declaration <items>` | 作品声明，逗号分隔（见下方可选值） | — |
| `--draft` | 存为草稿而非直接发布 | 关闭 |
| `--headless` | 无头模式 | — |

**`--declaration` 可选值（图文类）**：
`取材网络` / `引用站内` / `个人观点` / `引用AI` / `虚构演绎` / `投资观点` / `健康医疗`

### 5.2 `publish video` — 发布视频

| 参数 | 说明 | 默认 |
|---|---|---|
| `--file <path>` | 视频文件路径 | — |
| `--title <title>` | 视频标题 | — |
| `--topic <topic>` | 话题名称（**不含 `#`**） | — |
| `--cover <path>` | 封面图片路径 | — |
| `--description <desc>` | 视频简介 | — |
| `--gen-article` | 勾选「生成图文」获取额外图文创作收益 | 关闭 |
| `--collection <name>` | 添加至合集名称 | — |
| `--declaration <items>` | 作品声明，逗号分隔（见下方可选值） | — |
| `--visibility <mode>` | 谁可以看：`public` / `fans` / `private` | `public` |
| `--draft` | 存为草稿而非直接发布 | 关闭 |
| `--headless` | 无头模式 | — |

**`--declaration` 可选值（视频类）**：
`取自站外` / `引用站内` / `自行拍摄` / `AI生成` / `虚构演绎` / `投资观点` / `健康医疗`

> ⚠️ 图文与视频的声明选项**不完全相同**，不要混用。

### 5.3 `publish weitoutiao` — 发布微头条

| 参数 | 说明 | 默认 |
|---|---|---|
| `--content <content>` | 微头条内容 | — |
| `--images <paths>` | 图片路径，逗号分隔 | — |
| `--topic <topic>` | 话题名称（**不含 `#`**） | — |
| `--first-publish` | 勾选「头条首发」 | 关闭 |
| `--declaration <items>` | 作品声明，逗号分隔 | — |
| `--draft` | 存为草稿而非发布 | 关闭 |
| `--headless` | 无头模式 | — |

---

## 6. inspiration — 创作灵感

| 参数 | 说明 | 默认 |
|---|---|---|
| `--type <type>` | 类型：`activity`（创作活动）/ `hotspot`（热点推荐） | `activity` |
| `--headless` | 无头模式 | — |

---

## 输出格式

**成功** → stdout，JSON：

```json
{ "success": true, "action": "published", "title": "文章标题" }
```

**失败** → stderr，JSON：

```json
{ "error": "未登录，请执行 auth login", "stack": "..." }
```

---

## 数据目录

```
~/.toutiao-ops/
└── accounts/
    ├── default/
    │   ├── browser-data/       # 浏览器会话数据（含登录态）
    │   ├── screenshots/        # 登录二维码截图
    │   └── meta.json           # 账号元信息
    └── work/
        └── ...
```

⚠️ `browser-data/` 含登录会话，**禁止同步到云盘或 git**。

---

## 环境要求

- Node.js >= 18
- macOS / Linux / Windows
- 首次安装自动下载 Chromium；失败时手动 `npx playwright install chromium`

---

## 反检测措施（包内实现，勿改）

- `playwright-extra` + `puppeteer-extra-plugin-stealth` 隐藏自动化特征
- 持久化浏览器上下文保留真实浏览器指纹
- 随机延迟 + 人类节奏模拟输入
- 主动关闭弹窗和权限请求
