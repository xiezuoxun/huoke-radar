# -*- coding: utf-8 -*-
"""
线索雷达 · 本地采集服务
================================
让云端工作台（https://www.workbuddy.cn/space/d/...）能真正驱动本机采集器。

为什么需要它：网页跑在浏览器沙箱里，**没有任何办法直接启动你电脑上的程序**。
所以本机起一个只监听回环地址的小服务，页面通过 HTTP 调它。

设计上的两个关键决定：
1. **只监听 127.0.0.1** —— 外网、局域网都访问不到，页面关掉服务就断。
2. **采集完只回传数据，不负责写云端** —— 写库要 Open Platform token（30 分钟过期，
   只能在 IDE 会话里拿）。所以由页面拿到 rows 后用自己的登录态写库，服务端完全不碰 token。

接口：
    GET  /health                    服务与登录态自检
    POST /collect   {...}           启动一次采集（同一时间只允许一个任务）
    GET  /status?job=<id>           进度、实时日志、完成后的数据
    POST /cancel                    请求取消（当前步骤结束后生效）
    GET  /config                    当前关键词 / 平台 / 采集强度

启动：双击 start_agent.bat，或
    python agent_server.py --port 8765

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

VERSION = "1.0"

# 同时只跑一个采集任务（浏览器复用同一份登录态，并发会互相踩）
_LOCK = threading.Lock()
_JOBS = {}
_CURRENT = {"job": None}
_JOB_SEQ = {"n": 0}

# ---------- 页面存活登记（「打开工作台才启动、关掉就退出」的落地机制）----------
# 页面每 15 秒打一次心跳；服务端维护 client_id -> 最近心跳时间。
# 一个页面都不剩、且没有任务在跑，持续 IDLE_EXIT 秒后自动退出。
_CLIENTS = {}
_IDLE_SINCE = {"t": None}
_LIFECYCLE = {"idle_exit": 0, "boot_at": 0.0, "grace": 90.0, "ever_beat": False}
# 启动宽限期：服务刚起来时浏览器可能还没加载完页面（Chrome 冷启动就要好几秒），
# 这段时间内一律不退出，否则会出现「服务起好了、浏览器还没连上、服务已经自杀」。
STARTUP_GRACE = 90.0
# 为什么是 300 秒：Chrome 对**后台标签页**的 setInterval 会节流到 1 分钟一次
# （隐藏超过 5 分钟更狠）。阈值设小了会把「切到别的标签页」误判成「页面已关」。
# 正常关闭走 pagehide → /bye，是秒级路径，不必依赖这个兜底值。
HEARTBEAT_TIMEOUT = 300.0


# ==================================================================
# 生命周期：页面关掉后自动退出
# ==================================================================
def _shutdown(reason):
    print("[服务] %s" % reason)
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


def _watchdog():
    """后台巡检：没有页面在用、也没有任务在跑，就进入倒计时。

    为什么不是「收到关闭信号立刻退」：页面刷新（F5）、链接跳转都会触发 pagehide，
    立刻退会导致新页面连不上。所以统一走倒计时，页面在倒计时内重新发心跳就能取消。
    """
    while True:
        time.sleep(3.0)
        now = time.time()
        if now - _LIFECYCLE["boot_at"] < _LIFECYCLE["grace"]:
            continue          # 刚启动，等页面连上来

        # 关键分流：在收到**第一次心跳之前**，绝不退出。
        # 因为「没心跳」有两种可能，服务端无法区分：
        #   a) 页面还在加载          → 退了就等于把人踢下线
        #   b) 用的是旧版页面（没心跳接口）→ 退了也是把人踢下线
        # 只有「曾经心跳过、后来又没了」才确定是页面被关掉，这时才启倒计时。
        if _LIFECYCLE["idle_exit"] and not _LIFECYCLE["ever_beat"]:
            continue

        idle = 0.0
        try:
            with _LOCK:
                for k in [k for k, ts in _CLIENTS.items() if now - ts > HEARTBEAT_TIMEOUT]:
                    _CLIENTS.pop(k, None)
                has_client = bool(_CLIENTS)
                has_job = _CURRENT["job"] is not None
                if has_client or has_job:
                    _IDLE_SINCE["t"] = None
                    continue
                if _IDLE_SINCE["t"] is None:
                    _IDLE_SINCE["t"] = now
                    continue
                idle = now - _IDLE_SINCE["t"]
        except Exception:
            continue
        limit = _LIFECYCLE["idle_exit"]
        if limit and idle >= limit:
            _shutdown("工作台已关闭 %d 秒且没有任务在跑，采集服务自动退出" % int(idle))


# ==================================================================
# 任务对象
# ==================================================================
class Job:
    def __init__(self, params):
        _JOB_SEQ["n"] += 1
        self.id = "J%d%03d" % (int(time.time()), _JOB_SEQ["n"] % 1000)
        self.params = params
        self.status = "queued"          # queued / running / done / error / cancelled
        self.step = "排队中"
        self.logs = deque(maxlen=500)
        self.rows = []
        self.batch = ""
        self.stats = {"scanned": 0, "notes_total": 0, "notes_done": 0,
                      "platforms": [], "keywords": []}
        self.started_at = time.time()
        self.finished_at = None
        self.error = ""
        self.cancelled = False
        self.diag = []          # 每个平台为什么 0 条，回给页面

    def log(self, msg):
        line = str(msg).rstrip()
        self.logs.append("[%s] %s" % (time.strftime("%H:%M:%S"), line))
        self._parse(line)

    def _parse(self, line):
        """从采集器日志里抠进度，页面据此画进度条。"""
        m = re.search(r"\[(\d+)/(\d+)\]", line)
        if m:
            self.stats["notes_done"] += 1
            self.stats["notes_total"] = max(self.stats["notes_total"],
                                            self.stats["notes_done"] - 1 + int(m.group(2)))
            tail = re.search(r"→\s*(\d+)\s*条", line)
            if tail:
                self.stats["scanned"] += int(tail.group(1))
            self.step = "正在扫描评论区（%s/%s）" % (m.group(1), m.group(2))
            return
        m = re.search(r"拿到\s*(\d+)\s*个内容链接", line)
        if m:
            n = int(m.group(1))
            self.stats["notes_total"] = max(self.stats["notes_total"],
                                            self.stats["notes_done"] + n)
            self.step = "已定位 %d 个内容，准备进评论区" % n
            return
        m = re.search(r"打开搜索页：(\S+)\s*/\s*(\S+)", line)
        if m:
            self.step = "正在搜索：%s / %s" % (m.group(1), m.group(2))
            return
        if "采集" in line and "条评论" in line:
            m = re.search(r"采集\s*(\d+)\s*条评论", line)
            if m:
                self.stats["scanned"] = max(self.stats["scanned"], int(m.group(1)))
            return
        if "人机验证" in line or "需要登录" in line:
            self.step = "等待人工完成验证 / 登录"
            return
        if "去重" in line:
            self.step = "正在去重合并"
            return

    def snapshot(self, with_rows=False):
        p = float(0)
        if self.stats["notes_total"]:
            p = min(96.0, 96.0 * self.stats["notes_done"] / max(1, self.stats["notes_total"]))
        if self.status in ("done", "error", "cancelled"):
            p = 100.0
        d = {
            "ok": True,
            "job": self.id,
            "status": self.status,
            "step": self.step,
            "progress": round(p, 1),
            "stats": dict(self.stats),
            "batch": self.batch,
            "count": len(self.rows),
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 1),
            "logs": list(self.logs)[-80:],
            "error": self.error,
            "params": self.params,
            "diagnostics": list(self.diag),
        }
        if with_rows and self.status == "done":
            d["rows"] = self.rows
        return d


# ==================================================================
# 渠道登录
# ==================================================================
# 强登录 cookie（登录后才有，游客态不会有），用于判断是否真的登录了
LOGIN_COOKIE = {
    "douyin":   ("douyin.com",     ["sessionid", "sessionid_ss"]),
    "xhs":      ("xiaohongshu.com", ["web_session"]),
    # 快手实际下发的写的是 webday7_st；只认 web_st 会漏判
    "kuaishou": ("kuaishou.com",   ["kuaishou.server.web_st", "kuaishou.server.webday7_st", "userId"]),
    "weibo":    ("weibo.com",      ["SUB"]),
    # cookie2 是游客也会有的票据，只认 unb 才不会把未登录当已登录
    "xianyu":   ("goofish.com",    ["unb"]),
    "bilibili": ("bilibili.com",   ["SESSDATA"]),
    "zhihu":    ("zhihu.com",      ["z_c0"]),
    # 58 登录后落的是 PPU / 58uname / passportAccount，旧写法那两个名字根本不存在
    "wuba58":   ("58.com",         ["PPU", "58uname", "passportAccount", "58cooper"]),
}
LOGIN_CN = {
    "douyin": "抖音", "xhs": "小红书", "kuaishou": "快手", "weibo": "微博",
    "xianyu": "闲鱼", "bilibili": "B站", "zhihu": "知乎", "wuba58": "58同城",
}
LOGIN_STATE_PATH = os.path.join(HERE, "login_state.json")
_LOGIN = {"thread": None, "code": "", "cn": "", "active": False, "error": "", "started": 0}


def _cookie_db_path():
    return os.path.join(HERE, "browser_data", "Default", "Network", "Cookies")


# ---- 登录态缓存 ----------------------------------------------------
# Chrome 启动/写盘时会短暂锁住 Cookies 库，同步读会阻塞 3~5 秒。
# 所以对外只返回缓存快照，真正的扫描放到后台线程里做。
_STATUS_CACHE = {"at": 0.0, "data": {}, "busy": False, "scanned": False, "busy_at": 0.0}
_STATUS_LOCK = threading.Lock()
STATUS_TTL = 25.0
BUSY_TIMEOUT = 15.0   # busy 卡住超过这个秒数就允许抢占，否则登录态会永远停在"检测中"


def _logged_from_db(code):
    """直接读 Chrome 的 Cookies 库（只读、不需要浏览器开着）。返回 (ok, expire_ts)。"""
    spec = LOGIN_COOKIE.get(code)
    if not spec:
        return False, 0
    domain, names = spec
    db = _cookie_db_path()
    if not os.path.exists(db):
        return False, 0
    try:
        import sqlite3
        con = sqlite3.connect("file:%s?immutable=1" % db.replace("\\", "/"), uri=True, timeout=0.05)
        cur = con.cursor()
        q = ("select host_key, name, expires_utc from cookies where name in (%s)"
             % ",".join("?" * len(names)))
        rows = cur.execute(q, list(names)).fetchall()
        con.close()
    except Exception:
        return False, 0
    now = time.time()
    for host, name, exp in rows:
        if domain not in (host or ""):
            continue
        exp_s = 0
        try:
            exp_s = int(exp) / 1e6 - 11644473600 if exp else 0
        except Exception:
            exp_s = 0
        if exp_s == 0 or exp_s > now:
            return True, int(exp_s)
    return False, 0


def _scan_login_status():
    """真正扫一遍 Cookies 库（可能被 Chrome 锁，耗时几百毫秒到几秒）"""
    out = {}
    for code, cn in LOGIN_CN.items():
        ok, exp = _logged_from_db(code)
        out[cn] = {"ok": ok, "expire": exp, "code": code}
    return out


def _refresh_login_status_async():
    """后台扫描，绝不阻塞请求线程"""
    now = time.time()
    with _STATUS_LOCK:
        if _STATUS_CACHE["busy"] and (now - _STATUS_CACHE.get("busy_at", 0)) < BUSY_TIMEOUT:
            return
        _STATUS_CACHE["busy"] = True
        _STATUS_CACHE["busy_at"] = now

    def _work():
        try:
            data = _scan_login_status()
            with _STATUS_LOCK:
                _STATUS_CACHE["data"] = data
                _STATUS_CACHE["at"] = time.time()
                _STATUS_CACHE["scanned"] = True
        except Exception:
            pass
        finally:
            with _STATUS_LOCK:
                _STATUS_CACHE["busy"] = False

    threading.Thread(target=_work, daemon=True).start()


def _login_status(force=False):
    """返回缓存快照；缓存过期时顺手踢一次后台刷新。

    首次查询在前台直接扫一遍（实测 18ms，只读 cookie 名和过期时间），
    否则页面第一次打开只能拿到空对象，会一直显示"登录检测中"。
    """
    now = time.time()
    with _STATUS_LOCK:
        data = dict(_STATUS_CACHE["data"])
        stale = (now - _STATUS_CACHE["at"]) > STATUS_TTL
        scanned = _STATUS_CACHE["scanned"]
        busy = _STATUS_CACHE["busy"] and (now - _STATUS_CACHE.get("busy_at", 0)) < BUSY_TIMEOUT

    if force or stale or not scanned:
        if busy:
            return data
        try:
            fresh = _scan_login_status()
            with _STATUS_LOCK:
                _STATUS_CACHE["data"] = fresh
                _STATUS_CACHE["at"] = time.time()
                _STATUS_CACHE["scanned"] = True
            return dict(fresh)
        except Exception:
            _refresh_login_status_async()
    return data


def _has_login_in_ctx(cookies, code):
    spec = LOGIN_COOKIE.get(code)
    if not spec:
        return False
    domain, names = spec
    for c in cookies or []:
        if c.get("name") in names and (c.get("value") or "") and domain in (c.get("domain") or ""):
            return True
    return False


def _run_login(code, url, wait_sec=300):
    """开一个有界面的 Chrome（复用 browser_data 登录态目录），等用户登录完成。"""
    _LOGIN.update({"active": True, "code": code, "cn": LOGIN_CN.get(code, code),
                   "error": "", "started": time.time()})
    ctx = None
    pw = None
    try:
        from playwright.sync_api import sync_playwright
        udd = os.path.join(HERE, "browser_data")
        os.makedirs(udd, exist_ok=True)
        pw = sync_playwright().start()
        kw = dict(
            user_data_dir=udd,
            headless=False,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-first-run", "--no-default-browser-check", "--lang=zh-CN"],
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        try:
            ctx = pw.chromium.launch_persistent_context(channel="chrome", **kw)
        except Exception:
            ctx = pw.chromium.launch_persistent_context(**kw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded",
                      timeout=max(8000, min(45000, int(wait_sec * 1000))))
        except Exception as ge:
            # 页面没打开也别立刻关窗：用户可能还想自己点两下
            _LOGIN["error"] = "页面加载慢：%s" % ge

        t0 = time.time()
        while time.time() - t0 < wait_sec:
            try:
                if _has_login_in_ctx(ctx.cookies(), code):
                    time.sleep(1.5)          # 让 cookie 落盘
                    break
            except Exception:
                break                        # 用户手动关了窗口
            time.sleep(2)
    except Exception as e:
        _LOGIN["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass
        _LOGIN["active"] = False
        # Chrome 关闭时把 cookie 落盘，稍等一下再重扫登录态
        try:
            time.sleep(0.8)
            _refresh_login_status_async()
        except Exception:
            pass


# ==================================================================
# 采集执行
# ==================================================================
def _build_cfg(params):
    cfg_path = os.path.join(HERE, "config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    kws = [k.strip() for k in (params.get("keywords") or []) if str(k).strip()]
    if kws:
        cfg["keywords"] = kws
    plats = [p for p in (params.get("platforms") or []) if p]
    if plats:
        cfg["platforms"] = plats
    if params.get("max_notes"):
        cfg["max_notes"] = int(params["max_notes"])
    if params.get("max_comments"):
        cfg["max_comments_per_note"] = int(params["max_comments"])
    if params.get("scroll_rounds"):
        cfg["scroll_rounds"] = int(params["scroll_rounds"])
    # 默认有界面：遇到人机验证/登录墙，用户能当场滑一下；页面可显式要求无头
    cfg["headless"] = bool(params.get("headless", False))
    cfg.setdefault("enable_cdp", False)   # 走持久化登录态，避免抢占用户 Chrome
    return cfg


def _run_job(job):
    job.status = "running"
    job.step = "正在加载采集器"
    try:
        from huoke_collector import build_rows, write_csv, summarize
        from browser_collect import BrowserCollector

        cfg = _build_cfg(job.params)
        job.stats["keywords"] = list(cfg.get("keywords") or [])
        job.stats["platforms"] = list(cfg.get("platforms") or [])
        job.log("[服务] 开始采集：关键词 %s / 平台 %s / 有界面=%s"
                % ("、".join(cfg.get("keywords") or []),
                   "、".join(cfg.get("platforms") or []),
                   not cfg.get("headless")))

        raw = []
        job.step = "正在启动浏览器"
        with BrowserCollector(cfg, log=job.log) as bc:
            raw = bc.collect() or []
            job.diag = list(getattr(bc, "diag", []) or [])

        for d in job.diag:
            job.log("[诊断] %s / %s → 链接 %s，评论 %s，结论 %s"
                    % (d.get("plat"), d.get("kw"), d.get("links", 0),
                       d.get("comments", 0), d.get("reason") or "ok"))

        if job.cancelled:
            job.status = "cancelled"
            job.step = "已取消"
            return

        job.step = "正在识别购买意向"
        job.log("[服务] 抓到 %d 条原始评论，开始做意向识别" % len(raw))
        rows, batch = build_rows(raw)
        job.rows = rows
        job.batch = batch

        out_dir = cfg.get("output_dir") or "./data"
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(HERE, out_dir.lstrip("./"))
        path = write_csv(rows, out_dir, batch)

        total, high, mid, low, plats = summarize(rows)
        job.stats["scanned"] = total
        job.log("[服务] 完成：%d 条评论 | 高 %d / 中 %d / 低 %d | 平台 %s"
                % (total, high, mid, low, plats))
        job.log("[服务] 已落盘：%s" % path)
        job.log("[服务] 接下来由页面负责写入云端（本服务不碰 token）")
        job.status = "done"
        job.step = "采集完成"
    except Exception as e:
        job.status = "error"
        job.error = "%s: %s" % (type(e).__name__, e)
        job.step = "采集失败"
        job.log("[错误] " + job.error)
        job.log(traceback.format_exc()[-1200:])
    finally:
        job.finished_at = time.time()
        with _LOCK:
            _CURRENT["job"] = None


# ==================================================================
# HTTP
# ==================================================================
class Handler(BaseHTTPRequestHandler):
    server_version = "HuokeAgent/" + VERSION
    protocol_version = "HTTP/1.1"

    # 静默访问日志（只留错误），避免控制台刷屏
    def log_message(self, fmt, *args):
        pass

    # ---------- 工具 ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Chrome Private Network Access（https 页面访问 localhost 需要）
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            # 页面故意用 text/plain 发，避开预检；这里自己解析
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _send_file(self, fpath, ctype):
        """把本地 HTML 直接吐给浏览器。
        为什么要有这个：云端 https 页面 fetch http://127.0.0.1 会被 Chrome 的
        Private Network Access / 混合内容策略拦掉（服务端 CORS 再全也没用）。
        让页面本身就从 127.0.0.1 加载 → 与 API 同源 → 零跨域零 PNA，必然通。
        """
        try:
            with open(fpath, "rb") as f:
                body = f.read()
        except Exception as e:
            return self._send({"ok": False, "error": "读取页面失败：%s" % e}, 500)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = parse_qs(u.query)

        # 本地托管工作台页面：http://127.0.0.1:8765/app
        # 页面与 API 同源，彻底避开 https→localhost 的浏览器拦截
        if path in ("/app", "/app/", "/index.html"):
            page = os.path.join(os.path.dirname(HERE), "huoke-radar.html")
            if not os.path.exists(page):
                page = os.path.join(HERE, "huoke-radar.html")
            return self._send_file(page, "text/html; charset=utf-8")

        if path in ("/", "/health", "/ping"):
            cfg = {}
            cp = os.path.join(HERE, "config.json")
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            bd = os.path.join(HERE, "browser_data")
            has_login = os.path.exists(os.path.join(bd, "Default", "Network", "Cookies"))
            cur = _CURRENT["job"]
            return self._send({
                "ok": True,
                "service": "huoke-agent",
                "version": VERSION,
                "python": sys.executable,
                "logined": has_login,
                "browser_data": bd if has_login else "",
                "busy": bool(cur),
                "current_job": cur.id if cur else "",
                "clients": len(_CLIENTS),
                "idle_exit": _LIFECYCLE["idle_exit"],
                "config": {
                    "keywords": cfg.get("keywords", []),
                    "platforms": cfg.get("platforms", []),
                    "max_notes": cfg.get("max_notes", 10),
                    "max_comments": cfg.get("max_comments_per_note", 20),
                },
            })

        if path == "/status":
            jid = (q.get("job") or [""])[0]
            job = _JOBS.get(jid) or _CURRENT["job"]
            if not job:
                return self._send({"ok": False, "error": "没有正在进行的任务"}, 404)
            with_rows = (q.get("rows") or ["0"])[0] in ("1", "true", "yes")
            return self._send(job.snapshot(with_rows=with_rows))

        if path == "/login/status":
            data = _login_status()
            return self._send({
                "ok": True,
                "logins": data,
                "login_checking": (not _STATUS_CACHE["scanned"]) or (
                    _STATUS_CACHE["busy"]
                    and (time.time() - _STATUS_CACHE.get("busy_at", 0)) < BUSY_TIMEOUT),
                "login_active": bool(_LOGIN["active"]),
                "login_platform": _LOGIN["cn"],
                "login_error": _LOGIN["error"],
            })

        if path == "/config":
            cp = os.path.join(HERE, "config.json")
            cfg = {}
            if os.path.exists(cp):
                try:
                    with open(cp, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            return self._send({"ok": True, "config": cfg})

        return self._send({"ok": False, "error": "未知接口 %s" % path}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/heartbeat":
            d = self._body() or {}
            cid = str(d.get("client") or "").strip()
            if not cid:
                return self._send({"ok": False, "error": "缺少 client"}, 400)
            with _LOCK:
                _CLIENTS[cid] = time.time()
                _IDLE_SINCE["t"] = None
                _LIFECYCLE["ever_beat"] = True
                n = len(_CLIENTS)
            return self._send({"ok": True, "clients": n,
                               "idle_exit": _LIFECYCLE["idle_exit"]})

        if path == "/bye":
            d = self._body() or {}
            cid = str(d.get("client") or "").strip()
            with _LOCK:
                if cid:
                    _CLIENTS.pop(cid, None)
                else:
                    _CLIENTS.clear()
                n = len(_CLIENTS)
                # 页面正常关闭（pagehide 触发）走这条路：立刻开始倒计时，
                # 比等心跳超时快得多。刷新的话新页面会马上重新心跳，把倒计时清掉。
                if n == 0 and _CURRENT["job"] is None and _IDLE_SINCE["t"] is None:
                    _IDLE_SINCE["t"] = time.time()
            return self._send({"ok": True, "clients": n})

        if path == "/collect":
            params = self._body() or {}
            if _LOGIN["active"]:
                return self._send({"ok": False,
                                   "error": "登录窗口还开着（%s），登录完成后再采集" % _LOGIN["cn"]}, 409)
            with _LOCK:
                if _CURRENT["job"] is not None:
                    return self._send({"ok": False, "error": "已有任务在跑",
                                       "job": _CURRENT["job"].id}, 409)
                job = Job(params)
                _JOBS[job.id] = job
                _CURRENT["job"] = job
            # 只保留最近 20 个任务
            for k in list(_JOBS.keys())[:-20]:
                _JOBS.pop(k, None)
            t = threading.Thread(target=_run_job, args=(job,), daemon=True)
            t.start()
            job.log("[服务] 任务已受理：%s" % job.id)
            return self._send({"ok": True, "job": job.id})

        if path == "/login":
            d = self._body() or {}
            code = str(d.get("code") or "").strip()
            url = str(d.get("url") or "").strip()
            if code not in LOGIN_COOKIE:
                return self._send({"ok": False, "error": "该渠道暂不支持自动登录（%s）" % code}, 400)
            if not url.startswith("http"):
                return self._send({"ok": False, "error": "登录地址无效"}, 400)
            try:
                wait_sec = int(d.get("wait") or 300)
            except Exception:
                wait_sec = 300
            wait_sec = max(5, min(900, wait_sec))
            if _CURRENT["job"] is not None:
                return self._send({"ok": False, "error": "正在采集，先等任务跑完再登录"}, 409)
            if _LOGIN["active"]:
                return self._send({"ok": False,
                                   "error": "已经有一个登录窗口开着（%s），先完成它" % _LOGIN["cn"]}, 409)
            t = threading.Thread(target=_run_login, args=(code, url, wait_sec), daemon=True)
            t.start()
            _LOGIN["thread"] = t
            return self._send({"ok": True, "platform": LOGIN_CN.get(code, code),
                               "url": url, "wait": wait_sec})

        if path == "/quit":
            with _LOCK:
                busy = _CURRENT["job"] is not None
            if busy:
                return self._send({"ok": False, "error": "正在采集，先取消任务再关闭"}, 409)
            self._send({"ok": True, "msg": "服务正在退出"})
            threading.Timer(0.4, lambda: _shutdown("收到关闭请求，服务退出")).start()
            return

        if path == "/cancel":
            job = _CURRENT["job"]
            if not job:
                return self._send({"ok": False, "error": "没有正在进行的任务"}, 404)
            job.cancelled = True
            job.log("[服务] 已收到取消请求，当前步骤结束后停止")
            return self._send({"ok": True, "job": job.id})

        return self._send({"ok": False, "error": "未知接口 %s" % path}, 404)


def _ping_existing(host, port, timeout=2.0):
    """探测该端口上是否已有本服务在跑。返回 health dict 或 None。"""
    import json as _json
    import urllib.request as _req

    try:
        with _req.urlopen("http://%s:%d/health" % (host, port), timeout=timeout) as r:
            d = _json.loads(r.read().decode("utf-8", "replace"))
        return d if isinstance(d, dict) and d.get("ok") else None
    except Exception:
        return None


def _ensure_streams():
    """用 pythonw 启动时没有控制台，sys.stdout/stderr 是 None，print 会直接崩。

    这里兜底接到 debug/agent.log，既救回 print，也方便事后查问题。
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_dir = os.path.join(HERE, "debug")
        os.makedirs(log_dir, exist_ok=True)
        f = open(os.path.join(log_dir, "agent.log"), "a", encoding="utf-8", buffering=1)
    except Exception:
        class _Sink(object):
            def write(self, *_a):
                pass

            def flush(self):
                pass
        f = _Sink()
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


def main():
    _ensure_streams()

    ap = argparse.ArgumentParser(description="线索雷达 · 本地采集服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--idle-exit", type=int, default=0, metavar="秒",
                    help="工作台关闭后多少秒没有心跳就自动退出（0=一直常驻，默认 0）")
    ap.add_argument("--startup-grace", type=int, default=90, metavar="秒",
                    help="启动后多少秒内不因「无人使用」退出，留给浏览器加载页面（默认 90）")
    ap.add_argument("--allow-multi", action="store_true",
                    help="端口已被占用时仍然强行再起一个实例（一般不必要）")
    args = ap.parse_args()

    os.chdir(HERE)

    # 已有实例在跑就直接复用，避免「Address already in use」把人吓一跳
    if not args.allow_multi:
        alive = _ping_existing(args.host, args.port)
        if alive:
            print("=" * 58)
            print(" 服务已经在运行了，不用重复启动。")
            print(" 地址：http://%s:%d  （v%s）" % (args.host, args.port, alive.get("version", "?")))
            print(" 登录态：%s" % ("有效" if alive.get("logined") else "未登录（请先跑 init_login.bat）"))
            print(" 状态：%s" % ("采集中" if alive.get("busy") else "空闲"))
            print(" 直接用工作台即可，本窗口可以直接关掉。")
            print("=" * 58)
            return 0

    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        print("=" * 58)
        print(" 启动失败：端口 %d 被占用，但探测不到本服务。" % args.port)
        print(" 可能是别程序占了，换个端口：")
        print("   python agent_server.py --port 8766")
        print(" 同时把工作台页面里的 AGENT 常量改成 127.0.0.1:8766")
        print(" 原始错误：%s" % e)
        print("=" * 58)
        return 1
    _LIFECYCLE["idle_exit"] = max(0, int(args.idle_exit or 0))
    _LIFECYCLE["grace"] = max(0.0, float(args.startup_grace or 0))
    _LIFECYCLE["boot_at"] = time.time()
    print("=" * 58)
    print(" 线索雷达 · 本地采集服务  v%s" % VERSION)
    print(" 监听：http://%s:%d" % (args.host, args.port))
    print(" 工作台点「开始采集」即可驱动本机采集器")
    if _LIFECYCLE["idle_exit"]:
        print(" 生命周期：随工作台 —— 页面全关后 %d 秒自动退出（启动宽限 %d 秒）"
              % (_LIFECYCLE["idle_exit"], int(_LIFECYCLE["grace"])))
    else:
        print(" 生命周期：常驻（关掉这个窗口才退出）")
    print("=" * 58)

    if _LIFECYCLE["idle_exit"]:
        threading.Thread(target=_watchdog, daemon=True).start()

    # 启动就先把登录态扫一遍，之后全靠后台刷新，页面永远秒开
    _refresh_login_status_async()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
