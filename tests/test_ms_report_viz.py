#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ms_report_viz — 多源融合质量报告（v6.0 迭代1 A1）单元测试。

覆盖：
  - build() 四块内容齐全（事件卡片/漏聚候选/覆盖矩阵/缺口清单）
  - 空数据降级：各块显示 empty 提示，不抛异常
  - 从真实产物可生成完整 HTML
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from multi_source import report_viz as rv


FUSED = [
    {"event_id": "EV01", "title": "SK hynix 公布约 384 亿美元扩产计划", "segment": "制造",
     "published": "2026-08-07", "n_sources": 3, "n_unique_sources": 3,
     "verification": "verified", "confidence": 83.0,
     "primary_source": {"source_id": "skhynix_ir", "source_name": "SK hynix 新闻室"},
     "sources": [{"source_id": "skhynix_ir", "source_name": "SK hynix 新闻室", "tier": 0}],
     "divergences": []},
    {"event_id": "EV03", "title": "AMD Unveils Instinct MI400 Series", "segment": "设计",
     "published": "2026-08-07", "n_sources": 2, "n_unique_sources": 2,
     "verification": "conflict", "confidence": 55.0,
     "primary_source": {"source_id": "eetimes", "source_name": "EE Times"},
     "sources": [{"source_id": "eetimes", "source_name": "EE Times", "tier": 1},
                 {"source_id": "163_news", "source_name": "网易科技", "tier": 4}],
     "divergences": [{"a": "163_news", "b": "eetimes",
                      "a_claim": ["384GB"], "b_claim": ["432GB"],
                      "note": "关键数字不一致（GB）"}]},
]

GAP = {
    "cells": [
        {"segment": "设计", "type": "ir", "type_label": "公司一手(IR/法说会)",
         "actual": 5, "target": 1, "level": "充足", "source_ids": ["a", "b"]},
        {"segment": "EDA", "type": "academic", "type_label": "学术会议/论文",
         "actual": 0, "target": 1, "level": "严重缺口", "source_ids": []},
    ],
    "gaps": [
        {"segment": "EDA", "type": "academic", "type_label": "学术会议/论文",
         "actual": 0, "target": 1, "level": "严重缺口", "source_ids": []},
    ],
}

LEAK = {
    "meta": {"generated": "2026-08-09"},
    "candidates": [{
        "pair": ["EV09", "EV10"], "signals": {"digit": {"hit": True}, "entity_time": {"hit": True}},
        "candidate_anchors": ["存储超级周期"], "priority": "high",
        "reason": "共享实体 dram + 日期差 0 天",
    }],
    "stats": {"total_candidates": 1, "by_priority": {"high": 1}},
}

HEALTH = {
    "generated": "2026-08-09",
    "sources": [
        {"source_id": "sec_edgar", "source_name": "SEC EDGAR", "status": "ok",
         "avg_latency_ms": 691, "availability_7d": 1.0},
        {"source_id": "aihot", "source_name": "AIHOT 聚合 API", "status": "ok",
         "avg_latency_ms": 293, "availability_7d": 1.0},
    ],
    "global": {"raw_count": 19, "cleaned_count": 19, "discard_rate": 0.0,
               "fused_events": 11, "conflict_rate": 0.09, "gap_cells": 13},
}


def test_build_four_blocks():
    html = rv.build(FUSED, GAP, LEAK, HEALTH)
    assert 'class="ev-card"' in html
    assert "EV01" in html and "EV03" in html
    assert 'class="div-block"' in html          # 分歧高亮
    assert "384GB" in html and "432GB" in html   # 双方主张
    assert 'class="tbl cov"' in html             # 覆盖矩阵
    assert 'class="health-dots"' in html         # 健康状态点
    assert 'class="gap-item"' in html            # 缺口清单
    assert "严重缺口" in html
    assert "存储超级周期" in html                 # 漏聚锚词


def test_build_empty_data_degrades():
    html = rv.build(None, None, None, {})
    assert 'class="empty"' in html
    assert "暂无融合事件" in html
    assert "暂无漏聚候选" in html
    assert "暂无覆盖矩阵" in html
    assert "暂无缺口数据" in html


def test_build_from_real_products(tmp_path):
    """从真实产物可生成完整 HTML，四大块均存在。"""
    from multi_source.report_viz import _load_json, _load_health
    out = rv.run(tmp_path / "report.html")
    html = out.read_text(encoding="utf-8")
    assert out.exists()
    assert len(html) > 5000
    for pat in ('ev-card', 'cov', 'health-dots', 'gap-item'):
        assert pat in html
    fused = _load_json("fused_events.json")
    assert isinstance(fused, list) and len(fused) > 0
    health = _load_health()
    assert isinstance(health, dict)
