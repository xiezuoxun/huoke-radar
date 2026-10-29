# -*- coding: utf-8 -*-
"""
线索雷达 · 一键打开工作台
================================
双击「打开线索雷达」时跑的就是它，做三件事：

  1. 看本地采集服务是不是已经在跑（在跑就复用，不重复起）
  2. 没在跑 → 用 pythonw 无窗口拉起 agent_server.py --idle-exit 20
     （关掉工作台页面后 20 秒，服务自己退出，不留后台残留）
  3. 打开浏览器到工作台地址

为什么要有这个入口：网页跑在浏览器沙箱里，**没有任何办法启动本机程序**。
所以「打开工作台」这个动作必须由一个本地入口触发，不能靠网页自己。

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_PORT = 8765
IDLE_EXIT = 20          # 页面全关后多少秒退出

# 为什么要开本地页面而不是云端页面：
# 云端是 https，页面 fetch http://127.0.0.1:8765 会被 Chrome 的混合内容 / Private Network
# Access 策略拦掉 —— 服务端 CORS 写得再全也没用，表现就是「重新检测永远连不上」。
# 改成由本地服务自己托管页面（/app），页面与 API 同源，零跨域，稳定通。
WORKBENCH_URL = "http://127.0.0.1:%d/app"
CLOUD_URL = "https://www.workbuddy.cn/space/d/8Ga6KQowmacfSimrnvZHUh"


# 本机回环地址绝对不能走代理：系统里一旦有 http_proxy（公司网络、VPN、抓包工具都会设），
# urlopen 会把 127.0.0.1 也丢给代理，代理回 502 → 被误判成「服务没起来」→ 反复重启。
# 所以健康检查固定用空代理 opener。
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _health(port, timeout=1.5):
    try:
        with _NO_PROXY_OPENER.open("http://127.0.0.1:%d/health" % port, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        return d if isinstance(d, dict) and d.get("ok") else None
    except Exception:
        return None


def _log_tail(path, n=12):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [L.rstrip() for L in f if L.strip()]
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def _interpreter():
    """优先 pythonw.exe（真无窗口）；这个 venv 没装 pythonw，
    那就退回 python.exe + DETACHED_PROCESS，效果一样：不弹窗口、不挂任务栏。"""
    py = sys.executable
    cand = os.path.join(os.path.dirname(py), "pythonw.exe")
    return cand if os.path.exists(cand) else py


def _spawn(port):
    """无窗口、脱离父进程地拉起采集服务，并等它就绪。"""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    # 输出不再丢进黑洞：写 debug/agent.log，出问题才有得查
    dbg = os.path.join(HERE, "debug")
    os.makedirs(dbg, exist_ok=True)
    logpath = os.path.join(dbg, "agent.log")

    env = os.environ.copy()
    # 子进程也排除回环代理：采集器要访问抖音/小红书，但绝不能把 127.0.0.1 也代理走
    env["no_proxy"] = "127.0.0.1,localhost"
    env["NO_PROXY"] = "127.0.0.1,localhost"

    args = [_interpreter(), os.path.join(HERE, "agent_server.py"),
            "--port", str(port), "--idle-exit", str(IDLE_EXIT)]
    with open(logpath, "a", encoding="utf-8", buffering=1) as lf:
        lf.write("\n===== %s 启动 port=%d =====\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S"), port))
        lf.flush()
        subprocess.Popen(
            args,
            cwd=HERE,
            env=env,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.DEVNULL,
            stdout=lf,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )

    # 服务冷启动要导入 playwright，给足 25 秒
    for _ in range(50):
        if _health(port, timeout=1.0):
            return True
        time.sleep(0.5)
    return False


def main():
    argv = sys.argv[1:]
    port = DEFAULT_PORT
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except Exception:
            port = DEFAULT_PORT
    no_open = "--no-open" in argv          # 自检用：只起服务不开浏览器
    do_stop = "--stop" in argv             # 关闭服务

    if do_stop:
        if not _health(port):
            print("[i] 采集服务本来就没在运行。")
            return 0
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/quit" % port, data=b"{}",
                headers={"Content-Type": "text/plain;charset=UTF-8"}, method="POST")
            with _NO_PROXY_OPENER.open(req, timeout=5) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            if d.get("ok"):
                print("[ok] 采集服务已关闭。")
                return 0
            print("[x] 关闭失败：%s" % d.get("error"))
            return 1
        except Exception as e:
            print("[x] 关闭失败：%s" % e)
            return 1

    h = _health(port)
    reused = bool(h)

    if not h:
        if not _spawn(port):
            print("[x] 采集服务没能起来。")
            print("    日志：%s" % os.path.join(HERE, "debug", "agent.log"))
            tail = _log_tail(os.path.join(HERE, "debug", "agent.log"))
            if tail:
                print("    ---- 日志尾部 ----")
                print(tail)
            print("    手动排查：双击桌面上的「启动采集服务.bat」看窗口里的报错")
            try:
                input("\n按回车关闭…")
            except Exception:
                pass
            return 1
        # 再确认一次：有的环境会立刻杀掉刚拉起的子进程，早发现比让用户对着空白页猜好
        time.sleep(0.8)
        h = _health(port)
        if not h:
            print("[x] 服务启动后又退出了（子进程被清理）。")
            print("    日志：%s" % os.path.join(HERE, "debug", "agent.log"))
            tail = _log_tail(os.path.join(HERE, "debug", "agent.log"))
            if tail:
                print("    ---- 日志尾部 ----")
                print(tail)
            print("    改用前台方式：双击桌面上的「启动采集服务.bat」（窗口保持开着）")
            return 1

    if not no_open:
        webbrowser.open(WORKBENCH_URL % port)

    state = "登录态有效" if (h or {}).get("logined") else "未登录（需先跑一次 init_login.bat）"
    print("[ok] 采集服务%s · %s" % ("复用已在运行的实例" if reused else "已启动", state))
    print("     工作台已打开：%s" % (WORKBENCH_URL % port))
    print("     关闭工作台页面后 %d 秒，服务会自动退出。" % IDLE_EXIT)
    if not no_open:
        time.sleep(1.2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
