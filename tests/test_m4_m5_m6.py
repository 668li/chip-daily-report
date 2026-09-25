#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4/M5/M6 闭环 · 回归测试（独立可跑，无需 pytest）。

运行：python tests/test_m4_m5_m6.py
覆盖：
  M4 规则自生长：suggest 分类正确（软FAIL→加强prompt / 硬WARN→修parser / 软WARN→放宽）；
                run() 真实 7 期不崩、写 state/rule_growth.json。
  M5 自动反写：build_block 聚合 M3/M4/M5 信号；rewrite 非破坏（锚点段插入、原文其余保留、
              同日去重）。
  M6 自我科研循环：--dry 串联 M3+M4 成功（不反写 SKILL、推进里程碑），写 evolution_loop.json。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))

import rule_growth as rg
import m5_rewrite_skill as m5

ANCHOR_TXT = "## 自动沉淀的注意点（M5 抗遗忘回路）"
fail = 0


def check(name, cond):
    global fail
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fail += 1


# ---------------- M4 ----------------
hist = []
for i in range(7):
    hist.append((f"202608{i}", [
        {"num": 14, "name": "技术注解", "result": "FAIL" if i < 5 else "PASS", "note": ""},
        {"num": 1, "name": "元信息", "result": "WARN" if i < 6 else "PASS", "note": ""},
        {"num": 20, "name": "信号层", "result": "WARN" if i < 4 else "PASS", "note": ""},
        {"num": 2, "name": "产业链完整性", "result": "PASS", "note": ""},
    ]))
agg = rg.tally(hist)
sugs = rg.suggest(agg)
acts = {s["name"]: s["action"] for s in sugs}
check("M4 软规则FAIL→tighten_prompt", acts.get("技术注解") == "tighten_prompt")
check("M4 硬规则WARN→fix_parser", acts.get("元信息") == "fix_parser")
check("M4 软规则WARN→relax_or_prompt", acts.get("信号层") == "relax_or_prompt")

# 真实 7 期不崩
r4 = rg.run()
check("M4 run() 真实数据期数=7", r4["reports_analyzed"] == 7)
check("M4 run() 写出 rule_growth.json", (REPO / "state" / "rule_growth.json").exists())

# ---------------- M5 ----------------
data = {"m3": [{"kind": "certainty", "certainty": "高确定性", "issue": "偏差率33%",
                "recommendation": "复核高确定性边界"}],
        "m4": [{"num": 14, "name": "技术注解", "kind": "soft",
                "recommendation": "加强 prompt 中明确技术注解要求"}],
        "scenario": "剧本命中率：升级=`真趋势`(100%)；淘汰=`被绕开`(0%)"}
block = m5.build_block(data, "2026-08-21")
check("M5 block 含 M3/M4/M5 三段", all(k in block for k in
      ["预判校准（M3）", "规则自生长（M4）", "剧本复盘（M5）"]))

# rewrite 非破坏 + 同日去重：用临时 SKILL 副本
with tempfile.TemporaryDirectory() as td:
    skill_p = Path(td) / "SKILL.md"
    orig = "# 标题\n\n## 其它段\n旧内容保留\n\n## 自动沉淀的注意点（M5 抗遗忘回路）\n> 说明\n\n### 规律沉淀 · 2026-08-20\n旧块\n"
    skill_p.write_text(orig, encoding="utf-8")
    new1 = m5.rewrite(skill_p, block, 8)
    skill_p.write_text(new1, encoding="utf-8")
    t = skill_p.read_text(encoding="utf-8")
    check("M5 锚点段保留", "## 自动沉淀的注意点" in t)
    check("M5 旧段内容未破坏", "旧内容保留" in t and "## 其它段" in t)
    check("M5 新块含当天日期", "### 规律沉淀 · 2026-08-21" in t)
    # 同日再写 → 去重为 1
    new2 = m5.rewrite(skill_p, block, 8)
    skill_p.write_text(new2, encoding="utf-8")
    import re
    n = len(re.findall(r"### 规律沉淀 · 2026-08-21", skill_p.read_text(encoding="utf-8")))
    check("M5 同日去重（同日期仅 1 块）", n == 1)

# 回归：正文引用锚点标题（行内文本）时，rewrite 仍只操作真正的锚点段
with tempfile.TemporaryDirectory() as td:
    skill_p = Path(td) / "SKILL.md"
    orig = ("# 标题\n\n正文引用「## 自动沉淀的注意点（M5 抗遗忘回路）」锚点段\n\n"
            "## 自动沉淀的注意点（M5 抗遗忘回路）\n> 说明\n\n"
            "### 规律沉淀 · 2026-08-20\n旧块\n\n## 其它段\n尾部\n")
    skill_p.write_text(orig, encoding="utf-8")
    out = m5.rewrite(skill_p, block, 8)
    check("M5 行内引用不被误当作锚点（引用行原样保留）",
          "正文引用「## 自动沉淀的注意点（M5 抗遗忘回路）」锚点段" in out)
    first = out.index(ANCHOR_TXT)
    second = out.index(ANCHOR_TXT, first + 1)  # 真正的锚点标题行
    i_block = out.index("### 规律沉淀 · 2026-08-21")
    i_other = out.index("## 其它段")
    check("M5 新块落在真正锚点段内（真标题之后、其它段之前）", second < i_block < i_other)

# ---------------- M6 ----------------
# --dry：串联 M3+M4（steps 仅 2 项），不反写 SKILL、不推进里程碑（临时 OUT，不污染真实 state）
import evolution_loop as evo
_orig_run, _orig_out, _orig_date, _orig_argv = evo._run, evo.OUT, evo.date, sys.argv


def _ok_run(script, *extra):
    return {"script": script, "rc": 0, "out": "ok", "err": ""}


class _FakeDate:
    @staticmethod
    def today():
        return type("D", (), {"isoformat": lambda self: fake["d"]})()


try:
    with tempfile.TemporaryDirectory() as td:
        evo.OUT = Path(td) / "evolution_loop.json"
        evo._run = _ok_run
        evo.date = _FakeDate
        fake = {"d": "2026-08-21"}

        sys.argv = ["evo", "--dry"]
        check("M6 --dry 退出码 0 且未推进里程碑", evo.main() == 0 and json.loads(
            evo.OUT.read_text(encoding="utf-8"))["auto_streak"] == 0)
        d = json.loads(evo.OUT.read_text(encoding="utf-8"))
        check("M6 --dry steps 仅 M3+M4 两项", len(d["runs"][-1]["steps"]) == 2)

        sys.argv = ["evo"]
        check("M6 首次全绿 → streak=1", evo.main() == 0 and json.loads(
            evo.OUT.read_text(encoding="utf-8"))["auto_streak"] == 1)
        n1 = len(json.loads(evo.OUT.read_text(encoding="utf-8"))["runs"])

        check("M6 同日 full 重跑 → streak 不虚增", evo.main() == 0 and json.loads(
            evo.OUT.read_text(encoding="utf-8"))["auto_streak"] == 1)
        check("M6 runs 追加且不超上限 50", len(json.loads(
            evo.OUT.read_text(encoding="utf-8"))["runs"]) == n1 + 1 <= 50)

        fake["d"] = "2026-08-22"
        check("M6 跨日全绿 → streak=2", evo.main() == 0 and json.loads(
            evo.OUT.read_text(encoding="utf-8"))["auto_streak"] == 2)

        def _fail_run(script, *extra):
            return {"script": script, "rc": 1 if script == "forecast_calibrator.py" else 0,
                    "out": "", "err": "boom"}
        evo._run = _fail_run
        rc = evo.main()
        d = json.loads(evo.OUT.read_text(encoding="utf-8"))
        check("M6 跨日失败 → 不倒扣 streak 且记录 failed",
              rc == 1 and d["auto_streak"] == 2 and d["runs"][-1]["failed"] == ["forecast_calibrator.py"])
finally:
    evo._run, evo.OUT, evo.date, sys.argv = _orig_run, _orig_out, _orig_date, _orig_argv

print(f"\n{'✅ 全部通过' if fail == 0 else f'❌ {fail} 项失败'}")
sys.exit(1 if fail else 0)
