# 知乎文章发布运行手册

更新时间：2026-05-24

## 目标

这份文档用于沉淀知乎文章发布链路的稳定流程、自动化边界、调试节点和注意事项，方便后续复用。

适用范围：

- 知乎专栏文章发布
- 专用可控 Chrome + Playwright/CDP 自动化
- 标题、正文、正文配图、封面上传
- 发布前校验、发布后复核

相关脚本：

- `.tmp/launch_zhihu_controlled_chrome.js`
- `.tmp/probe_zhihu_writer.js`
- `.tmp/publish_zhihu_article_controlled.js`

相关记录文件：

- `.tmp/zhihu-publish-records.json`
- `.tmp/generated/<slug>/debug/zhihu/*.json`
- `.tmp/generated/<slug>/debug/zhihu/*.png`

## 当前结论

截至 2026-05-24，这条链路已经验证到可用状态：

- 可稳定打开知乎写文章页
- 标题可自动写入
- 正文可自动写入
- 正文图片可通过 `input[type=file]` 直接上传
- 文章封面可通过专用封面 input 上传
- 点击发布后，知乎会新开正式文章页
- 已实发成功的样例文章：
  - `Google I/O 2026：AI 开始从回答问题走向替你做事`
  - 链接：
    - `https://zhuanlan.zhihu.com/p/2042005644450984740`

## 硬规则

以下规则后面都要固定执行：

1. 相同内容只能正式发布一次。
2. 调试时优先用 `--draft-only`，不要拿同一篇内容反复点正式发布。
3. 必须使用专用可控 Chrome，不要直接依赖桌面坐标点击。
4. 只有在用户主页或文章页确认可见后，才算发布成功。
5. 已成功发布的内容要写入本地记录，后续命中同一标题或指纹时直接拦截。

## 稳定环境

当前知乎使用单独的专用可控实例。

固定参数：

- 远程调试端口：`9225`
- 持久化用户目录：`.tmp/browser-profiles/zhihu-automation`
- 写文章页：`https://zhuanlan.zhihu.com/write`

启动命令：

```bash
node .tmp/launch_zhihu_controlled_chrome.js
```

首次需要在这个专用窗口里登录一次知乎，后续可以复用登录态。

## 标准流程

### 1. 准备 payload 和图片资产

建议沿用现有 payload 结构，至少包含：

- `slug`
- `title`
- `summary`
- `article_blocks`
- `body_images`

图片资产放在：

```text
.tmp/generated/<slug>/
```

通常包括：

- `cover.png`
- `body-01.png`
- `body-02.png`
- `body-03.png`
- `article.md`

### 2. 打开或复用写文章页

探针命令：

```bash
node .tmp/probe_zhihu_writer.js
```

已验证关键节点：

- 标题框：
  - `textarea[placeholder*="请输入标题"]`
- 正文编辑器：
  - `.public-DraftEditor-content`
  - 兜底 `.Dropzone.Editable-content`
- 正文图片 input：
  - `accept` 包含 `image/` 且 `multiple=true`
- 封面 input：
  - `input.UploadPicture-input[type=file]`
- 发布按钮：
  - 可见按钮文本 `发布`

### 3. 先跑草稿模式

建议先用草稿模式确认写入、插图和封面都通：

```bash
node .tmp/publish_zhihu_article_controlled.js .tmp/toutiao_payload_google_io_2026.json --draft-only
```

草稿模式会完成：

- 打开知乎写文章页
- 写入标题
- 写入正文
- 上传正文图片
- 上传封面
- 保留为知乎草稿

成功后，页面会进入：

- `https://zhuanlan.zhihu.com/p/<id>/edit`

这说明草稿已经创建。

### 4. 正式发布

正式发布命令：

```bash
node .tmp/publish_zhihu_article_controlled.js .tmp/toutiao_payload_google_io_2026.json
```

当前脚本的真实行为是：

1. 打开或复用写文章页
2. 写入标题
3. 写入正文
4. 上传正文图片
5. 上传封面
6. 点击 `发布`
7. 等待知乎新开正式文章页

### 5. 发布成功的真实判断方式

这次实测里，知乎不是在原编辑页直接显示“发布成功”，而是：

1. 原编辑页短暂显示 `发布中...`
2. 新开正式文章页：
   - `https://zhuanlan.zhihu.com/p/<id>`
3. 用户主页里的 `文章` 数量增加

所以当前脚本的成功判断应该是：

- 检测到新开的正式文章页
- 或者主页里能看到新文章卡片

不能只盯着原编辑页的提示文案。

## 正文图片链路

这部分已经验证可用：

1. 不是系统文件弹窗方案。
2. 页面里本身就有可操作的 `input[type=file]`。
3. 可以直接用 `setInputFiles` 上传正文图。
4. 当前实测成功插入了 `3` 张正文图。

已验证结论：

- 发布后的文章页里能看到正文图片
- 文章页里统计到的图片节点数量会大于插入数量，因为知乎会有包装节点或重复渲染

## 封面链路

这次也已验证到“可上传”状态：

- 页面存在专用封面 input：
  - `input.UploadPicture-input[type=file]`
- 可以直接 `setInputFiles(coverPath)`

注意：

- 编辑页文案不一定会即时从“添加文章封面”切成别的状态
- 所以封面是否真正被接收，建议结合发布后卡片或推荐流展示再做二次确认

当前结论：

- 封面上传链路已接通
- 但展示层是否在每个入口都显式露出封面，还需要后续继续观察

## 发布后复核

发布完成后，至少要做两层复核：

1. 打开文章页，确认标题、正文、正文图片正常
2. 打开用户主页的 `文章` 列表，确认新文章卡片已经出现

本次实测的关键验证：

- 用户主页：
  - `文章 1`
- 文章标题：
  - `Google I/O 2026：AI 开始从回答问题走向替你做事`
- 发布后快照：
  - [zhihu-published-article.png](C:/Users/Administrator/Documents/code-news/.tmp/zhihu-published-article.png)
  - [zhihu-posts-check.png](C:/Users/Administrator/Documents/code-news/.tmp/zhihu-posts-check.png)

## 去重机制

当前本地去重记录文件：

- [zhihu-publish-records.json](C:/Users/Administrator/Documents/code-news/.tmp/zhihu-publish-records.json)

记录字段包括：

- `fingerprint`
- `title`
- `slug`
- `publishedAt`
- `url`

后面脚本应优先检查：

- 相同正文指纹
- 相同标题

命中后直接返回：

- `duplicate_blocked`

## 调试证据

本次知乎链路的关键证据文件：

- [01-ready.json](C:/Users/Administrator/Documents/code-news/.tmp/generated/2026-05-24-google-io-2026-agentic-ai/debug/zhihu/01-ready.json)
- [02-filled.json](C:/Users/Administrator/Documents/code-news/.tmp/generated/2026-05-24-google-io-2026-agentic-ai/debug/zhihu/02-filled.json)
- [03-after-publish.json](C:/Users/Administrator/Documents/code-news/.tmp/generated/2026-05-24-google-io-2026-agentic-ai/debug/zhihu/03-after-publish.json)
- [zhihu-writer-probe.png](C:/Users/Administrator/Documents/code-news/.tmp/zhihu-writer-probe.png)
- [zhihu-published-article.png](C:/Users/Administrator/Documents/code-news/.tmp/zhihu-published-article.png)

## 当前最稳的结论

知乎这条链路已经具备继续复用的条件。

对后续最重要的不是重新摸 DOM，而是固定执行下面这套顺序：

1. 起专用知乎可控 Chrome
2. 确认登录态
3. 先跑草稿模式
4. 确认正文和配图
5. 再正式发布
6. 发布后去主页和文章页双重复核

## 一句话总结

知乎发布已经打通：

**标题、正文、正文配图、封面、正式发布、发布后可见性校验，全部已有实证。**
