#!/usr/bin/env python3
"""M0 回归测试：IR 渲染器是 parser 的忠实逆函数。

验证：golden 日报 → parser.parse_report → report_renderer.render_markdown
→ 重新跑 validate_report.py 必须 exit 0（26 项全 PASS），且新闻条数/章节一致。

这证明「结构化中间表示（IR）」可作为单一数据源：同一份 dict 既能渲染出
满足格式契约的 Markdown（校验对象），也能（后续）直接喂给 report_viz 生成 HTML，
从而退役脆弱的正则 parser。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from report_viz import parser  # noqa: E402
from report_renderer import render_markdown, from_json, to_json  # noqa: E402

GOLDEN = REPO / "芯片行业日报_20260817.md"
VALIDATE = REPO / "scripts" / "validate_report.py"
TMP = REPO / "delivery" / "_m0_roundtrip_test.md"


def test_parse_render_roundtrip_is_lossless_for_validation():
    """parse→render→validate 必须 26 项全 PASS，且核心计数一致。"""
    report = parser.parse_report(str(GOLDEN))
    md = render_markdown(report)

    TMP.write_text(md, encoding="utf-8")
    try:
        # IR 可序列化（JSON 单一数据源可用）
        blob = to_json(report)
        back = from_json(blob)
        assert back["news_count"] == report["news_count"]

        # 关键结构字段必须被 parser 完整捕获（M0 完整性门槛）
        assert len(report["catalysts"]) >= 1, "前瞻催化剂表格未被捕获"
        # v5.11 确定性列：至少有一条标了确定性
        assert any(c.get("certainty") for c in report["catalysts"]), "v5.11 确定性列丢失"
        assert report["forward_review"] and report["forward_review"]["items"], "前瞻兑现回顾未被捕获"
        assert report["catalyst_notes"], "前瞻解读块未被捕获"

        # 跑硬校验，必须 exit 0
        r = subprocess.run(
            [sys.executable, str(VALIDATE), str(TMP)],
            capture_output=True,
            text=True,
        )
        print(r.stdout)
        assert r.returncode == 0, f"validate 未通过 (exit {r.returncode})\n{r.stderr}\n{r.stdout}"
    finally:
        if TMP.exists():
            TMP.unlink()


def test_segment_news_count_matches_declared():
    report = parser.parse_report(str(GOLDEN))
    total = sum(len(v) for v in report["segments"].values())
    assert total == report["news_count"], f"环节新闻数 {total} != 声明 {report['news_count']}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
