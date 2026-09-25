#!/usr/bin/env python3
"""report_viz.views.dimensions_view — 横向维度可视化（市场/政策/资本）。

把日报新增的 ## 市场与需求 / ## 政策与监管 / ## 资本与投融资 三个维度，
渲染为带导语、子节卡片与来源徽章的视图；内联 [名称](url) 转为可点击链接，
来源级别用 A 绿 / B 琥珀 徽章呈现（与日报卡片视图一致）。
"""
from __future__ import annotations

import html
import re

from .. import parser as _p

DIM_META = {
    "市场与需求": {"color": "#0891b2", "icon": "📈", "desc": "供需 · 价格 · 景气度"},
    "政策与监管": {"color": "#7c3aed", "icon": "⚖️", "desc": "出口管制 · 补贴 · 安全审查"},
    "资本与投融资": {"color": "#16a34a", "icon": "💰", "desc": "融资 · 并购 · IPO · 产线投资"},
}

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def _esc(text):
    return html.escape(str(text or ""), quote=True)


def _render_body(body: str) -> str:
    """转义后把 [name](url) 转为链接、换行转 <br>。"""
    esc = _esc(body).replace("\n", "<br>")
    return _LINK_RE.sub(
        lambda m: f'<a href="{_esc(m.group(2))}" class="src-link" '
        f'target="_blank" rel="noopener">{_esc(m.group(1))}</a>',
        esc,
    )


def _badges(sources):
    if not sources:
        return ""
    chips = []
    for x in sources:
        cls = "badge-a" if x["level"] == "A" else "badge-b"
        chips.append(
            f'<a class="{cls}" href="{_esc(x["url"])}" target="_blank" '
            f'rel="noopener">{_esc(x["name"])} · {x["level"]}</a>'
        )
    return f'<div class="ds-srcs">{"".join(chips)}</div>'


def render(report: dict) -> str:
    dims = report.get("dimensions", {})
    if not dims:
        return '<div class="dim-empty">本期日报未包含横向维度小节。</div>'

    blocks = []
    # 固定顺序：市场 → 政策 → 资本
    for dim in ("市场与需求", "政策与监管", "资本与投融资"):
        if dim not in dims:
            continue
        meta = DIM_META.get(dim, {})
        color = meta.get("color", "#334155")
        d = dims[dim]
        subs = d.get("subs", [])
        a_count = sum(1 for s in subs if s["level"] == "A")

        head = (
            f'<div class="dim-head" style="border-color:{color}">'
            f'<span class="dim-ico" style="background:{color}">{meta.get("icon", "")}</span>'
            f'<div><div class="dim-name">{_esc(dim)}</div>'
            f'<div class="dim-desc">{_esc(meta.get("desc", ""))} · 共 {len(subs)} 节 / A 级 {a_count}</div>'
            f"</div></div>"
        )
        intro = d.get("intro", "")
        intro_html = (
            f'<div class="dim-intro">{_render_body(intro)}</div>' if intro else ""
        )

        sub_html = []
        for s in subs:
            sub_html.append(
                f'<div class="dim-sub">'
                f'<div class="ds-title">{_esc(s["title"])}</div>'
                f'<div class="ds-body">{_render_body(s["body"])}</div>'
                f"{_badges(s['sources'])}"
                f"</div>"
            )

        blocks.append(
            f'<section class="dim-block">{head}{intro_html}{"".join(sub_html)}</section>'
        )

    return "".join(blocks)
