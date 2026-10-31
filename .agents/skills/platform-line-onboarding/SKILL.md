---
name: platform-line-onboarding
description: 给 Obsidian 自媒体中枢「新接一条平台采集线」（关注清单 → 博主闸 → 作品闸 → 去重 → 落盘 raw/运营中心 双线 → 记台账 → 登记文档）的标准动作清单与踩坑集。当用户说「参照 XX 线把 YY 平台也接进来」「把某平台关注博主的内容采进来」「新接一条产线」「这条线怎么接」时使用。含零回归对照手法（改共享脚本必做）与词表匹配陷阱。
agent_created: true
version: 1.1.0
tags: [pipeline, onboarding, vault, hermes, raw, 运营中心]
---

# 新平台采集线接入（platform-line-onboarding）

> 为什么有这份：2026-10-01 一天之内接了 **三条**平台线（视频号 / 公众号 / 知乎）。
> 每次都要重新推一遍「闸门怎么复用、落盘写哪、文档改哪、怎么证明没改坏别的线」——
> 这份把动作和坑一次固化。三条线的产物都在 `系统中枢/系统脚本工具链/` 两份工具说明里。

## 一、动手前（不许跳）

```bash
# 1) 开工三查
python C:\Users\Administrator\Documents\code-news\scripts\work_lookup.py "<平台/主题关键词>"
#    命中「进行中」且非自己 → 不重复开工；命中「已完成」→ 复用产出

# 2) 复用守则盘点（三选一：直接调用 / 扩展合并 / 新建）
python C:/Users/Administrator/Documents/code-news/scripts/tool_inventory.py <关键词>
```

**默认答案几乎总是「复用」**。已存在的可复用件（2026-10-01 现状）：

| 环节 | 现成件 | 说明 |
|---|---|---|
| 博主级方向闸 | `raw_creator_filter.py` | **平台自适应**，靠清单的「平台」字段；`--profile ai\|ops` |
| 作品级方向闸 | `ops_work_filter.py` | **平台自适应**（清单有 `bvid` → B站判 `title＋desc`；否则判 `desc`）；`--profile ai\|ops` |
| 挑批 | `raw_pick_batch.py` | 平台自适应，靠 `--state`；**有 fans 的平台走 fans 分支，只有昵称/认证的走 signal 分支** |
| 三层去重闸 | `raw_dedup.py` | 平台自适应（抖音/视频号；新平台要加字段特征） |
| 视频转录底座 | `video_collect.py` | `download_audio` / `transcribe_whisper` / `detect_platform` 可 **import 复用**；**必须 Python313**（yt_dlp/whisper 只装那儿） |
| 正文体例（视频/文章） | `batch_polish_transcripts.standard_body()` / `standard_article_body()` | 「核心要点＋整理稿＋原文」的**唯一实现** |
| 台账 | `ops_tracker.py` / `raw/.state/collection_tracker.json` | 两线各一份；`ops_tracker.record()` **要显式传 `platform=`**（默认 douyin，不传会记错） |
| 正文顺化 | `raw_lint.normalize_body()` / `compact_whitespace()` / `paragraphize()` | 别自己写 |
| 路径常量 | `vault_paths.py` | **单一事实源**，别硬编码路径 |

**只有「该平台特有的取数通道」才值得新建脚本。**

## 二、标准动作清单

1. **探针先行**（只读，不写任何文件）：先用 `bsk evaluate` 在浏览器登录态下试通该平台的
   「关注列表」「某博主的作品列表」两个接口，拿到真实字段名与总量。
   **结论必须是实测的**，不能靠记忆或二手资料。探针落 `code-news/scripts/_probe/`。
2. **建关注清单采集器**：产出 `raw/.state/关注清单-<平台>.json`，
   **结构与已有清单同构**（`平台` / `关注总数` / `采集条数` / `已拉到页` / `采集于` / `博主:[{nick, sec, fans, works, ...}]`）
   —— 同构才能直接喂现成的闸门。
3. **跑博主闸**，出两张明面候选表（ai 画像 → `raw/_报告/选号/`；ops → `运营中心/_报告/选号/`）。
4. **建作品采集器**（若有需要），走 `--line raw|ops` 或 `--out-dir` 判线。
5. **端到端测试**：每条线真落几篇，跑 `raw_lint` 验合规。
6. **登记文档**（见 §五）。
7. **收工三写**（见 §六）。

## 三、零回归对照（**改共享脚本必做，这是硬要求**）

`raw_creator_filter.py` / `raw_pick_dedup` 这类被 4~5 条产线共用的脚本，改之前必须留对照：

```bash
# 改前：用 --out 指向临时路径（绝不碰 vault），保存 md5
python raw_creator_filter.py --profile ai --out /tmp/base_ai.md
python raw_creator_filter.py --profile ops --out /tmp/base_ops.md
md5sum /tmp/base_ai.md /tmp/base_ops.md
# 改后：同样跑一遍，diff 必须为空（或差异**逐条可解释**）
diff /tmp/base_ai.md /tmp/new_ai.md
```

**设计原则**：新能力要**按条件自动启用**，让老清单走不到新分支。
例：`--headline auto`（默认）＝ 清单里有 `headline` 字段才启用 → 抖音/视频号/公众号/头条的清单没这个字段，
判定与报告**逐字节不变**。

**若差异非空**：不要藏着 —— 逐条列出「上调/下调」各多少、具体哪些、为什么，交用户裁。
（例：词表匹配口径修复改了 25 行，3 个「下调」全是修掉假阳性 —— 这就叫可解释。）

**改词表专用闸**（比 md5 diff 更硬，2026-10-02 立）：
`python code-news/scripts/_probe/wordlist_regression.py` —— 一次量清三段：
A 博主级（6 份关注清单：bilibili/douyin/channels/wechat/toutiao/zhihu）｜
B 作品级（B站 260 ＋ 抖音 798 去重 ＋ 视频号 103）｜
C **逐词归因**（每个新词各命中几条、原本属于哪桶）。
`--add "词1,词2"` 可临时换候选集复测；`--unify-all` 才是把 WEAK/NO 也合一（默认关，因为会收窄排除面）。
**验收线：博主级「下调 0」，作品级差异逐条可解释。**

## 四、踩坑集（都是实测踩过的）

| 坑 | 现象 | 正解 |
|---|---|---|
| **词表匹配大小写** | `w in text` 区分大小写 → 小写 `ai` 漏判；但朴素 `.lower()` 会把 `InsDaily`/`Chain`/`brain`/`Pai` 判成 AI | 用 `raw_creator_filter._hit()`：归一 ＋ 词边界（含**驼峰转折**） |
| **`re.I` 吃掉 lookaround** | `(?<=[a-z])(?=[A-Z])` 配 `re.I` 后 `[A-Z]` 也变不敏感 → 驼峰判据失效 | 边界判定**在 Python 里显式做**，别放正则 |
| **简介含 `\|` 撑断 Markdown 表** | 报告表格断列 | 写进表格的单元格要 `.replace("\|","\\\|")` |
| **续传从「下一页」续** | 关注列表是**追加式**，新增的人排末尾 → 从下一页续会跳过 | 从**最后一页**重拉续起，靠 id 去重 |
| **把「备选」也当入选** | 既定口径是「仅弱词→备选（**宁可不采**）」，误采会捞进综合新闻号 | 默认**只取候选**，备选要显式开关 |
| **bsk 会话掉线** | 输出 `waiting for browser extension to connect…`，所有 fetch 返回空 | 先 `bsk status` 看 `browsers connected`；失败就**重跑**（脚本应按 id 断点续传，不重复落盘） |
| **共享台账编码** | Windows 默认 GBK 读 UTF-8 台账 → `UnicodeDecodeError` | 读写**都写死 `encoding="utf-8"`** |
| **闸门落点互相覆盖** | `--profile ai` 与 `ops` 的产物同名 | 靠 `--profile` 决定落 `raw/_报告/选号/` 还是 `运营中心/_报告/选号/` |
| **挑批也踩「裸子串大小写」** | `pick_douyin()` 用 `w in nick`（大小写敏感），而词表已归一 → 含 `Ai` 的号被判「无强词」漏掉（2026-10-02 实测抖音漏 6 个号，含粉丝第一的「Ai风向标」104.8万） | 改共享脚本时，**别只改闸门**——凡用到词表的地方（闸门 / 挑批 / 过滤）都要同源走 `raw_creator_filter._hit()` |
| **同一张词表存了两处** | ai 强词表 `raw_creator_filter.AI_STRONG`（20 词）与 `ops_work_filter.AI_STRONG2`（26 词）**各存一份且已漂移**（作品级多 `ChatGPT/Gemini/Midjourney/开源模型/多模态`）→ 改一处漏一处，正是 2026-10-01「两级闸门口径打架」的复发点 | 立**单一真源**：`raw_creator_filter` 改为 `from ops_work_filter import AI_STRONG2 as AI_STRONG`，本地只留 `_AI_STRONG_FALLBACK` 兜底。**调 ai 词表只改 `ops_work_filter` 一处。**（WEAK/NO 两级**有意不合一**：作品级排除词比博主级窄是对的，强行合一会让 5 个博主从「不候选」退成「待人工」） |
| **凭感觉补词 / 补完不验证** | 新平台语料里大量内容落「待人工」，随手往词表塞词 → 要么没补到点子上，要么在别的平台误伤 | ① 先跑语料探针量「待人工」占比与词频（`_probe/bili_wordlist_probe.py` 是模板）；② 补词口径＝**探针语料实证** ∪ **无歧义的 AI 产品名**；③ 有同形词风险的（`豆包`撞红豆包、`龙虾`撞小龙虾、`Kimi/海螺/星火/扣子/元宝` 撞人名动物常用词）**宁缺毋滥**，理由写进词表上方注释；④ 补完必过**跨平台零回归闸**（`_probe/wordlist_regression.py`：6 平台关注清单 ＋ 3 份作品语料 ＋ 逐词归因），要求「下调 0」 |
| **只看 B站语料就下结论** | 260 条 B站作品只覆盖 9 个 UP 主，不足以代表全平台；凭它调词会以为「0 命中＝不需要」 | 探针要**跨语料交叉**：B站 260 ＋ 抖音 798 ＋ 视频号 103 ＋ 6 平台关注清单。**反例**：`AGI` 在作品语料里 0 命中，却在关注清单里捞出 15 个号（钛媒体AGI / 玄姐聊AGI / 饼干哥哥AGI🍪…）—— 只看作品语料就会漏掉它 |
| **新平台接口字段不全** | B站 `x/relation/followings` **不返回粉丝数**（抖音返回） | 逐字段实测再写脚本；B站由 `x/relation/stat?vmid=` 补（免签名），只补缺失的、二次跑秒过 |
| **用错 Python 解释器** | 转录报 `No module named yt_dlp` | `yt_dlp` / `whisper` **只装在系统 Python313**（`C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe`）；托管解释器什么都没有。脚本应在入口 `find_spec` 自检并明确报错 |
| **bsk 会话不能并发** | 第二个 `evaluate` 报 `previous session command is still running` | 一个 session 一次只跑一条命令；批量脚本要**串行**发指令，别并发调 |
| **`ops_tracker.record()` 漏传 `platform`** | 新平台的条目落库记成 `douyin` | 该函数 `platform` 默认 `douyin`，调用方**必须显式传**；`raw_tracker_record()` 同理（另可传 `method=` 避免记成定义处的文件名） |
| **按「占位标题」丢内容** | 知乎把「转发/分享」类条目塞进 `/articles`，`title` 固定是「分享文章」；实测某博主近 30 天 **4–5 篇**这样，正文却有 1268–5309 字完整干货（「个人注册订阅号还是服务号？」） | **标题是元数据，不能拿来判内容有无**。命中占位词（`分享文章`/`分享`/`文章`/`无标题`/`转发文章`/空）→ 用 `batch_polish_transcripts.derive_title()` 从正文拟题；**再补一层不依赖网络的确定性兜底**（从正文捞首个含 ≥4 汉字的短句截断），因为 `derive_title` 会因超时或 `_clean_title` 校验（≥4 汉字 / ≤30 字 / 无 4 连英文）失败。frontmatter 记 `title_source` 便于追溯 |
| **改完 import 关系不测所有顺序** | `ops_work_filter` 写 `from raw_creator_filter import _hit`，而后者有 `try: from ops_work_filter import OP_STRONG` → 成环，`except Exception` **静默吞掉** ImportError → `PROFILES` 只剩 `ai`，**ops 画像凭空消失**（表现为 `KeyError: 'ops'`）。之前的零回归/冒烟全没抓到，因为探针直接读 `owf.PROFILES`（后导入、执行完整） | ① 共享匹配器下沉到**独立叶子模块**（`word_match.py`），两边都向下依赖 → 断环；② **`except Exception` 兜底分支是掩盖 bug 的温床**，改 import 后必须显式断言所有顺序组合下 `PROFILES` 的 keys 齐全 |
| **`--count` 把「跳过」也算进配额** | 转录脚本超长跳过走 `continue`，而 `todo[:count]` 只排除 `done`、**不排除 `skipped`** → 队首几条全是超长的号，**每轮拿到同样的条目、全跳过、一步不前进**。实测：`吴恩达AI课程研究院` 103 条视频条条 53~100 分钟 → **永远零产出**；`comfyui`（含 430min）、`赛博门外憨`（含 324min）次轮起空转 | 分批跑之前先看**每个号队首几条的时长分布**；`todo` 过滤要**同时排除 `done` 与 `skipped`**（或让 `--count` 只数真正开跑的条目）。**「跑了 N 轮还是 0 条」＝先查这个，别怪网络** |
| **`continue` 顺手吞掉落盘** | 超长分支 `prog["skipped"].append(...); continue` 把循环**底部**的 `prog_path.write_text(...)` 一起跳过了 → 日志 13 条 skip、进度文件里只剩 2 条，**进度文件成了不可信的记录** | 循环里任何 `continue` 前，先确认「状态写盘」是在 `continue` **之前**；跨轮统计以**运行日志**为准，别只信 `.progress.json` |
| **把「归位搬走」误判成丢数据** | ops 线往 `运营中心/_收件箱/videos/<平台>/` 写料，`ops_inbox_sink.py` 会按**内容主题**把它归位到 `运营中心/<平台>/_原文/`（甚至跨平台，如标题含「公众号」→ 归 `公众号/_原文/`）→ 只数收件箱会以为「成功 22 却只落 13 篇」 | 核对落盘数时，**收件箱 ＋ 各平台 `_原文/` ＋ 其他线 `_原文/` 一起数**；`ops_inbox_sink.py --apply` 会留 `move-map.json` 备份，可据此逐条对账 |
| **whisper 一直跑 CPU，怪不到配置头上** | 报 `FP16 is not supported on CPU; using FP32 instead`，1:45/条；查配置全对 | **真因是装了 CPU-only 的 torch**：`python -c "import torch;print(torch.__version__, torch.cuda.is_available())"` → `2.12.0 False`。**判据先看 `torch.cuda.is_available()`，再看配置**。换 `torch==<同版本>+cu126`（`--index-url https://download.pytorch.org/whl/cu126`，版本号要与现装**逐位一致**才是 drop-in）。⚠️ 共享 Python 被多条线共用 → 换之前先报告，并**在隔离 venv 验证 CUDA 后再动生产**；且**必须在无转录进程运行时装**（Windows 下 torch DLL 被占用会 `Access is denied`） |
| **先验手法：`venv --system-site-packages`** | 想验 GPU 又不想装两遍依赖 | `python -m venv --system-site-packages <dir>` → 隔离环境**继承系统站点包**（whisper/numpy 等），只需往里装一个 torch 就能验；`pip install --no-index --find-links <本地轮子目录>` 可完全离线装。**2026-10-02 实测：同一条 5 分钟音频 CPU 232.8s vs GPU 24.0s（≈9.7×）** |
| **放宽「超长」阈值却不先上 GPU** | 把 `--max-duration` 从 30 分钟放到 100 分钟，以为能吃到教程类长视频 | **whisper 耗时 ∝ 音频时长** → 100 分钟视频 CPU 光转录就 ≈78 分钟（GPU ≈8 分钟）。**「放宽阈值」与「上 GPU」必须同批做**，否则等于给自己挖坑。上完 GPU 后瓶颈会转移到 **LLM 整理**那一段（约 2:50/条），下次提速要看那里 |
| **运行时守卫写了两份 → 必然漂移** | 每接一条新线就在脚本里手抄一份「查解释器 + 查 CUDA」→ 改一处漏一处，几条线的判据迟早不一致 | 立**单一真源** `torch_runtime.py`（`check_runtime()`），所有转录入口 `from torch_runtime import check_runtime` 共用；**判据不只看包在不在，必须看 `torch.cuda.is_available()`**（装了 CPU 版 torch 时包也在、但会静默跑 CPU）。默认**醒目告警不阻断**（别让告警把批处理打死），入口另给 `--require-gpu` 让无人值守场景**发现 CPU 直接退出（码 2）** |
| **cron 拉起的任务跑在别的解释器上** | 以为「脚本里写了 Python313」就没事 → 其实 Hermes cron 用 `sys.executable` 拉起 `script=` 任务，解释器＝**hermes venv（CPU torch）**；脚本再 `subprocess` 调转录子进程时若沿用 `sys.executable`，**转录就静默跑 CPU**。最隐蔽，因为父脚本日志一切正常 | 凡**编排器/父进程**拉起转录子进程，**显式传 Python313 绝对路径**（如 `ops_nightly_harvest.transcribe_py()`），**不要用 `sys.executable`**；并让子进程入口自带守卫兜底。查全机 torch 环境：`python -c "import torch;print(torch.__version__, torch.cuda.is_available())"` 逐个解释器跑一遍 |
| **以为 GPU 会把端到端提速 10×** | 单看转录段 CPU→GPU 是 ≈9.7×，就以为整条线快 10 倍 | 实测**端到端只快约 17%** —— whisper 降到秒级后，**LLM 整理（≈2:50/条）成了新绝对大头**。**报收益要报端到端**，并说清瓶颈已转移；要再快得从**整理侧**（批量化/换模型/并发）入手，继续在 GPU 上加码没用 |


## 五、落盘规则速查（口径权威：`规则与权限/智能体共享/07-raw素材层标准.md`）

| | raw 线 | 运营中心线 |
|---|---|---|
| 文章 | `raw/articles/<平台>/{YYYY-MM-DD}-<平台>-{slug≤40}-{作品号}.md` | `运营中心/_收件箱/articles/<平台>/{日期}_{标题}_{作品号}.md` |
| 视频 | `raw/videos/<平台>/...` | `运营中心/_收件箱/videos/<平台>/...` |
| 台账 | `raw/.state/collection_tracker.json` | `运营中心/.state/collection_tracker.json` |

- **作品号必填**（去重主键）；日期＝**采集日**（≠ 发布日，两个字段分别写）。
- frontmatter 必填 6：`title` / `platform` / `media_type` / `author` / `url` / `collected`。
- 文章正文：`## 💡 核心要点` → `## 📄 原文`（图片保留原链接**不下载**）。
- **不要**把两条线互写；不要往 `raw/` 写报告（明面报告落 `raw/_报告/`）。
- **改了脚本，同一次就把工具说明一起改**（`系统脚本工具链/_索引.md` §四「同步义务」是硬规则）。

## 六、收工三写

```bash
python C:\Users\Administrator\Documents\code-news\scripts\handoff_append.py \
  --task WK-<YYYYMMDD>-NN --agent <自己> --status 待审 \
  --did "..." --files "..." --evidence "..." --open "..." --next "..." \
  [--create --title "..." --platform "..."]
```
证据要**可复核**：命令 + 退出码 / 产出文件绝对路径 / md5 / 探针输出。
先查台账拿到正确的下一个 `NN`（别占用别人的号）。

收尾再跑一次：
```bash
python C:\Users\Administrator\Documents\code-news\scripts\check_doc_references.py   # MISSING 必须 0
python C:\Users\Administrator\.hermes\scripts\raw_lint.py --root raw/articles/<平台>  # 不合规必须 0
```

## 七、一条重要经验：源决定上限，代码只决定下限

知乎线代码全通、测试全过，但**运营线产出是 AI 快讯** —— 根因是那 21 个关注博主里**没有运营博主**，
不是代码问题。**新线跑通后一定要看产出的内容对不对口**，别只看「有没有文件落下来」。
发现源不对口时：如实报告 + 给出「先只跑哪条线 / 需要补什么源」的建议，别硬凑。

> ✅ **2026-10-02 补源的正解**：别只建议「去关注运营博主」然后等 —— 直接上 §九 的**甩链接入口**，
> 用户刷到好号甩个链接进来，`--save` 沉淀成长期货源。知乎线就是这么把「运营师兄」接进来的，
> 补完源后 ops 线立刻有对口产出（视频号分发原理 / 公众号新规 / 短视频起号流程）。
> **「源不够」的解法是降低补源的门槛，不是降低产出的标准。**

## 九、「甩链接即采」入口（可复制到任何平台线，2026-10-02 立）

**触发场景**：用户刷到一个好号，直接把主页链接甩过来要采集。**这是高频动作**，
不该逼人先手工造一份临时 JSON 清单。

**错误做法**：另写一个「甩链接专用脚本」。→ **双实现必然漂移**（下游的博主闸 / 作品闸 / 去重 /
落盘 / 台账全要复制一遍）。这个坑刚在「两级闸门两套匹配口径」上吃过。

**正确做法**：给**现有**采集器加三个开关，**下游一个字节都不改**。

```
--url   <链接|url_token>   吃 完整主页链接 / <平台>/<token> 片段 / 裸 token，逗号或空格混排多个
                           给了它就不读 --state，脚本自己拉 profile 组单博主清单
--save                     把拉到的博主按 id 去重**并入关注清单**，之后每日自动采
                           写入时打 来源: "手动链接:YYYY-MM-DD" 标记，与「真关注来的」可区分
--force                    闸门没过也照采。**只在 --url 入口生效**，关注清单入口提示「已忽略」
```

**四个必须做对的地方**：

1. **产出同构 block**。`fetch_profile()` 必须返回与关注清单**同构**的字段
   （`sec` / `nick` / `headline` / `fans` / `ans` / `art` / `works`）—— 这是「下游零改动」的前提。
2. **`--force` 必须受限**。词表永远有覆盖不到的时候，但「绕过闸门」这个口子只能开给
   **用户明确点名的号**。若不加限制，一次误用就把整份关注清单几十个号全硬采了。
3. **闸门没过要摆判词**。逐个号打印「昵称 / 简介 / 判词 / 原因」再 `exit 2`，**不静默丢**。
   并提示「确认要采就加 `--force`，或换 `--profile`」。
4. **bsk 会话改懒启动**。甩链接入口要**先用会话拉 profile**，所以会话启动不能再固定在「闸门之后」。
   抽一对 `ensure_session()` / `stop_session()`，各退出路径都要 `stop_session()`。
   （顺带好处：所有网络取数都在 LLM 之前跑完，**避开 bsk session 约 20 分钟过期**的问题。）

**并入关注清单的保号前提**：清单采集器必须**按 id 预载旧条目再写回**（知乎 `zhihu_following_collect.py`
第 70-80 行就是），否则下次全量重拉会把手动条目冲掉。仍要留 `来源` 字段，
因为**整个清单文件被删掉重拉时手动条目会丢** —— 那时靠 `来源` grep 补齐。

**实测**（`zhihu_creator_collect.py`，2026-10-02）：甩链接 → profile → 博主闸「候选」→ `--save` 并入清单
（21 真关注 ＋ 1 手工 = 22）→ 近 30 天 23 篇 → 过闸去重 21 篇。全程无手工 JSON。

## 八、四条线的入口形态（实测速查 · 接新平台前先对号）

| 平台 | 关注清单怎么来 | 「按博主列作品」 | 转录 / 取正文 | 实测日期 |
|---|---|---|---|---|
| 抖音 | bsk ＋ `following/list`（免签名，**带** fans/works） | ✅ `ops_douyin_list_videos.py`（免签名） | 本地 Whisper / RedFox | 2026-09-29 |
| 视频号 | UIA 读微信 PC 端「关注」页 | ❌ RedFox 无该接口（10 个端点全空） | `channels_transcribe_local.py`（直链 mp4） | 2026-10-01 |
| 公众号 | UIA 读微信 PC 端「关注」 | ✅ `gzhData/queryWorkList` | 免转录（正文即文本） | 2026-10-01 |
| 知乎 | bsk ＋ `members/<token>/followees` | ✅ 回答＋文章接口 | 免转录（正文即 HTML） | 2026-10-01 |
| **B站** | bsk ＋ `x/relation/followings`（免签名，**无** fans，须补） | ✅ `x/space/wbi/arc/search` —— **必须 wbi 签名** | 本地 Whisper（`bilibili_transcribe_local.py`） | 2026-10-02 |

**两条判断法则**：
1. **「关注清单」几乎都拿得到**（bsk 复用登录态 / UIA 读客户端），别在这步卡住。
2. **真正的分水岭是「能不能按博主列作品」**：
   拿不到 → 退回**关键词制**（视频号）；拿得到 → 照抖音的**博主制**（B站 / 公众号 / 知乎）。
3. **签名门槛先探再写**：B站 `x/space/wbi/*` 系列要 wbi 签名（自算即可，见 `bili_wbi.py`），
   但**同平台的 `x/relation/*`、`x/v3/fav/*` 免签名** —— 别一看到风控就以为整条线走不通。
