#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.report_viz — 多源融合质量报告（v6.0，迭代1 A1）。

消费 multi_source/data 的产物（fused_events / gap_report / leak_report /
source_registry）+ state/source_health.yaml，生成零依赖单文件 HTML：

  1. 多源事件卡片   —— 事件标题/环节/置信度/来源数/分歧高亮
  2. 漏聚候选表     —— leak_detector 的"该聚未聚"候选 + 锚词建议
  3. 源覆盖矩阵     —— 环节×来源类型 充足度（绿/黄/红）+ 数据源健康状态点
  4. 缺口清单       —— 严重缺口 / 缺口 与建议动作

独立报告（不融入 report_viz 日报视图）：multi_source 是"生成前"融合链路，
面向维护者（数据质量/信息差），与面向读者的日报 HTML 语义不同。

CLI：python scripts/multi_source/report_viz.py [--out delivery/multi_source_report.html]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
STATE_DIR = ROOT / "state"
DEFAULT_OUT = ROOT / "delivery" / "multi_source_report.html"

SEG_ORDER = ["设计", "制造", "封测", "EDA", "材料"]
TIER_META = {0: ("T0 一手", "#15803d"), 1: ("T1 英文权威", "#0f766e"),
             2: ("T2 监管/财报", "#1d4ed8"), 3: ("T3 中文权威", "#b45309"),
             4: ("T4 聚合/线索", "#64748b")}
LEVEL_META = {"充足": ("充足", "#dcfce7", "#15803d"),
              "缺口": ("缺口", "#fef3c7", "#b45309"),
              "严重缺口": ("严重缺口", "#fee2e2", "#b91c1c")}
PRIO_META = {"high": ("高", "#fee2e2", "#b91c1c"),
             "medium": ("中", "#fef3c7", "#b45309"),
             "low": ("低", "#dcfce7", "#15803d")}


def _esc(t):
    return html.escape(str(t or ""), quote=True)


def _load_json(name: str):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_health() -> dict:
    if yaml is None:
        return {}
    try:
        p = STATE_DIR / "source_health.yaml"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


# ---------------- 1. 多源事件卡片 ----------------
def _event_cards(fused) -> str:
    if not fused:
        return '<div class="empty">暂无融合事件（fused_events.json 缺失）</div>'
    cards = []
    for ev in fused:
        conf = ev.get("confidence", 0)
        bar_color = "#15803d" if conf >= 75 else ("#b45309" if conf >= 50 else "#b91c1c")
        divs = ev.get("divergences") or []
        div_html = ""
        if divs:
            rows = []
            for d in divs:
                rows.append(
                    f'<div class="div"><b>{_esc(d.get("a"))}</b> 说 '
                    f'<span class="claim">{_esc(" / ".join(d.get("a_claim") or []))}</span>'
                    f'，<b>{_esc(d.get("b"))}</b> 说 '
                    f'<span class="claim">{_esc(" / ".join(d.get("b_claim") or []))}</span>'
                    f'<span class="div-note">{_esc(d.get("note") or "")}</span></div>'
                )
            div_html = (f'<div class="div-block"><div class="div-title">⚠ 跨源分歧</div>'
                        f'{"".join(rows)}</div>')

        src_badges = []
        for s in ev.get("sources") or []:
            sid = s.get("source_id", "?")
            tier = s.get("tier")
            label, color = TIER_META.get(tier, (f"T{tier}", "#64748b"))
            src_badges.append(
                f'<span class="src-badge" style="color:{color};border-color:{color}">'
                f'{_esc(s.get("source_name") or sid)} · {label}</span>'
            )
        primary = (ev.get("primary_source") or {}).get("source_name", "—")

        cards.append(f"""
        <article class="ev-card">
          <div class="ev-head">
            <span class="ev-id">{_esc(ev.get("event_id"))}</span>
            <h3>{_esc(ev.get("title"))}</h3>
            <span class="seg-chip">{_esc(ev.get("segment"))}</span>
          </div>
          <div class="ev-meta">
            <span>📅 {_esc(ev.get("published"))}</span>
            <span>🔗 {ev.get("n_sources", 0)} 源 · {ev.get("n_unique_sources", 0)} 独立源</span>
            <span>✅ {_esc(ev.get("verification"))}</span>
            <span>🎯 主源：{_esc(primary)}</span>
            <div class="conf"><span>置信度 {conf}</span>
              <div class="conf-track"><div class="conf-fill" style="width:{conf}%;background:{bar_color}"></div></div></div>
          </div>
          <div class="srcs">{''.join(src_badges)}</div>
          {div_html}
        </article>""")
    return "".join(cards)


# ---------------- 2. 漏聚候选表 ----------------
def _leak_table(leak) -> str:
    if not isinstance(leak, dict) or not leak.get("candidates"):
        return '<div class="empty">暂无漏聚候选（leak_report.json 缺失或为空）</div>'
    stats = leak.get("stats") or {}
    rows = []
    for c in leak["candidates"]:
        pair = c.get("pair") or []
        sig = c.get("signals") or {}
        sig_hits = [k for k, v in sig.items() if isinstance(v, dict) and v.get("hit")]
        anchors = c.get("candidate_anchors") or []
        prio = c.get("priority", "low")
        plabel, pfg, pbg = PRIO_META.get(prio, PRIO_META["low"])
        rows.append(f"""
        <tr>
          <td><b>{_esc(" ↔ ".join(pair))}</b></td>
          <td><span class="prio" style="color:{pfg};background:{pbg}">{plabel}</span></td>
          <td>{_esc(" / ".join(sig_hits) or "—")}</td>
          <td>{_esc("、".join(anchors) or "—")}</td>
          <td class="leak-reason">{_esc(c.get("reason") or "")}</td>
        </tr>""")
    return f"""
    <table class="tbl">
      <thead><tr><th>候选事件对</th><th>优先级</th><th>命中信号</th><th>候选锚词</th><th>理由</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <div class="note">共 {stats.get('total_candidates', 0)} 个候选 · 锚词需人工审核后写回 fusion.py（只建议不自动改码）</div>"""


# ---------------- 3. 源覆盖矩阵 ----------------
def _coverage_matrix(gap, health) -> str:
    if not isinstance(gap, dict) or not gap.get("cells"):
        return '<div class="empty">暂无覆盖矩阵（gap_report.json 缺失）</div>'
    types = []
    seen = set()
    for c in gap["cells"]:
        t = c.get("type")
        if t and t not in seen:
            seen.add(t)
            types.append(t)
    type_labels = {c.get("type"): c.get("type_label") for c in gap["cells"]}

    # 健康状态点
    health_src = {}
    for s in (health.get("sources") or []):
        health_src[s.get("source_id")] = s
    health_dots = []
    for sid, s in health_src.items():
        st = s.get("status", "down")
        color = {"ok": "#15803d", "degraded": "#b45309", "down": "#b91c1c"}.get(st, "#b91c1c")
        lat = s.get("avg_latency_ms", 0)
        avail = s.get("availability_7d", 0)
        health_dots.append(
            f'<span class="hd" title="{_esc(s.get("source_name"))} · {st} · {lat}ms · 7日可用率 {avail}">'
            f'<i style="background:{color}"></i>{_esc(s.get("source_name"))}</span>'
        )

    thead = "<th>环节</th>" + "".join(f"<th>{_esc(type_labels.get(t, t))}</th>" for t in types)
    rows = []
    for seg in SEG_ORDER:
        cells = {c.get("type"): c for c in gap["cells"] if c.get("segment") == seg}
        tds = []
        for t in types:
            c = cells.get(t)
            if not c:
                tds.append("<td class='cov-na'>—</td>")
                continue
            label, bg, fg = LEVEL_META.get(c.get("level"), LEVEL_META["缺口"])
            tds.append(f'<td style="background:{bg};color:{fg}">{label}</td>')
        rows.append(f"<tr><td><b>{seg}</b></td>{''.join(tds)}</tr>")
    return f"""
    <table class="tbl cov">
      <thead><tr>{thead}</tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    <div class="health-dots"><b>数据源健康：</b>{''.join(health_dots) or '—'}</div>"""


# ---------------- 4. 缺口清单 ----------------
def _gap_list(gap) -> str:
    if not isinstance(gap, dict):
        return '<div class="empty">暂无缺口数据</div>'
    gaps = [g for g in (gap.get("gaps") or []) if g.get("level") != "充足"]
    if not gaps:
        return '<div class="empty">🎉 无严重缺口，源覆盖良好</div>'
    items = []
    for g in gaps:
        label, bg, fg = LEVEL_META.get(g.get("level"), LEVEL_META["缺口"])
        srcs = g.get("source_ids") or []
        items.append(f"""
        <div class="gap-item" style="border-left-color:{fg}">
          <div class="gap-head"><b>{_esc(g.get("segment"))} · {_esc(g.get("type_label"))}</b>
            <span class="gap-lvl" style="background:{bg};color:{fg}">{label}</span></div>
          <div class="gap-desc">实际 {g.get("actual", 0)} 源 / 目标 {g.get("target", 1)} 源</div>
          <div class="gap-srcs">现有：{_esc("、".join(srcs) or "无")}</div>
        </div>""")
    return "".join(items)


# ---------------- 装配 ----------------
CSS = """
:root{--bg:#f1f5f9;--card:#fff;--ink:#1e293b;--muted:#64748b;--line:#e2e8f0}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:1060px;margin:0 auto;padding:24px 18px 56px}
header{background:linear-gradient(120deg,#0f172a,#134e4a);color:#fff;border-radius:16px;padding:20px 26px}
header h1{margin:0 0 6px;font-size:22px}
.meta{font-size:13px;opacity:.9}
h2.sec{font-size:17px;margin:26px 0 12px;padding-bottom:8px;border-bottom:2px solid var(--line)}
.block{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:18px}
.empty{padding:16px;text-align:center;color:var(--muted);background:#f8fafc;border:1px dashed var(--line);border-radius:10px}
.ev-card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:12px;background:#fbfdff}
.ev-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.ev-id{font-size:11px;font-weight:700;color:#fff;background:#0f172a;border-radius:6px;padding:1px 7px}
.ev-head h3{margin:0;font-size:15px}
.seg-chip{font-size:11.5px;font-weight:700;color:#134e4a;background:#ccfbf1;border-radius:999px;padding:1px 9px}
.ev-meta{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:var(--muted);margin-bottom:8px;align-items:center}
.conf{display:flex;align-items:center;gap:6px}
.conf-track{width:90px;height:8px;background:#e2e8f0;border-radius:999px;overflow:hidden}
.conf-fill{height:100%;border-radius:999px}
.srcs{display:flex;flex-wrap:wrap;gap:6px}
.src-badge{font-size:11.5px;border:1px solid;border-radius:999px;padding:0 9px;font-weight:600}
.div-block{background:#fff5f5;border:1px solid #fecaca;border-radius:10px;padding:8px 12px;margin-top:8px}
.div-title{font-weight:700;color:#b91c1c;font-size:12.5px;margin-bottom:4px}
.div{font-size:12.5px;color:#334155;margin-bottom:4px}
.claim{font-weight:700;color:#b91c1c}
.div-note{margin-left:8px;font-size:11.5px;color:var(--muted)}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th,.tbl td{border-bottom:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
.tbl th{color:var(--muted);font-weight:600;white-space:nowrap}
.prio{font-weight:700;font-size:11.5px;border-radius:999px;padding:0 9px;white-space:nowrap}
.leak-reason{font-size:12px;color:#475569}
.cov td{text-align:center;white-space:nowrap}
.cov-na{color:#cbd5e1}
.note{font-size:12px;color:var(--muted);margin-top:8px}
.health-dots{margin-top:12px;font-size:12.5px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
.hd{display:inline-flex;align-items:center;gap:5px;color:#475569}
.hd i{width:9px;height:9px;border-radius:50%;display:inline-block}
.gap-item{border:1px solid var(--line);border-left-width:4px;border-radius:10px;padding:9px 12px;margin-bottom:8px;background:#fbfdff}
.gap-head{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.gap-lvl{font-size:11px;font-weight:700;border-radius:999px;padding:0 9px}
.gap-desc{font-size:12.5px;color:var(--muted)}
.gap-srcs{font-size:12px;color:#475569;margin-top:2px}
footer{margin-top:26px;text-align:center;font-size:12px;color:var(--muted)}
"""


def build(fused, gap, leak, health) -> str:
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    g = (health.get("global") or {}) if health else {}
    g_meta = (
        f"raw {g.get('raw_count', '—')} → cleaned {g.get('cleaned_count', '—')} · "
        f"丢弃率 {g.get('discard_rate', '—')} · 融合事件 {g.get('fused_events', '—')} · "
        f"冲突率 {g.get('conflict_rate', '—')} · 缺口格 {g.get('gap_cells', '—')}"
        if g else "全局指标：—"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>multi_source 融合质量报告</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🧩 multi_source 融合质量报告</h1>
    <div class="meta">生成于 {gen} · 数据源采集 → 清洗 → 融合 → 缺口分析 → 漏聚探测 全链路观测</div>
  </header>

  <h2 class="sec">1 · 多源事件卡片（{len(fused) if isinstance(fused, list) else 0} 条）</h2>
  <div class="block">{_event_cards(fused)}</div>

  <h2 class="sec">2 · 漏聚候选（该聚未聚）</h2>
  <div class="block">{_leak_table(leak)}</div>

  <h2 class="sec">3 · 源覆盖矩阵 + 数据源健康</h2>
  <div class="block">{_coverage_matrix(gap, health)}</div>

  <h2 class="sec">4 · 缺口清单</h2>
  <div class="block">{_gap_list(gap)}</div>

  <footer>由 chip-daily-report · multi_source 生成 · 面向维护者 · 全局指标：{_esc(g_meta)}</footer>
</div>
</body>
</html>"""


def run(out: Path | None = None) -> Path:
    fused = _load_json("fused_events.json")
    gap = _load_json("gap_report.json")
    leak = _load_json("leak_report.json")
    health = _load_health()
    out = out or DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(fused, gap, leak, health), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 multi_source 融合质量报告 HTML")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出路径")
    args = ap.parse_args()
    out = run(Path(args.out))
    print(f"[report_viz] 已生成 {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
