#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.fusion — 模块3：数据融合与校验机制。

流程：
  1. 聚类（cluster）：实体共现聚类，标题提取公司/事件/通用词锚，
     两篇共享 ≥2 个实体 → 同一事件（2026-08-09 对抗审查起：仅标题、
     边界匹配、前置同义词归一，正文因 HBM 供应链交叉引用不再参与）。
  2. 交叉验证（cross_validate）：同一事件 ≥2 个独立来源（不同 source_id）
     佐证 → 标记 "verified"；仅 1 源 → "single_source"（置信度上限被压低）。
  3. 置信度评估（confidence）：综合 4 因子加权：
       tier_score   来源层级（Tier-0=1.0, 1=0.9, 2=0.85, 3=0.8, 4=0.6）取最高
       multi_source 多源度 = (n-1)/n （n=独立源数）
       freshness    时效 = 1.0(≤72h) → 0.6(>7d) 按运行当天衰减
       consistency  一致性 = 1.0(无分歧) / 0.6(有分歧) / 0.4(单源)
     confidence = 100 * (0.35*tier + 0.3*multi + 0.2*fresh + 0.15*consist)
  4. 分歧检测：同事件内各源正文的同单位指标数字（亿/万/片/层…）无交集
     视为硬冲突 → divergence 标记
输出：data/fused_events.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

TIER_SCORE = {0: 1.0, 1: 0.9, 2: 0.85, 3: 0.8, 4: 0.6}
W_TIER, W_MULTI, W_FRESH, W_CONSIST = 0.35, 0.30, 0.20, 0.15

# 关键数字 / 事实词（供 extract_entities 的 numbers 字段；聚类与分歧检测不用）
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:亿|万|%|美元|新台币|韩元|片|层|GB|TB)?")

# 实体锚点三级分类（解决高频词传染问题）
#   公司锚(company)：高特异主体，跨事件区分度最大
#   事件锚(event)：产品/型号/法案等事件级唯一标识，命中即同事件
#   通用词(generic)：频发技术词，须与公司锚/数字锚组合使用
COMPANY_ANCHORS = [
    "skhynix", "寒武纪", "tsmc", "长电", "通富", "华大九天",
    "概伦电子", "锐成芯微", "纳能微", "鼎龙", "南大光电", "samsung",
    "intel", "amd", "nvidia", "micron",
    "中芯", "华虹", "asml", "北方华创", "中微", "盛合晶微", "日月光",
    "华为", "麒麟", "昇腾", "盛美", "晶合",
]
EVENT_ANCHORS = [
    "mi400", "mi455x", "cdna", "instinct", "helios", "n2", "argus",
    "xdfoi", "match", "临港", "logicfolding", "14a", "terafab", "xe90",
    "x90plus", "y2", "m17",
]
GENERIC_TERMS = [
    "hbm", "dram", "nand", "2nm", "3nm", "5nm", "7nm", "14nm", "gaa",
    "euv", "duv", "cowos", "chiplet", "2.5d", "3dic", "光刻胶", "电子特气",
    "硅中介层", "混合键合", "扩产", "并购", "扭亏", "业绩", "财报", "良率",
    "价格", "融资", "ipo", "上市", "产能", "封测", "存储", "出口管制",
    "合同", "营收", "净利润", "爬坡",
    # 政策流程机构锚（2026-08-09 补：让 MATCH Act 中英双源标题共享实体）
    # 归一后英文命中 {foreignaffairs, house}，中文命中 {foreignaffairs, house}，交集=2 ✓
    "foreignaffairs", "house",
    # 价格事件锚（2026-08-09 迭代2 leak 审核回写：EV09↔EV10 存储价格双源漏聚）
    # 英文 'contract prices'→contractprice 命中 {dram, contractprice, 2q26}
    # 中文 '合约价'→contractprice 命中 {dram, contractprice, q2}，交集={dram,contractprice}=2 ✓
    "contractprice", "q2", "2q26",
]

# 同义词归一（变体 → 规范形，匹配前由 _normalize_text 先替换）
#   例：SK hynix / SK海力士 / 海力士 → skhynix；台积电 → tsmc
SYNONYM_MAP = {
    "sk hynix": "skhynix", "sk海力士": "skhynix", "海力士": "skhynix",
    "台积电": "tsmc",
    "英伟达": "nvidia",
    "三星": "samsung",
    "英特尔": "intel",
    "美光": "micron",
    "foreign affairs": "foreignaffairs", "外交事务": "foreignaffairs",
    "众议院": "house",
    # 价格术语中英配对（2026-08-09 迭代2 leak 审核回写：contract price ↔ 合约价）
    # 'contract prices'（复数）必须先于单数替换，避免残留尾缀 s 破坏边界断言
    "contract prices": "contractprice", "contract price": "contractprice",
    "合约价": "contractprice",
}


def _norm(kw: str) -> str:
    return SYNONYM_MAP.get(kw.lower(), kw.lower())


# 锚词匹配：ASCII 锚做词边界匹配（防 n2→N2X、2nm→0.7nm、y2→y2k）；
# 中文锚直接子串匹配——中文后跟数字是常态（『营收59.96亿』），
# 边界断言的后缀 (?![a-z0-9]) 会误伤导致锚丢失（2026-08-09 对抗审查修正）
def _anchored(pattern: str, low: str) -> bool:
    if any(ord(ch) > 127 for ch in pattern):
        return pattern in low
    return re.search(rf"(?<![a-z0-9.]){re.escape(pattern)}(?![a-z0-9])", low) is not None


def _normalize_text(text: str) -> str:
    """前置同义词归一：把中英变体（SK hynix/SK海力士/海力士 → skhynix）先替换为
    规范形，锚词匹配发生在归一之后的文本上。否则 SYNONYM_MAP 形同虚设——
    『sk hynix』（带空格）永远匹配不上锚词表里的『skhynix』。

    替换值两侧补空格：避免中文相邻变体替换后粘连（『众议院外交事务』若直接
    替换成 houseforeignaffairs，会破坏 house 锚的边界断言导致漏匹配）。
    按 key 长度降序替换，避免『sk海力士』被『海力士』抢先替换成半截。"""
    low = (text or "").lower()
    for k in sorted(SYNONYM_MAP, key=len, reverse=True):
        low = low.replace(k, f" {SYNONYM_MAP[k]} ")
    return low


def extract_entities(text: str) -> dict:
    """返回 {company:set, event:set, generic:set, numbers:set}。

    2026-08-09 对抗审查加固：
      1. 前置归一：变体先替换为规范形再匹配锚词（sk hynix → skhynix）
      2. 边界匹配：短锚不命中子串（n2 ≠ N2X，2nm ≠ 0.7nm）
      3. white house 负面排除：house 锚不误命中白宫新闻
    """
    low = _normalize_text(text)
    company, event, generic = set(), set(), set()
    for kw in COMPANY_ANCHORS:
        if _anchored(kw.lower(), low):
            company.add(_norm(kw))
    for kw in EVENT_ANCHORS:
        if _anchored(kw.lower(), low):
            event.add(_norm(kw))
    for kw in GENERIC_TERMS:
        if kw == "house" and "white house" in low:
            continue  # house 锚负面排除：白宫新闻不属于众议院法案事件
        if _anchored(kw.lower(), low):
            generic.add(_norm(kw))
    numbers = set(NUM_RE.findall(text or ""))
    return {"company": company, "event": event, "generic": generic, "numbers": numbers}


def _freshness(published: str, today=None) -> float:
    """时效分：以运行当天为基准（2026-08-09 对抗审查修复——原实现硬编码
    datetime(2026,8,8)，定时任务每天跑但基准永远冻结，时效分失真）。"""
    if not published or published == "unknown":
        return 0.6
    try:
        from datetime import datetime, date
        if today is None:
            today = date.today()
        d = datetime.strptime(published, "%Y-%m-%d").date()
        days = (today - d).days
        if days <= 3:
            return 1.0
        if days <= 7:
            return 0.85
        if days <= 30:
            return 0.7
        return 0.6
    except Exception:
        return 0.6


def cluster(cleaned: list[dict], min_shared: int = 2) -> list[list[dict]]:
    """实体共现聚类：两篇报道共享 ≥min_shared 个实体关键词 → 同一事件。

    相比纯 Jaccard，实体锚点（公司/技术/政策）对中英混杂标题更稳健：
    同一事件的『SK hynix 扩产』无论中英措辞如何，都命中 {skhynix, 扩产, hbm...}。

    实体仅从标题提取（2026-08-08 调优）：正文含 HBM 供应链交叉引用
    （如『SK hynix 为 AMD MI400 供 HBM』『AMD 采用台积电 N2 工艺』），
    会把不同事件串在一起造成误聚类；标题是编辑提炼的核心信息，最干净。
    published=unknown 的条目排最后（字符串比较会让 unknown 冒充最新，
    2026-08-09 对抗审查修复；reverse=True 下非 unknown 为 True 排最前）。
    """
    items = sorted(cleaned,
                   key=lambda c: (c["published"] != "unknown", c["published"]),
                   reverse=True)
    for it in items:
        # 仅标题；numbers 不参与聚类（NUM_RE 命中日期/编号等噪声）
        ent = extract_entities(it["title"])
        it["_entities"] = ent["company"] | ent["event"] | ent["generic"]
    groups: list[list[dict]] = []
    for it in items:
        placed = False
        for g in groups:
            rep = g[0]
            shared = it["_entities"] & rep["_entities"]
            if len(shared) >= min_shared:
                g.append(it)
                placed = True
                break
        if not placed:
            groups.append([it])
    return groups


# 指标数字正则：只抓『带单位』的数字（年份/投票/日期等无单位噪声被自动排除）
_VAL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(亿美元|亿元|亿|万片|万层|万张|万|片|层|GB|TB)")
# 软词窗口：数字前 8 字符内出现任一软词 → 该数字视为约数，不参与冲突判定
_SOFT_KW = ("约", "预计", "或", "接近", "可能", "超过")
# 单位归一：币种/量词变体 → 规范单位（亿美元/亿元 → 亿）
_UNIT_NORM = {"亿美元": "亿", "亿元": "亿", "万片": "万片", "万层": "万层", "万张": "万张"}


def _metric_nums(text: str) -> dict[str, set[float]]:
    """提取正文中的指标数字 → {规范单位: {数值...}}。百分比不参与（涨幅区间
    与单点表述差异不视为硬冲突）；软词邻近数字跳过。2026-08-09 对抗审查重写：
    旧实现用『整篇含软词就全软 + 集合差集』，既漏报（shared 数字 continue
    跳过 78亿 vs 58亿）又受年份噪声污染（两源共享 2026 直接跳过）。"""
    out: dict[str, set[float]] = {}
    for m in _VAL_RE.finditer(text or ""):
        unit = _UNIT_NORM.get(m.group(2), m.group(2))
        start = max(0, m.start() - 8)
        if any(k in text[start:m.start()] for k in _SOFT_KW):
            continue
        out.setdefault(unit, set()).add(float(m.group(1)))
    return out


def _detect_divergence(group: list[dict]) -> list[dict]:
    """检测组内源的关键数字/事实差异。

    2026-08-09 对抗审查重写（原实现 3 个缺陷）：
      1. `shared` 数字非空即 continue → 漏报『78亿 vs 58亿』（两源共享 12万片）
      2. 年份『2026』共享 → 漏报『59.96亿 vs 55亿』
      3. 无单位数字参与差集 → 误报『12万片』vs『330吨』（不同指标）
    新规则：同规范单位下，两源数值集合**无交集** → 硬冲突；有共同值（如
    A 含细分数字 78亿、B 只报 384亿，共享 384）→ 不报，避免细分误报。
    """
    divergences = []
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            a, b = group[i], group[j]
            ma, mb = _metric_nums(a["body"]), _metric_nums(b["body"])
            for unit in sorted(set(ma) & set(mb)):
                if not (ma[unit] & mb[unit]):  # 同单位、数值无交集 → 冲突
                    divergences.append({
                        "a": a["source_id"], "b": b["source_id"],
                        "a_claim": sorted(f"{v:g}{unit}" for v in ma[unit])[:3],
                        "b_claim": sorted(f"{v:g}{unit}" for v in mb[unit])[:3],
                        "note": f"关键数字不一致（{unit}）",
                    })
                    break
    return divergences


def fuse(cleaned: list[dict]) -> list[dict]:
    groups = cluster(cleaned)
    events = []
    for gi, g in enumerate(groups, 1):
        # 组内去重：同一源多条保留最新（g 内按 published 降序，reversed 后
        # 最新最后写入 dict 覆盖旧版；2026-08-09 对抗审查修复——原实现
        # 后者覆盖前者实际保留的是最旧条目，注释与行为相反）
        by_source = {it["source_id"]: it for it in reversed(g)}
        uniq = list(by_source.values())
        n_src = len(uniq)
        tier_max = max(it["tier"] for it in uniq)
        tier_score = TIER_SCORE.get(tier_max, 0.6)
        multi = (n_src - 1) / n_src if n_src > 1 else 0.0
        fresh = max(_freshness(it["published"]) for it in uniq)
        divergences = _detect_divergence(uniq)
        consist = 0.6 if divergences else (1.0 if n_src >= 2 else 0.4)
        confidence = round(
            100 * (W_TIER * tier_score + W_MULTI * multi + W_FRESH * fresh + W_CONSIST * consist), 1
        )
        # 主条目 = 最高 tier（一手优先），同 tier 取最新；unknown 日期视为最早
        primary = max(uniq, key=lambda it: (TIER_SCORE.get(it["tier"], 0),
                                            it["published"] != "unknown", it["published"]))
        sources = sorted(
            [{"source_id": it["source_id"], "source_name": it["source_name"],
              "tier": it["tier"], "type": it["type"], "title": it["title"],
              "url": it["url"], "published": it["published"],
              "publisher_domain": it.get("publisher_domain", "")}
             for it in uniq],
            key=lambda s: TIER_SCORE.get(s["tier"], 0), reverse=True,
        )
        events.append({
            "event_id": f"EV{gi:02d}",
            "title": primary["title"],
            "segment": primary["segment"],
            "published": max((it["published"] for it in uniq if it["published"] != "unknown"),
                             default="unknown"),
            "n_sources": n_src,
            "n_unique_sources": n_src,
            "verification": "verified" if n_src >= 2 else "single_source",
            "confidence": confidence,
            "confidence_breakdown": {
                "tier_score": tier_score, "multi_source": round(multi, 3),
                "freshness": round(fresh, 3), "consistency": consist,
            },
            "divergences": divergences,
            "primary_source": sources[0] if sources else None,
            "sources": sources,
            "summary": primary["body"][:160],
        })
    events.sort(key=lambda e: (e["confidence"], e["n_sources"]), reverse=True)
    return events


def main():
    cleaned = json.loads((DATA_DIR / "cleaned_events.json").read_text(encoding="utf-8"))
    events = fuse(cleaned)
    (DATA_DIR / "fused_events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(f"[fusion] 融合 {len(cleaned)} 条原始 → {len(events)} 条事件")
    print("[fusion] 验证状态:", dict(Counter(e["verification"] for e in events)))
    if events:
        print("[fusion] 平均置信度:", round(sum(e["confidence"] for e in events) / len(events), 1))
        for e in events[:5]:
            print(f"  {e['event_id']} [{e['verification']}] conf={e['confidence']} 源数={e['n_sources']} {e['title'][:36]}")
    else:
        # 0 条事件是合法场景（规则 X12：节假日 0 条 PASS），不能除零崩溃
        print("[fusion] 无事件（节假日/无数据），跳过统计")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
