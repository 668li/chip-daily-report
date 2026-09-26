#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_admission — 采集准入前移（P1-C）的对抗样本回归。

纪律（v7 复盘 ⑦.2：内容分类门必须带对抗样本集）：
  - 域名根（https://www.cnbc.com）→ 拒
  - 仅斜杠（https://www.cnbc.com/）→ 拒
  - 空 URL / 缺字段 → 拒
  - 正常文章级 URL → 过
  - 管线集成：混入首页级条目时，候选池不含它且 admission_dropped 计数正确

离线测试：monkeypatch collector，零网络依赖。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MS = ROOT / "scripts" / "multi_source"
for p in (MS,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cleaner  # noqa: E402
import collector  # noqa: E402


def test_is_article_url_adversarial():
    # 拒：域名根 / 仅斜杠 / 空 / 纯空白
    assert not cleaner.is_article_url("https://www.cnbc.com")
    assert not cleaner.is_article_url("https://www.cnbc.com/")
    assert not cleaner.is_article_url("")
    assert not cleaner.is_article_url("   ")
    assert not cleaner.is_article_url(None)  # None 不炸
    # 过：真实文章级路径
    assert cleaner.is_article_url("https://www.cnbc.com/2026/09/25/chip-news.html")
    assert cleaner.is_article_url("https://www.trendforce.com/news/2026-09-25-coyos/")
    # 过：带 query 的文章页
    assert cleaner.is_article_url("https://x.com/a/b?id=1")


def _mk(title, url):
    return collector.RawItem(source_id="t", source_name="T", tier=1, type="rss",
                             segment="制造", title=title, url=url,
                             published="2026-09-25", body="x")


def test_admit_article_level_splits():
    cleaned = cleaner.normalize([_mk("好文章", "https://a.com/x/1"),
                                 _mk("首页", "https://a.com")])
    admitted, dropped = cleaner.admit_article_level(cleaned)
    assert [c["title"] for c in admitted] == ["好文章"]
    assert [c["title"] for c in dropped] == ["首页"]


def test_pipeline_admission_drops_homepage(tmp_path, monkeypatch):
    """集成：混入 1 条首页级条目 → 不入候选、计数与披露正确。"""
    spec = importlib.util.spec_from_file_location("prepare_candidates", MS / "prepare_candidates.py")
    pc = importlib.util.module_from_spec(spec)
    sys.modules["prepare_candidates"] = pc
    spec.loader.exec_module(pc)

    base = collector.load_offline({})
    rogue = base[:1] + [_mk("伪追溯首页条目", "https://www.example-news.com")]
    monkeypatch.setattr(pc.collector, "collect", lambda mode="online", scope=None: rogue)

    out = tmp_path / "gate_report.json"
    result = pc.run(out_file=out)
    assert result["ok"] is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["stats"]["admission_dropped"] == 1
    dropped_titles = [d["title"] for d in data.get("rejected_by_admission", [])]
    assert "伪追溯首页条目" in dropped_titles
    for c in data["candidates"]:
        assert c.get("url", "") is not None
