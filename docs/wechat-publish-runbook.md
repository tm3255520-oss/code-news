# 公众号文章发布运行手册

更新时间：2026-05-24

## 目标

这份文档用于沉淀微信公众号文章发布链路的稳定流程、自动化边界、人工介入点和踩坑记录，方便后续复用，减少反复试错。

适用范围：

- 微信公众号图文文章发布
- 可控 Chrome + Playwright/CDP 自动化
- 标题、摘要、正文、正文配图、封面设置
- 发布前校验、扫码验证、发布后复核

相关脚本：

- `.tmp/publish_wechat_article_controlled.js`
- `.tmp/publish_wechat_article.py`
- `.tmp/render_toutiao_assets.js`

相关目录与记录文件：

- `.tmp/browser-profiles/wechat-automation`
- `.tmp/generated/<slug>/debug/wechat/*.json`
- `.tmp/generated/<slug>/debug/wechat/*.png`

## 当前结论

截至 2026-05-24，这条链路已经验证到可用状态：

- 新建文章入口可稳定打开
- 标题、作者、摘要、正文可自动写入
- 正文图片上传可用
- 封面可通过“从正文选择”稳定设置
- 发布确认弹层可自动推进
- 最后一步需要人工扫码做微信验证
- 人工扫码完成后，作品可以成功发表

本次已验证发布的题目：

- `Google I/O 2026：AI 开始从回答问题走向替你做事`

## 硬规则

以下规则后面都要固定执行：

1. 相同内容只能正式发布一次。
2. 做自动化调试时，优先使用草稿保存，不要直接拿同一篇内容反复点正式发表。
3. 必须使用专用可控 Chrome，不要在日常主浏览器里硬做桌面坐标自动化。
4. 看到微信验证二维码时，不要再把它当成脚本错误；这是平台的人工校验门槛。
5. 只有在发布后列表或后台记录确认成功后，才算链路真正完成。

## 稳定环境

当前稳定方案不是操作用户正在使用的主 Chrome，而是单独起一个可控实例。

固定参数：

- 远程调试端口：`9223`
- 持久化用户目录：`.tmp/browser-profiles/wechat-automation`
- 平台首页：`https://mp.weixin.qq.com/`

这样做的原因：

- 主浏览器标签太多时，桌面级点击容易串窗
- 可控 Chrome 能用 CDP 直接读 DOM、点可见元素、做 `setInputFiles`
- 登录状态可复用，不需要每次重登

## 标准流程

### 1. 准备 payload 和图片资产

建议沿用现有 payload 结构，至少包含：

- `slug`
- `title`
- `summary`
- `article_blocks`
- `body_images`
- `sources`

图片资产放在：

```text
.tmp/generated/<slug>/
```

核心文件通常包括：

- `cover.png`
- `body-01.png`
- `body-02.png`
- `body-03.png`
- `article.md`

### 2. 登录专用公众号后台

如果专用 Chrome 还没登录，先在该窗口扫码登录。登录成功后，再运行自动化脚本。

### 3. 先跑草稿模式

建议先用草稿模式确认写入、插图和封面链路是通的：

```bash
node .tmp/publish_wechat_article_controlled.js .tmp/toutiao_payload_google_io_2026.json --draft-only
```

草稿模式会完成：

- 打开文章编辑页
- 写入标题
- 写入作者
- 写入摘要
- 写入正文
- 插入正文图片
- 从正文图里选择封面
- 保存草稿

### 4. 正式发布

正式发布命令：

```bash
node .tmp/publish_wechat_article_controlled.js .tmp/toutiao_payload_google_io_2026.json
```

当前脚本的真实行为是：

1. 打开“新的创作 -> 文章”
2. 进入新标签页编辑器
3. 写入标题和正文
4. 插入正文图片
5. 进入封面选择流程
6. 点击发表
7. 处理两层发表确认弹层
8. 停在微信验证二维码处

如果到达二维码，这不算失败，脚本会返回：

- `awaiting_wechat_verification`

含义是：

- 自动化部分已经跑到平台允许的最后一步
- 接下来必须由人扫码

### 5. 人工扫码验证

本次实测的最终门槛是：

- 页面弹出 `微信验证`
- 提示“扫码后，请联系管理员进行验证”

说明：

- 管理员微信号或运营者微信号可以直接完成验证
- 非管理员微信号可能还需要管理员确认

扫码完成后，文章即可正式发表。

## 关键页面与节点

以下节点已经验证过，可作为后续维护的优先定位点：

- 新建文章入口：`.new-creation__menu-item`
- 标题编辑器：第 1 个 `.ProseMirror`
- 正文编辑器：第 2 个 `.ProseMirror`
- 正文图片上传：`#js_editor_insertimage input[type=file]`
- 封面区域：`#js_cover_area`
- 从正文选封面按钮：`.js_selectCoverFromContent`

## 正文图片链路

这部分已经确认稳定：

1. 不是系统文件弹窗方案。
2. 编辑器工具栏里已经存在可直接操作的 `input[type=file]`。
3. 可以直接用 `setInputFiles` 上传正文图。
4. 上传后图片会进入正文内容区。

已验证结论：

- 正文里能稳定插入 3 张图
- 平台会把本地图上传到微信自己的资源地址
- DOM 里能看到 `rich_pages wxw-img js_insertlocalimg`

## 封面链路

这次最关键的稳定结论是：

正文里即使已经有图片，也不等于封面要求已经满足。

平台的真实要求是：

1. 点击 `拖拽或选择封面`
2. 选择 `从正文选择`
3. 选中一张正文图片缩略图
4. 点击 `下一步`
5. 在裁剪弹层点击 `确认`

只有这样，后续点击发表时，`必须插入一张图片` 这个报错才会消失。

结论：

- “正文有图” 和 “封面已设置” 是两件事
- 当前最稳的封面方案不是单独上传 `cover.png`
- 当前最稳的方案是“从正文图片中显式选封面”

## 发表弹层链路

本次实测里，发表不是一次点击完成，而是多层确认：

1. 第一层：`发表 / 取消`
2. 第二层：`已开启群发通知 -> 继续发表 / 取消`
3. 第三层：`微信验证` 二维码

处理顺序必须按当前可见弹层来，不能只按按钮文案乱点。否则容易点到隐藏层里残留的同名按钮。

## 发布后复核

扫码成功后，建议手动做两层复核：

1. 回到公众号后台首页，查看“近期发表”或对应发布记录
2. 确认标题、封面、正文图片都符合预期

不要把“已经出现二维码”当成发布成功，也不要把“脚本运行结束”当成发布成功。

## 调试证据

这次链路里最有价值的调试快照在这里：

- [03-editor-filled.json](C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-05-24-google-io-2026-agentic-ai\debug\wechat\03-editor-filled.json)
- [04-after-save-draft.png](C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-05-24-google-io-2026-agentic-ai\debug\wechat\04-after-save-draft.png)
- [publish-state.json](C:\Users\Administrator\Documents\code-news\.tmp\generated\2026-05-24-google-io-2026-agentic-ai\debug\wechat\publish-state.json)
- [wechat-after-visible-publish-confirm.json](C:\Users\Administrator\Documents\code-news\.tmp\wechat-after-visible-publish-confirm.json)
- [wechat-after-continue-publish.png](C:\Users\Administrator\Documents\code-news\.tmp\wechat-after-continue-publish.png)

## 本次踩坑

### 1. 主 Chrome 不适合做正式链路

原因：

- 标签页太多
- 焦点容易乱
- 桌面级点击容易误命中

规避方式：

- 永远优先用专用可控 Chrome

### 2. 不能把“正文插图成功”误判成“封面已满足”

原因：

- 平台对封面有独立校验

规避方式：

- 必须显式走“从正文选择 -> 下一步 -> 确认”

### 3. 不能把二维码门槛误判成脚本失败

原因：

- 这是微信公众平台的最终人工验证步骤

规避方式：

- 把它当成标准流程的一部分
- 脚本层面返回 `awaiting_wechat_verification`

### 4. 调试时要警惕隐藏弹层

原因：

- 页面里可能残留不可见的旧弹层
- 同名按钮很多，直接按文本匹配容易误点

规避方式：

- 只操作当前可见的主按钮
- 关键步骤一定留截图

## 推荐工作方式

以后跑公众号文章，固定按下面顺序：

1. 先生成文章和图片资产
2. 确认专用 Chrome 已登录
3. 先跑 `--draft-only`
4. 检查草稿页的标题、正文、图片、封面
5. 再跑正式发布
6. 到二维码时人工扫码
7. 发布后回后台复核

## 后续改进建议

1. 给脚本补“扫码后轮询发表结果”的能力，自动把最终成功状态写入本地记录。
2. 给公众号链路单独加一个 `wechat-publish-records.json`，避免后续重复发同一篇内容。
3. 给发布后复核补一段自动检查逻辑，回主页确认“近期发表”确实出现新条目。
