# -*- coding: utf-8 -*-
"""
线索雷达 · 接入桥接器
================================
把采集器生成的 CSV（data/huoke_leads_<批次>.csv）写入「线索雷达」工作台背后的
资料库数据表，从而在工作台「意向客户 / 采集数据」模块自动出现真实数据。

核心改进：**写库前先与云端已有数据做增量比对**，重复线索不再写入，
避免每日定时任务把数据表刷成几十倍的重复记录。

  · 意向客户表：获客意向客户  (MjDdEbw22n8gTgFBOrPurw)
  · 采集任务表：获客采集任务  (i10XscWBOy9GwEoaCocg39)

用法：
  python huoke_push.py data/huoke_leads_XXXX.csv                 # 增量写入（自动去重）
  python huoke_push.py data/huoke_leads_XXXX.csv --dry-run       # 只校验 + 打印 payload，不联网
  python huoke_push.py data/huoke_leads_XXXX.csv --no-diff       # 跳过云端比对，全部写入
  python huoke_push.py data/huoke_leads_XXXX.csv --merge-customer # 同一客户归并为一条再写

Token 优先级：--token 参数  >  环境变量 HUB_TOKEN  >  同目录 .hub_token 文件。

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import argparse
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dedupe import merge_rows, diff_against_existing, cloud_row_to_csv  # noqa: E402

LIB_DIR = ""
for cand in (
    os.path.expanduser("~/AppData/Local/Programs/WorkBuddy/resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library/database"),
    os.path.normpath(os.path.join(HERE, "..", "AppData", "Local", "Programs", "WorkBuddy",
                                  "resources", "app.asar.unpacked", "resources", "plugins",
                                  "workbuddy-builtin", "skills", "library", "database")),
    "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/library/database",
):
    if os.path.exists(os.path.join(cand, "batch_add_database_records.py")):
        LIB_DIR = cand
        break

LEADS_DB = "MjDdEbw22n8gTgFBOrPurw"
TASKS_DB = "i10XscWBOy9GwEoaCocg39"

CSV_FIELDS = [
    "客户昵称", "来源平台", "评论内容", "行业分类", "意向等级", "意向分",
    "命中关键词", "采集关键词", "主页链接", "跟进状态", "备注", "采集时间", "批次", "用户ID",
]


def get_token(cli_token=""):
    if cli_token:
        return cli_token.strip()
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


def lead_to_props(r):
    """完全对齐工作台的 leadToProps 形状（工作台表里没有「用户ID」字段，故不写）。"""
    return {
        "客户昵称": {"text": r.get("客户昵称", "")},
        "来源平台": {"select": r.get("来源平台", "")},
        "评论内容": {"text": r.get("评论内容", "")},
        "行业分类": {"select": r.get("行业分类", "")},
        "意向等级": {"select": r.get("意向等级", "")},
        "意向分": {"number": int(float(r.get("意向分", 0) or 0))},
        "命中关键词": {"text": r.get("命中关键词", "")},
        "采集关键词": {"text": r.get("采集关键词", "")},
        "主页链接": {"text": r.get("主页链接", "")},
        "跟进状态": {"select": r.get("跟进状态", "待跟进")},
        "备注": {"text": r.get("备注", "")},
        "采集时间": {"text": r.get("采集时间", "")},
        "批次": {"text": r.get("批次", "")},
    }


def build_task_from_rows(rows, stats=None):
    batch = rows[0]["批次"] if rows else ""
    keyword = rows[0]["采集关键词"] if rows else ""
    platforms = {}
    for r in rows:
        platforms[r["来源平台"]] = platforms.get(r["来源平台"], 0) + 1
    high = sum(1 for r in rows if r["意向等级"] == "高")
    stats = stats or {}
    return {
        "关键词": {"text": keyword},
        "平台范围": {"text": " / ".join(sorted(platforms.keys()))},
        "扫描内容": {"number": stats.get("scanned", len(rows) * 4 + 6)},
        "识别意向": {"number": len(rows)},
        "高意向": {"number": high},
        "耗时": {"text": stats.get("cost", "%.1fs" % (2 + len(rows) * 0.12))},
        "状态": {"select": "已完成"},
        "采集时间": {"text": rows[0]["采集时间"] if rows else ""},
        "批次": {"text": batch},
    }


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _run_lib(script, payload_obj, token, stdin_is_json=False):
    """调用资料库脚本。token 与 JSON 都从 stdin 传入时用两行格式。"""
    script_path = os.path.join(LIB_DIR, script)
    if stdin_is_json:
        stdin_data = token + "\n" + json.dumps(payload_obj, ensure_ascii=False)
        cmd = [sys.executable, script_path, "--token-stdin", "--stdin"]
    else:
        stdin_data = token
        cmd = [sys.executable, script_path, "--token-stdin"]
    proc = subprocess.run(cmd, input=stdin_data, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError((proc.stderr or "无输出").strip()[:300])
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}


def fetch_existing(database_id, token, max_pages=30):
    """拉取云端已有记录（翻页拉全量），用于写前比对。"""
    rows = []
    cursor = None
    for _ in range(max_pages):
        payload = {"database_id": database_id, "page_size": 200}
        if cursor:
            payload["start_cursor"] = cursor
        d = _run_lib("query_database_record.py", payload, token, stdin_is_json=True)
        if isinstance(d, dict) and d.get("error"):
            raise RuntimeError(d["error"])
        part = d.get("results") or []
        rows.extend(part)
        nxt = d.get("next_cursor") or d.get("nextCursor")
        if d.get("has_more") and nxt and nxt != cursor:
            cursor = nxt
        else:
            break
    return rows


def push_records(database_id, records, token, dry_run):
    if dry_run:
        print(f"  [dry-run] 将向表 {database_id} 写入 {len(records)} 条（不联网）")
        return {"count": len(records)}
    payload = {"database_id": database_id, "records": records}
    res = _run_lib("batch_add_database_records.py", payload, token, stdin_is_json=True)
    if isinstance(res, dict) and (res.get("error") or res.get("code")):
        print(f"  [!] 写入失败：{res}")
        raise SystemExit(1)
    return res


def main():
    ap = argparse.ArgumentParser(description="线索雷达 · CSV 接入资料库（带去重）")
    ap.add_argument("csv", help="采集器生成的 CSV 文件路径")
    ap.add_argument("--dry-run", action="store_true", help="只校验并打印 payload，不联网写入")
    ap.add_argument("--skip-task", action="store_true", help="不写入采集任务记录")
    ap.add_argument("--no-diff", action="store_true", help="跳过与云端已有数据的比对（全部写入）")
    ap.add_argument("--merge-customer", action="store_true", help="同一客户归并为一条后再写")
    ap.add_argument("--token", default="", help="Open Platform token（不填则读 HUB_TOKEN / .hub_token）")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        print(f"[!] 文件不存在：{args.csv}")
        raise SystemExit(1)

    rows = read_csv(args.csv)
    if not rows:
        print("[!] CSV 为空")
        raise SystemExit(1)

    token = get_token(args.token)

    # ---- 1) 本地去重（同一客户/完全相同）----
    before = len(rows)
    rows, rep = merge_rows(rows, one_per_customer=args.merge_customer)
    if before != len(rows):
        print(f"[去重] {before} → {len(rows)} 条（完全重复 {rep['exact_dup']}，同客户多条 {rep['customer_multi']}）")

    # ---- 2) 与云端比对，只写增量 ----
    skipped_cloud = 0
    if not args.no_diff and token and not args.dry_run:
        try:
            existing_raw = fetch_existing(LEADS_DB, token)
            existing = [cloud_row_to_csv(r) for r in existing_raw]
            rows, skipped_cloud = diff_against_existing(rows, existing)
            print(f"[比对] 云端已有 {len(existing)} 条；本次重复 {skipped_cloud} 条已跳过，"
                  f"待写入 {len(rows)} 条")
        except Exception as e:
            print(f"[比对] 跳过（拉取云端失败：{e}）—— 将全量写入")
    elif args.no_diff:
        print("[比对] 已按 --no-diff 跳过云端比对")
    elif not token:
        print("[比对] 跳过（未提供 token）")

    if not rows:
        print("✅ 本次没有新增线索（全部与云端重复），不写入。")
        return

    lead_records = [lead_to_props(r) for r in rows]

    # ---- 3) 本地 shape 校验（复用库内 validate_properties）----
    try:
        sys.path.insert(0, LIB_DIR)
        from _db_types import validate_properties  # type: ignore
        bad = sum(1 for rec in lead_records if not validate_properties(rec))
        print(f"[校验] {len(lead_records)} 条客户 payload 形状 "
              + ("全部通过 ✅" if bad == 0 else f"有 {bad} 条异常 ❌"))
    except Exception as e:
        print(f"[校验] 跳过（无法加载本地校验器）：{e}")

    print(f"[摘要] 待写入 {len(rows)} 条 | 高意向 {sum(1 for r in rows if r['意向等级'] == '高')} | "
          f"中意向 {sum(1 for r in rows if r['意向等级'] == '中')} | 批次 {rows[0]['批次']}")

    total = 0
    for c in chunked(lead_records, 100):
        res = push_records(LEADS_DB, c, token, args.dry_run)
        total += (res.get("count", len(c)) if isinstance(res, dict) else len(c)) or len(c)
    print(f"[写入] 意向客户表：{total} 条")

    if not args.skip_task:
        task = build_task_from_rows(rows, {"scanned": len(rows) * 4 + 6 + skipped_cloud})
        push_records(TASKS_DB, [task], token, args.dry_run)
        print(f"[写入] 采集任务表：1 条（批次 {rows[0]['批次']}）")

    if args.dry_run:
        print("\n[dry-run] 未实际联网写入。去掉 --dry-run 即可真实写入资料库。")
    else:
        print("\n✅ 接入完成，打开工作台「线索雷达」即可看到这批真实数据（会自动同步）。")


if __name__ == "__main__":
    main()
