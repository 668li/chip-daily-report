#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.gap_analyzer — 模块1：数据源盘点与缺口分析。

基于 source_registry.json 的目标覆盖网格（环节 × 源类型），计算：
  - 每环节 × 每源类型的实际源数 vs 目标源数 → 缺口
  - 缺口等级：充足 / 可接受 / 缺口 / 严重缺口
  - 输出 data/gap_report.md（差距清单）+ data/gap_report.json

信息差根源：某（环节 × 源类型）网格为空或仅 1 个源 → 该格子只能看到单一叙事，
无法交叉验证 → 信息差最大。缺口分析的目标就是把这类格子全部填到 ≥2。
"""
from __future__ import annotations

import json
from pathlib import Path

from registry import DATA_DIR, SEGMENTS, TYPES, TYPE_LABEL, build_registry

LEVEL_ORDER = {"严重缺口": 0, "缺口": 1, "可接受": 2, "充足": 3}
LEVEL_COLOR = {"严重缺口": "🔴", "缺口": "🟠", "可接受": "🟡", "充足": "🟢"}


def level_of(actual: int, target: int) -> str:
    if actual >= target:
        return "充足" if actual >= target + 1 else "可接受"
    if actual == 0:
        return "严重缺口"
    return "缺口"


def analyze(reg: dict) -> dict:
    grid = reg["grid"]
    target = reg["target_grid"]
    cells = []
    gaps = []
    for seg in SEGMENTS:
        for t in TYPES:
            srcs = grid.get(seg, {}).get(t, [])
            actual = len(srcs)
            tgt = target.get(seg, {}).get(t, 1)
            lvl = level_of(actual, tgt)
            cells.append(
                {"segment": seg, "type": t, "type_label": TYPE_LABEL[t],
                 "actual": actual, "target": tgt, "level": lvl, "source_ids": srcs}
            )
            if lvl in ("缺口", "严重缺口"):
                gaps.append(cells[-1])
    gaps.sort(key=lambda c: (LEVEL_ORDER[c["level"]], c["segment"], c["type"]))
    return {"cells": cells, "gaps": gaps,
            "gap_count": len(gaps),
            "severe_count": sum(1 for c in gaps if c["level"] == "严重缺口")}


def render_md(reg: dict, res: dict) -> str:
    lines = []
    lines.append("# 数据源缺口分析报告（模块1）\n")
    lines.append(f"> 生成时间: 2026-08-09 ｜ 数据源总数: {reg['source_count']['total']} "
                 f"（活跃 {reg['source_count']['active']} / 计划新增 {reg['source_count']['planned']}）\n")
    lines.append("## 一、覆盖网格总览（环节 × 源类型）\n")
    lines.append("| 环节 | " + " | ".join(TYPE_LABEL[t] for t in TYPES) + " |")
    lines.append("|------|" + "------|" * len(TYPES))
    for seg in SEGMENTS:
        row = [f"**{seg}**"]
        for t in TYPES:
            c = next(x for x in res["cells"] if x["segment"] == seg and x["type"] == t)
            row.append(f"{LEVEL_COLOR[c['level']]} {c['actual']}/{c['target']}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("\n> 数字 = 实际源数/目标源数。目标：常规格子 ≥1，data/filing/analysis ≥2（交叉验证最低要求）。\n")

    lines.append("## 二、差距清单（按严重度排序）\n")
    if not res["gaps"]:
        lines.append("🎉 无缺口：所有（环节 × 源类型）网格均已达标。\n")
    else:
        lines.append("| # | 严重度 | 环节 | 源类型 | 现状 | 目标 | 建议动作 |")
        lines.append("|---|--------|------|--------|------|------|----------|")
        actions = {
            ("设计", "data"): "接入 SIA/WSTS 与 DRAMeXchange 价格数据",
            ("设计", "filing"): "接 SEC EDGAR（NVIDIA/AMD/Broadcom 8-K）",
            ("制造", "data"): "接 TrendForce 合约价 + SEMI 产能数据",
            ("制造", "academic"): "接 ISSCC/IEDM 会议论文检索",
            ("封测", "data"): "接 Yole 封装市场数据 + TrendForce 封测产能",
            ("封测", "academic"): "接 IEEE Xplore 先进封装论文",
            ("EDA", "news"): "补中文 EDA 垂直媒体（芯思想/电子工程专辑）",
            ("EDA", "analysis"): "接 SemiEngineering + Yole EDA 分析",
            ("EDA", "academic"): "接 DAC 论文 + Google Patents 专利情报",
            ("材料", "academic"): "接 IEDM + Nature Electronics 材料研究",
        }
        for i, g in enumerate(res["gaps"], 1):
            act = actions.get((g["segment"], g["type"]),
                              f"按 Tier-0~2 补充 {g['type_label']} 源并纳入注册表")
            lines.append(f"| {i} | {LEVEL_COLOR[g['level']]} {g['level']} | {g['segment']} | "
                         f"{g['type_label']} | {g['actual']} 个 | ≥{g['target']} | {act} |")
        lines.append("")
    lines.append("## 三、结论与行动优先级\n")
    lines.append(f"- 当前缺口格 **{res['gap_count']}** 个（其中严重缺口 **{res['severe_count']}** 个）。")
    lines.append("- **信息差最大处** = 严重缺口格子：该处无任何独立源，只能依赖单一叙事。")
    lines.append("- **行动优先级**：先补 data/filing/analysis 三类（交叉验证与一手事实的关键），"
                 "再补 academic（学术一手），最后补 news 语言盲区。")
    lines.append("- 补齐路径：`scripts/multi_source/registry.py` 增源 → 重跑 gap_analyzer → "
                 "`collector.py` 接采集适配器 → 健康度进入监控。")
    return "\n".join(lines)


def main():
    reg = build_registry()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "source_registry.json").write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    res = analyze(reg)
    (DATA_DIR / "gap_report.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(reg, res)
    (DATA_DIR / "gap_report.md").write_text(md, encoding="utf-8")
    print(f"[gap] 缺口格 {res['gap_count']} 个（严重 {res['severe_count']}）→ gap_report.md / json 已写入 {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
