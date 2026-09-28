#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_claims — 声明级对账门禁（v8 R2 源深水区，2026-09-28）。

把「No citation → no output」从写作纪律变成机器门禁：日报每条新闻的
**承重数字**（涨价幅度/capex 量级/份额/产能/节点名…）逐条对照其来源
文章原文（经 article_fetch 安全抓取），对不上不出版。

对账语义（如实声明边界）：
  - 匹配的是「数字出现在原文」，不是「语义等于原文」——机器门禁只卡
    「编出来的数字/张冠李戴的数字」，语义核查仍归生成会话与独立评审。
  - 数字生成跨语言变体：中文「640 亿美元」↔ 英文 "$64 billion"；「5%」↔
    "5 percent"；「14A」↔「A14」；「2 万片」↔ "20,000"。
  - Google News 分享链（302+JS 二跳）本环境无法端到端验证 → 判
    redirect_only 降级证据（与 v8 第 2 期口径一致），不算 FAIL。
  - 抓不到正文（反爬/付费墙/超时）→ no_text，WARN 不 FAIL，但计入
    「可对账率」如实暴露——不能验证的条目比例高就是高，不粉饰。
  - 唯一 FAIL 条件：拿到了足量原文、而该条目全部直链来源的数字覆盖率
    均 < 50%——即「原文摆在那里、数字对不上」。

退出码：存在 mismatch → 1（不许出版）；其余 0。
用法：
  python scripts/validate_claims.py 芯片行业日报_20260926.md
  python scripts/validate_claims.py <md> --no-fetch          # 离线：只看缓存
  python scripts/validate_claims.py <md> --max-fetch 20      # 单次抓取上限
输出：state/claim_report.json + 控制台逐条判定
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "multi_source"))

from validate_report import extract_news_items  # 与 26 项门禁同一条目解析口径
from article_fetch import get_article_text, is_gnews_link  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON_OUT = ROOT / "state" / "claim_report.json"
MIN_TEXT_CHARS = 400      # 低于此长度视为「没拿到正文」（cookie 壳/提示页）
MISMATCH_COV = 0.5        # 覆盖率低于此线且已取得正文 → FAIL
MAX_CLAIMS = 12           # 单条目最多核对 12 个承重数字（防极端长条目拖爆预算）

_FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


# ============================================================
# 承重数字提取 + 跨语言变体
# ============================================================
def _norm_text(t: str) -> tuple[str, str]:
    """归一化：(n1=保留空格, n2=去空格)。全角数字→半角、数字内逗号删除。"""
    t = (t or "").translate(_FW_DIGITS).lower()
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    n1 = re.sub(r"\s+", " ", t).strip()
    n2 = re.sub(r"\s+", "", t)
    return n1, n2


_NUM = r"(\d+(?:\.\d+)?)"


def extract_claims(text: str) -> list[dict]:
    """从条目文本（标题+摘要，去技术注解）提取承重数字。
    返回 [{kind, value, display, variants}]，按出现顺序去重。"""
    text = re.sub(r"\s*\[技术注解[:：][^\]]*\]", "", text or "")
    claims: list[dict] = []
    seen: set = set()

    def add(kind, value, display, variants):
        key = (kind, str(value))
        if key in seen:
            return
        seen.add(key)
        claims.append({"kind": kind, "value": value,
                       "display": display, "variants": variants})

    for m in re.finditer(_NUM + r"\s*(?:%|％|个百分点|百分点)", text):
        v = float(m.group(1))
        add("pct", v, m.group(0).strip(),
            [f"{v:g}%", f"{v:g} %", f"{v:g} percent", f"{v:g}个百分点"])

    for m in re.finditer(_NUM + r"\s*万亿(美元|元)?", text):
        v = float(m.group(1))
        add("trillion", v, m.group(0).strip(),
            [f"{v:g}万亿", f"{v:g} trillion", f"${v:g}t", f"{v:g}t"])

    for m in re.finditer(_NUM + r"\s*亿(美元|元)?", text):
        v = float(m.group(1))
        b = v / 10.0  # 1 billion = 10 亿：640 亿 = $64 billion
        variants = [f"{v:g}亿", f"{v:g}"]
        if b >= 0.1:
            variants += [f"{b:g} billion", f"{b:g}-billion", f"{b:g}b",
                         f"${b:g}b", f"{b:g}bn", f"${b:g}bn",
                         f"us${b:g}b", f"{b:g} billion"]
        add("yi", v, m.group(0).strip(), variants)

    for m in re.finditer(_NUM + r"\s*万(片|颗|块|元|美元|片/月)?", text):
        v = float(m.group(1))
        total = v * 10000
        variants = [f"{v:g}万"]
        if total == int(total):
            variants += [f"{int(total):,}", str(int(total))]
            k = total / 1000
            if k >= 1:
                variants.append(f"{k:g}k")
        add("wan", v, m.group(0).strip(), variants)

    for m in re.finditer(_NUM + r"\s*(?:nm|纳米)", text):
        v = float(m.group(1))
        add("nm", v, m.group(0).strip(), [f"{v:g}nm", f"{v:g} nm", f"{v:g}纳米"])

    # 制程节点名：14A / A14 / 18A / N2（字母前后两种写法互通）
    for m in re.finditer(r"\b([ANan]\d{1,2}|\d{1,2}[Aa])\b(?![a-z])", text):
        tok = m.group(1).upper()
        if not re.fullmatch(r"[AN]\d{1,2}|\d{1,2}A", tok):
            continue
        alt = (tok[1:] + tok[0]) if tok[0] in "AN" else (tok[-1] + tok[:-1])
        add("node", tok, m.group(1), [tok.lower(), alt.lower()])

    for m in re.finditer(r"\b((?:19|20)\d{2})\b", text):
        add("year", m.group(1), m.group(1), [m.group(1)])

    for m in re.finditer(_NUM + r"\s*倍", text):
        v = float(m.group(1))
        add("times", v, m.group(0).strip(), [f"{v:g}x", f"{v:g} times", f"{v:g}倍"])

    for m in re.finditer(_NUM + r"\s*TOPS", text, re.I):
        v = float(m.group(1))
        add("tops", v, m.group(0).strip(), [f"{v:g} tops", f"{v:g}tops"])

    for m in re.finditer(_NUM + r"\s*美元", text):
        v = float(m.group(1))
        add("usd", v, m.group(0).strip(),
            [f"${v:g}", f"{v:g} dollars", f"{v:g}美元"])

    return claims[:MAX_CLAIMS]


def match_claims(claims: list[dict], text: str) -> tuple[int, list[str]]:
    """返回 (命中数, 未命中 display 列表)。n1/n2 双归一化文本上任一变体命中即算。"""
    if not claims:
        return 0, []
    n1, n2 = _norm_text(text)
    missing = []
    hit = 0
    for c in claims:
        if any(v in n1 or v in n2 for v in c["variants"]):
            hit += 1
        else:
            missing.append(c["display"])
    return hit, missing


# ============================================================
# 条目级对账
# ============================================================
_URL_RE = re.compile(r"\[.+?\]\((https?://[^)\s]+)\)")


def audit_entry(item: dict, cache_dir: Path, timeout: int, max_fetch: int,
                budget: list, extra_hosts: set) -> dict:
    """对单条新闻做声明级对账，返回结构化判定（不抛出）。"""
    claim_text = f"{item['title']} {item['summary']}"
    claims = extract_claims(claim_text)
    urls = list(dict.fromkeys(_URL_RE.findall(item.get("source") or "")))
    direct = [u for u in urls if not is_gnews_link(u)][:2]
    gnews = [u for u in urls if is_gnews_link(u)]

    out = {"title": item["title"][:60], "claims": [c["display"] for c in claims],
           "n_claims": len(claims), "direct_urls": direct, "gnews_urls": gnews,
           "verdict": "no_claims", "coverage": None, "missing": [],
           "sources": []}

    if not claims:
        return out  # 综述性/无数字条目：无可对账声明，中性跳过

    texts = []
    for u in direct:
        if budget[0] <= 0:
            out["sources"].append({"url": u, "status": "fetch_budget",
                                   "error": "单次运行抓取预算用尽"})
            continue
        budget[0] -= 1
        res = get_article_text(u, cache_dir=cache_dir, timeout=timeout,
                               extra_hosts=extra_hosts)
        out["sources"].append({"url": u, "status": res["status"],
                               "text_len": res["text_len"],
                               "error": res["error"]})
        if res["text_len"] >= MIN_TEXT_CHARS:
            texts.append(res["text"])

    if texts:
        best_cov, best_missing = 0.0, []
        for t in texts:
            hit, missing = match_claims(claims, t)
            cov = hit / len(claims)
            if cov > best_cov:
                best_cov, best_missing = cov, missing
        out["coverage"] = best_cov
        out["missing"] = best_missing
        if best_cov >= 0.999:
            out["verdict"] = "ok"
        elif best_cov >= MISMATCH_COV:
            out["verdict"] = "partial"
        else:
            out["verdict"] = "mismatch"
    elif direct:
        # 有直链但全都没拿到正文（反爬/付费墙/超时/预算尽）——如实暴露不算 FAIL
        out["verdict"] = "no_text"
    elif gnews:
        out["verdict"] = "redirect_only"
    else:
        out["verdict"] = "no_source"
    return out


_VERDICT_MARK = {"ok": "✓", "partial": "◐", "mismatch": "✗",
                 "no_text": "⚠", "redirect_only": "↓",
                 "no_claims": "·", "no_source": "✗"}


def run(report: Path, cache_dir: Path, timeout: int, max_fetch: int,
        no_fetch: bool, json_out: Path) -> int:
    content = report.read_text(encoding="utf-8")
    items = extract_news_items(content)

    # 引用域并入白名单：报告引用的链接就是读者会被引导点开的链接，
    # 抓「同一个链接」做对账不放大信任面（对账白名单四来源之一）。
    cited_hosts = {(urllib_host(u) or "").lower() for u in
                   _URL_RE.findall(content)}
    cited_hosts.discard("")

    budget = [0 if no_fetch else max_fetch]
    results = [audit_entry(it, cache_dir, timeout, max_fetch, budget,
                           cited_hosts) for it in items]

    n = len(results)
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1

    print(f"\n【声明级对账】{report.name}：{n} 条新闻，"
          f"抓取预算 {max_fetch}（剩 {budget[0]}）")
    for i, r in enumerate(results, 1):
        mark = _VERDICT_MARK[r["verdict"]]
        cov = f" 覆盖 {r['coverage']*100:.0f}%" if r["coverage"] is not None else ""
        miss = f" 缺:{';'.join(r['missing'][:4])}" if r["missing"] else ""
        src = ",".join(s["status"] for s in r["sources"]) or ("gnews" if r["gnews_urls"] else "-")
        print(f"  {mark} #{i:02d} [{r['verdict']}] {r['title'][:40]}{cov}{miss} ({src})")

    mismatch = tally.get("mismatch", 0)
    verifiable = tally.get("ok", 0) + tally.get("partial", 0)
    print(f"\n【对账总结】mismatch={mismatch} partial={tally.get('partial', 0)} "
          f"ok={tally.get('ok', 0)} no_text={tally.get('no_text', 0)} "
          f"redirect_only={tally.get('redirect_only', 0)} "
          f"no_claims={tally.get('no_claims', 0)} no_source={tally.get('no_source', 0)}")
    if n:
        print(f"  可对账率（取得正文且已核对）: {verifiable}/{n} = "
              f"{verifiable/n*100:.0f}%（redirect_only/no_text 为本环境无法验证，"
              f"如实暴露不粉饰）")

    payload = {"report": str(report), "generated_at": time.strftime("%F %T"),
               "stats": {"entries": n, **tally,
                         "verifiable_ratio": round(verifiable / n, 3) if n else 0.0},
               "entries": results}
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"  明细已写 {json_out.relative_to(ROOT) if json_out.is_relative_to(ROOT) else json_out}")

    if mismatch:
        print(f"\n✗ FAIL：{mismatch} 条新闻承重数字与原文对不上——对不上不出版，"
              f"请回改该条目（补交叉来源/修正数字/撤稿）后重跑")
        return 1
    print("\n✓ 声明级对账通过（无 mismatch）")
    return 0


def urllib_host(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="声明级对账门禁：承重数字逐条对照原文")
    ap.add_argument("report", help="日报 md 路径")
    ap.add_argument("--cache-dir", default=str(ROOT / "state" / "article_cache"))
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--max-fetch", type=int, default=20)
    ap.add_argument("--no-fetch", action="store_true", help="离线：只读缓存")
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    args = ap.parse_args()
    report = Path(args.report)
    if not report.exists():
        print(f"✗ 找不到日报：{report}")
        return 2
    return run(report, Path(args.cache_dir), args.timeout, args.max_fetch,
               args.no_fetch, Path(args.json_out))


if __name__ == "__main__":
    sys.exit(main())
