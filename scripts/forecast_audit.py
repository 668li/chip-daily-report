# -*- coding: utf-8 -*-
"""
前瞻催化剂履约审计（v5.13 · 预告→验证闭环 · 自我校准）

设计目的（重要）：
  本脚本不是为了"证明前瞻很准"，而是为了**主动暴露验证环节的自我欺骗**。
  历史教训：早期 verdict 只有"一致/有偏差"两类，导致 9 条已验证条目中 0 条"打脸"，
  实为验证过松 + 后见之明偏差（hindsight bias）+ 伪预测（只预测"事件会发生"）。

核心审计维度：
  A. 命中率    —— HIT / PARTIAL / MISS / PENDING / OVERDUE 分布
  B. 校准度    —— 确定性分级（高/中/低）是否真能区分命中率（分级无效则红旗）
  C. 时点偏差  —— 预估 event_date 与实际发生日的偏差（仅当 verified_note 含实际日期时可判）
  D. 验证滞后  —— verified_date - event_date，>7 天计红旗（闭环失效）
  E. 场景覆盖  —— 有多少前瞻写了互斥情景（三选一），覆盖率低则判断不可证伪
  F. 伪预测率  —— when_judged 是否含可证伪量化阈值（数字/%/条件句），否则是"事件是否发生"的伪预测

红旗（RED FLAG）：
  R1 零打脸    —— 已验证 >= 5 且 MISS == 0
  R2 伪预测    —— 可证伪判断占比 < 50%
  R3 逾期未验  —— 事件日已过 grace_days 仍未 verified
  R4 验证滞后  —— 滞后 > 7 天
  R5 分级失效  —— 高确定性与中/低确定性命中率无差异（差值 < 10pp）
  R6 场景缺失  —— 高重要度前瞻未写互斥情景

用法：
  python scripts/forecast_audit.py [--log state/forecast_log.json] [--out delivery/forecast_audit.md] [--today 2026-09-10] [--grace-days 3]

退出码：始终 0（审计不阻断交付，但红旗必须写进报告并人工/下期跟进）
"""
import json
import re
import argparse
import os
from datetime import date, datetime

HIT_KW = ("一致", "兑现", "应验", "命中")
PARTIAL_KW = ("有偏差", "部分", "方向正确", "偏弱")
MISS_KW = ("失败", "相反", "打脸", "证伪", "背离", "未成真", "打脸")
UNRESOLVED_KW = ("待数据", "待确认", "数据未取得")

# 可证伪判断的信号词：出现这些 + 数字 = 可被客观证伪的预测
FALSIFIABLE_PAT = re.compile(
    r"(\d+(\.\d+)?\s*%|\d+(\.\d+)?\s*(亿|万|万亿|美元|片|颗|层))"
)
FALSIFIABLE_CTX = re.compile(r"(若|如|维持|跌破|超过|低于|高于|增速|占比|指引|环比|同比|阈值)")


def parse_date(s):
    """解析 YYYY-MM-DD；非标准（如 2026-Q4）返回 None（视为不可解析/待定）。"""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def norm_verdict(v):
    if not v:
        return "PENDING"
    for k in MISS_KW:
        if k in v:
            return "MISS"
    for k in PARTIAL_KW:
        if k in v:
            return "PARTIAL"
    for k in UNRESOLVED_KW:
        if k in v:
            return "UNRESOLVED"
    for k in HIT_KW:
        if k in v:
            return "HIT"
    return "OTHER"


def is_falsifiable(entry):
    """判断前瞻是否含可证伪的量化判断（而非仅'事件会发生'的伪预测）。"""
    text = (entry.get("when_judged") or "") + " " + (entry.get("event") or "")
    has_num = bool(FALSIFIABLE_PAT.search(text))
    has_ctx = bool(FALSIFIABLE_CTX.search(text))
    return has_num and has_ctx


def audit(log_path, today, grace_days):
    with open(log_path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])

    rows = []
    for e in entries:
        ev_date = parse_date(e.get("event_date"))
        vf_date = parse_date(e.get("verified_date"))
        verdict = e.get("verdict")
        verified = bool(e.get("verified"))
        state = norm_verdict(verdict)

        # 逾期判定：未验证 且 事件日 + grace_days < today
        overdue = False
        if not verified and ev_date and (today - ev_date).days > grace_days:
            overdue = True
            state = "OVERDUE"

        lag = None
        if verified and ev_date and vf_date:
            lag = (vf_date - ev_date).days

        rows.append({
            "id": e.get("id"),
            "event": e.get("event"),
            "report_date": e.get("report_date"),
            "event_date": e.get("event_date"),
            "certainty": e.get("certainty") or "未标注",
            "importance": e.get("importance") or "未标注",
            "verified": verified,
            "state": state,
            "verdict": verdict,
            "lag_days": lag,
            "overdue": overdue,
            "falsifiable": is_falsifiable(e),
            "has_scenarios": bool(e.get("scenarios")),
        })

    # ---- 统计 ----
    verified_rows = [r for r in rows if r["verified"]]
    total = len(rows)
    n_verified = len(verified_rows)

    def cnt(st):
        return sum(1 for r in verified_rows if r["state"] == st)

    hit, partial, miss, other = cnt("HIT"), cnt("PARTIAL"), cnt("MISS"), cnt("OTHER")
    hit_rate = (hit / n_verified * 100) if n_verified else 0.0

    n_overdue = sum(1 for r in rows if r["state"] == "OVERDUE")
    n_pending = sum(1 for r in rows if r["state"] == "PENDING")
    n_falsifiable = sum(1 for r in rows if r["falsifiable"])
    falsifiable_rate = (n_falsifiable / total * 100) if total else 0.0
    lags = [r["lag_days"] for r in verified_rows if r["lag_days"] is not None]
    n_late = sum(1 for d in lags if d > 7)
    n_scen = sum(1 for r in rows if r["has_scenarios"])
    scen_rate = (n_scen / total * 100) if total else 0.0

    # 校准度：按 certainty 分组算命中率
    calib = {}
    for c in ("高确定性", "中确定性", "低确定性", "未标注"):
        grp = [r for r in verified_rows if r["certainty"] == c]
        if grp:
            h = sum(1 for r in grp if r["state"] == "HIT")
            calib[c] = {"n": len(grp), "hit": h, "rate": h / len(grp) * 100}
        else:
            calib[c] = {"n": 0, "hit": 0, "rate": None}

    # ---- 红旗 ----
    flags = []
    if n_verified >= 5 and miss == 0:
        flags.append(
            "R1 零打脸：已验证 %d 条但 MISS=0。真实预测不可能百分百命中，"
            "说明存在验证过松 / 后见之明偏差 / verdict 枚举缺少'失败'类。"
            "必须允许并鼓励记录打脸，否则闭环失去校准价值。" % n_verified
        )
    if falsifiable_rate < 50:
        flags.append(
            "R2 伪预测率过高：仅 %.0f%% 的前瞻含可证伪量化阈值。多数前瞻只在预测"
            "'事件会不会发生'（发布会/财报日必然发生），命中率虚高且无信息量。"
            "前瞻必须写明数字/阈值/条件句。" % falsifiable_rate
        )
    if n_overdue:
        ids = ", ".join(r["id"] for r in rows if r["state"] == "OVERDUE")
        flags.append(
            "R3 逾期未验证：%d 条事件日已过 %d 天宽限仍未验证（%s）。"
            "逾期项必须下期优先补验或显式作废，不得无限顺延。" % (n_overdue, grace_days, ids)
        )
    if n_late:
        flags.append(
            "R4 验证滞后：%d 条验证日晚于事件日 7 天以上（最大 %d 天）。"
            "滞后过久导致闭环失去时效价值，应在事件日 +3 天内验证。" % (n_late, max(lags))
        )
    hi = calib.get("高确定性", {}).get("rate")
    mid = calib.get("中确定性", {}).get("rate")
    if hi is not None and mid is not None and abs(hi - mid) < 10:
        flags.append(
            "R5 确定性分级失效：高确定性命中率 %.0f%% vs 中确定性 %.0f%%，差异 <10pp，"
            "说明 certainty 分级没有实际区分能力，需重新定义分级标准。" % (hi, mid)
        )
    n_hi_no_scen = sum(
        1 for r in rows
        if r["importance"] == "高" and not r["has_scenarios"]
    )
    if n_hi_no_scen:
        flags.append(
            "R6 高重要度缺情景：%d 条高重要度前瞻未写互斥情景（真趋势/炒作/被绕开）。"
            "无情景=无法判断方向对不对，只能判断事件发没发生。" % n_hi_no_scen
        )

    return {
        "total": total, "n_verified": n_verified, "hit": hit, "partial": partial,
        "miss": miss, "other": other, "hit_rate": hit_rate,
        "n_pending": n_pending, "n_overdue": n_overdue,
        "falsifiable_rate": falsifiable_rate, "scen_rate": scen_rate,
        "max_lag": max(lags) if lags else None, "n_late": n_late,
        "calib": calib, "flags": flags, "rows": rows,
    }


def render_md(res, log_path, today, grace_days):
    L = []
    A = L.append
    A("# 前瞻催化剂履约审计（预告→验证闭环 · 自我校准）\n")
    A("> 审计日期: %s | 日志: `%s` | 逾期宽限: %d 天\n" % (today, log_path, grace_days))
    A("> **本审计的目的不是证明前瞻很准，而是主动暴露验证环节的自我欺骗。**\n")

    A("## 一、总览\n")
    A("| 指标 | 数值 |")
    A("|------|------|")
    A("| 登记前瞻总数 | %d |" % res["total"])
    A("| 已验证 | %d |" % res["n_verified"])
    A("| 待验证（事件未到） | %d |" % res["n_pending"])
    A("| **逾期未验证** | **%d** |" % res["n_overdue"])
    A("| 命中 HIT | %d |" % res["hit"])
    A("| 部分命中 PARTIAL | %d |" % res["partial"])
    A("| **打脸 MISS** | **%d** |" % res["miss"])
    A("| 命中率（HIT/已验证） | %.1f%% |" % res["hit_rate"])
    A("| 可证伪判断占比 | %.1f%% |" % res["falsifiable_rate"])
    A("| 互斥情景覆盖率 | %.1f%% |" % res["scen_rate"])
    A("| 最大验证滞后 | %s |" % (("%d 天" % res["max_lag"]) if res["max_lag"] is not None else "-"))
    A("")

    A("## 二、校准度（确定性分级是否真能区分命中率）\n")
    A("| 确定性 | 已验证数 | 命中 | 命中率 |")
    A("|--------|----------|------|--------|")
    for c in ("高确定性", "中确定性", "低确定性", "未标注"):
        v = res["calib"].get(c)
        if not v or v["n"] == 0:
            continue
        A("| %s | %d | %d | %.1f%% |" % (c, v["n"], v["hit"], v["rate"]))
    A("")

    A("## 三、红旗（必须下期跟进，不得无视）\n")
    if res["flags"]:
        for i, f in enumerate(res["flags"], 1):
            A("%d. **%s**\n" % (i, f))
    else:
        A("本期无红旗。\n")
    A("")

    A("## 四、逐条明细\n")
    A("| ID | 事件 | 预估日 | 确定性 | 状态 | 结论 | 滞后 | 可证伪 |")
    A("|----|------|--------|--------|------|------|------|--------|")
    for r in res["rows"]:
        A("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"],
            (r["event"] or "")[:28],
            r["event_date"] or "-",
            r["certainty"],
            r["state"],
            (r["verdict"] or "-")[:20],
            ("%d天" % r["lag_days"]) if r["lag_days"] is not None else "-",
            "是" if r["falsifiable"] else "**否**",
        ))
    A("")
    A("---")
    A("*由 scripts/forecast_audit.py 自动生成。审计结论须写入当期日报的「前瞻兑现回顾」，"
      "红旗项须在下期优先处理。*")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="state/forecast_log.json")
    ap.add_argument("--out", default="delivery/forecast_audit.md")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD，默认今天")
    ap.add_argument("--grace-days", type=int, default=3)
    args = ap.parse_args()

    today = parse_date(args.today) or date.today()
    res = audit(args.log, today, args.grace_days)

    md = render_md(res, args.log, today, args.grace_days)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    print("[forecast_audit] 已写入 %s" % args.out)
    print("  总数=%d 已验证=%d 命中=%d 部分=%d 打脸=%d 逾期=%d 命中率=%.1f%%" % (
        res["total"], res["n_verified"], res["hit"], res["partial"],
        res["miss"], res["n_overdue"], res["hit_rate"]))
    print("  可证伪判断占比=%.1f%% 情景覆盖=%.1f%% 最大滞后=%s" % (
        res["falsifiable_rate"], res["scen_rate"], res["max_lag"]))
    if res["flags"]:
        print("  ⚠ 红旗 %d 项：" % len(res["flags"]))
        for f in res["flags"]:
            print("    - " + f.split("：")[0])
    else:
        print("  无红旗")


if __name__ == "__main__":
    main()
