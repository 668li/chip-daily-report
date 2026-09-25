#!/usr/bin/env python3
"""evolution_loop.py — M6 自我科研循环（终极里程碑）。

设计目标（见 references/evolution_plan.md M6）：
  把 M3（预判校准）+ M4（规则自生长）+ M5（复盘反写）串成一条全自动链：
    采集 feedback → 提炼规律 → 反写 rubric/system → 验证改进。
  每跑一次记一笔到 state/evolution_loop.json（保留最近 50 次，审计日志），并维护
  「连续无人工调 rubric 期数」计数器——当该计数器达到里程碑（默认 30），即视为系统
  「会自己长记性」（M6 达标）。同一自然日内重复运行不重复计数（防虚增）。

执行（全部 fail-soft，单步失败不阻断整链）：
  1. forecast_calibrator.py --apply   → M3 校准建议（state/forecast_calibration.json）
  2. rule_growth.py --apply           → M4 规则频率 + 自生长建议（state/rule_growth.json）
  3. m5_rewrite_skill.py --apply      → M5 反写 SKILL.md 注意点段
  4. 汇总写入 state/evolution_loop.json（含里程碑计数）

用法：python scripts/evolution_loop.py [--dry]   （--dry 只跑前两步、不反写 SKILL）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
OUT = STATE / "evolution_loop.json"
MILESTONE = 30  # 连续无人工调 rubric 期数里程碑


def _run(script: str, *extra) -> dict:
    p = ROOT / "scripts" / script
    try:
        r = subprocess.run([sys.executable, str(p), *extra],
                           capture_output=True, text=True, timeout=300)
        return {"script": script, "rc": r.returncode,
                "out": (r.stdout or "")[-600:], "err": (r.stderr or "")[:300]}
    except Exception as ex:
        return {"script": script, "rc": -1, "out": "", "err": str(ex)}


def load_history() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"runs": [], "auto_streak": 0, "milestone": MILESTONE}


def main() -> int:
    ap = argparse.ArgumentParser(description="M6 自我科研循环：M3→M4→M5 串联")
    ap.add_argument("--dry", action="store_true",
                    help="只跑 M3+M4（采集+规律），不反写 SKILL（不推进里程碑）")
    args = ap.parse_args()

    hist = load_history()
    today = date.today().isoformat()

    steps = [_run("forecast_calibrator.py", "--apply"),
             _run("rule_growth.py", "--apply")]
    if not args.dry:
        steps.append(_run("m5_rewrite_skill.py", "--apply"))

    failed = [s for s in steps if s["rc"] != 0]
    auto_ok = (not failed) and (not args.dry)

    # 里程碑计数：仅「全绿 + 非 dry」才推进；且当天已出现过 full success 则不重复 +1
    # （同日重跑 / dry→full 混跑都不会虚增或回退 streak）
    last_full = None
    for r in reversed(hist.get("runs", [])):
        if not r.get("failed") and any(s["script"] == "m5_rewrite_skill.py"
                                       for s in r.get("steps", [])):
            last_full = r
            break
    already_advanced_today = last_full is not None and last_full.get("date") == today

    prev_streak = hist.get("auto_streak", 0)
    if auto_ok and not already_advanced_today:
        prev_streak += 1
    # 自动失败不倒扣；仅人工改 rubric 时由人工把 auto_streak 归零（见 SKILL.md 注意点段说明）
    hist["auto_streak"] = prev_streak

    run_rec = {
        "date": today,
        "steps": steps,
        "failed": [s["script"] for s in failed],
        "auto_streak": prev_streak,
        "milestone_reached": prev_streak >= hist.get("milestone", MILESTONE),
    }
    hist["runs"].append(run_rec)
    hist["runs"] = hist["runs"][-50:]  # 保留最近 50 次（审计日志）
    hist["milestone"] = hist.get("milestone", MILESTONE)
    OUT.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[M6] 自我科研循环 {today}：{'全部成功' if not failed else f'{len(failed)} 步失败'}")
    for s in steps:
        mark = "✓" if s["rc"] == 0 else "✗"
        print(f"  {mark} {s['script']} (rc={s['rc']})")
    print(f"  自动进化连续期：{hist['auto_streak']} / 里程碑 {hist['milestone']}")
    if run_rec["milestone_reached"]:
        print("  🏁 已达 M6 里程碑：系统连续自进化，可视作「会自己长记性」")
    elif args.dry:
        print("  （--dry：未反写 SKILL，不推进里程碑）")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
