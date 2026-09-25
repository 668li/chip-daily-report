#!/usr/bin/env python3
"""
forecast_tracker.py — 前瞻催化剂履约日志辅助（v5.10 方向1·预告→验证闭环）

用途（fail-soft，不阻塞日报生成）：
  - show-due      列出 history 中仍未 verified（或 event_date 已过期）的条目，供「前瞻兑现回顾」回看
  - add           向 state/forecast_log.json 追加一条本期新前瞻催化剂
  - verify        标记某条前瞻为已验证（verified/verdict/verified_note/verified_date）
  - summary       打印履约统计（✅/⚠️/❓ 计数）

数据：state/forecast_log.json（与 SKILL.md v5.10 约定一致）

v2 扩展（多剧本并行打分 · 见 evolution_plan M3/M5 强化）：
  - add 支持 --scenarios：为某条前瞻挂 2~3 个「互斥剧本」（真趋势/炒作/被绕开），
    每个剧本含 stance/statement/certainty，下期现实逐一打分。
  - verify 支持 --scenario-id：标记某个剧本已验证（而非整条事件的单一 verdict）。
  - 向后兼容：无 scenarios 的旧条目仍按顶层 event/verdict 工作，校准器双轨统计。
"""
import argparse
import json
import os
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LOG_PATH = os.path.join(REPO, "state", "forecast_log.json")


def _today() -> date:
    return date.today()


def _load() -> dict:
    if not os.path.exists(LOG_PATH):
        return {"schema_version": 1, "description": "", "entries": []}
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"schema_version": 1, "description": "", "entries": []}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def cmd_show_due(args) -> int:
    data = _load()
    today = _today()
    due = []
    for e in data.get("entries", []):
        if e.get("verified"):
            continue
        ev = e.get("event_date", "")
        try:
            overdue = _parse(ev) < today
        except Exception:
            overdue = False
        due.append((e, overdue))
    if not due:
        print("（无待回看条目）")
        return 0
    for e, overdue in due:
        flag = " [已过期未验证]" if overdue else ""
        print(f"- {e.get('id')} | {e.get('event_date')} | {e.get('segment')} | {e.get('importance')} | {e.get('certainty')} | {e.get('event')}{flag}")
    return 0


def _load_scenarios(arg: str | None):
    """从 --scenarios 解析剧本列表：支持 JSON 文件或内联 JSON 字符串。

    每项：{stance(真趋势/炒作/被绕开), statement, certainty?}
    fail-soft：解析失败返回 None（不挂剧本，不影响主条目写入）。
    """
    if not arg:
        return None
    raw = None
    p = arg.strip()
    if p.startswith("[") or p.startswith("{"):
        raw = p
    elif os.path.exists(p):
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            return None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    scen = obj if isinstance(obj, list) else [obj]
    out = []
    for s in scen:
        if not isinstance(s, dict) or not s.get("statement"):
            continue
        out.append(
            {
                "id": s.get("id"),
                "stance": s.get("stance", "真趋势"),
                "statement": s["statement"],
                "certainty": s.get("certainty", "中确定性"),
                "verified": False,
                "verified_date": None,
                "verdict": None,
                "verified_note": None,
            }
        )
    return out or None


def cmd_add(args) -> int:
    data = _load()
    scenarios = _load_scenarios(args.scenarios)
    if scenarios:
        for i, s in enumerate(scenarios, 1):
            if not s["id"]:
                s["id"] = f"{args.id}-s{i}"
    entry = {
        "id": args.id,
        "report_date": args.report_date,
        "event_date": args.event_date,
        "event": args.event,
        "segment": args.segment,
        "importance": args.importance,
        "certainty": args.certainty,
        "source": args.source,
        "when_judged": args.judged,
        "verified": False,
        "verified_date": None,
        "verdict": None,
        "verified_note": None,
        "scenarios": scenarios,  # 可能 None（向后兼容）
    }
    # 去重：同 id 覆盖
    entries = data.get("entries", [])
    for i, ex in enumerate(entries):
        if ex.get("id") == args.id:
            entries[i] = entry
            break
    else:
        entries.append(entry)
    data["entries"] = entries
    _save(data)
    tag = f" + {len(scenarios)} 个互斥剧本" if scenarios else ""
    print(f"已写入/更新前瞻条目：{args.id}{tag}")
    return 0


def cmd_verify(args) -> int:
    data = _load()
    found = False
    for e in data.get("entries", []):
        if e.get("id") != args.id:
            continue
        if args.scenario_id:
            # 验证某个互斥剧本
            for s in e.get("scenarios") or []:
                if s.get("id") == args.scenario_id:
                    s["verified"] = True
                    s["verified_date"] = args.date or _today().isoformat()
                    s["verdict"] = args.verdict
                    s["verified_note"] = args.note
                    found = True
                    print(f"已标记剧本验证：{args.scenario_id} -> {args.verdict}")
                    break
            else:
                print(f"未找到剧本：{args.scenario_id}（条目 {args.id}）", file=sys.stderr)
                return 1
        else:
            # 验证整条事件（旧行为）
            e["verified"] = True
            e["verified_date"] = args.date or _today().isoformat()
            e["verdict"] = args.verdict
            e["verified_note"] = args.note
            found = True
            print(f"已标记验证：{args.id} -> {args.verdict}")
        break
    if not found:
        print(f"未找到条目：{args.id}", file=sys.stderr)
        return 1
    _save(data)
    return 0


def cmd_summary(args) -> int:
    data = _load()
    entries = data.get("entries", [])
    done = [e for e in entries if e.get("verified")]
    pending = [e for e in entries if not e.get("verified")]
    cons = sum(1 for e in done if str(e.get("verdict", "")).startswith("一致"))
    warn = sum(1 for e in done if "偏差" in str(e.get("verdict", "")))
    ch = [e for e in entries if e.get("certainty") == "高确定性"]
    cm = [e for e in entries if e.get("certainty") == "中确定性"]
    cl = [e for e in entries if e.get("certainty") == "低确定性"]
    # 剧本维度
    scen_all = [s for e in entries for s in (e.get("scenarios") or [])]
    scen_done = [s for s in scen_all if s.get("verified")]
    print(f"总条目：{len(entries)} | 已验证：{len(done)}（✅一致 {cons} / ⚠️有偏差 {warn}）| 待回看：{len(pending)}")
    print(f"确定性分布：高 {len(ch)} / 中 {len(cm)} / 低 {len(cl)}")
    if scen_all:
        print(f"互斥剧本：共 {len(scen_all)} 个（已验证 {len(scen_done)}）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="前瞻催化剂履约日志辅助（v5.10）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("show-due", help="列出待回看条目")
    sp.set_defaults(func=cmd_show_due)

    sp = sub.add_parser("add", help="追加一条本期前瞻")
    sp.add_argument("--id", required=True)
    sp.add_argument("--report-date", required=True)
    sp.add_argument("--event-date", required=True)
    sp.add_argument("--event", required=True)
    sp.add_argument("--segment", required=True)
    sp.add_argument("--importance", required=True)
    sp.add_argument("--certainty", default="中确定性", help="确定性分级：高确定性/中确定性/低确定性")
    sp.add_argument("--source", required=True)
    sp.add_argument("--judged", required=True)
    sp.add_argument("--scenarios", default=None,
                    help="互斥剧本：JSON 文件或内联 JSON（[{stance,statement,certainty}]）；"
                         "stance ∈ 真趋势/炒作/被绕开")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("verify", help="标记条目/剧本已验证")
    sp.add_argument("--id", required=True)
    sp.add_argument("--scenario-id", default=None, help="指定则验证该互斥剧本而非整条事件")
    sp.add_argument("--verdict", required=True)
    sp.add_argument("--note", required=True)
    sp.add_argument("--date", default=None)
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("summary", help="履约统计")
    sp.set_defaults(func=cmd_summary)

    args = p.parse_args()
    try:
        return args.func(args)
    except Exception as ex:
        print(f"[forecast_tracker] fail-soft: {ex}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
