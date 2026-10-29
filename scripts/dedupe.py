# -*- coding: utf-8 -*-
"""
线索雷达 · 去重合并引擎
================================
解决三个真实问题：

1) 同一条评论被多次采到（同一视频反复打开、每日定时任务重叠）→ 完全重复，合并为一条；
2) 同一个客户在多个内容下留了多条评论 → 归并为「一个客户一条主记录」，
   以意向分最高的那条作为主内容，其余作为补充证据合并（关键词 / 批次 / 时间）；
3) 新采集的数据与云端已有数据重复 → 写库前做差分，只写增量，避免数据表爆炸。

身份识别优先级（同一平台内）：
    用户ID  >  主页链接  >  昵称
（真实活跃用户昵称会改，但用户ID/主页链接稳定；三者都没有则视为不同客户，不合并）

跟进状态合并取「推进最远」的那一档，绝不因为去重把已成交客户回退成待跟进。

声明：本文件仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import re

# 跟进状态推进程度，数字越大越靠后（合并时取最大）
FOLLOW_RANK = {
    "待跟进": 0,
    "已联系": 1,
    "已加微": 2,
    "已成交": 3,
    "无效": -1,
}

# 参与「证据合并」的字段：多行合并时去重后拼接
MERGE_LIST_FIELDS = ["命中关键词", "采集关键词", "批次"]

_PUNCT = re.compile(r"[\s\u3000,,。.!！?？~～、;；:：\"'“”‘’()（）\[\]【】<>《》\-—_+*#/\\|]+")


def norm_text(s):
    """归一化文本：去空白、去标点、转小写，用于判重。"""
    return _PUNCT.sub("", str(s or "")).lower()


def _first(row, *keys):
    for k in keys:
        v = str(row.get(k, "") or "").strip()
        if v:
            return v
    return ""


def identity_keys(row):
    """返回该行的全部身份候选键（按优先级排序）。

    为什么要多个：云端记录可能只有「主页链接」没有「用户ID」，
    而本地采集同时有两者 —— 只用一个键做跨源比对会漏判重复。
    """
    plat = _first(row, "来源平台", "platform")
    uid = _first(row, "用户ID", "用户id", "uid", "user_id")
    url = _first(row, "主页链接", "url", "author_url")
    name = _first(row, "客户昵称", "nickname", "name")
    keys = []
    if uid:
        keys.append(f"{plat}|uid:{uid}")
    if url:
        keys.append(f"{plat}|url:{url}")
    if name:
        keys.append(f"{plat}|name:{norm_text(name)}")
    return keys


def identity_key(row):
    """返回主身份 key（平台内唯一）。无有效身份信息时返回 None（不参与合并）。"""
    keys = identity_keys(row)
    return keys[0] if keys else None


def comment_keys(row):
    """返回该评论的全部去重候选键（身份候选 × 归一化正文）。"""
    body = norm_text(_first(row, "评论内容", "comment", "content"))
    if not body:
        return []
    return [f"{k}|{body}" for k in identity_keys(row)]


def comment_key(row):
    """返回评论主去重 key（同一客户同一条评论）。"""
    keys = comment_keys(row)
    if keys:
        return keys[0]
    body = norm_text(_first(row, "评论内容", "comment", "content"))
    return f"anon|{body}" if body else None


def _score(row):
    try:
        return int(float(row.get("意向分", 0) or 0))
    except Exception:
        return 0


def _level_of(score):
    return "高" if score >= 85 else ("中" if score >= 60 else "低")


def _merge_list_field(values):
    seen, out = set(), []
    for v in values:
        for part in str(v or "").replace(",", "/").split("/"):
            p = part.strip()
            if p and p not in seen:
                seen.add(p)
                out.append(p)
    return " / ".join(out)


def _merge_follow(values):
    best = "待跟进"
    best_rank = -99
    for v in values:
        r = FOLLOW_RANK.get(str(v or "").strip(), 0)
        if r > best_rank:
            best_rank = r
            best = str(v or "").strip() or "待跟进"
    return best


def _earliest(times):
    vals = [t for t in times if t]
    return min(vals) if vals else ""


def merge_group(rows):
    """把同一客户的多条记录合并成一条主记录。"""
    if len(rows) == 1:
        return dict(rows[0])

    # 主记录 = 意向分最高（并列取较早采集的）
    rows = sorted(rows, key=lambda r: (-_score(r), _first(r, "采集时间") or "9999"))
    main = dict(rows[0])
    best = max(_score(r) for r in rows)
    main["意向分"] = best
    main["意向等级"] = _level_of(best)
    for f in MERGE_LIST_FIELDS:
        main[f] = _merge_list_field([r.get(f, "") for r in rows])
    main["跟进状态"] = _merge_follow([r.get("跟进状态", "") for r in rows])
    t = _earliest([_first(r, "采集时间") for r in rows])
    if t:
        main["采集时间"] = t
    # 备注：保留非空且不重复的
    notes = []
    for r in rows:
        n = _first(r, "备注")
        if n and n not in notes:
            notes.append(n)
    main["备注"] = "；".join(notes)
    # 主页链接优先取非空且像用户主页的
    for r in rows:
        u = _first(r, "主页链接")
        if u:
            main["主页链接"] = u
            break
    return main


def merge_rows(rows, one_per_customer=False):
    """去重合并。

    Args:
        rows: 行字典列表（字段名与工作台 CSV 一致）
        one_per_customer: True 时同一客户只保留一条主记录（默认 False，
                          仅合并「完全重复」，同一客户的多条不同评论各自保留）

    Returns:
        (deduped_rows, report)  report 含统计信息
    """
    total = len(rows)

    # 第一步：完全重复（同客户 + 同内容）合并
    by_comment = {}
    order = []
    for r in rows:
        k = comment_key(r)
        if k is None:
            # 无内容/无身份，按对象保序列，不参与合并
            order.append(("__raw__", len(order)))
            by_comment[("__raw__", len(order) - 1)] = [r]
            continue
        if k not in by_comment:
            by_comment[k] = []
            order.append(k)
        by_comment[k].append(r)

    stage1 = [merge_group(by_comment[k]) for k in order]
    exact_dup = total - len(stage1)

    # 第二步（可选）：同一客户归并为一条
    cust_merged = 0
    if one_per_customer:
        by_cust = {}
        cust_order = []
        passthrough = []
        for r in stage1:
            ident = identity_key(r)
            if ident is None:
                passthrough.append(r)
                continue
            if ident not in by_cust:
                by_cust[ident] = []
                cust_order.append(ident)
            by_cust[ident].append(r)
        stage2 = []
        for ident in cust_order:
            group = by_cust[ident]
            if len(group) > 1:
                cust_merged += len(group) - 1
            stage2.append(merge_group(group))
        stage2.extend(passthrough)
        final = stage2
    else:
        final = stage1
        # 统计「同一客户多条评论」的情况，仅用于报告
        seen = {}
        for r in stage1:
            ident = identity_key(r)
            if ident:
                seen[ident] = seen.get(ident, 0) + 1
        cust_merged = sum(v - 1 for v in seen.values() if v > 1)

    # 按意向分降序，便于工作台首屏看到最热的
    final.sort(key=lambda r: (-_score(r), _first(r, "采集时间")))

    report = {
        "in": total,
        "out": len(final),
        "exact_dup": exact_dup,
        "customer_dup": cust_merged if one_per_customer else 0,
        "customer_multi": cust_merged,
        "one_per_customer": one_per_customer,
    }
    return final, report


def diff_against_existing(new_rows, existing_rows):
    """写库前增量比对：返回 existing 中不存在的行（按评论 key 判重）。

    existing_rows 需要能被 comment_keys 处理（云端行先用 cloud_row_to_csv 转换）。
    采用「任一身份候选键命中即判重」，避免云端缺用户ID时误判为新数据。
    """
    existing_keys = set()
    for r in existing_rows:
        for k in comment_keys(r):
            existing_keys.add(k)

    out = []
    skipped = 0
    for r in new_rows:
        keys = comment_keys(r)
        if keys and any(k in existing_keys for k in keys):
            skipped += 1
            continue
        for k in keys:
            existing_keys.add(k)  # 新行内部也去重
        out.append(r)
    return out, skipped


# ============ 云端行 → CSV 同名字段（供 push 前比对） ============
def cloud_row_to_csv(row):
    """把资料库返回的 {字段: 值 或 {type:值}} 结构转成 CSV 同名字段字典。"""
    def val(v):
        if isinstance(v, dict):
            for k in ("text", "select", "number", "string", "value"):
                if k in v:
                    return v[k]
            return ""
        if isinstance(v, list):
            parts = []
            for it in v:
                if isinstance(it, dict):
                    parts.append(str(it.get("text") or it.get("name") or ""))
                else:
                    parts.append(str(it))
            return " / ".join([p for p in parts if p])
        return v if v is not None else ""

    keys = ["客户昵称", "来源平台", "评论内容", "行业分类", "意向等级", "意向分",
            "命中关键词", "采集关键词", "主页链接", "跟进状态", "备注", "采集时间", "批次", "用户ID"]
    out = {}
    for k in keys:
        out[k] = val(row.get(k, ""))
    return out


if __name__ == "__main__":
    # 自测：构造「完全重复」「同客户多条」「不同客户」三类样本
    demo = [
        # 同一客户 A，两条不同评论（一条高意向一条低）
        {"客户昵称": "小王", "来源平台": "抖音", "评论内容": "这套沙发多少钱？链接发一下",
         "意向分": 90, "意向等级": "高", "命中关键词": "价格", "采集关键词": "家具",
         "批次": "B1", "采集时间": "2026-10-27 09:00", "跟进状态": "待跟进", "主页链接": "https://douyin.com/user/u1", "用户ID": "u1"},
        {"客户昵称": "小王", "来源平台": "抖音", "评论内容": "好看",
         "意向分": 35, "意向等级": "低", "命中关键词": "", "采集关键词": "家具",
         "批次": "B2", "采集时间": "2026-10-27 10:00", "跟进状态": "已联系", "主页链接": "https://douyin.com/user/u1", "用户ID": "u1"},
        # 完全重复（同客户同内容，仅采集时间不同）
        {"客户昵称": "小王", "来源平台": "抖音", "评论内容": "这套沙发多少钱, 链接发一下!",
         "意向分": 90, "意向等级": "高", "命中关键词": "价格", "采集关键词": "家具",
         "批次": "B3", "采集时间": "2026-10-27 11:00", "跟进状态": "已加微", "主页链接": "https://douyin.com/user/u1", "用户ID": "u1"},
        # 不同平台同名（不应合并）
        {"客户昵称": "小王", "来源平台": "小红书", "评论内容": "多少钱",
         "意向分": 52, "意向等级": "低", "命中关键词": "多少钱", "采集关键词": "家具",
         "批次": "B1", "采集时间": "2026-10-27 09:30", "跟进状态": "待跟进", "主页链接": "https://xhs.com/user/u9", "用户ID": "u9"},
    ]

    print("=== 仅合并完全重复（保留同客户多条评论）===")
    out, rep = merge_rows(demo, one_per_customer=False)
    print(f"输入 {rep['in']} → 输出 {rep['out']}（完全重复剔除 {rep['exact_dup']}）")
    for r in out:
        print(f"  [{r['来源平台']}] {r['客户昵称']} | {r['评论内容'][:20]} | {r['意向等级']}{r['意向分']} | 状态={r['跟进状态']} | 批次={r['批次']} | 时间={r['采集时间']}")

    print("\n=== 同一客户归并为一条 ===")
    out2, rep2 = merge_rows(demo, one_per_customer=True)
    print(f"输入 {rep2['in']} → 输出 {rep2['out']}（完全重复 {rep2['exact_dup']}，客户归并 {rep2['customer_dup']}）")
    for r in out2:
        print(f"  [{r['来源平台']}] {r['客户昵称']} | {r['评论内容'][:20]} | {r['意向等级']}{r['意向分']} | 状态={r['跟进状态']} | 批次={r['批次']} | 时间={r['采集时间']} | 关键词={r['命中关键词']}")

    print("\n=== 增量比对 ===")
    existing = [cloud_row_to_csv({"客户昵称": {"text": "小王"}, "来源平台": {"select": "抖音"},
                                  "评论内容": {"text": "这套沙发多少钱？链接发一下"}, "意向分": {"number": 90},
                                  "跟进状态": {"select": "待跟进"}, "采集时间": {"text": "2026-10-27 09:00"},
                                  "批次": {"text": "B1"}, "主页链接": {"text": "https://douyin.com/user/u1"}})]
    new_only, skipped = diff_against_existing(demo, existing)
    print(f"新数据 {len(demo)} 条，云端已存在 {skipped} 条重复，需写入 {len(new_only)} 条")
    for r in new_only:
        print(f"  + [{r['来源平台']}] {r['客户昵称']} | {r['评论内容'][:20]} | {r['意向分']}")
