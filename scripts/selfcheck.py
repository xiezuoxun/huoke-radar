# -*- coding: utf-8 -*-
"""
线索雷达 · 一键自检
========================
连不上工作台时双击「自检.bat」，它会按顺序检查 5 项，直接告诉你断在哪一环。

检查顺序（前一环不通，后面基本不用看）：
  1. 隔离环境的 python 在不在
  2. 8765 端口有没有被监听（= 采集服务在不在跑）
  3. /health 能不能取到（绕过代理）
  4. 抖音 / 小红书登录态在不在
  5. 有没有残留进程占着端口

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import json
import os
import socket
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
PY = r"C:\Users\lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OK, BAD, WARN = "[OK]  ", "[X]   ", "[!]   "


def listening(port, host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def health(port, timeout=3.0):
    try:
        with OPENER.open("http://127.0.0.1:%d/health" % port, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"_err": "%s: %s" % (type(e).__name__, e)}


def main():
    print("=" * 56)
    print(" 线索雷达 · 自检")
    print("=" * 56)
    print()

    problems = []

    # ---------- 1. python ----------
    if os.path.exists(PY):
        print(OK + "隔离环境 python 就位")
    else:
        print(BAD + "找不到隔离环境 python：%s" % PY)
        print("      先双击 collector\\install.bat 重装环境")
        problems.append("python")

    # ---------- 2. 端口 ----------
    alive = listening(PORT)
    if alive:
        print(OK + "端口 %d 已被监听 → 采集服务在跑" % PORT)
    else:
        print(BAD + "端口 %d 没有监听 → 采集服务没在跑" % PORT)
        print("      ★ 这就是「连接不上」的直接原因")
        print("      解决：双击桌面上的「启动采集服务.bat」，窗口别关，再回工作台刷新")
        problems.append("port")

    # ---------- 3. /health ----------
    if alive:
        h = health(PORT)
        if h.get("_err"):
            print(BAD + "/health 取不到：%s" % h["_err"])
            print("      端口在听但接口不通，可能有别的程序占用了 8765")
            problems.append("health")
        else:
            print(OK + "/health 正常 · 登录态=%s · 采集中=%s · 已连页面=%s"
                  % (bool(h.get("logined")), bool(h.get("busy")), h.get("clients")))
            if not h.get("logined"):
                print("      " + WARN.lstrip() + "还没登录抖音/小红书 → 双击 init_login.bat 扫一次码")
                problems.append("login")
            if h.get("clients") == 0:
                print("      [!] 还没有页面连上来：把工作台页面刷新一下（F5）")

    # ---------- 4. 登录态文件 ----------
    ck = os.path.join(HERE, "browser_data", "Default", "Network", "Cookies")
    if os.path.exists(ck):
        print(OK + "登录态文件存在（browser_data/Default/Network/Cookies）")
    else:
        print(WARN + "没有登录态文件：采集会拿不到评论区，先跑一次 init_login.bat")
        if "login" not in problems:
            problems.append("login")

    # ---------- 5. 结论 ----------
    print()
    print("-" * 56)
    if not problems:
        print("结论：一切正常。回工作台刷新页面即可，顶部应显示「本地采集器已连接」。")
        print()
        print("如果页面仍显示未连接，多半是浏览器代理问题：")
        print("  在浏览器里直接打开  http://127.0.0.1:8765/health")
        print("  - 能看到一段 JSON  → 本地没问题，是页面缓存，Ctrl+F5 强刷")
        print("  - 打不开 / 502     → 浏览器走了代理，把 127.0.0.1 加入代理例外")
    elif problems == ["port"]:
        print("结论：只差一步 —— 双击桌面「启动采集服务.bat」，窗口保持开着。")
        print("      （更省事：直接双击「打开线索雷达.bat」，它会把服务一起拉起来）")
    else:
        print("结论：有 %d 处需要处理：%s" % (len(problems), "、".join(problems)))
        print("照上面标 [X] 的行处理，然后重新双击本自检。")
    print("-" * 56)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
