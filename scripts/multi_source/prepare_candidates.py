#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.prepare_candidates — 一键生成日报候选池（迭代3 新增 · 2026-08-15）。

把「online 采集 → 清洗 → 融合 → 选择性纳入门禁」串成一条命令，
供日报生成 Step 2 在搜索前调用：先看机器采集 + 门禁提纯出的候选池，
命中即优先采用（天然 A/B 级来源 + 已交叉验证），池内不足再走四层搜索。

设计要点：
  - **全程不落盘 multi_source/data/**（该目录是回归基线，跑 online 会覆盖
    致测试挂 → 中间产物全走内存/临时目录，只输出 state/gate_report.json）
  - fail-soft：任一环节失败 → 输出空候选 + 明确错误，绝不阻塞日报生成
  - 幂等：重复运行只覆盖当日 gate_report.json

输出：
  - state/gate_report.json  —— 结构化候选池（candidates 字段 + 拒绝原因分布）
  - 控制台摘要（候选条数 / 按环节分布 / 拒绝原因）

CLI：python scripts/multi_source/prepare_candidates.py
     [--conf-min 60] [--top-n 24] [--max-per-segment 6]
     [--aihot-queries "半导体,芯片,存储,光刻"] [--aihot-limit 6]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# 模块级导入（2026-08-15）：脚本目录会自动进入 sys.path[0]（CLI 直跑），
# 测试也已在 conftest/用例中 insert 该目录 —— 模块级 import 让
# collector 等成为模块属性，便于 monkeypatch 与复用。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import collector  # noqa: E402
import cleaner  # noqa: E402
import fusion  # noqa: E402
import gate as gate_mod  # noqa: E402
import article_fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / "state"
DEFAULT_OUT = STATE_DIR / "gate_report.json"


def enrich_top_candidates(report: dict, top_n: int = 8, timeout: int = 10,
                          cache_dir: Path | None = None) -> int:
    """v8 R2 源深水区：给 top 候选抓原文全文（body_full），让生成会话读原文
    而不是 160 字 RSS 摘要。fail-soft：单条失败原样跳过，绝不阻塞候选池。
    只抓直链文章级 URL（gnews 跳转链直接跳过）；返回成功条数。"""
    if top_n <= 0:
        return 0
    done = 0
    for c in report.get("candidates", []):
        if done >= top_n:
            break
        url = str(c.get("primary_source") or "").strip()
        if not url or article_fetch.is_gnews_link(url):
            continue
        res = article_fetch.get_article_text(
            url, cache_dir=cache_dir or article_fetch.ROOT / "state" / "article_cache",
            timeout=timeout, allow_fetch=True)
        if res.get("text"):
            # 截断到 4000 字符：够生成会话读原文，gate_report.json 不膨胀
            c["body_full"] = res["text"][:4000]
            c["body_full_len"] = res["text_len"]
            done += 1
    return done


def run(conf_min: float = 60.0, top_n: int = 24, max_per_segment: int = 6,
        aihot_queries: str = "半导体,芯片,存储,光刻", aihot_limit: int = 6,
        out_file: Path | None = None, enrich_top: int = 8) -> dict:
    """执行完整候选池流水线，返回 gate 报告 dict（fail-soft）。"""
    result: dict = {"ok": False, "error": None, "gate": None}
    try:
        scope = {
            "aihot_queries": [q.strip() for q in aihot_queries.split(",") if q.strip()],
            "aihot_limit": aihot_limit,
            "aihot_selected": True,  # v8 AIHOT 对标轮：精选池直采（无关键词交叉发现）
        }
        items = collector.collect(mode="online", scope=scope)
        cleaned = cleaner.normalize(items)
        # v8 P1-C 采中准入：无文章级 URL 不入池（G-1 前移，评审 P0-1 伪追溯断根）
        cleaned, admission_dropped = cleaner.admit_article_level(cleaned)
        events = fusion.fuse(cleaned)
        report = gate_mod.gate(events, conf_min=conf_min,
                               max_per_segment=max_per_segment, top_n=top_n)
        report["stats"]["admission_dropped"] = len(admission_dropped)
        if admission_dropped:
            report.setdefault("rejected_by_admission", []) .extend(
                {"title": c.get("title", "")[:80], "url": c.get("url", ""),
                 "reason": "homepage_or_empty_url"} for c in admission_dropped)
        # v8 R2：top 候选附原文全文（fail-soft，失败不影响候选池本身）
        report["stats"]["enriched_full_text"] = enrich_top_candidates(
            report, top_n=enrich_top)

        out = out_file or DEFAULT_OUT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        result.update(ok=True, gate=report, out=str(out))
    except Exception as e:  # fail-soft：任何异常输出空候选 + 错误信息
        result["error"] = str(e)
        empty = {
            "generated": None,
            "rules": {"conf_min": conf_min, "max_per_segment": max_per_segment, "top_n": top_n},
            "stats": {"raw": 0, "candidates": 0, "rejected": 0, "by_reason": {}},
            "candidates": [], "rejected": [],
            "error": str(e),
        }
        (out_file or DEFAULT_OUT).parent.mkdir(parents=True, exist_ok=True)
        (out_file or DEFAULT_OUT).write_text(
            json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8")
        result["gate"] = empty
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="一键生成日报候选池（online 采集→清洗→融合→门禁）")
    ap.add_argument("--conf-min", type=float, default=60.0)
    ap.add_argument("--top-n", type=int, default=24)
    ap.add_argument("--max-per-segment", type=int, default=6)
    ap.add_argument("--aihot-queries", default="半导体,芯片,存储,光刻")
    ap.add_argument("--aihot-limit", type=int, default=6)
    ap.add_argument("--enrich-top", type=int, default=8,
                    help="给前 N 条直链候选抓原文全文（0=关闭）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    result = run(args.conf_min, args.top_n, args.max_per_segment,
                 args.aihot_queries, args.aihot_limit, Path(args.out),
                 enrich_top=args.enrich_top)
    gate = result["gate"]

    if not result["ok"]:
        print(f"[prepare_candidates] 流水线失败（fail-soft，输出空候选）：{result['error']}")
        return 0

    s = gate["stats"]
    print(f"[prepare_candidates] online 采集 → 候选 {s['candidates']} 条 / 拒 {s['rejected']} 条"
          f"（raw {s['raw']}，准入拦首页级 {s.get('admission_dropped', 0)} 条）")
    if s["by_reason"]:
        print(f"[prepare_candidates] 拒绝原因: {s['by_reason']}")
    by_seg = Counter(c["segment"] for c in gate["candidates"])
    if by_seg:
        print(f"[prepare_candidates] 候选池按环节: {dict(by_seg)}")
    for c in gate["candidates"][:10]:
        flags = (" " + " ".join(c["flags"])) if c.get("flags") else ""
        print(f"  [{c['segment']}] conf={c['confidence']:.0f} {c['verification']}{flags}"
              f" | {c['title'][:52]}")
    try:
        rel = Path(result["out"]).relative_to(ROOT)
    except ValueError:
        rel = Path(result["out"])
    print(f"[prepare_candidates] 候选池已写回 {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
