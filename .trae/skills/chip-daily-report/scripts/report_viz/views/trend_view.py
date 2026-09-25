#!/usr/bin/env python3
"""report_viz.views.trend_view — 趋势图视图（v5.5 新增）。

把「历史走势」可视化：优先读取 delivery/quality_dashboard.json（F9 质量看板聚合，
含各期条数 / A 级占比 / X12 分级 / 自检通过率），渲染：

  A. 历史趋势折线 —— 新闻条数（蓝）与 A 级占比（绿）双折线，X 轴为各期日期
  B. 质量聚合 —— 期数 / 平均条数 / 平均 A 占比 / 自检通过率 + X12 条数分级分布条
  C. 本期环节分布 —— 5 环节新闻条数条形图（分色）
  D. 持续追踪趋势 —— 方向 / 连续期数 / Δ 变比 主题卡（复用 tk-card 样式）

quality_dashboard.json 缺失时优雅降级：仅展示 C/D（本期数据），不影响整页渲染。
"""
from __future__ import annotations

import re

from .. import parser as _p
from ._charts import (
    esc,
    fmt_date,
    fmt_ratio,
    legend_html,
    load_dashboard,
    svg_bars,
    svg_lines,
)

# 与 report_view / chain_view 保持一致的环节配色
SEG_COLORS = {
    "设计": "#2563eb",
    "制造": "#7c3aed",
    "封测": "#0891b2",
    "EDA": "#db2777",
    "材料": "#16a34a",
}

# 持续追踪 detail 方向解析：'up（连续4期）Δ +53~58% QoQ — 正文…'
_DIR_RE = re.compile(
    r"^(up|down|flat|tight|loose)\s*[（(]\s*连续\s*(\d+)\s*期[）)]\s*Δ\s*([^—–\-]+?)\s*(?:—|–|-|$)"
)
DIR_META = {
    "up": ("上行", "#dc2626"),
    "down": ("下行", "#16a34a"),
    "flat": ("平稳", "#64748b"),
    "tight": ("趋紧", "#b45309"),
    "loose": ("趋松", "#0891b2"),
}

_GRADE_STYLE = (("PASS", "#15803d"), ("WARN", "#b45309"), ("FAIL", "#b91c1c"))


def _news_total(report: dict) -> int:
    return sum(len(v) for v in report.get("segments", {}).values())


# ---------------- A 历史趋势 ----------------

def _history_block(dash: dict) -> str:
    reps = sorted(dash.get("reports", []), key=lambda r: r.get("date", ""))
    if len(reps) < 2:
        return ""
    labels = [fmt_date(r.get("date", "")) for r in reps]
    counts = [r.get("computed_news") or r.get("declared_news") or 0 for r in reps]
    ratios = [r.get("a_ratio") for r in reps]
    series = [
        {"name": "新闻条数", "color": "#2563eb", "values": counts, "fmt": lambda v: f"{v:.0f}"},
        {"name": "A 级占比", "color": "#16a34a", "values": ratios, "fmt": fmt_ratio},
    ]
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">📊 历史趋势 <span class="tr-sub">quality_dashboard · {len(reps)} 期</span></h2>
      <div class="chart-card">{svg_lines(labels, series)}{legend_html(series)}</div>
      <p class="tr-note">双轴各自独立归一化（形状可比，精确数值见数据点标注）· A 级占比按权威域名白名单对真实 URL 计算</p>
    </section>"""


# ---------------- B 质量聚合 ----------------

def _quality_block(dash: dict) -> str:
    agg = dash.get("aggregate", {})
    avg_count = agg.get("avg_news_count")
    stats = [
        ("报告期数", agg.get("report_count", "—")),
        ("平均新闻条数", f"{avg_count:.1f}" if isinstance(avg_count, (int, float)) else "—"),
        ("平均 A 级占比", fmt_ratio(agg.get("avg_computed_a_ratio"))),
        ("自检通过率", fmt_ratio(agg.get("avg_selfcheck_pass_rate"))),
    ]
    cards = "".join(
        f'<div class="wk-card"><div class="wk-num">{esc(str(v))}</div>'
        f'<div class="wk-label">{esc(lab)}</div></div>'
        for lab, v in stats
    )

    x12 = agg.get("x12_distribution", {})
    total = sum(x12.values()) or 1
    bars = []
    for grade, color in _GRADE_STYLE:
        n = x12.get(grade, 0)
        w = 100 * n / total
        bars.append(
            f'<div class="x12-row"><span class="x12-lab">{grade}</span>'
            f'<div class="x12-track"><div class="x12-fill" style="width:{w:.1f}%;background:{color}"></div></div>'
            f'<span class="x12-num">{n}</span></div>'
        )
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">🧪 质量聚合 <span class="tr-sub">跨期汇总 · 自检 / 条数分级</span></h2>
      <div class="wk-cards">{cards}</div>
      <div class="chart-card x12-card">
        <div class="x12-title">新闻条数分级（X12 软指标：15-20 条 PASS / 10-14、21-25 WARN）</div>
        {"".join(bars)}
      </div>
    </section>"""


# ---------------- C 本期环节分布 ----------------

def _segment_block(report: dict) -> str:
    segs = report.get("segments", {})
    items = []
    for seg in _p.SEG_ORDER:
        n = len(segs.get(seg) or [])
        if n:
            items.append((seg, n, SEG_COLORS.get(seg, "#334155")))
    if not items:
        return ""
    legend = legend_html([{"name": k, "color": SEG_COLORS[k]} for k, _, _ in items])
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">🧩 本期环节分布 <span class="tr-sub">设计 → 制造 → 封测 → EDA → 材料 · 共 {_news_total(report)} 条</span></h2>
      <div class="chart-card">{svg_bars(items)}{legend}</div>
    </section>"""


# ---------------- D 持续追踪趋势 ----------------

def _tracking_block(report: dict) -> str:
    items = report.get("tracking", [])
    if not items:
        return ""
    cards = []
    for it in items:
        m = _DIR_RE.search(it.get("detail") or "")
        if m:
            key, streak, delta = m.group(1), m.group(2), m.group(3).strip()
            label, color = DIR_META.get(key, (key, "#64748b"))
            tag = (
                f'<span class="tr-dir" style="color:{color};border-color:{color}">'
                f"{label} · 连续 {streak} 期</span>"
            )
            delta_html = (
                f'<p class="tk-detail tk-delta">Δ 变比：{esc(delta)}</p>' if delta else ""
            )
        else:
            tag = (
                '<span class="tr-dir" style="color:#64748b;border-color:#94a3b8">'
                "方向未标注</span>"
            )
            delta_html = ""
        cards.append(
            f'<div class="tk-card"><div class="tk-head">{tag}'
            f'<span class="tk-topic">{esc(it["topic"])}</span></div>'
            f"{delta_html}"
            f'<p class="tk-detail">{esc(it["detail"])}</p></div>'
        )
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">📈 持续追踪趋势 <span class="tr-sub">跨日记忆 · 方向 / 连续期数 / Δ 变比</span></h2>
      <div class="tk-grid">{"".join(cards)}</div>
    </section>"""


# ---------------- 装配入口 ----------------

def render(report: dict) -> str:
    blocks = []
    dash = load_dashboard()
    if dash:
        blocks.append(_history_block(dash))
        blocks.append(_quality_block(dash))
    else:
        blocks.append(
            '<div class="dim-empty">未找到 delivery/quality_dashboard.json，趋势图降级为仅本期数据'
            "（运行 quality_dashboard.py 刷新看板后自动恢复历史曲线）。</div>"
        )
    blocks.append(_segment_block(report))
    blocks.append(_tracking_block(report))
    return "".join(blocks)
