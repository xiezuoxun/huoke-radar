# -*- coding: utf-8 -*-
"""
线索雷达 · 每日定时采集编排
================================
一条命令跑完「采集 → 去重 → 写 CSV → 写入资料库」的完整闭环，专为无人值守设计。

典型用法：
  # 手动跑一轮（会自动 push，token 从 --token / HUB_TOKEN / .hub_token 取）
  python daily_run.py

  # 只采集落本地 CSV，不联网写库（Windows 计划任务兜底模式）
  python daily_run.py --no-push

  # 指定关键词 / 平台 / 无头
  python daily_run.py --keyword 家具 减脂 --platform douyin xhs --headless

  # 先看配置会跑什么，不实际执行
  python daily_run.py --dry-plan

调度方式（二选一）：
  A) WorkBuddy 定时任务（推荐：每次都能拿新 token，能真正写进资料库）
     在 WorkBuddy 里建一个每天固定时间的自动化，让它执行本脚本。
  B) Windows 计划任务（本机离线兜底，建议配 --no-push，token 过期不影响采集）
     以管理员身份运行：powershell -ExecutionPolicy Bypass -File install_schedule.ps1

日志：collector/logs/daily_YYYYMMDD.log；运行结果同时以 JSON 打到 stdout 末行。

声明：仅供个人工作 / 学习 / 研究使用，严禁商用。控制频率，勿大规模抓取。
"""

import argparse
import datetime
import json
import logging
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import huoke_collector as HC  # noqa: E402
from dedupe import merge_rows  # noqa: E402

LOG_DIR = os.path.join(HERE, "logs")


def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    fp = os.path.join(LOG_DIR, "daily_%s.log" % datetime.datetime.now().strftime("%Y%m%d"))
    logger = logging.getLogger("daily")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(fp, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger, fp


def resolve_token(cli_token=""):
    t = (cli_token or "").strip()
    if t:
        return t
    t = os.environ.get("HUB_TOKEN", "").strip()
    if t:
        return t
    fp = os.path.join(HERE, ".hub_token")
    if os.path.exists(fp):
        try:
            return open(fp, "r", encoding="utf-8").read().strip()
        except Exception:
            return ""
    return ""


def build_run_cfg(base_cfg, watch, args):
    """把 config.json 的 watch 段 + 命令行覆盖合并成一次运行的配置。"""
    cfg = dict(base_cfg)
    cfg["keywords"] = list(watch.get("keywords") or cfg.get("keywords") or [])
    cfg["platforms"] = list(watch.get("platforms") or cfg.get("platforms") or [])
    cfg["max_notes"] = int(watch.get("max_notes", cfg.get("max_notes", 10)))
    cfg["max_comments_per_note"] = int(watch.get("max_comments_per_note", cfg.get("max_comments_per_note", 20)))
    cfg["scroll_rounds"] = int(watch.get("scroll_rounds", cfg.get("scroll_rounds", 10)))
    cfg["dedupe_mode"] = watch.get("dedupe_mode", cfg.get("dedupe_mode", "exact"))
    cfg["headless"] = bool(watch.get("headless", cfg.get("headless", False)))
    cfg["enable_cdp"] = bool(watch.get("enable_cdp", cfg.get("enable_cdp", True)))

    if args.keyword:
        cfg["keywords"] = args.keyword
    if args.platform:
        cfg["platforms"] = args.platform
    if args.headless:
        cfg["headless"] = True
    if args.max_notes:
        cfg["max_notes"] = args.max_notes
    if args.max_comments:
        cfg["max_comments_per_note"] = args.max_comments
    if args.dedupe:
        cfg["dedupe_mode"] = args.dedupe
    return cfg


def pick_mode(args, watch):
    if args.mode:
        return args.mode
    return watch.get("mode", "browser")


def collect_once(cfg, mode, log):
    if mode == "browser":
        return HC.collect_browser(cfg)
    if mode == "mediacrawler":
        return HC.collect_mediacrawler(cfg, cfg.get("mc_dir", ""))
    return HC.collect_mock(cfg)


def main():
    ap = argparse.ArgumentParser(description="线索雷达 · 每日定时采集编排")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--mode", choices=["browser", "mediacrawler", "mock"], default="")
    ap.add_argument("--mc-dir", default="", help="mediacrawler 模式的 data 目录")
    ap.add_argument("--keyword", nargs="*")
    ap.add_argument("--platform", nargs="*")
    ap.add_argument("--max-notes", type=int, default=0)
    ap.add_argument("--max-comments", type=int, default=0)
    ap.add_argument("--dedupe", choices=["exact", "customer", "off"], default="")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--no-push", action="store_true", help="只落本地 CSV，不联网写资料库")
    ap.add_argument("--no-diff", action="store_true", help="push 时跳过云端比对")
    ap.add_argument("--token", default="", help="Open Platform token")
    ap.add_argument("--retry", type=int, default=1, help="采集为空时重试次数")
    ap.add_argument("--dry-plan", action="store_true", help="只打印本次将执行的计划")
    args = ap.parse_args()

    log, log_path = setup_logger()
    started = datetime.datetime.now()
    log.info("=" * 56)
    log.info("线索雷达 · 每日采集开始 %s", started.strftime("%Y-%m-%d %H:%M:%S"))

    base_cfg = HC.load_config(args.config)
    watch = base_cfg.get("watch") or {}
    cfg = build_run_cfg(base_cfg, watch, args)
    if args.mc_dir:
        cfg["mc_dir"] = args.mc_dir
    mode = pick_mode(args, watch)

    log.info("模式=%s | 关键词=%s | 平台=%s | headless=%s | 去重=%s | push=%s",
             mode, cfg["keywords"], cfg["platforms"], cfg["headless"],
             cfg["dedupe_mode"], not args.no_push)

    if args.dry_plan:
        log.info("--dry-plan：仅打印计划，不执行。")
        print(json.dumps({"plan": {"mode": mode, "keywords": cfg["keywords"],
                                   "platforms": cfg["platforms"], "headless": cfg["headless"],
                                   "dedupe": cfg["dedupe_mode"], "push": not args.no_push}},
                         ensure_ascii=False))
        return 0

    if not cfg["keywords"] or not cfg["platforms"]:
        log.error("关键词或平台为空，终止。请检查 config.json 的 watch 段。")
        return 2

    # ---------- 1. 采集（带重试）----------
    raw = []
    attempt = 0
    while attempt <= args.retry:
        attempt += 1
        log.info("开始采集（第 %d 次尝试）…", attempt)
        try:
            raw = collect_once(cfg, mode, log) or []
        except Exception as e:
            log.error("采集异常：%s", e)
            log.debug(traceback.format_exc())
            raw = []
        if raw:
            break
        if attempt <= args.retry:
            log.warning("本次采集 0 条，10 秒后重试…")
            import time
            time.sleep(10)

    if not raw:
        log.error("采集结果为空。常见原因：未登录 / 触发了风控 / 页面改版。"
                  "请用非 headless 跑一次确认（python huoke_collector.py --mode browser）。")
        print(json.dumps({"ok": False, "reason": "empty", "log": log_path}, ensure_ascii=False))
        return 1

    log.info("采集原始评论 %d 条", len(raw))

    # ---------- 2. 意向识别 + 去重 ----------
    rows, batch = HC.build_rows(raw)
    before = len(rows)
    if cfg["dedupe_mode"] != "off":
        rows, rep = merge_rows(rows, one_per_customer=(cfg["dedupe_mode"] == "customer"))
        log.info("去重：%d → %d 条（完全重复 %d，同客户多条 %d）",
                 before, len(rows), rep["exact_dup"], rep["customer_multi"])

    fname = HC.write_csv(rows, cfg["output_dir"], batch)
    high = sum(1 for r in rows if r["意向等级"] == "高")
    log.info("已写 CSV：%s（%d 条，高意向 %d）", fname, len(rows), high)

    result = {
        "ok": True, "batch": batch, "csv": fname,
        "collected": len(raw), "after_dedupe": len(rows), "high": high,
        "pushed": 0, "skipped_cloud": 0, "log": log_path,
    }

    # ---------- 3. 写入资料库 ----------
    if args.no_push:
        log.info("按 --no-push 跳过入库。下次可在工作台「导入 CSV」选 %s", fname)
    else:
        token = resolve_token(args.token)
        if not token:
            log.warning("未找到 token（--token / HUB_TOKEN / .hub_token），跳过入库。"
                        "本地 CSV 已生成，可在工作台手动导入。")
        else:
            try:
                import huoke_push as HP
                from dedupe import diff_against_existing, cloud_row_to_csv
                existing = [cloud_row_to_csv(r) for r in HP.fetch_existing(HP.LEADS_DB, token)]
                new_rows, skipped = diff_against_existing(rows, existing)
                result["skipped_cloud"] = skipped
                log.info("云端已有 %d 条，本次重复 %d 条跳过，新增 %d 条",
                         len(existing), skipped, len(new_rows))
                if new_rows:
                    total = 0
                    for c in HP.chunked([HP.lead_to_props(r) for r in new_rows], 100):
                        res = HP.push_records(HP.LEADS_DB, c, token, False)
                        total += (res.get("count", len(c)) if isinstance(res, dict) else len(c)) or len(c)
                    result["pushed"] = total
                    log.info("已写入意向客户表 %d 条", total)
                    if not args.no_push:
                        HP.push_records(HP.TASKS_DB, [HP.build_task_from_rows(new_rows, {"scanned": len(raw)})], token, False)
                        log.info("已写入采集任务表 1 条（批次 %s）", batch)
                else:
                    log.info("本次无新增线索（全部与云端重复），不写库。")
            except Exception as e:
                log.error("入库失败：%s（本地 CSV 已保存，可手动导入）", e)
                log.debug(traceback.format_exc())
                result["push_error"] = str(e)[:200]

    dur = (datetime.datetime.now() - started).total_seconds()
    log.info("完成，用时 %.1fs", dur)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
