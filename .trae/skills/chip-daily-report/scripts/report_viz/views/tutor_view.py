#!/usr/bin/env python3
"""report_viz.views.tutor_view — 导师课堂视图（v5.8）。

把日报的 '## 今日导师课' 小节渲染成"一节课"：
  - 今日速览：黑板书风格类比大卡（一句话记住今天）
  - 深度第一课：课件卡（掰开揉碎讲透 1-2 件事）
  - 必懂概念：导师重点划（概念网格）
  - 课后思考：2-3 道引导性思考题

学生视角：不堆术语，用类比 + 问题引导；与费曼解释（词是什么）互补，
导师课解决"这些意味着什么、我该怎么想"。
"""
from __future__ import annotations

import html
import re

# 模块 -> (图标, 副标题)
MOD_META = {
    "今日速览": ("🎬", "一句话记住今天 · 类比开场"),
    "深度第一课": ("📚", "今日最值得弄懂的一件事 · 掰开揉碎"),
    "必懂概念": ("🎯", "导师重点划 · 记住这几个就够"),
    "课后思考": ("✍️", "带着问题离开 · 想一想再说"),
}

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _inline(text: str) -> str:
    """行内渲染：**加粗** → <b>；其余转义。"""
    return _BOLD_RE.sub(r"<b>\1</b>", _esc(text))


def _md_lines(body: list) -> str:
    """把模块 body 的原始 markdown 行渲染为 HTML：连续 - 列表 / 编号列表 / 段落。"""
    if not body:
        return ""
    out = []
    i = 0
    while i < len(body):
        line = body[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("- "):
            items = []
            while i < len(body) and body[i].strip().startswith("- "):
                items.append(f"<li>{_inline(body[i].strip()[2:])}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
        elif re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(body) and re.match(r"^\d+\.\s+", body[i].strip()):
                items.append(
                    f"<li>{_inline(re.sub(r'^\\d+\\.\\s+', '', body[i].strip()))}</li>"
                )
                i += 1
            out.append(f"<ol>{''.join(items)}</ol>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
            i += 1
    return "".join(out)


def _speed_block(body: list) -> str:
    """今日速览：黑板书风格类比卡。"""
    paras = _md_lines(body)
    return f"""
    <section class="tu-block tu-speed">
      <h2 class="tu-title">🎬 今日速览 <span class="tu-sub">一句话记住今天 · 类比开场</span></h2>
      <div class="tu-board">{paras}</div>
    </section>"""


def _lesson_block(body: list) -> str:
    """深度第一课：课件卡。首行为加粗导语 → 课件副题，其余为要点。"""
    lead = ""
    points = []
    for ln in body:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("**") and s.endswith("**"):
            lead = s.strip("*")
        else:
            points.append(s)
    lead_html = (
        f'<div class="tu-lead">💡 {_inline(lead)}</div>' if lead else ""
    )
    points_html = _md_lines(points)
    return f"""
    <section class="tu-block tu-lesson">
      <h2 class="tu-title">📚 深度第一课 <span class="tu-sub">今日最值得弄懂的一件事 · 掰开揉碎</span></h2>
      <div class="tu-lesson-card">
        {lead_html}
        {points_html}
      </div>
    </section>"""


def _concepts_block(body: list) -> str:
    """必懂概念：概念网格（导师重点划）。每行 '- **词**：解释' 一张卡。"""
    cards = []
    for ln in body:
        m = re.match(r"^-\s*\*\*(.+?)\*\*\s*[:：]\s*(.+)$", ln.strip())
        if m:
            cards.append(
                f'<div class="tu-concept"><div class="tu-concept-term">{_esc(m.group(1))}</div>'
                f'<div class="tu-concept-text">{_inline(m.group(2))}</div></div>'
            )
    if not cards:
        return ""
    return f"""
    <section class="tu-block tu-concepts">
      <h2 class="tu-title">🎯 必懂概念 <span class="tu-sub">导师重点划 · 记住这几个就够 · {len(cards)} 个</span></h2>
      <div class="tu-concept-grid">{"".join(cards)}</div>
    </section>"""


def _homework_block(body: list) -> str:
    """课后思考：编号思考题卡。"""
    qs = []
    for ln in body:
        m = re.match(r"^(\d+)\.\s+(.+)$", ln.strip())
        if m:
            qs.append((int(m.group(1)), m.group(2)))
    if not qs:
        return ""
    cards = []
    for num, text in qs:
        cards.append(
            f'<div class="tu-q"><span class="tu-q-num">{num}</span>'
            f'<span class="tu-q-text">{_inline(text)}</span></div>'
        )
    return f"""
    <section class="tu-block tu-homework">
      <h2 class="tu-title">✍️ 课后思考 <span class="tu-sub">带着问题离开 · 想一想再说 · {len(qs)} 题</span></h2>
      <div class="tu-q-list">{"".join(cards)}</div>
    </section>"""


def render(report: dict) -> str:
    """渲染导师课堂视图 HTML 片段。"""
    tutor = report.get("tutor", [])
    if not tutor:
        return (
            '<div class="tu-empty">本日报暂无「今日导师课」小节'
            '（v5.8 导师课堂：今日速览 / 深度第一课 / 必懂概念 / 课后思考）</div>'
        )

    blocks = {"今日速览": [], "深度第一课": [], "必懂概念": [], "课后思考": []}
    for it in tutor:
        mod = it.get("module", "")
        body = it.get("body", [])
        # 兼容带编号的标题，如 '深度第一课：AI 的内存到底卡在哪儿？'
        for key in blocks:
            if mod.startswith(key):
                blocks[key].append({"body": body, "title": mod})
                break

    html_parts = []
    if blocks["今日速览"]:
        html_parts.append(_speed_block(blocks["今日速览"][0]["body"]))
    if blocks["深度第一课"]:
        for lesson in blocks["深度第一课"]:
            html_parts.append(_lesson_block(lesson["body"]))
    if blocks["必懂概念"]:
        html_parts.append(_concepts_block(blocks["必懂概念"][0]["body"]))
    if blocks["课后思考"]:
        html_parts.append(_homework_block(blocks["课后思考"][0]["body"]))
    if not html_parts:
        return (
            '<div class="tu-empty">「今日导师课」小节存在但未识别到标准模块'
            '（应含 今日速览 / 深度第一课 / 必懂概念 / 课后思考）</div>'
        )

    return f"""
    <div class="tutor-view">
      <div class="tu-intro">
        <b>📖 今日导师课</b> —— 把今天的日报当一节课来上：先听懂今天讲了什么
        （今日速览），再弄懂最值得弄懂的一件事（深度第一课），记住几个核心概念
        （必懂概念），最后带着问题自己想一想（课后思考）。面向零基础读者。
      </div>
      {"".join(html_parts)}
    </div>"""
