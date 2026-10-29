# 商机获客 · 线索雷达（Lead Radar）

一套「采集 → 识别 → 入库 → 跟进」的商机获客平台，供 WorkBuddy skill 形式分发。

- **采集**：Playwright 复用登录态，抓取抖音 / 小红书关键词搜索下的公开评论
- **识别**：意向打分（高/中/低）+ 行业分类（13 类产品）
- **入库**：写入资料库数据表（获客意向客户 / 获客采集任务），增量去重
- **跟进**：工作台页面 `workbench/huoke-radar.html`，可视化 + 状态流转 + 一键采集

## 快速开始

1. 用「资料库」skill 建两张表（字段见 `docs/搭建指南.md`）
2. `python scripts/init_workspace.py --leads-db <id> --tasks-db <id>` 绑定表 id
3. 把 `workbench/huoke-radar.html` 部署到资料库，得到你的链接
4. `python -m pip install -r scripts/requirements.txt`
5. `python scripts/init_session.py` 登录抖音/小红书
6. 双击 `scripts/start_agent.bat` + 打开工作台 → 「采集任务」→ 开始采集

详见 **`docs/搭建指南.md`**（从零到上线）与 **`SKILL.md`**（AI 引导流程）。

## 目录

```
SKILL.md                引导文件（AI 工作流）
scripts/                采集器 + 初始化 + 一键脚本
workbench/              工作台页面（部署用）
docs/                   搭建指南 + 设计文档
```

## 合规

仅个人工作/学习/研究，禁止商用。只采集公开评论文本，不获取隐私信息，控制频率。
