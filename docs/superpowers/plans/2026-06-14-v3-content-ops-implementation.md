# v3 内容运营总控实施计划

> 面向当前仓库执行。第一阶段目标是把 `生成前到发布前` 的主链落地，不做正式发布。

## 目标

在 `C:\Users\Administrator\Documents\code-news` 内建立 v3 主控闭环：

1. 历史内容和发布记录可迁移进统一状态。
2. 当前内容可走 `预检 + 图片计划 + Skills 调用包 + 发布占位预览`。
3. 插图多样性从文档约束变成代码约束。

## 验证命令

统一用：

```powershell
python -m unittest discover -s tests -t . -v
```

## Task 1: 落库配置与接口映射

- [ ] 新建 `config/tool_registry.json`
- [ ] 新建 `config/content_domains.json`
- [ ] 新建 `config/image_strategy.json`
- [ ] 验证注册表能被脚本读取

验证点：

- 新配置文件存在
- 接口层名称完整
- 已采用 / 占位能力区分清楚

## Task 2: 落地图片多样性引擎

- [ ] 新建 `scripts/image_strategy.py`
- [ ] 新建 `tests/scripts/test_image_strategy.py`
- [ ] 先写失败测试：最近两篇封面家族重复时，必须自动避让
- [ ] 先写失败测试：同一篇的三张正文图必须选择不同家族
- [ ] 实现最小可用选择器

验证点：

- 测试通过
- 生成的图片计划明确写出：
  - `coverFamily`
  - `coverRenderer`
  - `coverPalette`
  - `bodyFamilies`
  - `bodyRenderers`

## Task 3: 落地 v3 预发布总控脚本

- [ ] 新建 `scripts/run_v3_content_ops.py`
- [ ] 新建 `tests/scripts/test_run_v3_content_ops.py`
- [ ] 先写失败测试：脚本执行后必须产出 `image-plan.json`
- [ ] 先写失败测试：脚本执行后必须产出 `skill-packets.json`
- [ ] 先写失败测试：脚本执行后必须产出 `publish-preview.json`
- [ ] 先写失败测试：状态文件必须出现 `v3` 区块和 `xiaohongshu` 占位状态
- [ ] 实现最小闭环

验证点：

- 不触发正式发布
- 能复用现有质量预检
- 能输出四平台发布占位信息

## Task 4: 落地历史迁移

- [ ] 新建 `scripts/migrate_legacy_data.py`
- [ ] 新建 `tests/scripts/test_migrate_legacy_data.py`
- [ ] 先写失败测试：缺失状态文件的历史目录可自动补齐
- [ ] 先写失败测试：已有发布记录能回填到统一状态
- [ ] 额外生成迁移索引

验证点：

- 旧内容目录缺状态时可补写
- 不覆盖已有状态
- 迁移只使用真实存在的旧证据

## Task 5: 收口与验证

- [ ] 运行完整测试集
- [ ] 用一个真实 payload 跑一次 v3 预发布链
- [ ] 记录当前还未自动接通的能力

验证点：

- 所有新增测试通过
- 实际产物可落在 `.tmp/generated/<slug>/`
- 最终输出需要用户配合的事项清单
