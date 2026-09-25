#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3/M5 多剧本并行打分 · 回归测试（独立可跑，无需 pytest）。

运行：python tests/test_m3_scenarios.py
覆盖：
  1. forecast_calibrator：真实日志（含剧本）场景统计正确 + 与 weekly_review 口径一致
  2. 向后兼容：无剧本日志 scenario_stats 全 0、不崩
  3. forecast_tracker：add --scenarios 挂接 + verify --scenario-id 按剧本验证
  4. weekly_review.build_scenario_review：渲染数据生成无异常
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))

import forecast_calibrator as fc
import weekly_review as wr
from forecast_tracker import _load_scenarios

fail = 0


def check(name, cond):
    global fail
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fail += 1


# 1) 真实日志（已含中芯国际 3 剧本）----------------------------------------
real = json.loads((REPO / "state" / "forecast_log.json").read_text(encoding="utf-8"))
r = fc.calibrate(real)
check("真实日志含 scenario_stats 字段", "scenario_stats" in r)
s = r["scenario_stats"]
check("真趋势命中率=1.0", s["真趋势"]["hit_rate"] == 1.0)
check("炒作命中率=1.0（被打脸即命中）", s["炒作"]["hit_rate"] == 1.0)
check("被绕开命中率=0.0（被打脸=失准）", s["被绕开"]["hit_rate"] == 0.0)
check("确定性档位统计仍在工作", r["stats_by_certainty"]["高确定性"]["total"] >= 1)

# 与 weekly_review 同口径
rev = wr.build_scenario_review(real)
check("weekly 口径与 calibrator 一致（真趋势）",
      rev["stance_stats"]["真趋势"]["hit_rate"] == s["真趋势"]["hit_rate"])
check("weekly 口径与 calibrator 一致（被绕开）",
      rev["stance_stats"]["被绕开"]["hit_rate"] == s["被绕开"]["hit_rate"])
check("M5 场景节事件含中芯国际剧本",
      any(any(sc["stance"] == "真趋势" for sc in ev["scenarios"])
          for ev in rev["events"] if "中芯" in ev["event"]))

# 2) 向后兼容：无剧本日志 --------------------------------------------------
no_scen = {"schema_version": 1, "entries": [
    {"id": "x1", "event": "E1", "certainty": "高确定性", "verified": True,
     "verdict": "一致", "verified_note": "ok"},
]}
r2 = fc.calibrate(no_scen)
check("无剧本日志 scenario_stats 全 0",
      all(v["total"] == 0 for v in r2["scenario_stats"].values()))
rev2 = wr.build_scenario_review(no_scen)
check("无剧本周度复盘返回空提示（不崩）",
      "暂无互斥剧本" in wr._md_scenario_review(rev2))
check("无剧本周度复盘 html 不崩",
      isinstance(wr._html_scenario_review(rev2), str))

# 3) forecast_tracker：挂剧本 + 按剧本验证（进程内 monkeypatch _LOG_FILE 测功能，不污染真实数据）
import forecast_tracker as ft

with tempfile.TemporaryDirectory() as td:
    logp = Path(td) / "forecast_log.json"
    logp.write_text(json.dumps({"schema_version": 1, "entries": []}, ensure_ascii=False),
                    encoding="utf-8")
    ft._LOG_FILE = logp  # 指向临时日志（_load/_save 读写 _LOG_FILE）
    scen_json = json.dumps([
        {"stance": "真趋势", "statement": "A 事件如期落地", "certainty": "高确定性"},
        {"stance": "炒作", "statement": "B 叙事被证伪", "certainty": "中确定性"},
    ], ensure_ascii=False)
    args_add = type("A", (), {
        "id": "t1", "report_date": "2026-08-21", "event_date": "2026-08-21",
        "event": "测试事件", "segment": "制造", "importance": "高",
        "certainty": "高确定性", "source": "https://x.com",
        "judged": "看落地", "scenarios": scen_json,
    })()
    check("tracker add 带 --scenarios 成功", ft.cmd_add(args_add) == 0)
    data = json.loads(logp.read_text(encoding="utf-8"))
    check("写入的条目含 scenarios 列表", len(data["entries"][0]["scenarios"]) == 2)
    check("剧本 id 自动补 -s1/-s2",
          data["entries"][0]["scenarios"][0]["id"] == "t1-s1"
          and data["entries"][0]["scenarios"][1]["id"] == "t1-s2")

    # 按剧本验证
    args_ver = type("V", (), {
        "id": "t1", "scenario_id": "t1-s1", "verdict": "一致",
        "note": "落地", "date": "2026-08-21",
    })()
    check("tracker verify --scenario-id 成功", ft.cmd_verify(args_ver) == 0)
    data = json.loads(logp.read_text(encoding="utf-8"))
    sc1 = data["entries"][0]["scenarios"][0]
    check("剧本 s1 被标记 verified+一致", sc1["verified"] and sc1["verdict"] == "一致")
    check("整条事件仍未被 verify", data["entries"][0]["verified"] is False)

# 4) _load_scenarios 容错 --------------------------------------------------
check("_load_scenarios 内联 JSON 解析",
      len(_load_scenarios('[{"stance":"炒作","statement":"X"}]')) == 1)
check("_load_scenarios 坏 JSON 返回 None（fail-soft）",
      _load_scenarios("not json") is None)

print(f"\n{'✅ 全部通过' if fail == 0 else f'❌ {fail} 项失败'}")
sys.exit(1 if fail else 0)
