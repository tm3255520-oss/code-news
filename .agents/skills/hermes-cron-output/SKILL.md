---
name: hermes-cron-output
description: 给 Obsidian 自媒体中枢挂一个新的「周期性产出」（每日清单 / 日报 / 周报 / 体检），由 Hermes cron 驱动。当用户说「每天给我一份 XX 汇总」「做个每日清单」「挂个定时产出」「每天点开看 XX 有多少」时使用。含判据选择纪律（契约字段 vs 文件 mtime）、cron 注册范式（薄包装 + no_agent 静默语义 + HERMES_HOME 影子 home 坑）、行尾基准判定、登记点清单与收工三写。
agent_created: true
version: 1.0.0
tags: [hermes, cron, vault, 定时产出, 清单, 日报]
---

# 给中枢挂一个周期性产出（hermes-cron-output）

> 为什么有这份：2026-10-04 做「每日投料清单」时，从需求到上线走了 40+ 步，
> 其中**判据选错会直接产出假数据**、**cron 注册有影子 home 坑**、**行尾基准要读字节**这几条都不是能凭直觉蒙对的。
> 本文把动作与坑一次固化。首个实例见 `系统中枢/运行小结/系统与配置/2026-10-04-投料清单脚本上线-运行小结.md`。

## 一、动手前（不许跳）

```bash
# 1) 开工三查
python C:\Users\Administrator\Documents\code-news\scripts\work_lookup.py "<主题关键词>"
#    命中「进行中」且非自己 → 不重复开工；命中「已完成」→ 复用产出

# 2) 复用盘点（守则 §4 硬规则）
python C:\Users\Administrator\Documents\code-news\scripts\tool_inventory.py <关键词>
#    结论按 ①直接调用 / ②扩展合并 / ③新建 三选一，并在提交信息里写明
```

**先读同族脚本**。同类产物一定已经有脚本在写（实例：`raw_lint.py` 已在扫 `raw/` 并读 `collected`、
`account_dashboard.py` 已是「读多源 → 汇成一页」的范式）。复用它的**判据与解析口径**，
别自己另写一套 —— 否则同目录两个脚本对同一份数据给出两种结论。

## 二、定判据（本 skill 的核心，选错就产出假数据）

### 🔴 铁律：绝不用文件 mtime 做时间判据

`mtime` 会被**归一化 / 搬运 / 归位 / 重写**改掉。实测（2026-10-04）：

| 口径 | 2026-10-01 的 raw 文件数 |
|---|---|
| 文件 mtime | **253** |
| frontmatter `collected` | **15** |

元凶是每日 cron「raw文章体例归一-每日」重写文件。**用 mtime 做日报 = 报假数。**

**正解**：用 vault 已定的 **frontmatter 契约字段**（`raw_lint.py` 的必填清单：`title/platform/media_type/author/url/collected`）。
动手前**先验证覆盖率**：

```python
# 扫一遍目标目录，统计 collected 覆盖率；低于 ~95% 就要找兜底（文件名前缀日期）
```

### 多入口时，先搞清每个入口的「形态」

形态不同 → 取数逻辑不能一套通用。实例（两个投料口）：

| | `raw/` | `运营中心/_收件箱/` |
|---|---|---|
| 形态 | **仓库**（纪律「只进不出」） | **漏斗**（加工后归位到 `平台/_原文/`） |
| 实测 | 421 个 md 累积着 | **只剩 5 个文件**，历史全被搬走 |
| 后果 | 扫目录能看全历史 | **扫目录只能看到「还剩多少」** → 必须同时扫归位后的 `_原文/` |

### 台账 vs 文件系统，谁是权威？

**先对账，再选**。实例：raw 台账 388 条 vs 实际 421 个文件；运营中心台账 331 条 vs 收件箱仅 5 个文件。
台账时间戳还可能是**批量回填的**（`ops_tracker.py --sync` 写的是当时时间，不是真实采集时间）。
→ **文件系统 + 契约字段更可信**，台账只作辅助（去重、状态）。

## 三、写脚本

```python
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from vault_paths import RAW, OPS_CENTER      # 路径一律走 vault_paths，不硬编码
```

- **判据与同族脚本同口径**：frontmatter 解析（`FM_RE` / `fm_field`）直接照 `raw_lint.py` 抄，别自创
- **幂等靠全量重算**，不靠增量追加：每次重新生成整份产物（数据源是文件系统，扫一遍很快）→ 天然幂等，重复跑无害
- **加 `--quiet`** 供 cron 用（见 §五 静默语义）
- **行尾显式指定**，且在源码里**运行时构造** `CRLF = chr(13) + chr(10)`，不写 `\r\n` 转义字面量（写入工具会规范化转义序列）

## 四、干跑验证（写进 vault 前必须做）

```bash
python <脚本> --dry-run          # 只打印统计
python <脚本> --month 2026-09    # 先只跑一个月看格式
```

1. **产物格式**用 Read 看一眼（截断长度、分组层级是否可读）
2. **行尾按字节复核**（判据只用 Python 读字节，`grep -c $'\r'` 在 Git Bash 下对纯 LF 也报「全含 CR」，不可用）：

```python
raw = p.read_bytes(); nl = raw.count(b"\n"); crlf = raw.count(b"\r\n")
# 纯 CRLF: crlf == nl；纯 LF: crlf == 0；否则 MIXED 需归一
```

3. **行尾基准 = 同族产物**，不是「目录多数」。实例：`raw/_报告/` 下 LF 10 / CRLF 14 本就不统一，
   而 `raw_lint.py`（同族脚本，用 `write_text`）产出的最新报告是 **CRLF** → 取 CRLF。
   **新建目录无同族时**，看同层脚本产物的实际字节，不看文档结论。
4. **复读磁盘自证**：改完用脚本重新从磁盘读关键串，别只信工具的成功回执

## 五、注册 cron

### 范式：薄包装 + 注册器（照抄现有）

```
~/.hermes/scripts/<name>.py          # 主实现
~/.hermes/scripts/<name>_cron.py     # 薄包装：subprocess 调主脚本，转发 stdout
~/.hermes/scripts/register_<name>_cron.py   # 注册器，用 create_job()
```

```python
sys.path.insert(0, r"C:\Users\Administrator\.hermes\hermes-agent")
from cron.jobs import create_job
create_job(prompt="...", schedule="0 6 * * *", name="<任务名>",
           script="<name>_cron.py", no_agent=True, deliver="local")
```

**跑注册器必须用带 croniter 的 venv python**：`~/.hermes/hermes-agent/venv/Scripts/python.exe`

### 🔴 三个坑

1. **HERMES_HOME 影子 home**：若 `HERMES_HOME` 没指向 `C:\Users\Administrator\.hermes`，
   job 会写进 `%LOCALAPPDATA%\hermes`（影子 home，**空的 cron/**）→ **任务创建成功但永不触发**。
   注册前先 `echo $HERMES_HOME` 确认；不确定就用 `~/.hermes/bin/hcron.cmd`（它内部钉死 HERMES_HOME）。
2. **`no_agent=True` 的 stdout 会被直接交付**（verbatim）→ 想「成功即静默」就在包装脚本里只在失败时输出，
   主脚本加 `--quiet`。参照 `cron_watchdog.py` 的语义。
3. **注册后必须验证**，`jobs.json` 里的 `next_run` 可能是 null（运行时才算）：
   ```bash
   cmd //c "C:\Users\Administrator\.hermes\bin\hcron.cmd cron list" | grep -A6 "<任务名>"
   # 要看到 [active] / Next run: <真实时间> / Mode: no-agent
   ```

**排期位置**：挂在**上游跑完之后**，留余量。实例：凌晨采集 04:00–04:55 → 清单 06:00。

## 六、登记（「一处改动要在 N 处登记」）

| 登记点 | 说明 |
|---|---|
| 相关**索引** | 新增目录/产物要回改索引页（如 `raw/_索引.md` 的目录表），并更新其 `updated` 字段 |
| `技能变更日志.md` | `系统中枢/规则与权限/智能体共享/`，7 列表格（日期/技能名/主实现路径/变更类型/变更原因/影响 Agent/验证结果），**最新在最下**，行尾 **LF** |
| **运行小结** | `系统中枢/运行小结/<6分类>/YYYY-MM-DD-<主题>-运行小结.md`，**系统运行环节强制落盘** |
| `code-news/config/tool_registry.json` | ⚠️ **看 scope 再决定**：该表明文排除「基础设施/运维任务（日志轮转、健康巡检、vault 同步、git 留痕…）」——**定时产出类不登记**，其调度真相以 `jobs.json` 为准 |
| 协同三件套 | 见 §七 |

## 七、收工三写

```bash
python C:\Users\Administrator\Documents\code-news\scripts\handoff_append.py \
  --task WK-YYYYMMDD-NN --agent <自己> --status 已完成 \
  --title "<标题>" --platform "<平台/形态>" \
  --did "<一句话结果>" --evidence "<路径 / 命令+退出码>" \
  --files "<逗号分隔路径>" --open "<未决问题>" --next "<下一步>" \
  --create --dry-run        # 先 dry-run，确认无误再去掉
```

- **任务 ID 先查重**：`grep "WK-<今天>" 任务台账.md` —— 撞号时 `--create` **不报错**而静默走「更新」分支，
  会把别人的行覆盖掉（台账里已有两次事故记录）
- 协同区三个文件（台账 / 交接 / 会话索引）由脚本写入，**行尾是 CRLF**，别按治理区 LF 归一

## 八、踩坑速查

| 坑 | 判据 |
|---|---|
| mtime 当时间 | 先跑「按 mtime 计日 vs 按契约字段计日」两组数，差异大 = 有归一/搬运在改 mtime |
| 只看收件箱 | 若该目录有「加工后搬走」的下游，收件箱只反映残量；同时扫归位目录 |
| 台账当权威 | 先对账（台账条数 vs 文件数），不等就信文件系统 |
| 行尾写错 | 按字节读同族产物，不读文档结论；`grep` 判行尾不可用 |
| cron 不触发 | 先查 HERMES_HOME 是不是影子 home |
| 每天被推送刷屏 | `no_agent` 的 stdout 会直交付 → 成功即静默 |
| `--create` 撞号 | 静默覆盖他人台账行；先 grep 查重 |
| 标题过长 | 视频平台标题常带 hashtag，清单要截断（如 60 字），做成可调常量 |
| **cron 跑必败、手动跑必成** | 先查 **`PYTHONPATH`**：cron 会注入指向 hermes venv site-packages 的 PYTHONPATH；子进程若用**另一个 Python 版本**，会去加载错版本的 C 扩展（实测 2026-10-04：Python313 加载 venv 的 torch → `WinError 126 ... torch_python.dll` → 0 秒退出码 1）。修法：`env = dict(os.environ); env.pop("PYTHONPATH", None)` 再传 `subprocess` |
| **只看到「退出码 1」看不到原因** | 包装脚本常把子进程 stdout+stderr 吞掉。写个**诊断包装**（同样的调用 + `capture_output=True`，把 stdout/stderr 打出来），挂成 cron 跑一次即可见真报错 —— 比猜快十倍 |
| **`hcron cron run` 任务半途夭折** | 该命令让 owner 进程等着；owner 若被信号带走，任务状态变 `unknown`、子进程一起死。改用「把 once job 的 `run_at` 设到 1–2 分钟后，让调度器自然触发」（`source=builtin`），更稳 |
| 浏览器类采集起不来 | **两层**：① daemon 没跑（`bsk daemon start`；沙箱内起不了 detached 进程，需用户在独立终端手动）② **扩展没连 daemon**（`bsk doctor` 看 `extension connected`）——扩展是「浏览器主动连 daemon」，daemon 活着但没浏览器连上也白搭；扩展装在哪个 Chrome profile，就得用那个 profile 开浏览器 |
| **长任务跑到第 60 分钟突然死了** | cron 有 **1 小时脚本硬超时**（`hermes-agent/cron/scheduler.py: _DEFAULT_SCRIPT_TIMEOUT = 3600`），报 `Script timed out after 3600s`。**它不在你的脚本里，是调度器层面的闸**，脚本自设的 `timeout` 管不着。长任务要**分片**（每片留余量，如 45 分钟）＋确认上游脚本支持断点续传；也可用 `HERMES_CRON_SCRIPT_TIMEOUT` / 配置 `script_timeout_seconds` 覆盖，但那要动全局并重启 gateway |
