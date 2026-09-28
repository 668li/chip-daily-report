#!/usr/bin/env python3
"""
test_quality_dashboard.py —— F9 质量看板解析器回归测试

校验 quality_dashboard.parse_report 对真实历史报告的解析正确性，
防止解析逻辑在后续维护中静默失效（尤其来源 URL 分类、X 系列信号）。
"""
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "quality_dashboard", ROOT / "scripts" / "quality_dashboard.py"
)
qd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qd)

REG = yaml.safe_load((ROOT / "rules" / "rule_registry.yaml").read_text(encoding="utf-8"))
A = {d["domain"].lower() for d in REG["domains"]["a_level"]}
B = {d["domain"].lower() for d in REG["domains"]["b_level"]}
C = {d["domain"].lower() for d in REG["domains"]["c_level"]}


def report(name):
    return qd.parse_report(ROOT / name, A, B, C)


def test_20260727_core_metrics():
    r = report("芯片行业日报_20260727.md")
    # 22 条新闻，16 条 A 级（与自检表自述一致）
    assert r["computed_news"] == 22
    assert r["a_count"] == 16
    assert abs(r["a_ratio"] - 0.727) < 0.01
    # 5 环节全覆盖
    assert r["segment_coverage_count"] == 5
    # X14：含独立「来源分级统计」小节
    assert r["x14"] is True
    # X15：简写标题 ## EDA / ## 材料
    assert r["x15"] is True
    # X16：标题缺日期
    assert r["x16_title"] is False
    # 数据完整性对账：计算 72.7% vs 自述 33.3% 偏差 ~0.394
    assert r["declared_a_ratio"] is not None
    assert abs(r["ratio_gap"] - 0.394) < 0.02
    # X12：22 条 -> FAIL（>20，超路线 C 上限+缓冲；历史报告按现役口径回望）
    assert r["x12_grade"] == "FAIL"


def test_20260720_x11_and_count():
    r = report("芯片行业日报_20260720.md")
    assert r["computed_news"] == 11
    # 今日要点含股价 -> X11 命中
    assert r["x11"] is True
    # 标题含日期 -> X16 通过
    assert r["x16_title"] is True
    # 11 条 -> PASS（8-13 路线 C 目标区间）
    assert r["x12_grade"] == "PASS"


def test_20260722_count_and_grade():
    r = report("芯片行业日报_20260722.md")
    assert r["computed_news"] == 9
    # 9 条 -> PASS（8-13；旧口径 <10 FAIL 已随路线 C 废止）
    assert r["x12_grade"] == "PASS"
    # 标题含日期
    assert r["x16_title"] is True


def test_classify_parent_domain():
    # 父域匹配：semiconductor.samsung.com -> A（X8 统一父域）
    assert qd.classify("semiconductor.samsung.com", A, B, C) == "A"
    # www 前缀去除
    assert qd.classify("www.tsmc.com", A, B, C) == "A"
    # B 级子域
    assert qd.classify("m.toutiao.com", A, B, C) == "B"
    # 未注册域 -> 未知
    assert qd.classify("example.blog.com", A, B, C) == "U"
