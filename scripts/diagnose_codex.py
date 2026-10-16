#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex DeepSeek 问题诊断和修复
直接检查并启动路由器服务
"""
import os
import sys
import socket
import subprocess
import time
import json
import urllib.request
import urllib.error

def check_port(port, timeout=1):
    """检查端口是否开放"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result == 0
    except:
        return False

def read_env_key(key_name):
    """从 .env 读取 key"""
    env_file = os.path.expanduser(r"~\.hermes\.env")
    print(f"  读取文件：{env_file}")
    try:
        with open(env_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key_name + "="):
                    return line.partition("=")[2].strip()
    except OSError as e:
        print(f"  错误：{e}")
    return None

def test_router():
    """测试路由器响应"""
    try:
        req = urllib.request.Request("http://127.0.0.1:8970/v1/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return True, data
    except Exception as e:
        return False, str(e)

def start_router():
    """启动路由器"""
    router_script = r"C:\Users\Administrator\Documents\code-news\scripts\codex_model_router.py"
    python_exe = r"C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe"

    if not os.path.exists(python_exe):
        python_exe = sys.executable

    if not os.path.exists(router_script):
        print(f"错误：路由器脚本不存在：{router_script}")
        return False

    print(f"启动路由器：{python_exe} {router_script} --port 8970")

    # 先设置环境变量
    os.environ["DEEPSEEK_API_KEY"] = read_env_key("DEEPSEEK_API_KEY") or ""

    proc = subprocess.Popen(
        [python_exe, router_script, "--port", "8970"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        cwd=os.path.dirname(router_script)
    )
    print(f"进程启动，PID={proc.pid}")
    return True

def kill_old_router():
    """杀死旧的路由器进程"""
    print("检查旧的路由器进程...")
    try:
        # 使用 taskkill 杀死占用 8970 端口的进程
        # Windows 原生 netstat 输出为本机 OEM 代码页(GBK)；自家 Python 子进程才用 utf-8
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True, text=True, timeout=5, encoding="gbk", errors="replace"
        )
        for line in result.stdout.splitlines():
            if ':8970' in line and 'LISTENING' in line:
                pid = line.split()[-1]
                print(f"  发现旧进程 PID={pid}，正在终止...")
                subprocess.run(['taskkill', '/F', '/PID', pid],
                             capture_output=True, timeout=5)
                print(f"  已终止进程 {pid}")
                return True
    except Exception as e:
        print(f"  检查失败：{e}")
    return False

def main():
    print("=" * 60)
    print("Codex DeepSeek 问题诊断")
    print("=" * 60)

    # 1. 检查 Key
    print("\n[1] 检查 DEEPSEEK_API_KEY...")
    key = read_env_key("DEEPSEEK_API_KEY")
    if key:
        print(f"  [OK] Key 已配置 (长度：{len(key)})")
    else:
        print(f"  [ERROR] Key 未找到!")
        return 1

    # 2. 检查端口
    print("\n[2] 检查端口 8970...")
    if check_port(8970):
        print("  [OK] 端口 8970 已开放")
        ok, result = test_router()
        if ok:
            print(f"  [OK] 路由器响应正常，{len(result.get('data', []))} 个模型")
        else:
            print(f"  [WARN] 路由器无响应：{result}")
    else:
        print("  [ERROR] 端口 8970 未开放 - 路由器未运行")

        # 杀死旧进程
        kill_old_router()

        # 启动新进程
        print("\n[3] 启动路由器...")
        if start_router():
            print("  等待 5 秒...")
            time.sleep(5)

            if check_port(8970):
                print("  [OK] 路由器已启动")
                ok, result = test_router()
                if ok:
                    print(f"  [OK] 路由器响应正常")
                else:
                    print(f"  [WARN] 路由器响应异常：{result}")
            else:
                print("  [ERROR] 路由器启动失败")
                print("\n请手动运行查看详细错误:")
                print(f"  python C:\\Users\\Administrator\\Documents\\code-news\\scripts\\codex_model_router.py --port 8970")
        else:
            print("  [ERROR] 无法启动路由器")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    print("\n如果路由器已启动但仍报错，请重启 Codex 桌面应用")
    return 0

if __name__ == "__main__":
    sys.exit(main())
