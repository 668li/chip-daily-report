#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_value_score — 信息价值量化评分（v6.0 迭代1 A3）单元测试。

覆盖：
  - score_of 合成公式：全 0 → 0 分；全满 → 100 分；边界不越界
  - upsert 幂等：同一天覆盖、跨天累计
  - compute_metrics 从真实产物可计算、score∈[0,100]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from multi_source import value_score as vs


def test_score_of_zero():
    m = {"a_ratio": 0.0, "exclusive_leads": 0, "cross_cov": 0.0,
         "continuity": 0.0, "divergences": 0}
    assert vs.score_of(m) == 0.0


def test_score_of_full():
    m = {"a_ratio": 1.0, "exclusive_leads": 10, "cross_cov": 1.0,
         "continuity": 1.0, "divergences": 10}
    assert vs.score_of(m) == 100.0


def test_score_of_mid():
    # A=0.5*0.3=0.15, E=3/5*0.2=0.12, S=0.6*0.2=0.12, C=0.75*0.15=0.1125, D=2/5*0.15=0.06
    # sum=0.5625 → 56.25
    m = {"a_ratio": 0.5, "exclusive_leads": 3, "cross_cov": 0.6,
         "continuity": 0.75, "divergences": 2}
    assert vs.score_of(m) == 56.2


def test_upsert_idempotent_same_day(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "SCORE_FILE", tmp_path / "value_score.json")
    vs.upsert("20260809", {"date": "20260809", "score": 50.0})
    vs.upsert("20260809", {"date": "20260809", "score": 60.0})
    history = json.loads((tmp_path / "value_score.json").read_text(encoding="utf-8"))
    assert len(history) == 1
    assert history[0]["score"] == 60.0


def test_upsert_accumulates_dates(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "SCORE_FILE", tmp_path / "value_score.json")
    vs.upsert("20260808", {"date": "20260808", "score": 40.0})
    vs.upsert("20260809", {"date": "20260809", "score": 50.0})
    history = json.loads((tmp_path / "value_score.json").read_text(encoding="utf-8"))
    assert [h["date"] for h in history] == ["20260808", "20260809"]


def test_compute_metrics_from_real_products():
    """从真实产物（fused_events.json + report_state.yaml）可计算，score∈[0,100]。"""
    m = vs.compute_metrics("20260809")
    entry = {"score": vs.score_of(m)}
    assert 0.0 <= entry["score"] <= 100.0
    assert m["events"] > 0, "真实产物应有事件"
    assert 0.0 <= m["a_ratio"] <= 1.0
    assert m["exclusive_leads"] >= 0
    assert 0.0 <= m["cross_cov"] <= 1.0
    assert 0.0 <= m["continuity"] <= 1.0
