#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_fusion_adversarial.py —— multi_source.fusion 对抗回归用例

2026-08-09 对抗式审查产出：对 fusion.py 的聚类/分歧检测/时效/日期处理
进行攻击性测试，固化以下修复：
  T1 同源多条保留最新版（原实现保留最旧，注释与行为相反）
  T2 同义词前置归一（sk hynix/SK海力士 变体才能命中 skhynix 锚）
  T3 分歧检测 shared 数字 continue 漏报 78亿 vs 58亿
  T4 年份噪声 2026 共享漏报 59.96亿 vs 55亿；细分数字/不同单位/约数不误报
  T5 空输入（规则 X12 节假日 0 条合法）不除零崩溃
  T6 White House 负面排除（house 锚不误命白宫新闻）
  T7 published=unknown 不劫持组首/主条目/事件日期
  T7b _freshness 基准动态化（原硬编码 2026-08-08，定时任务时效分冻结）
  T8 ASCII 短锚词边界匹配（n2≠N2X、2nm≠0.7nm、y2≠y2k）
  T9 MATCH Act 中英双源聚合回归
"""
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MS = ROOT / "scripts" / "multi_source"
sys.path.insert(0, str(MS))

import fusion  # noqa: E402
from fusion import (_detect_divergence, _freshness, cluster, extract_entities,  # noqa: E402
                    fuse)


def _mk(source_id, title, body="", published="2026-08-08", tier=3, segment="设计",
        source_name="s", type="news", url="http://x"):
    return {"source_id": source_id, "source_name": source_name, "tier": tier,
            "type": type, "segment": segment, "title": title, "url": url,
            "published": published, "body": body}


def _ents(text):
    e = extract_entities(text)
    return e["company"] | e["event"] | e["generic"]


def test_t1_same_source_keep_latest():
    """同一源多条共享实体进同组后，应保留最新版而非最旧版。"""
    items = [_mk("A", "SK hynix 扩产 HBM", body="旧版", published="2026-08-08"),
             _mk("A", "SK hynix 扩产 HBM 加码", body="新版", published="2026-08-09"),
             _mk("B", "SK hynix 扩产 HBM 详情", body="B", published="2026-08-09")]
    evs = fuse(items)
    kept = [s for e in evs if e["n_sources"] == 2
            for s in e["sources"] if s["source_id"] == "A"]
    assert kept and kept[0]["title"] == "SK hynix 扩产 HBM 加码"


def test_t2_synonym_anchor_variants():
    """SK hynix / SK海力士（无通用词）靠公司锚聚合（前置归一修复）。"""
    sa = _ents("SK hynix 公布扩产计划")
    sb = _ents("SK海力士公布扩产计划")
    assert "skhynix" in sa and "skhynix" in sb
    assert len(sa & sb) >= 2


def test_t3_shared_number_no_longer_skips_conflict():
    """两源共享 12万片 但 78亿 vs 58亿 冲突，必须报出。"""
    g = [_mk("A", "t", body="投资78亿元 月产能12万片"),
         _mk("B", "t", body="投资58亿元 月产能12万片")]
    d = _detect_divergence(g)
    assert len(d) == 1 and "亿" in d[0]["note"]


def test_t4_year_noise_no_longer_skips_conflict():
    """两源共享年份 2026，59.96亿 vs 55亿 冲突必须报出。"""
    g = [_mk("A", "t", body="2026年营收59.96亿元"),
         _mk("B", "t", body="2026年营收55亿元")]
    d = _detect_divergence(g)
    assert len(d) == 1


def test_t4b_sub_metric_shared_value_no_false_positive():
    """A 含 384亿+78亿（细分），B 只有 384亿 → 共享值存在，不误报。"""
    g = [_mk("A", "t", body="总投资384亿美元 其中HBM产线78亿"),
         _mk("B", "t", body="总投资384亿美元")]
    assert _detect_divergence(g) == []


def test_t4c_different_unit_no_false_positive():
    """12万片 vs 330吨（吨不在单位组被忽略）→ 不误报。"""
    g = [_mk("A", "t", body="月产能12万片"),
         _mk("B", "t", body="月产能12万片 另有光刻胶330吨")]
    assert _detect_divergence(g) == []


def test_t4d_soft_number_skipped():
    """约78亿（软词）vs 58亿 → 不报。"""
    g = [_mk("A", "t", body="投资约78亿元"), _mk("B", "t", body="投资58亿元")]
    assert _detect_divergence(g) == []


def test_t5_empty_input_no_crash():
    """空输入（规则 X12 节假日 0 条合法）不崩。"""
    assert fuse([]) == []


def test_t6_white_house_negative_exclusion():
    """house 锚不误命 White House；中文众议院仍命中。"""
    assert "house" not in _ents("White House plans new chip export curbs")
    assert "house" in _ents("美众议院通过芯片设备多边管制法案")


def test_t7_unknown_date_not_hijacking():
    """published=unknown 不劫持组首/主条目/事件日期。"""
    items = [_mk("A", "未知日期事件", published="unknown", tier=3),
             _mk("B", "正常日期事件", published="2026-08-01", tier=3),
             _mk("C", "正常日期事件 2", published="2026-08-02", tier=3)]
    groups = cluster(items)
    evs = fuse(items)
    assert groups[0][0]["published"] != "unknown"
    assert evs[0]["title"] != "未知日期事件"
    assert evs[0]["published"] == "2026-08-02"


def test_t7b_freshness_dynamic_baseline():
    """时效基准随运行日动态变化（原硬编码 2026-08-08 冻结）。"""
    assert _freshness("2026-08-09", today=datetime.date(2026, 8, 9)) == 1.0
    # 23 天后同一条目应衰减到 0.7（硬编码基准时恒为 1.0）
    assert _freshness("2026-08-09", today=datetime.date(2026, 9, 1)) == 0.7


def test_t8_short_anchor_word_boundary():
    """ASCII 短锚词边界匹配：防子串假阳性。"""
    assert "n2" not in _ents("Boeing N2X variant")
    assert "n2" in _ents("TSMC N2 工艺")
    assert "2nm" not in _ents("0.7nm 成熟制程")
    assert "7nm" not in _ents("0.7nm 成熟制程")
    assert "y2" not in _ents("Y2K bug fix")
    assert "ipo" in _ents("寒武纪 IPO 上市")


def test_t9_match_act_bilingual_regression():
    """MATCH Act 中英双源仍聚合（前置归一+house/foreignaffairs 锚）。"""
    items = [_mk("a", "MATCH Act: House Foreign Affairs Committee Passes 36-8"),
             _mk("b", "美众议院外交事务委员会36:8通过芯片设备多边管制法案")]
    evs = fuse(items)
    assert len(evs) == 1 and evs[0]["n_sources"] == 2


def test_real_data_regression():
    """真实数据（2026-08-08 日报 19 条）回归：10 事件 / 7 verified 无回归。

    2026-08-09 迭代2 锚词回写（contractprice/q2/2q26）后：存储价格双源
    （TrendForce↔腾讯）由漏聚变合并，事件 11→10、verified 6→7。"""
    import json
    cleaned = json.loads((MS / "data" / "cleaned_events.json").read_text(encoding="utf-8"))
    evs = fuse(cleaned)
    assert len(evs) == 10
    assert sum(1 for e in evs if e["verification"] == "verified") == 7
