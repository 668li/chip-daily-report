#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_claims_gate — 声明级对账门禁（v8 R2）的对抗样本回归。

纪律：门禁必须先被对抗样本打过才准上岗（v7 复盘 ⑦.2）。
  - 承重数字提取：pct/亿/万/年/节点名/TOPS，技术注解数字不提取
  - 跨语言变体匹配：640亿↔$64 billion、3%至6%↔3% to 6%、2万片↔20,000
  - 判定语义：mismatch=FAIL（对不上不出版）；gnews 跳转链=降级不 FAIL；
    抓不到正文=如实暴露不 FAIL；无数字条目=中性跳过
  - 安全：http URL / 白名单外域名 / 私网解析 拒抓；缓存读写与过期

离线测试：monkeypatch article_fetch / 抓取函数，零网络依赖；缓存走 tmp_path。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MS = ROOT / "scripts" / "multi_source"
for p in (MS, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import article_fetch  # noqa: E402
import validate_claims as vc  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# 承重数字提取
# ============================================================
def test_extract_claims_basic_kinds():
    text = ("台积电 2027 年 1 月起涨价 3%-6%，年度 capex 上修至约 640 亿美元，"
            "月产能 2 万片，14A 与台积电 A14 差距 5% 以内，N2 产线爬坡，"
            "NPU 达 40 TOPS，份额 72.5%")
    kinds = {(c["kind"], str(c["value"])) for c in vc.extract_claims(text)}
    assert ("pct", "3.0") in kinds and ("pct", "6.0") in kinds
    assert ("pct", "5.0") in kinds and ("pct", "72.5") in kinds
    assert ("yi", "640.0") in kinds
    assert ("wan", "2.0") in kinds
    assert ("tops", "40.0") in kinds
    years = {c["value"] for c in vc.extract_claims(text) if c["kind"] == "year"}
    assert "2027" in years
    nodes = {c["value"] for c in vc.extract_claims(text) if c["kind"] == "node"}
    assert any("14" in n for n in nodes) and "N2" in nodes


def test_extract_claims_excludes_teach_note():
    # 技术注解是教学内容不是新闻承重事实——其中数字不参与对账
    text = "份额升至 72.5% [技术注解: TOPS=每秒万亿次运算，40 TOPS 是门槛]"
    claims = vc.extract_claims(text)
    assert not any(c["kind"] == "tops" for c in claims)
    assert any(c["kind"] == "pct" for c in claims)


def test_extract_claims_no_month_day_noise():
    # 「1 月」「9 月 22 日」不做对账声明（英文原文月份写法不同、单数字噪声大）
    text = "9 月 22 日峰会后，2027 年 1 月起生效"
    kinds = {c["kind"] for c in vc.extract_claims(text)}
    assert kinds == {"year"}


def test_yi_claim_billion_variants():
    claims = vc.extract_claims("资本开支上修至约 640 亿美元")
    yi = [c for c in claims if c["kind"] == "yi"][0]
    assert "640亿" in yi["variants"]
    assert "64 billion" in yi["variants"] and "$64b" in yi["variants"]


# ============================================================
# 跨语言变体匹配
# ============================================================
def test_match_cn_text_with_space():
    claims = vc.extract_claims("约 640 亿美元")
    hit, missing = vc.match_claims(claims, "台积电拟投入 640 亿美元扩建产能")
    assert hit == 1 and not missing


def test_match_english_billion():
    claims = vc.extract_claims("约 640 亿美元")
    hit, missing = vc.match_claims(claims, "TSMC will spend $64 billion on capex in 2026")
    assert hit == 1 and not missing


def test_match_range_percent_english():
    claims = vc.extract_claims("涨价 3%-6%")
    hit, _ = vc.match_claims(claims, "prices will rise 3% to 6% on advanced nodes")
    assert hit == 2


def test_match_missing_number():
    claims = vc.extract_claims("份额约 72.5%")
    hit, missing = vc.match_claims(claims, "nothing about market share here at all")
    assert hit == 0 and missing == ["72.5%"]


# ============================================================
# 条目级判定语义
# ============================================================
def _entry(title, summary, source):
    return {"title": title, "summary": summary, "source": source,
            "timestamp": "2026-09-26 | 信号: 高/利好/正面"}


def _patch_fetch(monkeypatch, responder):
    monkeypatch.setattr(vc, "get_article_text", responder)


def test_audit_mismatch(monkeypatch, tmp_path):
    _patch_fetch(monkeypatch, lambda *a, **k: {
        "url": k.get("url") or (a[1] if len(a) > 1 else ""), "status": "ok",
        "text_len": 5000, "text": "totally unrelated content " * 100,
        "error": None})
    r = vc.audit_entry(
        _entry("份额条目", "台积电份额约 72.5%，其余不足三成",
               "[NeoTeo](https://www.neoteo.com/tsmc-share-q2/)"),
        tmp_path, 5, 4, [4], set())
    assert r["verdict"] == "mismatch"
    assert r["coverage"] == 0.0


def test_audit_ok(monkeypatch, tmp_path):
    body = "TSMC holds about 72.5 percent share in Q2 foundry market " * 20
    _patch_fetch(monkeypatch, lambda *a, **k: {
        "url": "", "status": "ok", "text_len": len(body), "text": body,
        "error": None})
    r = vc.audit_entry(
        _entry("份额条目", "台积电份额约 72.5%", "[NeoTeo](https://www.neoteo.com/x/)"),
        tmp_path, 5, 4, [4], set())
    assert r["verdict"] == "ok"


def test_audit_gnews_only_is_not_fail(monkeypatch, tmp_path):
    _patch_fetch(monkeypatch, lambda *a, **k: {"url": "", "status": "error",
                                               "text_len": 0, "text": "",
                                               "error": "should not be called"})
    r = vc.audit_entry(
        _entry("份额条目", "份额约 72.5%",
               "[NeoTeo 经 Google News](https://news.google.com/rss/articles/CBMi?oc=5)"),
        tmp_path, 5, 4, [4], set())
    assert r["verdict"] == "redirect_only"


def test_audit_no_text_is_not_fail(monkeypatch, tmp_path):
    _patch_fetch(monkeypatch, lambda *a, **k: {
        "url": "", "status": "too_short", "text_len": 80, "text": "",
        "error": "疑似反爬/付费墙"})
    r = vc.audit_entry(
        _entry("份额条目", "份额约 72.5%", "[Paywall](https://www.paywall.com/x/)"),
        tmp_path, 5, 4, [4], set())
    assert r["verdict"] == "no_text"


def test_audit_no_claims_neutral(monkeypatch, tmp_path):
    _patch_fetch(monkeypatch, lambda *a, **k: {"url": "", "status": "ok",
                                               "text_len": 0, "text": "",
                                               "error": None})
    r = vc.audit_entry(
        _entry("综述条目", "行业综述口径，无具体数字承重",
               "[SemiEngineering](https://semiengineering.com/week/)"),
        tmp_path, 5, 4, [4], set())
    assert r["verdict"] == "no_claims"


def test_audit_budget_exhausted(monkeypatch, tmp_path):
    called = []
    _patch_fetch(monkeypatch, lambda *a, **k: called.append(1) or {
        "url": "", "status": "ok", "text_len": 0, "text": "", "error": None})
    r = vc.audit_entry(
        _entry("份额条目", "份额约 72.5%", "[S](https://www.s.com/x/)"),
        tmp_path, 5, 4, [0], set())
    assert r["verdict"] == "no_text" and not called


# ============================================================
# run() 退出码 + JSON 产物
# ============================================================
_REPORT_TMPL = """# 日报测试

生成时间: 2026-09-26 08:00
覆盖范围: ≤72h
新闻总数: 2 条

## 制造

- **{t1}** — {s1} | 来源: [{n1}]({u1}) | 2026-09-26 | 信号: 高/利好/正面

- **{t2}** — {s2} | 来源: [{n2}]({u2}) | 2026-09-26 | 信号: 中/中性/中性
"""


def test_run_exit_codes(monkeypatch, tmp_path):
    good = "prices rise 3% to 6% in 2027 on advanced nodes " * 20
    bad = "completely unrelated body text " * 100

    def fake_fetch(url, cache_dir=None, **k):
        text = good if "good.com" in url else bad
        return {"url": url, "status": "ok", "text_len": len(text),
                "text": text, "error": None}

    _patch_fetch(monkeypatch, fake_fetch)
    md = tmp_path / "r.md"
    md.write_text(_REPORT_TMPL.format(
        t1="涨价条目", s1="台积电 2027 年起涨价 3%-6%",
        n1="S1", u1="https://www.good.com/article/1",
        t2="份额条目", s2="份额约 72.5%",
        n2="S2", u2="https://www.bad.com/article/2"), encoding="utf-8")
    jout = tmp_path / "claim_report.json"
    rc = vc.run(md, tmp_path / "cache", timeout=1, max_fetch=4,
                no_fetch=False, json_out=jout)
    assert rc == 1  # 一条对不上 → 不许出版
    payload = json.loads(jout.read_text(encoding="utf-8"))
    assert payload["stats"]["mismatch"] == 1
    assert payload["stats"]["ok"] == 1

    # 全对上 → exit 0
    md2 = tmp_path / "r2.md"
    md2.write_text(_REPORT_TMPL.format(
        t1="涨价条目", s1="台积电 2027 年起涨价 3%-6%",
        n1="S1", u1="https://www.good.com/article/1",
        t2="利好条目", s2="2027 年先进制程扩产",
        n2="S2", u2="https://www.good.com/article/1"), encoding="utf-8")
    rc2 = vc.run(md2, tmp_path / "cache", timeout=1, max_fetch=4,
                 no_fetch=False, json_out=tmp_path / "j2.json")
    assert rc2 == 0


# ============================================================
# article_fetch 安全与缓存
# ============================================================
def test_is_gnews_link():
    assert article_fetch.is_gnews_link(
        "https://news.google.com/rss/articles/CBMi?oc=5")
    assert not article_fetch.is_gnews_link("https://www.tomshardware.com/a/b")


def test_assert_citable_url_rejects():
    import pytest
    with pytest.raises(ValueError):  # http 拒
        article_fetch.assert_citable_url("http://www.tomshardware.com/a/b")
    with pytest.raises(ValueError):  # 白名单外域名拒（不经 DNS 即拒）
        article_fetch.assert_citable_url("https://evil.example.com/a")
    with pytest.raises(ValueError):  # 引用域未并入时拒
        article_fetch.assert_citable_url("https://www.neoteo.com/a", set())


def test_assert_citable_url_accepts_cited_host():
    host = article_fetch.assert_citable_url(
        "https://www.neoteo.com/a", {"www.neoteo.com"})
    assert host == "www.neoteo.com"


def test_cache_roundtrip_and_expiry(tmp_path):
    url = "https://www.tomshardware.com/a/1"
    article_fetch.store_cache(url, tmp_path, "正文内容" * 100, "proxy")
    rec = article_fetch.load_cached(url, tmp_path)
    assert rec and rec["text"].startswith("正文")
    assert article_fetch.get_article_text(
        url, cache_dir=tmp_path)["status"] == "cached"
    # 过期缓存视为未命中
    p = article_fetch._cache_path(tmp_path, url)
    stale = json.loads(p.read_text(encoding="utf-8"))
    stale["fetched_at"] = time.time() - 1000 * 3600
    p.write_text(json.dumps(stale), encoding="utf-8")
    assert article_fetch.load_cached(url, tmp_path) is None


def test_get_article_text_gnews_shortcircuit(tmp_path):
    r = article_fetch.get_article_text(
        "https://news.google.com/rss/articles/CBMi?oc=5", cache_dir=tmp_path)
    assert r["status"] == "redirect_only"


def test_fetch_text_rejects_before_network():
    # 白名单外域名必须在发请求前被拒（Mimosa 约束：发请求前校验 host）
    try:
        article_fetch.fetch_text("https://not-in-list.example.com/a", set())
        assert False, "should have raised"
    except ValueError:
        pass
