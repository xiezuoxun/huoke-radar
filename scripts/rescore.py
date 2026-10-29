# -*- coding: utf-8 -*-
"""对已采集的 CSV 重新打分（改了词库/阈值后无需重新采集）。

用法：
  python rescore.py data/xxx.csv [data/yyy.csv ...]     # 原地覆盖
  python rescore.py --dry data/xxx.csv                  # 只看变化，不写
"""
import csv
import io
import os
import sys

import intent

FIELDS = ["客户昵称", "来源平台", "评论内容", "行业分类", "意向等级", "意向分",
          "命中关键词", "采集关键词", "主页链接", "跟进状态", "备注", "采集时间",
          "批次", "用户ID"]


def rescore(path, dry=False):
    rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig")))
    up = down = 0
    for r in rows:
        old = r.get("意向等级") or ""
        a = intent.analyze(r.get("评论内容") or "", keyword=r.get("采集关键词") or "")
        r["意向分"] = str(a["score"])
        r["意向等级"] = a["level"]
        r["命中关键词"] = a["keywords"]
        if not r.get("行业分类") or r["行业分类"] in ("综合行业", ""):
            r["行业分类"] = a["industry"]
        if a["level"] != old:
            if a["level"] == "高" or (a["level"] == "中" and old == "低"):
                up += 1
            else:
                down += 1

    if not dry:
        with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows([{k: (r.get(k) or "") for k in FIELDS} for r in rows])

    hi = sum(1 for r in rows if r["意向等级"] == "高")
    mid = sum(1 for r in rows if r["意向等级"] == "中")
    print(f"{os.path.basename(path)} → {len(rows)} 条 | 高 {hi} / 中 {mid} / 低 {len(rows)-hi-mid}"
          f" | 上调 {up} 下调 {down}" + ("（dry-run 未写回）" if dry else ""))
    return rows


def main():
    args = [a for a in sys.argv[1:] if a != "--dry"]
    dry = "--dry" in sys.argv
    if not args:
        print(__doc__)
        return 1
    for p in args:
        if os.path.exists(p):
            rescore(p, dry)
        else:
            print(f"文件不存在：{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
