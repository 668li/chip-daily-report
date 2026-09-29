#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_source.ledger — 采集账本（v9 数据系统轮 · 2026-09-29）。

AIHOT 扩接内化的机制落地（真差距①+②，拍板解冻范围=数据供给层，其余冻结不变）：
  ① 首采限量+旧文归档 —— 源第一次拉到货之前（账本无 found>0 记录），丢弃
     published 早于 max_age_days 的条目并按 cap 封顶（AIHOT initialBackfillLimit
     同款语义：first-import 不进「今天」），防第 2 期 capex 旧闻事故（7/15 法说
     9/26 转引被当新鲜条）在采集层复发——G2-72h 只守报告层，这里守源头。
  ② 产出账本 —— 每次运行按 source_id 记录 found/kept/首采标记，滚动 90 天；
     per_day 产出速率（排除首采记录，AIHOT 排除 backfill 同口径）驱动 AIHOT
     频率自适应公式测算 clamp(1440/(perDay*3), 15, 60)。当前管线是日批单频，
     公式输出为「降级审查建议」而非自动调频——多频调度出现之前，建议由人消费
     （扩源手册第⑧步观察期 / ledger --status）。

设计纪律：
  * 状态在 state/collector_ledger.json（tracked，运行更新属预期 git 噪音，
    与 discovered_sources.json 同口径）
  * 测试零污染：所有函数带 path 参数，测试一律传 tmp_path；
    prepare_candidates.run(ledger_path=None) 默认**关**账本（生产 main()
    显式开），monkeypatch collect 的存量测试零影响
  * fail-soft：账本损坏/不可写 → 降级为「不守卫不记录」，绝不阻塞采集
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LEDGER = ROOT / "state" / "collector_ledger.json"

FIRST_IMPORT_CAP = 30             # 首采条数封顶（AIHOT initialBackfillLimit 默认 30）
FIRST_IMPORT_MAX_AGE_DAYS = 30    # 首采旧文窗：超龄按原文时间「归档」=不采集
KEEP_DAYS = 90                    # 账本滚动窗口（天）
INTERVAL_MIN, INTERVAL_MAX = 15, 60   # AIHOT 免费源频率夹持（分钟）


# ============================================================
# 底层读写（fail-soft）
# ============================================================
def _load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:
        pass
    return {"version": 1, "runs": []}


def _save(path: Path, data: dict) -> bool:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _parse_published(value) -> date | None:
    """RawItem.published 契约是 YYYY-MM-DD；空/不可解析 → None（无法判龄）。"""
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ============================================================
# ① 首采限量守卫
# ============================================================
def is_first_import(path: Path, source_id: str) -> bool:
    """账本无该源 found>0 的记录 → 首采（AIHOT cursor.initializedAt 语义：
    拉到过货才算初始化）。账本损坏/缺失 → True（守卫生效，安全侧）。"""
    for run in _load(path).get("runs", []):
        if run.get("source_id") == source_id and run.get("found", 0) > 0:
            return False
    return True


def first_import_guard(path: Path, source_id: str, items: list, *,
                       cap: int = FIRST_IMPORT_CAP,
                       max_age_days: int = FIRST_IMPORT_MAX_AGE_DAYS,
                       today: date | None = None) -> tuple[list, dict]:
    """首采守卫：超龄条目丢弃（按原文时间归档=不采集）+ 条数封顶。
    非首采原样返回。published 为空/不可解析 → 保留（无法判龄，交下游处置）。
    返回 (kept_items, stats)。"""
    found = len(items)
    if not is_first_import(path, source_id):
        return list(items), {"source_id": source_id, "first_import": False,
                             "found": found, "kept": found,
                             "dropped_old": 0, "capped": False}
    today = today or date.today()
    cutoff = today - timedelta(days=max_age_days)
    kept, dropped_old = [], 0
    for it in items:
        d = _parse_published(getattr(it, "published", ""))
        if d is not None and d < cutoff:
            dropped_old += 1
            continue
        kept.append(it)
    capped = len(kept) > cap
    kept = kept[:cap]
    return kept, {"source_id": source_id, "first_import": True,
                  "found": found, "kept": len(kept),
                  "dropped_old": dropped_old, "capped": capped}


# ============================================================
# ② 记账与产出速率
# ============================================================
def record_run(path: Path, source_id: str, *, found: int, kept: int,
               first_import: bool = False, dropped_old: int = 0,
               capped: bool = False, now: datetime | None = None) -> bool:
    """追加一条运行记录并滚动裁剪。写失败静默（返回 False），绝不抛出。"""
    now = now or datetime.now()
    data = _load(path)
    runs = data.setdefault("runs", [])
    runs.append({
        "date": now.strftime("%Y-%m-%d"),
        "ts": now.isoformat(timespec="seconds"),
        "source_id": source_id,
        "found": int(found), "kept": int(kept),
        "first_import": bool(first_import),
        "dropped_old": int(dropped_old), "capped": bool(capped),
    })
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    data["runs"] = [r for r in runs if str(r.get("date", "")) >= cutoff]
    return _save(path, data)


def per_day(path: Path, source_id: str, *, days: int = 7,
            now: datetime | None = None) -> float:
    """近 N 天日均产出（排除首采记录，AIHOT 排除 backfill 同口径）。"""
    now = now or datetime.now()
    window_start = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    kept = sum(r.get("kept", 0) for r in _load(path).get("runs", [])
               if r.get("source_id") == source_id and not r.get("first_import")
               and str(r.get("date", "")) >= window_start)
    return kept / float(days)


def suggest(path: Path, source_id: str, *, days: int = 7,
            now: datetime | None = None) -> dict:
    """AIHOT 频率自适应公式测算（建议输出，不自动调频——日批单频下由人消费）。"""
    mine = [r for r in _load(path).get("runs", [])
            if r.get("source_id") == source_id]
    per = per_day(path, source_id, days=days, now=now)
    out = {"source_id": source_id, "per_day": round(per, 2),
           "target_interval_minutes": None, "verdict": ""}
    if not mine:
        out["verdict"] = "无记录（新源或未接线）"
        return out
    if not any(not r.get("first_import") for r in mine):
        # 只有首采记录：速率按设计排除首采，还不能下结论
        out["verdict"] = "首采期——产出速率待非首采运行计入"
        return out
    if per <= 0:
        out["verdict"] = "静默/失败——列入降级审查（手册第②⑧步）"
        return out
    target = min(INTERVAL_MAX, max(INTERVAL_MIN, round(1440.0 / (per * 3))))
    out["target_interval_minutes"] = target
    out["verdict"] = "低产——观察期" if per < 0.5 else "正常"
    return out


# ============================================================
# 管线接线助手 + 报表
# ============================================================
def collect_guard(items: list, path: Path, *,
                  today: date | None = None) -> tuple[list, dict]:
    """按 source_id 分组套首采守卫并逐源记账。守卫只丢弃、永不重排——
    输出保持传入的全局顺序。返回 (kept_items, summary)。
    prepare_candidates 在 ledger_path 开启时调用。"""
    by_sid: dict[str, list] = {}
    order: list[str] = []
    for idx, it in enumerate(items):
        sid = str(getattr(it, "source_id", "?"))
        if sid not in by_sid:
            by_sid[sid] = []
            order.append(sid)
        by_sid[sid].append((idx, it))
    kept_pairs: list[tuple[int, object]] = []
    summary = {"sources": 0, "first_import": [], "dropped_old": 0, "capped": []}
    for sid in order:
        group = [it for _, it in by_sid[sid]]
        kept, stats = first_import_guard(path, sid, group, today=today)
        idset = {id(it) for it in kept}   # 守卫返回的是同对象子集，按身份映射回原位
        kept_pairs.extend((idx, it) for idx, it in by_sid[sid] if id(it) in idset)
        record_run(path, sid, found=stats["found"], kept=stats["kept"],
                   first_import=stats["first_import"],
                   dropped_old=stats["dropped_old"], capped=stats["capped"],
                   now=datetime.combine(today, datetime.min.time()) if today else None)
        summary["sources"] += 1
        if stats["first_import"]:
            summary["first_import"].append(sid)
        summary["dropped_old"] += stats["dropped_old"]
        if stats["capped"]:
            summary["capped"].append(sid)
    kept_pairs.sort(key=lambda t: t[0])
    return [it for _, it in kept_pairs], summary


def status_report(path: Path, *, now: datetime | None = None) -> list[dict]:
    """逐源聚合：运行次数 / 最近记录 / per_day / 公式建议。按 source_id 排序。"""
    runs: dict[str, list] = {}
    for r in _load(path).get("runs", []):
        runs.setdefault(str(r.get("source_id", "?")), []).append(r)
    out = []
    for sid in sorted(runs):
        mine = runs[sid]
        last = mine[-1]
        sug = suggest(path, sid, now=now)
        out.append({"source_id": sid, "runs": len(mine),
                    "last_date": str(last.get("date", "")),
                    "last_kept": last.get("kept", 0),
                    "per_day": sug["per_day"],
                    "target_interval_minutes": sug["target_interval_minutes"],
                    "verdict": sug["verdict"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="采集账本：首采限量/产出速率/自适应建议")
    ap.add_argument("--status", action="store_true", help="打印逐源状态表")
    ap.add_argument("--reset", metavar="SOURCE_ID", help="清除某源全部记录（开发用）")
    ap.add_argument("--path", default=str(DEFAULT_LEDGER))
    args = ap.parse_args()
    path = Path(args.path)

    if args.reset:
        data = _load(path)
        before = len(data.get("runs", []))
        data["runs"] = [r for r in data.get("runs", [])
                        if r.get("source_id") != args.reset]
        _save(path, data)
        print(f"[ledger] {args.reset}: 清除 {before - len(data['runs'])} 条记录")
        return 0

    rows = status_report(path)
    if not rows:
        print(f"[ledger] 账本为空（{path}）——首次 prepare_candidates 后生成")
        return 0
    print(f"[ledger] 逐源状态（账本 {path.name}，滚动 {KEEP_DAYS} 天）：")
    for r in rows:
        tgt = r["target_interval_minutes"]
        print(f"  {r['source_id']:<22} runs={r['runs']:<3} last={r['last_date']}"
              f" kept={r['last_kept']:<3} per_day={r['per_day']:<6}"
              f" 建议间隔={tgt if tgt else '—'}分钟  {r['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
