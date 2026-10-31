# -*- coding: utf-8 -*-
"""
线索雷达 · 真实数据采集器
================================
借鉴 NanmiCoder/MediaCrawler（64k★）的核心思路：
  · 用 Playwright 复用你本机已登录的浏览器态（CDP 连接本地 Chrome / 持久化上下文），
    绕过签名加密，采集抖音 / 小红书 关键词搜索下的公开评论；
  · 同时支持直接读取 MediaCrawler 导出的 jsonl，一键转成工作台可用的 CSV；
  · 内置「样本模拟」模式，无需浏览器即可验证整条数据管线；
  · 采集后自动去重合并（同一条评论 / 同一客户多条评论）。

三种模式：
  --mode mock          读取 sample_comments.json 生成 CSV（默认，可离线验证）
  --mode mediacrawler  读取 MediaCrawler 的 data/<平台>/search_comments_*.jsonl
  --mode browser       真实启动浏览器采集（需本机 Chrome + 已登录态）

输出：data/huoke_leads_<批次>.csv  —— 字段与「线索雷达」工作台完全对齐。

声明：本工具仅供个人工作 / 学习 / 研究使用，严禁任何商业用途。
      仅采集平台公开可见的评论文本，不获取手机号 / 私信等隐私数据；
      请遵守目标平台服务条款与《网络安全法》《反不正当竞争法》，控制频率、勿大规模抓取。
"""

import argparse
import csv
import json
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from intent import analyze, is_relevant  # noqa: E402
from dedupe import merge_rows  # noqa: E402

PLATFORM_CN = {
    "douyin": "抖音", "dy": "抖音", "抖音": "抖音",
    "xhs": "小红书", "xiaohongshu": "小红书", "小红书": "小红书",
    "ks": "快手", "kuaishou": "快手", "bili": "B站", "bilibili": "B站",
    "wb": "微博", "weibo": "微博", "tieba": "贴吧", "zhihu": "知乎",
}

# 平台别名归一：样本/导出目录可能用不同写法
PLAT_KEYS = {
    "douyin": ["douyin", "dy"],
    "xhs": ["xhs", "xiaohongshu"],
    "ks": ["ks", "kuaishou"],
    "bili": ["bili", "bilibili"],
    "wb": ["wb", "weibo"],
}

CSV_FIELDS = [
    "客户昵称", "来源平台", "评论内容", "行业分类", "意向等级", "意向分",
    "命中关键词", "采集关键词", "主页链接", "跟进状态", "备注", "采集时间", "批次", "用户ID",
]


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def batch_id():
    # 加 2 位随机后缀：避免同一秒内跑两次（手动 + 定时撞车）覆盖同一份 CSV
    import random
    return "B" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "%02d" % random.randint(0, 99)


def load_config(path):
    cfg = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("keywords", ["家具"])
    cfg.setdefault("platforms", ["douyin", "xiaohongshu"])
    cfg.setdefault("max_notes", 10)
    cfg.setdefault("max_comments_per_note", 20)
    cfg.setdefault("scroll_rounds", 10)
    cfg.setdefault("page_timeout", 20000)
    cfg.setdefault("output_dir", os.path.join(HERE, "data"))
    cfg.setdefault("headless", False)
    cfg.setdefault("enable_cdp", True)
    cfg.setdefault("cdp_port", 9222)
    cfg.setdefault("user_data_dir", os.path.join(HERE, "browser_data"))
    cfg.setdefault("dedupe_mode", "exact")   # exact=只去完全重复 | customer=同一客户归并为一条
    return cfg


def _sample_block(kw_block, plat):
    """按平台别名从样本里取列表（样本可能用 xiaohongshu，配置里写 xhs）。"""
    for k in [plat] + PLAT_KEYS.get(plat, []):
        if k in kw_block:
            return kw_block[k]
    return []


def collect_mock(cfg):
    """读取内置样本，模拟真实评论结构（用于离线验证管线）。"""
    sample_path = os.path.join(HERE, "sample_comments.json")
    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw = []
    for kw in cfg["keywords"]:
        kw_block = data.get(kw, {})
        for p in cfg["platforms"]:
            plat = p.lower()
            for item in _sample_block(kw_block, plat):
                raw.append({
                    "name": item.get("name", ""),
                    "comment": item.get("comment", ""),
                    "platform": PLATFORM_CN.get(plat, p),
                    "note_title": item.get("note_title", ""),
                    "url": item.get("url", ""),
                    "author_url": item.get("author_url", ""),
                    "uid": item.get("uid", ""),
                    "like": item.get("like", 0),
                    "keyword": kw,
                    "collected_at": now_str(),
                })
    return raw


def _pick(d, *keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _ts_to_str(v):
    try:
        v = float(v)
        if v > 1e12:  # 毫秒
            v = v / 1000.0
        return datetime.datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _author_url_of(plat, row):
    """MediaCrawler 里通常没有完整主页链接，按用户ID拼一个可点击的。"""
    uid = str(_pick(row, "user_id", "userId", default=""))
    if not uid:
        return ""
    if plat in ("douyin", "dy", "抖音"):
        return f"https://www.douyin.com/user/{uid}"
    if plat in ("xiaohongshu", "xhs", "小红书"):
        return f"https://www.xiaohongshu.com/user/profile/{uid}"
    return ""


def collect_mediacrawler(cfg, mc_dir):
    """读取 MediaCrawler 导出的 jsonl（data/<平台>/search_comments_*.jsonl）。"""
    if not mc_dir:
        mc_dir = os.path.join(HERE, "mediacrawler_data")
    raw = []
    if not os.path.isdir(mc_dir):
        print(f"[mediacrawler] 未找到目录：{mc_dir}")
        return raw
    for root, _dirs, files in os.walk(mc_dir):
        for fn in files:
            if not (fn.endswith(".jsonl") or fn.endswith(".json")):
                continue
            plat = os.path.basename(root).split("_")[0].lower()
            plat_cn = PLATFORM_CN.get(plat, plat)
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    comment = _pick(row, "content", "comment_content", "comment")
                    if not comment:
                        continue
                    raw.append({
                        "name": _pick(row, "nickname", "user_name", "name", "author"),
                        "comment": comment,
                        "platform": plat_cn,
                        "note_title": _pick(row, "note_title", "title", "ip_location"),
                        "url": _pick(row, "note_id", "aweme_id", "talk_id", "item_id", "url"),
                        "author_url": _author_url_of(plat, row),
                        "uid": _pick(row, "user_id", "userId"),
                        "like": _pick(row, "like_count", "digg_count", "sub_comment_count", default=0),
                        "keyword": _pick(row, "keyword", "search_keyword", default=""),
                        "collected_at": _ts_to_str(_pick(row, "add_ts", "create_time", "last_modify_ts", default="")) or now_str(),
                    })
    return raw


def collect_browser(cfg):
    """真实浏览器采集（选择器与反风控策略见 browser_collect.py）。"""
    try:
        from browser_collect import BrowserCollector
    except Exception as e:
        print(f"[browser] 无法加载采集模块：{e}")
        return []
    try:
        with BrowserCollector(cfg) as bc:
            return bc.collect()
    except RuntimeError as e:
        print(f"[browser] {e}")
        return []
    except Exception as e:
        print(f"[browser] 采集异常：{type(e).__name__}: {e}")
        return []


def build_rows(raw):
    """对原始评论跑意向识别，组装成对齐工作台的 CSV 行。

    主题相关性过滤：仅保留命中意向词(HOT/SOFT)或行业词库的评论，
    丢弃纯时间戳属地行、无关闲聊等噪音（避免「温州 靓号」搜索混入无关商机）。
    """
    b = batch_id()
    rows = []
    dropped = 0
    for r in raw:
        a = analyze(r.get("comment", ""), keyword=r.get("keyword", ""),
                    platform=r.get("platform", ""), name=r.get("name", ""))
        if not is_relevant(a["comment"]):
            dropped += 1
            continue
        rows.append({
            "客户昵称": a["name"],
            "来源平台": a["platform"],
            "评论内容": a["comment"],
            "行业分类": a["industry"],
            "意向等级": a["level"],
            "意向分": a["score"],
            "命中关键词": a["keywords"],
            "采集关键词": r.get("keyword", ""),
            "主页链接": r.get("author_url") or r.get("url", ""),
            "跟进状态": "待跟进",
            "备注": "",
            "采集时间": r.get("collected_at", now_str()),
            "批次": b,
            "用户ID": r.get("uid", ""),
        })
    if dropped:
        print(f"[相关性过滤] 丢弃 {dropped} 条无关评论（未命中意向词/行业词库）")
    return rows, b


def write_csv(rows, output_dir, b):
    os.makedirs(output_dir, exist_ok=True)
    fname = os.path.join(output_dir, f"huoke_leads_{b}.csv")
    with open(fname, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return fname


def summarize(rows):
    total = len(rows)
    high = sum(1 for r in rows if r["意向等级"] == "高")
    mid = sum(1 for r in rows if r["意向等级"] == "中")
    low = sum(1 for r in rows if r["意向等级"] == "低")
    platforms = {}
    for r in rows:
        platforms[r["来源平台"]] = platforms.get(r["来源平台"], 0) + 1
    return total, high, mid, low, platforms


def main():
    ap = argparse.ArgumentParser(description="线索雷达 · 真实数据采集器")
    ap.add_argument("--mode", choices=["mock", "mediacrawler", "browser"], default="mock")
    ap.add_argument("--keyword", nargs="*", help="覆盖 config 的关键词，如 --keyword 家具 减脂")
    ap.add_argument("--platform", nargs="*", help="覆盖 config 的平台，如 --platform douyin xhs")
    ap.add_argument("--mc-dir", default="", help="mediacrawler 模式的 data 目录")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--out", default="", help="CSV 输出目录")
    # 采集强度
    ap.add_argument("--max-notes", type=int, default=0, help="每个关键词最多进多少个内容（默认取 config）")
    ap.add_argument("--max-comments", type=int, default=0, help="每个内容最多采多少条评论（默认取 config）")
    ap.add_argument("--scroll-rounds", type=int, default=0, help="评论区滚动轮数")
    ap.add_argument("--headless", action="store_true", help="browser 模式无头运行（定时任务用）")
    ap.add_argument("--no-cdp", action="store_true", help="不连本机 Chrome，改用持久化上下文")
    # 去重
    ap.add_argument("--dedupe", choices=["exact", "customer", "off"], default="",
                    help="exact=只合并完全重复(默认) / customer=同一客户归并为一条 / off=不去重")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.keyword:
        cfg["keywords"] = args.keyword
    if args.platform:
        cfg["platforms"] = args.platform
    if args.out:
        cfg["output_dir"] = args.out
    if args.max_notes:
        cfg["max_notes"] = args.max_notes
    if args.max_comments:
        cfg["max_comments_per_note"] = args.max_comments
    if args.scroll_rounds:
        cfg["scroll_rounds"] = args.scroll_rounds
    if args.headless:
        cfg["headless"] = True
    if args.no_cdp:
        cfg["enable_cdp"] = False
    if args.dedupe:
        cfg["dedupe_mode"] = args.dedupe

    print(f"== 线索雷达采集器 == 模式: {args.mode} | 关键词: {cfg['keywords']} | 平台: {cfg['platforms']}"
          f" | 去重: {cfg.get('dedupe_mode')}")

    if args.mode == "mock":
        raw = collect_mock(cfg)
    elif args.mode == "mediacrawler":
        raw = collect_mediacrawler(cfg, args.mc_dir)
    else:
        raw = collect_browser(cfg)

    if not raw:
        print("[!] 未采集到任何评论，请检查配置 / 登录态 / 目录。")
        sys.exit(1)

    rows, b = build_rows(raw)

    # ---- 去重合并 ----
    mode = cfg.get("dedupe_mode", "exact")
    before = len(rows)
    if mode != "off":
        rows, rep = merge_rows(rows, one_per_customer=(mode == "customer"))
        print(f"[去重] {before} → {len(rows)} 条（完全重复 {rep['exact_dup']}，"
              f"同客户多条 {rep['customer_multi']}"
              + ("，已归并为一人一条" if rep["one_per_customer"] else "") + "）")

    fname = write_csv(rows, cfg["output_dir"], b)
    total, high, mid, low, plat = summarize(rows)

    print("-" * 50)
    print(f"批次: {b}")
    print(f"采集评论: {total} 条 | 高意向 {high} | 中意向 {mid} | 低意向 {low}")
    print(f"平台分布: {plat}")
    print(f"已写出: {fname}")
    print("\n下一步 → 接入工作台：")
    print(f"  python huoke_push.py \"{fname}\"          # 直接写入资料库（写前自动与云端比对去重）")
    print("  或在工作台「意向客户」页点「导入 CSV」选择该文件（本地导入）")


if __name__ == "__main__":
    main()
