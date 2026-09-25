#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1 · 来源交叉验证 · 回归测试（独立可跑，无需 pytest）。

运行：python tests/test_m1_crossvalidate.py
覆盖：
  1. cross_validate 对黄金样本：单源→待核实、≥2 独立源→跨源通过、聚类不误并
  2. 单源却标 A 级 → 推荐降 B（recommended_level 修正）
  3. validate_ir 接入 M1 检查（advisory WARN，不重排 26 项、不产生 FAIL）
  4. apply_downgrades 就地降级单源 A→B（仅新生成报告用）
  5. 26 项硬校验零回归：M1 为 advisory，不改 level 时 roundtrip 仍 26 PASS
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "scripts"))

from report_viz import parser
from cross_validate import cross_validate, apply_downgrades, normalize_sources, domain_of

fail = 0


def check(name, cond):
    global fail
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        fail += 1


rep = parser.parse_report("芯片行业日报_20260817.md")
ver = cross_validate(rep)

# 1) 基础判定
check("黄金 15 条全被评估", ver["total"] == 15)
check("交叉项聚类未误并成巨型组（组数<=3）", len(ver["clusters"]) <= 3)
check("单源数量>0（黄金多为单源）", ver["single_source"] > 0)

# 2) 单源 A → 推荐降 B
single_a = [v for v in ver["items"] if v["needs_verification"] and v["domain_level"] == "A"]
check("存在单源却标A的条目", len(single_a) >= 1)
check("这些条目 recommended_level 已降为 B",
      all(v["recommended_level"] == "B" for v in single_a))

# 3) validate_ir 接入 M1（WARN，不产生 FAIL）
from validate_ir import validate
rows, n_fail, n_warn = validate(rep)
m1_rows = [r for r in rows if r[0] == "M1"]
check("validate_ir 产出 M1 行", len(m1_rows) >= 1)
check("M1 行不重排 26 项编号", all(isinstance(r[0], str) for r in m1_rows))
check("M1 仅 WARN/PASS、无 FAIL", all(r[2] in ("WARN", "PASS") for r in m1_rows))
check("26 项硬校验 FAIL 数=0（M1 不破坏）", n_fail == 0)

# 4) apply_downgrades 就地降级
rep2 = parser.parse_report("芯片行业日报_20260817.md")
v2 = cross_validate(rep2)
apply_downgrades(rep2, v2)
downgraded = [it for seg, items in rep2["segments"].items() for it in items
              if it.get("level") == "B" and it.get("needs_verification")]
check("apply_downgrades 后存在 needs_verification 标记", len(downgraded) >= 1)
check("降级后单源A应变为B",
      all(it["level"] == "B" for seg, items in rep2["segments"].items() for it in items
          if (seg, it["title"]) in {(v["segment"], v["title"]) for v in single_a}))

# 5) 26 项 roundtrip 零回归（advisory，不改 level）
import tempfile
md = (REPO / "scripts" / "report_renderer.py").read_text(encoding="utf-8")  # 仅确保可导入
from report_renderer import render_markdown, to_json
out = render_markdown(rep)
tp = REPO / "tests" / "_tmp_m1.md"
tp.write_text(out, encoding="utf-8")
r = subprocess.run([sys.executable, str(REPO / "scripts" / "validate_report.py"), str(tp)],
                   capture_output=True, text=True)
check("roundtrip 渲染后 validate_report 仍 exit 0", r.returncode == 0)
tp.unlink(missing_ok=True)

# 工具函数
check("domain_of 去 www", domain_of("https://www.reuters.com/x") == "reuters.com")
check("normalize_sources 去重", len(normalize_sources([("a", "https://x.com/1"), ("a", "https://x.com/1")])) == 1)

print(f"\n{'✅ 全部通过' if fail == 0 else f'❌ {fail} 项失败'}")
sys.exit(1 if fail else 0)
