# -*- coding: utf-8 -*-
"""
线索雷达 · 浏览器真实采集模块
================================
借鉴 NanmiCoder/MediaCrawler 的核心思路，但只保留「无需逆向签名」的那条路：
    复用本机真实浏览器登录态  →  关键词搜索  →  进入内容  →  滚动评论区  →  抽取公开评论

相比初版选择器的强化点（都是实战踩坑经验）：
  1. **多候选选择器回退**：每个字段给 3-5 个候选 CSS，任一命中即用，平台改版不至于全废；
  2. **innerText 行切分兜底**：选择器全失效时，按文本行切分推断昵称/内容，仍能出数据；
  3. **JS 内聚合抽取**：一次 evaluate 抽完整页评论，减少跨进程往返，速度快 5-10 倍；
  4. **评论区独立滚动**：抖音评论区是右侧独立滚动容器，直接 window.scroll 无效，
     改为 JS 找可滚动祖先 + 滚到底，headless 下同样有效；
  5. **登录墙检测**：识别到未登录提示立即停下并明确告知，不静默返回 0 条；
  6. **风控检测**：识别验证码/滑块，自动降速重试，避免把账号跑进小黑屋；
  7. **文本清洗**：剔除「作者赞过」「回复」「3天前」「·」「点赞数」等 UI 噪音；
  8. **随机人类化延迟**：每次操作 1.2-2.8s 抖动，控制频率；
  9. **断点续跑**：已采过的视频/笔记 ID 记在 cache 里，重跑不重复打开。

两种连接方式：
  · CDP   —— 连你手动开着的 Chrome（--remote-debugging-port=9222），登录态最真实，适合手动跑；
  · 持久化 —— 独立 user_data 目录，首次扫码登录一次，之后自动复用，适合定时任务无人值守。

声明：仅供个人工作 / 学习 / 研究使用，严禁商用。
      仅采集平台公开可见的评论文本；不获取手机号、私信、身份证等隐私信息；
      遵守平台服务条款与《网络安全法》《反不正当竞争法》，务必控制频率、勿大规模抓取。
"""

import json
import os
import random
import re
import time

# ==================================================================
# 平台画像：URL 模板 + 多候选选择器
# ==================================================================
PROFILES = {
    "douyin": {
        "cn": "抖音",
        "home_url": "https://www.douyin.com/",
        "search_url": "https://www.douyin.com/search/{kw}?type=video",
        "login_hint": ["登录后查看", "扫码登录", "手机号登录", "请先登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "拖动滑块", "captcha"],
        "card_sels": [
            "a[href*='/video/']",
            "div[data-e2e='scroll-list'] a[href*='/video/']",
            "li a[href*='/video/']",
        ],
        "card_href_pat": r"/video/(\d+)",
        "comment_item_sels": [
            "div[data-e2e='comment-item']",
            ".comment-item",
            "[class*='commentItem']",
            "[class*='comment-item']",
        ],
        "comment_name_sels": [
            "a[href*='/user/']",
            ".comment-item-info-wrap a",
            "[class*='userName']",
            "[class*='nickname']",
            "[class*='author'] span",
        ],
        "comment_text_sels": [
            "[data-e2e='comment-level-1'] span",
            ".comment-content span",
            "[class*='commentContent']",
            "[class*='content'] span",
        ],
        "user_link_sels": ["a[href*='/user/']"],
        "user_href_pat": r"/user/([^/?&]+)",
        "expand_sels": ["[data-e2e='comment-icon']", "text=查看全部评论", "text=展开更多"],
    },
    "xhs": {
        "cn": "小红书",
        "home_url": "https://www.xiaohongshu.com/explore",
        "search_url": "https://www.xiaohongshu.com/search_result?keyword={kw}&type=51",
        "login_hint": ["登录后查看", "扫码登录", "手机号登录", "请先登录", "登录可以查看更多"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "拖动滑块", "captcha"],
        # 小红书笔记链接必须带 xsec_token，裸链接会 404「当前笔记暂时无法浏览」
        "use_state_token": True,
        "note_url_tpl": "https://www.xiaohongshu.com/explore/{id}?xsec_token={token}&xsec_source=pc_search",
        "fail_hint": ["当前笔记暂时无法浏览", "你访问的页面不见了", "笔记不存在"],
        "comment_ready_sel": ".comment-item, .parent-comment",
        "card_sels": [
            "a[href*='/explore/']",
            "a[href*='/discovery/item/']",
            "section.note-item a",
            "a.cover[href*='/explore/']",
        ],
        "card_href_pat": r"/(?:explore|discovery/item)/([0-9a-f]+)",
        "comment_item_sels": [
            ".comment-item",
            ".parent-comment",
            ".comment-inner-container",
            "[class*='comment-item']",
            "[class*='commentItem']",
        ],
        "comment_name_sels": [
            ".author-wrapper .name",
            ".author .name",
            "a[href*='/user/profile/'] .name",
            ".name",
            "[class*='nickname']",
        ],
        "comment_text_sels": [
            ".content .note-text",
            ".note-text",
            ".content",
            "[class*='note-text']",
            "[class*='content']",
        ],
        "user_link_sels": ["a[href*='/user/profile/']"],
        "user_href_pat": r"/user/profile/([^/?&]+)",
        "expand_sels": ["text=展开更多评论", "text=查看更多评论", ".show-more"],
    },

    # ---------------- 以下为 bilibili/快手/微博/知乎/闲鱼/58（beta：选择器待实测） ----------------
    "bilibili": {
        "cn": "B站",
        "home_url": "https://www.bilibili.com/",
        "search_url": "https://search.bilibili.com/all?keyword={kw}",
        "login_hint": ["登录后查看", "请先登录", "扫码登录", "登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha"],
        "card_sels": [
            "a[href*='//www.bilibili.com/video/']",
            "a[href*='/video/BV']",
            ".video-list-item a",
            ".bili-video-card a",
        ],
        "card_href_pat": r"/video/(BV[0-9A-Za-z]+)",
        "comment_item_sels": [
            "#comment .reply-item",
            ".reply-item",
            ".sub-reply-item",
            "[class*='reply-item']",
        ],
        "comment_name_sels": [
            ".user-name",
            "a[href*='//space.bilibili.com/']",
            ".sub-user-name",
            "[class*='user-name']",
        ],
        "comment_text_sels": [
            ".reply-content",
            ".root-reply",
            ".content-warp",
            "[class*='reply-content']",
        ],
        "user_link_sels": ["a[href*='//space.bilibili.com/']"],
        "user_href_pat": r"space\.bilibili\.com/(\d+)",
        "expand_sels": ["text=点击查看", "text=展开更多", ".view-more"],
    },
    "kuaishou": {
        "cn": "快手",
        "home_url": "https://www.kuaishou.com/",
        "search_url": "https://www.kuaishou.com/search/video?searchKey={kw}",
        "login_hint": ["登录后查看", "扫码登录", "请先登录", "手机号登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha"],
        "card_sels": [
            "a[href*='/short-video/']",
            "a[href*='/fw/photo/']",
            "[class*='video-card'] a",
        ],
        "card_href_pat": r"/(?:short-video|fw/photo)/([0-9A-Za-z_-]+)",
        # 快手搜索页是纯 JS 渲染，卡片是 div，整页没有一个 /short-video/ 锚点。
        # 结果只在 /rest/v/search/feed 的 JSON 里，photo.id 形如 3xgmgxsyzpdt7j2。
        "xhr_match": "/rest/v/search/feed",
        "xhr_id_re": r'"id"\s*:\s*"([0-9a-z]{12,24})"',
        "xhr_url_tpl": "https://www.kuaishou.com/short-video/{id}",
        "comment_item_sels": [
            ".comment-item",
            "[class*='comment-item']",
            "[class*='commentItem']",
        ],
        "comment_name_sels": [
            "a[href*='/profile/']",
            "[class*='userName']",
            "[class*='nickname']",
        ],
        "comment_text_sels": [
            "[class*='comment-content']",
            "[class*='content']",
            ".text",
        ],
        "user_link_sels": ["a[href*='/profile/']"],
        "user_href_pat": r"/profile/([^/?&]+)",
        "expand_sels": ["text=展开更多", "text=查看更多评论"],
    },
    "weibo": {
        "cn": "微博",
        "home_url": "https://m.weibo.cn/",
        "search_url": "https://m.weibo.cn/search?containerid=100103type%3D1%26q%3D{kw}",
        "login_hint": ["登录后查看", "请先登录", "扫码登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha"],
        "card_sels": [
            "a[href*='/detail/']",
            "a[href*='/status/']",
            ".card a[href*='m.weibo.cn']",
        ],
        "card_href_pat": r"/(?:detail|status)/([0-9A-Za-z]+)",
        "comment_item_sels": [
            ".comment-item",
            "[class*='comment-item']",
            ".item-content",
        ],
        "comment_name_sels": [
            ".m-text-cut",
            "a[href*='/u/']",
            "[class*='nick']",
        ],
        "comment_text_sels": [
            ".text",
            "[class*='comment-content']",
            ".weibo-text",
        ],
        "user_link_sels": ["a[href*='/u/']"],
        "user_href_pat": r"/u/(\d+)",
        "expand_sels": ["text=查看更多", "text=展开"],
    },
    "zhihu": {
        "cn": "知乎",
        "home_url": "https://www.zhihu.com/",
        "search_url": "https://www.zhihu.com/search?type=content&q={kw}",
        "login_hint": ["登录后查看", "请先登录", "扫码登录", "登录知乎"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha", "安全验证"],
        "card_sels": [
            "a[href*='/question/']",
            "a[href*='/answer/']",
            "a[href*='/p/']",
        ],
        "card_href_pat": r"/(?:question|answer|p)/(\d+)",
        "comment_item_sels": [
            ".CommentItem",
            "[class*='CommentItem']",
            ".NestComment",
        ],
        "comment_name_sels": [
            ".CommentItemV2-metaSuffix a",
            "a[href*='/people/']",
            ".UserLink-link",
        ],
        "comment_text_sels": [
            ".CommentRichText",
            ".RichText",
            "[class*='RichText']",
        ],
        "user_link_sels": ["a[href*='/people/']"],
        "user_href_pat": r"/people/([^/?&]+)",
        "expand_sels": ["text=展开阅读全文", "text=查看更多评论"],
    },
    "xianyu": {
        "cn": "闲鱼",
        "home_url": "https://www.goofish.com/",
        "search_url": "https://www.goofish.com/search?q={kw}",
        "login_hint": ["登录后查看", "请先登录", "扫码登录", "手机号登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha"],
        "card_sels": [
            "a[href*='item?id=']",
            "a[href*='/item/']",
            "[class*='item-card'] a",
        ],
        "card_href_pat": r"item\?id=(\d+)",
        "comment_item_sels": [
            "[class*='comment-item']",
            "[class*='commentItem']",
            ".comment",
        ],
        "comment_name_sels": [
            "[class*='nick']",
            "[class*='user-name']",
            "a[href*='goofish.com/personal']",
        ],
        "comment_text_sels": [
            "[class*='comment-content']",
            "[class*='content']",
        ],
        "user_link_sels": ["a[href*='goofish.com/personal']"],
        "user_href_pat": r"personal\?uid=([^&]+)",
        "expand_sels": ["text=查看更多", "text=展开"],
    },
    "wuba58": {
        "cn": "58同城",
        "home_url": "https://wz.58.com/",
        # 温州本地站：租房搜房东 / 二手房找业主，地域写死在 URL 里
        "search_url": "https://wz.58.com/sou/?key={kw}",
        "login_hint": ["登录后查看", "请先登录", "扫码登录"],
        "risk_hint": ["验证码", "滑动验证", "安全验证", "captcha"],
        "card_sels": [
            "a[href*='.shtml']",
            "a[href*='58.com/zufang/']",
            "a[href*='/chuzu/']",
            "a[href*='/hezu/']",
            "a[href*='/ershoufang/']",
        ],
        "card_href_pat": r"/(\d{6,})x?\.shtml",
        # 房源详情页没有评论区，需求信号写在正文里（"房子没宽带""要自己拉网"）。
        "page_text_fallback": True,
        "page_text_sels": [
            "[class*='house-word-introduce']",
            "[class*='house-desc']",
            "[class*='describe']",
            ".house-basic-info",
            "[class*='houseInfo']",
        ],
        "page_name_sels": [
            "[class*='broker'] [class*='name']",
            "[class*='agent'] [class*='name']",
            ".agent-name",
            "h1",
        ],
        "comment_item_sels": [
            "[class*='comment-item']",
            ".comment-list li",
            "[class*='reply']",
        ],
        "comment_name_sels": [
            "[class*='user-name']",
            "[class*='nick']",
            ".name",
        ],
        "comment_text_sels": [
            "[class*='comment-content']",
            "[class*='content']",
            ".desc",
        ],
        "user_link_sels": ["a[href*='58.com/']"],
        "user_href_pat": r"58\.com/([^/?&]+)",
        "expand_sels": ["text=查看更多", "text=展开"],
    },
}

ALIAS = {
    "douyin": "douyin", "dy": "douyin", "抖音": "douyin",
    "xhs": "xhs", "xiaohongshu": "xhs", "小红书": "xhs", "红书": "xhs",
    "bilibili": "bilibili", "bili": "bilibili", "b站": "bilibili", "哔哩哔哩": "bilibili",    "kuaishou": "kuaishou", "ks": "kuaishou", "快手": "kuaishou",
    "weibo": "weibo", "微博": "weibo",
    "zhihu": "zhihu", "知乎": "zhihu",
    "xianyu": "xianyu", "goofish": "xianyu", "闲鱼": "xianyu",
    "wuba58": "wuba58", "58": "wuba58", "58同城": "wuba58", "58.com": "wuba58",
}

# 评论里常见的 UI 噪音（作为整行出现时直接丢弃）
NOISE_LINES = {
    "作者赞过", "作者", "置顶", "展开", "展开更多", "收起", "回复", "分享", "收藏", "点赞",
    "查看全部评论", "展开更多回复", "查看更多回复", "留下你的精彩评论吧", "说点什么",
    "暂无评论", "抢首评", "写下你的评论", "有0条回复", "大家都在搜",
}
NOISE_PAT = re.compile(
    # 时间单位需覆盖「小时/分钟/星期」等多字单位，原版只收单字，漏了「13小时前」这类
    r"^(?:[·•\s]*\d+(?:秒|分钟?|小时?|天|周|星期|月|年)前[·•\s]*|"
    # 「N前·属地」= 时间戳+属地（如「6月前·浙江」），原版要求整行时间戳，属地漏网
    r"[·•\s]*\d+(?:秒|分钟?|小时?|天|周|星期|月|年)前\s*[·•]\s*[\u4e00-\u9fa5]{2,4}|"
    r"[·•\s]*\d+(?:\.\d+)?(?:万|w|W)?\s*(?:赞|次赞|点赞)[·•\s]*|"
    r"[·•\s]*\d+[·•\s]*|"
    r"[·•\s]*IP\s*属地[：:].*|"
    r"[·•\s]*作者[·•\s]*|"
    r"[·•\s]*回复[·•\s]*)$"
)

# ---------- 反自动化识别（stealth）----------
# Playwright 默认 UA 里带 "HeadlessChrome"，抖音/小红书一眼就认出来，必须换掉。
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'plugins', {
  get: () => [{ name: 'Chrome PDF Plugin' }, { name: 'Chrome PDF Viewer' }, { name: 'Native Client' }]
});
window.chrome = window.chrome || { runtime: {}, app: { isInstalled: false } };
const _q = window.navigator.permissions && window.navigator.permissions.query;
if (_q) {
  window.navigator.permissions.query = (p) => (
    p && p.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : _q.call(window.navigator.permissions, p)
  );
}
"""

# 人机验证页的特征文本（抖音「请完成下列验证后继续」、小红书滑块等）
VERIFY_TEXTS = [
    "请完成下列验证", "拖动完成上方拼图", "按住左边按钮", "滑动验证", "滑块验证",
    "安全验证", "人机验证", "请完成验证", "验证码", "captcha", "CAPTCHA",
    "识别下方", "点击图中",
]
JS_HAS_VERIFY_DOM = r"""
() => {
  const sels = [
    '#captcha_container', '#captcha-verify-image', '[class*="captcha"]', '[id*="captcha"]',
    '[class*="verify-wrap"]', '[class*="verifyWrap"]', '[class*="slide-verify"]', '[class*="secsdk"]'
  ];
  for (const s of sels) {
    try { if (document.querySelector(s)) return true; } catch (e) {}
  }
  return false;
}
"""


def _log(msg):
    print(msg, flush=True)


def _sleep(a=1.2, b=2.8):
    """人类化随机延迟。"""
    time.sleep(random.uniform(a, b))


def clean_comment(text):
    """清洗评论文本：去掉 UI 噪音行、时间戳、点赞数、@、多余空白。"""
    if not text:
        return ""
    lines = []
    for raw in str(text).split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s in NOISE_LINES:
            continue
        if NOISE_PAT.match(s):
            continue
        lines.append(s)
    out = " ".join(lines)
    out = re.sub(r"\s{2,}", " ", out).strip()
    # 太长的截断（评论正文极少超过 300 字，超了多半粘进了整段页面文本）
    if len(out) > 300:
        out = out[:300]
    return out


def looks_like_name(text):
    """粗判一个字符串是否像昵称（用于 innerText 兜底切分）。"""
    s = (text or "").strip()
    if not s or len(s) > 30:
        return False
    if s in NOISE_LINES:
        return False
    if NOISE_PAT.match(s):
        return False
    return True


# ==================================================================
# 浏览器内执行的抽取脚本
# ==================================================================
JS_EXTRACT = r"""
(args) => {
  const pickText = (el, sels) => {
    for (const s of sels) {
      let nodes = [];
      try { nodes = el.querySelectorAll(s); } catch (e) { continue; }
      for (const t of nodes) {
        const v = (t.innerText || t.textContent || '').trim();
        if (v) return v;
      }
    }
    return '';
  };
  const pickAttr = (el, sels, attr) => {
    for (const s of sels) {
      let nodes = [];
      try { nodes = el.querySelectorAll(s); } catch (e) { continue; }
      for (const t of nodes) {
        const v = t.getAttribute && t.getAttribute(attr);
        if (v) return v;
      }
    }
    // 元素自身可能就是链接
    if (el.getAttribute && el.getAttribute(attr)) return el.getAttribute(attr);
    return '';
  };

  let items = [];
  for (const s of args.itemSels) {
    try {
      const found = document.querySelectorAll(s);
      if (found.length) { items = Array.prototype.slice.call(found); break; }
    } catch (e) {}
  }
  if (!items.length) return { items: [], mode: 'no-items' };

  const out = items.map((el) => {
    const name = pickText(el, args.nameSels);
    let text = pickText(el, args.textSels);
    const link = pickAttr(el, args.linkSels, 'href');
    // innerText 兜底：按行切分，第一行当昵称，最长的非噪音行当内容
    const lines = (el.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    return { name: name, text: text, link: link, lines: lines };
  });
  return { items: out, mode: 'sel' };
}
"""

JS_COLLECT_LINKS = r"""
(selList) => {
  const out = new Set();
  const push = (el) => {
    const h = el && (el.href || el.getAttribute('href') || '');
    if (h) out.add(h);
  };
  // 关键：所有选择器取并集。旧写法命中第一个选择器就 return，
  // 一旦这个选择器只匹配到导航链接，整批结果就被判成 0 条（58 同城踩过）。
  for (const s of selList) {
    try { document.querySelectorAll(s).forEach(push); } catch (e) {}
  }
  // 兜底：选择器全落空时把整页锚点都收上来，交给 card_href_pat 过滤。
  // 58 的列表项锚点常常没有文字（图片包在 <a> 里），靠选择器不稳定。
  if (out.size < 5) {
    try { document.querySelectorAll('a[href]').forEach(push); } catch (e) {}
  }
  return Array.from(out);
}
"""

# 小红书：搜索页 DOM 里的 href 是裸链接（无 xsec_token），直接访问会 404。
# 真链接的 token 藏在 SSR 状态 window.__INITIAL_STATE__ 里，需要遍历提取。
# 注意 Vue 响应式对象有循环引用，绝不能 JSON.stringify，只能逐个取标量。
JS_STATE_TOKENS = r"""
(maxN) => {
  const st = window.__INITIAL_STATE__;
  if (!st) return [];
  const out = [];
  const seen = new Set();
  const ID_RE = /^[0-9a-f]{24}$/;
  const walk = (o, d) => {
    if (!o || d > 12 || out.length >= maxN || typeof o !== 'object') return;
    if (seen.has(o)) return;
    seen.add(o);
    try {
      const nid = (typeof o.noteId === 'string' && o.noteId) || (typeof o.id === 'string' && o.id) || '';
      const tk = typeof o.xsecToken === 'string' ? o.xsecToken : '';
      if (ID_RE.test(nid) && tk) { out.push([nid, tk]); return; }
    } catch (e) {}
    let keys = [];
    try { keys = Object.keys(o); } catch (e) { return; }
    for (const k of keys) { try { walk(o[k], d + 1); } catch (e) {} }
  };
  walk(st, 0);
  return out;
}
"""

JS_SCROLL_COMMENTS = r"""
() => {
  let scrolled = 0;
  // 找出所有可滚动的评论容器，滚到底
  const all = document.querySelectorAll('div, section, ul');
  for (const el of all) {
    try {
      const st = getComputedStyle(el);
      const oy = st.overflowY;
      if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 80 && el.clientHeight > 150) {
        el.scrollTop = el.scrollHeight;
        scrolled++;
      }
    } catch (e) {}
  }
  window.scrollBy(0, 1600);
  return scrolled;
}
"""

JS_COUNT_ITEMS = r"""
(selList) => {
  for (const s of selList) {
    try {
      const n = document.querySelectorAll(s).length;
      if (n) return n;
    } catch (e) {}
  }
  return 0;
}
"""

JS_CLICK_EXPAND = r"""
(sels) => {
  let clicked = 0;
  for (const s of sels) {
    let nodes = [];
    try { nodes = document.querySelectorAll(s); } catch (e) { continue; }
    for (const el of nodes) {
      const t = (el.innerText || '').trim();
      if (/展开|更多|查看全部/.test(t) || s.indexOf('text=') === 0 || s.indexOf('data-e2e') >= 0) {
        try { el.click(); clicked++; if (clicked > 3) return clicked; } catch (e) {}
      }
    }
  }
  return clicked;
}
"""


class BrowserCollector:
    """浏览器采集器。with 语句使用，或用 open()/collect()/close()。"""

    def __init__(self, cfg, log=_log):
        self.cfg = cfg
        self.log = log
        self._pw = None
        self._browser = None
        self._context = None
        self._owns_context = False
        self.cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collected_cache.json")
        self.cache = self._load_cache()
        self.diag = []          # 每个「平台×关键词」的真实结论，回传给页面显示，不再一律甩"缓存命中"
        self._last_stat = {}
        self._xhr_resps = []    # 纯 JS 站点的接口响应（快手），事后从里面取 id

    # ---------------- 生命周期 ----------------
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def _load_cache(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self):
        try:
            # 只保留最近 3000 条，避免无限增长
            if len(self.cache) > 3000:
                keys = list(self.cache.keys())[-3000:]
                self.cache = {k: self.cache[k] for k in keys}
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except Exception:
            pass

    def open(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(
                "未安装 playwright。请先执行：\n"
                "  pip install playwright\n"
                "本模块用 CDP 连你本机 Chrome，无需 playwright install chromium。\n"
                f"原始错误：{e}"
            )

        self._pw = sync_playwright().start()
        cdp_port = int(self.cfg.get("cdp_port", 9222))
        want_cdp = bool(self.cfg.get("enable_cdp", True))
        headless = bool(self.cfg.get("headless", False))
        udd = self.cfg.get("user_data_dir") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
        if not os.path.isabs(udd):
            udd = os.path.join(os.path.dirname(os.path.abspath(__file__)), udd)
        os.makedirs(udd, exist_ok=True)

        if want_cdp:
            try:
                self._browser = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                self._install_stealth()
                self.log(f"[browser] 已通过 CDP 连接本机 Chrome（:{cdp_port}），直接复用你的登录态 ✅")
                return
            except Exception as e:
                self.log(f"[browser] CDP 连接失败（{type(e).__name__}），改用持久化上下文模式")

        # 持久化上下文：优先用本机 Chrome 内核（channel='chrome'），免下载 chromium
        launch_kw = dict(
            user_data_dir=udd,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--lang=zh-CN",
            ],
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            user_agent=DEFAULT_UA,          # 去掉 UA 里的 HeadlessChrome 特征
            timezone_id="Asia/Shanghai",
        )
        try:
            self._context = self._pw.chromium.launch_persistent_context(channel="chrome", **launch_kw)
            self.log(f"[browser] 已用本机 Chrome 启动持久化上下文（headless={headless}）")
        except Exception:
            self._context = self._pw.chromium.launch_persistent_context(**launch_kw)
            self.log(f"[browser] 已用内置 Chromium 启动持久化上下文（headless={headless}）")
        self._owns_context = True
        self._install_stealth()
        if headless:
            self.log("[browser] 提示：headless 首次使用需先在非 headless 下扫码登录一次，Cookie 才会被复用")

    def _install_stealth(self):
        """注入反自动化脚本（隐藏 webdriver 标志等）。CDP 模式同样适用。"""
        try:
            self._context.add_init_script(STEALTH_JS)
        except Exception:
            pass

    def close(self):
        try:
            if self._owns_context and self._context:
                self._context.close()
        except Exception:
            pass
        try:
            # CDP 模式只断开，不关用户的浏览器
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._save_cache()

    # ---------------- 主流程 ----------------
    def collect(self):
        keywords = self.cfg.get("keywords") or []
        platforms = [ALIAS.get(str(p).lower(), str(p).lower()) for p in (self.cfg.get("platforms") or [])]
        raw = []
        self.diag = []
        page = self._context.new_page()
        page.set_default_timeout(int(self.cfg.get("page_timeout", 20000)))
        try:
            for kw in keywords:
                for plat in platforms:
                    if plat not in PROFILES:
                        self.log(f"[browser] 暂未内置「{plat}」选择器，跳过（可用 mediacrawler 模式读该平台导出）")
                        self.diag.append({"plat": plat, "kw": kw, "links": 0,
                                          "comments": 0, "reason": "unsupported"})
                        continue
                    try:
                        got = self._scrape(page, plat, kw)
                        raw.extend(got)
                        self.log(f"[browser] {PROFILES[plat]['cn']} / {kw} → 采集 {len(got)} 条评论")
                    except Exception as e:
                        self.log(f"[browser] {PROFILES[plat]['cn']} / {kw} 失败：{type(e).__name__}: {e}")
                        self.diag.append({"plat": PROFILES[plat]["cn"], "kw": kw,
                                          "links": 0, "comments": 0,
                                          "reason": "error", "detail": str(e)[:120]})
                    else:
                        st = dict(self._last_stat or {})
                        st.setdefault("plat", PROFILES[plat]["cn"])
                        st.setdefault("kw", kw)
                        st["comments"] = len(got)
                        self.diag.append(st)
                    _sleep(2.0, 4.0)
        finally:
            try:
                page.close()
            except Exception:
                pass
        return raw

    # ---------------- 单平台单关键词 ----------------
    def _scrape(self, page, plat, kw):
        prof = PROFILES[plat]
        import urllib.parse
        url = prof["search_url"].format(kw=urllib.parse.quote(kw))
        self.log(f"[browser] 打开搜索页：{prof['cn']} / {kw}")
        self._last_stat = {"plat": prof["cn"], "kw": kw, "links": 0, "comments": 0, "reason": ""}
        self._xhr_resps = []
        if prof.get("xhr_match"):
            # 只把响应对象攒起来，真正的 text() 留到页面还活着时再读，
            # 避免在 Playwright 事件回调里调同步 API 造成自锁。
            try:
                page.on("response", self._make_xhr_collector(prof))
            except Exception:
                pass
        page.goto(url, wait_until="domcontentloaded")
        _sleep(2.5, 4.0)

        block = self._detect_block(page, prof)
        if block:
            if not self._handle_block(page, prof, block):
                return []
            page.goto(url, wait_until="domcontentloaded")
            _sleep(2.5, 4.0)
            block = self._detect_block(page, prof)
            if block:
                self.log(f"[browser] {prof['cn']} 仍被拦截（{block}），跳过本次。")
                self._save_debug(page, plat, kw, "blocked")
                return []

        # 搜索页滚动加载更多卡片
        max_notes = int(self.cfg.get("max_notes", 10))
        links = self._collect_card_links(page, prof, max_notes)

        # 首次拿不到链接：回访首页建立会话（拿 Cookie / 过一过前置校验）后重试一次
        if not links:
            self.log("[browser] 首次未拿到链接，回访首页建立会话后重试…")
            try:
                page.goto(prof.get("home_url") or url, wait_until="domcontentloaded")
                _sleep(2.2, 3.8)
                b2 = self._detect_block(page, prof)
                if b2 and not self._handle_block(page, prof, b2):
                    return []
                page.goto(url, wait_until="domcontentloaded")
                _sleep(2.5, 4.0)
                links = self._collect_card_links(page, prof, max_notes)
            except Exception:
                pass

        if not links and prof.get("xhr_match"):
            _sleep(1.2, 2.0)
            links = self._links_from_xhr(prof, max_notes)
            if links:
                self.log(f"[browser] 页面没有锚点，改从搜索接口取到 {len(links)} 个作品链接")

        if not links:
            need_login = self._looks_login_wall(page, prof)
            if need_login:
                self._last_stat["reason"] = "need-login"
                self.log(f"[browser] {prof['cn']} 需要登录才能看到搜索结果 —— 请先在该平台登录一次。")
            else:
                self._last_stat["reason"] = "no-links"
                self.log(f"[browser] {prof['cn']} 搜索页没解析到内容（该词无结果/页面改版/风控），"
                         "换个关键词或先登录再试。")
            self._save_debug(page, plat, kw, "need-login" if need_login else "no-links")
            return []

        self.log(f"[browser] 拿到 {len(links)} 个内容链接，开始逐个进评论区")
        raw = []
        skipped_cache = 0
        limit_per_note = int(self.cfg.get("max_comments_per_note", 20))
        for idx, link in enumerate(links, 1):
            ckey = f"{plat}:{self._id_of(link, prof)}"
            if self.cache.get(ckey):
                skipped_cache += 1
                continue  # 断点续跑：这个内容已采过
            try:
                page.goto(link, wait_until="domcontentloaded")
                _sleep(2.0, 3.2)
                if self._is_dead_page(page, prof):
                    self.log(f"[browser]   [{idx}/{len(links)}] 笔记失效/无权限，跳过")
                    continue
                b = self._detect_block(page, prof)
                if b and not self._handle_block(page, prof, b):
                    self.log("[browser] 内容页被拦截，停止后续内容采集。")
                    break
                if b:
                    page.goto(link, wait_until="domcontentloaded")
                    _sleep(1.8, 3.0)
                note_title = ""
                try:
                    note_title = (page.title() or "").strip()[:60]
                except Exception:
                    pass
                items = self._collect_comments(page, prof, kw, limit_per_note, link)
                raw.extend(items)
                if items:
                    self.cache[ckey] = int(time.time())
                self.log(f"[browser]   [{idx}/{len(links)}] {link[-24:]} → {len(items)} 条")
            except Exception as e:
                self.log(f"[browser]   [{idx}/{len(links)}] 跳过：{type(e).__name__}")
            _sleep(1.5, 3.0)
        self._last_stat["links"] = len(links)
        self._last_stat["comments"] = len(raw)
        if not raw and skipped_cache == len(links):
            self._last_stat["reason"] = "cached"
        if skipped_cache:
            self.log(f"[browser] {skipped_cache}/{len(links)} 个内容已采过（断点缓存命中），本次跳过；"
                     "要重新采这批内容请删除 collected_cache.json")
            if skipped_cache == len(links):
                self.log("[browser] ⚠️ 本平台本关键词的内容全部命中缓存，所以这次是 0 条 —— "
                         "不是采集失败。换个关键词，或删掉 collected_cache.json 后重试。")
        return raw

    def _make_xhr_collector(self, prof):
        """返回一个只负责"把匹配的响应攒起来"的回调，读文本放到主线程做。"""
        marker = prof.get("xhr_match") or ""

        def handler(resp):
            try:
                if marker and marker in resp.url:
                    self._xhr_resps.append(resp)
            except Exception:
                pass

        return handler

    def _links_from_xhr(self, prof, max_notes):
        """从接口 JSON 里抽 id 拼详情链接（快手这类页面无锚点的站点）。"""
        pat = re.compile(prof.get("xhr_id_re") or r'"id"\s*:\s*"([0-9a-zA-Z_-]{12,24})"')
        tpl = prof.get("xhr_url_tpl") or ""
        if not tpl:
            return []
        links, seen = [], set()
        for resp in list(self._xhr_resps):
            try:
                body = resp.text()
            except Exception:
                continue
            for m in pat.finditer(body or ""):
                nid = m.group(1)
                if nid in seen:
                    continue
                seen.add(nid)
                links.append(tpl.format(id=nid))
                if len(links) >= max_notes:
                    return links
        return links

    def _looks_login_wall(self, page, prof):
        """没有结果时判断是不是被登录挡了。

        闲鱼/快手这类不会弹"扫码登录"大字，只是右上角一个「登录」入口，
        结果区继续挂骨架屏。所以判据是「有登录入口」+「结果区没内容」。
        """
        try:
            probe = page.evaluate(
                """() => {
                  const t = (document.body.innerText || '');
                  const loading = document.querySelectorAll(
                    '[class*="loading"],[class*="skeleton"],[class*="Loading"]').length;
                  const strongWords = ['扫码登录', '密码登录', '手机号登录', '登录后查看', '请先登录', '登录后可'];
                  const strong = strongWords.filter(w => t.indexOf(w) >= 0).length;
                  // 裸「登录」入口：a[href*=/login]、按钮文字为「登录」
                  const loginLink = document.querySelector('a[href*="/login"]');
                  const loginBtn = [...document.querySelectorAll('button,div[class*="login"],span[class*="login"]')]
                    .some(e => (e.innerText || '').trim() === '登录');
                  return {
                    loading: loading,
                    loadingText: t.indexOf('加载中') >= 0,
                    strong: strong,
                    hasLoginEntry: !!loginLink || loginBtn,
                    emptyText: /暂无|没有找到|无相关结果|换个词|没有更多/.test(t),
                  };
                }"""
            )
        except Exception:
            return False
        if probe.get("strong"):
            return True
        if probe.get("emptyText"):
            return False
        if probe.get("hasLoginEntry") and ((probe.get("loading") or 0) >= 1
                                          or probe.get("loadingText")):
            return True
        return False

    def _page_text_lead(self, page, prof):
        """详情页没有评论区时，把正文当成一条线索（58 房源描述就是这样）。"""
        text = ""
        for sel in prof.get("page_text_sels") or []:
            try:
                el = page.query_selector(sel)
            except Exception:
                el = None
            if not el:
                continue
            try:
                cand = (el.inner_text() or "").strip()
            except Exception:
                continue
            if len(cand) > 20:
                text = cand
                break
        if not text:
            try:
                text = (page.inner_text("body") or "").strip()
            except Exception:
                return None
        if text:
            # 58 详情页顶部是城市栏/导航，"退出 个人中心 商家中心"这些都混在正文里，
            # 先从内容锚点切一刀，再从导航尾巴切一刀，剩下的才是描述。
            for mk in ("房源描述", "房源亮点", "房屋亮点", "出租要求", "详情描述",
                       "商品详情", "服务内容", "服务介绍"):
                pos = text.find(mk)
                if pos > 0:
                    text = text[pos:]
                    break
            for mk in ("免费发布信息", "免费发布", "网站导航"):
                pos = text.rfind(mk)
                if pos > 0:
                    text = text[pos + len(mk):]
                    break
        text = clean_comment(text)
        if not text or len(text) < 12:
            return None
        name = ""
        for sel in prof.get("page_name_sels") or []:
            try:
                el = page.query_selector(sel)
            except Exception:
                el = None
            if not el:
                continue
            try:
                name = (el.inner_text() or "").strip()
            except Exception:
                name = ""
            if name:
                break
        if not name:
            try:
                name = (page.title() or "").strip()[:24]
            except Exception:
                name = ""
        return {
            "name": (name or "房源信息")[:30],
            "comment": text,
            "uid": "",
            "author_url": page.url,
            "like": 0,
            "collected_at": time.strftime("%Y-%m-%d %H:%M"),
        }

    def _id_of(self, link, prof):
        m = re.search(prof["card_href_pat"], link or "")
        return m.group(1) if m else re.sub(r"\W+", "", link or "")[-24:]

    def _detect_block(self, page, prof):
        """检测人机验证 / 登录墙。返回 'verify' / 'login' / None。"""
        try:
            body = page.inner_text("body", timeout=3000) or ""
        except Exception:
            return None
        head = body[:4000]
        for t in VERIFY_TEXTS:
            if t in head:
                return "verify"
        try:
            if page.evaluate(JS_HAS_VERIFY_DOM) and len(body) < 2000:
                return "verify"
        except Exception:
            pass
        for t in prof.get("login_hint", []):
            if t in head and len(body) < 1500:
                return "login"
        return None

    def _handle_block(self, page, prof, kind):
        """应对拦截。返回 True 表示可以继续采集。"""
        if kind == "verify":
            if self.cfg.get("headless"):
                self.log("[browser] ⚠️ 触发了人机验证，但当前是无头模式，无法手动通过。")
                self.log("[browser]    → 请改用有界面模式跑一次（去掉 --headless / 不加 --headless），"
                         "弹出窗口里手动滑一下，Cookie 会保存下来供后续复用。")
                return False
            wait = int(self.cfg.get("verify_wait", 120))
            self.log(f"[browser] ⏳ 抖音/小红书弹出了人机验证，请在弹出的浏览器窗口里手动完成（最多等 {wait}s）…")
            return self._poll_clear(page, prof, wait)
        if kind == "login":
            if self.cfg.get("headless"):
                self.log("[browser] ⚠️ 需要登录，但当前是无头模式。请先用有界面模式登录一次。")
                return False
            wait = int(self.cfg.get("login_wait", 180))
            self.log(f"[browser] ⏳ 需要登录，请在弹出的浏览器窗口里扫码/登录（最多等 {wait}s）…")
            return self._poll_clear(page, prof, wait)
        return False

    def _poll_clear(self, page, prof, max_wait):
        """轮询等待人工完成后拦截消失。"""
        t0 = time.time()
        while time.time() - t0 < max_wait:
            time.sleep(3)
            if self._detect_block(page, prof) is None:
                self.log("[browser] ✅ 拦截已解除，继续采集。")
                return True
        self.log("[browser] ⌛ 等待超时，本次跳过。")
        return False

    def _collect_card_links(self, page, prof, max_notes):
        # 小红书优先走 SSR 状态里的 xsec_token，拼出可直接访问的详情页
        if prof.get("use_state_token"):
            state_links = self._links_from_state(page, prof, max_notes)
            if state_links:
                self.log(f"[browser] 从页面状态解析到 {len(state_links)} 条带 xsec_token 的笔记链接")
                return state_links
            self.log("[browser] ⚠️ 页面状态里没拿到 xsec_token，退回 DOM 链接（大概率 404）")

        links, seen = [], set()
        for _ in range(8):
            try:
                hrefs = page.evaluate(JS_COLLECT_LINKS, prof["card_sels"])
            except Exception:
                hrefs = []
            for h in hrefs:
                if not h:
                    continue
                if prof["card_href_pat"] and not re.search(prof["card_href_pat"], h):
                    continue
                key = self._id_of(h, prof)
                if key in seen:
                    continue
                seen.add(key)
                links.append(h)
                if len(links) >= max_notes:
                    return links
            page.evaluate(JS_SCROLL_COMMENTS)
            _sleep(0.9, 1.6)
        return links

    def _links_from_state(self, page, prof, max_notes):
        """小红书专用：从 __INITIAL_STATE__ 提取 (noteId, xsecToken) 拼真链。"""
        tpl = prof.get("note_url_tpl") or "https://www.xiaohongshu.com/explore/{id}?xsec_token={token}"
        for attempt in range(3):
            try:
                pairs = page.evaluate(JS_STATE_TOKENS, max_notes * 3)
            except Exception:
                pairs = []
            links, seen = [], set()
            for nid, tk in pairs or []:
                if nid in seen:
                    continue
                seen.add(nid)
                links.append(tpl.format(id=nid, token=tk))
                if len(links) >= max_notes:
                    break
            if links:
                return links
            # 状态可能还没注水，滚一下再试
            try:
                page.evaluate(JS_SCROLL_COMMENTS)
            except Exception:
                pass
            _sleep(1.2, 2.0)
        return []

    def _is_dead_page(self, page, prof):
        """小红书裸链接会跳 404「当前笔记暂时无法浏览」，命中即跳过，不重试。"""
        hints = prof.get("fail_hint") or []
        if not hints:
            return False
        try:
            body = page.inner_text("body", timeout=2500) or ""
        except Exception:
            return False
        return any(h in body for h in hints)

    def _collect_comments(self, page, prof, kw, limit, page_url):
        # 评论区是懒加载的，先等内容容器出现（小红书尤其明显）
        ready = prof.get("comment_ready_sel")
        if ready:
            try:
                page.wait_for_selector(ready, timeout=8000)
            except Exception:
                pass
        # 尝试展开评论
        try:
            page.evaluate(JS_CLICK_EXPAND, prof["expand_sels"])
        except Exception:
            pass
        _sleep(1.0, 2.0)

        got = []
        last_count = 0
        stale = 0
        for round_i in range(int(self.cfg.get("scroll_rounds", 10))):
            try:
                bundle = page.evaluate(JS_EXTRACT, {
                    "itemSels": prof["comment_item_sels"],
                    "nameSels": prof["comment_name_sels"],
                    "textSels": prof["comment_text_sels"],
                    "linkSels": prof["user_link_sels"],
                })
            except Exception:
                bundle = {"items": []}
            items = bundle.get("items") or []
            for it in items:
                parsed = self._parse_item(it, prof)
                if parsed and parsed["comment"]:
                    parsed.update({
                        "platform": prof["cn"], "keyword": kw,
                        "url": page_url, "note_url": page_url,
                    })
                    got.append(parsed)

            # 去重保序
            got = self._uniq(got)
            if len(got) >= limit:
                break
            if len(got) == last_count:
                stale += 1
                if stale >= 3:
                    break
            else:
                stale = 0
                last_count = len(got)
            try:
                page.evaluate(JS_SCROLL_COMMENTS)
            except Exception:
                pass
            _sleep(0.8, 1.5)

        if not got and prof.get("page_text_fallback"):
            one = self._page_text_lead(page, prof)
            if one:
                one.update({"platform": prof["cn"], "keyword": kw,
                            "url": page_url, "note_url": page_url})
                got.append(one)
                self.log("[browser]   详情页无评论区，改用正文作为一条线索")

        return got[:limit]

    def _parse_item(self, it, prof):
        """把一条抽取结果规整成 {name, comment, uid, author_url}。"""
        name = (it.get("name") or "").strip()
        text = (it.get("text") or "").strip()
        link = (it.get("link") or "").strip()
        lines = [str(x).strip() for x in (it.get("lines") or []) if str(x).strip()]

        # innerText 兜底：昵称取第一行像名字的，内容取最长的那行
        if not name and lines:
            for ln in lines[:3]:
                if looks_like_name(ln):
                    name = ln
                    break
        if not text and len(lines) > 1:
            cand = [ln for ln in lines[1:] if not NOISE_PAT.match(ln) and ln not in NOISE_LINES]
            if cand:
                text = max(cand, key=len)

        text = clean_comment(text)
        if not text:
            return None
        # 内容里混入了昵称前缀时剥掉
        if name and text.startswith(name) and len(text) > len(name) + 2:
            text = text[len(name):].strip()

        uid = ""
        if link:
            m = re.search(prof["user_href_pat"], link)
            if m:
                uid = m.group(1)
        author_url = link if link.startswith("http") else ""

        return {
            "name": name[:30],
            "comment": text,
            "uid": uid,
            "author_url": author_url,
            "like": 0,
            "collected_at": time.strftime("%Y-%m-%d %H:%M"),
        }

    @staticmethod
    def _uniq(items):
        seen, out = set(), []
        for it in items:
            k = (it.get("uid") or it.get("name") or "") + "|" + re.sub(r"\s+", "", it.get("comment") or "")
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        return out

    def _save_debug(self, page, plat, kw, tag):
        """抓不到数据时保存快照与 HTML，便于定位是改版还是风控。"""
        try:
            d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
            os.makedirs(d, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            png = os.path.join(d, f"{plat}_{tag}_{stamp}.png")
            page.screenshot(path=png)
            self.log(f"[browser] 已保存现场截图：{png}（可发我分析页面结构）")
        except Exception:
            pass
