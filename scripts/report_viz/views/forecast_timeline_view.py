#!/usr/bin/env python3
"""report_viz.views.forecast_timeline_view — 前瞻催化剂时间轴（v5.11 方向3）。

读取 state/forecast_log.json（前瞻履约日志，含 v5.10 预告→验证 + v5.11 确定性分级），
渲染「未来催化剂时间轴」：

  - 顶部统计：未来 14 天事件数 / 全部待回看数
  - 竖向时间轴：每件未验证且日期 >= 今天的前瞻一条节点，按日期排序
  - 高亮未来 14 天窗口（near 节点加蓝边 + "未来14天"徽章），一眼看到密集风险/事件窗口
  - 每节点含：日期、事件、环节徽章、重要度、确定性（v5.11 三档色）、来源链接

数据缺失时优雅降级（提示运行流程以累积 forecast_log.json），不影响整页渲染。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # views/ -> report_viz/ -> scripts/ -> repo
LOG_PATH = ROOT / "state" / "forecast_log.json"
NEAR_DAYS = 14

# 环节配色（与全局 SEG 变量一致）
SEG_COLORS = {
    "设计": "#2563eb",
    "制造": "#7c3aed",
    "封测": "#0891b2",
    "EDA": "#db2777",
    "EDA/材料": "#db2777",
    "材料": "#16a34a",
    "政策": "#0f766e",
}
# 确定性三档色（v5.11）
CERT_META = {
    "高确定性": ("#15803d", "#dcfce7"),
    "中确定性": ("#b45309", "#fef3c7"),
    "低确定性": ("#b91c1c", "#fee2e2"),
}
# 重要度色
IMP_META = {
    "高": "#b91c1c",
    "中": "#b45309",
    "低": "#64748b",
}


def _esc(t) -> str:
    import html

    return html.escape(str(t or ""), quote=True)


def _parse(d: str) -> date | None:
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None


def _fmt_md(d: date) -> str:
    return f"{d.month}月{d.day}日"


def _load_entries() -> list:
    if not LOG_PATH.exists():
        return []
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        return data.get("entries", []) or []
    except Exception:
        return []


def render(report: dict) -> str:
    today = date.today()
    horizon = today + timedelta(days=NEAR_DAYS)
    entries = _load_entries()

    # 筛未验证 + 日期 >= 今天（只看未来）
    future = []
    for e in entries:
        if e.get("verified"):
            continue
        ev = _parse(e.get("event_date", ""))
        if not ev or ev < today:
            continue
        future.append((ev, e))
    future.sort(key=lambda x: x[0])

    near_n = sum(1 for ev, _ in future if ev <= horizon)
    total_pending = sum(1 for e in entries if not e.get("verified"))

    if not future:
        body = '<div class="tl-empty">近期暂无已登记的前瞻催化剂（运行日报流程后，'
        body += "state/forecast_log.json 会累积未来事件并自动显示在此时间轴）。</div>"
    else:
        nodes = []
        for ev, e in future:
            seg = e.get("segment", "—")
            seg_color = SEG_COLORS.get(seg, "#334155")
            cert = e.get("certainty", "—")
            c_fg, c_bg = CERT_META.get(cert, ("#64748b", "#f1f5f9"))
            imp = e.get("importance", "—")
            imp_color = IMP_META.get(imp, "#64748b")
            is_near = ev <= horizon
            near_cls = " near" if is_near else ""
            near_badge = '<span class="tl-window">未来14天</span>' if is_near else ""
            src = e.get("source", "")
            src_html = (
                f'<a class="tl-src" href="{_esc(src)}" target="_blank" rel="noopener">来源↗</a>'
                if src else ""
            )
            nodes.append(f"""
            <div class="tl-node{near_cls}">
              <div><span class="tl-date">{_esc(_fmt_md(ev))}</span>{near_badge}</div>
              <div class="tl-event">{_esc(e.get('event', '—'))}</div>
              <div class="tl-meta">
                <span class="tl-seg" style="color:{seg_color};background:{seg_color}1a">{_esc(seg)}</span>
                <span class="tl-imp" style="color:{imp_color};border-color:{imp_color}">{_esc(imp)}</span>
                <span class="tl-cert" style="color:{c_fg};background:{c_bg}">{_esc(cert)}</span>
                {src_html}
              </div>
            </div>""")
        body = f'<div class="tl-axis">{"".join(nodes)}</div>'

    return f"""
    <section class="tl-block">
      <h2 class="tl-title">🗓 前瞻催化剂时间轴 <span class="tl-sub">v5.11 方向3 · 数据来自 state/forecast_log.json</span></h2>
      <div class="tl-summary">
        <div class="tl-stat"><div class="tl-stat-num">{near_n}</div><div class="tl-stat-lab">未来 {NEAR_DAYS} 天事件</div></div>
        <div class="tl-stat"><div class="tl-stat-num">{len(future)}</div><div class="tl-stat-lab">全部未来事件</div></div>
        <div class="tl-stat"><div class="tl-stat-num">{total_pending}</div><div class="tl-stat-lab">待回看总数</div></div>
      </div>
      {body}
      <p class="tr-note">蓝点 = 未来 {NEAR_DAYS} 天密集窗口；确定性（{_esc(' / '.join(CERT_META))}）仅判时点是否官方确认，不预判结果。已发生/已验证事件自动移出本轴。</p>
    </section>"""
