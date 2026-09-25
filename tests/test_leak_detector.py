#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_leak_detector.py —— 漏聚探测器（leak_detector）回归用例

2026-08-09 产出。覆盖：
  1. 真实样例：EV09/EV10（同一 Q2 DRAM 合约价事件被拆成两条 single_source）
     必须被检出（验收核心）
  2. digit 信号边界：区间 vs 点、差>10% 不命中、跨币种归一、
     body 百分比噪声不命中（百分比仅取 title）
  3. entity_time 边界：共享实体+时间窗、超窗不命中、unknown 放行
  4. jaccard：同语言近重复命中；跨语言对低但 OR 下由 digit 兜底
  5. 确定性 / 空输入 / build_pairs 只取单源
  6. 探测器不改 fusion 输出（11 事件不回归）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MS = ROOT / "scripts" / "multi_source"
sys.path.insert(0, str(MS))

import json  # noqa: E402

import fusion  # noqa: E402
import leak_detector as ld  # noqa: E402
from leak_detector import (build_pairs, detect, signal_digit,  # noqa: E402
                           signal_entity_plus_time, signal_jaccard)


def _mk(source_id, title, body="", published="2026-07-14", tier=3, segment="设计",
        source_name="s", type="news", url="http://x"):
    return {"source_id": source_id, "source_name": source_name, "tier": tier,
            "type": type, "segment": segment, "title": title, "url": url,
            "published": published, "body": body}


def _mk_event(event_id, source_id, title, published="2026-07-14", tier=3):
    return {"event_id": event_id, "n_sources": 1, "verification": "single_source",
            "title": title, "published": published, "confidence": 50.0,
            "sources": [{"source_id": source_id, "tier": tier, "title": title,
                         "published": published, "url": "http://x",
                         "source_name": "s", "type": "news"}]}


# ---------------------------------------------------------------- 真实样例
def test_real_leak_ev09_ev10_detected():
    """真实漏聚 EV09↔EV10 已修复（2026-08-09 迭代2 锚词回写）。

    回写前：TrendForce 53-58% ↔ 腾讯 55%（存储价格）被漏检为 high 候选。
    回写后：contractprice/q2/2q26 锚让双源合并进同一事件（EV07），
    leak_detector 候选应为 0——本测试从"检出漏聚"反转为"验证修复"。
    """
    cleaned = json.loads((MS / "data" / "cleaned_events.json").read_text(encoding="utf-8"))
    fused = json.loads((MS / "data" / "fused_events.json").read_text(encoding="utf-8"))
    report = detect(cleaned, fused)
    pairs = [c["pair"] for c in report["candidates"]]
    assert ["EV09", "EV10"] not in pairs and ["EV10", "EV09"] not in pairs
    # 双源确实已合并在同一事件（TrendForce + 腾讯 存储价格）
    merged = [e for e in fused if {"trendforce", "qq_news"} <= {s["source_id"] for s in e["sources"]}]
    assert len(merged) == 1
    assert merged[0]["verification"] == "verified"


def test_no_false_positive_ev08_ev10():
    """body 百分比噪声不误报：EV08（45.64% 股权比例）vs EV10（55% 涨幅）
    百分比仅取 title，二者标题无百分比 → 不应作为 digit 候选。"""
    cleaned = json.loads((MS / "data" / "cleaned_events.json").read_text(encoding="utf-8"))
    fused = json.loads((MS / "data" / "fused_events.json").read_text(encoding="utf-8"))
    report = detect(cleaned, fused)
    pairs = [tuple(c["pair"]) for c in report["candidates"]]
    assert ("EV08", "EV10") not in pairs and ("EV10", "EV08") not in pairs


# ---------------------------------------------------------------- digit 信号
def test_digit_interval_vs_point():
    a, b = _mk("a", "存储价格涨55%"), _mk("b", "DRAM contract prices up 53-58%")
    hit, detail = signal_digit(a, b)
    assert hit and detail["percent"] is not None


def test_digit_point_vs_point_close():
    a, b = _mk("a", "涨价 55%"), _mk("b", "涨幅 52%")
    hit, _ = signal_digit(a, b)
    assert hit  # 52*1.1=57.2 ≥ 55*0.9=49.5 → 相交


def test_digit_far_apart_no_hit():
    a, b = _mk("a", "涨价 55%"), _mk("b", "涨幅 70%")
    hit, _ = signal_digit(a, b)
    assert not hit  # 55*1.1=60.5 < 70*0.9=63 → 不相交


def test_digit_cross_currency_unit():
    a, b = _mk("a", "投资384亿美元"), _mk("b", "投资384亿元")
    hit, detail = signal_digit(a, b)
    assert hit and detail["unit"] == "亿"  # 亿美元/亿元 → 亿 归一


def test_digit_percent_title_only_ignores_body_noise():
    """百分比仅取 title：45.64%(body) vs 55%(title) 不命中。"""
    a = _mk("a", "概伦电子并购", body="收购45.64%股权 100%控股")
    b = _mk("b", "存储合约价上涨55%")
    hit, _ = signal_digit(a, b)
    assert not hit


def test_digit_bare_number_no_hit():
    """裸数字（日期/编号，无单位无%）不命中。"""
    a, b = _mk("a", "2026年 8月8日 会议"), _mk("b", "2026年 8月8日 大会")
    hit, _ = signal_digit(a, b)
    assert not hit


# ---------------------------------------------------------------- entity_time
def test_entity_time_shared_one_same_day():
    a, b = _mk("a", "SK hynix 扩产"), _mk("b", "SK海力士扩产")
    hit, detail = signal_entity_plus_time(a, b)
    assert hit and detail["published_diff_days"] == 0
    assert "skhynix" in detail["shared_entities"]


def test_entity_time_outside_window_no_hit():
    a = _mk("a", "SK hynix 扩产", published="2026-07-01")
    b = _mk("b", "SK海力士扩产", published="2026-07-07")
    hit, detail = signal_entity_plus_time(a, b)
    assert not hit and detail["published_diff_days"] == 6


def test_entity_time_unknown_date_pass():
    """unknown 日期不否决：信号不命中但 detail 记录 None（由其他信号兜底）。"""
    a = _mk("a", "SK hynix 扩产", published="unknown")
    b = _mk("b", "SK海力士扩产", published="2026-07-14")
    hit, detail = signal_entity_plus_time(a, b)
    assert not hit and detail["published_diff_days"] is None


def test_entity_time_no_shared_entity():
    a, b = _mk("a", "SK hynix 扩产"), _mk("b", "寒武纪 财报")
    hit, _ = signal_entity_plus_time(a, b)
    assert not hit


# ---------------------------------------------------------------- jaccard
def test_jaccard_same_language_near_dup():
    a = _mk("a", "SK海力士拟投384亿美元扩产 加码HBM与DRAM")
    b = _mk("b", "SK海力士拟投384亿美元扩产 加码HBM")
    hit, detail = signal_jaccard(a, b)
    assert hit and detail["jaccard"] >= 0.25


def test_jaccard_cross_language_low_but_digit_fallback():
    """跨语言对 Jaccard 低（<0.25），但 OR 组合下 digit 兜底命中。"""
    a = _mk("a", "DRAM Contract Prices Up 53-58% QoQ in 2Q26")
    b = _mk("b", "存储超级周期：Q2 DRAM合约价环比上涨55%")
    hit_j, detail_j = signal_jaccard(a, b)
    assert not hit_j and detail_j["jaccard"] < 0.25
    hit_d, _ = signal_digit(a, b)
    assert hit_d  # digit 兜底


def test_jaccard_disjoint():
    a, b = _mk("a", "寒武纪 2026 半年度报告"), _mk("b", "鼎龙 光刻胶 产能")
    hit, _ = signal_jaccard(a, b)
    assert not hit


# ---------------------------------------------------------------- token 化
def test_leak_tokens_cjk_ascii_boundary():
    """『DRAM合约价』在 CJK/ASCII 边界切分成 dram + 中文短语（无 jieba
    分词，中文内部粘连成短语是预期行为）。"""
    toks = ld._leak_tokens("Q2 DRAM合约价环比上涨55%")
    assert "dram" in toks
    assert any("合约价" in t for t in toks)


def test_leak_tokens_filters_noise():
    """非归一版滤掉带单位数字（384 是具体值不是锚词建议）。"""
    toks = ld._leak_tokens("投资384亿美元扩产", normalize=False)
    assert "384" not in toks
    assert not any(t.isdigit() for t in toks)
    assert any("亿美元" in t for t in toks)  # 单位词保留（可粘连）


# ---------------------------------------------------------------- 结构/确定性
def test_build_pairs_only_single_source_sorted():
    evs = [_mk_event("EV02", "b", "寒武纪", published="2026-07-14"),
           _mk_event("EV01", "a", "SK hynix", published="2026-07-14"),
           _mk_event("EV03", "c", "AMD", published="2026-07-14"),
           _mk_event("EV05", "d", "长电", published="2026-07-14")]
    evs[-1]["n_sources"] = 2  # 多源事件排除
    evs[-1]["verification"] = "verified"
    pairs = build_pairs(evs)
    assert len(pairs) == 3  # 3 个单源 → C(3,2)
    # 确定性：按 event_id 排序，pair 内也排序
    assert all(p[0]["event_id"] < p[1]["event_id"] for p in pairs)
    ids = [tuple(p[i]["event_id"] for i in (0, 1)) for p in pairs]
    assert ids == [("EV01", "EV02"), ("EV01", "EV03"), ("EV02", "EV03")]


def test_detect_empty_input():
    report = detect([], [])
    assert report["candidates"] == []
    assert report["stats"]["total_candidates"] == 0


def test_detect_deterministic():
    cleaned = json.loads((MS / "data" / "cleaned_events.json").read_text(encoding="utf-8"))
    fused = json.loads((MS / "data" / "fused_events.json").read_text(encoding="utf-8"))
    r1, r2 = detect(cleaned, fused), detect(cleaned, fused)
    assert r1 == r2


def test_detect_requires_two_signals_or_rule():
    """仅 entity_time 命中（无数字）→ medium 候选。"""
    a = _mk("a", "SK hynix 扩产", published="2026-07-14")
    b = _mk("b", "SK海力士扩产", published="2026-07-15")
    cleaned = [a, b]
    fused = [_mk_event("EV01", "a", "SK hynix 扩产", "2026-07-14"),
             _mk_event("EV02", "b", "SK海力士扩产", "2026-07-15")]
    report = detect(cleaned, fused)
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["priority"] == "medium"


# ---------------------------------------------------------------- 不污染 fusion
def test_fusion_output_unchanged():
    """探测器只读 fused 产物，fusion 输出仍 10 事件（防回归）。

    2026-08-09 迭代2 锚词回写后：存储价格双源合并，事件 11→10、
    verified 6→7（见 test_fusion_adversarial.py::test_real_data_regression）。"""
    cleaned = json.loads((MS / "data" / "cleaned_events.json").read_text(encoding="utf-8"))
    evs = fusion.fuse(cleaned)
    assert len(evs) == 10
    assert sum(1 for e in evs if e["verification"] == "verified") == 7


def test_main_runs():
    """main() 可运行并产出报告文件。"""
    assert ld.main() == 0
    assert (MS / "data" / "leak_report.json").exists()
    assert (MS / "data" / "leak_report.md").exists()
