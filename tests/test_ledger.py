#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ledger — 采集账本（v9 数据系统轮）回归。

覆盖（对应 AIHOT 扩接内化真差距①②的机制化）：
  - 首采判定语义（无 found>0 记录 = 首采；账本损坏 = 守卫生效安全侧）
  - 首采守卫：超龄丢弃（按原文时间归档）/ undated 保留 / 条数封顶 / 非首采原样
  - 记账滚动裁剪 + per_day 窗口（排除首采，AIHOT 排除 backfill 同口径）
  - AIHOT 频率公式 clamp(1440/(perDay*3), 15, 60) 边界 + 降级审查判定
  - prepare_candidates 集成：ledger_path 开启时守卫+记账+gate 报告披露；
    两次运行首采标记翻转
零网络零污染：全部写 tmp_path。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MS = ROOT / "scripts" / "multi_source"
for p in (MS,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import collector  # noqa: E402
import ledger  # noqa: E402

TODAY = date(2026, 9, 29)
NOW = datetime(2026, 9, 29, 8, 0, 0)


def _mk(sid: str, published: str, title: str = "t"):
    return collector.RawItem(source_id=sid, source_name="S", tier=1, type="rss",
                             segment="制造", title=title,
                             url=f"https://example.com/{title}", published=published,
                             body="x")


# ------------------------------------------------------------
# 首采判定
# ------------------------------------------------------------
def test_first_import_semantics(tmp_path):
    p = tmp_path / "l.json"
    assert ledger.is_first_import(p, "s") is True          # 空账本 = 首采
    assert ledger.is_first_import(tmp_path / "missing_dir" / "l.json", "s") is True
    ledger.record_run(p, "s", found=0, kept=0, now=NOW)     # 拉空不算 initialized
    assert ledger.is_first_import(p, "s") is True
    ledger.record_run(p, "s", found=3, kept=3, now=NOW)     # 拉到货 → 已初始化
    assert ledger.is_first_import(p, "s") is False


def test_first_import_semantics_corrupt_ledger(tmp_path):
    p = tmp_path / "l.json"
    p.write_text("{broken json", encoding="utf-8")
    assert ledger.is_first_import(p, "s") is True           # 损坏 → 守卫生效（安全侧）


# ------------------------------------------------------------
# 首采守卫
# ------------------------------------------------------------
def test_guard_drops_old_keeps_undated(tmp_path):
    p = tmp_path / "l.json"
    old = (TODAY - timedelta(days=60)).isoformat()
    fresh = TODAY.isoformat()
    items = ([_mk("s", old, f"old{i}") for i in range(3)]
             + [_mk("s", fresh, f"fresh{i}") for i in range(5)]
             + [_mk("s", "", "undated")])                    # undated 混在尾部
    kept, stats = ledger.first_import_guard(p, "s", items, today=TODAY)
    assert stats["first_import"] is True
    assert stats["found"] == 9 and stats["kept"] == 6 and stats["dropped_old"] == 3
    assert stats["capped"] is False
    assert [i.title for i in kept] == [f"fresh{i}" for i in range(5)] + ["undated"]


def test_guard_caps_on_first_import(tmp_path):
    p = tmp_path / "l.json"
    fresh = TODAY.isoformat()
    items = [_mk("s", fresh, f"n{i}") for i in range(45)]
    kept, stats = ledger.first_import_guard(p, "s", items, today=TODAY)
    assert stats["kept"] == 30 and stats["capped"] is True and stats["dropped_old"] == 0


def test_guard_noop_when_not_first_import(tmp_path):
    p = tmp_path / "l.json"
    old = (TODAY - timedelta(days=60)).isoformat()
    ledger.record_run(p, "s", found=1, kept=1, now=NOW)     # 已初始化
    items = [_mk("s", old, "ancient"), _mk("s", "", "u")]
    kept, stats = ledger.first_import_guard(p, "s", items, today=TODAY)
    assert stats["first_import"] is False
    assert kept == items and len(kept) == 2                 # 原样返回，超龄也不丢


# ------------------------------------------------------------
# 记账 / 窗口 / 裁剪
# ------------------------------------------------------------
def test_per_day_window_excludes_first_import(tmp_path):
    p = tmp_path / "l.json"
    ledger.record_run(p, "s", found=4, kept=4, now=NOW)                          # 09-29 入窗
    ledger.record_run(p, "s", found=3, kept=3, now=NOW - timedelta(days=6))      # 09-23 入窗
    ledger.record_run(p, "s", found=5, kept=5, first_import=True,
                      now=NOW - timedelta(days=1))                               # 首采排除
    ledger.record_run(p, "s", found=9, kept=9, now=NOW - timedelta(days=7))      # 09-22 出窗
    assert ledger.per_day(p, "s", now=NOW) == (4 + 3) / 7.0


def test_record_run_trims_beyond_keep_days(tmp_path):
    p = tmp_path / "l.json"
    ledger.record_run(p, "s", found=1, kept=1,
                      now=datetime(2026, 5, 1))              # >90 天前
    ledger.record_run(p, "s", found=2, kept=2, now=NOW)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert [r["found"] for r in data["runs"]] == [2]         # 旧记录被裁剪


def test_collect_guard_preserves_order_and_summarizes(tmp_path):
    p = tmp_path / "l.json"
    fresh = TODAY.isoformat()
    items = [_mk("a", fresh, "a1"), _mk("b", fresh, "b1"), _mk("a", fresh, "a2")]
    kept, summary = ledger.collect_guard(items, p, today=TODAY)
    assert [i.title for i in kept] == ["a1", "b1", "a2"]     # 分组守卫后顺序不变
    assert summary["sources"] == 2
    assert sorted(summary["first_import"]) == ["a", "b"]
    assert summary["dropped_old"] == 0
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2                            # 逐源各记一条


# ------------------------------------------------------------
# AIHOT 公式测算
# ------------------------------------------------------------
def test_suggest_no_record_and_silent(tmp_path):
    p = tmp_path / "l.json"
    assert ledger.suggest(p, "s", now=NOW)["verdict"] == "无记录（新源或未接线）"
    ledger.record_run(p, "s", found=0, kept=0, now=NOW)
    out = ledger.suggest(p, "s", now=NOW)
    assert out["per_day"] == 0.0
    assert "降级审查" in out["verdict"]
    assert out["target_interval_minutes"] is None


def test_suggest_first_import_only_not_silent(tmp_path):
    """首采当天：只有首采记录≠静默——不许对新源误报降级审查。"""
    p = tmp_path / "l.json"
    ledger.record_run(p, "s", found=25, kept=25, first_import=True, now=NOW)
    out = ledger.suggest(p, "s", now=NOW)
    assert out["per_day"] == 0.0                              # 首采排除，速率仍 0
    assert "首采期" in out["verdict"] and "降级" not in out["verdict"]


def test_suggest_clamp_boundaries(tmp_path):
    p = tmp_path / "l.json"
    # per_day=10 → 1440/30=48
    ledger.record_run(p, "s", found=70, kept=70, now=NOW)
    assert ledger.suggest(p, "s", now=NOW)["target_interval_minutes"] == 48
    # per_day≈0.29 → 1680 → 夹到上限 60；verdict=低产
    ledger.record_run(p, "q", found=2, kept=2, now=NOW)
    out_q = ledger.suggest(p, "q", now=NOW)
    assert out_q["target_interval_minutes"] == 60
    assert out_q["verdict"] == "低产——观察期"
    # per_day=32 → 1440/96=15 → 下限
    ledger.record_run(p, "m", found=224, kept=224, now=NOW)
    assert ledger.suggest(p, "m", now=NOW)["target_interval_minutes"] == 15


# ------------------------------------------------------------
# prepare_candidates 集成（ledger_path 开启/关闭）
# ------------------------------------------------------------
def _load_pc():
    spec = importlib.util.spec_from_file_location(
        "prepare_candidates", MS / "prepare_candidates.py")
    pc = importlib.util.module_from_spec(spec)
    sys.modules["prepare_candidates"] = pc
    spec.loader.exec_module(pc)
    return pc


def test_pipeline_with_ledger_two_runs(tmp_path, monkeypatch):
    """开账本：首采守卫生效+gate 报告披露+二次运行首采标记翻转。"""
    pc = _load_pc()
    old = (date.today() - timedelta(days=60)).isoformat()
    fresh = date.today().isoformat()
    items = ([_mk("t", old, f"old{i}") for i in range(3)]
             + [_mk("t", fresh, f"fresh{i}") for i in range(28)]
             + [_mk("t", "", "rogue_homepage")])
    monkeypatch.setattr(pc.collector, "collect",
                        lambda mode="online", scope=None: list(items))
    lp = tmp_path / "ledger.json"

    r1 = pc.run(out_file=tmp_path / "g1.json", ledger_path=lp, enrich_top=0)
    assert r1["ok"] is True
    ls1 = r1["gate"]["stats"]["ledger"]
    assert ls1["first_import"] == ["t"] and ls1["dropped_old"] == 3
    assert ls1["sources"] == 1

    r2 = pc.run(out_file=tmp_path / "g2.json", ledger_path=lp, enrich_top=0)
    ls2 = r2["gate"]["stats"]["ledger"]
    assert ls2["first_import"] == []                          # 已初始化 → 守卫不丢
    data = json.loads(lp.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 2                             # 两次运行各记一条
    assert data["runs"][0]["found"] == 32 and data["runs"][0]["kept"] == 29


def test_pipeline_ledger_disabled_by_default(tmp_path, monkeypatch):
    """ledger_path=None（默认）：不守卫不记账——存量 monkeypatch 测试零影响。"""
    pc = _load_pc()
    default = ledger.DEFAULT_LEDGER
    before = default.read_text(encoding="utf-8") if default.exists() else None
    old = (date.today() - timedelta(days=60)).isoformat()
    items = [_mk("t", old, "ancient")]
    monkeypatch.setattr(pc.collector, "collect",
                        lambda mode="online", scope=None: list(items))
    r = pc.run(out_file=tmp_path / "g.json", enrich_top=0)
    assert r["ok"] is True
    assert "ledger" not in r["gate"]["stats"]
    after = default.read_text(encoding="utf-8") if default.exists() else None
    assert before == after                                   # 默认路径零写入
