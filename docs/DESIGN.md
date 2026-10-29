---
name: 商机雷达 · 温州移动
description: 运营商存量挖潜的本地作战台。暗色作战舱为默认主题，浅色日光为可选。以「产品线（流量/宽带/手机/靓号）＋渠道（9 个公开平台）＋地域（温州 12 区县）」三维度组织商机，强调信息密度、可扫读性与一线可执行性。
colors:
  bg: "#08070d"
  surface: "#12101c"
  surface-2: "#171523"
  surface-3: "#1d1a2b"
  line: "#272236"
  line-strong: "#3a3350"
  ink: "#f1eef9"
  ink-2: "#c6c0d8"
  ink-3: "#8b85a0"
  brand: "#8b5cf6"
  brand-2: "#22d3ee"
  brand-deep: "#6d28d9"
  brand-weak: "rgba(139,92,246,.14)"
  hot: "#f87171"
  warn: "#fbbf24"
  ok: "#34d399"
  info: "#60a5fa"
typography:
  display:    { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 26px, fontWeight: 750, lineHeight: 1.1,  letterSpacing: -0.03em }
  heading:    { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 20px, fontWeight: 700, lineHeight: 1.25, letterSpacing: -0.01em }
  subheading: { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 15px, fontWeight: 650, lineHeight: 1.35, letterSpacing: -0.005em }
  body:       { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 14px, fontWeight: 400, lineHeight: 1.55, letterSpacing: 0 }
  ui:         { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 13px, fontWeight: 500, lineHeight: 1.5,  letterSpacing: 0 }
  caption:    { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 12px, fontWeight: 500, lineHeight: 1.4,  letterSpacing: 0.2px }
  micro:      { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 11px, fontWeight: 500, lineHeight: 1.3,  letterSpacing: 0.2px }
  badge:      { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 10px, fontWeight: 800, lineHeight: 1.2,  letterSpacing: 0.6px }
  input:      { fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif', fontSize: 16px, fontWeight: 400, lineHeight: 1.4,  letterSpacing: 0 }
rounded:
  xs: 6px
  sm: 9px
  md: 12px
  lg: 16px
  xl: 20px
  full: 999px
spacing:
  xxs: 4px
  xs: 6px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 20px
  xxl: 28px
layout:
  rail: 216px
  contentMaxWidth: 1400px
  topbarMinHeight: 58px
  touchTarget: 44px
  pointerTarget: 36px
components:
  rail:
    width: 216px
    background: "surface"
    activeIndicator: "左侧 3px 品牌竖条 + brand-weak 底"
  topbar:
    minHeight: 58px
    borderBottom: "1px solid line"
  panel:
    background: "linear-gradient(180deg, surface, surface 88% mixed with bg)"
    border: "1px solid line"
    radius: 16px
    shadow: "0 1px 0 rgba(255,255,255,.03) inset, 0 12px 28px -18px rgba(0,0,0,.9)"
  kpiCard:
    grid: "6 列；≤1080px 3 列；≤860px 2 列；≤768px 2 列"
    padding: "13px 14px"
    topStripe: "2px 品牌渐变，向右 78% 淡出"
  chip:
    minHeight: 36px
    radius: full
    background: "surface-2"
    selectedBorder: "brand-line"
  buttonPrimary:
    height: 44px
    background: "linear-gradient(brand-deep, brand)"
    color: "#ffffff"
  buttonGhost:
    minHeight: 36px
    background: "transparent"
    border: "1px solid line"
  table:
    rowPadding: "0 16px"
    rowMinHeight: 52px
    hoverBackground: "surface-2"
  heatCell:
    minHeight: 64px
    background: "color-mix(brand 10%~44%, surface-2)"
    text: "ink / ink"
  drawer:
    width: 420px
    mobileWidth: "100vw，底部弹出，圆角 20px 20px 0 0"
  toast:
    position: "底部居中，translateY 进入"
  badge:
    padding: "2px 5px"
    radius: 4px
  prodCard:
    padding: "13px 14px 12px"
    leftStripe: "3px 产品色"
    subs: "11px / --ink-3 / 单行省略，最多 5 项，用 · 分隔"
  loginRow:
    minHeight: 56px
    grid: "图标 32px ｜ 名称+说明 ｜ 登录按钮"
    action: "36px 高文字按钮，移动端 44px"
---

# 商机雷达 · 设计规范

温州移动存量挖潜的**内部作战台**，不是对外展示页。使用者是片区经理和渠道主管，一天开十几次，看的是「现在该打给谁、说什么、成不成」。

## 一、三条硬原则

1. **一屏一决策。** 每页进来三秒要能回答一个问题：总览＝今天重点打谁；采集＝去哪找；商机池＝谁该跟进；产品线＝哪个产品缺弹药；地域＝哪个片区没打透。答不出来就是版式错了。
2. **密度优先于呼吸感。** 这是工具不是官网。信息密度高、行距紧、留白只用于分组，不用于「显得高级」。但**分组必须有物理边界**（面板边框），不能靠空白硬分。
3. **暗色不是装饰。** 深底让红色高意向、绿色成单、琥珀色预警跳出来，这是长时间盯屏的作战场景需要。浅色主题给打印／投屏／白天用，语义色保持一致。

## 二、颜色

### 画布与表面（三层，禁止再嵌套第四层）
| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#08070d` | 页面底色，近黑带紫 |
| `--surface` | `#12101c` | 面板默认底 |
| `--surface-2` | `#171523` | 面板内次级块、chip、表格 hover |
| `--surface-3` | `#1d1a2b` | 输入框、最内层块 |

背景叠加两层极淡径向光（左上紫 `.20`、右上青 `.13`），只做氛围，**不得**出现在面板内部。

### 文字三级
`--ink #f1eef9`（正文／数字）→ `--ink-2 #c6c0d8`（次要说明）→ `--ink-3 #8b85a0`（元信息、单位、时间）。三级都要对 `--surface` 达到 4.5:1；`--ink-3` 是下限色，不许再往下取。

### 品牌色
主紫 `--brand #8b5cf6`，深紫 `--brand-deep #6d28d9`（实心按钮底），青 `--brand-2 #22d3ee`（链接与可点动作）。**白字只允许压 `--brand-deep` 或更深的紫**，压 `--brand` 会掉到 4.0 以下。

### 语义色（必须成对／成组使用）
| 语义 | 主色 | 浅底 | 描边 |
|---|---|---|---|
| 高意向／紧急 | `--hot #f87171` | `rgba(248,113,113,.13)` | `.35` |
| 中意向／待办 | `--warn #fbbf24` | `rgba(251,191,36,.13)` | `.32` |
| 成单／在线 | `--ok #34d399` | `rgba(52,211,153,.13)` | `.32` |
| 信息／平台 | `--info #60a5fa` | `rgba(96,165,250,.13)` | `.32` |

三项（字＋浅底＋描边）要一起出现。只用色字＝看不出层级；只用色块＝糊成一片。

### 产品线色
流量／宽带／手机／靓号各有产品色，**只出现在点、进度条、图标底纹**上。产品色不得直接当正文文字色——暗底上偏暗、浅底上只有 3.2:1。文字一律回到 `--ink`。

## 三、字

9 级阶梯，全部整数 px。**不许出现 13.3／12.5／18.5 这类中间值**——Chrome 给 `<button>` 的 UA 默认字号是 13.33px，全局 reset 必须写 `button,input,select,textarea{font:inherit}` 掐掉。

| 令牌 | 桌面 | 移动 | 用途 |
|---|---|---|---|
| `--f-display` | 26 | 24 | KPI 数字、产品商机数 |
| `--f-h1` | 20 | 18 | 页面标题 |
| `--f-h2` | 15 | 15 | 面板标题 |
| `--f-body` | 14 | 14 | 正文、评论原文 |
| `--f-ui` | 13 | 13 | 表格单元格、按钮 |
| `--f-cap` | 12 | 12 | 说明、chip 文字 |
| `--f-micro` | 11 | 11 | 元信息、单位、图例 |
| badge | 10 | 10 | NEW 角标（大写 + 字距 .6px） |
| `--f-input` | 16 | 16 | 所有输入控件（防 iOS 聚焦缩放） |

数字统一 `font-variant-numeric: tabular-nums`，否则表格里数字会抖。

## 四、间距与圆角

间距只用 4 的倍数加一个 6：`4 / 6 / 8 / 12 / 16 / 20 / 28`。
圆角：输入与 chip `6~9`，面板 `16`，KPI 卡与内块 `12`，pill 用 `999`。**不要在面板内再套一层带边框带圆角的卡**——要分组就用 `--surface-2` 底块，不加边框。

## 五、组件规矩

**导轨（216px）**：图标＋文字；激活态＝左侧 3px 品牌竖条＋`--brand-weak` 底。移动端塌成底部 tab，高 52px。

**命令条**：一个输入＋一个主按钮＋关键词 chip＋采集器连接状态。这是全站唯一「一句话就能干活」的入口，不许多加字段。

**KPI 卡**：顶部 2px 品牌渐变条（78% 淡出），下面是标签／数字／环比。数字大、标签小，顺序不能反。

**表格行**：52px 行高，hover 变 `--surface-2`，整行可点开抽屉。**表头不许 `position:sticky`**——它会截断行的点击热区，而行点击是本产品的主交互。

**热力格**：温州 12 区县排成网格，底色按商机数在 `brand 10%~44%` 之间插值。**上限必须卡 44%**，再深文字就没法读。格内文字一律 `--ink`。

**抽屉**：右侧 420px 滑出；移动端底部弹出、圆角 `20 20 0 0`。内容顺序固定：谁 → 说了什么 → 判定依据 → 跟进动作。

**Toast**：底部居中，3 秒自动消失，只报结果不复述操作。

## 六、状态

每个可交互元素必须有：`hover`（提亮／描边）、`focus-visible`（3px 品牌外发光）、`disabled`（45% 不透明＋禁止光标）、`loading`（按钮文案改「采集中…」并禁用）。
列表必须三态：有数据／空（说明为什么空＋一个可执行的下一步）／加载骨架。

## 七、触控与响应式

- 断点：`1080 / 860 / 768 / 400`。
- 触控热区 **44×44**（`--tap`）；指针环境次级动作下限 **36×36**；全站没有小于 36 的点击目标。
- ≤768px：导轨变底部 tab、命令条按钮撑满、表格首列独占一行、抽屉底部弹出。
- ≤400px：KPI 保持两列，隐藏迷你趋势条。

## 八、动效

只有两处：页面切换 `translateY(7px) → 0`，340ms，`cubic-bezier(.16,1,.3,1)`；抽屉 320ms 同曲线。其余交互 ≤160ms。
`prefers-reduced-motion: reduce` 时全部压到 0.001ms。

## 九、四处业务约定

**意向评分词表（运营商）**：`collector/intent.py` 的 `HOT_WORDS` / `SOFT_WORDS` 必须覆盖运营商真实话术——**只收「动作 / 意图」词**（办理 / 办宽带 / 装宽带 / 装机 / 携号转网 / 转网 / 换手机 / 换靓号 / 流量不够 / 流量卡 / 宽带续费 / 续费 / 升级套餐 / 升档…），**不收「宽带 / 流量 / 靓号」这类产品名**——平台搜索本就按产品词进行，产品名几乎每条评论都带，收了会把纯闲聊全误判成线索。前端 `huoke-radar.html` 的 `HOT_WORDS` 必须与 `intent.py` 保持同源（高亮与 mock 兜底）。门槛：`意向分 >= 45` 才进「意向客户」，单 HOT 词 = 57（中），单 SOFT 词 = 45（低，临界）。

**产品类目（12 个）**：4 个主力（流量套餐 / 宽带 / 手机终端 / 靓号）+ 8 个扩展（融合套餐 / 副卡·亲情号 / 全屋光纤 FTTR / 政企·商铺 / 云电脑 / 智能穿戴 / 智家安防 / 视频会员）。
组合型产品（融合、云电脑、智能穿戴、智家安防、视频会员）必须在卡片底部带一行 `subs` 权益清单——用户看的是「到底卖什么」，不是「一个大类名」。视频会员的 `subs` 要写全平台：爱奇艺 / 腾讯视频 / 优酷 / 咪咕 NBA / 芒果 TV。

**地域三档**：`none` 不限（不拼任何地域词）/ `all` 温州全域（前缀「温州 」）/ 具体区县（前缀「鹿城 」「乐清 」等，去掉「区市县」后缀）。**「不限」时一个地域词都不许拼**，否则搜出来的东西和意图完全错位。默认 `all`。

**需登录渠道**：快手 / 微博 / 闲鱼 / B站 / 知乎 / 58同城 六个渠道在采集前检查登录态，未登录弹确认框（主按钮「先去登录」、次按钮「仍然采集」）。抖音 / 小红书已跑通，不拦。视频号无公开搜索接口，恒为「仅手工导入」。登录态由本地服务读 Chrome Cookies 库判定，**必须走后台缓存刷新**，不许在请求线程里同步读库——Chrome 启动时会锁库，同步读会把接口卡住 3~5 秒。

## Do's

1. 数字用 tabular-nums、右对齐；单位降一级字号并转 `--ink-3`。
2. 面板内分组用 `--surface-2` 底块，不加第二层边框。
3. 语义色三件套（字＋浅底＋描边）一起上。
4. 空状态写清「为什么空」，并给一个下一步按钮。
5. 新增平台／产品时，颜色进 `P_COLOR`、代码进 `P_CODE`、状态进 `P_STATUS`，三处对齐。
6. 组合型产品必须写 `subs` 权益清单；只写一个大类名等于没写。
7. 同源检测只认主机名（`127.0.0.1` / `localhost` / `[::1]`），**不要写死端口**——换端口就退回被 Chrome 拦截的绝对地址。

## Don'ts

1. 不要白字压 `--brand`（#8b5cf6），对比度只有约 3.7。
2. 不要让产品色当正文文字色。
3. 不要出现 13.3／12.5／18.5 这类半像素字号。
4. 不要给表头加 `position:sticky`。
5. 不要在面板里再套带边框的圆角卡。
6. 不要用 emoji 当图标，不要渐变文字。
7. 不要把热力格底色做到 50% 以上。

## Agent Prompt Guide

让 AI 改这个页面时，这三句必须写进 prompt：

> 1. 令牌只改 `:root`，组件里不写裸色值。
> 2. 字号只能从 `display / heading / subheading / body / ui / caption / micro / badge / input` 里挑。
> 3. 改完必须跑量化审计：横向溢出 = 0、低对比文字 = 0、移动端 <44px 热区 = 0。

审计脚本在 `_design_shots/v4/audit_v4.py`（暗色，5 页 × 4 断点）与 `_design_shots/v4/light_audit.py`（浅色抽查）；需求验收脚本 `_design_shots/v4/verify_v5.py`（地域入参 / 登录引导 / 产品类目）。
