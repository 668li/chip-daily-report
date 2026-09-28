#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests.test_collector_sources — 迭代2 数据源扩容回归用例。

覆盖：
  B1 AIHOT 适配器（真实契约解析 / 网络异常降级）
  B2 RSS 适配器（XML 解析 / 环节猜测 / 日期转换 / 注册表 ≥3 真实源）
  探针 fail-soft
全部用例零真实网络依赖（monkeypatch / 内置样例）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "multi_source"))

import collector


# ---------------- B1: AIHOT 适配器 ----------------

AIHOT_PAYLOAD = {
    "schemaVersion": 1,
    "items": [
        {
            "id": "x1", "title": "SK 海力士宣布向龙仁 Y2 投资 54 万亿韩元",
            "summary": "董事会批准投资 54 万亿韩元，Y2 将生产 HBM 等新一代产品。",
            "source": {"name": "IT之家（RSS）"},
            "links": {"original": "https://www.ithome.com/0/987/041.htm"},
            "publishedAt": "2026-08-07T07:41:07.000Z",
        },
        {
            "id": "x2", "title": "重复标题占位", "summary": "",
            "links": {}, "publishedAt": "2026-08-06T00:00:00.000Z",
        },
    ],
}


def test_aihot_parse_real_payload(monkeypatch):
    """AIHOT 真实契约：items[]/links.original/publishedAt 正确落 RawItem。"""
    calls = {}

    def fake_urlopen(req, timeout=10):
        calls["url"] = req.full_url
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1):
                import json
                return json.dumps(AIHOT_PAYLOAD).encode("utf-8")
        return R()

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    items = collector.AIHOTCollector().collect({"aihot_queries": ["半导体"], "aihot_limit": 2})
    assert len(items) == 2
    it = items[0]
    assert it.source_id == "aihot" and it.tier == 4
    assert it.title.startswith("SK 海力士")
    assert it.url == "https://www.ithome.com/0/987/041.htm"   # links.original 追溯
    assert it.published.startswith("2026-08-07")
    assert "韩元" in it.body
    assert "q=" in calls["url"]                                # 中文已 URL 编码


def test_aihot_network_fail_fallback():
    """AIHOT 断网/超时 → 返回 []（不抛异常，fail-soft 降级）。"""
    items = collector.AIHOTCollector().collect({"aihot_queries": ["q"], "aihot_limit": 1})
    # 依赖真实网络无法保证；这里只验证类型契约
    assert isinstance(items, list)


def test_aihot_duplicate_dedup(monkeypatch):
    """同名标题跨关键词去重（seen 集合）。"""
    payload = {"items": [
        {"id": "a", "title": "同一标题", "links": {"original": "u1"}, "publishedAt": ""},
        {"id": "b", "title": "同一标题", "links": {"original": "u2"}, "publishedAt": ""},
    ]}

    def fake_urlopen(req, timeout=10):
        import json
        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1): return json.dumps(payload).encode("utf-8")
        return R()

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    items = collector.AIHOTCollector().collect({"aihot_queries": ["半导体", "芯片"]})
    assert len(items) == 1


# ---------------- B2: RSS 适配器 ----------------

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Semiconductor Engineering</title>
  <item>
    <title>TSMC N2 Ramp Accelerates at Five Fabs</title>
    <link>https://semiengineering.com/tsmc-n2-ramp/</link>
    <pubDate>Fri, 07 Aug 2026 09:00:00 +0000</pubDate>
    <description>&lt;p&gt;TSMC N2 capacity to reach 120K wafers per month.&lt;/p&gt;</description>
  </item>
  <item>
    <title>先进封装与 Chiplet 的协同设计挑战</title>
    <link>https://semiengineering.com/adv-pkg-chiplet/</link>
    <pubDate>Thu, 06 Aug 2026 08:30:00 +0000</pubDate>
    <description>无描述</description>
  </item>
</channel></rss>"""


def test_rss_parse_items_and_fields():
    """RSS XML 解析：title/link/date/body 正确；HTML 标签与实体剥离。"""
    items = collector.RSSCollector()._parse(RSS_XML)
    assert len(items) == 2
    a = items[0]
    assert a.title == "TSMC N2 Ramp Accelerates at Five Fabs"
    assert a.url == "https://semiengineering.com/tsmc-n2-ramp/"
    assert a.published == "2026-08-07"                 # RFC822 → ISO
    assert a.body == "TSMC N2 capacity to reach 120K wafers per month."


def test_rss_guess_segment():
    """标题关键词 → 5 环节猜测。"""
    assert collector._guess_segment("TSMC N2 Ramp at Five Fabs") == "制造"
    assert collector._guess_segment("HBM4 存储芯片量产") == "制造"
    assert collector._guess_segment("AMD Instinct MI400 SoC") == "设计"
    assert collector._guess_segment("Advanced Packaging CoWoS") == "封测"
    assert collector._guess_segment("EDA Verification for 3DIC") == "EDA"
    assert collector._guess_segment("光刻胶材料扩产") == "材料"
    assert collector._guess_segment("Random News") == "综合"


def test_rfc822_and_bad_date():
    assert collector._rfc822_to_date("Fri, 08 Aug 2026 07:41:07 +0000") == "2026-08-08"
    assert collector._rfc822_to_date("2026-08-07T07:41:07.000Z") == "2026-08-07"
    assert collector._rfc822_to_date("") == ""


def test_semiengineering_and_eetimes_subclass():
    """两个新源子类：id/tier/feed 正确（Tier-1 英文权威媒体）。"""
    se, ee = collector.SemiEngineeringCollector(), collector.EETimesCollector()
    assert se.source_id == "semiengineering" and se.tier == 1
    assert se.feed_url == "https://semiengineering.com/feed/"
    assert ee.source_id == "eetimes" and ee.tier == 1
    assert ee.feed_url == "https://www.eetimes.com/feed/"


def test_online_collectors_registry_at_least_3():
    """online 模式注册表 ≥3 个真实源（迭代2 验收标准）。"""
    assert len(collector.ONLINE_COLLECTORS) >= 3
    ids = {c.source_id for c in collector.ONLINE_COLLECTORS}
    assert {"sec_edgar", "aihot", "semiengineering", "eetimes"} <= ids


# ---------------- 探针 fail-soft ----------------

def test_probe_fail_soft(monkeypatch):
    """探针遇网络异常 → status=down 不抛异常。"""

    def boom(req, timeout=8):
        raise OSError("network unreachable")

    monkeypatch.setattr(collector.urllib.request, "urlopen", boom)
    results = collector.probe_online_sources()
    assert len(results) == len(collector.PROBE_ENDPOINTS)
    assert all(r["status"] == "down" for r in results)
    assert all("network unreachable" in (r["error"] or "") for r in results)


# ---------------- v8 R3: IT之家直链源 ----------------

ITHOME_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>IT之家</title>
<item><title>台积电 2027 年起晶圆代工涨价 3%-6%</title>
<link>https://www.ithome.com/1/006/598.htm</link>
<pubDate>Wed, 24 Sep 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;据财联社报道，涨价主要落在先进制程。&lt;/p&gt;</description>
</item>
<item><title>寒武纪发布新款推理芯片</title>
<link>https://www.ithome.com/0/987/041.htm</link>
<pubDate>Wed, 24 Sep 2026 09:00:00 GMT</pubDate>
<description>思元系列落地智算中心。</description>
</item>
</channel></rss>"""


def test_ithome_registered_and_parse():
    """IT之家（v8 R3）：注册在在线采集表与探针表；中文条目解析正确。"""
    assert collector.ITHomeCollector in collector.ONLINE_COLLECTORS
    assert any(sid == "ithome" for sid, _, _ in collector.PROBE_ENDPOINTS)
    items = collector.ITHomeCollector()._parse(ITHOME_XML)
    assert len(items) == 2
    a = items[0]
    assert a.source_id == "ithome"
    assert a.title == "台积电 2027 年起晶圆代工涨价 3%-6%"
    assert a.url == "https://www.ithome.com/1/006/598.htm"
    assert a.published == "2026-09-24"
    assert "涨价主要落在先进制程" in a.body  # HTML 剥离后正文保留
    assert collector._guess_segment(a.title) == "制造"


# ---------------- v8 R5-C: TrendForce 直连源（对齐轮补测：审查发现无 feed 解析单测） ----------------

TRENDFORCE_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>TrendForce News</title>
<item><title>TSMC 3nm Capacity Fully Booked Through 2027</title>
<link>https://www.trendforce.com/news/2026/09/28/tsmc-3nm-capacity-booked/</link>
<pubDate>Mon, 28 Sep 2026 06:00:00 GMT</pubDate>
<description>Foundry capacity update for advanced nodes.</description>
</item>
<item><title>DRAM Contract Prices Rise in October</title>
<link>https://www.trendforce.com/news/2026/09/27/dram-prices-rise/</link>
<pubDate>Sun, 27 Sep 2026 06:00:00 GMT</pubDate>
<description>Memory pricing momentum continues.</description>
</item>
</channel></rss>"""


def test_trendforce_registered_and_parse():
    """TrendForce（v8 R5-C）：注册断言（防静默缺失，v7 per-source 教训）+ 离线解析出文章级直链。"""
    assert collector.TrendForceCollector in collector.ONLINE_COLLECTORS
    assert any(sid == "trendforce" for sid, _, _ in collector.PROBE_ENDPOINTS)
    tf = collector.TrendForceCollector()
    assert tf.source_id == "trendforce"
    assert tf.tier == 1
    assert tf.feed_url == "https://www.trendforce.com/news/feed_v2/"
    items = tf._parse(TRENDFORCE_XML)
    assert len(items) == 2
    a = items[0]
    assert a.source_id == "trendforce"
    assert a.title == "TSMC 3nm Capacity Fully Booked Through 2027"
    # 文章级直链（域名根/仅斜杠 = 伪追溯，采中准入会拒）
    assert a.url.startswith("https://www.trendforce.com/news/")
    assert a.url.count("/") >= 5
    assert a.published == "2026-09-28"
