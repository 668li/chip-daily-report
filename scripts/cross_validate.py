"""
M1 · 来源交叉验证（事实三角验证层）

设计目标（见 references/evolution_plan.md §3）：
- 把「来源真实性」从「URL 存在」升级为「事实三角验证」——
  同一事实 ≥2 独立源支撑 → 跨源核验通过（cross_validated）；
  单源 → 自动标记「待核实」且推荐级别至多 B。
- 这是封死 ghost 幻觉天花板的唯一结构性办法。

实现要点：
- 纯函数、零第三方依赖（系统 Python 3.13，环境无 jsonschema/pytest）。
- 不重写任何硬校验；M1 在 M0 的 IR 之上叠加 `verification` 字段。
- 默认 advisory（不改 level，保 26 项零回归）；`apply_downgrades()` 显式降级，仅用于新生成流水线。
- 交叉项聚类：同一事实在多个环节被分别报道时，合并各自来源做三角验证。

接口：
- cross_validate(report) -> dict            # 返回 verification，不改动 report
- apply_downgrades(report, verification)     # 就地降级单源 A -> B + 置 needs_verification
- domain_of(url) / normalize_sources(sources)
"""
from __future__ import annotations

from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

STOP = set(
    "的 了 与 和 在 对 是 及 将 已 其 该 为 等 也 并 中 上 下 通过 表示 据 称 可能 预计 "
    "月 日 年 公司 宣布 发布 协议 合作 计划 表示将 称其 目标 全球 中国 美国 产业 市场 "
    "芯片 半导体 技术 产品 业务 增长 提升 下跌 上涨 上涨 季度 年度".split()
)


def domain_of(url: str) -> str:
    """从 URL 抽取域名（小写、去 www.）。非法 URL 返回空串。"""
    if not url:
        return ""
    try:
        net = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""
    return net


def normalize_sources(sources):
    """把 IR 的 sources（news 为 (name,url) 元组 / catalyst 为 {name,url,level} 字典）
    统一为 [{name, url, domain}]，并去重（按 url）。"""
    out = []
    seen = set()
    for s in sources or []:
        if isinstance(s, dict):
            name, url = s.get("name", ""), s.get("url", "")
        else:
            # 元组 / 列表
            try:
                name, url = s[0], s[1]
            except Exception:
                continue
        if not url:
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "url": url, "domain": domain_of(url)})
    return out


def _entities(text: str) -> set:
    """抽取「特定实体」用于同一事实聚类（避免通用词污染）。

    只取：拉丁公司/产品代号（>=3 字母，去常见虚词）；以及中文括号括起的机构名。
    不取通用二元组（芯片/半导体/封装 等全篇高频词），否则会把整份日报误并成一组。
    """
    if not text:
        return set()
    ents = set()
    import re

    for m in re.findall(r"[A-Za-z][A-Za-z0-9.+&\-]{2,}", text):
        w = m.lower()
        if w in STOP or w in ("inc", "corp", "ltd", "co", "the", "and", "com", "www"):
            continue
        ents.add(w)
    # 中文括号机构名：（台积电）/（英伟达）等
    for m in re.findall(r"[（(]([^（）()]{2,10})[）)]", text):
        ents.add("zh:" + m)
    return ents


# ---------------------------------------------------------------------------
# 核心：交叉验证
# ---------------------------------------------------------------------------


def cross_validate(report: dict) -> dict:
    """对 IR 做来源交叉验证，返回 verification dict（不改动 report）。

    verification 结构：
    {
      "total", "cross_validated", "needs_verification", "single_source",
      "multi_source",
      "clusters": [{"tokens":[...], "items":[title...], "domains":[...]}],
      "items": [{"segment","title","n_sources","n_domains","domain_level",
                 "recommended_level","cross_validated","needs_verification"}]
    }
    """
    segments = report.get("segments", {}) or {}
    flat = []  # (segment, item)
    for seg, items in segments.items():
        for it in items or []:
            flat.append((seg, it))

    # 1) 逐条基础判定
    per_item = {}
    for seg, it in flat:
        norms = normalize_sources(it.get("sources"))
        domains = {n["domain"] for n in norms if n["domain"]}
        n_src = len(norms)
        n_dom = len(domains)
        base_cv = n_dom >= 2  # 单条自带 ≥2 独立域 -> 跨源核验通过
        dom_level = it.get("level") or "B"
        per_item[id(it)] = {
            "seg": seg,
            "it": it,
            "norms": norms,
            "domains": domains,
            "n_src": n_src,
            "n_dom": n_dom,
            "domain_level": dom_level,
            "cross_validated": base_cv,
            "tokens": _entities(
                (it.get("title", "") or "") + " " + (it.get("summary", "") or "")
            ),
        }

    # 2) 交叉项聚类：同一事实被多环节分别报道 -> 合并来源做三角验证
    clusters = []
    used = set()
    ids = list(per_item.keys())
    for i in range(len(ids)):
        if ids[i] in used:
            continue
        a = per_item[ids[i]]
        group = [ids[i]]
        union_dom = set(a["domains"])
        union_tok = set(a["tokens"])
        for j in range(i + 1, len(ids)):
            if ids[j] in used:
                continue
            b = per_item[ids[j]]
            overlap = a["tokens"] & b["tokens"]
            # 共享 ≥3 显著 token 视为同一事实
            if len(overlap) >= 3:
                group.append(ids[j])
                union_dom |= b["domains"]
                union_tok |= b["tokens"]
                used.add(ids[j])
        used.add(ids[i])
        if len(group) >= 2 and len(union_dom) >= 2:
            # 整组跨源核验通过
            for gid in group:
                per_item[gid]["cross_validated"] = True
            clusters.append(
                {
                    "tokens": sorted(union_tok)[:8],
                    "items": [per_item[g]["it"].get("title", "") for g in group],
                    "domains": sorted(union_dom),
                }
            )

    # 3) 汇总 + 推荐级别
    items_out = []
    n_cv = n_need = n_single = n_multi = 0
    for key, info in per_item.items():
        cv = info["cross_validated"]
        n_src = info["n_src"]
        if n_src <= 1:
            n_single += 1
        else:
            n_multi += 1
        if cv:
            n_cv += 1
            recommended = info["domain_level"]  # 跨源通过，保留域名分级
        else:
            n_need += 1
            # 单源：推荐至多 B（即便域名是 A 级）
            recommended = "B" if info["domain_level"] == "A" else info["domain_level"]
        items_out.append(
            {
                "segment": info["seg"],
                "title": info["it"].get("title", ""),
                "n_sources": n_src,
                "n_domains": info["n_dom"],
                "domain_level": info["domain_level"],
                "recommended_level": recommended,
                "cross_validated": cv,
                "needs_verification": not cv,
            }
        )

    total = len(per_item)
    verification = {
        "total": total,
        "cross_validated": n_cv,
        "needs_verification": n_need,
        "single_source": n_single,
        "multi_source": n_multi,
        "clusters": clusters,
        "items": items_out,
    }
    return verification


def apply_downgrades(report: dict, verification: dict | None = None) -> dict:
    """就地应用 M1 降级：单源且被标 A 的新闻 -> B，并标记 needs_verification。

    仅用于新生成流水线（LLM 直出 IR 后）。对黄金样本做回归时默认不调用，
    以保 26 项零回归。
    返回 verification（若未传入则现算）。
    """
    if verification is None:
        verification = cross_validate(report)
    by_title = {(v["segment"], v["title"]): v for v in verification["items"]}
    for seg, items in report.get("segments", {}).items():
        for it in items or []:
            key = (seg, it.get("title", ""))
            v = by_title.get(key)
            if not v:
                continue
            if v["needs_verification"]:
                it["needs_verification"] = True
                if it.get("level") == "A" and v["recommended_level"] == "B":
                    it["level"] = "B"  # 单源 A -> 降 B（事实三角验证）
            else:
                it["verified"] = True
    report["verification"] = verification
    return verification


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from report_renderer import to_json, from_json

    p = sys.argv[1] if len(sys.argv) > 1 else None
    apply = "--apply" in sys.argv
    if not p:
        print("usage: python cross_validate.py <report.md|report.json> [--apply]")
        raise SystemExit(1)

    if p.endswith(".json"):
        rep = from_json(open(p, encoding="utf-8").read())
    else:
        from report_viz import parser

        rep = parser.parse_report(p)

    ver = cross_validate(rep)
    if apply:
        apply_downgrades(rep, ver)
        # 路径边界（防穿越）：写入位置固定为项目 delivery/ 目录，
        # 文件名取输入文件主干，CLI 路径成分不进入写入位置。
        _delivery = __import__("pathlib").Path(__file__).resolve().parent.parent / "delivery"
        _out = _delivery / (__import__("pathlib").Path(p).stem + ".verified.json")
        _out.parent.mkdir(parents=True, exist_ok=True)
        with _out.open("w", encoding="utf-8") as f:
            f.write(to_json(rep))
        print(f"[cross_validate] 已应用降级 -> {_out}")

    print(f"总新闻: {ver['total']}")
    print(f"跨源核验通过: {ver['cross_validated']}  | 待核实: {ver['needs_verification']}")
    print(f"单源: {ver['single_source']}  | 多源: {ver['multi_source']}")
    if ver["clusters"]:
        print(f"交叉项聚类（同事实多源）: {len(ver['clusters'])} 组")
        for c in ver["clusters"]:
            print(f"  - {c['items']}  | 域: {c['domains']}")
    print("\n逐条:")
    for v in ver["items"]:
        flag = "✓跨源" if v["cross_validated"] else "⚠待核实"
        rec = f"->{v['recommended_level']}" if v["recommended_level"] != v["domain_level"] else ""
        print(
            f"  [{flag}] {v['segment']} | {v['title'][:28]} | "
            f"源{v['n_sources']}/域{v['n_domains']} | 域级{v['domain_level']}{rec}"
        )
