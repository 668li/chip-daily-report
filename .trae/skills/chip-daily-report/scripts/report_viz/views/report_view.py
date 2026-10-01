#!/usr/bin/env python3
"""report_viz.views.report_view — 日报卡片视图渲染器。

把解析后的日报 dict 渲染为卡片式 HTML：
  - 读前须知图例条（v6.0，取导师课「今日速览」body，fail-soft）
  - 今日一课摘要卡（v6.0，取「深度第一课」，完整版在「导师课堂」Tab）
  - 今日要点高亮卡
  - 费曼解释卡（v6.0 前移到新闻之前，对齐 md 阅读曲线）
  - 5 环节分区（分色），每区下为新闻卡
  - 新闻卡含：回顾徽章、标题、摘要、技术注解高亮、teach 三层子行（v6.0）、来源级别徽章、时间戳、原始出处追溯
  - 持续追踪 / 前瞻催化剂 / 前瞻兑现回顾（v6.0 新增渲染）/ 深度解读 / 未来借鉴 / 自检结果折叠区

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


def _tutor_module(report: dict, prefix: str) -> dict | None:
    """从 report["tutor"] 按模块名前缀取模块（module 为 ### 子标题原文）。"""
    for mod in report.get("tutor", []):
        if str(mod.get("module", "")).startswith(prefix):
            return mod
    return None


def _read_first_banner(report: dict) -> str:
    """v6.0 读前须知图例条：取「今日速览」body 内以 **读前须知** 开头的段落；
    取不到不渲染（fail-soft）。数据链路：_parse_tutor 对模块 body 原样捕获。"""
    mod = _tutor_module(report, "今日速览")
    if not mod:
        return ""
    para: list[str] = []
    for ln in mod.get("body", []):
        s = ln.strip()
        if not s:
            if para:
                break
            continue
        if para or s.startswith("**读前须知**"):
            para.append(s)
    if not para:
        return ""
    text = "<br>".join(_esc(p) for p in para)
    return f'<div class="read-first">📖 {text}</div>'


def _lesson_card(report: dict) -> str:
    """v6.0 今日一课摘要卡：「深度第一课」标题 + 先记住一句话；取不到不渲染。"""
    mod = _tutor_module(report, "深度第一课")
    if not mod:
        return ""
    module_name = str(mod.get("module", ""))
    title = re.split("[：:]", module_name, maxsplit=1)[-1].strip()
    hook = ""
    for ln in mod.get("body", []):
        s = ln.strip()
        if "先记住一句话" in s:
            hook = s.strip("*").strip()
            break
    title_html = f'<div class="lesson-title">{_esc(title)}</div>' if title else ""
    hook_html = f'<div class="lesson-hook">{_esc(hook)}</div>' if hook else ""
    if not title_html and not hook_html:
        return ""
    return f"""
    <div class="lesson-card">
      <div class="lesson-tag">今日一课</div>
      {title_html}
      {hook_html}
      <div class="lesson-more">完整版见「导师课堂」标签页</div>
    </div>"""


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

    # v6.0 理解优先：teach 三层子行（槽值=子行原文含 emoji，旧 IR 无此键时跳过）
    teach = item.get("teach") or {}
    teach_lines = "".join(
        f'<div class="teach-line">{_esc(teach[slot])}</div>'
        for slot in ("principle", "impact", "career")
        if teach.get(slot)
    )
    teach_html = f'<div class="teach">{teach_lines}</div>' if teach_lines else ""

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
      {teach_html}
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
    """持续追踪（B·v5.3）。

    v8.1 起表格化：方向 / 变化（Δ）/ 连续 / 当日进展四要素分列。变化独立成列是这次
    做厚的核心——此前方向、变化、期数挤在一行散文里，跨日记忆实际退化成日志，
    读者扫不出「哪条在加速、哪条在熄火」。v6.0 及更早的项目符号形态继续兼容。
    """
    if not items:
        return ""
    if any(it.get("delta") or it.get("direction") for it in items):
        trs = []
        for it in items:
            d = it.get("delta") or "—"
            cls = (
                "tk-delta-up" if "↑" in d or "加速" in d
                else "tk-delta-down" if "↓" in d or "缓和" in d
                else "tk-delta-turn" if "⚡" in d
                else "tk-delta-flat"
            )
            trs.append(
                f'<tr><td class="tk-t-topic">{_esc(it.get("topic", ""))}</td>'
                f'<td>{_esc(it.get("direction", "—"))}</td>'
                f'<td class="{cls}">{_esc(d)}</td>'
                f'<td class="tk-streak">{_esc(it.get("streak", "—"))}</td>'
                f'<td class="tk-progress">{_esc(it.get("progress", "—"))}</td></tr>'
            )
        return f"""
    <section class="tracking-block">
      <h2 class="tk-title">📈 持续追踪 <span class="tk-sub">跨日记忆 · 变化列</span></h2>
      <table class="tk-table">
        <thead><tr><th>主题</th><th>方向</th><th>变化（Δ）</th><th>连续</th><th>当日进展</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>
    </section>"""
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
    """确定时点表格（C·v5.3，v6.1 起为「未来推演」节内的子表）。"""
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
      <table class="ct-table">
        <thead><tr><th>日期</th><th>事件</th><th>环节</th><th>重要度</th><th>来源</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>"""


def _future_block(report: dict) -> str:
    """未来推演（v6.1 推演型前瞻）：引言 + 推演卡（现状锚点/剧本/验证窗口）+ 确定时点表。

    三类数据任一存在即渲染；全空返回空串（兼容旧版仅催化剂表的历史报告）。
    """
    intro = (report.get("future_intro") or "").strip()
    notes = report.get("catalyst_notes") or []
    rows = report.get("catalysts") or []
    if not intro and not notes and not rows:
        return ""
    part_label = {"现状锚点": "fx-anchor", "推演链": "fx-chain"}
    cards = []
    for n in notes:
        parts = "".join(
            f'<div class="fx-part"><span class="fx-key">{_esc(k)}</span>'
            f'<span class="fx-val">{_esc(v)}</span></div>'
            for k, v in n.get("parts", [])
        )
        cls = "fx-card"
        cards.append(f'<div class="{cls}"><div class="fx-title">{_esc(n["title"])}</div>{parts}</div>')
    intro_html = f'<p class="fx-intro">{_esc(intro)}</p>' if intro else ""
    cards_html = f'<div class="fx-grid">{"".join(cards)}</div>' if cards else ""
    table_html = _catalyst_block(rows)
    sub = "推演块（剧本+验证窗口）+ 确定时点"
    return f"""
    <section class="catalyst-block">
      <h2 class="ct-title">🔮 未来推演 <span class="ct-sub">{sub}</span></h2>
      {intro_html}
      {cards_html}
      {table_html}
    </section>"""


def _feynman_block(items: list) -> str:
    """费曼解释（F1.3·v5.4，v6.0 前移到新闻之前）：大白话术语卡片。"""
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


def _scoreboard(rows: list) -> str:
    """四态计分板（v8.1）：命中/偏差/打脸/逾期四行独立成表，让欠账自己站起来。

    纪律：不显示命中率（该指标已废弃，虚高正是审计抓出的造假信号）；
    打脸 0 这一格必须显眼地是 0——它比任何命中数字都重要。
    """
    if not rows:
        return ""
    trs = []
    for r in rows:
        state = r.get("state", "")
        tone = (
            "sb-hit" if "命中" in state and "偏差" not in state
            else "sb-partial" if "偏差" in state
            else "sb-miss" if "打脸" in state
            else "sb-over"
        )
        # 打脸为零时整行点红：零打脸是红旗，不是"暂时没有"
        zero_flag = (
            " sb-zero"
            if tone == "sb-miss" and r.get("count", "").strip() in ("0", "0 条", "—")
            else ""
        )
        trs.append(
            f'<tr class="{tone}{zero_flag}"><td class="sb-state">{_esc(state)}</td>'
            f'<td class="sb-count">{_esc(r.get("count", "—"))}</td>'
            f'<td>{_esc(r.get("latest", "—"))}</td>'
            f'<td class="sb-next">{_esc(r.get("next", "—"))}</td></tr>'
        )
    return f"""
      <table class="sb-table">
        <thead><tr><th>状态</th><th>累计条数</th><th>最近一次</th><th>下一步</th></tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>"""


def _reader_voice_block(rv: dict | None) -> str:
    """读者回声（v8.1 固定节）：读者原话逐字引用 + 本期已改/未改台账。

    这是读者环的正文出口——反馈只躺在 state 文件里等于闭环没合上。
    原话逐字呈现，不加工不美化；本期无反馈也照写「无新反馈」，整节不省略。
    """
    if not rv:
        return ""
    intro = f'<div class="rv-intro">{_esc(rv.get("intro", ""))}</div>' if rv.get("intro") else ""
    quotes = ""
    if rv.get("quotes"):
        qs = []
        for q in rv["quotes"]:
            meta = f'<div class="rv-meta">{_esc(q["meta"])}</div>' if q.get("meta") else ""
            qs.append(
                f'<blockquote class="rv-quote">{_esc(q["text"])}{meta}</blockquote>'
            )
        quotes = "".join(qs)
    else:
        quotes = '<div class="rv-none">本期无新反馈，最近一次记录见下。</div>'
    li = "".join(
        f'<li><b>{_esc(x["issue"])}</b>：{_esc(x["text"])}</li>' for x in rv.get("ledger", [])
    )
    ledger = f'<ul class="rv-ledger">{li}</ul>' if li else ""
    return f"""
    <section class="rv-block">
      <h2 class="rv-title">🗣 读者回声 <span class="tk-sub">你的原话进了正文</span></h2>
      {intro}
      {quotes}
      {ledger}
    </section>"""


def _forward_review_block(fr: dict | None) -> str:
    """前瞻兑现回顾（v5.10，v6.0 起在日报视图渲染，对齐 md 曲线）：回看卡 + 四态计分板 + 预判成绩单。"""
    if not fr:
        return ""
    cards = []
    for it in fr.get("items", []):
        parts = "".join(
            f'<div class="fr-part"><b>{_esc(key)}</b>：{_esc(text)}</div>'
            for key, text in it.get("parts", [])
        )
        cards.append(
            f'<div class="fr-card"><div class="fr-title">{_esc(it.get("title", ""))}</div>{parts}</div>'
        )
    if not cards and not fr.get("summary") and not fr.get("scoreboard"):
        return ""
    intro = f'<div class="fr-intro">{_esc(fr.get("intro", ""))}</div>' if fr.get("intro") else ""
    summary = ""
    if fr.get("summary"):
        label = fr.get("summary_label") or "闭环小结"
        summary = f'<div class="fr-summary">{_esc(label)}：{_esc(fr["summary"])}</div>'
    board = _scoreboard(fr.get("scoreboard", []))
    return f"""
    <section class="fr-block">
      <h2 class="fr-title">✅ 兑现回顾 <span class="tk-sub">预告 → 验证闭环 · 允许打脸</span></h2>
      {intro}
      <div class="fr-grid">{"".join(cards)}</div>
      {board}
      {summary}
    </section>"""


def render(report: dict) -> str:
    """渲染日报视图 HTML 片段（v6.0 理解优先曲线，对齐 md 章节顺序：
    读前须知 → 今日一课 → 今日要点 → 费曼解释 → 五环节新闻 → 持续追踪
    → 前瞻催化剂 → 前瞻兑现回顾 → 深度解读 → 未来借鉴 → 自检折叠）。
    产业链关联/横向维度属独立 Tab（chain/dimensions），不在本视图重复。"""
    read_first = _read_first_banner(report)
    lesson = _lesson_card(report)
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
    catalysts = _future_block(report)
    feynman = _feynman_block(report.get("feynman", []))
    forward_review = _forward_review_block(report.get("forward_review"))
    deep_dive = _deep_dive_block(report.get("deep_dive", []))
    future_lessons = _future_lessons_block(report.get("future_lessons", []))
    reader_voice = _reader_voice_block(report.get("reader_voice"))
    selfcheck = _selfcheck_block(report.get("selfcheck", []))

    return f"""
    <div class="report-view">
      {read_first}
      {lesson}
      {highlights}
      {feynman}
      {seg_html}
      {tracking}
      {catalysts}
      {forward_review}
      {deep_dive}
      {future_lessons}
      {reader_voice}
      {selfcheck}
    </div>"""
