#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.value_score — 日报信息价值量化评分（v6.0，迭代1 A3）。

5 指标加权合成（消费现有产物，全部可自动计算）：
  A 级来源占比   A = 主源 tier≤1 的事件数 ÷ 事件总数         权重 0.30
  独家线索数     E = 单源且该源为 tier-4 聚合源的事件数       权重 0.20（min(E,5)/5）
  交叉验证覆盖   S = 有 ≥2 源佐证的事件覆盖的环节数 ÷ 5       权重 0.20
  跨日主题延续   C = report_state.yaml 中 streak≥2 主题数÷主题总数 权重 0.15
  分歧发现数     D = 全部事件 divergences 总数               权重 0.15（min(D,5)/5）

  价值分 = 100 × (0.30A + 0.20×min(E,5)/5 + 0.20S + 0.15C + 0.15×min(D,5)/5)

输出 state/value_score.json（历史累计数组，供 multi_source 报告与 F9 看板消费）。
CLI：python scripts/multi_source/value_score.py [--date YYYYMMDD]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "state"
DATA_DIR = Path(__file__).resolve().parent / "data"
SCORE_FILE = STATE_DIR / "value_score.json"

WEIGHTS = {"A": 0.30, "E": 0.20, "S": 0.20, "C": 0.15, "D": 0.15}
SEGMENTS = ["设计", "制造", "封测", "EDA", "材料"]


def _load_json(name: str):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def load_tier_map() -> dict:
    """source_id -> tier（来源注册表）。"""
    reg = _load_json("source_registry.json")
    if not isinstance(reg, dict):
        return {}
    out = {}
    for s in reg.get("sources") or []:
        out[s.get("id")] = s.get("tier")
    return out


def compute_metrics(date_str: str) -> dict:
    """从真实产物计算 5 指标，返回 {metric: value} 与明细。"""
    fused = _load_json("fused_events.json")
    gap = _load_json("gap_report.json")
    tier_map = load_tier_map()

    events = fused if isinstance(fused, list) else []
    n = len(events)
    if n == 0:
        return {"a_ratio": 0.0, "exclusive_leads": 0, "cross_cov": 0.0,
                "continuity": 0.0, "divergences": 0, "events": 0, "detail": {}}

    # A 级占比：主源 tier ≤ 1
    n_a = 0
    for ev in events:
        ps = ev.get("primary_source") or {}
        pid = ps.get("source_id")
        tier = tier_map.get(pid)
        if tier is None:
            # fallback：取 sources 里最小 tier
            tiers = [tier_map.get(s.get("source_id")) for s in (ev.get("sources") or [])]
            tiers = [t for t in tiers if t is not None]
            tier = min(tiers) if tiers else 9
        if tier <= 1:
            n_a += 1
    a_ratio = round(n_a / n, 4)

    # 独家线索：单源 且 该源 tier==4
    exclusive = 0
    for ev in events:
        srcs = ev.get("sources") or []
        if len(srcs) == 1:
            sid = srcs[0].get("source_id")
            if tier_map.get(sid) == 4:
                exclusive += 1

    # 交叉验证覆盖：≥2 源的事件覆盖的环节数 / 5
    covered_segs = set()
    for ev in events:
        if (ev.get("n_sources") or 0) >= 2:
            seg = ev.get("segment")
            if seg in SEGMENTS:
                covered_segs.add(seg)
    cross_cov = round(len(covered_segs) / len(SEGMENTS), 4)

    # 跨日主题延续率：report_state.yaml streak≥2 / 总数
    continuity = 0.0
    try:
        state = yaml.safe_load((STATE_DIR / "report_state.yaml").read_text(encoding="utf-8"))
        topics = state.get("tracked_topics") or []
        if topics:
            continued = sum(1 for t in topics if (t.get("streak") or 0) >= 2)
            continuity = round(continued / len(topics), 4)
    except Exception:
        pass

    # 分歧发现数
    n_div = sum(len(ev.get("divergences") or []) for ev in events)

    detail = {"n_a_tier_le1": n_a, "events": n, "exclusive_sources": exclusive,
              "covered_segments": sorted(covered_segs), "continued_topics": None}
    return {"a_ratio": a_ratio, "exclusive_leads": exclusive, "cross_cov": cross_cov,
            "continuity": continuity, "divergences": n_div, "events": n, "detail": detail}


def score_of(m: dict) -> float:
    """加权合成 0-100 分。"""
    a = m["a_ratio"]
    e = min(m["exclusive_leads"], 5) / 5
    s = m["cross_cov"]
    c = m["continuity"]
    d = min(m["divergences"], 5) / 5
    return round(100 * (WEIGHTS["A"] * a + WEIGHTS["E"] * e + WEIGHTS["S"] * s
                        + WEIGHTS["C"] * c + WEIGHTS["D"] * d), 1)


def upsert(date_str: str, entry: dict) -> list:
    """写回累计数组（同日覆盖，幂等）。"""
    SCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if SCORE_FILE.exists():
        try:
            history = json.loads(SCORE_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history = [h for h in history if h.get("date") != date_str]
    history.append(entry)
    history.sort(key=lambda h: h.get("date", ""))
    SCORE_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def run(date_str: str | None = None) -> dict:
    date_str = date_str or date.today().strftime("%Y%m%d")
    m = compute_metrics(date_str)
    entry = {
        "date": date_str,
        "a_ratio": m["a_ratio"],
        "exclusive_leads": m["exclusive_leads"],
        "cross_cov": m["cross_cov"],
        "continuity": m["continuity"],
        "divergences": m["divergences"],
        "events": m["events"],
        "score": score_of(m),
    }
    upsert(date_str, entry)
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="计算并写回日报信息价值分")
    ap.add_argument("--date", default=None, help="YYYYMMDD，默认今天")
    args = ap.parse_args()
    entry = run(args.date)
    print(f"[value_score] date={entry['date']} score={entry['score']}")
    print(f"  A级占比={entry['a_ratio']} 独家线索={entry['exclusive_leads']} "
          f"交叉验证={entry['cross_cov']} 主题延续={entry['continuity']} 分歧={entry['divergences']}")
    print(f"  已写回 {SCORE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
