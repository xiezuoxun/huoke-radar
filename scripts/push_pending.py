# -*- coding: utf-8 -*-
"""
线索雷达 · 补推待入库批次（幂等）
================================
扫描 collector/data 下所有 huoke_leads_B*.csv，与云端已有记录做增量去重，
把尚未写入资料库的线索补齐入云。任何采集路径（页面/CLI/定时任务/agent 服务）
只要落了本地 CSV，本脚本都能把缺失部分推上去——因此可作为「采集后自动推」的兜底。

  · 意向客户表：获客意向客户  (MjDdEbw22n8gTgFBOrPurw)
  · 采集任务表：获客采集任务  (i10XscWBOy9GwEoaCocg39)

用法：
  python push_pending.py --token <token>            # 补齐所有未入库批次
  python push_pending.py --token <token> --dry-run  # 只打印将写多少，不联网
  python push_pending.py --token <token> --min-score 45   # 只推意向分 >=45 的
  python push_pending.py --token <token> --batch B2026102910041141  # 只推指定批次

Token 优先级：--token 参数  >  环境变量 HUB_TOKEN  >  同目录 .hub_token 文件。
脚本重复执行是安全的：已入云的记录会被云端比对自动跳过，不会产生重复。

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import argparse
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import huoke_push as HP  # noqa: E402
from dedupe import diff_against_existing, cloud_row_to_csv  # noqa: E402

DATA_DIR = os.path.join(HERE, "data")


def list_batches(only=None):
    """返回 [(batch_id, path, rows)]，按批次时间升序。"""
    out = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "huoke_leads_B*.csv"))):
        batch = os.path.basename(p)[len("huoke_leads_"):-len(".csv")]
        if only and batch not in only:
            continue
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        out.append((batch, p, rows))
    return out


def main():
    ap = argparse.ArgumentParser(description="线索雷达 · 补推待入库批次（幂等）")
    ap.add_argument("--token", default="", help="Open Platform token")
    ap.add_argument("--min-score", type=int, default=0,
                    help="只推意向分 >= 该值的记录（0 = 全部）")
    ap.add_argument("--batch", default="", help="只推指定批次 id（可逗号分隔多个）")
    ap.add_argument("--dry-run", action="store_true", help="只统计将写多少，不联网")
    ap.add_argument("--report", action="store_true",
                    help="联网比对但只打印缺失清单，不写入（推荐先跑一次确认）")
    ap.add_argument("--no-task", action="store_true", help="不写采集任务记录")
    args = ap.parse_args()

    token = HP.get_token(args.token)
    if not token and not args.dry_run:
        print("[!] 未找到 token（--token / HUB_TOKEN / .hub_token）")
        return 1

    only = [b.strip() for b in args.batch.split(",") if b.strip()] if args.batch else None
    batches = list_batches(only)
    if not batches:
        print("[*] 没有可补推的批次（本地 CSV 不存在或全为空）")
        return 0

    # 汇总所有待推行（保留批次用于分组）
    all_rows = []
    for batch, path, rows in batches:
        for r in rows:
            r = dict(r)
            r["批次"] = r.get("批次") or batch
            all_rows.append(r)
    total_local = len(all_rows)

    if args.min_score > 0:
        before = total_local
        all_rows = [r for r in all_rows if int(float(r.get("意向分", 0) or 0)) >= args.min_score]
        print("[筛选] 意向分 >= %d：%d → %d 条" % (args.min_score, before, len(all_rows)))

    # 与云端比对（dry-run 时跳过联网，按“全部视为新增”）
    if args.dry_run:
        existing = []
        print("[dry-run] 跳过联网比对，视全部为新增")
    else:
        existing = [cloud_row_to_csv(r) for r in HP.fetch_existing(HP.LEADS_DB, token)]
        print("[比对] 云端已有 %d 条" % len(existing))

    new_rows, skipped = diff_against_existing(all_rows, existing)
    print("[去重] 本地 %d 条 → 待写入 %d 条（云端重复 %d 条跳过）"
          % (len(all_rows), len(new_rows), skipped))

    if not new_rows:
        print("✅ 全部批次已入库，无需补推。")
        return 0

    if args.report:
        by_batch = {}
        for r in new_rows:
            by_batch.setdefault(r["批次"], []).append(r)
        print("[report] 以下批次存在未入库线索（合计 %d 条），未写入："
              % len(new_rows))
        for batch, rows in sorted(by_batch.items()):
            print("  %s → 缺失 %d 条" % (batch, len(rows)))
        print("\n确认无误后去掉 --report 执行补推。")
        return 0

    # 按批次分组，逐批写线索 + 任务
    by_batch = {}
    for r in new_rows:
        by_batch.setdefault(r["批次"], []).append(r)

    total_pushed = 0
    for batch, rows in sorted(by_batch.items()):
        if args.dry_run:
            print("  [dry-run] %s → 将写 %d 条" % (batch, len(rows)))
            total_pushed += len(rows)
            continue
        lead_records = [HP.lead_to_props(r) for r in rows]
        cnt = 0
        for c in HP.chunked(lead_records, 100):
            res = HP.push_records(HP.LEADS_DB, c, token, False)
            cnt += (res.get("count", len(c)) if isinstance(res, dict) else len(c)) or len(c)
        total_pushed += cnt
        print("  %s → 写入 %d 条" % (batch, cnt))
        if not args.no_task and not args.dry_run:
            HP.push_records(HP.TASKS_DB,
                            [HP.build_task_from_rows(rows, {"scanned": len(rows) * 4 + 6})],
                            token, False)
            print("  %s → 采集任务表 1 条" % batch)

    if args.dry_run:
        print("\n[dry-run] 合计将写 %d 条。去掉 --dry-run 即真实写入。" % total_pushed)
    else:
        print("\n✅ 补推完成，合计写入 %d 条线索。公网页面经 SDK 实时读库，刷新即见。" % total_pushed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
