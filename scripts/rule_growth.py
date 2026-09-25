#!/usr/bin/env python3
"""rule_growth.py — M4 规则自生长（可进化架构 P2）。

设计目标（见 references/evolution_plan.md M4）：
  把 quality_dashboard 累积的多期「26 项自检」聚合，画「每条规则的 FAIL/WARN 频率」，
  让 rubric 开始「长」出来——高频 FAIL 的规则自动判断：
    - 硬结构规则（元信息/章节/来源链路等）→ 多半是 rubric 定义过严或生成器未满足
      → 建议「修复生成模板/parser」而非放宽；
    - 软质量规则（技术注解/信号层/前瞻覆盖等）→ 多半是 prompt 提示不足或阈值过紧
      → 建议「加强 prompt」或「放宽阈值」。
  输出结构化建议 + 写入 state/rule_growth.json（human-in-loop，不直接改规则）。

数据来源（零网络、零新增采集）：根目录全部 芯片行业日报_*.md 的 parser.selfcheck。
fail-soft：缺文件/解析失败自动跳过。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_MD_RE = "芯片行业日报_*.md"
OUT_PATH = ROOT / "state" / "rule_growth.json"

# 硬结构规则（必须 PASS；频繁 FAIL = 定义/模板 bug，不该放宽）
HARD_KEYWORDS = [
    "元信息", "产业链完整性", "来源可追溯", "章节顺序", "标题日期", "新闻条数",
    "来源统计位置", "环节全称", "免责声明", "自检小节", "去重", "附录越界", "中立性",
]
# 软质量规则（覆盖/质量；频繁 WARN/FAIL = prompt 提示或放宽阈值）
SOFT_KEYWORDS = [
    "摘要规范", "时效性", "今日要点", "技术注解", "产业链关联", "信号层",
    "持续追踪", "前瞻催化剂", "费曼解释", "今日导师课", "来源质量", "前瞻确定性分级",
    "前瞻兑现回顾",
]

FAIL_TH = 0.30   # 失败率阈值
WARN_TH = 0.50   # 弱信号（WARN）频率阈值
MIN_N = 3        # 样本下限（少于此不推断，防小样本过拟合）


def _classify(name: str) -> str:
    for k in HARD_KEYWORDS:
        if k in name:
            return "hard"
    return "soft"


def collect_selfchecks() -> list[tuple[str, list]]:
    """返回 [(date_str, [selfcheck dicts])]，扫描全部日报。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    from report_viz import parser

    history = []
    for p in sorted(ROOT.glob(REPO_MD_RE)):
        try:
            d = p.stem.replace("芯片行业日报_", "")
            rep = parser.parse_report(p)
            sc = rep.get("selfcheck") or []
            if sc:
                history.append((d, sc))
        except Exception:
            continue
    return history


def tally(history: list[tuple[str, list]]) -> dict:
    """按 (num, name) 聚合 PASS/FAIL/WARN。"""
    agg = defaultdict(lambda: {"num": None, "name": None, "PASS": 0, "FAIL": 0, "WARN": 0, "total": 0})
    for _d, scs in history:
        for c in scs:
            key = (c.get("num"), c.get("name"))
            a = agg[key]
            a["num"] = c.get("num")
            a["name"] = c.get("name")
            a["total"] += 1
            res = str(c.get("result", "")).upper()
            if res == "FAIL":
                a["FAIL"] += 1
            elif res == "WARN":
                a["WARN"] += 1
            else:
                a["PASS"] += 1
    return dict(agg)


def suggest(agg: dict) -> list[dict]:
    out = []
    for (num, name), a in agg.items():
        n = a["total"]
        if n < MIN_N:
            continue
        fail_rate = a["FAIL"] / n
        warn_rate = a["WARN"] / n
        kind = _classify(name or "")
        if fail_rate >= FAIL_TH:
            if kind == "hard":
                rec = ("硬结构规则频繁 FAIL（失败率 %.0f%%）：多半是 rubric 定义过严或"
                       "生成/解析模板未满足，建议修复生成模板与 parser，而非放宽校验"
                       % (fail_rate * 100))
                action = "fix_template"
            else:
                rec = ("软质量规则频繁 FAIL（失败率 %.0f%%）：建议加强 prompt 中明确该要求；"
                       "若属合理宽松则下调期望阈值" % (fail_rate * 100))
                action = "tighten_prompt"
            out.append({
                "num": num, "name": name, "kind": kind,
                "total": n, "fail_rate": round(fail_rate, 3), "warn_rate": round(warn_rate, 3),
                "issue": f"规则「{name}」失败率 {fail_rate:.0%} 超阈值 {FAIL_TH:.0%}",
                "action": action, "recommendation": rec,
            })
        elif warn_rate >= WARN_TH:
            if kind == "soft":
                rec = ("软质量规则频繁 WARN（弱信号率 %.0f%%）：长期若可接受则放宽阈值；"
                       "否则在 prompt 中加强该要求示例" % (warn_rate * 100))
                action = "relax_or_prompt"
            else:
                rec = ("硬结构规则频繁 WARN（弱信号率 %.0f%%）：检查是否边界条件过紧，"
                       "优先收紧 parser 判定而非放宽规则" % (warn_rate * 100))
                action = "fix_parser"
            out.append({
                "num": num, "name": name, "kind": kind,
                "total": n, "fail_rate": round(fail_rate, 3), "warn_rate": round(warn_rate, 3),
                "issue": f"规则「{name}」弱信号率 {warn_rate:.0%} 超阈值 {WARN_TH:.0%}",
                "action": action, "recommendation": rec,
            })
    # 按严重度排序：FAIL 优先、再按频率
    out.sort(key=lambda s: (s["fail_rate"], s["warn_rate"]), reverse=True)
    return out


def run() -> dict:
    history = collect_selfchecks()
    agg = tally(history)
    suggestions = suggest(agg)
    # 全规则频率快照（供 M5/看板复用）
    snapshot = [
        {"num": k[0], "name": v["name"], "total": v["total"],
         "pass": v["PASS"], "fail": v["FAIL"], "warn": v["WARN"],
         "fail_rate": round(v["FAIL"] / v["total"], 3) if v["total"] else None,
         "warn_rate": round(v["WARN"] / v["total"], 3) if v["total"] else None,
         "kind": _classify(v["name"] or "")}
        for k, v in sorted(agg.items(), key=lambda kv: (kv[0][0] or 0))
    ]
    return {
        "schema_version": 1,
        "generated": date.today().isoformat(),
        "reports_analyzed": len(history),
        "thresholds": {"fail": FAIL_TH, "warn": WARN_TH, "min_n": MIN_N},
        "snapshot": snapshot,
        "suggestions": suggestions,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="M4 规则自生长：聚合多期 26 项自检频率")
    ap.add_argument("--apply", action="store_true", help="写入 state/rule_growth.json")
    args = ap.parse_args()

    result = run()
    print(f"分析期数：{result['reports_analyzed']} | 规则数：{len(result['snapshot'])}")
    print(f"FAIL 阈值 {FAIL_TH:.0%} / WARN 阈值 {WARN_TH:.0%} / 样本下限 {MIN_N}")
    if result["suggestions"]:
        print("\n🌱 规则自生长建议（human-in-loop）：")
        for s in result["suggestions"]:
            tag = "硬" if s["kind"] == "hard" else "软"
            print(f"  - [#{s['num']} {s['name']}·{tag}] {s['issue']}")
            print(f"    → 动作={s['action']}：{s['recommendation']}")
    else:
        print("\n✅ 当前各规则 FAIL/WARN 频率均在阈值内，rubric 暂无需自生长。")

    if args.apply:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[rule_growth] 已写入 {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
