#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.health_check — 数据源健康度监控（v6.0，迭代1 A2）。

作用：
  - 每源：连通性探针（SEC EDGAR / AIHOT）+ 时延 + 连续失败计数 + 7 日可用率
  - 全局：采集量 / 清洗丢弃率 / 融合冲突率 / 缺口格数
  - 输出 state/source_health.yaml（与 report_state.yaml 同目录，供 F9 看板与 multi_source 报告消费）

设计原则：
  - fail-soft：网络不可用/文件缺失 → 状态 down / 指标 0，绝不抛异常、不影响退出码
  - 幂等：重复运行只更新当日记录，可用率用最近 7 日滑动窗口
  - CLI 独立可跑：python scripts/multi_source/health_check.py

运行环境：system Python 3.12（yaml 6.0.3 可用），勿用损坏的托管 venv。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/multi_source/ -> project root
STATE_DIR = ROOT / "state"
DATA_DIR = Path(__file__).resolve().parent / "data"
HEALTH_FILE = STATE_DIR / "source_health.yaml"

# 连续失败次数 → 状态
def _status_of(consecutive_failures: int) -> str:
    if consecutive_failures == 0:
        return "ok"
    if consecutive_failures <= 2:
        return "degraded"
    return "down"


def _load_json(name: str) -> list | dict | None:
    """读取 multi_source/data 下的 json，失败返回 None（fail-soft）。"""
    p = DATA_DIR / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_previous_health() -> dict | None:
    if yaml is None:
        return None
    try:
        if HEALTH_FILE.exists():
            return yaml.safe_load(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def collect_probes() -> list[dict]:
    """复用 collector 探针；collector 不可导入时（异常）返回空列表。"""
    try:
        from . import collector
        return collector.probe_online_sources()
    except Exception:
        # 兜底：直接按端点探测（避免 import 失败导致整个健康检查不可用）
        return _fallback_probe()


def _fallback_probe() -> list[dict]:
    import urllib.request
    import time
    results = []
    for sid, name, url in [
        ("sec_edgar", "SEC EDGAR",
         "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001045810&type=8-K&count=1&output=atom"),
        ("aihot", "AIHOT 聚合 API",
         "https://aihot.virxact.com/api/v1/items?mode=all&window=24h&limit=1"),
    ]:
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "chip-daily-report health-check contact@example.com"})
            with urllib.request.urlopen(req, timeout=8) as r:
                status_code = getattr(r, "status", 200)
            results.append({"source_id": sid, "source_name": name, "status": "ok",
                            "http_status": status_code,
                            "latency_ms": int((time.time() - start) * 1000), "error": None})
        except Exception as e:
            results.append({"source_id": sid, "source_name": name, "status": "down",
                            "http_status": None,
                            "latency_ms": int((time.time() - start) * 1000), "error": str(e)[:200]})
    return results


def compute_global_metrics() -> dict:
    """全局指标：raw/cleaned/fused 计数、丢弃率、冲突率、缺口格数。"""
    raw = _load_json("raw_events.json")
    cleaned = _load_json("cleaned_events.json")
    fused = _load_json("fused_events.json")
    gap = _load_json("gap_report.json")

    raw_count = len(raw) if isinstance(raw, list) else 0
    cleaned_count = len(cleaned) if isinstance(cleaned, list) else 0
    fused_events = len(fused) if isinstance(fused, list) else 0
    discard_rate = round((raw_count - cleaned_count) / raw_count, 4) if raw_count else 0.0

    n_div = 0
    if isinstance(fused, list):
        n_div = sum(len(ev.get("divergences") or []) for ev in fused)
    conflict_rate = round(n_div / fused_events, 4) if fused_events else 0.0

    gap_cells = 0
    severe = 0
    if isinstance(gap, dict):
        cells = gap.get("cells") or []
        gap_cells = len([c for c in cells if c.get("level") != "充足"])
        severe = len([c for c in cells if c.get("level") == "严重缺口"])
    return {
        "raw_count": raw_count,
        "cleaned_count": cleaned_count,
        "discard_rate": discard_rate,
        "fused_events": fused_events,
        "conflict_rate": conflict_rate,
        "gap_cells": gap_cells,
        "severe_gaps": severe,
    }


def merge_health(probes: list[dict], global_metrics: dict) -> dict:
    """合并探针结果与历史（7 日可用率滑动窗口），生成完整 health dict。"""
    today = date.today().isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    prev = load_previous_health() or {}
    prev_sources = {s["source_id"]: s for s in (prev.get("sources") or [])}

    out_sources = []
    for probe in probes:
        sid = probe["source_id"]
        old = prev_sources.get(sid, {})
        history = list(old.get("history") or [])
        # 当天已记录则替换，否则追加（保持最近 7 天）
        history = [h for h in history if h.get("date") != today]
        history.append({
            "date": today,
            "ok": probe["status"] == "ok",
            "latency_ms": probe["latency_ms"],
        })
        history = history[-7:]

        ok_days = sum(1 for h in history if h.get("ok"))
        availability = round(ok_days / len(history), 2) if history else 0.0
        consecutive = old.get("consecutive_failures", 0)
        consecutive = 0 if probe["status"] == "ok" else consecutive + 1

        latencies = [h.get("latency_ms", 0) for h in history if h.get("latency_ms")]
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0

        out_sources.append({
            "source_id": sid,
            "source_name": probe["source_name"],
            "status": _status_of(consecutive),
            "last_attempt": now,
            "last_success": now if probe["status"] == "ok" else old.get("last_success"),
            "consecutive_failures": consecutive,
            "availability_7d": availability,
            "avg_latency_ms": avg_latency,
            "last_error": probe.get("error"),
            "history": history,
        })

    return {
        "schema_version": 1,
        "generated": now,
        "sources": out_sources,
        "global": global_metrics,
    }


def write_health(health: dict) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(health, allow_unicode=True, sort_keys=False) if yaml else json.dumps(health, ensure_ascii=False, indent=2)
    HEALTH_FILE.write_text(text, encoding="utf-8")
    return HEALTH_FILE


def run() -> dict:
    """执行一次健康检查，返回 health dict（幂等可重复调用）。

    最终兜底：任何意外异常 → 产出全 down / 全 0 的健康记录，绝不抛出。
    """
    try:
        probes = collect_probes()
        global_metrics = compute_global_metrics()
    except Exception as e:  # pragma: no cover - 理论不可达，防御性兜底
        probes = [{"source_id": sid, "source_name": name, "status": "down",
                   "http_status": None, "latency_ms": 0, "error": str(e)[:200]}
                  for sid, name, _ in [
                      ("sec_edgar", "SEC EDGAR", ""), ("aihot", "AIHOT 聚合 API", "")]]
        global_metrics = {"raw_count": 0, "cleaned_count": 0, "discard_rate": 0.0,
                          "fused_events": 0, "conflict_rate": 0.0,
                          "gap_cells": 0, "severe_gaps": 0}
    health = merge_health(probes, global_metrics)
    write_health(health)
    return health


def main() -> int:
    health = run()
    print(f"[health_check] 已写入 {HEALTH_FILE.relative_to(ROOT)}")
    for s in health["sources"]:
        print(f"  {s['source_id']:<12} status={s['status']:<8} "
              f"latency={s['avg_latency_ms']}ms avail_7d={s['availability_7d']} "
              f"fail={s['consecutive_failures']} err={s['last_error'] or '-'}")
    g = health["global"]
    print(f"  global: raw={g['raw_count']} cleaned={g['cleaned_count']} "
          f"discard={g['discard_rate']} fused={g['fused_events']} "
          f"conflict={g['conflict_rate']} gaps={g['gap_cells']}(severe {g['severe_gaps']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
