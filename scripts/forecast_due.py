#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forecast_due — 兑现回顾到期对账器（v8 护城河冲刺加时①，2026-09-27）。

定位：推演可问责的复利引擎。扫 `state/forecast_log.json`，把「到期该对账」
的推演按四态口径点名——心跳会话每天先跑它，逾期未判直接非零退出响铃，
杜绝"到期无人记得"的静默烂账。

状态判定（verified=False 的条目才需要判）：
  OVERDUE  event_date < 今天 且未判定（逾期 N 天）
  DUE      event_date == 今天
  UPCOMING event_date 在未来 7 天内
  LATER    更远；UNPARSED  event_date 无法解析为日期（如"2026-Q4（窗口待定）"）
verified=True 的条目只计数，不打扰。

退出码：0=无逾期未判；1=存在逾期未判（响铃）；2=日志不可读。
用法：
  python scripts/forecast_due.py            # 点名 + 响铃判定
  python scripts/forecast_due.py --md       # 额外输出可贴进日报"兑现回顾"的 md 草稿
  python scripts/forecast_due.py --log path # 指定日志文件（默认 state/forecast_log.json）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = ROOT / "state" / "forecast_log.json"
DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _parse_date(s: str) -> date | None:
    m = DATE_RE.search(s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def scan(entries: list[dict], today: date) -> dict[str, list[dict]]:
    """把条目分拣进 OVERDUE/DUE/UPCOMING/LATER/UNPARSED/JUDGED 六桶。"""
    buckets: dict[str, list[dict]] = {k: [] for k in
                                      ("OVERDUE", "DUE", "UPCOMING", "LATER", "UNPARSED", "JUDGED")}
    for e in entries:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        if e.get("verified"):
            buckets["JUDGED"].append(e)
            continue
        d = _parse_date(str(e.get("event_date", "")))
        if d is None:
            buckets["UNPARSED"].append(e)
        elif d < today:
            e = {**e, "_overdue_days": (today - d).days}
            buckets["OVERDUE"].append(e)
        elif d == today:
            buckets["DUE"].append(e)
        elif (d - today).days <= 7:
            buckets["UPCOMING"].append(e)
        else:
            buckets["LATER"].append(e)
    for k in buckets:
        buckets[k].sort(key=lambda e: str(e.get("event_date", "")))
    return buckets


def render_md(buckets: dict[str, list[dict]], today: date) -> str:
    """输出可贴进日报"兑现回顾"的点名草稿（四态判定仍由人/会话写）。"""
    lines = [f"### 到期对账点名（截至 {today.isoformat()}）", ""]
    for e in buckets["OVERDUE"]:
        lines.append(f"- ⏳ **{e['id']}** 逾期 {e['_overdue_days']} 天（原定 {e.get('event_date')}）：{e.get('event', '')[:60]}")
    for e in buckets["DUE"]:
        lines.append(f"- 🔔 **{e['id']}** 今日到期：{e.get('event', '')[:60]}")
    for e in buckets["UPCOMING"]:
        d = _parse_date(str(e.get("event_date", "")))
        left = (d - today).days if d else "?"
        lines.append(f"- 📅 **{e['id']}** {left} 天后到期（{e.get('event_date')}）：{e.get('event', '')[:60]}")
    n_unparsed = len(buckets["UNPARSED"])
    if n_unparsed:
        lines.append(f"- ⚠ 另有 {n_unparsed} 条 event_date 无法解析（如'Q4（窗口待定）'），保留人工台账")
    lines.append("")
    lines.append(f"> 判定纪律：命中/偏差/打脸/逾期四态，附可公开核查的证据链接；未取得数据不结案。")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="推演到期对账点名器（逾期未判即响铃）")
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--md", action="store_true", help="输出可贴进日报的 md 草稿")
    args = ap.parse_args()

    try:
        log = json.loads(Path(args.log).read_text(encoding="utf-8"))
        entries = log.get("entries", []) if isinstance(log, dict) else []
    except Exception as e:  # noqa: BLE001
        print(f"[forecast_due] ✗ 日志不可读: {e}")
        return 2

    today = date.today()
    buckets = scan(entries, today)

    print(f"[forecast_due] 推演台账 {len(entries)} 条：判定 {len(buckets['JUDGED'])} / "
          f"逾期未判 {len(buckets['OVERDUE'])} / 今日到期 {len(buckets['DUE'])} / "
          f"7 天内 {len(buckets['UPCOMING'])} / 更远 {len(buckets['LATER'])} / 日期不可解析 {len(buckets['UNPARSED'])}")
    for e in buckets["OVERDUE"]:
        print(f"  ⏳ OVERDUE {e['id']}（逾期 {e['_overdue_days']} 天）: {e.get('event', '')[:56]}")
    for e in buckets["DUE"]:
        print(f"  🔔 DUE {e['id']}: {e.get('event', '')[:56]}")
    for e in buckets["UPCOMING"]:
        print(f"  📅 UPCOMING {e['id']}（{e.get('event_date')}）: {e.get('event', '')[:56]}")

    if args.md:
        print("\n---- 兑现回顾草稿 ----")
        print(render_md(buckets, today))

    if buckets["OVERDUE"]:
        print(f"[forecast_due] ✗ {len(buckets['OVERDUE'])} 条逾期未判——兑现回顾必须先处理，再出版日报")
        return 1
    print("[forecast_due] ✓ 无逾期未判")
    return 0


if __name__ == "__main__":
    sys.exit(main())
