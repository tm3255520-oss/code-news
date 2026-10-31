---
name: publish-content-completeness-gate
description: 给**已接通的发布环节**装「内容完整性门禁」——封面槽比例/横封面接线、标题·描述非空、必填项按契约逐项自审。当用户说「先把某平台的发布环节整改清楚」「封面不对/沿用上一条的封面」「除了视频本身，封面标题必填项要完善好」「发布后才发现少东西」「字段写了但没生效」时使用。含**六平台封面槽实测表**（抖音/快手/视频号/小红书 四个 9:16 竖版平台封面槽**全是 3:4**；B站/头条 16:9 横版无需登记）、三条硬认知（**封面槽比例 ≠ 视频画幅**、`form verify` 对必填缺项**不报错**、契约 required 写在**属性对象内部**而非标准 `required:[]` 数组）、内容寻址封面名、**证据等级纪律**（`SLOT_EVIDENCE` 区分「实测」与「推断」）、门禁摆放纪律（出图侧告警 + 发布侧硬拦 + 未实测平台不误伤）与 13 项验证清单。**边界**：只讲**已接通通道的内容完整性**；接新通道归 `yxer-publish-channel-onboarding`，建只读体检件归 `publish-line-preflight-entry`。
agent_created: true
version: 1.1.0
tags: [发布, 封面, 封面槽, 必填项, 门禁, 契约自审, yxer, 内容寻址]
---

# 给发布环节装「内容完整性门禁」

> 触发信号：**视频本身没问题，但发出去之后才发现封面不对 / 沿用上一条 / 少了必填项**。
> 这类缺陷的共同特征：**不报错、不崩溃、静默失效** —— 只能靠人肉发现。
> 本文是把它们从「靠人记」改成「代码拦」的标准动作。

## 〇、先记住这三条（不知道就会白干）

### 1. 🔴 平台**封面槽比例 ≠ 视频画幅** —— 而且**每个平台的视频画幅也不同**

最容易翻车的一条。**六平台实测结果**（2026-10-13，登入各自创作后台逐个核实）：

| 平台 | 视频画幅 | 封面槽 | 证据等级 |
|---|---|---|---|
| 抖音 | 1080×1920（9:16） | **竖 3:4** ＋ **横 4:3** | ✅ 实测 |
| 快手 | 1080×1920（9:16） | **竖 3:4** | ✅ 实测 |
| 视频号 | 1080×1920（9:16） | **竖 3:4** | ✅ 实测 |
| 小红书 | 1080×1920（9:16） | **竖 3:4** | ⚠️ 推断 |
| B站 | 1920×1080（16:9） | 按画幅 | ➖ 分析（无需登记） |
| 头条 | 1920×1080（16:9） | 按画幅 | ➖ 分析（无需登记） |

🔴 **所有 9:16 竖版平台的封面槽都是 3:4** —— 不是抖音一家的特例。
原实现"按视频画幅出封面"→ **四个竖版平台全部错配**
（抖音只是最先被发现的那个，因为它那条视频先露出问题）。
按 9:16 出图 → 平台**不认** → 回落到**上一条视频的封面**，
用户看到的现象就是"新视频用了昨天的封面"。

**反过来说**：B站 / 头条是 **16:9 横版视频**，封面与画幅基本一致
（B站官方推荐 1146×717 ≈ 16:10，差 ~11%，平台会裁切适配，不属于「比例错误」）
→ **不登记**。硬加规则 = 引入一条未核实的约束。

**取证姿势**（打开一条**已有作品**去"编辑"，全程零副作用）：

| 平台 | 入口 |
|---|---|
| 抖音 | 创作服务平台 → 内容管理 → 编辑作品 → 设置封面 |
| 快手 | 创作者服务平台 → 作品管理 → 编辑作品 → 封面设置 → **裁剪比例** |
| 视频号 | 视频号助手 → 作品 → **修改描述和封面** |
| 小红书 | 创作者中心 → 笔记管理 → 编辑（⚠️ 本机该域名常超时） |

⚠️ **别信第三方速查表**：实测视频号封面是 **3:4**，而多份速查表写「6:7」。
旁证只在拿不到实测时用，且必须标注为「推断」。

### 2. 🔴 `publish form verify` 对「必填缺项」**是不报错的**

它只判"表单自洽"。真正会报的只有 `yxer validate`，而且只有一句笼统的
`Schema validation failed` —— 不说缺哪项。**必须自己按契约点名。**

### 3. 🔴 契约里 `required` 的位置跟标准 JSON Schema **不一样**

yxer 导出的表单契约把 `required` 写在**每个属性对象内部**：

```json
"formType": {"type": "string", "required": true, "const": "task"}
```

而**不是**标准写法 `{"properties": {...}, "required": ["formType"]}`。
→ 通用校验库直接套**没用**，得自己递归下钻。

**还有一层**：契约 JSON 有时**漏标**必填。实测 `cover` / `coverKey`
契约里没有 `required: true`，但 yxer 文档 `references/platforms/video/index.md` §1.4
的「必填」列写的是「是」。**只靠契约一条腿会把它们静默漏掉** →
另设一张 `DOC_REQUIRED_ACCOUNT` 补判，并在报错里注明来源，别让人以为是契约要求的。

---

## 一、封面：三件事一起做

### 1.1 抽一个「封面槽规格」模块当**单一事实源**（关键）

槽比例**同时被两个脚本需要**：出图（`make_platform_covers.py`）与发布门禁（`publish_via_yxer.py`）。
两处各写一份常量 → 改一处忘另一处 = 静默失效（本仓库已三次踩到同款：
矩阵字段未接线、`--bgm/--sfx` 未接线、封面生成未接进编排器）。

```python
# platform_cover_spec.py  —— 不 import PIL！
COVER_SLOT = {
    "抖音":   {"vertical": (1080, 1440), "horizontal": (1440, 1080)},
    "快手":   {"vertical": (1080, 1440)},
    "视频号": {"vertical": (1080, 1440)},
    "小红书": {"vertical": (1080, 1440)},     # ⚠️ 推断，未实测
    # B站 / 头条 故意不登记：横版视频，封面按画幅走即可
}
HORIZONTAL_COVER_REQUIRED = {"抖音"}          # 只有抖音有独立横槽
RATIO_TOLERANCE = 0.015

# 🔑 给每条规格标「证据等级」—— 防止「推断」被当成「已核实」用，
#    同时告诉下一轮该补哪个平台的实测（核实后只改这一处，脚本不用动）
SLOT_EVIDENCE = {
    "抖音":   "实测 2026-10-13 · 创作服务平台「设置封面」",
    "快手":   "实测 2026-10-13 · 创作者平台「编辑作品→封面设置→裁剪比例」",
    "视频号": "实测 2026-10-13 · 视频号助手标注『个人主页和分享卡片(3:4)』",
    "小红书": "⚠️ 推断（未实测）· 待登入创作者中心核实",
}
```

**新增平台只需往 `COVER_SLOT` 加一行** —— 出图侧与发布门禁两侧自动接管。

🔴 **这个模块必须不 import PIL** —— 发布脚本跑在系统 Python 上，Pillow 不保证可用；
而门禁要在 `upload` **之前**判，不能等上传后回读宽高（那时文件已经出去了）。
所以要自带一个**零依赖读图尺寸**：PNG 读 IHDR（字节 16–24），JPEG 扫 SOFn 标记。

### 1.2 横封面一定要接线（**极易漏**）

`horizontalCover` 属于「**从来没人写过**」的字段 —— 契约里可选、validate 不会报，
所以能一路走到发布都发现不了。写入位置按官方口径：

```
✅ accountForms[0].contentPublishForm.horizontalCover
❌ accountForms[0].horizontalCover     # additionalProperties:false 会拒
（也可写 publishArgs.horizontalCover，CLI 校验时会补齐到 contentPublishForm）
```

结构用 `OldCover`：**只有 `{key, size, width, height}`，四个各自 required，没有 `format`**。
→ 写的时候**显式白名单**，别照抄 `cover` 的字段列表（那个带 `format`）。

自动发现横封面：显式 `--cover-horizontal` → 同目录最新 `cover_h_*.png` → 固定别名。
⚠️ **非必需平台不要瞎猜**：多写字段会被 `additionalProperties:false` 拒掉。

### 1.3 封面文件名改**内容寻址**

`yxer upload` 的**远端 key 取自本地文件名**，而远端路径是**按账号固定**的。
实证：`yxer query records` 里两次不同日期的发布，封面地址前缀完全相同：

```
https://oss-v2.yixiaoer.cn/yfb/t-6abf6a5173273a1c5cd7c6c8/cover.png   ← 10-11
https://oss-v2.yixiaoer.cn/yfb/t-6abf6a5173273a1c5cd7c6c8/cover.png   ← 10-13
```

固定名反复覆盖同一路径 → 撞缓存风险成立。

**做法（零破坏）**：出图侧写**两份**——内容哈希名 + 固定别名；
发布侧只凭「名字里的哈希 == 文件内容的哈希」**自证**挑哈希名：

```python
def content_addressed(p: Path) -> Path:
    digest = hashlib.sha1(p.read_bytes()).hexdigest()[:8]
    cand = p.with_name(f"{p.stem}_{digest}{p.suffix}")
    return cand if cand.is_file() else p       # 拿不到就退回原名
```

好处：**不需要额外传参或清单**，且哈希自证 → 别名过期也不会挑错（自动退回原名）；
`cover.png` 仍在 → 只认固定名的旧调用方（含历史 manifest）**一行都不用改**。

---

## 二、必填项：按契约自审（递归下钻）

```python
def audit_required(session: Path, payload: dict) -> list[str]:
    contract = json.loads(session.read_text(encoding="utf-8"))
    forms = (payload.get("publishArgs") or {}).get("accountForms") or []
    props = (((contract.get("contract") or {}).get("businessFields") or {})
             .get("accountForms") or {}).get("items", {}).get("properties", {})
    missing = _missing_in(props, forms[0], "")
    for name in DOC_REQUIRED_ACCOUNT:        # 契约漏标、文档标了的
        if forms[0].get(name) in (None, "", {}, []):
            missing.append(f"{name}（文档标必填，契约 JSON 未标 → 必须补判）")
    return missing


def _missing_in(schema_props: dict, obj: dict, prefix: str) -> list[str]:
    """required=true 的键要存在且非空；存在且 schema 给了 properties 就继续下钻。
    下钻是为了覆盖 horizontalCover 这类**嵌套对象自己的子必填**。"""
    missing = []
    for name, spec in (schema_props or {}).items():
        if not isinstance(spec, dict):
            continue
        path = f"{prefix}.{name}" if prefix else name
        present = isinstance(obj, dict) and obj.get(name) not in (None, "", [], {})
        if spec.get("required") is True and not present:
            missing.append(path)
            continue
        if present and isinstance(spec.get("properties"), dict) and isinstance(obj.get(name), dict):
            missing += _missing_in(spec["properties"], obj[name], path)
    return missing
```

**位置纪律**：放在**导出之后、`validate` 之前**。
代价是"视频/封面已经传过了，缺项时会白传一次"；
换来的是**以导出后的真实 payload 为准**（连 CLI 自己丢字段也能查出来），
而不是只对照"我打算写什么"。**宁可白传一次，也别放过一个静默缺项。**

**契约读数不复制进代码** —— 这条是「有规则只留一处」的直接应用：
字段增删/约束变化自动跟上，不用回来改常量。

---

## 三、文案：`minLength:1` 不等于 required

契约里 `title` / `description` 有的只标 `minLength: 1`、**不标 required**
→ 为空时 `verify` 照样过，到 `validate` 才报笼统错误；平台侧表现是"发出去没有标题"。

补一张显式表（**逐平台核过契约的 `minLength`**）：

```python
COPY_REQUIRED = {
    "抖音": ("title", "description"),   # 契约两者都 minLength=1（发布页实测描述为必填）
    "快手": ("title",),                 # title minLength=1；description minLength=0（可空）
    # B站/头条：title（头条连同 description）契约就是 required=true
    #          → 由 audit_required() 覆盖，**不在这里重复登记**（同一规则只留一处）
    # 小红书/视频号：title/description 契约都无 minLength → 平台允许空，不拦
}
```

**判据是契约的 `minLength`，不是"我觉得应该有"** —— 小红书/视频号硬加"非空"
会拦住平台本来就允许的发布。

标题**长度上限**通常早就有前置拦（`TITLE_MAX` / `DESC_MAX`），别重复造；
本轮核对发现已有实现与契约 `maxLength` 完全一致，直接沿用。

---

## 四、门禁摆哪儿（三道，各司其职）

| 层 | 位置 | 力度 | 理由 |
|---|---|---|---|
| 出图后 | 编排器（`adapt_for_platforms`） | **只告警** | 成片已生成；且发布侧还有硬门禁，不在这里重复阻断 |
| 发布前 | 发布脚本（`publish_via_yxer`） | **硬拦**（`SystemExit`） | 必须在**任何网络调用之前** —— 日志里连「① 建表单会话」都不该出现 |
| 逃生门 | `--relax-content-gate` | 一次放宽三档 | 用**一个**开关，别开三个（封面比例/缺横封面/文案为空） |

**摆放位置怎么验**：喂一个错封面跑一次，看日志**有没有**「① 建表单会话」。
有 → 摆晚了（已经白建会话白上传）。

**未实测的平台必须不误伤**：门禁只对规格表里登记过的平台生效。
`cover_gate('快手', …)` 要返回空 —— 这样下一轮补实测只需**填表**，脚本不用再改。

---

## 五、验证清单（13 项，照抄即可）

| # | 验证项 | 期望 |
|---|---|---|
| 1 | 出图 | 打印实际尺寸 + 哈希文件名 |
| 2 | **出图确定性** | 同输入重出，sha1 不变（证明"补出"不会悄悄换图） |
| 3 | 门禁·正例 | `[]` |
| 4 | 门禁·负例 | 喂**真**错比例图（自己合成合法 PNG 头，别用"看起来像"的文件） |
| 5 | 门禁·缺封面（**竖、横各试一次**） | 点明缺哪个 + 期望比例。竖传 `None` 走"必填缺项"分支，**不能抛异常** |
| 6 | 门禁·其他平台 | `[]`（不误伤） |
| 7 | 自审·正例 | `[]` |
| 8 | 自审·嵌套子必填 | 删子字段 → 逐个点名 |
| 9 | 自审·契约 required | 删 `formType` → 点名 |
| 10 | 自审·文档补判 | 删 `coverKey` → 点名并注明"契约未标" |
| 11 | **先拦后发** | 错封面 → 网络调用前退出 |
| 12 | **契约无漂移** | 新拉契约的 `contractHash` 与上次一致 |
| 13 | **未误投递** | `yxer query records` 最新一条时间戳**没变** |

⚠️ **第 13 项必做**：`--relax-content-gate` 这类逃生门会**真的往下走**。
测它的时候**一定要带 `--dry-run`**，或用一个必然上传失败的文件（如 4 字节假 mp4），
否则会拿测试文案真发一条出去。测完立刻查 `yxer query records` 复核。

---

## 六、踩坑集

| 坑 | 现象 | 处置 |
|---|---|---|
| 按视频画幅出封面 | 平台不认，回落到上一条的封面 | 见 §〇·1，槽比例单独记账 |
| 横封面字段从来没写 | validate 不报错，横槽永远空 | 见 §一·1.2，加进 `sets` |
| 固定封面名 | 换了图仍显示旧图 | 见 §一·1.3，内容寻址 |
| 用通用 JSON Schema 校验器 | 报"全部通过" | required 位置不同，见 §〇·3，自己递归 |
| 门禁函数没防 `None` | 缺封面时抛 `TypeError` 而非点名 | 门禁的**全部职责**是"友好点名"；任何入参缺失都先 `is None` 判一遍再取尺寸（见 §五·5） |
| 只读契约不读文档 | `cover`/`coverKey` 被当"不必填" | 加 `DOC_REQUIRED_ACCOUNT` 补判 |
| 门禁放在上传之后 | 缺项时白传一次大视频 | 位置纪律见 §四 |
| 逃生门测出真发 | 测试文案上线了 | 测试必带 `--dry-run`，见 §五·13 |
| 写 `accountForms[].horizontalCover` | `additionalProperties:false` 拒 | 写 `contentPublishForm.horizontalCover` |
| 相对工作目录 `.tmp/...` | 在别的 cwd 跑，产物落到别处；对比文件时看得一头雾水 | 跑脚本前先确认 cwd，或显式 `--work-dir` |
| `yxer` 走 `subprocess([...])` | `FileNotFoundError: WinError 2` | 它是 npm 全局的 cmd/shim，用 shell 调用或走本仓库的 `run()` 封装 |

---

## 七、边界

- 接**新通道**（新平台 / 新内容类型）→ `yxer-publish-channel-onboarding`
- 建**只读体检件**（通道可用性 / 登录态）→ `publish-line-preflight-entry`
- 采集线接入 → `platform-line-onboarding`
- 本 skill 只管**已接通通道的内容完整性**（封面 / 文案 / 必填项）。

> 权威口径文档：`D:/Obsidian Vault/obsidian Vault/系统中枢/经验沉淀/工作流/platform-publish-automation.md`
> 本机实例（2026-10-13，抖音）：
> - `code-news/scripts/platform_cover_spec.py`（规格 + 门禁原语，单一事实源）
> - `code-news/scripts/make_platform_covers.py`（内容寻址出图）
> - `code-news/scripts/publish_via_yxer.py`（横封面接线 + 门禁 + 必填自审）
> - `code-news/scripts/adapt_for_platforms.py`（出图后复核）
> - 方案与证据：`D:/AI-VIDEO/config/抖音发布整改方案-20261013.md` §六
