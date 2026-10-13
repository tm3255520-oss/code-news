---
name: hyperframes-local-transcribe
description: 本机**没有 whisper-cpp / WhisperX** 时，给 HyperFrames 字幕链路（embedded-captions / talking-head-recut / music-to-video）补上「音频 → 词级 transcript.json」这一步的实操手册。当出现「embedded-captions 报转录失败」「transcribe.cjs 报 hyperframes CLI not found」「skills 里没有 whisper-cpp 怎么办」「给这个视频加字幕但没有稿子」「离线做词级转录」「whisper 的结果怎么喂给 hyperframes」时使用。核心是**预置式绕过**——transcribe.cjs 开头若发现 `<project>/transcript.json` 已是合格 word-level（且有 language_code）会**直接 return，两个转录引擎一个都不碰**，所以只要自己产一份合格文件即可，全程不需要装任何额外工具。内含本机 whisper 的确切调用方式、CRLF 解析 bug、list/dict schema 不兼容、hfRoot 路径判据失效、`--initial_prompt` 纠正不了专名这**五个实测坑**与验收判据。**边界**：只管「转录这一环怎么在本机落地」；字幕的视觉设计/身份选择走 embedded-captions 本尊；产线整体故障走 hermes-pipeline-repair；whisper 引擎本身的升级/共享依赖树走 workbuddy-capability-audit。
agent_created: true
version: 1.0.0
tags: [hyperframes, captions, whisper, transcribe, 字幕, 转录, 离线, embedded-captions]
---

# HyperFrames 本地字幕转录（无 whisper-cpp / 无 WhisperX）

> 实测日期：2026-09-16。全部结论来自本机实跑（真产线音频 75s + 真产线视频 49.9s），非推断。
> 落地脚本：`scripts/whisper-to-transcript.py`（本 skill 内，自带校验与回读）

## 0. 这个 skill 管什么、不管什么

**管**：手上有一段音频或视频、**没有现成稿子**，要给 HyperFrames 的字幕工作流（`embedded-captions` / `talking-head-recut` / `music-to-video`）产出一份它能吃的 `transcript.json`。

**不管**：字幕长什么样、选哪个视觉身份 —— 那是 `embedded-captions` 本尊的事。

---

## 1. 一句话原理（为什么这条路走得通）

`embedded-captions/scripts/transcribe.cjs` 的开头有一段**预置检查**：

```js
// 第 125–148 行
const d = JSON.parse(fs.readFileSync(out, "utf8"));   // out = <project>/transcript.json
const wordShaped =
  d && Array.isArray(d.words) && d.words.length > 0 &&
  d.words.every((w) => w && typeof (w.text ?? w.word) === "string" &&
                        Number.isFinite(w.start) && Number.isFinite(w.end) &&
                        w.end < 36000);          // ← 排除毫秒格式
if (wordShaped && d.language_code) {
  console.log("[transcribe] already normalized, skipping");
  return;                                        // ← ★ 直接退出，引擎一个都不碰
}
```

**只要这份文件合格，函数在第 139 行就 `return` 了** —— 后面的 WhisperX（走 `uvx`）和
whisper.cpp（走 `hfRoot()`）**根本不会执行**。所以「没有 whisper-cpp」这件事，在**预置**这条路上完全不构成障碍。

上游 SKILL.md 第 255 行也自己写明了这个回退口：
> Transcription = WhisperX via `uvx` … **Falls back to an existing word-level `transcript.json` if present.**

**这不是绕路，是官方设计好的入口。**

### 那么谁来产这份文件

本机的 **openai-whisper（Python 版，已装）** —— 它不是 whisper-cpp，但同样能产出带词级时间戳的结果。
本 skill 的脚本负责把它转成上游要的 schema。

---

## 2. 本机环境事实（实测）

| 项 | 实况 |
|---|---|
| whisper 装在哪 | **系统 Python** —— `C:\Users\Administrator\AppData\Local\Programs\Python\Python313\Scripts\whisper.exe` |
| ⚠️ managed python 有吗 | **没有**。`~/.workbuddy-ai/binaries/python/...` 里 `import whisper` 直接失败 → **必须用系统 Python 那条路径** |
| 模型缓存 | `~/.cache/whisper/`：`large-v3-turbo.pt`（1.62 GB）、`small.pt`（484 MB） |
| 默认模型 | whisper CLI 自己的默认是 `turbo` |
| 速度基准 | **约 1× 实时**（CPU，FP32）：75 s 音频 → 72 s；`FP16 is not supported on CPU` 的警告是**正常的**，不是错误 |
| whisper-cpp | ❌ 未装（`hyperframes doctor` 会报缺） |
| WhisperX / whisperx | ❌ 未装 |
| `uvx` | ✅ 有（`~/.hermes/bin/uvx`）—— 但 WhisperX 路径要 `--python 3.12` + 现下模型，首次很重 |
| hyperframes CLI | `D:\pi-agent\node_modules\hyperframes`，入口 `bin/hyperframes.mjs`，**0.8.40** |

> **跑 whisper 前先清代理**（IDE 注入的 `HTTP_PROXY` 端口每次会话都变且不转发外网）：
> `env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy <命令>`

---

## 3. 三步流程

设：`AUDIO` = 音频或视频文件，`PROJ` = embedded-captions 的项目目录（要放 `source.mp4`）。

### 步骤 ①：whisper 转录（产 SRT + 词级 JSON）

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "C:/Users/Administrator/AppData/Local/Programs/Python/Python313/Scripts/whisper.exe" \
  "<AUDIO>" \
  --model large-v3-turbo --language zh \
  --output_format all --word_timestamps True \
  --output_dir "<临时目录>" --verbose False
```

产出 5 种格式，其中要的是 `<basename>.json`（**含 `segments[].words[]`，信息最全**）。

**两个参数细节**：
- `--output_format` **只接受单值或 `all`**，写 `json,srt` 会报 `invalid choice`。
- `--word_timestamps True` 是**带值的字符串**，不是裸 flag。

### 步骤 ②：转成上游 schema

```bash
python "<SKILL_DIR>/scripts/whisper-to-transcript.py" \
  "<临时目录>/<basename>.json"  "<PROJ>"  --mode cue --lang zh
```

产出 `<PROJ>/transcript.json`：

```json
{
  "text": "全文拼接",
  "language_code": "zh",
  "engine": "local-whisper",
  "words": [ { "text": "还在手动写代码", "start": 0.0, "end": 1.2, "type": "cue" }, … ]
}
```

### 步骤 ③：验证（**必做**）

```bash
node "C:/Users/Administrator/.agents/skills/embedded-captions/scripts/transcribe.cjs" "<PROJ>"
# 期望输出： [transcribe] already normalized, skipping      退出码 0
```

看到这一行才算通过 —— 说明后续 `prepare.sh` 会**跳过转录**，直接进 safe-zones 与排版。

---

## 4. 五个实测坑（每一个都真踩过）

### 坑 1 —— `hyperframes transcribe` 导入 SRT 时**不认 CRLF**，会把整份 SRT 吃成一条

**这是最坑的一个。** 直觉上「`whisper` 出 SRT → `hyperframes transcribe xxx.srt --json` → 完事」，
但实测：

| 输入 SRT 行尾 | `wordCount` | 结果 |
|---|---|---|
| **CRLF**（whisper 在 Windows 的**默认输出**，实测 172 个 CRLF / 0 个裸 LF） | **1** | 把**整份 SRT 原文**塞进一条 `text`，所有 cue 全丢 |
| **LF** | **43** | 43 条 cue 全部正确解析 ✅ |

→ **whisper 在 Windows 上直接产出的 SRT 喂进去必然失败**，且不报错，只是静静地给你一条垃圾。
→ 本 skill 的脚本**自己解析 SRT 并在读入时把行尾归一成 LF**，从根上避开。

### 坑 2 —— `hyperframes transcribe` 导入产物是 **list**，而 `transcribe.cjs` 要 **dict**

| 产出方 | 格式 |
|---|---|
| `hyperframes transcribe <srt> --json` | `[ {text,start,end,id}, … ]` ← **list** |
| `transcribe.cjs` 期望 | `{text, language_code, words:[…]}` ← **dict** |

`transcribe.cjs` 读 list 时 `d.words` 是 `undefined` → 判为
`existing transcript.json is NOT word-level … regenerating` → **掉头去跑转录引擎** → 本机必然失败。

→ **所以不要用 `hyperframes transcribe` 导入 SRT 来产这个文件**，直接用步骤 ② 的脚本一步到位。

### 坑 3 —— `transcribe.cjs` 的 `hfRoot()` 在本机判据失效

```js
// 第 15–25 行
if (fs.existsSync(path.join(r, "packages", "cli", "dist", "cli.js"))) return r;
```

它找的是**源码仓结构** `packages/cli/dist/cli.js`，而本机 hyperframes 是 **npm 安装形态**：
`D:\pi-agent\node_modules\hyperframes\dist\cli.js` → **三个候选全不成立** → `exit(3)`
（`[transcribe] hyperframes CLI not found — set HYPERFRAMES_ROOT`）。

→ **走预置路径就永远碰不到它**（第 139 行先 return）。这也是「预置」优于「让它自己转录」的又一个理由。

### 坑 4 —— 纯 LF、无 BOM 是硬要求

上游 `.gitattributes` 是 `* text=auto eol=lf`。落盘务必 `newline="\n"`，别让 Windows 给你转成 CRLF。
本 skill 的脚本已用 `open(..., newline="\n")` 固定。

### 坑 5 —— `--initial_prompt` **纠正不了专有名词**，别在这上面浪费时间

实测（真产线视频，真值应为 **Suno V5**）：

| 方式 | 结果 |
|---|---|
| 不带 prompt | `Cinov5` ❌ |
| `--initial_prompt "Suno V5、AI音乐生成、短视频BGM、demo。"` | `Ceno V5` ❌ **仍错**，且**分段被搅乱**（原本换行的 cue 变成逗号连成一片） |

→ **`initial_prompt` 对中文里的英文专有名词基本无效**，还会顺带改变解码分段。
→ **不要指望用 prompt 修专名。** 唯一可靠办法是**人工校对 `text` 字段**
（上游 SKILL.md 第 92 行把这一步列为硬门禁，原因正在于此）。
→ 专名错的字幕比没字幕更糟 —— 校对不过就改，改不了就别上。

---

## 5. 验收判据（四级，都要有真实输出）

1. **脚本自检**：`whisper-to-transcript.py` 打印 `回读校验: 通过 ✓`（它写完会回读并复算 `words` 条数与 `language_code`）
2. **schema 合规**：复刻 `transcribe.cjs` 第 127–138 行校验 —— `words` 非空、每条 `text` 是非空串、`start`/`end` 是有限数、**`end < 36000`**（这条专抓毫秒格式）、时间单调递增
3. **上游接受**：`transcribe.cjs` 输出 `already normalized, skipping`，**退出码 0**
4. **人工抽检**：`text` 字段读一遍 —— **上游 SKILL.md 第 92 行明确要求这一步**（「Sanity-read `transcript.json` before authoring」）。
   非母语/重口音可能转出**自信的胡话**，喂进字幕比没字幕更糟。

> ⚠️ 上游还有一条**决策门禁**：静音或不足 3 秒的音频上 whisper 会**幻觉**（经典是凭空生成 "Thank you."）。
> `transcribe.cjs` 的 `meanVolumeDb < -45 dB` 会告警。**走预置路径时这条守卫不会执行**（因为提前 return 了），
> 所以**你得自己看**：`ffmpeg -i <audio> -af volumedetect -f null -`，真实语音约 **-16 ~ -26 dB**。

---

## 6. 已知边界：`--mode cue` 还是 `--mode word`

**决定因素是语言，不是喜好。**

| 模式 | 一条 = | 中文实测 | 用在哪 |
|---|---|---|---|
| `cue`（**默认，中文推荐**） | 一个 segment / 一条 SRT cue（整句） | 43 条，**句级**，字幕按句上屏 | 整句字幕、verbatim 烧录 |
| `word` | 一个词 | **285 条，按单字切！**（「还在手动写代码」→ 还/在/手/动/写/代/码） | 英文逐词高亮 |

中文的 `word` 级切分是**按单字**的 —— 直接拿去逐词上屏会**一字一闪**，不可用。
上游 `--preserve-cues` 的文档原文也正是点名这个场景：
> Use when exporting an already-cued transcript whose entries have no internal spaces, **e.g. single-word or CJK captions**.

**所以：中文默认 `cue`。** 脚本在 `--mode word` 且检测到 CJK 时会打印警告。

> 若确实需要中文**逐词**高亮，正确做法不是在字级硬上，而是把字**合并成 2–5 字的词组**
> （`embedded-captions` SKILL.md 第 127 行：「grouped 2–5 at clause boundaries」）。
> 这一步本 skill 不做 —— 它属于字幕创作，走 `embedded-captions`。

---

## 7. 与其他方案的关系（什么时候不走这条路）

| 方案 | 何时选它 |
|---|---|
| **本 skill（预置式）** | 本机、离线、**不想装任何东西**；中文；已有音频/视频要加字幕 ← **默认选这个** |
| WhisperX via `uvx` | 需要 wav2vec2 强制对齐的**极紧**词级时间戳（上游判据是 80 ms 级）。代价：`--python 3.12` + 现下模型，首次很重 |
| 装 whisper-cpp | 想让 `transcribe.cjs` 全自动跑通。但要先解决坑 3 的 `HYPERFRAMES_ROOT` 判据 |
| **产线自己的字幕链** | 稿子是自己写的 + TTS 合成 → **根本不需要语音识别**。产线 `04_subtitle_generator.py` 用「字数估时 + ffprobe 校准」更快更准，**这是该保留的优势，别去替换它** |

---

## 8. 一页速查

```bash
# ① 转录（清代理；输出 all 才能拿到词级 json）
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  "$W" "<AUDIO>" --model large-v3-turbo --language zh \
  --output_format all --word_timestamps True --output_dir "<TMP>" --verbose False

# ② 转换（中文用 cue）
python "<SKILL_DIR>/scripts/whisper-to-transcript.py" "<TMP>/<base>.json" "<PROJ>" --mode cue --lang zh

# ③ 验证（看到 skipping 才算过）
node "C:/Users/Administrator/.agents/skills/embedded-captions/scripts/transcribe.cjs" "<PROJ>"
```
