#!/usr/bin/env python3
"""signal_history.py 回归测试（迭代5 · 信号历史累积）。

覆盖：
  1. norm_date 归一化（带横线 / 纯数字）
  2. snapshot_topics 洗快照（过滤非法方向、缺 topic）
  3. upsert 幂等（同日覆盖不重复累积）
  4. run 缺 state 文件 fail-soft 返回 None
  5. run 已存在快照跳过 / --force 覆盖
"""
import json
from pathlib import Path

import pytest

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "scripts"))
import signal_history as sh

# 构造隔离的临时 state 目录（不污染真实项目）
TMP_STATE = Path(__file__).resolve().parent / "_tmp_state"


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch, tmp_path):
    """把 sh 的 STATE_YAML / HISTORY_JSON 指向临时目录。"""
    state_yaml = tmp_path / "report_state.yaml"
    hist_json = tmp_path / "signal_history.json"
    monkeypatch.setattr(sh, "STATE_YAML", state_yaml)
    monkeypatch.setattr(sh, "HISTORY_JSON", hist_json)
    monkeypatch.setattr(sh, "ROOT", tmp_path)
    return state_yaml


def _write_state(path: Path, last_date: str, topics: list) -> None:
    import yaml

    data = {"last_report_date": last_date, "tracked_topics": topics}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


TOPICS = [
    {"topic": "HBM 价格与供需", "direction": "down", "streak": 1, "signal": "高/利空/负面"},
    {"topic": "先进封装产能紧缺", "direction": "tight", "streak": 4, "signal": "高/利好/正面"},
    {"topic": "坏主题（非法方向）", "direction": "sideways", "streak": 1, "signal": "—"},
    {"topic": "", "direction": "up", "streak": 1, "signal": "—"},
]


# ---------------- 1 norm_date ----------------

def test_norm_date_variants():
    assert sh.norm_date("2026-08-09") == "20260809"
    assert sh.norm_date("20260809") == "20260809"
    assert sh.norm_date("2026/08/09") == "20260809"
    assert sh.norm_date("") == ""
    assert sh.norm_date("abc") == "abc"  # 非日期原样


# ---------------- 2 snapshot_topics ----------------

def test_snapshot_filters_invalid():
    snap = sh.snapshot_topics({"tracked_topics": TOPICS})
    topics = [s["topic"] for s in snap]
    assert "HBM 价格与供需" in topics
    assert "先进封装产能紧缺" in topics
    # 非法方向 / 空 topic 被过滤
    assert all(s["direction"] in sh.VALID_DIRECTIONS for s in snap)
    assert "坏主题（非法方向）" not in topics
    assert "" not in topics


def test_snapshot_defaults():
    snap = sh.snapshot_topics({"tracked_topics": [
        {"topic": "X", "direction": "UP"},  # 大写归一
    ]})
    assert snap == [{"topic": "X", "direction": "up", "streak": 1, "signal": "中/中性/中性"}]


# ---------------- 3 upsert 幂等 ----------------

def test_upsert_idempotent(_isolate_state):
    hist = sh.upsert([], "20260809", [{"topic": "X", "direction": "up", "streak": 1}])
    assert len(hist) == 1
    # 同日再次 upsert -> 覆盖不重复
    hist = sh.upsert(hist, "20260809", [{"topic": "X", "direction": "down", "streak": 1}])
    assert len(hist) == 1
    assert hist[0]["topics"][0]["direction"] == "down"
    # 新日期追加 + 排序
    hist = sh.upsert(hist, "20260808", [{"topic": "Y", "direction": "up", "streak": 3}])
    assert [h["date"] for h in hist] == ["20260808", "20260809"]


# ---------------- 4 fail-soft ----------------

def test_run_missing_state(_isolate_state, capsys):
    """无 state 文件 -> None，不抛异常。"""
    assert sh.run() is None
    out = capsys.readouterr().out
    assert "跳过" in out


def test_run_no_valid_topics(_isolate_state):
    _write_state(_isolate_state, "20260809", [{"topic": "", "direction": "up"}])
    assert sh.run() is None


# ---------------- 5 run 跳过 / 覆盖 ----------------

def test_run_append_then_skip_then_force(_isolate_state):
    _write_state(_isolate_state, "2026-08-09", TOPICS[:2])
    entry = sh.run()
    assert entry is not None and entry["date"] == "20260809"
    assert len(entry["topics"]) == 2

    # 已存在 -> 跳过
    assert sh.run() is None
    # --force -> 覆盖
    entry2 = sh.run(force=True)
    assert entry2 is not None and entry2["date"] == "20260809"
    hist = sh.load_history()
    assert len(hist) == 1  # 仍未重复


def test_run_explicit_date(_isolate_state):
    _write_state(_isolate_state, "20260809", TOPICS[:1])
    # 先按 state 默认日期累积
    sh.run()
    # 再显式指定日期
    entry = sh.run(date_str="20260810")
    assert entry["date"] == "20260810"
    hist = sh.load_history()
    assert [h["date"] for h in hist] == ["20260809", "20260810"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
