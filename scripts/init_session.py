# -*- coding: utf-8 -*-
"""
线索雷达 · 首次登录初始化（只需跑一次）
================================
抖音 / 小红书的风控会拦住"全新浏览器环境"。所以第一次必须在一个**可见窗口**里
手动登录一次、顺带把人机验证滑过去。登录态会被保存进 browser_data/ 目录，
之后所有采集（包括无头定时任务）都会复用它，不用再登录。

用法：
    python init_session.py            # 引导式：逐个平台打开，你手动登录，按回车继续
    python init_session.py --check    # 只检查当前登录态是否可用，不做引导

完成后就可以一键采集了：
    python huoke_collector.py --mode browser --keyword 家具 --platform douyin xhs
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import huoke_collector as HC  # noqa: E402
from browser_collect import BrowserCollector, PROFILES  # noqa: E402

TARGETS = ["douyin", "xhs"]
PROBE_KEYWORD = "家具"


def check_platform(bc, page, plat):
    """用一个关键词搜索页探测是否还被拦。返回 (ok, reason)。"""
    prof = PROFILES[plat]
    import urllib.parse
    url = prof["search_url"].format(kw=urllib.parse.quote(PROBE_KEYWORD))
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        return False, f"页面打不开（{type(e).__name__}）"
    import time
    time.sleep(3.5)
    block = bc._detect_block(page, prof)
    if block == "verify":
        return False, "仍有人机验证"
    if block == "login":
        return False, "仍未登录"
    # 再看有没有内容卡片
    try:
        hrefs = page.evaluate(
            "(sels) => { for (const s of sels) { try { const n = document.querySelectorAll(s); "
            "if (n.length) return Array.from(n).map(a => a.href || ''); } catch(e){} } return []; }",
            prof["card_sels"],
        )
    except Exception:
        hrefs = []
    import re
    valid = [h for h in (hrefs or []) if h and re.search(prof["card_href_pat"], h)]
    if not valid:
        return False, "页面能开但没有内容卡片（可能被限流或页面改版）"
    return True, f"正常，探测到 {len(valid)} 个内容卡片"


def main():
    ap = argparse.ArgumentParser(description="线索雷达 · 首次登录初始化")
    ap.add_argument("--check", action="store_true", help="只检查登录态，不做引导")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    args = ap.parse_args()

    cfg = HC.load_config(args.config)
    cfg["enable_cdp"] = False       # 初始化必须用自带持久化环境，才能把 Cookie 存下来
    cfg["headless"] = False         # 必须可见，人工要操作

    print("=" * 58)
    print(" 线索雷达 · 首次登录初始化")
    print("=" * 58)
    print(f"登录态将保存到：{cfg.get('user_data_dir')}")
    print("每个平台：打开页面 → 你手动登录/过验证 → 回来按回车\n")

    with BrowserCollector(cfg) as bc:
        page = bc._context.new_page()
        results = {}

        for plat in TARGETS:
            prof = PROFILES[plat]
            name = prof["cn"]
            print(f"\n----- {name} -----")
            try:
                page.goto(prof["home_url"], wait_until="domcontentloaded")
            except Exception as e:
                print(f"  [!] 打开{name}首页失败：{e}")
                results[plat] = (False, "打不开首页")
                continue
            import time
            time.sleep(2.5)

            if args.check:
                ok, reason = check_platform(bc, page, plat)
                results[plat] = (ok, reason)
                print(("  ✅ " if ok else "  ❌ ") + reason)
                continue

            print(f"  👉 请在浏览器窗口里完成 {name} 登录（扫码/手机号都行）。")
            print(f"  👉 如果弹出人机验证，请手动滑一下。")
            try:
                input("  完成后回到这里按【回车】继续… ")
            except (EOFError, KeyboardInterrupt):
                print("\n  已跳过。")
                continue

            ok, reason = check_platform(bc, page, plat)
            results[plat] = (ok, reason)
            if ok:
                print(f"  ✅ {reason}")
            else:
                print(f"  ⚠️ {reason}")
                print(f"     可以在窗口里再试一次；或稍后重新运行本脚本。")

        try:
            page.close()
        except Exception:
            pass

    print("\n" + "=" * 58)
    print(" 结果")
    print("=" * 58)
    all_ok = True
    for plat in TARGETS:
        ok, reason = results.get(plat, (False, "未执行"))
        print(f"  {'✅' if ok else '❌'} {PROFILES[plat]['cn']}：{reason}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("全部就绪，现在可以一键采集：")
        print("  python huoke_collector.py --mode browser --keyword 家具 --platform douyin xhs")
        print("也可以直接跑每日任务：")
        print("  python daily_run.py")
    else:
        print("还有平台没就绪。重新运行本脚本再试一次：")
        print("  python init_session.py")
    print()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
