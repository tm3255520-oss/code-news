---
name: pipeline-health-audit
description: 给 AI 视频生产线（D:\AI-VIDEO + code-news\scripts）做全面体检，产出分级问题清单并规划分轮修复。当用户说「检查整条产线」「产线还有什么问题」「全面体检」「详细检查看存在什么问题」「把问题列出来逐项解决」「巡检」时使用。核心是「多路并行只读审计 + 逐条复核 + 分级报告 + 分轮修复」，严禁边查边改。
agent_created: true
version: 1.0.0
tags: [audit, pipeline, health-check, repair-gate, video-production]
---

# 产线体检（pipeline-health-audit）

> 适用：`D:\AI-VIDEO\` 产线本体 + `C:\Users\Administrator\Documents\code-news\scripts\` 脚本群。
> 首次落地：2026-10-06，49 脚本全量编译 + 4 路并行审计 → 出 `config\产线体检报告-YYYY-MM-DD.md`。
> 母规则：skill `repair-gate`（**只报告不动手**）。

## 一、先记住这条（与直觉相反）

**体检不是「找 bug」，是「找『错了也不报』的地方」。**

本产线画面/音频物理质量已经很高（色彩标签四齐、响度达标、转场实测生效），
**真正的风险不是「会崩」，是「崩了还告诉你成功」**。所以审计的第一优先级永远是：

1. **静默失败**：失败但返回 0 / 写盘成功但内容是错的 / 校验缺失导致坏数据进下游
2. **fail-open**：无参数或参数错误时不报错而是继续执行、覆写生产数据
3. **质检的盲区**：哪些真实缺陷是当前质检**查不出来**的（质检不报错 ≠ 没问题）

历史实证：`agnes_assemble_pro.py:479-489` 素材不足时静默产出「视频 24s / 音频 30s」的错片；
`qc_final_video.py` 退出码恒 0；`sfx_cut.py` 从「无参数崩溃」被修成「无参数静默覆写生产素材」。

## 二、执行流程（四步，不可跳）

### 第 1 步 · 全量语法编译（30 秒，先排除低级坏脚本）

```bash
cd "C:/Users/Administrator/Documents/code-news/scripts"
"C:/Users/Administrator/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe" - <<'EOF'
import glob
pats = ["agnes_*.py","qc_*.py","tts_engine.py","bgm_fit.py","gen_music.py","narration_diag.py",
        "compose_*.py","collect_material_batch.py","tts_repro_check.py","video_library.py","gen_mode.py"]
files=sorted({f for p in pats for f in glob.glob(p)})
bad=[]
for f in files:
    try: compile(open(f,encoding='utf-8').read(), f, 'exec')
    except SyntaxError as e: bad.append((f, f"line {e.lineno}: {e.msg}"))
print(f"检查 {len(files)} 个文件"); print(f"❌ {len(bad)}" if bad else "✅ 全部通过")
for f,e in bad: print("  -",f,"→",e)
EOF
```

🔴 **不要用 `py_compile.compile(f, cfile=os.devnull)`** —— Windows 下 `os.devnull` 是 `nul`，
py_compile 会报 `nul is a non-regular file`，**49 个文件会全部"失败"**（假阳性，浪费一轮）。

### 第 2 步 · 4 路并行只读审计（用 Explore 子代理）

**必须并行发**（一条消息里多个 Agent 调用）。分片方式（按数据流切，不按文件大小切）：

| 分片 | 覆盖 | 关键问题 |
|---|---|---|
| **A 音频链** | `agnes_voice.py` `tts_engine.py` `bgm_fit.py` `gen_music.py` `narration_diag.py` | 时长测量是否静默归零；TTS 不可复现的假设；「读 key/下载/探时长」是否重复实现且不一致 |
| **B 拼装质检链** | `agnes_assemble_pro.py` `qc_final_video.py` `qc_audio_scan.py` `agnes_normalize.py` | 素材不足/转场降级的静默分支；**质检退出码**；**质检盲区**；ffmpeg 滤镜坑 |
| **C 素材配置层** | `music\library` `music\sfx` `_licenses\授权台账.md` `config\*.md` `projects\*\project.json` | 台账 vs 实际文件数；ffprobe 实测参数 vs 台账数字；**文档之间互相矛盾**；引用路径是否存在 |
| **D 技能层** | 与产线相关的 skill（`stock-media-sourcing` `ffmpeg-audio-tracks` `video-model-onboarding` `d2v-channels-publish` `repair-gate`…） | **skill 写的命令/数字/路径与脚本实际是否一致**；脚本是否有同类 fail-open；SKILL.md 编码 |

给每个审计员的提示词必须包含：
- **「绝对不要修改任何文件、不要运行会写盘的命令」**
- 输出格式：**编号 + 标题 / 位置(文件:行号) / 证据(实际代码或实跑输出) / 严重度 P0-P2 / 标注是「事实」还是「判断」**
- **「不许把猜测写成事实；找不到就说找不到，不要凑数」**
- 已知问题清单（避免重复报，但要求**确认是否仍在**）

### 第 3 步 · 🔴 逐条复核（**这一步不能省**）

**审计员的结论是「它打算做的」，不是「它实际做的」。** 把 P0/P1 全部、P2 抽半数，
**自己读原码 + 实跑**核对。复核不过的**不写进报告**。

复核话术：`位置` 精确到行 → `sed -n 'A,Bp' file` 看原码 → 必要时跑一次（**用临时目录/临时根，别碰生产**）。

### 第 4 步 · 出报告 + 分轮方案

落盘 `D:\AI-VIDEO\config\产线体检报告-YYYY-MM-DD.md`，结构固定：
1. 结论摘要（P0/P1/P2 条数 + **一句话**）
2. P0 详表（六项格式）
3. P1 详表（现象/位置/证据/影响/严重度/事实或判断）
4. P2 简表（表格）
5. **已确认「无问题」**（🔴 必写 —— 避免下次重复排查，也证明审计不是走过场）
6. **分轮方案**（按投入产出比排序，每轮一个主题）
7. 未覆盖 / 存疑

## 三、分轮修复（用户的固定偏好）

用户明确要求：**「拆成 5 轮，每一轮都要我确认」**、**「减少确认密度」**。

所以报告末尾给**一张 5 轮表**，每轮：主题 / 覆盖条目 / **为什么这个顺序**。
推荐排序（2026-10-06 定）：

1. **拼装台硬闸门** —— 唯一会静默产出错片的洞，修法小收益大
2. **质检台真正门禁** —— 第 1 轮修完必须有质检兜底
3. **静默 0.0 系列** —— 测量失败静默变默认值，让全部体检形同虚设
4. **skill 层** —— 让 skill 自洽可复现、照做不崩、加防呆
5. **文档与整洁** —— 不影响运行但会带偏判断，可批量一次修

每轮走 `repair-gate`：**另起专用会话先测「问题真实存在」→ 在该会话修 → 回原会话独立复核**。

## 四、坑（本技能踩过的）

- 🔴 **`py_compile` + `os.devnull` 在 Windows 上全量假阳性**（见第 1 步）。
- 🔴 **`grep -c 'D:\\'` 在 Git Bash 里转义不可靠**（结果恒 0）→ 用 Python 正则数。
- 🔴 **`cut -c` / `head -c` 按字节切多字节 UTF-8 → 显示成乱码**，会误判「文件编码坏了」。
  判编码一律用 **Python 读 bytes**（能否 `decode('utf-8')` + 有无 BOM + 行尾）。
- 🔴 **子代理会「自证」**：它说「已实测」不等于真跑过。凡进报告的关键结论，**自己再跑一次**。
- ⚠️ **别把审计范围铺得太大**：先锁定「视频产线本体」，发布链/内容生成链/Obsidian 中枢另立一轮，
  否则一次铺开会把注意力摊薄，P0 反而被淹没。
