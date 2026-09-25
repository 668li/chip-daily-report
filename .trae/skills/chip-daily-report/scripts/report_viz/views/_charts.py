#!/usr/bin/env python3
"""report_viz.views._charts — 趋势图 / 周报对比 视图共用的小工具。

提供：HTML 转义、项目路径定位、quality_dashboard.json 读取，
以及纯字符串拼接的 SVG 折线图 / 条形图 / 水平堆叠条（零第三方依赖）。

图表约定：
  - 所有 SVG 用 viewBox + 百分比宽度，容器加 min-width 保证小屏可横滑；
  - 折线图多序列各自独立归一化（映射到绘图区高度），
    因此可以同图对比量纲不同的指标（如「条数」与「A 级占比」），
    精确数值一律标注在数据点上，避免双 Y 轴误导；
  - 折线 / 条形 / 堆叠均带 <title> 悬浮提示。
"""
from __future__ import annotations

import html
import json
from pathlib import Path


# ---------------- 基础 ----------------

def esc(text) -> str:
    """HTML 转义（属性安全）。"""
    return html.escape(str(text or ""), quote=True)


def project_root() -> Path:
    """views/_charts.py -> 项目根目录（含 rules/ delivery/ scripts/ 等）。"""
    return Path(__file__).resolve().parents[3]


def delivery_dir() -> Path:
    return project_root() / "delivery"


def load_dashboard() -> dict | None:
    """读取 delivery/quality_dashboard.json；不存在 / 损坏时返回 None（调用方降级）。"""
    try:
        p = delivery_dir() / "quality_dashboard.json"
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_date(d: str) -> str:
    """'20260809' -> '08-09'；非 8 位数字原样返回。"""
    s = str(d)
    return f"{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else s


def fmt_ratio(v) -> str:
    """0.357 -> '36%'；None -> '—'。"""
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


# ---------------- SVG 折线图 ----------------

def svg_lines(x_labels: list, series: list[dict], width: int = 940, height: int = 216) -> str:
    """多序列折线图。

    series: [{name, color, values: [float|None, ...], fmt: (float)->str}]，
            各序列独立归一化，None 值断点（不连线、不标注）。
    x_labels: 与 values 等长的 X 轴刻度。
    """
    n = len(x_labels)
    if not n or not series:
        return ""
    pad_l, pad_r, pad_t, pad_b = 12, 16, 20, 36
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    xs = [pad_l + pw * i / (n - 1) for i in range(n)] if n > 1 else [pad_l + pw / 2]

    def _y(vals, v):
        vs = [x for x in vals if x is not None]
        if not vs:
            return pad_t + ph / 2
        lo, hi = min(vs), max(vs)
        if hi - lo < 1e-9:
            hi = lo + 1.0
        return pad_t + ph * (0.96 - 0.88 * (v - lo) / (hi - lo))

    parts = []
    # 网格线（无数值刻度，数值以数据点标注为准）
    for i in range(5):
        gy = pad_t + ph * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#eef2f7" stroke-width="1"/>'
        )
    for i, lab in enumerate(x_labels):
        parts.append(
            f'<text x="{xs[i]:.1f}" y="{height - 12}" text-anchor="middle" '
            f'font-size="11.5" fill="#64748b">{esc(lab)}</text>'
        )
    for s in series:
        vals = s["values"]
        pts = [(i, xs[i], _y(vals, v)) for i, v in enumerate(vals) if v is not None]
        if len(pts) >= 2:
            poly = " ".join(f"{x:.1f},{y:.1f}" for _, x, y in pts)
            parts.append(
                f'<polyline points="{poly}" fill="none" stroke="{s["color"]}" '
                f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        fmt = s.get("fmt") or (lambda q: f"{q:.1f}")
        for i, x, y in pts:
            label = fmt(vals[i])
            parts.append(
                f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" '
                f'stroke="{s["color"]}" stroke-width="2.2">'
                f'<title>{esc(x_labels[i])} · {esc(s["name"])}：{esc(label)}</title></circle>'
                f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-size="10.5" '
                f'font-weight="700" fill="{s["color"]}">{esc(label)}</text></g>'
            )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" '
        f'aria-label="趋势折线图">{"".join(parts)}</svg>'
    )


# ---------------- SVG 信号强度曲线（固定量纲，迭代5） ----------------

# 方向 -> 强度数值（有绝对语义，与 svg_lines 的独立归一化不同）
DIRECTION_LEVEL = {"down": -2.0, "loose": -1.0, "flat": 0.0, "tight": 1.0, "up": 2.0}
DIRECTION_LABEL = {
    "down": "下行", "loose": "趋松", "flat": "平稳", "tight": "趋紧", "up": "上行",
}


def svg_signal_lines(
    x_labels: list,
    series: list[dict],
    width: int = 940,
    height: int = 260,
) -> str:
    """信号强度曲线：Y 轴固定 -2..2（down=-2 … up=2），不归一化。

    series: [{name, color, values: [float|None, ...], labels: [str, ...]}]，
      values 为方向强度数值（None 断点），labels 为数据点上的汉字标注（如「下行」）。
    画零轴线 + 半程虚线网格，反转点（相邻非 None 值差 > 1）自动加 ⚠ 标记。
    用于周度复盘 / 信号演进：同一坐标下可直观看到主题从 up 断崖到 down。
    """
    n = len(x_labels)
    if not n or not series:
        return ""
    pad_l, pad_r, pad_t, pad_b = 14, 16, 22, 38
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    xs = [pad_l + pw * i / (n - 1) for i in range(n)] if n > 1 else [pad_l + pw / 2]

    def _y(v: float) -> float:
        return pad_t + ph * (2.2 - v) / 4.4

    parts = []
    # 零轴线（更粗）+ 半程虚线
    parts.append(
        f'<line x1="{pad_l}" y1="{_y(0):.1f}" x2="{width - pad_r}" y2="{_y(0):.1f}" '
        f'stroke="#cbd5e1" stroke-width="1.6"/>'
    )
    for lv in (-1.0, 1.0):
        parts.append(
            f'<line x1="{pad_l}" y1="{_y(lv):.1f}" x2="{width - pad_r}" y2="{_y(lv):.1f}" '
            f'stroke="#eef2f7" stroke-width="1" stroke-dasharray="4 4"/>'
        )
    # Y 轴刻度文字
    for lv in (-2.0, -1.0, 0.0, 1.0, 2.0):
        parts.append(
            f'<text x="{pad_l - 6}" y="{_y(lv) + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#94a3b8">{lv:.0f}</text>'
        )
    for i, lab in enumerate(x_labels):
        parts.append(
            f'<text x="{xs[i]:.1f}" y="{height - 14}" text-anchor="middle" '
            f'font-size="11.5" fill="#64748b">{esc(lab)}</text>'
        )
    for s in series:
        vals, labels = s["values"], s["labels"]
        pts = [(i, xs[i], _y(vals[i])) for i, v in enumerate(vals) if v is not None]
        if len(pts) >= 2:
            poly = " ".join(f"{x:.1f},{y:.1f}" for _, x, y in pts)
            parts.append(
                f'<polyline points="{poly}" fill="none" stroke="{s["color"]}" '
                f'stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
            )
        for i, x, y in pts:
            label = labels[i] if i < len(labels) else f"{vals[i]:.0f}"
            parts.append(
                f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" '
                f'stroke="{s["color"]}" stroke-width="2.2">'
                f'<title>{esc(x_labels[i])} · {esc(s["name"])}：{esc(label)}</title></circle>'
                f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-size="10.5" '
                f'font-weight="700" fill="{s["color"]}">{esc(label)}</text></g>'
            )
        # 反转点标记：相邻非 None 值差 > 1
        non_none = [i for i, v in enumerate(vals) if v is not None]
        for a, b in zip(non_none, non_none[1:]):
            if vals[b] - vals[a] > 1 or vals[a] - vals[b] > 1:
                x, y = xs[b], _y(vals[b])
                parts.append(
                    f'<text x="{x + 7:.1f}" y="{y - 12:.1f}" font-size="13" '
                    f'fill="#dc2626" font-weight="800">⚠</text>'
                )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" '
        f'aria-label="信号强度曲线（固定量纲 -2..2）">{"".join(parts)}</svg>'
    )


# ---------------- SVG 条形图 ----------------

def svg_bars(items: list, width: int = 940, height: int = 190) -> str:
    """垂直条形图。items: [(label, value, color)]，value 顶部标注数字。"""
    if not items:
        return ""
    pad_l, pad_r, pad_t, pad_b = 10, 10, 24, 32
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    mv = max(v for _, v, _ in items) or 1
    bw = pw / len(items)
    parts = []
    for idx, (lab, v, color) in enumerate(items):
        bh = ph * (v / mv)
        x = pad_l + bw * idx + bw * 0.18
        w = bw * 0.64
        y = pad_t + ph - bh
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{max(bh, 1.5):.1f}" '
            f'rx="5" fill="{color}"><title>{esc(lab)}：{v} 条</title></rect>'
        )
        parts.append(
            f'<text x="{x + w / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle" '
            f'font-size="11.5" font-weight="700" fill="#334155">{v}</text>'
        )
        parts.append(
            f'<text x="{x + w / 2:.1f}" y="{height - 11}" text-anchor="middle" '
            f'font-size="11" fill="#64748b">{esc(lab)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" '
        f'aria-label="条形图">{"".join(parts)}</svg>'
    )


# ---------------- SVG 水平堆叠条 ----------------

def svg_stacked_bars(rows: list, width: int = 940, height: int | None = None) -> str:
    """水平堆叠条。rows: [{label, total, parts: [(value, color, name)]}]。

    每行一根轨道，按各环节条数堆叠（宽度按全表最大 total 归一），
    右侧标注该期总数；悬停可看每段明细。
    """
    if not rows:
        return ""
    pad_l, pad_t, pad_r = 4, 26, 52
    row_h, gap = 20, 30
    n = len(rows)
    if height is None:
        height = pad_t + n * (row_h + gap) + 14
    plot_w = width - pad_l - pad_r
    max_total = max((r["total"] for r in rows), default=1) or 1
    parts = []
    for i, r in enumerate(rows):
        y = pad_t + i * (row_h + gap) + row_h  # 条形下沿
        parts.append(
            f'<text x="{pad_l}" y="{y - row_h - 6:.1f}" font-size="12.5" font-weight="700" '
            f'fill="#1e293b">{esc(r["label"])}</text>'
        )
        parts.append(
            f'<rect x="{pad_l}" y="{y - row_h:.1f}" width="{plot_w}" height="{row_h}" '
            f'rx="6" fill="#f1f5f9"/>'
        )
        cx = pad_l
        for v, color, name in r["parts"]:
            w = plot_w * (v / max_total)
            if w > 0:
                parts.append(
                    f'<rect x="{cx:.1f}" y="{y - row_h:.1f}" width="{max(w, 1.0):.1f}" '
                    f'height="{row_h}" rx="3" fill="{color}">'
                    f'<title>{esc(r["label"])} · {esc(name)}：{v} 条</title></rect>'
                )
                cx += w
        parts.append(
            f'<text x="{pad_l + plot_w + 8}" y="{y - row_h / 2 + 4:.1f}" font-size="11.5" '
            f'fill="#64748b">{r["total"]}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="viz-svg" role="img" '
        f'aria-label="环节堆叠对比图">{"".join(parts)}</svg>'
    )


# ---------------- 图例 ----------------

def legend_html(series: list[dict]) -> str:
    """折线 / 条形图例。series: [{name, color}]。"""
    chips = "".join(
        f'<span class="lg-chip"><i style="background:{s["color"]}"></i>{esc(s["name"])}</span>'
        for s in series
    )
    return f'<div class="chart-legend">{chips}</div>' if chips else ""
