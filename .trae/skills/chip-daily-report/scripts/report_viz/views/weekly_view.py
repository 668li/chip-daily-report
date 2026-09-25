#!/usr/bin/env python3
"""report_viz.views.weekly_view — 周报对比视图（v5.5 新增）。

扫描项目根目录全部「芯片行业日报_YYYYMMDD.md」，用 parser 逐一解析后跨期对比：

  A. 概览统计卡 —— 期数 / 累计新闻 / 平均条数 / 平均 A 级占比 / 全环节覆盖期数
  B. 逐期对比表 —— 日期 / 新闻条数 / A 级占比（迷你条）/ 环节覆盖点阵 / 自检通过 / X12 等级 / 追踪主题数 / 催化剂数
  C. 条数 × 质量走势 —— 新闻条数与 A 级占比双折线
  D. 环节结构对比 —— 各期 5 环节条数水平堆叠条
  E. 持续追踪跨期对比 —— 主题 / 方向 / 连续期数（仅含追踪小节的期）

历史期（v5.3 之前）没有持续追踪 / 催化剂小节，对比表相应置「—」，不报错。
X12 等级优先取 delivery/quality_dashboard.json（F9 维护），缺失时从自检行推断。
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
    svg_lines,
    svg_stacked_bars,
)

MD_RE = re.compile(r"芯片行业日报_(\d{8})\.md$")

SEG_COLORS = {
    "设计": "#2563eb",
    "制造": "#7c3aed",
    "封测": "#0891b2",
    "EDA": "#db2777",
    "材料": "#16a34a",
}

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

_X12_CLS = {"PASS": "sc-pass", "WARN": "sc-warn", "FAIL": "sc-fail"}


# ---------------- 数据收集 ----------------

def _news_total(r: dict) -> int:
    return sum(len(v) for v in r.get("segments", {}).values())


def _a_ratio(r: dict):
    st = r.get("source_stats", {})
    a, b = st.get("A", 0), st.get("B", 0)
    return a / (a + b) if (a + b) else None


def _coverage(r: dict) -> int:
    segs = r.get("segments", {})
    return sum(1 for s in _p.SEG_ORDER if segs.get(s))


def _x12_from_selfcheck(r: dict) -> str:
    for x in r.get("selfcheck", []):
        if x.get("num") == 12 or "条数" in x.get("name", ""):
            return x.get("result", "—")
    return "—"


def _collect_reports() -> list:
    found = []
    for p in sorted(_p.ROOT.glob("芯片行业日报_*.md")):
        m = MD_RE.match(p.name)
        if not m:
            continue
        try:
            r = _p.parse_report(p)
        except Exception:
            continue
        r["_date"] = m.group(1)
        r["_file"] = p.name
        found.append(r)
    found.sort(key=lambda r: r["_date"])
    return found


# ---------------- A 概览 ----------------

def _overview_cards(reps: list) -> str:
    news_list = [_news_total(r) for r in reps]
    total_news = sum(news_list)
    ratios = [_a_ratio(r) for r in reps]
    ok = [x for x in ratios if x is not None]
    avg_ratio = sum(ok) / len(ok) if ok else None
    full = sum(1 for r in reps if _coverage(r) == 5)
    cards = [
        ("报告期数", len(reps)),
        ("累计新闻", total_news),
        ("平均条数", f"{total_news / len(reps):.1f}"),
        ("平均 A 级占比", fmt_ratio(avg_ratio)),
        ("全环节覆盖", f"{full}/{len(reps)} 期"),
    ]
    html = "".join(
        f'<div class="wk-card"><div class="wk-num">{esc(str(v))}</div>'
        f'<div class="wk-label">{esc(lab)}</div></div>'
        for lab, v in cards
    )
    span = f"{fmt_date(reps[0]['_date'])} ~ {fmt_date(reps[-1]['_date'])}"
    return (
        f'<section class="tr-block"><h2 class="tr-title">📋 概览 '
        f'<span class="tr-sub">{len(reps)} 期 · {span}</span></h2>'
        f'<div class="wk-cards">{html}</div></section>'
    )


# ---------------- B 逐期对比表 ----------------

def _compare_table(reps: list) -> str:
    dash = load_dashboard()
    dash_x12 = {}
    if dash:
        for x in dash.get("reports", []):
            dash_x12[x.get("date")] = x.get("x12_grade")

    trs = []
    for r in reps:
        segs = r.get("segments", {})
        n = _news_total(r)
        ratio = _a_ratio(r)

        dots = "".join(
            f'<i class="cov-dot" style="background:{SEG_COLORS[s] if segs.get(s) else "#e2e8f0"}" '
            f'title="{esc(s)}{" ✓" if segs.get(s) else " ✗"}"></i>'
            for s in _p.SEG_ORDER
        )

        ratio_html = "—"
        if ratio is not None:
            w = max(2.0, ratio * 100)
            ratio_html = (
                f'<div class="mini-bar"><div class="mini-fill" style="width:{w:.0f}%"></div></div>'
                f'<span class="mini-val">{fmt_ratio(ratio)}</span>'
            )

        sc = r.get("selfcheck", [])
        if sc:
            passed = sum(1 for x in sc if x["result"] == "PASS")
            sc_html = f"{passed}/{len(sc)}"
        else:
            sc_html = "—"
        x12 = dash_x12.get(r["_date"]) or _x12_from_selfcheck(r)
        cls = _X12_CLS.get(x12, "")
        x12_html = f'<span class="sc-pill {cls}">{esc(str(x12))}</span>' if cls else esc(str(x12))
        tk = len(r.get("tracking", [])) or "—"
        ct = len(r.get("catalysts", [])) or "—"

        trs.append(
            f'<tr><td class="ct-date">{fmt_date(r["_date"])}</td>'
            f"<td><b>{n}</b></td>"
            f"<td>{ratio_html}</td>"
            f'<td style="white-space:nowrap">{dots}</td>'
            f"<td>{sc_html}</td>"
            f"<td>{x12_html}</td>"
            f"<td>{tk}</td><td>{ct}</td></tr>"
        )
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">🗂 逐期对比 <span class="tr-sub">条数 · 来源质量 · 环节覆盖 · 自检 · 追踪/催化剂</span></h2>
      <div class="chart-card">
        <table class="wk-table">
          <thead><tr><th>日期</th><th>新闻</th><th>A 级占比</th><th>环节覆盖</th>
            <th>自检通过</th><th>X12</th><th>追踪</th><th>催化剂</th></tr></thead>
          <tbody>{"".join(trs)}</tbody>
        </table>
      </div>
    </section>"""


# ---------------- C 条数 × 质量走势 ----------------

def _counts_ratio_chart(reps: list) -> str:
    labels = [fmt_date(r["_date"]) for r in reps]
    counts = [_news_total(r) for r in reps]
    ratios = [_a_ratio(r) for r in reps]
    series = [
        {"name": "新闻条数", "color": "#2563eb", "values": counts, "fmt": lambda v: f"{v:.0f}"},
        {"name": "A 级占比", "color": "#16a34a", "values": ratios, "fmt": fmt_ratio},
    ]
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">📉 条数 × 质量走势 <span class="tr-sub">双轴独立归一化 · 精确数值见标注</span></h2>
      <div class="chart-card">{svg_lines(labels, series)}{legend_html(series)}</div>
    </section>"""


# ---------------- D 环节结构对比 ----------------

def _segment_stack(reps: list) -> str:
    rows = []
    for r in reps:
        segs = r.get("segments", {})
        parts = []
        for s in _p.SEG_ORDER:
            n = len(segs.get(s) or [])
            if n:
                parts.append((n, SEG_COLORS[s], s))
        rows.append(
            {"label": fmt_date(r["_date"]), "total": sum(p[0] for p in parts), "parts": parts}
        )
    legend = legend_html([{"name": s, "color": SEG_COLORS[s]} for s in _p.SEG_ORDER])
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">🧩 环节结构对比 <span class="tr-sub">堆叠长度 = 各环节新闻条数（按全表最大值归一）</span></h2>
      <div class="chart-card">{svg_stacked_bars(rows)}{legend}</div>
    </section>"""


# ---------------- E 持续追踪跨期对比 ----------------

def _tracking_compare(reps: list) -> str:
    rows = []
    for r in reps:
        for it in r.get("tracking", []):
            m = _DIR_RE.search(it.get("detail") or "")
            if m:
                key, streak = m.group(1), m.group(2)
                label, color = DIR_META.get(key, (key, "#64748b"))
            else:
                label, streak, color = "—", "—", "#94a3b8"
            rows.append((fmt_date(r["_date"]), it["topic"], label, streak, color, it["detail"]))
    if not rows:
        return ""
    trs = "".join(
        f'<tr><td class="ct-date">{esc(d)}</td><td class="wk-topic">{esc(t)}</td>'
        f'<td><span class="tr-dir" style="color:{color};border-color:{color}">{esc(lab)}</span></td>'
        f"<td>{esc(st)}</td><td class=\"wk-detail\">{esc(det)}</td></tr>"
        for d, t, lab, st, color, det in rows
    )
    return f"""
    <section class="tr-block">
      <h2 class="tr-title">🔁 持续追踪跨期对比 <span class="tr-sub">主题 · 方向 · 连续期数（v5.3 起收录）</span></h2>
      <div class="chart-card">
        <table class="wk-table">
          <thead><tr><th>日期</th><th>主题</th><th>方向</th><th>连续</th><th>说明</th></tr></thead>
          <tbody>{trs}</tbody>
        </table>
      </div>
    </section>"""


# ---------------- 装配入口 ----------------

def render(report: dict) -> str:
    """渲染周报对比视图（扫描全量日报 md，report 参数仅作占位一致性）。"""
    reps = _collect_reports()
    if not reps:
        return '<div class="dim-empty">未找到任何 芯片行业日报_*.md，无法跨期对比。</div>'
    return "".join(
        [
            _overview_cards(reps),
            _compare_table(reps),
            _counts_ratio_chart(reps),
            _segment_stack(reps),
            _tracking_compare(reps),
        ]
    )
