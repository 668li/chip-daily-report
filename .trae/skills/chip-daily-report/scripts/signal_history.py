#!/usr/bin/env python3
"""signal_history.py —— 信号历史累积（迭代5 · 认知深化 A）。

把 `state/report_state.yaml` 的「当日持续追踪主题快照」追加到
`state/signal_history.json` 历史数组（幂等：同日覆盖，不重复累积），
作为信号强度曲线 / 周度复盘 / 认知分析的原始数据源。

设计决策：
  - report_state.yaml 由生成流程 Step 6（AI）维护，保持手写格式（≤15 行）不变；
    本脚本只读它，绝不改写。
  - 历史数据写到独立 JSON（与 value_score.json 同模式：数组 + 同日 upsert）。
  - 快照只取结构化字段 (topic, direction, streak, signal)，不含 delta 长文本
    （delta 在各期日报「持续追踪」小节里有，周度复盘直接从日报提取）。

CLI：python scripts/signal_history.py [--date YYYYMMDD] [--force]
  --date  默认取 state/report_state.yaml 的 last_report_date
  --force 同日强制覆盖（默认已存在即跳过，幂等）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
STATE_YAML = ROOT / "state" / "report_state.yaml"
HISTORY_JSON = ROOT / "state" / "signal_history.json"

# 允许的方向取值（与 report_state.yaml / SKILL.md 一致）
VALID_DIRECTIONS = {"up", "down", "flat", "tight", "loose"}


def norm_date(s: str) -> str:
    """归一化日期为 YYYYMMDD：'2026-08-09' -> '20260809'（兼容手写带横线格式）。"""
    digits = re.sub(r"\D", "", str(s))
    return digits if len(digits) == 8 else str(s)


def load_state() -> dict | None:
    """读 report_state.yaml；缺失 / 损坏 / 无 yaml 时返回 None（fail-soft）。"""
    if yaml is None:
        return None
    try:
        data = yaml.safe_load(STATE_YAML.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_history() -> list:
    """读 signal_history.json；缺失 / 损坏时返回空列表。"""
    try:
        data = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def snapshot_topics(state: dict) -> list[dict]:
    """把 tracked_topics 洗成轻量快照（去掉 delta 长文本）。"""
    out = []
    for t in state.get("tracked_topics") or []:
        topic = (t.get("topic") or "").strip()
        direction = (t.get("direction") or "").strip().lower()
        if not topic or direction not in VALID_DIRECTIONS:
            continue
        out.append(
            {
                "topic": topic,
                "direction": direction,
                "streak": int(t.get("streak") or 1),
                "signal": (t.get("signal") or "中/中性/中性").strip(),
            }
        )
    return out


def upsert(history: list, date_str: str, snapshot: list[dict]) -> list:
    """写回累计数组（同日覆盖，幂等），按日期排序。"""
    HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    entry = {"date": date_str, "topics": snapshot}
    history = [h for h in history if h.get("date") != date_str]
    history.append(entry)
    history.sort(key=lambda h: h.get("date", ""))
    HISTORY_JSON.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return history


def run(date_str: str | None = None, force: bool = False) -> dict | None:
    """执行一次累积。返回写入的快照条目；无 state / 无日期 / 已存在且非 force -> None。"""
    state = load_state()
    if not state:
        print("[signal_history] 未找到可用的 state/report_state.yaml，跳过（fail-soft）")
        return None
    date_str = norm_date(date_str or state.get("last_report_date") or "")
    if not date_str:
        print("[signal_history] report_state.yaml 缺 last_report_date，跳过")
        return None
    snapshot = snapshot_topics(state)
    if not snapshot:
        print(f"[signal_history] {date_str} 无有效追踪主题快照，跳过")
        return None

    history = load_history()
    if any(h.get("date") == date_str for h in history) and not force:
        print(f"[signal_history] {date_str} 快照已存在，跳过（--force 可覆盖）")
        return None

    history = upsert(history, date_str, snapshot)
    entry = next(h for h in history if h.get("date") == date_str)
    print(f"[signal_history] 已累积 {date_str} 快照：{len(snapshot)} 个主题")
    for t in snapshot:
        print(f"  - {t['topic']}：{t['direction']}（连续 {t['streak']} 期）{t['signal']}")
    print(f"  历史累计 {len(history)} 期 -> {HISTORY_JSON.relative_to(ROOT)}")
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="累积 report_state.yaml 当日主题快照到信号历史")
    ap.add_argument("--date", default=None, help="YYYYMMDD，默认取 state 内 last_report_date")
    ap.add_argument("--force", action="store_true", help="同日强制覆盖")
    args = ap.parse_args()
    # fail-soft：无 state / 已存在快照 都是正常跳过，一律返回 0 不阻塞下游
    run(args.date, args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
