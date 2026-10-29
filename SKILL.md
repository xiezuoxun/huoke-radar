---
name: huoke-radar
description: 商机获客·线索雷达全套平台搭建与运营。采集抖音/小红书公开评论，识别购买/合作意向客户，写入资料库工作台实现自动获客。当用户想搭建获客工作台、采集抖音小红书商机、挖掘意向客户、复刻线索雷达平台、分享获客采集流程时使用。触发词：商机获客、线索雷达、获客采集、获客工作台、意向客户挖掘、抖音小红书获客、复刻获客平台、搭建获客流程。
display_name: 商机获客
display_name_en: Lead Radar
description_zh: 抖音/小红书公开评论采集 + 意向识别 + 资料库工作台自动获客
description_en: Collect public comments from Douyin/Xiaohongshu, identify intent leads, auto-sync to a cloud workbench
category: data-collection
version: 1.0.0
author: 阿旁
---

# 商机获客 · 线索雷达

## 📝 简介

一套「采集 → 识别 → 入库 → 跟进」的商机获客平台：
- **采集**：Playwright 复用登录态，抓取抖音 / 小红书关键词搜索下的**公开评论**；
- **识别**：`intent.py` 给每条评论打意向分（高/中/低）并推断行业分类；
- **入库**：把有意向的客户写入资料库数据表（工作台背后），自动去重不重复入库；
- **跟进**：工作台页面（`huoke-radar.html`）可视化展示，支持筛选 / 状态流转 / 一键采集。

> ⚠️ **合规声明**：仅用于个人工作 / 学习 / 研究，禁止商业用途。只采集平台**公开可见的评论文本**，
> 不获取手机号、私信、身份证等隐私信息。请遵守平台服务条款与《网络安全法》《反不正当竞争法》，
> **控制频率、勿大规模抓取**。规模化/商用请走官方开放平台（巨量引擎、小红书聚光）或合规数据服务商。

---

## ✨ 功能模块

| 模块 | 能力 | 价值 |
|---|---|---|
| 采集器（browser） | 多候选选择器、滚动采深、防封、文本清洗 | 稳定抓到抖音/小红书公开评论 |
| 意向识别（intent） | 打分/分级（高≥75/中≥55）+ 行业推断（13 类产品） | 从闲聊里筛出真潜客 |
| 去重合并（dedupe） | 用户ID>主页>昵称 身份识别，跨源比对 | 不把同一条评论/同一客户刷成重复 |
| 写库（huoke_push） | 写前与云端增量比对，只写新增 | 定时跑一个月也不重复 |
| 工作台（huoke-radar.html） | 今日待跟进、意向客户、采集任务、统计看板 | 打开即看、可跟进、可触发采集 |
| 采集任务页 | 关键词/平台/地域/强度配置，实时日志 | 一次配好，点按钮就跑 |
| 自动推（push_pending） | 扫本地所有批次，补齐未入库线索 | 采集后自动同步到公网 |
| 定时（daily_run） | 采集→识别→去重→落CSV→推库 全链路 | 无人值守日更 |

---

## 🔑 前置依赖

- **WorkBuddy**（含「资料库」skill）—— 用于建数据表、部署工作台页面；
- **Windows + Python 3.11+** + **Playwright**（仅库本体，复用本机 Chrome，无需下载内核）；
- **已登录的抖音 / 小红书**（首次用 `scripts/init_login.bat` 引导登录一次）。

> 本 skill 的采集器脚本都放在 `scripts/` 目录；所有命令请在 **skill 根目录**下执行。

---

## 🚀 全套搭建流程（从零到上线）

> 以下流程适合在 WorkBuddy 会话里由 AI 按步骤引导执行；也可手动对照 `docs/搭建指南.md` 操作。

### Step 1 · 建两张数据表（资料库）

让 AI 用「资料库」skill 建两张表，字段严格按下表（**字段名与类型必须一致**，否则页面读写不匹配）。

**表 A「获客意向客户」**：

| 字段 | 类型 | 配置 |
|---|---|---|
| 客户昵称 | text | — |
| 来源平台 | select | 抖音/小红书/视频号/快手/微博/知乎/B站 |
| 评论内容 | text | — |
| 行业分类 | select | 家具行业/少儿编程/私教减脂/家装设计/二手车/医美/宠物服务/母婴早教/流量套餐/宽带/手机终端/靓号/融合套餐/副卡·亲情号/全屋光纤 FTTR/政企·商铺/云电脑/智能穿戴/智家安防/视频会员/综合行业 |
| 意向等级 | select | 高/中/低 |
| 意向分 | number | — |
| 命中关键词 | text | — |
| 采集关键词 | text | — |
| 主页链接 | text | — |
| 跟进状态 | select | 待跟进/已联系/已加微/已成单/无效 |
| 备注 | text | — |
| 采集时间 | text | — |
| 批次 | text | — |

**表 B「获客采集任务」**：

| 字段 | 类型 | 配置 |
|---|---|---|
| 关键词 | text | — |
| 平台范围 | text | — |
| 扫描内容 | number | — |
| 识别意向 | number | — |
| 高意向 | number | — |
| 耗时 | text | — |
| 状态 | select | 已完成 |
| 采集时间 | text | — |
| 批次 | text | — |

> 建表用「资料库」skill 的「数据表」能力，建完后**复制两张表的 id**（形如 `MjDdEbw22n8gTgFBOrPurw`）。

### Step 2 · 绑定表 id 到平台

```bash
python scripts/init_workspace.py --leads-db <表A的id> --tasks-db <表B的id>
```

脚本会把两个表 id 替换进 `workbench/huoke-radar.html`、`scripts/huoke_push.py`、`scripts/push_pending.py`
（自动备份为 `*.bak`），使整套采集/推库链路指向你的表。

### Step 3 · 部署工作台页面（资料库）

用「资料库」skill 的「在线 page / md 转网页发布」能力，把 `workbench/huoke-radar.html` 部署上线，
得到**你自己的工作台链接**。该页面经 SDK 实时读表，打开即用。

### Step 4 · 装依赖（一次性）

```bash
# Windows：双击 scripts/install.bat，或
python -m pip install -r scripts/requirements.txt
```
> 依赖仅 `playwright>=1.40`。CDP 模式复用你本机 Chrome，**不需要** `playwright install chromium`。

### Step 5 · 登录平台（一次性）

```bash
python scripts/init_session.py          # 引导登录抖音 + 小红书
python scripts/init_session.py --check  # 只看登录态
```
登录态存 `scripts/browser_data/`（本 skill 未附带你的登录态，需自行登录一次）。

### Step 6 · 一键采集

```bash
# CLI 方式
python scripts/huoke_collector.py --mode browser --keyword 家具 减脂 --platform douyin xhs
python scripts/huoke_push.py scripts/data/huoke_leads_<批次>.csv   # 推库（增量去重）

# 工作台按钮方式（推荐）：双击 scripts/start_agent.bat 起本地服务，
# 打开你的工作台链接 → 「采集任务」→ 选产品/渠道 → 点「开始采集」
```

### Step 7 · 采集后自动推（可选，推荐）

```bash
python scripts/push_pending.py --report            # 先看哪些批次未入库
python scripts/push_pending.py                     # 补齐全部未入库（幂等）
```
在 WorkBuddy 建一个**每小时定时任务**执行 `push_pending.py`（每次现取 token），即可实现「采集后自动推」。

---

## 🔄 采集流程详解

```
选关键词/平台/地域 → 采集器复用登录态打开搜索页
  → 进入内容详情页（小红书自动补 xsec_token）
  → 评论区滚动采深（--scroll-rounds）
  → 意向识别打分（高≥75/中≥55/其余低）
  → 去重合并（用户ID>主页>昵称）
  → 落盘 CSV（data/huoke_leads_<批次>.csv）
  → 与云端增量比对 → 只写新增进「获客意向客户」+「获客采集任务」
```

### 采集模式

| 模式 | 命令 | 说明 |
|---|---|---|
| browser | `--mode browser` | 真实浏览器采集（**主力**） |
| mediacrawler | `--mode mediacrawler --mc-dir <dir>` | 吃 MediaCrawler 导出的 jsonl |
| mock | `--mode mock` | 内置样本，验证管线 |

### 常用参数

| 参数 | 作用 |
|---|---|
| `--max-notes 6` | 每关键词进几个内容 |
| `--max-comments 15` | 每内容采多少条评论 |
| `--scroll-rounds 8` | 评论区滚动轮数 |
| `--headless` | 无头（定时任务用；首次登录勿用） |
| `--dedupe exact/customer/off` | 去重策略 |

### 去重策略

| 策略 | 行为 |
|---|---|
| exact（默认） | 只合并「同一客户+同一条评论」 |
| customer | 同一客户多条留言归并成一条 |
| off | 不去重（排查用） |

### 定时

- **Windows 计划任务**（本机兜底，`--no-push`）：`powershell -ExecutionPolicy Bypass -File scripts/install_schedule.ps1`
- **WorkBuddy 定时任务**（推荐，能真正写库）：让自动化执行 `python scripts/daily_run.py`

---

## 🛠 常见坑（已踩过）

1. **小红书笔记链接必须带 `xsec_token`**：搜索页裸 `/explore/<id>` 会 404；采集器会从 SSR 状态拼真链接。
2. **评论区懒加载**：进详情页等 `.comment-item` 出现（内置 8s）。
3. **写库报「输入 JSON 为空」**：stdin 契约是**第一行 token、第二行 JSON**，键用 `database_id`（下划线），
   值带类型：`{"关键词": {"text": "家具"}, "状态": {"select": "已完成"}}`。
4. **意向分档（2026-10-27 校准）**：基础 35 + 高意向词 +22/个（≤3）+ 软意向词 +10/个（≤3）+ 高软同命中 +6；
   强负面且高意向词<2 → ×0.55。分档 ≥75 高 / ≥55 中 / 其余低。
5. **改了词库不用重采**：`python scripts/rescore.py data/xxx.csv`。
6. **采到 0 条**：多是 `collected_cache.json` 断点缓存（这批内容之前采过），换关键词或删该文件。
7. **页面连不上采集器**：确认 `scripts/start_agent.bat` 的黑窗口开着；云端 https 页面访问本机可能被拦，
   用本地方式打开工作台（`scripts/打开线索雷达.bat`）。

---

## 📁 目录结构

```
huoke-radar-skill/
├── SKILL.md                 # 本引导文件
├── README.md                # 项目说明
├── scripts/                 # 采集器 + 初始化 + 一键脚本
│   ├── init_workspace.py    # 绑定表 id（Step 2）
│   ├── huoke_collector.py   # 采集器主程序
│   ├── browser_collect.py   # 浏览器采集核心
│   ├── intent.py            # 意向识别引擎
│   ├── dedupe.py            # 去重合并
│   ├── huoke_push.py        # 写库（增量去重）
│   ├── push_pending.py      # 补推未入库（自动推）
│   ├── daily_run.py         # 定时编排
│   ├── agent_server.py      # 本地采集服务（页面触发）
│   ├── init_session.py      # 登录初始化
│   ├── install.bat / init_login.bat / install_schedule.ps1 / start_agent.bat
│   └── config.json / requirements.txt / sample_comments.json
├── workbench/
│   └── huoke-radar.html     # 工作台页面（部署到资料库）
└── docs/
    ├── 搭建指南.md           # 从零到上线详细步骤
    └── DESIGN.md             # 工作台设计文档
```

---

## ⚖️ 声明

仅供个人工作 / 学习 / 研究使用，禁止商用。数据源为公开评论文本，请合规使用、控制频率。
