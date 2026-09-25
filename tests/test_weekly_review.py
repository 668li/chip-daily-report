#!/usr/bin/env python3
"""weekly_review.py 回归测试（迭代5 · 认知深化 B）。

覆盖：
  1. collect_reports 按日期范围筛选（含 filename 匹配）
  2. build_signal_matrix 演进矩阵 + 反转 change 描述
  3. aggregate_reports 跨期聚合
  4. collect_catalysts 跨期去重
  5. render_md 结构断言（六大节）
  6. render_html 结构断言（曲线 / 台账 / 认知 / 风险 / 催化剂）
  7. 无日报 / 无信号历史降级不报错
"""
import sys
from pathlib import Path
from datetime import date

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import weekly_review as wr

# ---------------- 1 collect_reports ----------------

MINI_REPORT = """# 芯片行业日报 — 2026年8月9日

> 生成时间：2026-08-09 10:00
> 覆盖范围：2026-08-07 ~ 2026-08-09
> 新闻总数：2

## 今日要点
- 要点一

## 设计
- **英伟达砍 HBM** — 摘要正文一句话。 | 来源: [示例](https://example.com/a) | 2026-08-09

## 自检结果

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 产业链完整性 | PASS | ok |

**来源分级统计**：
- A级（权威）：example.com = 1 条
- B级（聚合）：无
- A级占比：100% ≥ 30% ✓
"""


def _write_report(tmp_path: Path, name: str) -> Path:
    p = tmp_path / name
    p.write_text(MINI_REPORT, encoding="utf-8")
    return p


def test_collect_reports_filters_by_range(tmp_path):
    _write_report(tmp_path, "芯片行业日报_20260808.md")
    _write_report(tmp_path, "芯片行业日报_20260809.md")
    _write_report(tmp_path, "芯片行业日报_20260720.md")
    reps = wr.collect_reports(tmp_path, date(2026, 8, 1), date(2026, 8, 9))
    assert [r["_date"] for r in reps] == ["20260808", "20260809"]


def test_collect_ignores_bad_names(tmp_path):
    _write_report(tmp_path, "芯片行业日报_20260809.md")
    (tmp_path / "not_report.md").write_text("# x", encoding="utf-8")
    reps = wr.collect_reports(tmp_path, date(2026, 8, 1), date(2026, 8, 31))
    assert len(reps) == 1


def test_week_range():
    start, end = wr.week_range(date(2026, 8, 9))  # 周日
    assert start == date(2026, 8, 3)  # 周一
    assert end == date(2026, 8, 9)
    start2, _ = wr.week_range(date(2026, 8, 4))  # 周二
    assert start2 == date(2026, 8, 3)


# ---------------- 2 build_signal_matrix ----------------

HISTORY = [
    {"date": "20260808", "topics": [
        {"topic": "HBM", "direction": "up", "streak": 3, "signal": "高/利好/正面"},
        {"topic": "封装", "direction": "tight", "streak": 2, "signal": "高/利好/正面"},
    ]},
    {"date": "20260809", "topics": [
        {"topic": "HBM", "direction": "down", "streak": 1, "signal": "高/利空/负面"},
        {"topic": "封装", "direction": "tight", "streak": 4, "signal": "高/利好/正面"},
    ]},
]


def test_signal_matrix_reversal_detected():
    dates, matrix = wr.build_signal_matrix(HISTORY)
    assert dates == ["20260808", "20260809"]
    assert matrix["HBM"]["levels"] == [2.0, -2.0]  # up=2, down=-2
    assert "反转" in matrix["HBM"]["change"]
    assert "延续 tight" in matrix["封装"]["change"] and "2→4" in matrix["封装"]["change"]


def test_signal_matrix_missing_day():
    dates, matrix = wr.build_signal_matrix([HISTORY[0]])
    assert dates == ["20260808"]
    assert matrix["HBM"]["levels"] == [2.0]
    assert matrix["HBM"]["signals"] == ["up（连续 3 期）"]


def test_signal_matrix_empty_history():
    dates, matrix = wr.build_signal_matrix([])
    assert dates == [] and matrix == {}


# ---------------- 3 aggregate_reports ----------------

def test_aggregate(tmp_path):
    p = _write_report(tmp_path, "芯片行业日报_20260809.md")
    reps = wr.collect_reports(tmp_path, date(2026, 8, 1), date(2026, 8, 31))
    agg = wr.aggregate_reports(reps)
    assert agg["news"] >= 1
    assert agg["sc_total"] >= 1 and agg["sc_rate"] == 1.0


def test_aggregate_empty():
    agg = wr.aggregate_reports([])
    assert agg["news"] == 0 and agg["avg_news"] == 0
    assert agg["avg_ratio"] is None and agg["sc_rate"] is None


# ---------------- 4 collect_catalysts 去重 ----------------

def test_catalysts_dedup():
    reps = [
        {"_date": "20260808", "catalysts": [
            {"date": "2026-08-10", "event": "台积电营收", "segment": "制造", "importance": "高", "source": "a"},
        ]},
        {"_date": "20260809", "catalysts": [
            {"date": "2026-08-10", "event": "台积电营收", "segment": "制造", "importance": "高", "source": "a"},  # 重复
            {"date": "2026-08-12", "event": "美光大会", "segment": "制造", "importance": "高", "source": "b"},
        ]},
    ]
    cats = wr.collect_catalysts(reps)
    assert [c["event"] for c in cats] == ["台积电营收", "美光大会"]


# ---------------- 5 render_md 结构 ----------------

def test_render_md_sections(tmp_path, monkeypatch):
    p = _write_report(tmp_path, "芯片行业日报_20260809.md")
    reps = wr.collect_reports(tmp_path, date(2026, 8, 1), date(2026, 8, 31))
    dates, matrix = wr.build_signal_matrix(HISTORY)
    ctx = {
        "reps": reps,
        "start": date(2026, 8, 3),
        "end": date(2026, 8, 9),
        "agg": wr.aggregate_reports(reps),
        "dates": dates,
        "matrix": matrix,
        "catalysts": wr.collect_catalysts(reps),
    }
    md = wr.render_md(ctx)
    for sec in ("本周概览", "本周主线叙事", "信号演进台账", "认知素材库",
                "风险与机会再评估", "下周前瞻催化剂"):
        assert f"## " in md and sec in md
    assert "HBM" in md and "反转" in md


def test_render_md_empty_week():
    ctx = {
        "reps": [], "start": date(2026, 8, 3), "end": date(2026, 8, 9),
        "agg": wr.aggregate_reports([]), "dates": [], "matrix": {},
        "catalysts": [],
    }
    md = wr.render_md(ctx)
    assert "尚无历史数据" in md  # 信号历史降级文案
    assert "0" in md  # 期数 0


# ---------------- 6 render_html 结构 ----------------

def test_render_html_structure(tmp_path):
    p = _write_report(tmp_path, "芯片行业日报_20260809.md")
    reps = wr.collect_reports(tmp_path, date(2026, 8, 1), date(2026, 8, 31))
    dates, matrix = wr.build_signal_matrix(HISTORY)
    ctx = {
        "reps": reps, "start": date(2026, 8, 3), "end": date(2026, 8, 9),
        "agg": wr.aggregate_reports(reps), "dates": dates, "matrix": matrix,
        "catalysts": wr.collect_catalysts(reps),
    }
    html = wr.render_html(ctx)
    assert "<svg" in html and "viewBox" in html
    assert "信号强度曲线" in html and "⚠" in html
    assert "wk-card" in html and "wk-table" in html
    assert "认知素材库" in html and "风险与机会再评估" in html
    assert "下周前瞻催化剂" in html


def test_render_html_no_signal():
    ctx = {
        "reps": [], "start": date(2026, 8, 3), "end": date(2026, 8, 9),
        "agg": wr.aggregate_reports([]), "dates": [], "matrix": {},
        "catalysts": [],
    }
    html = wr.render_html(ctx)
    assert "暂无历史" in html  # 优雅降级


# ---------------- 7 svg_signal_lines 基础 ----------------

def test_svg_signal_lines_fixed_axis():
    from report_viz.views._charts import svg_signal_lines
    svg = svg_signal_lines(
        ["08-08", "08-09"],
        [{"name": "HBM", "color": "#2563eb", "values": [2.0, -2.0], "labels": ["上行", "下行"]}],
    )
    assert "⚠" in svg  # 反转标记
    assert 'y1="122.0"' in svg  # 固定量纲：0 轴在绘图区正中（pad_t + ph/2）


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
