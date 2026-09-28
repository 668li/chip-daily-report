#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_runner — 每日心跳一条命令（v8 护城河冲刺 P0-0，2026-09-26）。

定位：机械链路的**入口与验收器**，不是内容生成器——日报正文创作是 LLM 会话
按 SKILL.md 六步流程干的活（ADR-002）。定时任务每天唤起会话 → 会话先跑本脚本
prepare → 按 SKILL.md 生成当期日报 → 再跑本脚本 verify → commit/push。

用法：
  python scripts/daily_runner.py --stage prepare                  # 发现层 quick + 候选池（生成前）
  python scripts/daily_runner.py --stage verify --report <md>     # 校验 + HTML 构建（生成后）
  python scripts/daily_runner.py --all --report <md>              # 全链路
  加 --dry-run：verify 的 HTML 写入临时目录，不碰 delivery/（验收演练用）

阶段与失败语义（任一 fatal 步失败 → 非零退出，并指明哪步炸了；ADR-001）：
  prepare:  ① discover.py --mode quick（fatal）② prepare_candidates.py（fatal；
            但候选=0 只 WARN——新闻淡日合法，链路炸了才是 FAIL）
  verify:   ① validate_report.py 26 项（fatal，须 exit 0）
            ② forecast_due.py 推演到期点名（fatal，逾期未判不许收工）
            ③ validate_understanding.py 理解层存在性校验（脚本存在则 fatal）
            ④ validate_claims.py 声明级对账（v8 R2：承重数字对照原文，
               对不上不出版；脚本存在则 fatal，首跑含真实网络抓取）
            ⑤ build_report_html.py（fatal）
            ⑥ 后置 fail-soft：signal_history / quality_dashboard（只 WARN 不破退出码）

诚实性约定：prepare 失败时定时会话应如实响铃，但仍可按 SKILL.md fail-soft
继续生成当期日报（交付韧性归 SKILL 流程管，问责归本脚本管）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISCOVER = ROOT / "scripts" / "multi_source" / "discover.py"
PREPARE = ROOT / "scripts" / "multi_source" / "prepare_candidates.py"
VALIDATE = ROOT / "scripts" / "validate_report.py"
VALIDATE_U = ROOT / "scripts" / "validate_understanding.py"
VALIDATE_CLAIMS = ROOT / "scripts" / "validate_claims.py"
BUILD_HTML = ROOT / "scripts" / "build_report_html.py"
SIGNAL_HISTORY = ROOT / "scripts" / "signal_history.py"
QUALITY_DASH = ROOT / "scripts" / "quality_dashboard.py"
FORECAST_DUE = ROOT / "scripts" / "forecast_due.py"
GATE_REPORT = ROOT / "state" / "gate_report.json"

PREPARE_TIMEOUT = 1200  # 发现层含网络探测，给足预算
VERIFY_TIMEOUT = 300
HEARTBEAT_FILE = ROOT / "state" / "heartbeat.json"   # 死亡开关状态（v8 R5-C）
HEARTBEAT_STALE_HOURS = 48  # 超过 48h 无成功心跳记录 → 红灯（工作日口径下两个跳距）

_results: list[tuple[str, str, str]] = []  # (stage, step, OK/WARN/FAIL + 备注)


def _write_heartbeat(stage: str) -> None:
    """v8 R5-C 死亡开关（四维审查最优先建议落地）：每次 runner 成功完成任一阶段
    就刷新最后成功时间——心跳死了，这个文件的时间戳就是尸体温度。
    fail-soft：写失败不阻塞流程，但打印。"""
    try:
        import json
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(json.dumps({
            "last_ok_stage": stage,
            "last_ok_ts": time.time(),
            "last_ok_date": time.strftime("%F %T"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[daily_runner] ⚠ heartbeat 写入失败（不阻塞）：{e}")


def check_heartbeat() -> None:
    """启动时读死亡开关：>48h 无成功记录 → 静默红灯打印（不阻塞本次运行——
    本次就是来救活它的）；文件不存在=从未成功过，同样红灯。
    消费者不止本脚本：任何会话（CLAUDE.md 约定）启动时都可读此文件亮红灯。"""
    import json
    try:
        rec = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
        age_h = (time.time() - float(rec["last_ok_ts"])) / 3600.0
        last = rec.get("last_ok_date", "?")
    except Exception:
        print("[daily_runner] ⛔ 心跳红灯：state/heartbeat.json 不存在或不可读"
              "——从未有过成功心跳记录（死亡开关，v8 R5-C）")
        return
    if age_h > HEARTBEAT_STALE_HOURS:
        print(f"[daily_runner] ⛔ 心跳红灯：上次成功心跳在 {last}"
              f"（{age_h:.0f}h 前 > {HEARTBEAT_STALE_HOURS}h 阈值）"
              "——心跳可能已静默死亡，请人工核查定时任务与配额")


def _run(step: str, stage: str, cmd: list[str], *, fatal: bool = True,
         timeout: int = 300) -> bool:
    """跑一步子命令；fatal 步失败记 FAIL 并由调用方终止，fail-soft 步只 WARN。"""
    t0 = time.time()
    print(f"\n[daily_runner] ▶ {stage}/{step}: {' '.join(cmd[1:])}")
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), timeout=timeout,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        _results.append((stage, step, f"FAIL 超时>{timeout}s"))
        print(f"[daily_runner] ✗ {stage}/{step} 超时（>{timeout}s）")
        return False
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-12:])
    dur = time.time() - t0
    if proc.returncode == 0:
        _results.append((stage, step, f"OK {dur:.0f}s"))
        print(f"[daily_runner] ✓ {stage}/{step} 通过（{dur:.0f}s）")
        if tail:
            print("    " + "\n    ".join(tail.splitlines()[-4:]))
        return True
    _results.append((stage, step, f"FAIL exit={proc.returncode} {dur:.0f}s"))
    print(f"[daily_runner] ✗ {stage}/{step} 失败 exit={proc.returncode}（{dur:.0f}s）")
    print("---- 该步输出末尾 ----")
    print(tail)
    if fatal:
        return False
    _results[-1] = (stage, step, f"WARN exit={proc.returncode}（fail-soft 不破退出码）")
    return True


def stage_prepare() -> bool:
    check_heartbeat()  # v8 R5-C 死亡开关：先验尸再干活
    ok = _run("discover-quick", "prepare",
              [sys.executable, str(DISCOVER), "--mode", "quick"],
              fatal=True, timeout=PREPARE_TIMEOUT)
    if not ok:
        return False
    ok = _run("prepare-candidates", "prepare",
              [sys.executable, str(PREPARE)], fatal=True, timeout=PREPARE_TIMEOUT)
    if not ok:
        return False
    # 推演到期点名（prepare 阶段容错预警：逾期未判在此可见，生成会话应先补判定）
    if Path(FORECAST_DUE).exists():
        _run("forecast-due", "prepare",
             [sys.executable, str(FORECAST_DUE)], fatal=False, timeout=VERIFY_TIMEOUT)
    # prepare_candidates 内部 fail-soft 永远 exit 0——问责看产物：空候选=淡日WARN，
    # 带 error 的空池=链路 FAIL
    try:
        import json
        gate = json.loads(GATE_REPORT.read_text(encoding="utf-8"))
        n = gate.get("stats", {}).get("candidates", 0)
        if gate.get("error"):
            _results.append(("prepare", "gate-report", f"FAIL 候选池带错误: {gate['error']}"))
            print(f"[daily_runner] ✗ prepare/gate-report 候选池带错误: {gate['error']}")
            return False
        if n == 0:
            _results.append(("prepare", "gate-report", "WARN 候选=0（新闻淡日？人工确认）"))
            print("[daily_runner] ⚠ prepare/gate-report 候选 0 条（淡日合法，请人工确认采集源）")
        else:
            _results.append(("prepare", "gate-report", f"OK 候选 {n} 条"))
            print(f"[daily_runner] ✓ prepare/gate-report 候选 {n} 条")
    except Exception as e:  # noqa: BLE001 —— 产物读不出=链路坏
        _results.append(("prepare", "gate-report", f"FAIL 产物不可读: {e}"))
        print(f"[daily_runner] ✗ prepare/gate-report 不可读: {e}")
        return False
    _write_heartbeat("prepare")
    return True


def _report_date(report: Path) -> str | None:
    m = re.search(r"(\d{8})", report.stem)
    return m.group(1) if m else None


def stage_verify(report: Path, dry_run: bool) -> bool:
    if not report.exists():
        _results.append(("verify", "report-exists", f"FAIL 找不到 {report}"))
        print(f"[daily_runner] ✗ verify/report-exists 找不到 {report}")
        return False

    if not _run("validate-report-26", "verify",
                [sys.executable, str(VALIDATE), str(report)],
                fatal=True, timeout=VERIFY_TIMEOUT):
        return False

    # 推演到期点名（verify 阶段强制：日报兑现回顾写完仍有人逾期未判 = 不许收工）
    if Path(FORECAST_DUE).exists():
        if not _run("forecast-due", "verify",
                    [sys.executable, str(FORECAST_DUE)],
                    fatal=True, timeout=VERIFY_TIMEOUT):
            return False

    if VALIDATE_U.exists():
        if not _run("validate-understanding", "verify",
                    [sys.executable, str(VALIDATE_U), str(report)],
                    fatal=True, timeout=VERIFY_TIMEOUT):
            return False
    else:
        _results.append(("verify", "validate-understanding", "WARN 未安装，跳过"))

    # 声明级对账（v8 R2 源深水区）：承重数字逐条对照来源原文，对不上不出版。
    # 首跑含真实网络抓取（≤max-fetch 条 × 10s），给长超时；缓存命中后变快。
    if VALIDATE_CLAIMS.exists():
        if not _run("validate-claims", "verify",
                    [sys.executable, str(VALIDATE_CLAIMS), str(report)],
                    fatal=True, timeout=PREPARE_TIMEOUT):
            return False

    html_out = Path(tempfile.mkdtemp(prefix="daily_runner_dryrun_")) if dry_run else ROOT / "delivery"
    if not _run("build-html", "verify",
                [sys.executable, str(BUILD_HTML), str(report), "--out", str(html_out)],
                fatal=True, timeout=VERIFY_TIMEOUT):
        return False
    _results.append(("verify", "html-out", f"OK {html_out}{'（dry-run 临时目录）' if dry_run else ''}"))

    # 后置 fail-soft：不破退出码，但失败可见
    date = _report_date(report)
    post = [[sys.executable, str(SIGNAL_HISTORY)] + (["--date", date] if date else []),
            [sys.executable, str(QUALITY_DASH)]]
    for cmd in post:
        if Path(cmd[1]).exists():
            _run(Path(cmd[1]).stem, "verify-post", cmd, fatal=False, timeout=VERIFY_TIMEOUT)
    _write_heartbeat("verify")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="每日心跳一条命令（prepare=生成前 / verify=生成后）")
    ap.add_argument("--stage", choices=["prepare", "verify"], help="单跑一个阶段")
    ap.add_argument("--all", action="store_true", help="prepare + verify 全链路")
    ap.add_argument("--report", default="", help="verify 阶段的日报 md 路径")
    ap.add_argument("--dry-run", action="store_true", help="HTML 写临时目录，不碰 delivery/")
    args = ap.parse_args()

    if not args.all and not args.stage:
        ap.error("需要 --stage prepare|verify 或 --all")

    t0 = time.time()
    print(f"[daily_runner] 心跳启动 {time.strftime('%F %T')} stage={'all' if args.all else args.stage}")
    ok = True
    if args.all or args.stage == "prepare":
        ok = stage_prepare()
    if ok and (args.all or args.stage == "verify"):
        if not args.report:
            print("[daily_runner] ✗ verify 需要 --report <日报md路径>")
            return 2
        ok = stage_verify(Path(args.report), args.dry_run)

    print("\n[daily_runner] ═══ 心跳总结 ═══")
    for stage, step, note in _results:
        mark = "✓" if note.startswith("OK") else ("⚠" if note.startswith("WARN") else "✗")
        print(f"  {mark} {stage}/{step}: {note}")
    total = time.time() - t0
    if ok:
        print(f"[daily_runner] ✓ 全部 fatal 步通过（总 {total:.0f}s）")
        return 0
    print(f"[daily_runner] ✗ 存在 fatal 失败步（总 {total:.0f}s）——定时会话请如实响铃，"
          f"再按 SKILL.md fail-soft 决定是否降级交付")
    return 1


if __name__ == "__main__":
    sys.exit(main())
