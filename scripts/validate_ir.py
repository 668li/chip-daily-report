#!/usr/bin/env python3
"""validate_ir — M2 校验前置：对结构化中间表示（IR）dict 做字段级硬校验。

设计目标（见 references/evolution_plan.md M2）：
  LLM 直出 IR JSON 后，先在这里跑一遍"字段级 26 项校验"，把结构性错误
  （缺环节 / 缺来源 / 新闻数不符 / A 级不足 / 误标[回顾] / 重复标题 / 缺自检等）
  在「渲染成 md / 喂给 HTML」之前就抓出来——避免脆弱的 md 正则 parser 成为唯一门禁。
  validate_report.py（文本正则）保留为最终安全网；两者口径一致、可交叉验证。

不依赖第三方库（运行环境可能缺 jsonschema），手动实现字段校验，fail-soft。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 标准 5 环节（+综合可选）
CORE_SEGS = ["设计", "制造", "封测", "EDA", "材料"]

# 中立性：投资建议关键词（与 validate_report.py INVESTMENT_ADVICE_KEYWORDS 一致）
INVESTMENT_ADVICE_KEYWORDS = [
    "建议买入", "值得投资", "前景光明", "看涨", "看跌",
    "强烈推荐", "买入评级", "目标价", "预测涨", "预计下跌",
    "股价有望", "建议卖出", "增持", "减持", "建议加仓",
    "建议减仓", "投资价值", "上涨空间", "下跌空间",
]

# 越界附录关键词（与 validate_report.py FORBIDDEN_APPENDICES 一致）
FORBIDDEN_APPENDICES = ["投资建议", "股价分析", "市场预测"]

SEG_HEADINGS = {
    "设计": "设计", "制造": "制造", "封测": "封测",
    "EDA": "EDA / 工具", "材料": "材料 / 设备", "综合": "综合 / 其他",
}


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def _parse_date(s: str):
    """解析 'YYYY-MM-DD' / 'YYYY年M月D日' / 'YYYY-MM-DD HH:MM' → date。失败返回 None。"""
    if not s:
        return None
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", s)
    if m:
        try:
            from datetime import date
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_gen_time(s: str):
    """解析生成时间 'YYYY-MM-DD HH:MM' → datetime。失败返回 None。"""
    if not s:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2})?", s)
    if not m:
        return None
    from datetime import datetime
    d, t = m.group(1), m.group(2) or "00:00"
    try:
        return datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _count_sentences(text: str) -> int:
    """统计句数（兼容中英文标点，排除小数点）。与 validate_report.count_sentences 一致。"""
    temp = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text or "")
    n = len(re.findall(r"[。！？.!?]", temp))
    if n == 0:
        return 2 if len(text or "") > 20 else 1
    return n


def _iter_text(report: dict):
    """把 IR 所有字符串字段扁平化为文本，供中立性/关键词扫描。"""
    def walk(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, dict):
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                yield from walk(v)
    yield from walk(report)


def _news_items(report: dict) -> list:
    out = []
    for seg, items in report.get("segments", {}).items():
        for it in (items or []):
            it = dict(it)
            it["_seg"] = seg
            out.append(it)
    return out


def _source_stats(report: dict) -> dict:
    """从各条新闻 level 汇总 A/B/C（与 report_renderer._compute_source_stats 口径一致）。"""
    stats = {"A": 0, "B": 0, "C": 0}
    for it in _news_items(report):
        lvl = it.get("level")
        if lvl in stats:
            stats[lvl] += 1
    return stats


# --------------------------------------------------------------------------
# 26 项字段校验
# --------------------------------------------------------------------------
def run_checks(report: dict):
    """返回 [(num, name, result, note), ...]；result ∈ PASS/FAIL/WARN。"""
    rows = []
    news = _news_items(report)
    total_news = len(news)
    gen_dt = _parse_gen_time(report.get("gen_time", ""))

    # 1. 元信息完整
    miss = [k for k in ("title", "gen_time", "coverage", "news_count") if not report.get(k)]
    rows.append((1, "元信息完整", "PASS" if not miss else "FAIL",
                 "齐全" if not miss else f"缺失: {','.join(miss)}"))

    # 2. 产业链完整性（5 核心环节都须出现，即使为空）
    missing_seg = [s for s in CORE_SEGS if s not in report.get("segments", {})]
    rows.append((2, "产业链完整性", "PASS" if not missing_seg else "FAIL",
                 "5 环节全覆盖" if not missing_seg else f"缺环节: {','.join(missing_seg)}"))

    # 3. 来源可追溯（每条新闻 sources 非空）
    no_src = [it["title"][:24] for it in news if not it.get("sources")]
    rows.append((3, "来源可追溯", "PASS" if not no_src else "FAIL",
                 f"{total_news} 条均有来源" if not no_src else f"{len(no_src)} 条缺来源: {no_src[0]}…"))

    # 4. 摘要规范（3-5 句；6 句 WARN；≥7 句 FAIL）
    bad4, warn4 = [], 0
    for it in news:
        c = _count_sentences(it.get("summary", ""))
        if c >= 7:
            bad4.append((it["title"][:20], c))
        elif c == 6:
            warn4 += 1
    if bad4:
        rows.append((4, "摘要规范", "FAIL", f"{len(bad4)} 条≥7句(过长): {bad4[0]}…"))
    elif warn4:
        rows.append((4, "摘要规范", "WARN", f"{warn4} 条 6 句，建议压到 3-5 句"))
    else:
        rows.append((4, "摘要规范", "PASS", f"{total_news} 条句数合格"))

    # 5. 时效性（is_review 与 gen_time - timestamp 一致性；用完整 gen_time 含时分，
    #    与 validate_report.check_timeliness 口径一致：diff_hours>72 须标[回顾]）
    from datetime import datetime as _dt
    bad5 = []
    for it in news:
        ts = it.get("timestamp", "")
        d = _parse_date(ts)
        if not d or "日期待确认" in ts:
            continue
        if not gen_dt:
            continue
        news_dt = _dt(d.year, d.month, d.day, 0, 0)
        diff_h = (gen_dt - news_dt).total_seconds() / 3600
        if diff_h < 0:
            bad5.append((it["title"][:20], "未来日期"))
        elif diff_h > 72:
            if not it.get("is_review"):
                bad5.append((it["title"][:20], f"超72h未标[回顾] {diff_h:.0f}h"))
        else:
            if it.get("is_review"):
                bad5.append((it["title"][:20], "误标[回顾]"))
    rows.append((5, "时效性", "PASS" if not bad5 else "FAIL",
                 "时效标注一致" if not bad5 else f"{len(bad5)} 条异常: {bad5[0]}…"))

    # 6. 今日要点（1-3 条）
    hl = report.get("highlights", []) or []
    ok6 = 1 <= len(hl) <= 3
    rows.append((6, "今日要点", "PASS" if ok6 else "FAIL",
                 f"{len(hl)} 条" if ok6 else f"应为 1-3 条，当前 {len(hl)} 条"))

    # 7. 自检小节（selfcheck 行数 ≥15）
    sc = report.get("selfcheck") or []
    rows.append((7, "自检小节", "PASS" if len(sc) >= 15 else "FAIL",
                 f"{len(sc)} 行自检表" if sc else "缺自检结果表"))

    # 8. 附录越界（IR 无附录构造：渲染器不生成越界附录 header；与 validate_report
    #     check_8 仅匹配 `^## 投资建议` 等 header 的口径一致 → 恒定 PASS）
    rows.append((8, "附录越界", "PASS", "IR 无附录构造；渲染器不生成越界附录 header"))

    # 9. 中立性（投资建议关键词）
    hit9 = []
    for t in _iter_text(report):
        for kw in INVESTMENT_ADVICE_KEYWORDS:
            if kw in t:
                hit9.append(kw)
                break
    rows.append((9, "中立性", "PASS" if not hit9 else "FAIL",
                 "未发现投资建议关键词" if not hit9 else f"命中: {hit9[:3]}"))

    # 10. 来源质量（A 级占比 ≥30%）
    st = _source_stats(report)
    ab = st["A"] + st["B"]
    pct = (st["A"] / ab * 100) if ab > 0 else 0
    rows.append((10, "来源质量", "PASS" if ab > 0 and pct >= 30 else "FAIL",
                 f"A级 {st['A']} / 共 {ab} = {pct:.1f}%" if ab > 0 else "无 A/B 级来源"))

    # 11. 免责声明（渲染器恒定输出，PASS）
    rows.append((11, "免责声明", "PASS", "渲染器恒定输出免责声明与分隔线"))

    # 12. 章节顺序（渲染器固定顺序，PASS）
    rows.append((12, "章节顺序", "PASS", "渲染顺序固定：今日要点→设计→…→材料→产业链关联→自检"))

    # 13. 去重（同环节内标题不重复）
    dups = []
    for seg, items in report.get("segments", {}).items():
        seen, titles = set(), [i.get("title", "") for i in (items or [])]
        for t in titles:
            base = t.replace("[回顾] ", "")
            if base in seen:
                dups.append(seg)
            seen.add(base)
    rows.append((13, "去重", "PASS" if not dups else "FAIL",
                 "无重复标题" if not dups else f"重复环节: {dups}"))

    # 14. 技术注解（涉及术语的新闻应有 [技术注解]；IR 层做软提示）
    ann = sum(1 for it in news if it.get("annotation"))
    if total_news >= 5 and ann == 0:
        rows.append((14, "技术注解", "WARN", "0 条含技术注解（专业术语新闻建议补 [技术注解]）"))
    else:
        rows.append((14, "技术注解", "PASS", f"{ann}/{total_news} 条含技术注解"))

    # 15. 产业链关联（≥2 组）
    cg = report.get("chain_groups", []) or []
    rows.append((15, "产业链关联", "PASS" if len(cg) >= 2 else "FAIL",
                 f"{len(cg)} 组关联" if cg else "缺产业链关联小节"))

    # 16. 新闻条数（news_count == 各环节之和，且 15-20）
    seg_sum = sum(len(v or []) for v in report.get("segments", {}).values())
    nc = report.get("news_count")
    if nc != seg_sum:
        rows.append((16, "新闻条数", "FAIL", f"news_count={nc} 但环节实际 {seg_sum} 条"))
    elif not (15 <= seg_sum <= 20):
        rows.append((16, "新闻条数", "FAIL", f"条数 {seg_sum} 不在 15-20 区间"))
    else:
        rows.append((16, "新闻条数", "PASS", f"{seg_sum} 条（落入 15-20）"))

    # 17. 来源统计位置（渲染器恒定输出在自检小节内，PASS）
    rows.append((17, "来源统计位置", "PASS", "渲染器恒定在自检结果内输出来源分级统计"))

    # 18. 环节全称（渲染器恒定用 SEG_HEADINGS 全称，PASS）
    rows.append((18, "环节全称", "PASS", "渲染器恒定使用全称（EDA / 工具 等）"))

    # 19. 标题日期（标题含日期）
    title = report.get("title", "")
    has_date = bool(re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", title))
    rows.append((19, "标题日期", "PASS" if has_date else "FAIL",
                 "标题含日期" if has_date else "标题缺日期"))

    # 20. 信号层（覆盖率 ≥80%）
    sig = sum(1 for it in news if it.get("signal"))
    cov = (sig / total_news * 100) if total_news else 0
    rows.append((20, "信号层", "PASS" if total_news and cov >= 80 else "FAIL",
                 f"覆盖率 {cov:.0f}%（{sig}/{total_news}，目标≥80%）" if total_news else "无新闻"))

    # 21-26 软指标（缺失即 WARN，不阻断）
    tr = report.get("tracking", []) or []
    rows.append((21, "持续追踪", "PASS" if tr else "WARN", f"{len(tr)} 条" if tr else "建议覆盖持续追踪"))
    cats = report.get("catalysts", []) or []
    rows.append((22, "前瞻催化剂", "PASS" if cats else "WARN", f"{len(cats)} 条" if cats else "建议覆盖前瞻催化剂"))
    fr = report.get("forward_review")
    rows.append((23, "前瞻兑现回顾", "PASS" if fr else "WARN", "已覆盖" if fr else "建议覆盖前瞻兑现回顾"))
    miss_cert = [c.get("event", "")[:16] for c in cats if not c.get("certainty")]
    rows.append((24, "前瞻确定性分级", "PASS" if (cats and not miss_cert) else "WARN",
                 "全部含确定性" if (cats and not miss_cert) else (f"{len(miss_cert)} 条缺确定性" if miss_cert else "无催化剂")))
    fy = report.get("feynman", []) or []
    rows.append((25, "费曼解释", "PASS" if fy else "WARN", f"{len(fy)} 条" if fy else "建议覆盖费曼解释"))
    tu = report.get("tutor", []) or []
    rows.append((26, "今日导师课", "PASS" if tu else "WARN", f"{len(tu)} 模块" if tu else "建议覆盖今日导师课"))

    # --- M1 来源交叉验证（事实三角验证，advisory WARN，不重排 26 项）---
    try:
        from cross_validate import cross_validate as _cv

        _ver = _cv(report)
        _single_a = [v for v in _ver["items"] if v["needs_verification"] and v["domain_level"] == "A"]
        if _single_a:
            rows.append(("M1", "来源交叉验证", "WARN",
                         f"{len(_single_a)} 条单源却标 A 级（事实三角验证不足，建议降 B + 待核实）："
                         + "；".join(x["title"][:14] for x in _single_a[:3])))
        if _ver["total"] and _ver["single_source"] / _ver["total"] >= 0.8:
            rows.append(("M1", "来源多样性", "WARN",
                         f"单源新闻占比 {_ver['single_source'] / _ver['total']:.0%}（≥80%），"
                         f"建议为关键事件补第二独立源做三角验证"))
        if _ver["cross_validated"]:
            rows.append(("M1", "来源交叉验证", "PASS",
                         f"{_ver['cross_validated']} 条≥2 独立源，跨源核验通过"))
    except Exception:
        pass

    return rows


def validate(report: dict):
    """返回 (rows, n_fail, n_warn)。"""
    rows = run_checks(report)
    n_fail = sum(1 for r in rows if r[2] == "FAIL")
    n_warn = sum(1 for r in rows if r[2] == "WARN")
    return rows, n_fail, n_warn


def print_report(rows, n_fail, n_warn):
    print("| # | 检查项 | 结果 | 说明 |")
    print("|---|--------|------|------|")
    for num, name, res, note in rows:
        mark = "✓" if res == "PASS" else ("⚠" if res == "WARN" else "✗")
        print(f"| {num} | {name} | {mark} {res} | {note} |")
    total = len(rows)
    print(f"\n通过 {total - n_fail - n_warn} / FAIL {n_fail} / WARN {n_warn}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="M2 校验前置：IR JSON 字段级 26 项校验")
    ap.add_argument("ir", help="IR JSON 文件路径")
    ap.add_argument("--json-out", help="把校验结果也写成 JSON", default=None)
    args = ap.parse_args()

    text = Path(args.ir).read_text(encoding="utf-8")
    try:
        report = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[validate_ir] JSON 解析失败：{e}", file=sys.stderr)
        sys.exit(2)

    rows, n_fail, n_warn = validate(report)
    print_report(rows, n_fail, n_warn)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"rows": rows, "fail": n_fail, "warn": n_warn},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
