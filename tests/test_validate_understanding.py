#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_validate_understanding — 理解层校验 v1 的回归红灯（P0-B 防注水锚）。

纪律（发射提示词）：新增门禁必须带「第 1 期缺陷样本回归红灯」——
从试产第 1 期真实报告构造缺陷副本（写在 tmp_path，**不碰真实历史文件**），
validate_understanding 必须对每个缺陷样本 FAIL；对原版必须 PASS。

离线测试：纯文本处理，不联网、不写 state。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPORT1 = ROOT / "芯片行业日报_20260925.md"

_spec = importlib.util.spec_from_file_location(
    "validate_understanding", ROOT / "scripts" / "validate_understanding.py")
vu = importlib.util.module_from_spec(_spec)
sys.modules["validate_understanding"] = vu
_spec.loader.exec_module(vu)


def _fails(rows) -> dict[str, str]:
    return {code: verdict for code, _d, verdict in rows if verdict.startswith("FAIL")}


@pytest.fixture(scope="module")
def report1_text() -> str:
    assert REPORT1.exists(), "试产第 1 期报告应在仓库根目录"
    return REPORT1.read_text(encoding="utf-8")


def _defect_copy(tmp_path: Path, report1_text: str, mutate) -> str:
    """构造缺陷副本（tmp 内），返回文本。"""
    mutated = mutate(report1_text)
    p = tmp_path / "defect_sample.md"
    p.write_text(mutated, encoding="utf-8")
    return mutated


def test_report1_passes(report1_text):
    """正向对照：第 1 期（v6.2 合规版）必须全 PASS。"""
    rows = vu.validate_text(report1_text)
    assert _fails(rows) == {}, f"原版不应有 FAIL: {_fails(rows)}"


def test_defect_missing_knowledge_anchor(report1_text, tmp_path):
    """缺陷样本①：推演块被删掉知识锚（v6.2 之前旧式文本）→ U4 必须 FAIL。"""
    def mutate(t: str) -> str:
        return "\n".join(ln for ln in t.splitlines() if "**知识锚**" not in ln)
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U4" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_missing_growth_meaning(report1_text, tmp_path):
    """缺陷样本②：成长含义整行删除 → U5 必须 FAIL。"""
    def mutate(t: str) -> str:
        return "\n".join(ln for ln in t.splitlines() if "**成长含义**" not in ln)
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U5" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_missing_verify_window(report1_text, tmp_path):
    """缺陷样本③：验证窗口行删除 → U6 必须 FAIL（不可对账的推演不许出版）。"""
    def mutate(t: str) -> str:
        return "\n".join(ln for ln in t.splitlines() if "**验证窗口**" not in ln)
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U6" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_empty_anchor_still_fails(report1_text, tmp_path):
    """缺陷样本④（注水锚）：知识锚标签在但内容被掏空 → U4 必须 FAIL。"""
    def mutate(t: str) -> str:
        return "\n".join(
            "- **知识锚**：" if ln.strip().startswith("- **知识锚**：") else ln
            for ln in t.splitlines())
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U4" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_no_feynman_section(report1_text, tmp_path):
    """缺陷样本⑤：费曼解释节整体删除 → U3 必须 FAIL。"""
    def mutate(t: str) -> str:
        lines, skip = [], False
        for ln in t.splitlines():
            if ln.startswith("## 费曼解释"):
                skip = True
                continue
            if skip and ln.startswith("## "):
                skip = False
            if not skip:
                lines.append(ln)
        return "\n".join(lines)
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U3" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_stub_lesson(report1_text, tmp_path):
    """缺陷样本⑥：深度第一课掏成占位一句 → U2 必须 FAIL（teach 槽防空转）。"""
    def mutate(t: str) -> str:
        lines, in_lesson = [], False
        for ln in t.splitlines():
            if ln.startswith("### 深度第一课"):
                in_lesson = True
                lines.append(ln)
                lines.append("")
                lines.append("（本课略。）")
                continue
            if in_lesson and (ln.startswith("### ") or ln.startswith("## ")):
                in_lesson = False
            if not in_lesson:
                lines.append(ln)
        return "\n".join(lines)
    _defect_copy(tmp_path, report1_text, mutate)
    assert "U2" in _fails(vu.validate_text(mutate(report1_text)))


def test_defect_no_lesson_section(report1_text, tmp_path):
    """缺陷样本⑦：今日导师课整节删除 → U1+U2 必须 FAIL。"""
    def mutate(t: str) -> str:
        lines, skip = [], False
        for ln in t.splitlines():
            if ln.startswith("## 今日导师课"):
                skip = True
                continue
            if skip and ln.startswith("## "):
                skip = False
            if not skip:
                lines.append(ln)
        return "\n".join(lines)
    _defect_copy(tmp_path, report1_text, mutate)
    f = _fails(vu.validate_text(mutate(report1_text)))
    assert "U1" in f and "U2" in f


def test_main_exit_codes(report1_text, tmp_path):
    """main() 退出码契约：原版 0；缺陷副本 1；缺文件 2。"""
    good = tmp_path / "good.md"
    good.write_text(report1_text, encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("\n".join(ln for ln in report1_text.splitlines()
                             if "**知识锚**" not in ln), encoding="utf-8")
    sys.argv = ["validate_understanding.py", str(good)]
    assert vu.main() == 0
    sys.argv = ["validate_understanding.py", str(bad)]
    assert vu.main() == 1
    sys.argv = ["validate_understanding.py", str(tmp_path / "nope.md")]
    assert vu.main() == 2
