# stale benchmark 输入硬闸门设计

日期：2026-06-20  
范围：`scripts/run_content_signal_pipeline.py`、`scripts/run_v3_content_ops.py` 及对应测试  
阶段边界：只把“对标输入过期”从提示升级为预检阻断，不进入正式发布，不自动刷新对标输入。

## 1. 背景

当前 v3 主链已经补齐两层能力：

1. `signalPipeline` 能写出对标输入来源追踪：
   - `sourceKind`
   - `registryKey`
   - `requestResolvedFrom`
   - `recordsResolvedFrom`
2. `signalPipeline` 能写出输入新鲜度观察值：
   - `requestAgeHours`
   - `recordsAgeHours`
   - `freshnessStatus`
3. `operator-checklist.md` 已能把这些信息展示给人工确认环节，并在 `freshnessStatus=stale` 时提示先刷新输入。

问题在于：现在的 stale 只停留在“提示层”，还没有进入状态机。旧的对标输入仍可能继续流入 `publish-preview` 和三平台预发状态，导致运营端看到“可确认发布”，但实际前置依据已经过期。

## 2. 目标

这次改动只完成一件事：

1. 当 `v3.signalPipeline.freshnessStatus == "stale"` 时，把头条、知乎、公众号三平台统一降为“不可发布”的预检阻断态。

同时满足三个可见性要求：

1. `pipeline-state.json` 能看到阻断结果和阻断原因。
2. `publish-preview.json` 能看到阻断结果和阻断原因。
3. `operator-checklist.md` 顶部保留明确动作提示，要求先刷新对标输入。

## 3. 非目标

这次明确不做：

1. 不改 `fresh` 与 `missing` 的既有判定逻辑。
2. 不自动刷新 benchmark request 或 records。
3. 不改小红书占位逻辑。
4. 不进入正式发布脚本。
5. 不引入新的 freshness 等级或动态阈值配置。

## 4. 设计原则

### 4.1 只在预检层加闸门

过期输入的问题本质上是“是否允许继续下游预发链”，因此闸门应落在 `run_v3_content_ops.py` 的预检状态整合层，而不是回写到 `run_content_signal_pipeline.py` 改变 freshness 计算语义。

### 4.2 统一阻断，不做平台分化

stale 的问题是共用输入已经过期，不是某个平台的单独问题。因此头条、知乎、公众号应统一处理，避免同一篇内容在不同平台出现不同的预检结论。

### 4.3 阻断必须可追踪

只改平台状态不够。阻断原因必须能在统一状态文件和预发预览文件中看到，避免后续人工排查时只能从 checklist 文本猜测发生了什么。

## 5. 行为设计

### 5.1 触发条件

命中以下条件时触发硬闸门：

- `state["v3"]["signalPipeline"]["freshnessStatus"] == "stale"`

### 5.2 三平台状态变更

命中硬闸门后，对以下平台统一改写：

- `platforms.toutiao`
- `platforms.zhihu`
- `platforms.wechat`

改写规则：

1. `status` 变为阻断态。
2. `prepublishStatus` 不再允许保留 `ready_for_confirmation`，而是写成明确阻断原因。
3. 记录 `error` 或等价说明字段，内容聚焦为“benchmark inputs stale”。
4. 保留 `manualConfirmRequired=true` 与 `formalPublishEnabled=false`，不扩大语义。

小红书不参与这次改写，继续保留现有 placeholder 逻辑。

### 5.3 `pipeline-state.json` 表达

`v3.signalPipeline` 保持现有 freshness 观测字段不变。  
阻断结果写入平台状态区即可，不额外发明新的顶层结构。

这样做的原因是：

1. freshness 是输入观测；
2. 阻断是下游状态决策；
3. 两者分层后更容易排查“为什么 stale”与“stale 后系统做了什么”。

### 5.4 `publish-preview.json` 表达

预发预览需要与平台状态保持同一结论：

1. 三平台预览结果不再表现为“待人工确认即可发布”。
2. 改为清晰的阻断态，例如 `blocked_by_stale_benchmark_inputs`。
3. 同时带出 freshness 背景，至少包含：
   - `freshnessStatus`
   - `requestAgeHours`
   - `recordsAgeHours`

### 5.5 `operator-checklist.md` 表达

继续保留顶部强提示，但提示语义从“建议刷新”明确为“必须先刷新，否则不可继续三平台预发确认”。

## 6. 代码落点

### 6.1 `scripts/run_content_signal_pipeline.py`

不改变 freshness 计算规则。  
只继续作为输入观测层，输出：

- `requestAgeHours`
- `recordsAgeHours`
- `freshnessStatus`

### 6.2 `scripts/run_v3_content_ops.py`

这里是本次主改动落点，需要补三类逻辑：

1. 统一识别 `signalPipeline.freshnessStatus == "stale"`。
2. 在平台状态整合阶段，把头条/知乎/公众号压成阻断态。
3. 在 `publish-preview` 生成阶段把阻断原因写透。

如果当前已有“清理陈旧平台状态”的帮助函数，应优先在这一层扩展，而不是新造一套平行状态改写流程。

### 6.3 测试

最少补两类回归：

1. `stale -> blocked`
   - 三平台不能再保留 `ready_for_confirmation`
   - `publish-preview` 能看到阻断原因
   - `operator-checklist` 保留强提示
2. `fresh -> unchanged`
   - 当前可确认预发链不回归

## 7. 风险与取舍

### 7.1 为什么不把 `missing` 一起并入硬闸门

`missing` 当前已经有独立缺源语义，和 stale 不是同一个问题。把两者混改会扩大测试面，也会让这次变更从“旧输入拦截”漂移成“整套输入状态重构”。

### 7.2 为什么不在 `run_content_signal_pipeline.py` 直接输出 blocked

那会把输入观测层和预检决策层耦合起来。后续如果还要增加别的闸门，例如质量分、素材缺失、平台合规预警，就会继续把 signal 层写成总控层，边界会变差。

### 7.3 为什么不自动刷新 stale 输入

自动刷新属于下一层能力，涉及 benchmark request 重建、记录再抓取、幂等覆盖和失败恢复。这和“先确保旧输入不能误流转”不是一个工作量级，不应混进本次最小改动。

## 8. 成功标准

这次设计落地后，满足以下标准才算完成：

1. 任一内容只要 `freshnessStatus=stale`，头条、知乎、公众号就不能再显示为可确认预发。
2. `pipeline-state.json`、`publish-preview.json`、`operator-checklist.md` 三处能看到一致的阻断结论。
3. `fresh` 路径不回归，现有测试继续通过。
4. 不引入正式发布行为，不改变小红书占位逻辑。
