#!/usr/bin/env python3
"""weekly_review.py —— 周度复盘聚合器（迭代5 · 认知深化 B）。

把「每日信息」升级为「认知资产」：聚合最近一个自然周（周一~截止日）的全部
日报产物，生成两份周度复盘文档：
  - delivery/芯片行业周度复盘_YYYYMMDD.md   （Markdown 认知资产，洞察区留 AI 润色）
  - delivery/芯片行业周度复盘_YYYYMMDD.html （单文件 HTML：概览卡 + 信号强度曲线 + 台账）

数据源（全部为已有产物，零网络依赖，任一元数据缺失自动降级）：
  1. 根目录 芯片行业日报_*.md        —— parser 解析（今日要点/环节/深度解读/未来借鉴/催化剂/自检）
  2. state/signal_history.json       —— 信号历史累积（scripts/signal_history.py 维护）
  3. delivery/quality_dashboard.json —— 质量聚合（scripts/quality_dashboard.py 维护，可选）

CLI：python scripts/weekly_review.py [--end YYYYMMDD] [--days N] [--out DIR] [--insights FILE]
  --end      截止日，默认今天；周范围 = 该日所在周的周一 ~ 该日
  --days     覆盖默认自然周：取截止日前 N 天内（含）的日报（调试/薄周用）
  --out      输出目录，默认 delivery/
  --insights Step 7 AI 洞察文件（纯文本，每行一条本周主线，空行分段）：
             注入到 md「本周主线叙事」洞察区与 html 主线区，保持两产物同步
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from report_viz import CSS as REPORT_CSS
from report_viz import parser as _p
from report_viz.views._charts import (
    DIRECTION_LEVEL,
    DIRECTION_LABEL,
    esc,
    fmt_date,
    fmt_ratio,
    legend_html,
    load_dashboard,
    svg_signal_lines,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
MD_RE = re.compile(r"芯片行业日报_(\d{8})\.md$")
REVIEW_NAME = "芯片行业周度复盘"

SEG_COLORS = {
    "设计": "#2563eb",
    "制造": "#7c3aed",
    "封测": "#0891b2",
    "EDA": "#db2777",
    "材料": "#16a34a",
}


# ---------------- 数据收集 ----------------

def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def week_range(end: date) -> tuple[date, date]:
    """截止日所在自然周：[周一, 截止日]。"""
    monday = end - timedelta(days=end.weekday())
    return monday, end


def collect_reports(root: Path, start: date, end: date) -> list[dict]:
    """扫描 root 下日报 md，取日期在 [start, end] 内的期（按日期升序）。"""
    found = []
    for p in sorted(root.glob("芯片行业日报_*.md")):
        m = MD_RE.match(p.name)
        if not m:
            continue
        d = parse_date(m.group(1))
        if not (start <= d <= end):
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


def load_signal_history() -> list:
    try:
        data = json.loads((STATE_DIR / "signal_history.json").read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def build_signal_matrix(history: list) -> tuple[list, dict]:
    """把 signal_history 转成主题演进矩阵。

    返回 (dates, matrix)：
      dates:  所有出现过的日期（升序）
      matrix: {topic: {"levels":[...], "labels":[...], "signals":[...], "change": str}}
    change 为本周变化摘要：方向反转标 ⚠，延续则记 streak 走势。
    """
    dates = sorted({h.get("date") for h in history if h.get("date")})
    by_topic: dict[str, dict[str, dict]] = {}
    for h in history:
        for t in h.get("topics") or []:
            topic = (t.get("topic") or "").strip()
            if topic:
                by_topic.setdefault(topic, {})[h["date"]] = t

    matrix = {}
    for topic, by_date in by_topic.items():
        levels, labels, signals = [], [], []
        for d in dates:
            t = by_date.get(d)
            if t:
                direction = (t.get("direction") or "").lower()
                levels.append(DIRECTION_LEVEL.get(direction, 0.0))
                labels.append(DIRECTION_LABEL.get(direction, direction or "—"))
                signals.append(f"{direction or '—'}（连续 {t.get('streak', 1)} 期）")
            else:
                levels.append(None)
                labels.append("")
                signals.append("—")
        change = _describe_change(by_date, dates)
        matrix[topic] = {"levels": levels, "labels": labels, "signals": signals, "change": change}
    return dates, matrix


def _describe_change(by_date: dict, dates: list) -> str:
    """本周变化摘要：首个与最后一个快照比较。"""
    entries = [(d, by_date[d]) for d in dates if d in by_date]
    if len(entries) < 2:
        if len(entries) == 1:
            d, t = entries[0]
            return f"{fmt_date(d)} 纳入追踪（{t.get('direction')}，连续 {t.get('streak', 1)} 期）"
        return "本周无快照"
    (_, first), (_, last) = entries[0], entries[-1]
    fd, ld = first.get("direction"), last.get("direction")
    if fd != ld:
        return f"⚠ 方向反转：{fd} → {ld}（{fmt_date(dates[0])}~{fmt_date(dates[-1])}）"
    fs, ls = first.get("streak"), last.get("streak")
    if ls > fs:
        return f"延续 {ld}，streak {fs}→{ls}"
    if ls < fs:
        return f"{ld} 但 streak 回落 {fs}→{ls}（中断后重启）"
    return f"延续 {ld}（连续 {ls} 期）"


def aggregate_reports(reps: list) -> dict:
    """跨期聚合质量 / 结构指标。"""
    totals = {"news": 0, "ratio_ok": [], "full_cov": 0, "sc_pass": [], "sc_total": []}
    for r in reps:
        n = sum(len(v) for v in r.get("segments", {}).values())
        totals["news"] += n
        st = r.get("source_stats", {})
        a, b = st.get("A", 0), st.get("B", 0)
        if a + b:
            totals["ratio_ok"].append(a / (a + b))
        totals["full_cov"] += int(sum(1 for s in _p.SEG_ORDER if r.get("segments", {}).get(s)) == 5)
        sc = r.get("selfcheck", [])
        if sc:
            totals["sc_pass"].append(sum(1 for x in sc if x["result"] == "PASS"))
            totals["sc_total"].append(len(sc))
    return {
        "news": totals["news"],
        "avg_news": totals["news"] / len(reps) if reps else 0,
        "avg_ratio": (sum(totals["ratio_ok"]) / len(totals["ratio_ok"])
                      if totals["ratio_ok"] else None),
        "full_cov": totals["full_cov"],
        "sc_pass": sum(totals["sc_pass"]),
        "sc_total": sum(totals["sc_total"]),
        "sc_rate": (sum(totals["sc_pass"]) / sum(totals["sc_total"])
                    if totals["sc_total"] else None),
    }


def collect_catalysts(reps: list) -> list[dict]:
    """聚合各期催化剂小节（按日期事件去重，日期升序）。"""
    seen = set()
    out = []
    for r in reps:
        for c in r.get("catalysts", []):
            key = (c.get("date"), c.get("event"))
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    out.sort(key=lambda c: str(c.get("date", "")))
    return out


# ---------------- Markdown 渲染 ----------------

def _md_rows(agg: dict, reps: list, start: date, end: date) -> str:
    rows = [
        ("报告期数", f"{len(reps)}"),
        ("覆盖日期", f"{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')}"),
        ("新闻总数", f"{agg['news']} 条（平均 {agg['avg_news']:.1f} 条/期）"),
        ("平均 A 级占比", fmt_ratio(agg["avg_ratio"])),
        ("全环节覆盖", f"{agg['full_cov']}/{len(reps)} 期"),
        ("自检通过率", f"{fmt_ratio(agg['sc_rate'])}（{agg['sc_pass']}/{agg['sc_total']} 项）"),
    ]
    return "\n".join(f"| {k} | {v} |" for k, v in rows)


def _md_insights(insights: list) -> str:
    if not insights:
        return ""
    lines = "\n".join(f"- {t}" for t in insights)
    return f"""
### 本周主线（AI 洞察 · Step 7）

{lines}
"""


def _md_highlights(reps: list) -> str:
    blocks = []
    for r in reps:
        hls = r.get("highlights") or []
        if not hls:
            continue
        items = "\n".join(f"  - {h}" for h in hls[:3])
        blocks.append(f"**{fmt_date(r['_date'])}**\n{items}")
    return "\n\n".join(blocks) if blocks else "（本周各期无今日要点小节）"


def _md_signal_table(dates: list, matrix: dict) -> str:
    if not dates:
        return "（signal_history.json 尚无历史数据 —— 从今日起每日 Step 6 运行 signal_history.py 自动累积）"
    head = "| 主题 | " + " | ".join(fmt_date(d) for d in dates) + " | 本周变化 |"
    sep = "|---|" + "---|" * len(dates) + "---|"
    rows = []
    for topic, m in matrix.items():
        cells = " | ".join(m["signals"])
        rows.append(f"| {topic} | {cells} | {m['change']} |")
    return "\n".join([head, sep] + rows)


def _md_cognition(reps: list) -> str:
    """认知素材库：各期深度解读标题 + 未来借鉴条目。"""
    blocks = []
    for r in reps:
        parts = []
        for dd in r.get("deep_dive", []):
            t = dd.get("title") or ""
            parts.append(f"  - 解读：{t}")
        fl = r.get("future_lessons", [])
        for f in fl:
            cat = f.get("category") or ""
            parts.append(f"  - [{cat}] {f.get('text')}")
        if parts:
            blocks.append(f"**{fmt_date(r['_date'])}**\n" + "\n".join(parts))
    return "\n\n".join(blocks) if blocks else "（本周各期无深度解读/未来借鉴小节）"


def _md_risks(reps: list) -> str:
    risks = []
    for r in reps:
        for f in r.get("future_lessons", []):
            if "风险" in (f.get("category") or ""):
                risks.append(f"- {fmt_date(r['_date'])}：{f.get('text')}")
    if not risks:
        return "（本周各期未来借鉴均无「风险提示」类条目）"
    return "\n".join(risks)


def _md_catalysts(cats: list) -> str:
    if not cats:
        return "（本周各期均无前瞻催化剂小节）"
    rows = []
    for c in cats:
        rows.append(
            f"| {c.get('date', '—')} | {c.get('event', '—')} | {c.get('segment', '—')} "
            f"| {c.get('importance', '—')} | {c.get('source', '—')} |"
        )
    return "| 日期 | 事件 | 环节 | 重要度 | 来源 |\n|---|--|--|--|--|\n" + "\n".join(rows)


def render_md(ctx: dict) -> str:
    start, end = ctx["start"], ctx["end"]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# 芯片行业周度复盘（{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')}）

> 生成时间：{gen} | 数据范围：{start.isoformat()} ~ {end.isoformat()} | 期数：{len(ctx['reps'])}
> 本文档由 weekly_review.py 聚合本周全部日报产物生成；「主线叙事」「认知增量」两节为
> 洞察区，由生成流程 Step 7（AI）结合本周各期深度解读与未来借鉴撰写润色。

## 一、本周概览

| 指标 | 数值 |
|---|--|
{_md_rows(ctx['agg'], ctx['reps'], start, end)}

## 二、本周主线叙事（洞察区 · Step 7 AI 润色）

{_md_insights(ctx.get('insights') or [])}
### 素材：各期今日要点

{_md_highlights(ctx['reps'])}

## 三、信号演进台账

{_md_signal_table(ctx['dates'], ctx['matrix'])}

> ⚠ = 方向反转（up↔down / tight↔loose 切换），是认知资产里最值得回看的转折点。

## 四、认知素材库（各期深度解读 + 未来借鉴）

{_md_cognition(ctx['reps'])}

## 五、风险与机会再评估

{_md_risks(ctx['reps'])}

## 六、下周前瞻催化剂

{_md_catalysts(ctx['catalysts'])}

---
*本文档由 chip-daily-report · weekly_review.py 生成 · 认知资产（迭代5）*
"""


# ---------------- HTML 渲染 ----------------

_REVIEW_CSS = """
.rv-head{background:linear-gradient(120deg,#0f172a,#4c1d95);color:#fff;border-radius:16px;
  padding:20px 24px;box-shadow:0 8px 24px rgba(15,23,42,.18)}
.rv-head h1{margin:0 0 6px;font-size:22px}
.rv-meta{font-size:13px;opacity:.9;display:flex;flex-wrap:wrap;gap:8px 20px}
.rv-block{background:#fff;border:1px solid var(--line,#e2e8f0);border-radius:14px;
  padding:16px 18px;margin-bottom:18px}
.rv-title{font-size:16.5px;margin:0 0 12px;color:var(--accent,#0f172a)}
.rv-sub{font-size:12.5px;color:var(--muted,#64748b);font-weight:500;margin-left:8px}
.rv-note{font-size:12px;color:#64748b;margin:8px 0 0;line-height:1.6}
.rv-hl{background:#f8fafc;border-left:3px solid #f59e0b;border-radius:8px;padding:8px 12px;
  font-size:13.5px;color:#334155;margin-bottom:8px;line-height:1.6}
.rv-hl b{color:#b45309}
.rv-cog{background:#f8fafc;border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:13px;line-height:1.7}
.rv-cog b{color:#1e293b}
.rv-cog li{margin-bottom:4px}
.rv-risk{background:#fff7f7;border:1px solid #fecaca;border-radius:8px;padding:8px 12px;
  font-size:13px;color:#7f1d1d;margin-bottom:6px}
.rv-cat{font-size:13px;color:#334155;margin-bottom:4px}
.rv-insight{border:1.5px dashed #a78bfa;background:#faf5ff;border-radius:10px;
  padding:10px 14px;font-size:13px;color:#5b21b6;line-height:1.7}
"""


def _html_overview(agg: dict, reps: list, start: date, end: date) -> str:
    cards = [
        ("报告期数", len(reps)),
        ("累计新闻", agg["news"]),
        ("平均条数", f"{agg['avg_news']:.1f}"),
        ("平均 A 级占比", fmt_ratio(agg["avg_ratio"])),
        ("全环节覆盖", f"{agg['full_cov']}/{len(reps)}"),
        ("自检通过率", fmt_ratio(agg["sc_rate"])),
    ]
    html = "".join(
        f'<div class="wk-card"><div class="wk-num">{esc(str(v))}</div>'
        f'<div class="wk-label">{esc(lab)}</div></div>'
        for lab, v in cards
    )
    return f"""<section class="rv-block">
<h2 class="rv-title">📋 本周概览 <span class="rv-sub">{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')} · {len(reps)} 期</span></h2>
<div class="wk-cards">{html}</div>
<p class="rv-note">数据来自本周全部日报（根目录 芯片行业日报_*.md）与 quality_dashboard 口径。</p>
</section>"""


def _html_signal(dates: list, matrix: dict) -> str:
    if not dates or not matrix:
        return """<section class="rv-block"><h2 class="rv-title">📈 信号强度曲线 <span class="rv-sub">暂无历史</span></h2>
<p class="rv-note">state/signal_history.json 尚无数据 —— 从今日起每日 Step 6 运行
<code>python scripts/signal_history.py</code> 自动累积，下周起曲线成形。</p></section>"""
    series = []
    colors = ["#2563eb", "#7c3aed", "#0891b2", "#db2777", "#16a34a", "#b45309"]
    for i, (topic, m) in enumerate(matrix.items()):
        series.append(
            {
                "name": topic,
                "color": colors[i % len(colors)],
                "values": m["levels"],
                "labels": m["labels"],
            }
        )
    labels = [fmt_date(d) for d in dates]
    trs = []
    for topic, m in matrix.items():
        cells = "".join(
            f'<td><span class="tr-dir" style="color:{_dir_color(s)};border-color:{_dir_color(s)}">'
            f'{esc(s)}</span></td>' if s != "—" else "<td>—</td>"
            for s in m["signals"]
        )
        trs.append(
            f'<tr><td class="wk-topic">{esc(topic)}</td>{cells}'
            f'<td class="wk-detail">{esc(m["change"])}</td></tr>'
        )
    return f"""<section class="rv-block">
<h2 class="rv-title">📈 信号强度曲线 <span class="rv-sub">固定量纲 -2..2 · ⚠ = 方向反转</span></h2>
<div class="chart-card">{svg_signal_lines(labels, series)}{legend_html(series)}</div>
<p class="rv-note">Y 轴固定量纲：down=-2 / loose=-1 / flat=0 / tight=1 / up=2，不归一化；
同一坐标下可直观看到主题从 up 断崖到 down（如 HBM 高位反转）。</p>
<div class="chart-card" style="margin-top:12px;overflow-x:auto">
<table class="wk-table"><thead><tr><th>主题</th>
{"".join(f"<th>{esc(fmt_date(d))}</th>" for d in dates)}<th>本周变化</th></tr></thead>
<tbody>{"".join(trs)}</tbody></table>
</div>
</section>"""


def _dir_color(signal: str) -> str:
    if signal.startswith("up"):
        return "#dc2626"
    if signal.startswith("down"):
        return "#16a34a"
    if signal.startswith("tight"):
        return "#b45309"
    if signal.startswith("loose"):
        return "#0891b2"
    return "#64748b"


def _html_insights(insights: list) -> str:
    if not insights:
        return ""
    cards = "".join(f'<div class="rv-hl"><b>🧭 主线</b> {esc(t)}</div>' for t in insights)
    return f'<div style="margin-bottom:10px">{cards}</div>'


def _html_highlights(reps: list) -> str:
    blocks = []
    for r in reps:
        for h in (r.get("highlights") or [])[:3]:
            blocks.append(
                f'<div class="rv-hl"><b>{fmt_date(r["_date"])}</b> {esc(h)}</div>'
            )
    return "".join(blocks) if blocks else '<p class="rv-note">本周各期无今日要点。</p>'


def _html_cognition(reps: list) -> str:
    blocks = []
    for r in reps:
        for dd in r.get("deep_dive", [])[:3]:
            blocks.append(
                f'<div class="rv-hl"><b>{fmt_date(r["_date"])} · 解读</b> {esc(dd.get("title", ""))}</div>'
            )
        for f in r.get("future_lessons", [])[:8]:
            blocks.append(
                f'<div class="rv-cog"><b>[{esc(f.get("category", ""))}]</b> {esc(f.get("text"))}</div>'
            )
    return "".join(blocks) if blocks else '<p class="rv-note">本周各期无深度解读/未来借鉴。</p>'


def _html_risks(reps: list) -> str:
    items = []
    for r in reps:
        for f in r.get("future_lessons", []):
            if "风险" in (f.get("category") or ""):
                items.append(
                    f'<div class="rv-risk">⚠ <b>{fmt_date(r["_date"])}</b> {esc(f.get("text"))}</div>'
                )
    return "".join(items) if items else '<p class="rv-note">本周各期无「风险提示」类条目。</p>'


def _html_catalysts(cats: list) -> str:
    if not cats:
        return '<p class="rv-note">本周各期均无前瞻催化剂小节。</p>'
    trs = "".join(
        f'<tr><td class="ct-date">{esc(str(c.get("date", "—")))}</td>'
        f'<td class="wk-topic">{esc(c.get("event", "—"))}</td>'
        f"<td>{esc(c.get('segment', '—'))}</td>"
        f"<td>{esc(c.get('importance', '—'))}</td>"
        f'<td class="wk-detail">{esc(c.get("source", "—"))}</td></tr>'
        for c in cats
    )
    return f"""<div class="chart-card"><table class="wk-table">
<thead><tr><th>日期</th><th>事件</th><th>环节</th><th>重要度</th><th>来源</th></tr></thead>
<tbody>{trs}</tbody></table></div>"""


def render_html(ctx: dict) -> str:
    start, end = ctx["start"], ctx["end"]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    span = f"{start.strftime('%m-%d')} ~ {end.strftime('%m-%d')}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>芯片行业周度复盘 · {span}</title>
<style>{REPORT_CSS}{_REVIEW_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="rv-head">
    <h1>🧭 芯片行业周度复盘 <span style="font-size:15px;opacity:.85">（{span}）</span></h1>
    <div class="rv-meta">
      <span>生成时间：{gen}</span>
      <span>期数：{len(ctx['reps'])}</span>
      <span>累计新闻：{ctx['agg']['news']} 条</span>
    </div>
  </header>

  {_html_overview(ctx['agg'], ctx['reps'], start, end)}

  <section class="rv-block">
    <h2 class="rv-title">🧭 本周主线叙事 <span class="rv-sub">AI 洞察 + 各期今日要点素材</span></h2>
    {_html_insights(ctx.get('insights') or [])}
    {_html_highlights(ctx['reps'])}
    <div class="rv-insight" style="margin-top:10px">💡 <b>洞察区说明</b>：Step 7（AI）应结合「认知素材库」与信号演进提炼 3-5 条本周主线，
    用 `--insights 文件` 注入（每行一条）即可同步更新 md 与 html。</div>
  </section>

  {_html_signal(ctx['dates'], ctx['matrix'])}

  <section class="rv-block">
    <h2 class="rv-title">🧠 认知素材库 <span class="rv-sub">各期深度解读 + 未来借鉴（跨期去重留档）</span></h2>
    {_html_cognition(ctx['reps'])}
  </section>

  <section class="rv-block">
    <h2 class="rv-title">⚠️ 风险与机会再评估 <span class="rv-sub">各期「风险提示」汇总</span></h2>
    {_html_risks(ctx['reps'])}
  </section>

  <section class="rv-block">
    <h2 class="rv-title">📅 下周前瞻催化剂 <span class="rv-sub">已公告确定时点（C·v5.3）</span></h2>
    {_html_catalysts(ctx['catalysts'])}
  </section>

  <footer class="foot">由 chip-daily-report · weekly_review.py 生成 · 认知资产（迭代5）</footer>
</div>
</body>
</html>"""


# ---------------- 装配入口 ----------------

def run(end_date: str | None = None, days: int | None = None, out_dir: Path | None = None,
        insights_file: Path | None = None) -> dict:
    end_d = parse_date(end_date or date.today().strftime("%Y%m%d"))
    if days:
        start_d = end_d - timedelta(days=days - 1)
    else:
        start_d, _ = week_range(end_d)
        start_d = max(start_d, end_d - timedelta(days=90))  # 防御：本周为空时兜底最近 90 天

    reps = collect_reports(ROOT, start_d, end_d)
    history = load_signal_history()
    dates, matrix = build_signal_matrix(history)
    insights: list[str] = []
    if insights_file and insights_file.exists():
        insights = [
            ln.strip()
            for ln in insights_file.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    ctx = {
        "reps": reps,
        "start": start_d,
        "end": end_d,
        "agg": aggregate_reports(reps),
        "dates": dates,
        "matrix": matrix,
        "catalysts": collect_catalysts(reps),
        "insights": insights,
    }

    out_dir = out_dir or ROOT / "delivery"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{REVIEW_NAME}_{end_d.strftime('%Y%m%d')}.md"
    html_path = out_dir / f"{REVIEW_NAME}_{end_d.strftime('%Y%m%d')}.html"
    md_path.write_text(render_md(ctx), encoding="utf-8")
    html_path.write_text(render_html(ctx), encoding="utf-8")

    print(f"[weekly_review] 周范围 {start_d.isoformat()} ~ {end_d.isoformat()}（{len(reps)} 期）")
    print(f"  信号历史 {len(dates)} 期 / {len(matrix)} 主题")
    print(f"  md   -> {md_path.relative_to(ROOT)}")
    print(f"  html -> {html_path.relative_to(ROOT)}")
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description="聚合本周日报产物生成周度复盘（认知资产）")
    ap.add_argument("--end", default=None, help="YYYYMMDD 截止日，默认今天")
    ap.add_argument("--days", type=int, default=None, help="取截止日前 N 天（默认自然周）")
    ap.add_argument("--out", default=None, help="输出目录，默认 delivery/")
    ap.add_argument("--insights", default=None, help="AI 洞察文件（每行一条本周主线）")
    args = ap.parse_args()
    run(args.end, args.days, Path(args.out) if args.out else None,
        Path(args.insights) if args.insights else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
