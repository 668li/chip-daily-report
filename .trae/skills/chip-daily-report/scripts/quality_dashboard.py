#!/usr/bin/env python3
"""
quality_dashboard.py —— 历史日报质量看板（F9 静态产物）

扫描 ROOT 下所有 `芯片行业日报_*.md`，逐份解析并聚合质量指标，生成：
  - delivery/quality_dashboard.md   （人读看板）
  - delivery/quality_dashboard.json （机读数据，便于后续接入看板/告警）

设计目标（对齐 X1–X16 裁决）：
  1. 来源分级占比：按 rules/rule_registry.yaml 的域名集合对每条新闻的真实 URL 做
     父域匹配，算出 A/B/C/未知 的分布 —— 不与报告「自述」来源占比混为一谈。
  2. 数据完整性对账：若报告内含独立「来源分级统计」小节，将其自述占比与脚本计算值
     做偏差核对，偏差过大即标记为数据质量风险（如 v4.0 某期自述 72.7% 但小节写 33.3%）。
  3. 结构合规：环节覆盖、自检表、X14（独立来源统计小节）、X15（简写标题）、
     X16（标题缺日期 / 元信息非引用块）、X11（今日要点含股价）等 WARN 信号。

用法：
  python quality_dashboard.py                  # 生成到 delivery/
  python quality_dashboard.py --out DIR        # 指定输出目录
  python quality_dashboard.py --json-only      # 只写 json

依赖：pyyaml（仅用于读取注册表；解析报告本身只用标准库）。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "rules" / "rule_registry.yaml"
DELIVERY = ROOT / "delivery"

# 5 个标准产业链环节（与注册表 segments 一致）
CANON_SEGMENTS = {
    "设计": "设计",
    "制造": "制造",
    "封测": "封测",
    "EDA": "EDA",
    "材料设备": "材料/设备",
}

# 标题中的环节关键词（用于从 ## 标题识别覆盖）
SEG_HEADING_KEYS = {
    "设计": ["设计"],
    "制造": ["制造"],
    "封测": ["封测"],
    "EDA": ["EDA"],
    "材料设备": ["材料", "设备"],
}

REPORT_GLOB = "芯片行业日报_*.md"


# ---------------------------------------------------------------------------
# 注册表加载 & 域名分类
# ---------------------------------------------------------------------------
def load_registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    a = {d["domain"].lower() for d in reg["domains"]["a_level"]}
    b = {d["domain"].lower() for d in reg["domains"]["b_level"]}
    c = {d["domain"].lower() for d in reg["domains"]["c_level"]}
    segs = list(reg.get("segments", []))
    return a, b, c, segs


def _match(domain, level_set):
    d = domain.lower().lstrip("www.")
    if d in level_set:
        return True
    for pat in level_set:
        if d == pat or d.endswith("." + pat):
            return True
    return False


def classify(domain, a_set, b_set, c_set):
    if _match(domain, a_set):
        return "A"
    if _match(domain, b_set):
        return "B"
    if _match(domain, c_set):
        return "C"
    return "U"


# ---------------------------------------------------------------------------
# 单份报告解析
# ---------------------------------------------------------------------------
RE_TITLE = re.compile(r"^#\s+芯片行业日报([^\n]*)$")
RE_DATE_IN_TITLE = re.compile(r"(20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|20\d{6}|20\d{2}-\d{2}-\d{2})")
RE_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
RE_NEWS_LINE = re.compile(r"^\s*-\s+\*\*.+\*\*")


def parse_report(path, a_set, b_set, c_set):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # --- 标题 & X16 ---
    title = ""
    title_has_date = False
    for ln in lines:
        m = RE_TITLE.match(ln)
        if m:
            title = m.group(0).strip()
            title_has_date = bool(RE_DATE_IN_TITLE.search(m.group(1)))
            break

    # --- 元信息（引用块）& 自述新闻数 ---
    meta_blockquote = False
    declared_news = None
    for ln in lines[:12]:
        if ln.lstrip().startswith(">"):
            meta_blockquote = True
        mm = re.search(r"新闻总数[::：]\s*(\d+)", ln)
        if mm:
            declared_news = int(mm.group(1))

    # --- 标题（章节）列表 ---
    headings = []
    for ln in lines:
        m = RE_HEADING.match(ln)
        if m and m.group(1) == "##":
            headings.append(m.group(2).strip())

    # 环节覆盖
    seg_cov = {k: False for k in CANON_SEGMENTS}
    for h in headings:
        for seg, keys in SEG_HEADING_KEYS.items():
            if any(k in h for k in keys):
                seg_cov[seg] = True

    # X15：简写标题（## EDA / ## 材料，无 / 工具、/ 设备）
    x15 = any(re.match(r"^EDA\s*$", h) or re.match(r"^材料\s*$", h) for h in headings)
    # X14：独立来源分级统计小节
    x14 = any("来源分级统计" in h for h in headings)
    # 产业链关联
    chain_present = any("产业链关联" in h for h in headings)

    # --- 新闻条数与来源 URL ---
    news_count = 0
    urls = []
    in_seg = False
    for ln in lines:
        hm = RE_HEADING.match(ln)
        if hm and hm.group(1) == "##":
            # 进入/离开环节章节
            in_seg = any(k in hm.group(2) for keys in SEG_HEADING_KEYS.values() for k in keys) \
                or "产业链关联" in hm.group(2)
            continue
        if not in_seg:
            continue
        if RE_NEWS_LINE.match(ln) and ("来源" in ln):
            news_count += 1
            for um in re.finditer(r"来源[:：]\s*[^\]]*\]\((https?://[^)\s]+)\)", ln):
                urls.append(um.group(1))

    # 来源分级
    counts = {"A": 0, "B": 0, "C": 0, "U": 0}
    for u in urls:
        host = urlparse(u).netloc.lower().lstrip("www.")
        if not host:
            continue
        counts[classify(host, a_set, b_set, c_set)] += 1
    total_src = sum(counts.values())
    a_ratio = (counts["A"] / total_src) if total_src else None

    # --- 自检表 ---
    selfcheck_present = any(h == "自检结果" for h in headings)
    sc_total = sc_pass = sc_fail = sc_warn = 0
    if selfcheck_present:
        # 取「自检结果」之后到下一个 ## 之间的表格行
        idx = next(i for i, ln in enumerate(lines) if RE_HEADING.match(ln)
                   and RE_HEADING.match(ln).group(2).strip() == "自检结果")
        for ln in lines[idx + 1:]:
            if RE_HEADING.match(ln):
                break
            rm = re.match(r"\|\s*(\d+)\s*\|\s*[^|]*\|\s*(PASS|FAIL|WARN)\s*\|", ln)
            if rm:
                sc_total += 1
                r = rm.group(2)
                if r == "PASS":
                    sc_pass += 1
                elif r == "FAIL":
                    sc_fail += 1
                else:
                    sc_warn += 1

    # --- 自述来源占比（来源分级统计小节） ---
    declared_a_ratio = None
    declared_src = {}
    if x14:
        # 找到该小节，解析 A/B/C 行
        for i, ln in enumerate(lines):
            hm = RE_HEADING.match(ln)
            if hm and "来源分级统计" in hm.group(2):
                for j in range(i + 1, min(i + 12, len(lines))):
                    if RE_HEADING.match(lines[j]):
                        break
                    rm = re.match(r"\|\s*(A级|B级|C级)\s*\|\s*(\d+)\s*条?", lines[j])
                    if rm:
                        declared_src[rm.group(1)] = int(rm.group(2))
                break
        if declared_src:
            tot = sum(declared_src.values())
            if tot:
                declared_a_ratio = declared_src.get("A级", 0) / tot

    # --- X11：今日要点含股价信号 ---
    x11 = False
    # 取 今日要点 小节内容
    try:
        ki = next(i for i, ln in enumerate(lines) if RE_HEADING.match(ln)
                  and "今日要点" in RE_HEADING.match(ln).group(2))
        buf = []
        for ln in lines[ki + 1:]:
            if RE_HEADING.match(ln):
                break
            buf.append(ln)
        kp = "\n".join(buf)
        if re.search(r"股价|市值", kp) and re.search(r"\d", kp):
            x11 = True
    except StopIteration:
        pass

    # --- X12 软指标（按计算新闻数） ---
    def x12_grade(n):
        if n == 0:
            return "PASS"  # 节假日
        if n < 10:
            return "FAIL"
        if n > 25:
            return "FAIL"
        if 15 <= n <= 20:
            return "PASS"
        return "WARN"  # 10-14 / 21-25

    x12 = x12_grade(news_count)

    # 日期（文件名）
    mdate = re.search(r"(\d{8})", path.name)
    date_str = mdate.group(1) if mdate else ""

    # 数据完整性偏差：自述 A 占比 vs 计算 A 占比
    ratio_gap = None
    if declared_a_ratio is not None and a_ratio is not None:
        ratio_gap = round(abs(declared_a_ratio - a_ratio), 3)

    seg_cov_count = sum(seg_cov.values())

    return {
        "file": path.name,
        "date": date_str,
        "title": title,
        "title_has_date": title_has_date,
        "meta_blockquote": meta_blockquote,
        "declared_news": declared_news,
        "computed_news": news_count,
        "sources_total": total_src,
        "a_count": counts["A"],
        "b_count": counts["B"],
        "c_count": counts["C"],
        "u_count": counts["U"],
        "a_ratio": round(a_ratio, 3) if a_ratio is not None else None,
        "segment_coverage": seg_cov,
        "segment_coverage_count": seg_cov_count,
        "selfcheck_present": selfcheck_present,
        "selfcheck_total": sc_total,
        "selfcheck_pass": sc_pass,
        "selfcheck_fail": sc_fail,
        "selfcheck_warn": sc_warn,
        "declared_a_ratio": round(declared_a_ratio, 3) if declared_a_ratio is not None else None,
        "ratio_gap": ratio_gap,
        "x11": x11,
        "x14": x14,
        "x15": x15,
        "x16_title": title_has_date,  # X16 标题日期部分
        "chain_present": chain_present,
        "x12_grade": x12,
    }


# ---------------------------------------------------------------------------
# 聚合 & 输出
# ---------------------------------------------------------------------------
def build_aggregate(reports):
    n = len(reports)
    if n == 0:
        return {}
    a_ratios = [r["a_ratio"] for r in reports if r["a_ratio"] is not None]
    declared_a = [r["declared_a_ratio"] for r in reports if r["declared_a_ratio"] is not None]
    gaps = [r["ratio_gap"] for r in reports if r["ratio_gap"] is not None]
    news = [r["computed_news"] for r in reports]
    sc_pass_rates = []
    for r in reports:
        if r["selfcheck_total"]:
            sc_pass_rates.append(r["selfcheck_pass"] / r["selfcheck_total"])

    # 环节覆盖矩阵
    seg_matrix = {k: sum(1 for r in reports if r["segment_coverage"][k]) for k in CANON_SEGMENTS}

    # X 信号命中
    x_hits = {
        "X11_今日要点含股价": sum(1 for r in reports if r["x11"]),
        "X14_独立来源统计小节": sum(1 for r in reports if r["x14"]),
        "X15_简写标题": sum(1 for r in reports if r["x15"]),
        "X16_标题缺日期": sum(1 for r in reports if not r["x16_title"]),
    }
    x12_dist = {}
    for r in reports:
        x12_dist[r["x12_grade"]] = x12_dist.get(r["x12_grade"], 0) + 1

    dates = [r["date"] for r in reports if r["date"]]

    return {
        "report_count": n,
        "date_range": [min(dates), max(dates)] if dates else [],
        "avg_computed_a_ratio": round(sum(a_ratios) / len(a_ratios), 3) if a_ratios else None,
        "declared_a_ratio_count": len(declared_a),
        "avg_declared_a_ratio": round(sum(declared_a) / len(declared_a), 3) if declared_a else None,
        "avg_ratio_gap": round(sum(gaps) / len(gaps), 3) if gaps else None,
        "max_ratio_gap": max(gaps) if gaps else None,
        "avg_news_count": round(sum(news) / len(news), 1) if news else None,
        "news_min": min(news) if news else None,
        "news_max": max(news) if news else None,
        "segment_coverage_matrix": seg_matrix,
        "segment_full_coverage_count": sum(1 for r in reports if r["segment_coverage_count"] == 5),
        "x_signals": x_hits,
        "x12_distribution": x12_dist,
        "avg_selfcheck_pass_rate": round(sum(sc_pass_rates) / len(sc_pass_rates), 3) if sc_pass_rates else None,
        "selfcheck_missing_count": sum(1 for r in reports if not r["selfcheck_present"]),
    }


def render_markdown(reports, agg):
    L = []
    L.append("# 芯片行业日报 · 质量看板（F9 静态产物）\n")
    L.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}  ")
    L.append(f"> 扫描范围：`{REPORT_GLOB}`（共 {agg['report_count']} 期）  ")
    L.append(f"> 数据源：真实 URL 按 `rules/rule_registry.yaml` 父域匹配，非报告自述\n")

    # 总览
    L.append("## 一、总览指标\n")
    L.append("| 指标 | 值 |")
    L.append("|------|----|")
    L.append(f"| 报告期数 | {agg['report_count']} |")
    L.append(f"| 日期范围 | {agg['date_range'][0]} ~ {agg['date_range'][1]} |")
    L.append(f"| 平均 A 级来源占比（计算值） | {pct(agg['avg_computed_a_ratio'])} |")
    if agg['avg_declared_a_ratio'] is not None:
        L.append(f"| 平均 A 级来源占比（报告自述，{agg['declared_a_ratio_count']} 期含该小节） | {pct(agg['avg_declared_a_ratio'])} |")
    if agg['avg_ratio_gap'] is not None:
        L.append(f"| 平均「自述 vs 计算」A 占比偏差 | {pct(agg['avg_ratio_gap'])}（最大 {pct(agg['max_ratio_gap'])}）|")
    L.append(f"| 平均新闻条数 | {agg['avg_news_count']}（区间 {agg['news_min']}~{agg['news_max']}）|")
    L.append(f"| 5 环节全覆盖期数 | {agg['segment_full_coverage_count']}/{agg['report_count']} |")
    L.append(f"| 平均自检 PASS 率 | {pct(agg['avg_selfcheck_pass_rate'])} |")
    L.append(f"| 自检表缺失期数 | {agg['selfcheck_missing_count']} |")
    L.append("")

    # X 信号
    L.append("## 二、X 系列合规信号（WARN 级）\n")
    L.append("| 信号 | 命中期数 | 说明 |")
    L.append("|------|---------|------|")
    L.append(f"| X11 今日要点含股价 | {agg['x_signals']['X11_今日要点含股价']} | 股价不得作今日要点 |")
    L.append(f"| X14 独立「来源分级统计」小节 | {agg['x_signals']['X14_独立来源统计小节']} | 应由校验器统一输出，不单独成节 |")
    L.append(f"| X15 简写章节标题（## EDA / ## 材料） | {agg['x_signals']['X15_简写标题']} | 应使用全称 ## EDA / 工具 等 |")
    L.append(f"| X16 标题缺日期 | {agg['x_signals']['X16_标题缺日期']} | 标题应含生成日期 |")
    L.append("")

    # X12 条数分布
    L.append("## 三、X12 新闻条数软指标分布\n")
    L.append("| 等级 | 期数 |")
    L.append("|------|------|")
    for g in ("PASS", "WARN", "FAIL"):
        if g in agg["x12_distribution"]:
            L.append(f"| {g} | {agg['x12_distribution'][g]} |")
    L.append("")

    # 环节覆盖矩阵
    L.append("## 四、环节覆盖矩阵\n")
    L.append("| 报告 | " + " | ".join(CANON_SEGMENTS.keys()) + " | 覆盖数 |")
    L.append("|------" + "|------" * (len(CANON_SEGMENTS) + 1) + "|")
    for r in reports:
        cells = ["✓" if r["segment_coverage"][k] else "—" for k in CANON_SEGMENTS]
        L.append(f"| {r['date']} | " + " | ".join(cells) + f" | {r['segment_coverage_count']} |")
    L.append("")

    # 逐期明细
    L.append("## 五、逐期明细\n")
    L.append("| 日期 | 新闻数 | A级 | B级 | C级 | 未知 | A占比 | 自检PASS | X11 | X14 | X15 | X16日期 |")
    L.append("|------|-------|-----|-----|-----|------|-------|----------|-----|-----|-----|--------|")
    for r in reports:
        L.append(
            f"| {r['date']} | {r['computed_news']} | {r['a_count']} | {r['b_count']} | "
            f"{r['c_count']} | {r['u_count']} | {pct(r['a_ratio'])} | "
            f"{r['selfcheck_pass']}/{r['selfcheck_total']} | "
            f"{flag(r['x11'])} | {flag(r['x14'])} | {flag(r['x15'])} | {flag(r['x16_title'])} |"
        )
    L.append("")

    # 数据完整性对账
    L.append("## 六、数据完整性对账（计算值 vs 报告自述）\n")
    recon = [r for r in reports if r["declared_a_ratio"] is not None]
    if recon:
        L.append("| 日期 | 计算A占比 | 自述A占比 | 偏差 | 风险 |")
        L.append("|------|---------|---------|------|------|")
        for r in recon:
            risk = "⚠ 偏差过大" if (r["ratio_gap"] or 0) >= 0.2 else "—"
            L.append(f"| {r['date']} | {pct(r['a_ratio'])} | {pct(r['declared_a_ratio'])} | "
                     f"{pct(r['ratio_gap'])} | {risk} |")
    else:
        L.append("_本报告集中无「来源分级统计」小节，暂无可对账项。_")
    L.append("")

    L.append("---")
    L.append(f"*本看板由 `scripts/quality_dashboard.py` 生成，来源分级以注册表为权威，"
             f"与 `check_rules_consistency.py`、`validate_report.py` 共用同一套域名集合。*")
    return "\n".join(L)


def pct(v):
    return f"{round(v * 100, 1)}%" if isinstance(v, (int, float)) else "—"


def flag(b):
    return "✓" if b else "—"


def _svg_line_chart(title, points, y_max, y_fmt, color):
    """points: list[(label, value)]，value ∈ [0, y_max]。返回内联 SVG（无外部依赖）。"""
    W, H = 680, 300
    pad_l, pad_r, pad_t, pad_b = 52, 20, 34, 48
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    n = len(points)
    if n == 0:
        return f'<svg viewBox="0 0 {W} {H}"><text x="{W//2}" y="{H//2}" fill="#6b7280">无数据</text></svg>'

    def x(i):
        return pad_l + (plot_w * (i / (n - 1))) if n > 1 else pad_l + plot_w / 2

    def y(v):
        return pad_t + plot_h * (1.0 - max(0.0, min(1.0, v / y_max)))

    p = [f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" '
         f'font-family="-apple-system,Segoe UI,Roboto,sans-serif" role="img" aria-label="{title}">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" fill="#1f2937">{title}</text>')
    # 横向网格 + Y 轴标签
    for g in range(5):
        gv = y_max * g / 4
        gy = y(gv)
        p.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{W - pad_r}" y2="{gy:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
        p.append(f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" font-size="10" fill="#6b7280" text-anchor="end">{y_fmt(gv)}</text>')
    # X 轴标签
    for i, (lab, _) in enumerate(points):
        p.append(f'<text x="{x(i):.1f}" y="{H - 16}" font-size="10" fill="#6b7280" text-anchor="middle">{lab}</text>')
    # 面积 + 折线
    area = (f"M{x(0):.1f},{y(0):.1f} "
            + " ".join(f"L{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
            + f" L{x(n - 1):.1f},{y(0):.1f} Z")
    p.append(f'<path d="{area}" fill="{color}" fill-opacity="0.10"/>')
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    p.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"/>')
    for i, (_, v) in enumerate(points):
        p.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3.5" fill="{color}"/>')
        if n <= 10:
            p.append(f'<text x="{x(i):.1f}" y="{y(v) - 8:.1f}" font-size="10" fill="{color}" text-anchor="middle">{y_fmt(v)}</text>')
    p.append('</svg>')
    return "\n".join(p)


def render_html(reports, agg):
    cards = [
        ("报告期数", str(agg["report_count"])),
        ("平均 A 级占比", pct(agg["avg_computed_a_ratio"])),
        ("5 环节全覆盖", f"{agg['segment_full_coverage_count']}/{agg['report_count']}"),
        ("平均新闻条数", str(agg["avg_news_count"])),
        ("平均自检 PASS 率", pct(agg["avg_selfcheck_pass_rate"])),
        ("X14/X15/X16 信号", f"{agg['x_signals']['X14_独立来源统计小节']}/"
                             f"{agg['x_signals']['X15_简写标题']}/{agg['x_signals']['X16_标题缺日期']}"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in cards
    )

    rp = [(r["date"][4:6] + "-" + r["date"][6:8], r["a_ratio"] or 0.0) for r in reports]
    nmax = max((r["computed_news"] for r in reports), default=25)
    np_ = [(r["date"][4:6] + "-" + r["date"][6:8], r["computed_news"]) for r in reports]
    a_chart = _svg_line_chart("A 级来源占比（计算值）", rp, 1.0, lambda v: f"{v * 100:.0f}%", "#2563eb")
    n_chart = _svg_line_chart("新闻条数", np_, max(25, nmax), lambda v: f"{v:.0f}", "#059669")

    # 逐期表格
    rows = []
    for r in reports:
        rows.append(
            f"<tr><td>{r['date']}</td><td>{r['computed_news']}</td>"
            f"<td>{r['a_count']}</td><td>{r['b_count']}</td><td>{r['c_count']}</td>"
            f"<td>{r['u_count']}</td><td>{pct(r['a_ratio'])}</td>"
            f"<td>{r['selfcheck_pass']}/{r['selfcheck_total']}</td>"
            f"<td>{flag(r['x11'])}</td><td>{flag(r['x14'])}</td>"
            f"<td>{flag(r['x15'])}</td><td>{flag(r['x16_title'])}</td></tr>"
        )
    table_html = (
        "<table><thead><tr><th>日期</th><th>新闻数</th><th>A</th><th>B</th><th>C</th>"
        "<th>未知</th><th>A占比</th><th>自检PASS</th><th>X11</th><th>X14</th><th>X15</th><th>X16日期</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>芯片行业日报 · 质量看板</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f7fa; color: #1f2937; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 28px 20px 48px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: #6b7280; font-size: 13px; margin-bottom: 22px; }}
  .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 26px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; }}
  .card .k {{ font-size: 12px; color: #6b7280; }}
  .card .v {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .panel {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; margin-bottom: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #eef0f3; padding: 7px 6px; text-align: center; }}
  th {{ color: #6b7280; font-weight: 600; }}
  td:first-child, th:first-child {{ text-align: left; }}
  tr:hover td {{ background: #f9fafb; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>芯片行业日报 · 质量看板（F9）</h1>
  <div class="sub">生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 来源分级以 rules/rule_registry.yaml 为权威（真实 URL 父域匹配，非报告自述）</div>
  <div class="cards">{card_html}</div>
  <div class="panel">{a_chart}</div>
  <div class="panel">{n_chart}</div>
  <div class="panel">{table_html}</div>
  <div class="sub">本页由 scripts/quality_dashboard.py 生成，与 quality_dashboard.md / .json 同源。X11=今日要点含股价，X14=独立来源统计小节，X15=简写标题，X16=标题缺日期。</div>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DELIVERY))
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    a_set, b_set, c_set, _ = load_registry()
    files = sorted(ROOT.glob(REPORT_GLOB))
    if not files:
        print(f"[dashboard] 未找到 {REPORT_GLOB}", file=sys.stderr)
        sys.exit(1)

    reports = [parse_report(p, a_set, b_set, c_set) for p in files]
    reports.sort(key=lambda r: r["date"])
    agg = build_aggregate(reports)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "quality_dashboard.json"
    json_path.write_text(
        json.dumps({"aggregate": agg, "reports": reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[dashboard] 已写入 {json_path}")

    if not args.json_only:
        md_path = out_dir / "quality_dashboard.md"
        md_path.write_text(render_markdown(reports, agg), encoding="utf-8")
        print(f"[dashboard] 已写入 {md_path}")
        if not args.no_html:
            html_path = out_dir / "quality_dashboard.html"
            html_path.write_text(render_html(reports, agg), encoding="utf-8")
            print(f"[dashboard] 已写入 {html_path}")

    # 控制台摘要
    print(f"[dashboard] 共 {agg['report_count']} 期 | "
          f"平均A占比(计算)={pct(agg['avg_computed_a_ratio'])} | "
          f"5环节全覆盖={agg['segment_full_coverage_count']}/{agg['report_count']} | "
          f"X信号={agg['x_signals']}")


if __name__ == "__main__":
    main()
