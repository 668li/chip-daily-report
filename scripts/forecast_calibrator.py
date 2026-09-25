#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forecast_calibrator.py — 预判校准器（M3，可进化架构进化核心）。

扫描 state/forecast_log.json 中已验证(verified=True)的前瞻条目，按确定性档位
（高确定性/中确定性/低确定性）统计「实际偏差率」，识别分级标准是否失准，
自动生成 rubric 修订建议。

这是可进化架构的关键反馈线（接 Karpathy「Verifiability」思想）：把"预测误差"
接回"置信度标准"——系统用自己的错判校准自己的自信，对抗 ghost 路径的过度
自信通病。

输出：
  - 人类可读报告（stdout）
  - --apply 时写入 state/forecast_calibration.json（结构化建议，human-in-loop）

fail-soft：数据缺失/解析失败 → 空建议，不抛异常、不阻塞。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOG_PATH = REPO / "state" / "forecast_log.json"
OUT_PATH = REPO / "state" / "forecast_calibration.json"

# 偏差率阈值：某档位实际偏差率超过该值则建议复核分级标准
DEV_THRESHOLD = 0.20
CERT_ORDER = ["高确定性", "中确定性", "低确定性"]

# 多剧本并行打分（L4 情景推演）：互斥剧本立场
STANCE_ORDER = ["真趋势", "炒作", "被绕开"]
# 各立场「理想」命中方向：真趋势应被印证、炒作应被打脸、被绕开应被印证（替代路线成真）
STANCE_HOPEFUL = {"真趋势": "一致", "炒作": "有偏差", "被绕开": "一致"}


def _load() -> dict | None:
    if not LOG_PATH.exists():
        return None
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _is_consistent(verdict: str) -> bool:
    return str(verdict or "").startswith("一致")


def _is_deviated(verdict: str) -> bool:
    return "偏差" in str(verdict or "")


def _scenario_records(entries: list) -> list[dict]:
    """展开所有已验证的互斥剧本为 (stance, verdict, entry_event) 记录。

    向后兼容：条目无 scenarios 时返回空（由确定性档位统计兜底）。
    """
    recs = []
    for e in entries:
        for s in e.get("scenarios") or []:
            if not s.get("verified"):
                continue
            recs.append(
                {
                    "stance": s.get("stance", "真趋势"),
                    "verdict": s.get("verdict", ""),
                    "event": e.get("event", ""),
                    "statement": s.get("statement", ""),
                    "entry_id": e.get("id"),
                }
            )
    return recs


def calibrate(data: dict | None) -> dict:
    entries = (data or {}).get("entries", []) or []
    verified = [e for e in entries if e.get("verified")]

    # ---- 既有：按确定性档位统计（向后兼容）----
    groups: dict[str, list] = {c: [] for c in CERT_ORDER}
    for e in verified:
        c = e.get("certainty", "中确定性")
        if c not in groups:
            c = "中确定性"
        groups[c].append(e)

    stats: dict[str, dict] = {}
    suggestions: list[dict] = []
    for c in CERT_ORDER:
        items = groups[c]
        n = len(items)
        if n == 0:
            stats[c] = {"total": 0, "consistent": 0, "deviated": 0, "dev_rate": None}
            continue
        consistent = sum(1 for e in items if _is_consistent(e.get("verdict", "")))
        deviated = n - consistent
        dev_rate = deviated / n
        stats[c] = {
            "total": n,
            "consistent": consistent,
            "deviated": deviated,
            "dev_rate": round(dev_rate, 3),
        }
        if dev_rate > DEV_THRESHOLD:
            dev_samples = [
                {"id": e.get("id"), "event": e.get("event"), "verified_note": e.get("verified_note")}
                for e in items
                if not _is_consistent(e.get("verdict", ""))
            ]
            suggestions.append(
                {
                    "kind": "certainty",
                    "certainty": c,
                    "dev_rate": round(dev_rate, 3),
                    "n": n,
                    "issue": f"{c}事件实际偏差率 {dev_rate:.0%} 超过阈值 {DEV_THRESHOLD:.0%}",
                    "recommendation": (
                        f"复核「{c}」分级标准：当前偏差偏高，建议重新界定该档位"
                        "「时点官宣」的边界（如是否混淆了'会谈已宣布'与'成果已确认'、"
                        "'法规生效日'与'细则落地日'），并在 SKILL.md 确定性 rubric 中"
                        "收紧定义或补充反例。"
                    ),
                    "dev_samples": dev_samples,
                }
            )

    # ---- 新增：多剧本并行打分（L4 情景推演）----
    scen = _scenario_records(verified)
    scenario_stats: dict[str, dict] = {}
    for st in STANCE_ORDER:
        recs = [r for r in scen if r["stance"] == st]
        n = len(recs)
        if n == 0:
            scenario_stats[st] = {"total": 0, "consistent": 0, "deviated": 0, "hit_rate": None}
            continue
        consistent = sum(1 for r in recs if _is_consistent(r["verdict"]))
        deviated = n - consistent
        # hit = 该立场「理想方向」被印证的比例（真趋势/被绕开→一致；炒作→有偏差）
        hopeful = STANCE_HOPEFUL[st]
        hit = sum(1 for r in recs if str(r["verdict"]).startswith(hopeful[:2]))
        scenario_stats[st] = {
            "total": n,
            "consistent": consistent,
            "deviated": deviated,
            "hit_rate": round(hit / n, 3),
        }
        # 剧本校准建议：某立场命中率显著偏离预期（< 0.5 视为系统性误判）
        if n >= 2 and hit / n < 0.5:
            suggestions.append(
                {
                    "kind": "scenario",
                    "stance": st,
                    "hit_rate": round(hit / n, 3),
                    "n": n,
                    "issue": (
                        f"「{st}」剧本命中率仅 {hit / n:.0%}（理想方向："
                        f"{'被印证' if hopeful == '一致' else '被打脸'}），"
                        f"系统对该类剧本判断失准"
                    ),
                    "recommendation": _scenario_advice(st, hit / n),
                    "dev_samples": [
                        {"event": r["event"], "statement": r["statement"], "verdict": r["verdict"]}
                        for r in recs
                        if not str(r["verdict"]).startswith(hopeful[:2])
                    ],
                }
            )

    # 剧本权重小结（升级/淘汰信号）
    scenario_weights = {
        st: (round(s["hit_rate"], 3) if s["hit_rate"] is not None else None)
        for st, s in scenario_stats.items()
    }

    return {
        "schema_version": 2,
        "generated": date.today().isoformat(),
        "threshold": DEV_THRESHOLD,
        "verified_total": len(verified),
        "stats_by_certainty": stats,
        "scenario_stats": scenario_stats,
        "scenario_weights": scenario_weights,
        "suggestions": suggestions,
    }


def _scenario_advice(stance: str, hit_rate: float) -> str:
    if stance == "真趋势":
        return (
            "我们对「真趋势」剧本过度自信：真趋势频被现实打脸。建议在判真趋势前"
            "强制列出至少 1 条反向证据（技术/产能/政策阻力），否则降一档确定性；"
            "并把「被绕开」剧本作为真趋势的默认对立面同时悬挂。"
        )
    if stance == "炒作":
        return (
            "「炒作」剧本频被现实印证（市场叙事有时领先基本面）：说明我们低估了"
            "资本叙事的兑现力。建议提升炒作剧本的权重，对高关注度的叙事单独追踪"
            "其后续是否被业绩/产能落地，而非一律当作噪声。"
        )
    # 被绕开
    return (
        "「被绕开」剧本频被现实打脸（替代路线未成真）：我们对技术绕开路径过于乐观。"
        "建议收紧「被绕开」剧本的触发条件——仅在已有量产/客户背书信号时才挂，"
        "避免把纯论文/实验室进展当作可绕开主线的证据。"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="预判校准器（M3 可进化架构）")
    ap.add_argument("--apply", action="store_true", help="将建议写入 state/forecast_calibration.json")
    args = ap.parse_args()

    data = _load()
    if data is None:
        print("[calibrator] fail-soft: forecast_log.json 缺失或无法解析，跳过")
        return 0

    result = calibrate(data)

    print(f"已验证前瞻总数：{result['verified_total']}")
    for c, s in result["stats_by_certainty"].items():
        if s["total"] == 0:
            continue
        dr = f"{s['dev_rate']:.0%}" if s["dev_rate"] is not None else "—"
        print(f"  {c}：{s['total']} 条 · 一致 {s['consistent']} · 偏差 {s['deviated']} · 偏差率 {dr}")

    # 多剧本并行打分
    scen_total = sum(s["total"] for s in result["scenario_stats"].values())
    if scen_total:
        print("\n🎭 多剧本并行打分（L4 情景推演）：")
        for st, s in result["scenario_stats"].items():
            if s["total"] == 0:
                continue
            hr = f"{s['hit_rate']:.0%}" if s["hit_rate"] is not None else "—"
            print(f"  [{st}] {s['total']} 个剧本 · 印证 {s['consistent']} · 被打脸 {s['deviated']} · 命中率 {hr}")
        w = result["scenario_weights"]
        active = {k: v for k, v in w.items() if v is not None}
        if active:
            best = max(active, key=lambda k: active[k])
            worst = min(active, key=lambda k: active[k])
            print(f"  → 当前最会判的剧本：{best}（命中率 {active[best]:.0%}）；"
                  f"最易误判：{worst}（命中率 {active[worst]:.0%}）")
    else:
        print("\n（暂无互斥剧本数据 —— add 时带 --scenarios 即可启用多剧本并行打分）")

    if result["suggestions"]:
        print("\n⚠️ 校准建议（human-in-loop，不直接改 rubric）：")
        for s in result["suggestions"]:
            if s.get("kind") == "scenario":
                print(f"  - [剧本·{s['stance']}] {s['issue']}")
            else:
                print(f"  - [{s['certainty']}] {s['issue']}")
            print(f"    → {s['recommendation']}")
    else:
        print("\n✅ 各档位偏差率与剧本命中率均在合理区间，暂无需修订 rubric。")

    if args.apply:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[calibrator] 已写入 {OUT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
