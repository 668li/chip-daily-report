#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests.test_gate — 迭代3 选择性纳入门禁 + 新数据源回归用例。

覆盖：
  C1 新源适配器（DigiTimes / CNBC / SemiAnalysis 子类注册与字段）
  C2 gate G1 置信度阈值（低置信度被拒）
  C3 gate G5 关键词黑白名单（off_topic / irrelevant 被拒）
  C4 gate G4 环节配额（超额环节按置信度截断）
  C5 gate G6 数量上限（top_n 截断）
  C6 gate G2/G3 降级标记（stale / single_low_tier 不剔除只标记）
  C7 gate fail-soft（空输入 → 空候选；坏字段 → 跳过）
  C8 gate_report.json 输出结构契约
全部用例零真实网络依赖（内置样例）。
"""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "multi_source"))

import collector
import gate as gate_mod


# ---------------- C1: 新源适配器 ----------------

def test_new_rss_subclasses_registered():
    """迭代3 新源子类：id/tier/feed 正确。"""
    cn = collector.CNBCCollector()
    sa = collector.SemiAnalysisCollector()
    assert cn.source_id == "cnbc" and cn.tier == 1
    assert "cnbc.com" in cn.feed_url
    assert sa.source_id == "semianalysis" and sa.tier == 1
    assert sa.feed_url == "https://semianalysis.com/feed/"


def test_digitimes_not_in_online_registry():
    """DigiTimes 实测反爬（HTML 壳/403）未接入在线采集器，避免采集器假阳性。"""
    assert not hasattr(collector, "DigiTimesCollector")


def test_online_registry_includes_new_sources():
    """online 注册表 ≥6 源且包含迭代3 新源（老源不丢）。"""
    ids = {c.source_id for c in collector.ONLINE_COLLECTORS}
    assert {"sec_edgar", "aihot", "semiengineering", "eetimes"} <= ids
    assert {"cnbc", "semianalysis"} <= ids


def test_probe_endpoints_include_new_sources():
    """探针端点表包含新源（health_check 复用）。"""
    ids = {sid for sid, _, _ in collector.PROBE_ENDPOINTS}
    assert {"cnbc", "semianalysis"} <= ids


# ---------------- C2: G1 置信度阈值 ----------------

def _mk_ev(eid="EV01", title="台积电 2nm 产能爬坡", conf=80.0, seg="制造",
           pub="2026-08-14", ver="verified", n=2, tier=1):
    return {
        "event_id": eid, "title": title, "segment": seg, "published": pub,
        "confidence": conf, "verification": ver, "n_sources": n,
        "primary_source": {"url": f"https://example.com/{eid}"},
        "sources": [{"tier": tier}],
    }


def test_g1_low_confidence_rejected():
    evs = [_mk_ev("EV01", conf=88.0), _mk_ev("EV02", conf=45.0)]
    rep = gate_mod.gate(evs, conf_min=60.0, top_n=10)
    assert rep["stats"]["candidates"] == 1
    assert rep["stats"]["rejected"] == 1
    assert rep["rejected"][0]["event_id"] == "EV02"
    assert rep["rejected"][0]["reason"] == "low_confidence"


# ---------------- C3: G5 关键词黑白名单 ----------------

def test_g5_off_topic_rejected():
    ev = _mk_ev("EV01", title="明星八卦娱乐新闻汇总", conf=90.0)
    rep = gate_mod.gate([ev], top_n=10)
    assert rep["stats"]["candidates"] == 0
    assert rep["rejected"][0]["reason"] == "off_topic"


def test_g5_irrelevant_rejected():
    ev = _mk_ev("EV01", title="今天天气不错适合出门散步", conf=90.0)
    rep = gate_mod.gate([ev], top_n=10)
    assert rep["stats"]["candidates"] == 0
    assert rep["rejected"][0]["reason"] == "irrelevant"


def test_g5_include_keyword_passes():
    for title in ["台积电 2nm 良率提升", "英伟达发布新一代 GPU",
                  "中芯国际 Q2 营收超预期", "国产 EDA 并购整合加速",
                  "SK 海力士 HBM4 量产出货"]:
        rep = gate_mod.gate([_mk_ev("EV01", title=title)], top_n=10)
        assert rep["stats"]["candidates"] == 1, title


def test_g5_short_ascii_word_boundary():
    """短英文词（ai/sic/arm）必须词边界匹配：防 'again'/'basic' 等子串误命中。

    2026-08-15 端到端实测回归：CNBC 'New super car bubble' 等新闻因标题含
    'ai' 子串（…Massive market rotation in AI…）之外的误命中混入候选池。
    """
    # 'again' 含 'ai' 子串 → 不应命中（纯噪音标题，无芯片词）；'AI 芯片' 词边界 → 应命中
    rep = gate_mod.gate([_mk_ev("EV01", title="Market Rotation Again: Index Funds Rebalance")], top_n=10)
    assert rep["stats"]["candidates"] == 0
    assert rep["rejected"][0]["reason"] == "irrelevant"
    rep = gate_mod.gate([_mk_ev("EV01", title="AI 芯片需求强劲 NVIDIA 受益")], top_n=10)
    assert rep["stats"]["candidates"] == 1


def test_g4_core_segments_only_quota():
    """G4 配额只对核心 5 环节计数；综合/未知作横切线索不占配额。"""
    evs = [_mk_ev(f"EV{i:02d}", seg="综合", conf=80 - i) for i in range(10)]
    rep = gate_mod.gate(evs, max_per_segment=3, top_n=10)
    # 10 条综合全部保留（不占配额），仅 top_n 生效
    assert rep["stats"]["candidates"] == 10


# ---------------- C4: G4 环节配额 ----------------

def test_g4_segment_quota():
    evs = [_mk_ev(f"EV{i:02d}", seg="制造", conf=95 - i * 5) for i in range(8)]
    rep = gate_mod.gate(evs, max_per_segment=3, top_n=10)
    cands = [e for e in rep["candidates"] if e["segment"] == "制造"]
    assert len(cands) == 3
    # 保留的是置信度最高的 3 条
    assert [c["confidence"] for c in cands] == [95.0, 90.0, 85.0]
    quota_rejected = [r for r in rep["rejected"] if r["reason"] == "segment_quota"]
    assert len(quota_rejected) == 5


# ---------------- C5: G6 数量上限 ----------------

def test_g6_top_n_cap():
    evs = [_mk_ev(f"EV{i:02d}", seg="制造" if i % 2 else "设计",
                  conf=80 - i) for i in range(10)]
    rep = gate_mod.gate(evs, max_per_segment=10, top_n=4)
    assert rep["stats"]["candidates"] == 4
    assert len([r for r in rep["rejected"] if r["reason"] == "top_n_cap"]) == 6


# ---------------- C6: G2/G3 降级标记（不剔除） ----------------

def test_g2_stale_flag_not_rejected():
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=30)).isoformat()
    ev = _mk_ev("EV01", pub=old, conf=85.0)
    rep = gate_mod.gate([ev], stale_days=7, top_n=10)
    assert rep["stats"]["candidates"] == 1
    assert "stale" in rep["candidates"][0]["flags"]


def test_g3_single_low_tier_flag_not_rejected():
    ev = _mk_ev("EV01", ver="single_source", n=1, tier=4)
    rep = gate_mod.gate([ev], top_n=10)
    assert rep["stats"]["candidates"] == 1
    assert "single_low_tier" in rep["candidates"][0]["flags"]


def test_review_tag_exempts_stale():
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=15)).isoformat()
    ev = _mk_ev("EV01", title="[回顾] 三星发布 zHBM 架构", pub=old, conf=85.0)
    rep = gate_mod.gate([ev], stale_days=7, top_n=10)
    assert "stale" not in rep["candidates"][0]["flags"]


# ---------------- C7: fail-soft ----------------

def test_gate_empty_input():
    rep = gate_mod.gate([])
    assert rep["stats"]["raw"] == 0
    assert rep["stats"]["candidates"] == 0
    assert rep["stats"]["rejected"] == 0


def test_gate_bad_items_skipped():
    evs = [None, {}, {"title": ""}, _mk_ev("EV01", conf=85.0)]
    rep = gate_mod.gate(evs, top_n=10)
    assert rep["stats"]["candidates"] == 1


# ---------------- C8: 输出契约 ----------------

def test_report_schema():
    evs = [_mk_ev("EV01", conf=85.0), _mk_ev("EV02", conf=30.0)]
    rep = gate_mod.gate(evs, top_n=10)
    assert {"generated", "rules", "stats", "candidates", "rejected"} <= set(rep)
    assert rep["stats"]["raw"] == 2
    assert isinstance(rep["candidates"][0]["flags"], list)
    assert "low_confidence" in rep["stats"]["by_reason"]


def test_main_writes_file(tmp_path):
    """CLI 入口：写 gate_report.json 且可反序列化。"""
    evs = [_mk_ev("EV01", conf=85.0), _mk_ev("EV02", conf=30.0)]
    events_file = tmp_path / "events.json"
    events_file.write_text(json.dumps(evs, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "gate_report.json"
    sys.argv = ["gate.py", "--events", str(events_file), "--out", str(out)]
    rc = gate_mod.main()
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["stats"]["candidates"] == 1


# ---------------- C9: prepare_candidates 一键流水线 ----------------

def test_prepare_candidates_runs_and_writes(tmp_path, monkeypatch):
    """一键流水线：真实调用 prepare_candidates.run()，输出契约正确。

    用 monkeypatch 把 collector.collect 替换为离线样例（零网络依赖），
    验证整条链（采集→清洗→融合→门禁→落盘）可跑通且输出 gate 契约。
    """
    import prepare_candidates as pc

    calls = {}

    def fake_collect(mode="offline", scope=None):
        calls["mode"] = mode
        return collector.load_offline(scope or {})

    monkeypatch.setattr(pc.collector, "collect", fake_collect)
    out = tmp_path / "gate_report.json"
    result = pc.run(conf_min=55.0, top_n=24, max_per_segment=6,
                    aihot_queries="半导体,芯片", aihot_limit=4, out_file=out)
    assert result["ok"] is True
    assert calls["mode"] == "online"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {"generated", "stats", "candidates", "rejected"} <= set(data)
    # 离线样例 10 事件 → 有候选（置信度≥55 的事件进入）
    assert data["stats"]["raw"] > 0
    assert all(isinstance(c.get("flags"), list) for c in data["candidates"])


def test_prepare_candidates_fail_soft(tmp_path, monkeypatch):
    """流水线任一环节异常 → 输出空候选 + error 字段，不抛异常（fail-soft）。"""
    import prepare_candidates as pc

    def boom_collect(mode="offline", scope=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(pc.collector, "collect", boom_collect)
    out = tmp_path / "gate_report.json"
    result = pc.run(out_file=out)
    assert result["ok"] is False
    assert "network down" in (result["error"] or "")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["stats"]["candidates"] == 0
    assert "error" in data
