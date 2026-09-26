#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.gate — 模块4.5：选择性纳入门禁（迭代3 新增 · 2026-08-15）。

定位：fusion 打分 → gate 选择性纳入 → 日报候选池。
把 multi_source 从「只打分不拦截」升级为「打分 + 门禁」：低置信度 /
超时效 / 偏离主题 / 环节失衡的事件在进日报前被拦截，且每条拦截都可解释。

为什么需要 gate（2026-08-15 调研结论）：
  - fusion 已算 confidence/verification/divergence，但结果没有真正挡在
    日报生成前面 —— 打分不被消费，等于白算；
  - 日报生成的 Step 2 目前「靠搜索碰运气」，候选池不固定、信息密度波动大；
  - 用户明确要求「接入更多源 + 提纯 + 选择性纳入」：多源带来噪音，
    必须有一道可解释的门禁把「有用事件」与「噪音」分开。

门禁规则（全部可解释，逐条记 reason）：
  G1 置信度阈值   confidence < conf_min → REJECT(reason=low_confidence)
  G2 时效门禁     发布时间距今 > stale_days 且标题未含[回顾] → 降级标记
                 （不直接剔除 —— 芯片行业新闻跨周仍有价值，降级后由日报
                 生成方决定是否标[回顾]；与 validate 72h 口径对齐）
  G3 来源分级     verification=single_source 且 tier 最高为 4 → 标记
                 single_low_tier（仅作线索，不直接剔除 —— 冷门公司
                 常只有聚合源，见 sources.md 使用纪律）
  G4 环节配额     每环节最多 max_per_segment 条（默认 6）；超额环节按
                 confidence 降序截断，超出者 → REJECT(reason=segment_quota)
  G5 关键词相关性 标题命中 EXCLUDE_KW → REJECT(reason=off_topic)；
                 标题未命中 INCLUDE_KW → REJECT(reason=irrelevant)
                 （INCLUDE 覆盖 5 环节 + 投资/AI/创新 主题，与用户
                 热点过滤硬性偏好一致）
  G6 数量上限     按 confidence 降序取前 top_n（默认 24），超出者
                 → REJECT(reason=top_n_cap)

输出：state/gate_report.json（fail-soft，任何异常不阻塞下游）
  {
    "generated": ISO时间,
    "stats": {"raw": n, "candidates": n, "rejected": n,
              "by_reason": {"low_confidence": n, "off_topic": n, ...}},
    "candidates": [事件摘要…],   // 进日报候选池（按 confidence 降序）
    "rejected":   [被拒事件 + reason],
  }

CLI：python scripts/multi_source/gate.py
     [--events scripts/multi_source/data/fused_events.json]（默认）
     [--conf-min 60] [--stale-days 7] [--max-per-segment 6] [--top-n 24]
     [--out state/gate_report.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "state"
DEFAULT_EVENTS = ROOT / "scripts" / "multi_source" / "data" / "fused_events.json"
DEFAULT_OUT = STATE_DIR / "gate_report.json"

# 关键词白名单（INCLUDE）：命中任一即保留 —— 5 环节 + 投资/AI/创新
INCLUDE_KW = [
    # 5 环节
    "芯片", "半导体", "晶圆", "代工", "制程", "封装", "测试", "光刻",
    "存储", "内存", "hbm", "dram", "nand", "ssd", "闪存", "gpu", "cpu",
    "soc", "asic", "fpga", "eda", "ip核", "设计", "流片", "fab", "foundry",
    "设备", "材料", "硅片", "光刻胶", "特气", "靶材", "cmp", "清洗",
    "cowos", "chiplet", "2.5d", "3d", "先进封装", "hbm4", "hbm3",
    # 公司
    "台积电", "tsmc", "三星", "samsung", "sk", "海力士", "美光", "micron",
    "英特尔", "intel", "英伟达", "nvidia", "amd", "高通", "联发科",
    "中芯", "smic", "华虹", "长鑫", "长江存储", "寒武纪", "华为", "海思",
    "昇腾", "麒麟", "asml", "东京电子", "应用材料", "lam", "kla",
    "北方华创", "中微", "长电", "通富", "华天", "日月光", "amkor",
    "synopsys", "cadence", "华大九天", "概伦", "芯原",
    # 主题：投资/AI/创新/政策
    "ai", "人工智能", "算力", "大模型", "智算", "数据中心",
    "融资", "ipo", "并购", "收购", "投资", "扩产", "产能", "资本开支",
    "财报", "营收", "净利润", "业绩", "预增", "扭亏",
    "出口管制", "实体清单", "管制", "禁令", "制裁", "关税",
    "涨价", "降价", "供需", "缺货", "景气",
    "量子", "光子", "硅光", "射频", "功率半导体", "sic", "gan", "碳化硅", "氮化镓",
    "risc-v", "arm", "x86", "chiplet", "pcu", "hpc",
]

# 关键词黑名单（EXCLUDE）：标题命中任一 → 剔除（与用户热点过滤偏好一致）
EXCLUDE_KW = [
    "娱乐", "八卦", "明星", "网红", "美食", "旅游", "体育", "足球", "篮球",
    "游戏攻略", "抽奖", "彩票", "养生", "情感", "星座", "房产", "招聘",
    "带货", "促销", "优惠券", "二手车", "综艺", "电影", "电视剧", "音乐",
]

# 时效门禁：超过该天数视为"跨周旧闻"，标记降级（不剔除）
STALE_DAYS = 7


def _today() -> date:
    return date.today()


# 短英文关键词（≤4 字符）做词边界匹配：防 "ai" 误命中 "again"、"sic" 误命中
# "basic" 等子串（2026-08-15 端到端实测：CNBC 跑车新闻混入候选池的根因）。
_ASCII_SHORT_MAX = 4


def _kw_in(text_low: str, kw: str) -> bool:
    """关键词命中判定：纯 ASCII 短词（≤4）用词边界，其余子串匹配。"""
    kwl = kw.lower()
    if kwl.isascii() and len(kwl) <= _ASCII_SHORT_MAX:
        return re.search(rf"(?<![a-z0-9]){re.escape(kwl)}(?![a-z0-9])", text_low) is not None
    return kwl in text_low


# 标准 5 环节（G4 配额只对这些环节计数；综合/未知作横切线索不占配额）
CORE_SEGMENTS = ("设计", "制造", "封测", "EDA", "材料")


def _days_since(published: str, today: date | None = None) -> int | None:
    """发布时间距今天数；无法解析/unknown → None。"""
    if not published or published == "unknown":
        return None
    try:
        d = datetime.strptime(published, "%Y-%m-%d").date()
        base = today or _today()
        return (base - d).days
    except Exception:
        return None


def _title_has_review_tag(title: str) -> bool:
    return bool(re.search(r"\[(回顾|译|独家)\]", title or ""))


# ---- v8 P1-D（2026-09-26）：publisher_domain 消费点 ----
# Google News 条目的 <source url=出版方域> 经 cleaner/fusion 透传到事件源条目。
# 消费点：G3 单源分级——若出版方域是 A 级官方一手域（rule_registry.yaml 唯一
# 权威源，X8 父域匹配口径），不该因「经聚合 feed 发现」被打 single_low_tier。
_OFFICIAL_DOMAINS: set[str] | None = None


def _official_domains() -> set[str]:
    """A 级域名集合（运行时读 rule_registry.yaml 即权威，无手工同步）。"""
    global _OFFICIAL_DOMAINS
    if _OFFICIAL_DOMAINS is None:
        try:
            import yaml
            reg = yaml.safe_load(
                (ROOT / "rules" / "rule_registry.yaml").read_text(encoding="utf-8")) or {}
            _OFFICIAL_DOMAINS = {
                (d.get("domain") or "").lower()
                for d in ((reg.get("domains") or {}).get("a_level") or [])
                if d.get("domain")}
        except Exception:
            _OFFICIAL_DOMAINS = set()  # fail-soft：读不到就维持旧行为
    return _OFFICIAL_DOMAINS


def _host_of(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    host = urlparse(u).netloc.lower()
    host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_official_domain(url: str = "", publisher_domain: str = "") -> bool:
    """url 或出版方域命中 A 级域（== 或 endswith('.'+域)）即官方一手。"""
    doms = _official_domains()
    if not doms:
        return False
    for cand in (publisher_domain, url):
        host = _host_of(cand)
        if host and any(host == d or host.endswith("." + d) for d in doms):
            return True
    return False


def gate(events: list[dict], conf_min: float = 60.0, stale_days: int = STALE_DAYS,
         max_per_segment: int = 6, top_n: int = 24) -> dict:
    """执行选择性纳入门禁。events 为 fusion.fuse() 输出结构（dict 列表）。

    返回 {generated, stats, candidates, rejected}。任何输入异常 fail-soft：
    空 events → 空候选；单条事件字段缺失 → 跳过该条。
    """
    today = _today()
    rejected: list[dict] = []
    passed: list[dict] = []
    by_reason: dict[str, int] = {}

    def _reject(ev: dict, reason: str):
        by_reason[reason] = by_reason.get(reason, 0) + 1
        rejected.append({
            "event_id": ev.get("event_id"),
            "title": (ev.get("title") or "")[:60],
            "confidence": ev.get("confidence"),
            "verification": ev.get("verification"),
            "segment": ev.get("segment"),
            "reason": reason,
        })

    for ev in events:
        if not isinstance(ev, dict) or not ev.get("title"):
            continue
        title = ev["title"]
        conf = ev.get("confidence") or 0
        segment = ev.get("segment") or "综合"

        # G1 置信度阈值
        if conf < conf_min:
            _reject(ev, "low_confidence")
            continue

        # G5 关键词相关性（先黑后白）
        t = title.lower()
        if any(kw in t for kw in EXCLUDE_KW):
            _reject(ev, "off_topic")
            continue
        if not any(_kw_in(t, kw) for kw in INCLUDE_KW):
            _reject(ev, "irrelevant")
            continue

        # 通过 G1/G5 后进入候选（G2/G3 为降级标记，不剔除）
        flags = []
        days = _days_since(ev.get("published"), today)
        if days is not None and days > stale_days and not _title_has_review_tag(title):
            flags.append("stale")  # 降级：日报生成方决定是否标[回顾]
        if ev.get("verification") == "single_source" and _max_tier(ev) == 4:
            ps = ev.get("primary_source") or {}
            if _is_official_domain(ps.get("url", ""), ps.get("publisher_domain", "")):
                flags.append("official_primary")  # P1-D：官方一手域，单源不降级
            else:
                flags.append("single_low_tier")  # 仅作线索
        entry = {
            "event_id": ev.get("event_id"),
            "title": title[:80],
            "segment": segment,
            "published": ev.get("published"),
            "confidence": conf,
            "verification": ev.get("verification"),
            "n_sources": ev.get("n_sources"),
            "flags": flags,
            "primary_source": (ev.get("primary_source") or {}).get("url", ""),
        }
        passed.append(entry)

    # G4 环节配额：核心 5 环节每环节至多 max_per_segment 条（按 confidence 降序）；
    # 综合/未知作横切线索（政策/市场维度），不占配额。
    passed.sort(key=lambda e: e["confidence"], reverse=True)
    seg_count: dict[str, int] = {}
    keep: list[dict] = []
    for ev in passed:
        seg = ev["segment"]
        if seg in CORE_SEGMENTS and seg_count.get(seg, 0) >= max_per_segment:
            _reject({**ev, "event_id": ev["event_id"], "title": ev["title"],
                     "confidence": ev["confidence"]}, "segment_quota")
            continue
        if seg in CORE_SEGMENTS:
            seg_count[seg] = seg_count.get(seg, 0) + 1
        keep.append(ev)

    # G6 数量上限
    candidates = keep[:top_n]
    for ev in keep[top_n:]:
        _reject({**ev, "event_id": ev["event_id"], "title": ev["title"],
                 "confidence": ev["confidence"]}, "top_n_cap")

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rules": {
            "conf_min": conf_min,
            "stale_days": stale_days,
            "max_per_segment": max_per_segment,
            "top_n": top_n,
        },
        "stats": {
            "raw": len(events),
            "candidates": len(candidates),
            "rejected": len(rejected),
            "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
        },
        "candidates": candidates,
        "rejected": rejected,
    }


def _max_tier(ev: dict) -> int:
    """事件内最高 source tier（fusion 未直接暴露 tier_max，从 sources 推）。"""
    srcs = ev.get("sources") or []
    tiers = [s.get("tier", 4) for s in srcs if isinstance(s, dict)]
    return max(tiers) if tiers else 4


def main() -> int:
    ap = argparse.ArgumentParser(description="multi_source 选择性纳入门禁（G1-G6）")
    ap.add_argument("--events", default=str(DEFAULT_EVENTS))
    ap.add_argument("--conf-min", type=float, default=60.0)
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS)
    ap.add_argument("--max-per-segment", type=int, default=6)
    ap.add_argument("--top-n", type=int, default=24)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    try:
        events = json.loads(Path(args.events).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[gate] 读取事件失败（fail-soft，输出空候选）：{e}")
        events = []

    report = gate(events, args.conf_min, args.stale_days,
                  args.max_per_segment, args.top_n)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = report["stats"]
    print(f"[gate] 原始 {s['raw']} 条 → 候选 {s['candidates']} 条 / 拒 {s['rejected']} 条")
    if s["by_reason"]:
        print("[gate] 拒绝原因:", s["by_reason"])
    try:
        rel = out.relative_to(ROOT)
    except ValueError:
        rel = out
    print(f"[gate] 已写回 {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
