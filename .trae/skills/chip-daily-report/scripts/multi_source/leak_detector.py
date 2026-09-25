#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.leak_detector — 漏聚探测器（2026-08-09 新增）。

检测『该聚未聚』的单源事件对：fused_events.json 中 n_sources==1 的事件，
两两组合后按三信号（digit / entity_time / jaccard）判定是否可能是同一事件
被拆开，输出候选锚词建议清单。**只建议、不自动改码**——人工审核后手动
写回 fusion.py 锚词表。

定位：建议工具，宁多报勿漏（假阳性由维护者过滤，假阴性=盲区继续存在）。

三信号（OR 组合，任一命中即候选）：
  digit        主信号：百分比/带单位数字，区间外扩 ±10% 后相交（53-58% vs 55%）
               百分比是强信号（与 fusion 分歧检测『百分比不参与』不同——
               那是防硬冲突误报，这里是找『同一数字的两个说法』）
  entity_time  辅信号：extract_entities(标题) 共享实体 ≥1 + 发布日差 ≤3 天
               （单源对共享实体天然 ≤1：≥2 早被 cluster 合并）
  jaccard      补信号：CJK/ASCII 边界切分 token 后 Jaccard ≥ 0.25（同语言近重复；
               跨语言对恒低，由 digit/entity_time 兜底）

输出：data/leak_report.json（程序消费）+ data/leak_report.md（人读）。
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import fusion  # 复用锚词表/数字工具/extract_entities（只读，不改）
from fusion import _UNIT_NORM, _VAL_RE, extract_entities  # noqa: WPS450
from fusion import COMPANY_ANCHORS, EVENT_ANCHORS, GENERIC_TERMS, SYNONYM_MAP

DATA_DIR = Path(__file__).resolve().parent / "data"

# 阈值
MIN_SHARED_ENTITIES = 1        # entity_time 共享实体下限（< 聚类阈值 2 的临界）
TIME_WINDOW_DAYS = 3           # 时间窗（天）
JACCARD_THRESHOLD = 0.25       # 标题 Jaccard 下限
RANGE_TOLERANCE = 0.10         # 数字区间外扩 ±10%
MAX_PAIRS = 1000               # 单源事件对上限（防 C(n,2) 爆炸）

# 百分比区间正则：53-58% / 55% 均匹配。第二组数字【可选】——
# 若写成"两数字必填+分隔符可选"，55% 会被拆成 (5,5)。
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*%")

# token 化停用词（中英）
_LEAK_STOP = {
    "the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "with", "by",
    "up", "down", "at", "as", "from", "is", "are", "was", "were", "be", "its",
    "this", "that", "for", "with", "about", "over", "into", "after", "before",
    "公司", "公布", "发布", "宣布", "拟", "约", "计划", "年", "月", "日", "第",
    "将", "已", "了", "的", "与", "和", "及", "为", "对", "在", "中",
}

# 候选锚词过滤：三锚表 + 同义词组 key/value 的规范形
_ALL_ANCHORS = (set(COMPANY_ANCHORS) | set(EVENT_ANCHORS) | set(GENERIC_TERMS)
                | set(SYNONYM_MAP.keys()) | set(SYNONYM_MAP.values()))

# 数字区间（±10% 外扩）相交判定


def _to_interval(nums: list[tuple[str, str | None]]) -> list[tuple[float, float]]:
    """把解析出的数字对转成 [lo, hi] 区间（点值 → 退化为 [v, v]），外扩 ±10%。"""
    out = []
    for s1, s2 in nums:
        v1 = float(s1)
        hi = float(s2) if s2 else v1
        lo, hi = min(v1, hi), max(v1, hi)
        pad = (hi - lo) * RANGE_TOLERANCE if hi > lo else hi * RANGE_TOLERANCE
        out.append((lo - pad, hi + pad))
    return out


def _intervals_overlap(a: list[tuple[float, float]],
                       b: list[tuple[float, float]]) -> bool:
    for x in a:
        for y in b:
            if max(x[0], y[0]) <= min(x[1], y[1]):
                return True
    return False


def _parse_percents(text: str) -> list[tuple[str, str | None]]:
    return [(m.group(1), m.group(2)) for m in _PCT_RE.finditer(text or "")]


def _parse_units(text: str) -> list[tuple[str, str | None]]:
    """带单位数字（复用 fusion._VAL_RE），仅保留数值，单位用于归一后比较。"""
    return [(m.group(1), None) for m in _VAL_RE.finditer(text or "")]


def signal_digit(a: dict, b: dict) -> tuple[bool, dict]:
    """主信号：百分比或带单位数字，同单位区间 ±10% 相交 → 命中。

    返回 (hit, detail)。detail 记录命中来源（percent/unit）与具体数值，
    供报告展示与测试断言。

    2026-08-09 实测调优：**百分比通道仅取标题**——正文里的百分比常是
    不同指标（如 45.64% 股权比例 vs 55% 价格涨幅），数值相近但语义无关，
    造成误报（EV08↔EV10 活案例）；标题里的百分比是编辑提炼的核心数字，
    跨事件冲突概率低。带单位数字（384亿/12万片）保持 title+body。
    """
    detail = {"hit": False, "percent": None, "unit": None, "field": "title"}
    # 百分比：仅标题（核心数字），body 百分比噪声大
    pa, pb = _parse_percents(a.get("title", "")), _parse_percents(b.get("title", ""))
    if pa and pb and _intervals_overlap(_to_interval(pa), _to_interval(pb)):
        detail.update({"hit": True, "percent": f"{pa} vs {pb}", "field": "title"})
        return True, detail
    # 带单位数字：title+body，同一规范单位下区间相交
    for field, ta, tb in (("title", a.get("title", ""), b.get("title", "")),
                          ("body", a.get("body", ""), b.get("body", ""))):
        ua = {(unit, tuple(sorted(vals))) for unit, vals in _unit_nums(ta).items()}
        ub = {(unit, tuple(sorted(vals))) for unit, vals in _unit_nums(tb).items()}
        for unit_a, vals_a in ua:
            for unit_b, vals_b in ub:
                if unit_a != unit_b:
                    continue
                ia = _to_interval([(str(v), None) for v in vals_a])
                ib = _to_interval([(str(v), None) for v in vals_b])
                if _intervals_overlap(ia, ib):
                    detail.update({"hit": True, "unit": unit_a,
                                   "vals": f"{vals_a} vs {vals_b}", "field": field})
                    return True, detail
    return False, detail


def _unit_nums(text: str) -> dict[str, set[float]]:
    """带单位数字 → {规范单位: {数值...}}（复用 fusion._UNIT_NORM）。"""
    out: dict[str, set[float]] = {}
    for m in _VAL_RE.finditer(text or ""):
        unit = _UNIT_NORM.get(m.group(2), m.group(2))
        out.setdefault(unit, set()).add(float(m.group(1)))
    return out


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def signal_entity_plus_time(a: dict, b: dict) -> tuple[bool, dict]:
    """辅信号：标题共享实体 ≥1（< 聚类阈值 2 的临界）+ 发布日差 ≤3 天。

    published 为 unknown 时放行（不因缺日期否决），但该信号不命中，
    由其他信号兜底。
    """
    ea = extract_entities(a.get("title", ""))
    eb = extract_entities(b.get("title", ""))
    shared = ((ea["company"] | ea["event"] | ea["generic"])
              & (eb["company"] | eb["event"] | eb["generic"]))
    detail = {"hit": False, "shared_entities": sorted(shared),
              "published_diff_days": None}
    if len(shared) < MIN_SHARED_ENTITIES:
        return False, detail
    da, db = _parse_date(a.get("published", "")), _parse_date(b.get("published", ""))
    if da is None or db is None:
        detail["published_diff_days"] = None  # unknown 放行：不否决，但需其他信号
        # 只有实体共享 + 至少一个日期缺失 → 弱命中（低置信，medium）
        detail["hit"] = False
        return False, detail
    diff = abs((da - db).days)
    detail["published_diff_days"] = diff
    if diff <= TIME_WINDOW_DAYS:
        detail["hit"] = True
        return True, detail
    return False, detail


def _leak_tokens(text: str, normalize: bool = True) -> set[str]:
    """token 化：小写 → （可选）数字归一为 # → CJK/ASCII 边界插空格 → 切分 → 去停用词。

    关键：CJK 与 ASCII 之间无空格会粘连成单 token（如『dram合约价』、
    『384亿美元』），导致跨语言 Jaccard 恒为 0——插空格修复
    （2026-08-09 对抗审查产出；边界类含 \\d 覆盖数字↔中文）。

    normalize=True：Jaccard 相似度用（53-58% vs 55% 都变 #，对齐表述差异）；
    滤掉含 # 的归一噪声 token（q#/#q#/#b）。
    normalize=False：候选锚词用；保留原始词形，滤掉纯数字/带单位数字
    （384、53-58% 是具体值不是通用锚词，建议『亿美元』这类单位词才有意义）。
    """
    t = (text or "").lower()
    if normalize:
        t = re.sub(r"\d+", "#", t)
    t = re.sub(r"(?<=[a-z0-9#])(?=[\u4e00-\u9fff])", " ", t)  # ascii/数字→cjk 边界
    t = re.sub(r"(?<=[\u4e00-\u9fff])(?=[a-z0-9#])", " ", t)  # cjk→ascii/数字 边界
    toks = re.split(r"[^a-z0-9\u4e00-\u9fff#]+", t)
    out = set()
    for w in toks:
        w = w.strip(".")
        if len(w) <= 1 or w in _LEAK_STOP:
            continue
        if normalize:
            if "#" in w:           # 归一噪声：q#/#q#/#b/#nm
                continue
        else:
            # 非归一：滤掉纯数字/带单位数字 token（具体值不是锚词建议）
            if re.fullmatch(r"\d+(?:\.\d+)?(?:%|亿|万|美元|亿元|万片|片|层|GB|TB)?", w):
                continue
        if not re.search(r"[a-z\u4e00-\u9fff]", w):
            continue
        out.add(w)
    return out


def signal_jaccard(a: dict, b: dict) -> tuple[bool, dict]:
    """补信号：标题 token 集合 Jaccard ≥ 阈值（同语言近重复）。

    跨语言对（中英）Jaccard 天然低，此信号主要抓『同语言复述』；
    OR 组合下跨语言对由 digit/entity_time 兜底。
    """
    ta, tb = _leak_tokens(a.get("title", "")), _leak_tokens(b.get("title", ""))
    union = ta | tb
    j = (len(ta & tb) / len(union)) if union else 0.0
    return j >= JACCARD_THRESHOLD, {"hit": j >= JACCARD_THRESHOLD, "jaccard": round(j, 3),
                                    "tokens_a": sorted(ta), "tokens_b": sorted(tb)}


def _extract_candidates(a: dict, b: dict) -> dict:
    """候选锚词挖掘：双侧 title+body 共现 token，过滤三锚表+同义词组+停用词。

    返回 {shared: [], side_a: [], side_b: []}。shared 是两侧共现（最有价值，
    补一个锚即可让交集+1）；side_a/side_b 是单侧独有 token——跨语言对齐
    需人工配对同义词（如 contract price ↔ 合约价），MD 中提示。
    """
    text_a = (a.get("title", "") + " " + a.get("body", ""))
    text_b = (b.get("title", "") + " " + b.get("body", ""))
    # 候选锚词用非归一 token（保留原始词形，如『合约价』而非『#』）
    ta, tb = _leak_tokens(text_a, normalize=False), _leak_tokens(text_b, normalize=False)
    shared = ta & tb - _ALL_ANCHORS
    side_a = (ta - tb - _ALL_ANCHORS) - shared
    side_b = (tb - ta - _ALL_ANCHORS) - shared
    return {"shared": sorted(shared), "side_a": sorted(side_a), "side_b": sorted(side_b)}


def build_pairs(events: list[dict]) -> list[tuple[dict, dict]]:
    """仅 n_sources==1 的单源事件，按 event_id 排序后两两组合（确定性）。"""
    singles = sorted([e for e in events if e.get("n_sources", 1) == 1],
                     key=lambda e: e.get("event_id", ""))
    pairs = []
    for i in range(len(singles)):
        for j in range(i + 1, len(singles)):
            if len(pairs) >= MAX_PAIRS:
                return pairs
            pairs.append((singles[i], singles[j]))
    return pairs


def _priority(signals: dict) -> tuple[str, int]:
    """优先级：digit 命中 → high；仅 entity_time → medium；仅 jaccard → low。

    score = 命中信号权重和（digit 50 / entity_time 30 / jaccard 20）。"""
    score = 0
    if signals["digit"]["hit"]:
        score += 50
    if signals["entity_time"]["hit"]:
        score += 30
    if signals["jaccard"]["hit"]:
        score += 20
    if signals["digit"]["hit"]:
        return "high", score
    if signals["entity_time"]["hit"]:
        return "medium", score
    return "low", score


def detect(cleaned: list[dict], fused: list[dict]) -> dict:
    """主入口：对单源事件对跑三信号 OR，输出候选清单。

    返回 {meta, candidates, stats}。meta 记录阈值/输入规模；
    candidates 按 score 降序；stats 汇总信号命中分布。
    """
    by_source = {it["source_id"]: it for it in cleaned}
    candidates = []
    for ev_a, ev_b in build_pairs(fused):
        sa = ev_a["sources"][0] if ev_a.get("sources") else {}
        sb = ev_b["sources"][0] if ev_b.get("sources") else {}
        a = {**sa, "body": by_source.get(sa.get("source_id"), {}).get("body", "")}
        b = {**sb, "body": by_source.get(sb.get("source_id"), {}).get("body", "")}

        sig_digit, d_digit = signal_digit(a, b)
        sig_time, d_time = signal_entity_plus_time(a, b)
        sig_jac, d_jac = signal_jaccard(a, b)

        if not (sig_digit or sig_time or sig_jac):
            continue

        signals = {"digit": d_digit, "entity_time": d_time, "jaccard": d_jac}
        priority, score = _priority(signals)
        cand_anchors = _extract_candidates(a, b)

        # reason 组装：说明为什么可能是同一事件
        reasons = []
        if d_digit["hit"]:
            src = d_digit.get("percent") or d_digit.get("vals")
            reasons.append(f"数字相近({d_digit['field']}: {src})")
        if d_time["hit"]:
            reasons.append(f"共享实体{d_time['shared_entities']}+日期差{d_time['published_diff_days']}天")
        if d_jac["hit"]:
            reasons.append(f"标题相似(Jaccard={d_jac['jaccard']})")
        hint = ""
        if cand_anchors["shared"]:
            hint = f"，候选锚词 shared={cand_anchors['shared']}"
        elif cand_anchors["side_a"] and cand_anchors["side_b"]:
            hint = f"，两侧独有词需人工配对同义词({cand_anchors['side_a'][:2]} ↔ {cand_anchors['side_b'][:2]})"

        candidates.append({
            "pair": [ev_a["event_id"], ev_b["event_id"]],
            "sources": [
                {"event_id": ev_a["event_id"], "source_id": sa.get("source_id"),
                 "tier": sa.get("tier"), "title": sa.get("title"),
                 "published": sa.get("published")},
                {"event_id": ev_b["event_id"], "source_id": sb.get("source_id"),
                 "tier": sb.get("tier"), "title": sb.get("title"),
                 "published": sb.get("published")},
            ],
            "signals": signals,
            "shared_entities": d_time["shared_entities"],
            "published_diff_days": d_time["published_diff_days"],
            "candidate_anchors": cand_anchors,
            "priority": priority,
            "score": score,
            "reason": "可能是同一事件（" + "；".join(reasons) + "）" + hint,
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    stats = {
        "total_candidates": len(candidates),
        "by_priority": {"high": sum(1 for c in candidates if c["priority"] == "high"),
                        "medium": sum(1 for c in candidates if c["priority"] == "medium"),
                        "low": sum(1 for c in candidates if c["priority"] == "low")},
    }
    meta = {
        "generated": date.today().isoformat(),
        "input_events": len(fused),
        "single_source": sum(1 for e in fused if e.get("n_sources", 1) == 1),
        "pairs_checked": len(build_pairs(fused)),
        "thresholds": {"min_shared_entities": MIN_SHARED_ENTITIES,
                       "time_window_days": TIME_WINDOW_DAYS,
                       "jaccard": JACCARD_THRESHOLD,
                       "range_tolerance": RANGE_TOLERANCE},
    }
    return {"meta": meta, "candidates": candidates, "stats": stats}


def render_md(report: dict) -> str:
    """人读 Markdown：候选清单 + 人工审核指引。"""
    lines = [
        "# 漏聚探测器报告",
        "",
        f"> 生成于 {report['meta']['generated']} | 输入 {report['meta']['input_events']} 事件"
        f"（单源 {report['meta']['single_source']}）| 检查 {report['meta']['pairs_checked']} 对"
        f" | 候选 {report['stats']['total_candidates']} 个",
        "",
        "## 候选清单（按 score 降序）",
        "",
        "| 优先级 | pair | 命中信号 | 共享实体 | 日期差 | 候选锚词建议 | 理由 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in report["candidates"]:
        sigs = [k for k, v in c["signals"].items() if v["hit"]]
        anchors = []
        if c["candidate_anchors"]["shared"]:
            anchors.append("shared:" + ",".join(c["candidate_anchors"]["shared"]))
        if c["candidate_anchors"]["side_a"]:
            anchors.append("A侧:" + ",".join(c["candidate_anchors"]["side_a"][:4]))
        if c["candidate_anchors"]["side_b"]:
            anchors.append("B侧:" + ",".join(c["candidate_anchors"]["side_b"][:4]))
        lines.append(
            f"| {c['priority']} | {c['pair'][0]}↔{c['pair'][1]} | {','.join(sigs)} "
            f"| {','.join(c['shared_entities']) or '-'} "
            f"| {c['published_diff_days'] if c['published_diff_days'] is not None else '-'} "
            f"| {'; '.join(anchors) or '-'} | {c['reason'][:80]} |"
        )
    lines += [
        "",
        "## 审核指引",
        "",
        "- 本报告是**建议清单**：候选锚词需人工审核后手动写回 `fusion.py` 的",
        "  `COMPANY_ANCHORS` / `EVENT_ANCHORS` / `GENERIC_TERMS` / `SYNONYM_MAP`。",
        "- **shared** 候选最有价值：补一个锚词即可让两侧交集 +1，直击漏聚。",
        "- **A侧/B侧** 是单侧独有词：跨语言对（中英）需人工配对同义词组",
        "  （如 `contract price` ↔ `合约价`），配对后加入 `SYNONYM_MAP`。",
        "- `high` 优先级（数字命中）可信度高，建议优先审核；`low` 可忽略。",
        "- 误报是预期行为：宁可多报，不可让盲区继续存在。",
        "",
    ]
    return "\n".join(lines)


def main():
    cleaned = json.loads((DATA_DIR / "cleaned_events.json").read_text(encoding="utf-8"))
    fused = json.loads((DATA_DIR / "fused_events.json").read_text(encoding="utf-8"))
    report = detect(cleaned, fused)
    (DATA_DIR / "leak_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "leak_report.md").write_text(
        render_md(report), encoding="utf-8")
    st = report["stats"]
    print(f"[leak] 检查 {report['meta']['pairs_checked']} 对单源 → 候选 {st['total_candidates']} 个 "
          f"(high {st['by_priority']['high']} / medium {st['by_priority']['medium']} / "
          f"low {st['by_priority']['low']})")
    for c in report["candidates"][:10]:
        print(f"  [{c['priority']:6s}] {c['pair'][0]}↔{c['pair'][1]} | {c['reason'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
