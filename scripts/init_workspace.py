# -*- coding: utf-8 -*-
"""
商机获客 · 初始化工作台绑定
================================
把你在资料库里新建的「获客意向客户」「获客采集任务」两张表的 id，
替换进工作台页面与推送脚本，使整套采集链路指向你自己的表。

用法（在 skill 根目录下）：
    python scripts/init_workspace.py --leads-db <新意向客户表id> --tasks-db <新采集任务表id>

说明：
  - 纯文本全局替换，不需要 token，重复执行安全（已替换则无变化）。
  - 会修改 workbench/huoke-radar.html、scripts/huoke_push.py、scripts/push_pending.py。
  - 修改前自动备份为 *.bak（仅当原 id 仍在文件中时）。

前置步骤（在 WorkBuddy 里用「资料库」skill 完成）：
  1. 建一张表，命名为「获客意向客户」，字段见 docs/搭建指南.md 的表结构；
  2. 建一张表，命名为「获客采集任务」，字段见 docs/搭建指南.md 的表结构；
  3. 分别复制两张表的 id，传给本脚本。

声明：仅供个人工作 / 学习 / 研究使用，禁止商用。
"""

import argparse
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

OLD_LEADS = "MjDdEbw22n8gTgFBOrPurw"
OLD_TASKS = "i10XscWBOy9GwEoaCocg39"

FILES = [
    os.path.join(SKILL_ROOT, "workbench", "huoke-radar.html"),
    os.path.join(SKILL_ROOT, "scripts", "huoke_push.py"),
    os.path.join(SKILL_ROOT, "scripts", "push_pending.py"),
]


def replace_in_file(path, old, new, replaced_log):
    if not os.path.exists(path):
        print("[跳过] 不存在：%s" % path)
        return 0
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    n = content.count(old)
    if n == 0:
        print("[无变化] %s（未找到 %s）" % (os.path.basename(path), old))
        return 0
    if not os.path.exists(path + ".bak"):
        shutil.copy2(path, path + ".bak")
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    replaced_log.append((os.path.basename(path), old, new, n))
    print("[替换] %s：%s → %s（%d 处）" % (os.path.basename(path), old, new, n))
    return n


def main():
    ap = argparse.ArgumentParser(description="商机获客 · 初始化工作台表绑定")
    ap.add_argument("--leads-db", required=True, help="新建的「获客意向客户」表 id")
    ap.add_argument("--tasks-db", required=True, help="新建的「获客采集任务」表 id")
    args = ap.parse_args()

    leads = (args.leads_db or "").strip()
    tasks = (args.tasks_db or "").strip()
    if not leads or not tasks:
        print("[!] 两个表 id 都不能为空")
        return 1
    if leads == OLD_LEADS or tasks == OLD_TASKS:
        print("[!] 传入的 id 与默认值相同，请确认你新建了表而不是误传旧 id")
        return 1

    log = []
    total = 0
    for f in FILES:
        total += replace_in_file(f, OLD_LEADS, leads, log)
        total += replace_in_file(f, OLD_TASKS, tasks, log)

    if total == 0:
        print("✅ 所有文件均已绑定到目标表（无需修改）。")
    else:
        print("\n✅ 初始化完成，共替换 %d 处。已自动备份原文件为 *.bak。" % total)
        print("   下一步：把 workbench/huoke-radar.html 部署到资料库，即可获得你的工作台链接。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
