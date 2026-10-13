---
name: wsl-service-autostart
description: 给「跑在 WSL2 里的常驻服务」（DSH/3080、PM2 托管进程、任何监听端口的 Linux 服务）配 Windows 开机自启的实操手册。当用户说「把 XX 设置成开机自启」「重启后 XX 没了」「开机后 127.0.0.1:端口 打不开」「WSL 里的服务要自动起来」「也把我的 YY 设置成自启」时使用。含「两段链路」模型、无法执行 wsl.exe 时的只读取证法、cmd/vbs/sh 三种文件的编码与行尾硬规矩。**边界**：只管「让服务在登录后自动起来」；服务本身起不来（报错/插件冲突）走 hermes-pipeline-repair 或对应服务的自检流程。
agent_created: true
version: 1.0.0
tags: [wsl, autostart, windows, pm2, systemd, ops]
---

# WSL 服务开机自启

> 来源：2026-10-01 给 DSH（DeepSeek Harness，3080）配自启的实战（WK-20261001-03）。
> 适用于本机：Windows + WSL2 Ubuntu + systemd + PM2。

## 一、先建立正确模型：「开机自启」是两段，不是一段

这是最容易做错的地方 —— **只配了后一段，前一段空着，重启后照样打不开。**

| 段 | 位置 | 缺了会怎样 |
|---|---|---|
| **前段：Windows 唤醒 WSL** | Windows 启动文件夹 / 计划任务 | **WSL 默认不开机自启**，没人唤醒它，后面配得再对也没用 |
| **后段：WSL 内拉起服务** | systemd 服务（或 `~/.bashrc` / `rc.local`） | WSL 起来了但服务没起 |

**结论：永远先问「前段配了吗」，再动后段。**

---

## 二、前置侦察：不动手，先摸清现状

### ⚠️ 环境约束（本机实测，务必先确认）

本机安全策略的**程序黑名单**拦截了 `wsl.exe`、`schtasks.exe`、`reg.exe`，
Bash 与 PowerShell 工具**都调不动**，且规则明确禁止绕过。

**→ 操作 WSL 只能走 UNC 路径读写文件，不能执行命令：**

```
//wsl.localhost/Ubuntu/<绝对路径>        # 例：//wsl.localhost/Ubuntu/etc/wsl.conf
```

判断 WSL 内部状态靠**读文件**，不靠跑命令。下面这套只读取证法能覆盖 90% 的判断。

### 侦察清单（全部只读）

| 要查什么 | 怎么查（Bash 工具） |
|---|---|
| WSL 是否启用 systemd | `cat "//wsl.localhost/Ubuntu/etc/wsl.conf"` → 找 `[boot] systemd=true` |
| 发行版名与默认用户 | 同上，`[user] default=<user>` |
| PM2 托管了哪些进程 | `cat ".../home/<user>/.pm2/dump.pm2"`（JSON，用 python 解析出 name/script/args/cwd） |
| PM2 daemon 是否**由 systemd 拉起** | `cat ".../proc/$(cat .../.pm2/pm2.pid)/stat"` → **第 4 个字段是 ppid** |
| systemd 服务是否 enabled | `ls ".../etc/systemd/system/multi-user.target.wants/"` 看有无对应软链接 |
| 服务是否由 systemd 生成 | 读 `.../etc/systemd/system/<name>.service` 全文 |
| 用户级服务是否有 linger | `ls ".../var/lib/systemd/linger/"` —— **为空 = 用户级服务不会自启** |
| 端口是否在监听 | `netstat -ano \| grep ":<port>"`（WSL 端口经 localhost 转发，Windows 侧可见） |

### 🔑 核心判据：ppid 是不是 1

```bash
cat "//wsl.localhost/Ubuntu/proc/$(cat "//wsl.localhost/Ubuntu/home/ubuntu/.pm2/pm2.pid")/stat"
# 输出形如：282 (PM2 v7.0.3: God) S 1 282 ...
#                              ↑ 第 4 字段 = ppid
```

**ppid = 1（systemd）→ 证明服务确由 systemd 自动拉起，后段链路有效。**
ppid 是别的（比如某个 shell 的 pid）→ 说明是手工起的，**后段根本没配好**，先修后段。

这比看任何日志都硬 —— 日志只能说明「起过」，ppid 能说明「是谁起的」。

---

## 三、落地：三件套

沿用已验证的 VBS 模式（本机 pi-web 与 DSH 同款）。

### ① WSL 侧：幂等守护脚本 `~/.<service>/autostart-<svc>.sh`

**要点：不抢跑。** 如果 systemd 已经会自动拉起，脚本只做「等待 + 验证 + 兜底」，
绝不无条件 `pm2 resurrect` —— 两个 resurrect 并发会互相重启，反而制造故障。

```bash
#!/usr/bin/env bash
set -uo pipefail          # 注意：不要用 set -e，探测失败会误退

LOG="/home/<user>/.<service>/logs/autostart.log"
PORT=<端口>
export PATH="/home/<user>/.local/bin:/home/<user>/.nvm/versions/node/<ver>/bin:$PATH"

up() {                    # 优先 curl（验到 HTTP 层），退回 bash 内建 /dev/tcp
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null -m 3 "http://127.0.0.1:${PORT}/" 2>/dev/null
  else
    (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null
  fi
}

log "===== autostart begin ====="

# 阶段一：等 systemd 自动拉起（最多 60s）
for i in $(seq 1 30); do
  up && { log "OK: 就绪（等待 $((i*2))s）"; exit 0; }
  sleep 2
done

# 阶段二：兜底
log "WARN: 60s 未就绪，pm2 resurrect 兜底"
PM2_BIN="$(command -v pm2 || echo /home/<user>/.nvm/versions/node/<ver>/lib/node_modules/pm2/bin/pm2)"
"$PM2_BIN" resurrect >> "$LOG" 2>&1

# 阶段三：再等 30s 确认，失败写 pm2 list 便于排查
for i in $(seq 1 15); do
  up && { log "OK: 兜底成功"; exit 0; }
  sleep 2
done
log "FAIL: 仍未就绪"; "$PM2_BIN" list >> "$LOG" 2>&1; exit 1
```

### ② Windows 侧：启动器 `D:\<svc>\<svc>-autostart.cmd`

```cmd
@echo off
setlocal
set "LOG=D:\<svc>\<svc>-autostart.log"
set "WSL=C:\Windows\System32\wsl.exe"
set "GUARD=/home/<user>/.<service>/autostart-<svc>.sh"
set "MAXTRY=5"

echo [%date% %time%] ===== launcher invoked ===== >> "%LOG%"

rem Retry: WSL service may not be ready right after logon.
set /a TRY=0
:retry
set /a TRY+=1
"%WSL%" -d Ubuntu -u <user> -e /bin/bash %GUARD% >> "%LOG%" 2>&1
set "RC=%errorlevel%"
echo [%date% %time%] attempt %TRY% exit=%RC% >> "%LOG%"
if "%RC%"=="0" goto done
if %TRY% LSS %MAXTRY% (
  timeout /t 20 /nobreak >nul
  goto retry
)
echo [%date% %time%] FAILED after %TRY% attempts >> "%LOG%"

:done
echo [%date% %time%] ===== launcher done ===== >> "%LOG%"
endlocal
```

要点：
- 用 `-e /bin/bash <绝对路径>`（**绝对路径**，别写裸 `bash`，也别依赖 PATH）
- **加重试**：登录瞬间 WSL 服务常未就绪，不重试会随机失败
- 退出码语义要和守护脚本对齐（0 = 服务已就绪）

### ③ 启动文件夹：VBS 隐藏窗口 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\<svc>-<port>.vbs`

```vbs
' <svc> on port <port> (WSL Ubuntu + PM2) - autostart at logon (hidden window)
Set sh = CreateObject("WScript.Shell")
sh.Run """D:\<svc>\<svc>-autostart.cmd""", 0, False
```

`0` = 隐藏窗口，`False` = 不等待（不阻塞登录）。

---

## 四、编码与行尾硬规矩（踩过的坑，必查）

| 文件 | 行尾 | 编码 | 不遵守的后果 |
|---|---|---|---|
| `.cmd` / `.bat` | **CRLF** | **纯 ASCII** | LF 会让 `goto`/标签行为异常；UTF-8 中文注释在 cmd 里乱码（cmd 按 ANSI 读批处理） |
| `.vbs` | **CRLF** | ASCII | 一般能容错，但统一 CRLF 最稳 |
| `.sh`（WSL 内） | **纯 LF** | UTF-8 | 带 `\r` 会报 `\r: command not found` |

**转换与校验：**

```bash
sed -i 's/\r$//' f.cmd && sed -i 's/$/\r/' f.cmd   # 先清再转，避免 \r\r
grep -nP '[^\x00-\x7F]' f.cmd                       # 应无输出（纯 ASCII）
od -c f.cmd | head -3                               # 判行尾的权威手段
```

> ⚠️ **判行尾必须用 `od -c`**：Git Bash 的 `grep -c $'\r'` 因文本模式剥离 CR，**永远报 0**，会骗你。

---

## 五、验证

### 即时验证（幂等，随时可跑，不影响在跑的服务）

```bash
# Windows 侧：双击，或
cmd /c D:\<svc>\<svc>-autostart.cmd
# WSL 侧单独验证守护脚本
bash ~/.<service>/autostart-<svc>.sh; echo "rc=$?"
```

判据：Windows 日志出现 `attempt 1 exit=0`；WSL 日志出现 `OK: ... 已就绪`。

### 真实验证（必做一次）

重启 → 登录 → 等 1–2 分钟 → 访问 `http://127.0.0.1:<port>`。
**不做这一步就等于没验证过**（守护脚本没跑过、重试逻辑没触发过）。

---

## 六、已知边界（交付时必须讲清）

1. **是「登录自启」，不是「开机自启」**。VBS 在用户登录时触发。开机后无人登录（未配自动登录）→ 服务不会起来。要真正的开机自启得改注册表自动登录或转计划任务。
2. **用户级 systemd 服务不会自启**：`/var/lib/systemd/linger/` 为空时，`~/.config/systemd/user/` 下的服务不会随 WSL 启动。需要就 `sudo loginctl enable-linger <user>`。
3. **systemd 服务的 `ExecStart` 常硬编码路径**（本机 `pm2-ubuntu.service` 写死了 nvm 的 node 版本路径）。日后清理该路径或换 node 版本 → 服务静默失败。**交付时明确提示这一点。**
4. **自启只保证「起得来」，不保证「起得对」**。改了 profile / 插件 / 依赖后，仍须做一次冷启动自检。
5. 黑名单环境下**无法端到端自测**，必须如实告知用户，并给出上面「即时验证 + 真实验证」两步让用户跑。

---

## 相关

- 本机 DSH 的完整落地记录：`D:\Obsidian Vault\obsidian Vault\系统中枢\各Agent档案\dsh\DSH常用指令速查.md` §七
- 协同登记：`系统中枢/协同/任务台账.md`（任务 ID 形如 `WK-<YYYYMMDD>-<序号>`）
