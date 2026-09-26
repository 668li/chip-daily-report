#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests.test_discover — 自主源发现层 v1 回归（全离线、零真实网络）。

覆盖：
  D1  gnews 出版方域名提取（<source url> 标签样例）
  D2  首页 link rel=alternate feed 发现
  D3  路径清单兜底发现
  D4  HTML 反爬壳拒绝（AnandTech 200+HTML 陷阱）
  D5  feed 合法性（无条目拒 / 正常过）
  D6  相关性阈值（≥3 关键词 且 ≥2 条目命中才过，不够要拒）
  D7  dc:date（Nikkei RDF）日期解析
  D8  生命周期退避数学（30min*2^n 指数、封顶 7 天）
  D9  连续 3 败转 frozen
  D10 trial 连续 2 次过转 active（candidate→trial→active 全链）
  D11 _assert_safe_url 拒 http / 拒私网与回环 IP（monkeypatch getaddrinfo）
  D12 collector._dynamic_hosts 从 tmp 状态文件正确合并白名单
  D13 动态 RSS 采集器用 state 里的源实例化并解析 fixture XML
  D14 rescore 模式全池复判（确定性失败降级 / 瞬时失败不动 / 通过保留）
  附加：状态文件原子写回与 fail-soft、known 域过滤、collector 侧
       GoogleNews publisher_domain / RDF+dc:date / 巨潮 GBK / newsnow 代理回退

纪律：状态文件操作全部走 tmp_path；网络点全部 monkeypatch；
     mock urlopen 的桩必须带 def read(self, n=-1)。
"""
import json
import sys
import urllib.error as urllib_error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "multi_source"))

import collector
import discover


# ---------------- fixtures（内联字符串，零网络） ----------------

GNEWS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>台积电 2nm 量产提速 - 科技新报</title>
    <link>https://news.google.com/rss/articles/abc1</link>
    <source url="https://technews.tw">科技新报</source>
    <pubDate>Fri, 25 Sep 2026 08:00:00 +0000</pubDate>
  </item>
  <item>
    <title>TSMC N2 output ramps - Tom's Hardware</title>
    <link>https://news.google.com/rss/articles/abc2</link>
    <source url="https://www.tomshardware.com">Tom's Hardware</source>
    <pubDate>Fri, 25 Sep 2026 07:00:00 +0000</pubDate>
  </item>
  <item>
    <title>more chip news - Tom's Hardware</title>
    <link>https://news.google.com/rss/articles/abc3</link>
    <source url="https://www.tomshardware.com">Tom's Hardware</source>
  </item>
</channel></rss>"""

HTML_HOME = """<!doctype html><html><head>
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
<link rel="alternate" type="application/atom+xml" href="https://demo.example.com/atom.xml">
<link rel="stylesheet" href="/style.css">
</head><body>hello</body></html>"""

# 条目刻意命中 ≥3 个不同关键词 × ≥2 条目（过相关性门槛）
CHIP_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>DeadBlog chip news</title>
<item><title>TSMC wafer fab expansion for semiconductor supply</title>
<link>https://deadblog.example.com/a</link>
<pubDate>Thu, 24 Sep 2026 10:00:00 +0000</pubDate>
<description>chip fab foundry wafer semiconductor capacity</description></item>
<item><title>NVIDIA HBM memory partner rolls out advanced packaging</title>
<link>https://deadblog.example.com/b</link>
<pubDate>Fri, 25 Sep 2026 09:00:00 +0000</pubDate>
<description>nvidia hbm packaging chiplet asml litho</description></item>
</channel></rss>"""

# Nikkei RDF 形态：命名空间条目 + dc:date
NIKKEI_RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Nikkei Asia</title></channel>
<item rdf:about="x"><title>TSMC chip orders jump</title>
<link>https://asia.nikkei.com/a</link>
<dc:date>2026-09-25T09:30:00+09:00</dc:date>
<description>semiconductor wafer foundry</description></item>
</rdf:RDF>"""


def _pass_result(domain):
    """构造一条探测通过的标准结果。"""
    return {"domain": domain, "ok": True, "relevant": True,
            "feed_url": f"https://{domain}/feed", "homepage": f"https://{domain}/",
            "discovered_via": "path_list",
            "score": {"kw_hits": 8, "entry_hits": 3},
            "last_entry_date": "2026-09-25",
            "evidence": {"http_ok": True, "entry_count": 5, "sample_titles": ["t"]}}


# ---------------- D1: gnews 出版方域名提取 ----------------

def test_gnews_publisher_domain_extraction(monkeypatch):
    """条目 <source url=...> → 出版方域名计频；www 剥离归一；样本标题保留。"""

    def fake_fetch(url, timeout=12, no_proxy=False):
        assert url.startswith("https://news.google.com/rss/search?")
        assert "hl=zh-CN" in url and "gl=CN" in url and "ceid=CN:zh-Hans" in url
        return GNEWS_XML.encode("utf-8")

    monkeypatch.setattr(discover, "_fetch", fake_fetch)
    monkeypatch.setattr(discover, "_GNEWS_INTERVAL", 0.0)
    out = discover.gnews_domains(["(半导体 OR 芯片) when:7d"], "zh-CN")
    assert out["technews.tw"]["hits"] == 1
    assert out["tomshardware.com"]["hits"] == 2          # www. 剥离后合并计频
    assert any("台积电" in t for t in out["technews.tw"]["sample_titles"])


# ---------------- D2/D3: feed 自动发现 ----------------

def test_homepage_link_tag_discovery():
    """首页 <link rel=alternate type=rss/atom+xml> href → 绝对 https URL。"""
    links = discover.feed_links_from_html(HTML_HOME, "https://demo.example.com/")
    assert "https://demo.example.com/feed.xml" in links
    assert "https://demo.example.com/atom.xml" in links
    assert len(links) == 2                                # stylesheet 不算


def test_feed_path_fallback_discovery(monkeypatch):
    """首页抓取失败 → 常见路径清单兜底发现 /rss。"""

    def fake_fetch(url, timeout=12, no_proxy=False):
        if url.rstrip("/") == "https://deadblog.example.com":
            raise OSError("homepage blocked")
        if url == "https://deadblog.example.com/rss":
            return CHIP_FEED.encode("utf-8")
        raise OSError(f"404 {url}")

    monkeypatch.setattr(discover, "_fetch", fake_fetch)
    res = discover.probe_domain("deadblog.example.com")
    assert res["ok"] is True
    assert res["feed_url"] == "https://deadblog.example.com/rss"
    assert res["discovered_via"] == "path_list"
    assert res["relevant"] is True                        # 6 关键词 × 2 条目
    assert res["evidence"]["entry_count"] == 2


# ---------------- D4/D5: feed 合法性 ----------------

def test_html_shell_rejected(monkeypatch):
    """AnandTech 陷阱：HTTP 200 但内容是 HTML 壳 → 拒绝。"""

    def fake_fetch(url, timeout=12, no_proxy=False):
        return b"<!DOCTYPE html><html><head><title>AnandTech</title></head></html>"

    monkeypatch.setattr(discover, "_fetch", fake_fetch)
    res = discover.probe_feed_url("https://dead.example.com/feed")
    assert res["ok"] is False and res["reason"] == "html_shell"


def test_feed_validity_no_entries_rejected(monkeypatch):
    """XML 合法但 0 条目 → 拒绝（not_a_feed 家族：no_entries）。"""
    empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'

    def fake_fetch(url, timeout=12, no_proxy=False):
        return empty.encode("utf-8")

    monkeypatch.setattr(discover, "_fetch", fake_fetch)
    res = discover.probe_feed_url("https://x.example.com/feed")
    assert res["ok"] is False and res["reason"] == "no_entries"


def test_feed_validity_normal_pass(monkeypatch):
    """正常 feed：≥1 条目 + 90 天内新条目 → 通过，取最新条目日期。"""
    monkeypatch.setattr(discover, "_fetch",
                        lambda url, timeout=12, no_proxy=False: CHIP_FEED.encode("utf-8"))
    res = discover.probe_feed_url("https://x.example.com/feed")
    assert res["ok"] is True and res["entry_count"] == 2
    assert res["last_entry_date"] == "2026-09-25"
    assert res["freshness"] == "ok"


# ---------------- D6: 相关性阈值 ----------------

def test_relevance_threshold():
    """判定 = 不同关键词 ≥3 且 命中条目 ≥2 且 命中占比 ≥25%；任一不满足要拒。"""
    strong = [
        {"title": "TSMC wafer fab expansion", "description": "semiconductor foundry"},
        {"title": "NVIDIA HBM advanced packaging", "description": "chiplet CoWoS"},
    ]
    s = discover.score_relevance(strong)
    assert s["kw_hits"] >= 3 and s["entry_hits"] == 2
    assert s["hit_ratio"] == 1.0
    assert discover.is_relevant(s) is True

    weak_one_entry = [{"title": "TSMC wafer fab semiconductor foundry chip",
                       "description": "hbm dram nand euv"}]
    s1 = discover.score_relevance(weak_one_entry)
    assert s1["kw_hits"] >= 3 and s1["entry_hits"] == 1
    assert discover.is_relevant(s1) is False              # 命中条目不足 2

    narrow_two_entries = [
        {"title": "TSMC capex", "description": ""},
        {"title": "TSMC revenue", "description": ""},
    ]
    s2 = discover.score_relevance(narrow_two_entries)
    assert s2["entry_hits"] == 2 and s2["kw_hits"] < 3
    assert discover.is_relevant(s2) is False              # 不同关键词不足 3

    # 消防水管全站 feed：几十条里夹 2 条芯片内容——绝对数过、密度不过
    firehose = [{"title": f"Generic news item {i}",
                 "description": "sports politics weather lifestyle"}
                for i in range(8)] + [
        {"title": "Samsung fab utilization steady", "description": "foundry semiconductor"},
        {"title": "SK hynix HBM output", "description": "dram memory chip"},
    ]
    s3 = discover.score_relevance(firehose)
    assert s3["kw_hits"] >= 3 and s3["entry_hits"] == 2
    assert s3["hit_ratio"] < discover.RELEVANCE_MIN_RATIO
    assert discover.is_relevant(s3) is False              # 密度 20% < 25%


# ---------------- D7: dc:date（Nikkei RDF） ----------------

def test_dc_date_parsing():
    """RDF 命名空间条目 + dc:date → 本地名匹配并归一化为 YYYY-MM-DD。"""
    entries = discover.parse_feed_entries(NIKKEI_RDF)
    assert len(entries) == 1
    assert entries[0]["date"] == "2026-09-25"
    assert entries[0]["title"] == "TSMC chip orders jump"
    assert entries[0]["link"] == "https://asia.nikkei.com/a"


# ---------------- D8: 生命周期退避数学 ----------------

def test_backoff_math_exponential_capped():
    """30min * 2^error_count 指数退避，封顶 7 天。"""
    assert discover.backoff_seconds(0) == 30 * 60
    assert discover.backoff_seconds(1) == 30 * 60 * 2
    assert discover.backoff_seconds(2) == 30 * 60 * 4
    assert discover.backoff_seconds(3) == 30 * 60 * 8
    assert discover.backoff_seconds(10) == 7 * 24 * 3600
    assert discover.backoff_seconds(99) == 7 * 24 * 3600  # 封顶


def test_lifecycle_fail_sets_backoff_next_check():
    """失败 → error_count+1 且 next_check_at = now + 30min*2^新error_count。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "d.com", "domain": "d.com", "state": "trial", "error_count": 0,
         "consecutive_ok": 1, "next_check_at": 0}]}
    now = 1_700_000_000.0
    discover.update_lifecycle(state, [{"domain": "d.com", "ok": False,
                                       "relevant": False, "reason": "html_shell"}],
                              now=now)
    rec = state["sources"][0]
    assert rec["error_count"] == 1 and rec["consecutive_ok"] == 0
    assert rec["next_check_at"] == pytest.approx(now + 30 * 60 * 2)
    assert rec["last_checked"] != ""


# ---------------- D9/D10: 状态转移 ----------------

def test_three_failures_freeze():
    """连续 3 次失败 → frozen（冻结池保留，不删除）。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "d.com", "domain": "d.com", "state": "trial", "error_count": 2,
         "consecutive_ok": 0, "next_check_at": 0}]}
    discover.update_lifecycle(state, [{"domain": "d.com", "ok": False,
                                       "relevant": False, "reason": "stale_feed"}],
                              now=1.0)
    rec = state["sources"][0]
    assert rec["error_count"] == 3
    assert rec["state"] == "frozen"
    assert rec["next_check_at"] == pytest.approx(1.0 + 30 * 60 * 8)


def test_trial_two_passes_promote_active():
    """trial 已 1 连过 → 再过 1 次（连续 2 次）→ active，promoted 计 1。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "d.com", "domain": "d.com", "state": "trial", "error_count": 0,
         "consecutive_ok": 1, "next_check_at": 0}]}
    stats = discover.update_lifecycle(state, [_pass_result("d.com")],
                                      now=1_700_000_000.0)
    rec = state["sources"][0]
    assert rec["state"] == "active" and rec["consecutive_ok"] == 2
    assert rec["error_count"] == 0
    assert stats["promoted"] == 1 and stats["validated"] == 1


def test_candidate_pass_goes_trial_then_active():
    """全链：candidate 首过 → trial；连续第 2 次过 → active。"""
    state = {"version": 1, "updated": "", "sources": []}
    now = 1_700_000_000.0
    discover.update_lifecycle(state, [_pass_result("new.com")], now=now)
    rec = state["sources"][0]
    assert rec["state"] == "trial" and rec["consecutive_ok"] == 1
    assert rec["feed_url"] == "https://new.com/feed"
    stats = discover.update_lifecycle(state, [_pass_result("new.com")],
                                      now=now + discover.OK_INTERVAL)
    assert rec["state"] == "active"
    assert stats["promoted"] == 1


def test_failed_new_candidate_pooled_with_backoff_then_recovered():
    """确定性失败的新域入池为 candidate（带退避，防死域每轮重占探测名额）；
    3 败转 frozen；冻结后重探通过翻案回 trial。"""
    state = {"version": 1, "updated": "", "sources": []}
    now = 1_700_000_000.0
    fail = {"domain": "dead.com", "ok": False, "relevant": False,
            "reason": "not_a_feed"}   # 确定性失败（走 error_count/frozen 链）
    discover.update_lifecycle(state, [fail], now=now)
    rec = state["sources"][0]
    assert rec["state"] == "candidate" and rec["error_count"] == 1
    assert rec["next_check_at"] == pytest.approx(now + 30 * 60 * 2)
    discover.update_lifecycle(state, [fail], now=now + 30 * 60 * 2)
    assert rec["error_count"] == 2 and rec["state"] == "candidate"
    discover.update_lifecycle(state, [fail], now=now + 30 * 60 * 4)
    assert rec["error_count"] == 3 and rec["state"] == "frozen"
    # 冻结池翻案：重探通过 → trial（consecutive_ok 重置为 1）
    discover.update_lifecycle(state, [_pass_result("dead.com")],
                              now=now + 30 * 60 * 8)
    assert rec["state"] == "trial" and rec["consecutive_ok"] == 1


def test_transient_failures_do_not_freeze_or_demote():
    """对抗审查 #5：断网/超时类瞬时失败不冻结、不改 state（trial/active
    不被 collector 动态白名单除名）；确定性失败才累积 error_count 走 frozen。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "a.com", "domain": "a.com", "state": "active", "error_count": 0,
         "consecutive_ok": 5, "next_check_at": 0}]}
    now = 1_000_000.0
    for i in range(5):  # 断网一下午：5 轮瞬时失败
        discover.update_lifecycle(
            state, [{"domain": "a.com", "ok": False, "relevant": False,
                     "reason": "fetch_failed:URLError"}], now=now + i * 3600)
    rec = state["sources"][0]
    assert rec["state"] == "active" and rec["error_count"] == 0
    assert rec["transient_errors"] == 5
    last_gap = rec["next_check_at"] - (now + 4 * 3600)
    assert last_gap <= discover.TRANSIENT_MAX_BACKOFF   # 瞬时退避封顶 24h
    # 恢复通过 → active 保持、连击重新计数（失败已清 0，通过后为 1）
    discover.update_lifecycle(state, [_pass_result("a.com")], now=now + 5 * 3600)
    assert rec["state"] == "active" and rec["consecutive_ok"] == 1
    # 确定性失败另走 error_count → frozen
    for i in range(3):
        discover.update_lifecycle(
            state, [{"domain": "a.com", "ok": False, "relevant": False,
                     "reason": "not_a_feed"}], now=now + 6 * 3600 + i * 7200)
    assert rec["state"] == "frozen" and rec["error_count"] == 3


def test_recheck_does_not_overwrite_discovered_via():
    """对抗审查 #2：生命周期复核（feed_hint 命中，via=recheck）不得改写
    「首次发现渠道」——否则 gnews 首发现的源会被错标成 hint。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "d.com", "domain": "d.com", "state": "trial", "error_count": 0,
         "consecutive_ok": 1, "next_check_at": 0, "discovered_via": "gnews"}]}
    r = _pass_result("d.com")
    r["discovered_via"] = "recheck"
    discover.update_lifecycle(state, [r], now=1.0)
    assert state["sources"][0]["discovered_via"] == "gnews"   # 原值保留
    r2 = _pass_result("new2.com")
    r2["discovered_via"] = "link_tag"
    discover.update_lifecycle(state, [r2], now=2.0)
    new_rec = [s for s in state["sources"] if s["domain"] == "new2.com"][0]
    assert new_rec["discovered_via"] == "link_tag"            # 空值时才写入


def test_relevance_word_boundary_blocks_substring_false_positives():
    """对抗审查 #1：英文关键词按词边界匹配，纯子串下无关内容可刷过
    （chiptune→chip、medal→eda、fabulous→fab、石版画 lithograph→litho）。"""
    decoy = [
        {"title": "Chiptune music festival lineup announced",
         "description": "a celebration of 8-bit sounds and retro game music"},
        {"title": "Lithograph art prints and medal ceremony",
         "description": "an exhibition of stone lithograph works and medals"},
    ]
    s = discover.score_relevance(decoy)
    assert s["kw_hits"] == 0 and s["entry_hits"] == 0
    assert discover.is_relevant(s) is False
    # 词边界不误伤真命中：fab/fabs、chip/chips 等真实词形仍命中
    real = [{"title": "TSMC fabs raise wafer chip prices",
             "description": "semiconductor foundry capacity expansion"}]
    s2 = discover.score_relevance(real)
    assert {"tsmc", "fab", "wafer", "chip", "semiconductor", "foundry"} <= set(s2["matched"])


def test_chip_kw_chinese_coverage_domestic_chain_and_policy():
    """对抗审查 #6：国产链公司名/政策词/设备材料词不再零命中。"""
    entries = [
        {"title": "台积电2nm量产 中芯国际跟进扩产",
         "description": "晶圆厂先进制程竞争加剧"},
        {"title": "北方华创中标中微公司刻蚀设备大单",
         "description": "国产设备验证流片提速"},
        {"title": "美国将多家中国公司列入实体清单",
         "description": "出口管制升级，国家大基金加码靶材与CMP抛光垫国产化"},
    ]
    s = discover.score_relevance(entries)
    # matched 只截取前 12 个，完整命中集用 _kw_hits_in 逐词断言
    all_text = " ".join(e["title"] + " " + e["description"] for e in entries).lower()
    hits = discover._kw_hits_in(all_text)
    for kw in ("台积电", "中芯国际", "晶圆厂", "北方华创", "中微公司", "刻蚀",
               "流片", "实体清单", "出口管制", "大基金", "靶材", "抛光垫"):
        assert kw in hits, kw
    assert discover.is_relevant(s) is True


def test_discover_redirect_handler_blocks_unsafe_targets(monkeypatch):
    """对抗审查 #4：重定向落点必须再过安全校验——http/私网落点阻断，
    https 合法落点放行（零网络：getaddrinfo 全部 monkeypatch）。"""
    handler = discover._DiscoverRedirectHandler()
    req = discover.urllib.request.Request("https://origin.example.com/feed")
    with pytest.raises(ValueError):   # http 落点
        handler.redirect_request(req, None, 302, "Found", {},
                                 "http://evil.example.com/secret")
    monkeypatch.setattr(discover.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(2, 1, 6, "", ("10.0.0.7", 443))])
    with pytest.raises(ValueError):   # 私网落点（302→内网 SSRF）
        handler.redirect_request(req, None, 302, "Found", {},
                                 "https://redirect.example.com/secret")
    monkeypatch.setattr(discover.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    out = handler.redirect_request(req, None, 302, "Found", {},
                                   "https://target.example.com/feed")
    assert out is not None and out.full_url == "https://target.example.com/feed"


def test_collector_redirect_handler_blocks_non_whitelist():
    """collector 侧重定向校验：非 https / 非白名单落点阻断，白名单内放行。"""
    handler = collector._SafeRedirectHandler()
    req = collector.urllib.request.Request("https://semiengineering.com/feed")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "http://open.example.com/x")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "https://not-in-allowlist.example.com/x")
    out = handler.redirect_request(req, None, 302, "Found", {},
                                   "https://www.eetimes.com/feed/")
    assert out is not None and out.full_url == "https://www.eetimes.com/feed/"


def test_build_probe_queue_weighted_round_robin():
    """组权重轮转：gnews-en 占 3/6 名额，zh/newsnow/opml 各 1/6。"""
    pool = {}
    for i in range(10):
        pool[f"zh{i}.com"] = {"hits": 50, "sample_titles": ["半导体芯片"], "via": "gnews",
                              "group": "gnews-zh", "feed_hint": ""}
        pool[f"en{i}.com"] = {"hits": 50, "sample_titles": ["TSMC chip fab"], "via": "gnews",
                              "group": "gnews-en", "feed_hint": ""}
    pool["nn.com"] = {"hits": 9, "sample_titles": [], "via": "newsnow",
                      "group": "newsnow", "feed_hint": ""}
    queue = discover._build_probe_queue(pool, 10)
    doms = [d for d, _ in queue]
    assert len(doms) == len(set(doms))            # 无重复入队（权重轮转下也一样）
    groups = [c["group"] for _, c in queue]
    assert groups.count("gnews-en") == 6          # en 按权重占多数（3/6 位循环）
    assert groups.count("gnews-zh") == 3
    assert groups.count("newsnow") == 1
    assert doms[0] == "en0.com" and doms[1] == "zh0.com"


# ---------------- D11: _assert_safe_url ----------------

def test_assert_safe_url_rejects_http():
    """http 明文 → 拒绝（发现层 https-only）。"""
    with pytest.raises(ValueError):
        discover._assert_safe_url("http://example.com/feed")


def test_assert_safe_url_rejects_private_ip(monkeypatch):
    """DNS 解析到私网地址 → 拒绝（SSRF 防线）。"""

    def fake_getaddrinfo(host, port, *a, **k):
        return [(2, 1, 6, "", ("10.1.2.3", 443)),
                (2, 1, 6, "", ("192.168.1.5", 443))]

    monkeypatch.setattr(discover.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        discover._assert_safe_url("https://evil.example.com/feed")


def test_assert_safe_url_rejects_loopback(monkeypatch):
    """DNS 解析到环回地址 → 拒绝。"""
    monkeypatch.setattr(discover.socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError):
        discover._assert_safe_url("https://inner.example.com/feed")


# ---------------- D12: collector._dynamic_hosts ----------------

def test_collector_dynamic_hosts_merge(tmp_path):
    """trial/active 的域名与 feed 域名并入白名单；frozen 不并入。"""
    sf = tmp_path / "discovered_sources.json"
    sf.write_text(json.dumps({
        "version": 1, "updated": "2026-09-26T00:00:00Z",
        "sources": [
            {"id": "a.com", "domain": "a.com", "state": "trial",
             "feed_url": "https://feed.a.com/rss"},
            {"id": "b.com", "domain": "www.b.com", "state": "active",
             "feed_url": "https://b.com/feed"},
            {"id": "c.com", "domain": "c.com", "state": "frozen",
             "feed_url": "https://c.com/feed"},
        ]}, ensure_ascii=False), encoding="utf-8")
    hosts = collector._dynamic_hosts(sf)
    assert {"a.com", "feed.a.com", "www.b.com", "b.com"} <= hosts
    assert "c.com" not in hosts and "feed.c.com" not in hosts
    # www 变体互补（2026-09-26 回测发现）：state 存裸域而 feed 在 www 子域
    # （或反之）都要放行，否则动态源被白名单拒绝、采集静默缺失
    assert "www.a.com" in hosts and "www.feed.a.com" in hosts
    assert "www.b.com" in hosts and "www.b.com" in hosts
    sf2 = tmp_path / "www_case.json"
    sf2.write_text(json.dumps({"version": 1, "updated": "", "sources": [
        {"id": "t.com", "domain": "techpowerup.com", "state": "active",
         "feed_url": "https://www.techpowerup.com/rss"}]}, ensure_ascii=False),
        encoding="utf-8")
    h2 = collector._dynamic_hosts(sf2)
    assert {"techpowerup.com", "www.techpowerup.com"} <= h2


def test_collector_dynamic_hosts_missing_file_fail_soft(tmp_path):
    """状态文件不存在 / 损坏 → 空集（退回纯静态白名单）。"""
    assert collector._dynamic_hosts(tmp_path / "nope.json") == set()
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    assert collector._dynamic_hosts(bad) == set()


# ---------------- D13: 动态 RSS 采集器 ----------------

def test_dynamic_rss_collector_from_state(tmp_path, monkeypatch):
    """state 里的 trial/active 源 → 动态 RSSCollector 子类 → 解析 fixture XML。"""
    sf = tmp_path / "discovered_sources.json"
    sf.write_text(json.dumps({"version": 1, "updated": "", "sources": [
        {"id": "newsite_example.com", "domain": "newsite.example.com",
         "state": "active", "feed_url": "https://newsite.example.com/feed"}]},
        ensure_ascii=False), encoding="utf-8")
    # 动态白名单与采集器实例化都指向 tmp 状态文件（绝不碰真实 state/）
    monkeypatch.setattr(collector, "_DISCOVERED_STATE_PATH", sf)
    monkeypatch.setattr(collector.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline test")))
    classes = collector.dynamic_rss_collectors(sf)
    assert len(classes) == 1
    c = classes[0]()
    assert c.feed_url == "https://newsite.example.com/feed"
    # 对抗审查 #3：动态源 tier=4（线索级）——零人工审核源不与 registry
    # A 级中文权威（tier=3）同级，且 gate G3 会对 tier=4 单源打 single_low_tier
    assert c.source_id == "dyn_newsite_example.com" and c.tier == 4

    def fake_urlopen(req, timeout=10):
        class R:                       # 桩必须带 def read(self, n=-1)
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                return CHIP_FEED.encode("utf-8")

        return R()

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    items = c.collect({})
    assert len(items) == 2
    assert items[0].title.startswith("TSMC wafer fab")
    assert items[0].published == "2026-09-24"


# ---------------- 附加：状态文件 / known 过滤 / collector 侧 ----------------

def test_state_save_load_roundtrip_and_fail_soft(tmp_path):
    """原子写回（.tmp 被 os.replace 消费）+ 读损坏/缺失文件 fail-soft。"""
    p = tmp_path / "state" / "discovered_sources.json"
    assert discover.load_state(p) == {"version": 1, "updated": "", "sources": []}
    st = {"version": 1, "updated": "x", "sources": [{"id": "a", "domain": "a.com"}]}
    discover.save_state(st, p)
    assert not p.with_suffix(".tmp").exists()            # 原子替换后 tmp 消失
    assert discover.load_state(p)["sources"][0]["id"] == "a"


def test_known_domains_and_net_new_filter():
    """known = registry ∪ collector 白名单 ∪ state 已有；net-new 只留增量。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "x", "domain": "already-found.com", "state": "trial", "feed_url": ""}]}
    known = discover.known_domains(state)
    assert "semiengineering.com" in known                 # collector 白名单
    assert "tomshardware.com" in known                    # registry（www 剥离归一）
    assert "already-found.com" in known                   # state 已有
    pool = {"brand-new.com": {"hits": 5, "sample_titles": []},
            "semiengineering.com": {"hits": 9, "sample_titles": []}}
    known_norm = {discover._norm_host(k) for k in known}
    net_new = {d for d in pool if discover._norm_host(d) not in known_norm}
    assert net_new == {"brand-new.com"}


def test_google_news_collector_publisher_domain(monkeypatch):
    """GoogleNews 采集器：中英 2 组 query，publisher_domain 落 raw_payload。"""

    def fake_urlopen(req, timeout=10):
        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                return GNEWS_XML.encode("utf-8")

        return R()

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(collector.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline test")))
    c = collector.GoogleNewsCollector()
    c.QUERY_INTERVAL = 0.0
    items = c.collect({})
    doms = {it.raw_payload.get("publisher_domain") for it in items}
    assert "https://www.tomshardware.com" in doms
    assert "https://technews.tw" in doms
    assert all(it.tier == 4 for it in items)              # 线索级


def test_rss_parse_rdf_dc_date():
    """collector._parse 兼容 Nikkei RDF：命名空间条目 + dc:date 日期兜底。"""
    items = collector.RSSCollector()._parse(NIKKEI_RDF)
    assert len(items) == 1
    assert items[0].published == "2026-09-25"
    assert items[0].url == "https://asia.nikkei.com/a"


def test_cninfo_gbk_contract(monkeypatch):
    """巨潮契约：GBK 字节容错解码、<em> 清洗、adjunctUrl 拼 PDF 前缀、
    毫秒时间戳（北京时间）、no_proxy 直连。"""
    ts_ms = int(datetime(2026, 9, 25, 10, 0,
                         tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
    payload = {"announcements": [
        {"announcementTitle": "<em>芯片</em>架构研发进展",
         "adjunctUrl": "finalpage/2026-09-25/abc.PDF",
         "announcementTime": ts_ms, "secName": "某芯片公司"}]}
    body = json.dumps(payload, ensure_ascii=False).encode("gbk")

    def fake_fetch_ex(url, timeout=10, no_proxy=False):
        assert no_proxy is True                           # 国内站绕系统代理
        return body

    monkeypatch.setattr(collector, "_safe_fetch_ex", fake_fetch_ex)
    items = collector.CninfoCollector().collect({})
    assert len(items) == 1
    it = items[0]
    assert it.title == "芯片架构研发进展"                  # <em> 已清洗
    assert it.url == "https://static.cninfo.com.cn/finalpage/2026-09-25/abc.PDF"
    assert it.published == "2026-09-25"
    assert it.type == "filing" and it.tier == 3


def test_newsnow_proxy_fallback_then_skip(monkeypatch):
    """newsnow：no_proxy 直连失败 → 走系统代理重试成功；两路全挂 → 跳过。"""
    calls = []

    def flaky_fetch_ex(url, timeout=10, no_proxy=False):
        calls.append(no_proxy)
        if no_proxy:
            raise OSError("direct blocked")
        return json.dumps({"items": [{"title": "存储涨价",
                                      "url": "https://www.cls.cn/x"}]}).encode("utf-8")

    monkeypatch.setattr(collector, "_safe_fetch_ex", flaky_fetch_ex)
    items = collector.NewsnowCollector().collect({})
    assert calls[:2] == [True, False]                     # 先直连后代理
    assert items and all(it.tier == 4 for it in items)

    def boom(url, timeout=10, no_proxy=False):
        raise OSError("down")

    monkeypatch.setattr(collector, "_safe_fetch_ex", boom)
    assert collector.NewsnowCollector().collect({}) == []  # 全失败 → 跳过不抛


# ---------------- 回测修复（第 2 轮）：规范化 / 队列 / 双路径回退 ----------------

def test_canonical_domain_strips_mobile_mirror():
    """移动端镜像（m./wap.）规范化到发布方主域；普通域与短域不动。"""
    assert discover._canonical_domain("m.21jingji.com") == "21jingji.com"
    assert discover._canonical_domain("wap.eastmoney.com") == "eastmoney.com"
    assert discover._canonical_domain("https://touch.sohu.com/x") == "sohu.com"
    assert discover._canonical_domain("www.tomshardware.com") == "tomshardware.com"
    assert discover._canonical_domain("sina.cn") == "sina.cn"       # 短域不剥
    assert discover._canonical_domain("finance.sina.cn") == "finance.sina.cn"
    assert discover._canonical_domain("") == ""


def test_merge_candidates_canonicalizes_mobile_mirror():
    """候选池键 = 主域：移动镜像并入主域，组标签落池。"""
    pool: dict = {}
    discover._merge_candidates(pool, {"m.21jingji.com": {"hits": 3, "sample_titles": []}},
                               "gnews", group="gnews-zh")
    assert "21jingji.com" in pool and "m.21jingji.com" not in pool
    assert pool["21jingji.com"]["group"] == "gnews-zh"


def test_build_probe_queue_chip_density_and_round_robin():
    """加权轮转（en 先开跑）+ 组内按样本标题芯片密度排序：
    低 hits 的芯片垂类域应排在低密度高 hits 的财经门户前面。"""
    pool = {
        "zh-portal.com": {"hits": 50, "sample_titles": ["A股收涨 沪指上行"],
                          "via": "gnews", "group": "gnews-zh", "feed_hint": ""},
        "zh-chip.com": {"hits": 10,
                        "sample_titles": ["晶圆厂扩产带动芯片设备出货", "半导体出口管制升级"],
                        "via": "gnews", "group": "gnews-zh", "feed_hint": ""},
        "en-macro.com": {"hits": 30, "sample_titles": ["Fed rate decision"],
                         "via": "gnews", "group": "gnews-en", "feed_hint": ""},
        "en-chip.com": {"hits": 8,
                        "sample_titles": ["TSMC wafer fab expansion", "NVIDIA HBM chiplet"],
                        "via": "gnews", "group": "gnews-en", "feed_hint": ""},
        "nn-finance.com": {"hits": 20, "sample_titles": [], "via": "newsnow",
                           "group": "newsnow", "feed_hint": ""},
    }
    queue = discover._build_probe_queue(pool, 5)
    order = [d for d, _ in queue]
    # en 组先开跑且密度排序生效；en 组占 2 席（en-macro 也入队），zh-portal 垫底
    assert order == ["en-chip.com", "zh-chip.com", "en-macro.com",
                     "nn-finance.com", "zh-portal.com"]


def test_fetch_proxy_fallback_retry(monkeypatch):
    """系统代理 403 → 自动换直连重试一次成功；404 不重试。
    （_fetch 走显式 build_opener：带 ProxyHandler({}) 参数的=直连分支）"""
    monkeypatch.setattr(discover, "_POLITE_INTERVAL", 0.0)
    monkeypatch.setattr(discover.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline test")))
    calls = {"proxy": 0, "direct": 0}

    class ErrOpener:
        def __init__(self, err):
            self._err = err

        def open(self, req, timeout=12):
            raise self._err

    class OkOpener:
        def open(self, req, timeout=12):
            class R:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def read(self, n=-1):
                    return b"<rss><channel><item><title>t</title></item></channel></rss>"

            return R()

    def fake_build_opener(*handlers):
        is_direct = any(isinstance(h, discover.urllib.request.ProxyHandler)
                        for h in handlers)
        if is_direct:
            calls["direct"] += 1
            return OkOpener()
        calls["proxy"] += 1
        return ErrOpener(urllib_error.HTTPError(
            "https://retry.example.com/feed", 403, "Forbidden", None, None))

    monkeypatch.setattr(discover.urllib.request, "build_opener", fake_build_opener)
    body = discover._fetch("https://retry.example.com/feed")
    assert body.startswith(b"<rss>")
    assert calls == {"proxy": 1, "direct": 1}      # 先代理后直连，各一次

    # 404：确定性答案，不触发换路径重试
    def fake_build_opener_404(*handlers):
        is_direct = any(isinstance(h, discover.urllib.request.ProxyHandler)
                        for h in handlers)
        calls["direct" if is_direct else "proxy"] += 1
        return ErrOpener(urllib_error.HTTPError(
            "https://retry.example.com/missing", 404, "Not Found", None, None))

    monkeypatch.setattr(discover.urllib.request, "build_opener", fake_build_opener_404)
    with pytest.raises(urllib_error.HTTPError):
        discover._fetch("https://retry.example.com/missing")
    assert calls == {"proxy": 2, "direct": 1}      # 404 未触发直连重试


def test_fetch_no_proxy_falls_back_to_proxy(monkeypatch):
    """显式 no_proxy 直连失败 → 换系统代理重试（newsnow/cninfo 形态对称）。"""
    monkeypatch.setattr(discover, "_POLITE_INTERVAL", 0.0)
    monkeypatch.setattr(discover.socket, "getaddrinfo",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("offline test")))

    def fake_build_opener(*handlers):
        is_direct = any(isinstance(h, discover.urllib.request.ProxyHandler)
                        for h in handlers)
        if is_direct:
            class BadOpener:
                def open(self, req, timeout=12):
                    raise OSError("direct blocked")
            return BadOpener()

        class OkOpener:
            def open(self, req, timeout=12):
                class R:
                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                    def read(self, n=-1):
                        return b"ok"

                return R()
        return OkOpener()

    monkeypatch.setattr(discover.urllib.request, "build_opener", fake_build_opener)
    assert discover._fetch("https://fallback.example.com/api", no_proxy=True) == b"ok"


def test_select_due_trial_always_rechecked_with_cap():
    """trial 试用期每次运行必复核（不受 next_check_at 限制），但最多占 cap/3；
    其余状态按到期时间。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": f"t{i}.com", "domain": f"t{i}.com", "state": "trial",
         "next_check_at": 9_999_999_999} for i in range(5)] + [
        {"id": "frozen-due.com", "domain": "frozen-due.com", "state": "frozen",
         "next_check_at": 1.0},
        {"id": "active-due.com", "domain": "active-due.com", "state": "active",
         "next_check_at": 2.0},
        {"id": "active-future.com", "domain": "active-future.com", "state": "active",
         "next_check_at": 9_999_999_999},
    ]}
    due = discover._select_due(state, now=100.0, cap=18)
    doms = [s["domain"] for s in due]
    # trial 最多 cap//3=6 个，但只有 5 个 trial → 全进；frozen/active 到期项跟进
    assert set(doms) == {f"t{i}.com" for i in range(5)} | {"frozen-due.com",
                                                           "active-due.com"}
    assert "active-future.com" not in doms
    # cap=3 时 trial 只占 1 个名额
    due3 = discover._select_due(state, now=100.0, cap=3)
    assert sum(1 for s in due3 if s["state"] == "trial") == 1
    assert len(due3) == 3


def test_rescore_pool_demotes_by_current_gate(monkeypatch, tmp_path):
    """D14 rescore 模式：门禁升级后用当前门禁全池复判——确定性失败/低相关
    降回 candidate（计数归零），瞬时失败不动，通过者保留并刷新证据；
    candidate 不参与复判。"""
    state = {"version": 1, "updated": "", "sources": [
        {"id": "good.com", "domain": "good.com", "state": "active",
         "feed_url": "https://good.com/feed/", "error_count": 0,
         "consecutive_ok": 5, "evidence": {}},
        {"id": "bad.com", "domain": "bad.com", "state": "active",
         "feed_url": "https://bad.com/feed/", "error_count": 0,
         "consecutive_ok": 5, "evidence": {}},
        {"id": "dead.com", "domain": "dead.com", "state": "trial",
         "feed_url": "https://dead.com/feed/", "error_count": 0,
         "consecutive_ok": 1, "evidence": {}},
        {"id": "flaky.com", "domain": "flaky.com", "state": "trial",
         "feed_url": "https://flaky.com/feed/", "error_count": 0,
         "consecutive_ok": 1, "evidence": {}},
        {"id": "cand.com", "domain": "cand.com", "state": "candidate",
         "feed_url": "https://cand.com/feed/", "evidence": {}},
    ]}
    p = tmp_path / "discovered_sources.json"
    p.write_text(json.dumps(state), encoding="utf-8")

    ent_chip = [
        {"title": "TSMC 2nm wafer fab ramp", "description": "foundry chip output",
         "link": "https://good.com/a", "date": "2026-09-20"},
        {"title": "ASML lithography orders", "description": "EUV chiplet packaging",
         "link": "https://good.com/b", "date": "2026-09-21"},
    ]
    ent_game = [
        {"title": "Best gaming keyboards and monitors", "description": "sale deals",
         "link": "https://bad.com/a", "date": "2026-09-20"},
    ]

    def fake_probe(feed_url):
        if "good.com" in feed_url:
            return {"ok": True, "entries": ent_chip, "entry_count": 2,
                    "last_entry_date": "2026-09-21"}
        if "bad.com" in feed_url:
            return {"ok": True, "entries": ent_game, "entry_count": 1,
                    "last_entry_date": "2026-09-20"}
        if "dead.com" in feed_url:
            return {"ok": False, "reason": "html_shell"}
        return {"ok": False, "reason": "fetch_failed:URLError"}

    monkeypatch.setattr(discover, "probe_feed_url", fake_probe)
    res = discover.rescore_pool(p)
    assert res["checked"] == 4
    assert res["kept"] == 1
    assert res["demoted"] == 2
    assert res["skipped_transient"] == 1

    data = json.loads(p.read_text(encoding="utf-8"))
    by = {s["domain"]: s for s in data["sources"]}
    assert by["good.com"]["state"] == "active"
    assert by["good.com"]["evidence"]["rescore"].endswith("kept")
    assert by["bad.com"]["state"] == "candidate"
    assert by["bad.com"]["evidence"]["rescore"].endswith("demoted:low_relevance")
    assert by["dead.com"]["state"] == "candidate"
    assert by["dead.com"]["evidence"]["rescore"].endswith("demoted:html_shell")
    assert by["flaky.com"]["state"] == "trial"      # 瞬时失败不动
    assert by["cand.com"]["state"] == "candidate"   # candidate 不参与复判
