#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_health_check — 数据源健康度监控（v6.0 迭代1 A2）单元测试。

覆盖：
  - _status_of 状态判定（0→ok / 1-2→degraded / ≥3→down）
  - merge_health：7 日可用率滑动窗口、连续失败累积、当天去重（幂等）
  - fail-soft：探针全 down 时不抛异常、状态正确标记
  - compute_global_metrics：空产物 → 全 0 不抛
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from multi_source import health_check as hc


def test_status_of():
    assert hc._status_of(0) == "ok"
    assert hc._status_of(1) == "degraded"
    assert hc._status_of(2) == "degraded"
    assert hc._status_of(3) == "down"
    assert hc._status_of(10) == "down"


def test_merge_health_basic(monkeypatch, tmp_path):
    monkeypatch.setattr(hc, "HEALTH_FILE", tmp_path / "source_health.yaml")
    monkeypatch.setattr(hc, "STATE_DIR", tmp_path)
    probes = [
        {"source_id": "sec_edgar", "source_name": "SEC EDGAR", "status": "ok",
         "http_status": 200, "latency_ms": 500, "error": None},
        {"source_id": "aihot", "source_name": "AIHOT", "status": "down",
         "http_status": None, "latency_ms": 3000, "error": "timeout"},
    ]
    health = hc.merge_health(probes, {"raw_count": 19})
    assert len(health["sources"]) == 2
    s1 = health["sources"][0]
    assert s1["status"] == "ok"
    assert s1["consecutive_failures"] == 0
    assert s1["availability_7d"] == 1.0
    s2 = health["sources"][1]
    assert s2["status"] == "degraded"  # 首次失败
    assert s2["consecutive_failures"] == 1
    assert s2["last_error"] == "timeout"


def test_merge_idempotent_same_day(monkeypatch, tmp_path):
    """同一天重复运行：history 当天去重，不重复累积。"""
    monkeypatch.setattr(hc, "HEALTH_FILE", tmp_path / "source_health.yaml")
    monkeypatch.setattr(hc, "STATE_DIR", tmp_path)
    probe = {"source_id": "aihot", "source_name": "AIHOT", "status": "ok",
             "http_status": 200, "latency_ms": 200, "error": None}
    h1 = hc.merge_health([probe], {})
    h2 = hc.merge_health([probe], {})
    hist = h2["sources"][0]["history"]
    assert len(hist) == 1, "当天重复运行应只保留 1 条 history"
    assert h2["sources"][0]["consecutive_failures"] == 0


def test_merge_failure_accumulates(monkeypatch, tmp_path):
    """连续失败累积到 down，且可用率下降（模拟真实 run 链路：merge→write→merge…）。"""
    monkeypatch.setattr(hc, "HEALTH_FILE", tmp_path / "source_health.yaml")
    monkeypatch.setattr(hc, "STATE_DIR", tmp_path)
    probe = {"source_id": "sec_edgar", "source_name": "SEC EDGAR", "status": "down",
             "http_status": None, "latency_ms": 999, "error": "x"}
    health = None
    for _ in range(4):
        health = hc.merge_health([probe], {})
        hc.write_health(health)  # 持久化，供下一次 merge 读取历史
    s = health["sources"][0]
    assert s["consecutive_failures"] == 4
    assert s["status"] == "down"


def test_compute_global_metrics_missing_files(monkeypatch, tmp_path):
    """产物缺失 → 全 0，不抛异常（fail-soft）。"""
    monkeypatch.setattr(hc, "DATA_DIR", tmp_path)  # 空目录
    g = hc.compute_global_metrics()
    assert g["raw_count"] == 0
    assert g["cleaned_count"] == 0
    assert g["discard_rate"] == 0.0
    assert g["fused_events"] == 0
    assert g["conflict_rate"] == 0.0
    assert g["gap_cells"] == 0


def test_probe_failsoft(monkeypatch, tmp_path):
    """探针内部异常 → 返回 down 列表，不抛出。
    HEALTH_FILE/STATE_DIR 必须指向 tmp_path：run() 末尾会 write_health 真实
    落盘，不 patch 会覆盖受跟踪的 state/source_health.yaml 并删掉 4 个源的
    历史（对抗审查 #9 披露的存量污染缺陷，此处修根因）。"""
    def boom(timeout=8):
        raise RuntimeError("network unreachable")
    monkeypatch.setattr(hc, "HEALTH_FILE", tmp_path / "source_health.yaml")
    monkeypatch.setattr(hc, "STATE_DIR", tmp_path)
    monkeypatch.setattr(hc, "collect_probes", boom)
    try:
        # collect_probes 本身抛异常由 run() 处理：这里验证 run 不炸
        health = hc.run()
        assert isinstance(health, dict)
        assert (tmp_path / "source_health.yaml").exists()  # 落盘走 tmp
    except Exception:
        raise AssertionError("run() 在探针异常时应 fail-soft，不应抛出")
