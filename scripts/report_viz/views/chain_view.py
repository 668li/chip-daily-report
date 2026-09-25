#!/usr/bin/env python3
"""report_viz.views.chain_view — 产业链全貌可视化（价值链条形信息图）。

把日报的「5 环节 + 3 组关联」渲染为：
  - 环节规模条（每环节新闻数 + A/B 来源级别分布）
  - 价值链条形 SVG：上游支撑层(材料 / EDA) → 中游核心层(设计 → 制造)
    → 下游层(封测 / OSAT) → 终端应用，卡片内为本期真实厂商 / 事件，
    流向箭头表达「支撑 / 制造 / 封测」的产业链传导关系
  - 三组产业链关联「传导链」水平流图（量化明细 + 技术领域链）

扩展方式：与 report_view 一样，导出的 render(report) 在 VIEW_REGISTRY 注册即可。
未来新增「趋势图」「周报对比」等模块，照此新增一个 view 文件并注册。
"""
from __future__ import annotations

import html
import re

from ..parser import SEG_ORDER

SEG_META = {
    "设计": ("芯片设计", "#2563eb"),
    "制造": ("晶圆制造", "#7c3aed"),
    "封测": ("封测 / OSAT", "#0891b2"),
    "EDA": ("EDA / IP", "#db2777"),
    "材料": ("材料 / 设备", "#16a34a"),
}
PALETTE = ["#2563eb", "#db2777", "#16a34a"]
LVL_COLOR = {"A": "#16a34a", "B": "#d97706", "C": "#dc2626"}

# 价值链条分层布局：上游 → 中游 → 下游（slot: left / right / center）
TIERS = [
    ("上游支撑层", [("EDA", "left"), ("材料", "right")]),
    ("中游核心层", [("设计", "left"), ("制造", "right")]),
    ("下游层", [("封测", "center")]),
]


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _trunc(s: str, n: int = 16) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def _seg_seq(title: str):
    """从关联组标题的（环节）标签按出现顺序提取环节路径（去重保序）。"""
    pos = []
    for k in SEG_ORDER:
        for m in re.finditer(re.escape(k), title):
            pos.append((m.start(), k))
    pos.sort()
    seq = []
    for _, k in pos:
        if not seq or seq[-1] != k:
            seq.append(k)
    return seq


def _seg_strip(report: dict) -> str:
    cells = []
    for s in SEG_ORDER:
        items = report.get("segments", {}).get(s, [])
        a = sum(1 for it in items if it["level"] == "A")
        b = sum(1 for it in items if it["level"] == "B")
        c = sum(1 for it in items if it["level"] == "C")
        label, color = SEG_META[s]
        cells.append(
            f'<div class="ss-cell" style="border-color:{color}">'
            f'<div class="ss-name" style="color:{color}">{label}</div>'
            f'<div class="ss-num">{len(items)} 条</div>'
            f'<div class="ss-ab">A {a} · B {b} · C {c}</div></div>'
        )
    return f'<div class="seg-strip">{"".join(cells)}</div>'


def _stage_card(x, y, w, h, seg, items):
    label, color = SEG_META[seg]
    lines = ""
    ty = y + 52
    for it in items[:4]:
        lc = LVL_COLOR.get(it["level"], "#64748b")
        lines += (
            f'<circle cx="{x+20}" cy="{ty-4}" r="4.2" fill="{lc}"/>'
            f'<text x="{x+33}" y="{ty}" font-size="13" fill="#334155">'
            f"{_esc(_trunc(it['title'], 17))}</text>"
        )
        ty += 22
    if len(items) > 4:
        lines += (
            f'<text x="{x+33}" y="{ty}" font-size="12" fill="#94a3b8">'
            f"+{len(items) - 4} 条…</text>"
        )
    return (
        f'<g class="stage" data-seg="{seg}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#fff" '
        f'stroke="{color}" stroke-width="2.5" filter="url(#ds)"/>'
        f'<path d="M{x},{y+14} a14,14 0 0 1 14,-14 h{w-28} a14,14 0 0 1 14,14 v20 h-{w} z" '
        f'fill="{color}"/>'
        f'<text x="{x+15}" y="{y+25}" fill="#fff" font-size="15" font-weight="700">{label}</text>'
        f'<text x="{x+w-15}" y="{y+25}" text-anchor="end" fill="#fff" font-size="13" '
        f'opacity=".92">{len(items)} 条</text>'
        f"{lines}"
        f"</g>"
    )


def _arrow(x1, y1, x2, y2, color="#475569", width=2.6, dash=False):
    da = ' stroke-dasharray="7 5"' if dash else ""
    return (
        f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
        f'stroke="{color}" stroke-width="{width}" marker-end="url(#arrow)"{da} '
        f'class="{"flow" if dash else "bk"}"/>'
    )


def _arrow_label(x, y, text, color="#475569"):
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" font-size="11.5" '
        f'font-weight="600" fill="{color}">{_esc(text)}</text>'
    )


def _generate_svg(report: dict) -> str:
    W, H = 1000, 672
    # 卡片几何
    CW, CH = 400, 124
    LX, RX = 70, 530          # 左 / 右 列 x
    CX = 300                  # 下游居中 x
    Y_UP, Y_MID, Y_DOWN = 120, 288, 456
    demand_y, term_y = 18, 600

    seg_items = {s: report.get("segments", {}).get(s, []) for s in SEG_ORDER}

    def card_pos(slot):
        if slot == "left":
            return LX, (Y_UP if False else None)
        return None

    # 各卡片坐标
    pos = {
        "EDA": (LX, Y_UP),
        "材料": (RX, Y_UP),
        "设计": (LX, Y_MID),
        "制造": (RX, Y_MID),
        "封测": (CX, Y_DOWN),
    }

    def cx(slot_x, w=CW):
        return slot_x + w / 2

    # 节点中心
    n_cx = {s: cx(px) for s, (px, _) in pos.items()}
    n_bottom = {s: py + CH for s, (_, py) in pos.items()}
    n_top = {s: py for s, (_, py) in pos.items()}

    stage_svg = []
    for tier_name, slots in TIERS:
        for seg, slot in slots:
            px, py = pos[seg]
            stage_svg.append(_stage_card(px, py, CW, CH, seg, seg_items[seg]))

    # 流向箭头（价值链正向传导）
    arrows = []
    # 需求 → 上游
    arrows.append(_arrow(500, demand_y + 56, 500, Y_UP - 4))
    # EDA → 设计（支撑，同源 x）
    arrows.append(_arrow(n_cx["EDA"], n_bottom["EDA"], n_cx["设计"], n_top["设计"], color=SEG_META["EDA"][1]))
    arrows.append(_arrow_label(n_cx["EDA"] + 14, (n_bottom["EDA"] + n_top["设计"]) / 2, "支撑", SEG_META["EDA"][1]))
    # 材料 → 制造（供给，同源 x）
    arrows.append(_arrow(n_cx["材料"], n_bottom["材料"], n_cx["制造"], n_top["制造"], color=SEG_META["材料"][1]))
    arrows.append(_arrow_label(n_cx["材料"] - 14, (n_bottom["材料"] + n_top["制造"]) / 2, "供给", SEG_META["材料"][1]))
    # 设计 → 制造（中游主链路，水平）
    arrows.append(_arrow(LX + CW, Y_MID + CH / 2, RX, Y_MID + CH / 2, color="#334155", width=3))
    arrows.append(_arrow_label((LX + CW + RX) / 2, Y_MID + CH / 2 - 10, "设计交付", "#334155"))
    # 制造 → 封测（下游，对角）
    arrows.append(_arrow(n_cx["制造"], n_bottom["制造"], n_cx["封测"], n_top["封测"], color="#334155", width=3))
    arrows.append(_arrow_label((n_cx["制造"] + n_cx["封测"]) / 2 + 30, (n_bottom["制造"] + n_top["封测"]) / 2, "封测", "#334155"))
    # 封测 → 终端
    arrows.append(_arrow(500, n_bottom["封测"], 500, term_y - 4, color="#334155", width=3))

    # 分层标签
    tier_pills = []
    for y, name in [(Y_UP - 34, "上游支撑层"), (Y_MID - 34, "中游核心层"), (Y_DOWN - 34, "下游层")]:
        pill_w = len(name) * 15 + 26
        tier_pills.append(
            f'<g><rect x="60" y="{y}" width="{pill_w}" height="26" rx="13" fill="#0f172a"/>'
            f'<text x="73" y="{y+18}" fill="#fff" font-size="13" font-weight="700">{_esc(name)}</text></g>'
        )

    # 需求 / 终端 横幅
    demand = (
        f'<g><rect x="60" y="{demand_y}" width="880" height="56" rx="16" fill="url(#demand)"/>'
        f'<text x="84" y="{demand_y+34}" fill="#fff" font-size="17" font-weight="800">需求驱动</text>'
        f'<text x="186" y="{demand_y+33}" fill="#fff" font-size="13.5" opacity=".92">'
        f"AI 算力军备竞赛 · HBM4 量产交付 · 国产替代加速</text></g>"
    )
    terminal = (
        f'<g><rect x="60" y="{term_y}" width="880" height="56" rx="16" fill="url(#term)"/>'
        f'<text x="84" y="{term_y+34}" fill="#fff" font-size="17" font-weight="800">终端应用</text>'
        f'<text x="186" y="{term_y+33}" fill="#fff" font-size="13.5" opacity=".92">'
        f"AI 服务器 · 智能手机 · 汽车电子 · 高性能计算</text></g>"
    )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="产业链全貌价值链条形图" class="chain-svg">'
        f'<defs>'
        f'<marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" '
        f'markerUnits="strokeWidth"><path d="M0,0 L7,3 L0,6 Z" fill="#475569"/></marker>'
        f'<filter id="ds" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.13"/></filter>'
        f'<linearGradient id="demand" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#0f172a"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient>'
        f'<linearGradient id="term" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#0891b2"/><stop offset="1" stop-color="#155e75"/></linearGradient>'
        f"</defs>"
        f"{demand}{terminal}"
        f'{"".join(tier_pills)}'
        f'{"".join(arrows)}'
        f'{"".join(stage_svg)}'
        f"</svg>"
    )


def _chain_ribbon(gi: int, grp: dict) -> str:
    color = PALETTE[gi % len(PALETTE)]
    seq = _seg_seq(grp["title"])
    steps = ""
    for i, k in enumerate(seq):
        steps += (
            f'<span class="cr-step" data-seg="{k}" style="border-color:{color}">'
            f"{SEG_META[k][0]}</span>"
        )
        if i < len(seq) - 1:
            steps += '<span class="cr-arrow">→</span>'
    summary = _trunc(grp["body"], 90)
    return f"""
    <div class="chain-ribbon" style="border-left:4px solid {color}">
      <div class="cr-head">
        <span class="cr-num" style="background:{color}">{gi+1}</span>
        <span class="cr-title">{_esc(grp['title'])}</span>
      </div>
      <div class="cr-flow">{steps}</div>
      <p class="cr-body">{_esc(summary)}</p>
    </div>"""


def render(report: dict) -> str:
    """渲染产业链全貌视图 HTML 片段。"""
    svg = _generate_svg(report)
    ribbons = "".join(
        _chain_ribbon(gi, g) for gi, g in enumerate(report.get("chain_groups", []))
    )
    return f"""
    <div class="chain-view">
      <p class="chain-intro">半导体价值链条：<b>上游支撑层</b>（材料 / 设备、EDA / IP）
        → <b>中游核心层</b>（芯片设计 → 晶圆制造）→ <b>下游层</b>（封测 / OSAT）→ 终端应用。
        卡片内为本期真实厂商 / 事件（圆点：<span style="color:#16a34a">绿=A 级一手</span> /
        <span style="color:#d97706">琥珀=B 级聚合</span>）；下方为三组产业链关联传导链（含量化与技术依赖）。</p>
      {_seg_strip(report)}
      <div class="chain-svg-wrap">
        {svg}
      </div>
      <h3 class="chain-detail-title">三组产业链关联传导链（量化 + 技术领域链）</h3>
      <div class="chain-ribbons">{ribbons}</div>
    </div>"""
