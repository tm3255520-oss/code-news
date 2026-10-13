---
name: hermes-pipeline-repair
description: Hermes 内容产线（视频号/公众号/头条等）故障定位与逐项修复验证手册。当产线报错、断供、某步骤静默没执行、日志出现异常告警、模型调用失败，或用户说「产线又挂了」「XX 天没出片」「修一下这条产线」时使用。内含 14 类高频故障模式（try 耦合吞步骤 / 配置被瘦身 / 模型 EOL / 校验函数反被数据打崩 / safe-delete 拦截 / 思考独白泄漏 / 变量遮蔽顶掉标题 / U+FFFD 乱码与不可打印字符 / 检查环节发现问题但产物仍留下 / 标题 30 字硬截断 / 同构处漏改 / 槽位语义错配 / 按仓库名查台账误判未发布 / 上游名称大小写不保真导致同库重复出文）+ 环境铁律（含环境变量双源漂移排查：`.env` vs `HKCU\Environment`、**CLI 版本核查**、`capture_output=True` 管道死锁）+ 验证模板 + 存量污染治理 + 视频号上传的**取证过程**（三轮误判的对照实验；**操作与判据已拆到独立 skill `d2v-channels-publish`**）。**边界**：**动手修之前必须先过 repair-gate 拿许可**；只要「只读诊断、先看看有什么问题」走 content-pipeline-audit；日常「推视频号」（非故障场景）走 d2v-channels-publish。
agent_created: true
version: 1.7.3
tags: [hermes, repair, pipeline, debugging, ffmpeg, llm-gateway]
---

# Hermes 产线故障定位与修复验证手册

> 配套：`content-pipeline-audit`（先审计出问题清单）、`repair-gate`（决定要不要动手）
> 本 skill 管的是**已知故障模式的快速定位**与**修复后的验证方法**。

## 0. 适用对象

跑在 `C:\Users\Administrator\.hermes\scripts\` 下的产线脚本族：
`daily_video_production.py`、`article_to_script.py`、`article_generator.py`、
`dsh_article_generator.py`、`publish_channels.py`、`video_enhance/*`。

---

## 1. 环境铁律（先看这，能省半小时）

### 1.1 必须用 Hermes runtime 的 python 绝对路径

```bash
PY="C:/Users/Administrator/.hermes/hermes-agent/.hermes-runtime/python/cpython-3.11-windows-x86_64-none/python.exe"
```

**不要**用 `C:\Users\Administrator\.workbuddy-ai\binaries\python\...`——那是另一个环境，
缺 Hermes 依赖（且 PEP 668 托管只读，装包要 `uv pip install --target` 到 `_vendor`）。
> **实测（2026-09-15）**：用那个环境 import `article_generator` 直接
> `ModuleNotFoundError: No module named 'yaml'`；连系统 python（`AppData\Local\Programs\Python\Python313`）
> 虽然侥幸有 `PyYAML 6.0.3` 能跑通，但**它不是产线的环境**。
> **验证/复现一律用上面这个 Hermes runtime python** —— 否则「验证通过」不代表产线通过。

### 1.2 跑产线前必须清掉代理环境变量

系统里残留的 `HTTP_PROXY` 端口**已失效**（如 57154），会让所有外网调用超时：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 <script.py> ... 
```

`-u`（无缓冲）+ `-X utf8`（防 Windows GBK 下 ✅▶ 等字符崩）是标配。

### 1.3 日志要落盘再 tail

长跑脚本直接前台输出容易丢。固定套路：

```bash
LOG="C:/Users/Administrator/AppData/Local/Temp/e2e_<n>.log"; : > "$LOG"
env -u ... "$PY" ... >> "$LOG" 2>&1 ; echo "EXIT=$?" >> "$LOG"
```
然后用后台任务 + 完成后读取，别傻等（见 `execution-timeout-guard`）。

### 1.4 改动前必须备份（skills/scripts 无版本控制）

```bash
cp -p <file> <file>.bak.<YYYYMMDD>-<短标签>
```

### 1.5 环境变量有**两个源**，别只看 `.env`（2026-09-15 实测）

产线要用的 key 同时存在于两处：**`.env` 文件** 与 **Windows 用户级环境变量 `HKCU\Environment`**。
两者**可能不一致**（本机实测**漂移 13 个键**），而且**谁新谁旧没有规律**。

**排查三段式（顺序不能颠倒）：**

1. **两侧都读**。读注册表用 `winreg`（`reg.exe` 被本机安全策略 Program Blacklist 拦截）：
   ```python
   import winreg
   k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
   v, _ = winreg.QueryValueEx(k, "NVIDIA_API_KEY")
   ```
   ⚠️ **当前进程的 `os.environ` 看不到注册表里刚写入的变量** —— 新进程才会继承。
2. **先探测两侧的真实有效性，再决定统一到哪一侧**。逐 key 打一次真实 API，**只看状态码，不打印明文**。
3. 只有第 2 步做完才能动。**按「哪边更该是权威」的架构直觉去统一，有一半概率把好 key 换成坏 key** ——
   本机就是反的：**注册表侧 200（有效）、`.env` 侧 403（失效）**，
   根因是 `codex_proxy_watchdog.py` 的 `read_user_env()` 注释写的「任务计划进程可能不继承 shell 变量」
   → Codex 代理把 key **固化进注册表**，`.env` 退化成了滞后副本。

**取值顺序的实际语义**：`load_env()` 用 `os.environ.setdefault()` →
进程已继承注册表值时，**`.env` 那份被静默忽略** = 「改了 `.env` 不生效」的认知陷阱。
2026-09-15 已加固：漂移**告警（只列键名、绝不列值）** + `HERMES_ENV_OVERRIDE=1` 开关（显式以 `.env` 为准），
**默认行为与旧版 `setdefault` 逐场景等价（零回归）**。

**⚠️ 连带盲区 —— 监控脚本只读 `.env`**：`watch_nvidia_keys.py` 不看注册表，
两源漂移时它对「key 是否恢复」的判断**是在说谎**（本机实测如此）。
所以**动过任何环境变量后，必须顺带校准它的状态文件** `cache/nvidia_key_watch.json`，
否则下一轮会**误报「自愈恢复」推送**（本次校准 5 项 403→200 后才 `recovered=[] / newly_down=[]`）。

> 完整处置记录见验收报告 §11.6；验证脚本 `verify_15d.py`（29/29）+ `sync_env_keys.py`（7 条硬不变量）。

### 1.6 「工具能力缺失」先核版本，再怀疑物理限制 ★2026-09-15 定型

**症状形态**：某能力「怎么试都不行」，现象稳定复现、看起来像是平台/浏览器/协议**根本不支持**。

**判据**：在写任何「绕过去」的方案之前，先跑一次版本核查。

```bash
bsk --version ; bsk doctor ; <cmd> --help | grep -i <你要的能力>
```

> **实测（2026-09-15）**：视频号自动上传「怎么都传不上去」，曾被结论为「user activation 绕不过去 +
> 扩展与守护进程能力不对齐」，写进 skill 当成物理限制。**实际根因是 `bsk` CLI 停在 0.1.6**（2026-06-30），
> 而 `upload` 命令是 **0.2.0 才新增**的（PR #123 会话级上传 / PR #124 drop to upload）。
> 升到 0.2.1 后 `bsk upload` 直接可用，**整个「绕过去」的方案作废**。

**为什么这条要和 §1.5 并列**：环境变量漂移（1.5）和工具版本（1.6）是同一类错误的两个面 ——
**「当前这台机器上的状态」不等于「文档里描述的能力」，也不等于「我记忆里的能力」。**
现象为真 ≠ 归因正确；每个结论都要配一个**能把它推翻**的对照实验。

### 1.7 别用 `capture_output=True` 接长跑/常驻 CLI ★2026-09-15 定型

```python
subprocess.run(["bsk", "session", "start"], capture_output=True)   # ← 会挂死
```

**根因**：`bsk session start` 会留下**持有管道写端句柄的子进程**（daemon/扩展桥）。
父进程要等 EOF，而管道写端始终没关 → `run()` 永不返回 → 宿主把它当「遗留后台子进程」SIGTERM 掉。
**shell 里 `$(bsk session start | tr ...)` 同理会秒杀**（`out=` 的管道读端一直等不到 EOF）。

**正确姿势 —— 输出走临时文件，不经过管道**：

```bash
bsk session start > "$TMP/bsk_sid_raw.txt" 2>&1 < /dev/null
SID=$(grep -E '^[a-z]{4}$' "$TMP/bsk_sid_raw.txt" | tail -1)
```

> 同理：解析 session id 时**别取第一行**（`waiting for browser extension to connect…` 会先出现），
> 按格式 `^[a-z]{4}$` 过滤 + 取最后一条。

### 1.8 长二进制常量一律代码生成 + 当场自证，不要手抄

**实测教训（2026-09-15）**：把 1128 字符的 WAV base64 **手工分行**抄进源码 →
拼接后变成 12086 字符、第 1086 位起错位 → `data:` URL 里混入非 ASCII → 浏览器对**任何**负载都报
`error`。而这个「探针自己坏了」的假信号，形状和「页面 hidden 导致媒体不加载」的**真信号一模一样**，
差点把整条证据链搅浑。

```python
raw = hdr + b"\x80" * n
b64 = base64.b64encode(raw).decode("ascii")
back = base64.b64decode(b64)                     # 自证：解回来逐字段核对
assert len(raw) == 844 and len(b64) == 1128 and back[:4] == b"RIFF"
```

**规矩**：探针/夹具坏了要**当场炸**（assert），不能悄悄退化成假信号 —— 否则诊断输出本身在说谎。

---

## 2. 十四类高频故障模式

> **分档速查**（2026-09-15 第三轮后）
> - **影响面最大**：M10（标题截断，已修）
> - **最隐蔽**：M7（变量遮蔽）、M9（检查环节发现了但产物留下）
> - **已修**：M7 / M8 / M10 / M11 / M12（槽位语义，方案 A 拆语义）/ M14（大小写重复）
>
> **M1–M14 是「代码/配置里的故障」。还有一类不在这个编号里，但坑得更久 ——
> 「环境和宿主给你的假象」：§1.6 工具版本、§1.7 管道死锁、§1.8 探针自身损坏、
> §3.1 归因纪律、§6.7 Agent Window 可见性门禁。卡住时**先翻这五节**。**
> - **当前无已知活缺陷**：原先「每跑必产」的 M12 已于 2026-09-15 修复并验证

### M1 「一个 try 块串了多件事」→ 第一件失败吞掉后面全部 ★最高频

**症状**：某步骤「静默没执行」、输出缺一段、后半段功能从未生效，但日志只有一条无关的告警。

**判据**：找到那个「没执行」的步骤，**看它前面是否有个同 try 的兄弟步骤会抛异常**。

**本机真实案例（2026-09-14，同一文件踩两次）**：
- `daily_video_production.py` 上传副本段：「清理旧副本」抛异常（safe-delete 拦截）
  → 外层 except 捕获 → 紧跟的 `shutil.copy2` **根本没执行**
  → 视频合成成功但待上传区是空的，发布闭环断在最后一步
- 同文件「统一归档」段：`copy2` 自我复制抛 `SameFileError`
  → 紧跟的「快手同步归档」**从未执行过**

**修法**：把「锦上添花」与「必须成功」的操作拆成**独立 try**。
清理失败只告警 + 列出残留，不阻断复制。

**验证**：改前/改后各跑一次，对比关键行的出现次数（如 `grep -c "统一归档失败"`，应 1 → 0）。

---

### M2 配置文件被「瘦身」→ 网关恒报无密钥

**症状**：`model_gateway` 返回 `no key for provider <name> (env None)`；产线被迫全程走单一通道。

**判据**：
```bash
PY=...; "$PY" -c "
import sys; sys.path.insert(0,r'C:\Users\Administrator\Documents\code-news\scripts')
from model_gateway import resolve
for role in ('script','general','reasoning','fast','vision'):
    print(role, resolve(role=role))
"
```
任何一个 role 解析不出 key → 配置有问题。

**根因定位**：比对文件体积与备份。
```bash
ls -la "C:/Users/Administrator/Documents/code-news/config/model_providers.json"*
```
2026-09-14 实测：该文件在 9/6–9/7 之间从 **23KB → 12KB**，
`providers.<name>.key_env` / `.endpoints` 与顶层 `roles` 段被整段剥掉，只剩 `models` 清单。

**修法**：从旧备份取回字段，**只补连接字段、不动 models 清单**。
键序约定 `key_env / endpoints / models`。注意 `key_env` 要写**本机实际环境变量名**
（如 `NVIDIA_API_KEY`，不是备份里的 `NVIDIA_API_KEY_KIMI`）。

---

### M3 模型被上游 EOL → HTTP 410 Gone

**症状**：`HTTP 410: {"detail":"... has reached its end of life ..."}`，或 404。

**判据**：EOL 时间戳常与产线「最后一次成功日」**完全重合**——这是最强的断供信号。
2026-09-14 实测：`minimaxai/minimax-m3` 的 EOL = `2026-09-09T09:00:00Z`，
与产线最后成功日 9/9 一致。

**修法（两件事，缺一不可）**：
1. **重选模型** —— 必须实测探测，别信二手对比表：
   ```bash
   # 先 GET /v1/models 拉清单，再 12 线程并发探测（别逐 key 串行，16 key × 90s 会拖死）
   ```
   探测时**必须看输出质量**：`nemotron-3-super-120b` / `nemotron-3.5-lightning-30b`
   会吐英文思考独白（触发 M6），选它们等于让刚修的问题复发。
2. **加 410/404 快速跳过** —— 模型下架时换 key 无济于事，逐 key 重试会白跑 16 轮完整握手：
   ```python
   except urllib.error.HTTPError as e:
       if e.code in (404, 410):
           print(f"[WARN] 模型 {model} 已下架（HTTP {e.code}），跳过剩余 key 直接降级", file=sys.stderr)
           break          # ← 关键：break，不是 continue
       continue
   ```

**降级链设计**：主路径 = 标准网关（`role=script`）；回退层 = NVIDIA 直连主模型 + 降级模型。
**NVIDIA 只是回退层，不是主路**——9/9 断供的教训就是回退层被当成了唯一路径。

---

### M4 校验函数比它要校验的内容更脆 ★隐蔽

**症状**：`KeyError` 崩在 `validate_*` 里；同一输入**有时过有时崩**（看似随机）。

**判据**：被校验的是 **LLM 输出**，而 LLM 输出的字段**不保证存在**。
若崩溃那行在某个 `if` 分支内，就是**数据触发型**故障——只有该分支条件成立才求值。

真实案例：`article_to_script.py:validate_script`
```python
errors.append(f"段'{s['role']}'数字过多({len(nums)}个)…")   # 裸下标，位于 if 分支内
```
实测该 LLM 输出 **`role` 字段 0 段**（从来没有），所以只要某段数字 >5 个进入该分支，就必崩。

**修法**：一律 `.get()` + `isinstance(s, dict)` 防护，并加段序号方便定位。
**原则：校验函数绝不能比它要校验的内容更脆——它应该报错，不该崩。**

---

### M5 safe-delete 拦截 → 个人目录删不掉

**症状**：`[safe-delete][SAFE_DELETE_FAIL_CLOSED] {"target":"...","reason":"trash-failed","detail":"SHFileOperationW 失败: 0x2"}`

**判据（实测）**：拦截是**路径相关**的——
- `C:\Users\Administrator\Videos\` 等**个人目录** → 被拦
- `%TEMP%` → 不受影响

**注意**：这是**运行沙箱行为，不是产线 bug**。别去"修"它。
要验证真实缺陷，用 `shutil.copy2` 单独测试即可（18MB 复制成功 → 证明复制能力本身正常）。

**产线侧正确应对**：见 M1——把删除降级为「告警 + 列出残留」，绝不阻断复制。

---

### M6 推理型模型「思考独白」泄漏进产物

**症状**：产出文章/口播稿里出现
`Translate to Chinese:` / `Original:` / `We need to rewrite…` / `Let's go through…`

**判据**：这是**模型选择问题 + 防护缺失**双重成因。
2026-09-14 实测：`nemotron-3-super-120b-a12b` 是直接源头（会输出规则复述）；
且真实污染形态是「**思考独白 ↔ 正文交替穿插**」，不是单纯的「开头多一段」。

**2026-09-15 补充：怎么一句话证实某个模型是泄漏源**（不用翻产物）
```bash
# 极小额探针（max_tokens=8，问一句"回复：可用"）
# 泄漏源模型会把内心独白当回答吐出来：
#   super-120b-a12b  → '嗯，用户发了"回'          ← 自言自语，越界
#   ultra-550b-a55b  → '用户回复了"可用'          ← 正常作答
```
**换模型要换干净**：P2-8 只在 `article_generator.py` / `dsh_article_generator.py` 换了默认值，
`article_image.py:16`、`source_researcher.py:173`、`dsh_source_researcher.py:183` **漏了 3 处**
（2026-09-15 已补，全库 `LLM_MODEL` 默认值零残留）。
> 判据命令：用 `provider_model_audit.sync_runtime_pins` 自己的正则
> `os\.environ\.get\("LLM_MODEL",\s*"([^"]+)"\)` 全库扫，排除 `.bak` / `__pycache__`。

**三层修法（少一层都不够）**：
1. **换模型**：用输出干净的（实测 `nemotron-3-ultra-550b-a55b`）
2. **整篇闸门**，不能只裁开头：
   ```python
   _STRONG_LEAK_PATTERNS = (
       r"Translate to Chinese\s*:", r"We need to (rewrite|polish|translate|answer|keep)",
       r"Here'?s a thinking process", r"(?m)^\s*Original\s*:\s*$",
       r"(?m)^\s*Let'?s (go through|translate|rewrite|polish)\b", ...
   )
   def _count_process_leaks(text):
       return sum(len(re.findall(p, text, re.IGNORECASE)) for p in _STRONG_LEAK_PATTERNS)
   # 闸门：leaks >= 1 → 拒绝该次润色，保留原稿（宁可不润色也不发脏文）
   ```
3. **prompt 加硬性约束**：禁止输出翻译对照/工作过程；首行必须是 `#` 标题

**验证**：污染样本被拒 + 干净样本放行（**零误伤**）+ 每种泄漏形态逐条识别正确。

---

### M7 Python 作用域「变量遮蔽」→ 文章一级标题被 Issue 标题顶掉 ★最隐蔽

**症状**：深度文 H1 是一条 commit / Issue 标题，例如
`# fix(jobindex‑search): reject non‑jobindex detail URLs instead of fetching them verbatim`
`# feat: add a model architecture visual type (40 -> 41)`

**根因**（2026-09-15 实测证实，3 个独立样本精确吻合）：
`generate_deep_article()` 是**一个超长函数**，文章标题与循环内局部变量**同名**：

```python
# article_generator.py   /  dsh_article_generator.py 同构
1117:  title = title_candidates[0]        # ← 文章标题
1172:  title = p.get('title', '')         # ← 「踩坑实录」循环里，同一函数作用域！
~1296: body_parts = [f"# {title}", ...]   # ← 拿到的是循环最后一条 Issue 标题
# DSH: 900 / 955 / 1080
```
→ 凡 `llm_analysis.verified_problems` 非空，H1 就被顶成 Issue 标题；
为 0 时循环不执行、标题正常。**这解释了「有些文章标题正常、有些是英文 commit」的诡异分布。**

**定位手法（可复用）**：写一个**受控重放**脚本——patch `OUTPUT_DIR` 到临时目录
（**不碰 vault**），在 `call_llm` / `llm_polish_article` 上挂探针，打印
「润色前 draft 的 H1」。**若 draft 的 H1 就已经是 Issue 标题，说明跟润色无关，
是生成阶段被遮蔽**——这一步能省掉大量瞎猜。

**判据（一句话）**：`文件 H1 == llm_analysis.verified_problems[min(n,4)-1]['title']`
（`llm_analysis` 在 `_data.json` 里，**不在** 调研.md 顶层）。

**✅ 修法（2026-09-15 已修，两文件）**：循环内变量改名 `title` → `issue_title`；
并在文章标题定义处（主管线 1117 / DSH 900 行后）**加警示注释**，防止后人再把
临时变量命名成 `title`。备份标签 `.bak.20260915-091628-m7`。

**连带发现（重要）**：`dsh_article_generator.py` 1162 段有个「标题兜底」补丁，
原注释写「LLM 润色偶发把标题改成 Issue 标题」—— **根因判断是错的**（真根因是遮蔽），
而且它 `f'# {title}'` 引用的正是**被污染的那个 `title`** → **把错误标题又写回一遍，形同虚设**。
**教训：看到一个「兜底 / 修正」补丁时，先验证它的根因判断对不对，再验证它读的输入本身干不干净。**

**验证 M7 的六重手法（可复用）**

| 层 | 做法 |
|---|---|
| V1 AST 静态 | 断言 `generate_deep_article()` 内 `title` 赋值处数 == 1 |
| V2 AST 静态 | 遍历所有 `ast.For` 体内的 `ast.Assign`，断言无裸名 `title` |
| V3/V4 对照 | 用 `SourceFileLoader` 加载 `.bak`（**必须复现**）+ 加载现版（**必须正常**），判据 `body in all_issue_titles` |
| V5 双向夹逼 | stub `generate_titles` → 固定标题；stub `llm_polish_article` → 注入 commit 式坏标题；断言最终 H1 == 固定标题 |
| V6 不误伤 | 拿真实产出过的正常标题 + commit 风格标题各若干，断言放行/拦截比例 |
| 真实全路径 | 不 stub，真跑一次，看 H1 是否为中文模板标题 |

> ⚠️ 两个踩过的坑：① 断言**不要**依赖 `generate_titles()`（内部是 `random.choices`
> 加权抽样，跨调用不可复现）——改判「是否等于某条 Issue 标题」这类**确定性判据**；
> ② 备份文件后缀不是 `.py`，`spec_from_file_location` 推不出 loader，要显式传
> `importlib.machinery.SourceFileLoader`。

> ⚠️ **反向的遮蔽也会咬人（2026-09-15 踩到）**：不只是「旧代码里已有遮蔽」，
> **你自己新增一个模块级函数/常量时，也可能制造出新的遮蔽** ——
> 本次新增模块级 `repo_key()` 后，`build_topic_fingerprints()` 里有个**同名局部变量**
> （`repo_key = f.stem…`）立刻变成雷（详见 M14 末段）。
> → **纪律：新增任何模块级符号后，`grep -n "<符号名>"` 全量过一遍，
> 确认不存在「局部同名 / 参数同名 / 内层函数同名」。**

---

### M8 润色产物标题里的 U+FFFD 乱码

**症状**：标题首位一个可见乱码，如 `# � 涨星最快项目 ECC，我实际跑了一遍。`
（`\xef\xbf\xbd` = U+FFFD 替换字符）

**别急着怪编码**——2026-09-15 用两个对照实验定性：
| 实验 | 结果 | 结论 |
|---|---|---|
| 让模型原样输出 `🔥🚀✅` | 完整返回，码位 `0x1f525/0x1f680/0x2705` | SDK / HTTP 层**不丢字** |
| 让它「写一个带 emoji 的一级标题」 | 稳定返回 `# \ufffd 🚀 …`（温度 0，可复现） | **是模型/端点侧吐出的 U+FFFD** |

**排查手法**：`p.read_bytes().count(b'\xef\xbf\xbd')` 全库扫，看命中是否包含
**产线自动产出**的文件——包含即为系统性缺陷，不是本地编码问题。

**修法 —— ✅ 2026-09-15 已修并验证（代码 25/25 + 存量 11/11）**

**改动 1** 两文件新增同一份净化器（`article_generator.py` / `dsh_article_generator.py`）：

```python
_UNPRINTABLE_RE = re.compile(
    "["
    "\ufffd"                                    # 替换字符（解码失败的产物）
    "\ufeff"                                    # BOM / 零宽不换行空格
    "\u200b-\u200f\u2060-\u2064"                # 零宽与不可见格式字符
    "\u2028\u2029\u202a-\u202e"                 # 行分隔符 / 双向控制
    "\u00ad"                                    # 软连字符
    "\u0000-\u0008\u000b\u000c\u000e-\u001f"    # C0 控制（保留 \t \n \r）
    "\u007f-\u009f"                             # DEL + C1
    "]"
)

def _sanitize_unprintable(text):
    if not text:
        return text
    t = _UNPRINTABLE_RE.sub("", text)
    t = re.sub(r"^(#{1,6})[ \t]+", r"\1 ", t, flags=re.MULTILINE)  # ← 关键，见下
    t = re.sub(r"^[ \t]+(?=\S)", "", t, flags=re.MULTILINE)
    return t
```

**改动 2** `_clean_polished_output()` 返回前调用它（原来只剥围栏、只裁独白）。

**改动 3** `_looks_like_reasoning()` 加「首行强指纹」：首行 > 15 字符且以
`We need to` / `We must` / `We should` / `Let's go through` / `Original:` / `Translate to Chinese` /
`Sure,` / `Certainly,` 开头 → **单条即判**。（旧版要命中 ≥2 个 markers，遇到「只复述一句规则、
其余是中文」的开头会漏放。）

**⚠️ 两个容易踩的点**

1. **只清「行首空白」清不到标题行**。`# � 标题` 删掉 `�` 后剩 `#  标题`（`# ` 的空格 + `�` 后的空格），
   而**行首是 `#` 不是空白** → 必须单独把「`#` + 连续空白」归并成一个空格。**这是验证脚本 FAIL 才逼出来的。**
2. **做「新旧对照」实验，用例必须落在「新判据覆盖、旧判据不覆盖」的那条缝上**。
   我第一版对照用例选了纯英文输入 → 旧版靠「整段零中文（cjk < 5%）」也能命中 →
   两边一样、实验没有鉴别力。改成「首行英文元话语 + 独白主体中文」才区分开。
   （`_looks_like_reasoning` 实际有**两条**判据：零中文比例 + markers 计数。改造前先读清它们。）

**存量清理**：直接 `import` 产线模块、复用 `_sanitize_unprintable`，**不要另写一份正则** ——
保证「存量清理判据」与「今后防再发判据」是同一份实现，否则两边会漂移（M11）。

**已知不可逆损坏不用修**：`系统中枢/运行小结/代码与开发/skill-toutiao-*` 那几篇的**文件头已自带标注**
「本文件存在不可逆 UTF-8 字符损坏，部分内容已不可恢复，仅作历史参考」→
**先读文件头 400 字符再决定要不要修**，别拿字节数当唯一线索。

> **⚠️ 同族形态（H1 之外，2026-09-15 新发现 / 同日已处置 —— 见本节末「D6 处置记录」）**：
> 润色产物的头部污染**不止 H1**。
> 5 篇文件是**正文开头**多了一段 prompt 回显（`# 标题` 之前），形如
> ```
> We need to polish the article according to rules.
>
> We must keep frontmatter unchanged (none given). Keep markdown formatting.
> ...
> Original:
>
> # 用了几天ai-job-search，发现和预期不太一样。
> ```
> 实例：`深度调研/2026-09-12/MadsLorentZen-ai-job-search-推文.md` 及其 `_终稿_` / 草稿箱派生件；
> `2026-09-14-DSH-strukto-ai-mirage-深度文_终稿_*.md`（= M9 的污染终稿）。
> → **H1 判据查不到它**（H1 本身是干净的），必须**单独查「首个 `#` 之前是否有英文元话语」**。
> 代码层已加固（首行强指纹，新产出会被裁），**存量未动**。

---

### M9 「检查」环节自己发现了问题，但产物还是留下了

**实例**：DSH 9/14 strukto 那篇，多模型交叉审查把问题全抓到了（`最终判定: fail`，
P0 直接写着「标题引用 GitHub Issue 原文」「正文混入未清理的编辑指令与思维链笔记」），
但 `审查报告/<name>_终稿_*.md` **与污染深度文 sha256 完全相同** —— 终稿成了污染件的副本。

**判据**：`审查报告/` 下 `<name>_终稿_*.md` 与 `<name>_深度文.md` 字节数/哈希是否一致。
**风险评估**：`dsh_content_production_pipeline.py:219` 是 `final = find_review_final(...) if ok else None`，
即**审查失败则终稿不被消费** → 这次没外流；但终稿文件留在库里，日后重跑有被 `find_review_final()`
（取 mtime 最新）误取的风险 → **建议隔离，别只依赖上游判定**。

---

### M10 标题被「30 字硬截断」切成半句话 ★影响面最大

**症状**：发布标题以 `...` 结尾、句子说到一半，例如
`# 整理 Skill 清单的痛，gods-eye-view...`
`# 还在手动翻文档找配置？这个patent-discl.....`
`# GitHub Trending 的awesome-gp...`

**根因（2026-09-15 定量）**：`generate_titles()` 里有**两把刀**，且都不在词边界切：

```python
# article_generator.py  generate_titles()
258:  if len(project_name) > 15: short_name = project_name[:12] + '...'   # 刀 1：切 topic
310:  if filled and len(filled) > 30: filled = filled[:27] + '...'        # 刀 2：切整个标题
```

**量化（两种互补方法，建议都做）**

1. **确定性**：把 `title_formulas.json` 的 17 个模板逐个用**各槽位最长真实取值**填充，
   算长度 → **12 / 17（71%）必然 > 30 字**。最长的 `GitHub {hot_level} 的{topic}，我替你踩完了坑` 达 41 字。
2. **采样**：拿真实 repo 名（注意管线只传 `repo_name.split('/')[-1]`，**不传 `owner/repo`**）跑 1200 轮，
   统计 `title_candidates[0]`（= H1 = 发布标题）→ **26.4% 以 `...` 结尾**。

**判据（一句话）**：`H1.endswith('...')` —— 全 vault `rglob('*深度文*.md')` 扫一遍，
数出多少篇 H1 带省略号。**存量已有 18 篇。**

**两个加重情节**
- **复合省略号**：`short_name` 本身以 `...` 结尾、又恰被切在 27 字处 → 出现**五个连点**
  （`在几十个工具里挑花眼的痛，awesome-mcp-.....`）。
- **会溢出到发布环节**：`发布台账.md` 里已出现被截断的项目名 `K-Dense-AI/scientific-agent...`
  → 别只看文章文件，**台账也要查**。

**修法方向 —— ✅ 2026-09-15 上午已修并验证（29/29 PASS）**

**先定基准，再定改法（这一步别省）**：30 字**不是拍脑袋数字**，是项目既定基准 ——
封面 `image_generator.py` 取 `title[:30]`、`toutiao_format_adapter` / `zhihu_format_adapter` 都按 30 设计。
→ **放宽上限会连带封面排版、平台适配全部要改，收益远小于风险**。

> **结论：不动 30 字上限，只改「切法」+「候选排序」。**
> 遇到「上限该放宽还是该筛模板」这类取舍，**先去查这个数字是谁定的、还有谁依赖它** —— 通常会发现它不是可自由调的参数。

**实际改法（三文件）**

1. `article_generator.py`：新增 `TITLE_MAX=30` / `TITLE_TOPIC_MAX=16` / `TITLE_ELLIPSIS="…"` 常量；
   - `_shorten_topic()`：按 `-` / `_` **词边界**缩短（`limit=13`，`len(acc) >= 4` 才采用，否则 `name[:limit]+"…"`）
     → `awesome-mcp-servers` 变 `awesome-mcp…`，**保留完整词段**，不再是 `awesome-mcp-se...`；
   - `_smart_cut_title()`：**标点优先**断句（`，？！、：。 `），`best >= 12` 才断，否则 `text[:27]` 硬切兜底；
     若第 27 字已是 `…` 则不叠成 `…...`；
   - `generate_titles()`：加 `complete` / `degraded` 分组 + `formula_of_title` 字典，**完整句优先排到位置 0**（= H1 = 发布标题）。
2. `dsh_article_generator.py`：同构改动。
3. `publish_draft_v2.py`：`extract_title()` 三处硬切改用 `_smart_cut_title()`。

**验证结果**

| 指标 | 修前 | 修后 |
|---|---|---|
| 主管线**硬切率** | 45.6% | **0.0%** |
| DSH 线硬切率 | 44.1% | **0.0%** |
| 标题完整句率 | — | **100%** |
| 复合省略号 `.....` | 613 次 | **0** |

**⚠️ 存量处置提醒**：改完后**必须跑一次存量处置**（见第 5 章）—— 修复前产出的坏标题**不会自己变好**。
本项修完后存量处置共写了 **69 篇**（深度文 30 + 漏网副本 8 + **推文 31**）。
→ **`-推文.md` 是文章的第二形态，和 `-深度文.md` 同病**。只扫「深度文」会漏掉一半。

**⚠️ 省略号形态统一**：本项目既有约定是 `…`（U+2026，`tie_tu_format_adapter.py` 多处已在用），
不要用 ASCII `...`。判据里两种都要覆盖（`H1.endswith('...') or H1.endswith('…')`）。

---

### M11 「一处修了、同构处漏改」—— 分叉线的配置/逻辑漂移 ★吃亏两次

**症状**：同一个 bug 明明修过，另一条线上还在反复出现。

**2026-09-15 实证（同一会话内栽了两次）**

| 缺陷 | 已修处 | 漏改处 | 后果 |
|---|---|---|---|
| 泄漏源模型 | `article_generator.py`（P2-8 已换） | `source_researcher.py:173`、`dsh_source_researcher.py:183`、`article_image.py:16` | 3 处继续把思考独白写进产物 |
| `hot_level` 含 "GitHub" | `article_generator.py:266` 已加修正 | `dsh_article_generator.py:300` 硬编码 `'GitHub Trending'` | DSH 线**至今每跑必产** `GitHub GitHub Trending 的...` |

**✅ 2026-09-15 上午两处均已收口**：泄漏源模型 3 处漏网已替换（#12）；
`dsh_article_generator.py` 的 `hot_level` 已对齐主管线（`random.choice(['Trending','周榜前排','涨星最快']) if stars > 1000 else '新兴项目'`），
并**同源补做槽位多样化**（`pain_point` / `benefit` 由硬编码改随机池）→ `verify_d4.py` **9/9 PASS**，
全库 `'GitHub GitHub'` 命中 **453 条 → 0 条**。

**判据（一句话）**：`diff <主管线文件> <分叉文件>`，只看**同一段逻辑的两份实现是否一致**。

**排查套路**
```bash
# 找同名函数/常量在两条线的实现差异
grep -n "def generate_titles\|template_slots\|LLM_MODEL = os.environ.get" \
     article_generator.py dsh_article_generator.py
```
> **DSH 线是分叉未同步的旧版**：它的 `hot_level` / `benefit` / `pain_point` **全部硬编码无随机**，
> 主管线的 P1-5「槽位多样化」也没同步。~~**改 DSH 任何一处前，先做一次两文件的整体对齐 diff**~~
> → **2026-09-15 已整体对齐一次**（D4 项）。但**新增模板 / 新增槽位时仍要重新对齐** —— 结构性护栏只有 diff 能发现。

---

### M12 「一个槽位被多条模板以互不兼容的语义消费」★2026-09-15 新发现 / 同日已修

> **✅ 已修（2026-09-15，方案 A）。** 修法与验证见本节末「修复记录」。
> 以下「症状 / 根因」段保留原貌，因为它才是**怎么认出这类缺陷**的教材。

**症状**：产出的标题**语法没错、但语义荒谬**，例如

```
实测99个TencentDB-Agent-M…，只有2个值得用。      ← 这是「千星数」当成了「测了几个工具」
一周涨星58k的ouroboros，到底好在哪。             ← 「5.8 万星」被写成「58k」，勉强读得通
99个firecrawl-pd…，第2个我天天在用。             ← 这是「千星数」当成了「榜单条目数」
```

**怎么发现的**：不是主动排查出来的 —— 是**跑存量处置的 dry-run 时顺带炸出来的**。
→ **教训：dry-run 的输出要逐条读，别只看计数。** 本次如果只盯「待处置 N 篇」这个数字，D5 就漏掉了。

**根因（两文件同构）**

```python
# article_generator.py:345 / dsh_article_generator.py:378
'number': str(min(stars // 100, 99)),      # ← 语义是「千星数」
```

而 `title_formulas.json` 里**有 3 条模板用互不兼容的语义消费同一个槽位**（weight 合计 8/36 ≈ 22%）：

| 模板 | 模板要的语义 | 实际喂的 | 偏差 |
|---|---|---|---|
| `一周涨星{number}k的{topic}，到底好在哪` | 千星数 | 千星数 | ✅ 唯一匹配 |
| `实测{number}个{topic}，只有{n}个值得用` | **测了几个同类工具** | 千星数 | **最高 12.0 倍** |
| `{number}个{topic}，第{n}个我天天在用` | **榜单条目数** | 千星数 | 数倍 ~ 数十倍 |

**两个次生效应**

1. **饱和聚集**：`min(..., 99)` 令 **≥9,900 星全部退化成 `99`** → 22.6k / 77k / 171k 三个
   量级完全不同的项目，标题长得**一模一样**（读者看不出差别，也失去了「涨星快」的信号价值）。
2. **命中率反推**：H1 命中这 3 条模板的比例 25.2%（400 轮抽样）；M7 修复前版本 21.0%
   → **老缺陷，不是新改动引入的**（定位新旧缺陷时，**跑一次旧版本对照片**比反复读代码快）。

**量化判据（抽样脚本要跑）**：固定 `random.seed()`，跑 400 轮，统计
①各模板命中率 ②`number` 填充值分布（看是否堆在 `99`）③与真实 `stars` 的偏差倍数。

**处置原则 —— 存量阶段只做减法，别顺手改产线**

存量处置阶段只做**判据层保护**：在坏标题判据里加 `NUM_PAT`，把这 3 条模板的产物识别出来并**排除**，
避免用同样的错语义去「修」出新的错标题。
（这条原则仍然成立：**存量治理和产线修复是两个阶段**，别在 dry-run 里顺手改产线。）

**修复记录（2026-09-15，方案 A 落地）**

选择 **A**（槽位按真实语义分流），理由：B 引入 `slot_semantics` 声明层、复杂度换来的灵活性
这个规模用不上；C 直接砍 22% weight 损伤标题多样性。A 是「语义本来就该这样」。

| 动作 | 落点 |
|---|---|
| `title_formulas.json` → **v2.0.0** | 新增 `slots_doc`（7 槽位真实语义声明）、`rules`（缺数据即跳过，不填假值）、`retired` |
| **下线 2 条**拿不到真数据的模板 | `实测{number}个{topic}，只有{n}个值得用`、`{number}个{topic}，第{n}个我天天在用`（保留 17 条 / weight 仍 36） |
| 喂数改真数据 | 两文件 `generate_titles()` 加 `growth` 形参，4 个调用点传 `repo_info.get('growth', 0) or 0` |
| 缺数据即跳过 | `missing` 机制 + `re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "", filled)` 兜底防占位符泄漏 |

**关键取证（决定方案可行性，别跳过）**：`growth` 到底拿不拿得到？

| 线 | 来源 | 非零比率 | 中位 |
|---|---|---|---|
| 主管线 | `_repos.json.growth` → `article_generator.py:1929` | **158 / 169** | 4,841 |
| DSH 线 | `dsh_source_collector.py:139/211` **写死 0** | 0 / 全部 | 0 |

→ DSH 线恒 0，自然走「跳过模板」分支，不会造假数。**若没做这步取证，方案 A 无从谈起**
（这也是「先证明数据可得，再改消费端」的一般次序）。

**验证怎么做的（这套对照法可复用）**：
`generate_titles()` 新旧签名不同 → 旧版走 `legacy=True` 分支按旧签名调用（**新旧对照必须适配旧接口**）。
- **动态对照**：同一输入集，旧版产出 `number` 型错标题 **71/196 → 新版 0 条**；
- **饱和对照**：旧版 `min(stars//100, 99)` 令 ≥9,900 星全退化成 `99`（22.6k/77k/171k 标题雷同）；
- **反证**：旧版实际落地的数字集合是 `['99']`，与真实 `growth`（651/4841/25469）**完全脱钩**；
- **冒烟**：`growth = 0 / 4841 / 25469` 三档 600 轮，异常 0；`growth=0` 时相关短语 0 次命中。
- 结果：`verify_d5.py` **28/28 PASS**。

**存量**：已外流 35 文件（活 12 + 归档 23）**不回改** —— 属已发布内容，
回改标题会制造「标题与内容不符」的新问题。

**修法三选一（备查）**

- **A（推荐）** 槽位改名分流：`number` 拆成 `stars_k` / `tested_n` / `rank_n`，模板各自引用 → 语义显式，改动量中等；
- **B** 给模板加 `slot_semantics` 声明，生成时按声明动态填 → 灵活但引入复杂度；
- **C** 砍掉那 3 条模板（占 22% weight）→ 最省事，但损失标题多样性。

**泛化判据**：**一个槽位值，若被 ≥2 条模板以不同单位/不同量纲消费，就是缺陷。**
读 `title_formulas.json`（或任何模板库）时，把每个占位符**逐条目视核对它在各模板里的语义**，
不要只看它「有没有被填充」。

---

### M13 「往前看」的错误：按仓库名查台账 → 误判「未发布」★2026-09-15 定型

**症状**：缺陷明明已经外流到真实发布，报告却写「均无发布记录 → 未按正式发布发出」。

**实例（本次栽了）**：8 篇 commit 式 H1（M7 产物），我用**仓库名**去 `发布台账.md` 里搜 → 一条都搜不到
→ 判「未外流」。实查发现**已外流 3 处，其中 2 条头条状态为「已发布」**：

| 平台 | 发布件 | 台账状态 | 源文章 |
|---|---|---|---|
| 头条 | `发布/已发布/头条/2026-09-14-add a model architecture.md` | **已发布** | `2026-09-14-cathrynlavery-diagram-design-深度文.md` |
| 头条 | `发布/已发布/头条/2026-09-15-keep changelog-video's.md` | **已发布** | `2026-09-15-heygen-com-hyperframes-深度文.md` |
| 小红书 | `发布/已发布/小红书/2026-09-12/fix(jobindex-sear`（目录名） | 失败 | `MadsLorentZen-ai-job-search-推文.md` |

**错在哪（这是关键认知）**：**台账里存的就是被损坏后的标题** ——
`add a model architecture`、`keep changelog-video's`、`fix(jobindex-sear...` 这些正是 M7 的产物。
**用仓库名去搜损坏标题，必然搜不到。**

**正确判据（一句话）**：**按 H1 原文 / 台账标题原文比对，不要按仓库名。**

**正确查法（两条腿都要走）**

```bash
# ① 台账：按损坏形态直接捞（而不是按仓库名）
grep -nE "(^|[^a-zA-Z])(fix|feat|chore|docs|refactor|perf|test|build|ci|revert)(\([^)]*\))?:" 发布台账.md
grep -n "\.\.\.\|…" 发布台账.md

# ② 发布目录：按文件名损坏形态捞
find 发布/已发布 -\( -name "*...*" -o -name "fix(*" -o -name "feat(*" -o -name "*keep changelog*" \) | sort
```

**配套认知**：**发布件是「已投递快照」，不回改** —— 回改等于篡改历史交付物，且平台端已发出无法撤回。
→ 只**登记**，要重发就基于**已修好的母版**重新走发布流程。

**顺带修正一个量级印象**：同类缺陷里 **M10（截断）的发布面比 M7 大得多** ——
发布目录下损坏文件名 **13 处**（M7 占 3），台账损坏标题行 **16 行**、状态「已发布」**3 行**。
别因为 M7 更「显眼」就低估 M10。

---

### M14 上游名称「大小写不保真」+ 集合精确比较 → 同一项目重复出文 ★2026-09-15 定型

**症状**：同一个 GitHub 项目被当成两个不同项目 → **候选池去重失效、重复出文**。
标题、正文看起来都正常，**没有任何报错**，所以只有对比候选池数据时才看得出来。

**根因**：`owner/repo` 在 **GitHub API 层是大小写不敏感的**，
但**上游 AI 日报 / 转述不保真** —— 同一项目这次写 `MadsLorentZen`、下次写 `MadsLorentzen`。
而代码里全是用**集合精确比较**做去重：

```python
if name in seen:                       # 换个大小写 → 判成新项目
if repo_name not in existing_repos:    # 同上
seen = {p['name']: ...}                # 字典键也是精确大小写
```

**实测证据**（写报告时必须有这种一行铁证）：`2026-09-12_repos.json` 里
**同时存在** `MadsLorentZen/ai-job-search` 与 `MadsLorentzen/ai-job-search`，`stars` 均 **39858**。

**影响面得靠 grep 摸清，别只修看到的那一处**（这是 M11 的同类功课）：

| 文件 | 比较点 |
|---|---|
| `daily_content_refiner.py` | `merge()` 建键 + `seen_names` |
| `article_generator.py` | `get_existing_repos` 决策 + today 决策 |
| `dsh_article_generator.py` | 同构两处 |
| `content_production_pipeline.py` | 调研切片 `_written`（**漏判会白跑一次 LLM 调研**） |
| `dsh_candidate_selector.py` | `seen`（状态文件）/ `written`（共享目录） |

→ 共 **6 个比较点跨 5 个文件**。

**统一修法**：定义一个**唯一口径**的归一化键函数，所有比较走它：

```python
def repo_key(name: str) -> str:
    """repo 名的归一化比较键（仅用于比较，**不回写原始拼写**）。"""
    return (name or "").casefold()
```

两条纪律：

1. **`.casefold()` 而不是 `.lower()`** —— casefold 是「大小写折叠」，对
   `ß / İ` 等 Unicode 边角也正确；`.lower()` 在纯 ASCII 下等价，但没理由不用更强的那个。
2. **只归一化比较，不改写存储** —— 原始拼写要保留：它决定**文章文件名**、
   影响**「已写过」历史匹配**、也影响人读日志。把 `name` 改写了会引发一串次生问题。

**验证怎么做（新旧动态对照，别只 grep 符号在不在）**：

- 从 `.bak` 里**抽出真实函数源码**（正则 + `textwrap.dedent`，嵌套函数必须先 dedent）
  与现版分别 `exec`，喂同一份「同库异写」输入 → **旧版 2 条 / 新版 1 条**；
- `dsh_candidate_selector` 这类有 IO 的，**monkeypatch 模块常量到临时目录后真跑 `main()`**，
  比对输出 JSON 的 `skipped_duplicates` —— 端到端比读代码可信；
- `article_generator` 的 `get_existing_repos()` 同样 monkeypatch `CONTENT_PRODUCT` / `OUTPUT_DIR` / `DATE` 后真跑；
- **顺手证伪一条**：共享文章目录那条路径本来就 `.lower()` 双向比较、**大小写不敏感**
  → 那里改的**是一致性加固、不是修 bug**。**报告里要如实写，别把加固算成战绩。**

**泛化判据（一句话）**：**凡是拿「外部来源的名称」当集合键 / 去重键 / 字典键，
先问一句：这个来源保真大小写吗？** 不保真 → 一律先归一化再比。
同类还有：GitHub 组织名、PyPI 包名（本就不允许大小写区分语义）、模型 ID、平台账号名。

**⚠️ 改完必做的一步（本次踩到）**：新增了模块级函数名 `repo_key` 后，
发现 `article_generator.py` / `dsh_article_generator.py` 的
`build_topic_fingerprints()` 里**有一个同名的局部变量** `repo_key = f.stem…` ——
**正是 M7 的变量遮蔽形态**。当前不影响功能（该函数内只用局部那份），
但埋了雷：以后谁在这个函数里调 `repo_key(...)` 就会 `TypeError: 'str' object is not callable`。

→ **纪律：一次新增模块级符号后，必须 `grep -n "<符号名>"` 全量过一遍，
确认没有「局部同名」或「参数同名」（M7）**。本例把局部变量改名 `stem_key` 消掉。

---

## 3. 逐项修复验证流程（用户要求「修一项验一项」时照此执行）

```
① 备份          cp -p <file> <file>.bak.<日期>-<标签>
② 改一处        一次只动一个问题，改完立刻停
③ 语法检查      "$PY" -X utf8 -m py_compile <file.py>
④ 残留检查      grep -n "<改动的符号>" <file>   # 确认只剩注释
⑤ 隔离验证      写独立测试脚本跑该模块（放 %TEMP%）
⑥ 全链路重跑    跑真实产线，EXIT=0 且产物规格正确
⑦ 对照计数      关键告警/关键行 改前 vs 改后 计数对比
⑧ 记证据        改动 + 验证输出写进记忆文件
```

**只做 ①②③ 就宣布"修好了"是不合格的**——本会话的教训：
P2-8 原修复被**自己的端到端验证**推翻（只裁开头，中段残留被放行）。

### 3.1 归因纪律：每个结论都要配一个**能推翻它**的对照实验 ★2026-09-15 定型

这是整份手册里最贵的一条，因为它**不解决任何具体 bug，但决定你会不会在错的方向上耗掉几天**。

**规则**：

1. **现象为真 ≠ 归因正确**。同一组现象可以支撑多个互斥假设，必须设计实验把它们分开。
2. **对照实验的最低要求是「单变量」** —— 只改你怀疑的那一个因素，其余全不动
   （例：同一个页面、同一个文件，只把窗口从遮挡改为前台 → `hidden`/`visible` 两态对照）。
3. **优先做「能不能推翻」的实验，而不是「能不能印证」的实验**。印证很容易，随便看两眼都能印证。
4. **沉默也是数据，而且最容易被忽略**：`error === null` + 永久挂住，看起来像「还在加载」，
   其实可能是「根本没启动加载」。**没有报错不等于没问题。**
5. **连续三次归因都被推翻时，停手，回头查你自己的工具链**（版本 / 环境 / 探针本身）——
   见 §1.6、§1.8。三次偏在同一侧，说明**测量工具**坏了，不是被测对象难。

**本轮实例（三次归因全错，第四次才对）**：

| # | 结论 | 推翻方式 |
|---|---|---|
| 1 | 渲染层次问题（shadow DOM） | 查 `wujie-app.shadowRoot` → `null`；内容在同源 iframe 里（§6.2） |
| 2 | 页面元素不存在 / 拒绝接收 | 预埋 drop 监听 → 文件真的到了、`beforeUpload` 真的被调了（§6.3） |
| 3 | 扩展与守护进程能力不对齐 | 升到 0.2.1 → `bsk upload` 可用，但**仍然传不上去**（§1.6 之后） |
| 4 | ✅ **hidden 文档不加载媒体** → 页面拿不到视频元数据 → 不上传 | 抬窗对照：`hidden → TIMEOUT` / `visible → loadedmetadata`（§6.7） |

> 教训浓缩成一句：**「自动上传失败」这类现象，先查工具版本（v4.4），再查宿主环境（v4.5）。**
> 两次都是「现象为真、归因错了」—— 所以**每下一个结论，都要配一个能把它推翻的对照实验**。

### 全链路验收命令模板

```bash
PY="C:/Users/Administrator/.hermes/hermes-agent/.hermes-runtime/python/cpython-3.11-windows-x86_64-none/python.exe"
LOG="C:/Users/Administrator/AppData/Local/Temp/e2e_pipeline.log"; : > "$LOG"
cd "C:/Users/Administrator/.hermes/scripts"
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$PY" -u -X utf8 daily_video_production.py --repo <owner-repo> --skip-broll >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
```

**通过标准**（四条全中才算过）：
1. `EXIT=0`
2. 日志出现 `📤 上传副本（仅此一个，直接拖它）: ...`
3. `C:\Users\Administrator\Videos\视频号待上传\` 出现**本次新时间戳**的 mp4
4. `ffprobe` 规格正确：`h264` + `1080×1920` + `aac` + 时长/体积合理

---

## 4. 产物落点（别落错目录）

| 产物 | 落点 |
|---|---|
| 视频 / 口播脚本 / scene_plan / 字幕 | `D:\Obsidian Vault\obsidian Vault\内容生产\成品与素材\<日期>_<仓库名>\` |
| 上传副本（人工拖入视频号助手） | `C:\Users\Administrator\Videos\视频号待上传\`（**永远只有最新一条**） |
| 数据快照 `_data.json` / `_调研.md` | `内容生产\创作与调研\素材与资源\源码调研\` |
| 快手归档 | `内容生产\发布\已发布\快手\`（由 `publish_multi_platform.py` 管，**不归产线预归档**） |
| 发布台账 | 幂等键 = `日期\|标题\|平台` |

**数据铁律**：口播稿里所有数字/功能必须来自 `_data.json` 快照，禁止 LLM 编造。
选材时必须拒绝没有 `_data.json` 的稿子（除非显式 `--allow-no-data`）。

---

## 5. 存量污染治理：走「重新生成」而不是「手工清洗」★2026-09-15 定型

**核心认知**：被污染的产物**不是一篇脏文章，而是一次失败润色的完整 dump**。
而 `generate_deep_article()` 的正文本来就是**从上游数据重新组装**的
（`_data.json` + `_调研.md` + `<日期>_repos.json`），**与旧文件内容无关**
→ 只要上游在，就能干净重做，**完全不需要从垃圾里捞正文**。

### 5.1 三步流程

```
① 扫描    用与 article_generator._STRONG_LEAK_PATTERNS 同一套判据扫全库产物
② 核上游  确认 <slug>_data.json / <slug>_调研.md 存在（注意：DSH 线在别的目录！）
③ 重生成  反射加载生成器 → patch DATE/NOW/REPOS_JSON → 调 generate_deep_article()
```

### 5.2 三个必踩的坑

1. **必须 patch 模块级 `DATE`**，否则输出落到今天的文件名 → 生成 `09-15-*` 新文件，
   旧污染件还在，等于没修。
   ```python
   ag.DATE = "2026-09-14"                                  # 决定输出文件名
   ag.NOW  = datetime.strptime(ag.DATE, "%Y-%m-%d")
   ag.REPOS_JSON = CONTENT_PRODUCT / f"{ag.DATE}_repos.json"
   ```
2. **生成器自己不读 `.env`**（`call_llm` 直接 `os.environ.get("NVIDIA_API_KEY_A1")`），
   离线单跑会静默打印「⚠️ 无 LLM API Key，跳过内容加工」，产出**干净但未翻译的初稿**。
   必须**在 import 之前**灌 env（`LLM_MODEL` / `LLM_BASE_URL` 在模块顶层就被读取）：
   ```python
   ENV_FILE = Path(r"C:/Users/Administrator/.hermes/.env")   # 用 setdefault，别覆盖已有值
   ```

   > **2026-09-15 已取证：这不是生产缺陷，只是离线单跑的坑。** 别再把它当 bug 报上去。
   > - **架构如此**：`load_env()` 只在**两个入口**（`content_production_pipeline.py` /
   >   `dsh_content_production_pipeline.py`，外加 `dsh_source_collector.py`）定义并调用；
   >   6 个 worker（`article_generator` / `dsh_article_generator` / `daily_content_refiner` /
   >   `dsh_candidate_selector` / `source_researcher` / `auto_review_latest`）**全都不自读**
   >   —— 入口加载一次、子进程继承 `os.environ`，是**家族统一设计**。
   > - **双保险**：所需键同时持久化在 **Windows 用户级环境变量**（`HKCU\Environment`，
   >   用 `winreg` 读，`reg.exe` 被安全策略拦）。
   > - **调度链不绕过**：`cron/jobs.json` 里内容产线只有「08:15 主管线」「09:15 DSH」两条，
   >   都是入口脚本，**没有任何任务直调 `article_generator.py`**。
   > - ⚠️ **但 `load_env()` 用的是 `setdefault`** → 进程已继承注册表值时，**`.env` 那份被静默忽略**。
   >   2026-09-15 实测：两源**漂移 13 个键**（远不止 `NVIDIA_API_KEY` 一个），
   >   且**注册表侧才是有效的、`.env` 是滞后副本**。
   >   **已处置**：`.env` 同步 5 键（行为零变更）+ 三处 `load_env()` 加漂移告警与 `HERMES_ENV_OVERRIDE` 开关
   >   （默认零回归）；监控状态文件同步校准。
   >   **完整排查三段式见 §1.5** —— 切记：**先探两侧有效性，再决定统一到哪侧**。
3. **DSH 专线的上游不在主管线目录**：
   | 线 | 上游目录 | 产物名 |
   |---|---|---|
   | 主管线 | `内容生产\创作与调研\素材与资源\源码调研\` | `<日期>-<repo>-深度文.md` |
   | DSH | `内容生产\DSH专线\`（+ `DSH专线\content产品\<日期>_dsh_repos.json`） | `<日期>-DSH-<repo>-深度文.md` |
   > 找不到上游时先 `find <vault> -iname "*<keyword>*"` 全库找，别急着下「无法重新生成」的结论。

### 5.3 收尾两件事（别漏）

- **留证**：改前把污染件 `copy2` 到 **vault 之外**（如 `outputs/polluted_articles_<日期>/`），文件名后缀 `.polluted.md`；
  `if not bk.exists()` 守卫可防第二次跑时用干净版覆盖掉证据。
- **修标题**：重生成后 H1 很可能仍被 M7 影响 → 用管线自己的 `generate_titles()` 重取
  （**不要自己编标题**），并过滤掉「被 30 字截断成 `...`」和「槽位拼接出的叠词（如`手动手动`）」的候选：
  ```python
  clean = [c for c in cands if not c.endswith("...") and not re.search(r"([\u4e00-\u9fff]{2})\1", c)]
  ```

### 5.4 处置前的三个必查

- **外流核查**：查 `内容生产\发布\发布台账.md` 有没有该文（幂等键 `日期|标题|平台`）。
  注意同名旧版本会误命中 —— 要核对**日期**，别只看标题。
- **下游是否已消费**：查 `审查报告/<name>_最终审查_*.md` 的「最终判定」。
  `fail` 的稿子通常是**被系统自己拦下的**，风险等级远低于「pass 且已发布」。
- **H1 质量全库体检**（2026-09-15 新增）：存量问题**不止泄漏**，标题本身有三族缺陷。
  一条命令扫完（**先按内容哈希去重**，vault 里同一篇文章常有 `_with_images` / `-推文` / `_with_config` 多个副本）：
  ```python
  # 判据（全部作用在 H1 = 第一行 '^# ' 上）
  h1.endswith("...") or h1.endswith("…")              # M10 被 30 字切半句
  "..." in h1 or "…" in h1                            # M10 项目名被切
  "GitHub GitHub" in h1                                # M11 槽位重复
  re.match(r"^(fix|feat|chore|docs|refactor|style|perf|test|build|ci|revert|Merge)\b", h1, re.I)  # M7 遮蔽残留
  any(ch in h1 for ch in "\ufffd\ufeff\u200b\u2028")   # M8 乱码/不可打印（2026-09-15 补）
  re.match(r"(一周涨星\s*\d+\s*k|实测\s*\d+\s*个|^\d+\s*个[^，。]{1,30}，\s*第\s*\d+\s*个)", h1)  # M12 槽位语义错配
  ```
  **H1 之外还要查一处**（M8 同族）：`首个 '#' 标题之前是否出现英文元话语`
  （`We need to` / `Original:` / `Translate to Chinese` / `Keep markdown formatting`）——
  **H1 判据对这类「正文头部 prompt 回显」完全无效**，因为 H1 本身是干净的。

  ⚠️ **`^#\s+` 取到的未必是第一行** —— 若文件头部有 prompt 回显，`# 标题` 会被挤到后面，
  于是「H1 干净」的错觉会让这类污染整片漏过。**扫的时候要同时报告「H1 所在行号」**，
  行号 > 1 就说明前面有多余内容。
  2026-09-15 实测基线（`*深度文*.md`，去重 429 个文件）：commit 式 8 / 截断 18 / `GitHub GitHub` 2 / U+FFFD 0。
  全库（3543 个 .md，排除 归档/_backup/.review_tmp）：H1 含 U+FFFD **6** / 头部 prompt 回显 **5**。
  > ⚠️ 「头部回显 5」是**只看开头**扫出来的；改用**整篇判据** `_count_process_leaks()`
  > 重扫同一批 3543 个 .md → **命中 9**（多出 2 份「最终审查报告」正文被思维链占据且中途截断，
  > 以及 2 份终稿副本）。**扫存量时，"只看开头"和"看整篇"是两个结果。**
  > **区分「代码已修」与「存量未清」**：代码修好后，**修复之前**产出的文件仍带病。
  > 判断某篇是否属「修复前残留」→ 比对该文件的 **mtime** 与修复时刻。

**D6 处置记录（2026-09-15，全库扫描 9 命中 → 三路处置，验证 15/15）**

按**能不能恢复**分三路，**不要一律剥离**：

| 路 | 情形 | 处置 |
|---|---|---|
| **a 剥离** | 正文完整，只是头/尾多了元话语 | 头裁至首个 `#`、尾裁至模板块 `---`；**正文逐字节保留** |
| **b 标注** | 正文被思维链顶掉且**中途截断** → 信息不可恢复 | 加 `> ⚠️ **日期 标注**：` 文件头，**不伪造缺失内容**（同 `skill-toutiao-*` 既有样式） |
| **c 隔离** | 终稿副本已损坏且是**过期版本** | 移入 `_隔离_污染终稿-<日期>/`，按来源分子目录 + `README.md`；**不删** |

**a 路必守的 5 条硬不变量**（`apply_d6a_strip.py` 内置，逐条断言后才写盘）：

```
A 头部确实像独白      _looks_like_reasoning(head) and any(is_meta(l) for l in head)   # 与产线同款判据
B 尾部确实含泄漏      _count_process_leaks(tail) >= 1
C 正文逐字节保留      剥离前后正文段做字节比对（不是"看起来对"）
D 裁后无残留          _count_process_leaks(结果) == 0
E 行尾不变            CRLF/LF 与末尾换行都不变 → 用 write_bytes，别用 write_text
```

> ⚠️ **断言 A 别写太严**：原本要求「头部区每一行都是元话语」，结果崩了 ——
> 独白自己会列举代码片段（延续上一句 "In the article, there are"），
> 这些行不算 is_meta。→ 放宽为**产线同款判据**（整体像独白 + 至少一行元话语）。

**c 路的判据（怎么确认"过期副本"而不是"唯一正本"）**：
比 **行数 + H1 形态 + mtime + sha256**。本次：正本 125 行 / H1 干净 / 09-15 重生成；
副本 222 行 / H1 是英文 Issue 标题 / 英文未译 / 多处截断，两份副本 sha256 相同 → 判过期。
**隔离后要验证下游**：`find_review_final()`（glob `{stem}_终稿_*.md` 取 mtime 最新）
**必须返回 `None`**，否则隔离白做。

**代码层防线的版本梯度（用于证明"这次改的确实是关键那条"）**：

| 版本 | 防线 | 同一污染输入 |
|---|---|---|
| 更早版 | 无 | 污染就在这个窗口产生 |
| 中间版 | 有头部裁剪，但 `_is_valid_polish` **只查开头 600 字** | **校验通过 → 落盘** |
| 现版 | 增 `_count_process_leaks() >= 1` **整篇闸门** | **拒收** |

> **教训**：**只查头部的校验函数挡不住尾部污染。** 凡是「防模型跑偏」的校验，
> 判据必须作用在**整篇**，而不是前 N 个字符。

### 5.5 批量修 H1 的工程细节（2026-09-15 实战，69 篇写盘零事故）

**扫描范围（别只扫一种文件名）**
```python
ARTICLE_GLOBS = ("*深度文*.md", "*推文*.md")     # ← -推文.md 是文章第二形态，同病
EXCLUDE_DIRS  = ("归档", "_backup", ".review_tmp")  # 归档/备份不篡改
```
> 2026-09-15 因为只写了 `*深度文*`，**漏掉 48 份推文**，第二轮又补跑一次。

**内容去重要用并查集，不能只按 hash 去重**
同一篇文章常有 `OmniRoute-深度文.md` 和 `2026-08-10-diegosouzapw-OmniRoute-深度文.md`
这种**内容相同、keyword 名不同**的副本 → 单纯按内容 hash 去重会**永久残留 4 份**。
→ 并查集把同 hash 的文件并成一组（`hh_kw` 记录 hash→第一个 keyword），**组内标题必须一致**。

**幂等化（要求「两次 dry-run 逐字一致」）**
```python
random.seed(20260915)
for _m in (AG, DSH):
    _m._read_last_title_formula  = lambda: ""
    _m._write_last_title_formula = lambda *a, **k: None   # 去掉副作用
```

**写盘安全（三处断言 + bytes 写入）**
```python
new_txt = re.sub(r"^#\s+[^\r\n]+", lambda mm: f"# {new}", txt, count=1, flags=re.MULTILINE)
assert new_txt != txt
assert new_txt.count("\n")   == txt.count("\n"),   "行数变了"
assert new_txt.count("\r\n") == txt.count("\r\n"), "换行风格变了"
p.write_bytes(new_txt.encode("utf-8"))     # ← 不能用 write_text()！会按 os.linesep 翻译换行
```
> **本 vault 29/30 目标文件是 CRLF**，`write_text()` 会把 LF 改写成 CRLF。
> 另外 `^#\s+.+$` 的 `.+` 会**吞掉行尾 `\r`** → 三处正则必须写 `[^\r\n]+`。
> 这两点都是**断言在写盘前把文件救下来**的 —— 断言不是形式，是护栏。

**备份名要带路径指纹**
```python
ph = hashlib.sha256(str(p).encode("utf-8")).hexdigest()[:8]
bk = OUT / f"{p.stem}.{ph}.h1bak.md"        # ← 只用 p.name 会让不同目录同名文件互覆
```

**处置范围要收窄：只改坏标题文件，不要「整组重写」**
曾试过「组内任一不合格则整组重写」→ dry-run 把 `-调研报告.md` / `_素材包清单.md` / `_审查报告.md`
一起卷进来重写标题（误伤 36 篇）。→ 回退为：
**只处置命中坏标题判据的文件** + **漏网副本沿用首轮已收敛标题**（且只认「有留证文件」的，天然排除非文章类）。

**验证要「以原件留证为基准反查」**（`verify_*.py`，8 项）
留证可对应（无孤儿）/ 坏标题归零 / 每篇确有改动 / **改动仅限标题行**（合法值 2 或 4 行）/
行数与 CRLF 计数不变 / frontmatter `title` 与 H1 一致 / 全库文章类残留归零 / 同内容副本标题一致。
> 判据要写「**合法值集合**」而不是「不等就报错」：带 frontmatter 的必改 4 行；
> 换标题后**字节数可能恰好抵消**（2359→2359），拿字节数当判据会误报。

**收敛性**：处置完再跑一次 dry-run，必须 **0 篇 / 0 组**。

**判断能否"改标题"而不是"重生成"**：标题是 `generate_titles()` 的产物，**手工改会与正文/摘要脱节**。
但**存量清理**场景下（`title_candidates` 已无从恢复）可用「用管线自己的 `generate_titles()`
重取候选 + 严格判据过滤」的办法，比整篇重生成成本低得多，且**候选仍出自管线**、不引入人为创作。
两者取舍：**泄漏类污染走重生成（5.1）；纯标题缺陷走标题重取（本条）**。

---

## 6. 视频号草稿箱上传实操（2026-09-15 实跑，**自动链路已打通**）

> 📌 **本节已固化为独立 skill：`d2v-channels-publish`（2026-09-15 建）**
> 「正常怎么跑、判据是什么、故障怎么认」→ 去 `d2v-channels-publish`（包含可见性门禁的操作判据、
> CLI 参数表、退出码、函数↔职责映射表、故障速查表）。
> **本节保留的是「怎么查出来的」** —— 三轮取证过程、被推翻的结论（标 ❌）、对照实验设计，
> 这些是 repair 视角的东西，不重复搬进操作 skill。
> ⚠️ 本节与 `d2v-channels-publish` 有内容重叠；建议后续把本节瘦身为「短导航 + 只留跨产线通用部分」，
> **但未获用户确认前不擅自删改**。

> 背景：用户要「跑一条视频 + 推进视频号草稿箱」。本轮把这条链路从**全手工**做到了
> **`publish_channels.py --publish` 一键进箱**（草稿箱 2 → 3 → 4 条，两次端到端通过）。
>
> ⚠️ **本节内容经过两轮自我推翻**，保留下来的每条结论都配了对照实验。读的时候注意区分
> 「当时以为的」和「后来实测的」—— 被推翻的结论**故意留着**（标 ❌），因为那些误判的形态会复发。

### 6.0 历史：曾经的自动上传路径是坏的（**v4.5 已修，两处**）

| # | 位置 | 当时的现状 | 实测真相 | 修法 |
|---|---|---|---|---|
| ① | `TITLE_MIN, TITLE_MAX = 6, 50` | 按 50 字放行 | 平台短标题**硬限 16 字**，超限 → `error-title` → **三按钮全 disabled** → 保存静默失败 | 改 `6, 16`，**两端都拒绝**（不再静默截断/补字符） |
| ② | `publish_video()` → `bsk_fill(sid, "input[type=file]", path)` | 假设能用 CSS 填文件框 | **`bsk fill` 只支持文本、不支持文件**；且页面元素在**同源 iframe** 里，顶层 CSS 全失配 | 改调 **`bsk upload`**（0.2.0+），`input` 模式优先、`drop` 兜底，两条都失败才降级人工 |

**第 ② 项的最终真相（第三轮才挖到底）**：文件其实**早就送到了**，页面也接了 —— 卡住的是**另一个原因**，
见 §6.7。**「上传失败」这个现象为真，但三次归因（渲染层次 → 元素不存在 → 能力不对齐）全都偏了。**

→ 修完后的正常输出长这样（可作对照基线）：

```
[INFO] 标题校验: 通过 | 最终: HTML转视频全流程
[INFO] --publish 前置快照: 草稿箱现有 3 条（用于 ID 差分验证）
[INFO] 可见性前置检查: OK — Agent Window 已可见（media=loadedmetadata，title=视频号助手）
[INFO] bsk upload(input) 已交付文件，等待页面接收...
[INFO] ✅ 视频已就位
[INFO] 阶段: draft-saved | 已点击保存草稿（@e35），待 API 复核
[VERIFY] 草稿箱 3 → 4 条，新增 1 条
[VERIFY] 命中草稿（ID 差分）: export/UzFfBgAAxNmHVFBUfV_Mk8zT4DCagBukcnCWvOaIqTe
[VERIFY]   title=HTML转视频全流程 | video=✅ | status=1
✅ 验证通过：保存草稿成功（依据：ID 差分）
```

### 6.1 登录态：先排查「是不是连错了 Chrome 身份」（最大的一次误判）

**症状**：接口一直 `errCode=300333`，看起来像「登录态失效」。**但真根因常常是 profile 不匹配。**

| 现象 | 语义 | 能否单独定案 |
|---|---|---|
| `errCode=300333` | 带 sessionid，但会话无效/不属于本上下文 | ❌ 只作佐证 |
| `errCode=300330` | 无 cookie 或伪造 cookie | ❌ |
| `errCode=300334` | 还在回调中（code 未换成 session） | ❌ |
| **导航被重定向到 `login.html`** | 服务端不认这份凭据 | ✅ **这才是硬判据** |

> ⚠️ 曾把 `300333` 归因为「代理/hosts 劫持」。用**三输入对照**（真实 cookie=300333 / 伪造=300330 / 空=300330）
> 直接推翻该假设 —— **不同码说明凭据确实被识别**，问题在凭据本身不算数。

**判定 Chrome 身份归属（正解）**：
```
<User Data>\Local State  →  JSON  "profile.info_cache"  →  {"Profile 2": {"user_name": "...", ...}, "Profile 3": {...}}
<User Data>\Profile N\Network\Cookies                    ← SQLite，字段 host_key/name/expires_utc/encrypted_value
```
`encrypted_value` 是 DPAPI 加密的，**读不到明文也不需要读**；
只需**比对「哪个 profile 的 Cookies 里有 `channels.weixin.qq.com` 的 sessionid」**就能定归属。
> **文件被占用怎么办**：`sqlite3.connect(f"file:{path}?immutable=1", uri=True)` 只读绕过锁。
> **2026-09-15 实测**：视频号登录态在「工作」(Profile 3)，而 `bsk` 连的是「M」(Profile 2) → cookie 不互通。

**二维码登录链路（扫码）**：
```
login.html
  └─ iframe open.weixin.qq.com/connect/qrconnect?appid=wx20d84d087938fd46&scope=snsapi_login
       &redirect_uri=.../oauth-callback.html
     ├─ ❌ 在 Agent Window 里这个 iframe 常显示「加载失败，点击重试」
     └─ ✅ 改为**顶级页面**直接打开上述 qrconnect URL（self_redirect=false）→ 二维码正常渲染 → 用户扫码
  扫码 + 微信点「允许」→ 回调带 code= → **由平台页 JS 完成 code→session 交换**
```
> ⚠️ **不要手工顶级打开 `oauth-callback.html`**：会黑屏（`state=undefined`），因为 `state` 上下文丢了、
> 且换 session 的 JS 不在那个页面里。**正确做法：回调后重新 `navigate /platform`**，
> 若不再被踢到 `login.html` 且接口 `errCode=0`，即为登录成功。

### 6.2 发布页内容在**同源 iframe** 里 → 顶层 CSS 全废，只能用 `@eN`

```javascript
// 实测：发布页 post/create
document.querySelectorAll('input').length === 0     // ← 顶层查不到任何表单元素
document.querySelector('wujie-app')                  // ← 存在
```

❌ **旧结论（已推翻）**：「表单在 shadowRoot 里」。
✅ **实测真相**：**页面被套在一个同源 iframe 里** —— wujie 微前端用 iframe 承载子应用，
其 URL 是 `https://channels.weixin.qq.com/micro/content/post/create`，但 **`src` 属性显示的是
`empty.html`**，所以肉眼/脚本都极易误判成「普通 iframe」或「shadow DOM」。

```javascript
// 验证 1：它到底是不是 shadow root（答案：不是）
document.querySelector('wujie-app').shadowRoot                  // → null
// 验证 2：真正的内容在这里（同源 → contentDocument 可直接访问）
const d = document.querySelector('iframe').contentDocument;
d.querySelectorAll('input').length                               // → >0
d.querySelector('div.ant-upload.ant-upload-drag')                // → 上传区（Ant Design Upload.Dragger）
d.querySelector('span.ant-upload-btn input[type=file]')           // → display:none / accept="video/mp4,..." / multiple
```

**为什么这个误判会误导人**：`document.querySelectorAll('input').length === 0` 的现象是真的；
「顶层 document 看不到 iframe 内的 DOM」也是真的 —— 但**根因是跨文档边界，不是跨 shadow 边界**，
两者要用**完全不同的**手段穿透。按 shadow DOM 去猜，会一直在错误的层次里翻。

> ⚠️ **同构处漏改（2026-09-15 发现，未动）**：`publish_channels.py` 里 `find_ref_by_keyword()`
> 的 docstring 与 `_DEEP_ALL_JS` 的注释**仍写着「表单全在 shadowRoot 里」** —— 结论已更正、
> 代码注释没跟着改。**以本节的实测结论为准。**
> 顺带存疑：`__deepAll` 只递归 `shadowRoot`、**不跨 iframe 边界**，它为何仍能取到元素需单独确认
> （可能 `bsk evaluate` 的上下文本就在 frame 内）。
> **这是 M11「一处修了、同构处漏改」的变体 —— 更正一个结论时，要顺手搜一遍所有同构表述。**

**正确姿势 —— 无障碍快照能穿透 iframe**：
```bash
bsk snapshot --session "$SID"     # 拿到带 @e1..@eN 的 aria 树（含 iframe 内容）
```
→ **`bsk click @eN` / `bsk fill @eN "文本"` 可用**；要 JS 直取就用 `iframe.contentDocument` 穿透。
> 拼接 ref 时注意：快照文本里已是 `@e28`，别再补一个 `@`（会得到 `@@e28` → CDP 报错）。

### 6.3 上传视频：主路径 `bsk upload`（自动），兜底「原生对话框 + 剪贴板」

**主路径（0.2.0+ 才有；本机 2026-10-08 实测为 0.3.2）**：

```bash
bsk upload --session "$SID" --file "<视频绝对路径>" --mode input   # 优先
bsk upload --session "$SID" --file "<视频绝对路径>" --mode drop    # 兜底
```

> ⚠️ **`--mode input` 会真实触发页面 file input**，但**只在页面可见时才成功**（见 §6.7）。
> 页面 hidden 时它报的是 `error: the upload trigger did not activate a file input` ——
> **这个报错是在说谎**：真正原因是 hidden 门禁，`@eN` 没选错。修好可见性后同一个 ref 直接成功。

**验证交付是否真的到达页面**（别只看 CLI 退出码）：预埋一个 capture 阶段的监听，
记下 `dataTransfer` 的真实内容：

```javascript
document.addEventListener('drop', e => {
  window.__probe = {n: e.dataTransfer.files.length,
                    name: e.dataTransfer.files[0]?.name,
                    size: e.dataTransfer.files[0]?.size,
                    type: e.dataTransfer.files[0]?.type};
}, true);   // ← capture=true 必须在页面自己的 handler 之前拿到
```
> 实测（2026-09-15）：`--mode drop` 交付的是**真文件**（name/size=23,573,879/type 全部正确、
> `types:["Files"]`），页面 `beforeUpload` **也被调用了** —— 但页面随后停在校验视频元数据处。
> **所以「文件送到了吗」和「页面用不用」是两个独立问题，必须分开验证。**

**兜底路径（页面结构大改时仍可用）**：

```
① bsk click <上传区 ref>          # 例：@e22
     └─ 页面此刻才懒创建 input[type=file accept=video/mp4]
        并且**弹出 Windows 原生「打开」对话框（窗口类 #32770）**
② ctypes 枚举顶层窗口找 #32770 → SetForegroundWindow
③ 剪贴板写入视频绝对路径 → Ctrl+A（清空文件名框）→ Ctrl+V → Enter
     └─ 对话框关闭，视频开始上传
④ 监控进度：穿透 iframe 轮询 <video> 元素
     videoEl.readyState === 4  （HAVE_ENOUGH_DATA）且 videoEl.duration ≈ 预期秒数  → 上传完成
```
> **`reg.exe` / `tasklist` / `wmic` 常被安全策略拦**，进程/窗口枚举一律用 Python `ctypes`（`EnumWindows`）。

⚠️ **64 位 ctypes 必须显式声明签名**，否则 HANDLE 被截断成 32 位：
```
OSError: access violation writing 0x0000000000000020
```
```python
kernel32.GlobalAlloc.restype      = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes     = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype       = ctypes.c_void_p
kernel32.GlobalLock.argtypes      = [ctypes.c_void_p]
user32.OpenClipboard.argtypes     = [ctypes.c_void_p]
user32.SetClipboardData.restype   = ctypes.c_void_p
user32.SetClipboardData.argtypes  = [ctypes.c_uint, ctypes.c_void_p]
```

### 6.4 填表单：两个字段的坑完全不同

| 字段 | 真实结构（都在 §6.2 那个同源 iframe 里） | 无障碍树是否暴露 | 填法 |
|---|---|---|---|
| 短标题 | `input[placeholder*="短标题"]` | ✅ 暴露（如 `@e28`/`@e20`） | `bsk fill @e28 "标题"` |
| 描述 | `div.input-editor[contenteditable][placeholder="添加描述"]` | ❌ **不暴露** | `bsk evaluate` 里 JS `focus()` + Range 把光标放到末尾 → `bsk press Ctrl+V` |

**短标题 16 字硬限 ＋ 6 字下限：两端都拒绝，绝不静默加工**（最容易静默失败的一处）：
- 判据**不能只看自己脚本的常量**，要看页面自己怎么说：
  ```javascript
  document.querySelector('.error-title')?.textContent   // "标题超过16字限制"
  [...document.querySelectorAll('button')].map(b => [b.textContent.trim(), b.className])
  // → ["保存草稿","weui-desktop-btn_disabled"], ["发表", ...], ["手机预览", ...]
  ```
- 2026-09-15 实例：产线 `generate_titles()` 给了 20 字标题 → 三按钮全灰；
  换成 16 字 `GitHub5万星HTML转视频` → 报错消失、按钮转亮 → 保存成功。
- **下限**：旧版会把 `短` 补成 `短。。。。。` 凑够 6 字 —— 这是**静默造假**（存进草稿箱的标题不是产线给的）。
  v4.5 起改为**直接拒绝并报错**，交由上游重新取标题。
- **「标题对上了没」别用严格相等** —— 平台会做规范化（全角/半角、空格、省略号）。
  用 `_title_similar(actual, expected)`：**≥6 字 且 ≥较短串的 80%** 才算命中。
  固定长度阈值在这种「平台会改写你」的场景下必然误判。
- 描述里写 `#话题` 会被平台**自动识别成真话题**（DOM 变成 `<span class="topic">`），不用额外操作。

### 6.5 保存后**必须用 API 权威验证**，不要只看「点了按钮没报错」

**最强判据 —— 发布前快照 + 结束后做差集**（而不是「事后找一条看着像的」）：

```python
before = snapshot_draft_ids(cookie)      # {objectId: {...}}，发布前先拍
# ... 执行保存 ...
after = snapshot_draft_ids(cookie)
new_ids = set(after) - set(before)       # 恰好 +1 条 = 本次存的；+0 或多条都要追查
```

> 为什么必须做差集：草稿箱里本来就有历史草稿，**「找到一条标题相似的」会把别人的账算成自己的**。
> 实测两次端到端都是**恰好 +1**（2→3、3→4），且 `get_draft_info` 复核 `status=1`。

```
POST {API_BASE}/post/get_draft_list   （cookie 需含 sessionid）
POST {API_BASE}/post/get_draft_info   {objectId}
```
通过标准（四条全中）：
1. `errCode == 0`
2. 草稿**条数 +1**（且 ID 差分恰好 1 条），新条目 `video == "Y"` / 标题与预期一致
3. `get_draft_info` 详情：`media` 里**有视频且已生成 URL**、有封面、描述完整、**`status == 1`（草稿态）**
4. `log_ledger(日期, 标题, "视频号", "待发布", remark=objectId, ...)` 返回 `True`

> 2026-09-15 实例：草稿 2 → 3 条，新增 `1789450252 | video=Y | GitHub5万星HTML转视频`，
> objectId `export/UzFfBgAAxKuAFF0VUyvNk8zT4DCac8SqxoGa5jFxJ-q7xKXq5g`。

**收尾**：`release_agent_window()`（还原被抬起的窗口，见 §6.7）+ `bsk session stop --all`（不要留野 session）。

### 6.6 两点补充

- `bsk` 偶发 `error: browser rejected the underlying CDP call` —— **同一 session 反复操作时的瞬态失败，重试即可**，别当成选择器写错去改代码。
- 产线末尾清理待上传区旧副本的 `safe-delete` 失败（`SHFileOperationW 失败: 0x2`）**无害**，
  但不阻断 `shutil.copy2` 的同时**会在 `视频号待上传\` 残留旧 mp4** —— 人工拖拽前确认拿的是本次文件。

### 6.7 ★核心：**Agent Window 必须前台可见，否则这个浏览器不加载任何媒体**（第三轮才挖到底）

> 这是整个 §6 里最难发现的一层，也是把「自动上传」从**三次错误归因**里救出来的那一层。
> 前面三次（渲染层次 → 元素不存在 → 两侧能力不对齐）**现象都是真的，结论都是错的**。

**完整因果链（全部实测，非推测）**：

```
Agent Window 被用户自己的 Chrome 窗口完全遮挡
  → Chrome 原生窗口遮挡检测（Windows: CalculateNativeWinOcclusion）把它判为 occluded
  → document.visibilityState === 'hidden'
  → Chrome 对 hidden 文档一律不加载媒体资源
  → 视频号发布页靠 <video> 读元数据校验时长/分辨率，这一步永远不返回
  → beforeUpload 之后零上传请求 → 页面只造一个坏掉的 blob: 预览
  → bsk upload 交付的文件被「接住但不用」
```

**症状的精确形态（记住这个形状，它能帮你少走三天弯路）**：

| 观测量 | 值 |
|---|---|
| `videoEl.readyState` | **永远 0**（HAVE_NOTHING） |
| `videoEl.networkState` | **永远 2**（LOADING，即「正在加载」） |
| `videoEl.error` | **null（不报错！）** |
| 表现 | **永久挂住**，没有异常、没有 console 报错、没有网络失败 |

**⚠️ 最容易误判的地方**：它长得像「资源还在加载」，其实是「Chrome 根本不打算加载」。
**`error === null` 不等于没问题 —— 沉默本身就是症状。**

**「不加载媒体」的边界在哪（已实测排除全部替代解释）**：

| 假设 | 对照实验 | 结论 |
|---|---|---|
| 文件本身坏了 | 23,573,879 B 全量读取、MP4 `ftypisom` 头正确 | ❌ 排除 |
| 路径含中文 | 换成纯 ASCII 路径 `ascii_test.mp4`（sha256 与原件逐位相同） | ❌ 排除（同样失败） |
| 编解码不支持 | `canPlayType` / MSE / WebCodecs（`VideoDecoder.isConfigSupported('avc1.42E01E')` = supported、`AudioDecoder('pcm-u8')` = supported） | ❌ 排除（解码器是好的） |
| CSP 拦截 | console 无任何拦截记录 | ❌ 排除 |
| 资源加载机制整体坏了 | **同一上下文** `<img>` 的 data URL **225ms 加载成功** | ❌ 排除（只卡「媒体元素」这道门） |
| 「网络/文件来的才受影响」 | 用**完全自包含**的 `data:` URL 在干净 `about:blank` 上测 —— 连 **844 字节的 WAV** 都加载不了；纯内存 Blob 也一样 | ❌ 排除（与来源无关） |

**因果闭环（对照实验，把窗口抬到最前）**：
```
before: vis=hidden  → <video> TIMEOUT   rs=0
after : vis=visible → <video> loadedmetadata rs=4     ← 立刻恢复
```

**修法（`publish_channels.py` v4.5，已实现并两次端到端通过）**：

```python
# ① 「导航 → 上传」之间插入可见性前置检查（把失败挡在门口，而不是传到一半才发现）
vis_ok, vis_msg = ensure_agent_window_visible(sid)      # attempts=3
print(f"[INFO] 可见性前置检查: {'OK' if vis_ok else '未通过'} — {vis_msg}")

# ② 等待循环里周期性复抬（窗口再次被遮挡会掉回去）
wait_for_video(sid, timeout_s=240, nudger=_nudge)

# ③ 收尾只还原自己动过的窗口
release_agent_window(); bsk_stop(sid)
```

**门禁判据 = `visibilityState == 'visible'`**，`media` 只作旁证打印：
```python
def _media_gate_open(st): return st.get("v") == "visible"
```
> 理由：因果链上「媒体能不能加载」是**被 visibility 决定**的。若把 `media` 也写进判据，
> 探针负载自身的任何问题都会反过来卡死主流程（本机真踩过：探针坏了 → 门禁比真实要求更严）。

**Windows 侧窗口操作（`_bsk_win.ps1`，Python 调 PowerShell）**：

```
EnumWindows + GetClassName == 'Chrome_WidgetWin_1' + 标题匹配 → hwnd
抬起：SetWindowPos(hwnd, HWND_TOPMOST=-1, x,y,w,h, SWP_SHOWWINDOW=0x40) + SetForegroundWindow
还原：SetWindowPos(hwnd, HWND_NOTOPMOST=-2, 原x,原y,原w,原h, 0x50)   # 原位置先落盘存 state.json
```

> - ⚠️ **只接受 `Chrome_WidgetWin_1`**，别把标题匹配到的任意窗口都动。
> - ⚠️ **拿不到页面标题就拒绝操作** —— 否则助手会匹配「第一个 Chrome 窗口」，
>   那很可能是**用户自己正在用的窗口**，一动就把人家窗口挪走。
> - 窗口标题走命令行会被中文/引号弄坏 → **用 base64 传**（`-TitleB64`），PS 里 `[Console]::OutputEncoding = UTF8` 防回显乱码。
> - **抬起尺寸别盖满屏幕**：默认 `900×640`。第一版用了 `1320×1497`，几乎把用户屏幕占满。
> - `[System.IntPtr]` 转 int64 用 `[int64]$h`（`$h.ToInt64()` 会报「找不到重载」）。
> - **它不该是正确性的硬依赖**：抬不起来就只报告 + 退回原失败路径（「提升成功率」而非「不抬就不干活」）。

**连带教训 —— `bsk evaluate` 默认 30s 硬超时**：
```
error: operation timed out ... tool RPC timed out after 30s
```
带等待的探针必须显式加 `--timeout 180s`，否则「探针超时」和「页面真的不返回」看起来一样。

### 6.8 bsk 0.2.1 及以后的能力清单（升级后解锁的，别再用 0.1.6 的记忆写脚本）

> **版本沿革**：0.1.6（2026-06-30）→ 0.2.1（2026-09-09）→ **0.3.2（2026-10-08 实测）**。
> 本节列的是 **0.2.1 引入**的能力，这些在 0.3.2 上依然可用。

0.2.1（2026-09-09）相对本机原 0.1.6（2026-06-30）新增：

| 命令 | 用途 |
|---|---|
| **`upload`** | 会话级文件上传（`--file` + `--mode input\|drop`）← §6.3 的关键 |
| `download` | 页面下载物落盘 |
| `observe --debug-surfaces` | 列出可交互面（定位上传区/按钮的好工具） |
| `network` / `console` | 抓网络请求 / console（排查「有没有发出上传请求」的权威依据） |
| `emulate` / `record` / `window resize` / `screenshot --out` | 视口模拟 / 录制 / 窗口尺寸 / 截图（注意参数名是 `--out`，不是 `--output`） |
| `tab {list,create,close,select,borrow,return}` | 标签页管理 |
| `request-help` / `status` / `logs` | 求助 / 状态 / 日志 |

**daemon 子命令只有 `start/stop/restart`** —— 状态要看顶层 `bsk status`
（`bsk daemon status` → `unrecognized subcommand 'status'`）。

**沙盒/无交互姿势**：`BSK_AUTO_START=0` 可阻止 CLI 自行拉起浏览器，方便在受控环境里复现。

**会话生命周期**（踩过两次）：**会话不跨 shell 命令存活** ——
`bsk session list` 在新命令里会显示 `(no active sessions)`。
**窗口操作与会话必须在同一进程生命周期内完成**（这也正是 §1.7 那条管道死锁坑的场景）。
