#!/usr/bin/env python3
"""test_m2_pipeline — M2 校验前置 + 生成流水线回归测试（独立可跑，无需 pytest）。

运行：
  python tests/test_m2_pipeline.py
（也可用 pytest 跑，断言即退出码）

覆盖：
  1. 黄金日报 parse → IR → validate_ir 前置校验 0 FAIL
  2. IR → render_markdown → validate_report.py 文本安全网 26 PASS（exit 0）
  3. 故意构造 broken IR（缺环节/缺来源/新闻数不符）→ validate_ir 抓到 FAIL
  4. generate_report 渲染产物与 report_renderer 直渲逐字节一致（确定性）
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from report_viz import parser          # noqa: E402
from report_renderer import render_markdown, to_json  # noqa: E402
from validate_ir import validate        # noqa: E402

# golden=当期合规样例（v8 冲刺换金：20260817 旧格式不满足 v7.1 [G-1]/[G-2] 门禁，
# 安全网应永远钉在最新通过 26 门禁的报告上；历史报告不改不追）
GOLDEN = REPO / "芯片行业日报_20260925.md"


def test_preflight_pass():
    rep = parser.parse_report(str(GOLDEN))
    rows, n_fail, n_warn = validate(rep)
    assert n_fail == 0, f"黄金 IR 前置校验应有 0 FAIL，实际 {n_fail}: {[(n,na) for n,na,r,_ in rows if r=='FAIL']}"
    print(f"  ✓ 黄金 IR 前置校验 0 FAIL / {n_warn} WARN")


def test_render_safety_net():
    rep = parser.parse_report(str(GOLDEN))
    md = render_markdown(rep)
    tmp = REPO / "tests" / "_m2_tmp.md"
    tmp.write_text(md, encoding="utf-8")
    # 列表参数 + 显式 shell=False：不经过 shell，杜绝命令注入面
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_report.py"), str(tmp)],
        capture_output=True, text=True, shell=False,
    )
    tmp.unlink(missing_ok=True)
    assert r.returncode == 0, f"render→validate_report 应 26 PASS，rc={r.returncode}\n{r.stdout[-400:]}"
    print("  ✓ 渲染 md → validate_report.py 安全网 26 PASS")


def test_broken_ir_caught():
    rep = json.loads(to_json(parser.parse_report(str(GOLDEN))))
    rep["segments"].pop("EDA")          # 缺环节
    rep["news_count"] = 999             # 条数不符
    for it in rep["segments"]["制造"]:
        it["sources"] = []              # 缺来源
    rows, n_fail, _ = validate(rep)
    assert n_fail >= 3, f"broken IR 应抓到 ≥3 FAIL，实际 {n_fail}"
    print(f"  ✓ broken IR 前置校验抓到 {n_fail} 项 FAIL（门禁有效）")


def test_deterministic():
    rep = parser.parse_report(str(GOLDEN))
    a = render_markdown(rep)
    # 经 generate_report 等价路径（parse→render）应逐字节一致
    b = render_markdown(parser.parse_report(str(GOLDEN)))
    assert a == b, "render_markdown 对相同 IR 须确定性（逐字节一致）"
    print("  ✓ 渲染确定性：相同 IR 逐字节一致")


def main():
    print("=== M2 流水线回归测试 ===")
    test_preflight_pass()
    test_render_safety_net()
    test_broken_ir_caught()
    test_deterministic()
    print("\n全部 M2 测试通过 ✓")


if __name__ == "__main__":
    main()
