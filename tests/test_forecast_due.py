#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_forecast_due — 到期对账点名器的回归（v8 加时①）。

覆盖：状态分拣六桶（逾期/今日/7 天内/更远/已判/日期不可解析）、
render_md、main 退出码契约（0 无逾期未判 / 1 有逾期未判 / 2 日志不可读）。
离线：tmp 夹具，不碰真实 forecast_log。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("forecast_due", ROOT / "scripts" / "forecast_due.py")
fd = importlib.util.module_from_spec(_spec)
sys.modules["forecast_due"] = fd
_spec.loader.exec_module(fd)

TODAY = date(2026, 9, 27)


def _e(id, event_date, verified=False):
    return {"id": id, "event_date": event_date, "event": f"事件{id}",
            "verified": verified, "verdict": "x" if verified else None}


def test_scan_buckets():
    entries = [
        _e("a", str(TODAY - timedelta(days=10))),            # 逾期未判
        _e("b", TODAY.isoformat()),                          # 今日到期
        _e("c", str(TODAY + timedelta(days=5))),             # 7 天内
        _e("d", str(TODAY + timedelta(days=30))),            # 更远
        _e("e", "2026-Q4（窗口待定）"),                       # 不可解析
        _e("f", str(TODAY - timedelta(days=99)), verified=True),  # 已判
    ]
    b = fd.scan(entries, TODAY)
    assert [e["id"] for e in b["OVERDUE"]] == ["a"]
    assert b["OVERDUE"][0]["_overdue_days"] == 10
    assert [e["id"] for e in b["DUE"]] == ["b"]
    assert [e["id"] for e in b["UPCOMING"]] == ["c"]
    assert [e["id"] for e in b["LATER"]] == ["d"]
    assert [e["id"] for e in b["UNPARSED"]] == ["e"]
    assert [e["id"] for e in b["JUDGED"]] == ["f"]


def test_render_md_contains_marks():
    entries = [_e("a", str(TODAY - timedelta(days=3))), _e("b", TODAY.isoformat())]
    md = fd.render_md(fd.scan(entries, TODAY), TODAY)
    assert "⏳" in md and "逾期 3 天" in md and "🔔" in md and "判定纪律" in md


def test_main_exit_codes(tmp_path):
    log = tmp_path / "forecast_log.json"
    log.write_text(json.dumps({"entries": [_e("a", str(TODAY - timedelta(days=1)))]}),
                   encoding="utf-8")
    sys.argv = ["forecast_due.py", "--log", str(log)]
    assert fd.main() == 1  # 逾期未判 → 响铃

    log.write_text(json.dumps({"entries": [_e("a", str(TODAY + timedelta(days=9)))]}),
                   encoding="utf-8")
    sys.argv = ["forecast_due.py", "--log", str(log)]
    assert fd.main() == 0  # 无逾期未判

    sys.argv = ["forecast_due.py", "--log", str(tmp_path / "nope.json")]
    assert fd.main() == 2  # 日志不可读
