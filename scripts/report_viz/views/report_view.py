#!/usr/bin/env python3
"""report_viz.views.report_view — 日报卡片视图渲染器。

把解析后的日报 dict 渲染为卡片式 HTML：
  - 今日要点高亮卡
  - 5 环节分区（分色），每区下为新闻卡
  - 新闻卡含：回顾徽章、标题、摘要、技术注解高亮、来源级别徽章、时间戳、原始出处追溯
  - 自检结果折叠区

扩展方式：本文件导出的 render(report) 即在 VIEW_REGISTRY 中注册的一个视图，
新增视图只需新建一个 render(report)->str 的模块并在 views/__init__.py 注册即可。
"""
from __future__ import annotations

import html
import re

from ..parser import SEG_ORDER

# 环节配色（与设计/制造/封测/EDA/材料一一对应）
SEG_META = {
    "设计": ("设计", "#2563eb"),
    "制造": ("制造", "#7c3aed"),
    "封测": ("封测", "#0891b2"),
    "EDA": ("EDA / 工具", "#db2777"),
    "材料": ("材料 / 设备", "#16a34a"),
}

LEVEL_META = {
    "A": ("A 级·权威", "#15803d", "#dcfce7"),
    "B": ("B 级·聚合", "#b45309", "#fef3c7"),
    "C": ("C 级·禁止", "#b91c1c", "#fee2e2"),
}

# v5.2 信号层徽章配色（light 主题：浅底深字）
_SIG_STYLE = {
    "high": ("重要·高", "#b91c1c", "#fee2e2"),
    "mid": ("重要·中", "#b45309", "#fef3c7"),
    "low": ("重要·低", "#64748b", "#e2e8f0"),
    "good": ("影响·利好", "#15803d", "#dcfce7"),
    "bad": ("影响·利空", "#b91c1c", "#fee2e2"),
    "neu": ("影响·中性", "#64748b", "#e2e8f0"),
    "pos": ("情绪·正面", "#15803d", "#dcfce7"),
    "neg": ("情绪·负面", "#b91c1c", "#fee2e2"),
    "neut": ("情绪·中性", "#64748b", "#e2e8f0"),
}

_SIG_MAP = {
    ("importance", "高"): "high",
    ("importance", "中"): "mid",
    ("importance", "低"): "low",
    ("impact", "利好"): "good",
    ("impact", "利空"): "bad",
    ("impact", "中性"): "neu",
    ("sentiment", "正面"): "pos",
    ("sentiment", "负面"): "neg",
    ("sentiment", "中性"): "neut",
}


def _signal_badges(item: dict) -> str:
    sig = item.get("signal")
    if not sig:
        return ""
    badges = []
    for key in ("importance", "impact", "sentiment"):
        val = sig.get(key)
        style_key = _SIG_MAP.get((key, val))
        if not style_key:
            continue
        label, fg, bg = _SIG_STYLE[style_key]
        badges.append(
            f'<span class="sig-badge" style="color:{fg};background:{bg}">{_esc(label)}</span>'
        )
    if not badges:
        return ""
    return f'<span class="sig-group">{"".join(badges)}</span>'


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _highlight_card(text: str) -> str:
    return f'<li class="hl-item">{_esc(text)}</li>'


def _news_card(item: dict) -> str:
    review = '<span class="badge badge-review">回顾</span>' if item["is_review"] else ""
    annotation = ""
    if item["annotation"]:
        annotation = (
            f'<div class="annot"><span class="annot-ico">💡</span>'
            f'<span class="annot-label">技术注解</span>'
            f'<span class="annot-body">{_esc(item["annotation"])}</span></div>'
        )
    origin = ""
    if item["origin"]:
        origin = f'<span class="tag tag-origin">原始出处：{_esc(item["origin"])}</span>'

    src_badges = []
    for name, url in item["sources"]:
        src_badges.append(
            f'<a class="src-link" href="{_esc(url)}" target="_blank" rel="noopener">'
            f'{_esc(name)} ↗</a>'
        )
    src_html = " ".join(src_badges) if src_badges else "—"

    lvl = item["level"]
    lvl_label, lvl_fg, lvl_bg = LEVEL_META.get(lvl, LEVEL_META["B"])
    level_badge = (
        f'<span class="badge" style="color:{lvl_fg};background:{lvl_bg}">{lvl_label}</span>'
    )
    ts = f'<span class="ts">🕒 {_esc(item["timestamp"])}</span>' if item["timestamp"] else ""

    return f"""
    <article class="news" data-seg="{_esc(item.get('_seg',''))}">
      <div class="news-head">
        {review}
        {level_badge}
        {_signal_badges(item)}
        <h3 class="news-title">{_esc(item["title"])}</h3>
      </div>
      <p class="news-summary">{_esc(item["summary"])}</p>
      {annotation}
      <div class="news-meta">
        <span class="srcs">{src_html}</span>
        {ts}
        {origin}
      </div>
    </article>"""


def _segment_block(seg_key: str, items: list) -> str:
    label, color = SEG_META[seg_key]
    cards = "\n".join(_news_card({**it, "_seg": seg_key}) for it in items)
    a = sum(1 for it in items if it["level"] == "A")
    b = sum(1 for it in items if it["level"] == "B")
    c = sum(1 for it in items if it["level"] == "C")
    stat = f'<span class="seg-stat">A {a} · B {b} · C {c}</span>' if (a or b or c) else ""
    return f"""
    <section class="seg" id="seg-{_esc(seg_key)}" style="--seg:{color}">
      <h2 class="seg-title"><span class="dot" style="background:{color}"></span>{_esc(label)}
        <span class="seg-count">{len(items)} 条</span>{stat}</h2>
      <div class="news-list">{cards}</div>
    </section>"""


def _selfcheck_block(rows: list) -> str:
    if not rows:
        return ""
    trs = []
    for r in rows:
        cls = f"sc-{r['result'].lower()}"
        trs.append(
            f'<tr class="{cls}"><td>{r["num"]}</td><td>{_esc(r["name"])}</td>'
            f'<td><span class="sc-pill {cls}">{r["result"]}</span></td>'
            f'<td>{_esc(r["note"])}</td></tr>'
        )
    return f"""
    <details class="selfcheck">
      <summary>自检结果（{len(rows)} 项 Rubric）</summary>
      <table class="sc-table">
        <thead><tr><th>#</th><th>检查项</th><th>结果</th><th>说明</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>
    </details>"""


def _tracking_block(items: list) -> str:
    """持续追踪（B·v5.3）：主题卡片列表。"""
    if not items:
        return ""
    cards = []
    dir_label = {"up": "↑ 上行", "down": "↓ 下行", "flat": "→ 平稳",
                 "tight": "↗ 趋紧", "loose": "↘ 趋松"}
    for it in items:
        topic = it["topic"]
        # 从 detail 里尝试提取方向标签（up/tight 等），拿不到就用中性
        dir_found = None
        for k, lab in dir_label.items():
            if f"（{k}" in it["detail"] or f"({k})" in it["detail"] or k + "（连续" in it["detail"]:
                dir_found = (k, lab)
                break
        arrow = f'<span class="tk-dir">{dir_found[1]}</span>' if dir_found else ""
        cards.append(
            f'<div class="tk-card"><div class="tk-head">{arrow}'
            f'<span class="tk-topic">{_esc(topic)}</span></div>'
            f'<p class="tk-detail">{_esc(it["detail"])}</p></div>'
        )
    return f"""
    <section class="tracking-block">
      <h2 class="tk-title">📈 持续追踪 <span class="tk-sub">跨日记忆 · 主题变比</span></h2>
      <div class="tk-grid">{"".join(cards)}</div>
    </section>"""


def _catalyst_block(rows: list) -> str:
    """前瞻催化剂（C·v5.3）：未来 7 天确定时点表格。"""
    if not rows:
        return ""
    imp_style = {"高": "#b91c1c", "中": "#b45309", "低": "#64748b"}
    trs = []
    for r in rows:
        ic = imp_style.get(r["importance"], "#64748b")
        links = " ".join(
            f'<a class="src-link" href="{_esc(s["url"])}" target="_blank" rel="noopener">'
            f'{_esc(s["name"])} ↗</a>'
            for s in r["sources"]
        ) or "—"
        trs.append(
            f'<tr><td class="ct-date">{_esc(r["date"])}</td>'
            f'<td>{_esc(r["event"])}</td>'
            f'<td>{_esc(r["segment"])}</td>'
            f'<td><span class="ct-imp" style="color:{ic};border-color:{ic}">{_esc(r["importance"])}</span></td>'
            f'<td>{links}</td></tr>'
        )
    return f"""
    <section class="catalyst-block">
      <h2 class="ct-title">🗓 前瞻催化剂 <span class="ct-sub">未来 7 天确定时点</span></h2>
      <table class="ct-table">
        <thead><tr><th>日期</th><th>事件</th><th>环节</th><th>重要度</th><th>来源</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>
    </section>"""


def _feynman_block(items: list) -> str:
    """费曼解释（F1.3·v5.4）：大白话术语卡片，放在前瞻催化剂之后、自检结果之前。"""
    if not items:
        return ""
    cards = []
    for it in items:
        cards.append(
            f'<div class="fk-card"><div class="fk-term">{_esc(it["term"])}</div>'
            f'<p class="fk-text">{_esc(it["text"])}</p></div>'
        )
    return f"""
    <section class="feynman-block">
      <h2 class="fk-title">💬 费曼解释 <span class="tk-sub">大白话术语表 · 零基础友好 · {len(items)} 条</span></h2>
      <div class="fk-grid">{"".join(cards)}</div>
    </section>"""


def _deep_dive_block(items: list) -> str:
    """深度解读（v5.6）：当日最重要新闻的"意味着什么/未来影响/格局意义"。"""
    if not items:
        return ""
    PART_ICON = {
        "这意味着什么": "💡",
        "未来影响": "🔮",
        "格局意义": "🌍",
    }
    cards = []
    for idx, it in enumerate(items, 1):
        parts = ""
        for key, text in it.get("parts", []):
            icon = PART_ICON.get(key, "•")
            parts += (
                f'<div class="dd-part"><div class="dd-part-title">{icon} {_esc(key)}</div>'
                f'<div class="dd-part-text">{_esc(text)}</div></div>'
            )
        cards.append(
            f'<div class="dd-card"><div class="dd-head">'
            f'<span class="dd-num">{idx}</span>'
            f'<span class="dd-title">{_esc(it["title"])}</span></div>{parts}</div>'
        )
    return f"""
    <section class="deep-block">
      <h2 class="dd-title">🔍 深度解读 <span class="tk-sub">最重要新闻 · 意味着什么 · 未来影响 · 格局意义 · {len(items)} 条</span></h2>
      <div class="dd-list">{"".join(cards)}</div>
    </section>"""


# v5.8 未来借鉴增强：趋势信号强度标注 + 格局时间轴
STRENGTH_RE = re.compile(r"（强度[:：]\s*([↑→↓])\s*([强中弱])）")
_TIMELINE_RE = re.compile(r"(\d+)\.\s*\*\*(.+?)\*\*\s*[：:]\s*(.*?)(?=\s*\d+\.\s*\*\*|$)")
_ST_META = {
    "↑": ("强", "#b91c1c", "#fee2e2"),
    "→": ("中", "#b45309", "#fef3c7"),
    "↓": ("弱", "#64748b", "#e2e8f0"),
}


def _render_strength(text: str) -> str:
    """把 '（强度：↑强）' 标注渲染为彩色徽章（↑ 红/→ 橙/↓ 灰）。"""
    def rep(m):
        arrow, lvl = m.group(1), m.group(2)
        label, fg, bg = _ST_META.get(arrow, (lvl, "#64748b", "#e2e8f0"))
        return (
            f'<span class="fu-strength" style="color:{fg};background:{bg}">'
            f"{arrow} 强度·{label}</span>"
        )

    return STRENGTH_RE.sub(rep, text)


def _timeline_html(text: str) -> str:
    """把格局时间轴文本（'1. **1 年内**：xxx 2. ...'）渲染为水平时间轴。"""
    stages = _TIMELINE_RE.findall(text or "")
    if not stages:
        return f'<div class="fu-text">{_esc(text)}</div>'
    cells = []
    for num, period, desc in stages:
        cells.append(
            f'<div class="tl-stage"><div class="tl-dot">阶段 {num}</div>'
            f'<div class="tl-period">{_esc(period)}</div>'
            f'<div class="tl-desc">{_esc(desc)}</div></div>'
        )
    return f'<div class="tl-track">{"".join(cells)}</div>'


def _future_lessons_block(items: list) -> str:
    """未来借鉴（v5.6，v5.8 增强）：趋势信号/格局预判/可借鉴行动/风险提示 + 格局时间轴。"""
    if not items:
        return ""
    CAT_META = {
        "趋势信号": ("📡", "#2563eb"),
        "格局预判": ("🌐", "#7c3aed"),
        "格局时间轴": ("🕐", "#0f766e"),
        "可借鉴行动": ("🛠", "#16a34a"),
        "风险提示": ("⚠️", "#b91c1c"),
    }
    cards = []
    for it in items:
        cat = it.get("category", "")
        icon, color = CAT_META.get(cat, ("•", "#334155"))
        if cat == "格局时间轴":
            body = _timeline_html(it.get("text", ""))
        else:
            body = (
                f'<div class="fu-text">{_render_strength(_esc(it.get("text", "")))}</div>'
            )
        cards.append(
            f'<div class="fu-card" style="border-top-color:{color}">'
            f'<div class="fu-head"><span class="fu-ico">{icon}</span>'
            f'<span class="fu-cat" style="color:{color}">{_esc(cat)}</span></div>'
            f"{body}</div>"
        )
    return f"""
    <section class="future-block">
      <h2 class="fu-title">🧭 未来借鉴 <span class="tk-sub">趋势信号 · 格局预判 · 格局时间轴 · 可借鉴行动 · 风险提示</span></h2>
      <div class="fu-grid">{"".join(cards)}</div>
    </section>"""


def render(report: dict) -> str:
    """渲染日报视图 HTML 片段。"""
    hl = "".join(_highlight_card(h) for h in report.get("highlights", []))
    highlights = (
        f'<div class="highlights"><h2 class="hl-title">今日要点</h2>'
        f'<ul class="hl-list">{hl}</ul></div>'
        if hl
        else ""
    )

    segs = []
    for seg in SEG_ORDER:
        items = report.get("segments", {}).get(seg)
        if items:
            segs.append(_segment_block(seg, items))
    seg_html = "\n".join(segs)

    tracking = _tracking_block(report.get("tracking", []))
    catalysts = _catalyst_block(report.get("catalysts", []))
    feynman = _feynman_block(report.get("feynman", []))
    deep_dive = _deep_dive_block(report.get("deep_dive", []))
    future_lessons = _future_lessons_block(report.get("future_lessons", []))
    selfcheck = _selfcheck_block(report.get("selfcheck", []))

    return f"""
    <div class="report-view">
      {highlights}
      {seg_html}
      {tracking}
      {catalysts}
      {feynman}
      {deep_dive}
      {future_lessons}
      {selfcheck}
    </div>"""
