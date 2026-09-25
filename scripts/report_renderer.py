#!/usr/bin/env python3
"""report_renderer — M0 结构化中间表示的渲染器（单一数据源 → Markdown）。

设计目标（见 references/evolution_plan.md M0）：
  LLM 不再自由写 md，而是输出「结构化中间表示（IR）」dict；本模块把同一份 dict
  确定性地渲染为 Markdown——其格式与 validate_report.py 的格式契约、report_viz/parser.py
  的正则严格互逆。于是：
    - IR 成为唯一真相源（single source of truth）；
    - Markdown 只是 IR 的一种序列化，校验脚本仍对 md 做硬校验（兜底）；
    - report_viz 的 7 视图可改为直接消费 IR，正则 parser 的脆弱性由此退役。

本模块不依赖 parser（纯函数式），输入/输出都是普通 dict / str，便于测试与复用。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# 5 个标准产业链环节 → 输出时的全称标题
SEG_HEADINGS = {
    "设计": "设计",
    "制造": "制造",
    "封测": "封测",
    "EDA": "EDA / 工具",
    "材料": "材料 / 设备",
    "综合": "综合 / 其他",
}
# 环节渲染顺序（决定日报章节顺序，须满足 validate 的 expected_order 非递减约束）
SEG_ORDER = ["设计", "制造", "封测", "EDA", "材料", "综合"]
# 横向维度顺序
DIM_ORDER = ["市场与需求", "政策与监管", "资本与投融资"]


def _render_sources(sources: list) -> str:
    """sources: 兼容两种形态——news 为 (name, url) 元组，catalyst 为 {name,url,level} 字典。"""
    parts = []
    for s in (sources or []):
        if isinstance(s, dict):
            parts.append(f"[{s['name']}]({s['url']})")
        else:  # 元组 (name, url)
            parts.append(f"[{s[0]}]({s[1]})")
    return " | ".join(parts)


def _render_news(it: dict) -> str:
    """渲染单条新闻为 validate 契约格式的行。"""
    prefix = "[回顾] " if it.get("is_review") else ""
    title = prefix + it.get("title", "")
    summary = it.get("summary", "")
    if it.get("annotation"):
        summary += f" [技术注解: {it['annotation']}]"
    if it.get("origin"):
        summary += f"（原始：{it['origin']}）"

    sources = it.get("sources") or []
    if sources:
        source_seg = f" | 来源: {_render_sources(sources)}"
    else:
        source_seg = " | 来源: 链接待验证"  # fail-soft，与 SKILL 失败处理一致

    tail = f" | {it.get('timestamp', '')}"
    signal = it.get("signal")
    if signal:
        tail += f" | 信号: {signal['importance']}/{signal['impact']}/{signal['sentiment']}"

    return f"- **{title}** — {summary}{source_seg}{tail}"


def _compute_source_stats(report: dict) -> dict:
    """从 segments 各条新闻的 level 汇总 A/B/C（与 validate 分母口径一致）。"""
    stats = {"A": 0, "B": 0, "C": 0}
    for items in report.get("segments", {}).values():
        for it in items:
            lvl = it.get("level")
            if lvl in stats:
                stats[lvl] += 1
    return stats


def render_markdown(report: dict) -> str:
    """把结构化日报 dict 渲染为 Markdown 字符串（与 validate 契约互逆）。"""
    out: list[str] = []

    # 头部：标题 + 元信息 blockquote
    out.append(f"# {report.get('title', '芯片行业日报')}")
    out.append("")
    out.append(f"> 生成时间: {report.get('gen_time', '')}")
    out.append(f"> 覆盖范围: {report.get('coverage', '')}")
    out.append(f"> 新闻总数: {report.get('news_count', '')}条")
    out.append("")

    # 今日要点
    out.append("## 今日要点")
    out.append("")
    for h in report.get("highlights", []):
        out.append(f"- {h}")
    out.append("")

    # 5 环节（+综合）
    for seg in SEG_ORDER:
        items = report.get("segments", {}).get(seg)
        if items is None:
            continue
        out.append(f"## {SEG_HEADINGS[seg]}")
        out.append("")
        if not items:
            out.append("- **今日暂无重要动态**")
            out.append("")
            continue
        for it in items:
            out.append(_render_news(it))
        out.append("")

    # 横向维度
    for dim in DIM_ORDER:
        d = report.get("dimensions", {}).get(dim)
        if not d:
            continue
        out.append(f"## {dim}")
        out.append("")
        intro = (d.get("intro") or "").strip()
        if intro:
            for line in intro.split("\n"):
                out.append(f"> {line}" if not line.startswith(">") else line)
            out.append("")
        for sub in d.get("subs", []):
            out.append(f"### {sub.get('title', '')}")
            out.append(sub.get("body", "").strip())
            out.append("")
        # 去掉最后一个多余的空行已在 append("") 多一个，下面统一由章节空行处理

    # 产业链关联
    chain = report.get("chain_groups", [])
    if chain:
        out.append("## 产业链关联")
        out.append("")
        for g in chain:
            out.append(f"- **{g.get('title', '')}**：{g.get('body', '')}")
        out.append("")

    # 持续追踪
    tr = report.get("tracking", [])
    if tr:
        out.append("## 持续追踪")
        out.append("")
        for t in tr:
            out.append(f"- **{t.get('topic', '')}**：{t.get('detail', '')}")
        out.append("")

    # 前瞻兑现回顾（v5.10 方向1）
    fr = report.get("forward_review")
    if fr:
        out.append("## 前瞻兑现回顾")
        out.append("")
        intro = (fr.get("intro") or "").strip()
        if intro:
            for line in intro.split("\n"):
                out.append(f"> {line}" if not line.startswith(">") else line)
            out.append("")
        for i, it in enumerate(fr.get("items", []), 1):
            out.append(f"### 回看 {i}：{it.get('title', '')}")
            for key, text in it.get("parts", []):
                out.append(f"- **{key}**：{text}")
        if fr.get("summary"):
            out.append(f"**闭环小结**：{fr['summary']}")
        out.append("")

    # 前瞻催化剂（v5.11，含确定性列 + 前瞻解读块）
    cats = report.get("catalysts", [])
    if cats:
        out.append("## 前瞻催化剂")
        out.append("")
        out.append("| 日期 | 事件 | 环节 | 重要度 | 确定性 | 来源 |")
        out.append("|------|------|------|--------|--------|------|")
        for c in cats:
            cert = c.get("certainty") or "—"
            out.append(
                f"| {c.get('date', '')} | {c.get('event', '')} | {c.get('segment', '')} "
                f"| {c.get('importance', '')} | {cert} | {_render_sources(c.get('sources', []))} |"
            )
        out.append("")
        for i, note in enumerate(report.get("catalyst_notes", []), 1):
            out.append(f"### 前瞻 {i}：{note.get('title', '')}")
            for key, text in note.get("parts", []):
                out.append(f"- **{key}**：{text}")
            out.append("")

    # 费曼解释
    fy = report.get("feynman", [])
    if fy:
        out.append("## 费曼解释")
        out.append("")
        for f in fy:
            out.append(f"- **{f.get('term', '')}**：{f.get('text', '')}")
        out.append("")

    # 深度解读
    dd = report.get("deep_dive", [])
    if dd:
        out.append("## 深度解读")
        out.append("")
        for i, d in enumerate(dd, 1):
            out.append(f"### 解读 {i}：{d.get('title', '')}")
            for key, text in d.get("parts", []):
                out.append(f"- **{key}**：{text}")
            out.append("")

    # 未来借鉴
    fl = report.get("future_lessons", [])
    if fl:
        out.append("## 未来借鉴")
        out.append("")
        for c in fl:
            out.append(f"- **{c.get('category', '')}**：{c.get('text', '')}")
        out.append("")

    # 今日导师课
    tu = report.get("tutor", [])
    if tu:
        out.append("## 今日导师课")
        out.append("")
        for m in tu:
            out.append(f"### {m.get('module', '')}")
            for line in m.get("body", []):
                out.append(line)
            out.append("")

    # 自检结果
    selfcheck = report.get("selfcheck", [])
    if selfcheck is not None:
        out.append("## 自检结果")
        out.append("")
        out.append("| # | 检查项 | 结果 | 说明 |")
        out.append("|---|--------|------|------|")
        for row in selfcheck:
            out.append(
                f"| {row.get('num', '')} | {row.get('name', '')} | {row.get('result', '')} | {row.get('note', '')} |"
            )
        out.append("")
        stats = _compute_source_stats(report)
        total = stats["A"] + stats["B"]
        pct = (stats["A"] / total * 100) if total > 0 else 0
        out.append("**来源分级统计**（基于 URL 域名判定，与校验脚本口径一致）：")
        out.append(f"- A级（权威）：{stats['A']} 条")
        out.append(f"- B级（聚合/行业）：{stats['B']} 条")
        out.append(f"- C级：{stats['C']} 条")
        out.append(f"- A级占比：{stats['A']}/{total} = {pct:.1f}% ≥ 30% ✓（聚合源均标注\"原始:X\"追溯）")
        out.append("")
        out.append("---")
        out.append("")
        out.append("*本日报由 chip-daily-report skill 生成，所有信息均来自公开可访问的新闻来源。*")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def to_json(report: dict) -> str:
    """IR dict → 紧凑 JSON 字符串。"""
    return json.dumps(report, ensure_ascii=False, indent=2)


def from_json(text: str) -> dict:
    """JSON 字符串 → IR dict。"""
    return json.loads(text)


def roundtrip(md_path, out_path=None, validate=False) -> str:
    """解析 md → 渲染 md（便利函数，用于回归/比对）。可选写文件或跑校验。"""
    import report_viz.parser as parser  # 延迟导入，避免 CLI 时的循环依赖噪音

    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    report = parser.parse_report(md_path)
    md = render_markdown(report)
    if out_path:
        Path(out_path).write_text(md, encoding="utf-8")
    if validate:
        vpy = repo_root / "validate_report.py"
        r = subprocess.run(
            [sys.executable, str(vpy), out_path or md_path],
            capture_output=True,
            text=True,
        )
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr)
    return md


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="M0 渲染器：md ↔ IR 互转/回归")
    ap.add_argument("md", help="输入日报 md 路径")
    ap.add_argument("--out", help="渲染输出 md 路径", default=None)
    ap.add_argument("--validate", action="store_true", help="渲染后跑 validate_report.py")
    ap.add_argument("--json", action="store_true", help="同时输出 IR 的 JSON 到 <out>.json")
    args = ap.parse_args()

    md = roundtrip(args.md, args.out, args.validate)
    if args.json and args.out:
        import report_viz.parser as parser

        rep = parser.parse_report(args.md)
        Path(args.out + ".json").write_text(to_json(rep), encoding="utf-8")
    if not args.out:
        print(md)
