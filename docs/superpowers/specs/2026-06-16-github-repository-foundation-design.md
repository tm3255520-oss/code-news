# GitHub 仓库基础配置设计

日期：2026-06-16
范围：`tm3255520-oss/code-news`
档位：标准档

## 1. 背景

`code-news` 已经完成本地仓库初始化、远端绑定和分支推送，但 GitHub 仓库还缺少最基本的协作约束：

1. 仓库首页没有说明当前主线和目录入口。
2. 缺少统一的问题登记模板，后续任务、缺陷、复盘会继续散乱。
3. 缺少统一的 PR 说明模板，变更范围和验证信息不稳定。
4. `main` 还没有保护规则，后续容易出现误推、误覆盖和无验证合入。

这轮只补“仓库基础配置”，不把范围扩展到 CI、Project、Wiki 或自动化发布。

## 2. 目标

这轮配置只追四件事：

1. 给仓库首页补一份面向当前 v3 主线的 `README.md`。
2. 建立最小可用的 `.github/ISSUE_TEMPLATE/` 和 `pull_request_template.md`。
3. 定义一组服务当前内容生产链的基础 labels 方案。
4. 为 `main` 制定保守的分支保护规则。

## 3. 非目标

本轮明确不做：

1. 不补 GitHub Actions。
2. 不建立 GitHub Project 看板。
3. 不补 Wiki、Release、Discussion。
4. 不把历史旧方案整理进仓库首页。
5. 不把正式发布和 72 小时追踪写成当前已完成能力。

## 4. 仓库内文件方案

### 4.1 `README.md`

README 只服务当前主线，内容保持短而准，覆盖：

1. 仓库是什么。
2. 当前阶段做什么、不做什么。
3. 目录入口怎么找。
4. 推荐工作流是什么。
5. 当前重点脚本和配置入口在哪里。

处理原则：

1. 不回写历史噪音。
2. 不写“已经全自动发布”这类不成立的话。
3. 明确小红书当前只保留预发布和策略位，不进入正式发布。

### 4.2 Issue 模板

先建两个 Markdown 模板：

1. `task.md`
   - 用于新增任务、规划项、阶段性落地动作。
2. `bug.md`
   - 用于流程异常、脚本问题、平台行为异常、质量回归。

模板只固定关键信息，不做花哨表单：

1. 背景 / 目标
2. 范围
3. 产出物
4. 验证方式
5. 风险或阻塞

### 4.3 `pull_request_template.md`

PR 模板固定以下信息：

1. 改了什么
2. 为什么改
3. 如何验证
4. 风险与回滚点
5. 本次明确不包含什么

目标是减少“改动很大但没有验证说明”的合入。

## 5. Label 方案

labels 先收敛为四类，直接服务现阶段内容链：

### 5.1 `topic/*`

1. `topic/ai-tools`
2. `topic/efficiency-tools`
3. `topic/digital-products`
4. `topic/light-tech`

### 5.2 `platform/*`

1. `platform/toutiao`
2. `platform/zhihu`
3. `platform/wechat`
4. `platform/xiaohongshu`

### 5.3 `stage/*`

1. `stage/monitor`
2. `stage/analyze`
3. `stage/rewrite-plan`
4. `stage/draft`
5. `stage/image`
6. `stage/preflight`
7. `stage/publish`
8. `stage/review`

### 5.4 `risk/*`

1. `risk/compliance`
2. `risk/duplicate`
3. `risk/quality`
4. `risk/tooling`

结论：

1. 不建过多 labels。
2. 先把平台、阶段、风险打透。
3. 等真正进入发布后追踪，再决定是否扩展 `metric/*` 一类标签。

## 6. `main` 分支保护策略

这轮采用保守规则，不假设 CI 已经完善：

1. 阻止直接强推到 `main`。
2. 阻止删除 `main`。
3. 通过 PR 合入 `main`。
4. 要求分支在合入前保持最新。
5. 暂不强制审批人数。
6. 暂不强制状态检查。

这样做的原因很直接：

1. 先把误操作挡住。
2. 不因为 CI 尚未成形而让仓库卡死。
3. 给后续加状态检查留空间。

## 7. 落地顺序

1. 写入本设计文档。
2. 新建 `README.md`。
3. 新建 `.github/ISSUE_TEMPLATE/task.md`。
4. 新建 `.github/ISSUE_TEMPLATE/bug.md`。
5. 新建 `.github/pull_request_template.md`。
6. 本地校对文件内容。
7. 后续再执行 labels 创建和 `main` 分支保护。

## 8. 成功标准

这轮完成的标准是：

1. 仓库首页能说明当前主线和入口。
2. Issue/PR 有稳定模板可用。
3. labels 和分支保护的规则已经成文并可执行。
4. 不额外引入超范围的 GitHub 配置。

## 9. 后续动作

本轮文件落地后，再做两件仓库外动作：

1. 在 GitHub 仓库里创建 labels。
2. 在 GitHub 仓库设置页里配置 `main` 分支保护。
