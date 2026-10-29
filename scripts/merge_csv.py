# -*- coding: utf-8 -*-
"""把多批采集 CSV 合并成一份，按「客户身份 + 评论内容」去重，保持首次出现顺序。

用法：
  python merge_csv.py out.csv a.csv b.csv c.csv
"""
import csv
import io
import os
import sys

FIELDS = ["客户昵称", "来源平台", "评论内容", "行业分类", "意向等级", "意向分",
          "命中关键词", "采集关键词", "主页链接", "跟进状态", "备注", "采集时间",
          "批次", "用户ID"]


def norm(s):
    return "".join(str(s or "").split())


def main():
    if len(sys.argv) < 3:
        print("用法: python merge_csv.py <out.csv> <in1.csv> [in2.csv ...]")
        return 1
    out_path, inputs = sys.argv[1], sys.argv[2:]

    seen = set()
    rows, skipped = [], 0
    for p in inputs:
        if not os.path.exists(p):
            print(f"跳过不存在的文件：{p}")
            continue
        with io.open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                uid = norm(r.get("用户ID")) or norm(r.get("客户昵称"))
                key = uid + "|" + norm(r.get("评论内容"))
                if key in seen:
                    skipped += 1
                    continue
                seen.add(key)
                rows.append({k: (r.get(k) or "") for k in FIELDS})

    with io.open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    hi = sum(1 for r in rows if r["意向等级"] == "高")
    mid = sum(1 for r in rows if r["意向等级"] == "中")
    low = sum(1 for r in rows if r["意向等级"] == "低")
    plat = {}
    for r in rows:
        plat[r["来源平台"]] = plat.get(r["来源平台"], 0) + 1
    print(f"合并完成：{len(rows)} 条（去重跳过 {skipped} 条）")
    print(f"意向分布：高 {hi} / 中 {mid} / 低 {low}")
    print(f"平台分布：{plat}")
    print(f"输出：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
